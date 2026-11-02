`timescale 1ns / 1ps
`default_nettype none

// Basys 3 common-anode display, active-low an/seg/dp; seg[0] is segment a.
// Hex F renders a dash. Divider is a clock enable, never a generated clock.
module sevenseg_status #(parameter DIGIT_CLKS = 100_000) (
    input wire clk, rst,
    input wire [15:0] digits,
    output reg [6:0] seg,
    output wire [3:0] an,
    output wire dp
);
    reg [31:0] count;
    reg [1:0] digit;
    wire [3:0] value = digits[4*digit +: 4];
    assign an = ~(4'b0001 << digit);
    assign dp = 1'b1;
    always @(posedge clk) begin
        if (rst) begin count <= 0; digit <= 0; end
        else if (count == DIGIT_CLKS-1) begin count <= 0; digit <= digit + 2'd1; end
        else count <= count + 32'd1;
    end
    always @(*) begin
        case (value)
            0: seg=7'b1000000; 1: seg=7'b1111001; 2: seg=7'b0100100;
            3: seg=7'b0110000; 4: seg=7'b0011001; 5: seg=7'b0010010;
            6: seg=7'b0000010; 7: seg=7'b1111000; 8: seg=7'b0000000;
            9: seg=7'b0010000; 10: seg=7'b0001000; 11: seg=7'b0000011;
            12: seg=7'b1000110; 13: seg=7'b0100001; 14: seg=7'b0000110;
            default: seg=7'b0111111;
        endcase
    end
endmodule
`default_nettype wire
