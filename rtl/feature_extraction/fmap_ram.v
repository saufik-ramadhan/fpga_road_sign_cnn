`timescale 1ns / 1ps
`default_nettype none

// fmap_ram: the 14x14x8 = 1,568 activations after convolution, 0..127.
// Address = filter*196 + row*14 + col, the order PyTorch flattens a
// (channel, row, column) tensor.
// Simple dual-port block RAM: conv_engine writes, maxpool reads.
// A read takes exactly one clock cycle (no output register).

module fmap_ram #(
    parameter DEPTH = 1568,
    parameter ADDR_W = 11
) (
    input  wire        clk,
    // write port: conv_engine
    input  wire        we,
    input  wire [ADDR_W-1:0] waddr,
    input  wire [7:0]  wdata,
    // read port: maxpool
    input  wire [ADDR_W-1:0] raddr,
    output reg  [7:0]  rdata
);

    (* ram_style = "block" *)
    reg [7:0] mem [0:DEPTH-1];

    always @(posedge clk) begin
        if (we)
            mem[waddr] <= wdata;
        rdata <= mem[raddr];
    end

endmodule

`default_nettype wire
