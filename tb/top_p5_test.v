// top_p5_test.v  -  test top for the Basys3: P5 comm code + dummy CNN
// Use this until P1's real top.v is ready. Then delete it and the dummy.
//
//   Live mode   (SW15 = 1): laptop sends a picture with tsr_link.py
//   Stored mode (SW15 = 0): SW3..SW0 choose picture, press BTNC
//   LEDs: LD2..LD0 = class,  LD15 = busy,  LD14 = done,  LD12 = UART error
module top_p5_test (
    input  wire        clk,                 // 100 MHz
    input  wire        RsRx,                // USB-UART: laptop -> board
    output wire        RsTx,                // USB-UART: board -> laptop
    input  wire [15:0] sw,
    input  wire        btnC,
    output wire [15:0] led
);
    // ---- wires between P5's box and the dummy CNN ----
    wire [7:0]   img_raddr, img_rdata;
    wire         cnn_start_uart, cnn_start, cnn_done;
    wire [2:0]   cnn_class;
    wire [191:0] cnn_scores;
    wire [31:0]  cnn_cycles;
    wire         uart_err;

    // ---- BTNC -> one-tick pulse (no debounce, enough for a test) ----
    reg b1 = 0, b2 = 0, b3 = 0;
    always @(posedge clk) begin b1 <= btnC; b2 <= b1; b3 <= b2; end
    wire btn_pulse = b2 & ~b3;

    assign cnn_start = cnn_start_uart | btn_pulse;

    comm_top u_comm (                       // <-- P5's real code
        .clk(clk), .rx(RsRx), .tx(RsTx),
        .live_mode(sw[15]), .stored_sel(sw[3:0]),
        .img_raddr(img_raddr), .img_rdata(img_rdata),
        .cnn_start(cnn_start_uart), .cnn_done(cnn_done),
        .cnn_class(cnn_class), .cnn_scores(cnn_scores), .cnn_cycles(cnn_cycles),
        .uart_err(uart_err));

    dummy_cnn u_cnn (                       // <-- replace with the real CNN later
        .clk(clk), .start(cnn_start), .done(cnn_done),
        .img_addr(img_raddr), .img_pixel(img_rdata),
        .class_id(cnn_class), .scores(cnn_scores), .cycles(cnn_cycles));

    // ---- LEDs ----
    reg busy = 0, done_led = 0;
    always @(posedge clk) begin
        if (cnn_start)     begin busy <= 1; done_led <= 0; end
        else if (cnn_done) begin busy <= 0; done_led <= 1; end
    end

    assign led[2:0]   = cnn_class;
    assign led[11:3]  = 9'd0;
    assign led[12]    = uart_err;
    assign led[13]    = 1'b0;
    assign led[14]    = done_led;
    assign led[15]    = busy;
endmodule
