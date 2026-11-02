`timescale 1ns / 1ps
`default_nettype none

// Synchronize and debounce on both edges; one pulse per stable press.
module button_pulse #(parameter STABLE_CLKS = 2_000_000) (
    input wire clk, rst, button,
    output reg pulse
);
    (* ASYNC_REG = "TRUE" *) reg sync_meta = 0, sync_value = 0;
    reg stable = 0;
    reg [31:0] count = 0;
    always @(posedge clk) begin
        sync_meta <= button; sync_value <= sync_meta;
        if (rst) begin stable <= 0; count <= 0; pulse <= 0; end
        else begin
            pulse <= 0;
            if (sync_value == stable) count <= 0;
            else if (count == STABLE_CLKS-1) begin
                stable <= sync_value; count <= 0; pulse <= sync_value;
            end else count <= count + 32'd1;
        end
    end
endmodule
`default_nettype wire
