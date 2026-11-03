`timescale 1ns / 1ps
`default_nettype none

// Strict signed comparison preserves the lowest class index on a tie (P2).
module argmax #(
    parameter CLASSES = 8,
    parameter CLASS_W = 3
) (
    input wire clk, rst, start,
    input wire [24*CLASSES-1:0] scores,
    output reg busy, done,
    output reg [CLASS_W-1:0] class_id
);
    reg [CLASS_W-1:0] index, best_index;
    reg signed [23:0] best;
    wire signed [23:0] candidate = scores[24*index +: 24];
    always @(posedge clk) begin
        if (rst) begin
            busy <= 0; done <= 0; class_id <= 0;
            index <= 0; best_index <= 0; best <= 0;
        end else begin
            done <= 0;
            if (!busy) begin
                if (start) begin
                    busy <= 1; index <= 1; best_index <= 0; best <= scores[23:0];
                end
            end else begin
                if (candidate > best) begin best <= candidate; best_index <= index; end
                index <= index + 3'd1;
                if (index == CLASSES - 1) begin
                    class_id <= candidate > best ? index : best_index;
                    busy <= 0; done <= 1;
                end
            end
        end
    end
endmodule
`default_nettype wire
