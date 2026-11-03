`timescale 1ns / 1ps
`default_nettype none

// P4 baseline: 8x14x14 -> 8x7x7, unsigned 2x2 max, CHW order.
// ISSUE/SAMPLE supports the existing one-clock feature-memory read port.
// The final pool write is committed one clock after done is asserted.
module maxpool2d #(
    parameter FILTERS = 8,
    parameter FILTER_W = 3,
    parameter FM_ADDR_W = 11,
    parameter POOL_ADDR_W = 9
) (
    input wire clk, rst, start,
    output reg busy, done,
    output wire [FM_ADDR_W-1:0] fmap_addr,
    input wire [7:0] fmap_data,
    output reg pool_we,
    output reg [POOL_ADDR_W-1:0] pool_addr,
    output reg [7:0] pool_data
);
    localparam ISSUE = 1'b0, SAMPLE = 1'b1;
    reg state;
    reg [FILTER_W-1:0] channel;
    reg [2:0] row, col;
    reg [1:0] tap;
    reg [POOL_ADDR_W-1:0] index;
    reg [7:0] maximum;
    wire [7:0] next_max = (tap == 0 || fmap_data > maximum) ? fmap_data : maximum;
    assign fmap_addr = channel * 11'd196 + (row * 11'd2 + tap[1]) * 11'd14
                      + col * 11'd2 + tap[0];

    always @(posedge clk) begin
        if (rst) begin
            busy <= 0; done <= 0; pool_we <= 0; state <= ISSUE;
            channel <= 0; row <= 0; col <= 0; tap <= 0; index <= 0;
            maximum <= 0; pool_addr <= 0; pool_data <= 0;
        end else begin
            done <= 0;
            pool_we <= 0;
            if (!busy) begin
                if (start) begin
                    busy <= 1; state <= ISSUE;
                    channel <= 0; row <= 0; col <= 0; tap <= 0; index <= 0;
                end
            end else if (state == ISSUE) begin
                state <= SAMPLE;
            end else begin
                state <= ISSUE;
                maximum <= next_max;
                tap <= tap + 2'd1;
                if (tap == 3) begin
                    pool_we <= 1; pool_addr <= index; pool_data <= next_max;
                    index <= index + 9'd1;
                    if (col == 6) begin
                        col <= 0;
                        if (row == 6) begin row <= 0; channel <= channel + 3'd1; end
                        else row <= row + 3'd1;
                    end else col <= col + 3'd1;
                    if (index == FILTERS * 49 - 1) begin busy <= 0; done <= 1; end
                end
            end
        end
    end
endmodule
`default_nettype wire
