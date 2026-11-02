// comm_top.v  -  everything P5 owns, in one box
//   uart_rx -> frame_ctrl -> uart_tx     (talking to the laptop)
//   image_input                          (picks live / stored picture)
// P1 connects this box to the real controller + CNN.
module comm_top #(
    parameter CLKS_PER_BIT = 868,           // 100 MHz / 115200 baud
    parameter TIMEOUT_CLKS = 1_000_000,     // 10 ms
    parameter STORED_FILE  = ""             // P2's .mem file with the 16 stored pictures
)(
    input  wire         clk,
    input  wire         rx,                 // RsRx pin
    output wire         tx,                 // RsTx pin

    input  wire         live_mode,          // SW15: 1 = picture from laptop, 0 = stored
    input  wire [3:0]   stored_sel,         // SW3..SW0: which stored picture

    // CNN side
    input  wire [7:0]   img_raddr,          // CNN asks for pixel at this address
    output wire [7:0]   img_rdata,          // ...and gets it 1 tick later
    output wire         cnn_start,          // 1 tick when a laptop picture is ready
    input  wire         cnn_done,
    input  wire [2:0]   cnn_class,
    input  wire [191:0] cnn_scores,
    input  wire [31:0]  cnn_cycles,

    output wire         uart_err            // LD12
);
    wire [7:0] rx_data;
    wire       rx_valid;
    wire [7:0] tx_data;
    wire       tx_send, tx_busy;
    wire       img_we;
    wire [7:0] img_waddr, img_wdata;

    uart_rx #(.CLKS_PER_BIT(CLKS_PER_BIT)) u_rx (
        .clk(clk), .rx(rx), .data(rx_data), .valid(rx_valid));

    uart_tx #(.CLKS_PER_BIT(CLKS_PER_BIT)) u_tx (
        .clk(clk), .data(tx_data), .send(tx_send), .busy(tx_busy), .tx(tx));

    frame_ctrl #(.TIMEOUT_CLKS(TIMEOUT_CLKS)) u_frame (
        .clk(clk),
        .rx_data(rx_data), .rx_valid(rx_valid),
        .tx_data(tx_data), .tx_send(tx_send), .tx_busy(tx_busy),
        .img_we(img_we), .img_waddr(img_waddr), .img_wdata(img_wdata),
        .cnn_start(cnn_start), .cnn_done(cnn_done), .cnn_class(cnn_class),
        .cnn_scores(cnn_scores), .cnn_cycles(cnn_cycles),
        .uart_err(uart_err));

    image_input #(.STORED_FILE(STORED_FILE)) u_img (
        .clk(clk), .live_mode(live_mode), .stored_sel(stored_sel),
        .we(img_we), .waddr(img_waddr), .wdata(img_wdata),
        .raddr(img_raddr), .rdata(img_rdata));
endmodule
