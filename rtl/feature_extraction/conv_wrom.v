`timescale 1ns / 1ps
`default_nettype none

// conv_wrom: the convolution layer's parameters, held in LUTs and loaded from
// P2's package (reference_model/models/<version>/mem/):
//   conv_weight.mem  72 signed 8-bit weights, 2 hex digits a line (-1 is ff),
//                    address filter*9 + kernel_row*3 + kernel_col, the order
//                    of PyTorch's weight[filter][0][kernel_row][kernel_col]
//   conv_bias.mem    8 signed BIAS_W-bit biases, BIAS_W/4 hex digits a line,
//                    address filter: 24 bits in p2-doc-int-v2 (-1 is ffffff),
//                    32 bits in p2-int-v1 (-1 is ffffffff)
// $readmemh does not sign-extend a short word, so the bias memory is exactly
// as wide as the file's words. Both outputs are registered, so each read
// takes exactly one clock cycle.
//
// A weight read returns TAPS consecutive weights: one (TAPS = 1, address
// filter*9 + kernel_row*3 + kernel_col), a kernel row (TAPS = 3, address
// filter*3 + kernel_row) or a whole kernel (TAPS = 9, address filter). Weight
// w_addr*TAPS + i is in bits 8*i +: 8.

module conv_wrom #(
    parameter WEIGHT_FILE = "conv_weight.mem",
    parameter BIAS_FILE   = "conv_bias.mem",
    parameter BIAS_W      = 24,
    parameter TAPS        = 1                   // weights per read: 1, 3 or 9
) (
    input  wire                     clk,
    input  wire [6:0]               w_addr,
    output reg  [8*TAPS-1:0]        w_data,
    input  wire [2:0]               b_addr,
    output reg  signed [BIAS_W-1:0] b_data
);

    localparam WEIGHT_COUNT = 72;
    localparam FILTER_COUNT = 8;

    (* rom_style = "distributed" *)
    reg [7:0]        wrom [0:WEIGHT_COUNT-1];
    (* rom_style = "distributed" *)
    reg [BIAS_W-1:0] brom [0:FILTER_COUNT-1];
    integer i;

    initial begin
        $readmemh(WEIGHT_FILE, wrom);
        $readmemh(BIAS_FILE, brom);
    end

    always @(posedge clk) begin
        for (i = 0; i < TAPS; i = i + 1)
            w_data[8*i +: 8] <= wrom[w_addr*TAPS + i];
        b_data <= brom[b_addr];
    end

endmodule

`default_nettype wire
