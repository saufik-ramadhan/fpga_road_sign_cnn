// frame_ctrl.v  -  P5: unpacks each message from the laptop, packs the reply
//
// REQUEST  (laptop -> board), 259 bytes:
//     A5 | CMD | 256 pixel bytes | CHK
//     CMD = 01 means "classify this picture".
//     CHK = low 8 bits of the sum of CMD + all 256 pixels.
//
// REPLY    (board -> laptop), 32 bytes (same size for good and bad replies):
//     5A | STATUS | CLASS | CYCLES(4 bytes) | 8 SCORES (3 bytes each) | CHK
//     STATUS: 00 OK, 01 bad checksum, 02 timeout, 03 unknown command
//     CLASS : 0..7
//     CHK   = low 8 bits of the sum of every byte between 5A and CHK.
//     (All multi-byte numbers are sent big-endian: the biggest byte first.)
//
// A frame stops mid-way if more than TIMEOUT_CLKS ticks pass between bytes;
// the board drops it silently and the laptop resends after 200 ms.
module frame_ctrl #(
    parameter TIMEOUT_CLKS = 1_000_000      // 10 ms at 100 MHz
)(
    input  wire         clk,

    // from uart_rx
    input  wire [7:0]   rx_data,
    input  wire         rx_valid,

    // to uart_tx
    output reg  [7:0]   tx_data = 8'd0,
    output reg          tx_send = 1'b0,
    input  wire         tx_busy,

    // to image_input (write side)
    output reg          img_we    = 1'b0,
    output reg  [7:0]   img_waddr = 8'd0,
    output reg  [7:0]   img_wdata = 8'd0,

    // CNN handshake (P1 controller / P3 / P4 provide these)
    output reg          cnn_start = 1'b0,   // 1 tick: "picture is ready, go"
    input  wire         cnn_done,           // 1 tick: "answer is ready"
    input  wire [2:0]   cnn_class,          // the answer, 0..7
    input  wire [191:0] cnn_scores,         // 8 scores x 24 bit; score k = bits [24*k +: 24]
    input  wire [31:0]  cnn_cycles,         // clock ticks the CNN needed

    // status
    output reg          uart_err = 1'b0     // for LD12: last frame was bad
);
    // ---- the steps this module goes through ----------------------------
    localparam S_SYNC  = 0;   // wait for A5
    localparam S_CMD   = 1;   // read the command byte
    localparam S_PIX   = 2;   // read 256 pixels
    localparam S_CHK   = 3;   // read the checksum, decide what to do
    localparam S_RUN   = 4;   // wait for the CNN to finish
    localparam S_LOAD  = 5;   // pick the next reply byte
    localparam S_PULSE = 6;   // give the UART one tick of "send"
    localparam S_WAIT  = 7;   // wait until the UART finished sending it

    reg [2:0] state = S_SYNC;

    // ---- receiving ------------------------------------------------------
    reg [7:0]  cmd      = 8'd0;
    reg [7:0]  rx_sum   = 8'd0;             // running checksum of the request
    reg [7:0]  px_count = 8'd0;             // which pixel is next (0..255)
    reg [23:0] timer    = 24'd0;            // ticks since the last byte

    // ---- the reply ------------------------------------------------------
    reg [7:0]   r_status = 8'd0;
    reg [2:0]   r_class  = 3'd0;
    reg [31:0]  r_cycles = 32'd0;
    reg [191:0] r_scores = 192'd0;          // score 0 sits at the TOP so we can shift it out
    reg [4:0]   tx_index = 5'd0;            // which reply byte (0..31)
    reg [7:0]   tx_sum   = 8'd0;            // running checksum of the reply

    // The reply byte for the current tx_index
    reg [7:0] reply_byte;
    always @(*) begin
        case (tx_index)
            5'd0:    reply_byte = 8'h5A;                    // sync
            5'd1:    reply_byte = r_status;
            5'd2:    reply_byte = {5'd0, r_class};
            5'd3:    reply_byte = r_cycles[31:24];
            5'd4:    reply_byte = r_cycles[23:16];
            5'd5:    reply_byte = r_cycles[15:8];
            5'd6:    reply_byte = r_cycles[7:0];
            5'd31:   reply_byte = tx_sum;                   // checksum
            default: reply_byte = r_scores[191:184];        // index 7..30: scores, top byte first
        endcase
    end

    integer k;

    always @(posedge clk) begin
        // one-tick signals go back to 0 unless set below
        img_we    <= 1'b0;
        cnn_start <= 1'b0;
        tx_send   <= 1'b0;

        // timeout timer: only counts while we are in the middle of receiving
        if (rx_valid || state == S_SYNC || state >= S_RUN) timer <= 0;
        else                                               timer <= timer + 1;

        case (state)
            // ================= RECEIVE =================
            S_SYNC: begin
                if (rx_valid && rx_data == 8'hA5) state <= S_CMD;
            end

            S_CMD: begin
                if (rx_valid) begin
                    cmd      <= rx_data;
                    rx_sum   <= rx_data;
                    px_count <= 8'd0;
                    state    <= S_PIX;
                end
            end

            S_PIX: begin
                if (rx_valid) begin
                    img_we    <= 1'b1;          // write the pixel into image_input
                    img_waddr <= px_count;
                    img_wdata <= rx_data;
                    rx_sum    <= rx_sum + rx_data;
                    px_count  <= px_count + 1;
                    if (px_count == 8'd255) state <= S_CHK;
                end
            end

            S_CHK: begin
                if (rx_valid) begin
                    if (rx_data != rx_sum) begin            // damaged message
                        r_status <= 8'h01;  uart_err <= 1'b1;
                        r_class  <= 3'd0;   r_cycles <= 32'd0;  r_scores <= 192'd0;
                        tx_index <= 5'd0;   tx_sum   <= 8'd0;
                        state    <= S_LOAD;                 // send an error reply
                    end else if (cmd != 8'h01) begin        // message fine, command unknown
                        r_status <= 8'h03;  uart_err <= 1'b1;
                        r_class  <= 3'd0;   r_cycles <= 32'd0;  r_scores <= 192'd0;
                        tx_index <= 5'd0;   tx_sum   <= 8'd0;
                        state    <= S_LOAD;
                    end else begin                          // good picture: run the CNN
                        uart_err  <= 1'b0;
                        cnn_start <= 1'b1;
                        state     <= S_RUN;
                    end
                end
            end

            // ================= WAIT FOR THE CNN =================
            S_RUN: begin
                if (cnn_done) begin
                    r_status <= 8'h00;
                    r_class  <= cnn_class;
                    r_cycles <= cnn_cycles;
                    // reorder: score 0 goes to the top of r_scores
                    for (k = 0; k < 8; k = k + 1)
                        r_scores[191 - 24*k -: 24] <= cnn_scores[24*k +: 24];
                    tx_index <= 5'd0;
                    tx_sum   <= 8'd0;
                    state    <= S_LOAD;
                end
            end

            // ================= SEND THE REPLY =================
            S_LOAD: begin
                tx_data <= reply_byte;
                tx_send <= 1'b1;
                if (tx_index >= 5'd1 && tx_index <= 5'd30)
                    tx_sum <= tx_sum + reply_byte;          // add to checksum
                if (tx_index >= 5'd7 && tx_index <= 5'd30)
                    r_scores <= {r_scores[183:0], 8'h00};   // next score byte moves to the top
                state <= S_PULSE;
            end

            S_PULSE: begin                      // tx_send is 1 during this tick; UART sees it
                state <= S_WAIT;
            end

            S_WAIT: begin
                if (!tx_busy) begin             // UART finished this byte
                    if (tx_index == 5'd31) state <= S_SYNC;     // whole reply sent
                    else begin
                        tx_index <= tx_index + 1;
                        state    <= S_LOAD;
                    end
                end
            end
        endcase

        // Timeout: bytes stopped coming in the middle of a frame -> give up
        if (timer >= TIMEOUT_CLKS && state >= S_CMD && state <= S_CHK) begin
            state    <= S_SYNC;
            uart_err <= 1'b1;
        end
    end
endmodule
