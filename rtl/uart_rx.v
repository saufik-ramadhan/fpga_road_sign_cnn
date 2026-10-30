// uart_rx.v  -  receives one byte at a time from the laptop (8N1)
// When a full byte has arrived, "valid" is 1 for exactly one clock tick.
module uart_rx #(
    parameter CLKS_PER_BIT = 868            // 100 MHz / 115200 baud = 868
)(
    input  wire       clk,
    input  wire       rx,                   // pin RsRx (from USB)
    output reg  [7:0] data  = 8'd0,         // the received byte
    output reg        valid = 1'b0          // 1 tick: "data is new"
);
    localparam IDLE = 0, START = 1, DATA = 2, STOP = 3;

    reg [1:0]  state     = IDLE;
    reg [15:0] clk_count = 0;               // counts clock ticks inside one bit
    reg [2:0]  bit_index = 0;               // which of the 8 data bits (0 = first)

    // The rx pin is asynchronous, so pass it through 2 flip-flops first.
    reg rx_s1 = 1'b1, rx_s2 = 1'b1;
    always @(posedge clk) begin
        rx_s1 <= rx;
        rx_s2 <= rx_s1;
    end

    always @(posedge clk) begin
        valid <= 1'b0;                      // default: no new byte

        case (state)
            IDLE: begin                     // line is high; wait for the start bit (low)
                clk_count <= 0;
                if (rx_s2 == 1'b0) state <= START;
            end

            START: begin                    // go to the MIDDLE of the start bit
                if (clk_count == (CLKS_PER_BIT - 1) / 2) begin
                    clk_count <= 0;
                    bit_index <= 0;
                    if (rx_s2 == 1'b0) state <= DATA;   // still low: real start bit
                    else               state <= IDLE;   // glitch: ignore
                end else clk_count <= clk_count + 1;
            end

            DATA: begin                     // sample each data bit in its middle
                if (clk_count == CLKS_PER_BIT - 1) begin
                    clk_count        <= 0;
                    data[bit_index]  <= rx_s2;          // UART sends the LSB first
                    if (bit_index == 7) state <= STOP;
                    else bit_index <= bit_index + 1;
                end else clk_count <= clk_count + 1;
            end

            STOP: begin                     // wait out the stop bit, then report the byte
                if (clk_count == CLKS_PER_BIT - 1) begin
                    valid <= 1'b1;
                    state <= IDLE;
                end else clk_count <= clk_count + 1;
            end
        endcase
    end
endmodule
