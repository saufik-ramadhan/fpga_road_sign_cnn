`timescale 1ns / 1ps
`default_nettype none

// P4 baseline: bias-first serial MAC, 392 CHW inputs x 8 classes.
// All memory reads take one clock; every signed24 partial sum is checked.
// score k occupies scores[24*k +: 24], matching P5's public interface.
module fc_engine #(
    parameter WEIGHT_FILE = "fc_weight.mem",
    parameter BIAS_FILE = "fc_bias.mem",
    parameter FEATURES = 392,
    parameter CLASSES = 8,
    parameter FEATURE_W = 9,
    parameter CLASS_W = 3,
    parameter WEIGHT_ADDR_W = 12,
    parameter FC_ROM_STYLE = "auto"
) (
    input wire clk, rst, start,
    output reg busy, done, ovf,
    output wire [FEATURE_W-1:0] pool_addr,
    input wire [7:0] pool_data,
    output reg [24*CLASSES-1:0] scores
);
    localparam ISSUE = 1'b0, MAC = 1'b1;
    reg state;
    reg [CLASS_W-1:0] class_index;
    reg [FEATURE_W-1:0] index;
    reg signed [23:0] acc;
    reg signed [23:0] biases [0:CLASSES-1];
    wire signed [7:0] weight;
    reg signed [23:0] bias;
    wire [WEIGHT_ADDR_W-1:0] weight_addr = class_index * FEATURES + index;
    initial $readmemh(BIAS_FILE, biases);
    always @(posedge clk) bias <= biases[class_index];
    generate
        if (FC_ROM_STYLE == "block") begin : block_weights
            fc_block_rom #(.DEPTH(FEATURES*CLASSES), .ADDR_W(WEIGHT_ADDR_W),
                .INIT_FILE(WEIGHT_FILE)) u_weights (.clk(clk), .addr(weight_addr), .data(weight));
        end else begin : default_weights
            reg signed [7:0] weights [0:FEATURES*CLASSES-1];
            reg signed [7:0] data;
            initial $readmemh(WEIGHT_FILE, weights);
            always @(posedge clk) data <= weights[weight_addr];
            assign weight = data;
        end
    endgenerate
    assign pool_addr = index;
    (* use_dsp = "yes" *) wire signed [16:0] product = $signed({1'b0, pool_data}) * weight;
    wire signed [23:0] base = index == 0 ? bias : acc;
    wire signed [24:0] sum = {base[23], base} + {{8{product[16]}}, product};

    always @(posedge clk) begin
        if (rst) begin
            busy <= 0; done <= 0; ovf <= 0; scores <= 0;
            state <= ISSUE; class_index <= 0; index <= 0; acc <= 0;
        end else begin
            done <= 0;
            if (!busy) begin
                if (start) begin
                    busy <= 1; ovf <= 0; state <= ISSUE;
                    class_index <= 0; index <= 0;
                end
            end else if (state == ISSUE) begin
                state <= MAC;
            end else begin
                state <= ISSUE;
                acc <= sum[23:0];
                if (sum[24] != sum[23]) ovf <= 1;
                if (index == FEATURES - 1) begin
                    scores[24*class_index +: 24] <= sum[23:0];
                    index <= 0;
                    class_index <= class_index + 3'd1;
                    if (class_index == CLASSES - 1) begin busy <= 0; done <= 1; end
                end else index <= index + 9'd1;
            end
        end
    end
endmodule
// Keep a simple synchronous ROM boundary for large FC weight banks.
(* keep_hierarchy = "yes" *)
module fc_block_rom #(
    parameter DEPTH = 33712,
    parameter ADDR_W = 16,
    parameter INIT_FILE = "fc_weight.mem"
) (
    input wire clk,
    input wire [ADDR_W-1:0] addr,
    output reg [7:0] data
);
    (* rom_style = "block" *) reg [7:0] mem [0:DEPTH-1];
    initial $readmemh(INIT_FILE, mem);
    always @(posedge clk) data <= mem[addr];
endmodule
`default_nettype wire
