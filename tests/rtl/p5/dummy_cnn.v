// dummy_cnn.v  -  PLACEHOLDER for P1 (controller) + P3 + P4 (CNN).
// Delete this file when the real CNN is ready; it has the same ports.
//
// What it does (so you can test the whole cable path):
//   1. reads all 256 pixels through image_input
//   2. adds them up                         -> sum
//   3. answer: class = sum mod 8            (the laptop can predict this!)
//   4. scores: the winning class gets 1000, class k otherwise gets k*10
//   5. cycles = how many clock ticks it took
module dummy_cnn (
    input  wire         clk,
    input  wire         start,              // 1 tick: begin
    output reg          done = 1'b0,        // 1 tick: answer ready

    output reg  [7:0]   img_addr = 8'd0,    // to image_input
    input  wire [7:0]   img_pixel,          // from image_input (1 tick later)

    output reg  [2:0]   class_id = 3'd0,
    output wire [191:0] scores,
    output reg  [31:0]  cycles   = 32'd0
);
    localparam IDLE = 0, READ = 1, FINISH = 2;
    reg [1:0]  state = IDLE;
    reg [8:0]  n     = 9'd0;                // 0..257
    reg [31:0] sum   = 32'd0;

    always @(posedge clk) begin
        done <= 1'b0;
        case (state)
            IDLE: if (start) begin
                n      <= 0;
                sum    <= 0;
                cycles <= 1;
                state  <= READ;
            end

            READ: begin
                cycles   <= cycles + 1;
                img_addr <= n[7:0];                 // ask for pixel n
                if (n >= 2) sum <= sum + img_pixel; // pixel (n-2) arrives now
                if (n == 9'd257) state <= FINISH;
                else n <= n + 1;
            end

            FINISH: begin
                cycles   <= cycles + 1;
                class_id <= sum[2:0];
                done     <= 1'b1;
                state    <= IDLE;
            end
        endcase
    end

    // fake scores, built from class_id
    genvar g;
    generate
        for (g = 0; g < 8; g = g + 1) begin : fake_score
            assign scores[24*g +: 24] = (class_id == g) ? 24'd1000 : (g * 10);
        end
    endgenerate
endmodule
