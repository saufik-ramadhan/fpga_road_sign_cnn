`timescale 1ns/1ps
module tb_maxpool;
    parameter NF = 8;
    parameter IN_W = 14;
    parameter FA_W = 11;
    parameter PA_W = 9;
    localparam OUT_W = IN_W/2;
    localparam FMAP_N = NF*IN_W*IN_W;
    localparam POOL_N = NF*OUT_W*OUT_W;

    reg clk = 1'b0, rst = 1'b1, start = 1'b0;
    wire busy, done;
    wire [FA_W-1:0] fmap_addr;
    reg  [7:0] fmap_dout;
    wire [PA_W-1:0] pool_addr;
    wire [7:0] pool_din;
    wire pool_we;

    reg [7:0] fmap_mem [0:FMAP_N-1];
    reg [7:0] pool_mem [0:POOL_N-1];
    reg [7:0] pool_exp [0:POOL_N-1];

    maxpool #(.NF(NF), .IN_W(IN_W), .FA_W(FA_W), .PA_W(PA_W)) dut (
        .clk(clk), .rst(rst), .start(start), .busy(busy), .done(done),
        .fmap_addr(fmap_addr), .fmap_dout(fmap_dout),
        .pool_addr(pool_addr), .pool_din(pool_din), .pool_we(pool_we));

    always #5 clk = ~clk;
    always @(posedge clk) fmap_dout <= fmap_mem[fmap_addr];
    always @(posedge clk) if (pool_we) pool_mem[pool_addr] <= pool_din;

    integer i, errors, cycles;
    initial begin
        $readmemh("fmap.mem", fmap_mem);
        $readmemh("pool_expected.mem", pool_exp);
        for (i = 0; i < POOL_N; i = i + 1) pool_mem[i] = 8'hxx;
        repeat (4) @(posedge clk); rst <= 1'b0;
        repeat (2) @(posedge clk);
        start <= 1'b1; @(posedge clk); start <= 1'b0;
        cycles = 0;
        while (!done && cycles < 4*POOL_N+1000) begin @(posedge clk); cycles = cycles + 1; end
        repeat (3) @(posedge clk);
        if (!done && cycles >= 4*POOL_N+1000) $display("FAIL: timeout");
        else begin
            errors = 0;
            for (i = 0; i < POOL_N; i = i + 1)
                if (pool_mem[i] !== pool_exp[i]) begin
                    if (errors == 0)
                        $display("FAIL: mismatch pertama di indeks %0d (f=%0d r=%0d c=%0d): dapat %h, harusnya %h",
                                 i, i/(OUT_W*OUT_W), (i%(OUT_W*OUT_W))/OUT_W, i%OUT_W, pool_mem[i], pool_exp[i]);
                    errors = errors + 1;
                end
            if (errors == 0) $display("PASS: %0d/%0d byte cocok, %0d clock sejak start", POOL_N, POOL_N, cycles);
            else $display("FAIL: %0d dari %0d byte salah", errors, POOL_N);
        end
        $finish;
    end
endmodule