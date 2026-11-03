`timescale 1ns / 1ps
`default_nettype none

// Stable P4 integration boundary. Replace/optimize internal engines without
// changing the P3 feature-read port or P1/P5 result handshake.
module classifier #(
    parameter WEIGHT_FILE = "fc_weight.mem",
    parameter BIAS_FILE = "fc_bias.mem",
    parameter ENABLE_CONV2 = 0,
    parameter [15:0] CONV2_M = 16'd54743,
    parameter CONV2_S = 24
) (
    input wire clk, rst, start,
    output reg busy, done,
    output wire ovf,
    output wire [10:0] fmap_addr,
    input wire [7:0] fmap_data,
    output wire [191:0] scores,
    output wire [2:0] class_id
);
    localparam [2:0] IDLE=0, POOL=1, FC=2, ARGMAX=3, CONV2=4;
    reg [2:0] state;
    reg pool_start, fc_start, arg_start, conv2_start;
    wire pool_done, fc_done, arg_done;
    wire pool_busy, fc_busy, arg_busy;
    wire pool_we;
    wire [8:0] write_addr, read_addr, pool_read_addr;
    wire [7:0] write_data;
    reg [7:0] read_data;
    reg [7:0] pool_memory [0:391];
    wire [7:0] fc_data;
    wire conv2_done, conv2_ovf, fc_ovf;
    assign ovf = conv2_ovf | fc_ovf;
    always @(posedge clk) begin
        if (pool_we) pool_memory[write_addr] <= write_data;
        read_data <= pool_memory[pool_read_addr];
    end
    generate
        if (ENABLE_CONV2) begin : d42
            wire write_en;
            wire [8:0] addr;
            wire [7:0] data;
            reg [7:0] activation [0:391];
            reg [7:0] fc_q;
            always @(posedge clk) begin
                if (write_en) activation[addr] <= data;
                fc_q <= activation[read_addr];
            end
            assign fc_data = fc_q;
            conv2_padded #(.M(CONV2_M), .S(CONV2_S)) u_conv2 (
                .clk(clk), .rst(rst), .start(conv2_start), .done(conv2_done),
                .ovf(conv2_ovf), .read_addr(pool_read_addr), .read_data(read_data),
                .write_en(write_en), .write_addr(addr), .write_data(data)
            );
        end else begin : baseline
            assign pool_read_addr = read_addr;
            assign fc_data = read_data;
            assign conv2_done = 1'b0;
            assign conv2_ovf = 1'b0;
        end
    endgenerate
    maxpool2d u_pool (
        .clk(clk), .rst(rst), .start(pool_start), .busy(pool_busy), .done(pool_done),
        .fmap_addr(fmap_addr), .fmap_data(fmap_data),
        .pool_we(pool_we), .pool_addr(write_addr), .pool_data(write_data)
    );
    fc_engine #(.WEIGHT_FILE(WEIGHT_FILE), .BIAS_FILE(BIAS_FILE)) u_fc (
        .clk(clk), .rst(rst), .start(fc_start), .busy(fc_busy), .done(fc_done),
        .ovf(fc_ovf), .pool_addr(read_addr), .pool_data(fc_data), .scores(scores)
    );
    argmax u_argmax (
        .clk(clk), .rst(rst), .start(arg_start), .scores(scores),
        .busy(arg_busy), .done(arg_done), .class_id(class_id)
    );
    always @(posedge clk) begin
        if (rst) begin
            state <= IDLE; busy <= 0; done <= 0;
            pool_start <= 0; fc_start <= 0; arg_start <= 0; conv2_start <= 0;
        end else begin
            pool_start <= 0; fc_start <= 0; arg_start <= 0; conv2_start <= 0; done <= 0;
            case (state)
                IDLE: if (start) begin busy <= 1; pool_start <= 1; state <= POOL; end
                POOL: if (pool_done) begin
                    if (ENABLE_CONV2) begin conv2_start <= 1; state <= CONV2; end
                    else begin fc_start <= 1; state <= FC; end
                end
                CONV2: if (conv2_done) begin fc_start <= 1; state <= FC; end
                FC: if (fc_done) begin arg_start <= 1; state <= ARGMAX; end
                ARGMAX: if (arg_done) begin done <= 1; busy <= 0; state <= IDLE; end
                default: begin state <= IDLE; busy <= 0; end
            endcase
        end
    end
endmodule
`default_nettype wire
