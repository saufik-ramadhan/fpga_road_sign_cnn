// tb_fc_engine.v : testbench fc_engine
// Butuh di folder tempat vvp dijalankan:
//   pool.mem       392 baris, 8 bit  (keluaran pool)
//   fc_weight.mem  3136 baris, 8 bit (bobot FC, [class, indeks CHW])
//   fc_bias.mem    8 baris, 32 bit
//   scores.mem     8 baris, 32 bit   (skor yang diharapkan dari golden model)
// Tiga uji dalam satu simulasi: jalan 1, jalan 2 dengan start palsu saat busy, jalan ulang.
`timescale 1ns/1ps

module tb_fc_engine;
    parameter N_IN     = 392;
    parameter N_CLS    = 8;
    parameter IA_W     = 9;
    parameter WA_W     = 12;
    parameter CLS_W    = 3;
    parameter WGT_BASE = 0;
    parameter ACC_W    = 32;

    localparam W_N   = N_CLS * N_IN;
    localparam LIMIT = 2 * W_N + 1000;

    reg clk = 1'b0, rst = 1'b1, start = 1'b0;
    wire busy, done;
    wire [IA_W-1:0] pool_raddr;
    reg  [7:0]      pool_dout;
    wire [WA_W-1:0] wgt_raddr;
    reg  signed [7:0] wgt_dout;
    reg  [N_CLS*ACC_W-1:0] bias_flat;
    wire [N_CLS*ACC_W-1:0] scores_flat;

    reg [7:0]  pool_mem [0:N_IN-1];
    reg [7:0]  wgt_mem  [0:WGT_BASE+W_N-1];
    reg [31:0] bias_mem [0:N_CLS-1];
    reg [31:0] exp_mem  [0:N_CLS-1];

    fc_engine #(.N_IN(N_IN), .N_CLS(N_CLS), .IA_W(IA_W), .WA_W(WA_W), .CLS_W(CLS_W),
                .WGT_BASE(WGT_BASE), .ACC_W(ACC_W)) dut (
        .clk(clk), .rst(rst), .start(start), .busy(busy), .done(done),
        .pool_raddr(pool_raddr), .pool_dout(pool_dout),
        .wgt_raddr(wgt_raddr),   .wgt_dout(wgt_dout),
        .bias_flat(bias_flat),   .scores_flat(scores_flat));

    always #5 clk = ~clk;   // 100 MHz

    // memori baca sinkron, latensi tepat 1 clock (seperti BRAM tanpa output register)
    always @(posedge clk) begin
        pool_dout <= pool_mem[pool_raddr];
        wgt_dout  <= wgt_mem[wgt_raddr];
    end

    integer done_count;
    initial done_count = 0;
    always @(posedge clk) if (done) done_count <= done_count + 1;

    integer j, errors, cycles, first_cycles, done_before;
    reg [31:0] got;

    task run_once;
        input integer poke_at;   // clock ke-n setelah start: kirim start palsu (0 = tidak)
        begin
            done_before = done_count;
            @(posedge clk); start <= 1'b1;
            @(posedge clk); start <= 1'b0;
            cycles = 0;
            while (!done && cycles < LIMIT) begin
                @(posedge clk);
                cycles = cycles + 1;
                if (poke_at != 0 && cycles == poke_at) start <= 1'b1;
                else                                   start <= 1'b0;
            end
            repeat (3) @(posedge clk);
            if (cycles >= LIMIT) begin
                $display("FAIL: timeout, done tidak pernah naik"); errors = errors + 1;
            end
            if (done_count - done_before != 1) begin
                $display("FAIL: jumlah pulsa done = %0d (harusnya 1)", done_count - done_before);
                errors = errors + 1;
            end
            if (busy !== 1'b0) begin
                $display("FAIL: busy masih 1 setelah done"); errors = errors + 1;
            end
        end
    endtask

    task check_scores;
        input integer run_id;
        begin
            for (j = 0; j < N_CLS; j = j + 1) begin
                got = scores_flat[j*ACC_W +: ACC_W];
                if (got !== exp_mem[j]) begin
                    $display("FAIL: jalan %0d, class %0d: dapat %0d, harusnya %0d",
                             run_id, j, $signed(got), $signed(exp_mem[j]));
                    errors = errors + 1;
                end
            end
        end
    endtask

    initial begin
        $readmemh("pool_expected.mem", pool_mem);
        for (j = 0; j < WGT_BASE; j = j + 1) wgt_mem[j] = 8'h7f;   // isi sampah: alamat salah akan ketahuan
        $readmemh("fc_weight.mem", wgt_mem, WGT_BASE);
        $readmemh("fc_bias.mem", bias_mem);
        $readmemh("scores.mem", exp_mem);
        for (j = 0; j < N_CLS; j = j + 1) bias_flat[j*ACC_W +: ACC_W] = bias_mem[j];

        errors = 0;
        repeat (4) @(posedge clk); rst <= 1'b0;
        repeat (2) @(posedge clk);

        run_once(0);   check_scores(1); first_cycles = cycles;
        repeat (10) @(posedge clk);

        run_once(300); check_scores(2);      // start palsu di tengah proses harus diabaikan
        if (cycles != first_cycles) begin
            $display("FAIL: start saat busy mengubah durasi (%0d vs %0d)", cycles, first_cycles);
            errors = errors + 1;
        end
        repeat (10) @(posedge clk);

        run_once(0);   check_scores(3);      // pakai ulang tanpa reset

        if (errors == 0)
            $display("PASS: %0d/%0d skor cocok, %0d clock per jalan",
                     N_CLS, N_CLS, first_cycles);
        else
            $display("FAIL: %0d kesalahan", errors);
        $finish;
    end
endmodule