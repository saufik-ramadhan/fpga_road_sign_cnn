`timescale 1ns / 1ps
`default_nettype none

// Serial bias-first CHW convolution on an 8x7x7 map with zero padding.
module conv2_padded #(
    parameter [15:0] M = 16'd54743,
    parameter S = 24,
    parameter WEIGHT_FILE = "conv2_weight.mem",
    parameter BIAS_FILE = "conv2_bias.mem"
) (
    input wire clk, rst, start,
    output reg done, ovf,
    output wire [8:0] read_addr,
    input wire [7:0] read_data,
    output wire write_en,
    output wire [8:0] write_addr,
    output wire [7:0] write_data
);
    localparam [2:0] IDLE=0, ISSUE=1, MAC=2, SCALE=3, WAIT_Q=4;
    reg [2:0] state;
    reg [2:0] f, c, y, x;
    reg [1:0] ky, kx;
    reg [8:0] index;
    reg signed [23:0] acc;
    reg signed [7:0] weights [0:575];
    reg signed [23:0] biases [0:7];
    reg signed [7:0] weight;
    reg padded;
    initial begin
        $readmemh(WEIGHT_FILE, weights);
        $readmemh(BIAS_FILE, biases);
    end
    wire signed [4:0] iy = $signed({2'b00,y}) + $signed({3'b000,ky}) - 5'sd1;
    wire signed [4:0] ix = $signed({2'b00,x}) + $signed({3'b000,kx}) - 5'sd1;
    wire outside = iy < 0 || iy > 6 || ix < 0 || ix > 6;
    assign read_addr = outside ? 9'd0 : c * 9'd49 + iy[2:0] * 9'd7 + ix[2:0];
    wire [9:0] weight_addr = f * 10'd72 + c * 10'd9 + ky * 10'd3 + kx;
    wire signed [8:0] pixel = padded ? 9'sd0 : $signed({1'b0,read_data});
    (* use_dsp = "yes" *) wire signed [16:0] product = pixel * weight;
    wire signed [23:0] base = (c == 0 && ky == 0 && kx == 0) ? biases[f] : acc;
    wire signed [24:0] sum = {base[23],base} + {{8{product[16]}},product};
    wire q_valid;
    assign write_addr = index;
    assign write_en = !rst && state == WAIT_Q && q_valid;
    requant_relu #(.M(M), .S(S), .ACC_W(24)) u_requant (
        .clk(clk), .rst(rst), .in_valid(state == SCALE), .acc(acc),
        .in_tag(1'b0), .out_valid(q_valid), .q(write_data), .out_tag()
    );
    always @(posedge clk) begin
        if (rst) begin
            state <= IDLE; done <= 0; ovf <= 0;
            f <= 0; c <= 0; y <= 0; x <= 0; ky <= 0; kx <= 0;
            index <= 0; acc <= 0; weight <= 0; padded <= 0;
        end else begin
            done <= 0;
            case (state)
                IDLE: if (start) begin
                    f <= 0; c <= 0; y <= 0; x <= 0; ky <= 0; kx <= 0;
                    index <= 0; ovf <= 0; state <= ISSUE;
                end
                ISSUE: begin
                    weight <= weights[weight_addr];
                    padded <= outside;
                    state <= MAC;
                end
                MAC: begin
                    acc <= sum[23:0];
                    if (sum[24] != sum[23]) ovf <= 1;
                    state <= ISSUE;
                    if (kx != 2) kx <= kx + 1'b1;
                    else begin
                        kx <= 0;
                        if (ky != 2) ky <= ky + 1'b1;
                        else begin
                            ky <= 0;
                            if (c != 7) c <= c + 1'b1;
                            else begin c <= 0; state <= SCALE; end
                        end
                    end
                end
                SCALE: state <= WAIT_Q;
                WAIT_Q: if (q_valid) begin
                    if (index == 391) begin done <= 1; state <= IDLE; end
                    else begin
                        index <= index + 1'b1;
                        state <= ISSUE;
                        if (x != 6) x <= x + 1'b1;
                        else begin
                            x <= 0;
                            if (y != 6) y <= y + 1'b1;
                            else begin y <= 0; f <= f + 1'b1; end
                        end
                    end
                end
                default: state <= IDLE;
            endcase
        end
    end
endmodule
`default_nettype wire
