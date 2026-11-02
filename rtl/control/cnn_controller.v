`timescale 1ns / 1ps
`default_nettype none

// P1 baseline sequencer. start is accepted only while idle; done is a pulse.
// cycles counts from acceptance through result completion, including handoffs.
module cnn_controller (
    input wire clk, rst, start,
    input wire conv_done, classifier_done,
    output reg conv_start, classifier_start,
    output reg busy, done,
    output reg [31:0] cycles
);
    localparam [1:0] IDLE=0, CONV=1, CLASSIFY=2;
    reg [1:0] state;
    always @(posedge clk) begin
        if (rst) begin
            state <= IDLE; conv_start <= 0; classifier_start <= 0;
            busy <= 0; done <= 0; cycles <= 0;
        end else begin
            conv_start <= 0; classifier_start <= 0; done <= 0;
            if (busy) cycles <= cycles + 32'd1;
            case (state)
                IDLE: if (start) begin
                    busy <= 1; cycles <= 0; conv_start <= 1; state <= CONV;
                end
                CONV: if (conv_done) begin classifier_start <= 1; state <= CLASSIFY; end
                CLASSIFY: if (classifier_done) begin busy <= 0; done <= 1; state <= IDLE; end
                default: begin state <= IDLE; busy <= 0; end
            endcase
        end
    end
endmodule
`default_nettype wire
