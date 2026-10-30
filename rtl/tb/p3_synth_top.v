`timescale 1ns / 1ps
`default_nettype none

// p3_synth_top: P3's block wired as cnn_core will wire it, for synth_p3.tcl
// only. conv_engine writes fmap_ram; the image port and the fmap_ram read
// port become top-level ports.

module p3_synth_top (
    input  wire        clk,
    input  wire        rst,
    input  wire        start,
    output wire        busy,
    output wire        done,
    output wire        ovf,
    output wire        pix_rd,
    output wire [7:0]  pix_addr,
    input  wire [7:0]  pix_data,
    input  wire [10:0] rd_addr,
    output wire [7:0]  rd_data
);

    `include "params.vh"

    wire        fm_we;
    wire [10:0] fm_addr;
    wire [7:0]  fm_data;

    conv_engine #(
        .M           (CONV_M),
        .S           (CONV_S),
        .BIAS        (CONV_BIAS),
        .WEIGHT_FILE ("conv_weights.mem")
    ) u_conv (
        .clk      (clk),
        .rst      (rst),
        .start    (start),
        .busy     (busy),
        .done     (done),
        .ovf      (ovf),
        .pix_rd   (pix_rd),
        .pix_addr (pix_addr),
        .pix_data (pix_data),
        .fm_we    (fm_we),
        .fm_addr  (fm_addr),
        .fm_data  (fm_data)
    );

    fmap_ram u_fmap (
        .clk   (clk),
        .we    (fm_we),
        .waddr (fm_addr),
        .wdata (fm_data),
        .raddr (rd_addr),
        .rdata (rd_data)
    );

endmodule

`default_nettype wire
