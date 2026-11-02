`timescale 1ns / 1ps
`default_nettype none

// conv_engine: the 3x3 convolution layer (8 filters, no padding) with its
// rescale and ReLU. Reads the 16x16 input image and writes the 14x14x8 = 1,568
// activations (0..127) into fmap_ram.
//
// One multiply-accumulate per clock cycle. Taps are issued in the order
// filter, output row, output column, kernel row, kernel column, so every
// output takes exactly 9 cycles and the pipeline never stalls: a run takes
// 1,568 x 9 = 14,112 cycles plus the pipeline depth.
//
//   stage A  counters drive pix_addr and the weight address
//   stage D  pixel and weight arrive (both memories take one cycle)
//   stage P  product register (the multiplier register in the DSP slice)
//   stage C  accumulator: the filter's bias plus 9 products, 24 bits
//   then requant_relu (2 stages) and the fmap_ram write
//
// Handshake: a 1-cycle start pulse while idle begins a run; start is ignored
// while busy. done is a 1-cycle pulse in the cycle after the last fmap_ram
// write, and busy falls with it. ovf is set if any accumulator step leaves
// the 24-bit range, and stays set until the next start.

module conv_engine #(
    parameter [15:0]     M           = 16'd1,       // CONV_M from params.vh
    parameter            S           = 1,           // CONV_S from params.vh
    parameter [8*24-1:0] BIAS        = {8{24'd0}},  // CONV_BIAS: filter f in [24*f +: 24]
    parameter            WEIGHT_FILE = "conv_weights.mem"
) (
    input  wire        clk,
    input  wire        rst,        // synchronous, active high
    input  wire        start,
    output reg         busy,
    output reg         done,
    output reg         ovf,
    // input image, through input_mux: pix_data arrives one cycle after pix_addr
    output wire        pix_rd,
    output wire [7:0]  pix_addr,   // row*16 + col
    input  wire [7:0]  pix_data,   // unsigned, 0..255
    // fmap_ram write port
    output wire        fm_we,
    output wire [10:0] fm_addr,    // filter*196 + row*14 + col
    output wire [7:0]  fm_data     // 0..127
);

    localparam [10:0] LAST_OUT = 11'd1567;

    wire go = start && !busy;

    // ---- stage A: tap counters ---------------------------------------------
    reg        run;                 // issuing taps
    reg [2:0]  f;
    reg [3:0]  r, c;                // output row and column, 0..13
    reg [1:0]  kr, kc;              // kernel row and column, 0..2
    reg [10:0] oaddr;               // f*196 + r*14 + c, counts 0..1567

    wire tap_first = (kr == 2'd0) && (kc == 2'd0);
    wire tap_last  = (kr == 2'd2) && (kc == 2'd2);

    wire [3:0] pix_row = r + {2'b00, kr};
    wire [3:0] pix_col = c + {2'b00, kc};
    assign pix_addr = {pix_row, pix_col};
    assign pix_rd   = run;

    wire [6:0] w_addr = f * 7'd9 + kr * 7'd3 + kc;

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
            if (kc != 2'd2) begin
                kc <= kc + 2'd1;
            end else begin
                kc <= 2'd0;
                if (kr != 2'd2) begin
                    kr <= kr + 2'd1;
                end else begin
                    kr    <= 2'd0;
                    oaddr <= oaddr + 11'd1;
                    if (c != 4'd13) begin
                        c <= c + 4'd1;
                    end else begin
                        c <= 4'd0;
                        if (r != 4'd13) begin
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

    // ---- stage D: memory outputs -------------------------------------------
    wire signed [7:0] w_data;

    conv_wrom #(.INIT_FILE(WEIGHT_FILE)) u_wrom (
        .clk  (clk),
        .addr (w_addr),
        .dout (w_data)
    );

    reg        d_valid, d_first, d_last;
    reg [2:0]  d_f;
    reg [10:0] d_oaddr;

    always @(posedge clk) begin
        d_first <= tap_first;
        d_last  <= tap_last;
        d_f     <= f;
        d_oaddr <= oaddr;
    end

    // ---- stage P: product, 0..255 times -127..127 --------------------------
    // use_dsp: left alone, Vivado builds this small multiply from LUTs, and it
    // becomes the slowest path once pix_data comes from a block RAM. In a DSP
    // slice the whole multiply-accumulate fits in one DSP48E1.
    (* use_dsp = "yes" *)
    reg signed [16:0] p;
    reg               p_valid, p_first, p_last;
    reg [2:0]         p_f;
    reg [10:0]        p_oaddr;

    always @(posedge clk) begin
        p       <= $signed({1'b0, pix_data}) * w_data;
        p_first <= d_first;
        p_last  <= d_last;
        p_f     <= d_f;
        p_oaddr <= d_oaddr;
    end

    // ---- stage C: accumulator ----------------------------------------------
    wire signed [23:0] bias_of [0:7];

    genvar gi;
    generate
        for (gi = 0; gi < 8; gi = gi + 1) begin : g_bias
            assign bias_of[gi] = BIAS[24*gi +: 24];
        end
    endgenerate

    reg signed [23:0] acc;
    reg               acc_valid;    // acc holds a finished output
    reg [10:0]        acc_oaddr;

    wire signed [23:0] acc_base = p_first ? bias_of[p_f] : acc;
    wire signed [24:0] acc_sum  = acc_base + p;
    wire               acc_ovf  = acc_sum[24] != acc_sum[23];

    always @(posedge clk) begin
        if (p_valid)
            acc <= acc_sum[23:0];
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

    // ---- rescale and ReLU, then the fmap_ram write --------------------------
    wire        rq_valid;
    wire [10:0] rq_addr;

    requant_relu #(.M(M), .S(S), .TAG_W(11)) u_rq (
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
