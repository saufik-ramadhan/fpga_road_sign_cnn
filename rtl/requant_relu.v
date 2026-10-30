`timescale 1ns / 1ps
`default_nettype none

// requant_relu: rescales a 24-bit accumulator to an activation of 0..127.
//
//     q = clamp((acc * M + 2^(S-1)) >> S, 0, 127)
//
// M is unsigned 16-bit and S is a right shift of 1 to 40, both from params.vh.
// The shift is arithmetic (a floor), like Python's >>, and the clamp at 0 is
// the ReLU. Negative sums clamp to 0 whichever way they round, so the RTL and
// the golden model cannot disagree on them.
//
// Two pipeline stages: the multiply is registered (inside the DSP slice), then
// rounding, shift and clamp. in_tag comes out with its result as out_tag, so
// the caller can pass the write address through without counting cycles.

module requant_relu #(
    parameter [15:0] M     = 16'd1,
    parameter        S     = 1,
    parameter        TAG_W = 1
) (
    input  wire               clk,
    input  wire               rst,
    input  wire               in_valid,
    input  wire signed [23:0] acc,
    input  wire [TAG_W-1:0]   in_tag,
    output reg                out_valid,
    output reg  [7:0]         q,
    output reg  [TAG_W-1:0]   out_tag
);

    // acc * M needs 40 bits; one more for the sign of M and one for rounding
    localparam [41:0] ROUND = 42'd1 << (S - 1);

    // synthesis translate_off
    initial begin
        if (S < 1 || S > 40) begin
            $display("requant_relu: S = %0d is outside 1..40", S);
            $finish;
        end
    end
    // synthesis translate_on

    // stage 1: multiply
    reg signed [40:0] prod;
    reg               prod_valid;
    reg [TAG_W-1:0]   prod_tag;

    // stage 2: round, shift, clamp
    wire signed [41:0] rounded = prod + $signed(ROUND);
    wire signed [41:0] shifted = rounded >>> S;

    always @(posedge clk) begin
        prod     <= acc * $signed({1'b0, M});
        prod_tag <= in_tag;

        if (shifted < 0)
            q <= 8'd0;
        else if (shifted > 127)
            q <= 8'd127;
        else
            q <= shifted[7:0];
        out_tag <= prod_tag;
    end

    always @(posedge clk) begin
        if (rst) begin
            prod_valid <= 1'b0;
            out_valid  <= 1'b0;
        end else begin
            prod_valid <= in_valid;
            out_valid  <= prod_valid;
        end
    end

endmodule

`default_nettype wire
