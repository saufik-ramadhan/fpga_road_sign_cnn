/*
Aturan interface: 
-- start : pulsa 1 clock. Diabaikan kalau busy. 
-- done  : pulsa 1 clock, saat semua 392 byte sudah tertulis di pool_ram.
-- fmap_dout valid TEPAT 1 clock setelah fmap_addr (BRAM tanpa output register).
-- bit valid (rd_valid) berjalan satu clock di belakang alamat.

Urutan baca tiap jendela 2x2 (k = 0..3):
k=0 -> (2r  , 2c  )   k=1 -> (2r  , 2c+1)
k=2 -> (2r+1, 2c  )   k=3 -> (2r+1, 2c+1)

maxpool.v : max-pool 2x2 stride 2, diparameterkan.
IN_W = lebar/tinggi feature map setelah konvolusi (16x16 -> 14, 32x32 -> 30)
fmap_ram : alamat = f*IN_W*IN_W + row*IN_W + col
pool_ram : alamat = f*OUT_W*OUT_W + r*OUT_W + c      (OUT_W = IN_W/2)
*/

// maxpool.v : max-pool 2x2 stride 2, diparameterkan.
//   IN_W = lebar/tinggi feature map setelah konvolusi (16x16 -> 14, 32x32 -> 30)
//   fmap_ram : alamat = f*IN_W*IN_W + row*IN_W + col
//   pool_ram : alamat = f*OUT_W*OUT_W + r*OUT_W + c      (OUT_W = IN_W/2)
module maxpool #(
    parameter NF   = 8,
    parameter IN_W = 14,
    parameter FA_W = 11,   // lebar alamat fmap_ram  (11 untuk IN_W=14, 13 untuk IN_W=30)
    parameter PA_W = 9    // lebar alamat pool_ram  (9 untuk IN_W=14, 11 untuk IN_W=30)
) (
    input  wire            clk,
    input  wire            rst,
    input  wire            start,
    output reg             busy,
    output reg             done,
    output wire [FA_W-1:0] fmap_addr,
    input  wire [7:0]      fmap_dout,
    output reg  [PA_W-1:0] pool_addr,
    output reg  [7:0]      pool_din,
    output reg             pool_we
);
    localparam OUT_W   = IN_W / 2;
    localparam FMAP_SZ = IN_W * IN_W;
    localparam POOL_SZ = OUT_W * OUT_W;

    reg [2:0] f;
    reg [3:0] r;
    reg [3:0] c;
    reg [1:0] k;
    reg       issuing;

    wire [4:0] in_row = {r, 1'b0} + k[1];
    wire [4:0] in_col = {c, 1'b0} + k[0];

    assign fmap_addr = f * FMAP_SZ + in_row * IN_W + in_col;
    wire [PA_W-1:0] out_addr = f * POOL_SZ + r * OUT_W + c;
    wire last_read = (f == NF-1) && (r == OUT_W-1) && (c == OUT_W-1) && (k == 2'd3);

    reg             rd_valid;
    reg [1:0]       rd_k;
    reg [PA_W-1:0]  rd_addr;
    reg             rd_last;
    reg [7:0]       cur_max;
    reg             fin;

    always @(posedge clk) begin
        if (rst) begin
            busy <= 1'b0; done <= 1'b0; issuing <= 1'b0; rd_valid <= 1'b0;
            pool_we <= 1'b0; fin <= 1'b0;
            f <= 3'd0; r <= 4'd0; c <= 4'd0; k <= 2'd0;
        end else begin
            done <= 1'b0; pool_we <= 1'b0; fin <= 1'b0; rd_valid <= 1'b0;

            if (start && !busy) begin
                busy <= 1'b1; issuing <= 1'b1;
                f <= 3'd0; r <= 4'd0; c <= 4'd0; k <= 2'd0;
            end

            if (issuing) begin
                rd_valid <= 1'b1;
                rd_k     <= k;
                rd_addr  <= out_addr;
                rd_last  <= last_read;
                if (k == 2'd3) begin
                    k <= 2'd0;
                    if (c == OUT_W-1) begin
                        c <= 4'd0;
                        if (r == OUT_W-1) begin
                            r <= 4'd0;
                            if (f == NF-1) issuing <= 1'b0;
                            else           f <= f + 3'd1;
                        end else r <= r + 4'd1;
                    end else c <= c + 4'd1;
                end else k <= k + 2'd1;
            end

            if (rd_valid) begin
                if (rd_k == 2'd0)             cur_max <= fmap_dout;
                else if (fmap_dout > cur_max) cur_max <= fmap_dout;
                if (rd_k == 2'd3) begin
                    pool_we   <= 1'b1;
                    pool_addr <= rd_addr;
                    pool_din  <= (fmap_dout > cur_max) ? fmap_dout : cur_max;
                    if (rd_last) fin <= 1'b1;
                end
            end

            if (fin) begin done <= 1'b1; busy <= 1'b0; end
        end
    end
endmodule