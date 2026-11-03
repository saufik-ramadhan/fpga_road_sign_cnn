`timescale 1ns / 1ps
`default_nettype none

// Complete baseline 16x16/int24 datapath. Pixel data must arrive one clock
// after pix_addr. The model's four parameter memories must belong together.
module cnn_core #(
    parameter [15:0] M = 16'd43980,
    parameter S = 25,
    parameter CONV_WEIGHT_FILE = "conv_weight.mem",
    parameter CONV_BIAS_FILE = "conv_bias.mem",
    parameter FC_WEIGHT_FILE = "fc_weight.mem",
    parameter FC_BIAS_FILE = "fc_bias.mem",
    parameter ENABLE_CONV2 = 0,
    parameter [15:0] CONV2_M = 16'd54743,
    parameter CONV2_S = 24,
    parameter FILTERS = 8,
    parameter FILTER_W = 3,
    parameter FM_ADDR_W = 11,
    parameter CLASSES = 8,
    parameter CLASS_W = 3,
    parameter POOL_ADDR_W = 9,
    parameter WEIGHT_ADDR_W = 12,
    parameter FC_ROM_STYLE = "auto",
    parameter N_MAC = 1,
    parameter FC_MAC = 1
) (
    input wire clk, rst, start,
    output wire busy, done,
    output reg ovf,
    output wire [31:0] cycles,
    output wire [7:0] pix_addr,
    output wire pix_rd,
    input wire [7:0] pix_data,
    output wire [CLASS_W-1:0] class_id,
    output wire [24*CLASSES-1:0] scores
);
    wire conv_start, conv_done, conv_busy, conv_ovf;
    wire classifier_start, classifier_done, classifier_busy, classifier_ovf;
    wire [FM_ADDR_W-1:0] fmap_addr;
    wire [7:0] fmap_data;
    cnn_controller u_controller (
        .clk(clk), .rst(rst), .start(start), .conv_done(conv_done),
        .classifier_done(classifier_done), .conv_start(conv_start),
        .classifier_start(classifier_start), .busy(busy), .done(done), .cycles(cycles)
    );
    feature_extraction #(.M(M), .S(S), .ACC_W(24),
        .WEIGHT_FILE(CONV_WEIGHT_FILE), .BIAS_FILE(CONV_BIAS_FILE),
        .FILTERS(FILTERS), .FILTER_W(FILTER_W), .FM_ADDR_W(FM_ADDR_W), .N_MAC(N_MAC)) u_features (
        .clk(clk), .rst(rst), .start(conv_start), .busy(conv_busy),
        .done(conv_done), .ovf(conv_ovf), .pix_rd(pix_rd), .pix_addr(pix_addr),
        .pix_data(pix_data), .rd_addr(fmap_addr), .rd_data(fmap_data)
    );
    classifier #(.WEIGHT_FILE(FC_WEIGHT_FILE), .BIAS_FILE(FC_BIAS_FILE),
        .ENABLE_CONV2(ENABLE_CONV2), .CONV2_M(CONV2_M), .CONV2_S(CONV2_S),
        .FILTERS(FILTERS), .FILTER_W(FILTER_W), .FM_ADDR_W(FM_ADDR_W),
        .CLASSES(CLASSES), .CLASS_W(CLASS_W), .POOL_ADDR_W(POOL_ADDR_W), .WEIGHT_ADDR_W(WEIGHT_ADDR_W), .FC_ROM_STYLE(FC_ROM_STYLE), .FC_MAC(FC_MAC)) u_classifier (
        .clk(clk), .rst(rst), .start(classifier_start), .busy(classifier_busy),
        .done(classifier_done), .ovf(classifier_ovf), .fmap_addr(fmap_addr),
        .fmap_data(fmap_data), .scores(scores), .class_id(class_id)
    );
    // Sample stage overflow only at its completion: the previous run's sticky
    // flags can still be high during the next run's start handoff.
    always @(posedge clk) begin
        if (rst || (start && !busy)) ovf <= 0;
        else if ((conv_done && conv_ovf) || (classifier_done && classifier_ovf)) ovf <= 1;
    end
endmodule
`default_nettype wire
