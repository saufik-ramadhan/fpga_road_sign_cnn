// fc_engine.v : lapisan fully connected, mengikuti kontrak P2 (p2-int-v1)
//
//   score[j] = bias[j] + SUM_{i=0}^{N_IN-1} pool[i] * weight[j*N_IN + i]     j = 0..N_CLS-1
//
//   pool   : uint8 (0..127) dari pool_ram, alamat i = (channel*7 + row)*7 + col  (0..391)
//   weight : int8 (-127..127) dari ROM, dibaca berurutan, alamat = WGT_BASE + j*N_IN + i
//   bias   : int32, bias[j] = bias_flat[j*ACC_W +: ACC_W]   (isi fc_bias.mem)
//   skor   : int32 bertanda, TIDAK di-rescale. Skor j = scores_flat[j*ACC_W +: ACC_W]
//
// Aturan antarmuka:
//   - start : pulsa 1 clock. Diabaikan kalau busy.
//   - done  : pulsa 1 clock. Saat done=1, seluruh skor sudah sah di scores_flat
//             dan bertahan sampai jalan berikutnya menimpanya.
//   - pool_dout dan wgt_dout sah TEPAT 1 clock setelah alamatnya (BRAM tanpa output register).
//
// Pipeline (satu suku per clock, tanpa jeda antar class):
//   A: alamat keluar (i, wcnt)                 -> memori menjawab 1 clock kemudian
//   D: pool_dout, wgt_dout tiba   -> kalikan, simpan di prod; bias dipilih ke bias_r
//   C: acc <= (suku pertama ? bias : acc) + prod; pada suku terakhir skor ditulis
// Setiap suku membawa label (valid, first, last, cls) yang berjalan satu tahap di belakang.
//
// Untuk 16x16: N_IN=392, IA_W=9,  WA_W=12.   Untuk 32x32: N_IN=1800, IA_W=11, WA_W=14.

module fc_engine #(
    parameter N_IN     = 392,   // input per class (8 filter x 7 x 7)
    parameter N_CLS    = 8,
    parameter IA_W     = 9,     // lebar alamat pool_ram
    parameter WA_W     = 12,    // lebar alamat ROM bobot
    parameter CLS_W    = 3,     // lebar counter class
    parameter WGT_BASE = 0,     // alamat awal bobot FC di ROM (mis. 72 kalau digabung bobot konvolusi)
    parameter ACC_W    = 32     // lebar akumulator dan skor (kontrak: int32)
) (
    input  wire                    clk,
    input  wire                    rst,        // reset sinkron, aktif tinggi
    input  wire                    start,
    output reg                     busy,
    output reg                     done,

    output wire [IA_W-1:0]         pool_raddr,
    input  wire [7:0]              pool_dout,  // unsigned
    output wire [WA_W-1:0]         wgt_raddr,
    input  wire signed [7:0]       wgt_dout,   // bertanda

    input  wire [N_CLS*ACC_W-1:0]  bias_flat,
    output wire [N_CLS*ACC_W-1:0]  scores_flat
);

    initial begin
        if ((1 << IA_W)  < N_IN)                $display("fc_engine ERROR: IA_W terlalu kecil untuk N_IN");
        if ((1 << WA_W)  < WGT_BASE + N_CLS*N_IN) $display("fc_engine ERROR: WA_W terlalu kecil untuk bobot");
        if ((1 << CLS_W) < N_CLS)               $display("fc_engine ERROR: CLS_W terlalu kecil untuk N_CLS");
    end

    // ---------------- tahap A: pembangkit alamat ----------------
    reg [IA_W-1:0]  i;        // indeks input 0..N_IN-1 (alamat pool_ram)
    reg [CLS_W-1:0] cls;      // class 0..N_CLS-1
    reg [WA_W-1:0]  wcnt;     // penghitung bobot: naik 1 tiap clock, tanpa perkalian
    reg             issuing;

    assign pool_raddr = i;
    assign wgt_raddr  = WGT_BASE + wcnt;

    // ---------------- label dan register pipeline ----------------
    reg                     d1_valid, d1_first, d1_last;    // sejajar dengan data dari memori
    reg [CLS_W-1:0]         d1_cls;

    reg                     d2_valid, d2_first, d2_last;    // sejajar dengan prod
    reg [CLS_W-1:0]         d2_cls;
    reg signed [16:0]       prod;                           // 9-bit bertanda x 8-bit bertanda
    reg signed [ACC_W-1:0]  bias_r;
    reg signed [ACC_W-1:0]  acc;
    reg [N_CLS*ACC_W-1:0]   scores_r;

    wire signed [8:0]       a_s      = {1'b0, pool_dout};   // pool jadi bertanda: nol di depan
    wire signed [ACC_W-1:0] acc_base = d2_first ? bias_r : acc;
    wire signed [ACC_W-1:0] acc_next = acc_base + prod;

    assign scores_flat = scores_r;

    always @(posedge clk) begin
        if (rst) begin
            busy <= 1'b0; done <= 1'b0; issuing <= 1'b0;
            d1_valid <= 1'b0; d2_valid <= 1'b0;
            i <= {IA_W{1'b0}}; cls <= {CLS_W{1'b0}}; wcnt <= {WA_W{1'b0}};
            acc <= {ACC_W{1'b0}}; scores_r <= {(N_CLS*ACC_W){1'b0}};
        end else begin
            done     <= 1'b0;
            d1_valid <= 1'b0;

            if (start && !busy) begin
                busy <= 1'b1; issuing <= 1'b1;
                i <= {IA_W{1'b0}}; cls <= {CLS_W{1'b0}}; wcnt <= {WA_W{1'b0}};
            end

            // tahap A: keluarkan alamat, catat label untuk tahap berikutnya
            if (issuing) begin
                d1_valid <= 1'b1;
                d1_first <= (i == 0);
                d1_last  <= (i == N_IN-1);
                d1_cls   <= cls;
                wcnt     <= wcnt + 1'b1;
                if (i == N_IN-1) begin
                    i <= {IA_W{1'b0}};
                    if (cls == N_CLS-1) issuing <= 1'b0;
                    else                cls <= cls + 1'b1;
                end else i <= i + 1'b1;
            end

            // tahap D: data tiba, kalikan
            d2_valid <= d1_valid;
            d2_first <= d1_first;
            d2_last  <= d1_last;
            d2_cls   <= d1_cls;
            prod     <= a_s * wgt_dout;
            bias_r   <= bias_flat[d1_cls*ACC_W +: ACC_W];

            // tahap C: akumulasi
            if (d2_valid) begin
                acc <= acc_next;
                if (d2_last) begin
                    scores_r[d2_cls*ACC_W +: ACC_W] <= acc_next;
                    if (d2_cls == N_CLS-1) begin
                        done <= 1'b1;
                        busy <= 1'b0;
                    end
                end
            end
        end
    end

endmodule