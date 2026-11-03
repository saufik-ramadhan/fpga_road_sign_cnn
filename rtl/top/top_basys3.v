`timescale 1ns / 1ps
`default_nettype none

// Basys 3 integration top: one 100 MHz clock domain, no dummy CNN.
// BTNC in stored mode (SW15=0) starts SW3:0; UART requests always use live RAM.
// One UART request arriving during a stored run is queued; no unsolicited
// UART reply is generated for a button-triggered stored inference.
module top_basys3 #(
    parameter CLKS_PER_BIT = 868,
    parameter TIMEOUT_CLKS = 1_000_000,
    parameter BUTTON_STABLE_CLKS = 2_000_000,
    parameter DISPLAY_DIGIT_CLKS = 100_000,
    parameter STORED_FILE = "signs.mem",
    parameter [15:0] M = 16'd43980,
    parameter S = 25,
    parameter CONV_WEIGHT_FILE = "conv_weight.mem",
    parameter CONV_BIAS_FILE = "conv_bias.mem",
    parameter FC_WEIGHT_FILE = "fc_weight.mem",
    parameter FC_BIAS_FILE = "fc_bias.mem",
    parameter ENABLE_CONV2 = 0,
    parameter [15:0] CONV2_M = 16'd54743,
    parameter CONV2_S = 24,
    parameter N_MAC = 1,
    parameter FC_MAC = 1
) (
    input wire clk, RsRx, btnC,
    input wire [15:0] sw,
    output wire RsTx,
    output wire [15:0] led,
    output wire [6:0] seg,
    output wire [3:0] an,
    output wire dp
);
    // Power-on synchronous reset for P1/P3/P4. P5 retains its existing FPGA
    // initial state; there is deliberately no partial run-time reset button.
    reg [3:0] startup = 4'b1111;
    always @(posedge clk) startup <= {startup[2:0], 1'b0};
    wire rst = startup[3];
    (* ASYNC_REG = "TRUE" *) reg [4:0] sw_meta = 0, sw_sync = 0;
    always @(posedge clk) begin
        sw_meta <= {sw[15], sw[3:0]}; sw_sync <= sw_meta;
    end
    wire button_start;
    button_pulse #(.STABLE_CLKS(BUTTON_STABLE_CLKS)) u_button (
        .clk(clk), .rst(rst), .button(btnC), .pulse(button_start)
    );
    wire uart_start, uart_error, busy, done, overflow, pix_rd;
    wire [7:0] pixel_addr, pixel_data;
    wire [2:0] class_id;
    wire [191:0] scores;
    wire [31:0] cycles;
    reg core_start, active_uart, pending_uart, result_valid;
    reg [3:0] stored_selection;
    comm_top #(.CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CLKS(TIMEOUT_CLKS),
        .STORED_FILE(STORED_FILE)) u_comm (
        .clk(clk), .rx(RsRx), .tx(RsTx),
        .live_mode(active_uart), .stored_sel(stored_selection),
        .img_raddr(pixel_addr), .img_rdata(pixel_data), .cnn_start(uart_start),
        .cnn_done(done && active_uart), .cnn_class(class_id), .cnn_scores(scores),
        .cnn_cycles(cycles), .uart_err(uart_error)
    );
    cnn_core #(.M(M), .S(S), .CONV_WEIGHT_FILE(CONV_WEIGHT_FILE),
        .CONV_BIAS_FILE(CONV_BIAS_FILE), .FC_WEIGHT_FILE(FC_WEIGHT_FILE),
        .FC_BIAS_FILE(FC_BIAS_FILE), .ENABLE_CONV2(ENABLE_CONV2),
        .CONV2_M(CONV2_M), .CONV2_S(CONV2_S),
        .N_MAC(N_MAC), .FC_MAC(FC_MAC)) u_core (
        .clk(clk), .rst(rst), .start(core_start), .busy(busy), .done(done),
        .ovf(overflow), .cycles(cycles), .pix_addr(pixel_addr), .pix_rd(pix_rd),
        .pix_data(pixel_data), .class_id(class_id), .scores(scores)
    );
    always @(posedge clk) begin
        if (rst) begin
            core_start <= 0; active_uart <= 0; pending_uart <= 0;
            stored_selection <= 0; result_valid <= 0;
        end else begin
            core_start <= 0;
            if (done) result_valid <= 1;
            if (uart_start) pending_uart <= 1;
            if (!busy && !core_start) begin
                if (pending_uart || uart_start) begin
                    active_uart <= 1; pending_uart <= 0; core_start <= 1; result_valid <= 0;
                end else if (button_start && !sw_sync[4]) begin
                    active_uart <= 0; stored_selection <= sw_sync[3:0];
                    core_start <= 1; result_valid <= 0;
                end
            end
        end
    end
    assign led = {busy, result_valid, overflow, uart_error, 6'd0,
                  pending_uart, active_uart, result_valid, class_id};
    wire [15:0] display_digits = overflow ? 16'heeee :
        (result_valid && !busy ? {12'hfff, 1'b0, class_id} : 16'hffff);
    sevenseg_status #(.DIGIT_CLKS(DISPLAY_DIGIT_CLKS)) u_display (
        .clk(clk), .rst(rst), .digits(display_digits), .seg(seg), .an(an), .dp(dp)
    );
endmodule
`default_nettype wire
