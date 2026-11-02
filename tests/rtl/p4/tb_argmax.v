`timescale 1ns/1ps

module tb_argmax;

    parameter N_CLS = 8;
    parameter ACC_W = 32;
    parameter CLS_W = 3;

    // Sinyal Testbench
    reg  [N_CLS*ACC_W-1:0] scores_flat;
    wire [CLS_W-1:0]       class_out;

    // Instansiasi Device Under Test (DUT)
    argmax #(
        .N_CLS(N_CLS),
        .ACC_W(ACC_W),
        .CLS_W(CLS_W)
    ) dut (
        .scores_flat(scores_flat),
        .class_out(class_out)
    );

    integer errors;
    integer j;

    initial begin
        errors = 0;

        // Uji Kasus 1: Skor tertinggi berada di kelas tengah (misal: kelas 3)
        // Set semua skor ke nilai kecil, lalu berikan nilai besar di kelas 3
        for (j = 0; j < N_CLS; j = j + 1) begin
            scores_flat[j*ACC_W +: ACC_W] = 32'sd10;
        end
        scores_flat[3*ACC_W +: ACC_W] = 32'sd500; // Tertinggi
        
        #10;
        if (class_out !== 3'd3) begin
            $display("FAIL: Kasus 1 - Harusnya kelas 3, tetapi mendapat kelas %0d", class_out);
            errors = errors + 1;
        end else begin
            $display("PASS: Kasus 1 (Skor tertinggi di kelas 3) -> Terpilih kelas %0d", class_out);
        end

        // Uji Kasus 2: Aturan Tie-Breaker (Skor sama besar di beberapa kelas)
        // Berikan skor sama besar (misal 999) pada kelas 2 dan kelas 5. 
        // Sesuai aturan, kelas dengan indeks lebih rendah (kelas 2) harus menang.
        for (j = 0; j < N_CLS; j = j + 1) begin
            scores_flat[j*ACC_W +: ACC_W] = 32'sd0;
        end
        scores_flat[2*ACC_W +: ACC_W] = 32'sd999;
        scores_flat[5*ACC_W +: ACC_W] = 32'sd999; // Seri dengan kelas 2

        #10;
        if (class_out !== 3'd2) begin
            $display("FAIL: Kasus 2 (Tie-breaker) - Harusnya kelas 2 yang menang, tetapi mendapat kelas %0d", class_out);
            errors = errors + 1;
        end else begin
            $display("PASS: Kasus 2 (Tie-breaker antara kelas 2 & 5) -> Terpilih kelas %0d (Indeks lebih rendah)", class_out);
        end

        // Uji Kasus 3: Skor bernilai negatif semua, cari yang paling tinggi (mendekati 0 / paling kecil negatifnya)
        scores_flat[0*ACC_W +: ACC_W] = -32'sd150;
        scores_flat[1*ACC_W +: ACC_W] = -32'sd50;  // Tertinggi (paling tidak negatif)
        scores_flat[2*ACC_W +: ACC_W] = -32'sd300;
        scores_flat[3*ACC_W +: ACC_W] = -32'sd100;
        scores_flat[4*ACC_W +: ACC_W] = -32'sd500;
        scores_flat[5*ACC_W +: ACC_W] = -32'sd200;
        scores_flat[6*ACC_W +: ACC_W] = -32'sd80;
        scores_flat[7*ACC_W +: ACC_W] = -32'sd120;

        #10;
        if (class_out !== 3'd1) begin
            $display("FAIL: Kasus 3 (Skor negatif) - Harusnya kelas 1, tetapi mendapat kelas %0d", class_out);
            errors = errors + 1;
        end else begin
            $display("PASS: Kasus 3 (Skor negatif) -> Terpilih kelas %0d", class_out);
        end

        // Ringkasan Pengujian
        if (errors == 0) begin
            $display("\nSELESAI: SEMUA PENGUJIAN ARGMAX BERHASIL (PASS)!");
        end else begin
            $display("\nSELESAI: Terdapat %0d kesalahan.", errors);
        end

        $finish;
    end

endmodule