`timescale 1ns / 1ps
`default_nettype none

// requant_relu: rescales an ACC_W-bit accumulator to an activation of 0..127,
// exactly as P2's contract defines it (reference_model/INTEGER_CONTRACT.md):
//
//     P = max(0, acc)
//     q = min(127, (P*M + R) >> S),   R = 2^(S-1), or 0 when S = 0
//
// M is unsigned 16-bit (1..65535) and S is 0..47. The ReLU comes first, so
// only non-negative numbers are multiplied and shifted, and the rounding is to
// nearest with halves going up. P*M + R is computed in 48 bits, as
// p2-doc-int-v2's contract says. That holds every legal value even for a
// 32-bit acc (P < 2^31, M < 2^16, R <= 2^46), so it also equals p2-int-v1's
// 64-bit formula.
//
// Two pipeline stages: ReLU and multiply (registered), then rounding, shift
// and clamp. in_tag comes out with its result as out_tag, so the caller can
// pass the write address through without counting cycles.

module requant_relu #(
    parameter [15:0] M     = 16'd1,
    parameter        S     = 0,
    parameter        ACC_W = 24,
    parameter        TAG_W = 1
) (
    input  wire                    clk,
    input  wire                    rst,
    input  wire                    in_valid,
    input  wire signed [ACC_W-1:0] acc,
    input  wire [TAG_W-1:0]        in_tag,
    output reg                     out_valid,
    output reg  [7:0]              q,
    output reg  [TAG_W-1:0]        out_tag
);

    localparam [47:0] ROUND = (S == 0) ? 48'd0 : 48'd1 << (S - 1);

    // synthesis translate_off
    initial begin
        if (M == 16'd0 || S < 0 || S > 47 || ACC_W < 2 || ACC_W > 32) begin
            $display("requant_relu: M = %0d, S = %0d, ACC_W = %0d; the contract needs M 1..65535, S 0..47, ACC_W up to 32",
                     M, S, ACC_W);
            $finish;
        end
    end
    // synthesis translate_on

    // stage 1: ReLU, then multiply
    wire [ACC_W-2:0]   pos = acc[ACC_W-1] ? {(ACC_W-1){1'b0}} : acc[ACC_W-2:0];
    reg  [ACC_W+14:0]  prod;        // (ACC_W - 1) + 16 bits
    reg                prod_valid;
    reg  [TAG_W-1:0]   prod_tag;

    // stage 2: round, shift, clamp
    wire [47:0] rounded = prod + ROUND;
    wire [47:0] shifted = rounded >> S;

    always @(posedge clk) begin
        prod     <= pos * M;
        prod_tag <= in_tag;

        q       <= (shifted > 48'd127) ? 8'd127 : shifted[7:0];
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
