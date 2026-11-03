`timescale 1ns / 1ps
`default_nettype none

// p3_synth_top: P3's block wired as cnn_core will wire it, for synth_p3.tcl
// only. Reuses the production feature_extraction wrapper. Its image and
// fmap read interfaces become top-level ports. Default parameters run
// P2's model p2-doc-int-v2, with the .mem files synth_p3.tcl copies next to it;
// synth_p3.tcl sets N_MAC, the conv_engine version, with synth_design -generic.

module p3_synth_top #(
    parameter N_MAC = 1
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
    input  wire [10:0] rd_addr,
    output wire [7:0]  rd_data
);

    feature_extraction #(.N_MAC(N_MAC)) u_features (
        .clk(clk), .rst(rst), .start(start),
        .busy(busy), .done(done), .ovf(ovf),
        .pix_rd(pix_rd), .pix_addr(pix_addr), .pix_data(pix_data),
        .rd_addr(rd_addr), .rd_data(rd_data)
    );

endmodule

`default_nettype wire
