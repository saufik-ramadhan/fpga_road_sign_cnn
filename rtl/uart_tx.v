// uart_tx.v  -  sends one byte at a time to the laptop (8N1)
// Pulse "send" for 1 tick while "busy" is 0. "busy" is 1 until the byte is gone.
module uart_tx #(
    parameter CLKS_PER_BIT = 868            // 100 MHz / 115200 baud = 868
)(
    input  wire       clk,
    input  wire [7:0] data,                 // byte to send
    input  wire       send,                 // 1 tick: "please send data"
    output reg        busy = 1'b0,
    output reg        tx   = 1'b1           // pin RsTx (to USB); idle level is high
);
    localparam IDLE = 0, START = 1, DATA = 2, STOP = 3;

    reg [1:0]  state     = IDLE;
    reg [15:0] clk_count = 0;
    reg [2:0]  bit_index = 0;
    reg [7:0]  shift     = 8'd0;            // copy of the byte being sent

    always @(posedge clk) begin
        case (state)
            IDLE: begin
                tx <= 1'b1;
                if (send) begin
                    shift     <= data;
                    busy      <= 1'b1;
                    clk_count <= 0;
                    tx        <= 1'b0;      // start bit
                    state     <= START;
                end
            end

            START: begin                    // hold the start bit for one bit time
                if (clk_count == CLKS_PER_BIT - 1) begin
                    clk_count <= 0;
                    bit_index <= 0;
                    tx        <= shift[0];  // first data bit (LSB)
                    state     <= DATA;
                end else clk_count <= clk_count + 1;
            end

            DATA: begin
                if (clk_count == CLKS_PER_BIT - 1) begin
                    clk_count <= 0;
                    if (bit_index == 7) begin
                        tx    <= 1'b1;      // stop bit
                        state <= STOP;
                    end else begin
                        bit_index <= bit_index + 1;
                        tx        <= shift[bit_index + 1];
                    end
                end else clk_count <= clk_count + 1;
            end

            STOP: begin
                if (clk_count == CLKS_PER_BIT - 1) begin
                    busy  <= 1'b0;
                    state <= IDLE;
                end else clk_count <= clk_count + 1;
            end
        endcase
    end
endmodule
