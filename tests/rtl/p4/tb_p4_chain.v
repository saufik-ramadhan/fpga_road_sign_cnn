// tb_p4_chain.v : rantai subsistem P4 untuk satu vektor
//   fmap_ram --(maxpool)--> pool_ram --(fc_engine)--> 8 skor --(argmax di testbench)--> class
//
// File yang dibaca dari folder kerja (nama sama dengan folder vectors/<nama>/ milik P2):
//   activation.mem   1568 baris, 8 bit   masukan maxpool (keluaran requant_relu)
//   pool.mem          392 baris, 8 bit   keluaran maxpool yang diharapkan
//   scores.mem          8 baris, 32 bit  skor yang diharapkan
//   prediction.mem      1 baris, 8 bit   class yang diharapkan
//   fc_weight.mem, fc_bias.mem           parameter FC
//
// Urutan, seperti yang nanti dilakukan controller (P1): start maxpool -> done -> start fc_engine -> done.
`timescale 1ns/1ps

module tb_p4_chain;
    parameter NF    = 8;
    parameter IN_W  = 14;   // peta konvolusi (input 16x16 -> 14)
    parameter FA_W  = 11;
    parameter PA_W  = 9;
    parameter WA_W  = 12;

    localparam OUT_W  = IN_W / 2;
    localparam FMAP_N = NF * IN_W * IN_W;
    localparam POOL_N = NF * OUT_W * OUT_W;
    localparam N_CLS  = 8;
    localparam ACC_W  = 32;
    localparam LIM_MP = 4 * POOL_N + 1000;
    localparam LIM_FC = 2 * N_CLS * POOL_N + 1000;

    reg clk = 1'b0, rst = 1'b1, mp_start = 1'b0, fc_start = 1'b0;
    wire mp_busy, mp_done, fc_busy, fc_done;

    wire [FA_W-1:0] fmap_addr;   reg  [7:0] fmap_dout;
    wire [PA_W-1:0] pool_waddr;  wire [7:0] pool_din;  wire pool_we;
    wire [PA_W-1:0] pool_raddr;  reg  [7:0] pool_dout;
    wire [WA_W-1:0] wgt_raddr;   reg  signed [7:0] wgt_dout;
    reg  [N_CLS*ACC_W-1:0] bias_flat;
    wire [N_CLS*ACC_W-1:0] scores_flat;

    reg [7:0]  fmap_mem [0:FMAP_N-1];
    reg [7:0]  pool_mem [0:POOL_N-1];
    reg [7:0]  pool_exp [0:POOL_N-1];
    reg [7:0]  wgt_mem  [0:N_CLS*POOL_N-1];
    reg [31:0] bias_mem [0:N_CLS-1];
    reg [31:0] sc_exp   [0:N_CLS-1];
    reg [7:0]  pred_exp [0:0];

    maxpool #(.NF(NF), .IN_W(IN_W), .FA_W(FA_W), .PA_W(PA_W)) u_mp (
        .clk(clk), .rst(rst), .start(mp_start), .busy(mp_busy), .done(mp_done),
        .fmap_addr(fmap_addr), .fmap_dout(fmap_dout),
        .pool_addr(pool_waddr), .pool_din(pool_din), .pool_we(pool_we));

    fc_engine #(.N_IN(POOL_N), .N_CLS(N_CLS), .IA_W(PA_W), .WA_W(WA_W), .CLS_W(3),
                .WGT_BASE(0), .ACC_W(ACC_W)) u_fc (
        .clk(clk), .rst(rst), .start(fc_start), .busy(fc_busy), .done(fc_done),
        .pool_raddr(pool_raddr), .pool_dout(pool_dout),
        .wgt_raddr(wgt_raddr),   .wgt_dout(wgt_dout),
        .bias_flat(bias_flat),   .scores_flat(scores_flat));

    // argmax asli (kombinasional): membaca scores_flat, keluarkan class terpilih
    wire [2:0] class_out;
    argmax #(.N_CLS(N_CLS), .ACC_W(ACC_W), .CLS_W(3)) u_arg (
        .scores_flat(scores_flat), .class_out(class_out));

    always #5 clk = ~clk;   // 100 MHz

    // semua memori: baca sinkron dengan latensi tepat 1 clock; pool_ram ditulis maxpool, dibaca fc_engine
    always @(posedge clk) begin
        fmap_dout <= fmap_mem[fmap_addr];
        if (pool_we) pool_mem[pool_waddr] <= pool_din;
        pool_dout <= pool_mem[pool_raddr];
        wgt_dout  <= wgt_mem[wgt_raddr];
    end

    integer clk_count;
    initial clk_count = 0;
    always @(posedge clk) clk_count <= clk_count + 1;

    integer i, j, errors, pool_err, score_err, cycles, t_start, best_idx;
    reg [31:0] got, best;

    initial begin
        $readmemh("activation.mem", fmap_mem);
        $readmemh("pool.mem", pool_exp);
        $readmemh("fc_weight.mem", wgt_mem);
        $readmemh("fc_bias.mem", bias_mem);
        $readmemh("scores.mem", sc_exp);
        $readmemh("prediction.mem", pred_exp);
        for (i = 0; i < POOL_N; i = i + 1) pool_mem[i] = 8'hxx;
        for (j = 0; j < N_CLS; j = j + 1) bias_flat[j*ACC_W +: ACC_W] = bias_mem[j];

        errors = 0; pool_err = 0; score_err = 0;
        repeat (4) @(posedge clk); rst <= 1'b0;
        repeat (2) @(posedge clk);

        // ---- fase 1: maxpool ----
        t_start = clk_count;
        @(posedge clk); mp_start <= 1'b1;
        @(posedge clk); mp_start <= 1'b0;
        cycles = 0;
        while (!mp_done && cycles < LIM_MP) begin @(posedge clk); cycles = cycles + 1; end
        if (cycles >= LIM_MP) begin $display("FAIL: maxpool timeout"); errors = errors + 1; end
        repeat (3) @(posedge clk);
        for (i = 0; i < POOL_N; i = i + 1)
            if (pool_mem[i] !== pool_exp[i]) begin
                if (pool_err == 0)
                    $display("FAIL: pool indeks %0d (f=%0d r=%0d c=%0d): dapat %h, harusnya %h",
                             i, i/(OUT_W*OUT_W), (i%(OUT_W*OUT_W))/OUT_W, i%OUT_W, pool_mem[i], pool_exp[i]);
                pool_err = pool_err + 1;
            end

        // ---- fase 2: fc_engine ----
        @(posedge clk); fc_start <= 1'b1;
        @(posedge clk); fc_start <= 1'b0;
        cycles = 0;
        while (!fc_done && cycles < LIM_FC) begin @(posedge clk); cycles = cycles + 1; end
        if (cycles >= LIM_FC) begin $display("FAIL: fc_engine timeout"); errors = errors + 1; end
        repeat (3) @(posedge clk);
        for (j = 0; j < N_CLS; j = j + 1) begin
            got = scores_flat[j*ACC_W +: ACC_W];
            if (got !== sc_exp[j]) begin
                $display("FAIL: skor class %0d: dapat %0d, harusnya %0d", j, $signed(got), $signed(sc_exp[j]));
                score_err = score_err + 1;
            end
        end

        // ---- argmax: keluaran modul argmax.v dibandingkan dengan prediction.mem ----
        best_idx = class_out;
        if (class_out != pred_exp[0]) begin
            $display("FAIL: argmax = %0d, harusnya %0d", class_out, pred_exp[0]);
            errors = errors + 1;
        end

        errors = errors + pool_err + score_err;
        if (errors == 0)
            $display("PASS: pool %0d/%0d byte, skor %0d/%0d, argmax = %0d, %0d clock dari start maxpool sampai done fc",
                     POOL_N, POOL_N, N_CLS, N_CLS, best_idx, clk_count - t_start);
        else
            $display("FAIL: %0d kesalahan (pool %0d, skor %0d)", errors, pool_err, score_err);
        $finish;
    end
endmodule