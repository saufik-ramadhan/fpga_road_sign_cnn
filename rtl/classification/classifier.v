`timescale 1ns / 1ps
`default_nettype none

// Stable P4 integration boundary. Replace/optimize internal engines without
// changing the P3 feature-read port or P1/P5 result handshake.
module classifier #(
    parameter WEIGHT_FILE = "fc_weight.mem",
    parameter BIAS_FILE = "fc_bias.mem"
) (
    input wire clk, rst, start,
    output reg busy, done,
    output wire ovf,
    output wire [10:0] fmap_addr,
    input wire [7:0] fmap_data,
    output wire [191:0] scores,
    output wire [2:0] class_id
);
    localparam [1:0] IDLE=0, POOL=1, FC=2, ARGMAX=3;
    reg [1:0] state;
    reg pool_start, fc_start, arg_start;
    wire pool_done, fc_done, arg_done;
    wire pool_busy, fc_busy, arg_busy;
    wire pool_we;
    wire [8:0] write_addr, read_addr;
    wire [7:0] write_data;
    reg [7:0] read_data;
    reg [7:0] pool_memory [0:391];
    always @(posedge clk) begin
        if (pool_we) pool_memory[write_addr] <= write_data;
        read_data <= pool_memory[read_addr];
    end
    maxpool2d u_pool (
        .clk(clk), .rst(rst), .start(pool_start), .busy(pool_busy), .done(pool_done),
        .fmap_addr(fmap_addr), .fmap_data(fmap_data),
        .pool_we(pool_we), .pool_addr(write_addr), .pool_data(write_data)
    );
    fc_engine #(.WEIGHT_FILE(WEIGHT_FILE), .BIAS_FILE(BIAS_FILE)) u_fc (
        .clk(clk), .rst(rst), .start(fc_start), .busy(fc_busy), .done(fc_done),
        .ovf(ovf), .pool_addr(read_addr), .pool_data(read_data), .scores(scores)
    );
    argmax u_argmax (
        .clk(clk), .rst(rst), .start(arg_start), .scores(scores),
        .busy(arg_busy), .done(arg_done), .class_id(class_id)
    );
    always @(posedge clk) begin
        if (rst) begin
            state <= IDLE; busy <= 0; done <= 0;
            pool_start <= 0; fc_start <= 0; arg_start <= 0;
        end else begin
            pool_start <= 0; fc_start <= 0; arg_start <= 0; done <= 0;
            case (state)
                IDLE: if (start) begin busy <= 1; pool_start <= 1; state <= POOL; end
                POOL: if (pool_done) begin fc_start <= 1; state <= FC; end
                FC: if (fc_done) begin arg_start <= 1; state <= ARGMAX; end
                ARGMAX: if (arg_done) begin done <= 1; busy <= 0; state <= IDLE; end
                default: begin state <= IDLE; busy <= 0; end
            endcase
        end
    end
endmodule
`default_nettype wire
