`timescale 1ns / 1ps
`default_nettype none

module c43_board_tb;
    reg clk = 0;
    always #5 clk = !clk;
    reg [15:0] sw = 0;
    reg btn = 0;
    wire tx, dp;
    wire [15:0] led;
    wire [6:0] seg;
    wire [3:0] an;
    reg [7:0] expected [0:15];
    integer i, timeout;
    top_basys3_c43 #(.BUTTON_STABLE_CLKS(3), .DISPLAY_DIGIT_CLKS(4)) dut (
        .clk(clk), .RsRx(1'b1), .btnC(btn), .sw(sw), .RsTx(tx),
        .led(led), .seg(seg), .an(an), .dp(dp)
    );

    task fail;
        input [255:0] reason;
        begin
            $display("FAIL C-43 board slot %0d: %0s", i, reason);
            $finish;
        end
    endtask

    initial begin
        $readmemh("stored_classes.mem", expected);
        repeat (10) @(negedge clk);
        sw[15] = 1;
        repeat (6) @(negedge clk);
        btn = 1;
        repeat (10) @(negedge clk);
        if (led[15:14] !== 2'b00) fail("accepted BTNC with SW15 high");
        btn = 0;
        sw[15] = 0;
        for (i = 0; i < 16; i = i + 1) begin
            sw[3:0] = i[3:0];
            repeat (10) @(negedge clk);
            btn = 1;
            repeat (10) @(negedge clk);
            if (led[15:14] !== 2'b10) fail("missing busy or stale result");
            btn = 0;
            sw[3:0] = ~i[3:0];
            timeout = 0;
            while (led[14] !== 1'b1 && timeout < 110000) begin
                @(negedge clk);
                timeout = timeout + 1;
            end
            if (led[15:13] !== 3'b010 || tx !== 1'b1) fail("status or idle UART");
            if ({2'b0, led[5:0]} !== expected[i]) fail("class LEDs");
            if (dut.digits[15:8] !== 8'hff ||
                {4'b0, dut.digits[7:4]} !== expected[i]/8'd10 ||
                {4'b0, dut.digits[3:0]} !== expected[i]%8'd10) fail("decimal display");
        end
        $display("PASS C-43 board: 16 stored slots, class LEDs, decimal display and switch latch");
        $finish;
    end
endmodule
`default_nettype wire
