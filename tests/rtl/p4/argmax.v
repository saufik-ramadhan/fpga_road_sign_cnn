module argmax #(
    parameter N_CLS = 8,
    parameter ACC_W = 32,
    parameter CLS_W = 3
)(
    input  wire [N_CLS*ACC_W-1:0] scores_flat, // Masukan 8 skor (int32) dari fc_engine
    output reg  [CLS_W-1:0]       class_out    // Kelas terpilih (0 s.d 7)
);

    integer i;
    reg signed [ACC_W-1:0] max_score;
    reg [CLS_W-1:0]       best_class;

    always @(*) begin
        // Inisialisasi dengan kelas pertama (0)
        max_score  = scores_flat[0*ACC_W +: ACC_W];
        best_class = 3'd0;

        // Bandingkan dengan kelas-kelas berikutnya (1 sampai 7)
        for (i = 1; i < N_CLS; i = i + 1) begin
            // Menggunakan tanda operator < agar jika ada skor yang SAMA (tie),
            // kelas dengan indeks lebih rendah yang dipilih (tidak menimpa max_score).
            if ($signed(scores_flat[i*ACC_W +: ACC_W]) > max_score) begin
                max_score  = scores_flat[i*ACC_W +: ACC_W];
                best_class = i[CLS_W-1:0];
            end
        end

        class_out = best_class;
    end

endmodule