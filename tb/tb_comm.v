`timescale 1ns/1ps
// tb_comm.v  -  testbench for P5's communication code (with the dummy CNN)
// Pretends to be the laptop: sends frames, reads replies, prints PASS / FAIL.
module tb_comm;
    // small numbers so the simulation is quick
`ifndef TEST_CPB
`define TEST_CPB 16
`endif
`ifndef TEST_TIMEOUT
`define TEST_TIMEOUT 3000
`endif
    localparam CPB     = `TEST_CPB;             // clocks per UART bit
    localparam TIMEOUT = `TEST_TIMEOUT;     // clocks

    reg clk = 0;
    always #5 clk = ~clk;                   // 100 MHz

    reg        rx = 1'b1;
    wire       tx;
    reg        live_mode = 1;
    reg  [3:0] stored_sel = 0;
    reg        tb_start = 0;

    wire [7:0]   img_raddr, img_rdata;
    wire         cnn_start_uart, cnn_done, uart_err;
    wire [2:0]   cnn_class;
    wire [191:0] cnn_scores;
    wire [31:0]  cnn_cycles;

    comm_top #(.CLKS_PER_BIT(CPB), .TIMEOUT_CLKS(TIMEOUT)) dut (
        .clk(clk), .rx(rx), .tx(tx),
        .live_mode(live_mode), .stored_sel(stored_sel),
        .img_raddr(img_raddr), .img_rdata(img_rdata),
        .cnn_start(cnn_start_uart), .cnn_done(cnn_done),
        .cnn_class(cnn_class), .cnn_scores(cnn_scores), .cnn_cycles(cnn_cycles),
        .uart_err(uart_err));

    dummy_cnn cnn (
        .clk(clk), .start(cnn_start_uart | tb_start), .done(cnn_done),
        .img_addr(img_raddr), .img_pixel(img_rdata),
        .class_id(cnn_class), .scores(cnn_scores), .cycles(cnn_cycles));

    // ------------------------------------------------------------------
    // "laptop" helpers
    // ------------------------------------------------------------------
    task send_byte(input [7:0] b);
        integer i;
        begin
            rx = 0;                         repeat (CPB) @(posedge clk);   // start bit
            for (i = 0; i < 8; i = i + 1) begin
                rx = b[i];                  repeat (CPB) @(posedge clk);   // data bits, LSB first
            end
            rx = 1;                         repeat (CPB) @(posedge clk);   // stop bit
        end
    endtask

    task recv_byte(output [7:0] b);
        integer i;
        begin
            @(negedge tx);                              // start bit begins
            repeat (CPB + CPB/2) @(posedge clk);        // jump to the middle of data bit 0
            for (i = 0; i < 8; i = i + 1) begin
                b[i] = tx;
                repeat (CPB) @(posedge clk);
            end
        end
    endtask

    reg [7:0] pix [0:255];
    reg [7:0] reply [0:31];
    integer   errors = 0;

    // Send  A5 | cmd | 256 pixels | checksum(+chk_fudge)
    task send_request(input [7:0] cmd, input [7:0] chk_fudge, input integer n_pixels);
        integer i;
        reg [7:0] sum;
        begin
            sum = cmd;
            send_byte(8'hA5);
            send_byte(cmd);
            for (i = 0; i < n_pixels; i = i + 1) begin
                send_byte(pix[i]);
                sum = sum + pix[i];
            end
            if (n_pixels == 256) send_byte(sum + chk_fudge);
        end
    endtask

    task read_reply;
        integer i;
        begin
            for (i = 0; i < 32; i = i + 1) recv_byte(reply[i]);
        end
    endtask

    task check(input cond, input [255:0] what);
        begin
            if (cond !== 1'b1) begin
                errors = errors + 1;
                $display("  FAIL: %0s", what);
            end
        end
    endtask

    // checks that are the same for every reply
    task check_reply_basics(input [7:0] want_status);
        integer i;
        reg [7:0] s;
        begin
            s = 0;
            for (i = 1; i <= 30; i = i + 1) s = s + reply[i];
            check(reply[0]  == 8'h5A,       "sync byte is 5A");
            check(reply[1]  == want_status, "status");
            check(reply[31] == s,           "reply checksum");
        end
    endtask

    integer starts = 0, reply_sends = 0;
    always @(posedge clk) begin
        if (cnn_start_uart) starts = starts + 1;
        if (dut.tx_send) reply_sends = reply_sends + 1;
    end
    reg [7:0] bad_checksum;
    integer starts_before, replies_before;

    task send_bad_stop(input [7:0] b);
        integer j;
        begin
            @(negedge clk);
            rx = 0; repeat (CPB) @(negedge clk);
            for (j = 0; j < 8; j = j + 1) begin
                rx = b[j]; repeat (CPB) @(negedge clk);
            end
            rx = 0; repeat (CPB) @(negedge clk);
            rx = 1; repeat (2*CPB) @(negedge clk);
        end
    endtask

    integer i, expect_sum;
    reg [2:0] expect_class;
    reg [23:0] sc;

    initial begin
`ifdef DUMP
        $dumpfile("tb_comm.vcd");
        $dumpvars(0, tb_comm);
`endif
        repeat (20) @(posedge clk);

        // ---------- TEST 1: good picture from the laptop ----------
        $display("TEST 1: good picture (live mode)");
        expect_sum = 0;
        for (i = 0; i < 256; i = i + 1) begin
            pix[i] = (i % 7) * 3;
            expect_sum = expect_sum + pix[i];
        end
        expect_class = expect_sum % 8;
        fork
            send_request(8'h01, 8'h00, 256);
            read_reply;
        join
        check_reply_basics(8'h00);
        check(reply[2] == {5'd0, expect_class}, "class = pixel sum mod 8");
        check({reply[3], reply[4], reply[5], reply[6]} > 256, "cycles > 256");
        for (i = 0; i < 8; i = i + 1) begin
            sc = {reply[7+3*i], reply[8+3*i], reply[9+3*i]};
            check(sc == ((i == expect_class) ? 24'd1000 : i*10), "score value");
        end
        check(uart_err == 0, "uart_err stays 0");
        $display("  class=%0d  cycles=%0d", reply[2], {reply[3], reply[4], reply[5], reply[6]});

        // ---------- TEST 2: wrong checksum ----------
        $display("TEST 2: wrong checksum");
        fork
            send_request(8'h01, 8'h01, 256);
            read_reply;
        join
        check_reply_basics(8'h01);
        check(uart_err == 1, "uart_err = 1");

        // ---------- TEST 3: unknown command ----------
        $display("TEST 3: unknown command");
        fork
            send_request(8'h77, 8'h00, 256);
            read_reply;
        join
        check_reply_basics(8'h03);

        // ---------- TEST 4: frame stops half-way (timeout) ----------
        $display("TEST 4: timeout, then recover");
        send_request(8'h01, 8'h00, 10);                 // only 10 pixels, then silence
        repeat (TIMEOUT + 200) @(posedge clk);
        check(uart_err == 1, "uart_err = 1 after timeout");
        check(tx == 1, "no reply is being sent");
        fork
            send_request(8'h01, 8'h00, 256);            // next frame must work again
            read_reply;
        join
        check_reply_basics(8'h00);
        check(reply[2] == {5'd0, expect_class}, "class after recovery");
        check(uart_err == 0, "uart_err cleared by good frame");

        // ---------- TEST 5: stored pictures (no UART) ----------
        $display("TEST 5: stored pictures");
        live_mode = 0;
        for (i = 0; i < 16; i = i + 1) begin
            stored_sel = i;
            @(posedge clk); tb_start = 1; @(posedge clk); tb_start = 0;
            @(posedge cnn_done); @(posedge clk);
            check(cnn_class == (i % 8), "stored picture n -> class n mod 8");
        end

        // ---------- TEST 6: invalid checksum stop bit, then recover ----------
        $display("TEST 6: invalid stop bit, timeout, then recover");
        live_mode = 1;
        starts_before = starts;
        replies_before = reply_sends;
        send_request(8'h01, 8'h00, 255);
        send_byte(pix[255]);
        // Same checksum as a valid request, but its stop bit is LOW.
        bad_checksum = 8'h01;
        for (i = 0; i < 256; i = i + 1) bad_checksum = bad_checksum + pix[i];
        send_bad_stop(bad_checksum);
        repeat (TIMEOUT + 200) @(posedge clk);
        check(starts == starts_before, "bad stop must not start CNN");
        check(reply_sends == replies_before, "bad stop must not send reply");
        check(uart_err == 1, "bad stop frame times out");
        fork
            send_request(8'h01, 8'h00, 256);
            read_reply;
        join
        check_reply_basics(8'h00);
        check(reply[2] == {5'd0, expect_class}, "class after bad stop recovery");
        check(uart_err == 0, "good frame clears error");

        if (errors != 0) $fatal(1, "%0d CHECK(S) FAILED", errors);
        $display("ALL TESTS PASSED");
        $finish;
    end

    initial begin                       // safety stop
        #200_000_000;
        $fatal(1, "TIMEOUT: testbench hung");
    end
endmodule
