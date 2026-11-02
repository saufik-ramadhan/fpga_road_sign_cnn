`timescale 1ns/1ps
// Direct RX tests, including framing errors and break recovery.
module tb_uart_rx;
    parameter CPB = 16;
    reg clk = 0;
    always #5 clk = ~clk;
    reg rx = 1;
    wire [7:0] data;
    wire valid;
    integer count = 0;
    reg [7:0] received [0:15];
    reg prev_valid = 0;

    uart_rx #(.CLKS_PER_BIT(CPB)) dut (
        .clk(clk), .rx(rx), .data(data), .valid(valid));

    always @(posedge clk) begin
        if (valid === 1'b1) begin
            if (prev_valid) $fatal(1, "valid is longer than one clock");
            received[count] = data;
            count = count + 1;
        end
        prev_valid <= valid;
    end

    task send_byte(input [7:0] b, input stop_high);
        integer i;
        begin
            rx = 0; repeat (CPB) @(negedge clk);
            for (i = 0; i < 8; i = i + 1) begin
                rx = b[i]; repeat (CPB) @(negedge clk);
            end
            rx = stop_high; repeat (CPB) @(negedge clk);
        end
    endtask

    initial begin
        repeat (20) @(negedge clk);
        send_byte(8'hA5, 1'b1);
        send_byte(8'h00, 1'b1); // back-to-back, no extra idle
        send_byte(8'hFF, 1'b1);
        repeat (CPB) @(negedge clk);
        if (count != 3 || received[0] !== 8'hA5 ||
            received[1] !== 8'h00 || received[2] !== 8'hFF)
            $fatal(1, "back-to-back byte mismatch");

        send_byte(8'hA5, 1'b0);
        rx = 1; repeat (2*CPB) @(negedge clk);
        if (count != 3) $fatal(1, "accepted invalid stop bit");
        send_byte(8'h5A, 1'b1);
        repeat (CPB) @(negedge clk);
        if (count != 4 || received[3] !== 8'h5A)
            $fatal(1, "failed recovery after invalid stop");

        // A sustained break must never produce spurious zero bytes.
        rx = 0; repeat (30*CPB) @(negedge clk);
        if (count != 4) $fatal(1, "accepted data during break");
        // A short HIGH glitch must not re-arm the receiver during break.
        rx = 1; repeat (CPB/4) @(negedge clk);
        rx = 0; repeat (20*CPB) @(negedge clk);
        if (count != 4) $fatal(1, "idle glitch re-armed RX during break");
        rx = 1; repeat (2*CPB) @(negedge clk);
        send_byte(8'hC3, 1'b1);
        repeat (CPB) @(negedge clk);
        if (count != 5 || received[4] !== 8'hC3)
            $fatal(1, "failed recovery after break");

        // A pulse shorter than half a bit is not a start bit.
        rx = 0; repeat (CPB/4) @(negedge clk);
        rx = 1; repeat (12*CPB) @(negedge clk);
        if (count != 5) $fatal(1, "accepted short start glitch");
        $display("PASS tb_uart_rx CPB=%0d", CPB);
        $finish;
    end
    initial begin
        #20_000_000;
        $fatal(1, "TIMEOUT: tb_uart_rx hung");
    end
endmodule
