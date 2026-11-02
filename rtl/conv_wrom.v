`timescale 1ns / 1ps
`default_nettype none

// conv_wrom: the 72 convolution weights, signed 8-bit, held in LUTs.
// Address = filter*9 + kernel_row*3 + kernel_col, the order of PyTorch's
// weight[filter][0][kernel_row][kernel_col].
// The output is registered, so a read takes exactly one clock cycle.
// INIT_FILE has 72 lines of two hex digits, two's complement (-1 is ff).

module conv_wrom #(
    parameter INIT_FILE = "conv_weights.mem"
) (
    input  wire              clk,
    input  wire [6:0]        addr,
    output reg  signed [7:0] dout
);

    (* rom_style = "distributed" *)
    reg [7:0] rom [0:71];

    initial $readmemh(INIT_FILE, rom);

    always @(posedge clk)
        dout <= rom[addr];

endmodule

`default_nettype wire
