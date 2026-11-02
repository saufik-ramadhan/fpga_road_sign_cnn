`timescale 1ns / 1ps
`default_nettype none

// requant_relu: rescales a 32-bit accumulator to an activation of 0..127,
// exactly as P2's contract defines it (reference_model/INTEGER_CONTRACT.md):
//
//     P = max(0, acc)
//     q = min(127, (P*M + R) >> S),   R = 2^(S-1), or 0 when S = 0
//
// M is unsigned 16-bit (1..65535) and S is 0..47. The ReLU comes first, so
// only non-negative numbers are multiplied and shifted, and the rounding is to
// nearest with halves going up. The contract computes P*M + R in 64 bits.
// With a 32-bit acc that sum never needs more than 48 bits (P < 2^31,
// M < 2^16, R <= 2^46), so the result equals the 64-bit formula for every
// legal input, and synthesis drops the upper bits, which are always zero.
//
// Two pipeline stages: ReLU and multiply (registered, in DSP slices), then
// rounding, shift and clamp. in_tag comes out with its result as out_tag, so
// the caller can pass the write address through without counting cycles.

module requant_relu #(
    parameter [15:0] M     = 16'd1,
    parameter        S     = 0,
    parameter        TAG_W = 1
) (
    input  wire               clk,
    input  wire               rst,
    input  wire               in_valid,
    input  wire signed [31:0] acc,
    input  wire [TAG_W-1:0]   in_tag,
    output reg                out_valid,
    output reg  [7:0]         q,
    output reg  [TAG_W-1:0]   out_tag
);

    localparam [63:0] ROUND = (S == 0) ? 64'd0 : 64'd1 << (S - 1);

    // synthesis translate_off
    initial begin
        if (M == 16'd0 || S < 0 || S > 47) begin
            $display("requant_relu: M = %0d, S = %0d; the contract needs M 1..65535, S 0..47", M, S);
            $finish;
        end
    end
    // synthesis translate_on

    // stage 1: ReLU, then multiply
    wire [30:0]     pos = acc[31] ? 31'd0 : acc[30:0];
    reg  [46:0]     prod;
    reg             prod_valid;
    reg [TAG_W-1:0] prod_tag;

    // stage 2: round, shift, clamp
    wire [63:0] rounded = {17'd0, prod} + ROUND;
    wire [63:0] shifted = rounded >> S;

    always @(posedge clk) begin
        prod     <= pos * M;
        prod_tag <= in_tag;

        q       <= (shifted > 64'd127) ? 8'd127 : shifted[7:0];
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
