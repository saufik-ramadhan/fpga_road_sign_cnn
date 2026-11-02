`timescale 1ns / 1ps
`default_nettype none

// conv_wrom: the convolution layer's parameters, held in LUTs and loaded from
// P2's package (reference_model/models/<version>/mem/):
//   conv_weight.mem  72 signed 8-bit weights, 2 hex digits a line (-1 is ff),
//                    address filter*9 + kernel_row*3 + kernel_col, the order
//                    of PyTorch's weight[filter][0][kernel_row][kernel_col]
//   conv_bias.mem    8 signed 32-bit biases, 8 hex digits a line (-1 is
//                    ffffffff), address filter
// Both outputs are registered, so each read takes exactly one clock cycle.

module conv_wrom #(
    parameter WEIGHT_FILE = "conv_weight.mem",
    parameter BIAS_FILE   = "conv_bias.mem"
) (
    input  wire               clk,
    input  wire [6:0]         w_addr,
    output reg  signed [7:0]  w_data,
    input  wire [2:0]         b_addr,
    output reg  signed [31:0] b_data
);

    (* rom_style = "distributed" *)
    reg [7:0]  wrom [0:71];
    (* rom_style = "distributed" *)
    reg [31:0] brom [0:7];

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
