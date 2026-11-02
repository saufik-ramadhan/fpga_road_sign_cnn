// tb_sign_display.v : Testbench untuk modul sign_display (Basys3)
//
// Konvensi diuji (sama dgn modul & .xdc Basys3):
//   - seg[6:0] = {g,f,e,d,c,b,a}, AKTIF-LOW (segmen nyala = 0)
//   - an aktif-low, led aktif-high, reset aktif-high
//
// Uji:
//   - valid=0 -> semua display & LED mati
//   - 8 kelas: LED one-hot + 4 digit 7-seg menampilkan teks benar
//
// Jalankan:
//   iverilog -g2005 -o sim_display tb_sign_display.v sign_display.v
//   vvp sim_display
//
`timescale 1ns/1ps

module tb_sign_display;

    reg        clk = 0;
    reg        rst = 1;
    reg  [2:0] class_in = 0;
    reg        valid = 0;
    wire [6:0] seg;
    wire [3:0] an;
    wire [7:0] led;

    sign_display uut (
        .clk(clk), .rst(rst),
        .class_in(class_in), .valid(valid),
        .seg(seg), .an(an), .led(led)
    );

    always #5 clk = ~clk;  // 100 MHz

    // Pola segmen AKTIF-LOW, urutan {g,f,e,d,c,b,a} (segmen nyala = 0)
    localparam [6:0] S_0   = 7'b1000000;  // 0/O
    localparam [6:0] S_3   = 7'b0110000;  // 3
    localparam [6:0] S_5S  = 7'b0010010;  // 5/S
    localparam [6:0] S_P   = 7'b0011000;  // P
    localparam [6:0] S_r   = 7'b0101111;  // r
    localparam [6:0] S_I   = 7'b1111001;  // I
    localparam [6:0] S_o   = 7'b0100011;  // o
    localparam [6:0] S_y   = 7'b0010001;  // y
    localparam [6:0] S_L   = 7'b1000111;  // L
    localparam [6:0] S_d   = 7'b0100001;  // d
    localparam [6:0] S_t   = 7'b0000111;  // t
    localparam [6:0] S_n   = 7'b0101011;  // n
    localparam [6:0] S_E   = 7'b0000110;  // E
    localparam [6:0] S_C   = 7'b1000110;  // C
    localparam [6:0] S_A   = 7'b0001000;  // A
    localparam [6:0] S_U   = 7'b1000001;  // U
    localparam [6:0] S_G   = 7'b1000010;  // G
    localparam [6:0] S_BLK = 7'b1111111;  // blank (semua mati)

    // Tabel expected: [class][digit] — digit 0=kanan, 3=kiri
    reg [6:0] expected [0:7][0:3];
    reg [8*8-1:0] class_name [0:7];

    integer cls, dig, errors, total_checks;
    reg [7:0] led_expected;

    // Tunggu sampai digit tertentu aktif, lalu cek segment
    task wait_for_digit;
        input [1:0] target_dig;
        input [6:0] exp_seg;
        integer timeout;
        reg [3:0] target_an;
        begin
            case (target_dig)
                2'd0: target_an = 4'b1110;
                2'd1: target_an = 4'b1101;
                2'd2: target_an = 4'b1011;
                2'd3: target_an = 4'b0111;
                default: target_an = 4'b1111;
            endcase
            timeout = 0;
            while (an !== target_an && timeout < 200000) begin
                @(posedge clk);
                timeout = timeout + 1;
            end
            @(posedge clk);  // 1 clock tambahan supaya stabil
            if (an !== target_an) begin
                $display("FAIL: class %0d digit %0d — anode %b tidak pernah aktif (timeout)", cls, target_dig, target_an);
                errors = errors + 1;
            end else if (seg !== exp_seg) begin
                $display("FAIL: class %0d (%0s) digit %0d — seg=%b, harusnya %b",
                         cls, class_name[cls], target_dig, seg, exp_seg);
                errors = errors + 1;
            end
            total_checks = total_checks + 1;
        end
    endtask

    initial begin
        // --- Rekam waveform untuk GTKWave ---
        $dumpfile("sign_display.vcd");
        $dumpvars(0, tb_sign_display);

        // class 0: "  30"
        expected[0][3] = S_BLK; expected[0][2] = S_BLK; expected[0][1] = S_3;   expected[0][0] = S_0;
        // class 1: "  50"
        expected[1][3] = S_BLK; expected[1][2] = S_BLK; expected[1][1] = S_5S;  expected[1][0] = S_0;
        // class 2: "PrIo"
        expected[2][3] = S_P;   expected[2][2] = S_r;   expected[2][1] = S_I;   expected[2][0] = S_o;
        // class 3: " yLd"
        expected[3][3] = S_BLK; expected[3][2] = S_y;   expected[3][1] = S_L;   expected[3][0] = S_d;
        // class 4: "StOP"
        expected[4][3] = S_5S;  expected[4][2] = S_t;   expected[4][1] = S_0;   expected[4][0] = S_P;
        // class 5: "noE "
        expected[5][3] = S_n;   expected[5][2] = S_o;   expected[5][1] = S_E;   expected[5][0] = S_BLK;
        // class 6: "CAUt"
        expected[6][3] = S_C;   expected[6][2] = S_A;   expected[6][1] = S_U;   expected[6][0] = S_t;
        // class 7: "rIGt"
        expected[7][3] = S_r;   expected[7][2] = S_I;   expected[7][1] = S_G;   expected[7][0] = S_t;

        class_name[0] = "Speed30 ";
        class_name[1] = "Speed50 ";
        class_name[2] = "Priority";
        class_name[3] = "Yield   ";
        class_name[4] = "Stop    ";
        class_name[5] = "NoEntry ";
        class_name[6] = "Caution ";
        class_name[7] = "KeepRigt";

        errors = 0;
        total_checks = 0;

        // --- Reset (aktif-high) ---
        repeat (10) @(posedge clk);
        rst <= 0;
        repeat (5) @(posedge clk);

        // --- Uji valid=0: semua mati ---
        valid <= 0;
        class_in <= 3'd4;
        repeat (200000) @(posedge clk);
        @(posedge clk);
        if (seg !== 7'b1111111 || an !== 4'b1111 || led !== 8'd0) begin
            $display("FAIL: valid=0 tapi display tidak mati (seg=%b an=%b led=%b)", seg, an, led);
            errors = errors + 1;
        end else begin
            $display("PASS: valid=0 -> display mati");
        end
        total_checks = total_checks + 1;

        // --- Uji setiap kelas ---
        valid <= 1;
        for (cls = 0; cls < 8; cls = cls + 1) begin
            class_in <= cls;
            repeat (100) @(posedge clk);

            led_expected = 8'd1 << cls;
            if (led !== led_expected) begin
                $display("FAIL: class %0d — LED=%b, harusnya %b", cls, led, led_expected);
                errors = errors + 1;
            end
            total_checks = total_checks + 1;

            for (dig = 0; dig < 4; dig = dig + 1) begin
                wait_for_digit(dig[1:0], expected[cls][dig]);
            end
        end

        $display("");
        if (errors == 0)
            $display("PASS: semua %0d pengecekan LULUS — 8 kelas x 4 digit + LED + valid=0", total_checks);
        else
            $display("FAIL: %0d kesalahan dari %0d pengecekan", errors, total_checks);
        $finish;
    end

endmodule