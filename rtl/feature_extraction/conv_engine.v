`timescale 1ns / 1ps
`default_nettype none

// conv_engine: the 3x3 convolution layer (8 filters, no padding) with its
// rescale and ReLU. Reads the 16x16 input image and writes the 14x14x8 = 1,568
// activations (0..127) into fmap_ram. The arithmetic is P2's contract
// (reference_model/README.md): an ACC_W-bit accumulator that starts
// at the filter's bias and adds the 9 products in kernel order.
//
// N_MAC sets how many multipliers work in parallel: 1 (the default), 3 or 9.
// Every version adds the same products in the same order, each through an
// adder of its own, so all of them give the same accumulators, activations
// and ovf; only the cycle count and the resources differ.
//
// N_MAC = 1: one multiply-accumulate per clock cycle. Taps are issued in the
// order filter, output row, output column, kernel row, kernel column, so every
// output takes exactly 9 cycles and the pipeline never stalls: a run takes
// 1,568 x 9 = 14,112 cycles plus the pipeline depth.
//
//   stage A  counters drive pix_addr and the weight address
//   stage D  pixel and weight arrive (both memories take one cycle)
//   stage P  product register (the multiplier register in the DSP slice);
//            the filter's bias arrives
//   stage C  accumulator: the filter's bias plus 9 products, ACC_W bits
//   then requant_relu (2 stages) and the fmap_ram write
//
// N_MAC = 3 and 9: the image has one read port, so conv_window reads each
// pixel once, in raster order, into a 3x3 register window fed by two line
// buffers, and holds each window position while all 8 filters use it. The
// order is output row, output column, filter, then kernel row for N_MAC = 3.
//
//   stage A  conv_window issues a step: a filter (and kernel row) of a window
//   stage D  the weights arrive, a kernel row or a whole kernel per read;
//            the window holds the step's pixels
//   stage P  N_MAC products (DSP slices); the filter's bias arrives
//   N_MAC = 3: stage C adds the row's 3 products to the accumulator, which
//              starts at the bias: 3 steps per output, 24 per window
//   N_MAC = 9: three pipelined stages add the kernel's rows to the bias, one
//              row each, then the sum goes to acc: one output per cycle
//   then requant_relu (2 stages) and the fmap_ram write
//
// From start to done, the same for every image: N_MAC = 1 takes 14,117
// cycles (14,112 steps and 5 of pipeline); N_MAC = 3 takes 4,770 (4,704 steps,
// 61 in which the window fills: its first 35 pixels, then 2 at each new row,
// and 5 of pipeline); N_MAC = 9 takes 1,636 (1,568 steps, 61 and 7).
//
// Handshake: a 1-cycle start pulse while idle begins a run; start is ignored
// while busy. done is a 1-cycle pulse in the cycle after the last fmap_ram
// write, and busy falls with it. ovf is set if any partial sum of P2's serial
// order (the bias, plus the products added one at a time in kernel order)
// leaves the ACC_W-bit range, which the contract forbids, even if a later
// product would bring it back; it stays set until the next start.
//
// The parameter defaults are P2's model p2-doc-int-v2, the values in its
// params.vh (P2_RESCALE_M, P2_RESCALE_S, P2_ACC_BITS), so a top that passes no
// parameters runs that model; p2-int-v1 needs M = 34172 and ACC_W = 32. The two
// .mem files are the package's mem/ files, and conv_bias.mem's words must be
// ACC_W bits wide. Simulators read them from their working folder, and Vivado
// finds them once they are added to the project (read_mem in a non-project
// Tcl flow).

module conv_engine #(
    parameter [15:0] M           = 16'd43980,          // rescale multiplier, 1..65535
    parameter        S           = 25,                 // rescale shift, 0..47
    parameter        ACC_W       = 24,                 // accumulator and bias width, 18..32
    parameter        WEIGHT_FILE = "conv_weight.mem",  // 72 weights, int8
    parameter        BIAS_FILE   = "conv_bias.mem",    // 8 biases, ACC_W bits each
    parameter        FILTERS = 8,
    parameter FILTER_W = 3,
    parameter FM_ADDR_W = 11,
    parameter N_MAC       = 1                   // multipliers: 1, 3 or 9
) (
    input  wire        clk,
    input  wire        rst,        // synchronous, active high
    input  wire        start,
    output reg         busy,
    output reg         done,
    output reg         ovf,        // a partial sum left the ACC_W-bit range
    // input image, through input_mux: pix_data arrives one cycle after pix_addr
    output wire        pix_rd,
    output wire [7:0]  pix_addr,   // row*16 + col
    input  wire [7:0]  pix_data,   // unsigned, 0..255
    // fmap_ram write port
    output wire        fm_we,
    output wire [FM_ADDR_W-1:0] fm_addr,    // filter*196 + row*14 + col
    output wire [7:0]  fm_data     // 0..127
);

    localparam [FM_ADDR_W-1:0] LAST_OUT = FILTERS * 196 - 1;
    localparam [3:0] LAST_OUTPUT_COORD = 4'd13;
    localparam [1:0] LAST_KERNEL_COORD = 2'd2;
    localparam [6:0] KERNEL_TAPS = 7'd9;
    localparam [6:0] KERNEL_SIDE = 7'd3;
    localparam [FM_ADDR_W-1:0] FILTER_OUTPUTS = 11'd196;

    // synthesis translate_off
    initial begin
        if (ACC_W < 18 || ACC_W > 32) begin
            $display("conv_engine: ACC_W = %0d is outside 18..32", ACC_W);
            $finish;
        end
        if ((N_MAC != 1 && N_MAC != 3 && N_MAC != 9) ||
            (N_MAC != 1 && FILTERS != 8)) begin
            $display("conv_engine: N_MAC = %0d; it must be 1, 3 or 9", N_MAC);
            $finish;
        end
    end
    // synthesis translate_on

    wire go = start && !busy;

    // ---- the accumulator's last step, in every version ---------------------
    // p_valid: a step adds products to the sum of output p_oaddr this cycle,
    // and acc_ovf says that one of the step's partial sums left the ACC_W-bit
    // range. acc holds a finished sum when acc_valid is high, for output
    // acc_oaddr. requant_relu, the overflow flag and conv_engine_tb use these.
    reg                    p_valid;
    reg [FM_ADDR_W-1:0]             p_oaddr;
    wire                   acc_ovf;
    reg signed [ACC_W-1:0] acc;
    reg                    acc_valid;    // acc holds a finished output
    reg [FM_ADDR_W-1:0]             acc_oaddr;

    // One kernel row of P2's serial sum, as N_MAC = 9's row stages add it (and
    // N_MAC = 3's accumulator, written out): base, plus each of the row's
    // three products in turn (kernel column kc in q[17*kc +: 17]). Each partial
    // sum is exact in ACC_W + 1 bits, and it is outside the ACC_W-bit range
    // when its top two bits differ. Returns {a partial sum was outside, the
    // row's sum in ACC_W bits}: the sum passed on keeps ACC_W bits, as the
    // accumulator of N_MAC = 1 does.
    function [ACC_W:0] row_add;
        input signed [ACC_W-1:0] base;
        input        [50:0]      q;
        reg   signed [ACC_W:0]   s1, s2, s3;
        begin
            s1 = base + $signed(q[16:0]);
            s2 = s1 + $signed(q[33:17]);
            s3 = s2 + $signed(q[50:34]);
            row_add = {s1[ACC_W] != s1[ACC_W-1] || s2[ACC_W] != s2[ACC_W-1] ||
                       s3[ACC_W] != s3[ACC_W-1], s3[ACC_W-1:0]};
        end
    endfunction

    generate
    if (N_MAC == 1) begin : g_serial

        // ---- stage A: tap counters -----------------------------------------
        reg        run;                 // issuing taps
        reg [FILTER_W-1:0] f;
        reg [3:0]  r, c;                // output row and column, 0..13
        reg [1:0]  kr, kc;              // kernel row and column, 0..2
        reg [FM_ADDR_W-1:0] oaddr;               // f*196 + r*14 + c, counts 0..1567

        wire tap_first = (kr == 2'd0) && (kc == 2'd0);
        wire tap_last  = (kr == LAST_KERNEL_COORD) && (kc == LAST_KERNEL_COORD);

        wire [3:0] pix_row = r + {2'b00, kr};
        wire [3:0] pix_col = c + {2'b00, kc};
        assign pix_addr = {pix_row, pix_col};
        assign pix_rd   = run;

        wire [FILTER_W+3:0] w_addr = f * KERNEL_TAPS + kr * KERNEL_SIDE + kc;

        always @(posedge clk) begin
            if (rst)
                run <= 1'b0;
            else if (go)
                run <= 1'b1;
            else if (run && tap_last && oaddr == LAST_OUT)
                run <= 1'b0;
        end

        always @(posedge clk) begin
            if (rst || go) begin
                f     <= 3'd0;
                r     <= 4'd0;
                c     <= 4'd0;
                kr    <= 2'd0;
                kc    <= 2'd0;
                oaddr <= 11'd0;
            end else if (run) begin
                if (kc != LAST_KERNEL_COORD) begin
                    kc <= kc + 2'd1;
                end else begin
                    kc <= 2'd0;
                    if (kr != LAST_KERNEL_COORD) begin
                        kr <= kr + 2'd1;
                    end else begin
                        kr    <= 2'd0;
                        oaddr <= oaddr + 11'd1;
                        if (c != LAST_OUTPUT_COORD) begin
                            c <= c + 4'd1;
                        end else begin
                            c <= 4'd0;
                            if (r != LAST_OUTPUT_COORD) begin
                                r <= r + 4'd1;
                            end else begin
                                r <= 4'd0;
                                f <= f + 3'd1;
                            end
                        end
                    end
                end
            end
        end

        // ---- stage D: memory outputs ---------------------------------------
        reg        d_valid, d_first, d_last;
        reg [FILTER_W-1:0] d_f;
        reg [FM_ADDR_W-1:0] d_oaddr;

        // The bias is read with stage D's filter number, so it arrives in stage P
        // together with the product it starts the sum with.
        wire signed [7:0]       w_data;
        wire signed [ACC_W-1:0] b_data;

        conv_wrom #(.WEIGHT_FILE(WEIGHT_FILE), .BIAS_FILE(BIAS_FILE), .BIAS_W(ACC_W),
                    .FILTERS(FILTERS), .FILTER_W(FILTER_W)) u_wrom (
            .clk    (clk),
            .w_addr (w_addr),
            .w_data (w_data),
            .b_addr (d_f),
            .b_data (b_data)
        );

        always @(posedge clk) begin
            d_first <= tap_first;
            d_last  <= tap_last;
            d_f     <= f;
            d_oaddr <= oaddr;
        end

        // ---- stage P: product, 0..255 times -127..127 ----------------------
        // use_dsp: left alone, Vivado builds this small multiply from LUTs, and it
        // becomes the slowest path once pix_data comes from a block RAM. In a DSP
        // slice the whole multiply-accumulate fits in one DSP48E1.
        (* use_dsp = "yes" *)
        reg signed [16:0] p;
        reg               p_first, p_last;

        always @(posedge clk) begin
            p       <= $signed({1'b0, pix_data}) * w_data;
            p_first <= d_first;
            p_last  <= d_last;
            p_oaddr <= d_oaddr;
        end

        // ---- stage C: accumulator ------------------------------------------
        wire signed [ACC_W-1:0] acc_base = p_first ? b_data : acc;
        wire signed [ACC_W:0]   acc_sum  = acc_base + p;
        assign acc_ovf = acc_sum[ACC_W] != acc_sum[ACC_W-1];

        always @(posedge clk) begin
            if (p_valid)
                acc <= acc_sum[ACC_W-1:0];
            acc_oaddr <= p_oaddr;
        end

        always @(posedge clk) begin
            if (rst) begin
                d_valid   <= 1'b0;
                p_valid   <= 1'b0;
                acc_valid <= 1'b0;
            end else begin
                d_valid   <= run;
                p_valid   <= d_valid;
                acc_valid <= p_valid && p_last;
            end
        end

    end else begin : g_window

        // ---- stage A: conv_window issues the steps -------------------------
        localparam ROWS = 9 / N_MAC;    // steps per filter: kernel rows, or 1

        wire        s_valid;
        wire [2:0]  s_f;
        wire [1:0]  s_kr;
        wire [7:0]  s_pos;              // output row*14 + col
        wire [71:0] win;                // in stage D: pixel (r+kr, c+kc) in bits 8*(kr*3 + kc) +: 8

        conv_window #(.ROWS(ROWS)) u_window (
            .clk        (clk),
            .rst        (rst),
            .go         (go),
            .pix_rd     (pix_rd),
            .pix_addr   (pix_addr),
            .pix_data   (pix_data),
            .step_valid (s_valid),
            .step_f     (s_f),
            .step_kr    (s_kr),
            .step_pos   (s_pos),
            .win        (win)
        );

        wire [FILTER_W+3:0] w_addr = s_f * ROWS + s_kr;  // a kernel row (N_MAC = 3) or a kernel

        // ---- stage D: the weights arrive; win holds the step's pixels -------
        reg        d_valid;
        reg [FILTER_W-1:0] d_f;
        reg [1:0]  d_kr;
        reg [FM_ADDR_W-1:0] d_oaddr;

        // As in N_MAC = 1, the bias is read with stage D's filter number and
        // arrives in stage P, with the products the sum starts with.
        wire [8*N_MAC-1:0]      w_data;
        wire signed [ACC_W-1:0] b_data;

        conv_wrom #(.WEIGHT_FILE(WEIGHT_FILE), .BIAS_FILE(BIAS_FILE), .BIAS_W(ACC_W),
                    .TAPS(N_MAC), .FILTERS(FILTERS), .FILTER_W(FILTER_W)) u_wrom (
            .clk    (clk),
            .w_addr (w_addr),
            .w_data (w_data),
            .b_addr (d_f),
            .b_data (b_data)
        );

        always @(posedge clk) begin
            d_f     <= s_f;
            d_kr    <= s_kr;
            d_oaddr <= s_f * FILTER_OUTPUTS + s_pos;
        end

        always @(posedge clk) begin
            if (rst)
                d_valid <= 1'b0;
            else
                d_valid <= s_valid;
        end

        if (N_MAC == 3) begin : g_rows

            // ---- stage P: the three products of kernel row d_kr --------------
            reg d_first, d_last;
            wire [23:0] x = win[24*d_kr +: 24];

            always @(posedge clk) begin
                d_first <= s_kr == 2'd0;
                d_last  <= s_kr == LAST_KERNEL_COORD;
            end

            // One multiplier per kernel column, each with its own product
            // register, as in N_MAC = 1, so that Vivado puts each in a DSP slice.
            genvar t;
            for (t = 0; t < 3; t = t + 1) begin : g_mul
                (* use_dsp = "yes" *)
                reg signed [16:0] p;
                always @(posedge clk)
                    p <= $signed({1'b0, x[8*t +: 8]}) * $signed(w_data[8*t +: 8]);
            end
            wire [50:0] q = {g_mul[2].p, g_mul[1].p, g_mul[0].p};   // kernel column kc in bits 17*kc +: 17
            reg         p_first, p_last;

            always @(posedge clk) begin
                p_first <= d_first;
                p_last  <= d_last;
                p_oaddr <= d_oaddr;
            end

            // ---- stage C: accumulator, a kernel row per cycle ----------------
            // row_add written out with use_dsp = "no": acc feeds the next row,
            // and in this loop the three adders are faster in the fabric's
            // carry chains than chained through the three DSP slices.
            wire signed [ACC_W-1:0] base = p_first ? b_data : acc;
            (* use_dsp = "no" *)
            wire signed [ACC_W:0]   s1 = base + $signed(q[16:0]);
            (* use_dsp = "no" *)
            wire signed [ACC_W:0]   s2 = s1 + $signed(q[33:17]);
            (* use_dsp = "no" *)
            wire signed [ACC_W:0]   s3 = s2 + $signed(q[50:34]);
            assign acc_ovf = s1[ACC_W] != s1[ACC_W-1] || s2[ACC_W] != s2[ACC_W-1] ||
                             s3[ACC_W] != s3[ACC_W-1];

            always @(posedge clk) begin
                if (p_valid)
                    acc <= s3[ACC_W-1:0];
                acc_oaddr <= p_oaddr;
            end

            always @(posedge clk) begin
                if (rst) begin
                    p_valid   <= 1'b0;
                    acc_valid <= 1'b0;
                end else begin
                    p_valid   <= d_valid;
                    acc_valid <= p_valid && p_last;
                end
            end

        end else begin : g_kernel

            // ---- stage P: nine products, a kernel row at a time --------------
            // Row 0 multiplies in stage D. Rows 1 and 2 keep their pixels and
            // weights for one and two more cycles (the DSP slices' input
            // registers), so each row's products reach its adders in the same
            // cycle as the sum of the rows above.
            reg [47:0] x12, w12;        // rows 1 and 2, one cycle later
            reg [23:0] x2, w2;          // row 2, two cycles later

            always @(posedge clk) begin
                x12 <= win[71:24];
                w12 <= w_data[71:24];
                x2  <= x12[47:24];
                w2  <= w12[47:24];
            end

            // tap t = kr*3 + kc: its pixel and weight, with the delays above;
            // one multiplier and product register per tap, as in N_MAC = 1
            wire [71:0] xs = {x2, x12[23:0], win[23:0]};
            wire [71:0] ws = {w2, w12[23:0], w_data[23:0]};
            genvar t;
            for (t = 0; t < 9; t = t + 1) begin : g_mul
                (* use_dsp = "yes" *)
                reg signed [16:0] p;
                always @(posedge clk)
                    p <= $signed({1'b0, xs[8*t +: 8]}) * $signed(ws[8*t +: 8]);
            end
            // kernel column kc in bits 17*kc +: 17
            wire [50:0] q0 = {g_mul[2].p, g_mul[1].p, g_mul[0].p};  // row 0, in stage P
            wire [50:0] q1 = {g_mul[5].p, g_mul[4].p, g_mul[3].p};  // row 1, one cycle later
            wire [50:0] q2 = {g_mul[8].p, g_mul[7].p, g_mul[6].p};  // row 2, two cycles later

            // ---- rows 0, 1 and 2: the bias plus each row, one stage per row --
            reg                    r0_valid, r1_valid;
            reg [FM_ADDR_W-1:0]             r0_oaddr, r1_oaddr;
            reg signed [ACC_W-1:0] r1_sum, r2_sum;
            reg                    r1_ovf, r2_ovf;

            wire [ACC_W:0] row0 = row_add(b_data, q0);
            wire [ACC_W:0] row1 = row_add(r1_sum, q1);
            wire [ACC_W:0] row2 = row_add(r2_sum, q2);
            assign acc_ovf = r2_ovf || row2[ACC_W];

            always @(posedge clk) begin
                r0_oaddr  <= d_oaddr;
                r1_sum    <= row0[ACC_W-1:0];
                r1_ovf    <= row0[ACC_W];
                r1_oaddr  <= r0_oaddr;
                r2_sum    <= row1[ACC_W-1:0];
                r2_ovf    <= r1_ovf || row1[ACC_W];
                p_oaddr   <= r1_oaddr;
                if (p_valid)
                    acc <= row2[ACC_W-1:0];
                acc_oaddr <= p_oaddr;
            end

            always @(posedge clk) begin
                if (rst) begin
                    r0_valid  <= 1'b0;
                    r1_valid  <= 1'b0;
                    p_valid   <= 1'b0;
                    acc_valid <= 1'b0;
                end else begin
                    r0_valid  <= d_valid;
                    r1_valid  <= r0_valid;
                    p_valid   <= r1_valid;
                    acc_valid <= p_valid;
                end
            end

        end

    end
    endgenerate

    // ---- rescale and ReLU, then the fmap_ram write --------------------------
    wire        rq_valid;
    wire [FM_ADDR_W-1:0] rq_addr;

    requant_relu #(.M(M), .S(S), .ACC_W(ACC_W), .TAG_W(FM_ADDR_W)) u_rq (
        .clk       (clk),
        .rst       (rst),
        .in_valid  (acc_valid),
        .acc       (acc),
        .in_tag    (acc_oaddr),
        .out_valid (rq_valid),
        .q         (fm_data),
        .out_tag   (rq_addr)
    );

    assign fm_we   = rq_valid;
    assign fm_addr = rq_addr;

    // ---- handshake ---------------------------------------------------------
    wire last_write = rq_valid && (rq_addr == LAST_OUT);

    always @(posedge clk) begin
        if (rst) begin
            busy <= 1'b0;
            done <= 1'b0;
            ovf  <= 1'b0;
        end else begin
            done <= last_write;

            if (go)
                busy <= 1'b1;
            else if (last_write)
                busy <= 1'b0;

            if (go)
                ovf <= 1'b0;
            else if (p_valid && acc_ovf)
                ovf <= 1'b1;
        end
    end

endmodule

`default_nettype wire
