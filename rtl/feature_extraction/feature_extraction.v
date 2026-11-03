`timescale 1ns / 1ps
`default_nettype none

// Integration boundary for P3: convolution/requantization writes the feature
// memory internally; the downstream classifier gets a one-cycle read port.
// start/done/busy and pixel-read timing are the conv_engine interface unchanged.
module feature_extraction #(
    parameter [15:0] M = 16'd43980,
    parameter S = 25,
    parameter ACC_W = 24,
    parameter WEIGHT_FILE = "conv_weight.mem",
    parameter BIAS_FILE = "conv_bias.mem",
    parameter FILTERS = 8,
    parameter FILTER_W = 3,
    parameter FM_ADDR_W = 11
) (
    input  wire        clk,
    input  wire        rst,
    input  wire        start,
    output wire        busy,
    output wire        done,
    output wire        ovf,
    output wire        pix_rd,
    output wire [7:0]  pix_addr,
    input  wire [7:0]  pix_data,
    input  wire [FM_ADDR_W-1:0] rd_addr,
    output wire [7:0]  rd_data
);
    wire        fm_we;
    wire [FM_ADDR_W-1:0] fm_addr;
    wire [7:0]  fm_data;

    conv_engine #(
        .M(M), .S(S), .ACC_W(ACC_W),
        .WEIGHT_FILE(WEIGHT_FILE), .BIAS_FILE(BIAS_FILE), .FILTERS(FILTERS), .FILTER_W(FILTER_W), .FM_ADDR_W(FM_ADDR_W)
    ) u_conv (
        .clk(clk), .rst(rst), .start(start),
        .busy(busy), .done(done), .ovf(ovf),
        .pix_rd(pix_rd), .pix_addr(pix_addr), .pix_data(pix_data),
        .fm_we(fm_we), .fm_addr(fm_addr), .fm_data(fm_data)
    );

    fmap_ram #(.DEPTH(FILTERS*196), .ADDR_W(FM_ADDR_W)) u_fmap (
        .clk(clk), .we(fm_we), .waddr(fm_addr), .wdata(fm_data),
        .raddr(rd_addr), .rdata(rd_data)
    );
endmodule

`default_nettype wire
