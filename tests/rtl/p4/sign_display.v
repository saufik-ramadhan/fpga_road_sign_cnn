/*
sign_display.v: Modul display 7-seg + LED untuk klasifikasi rambu lalu lintas 
Input : clk, rst, class_in[2:0] indeks kelas dari argmax, dan valid 
Output: 7-seg [6:0], an[3:0], dan led [7:0]
// Mapping kelas:
0 = Speed 30  ->  "  30"     4 = Stop      -> "StOP"
1 = Speed 50  ->  "  50"     5 = No entry   -> "noE "
2 = Priority  ->  "PrIo"     6 = Caution    -> "CAUt"
3 = Yield     ->  " yLd"     7 = Keep right -> "rIGt"
Refresh rate: 100 MHz / 2^17 ≈ 763 Hz per digit (3 kHz total), cukup untuk
mata manusia melihat display stabil tanpa kedip
*/ 

`timescale 1ns/1ps
 
module sign_display (
    input  wire        clk,
    input  wire        rst,       
    input  wire [2:0]  class_in,
    input  wire        valid,
    output reg  [6:0]  seg,       // aktif-LOW, {g,f,e,d,c,b,a}
    output reg  [3:0]  an,        // aktif-LOW
    output reg  [7:0]  led        // aktif-HIGH
);
 
    // =========================================================================
    // 1) Refresh counter — 2 bit atas memilih digit aktif (~763 Hz/digit)
    // =========================================================================
    reg [16:0] refresh_cnt;
    wire [1:0] digit_sel = refresh_cnt[16:15];
 
    always @(posedge clk or posedge rst)
        if (rst) refresh_cnt <= 17'd0;
        else     refresh_cnt <= refresh_cnt + 1'b1;
 
    // =========================================================================
    // 2) Character ROM: class_in x digit -> kode karakter
    // =========================================================================
    localparam CH_0   = 5'd0;   // 0 / O
    localparam CH_3   = 5'd1;   // 3
    localparam CH_5S  = 5'd2;   // 5 / S (sama)
    localparam CH_P   = 5'd3;   // P
    localparam CH_r   = 5'd4;   // r (kecil)
    localparam CH_I   = 5'd5;   // I
    localparam CH_o   = 5'd6;   // o (kecil)
    localparam CH_y   = 5'd7;   // y
    localparam CH_L   = 5'd8;   // L
    localparam CH_d   = 5'd9;   // d (kecil)
    localparam CH_t   = 5'd10;  // t (kecil)
    localparam CH_n   = 5'd11;  // n (kecil)
    localparam CH_E   = 5'd12;  // E
    localparam CH_C   = 5'd13;  // C
    localparam CH_A   = 5'd14;  // A
    localparam CH_U   = 5'd15;  // U
    localparam CH_G   = 5'd16;  // G
    localparam CH_BLK = 5'd31;  // blank (mati)
 
    // Lookup: [class_in][digit_sel]  digit_sel: 0=kanan .. 3=kiri
    reg [4:0] char_code;
    always @(*) begin
        case ({class_in, digit_sel})
            {3'd0, 2'd3}: char_code = CH_BLK;   // "  30"
            {3'd0, 2'd2}: char_code = CH_BLK;
            {3'd0, 2'd1}: char_code = CH_3;
            {3'd0, 2'd0}: char_code = CH_0;
            {3'd1, 2'd3}: char_code = CH_BLK;   // "  50"
            {3'd1, 2'd2}: char_code = CH_BLK;
            {3'd1, 2'd1}: char_code = CH_5S;
            {3'd1, 2'd0}: char_code = CH_0;
            {3'd2, 2'd3}: char_code = CH_P;     // "PrIo"
            {3'd2, 2'd2}: char_code = CH_r;
            {3'd2, 2'd1}: char_code = CH_I;
            {3'd2, 2'd0}: char_code = CH_o;
            {3'd3, 2'd3}: char_code = CH_BLK;   // " yLd"
            {3'd3, 2'd2}: char_code = CH_y;
            {3'd3, 2'd1}: char_code = CH_L;
            {3'd3, 2'd0}: char_code = CH_d;
            {3'd4, 2'd3}: char_code = CH_5S;    // "StOP" (S=5)
            {3'd4, 2'd2}: char_code = CH_t;
            {3'd4, 2'd1}: char_code = CH_0;     // O=0
            {3'd4, 2'd0}: char_code = CH_P;
            {3'd5, 2'd3}: char_code = CH_n;     // "noE "
            {3'd5, 2'd2}: char_code = CH_o;
            {3'd5, 2'd1}: char_code = CH_E;
            {3'd5, 2'd0}: char_code = CH_BLK;
            {3'd6, 2'd3}: char_code = CH_C;     // "CAUt"
            {3'd6, 2'd2}: char_code = CH_A;
            {3'd6, 2'd1}: char_code = CH_U;
            {3'd6, 2'd0}: char_code = CH_t;
            {3'd7, 2'd3}: char_code = CH_r;     // "rIGt"
            {3'd7, 2'd2}: char_code = CH_I;
            {3'd7, 2'd1}: char_code = CH_G;
            {3'd7, 2'd0}: char_code = CH_t;
            default:      char_code = CH_BLK;
        endcase
    end
 
    // =========================================================================
    // 3) Segment encoder -> pola 7-seg AKTIF-LOW, urutan {g,f,e,d,c,b,a}
    //    (segmen NYALA = 0, sama seperti decoder common-anode Basys3)
    // =========================================================================
    reg [6:0] seg_al;   // active-low
    always @(*) begin
        case (char_code)
            //                  gfedcba
            CH_0:   seg_al = 7'b1000000;  // 0 / O
            CH_3:   seg_al = 7'b0110000;  // 3
            CH_5S:  seg_al = 7'b0010010;  // 5 / S
            CH_P:   seg_al = 7'b0011000;  // P
            CH_r:   seg_al = 7'b0101111;  // r (kecil)
            CH_I:   seg_al = 7'b1111001;  // I (= pola '1')
            CH_o:   seg_al = 7'b0100011;  // o (kecil)
            CH_y:   seg_al = 7'b0010001;  // y
            CH_L:   seg_al = 7'b1000111;  // L
            CH_d:   seg_al = 7'b0100001;  // d (kecil)
            CH_t:   seg_al = 7'b0000111;  // t (kecil)
            CH_n:   seg_al = 7'b0101011;  // n (kecil)
            CH_E:   seg_al = 7'b0000110;  // E
            CH_C:   seg_al = 7'b1000110;  // C
            CH_A:   seg_al = 7'b0001000;  // A
            CH_U:   seg_al = 7'b1000001;  // U
            CH_G:   seg_al = 7'b1000010;  // G
            default: seg_al = 7'b1111111; // blank (semua mati)
        endcase
    end
 
    // =========================================================================
    // 4) Output register
    // =========================================================================
    always @(posedge clk or posedge rst) begin
        if (rst) begin
            seg <= 7'b1111111;      // semua segmen mati (aktif-low)
            an  <= 4'b1111;         // semua digit mati
            led <= 8'b0;
        end else if (!valid) begin
            seg <= 7'b1111111;
            an  <= 4'b1111;
            led <= 8'b0;
        end else begin
            seg <= seg_al;          // sudah aktif-low, langsung
            case (digit_sel)
                2'd0: an <= 4'b1110;  // digit 0 (kanan) aktif
                2'd1: an <= 4'b1101;  // digit 1
                2'd2: an <= 4'b1011;  // digit 2
                2'd3: an <= 4'b0111;  // digit 3 (kiri) aktif
                default: an <= 4'b1111;
            endcase
            led <= 8'd1 << class_in;  // one-hot, aktif-high
        end
    end
 
endmodule