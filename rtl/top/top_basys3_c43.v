`timescale 1ns / 1ps
`default_nettype none

// Stored-image demo of C-43 seed 44. Same Basys 3 pins as top_basys3.
module top_basys3_c43 #(
    parameter BUTTON_STABLE_CLKS = 1_000_000,
    parameter DISPLAY_DIGIT_CLKS = 50_000,
    parameter STORED_FILE = "signs.mem",
    parameter [15:0] M = 16'd38660,
    parameter S = 24
) (
    input wire clk, RsRx, btnC,
    input wire [15:0] sw,
    output wire RsTx,
    output wire [15:0] led,
    output wire [6:0] seg,
    output wire [3:0] an,
    output wire dp
);
    // Divide the 100 MHz board clock for the C-43 BRAM-to-score path.
    reg divided_clk = 1'b0;
    always @(posedge clk) divided_clk <= ~divided_clk;
    wire core_clk;
`ifdef SYNTHESIS
    BUFG u_core_clock (.I(divided_clk), .O(core_clk));
`else
    assign core_clk = divided_clk;
`endif
    reg [3:0] startup = 4'b1111;
    always @(posedge core_clk) startup <= {startup[2:0], 1'b0};
    wire rst = startup[3];
    (* ASYNC_REG = "TRUE" *) reg [4:0] sw_meta = 0, sw_sync = 0;
    always @(posedge core_clk) begin
        sw_meta <= {sw[15], sw[3:0]};
        sw_sync <= sw_meta;
    end
    wire button_start, busy, done, overflow;
    wire [7:0] pix_addr, pix_data;
    wire [5:0] class_id;
    reg core_start, result_valid;
    reg [3:0] stored_selection;
    button_pulse #(.STABLE_CLKS(BUTTON_STABLE_CLKS)) u_button (
        .clk(core_clk), .rst(rst), .button(btnC), .pulse(button_start)
    );
    image_input #(.STORED_FILE(STORED_FILE)) u_input (
        .clk(core_clk), .live_mode(1'b0), .stored_sel(stored_selection),
        .we(1'b0), .waddr(8'd0), .wdata(8'd0), .raddr(pix_addr), .rdata(pix_data)
    );
    cnn_core #(.M(M), .S(S), .FILTERS(16), .FILTER_W(4), .FM_ADDR_W(12),
        .CLASSES(43), .CLASS_W(6), .POOL_ADDR_W(10), .WEIGHT_ADDR_W(16), .FC_ROM_STYLE("block")) u_core (
        .clk(core_clk), .rst(rst), .start(core_start), .busy(busy), .done(done),
        .ovf(overflow), .cycles(), .pix_addr(pix_addr), .pix_rd(),
        .pix_data(pix_data), .class_id(class_id), .scores()
    );
    always @(posedge core_clk) begin
        if (rst) begin
            core_start <= 0;
            result_valid <= 0;
            stored_selection <= 0;
        end else begin
            core_start <= 0;
            if (done) result_valid <= 1;
            if (button_start && !sw_sync[4] && !busy && !core_start) begin
                stored_selection <= sw_sync[3:0];
                core_start <= 1;
                result_valid <= 0;
            end
        end
    end
    assign RsTx = 1'b1;
    assign led = {busy, result_valid, overflow, 7'd0, class_id};
    wire [3:0] tens = class_id / 6'd10;
    wire [3:0] ones = class_id % 6'd10;
    wire [15:0] digits = overflow ? 16'heeee :
        (result_valid && !busy ? {8'hff, tens, ones} : 16'hffff);
    sevenseg_status #(.DIGIT_CLKS(DISPLAY_DIGIT_CLKS)) u_display (
        .clk(core_clk), .rst(rst), .digits(digits), .seg(seg), .an(an), .dp(dp)
    );
endmodule
`default_nettype wire
