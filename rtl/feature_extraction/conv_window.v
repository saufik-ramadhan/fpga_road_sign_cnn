`timescale 1ns / 1ps
`default_nettype none

// conv_window: the image side of conv_engine's 3- and 9-multiplier versions.
// Reads the 16x16 image once per run, in raster order (row*16 + col), through
// the one-cycle image port, and keeps the newest 3x3 neighbourhood in
// registers. Two line buffers of 13 pixels hold the rest of the two rows above,
// so every pixel is read exactly once.
//
// When pixel (y, x) completes a window (y >= 2 and x >= 2), the window holds
// the pixels of output (r, c) = (y-2, x-2), and the module issues 8*ROWS steps
// for it, one per cycle: filters 0..7, each as ROWS kernel rows (ROWS = 3) or
// as one step (ROWS = 1). It reads the next pixel in the cycle of the last
// step, so the window moves on just after that step has used it, and the steps
// of consecutive windows follow without a gap. The 60 pixels that complete no
// window (rows 0 and 1, and columns 0 and 1 of rows 2 to 15) are read one per
// cycle.
//
//   cycle n    a step is issued: step_f, step_kr, step_pos (conv_engine's stage A)
//   cycle n+1  win holds that step's pixels (stage D)
//
// The image must not change during a run. pix_addr is the next pixel to read
// and pix_rd marks the cycles that read it.

module conv_window #(
    parameter ROWS = 1                  // steps per filter: 1 (N_MAC = 9) or 3 (N_MAC = 3)
) (
    input  wire        clk,
    input  wire        rst,             // synchronous, active high
    input  wire        go,              // start a run
    // input image, through input_mux: pix_data arrives one cycle after pix_addr
    output wire        pix_rd,
    output reg  [7:0]  pix_addr,        // row*16 + col
    input  wire [7:0]  pix_data,
    // steps, in the order they are issued
    output reg         step_valid,      // a step is issued this cycle
    output reg  [2:0]  step_f,          // filter
    output reg  [1:0]  step_kr,         // kernel row, 0 when ROWS = 1
    output reg  [7:0]  step_pos,        // output row*14 + col, 0..195
    // the window, one cycle after its steps: pixel (r+kr, c+kc) in bits 8*(kr*3 + kc) +: 8
    output wire [71:0] win
);

    localparam [7:0] LAST_PIX = 8'd255;
    localparam [2:0] LAST_FILTER = 3'd7;
    localparam [1:0] LAST_ROW = ROWS - 1;

    // ---- reads and steps ---------------------------------------------------
    reg more;                           // pixels left to read

    wire last_step = step_valid && step_f == LAST_FILTER && step_kr == LAST_ROW;
    wire complete  = pix_addr[7:5] != 3'd0 && pix_addr[3:1] != 3'd0;   // row >= 2, col >= 2

    assign pix_rd = more && (!step_valid || last_step);

    always @(posedge clk) begin
        if (rst) begin
            more       <= 1'b0;
            step_valid <= 1'b0;
        end else if (go) begin
            more       <= 1'b1;
            step_valid <= 1'b0;
        end else if (pix_rd) begin
            more       <= pix_addr != LAST_PIX;
            step_valid <= complete;     // its steps start in the next cycle
        end else if (last_step) begin
            step_valid <= 1'b0;         // the last window of the image
        end
    end

    always @(posedge clk) begin
        if (rst || go) begin
            pix_addr <= 8'd0;
            step_f   <= 3'd0;
            step_kr  <= 2'd0;
            step_pos <= 8'd0;
        end else begin
            if (pix_rd)
                pix_addr <= pix_addr + 8'd1;
            if (step_valid) begin
                if (step_kr != LAST_ROW) begin
                    step_kr <= step_kr + 2'd1;
                end else begin
                    step_kr <= 2'd0;
                    step_f  <= step_f + 3'd1;       // 7 wraps to 0 for the next window
                    if (step_f == LAST_FILTER)
                        step_pos <= step_pos + 8'd1;
                end
            end
        end
    end

    // ---- window and line buffers ---------------------------------------------
    // After pixel (y, x) has moved in, w[kr*3 + kc] holds pixel (y-2+kr, x-2+kc).
    // Each window row passes its oldest pixel to a line buffer of 13 pixels,
    // which hands it to the row above 16 moves (one image row) after it entered
    // the window: lb_mid between the bottom and middle rows, lb_top between the
    // middle and top rows. No reset: a window is used only after the 35 pixels
    // from its top-left to its bottom-right corner have moved in during this run.
    reg shift;                          // pix_data holds the pixel read in the last cycle
    reg [7:0] w      [0:8];
    reg [7:0] lb_mid [0:12];
    reg [7:0] lb_top [0:12];
    integer i;

    always @(posedge clk) begin
        if (rst)
            shift <= 1'b0;
        else
            shift <= pix_rd;
    end

    always @(posedge clk) begin
        if (shift) begin
            w[8] <= pix_data;
            w[7] <= w[8];
            w[6] <= w[7];
            lb_mid[0] <= w[6];
            for (i = 1; i < 13; i = i + 1)
                lb_mid[i] <= lb_mid[i-1];
            w[5] <= lb_mid[12];
            w[4] <= w[5];
            w[3] <= w[4];
            lb_top[0] <= w[3];
            for (i = 1; i < 13; i = i + 1)
                lb_top[i] <= lb_top[i-1];
            w[2] <= lb_top[12];
            w[1] <= w[2];
            w[0] <= w[1];
        end
    end

    assign win = {w[8], w[7], w[6], w[5], w[4], w[3], w[2], w[1], w[0]};

endmodule

`default_nettype wire
