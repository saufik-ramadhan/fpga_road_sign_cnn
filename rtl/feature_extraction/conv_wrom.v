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

module conv_wrom #(
    parameter WEIGHT_FILE = "conv_weight.mem",
    parameter BIAS_FILE   = "conv_bias.mem",
    parameter BIAS_W      = 24
) (
    input  wire                     clk,
    input  wire [6:0]               w_addr,
    output reg  signed [7:0]        w_data,
    input  wire [2:0]               b_addr,
    output reg  signed [BIAS_W-1:0] b_data
);

    localparam WEIGHT_COUNT = 72;
    localparam FILTER_COUNT = 8;

    (* rom_style = "distributed" *)
    reg [7:0]        wrom [0:WEIGHT_COUNT-1];
    (* rom_style = "distributed" *)
    reg [BIAS_W-1:0] brom [0:FILTER_COUNT-1];

    initial begin
        $readmemh(WEIGHT_FILE, wrom);
        $readmemh(BIAS_FILE, brom);
    end

    always @(posedge clk) begin
        w_data <= wrom[w_addr];
        b_data <= brom[b_addr];
    end

endmodule

`default_nettype wire
