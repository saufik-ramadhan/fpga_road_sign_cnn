`timescale 1ns / 1ps
`default_nettype none

// conv_engine_tb: runs conv_engine into fmap_ram, wired as in cnn_core, on
// N_IMG images and checks all 1,568 activations of each image bit-exact.
//
// Run it from the folder that holds the vectors (run_p3_tests.py does this):
//   pixels.mem        N_IMG*256 lines, 2 hex digits, image after image, row*16+col
//   conv_weights.mem  72 lines, 2 hex digits, two's complement
//   conv_out.mem      N_IMG*1568 lines, 2 hex digits, filter*196 + row*14 + col
//   params.vh         CONV_M, CONV_S, CONV_BIAS (on the include path)
//
// Also checks: every address written exactly once with a value of 0..127, a
// one-cycle done with busy falling, the same cycle count for every image,
// start ignored while busy (image 1), and the overflow flag: clear, or set
// when compiled with EXPECT_OVF.

`ifndef N_IMG
`define N_IMG 20
`endif

module conv_engine_tb;

    `include "params.vh"

    localparam N_IMG   = `N_IMG;
    localparam N_PIX   = 256;
    localparam N_OUT   = 1568;
    localparam TIMEOUT = 100000;    // cycles per image

    reg clk = 1'b0;
    always #5 clk = ~clk;           // 100 MHz

    reg rst   = 1'b1;
    reg start = 1'b0;

    // ---- DUT ---------------------------------------------------------------
    wire        busy, done, ovf;
    wire        pix_rd;
    wire [7:0]  pix_addr;
    reg  [7:0]  pix_data;
    wire        fm_we;
    wire [10:0] fm_addr;
    wire [7:0]  fm_data;
    reg  [10:0] rd_addr = 11'd0;
    wire [7:0]  rd_data;

    conv_engine #(
        .M           (CONV_M),
        .S           (CONV_S),
        .BIAS        (CONV_BIAS),
        .WEIGHT_FILE ("conv_weights.mem")
    ) dut (
        .clk      (clk),
        .rst      (rst),
        .start    (start),
        .busy     (busy),
        .done     (done),
        .ovf      (ovf),
        .pix_rd   (pix_rd),
        .pix_addr (pix_addr),
        .pix_data (pix_data),
        .fm_we    (fm_we),
        .fm_addr  (fm_addr),
        .fm_data  (fm_data)
    );

    fmap_ram u_fmap (
        .clk   (clk),
        .we    (fm_we),
        .waddr (fm_addr),
        .wdata (fm_data),
        .raddr (rd_addr),
        .rdata (rd_data)
    );

    // ---- image memory: one-cycle read, like img_buf behind input_mux --------
    // Data is X unless the engine asked for it, so a pipeline that uses a
    // pixel at the wrong time produces X and fails the comparison.
    reg [7:0] pixels [0:N_IMG*N_PIX-1];
    reg [7:0] golden [0:N_IMG*N_OUT-1];
    integer   img = 0;

    always @(posedge clk)
        pix_data <= pix_rd ? pixels[img*N_PIX + pix_addr] : 8'hxx;

    // ---- write monitor -----------------------------------------------------
    reg     written [0:N_OUT-1];
    integer n_writes = 0;
    integer bad_writes = 0;

    always @(posedge clk) begin
        if (!rst && fm_we) begin
            n_writes = n_writes + 1;
            if (fm_addr >= N_OUT || fm_data > 8'd127 || written[fm_addr] === 1'b1) begin
                if (bad_writes < 5)
                    $display("  bad write: addr %0d data %0d (out of range, over 127, or written twice)",
                             fm_addr, fm_data);
                bad_writes = bad_writes + 1;
            end else begin
                written[fm_addr] = 1'b1;
            end
        end
    end

    // ---- handshake monitor -------------------------------------------------
    reg     done_q = 1'b0;
    integer bad_handshake = 0;

    always @(posedge clk) begin
        done_q <= done;
        if (!rst && done && (done_q || busy)) begin
            $display("  handshake error: done longer than one cycle, or busy still high");
            bad_handshake = bad_handshake + 1;
        end
    end

    // ---- waveform, when compiled with DUMP ---------------------------------
    // Saves one image's run and read-back to conv_engine_tb.vcd, for GTKWave:
    // image DUMP_IMG (default 3, a ramp with easy-to-read pixel values), or the
    // last image when there are fewer. The other images are left out to keep
    // the file small.
`ifdef DUMP
`ifndef DUMP_IMG
`define DUMP_IMG 3
`endif
    localparam DUMP_AT = (`DUMP_IMG < N_IMG) ? `DUMP_IMG : N_IMG - 1;

    initial begin
        $dumpfile("conv_engine_tb.vcd");
        $dumpvars(1, conv_engine_tb);
        $dumpvars(1, dut);
        $dumpvars(1, dut.u_rq);
        $dumpoff;
        wait (img == DUMP_AT);
        $dumpon;
        wait (img == DUMP_AT + 1);
        $dumpoff;
    end
`endif

    // ---- test sequence -----------------------------------------------------
    integer i, k, cycles, first_cycles, mismatches, errors;
    reg [7:0] got, want;

    initial begin
        $readmemh("pixels.mem", pixels);
        $readmemh("conv_out.mem", golden);

        errors       = 0;
        mismatches   = 0;
        first_cycles = -1;

        repeat (4) @(negedge clk);
        rst = 1'b0;
        @(negedge clk);

        for (i = 0; i < N_IMG; i = i + 1) begin
            img = i;
            for (k = 0; k < N_OUT; k = k + 1) begin
                u_fmap.mem[k] = 8'hxx;      // a missed write reads back as X
                written[k]    = 1'b0;
            end
            n_writes = 0;

            // one-cycle start pulse; cycles counts clock edges until done
            start = 1'b1;
            @(negedge clk);
            start  = 1'b0;
            cycles = 0;
            while (done !== 1'b1 && cycles < TIMEOUT) begin
                @(negedge clk);
                cycles = cycles + 1;
                if (i == 1)                 // a second start in mid-run must be ignored
                    start = (cycles == 1000);
            end
            start = 1'b0;

            if (cycles >= TIMEOUT) begin
                $display("FAIL conv_engine_tb: image %0d, no done after %0d cycles", i, TIMEOUT);
                $finish;
            end
            if (first_cycles < 0)
                first_cycles = cycles;
            else if (cycles != first_cycles) begin
                $display("  image %0d took %0d cycles, image 0 took %0d", i, cycles, first_cycles);
                errors = errors + 1;
            end
`ifdef EXPECT_OVF
            if (ovf !== 1'b1) begin
                $display("  image %0d: ovf not set, but this test overflows the accumulator", i);
                errors = errors + 1;
            end
`else
            if (ovf !== 1'b0) begin
                $display("  image %0d: accumulator overflow", i);
                errors = errors + 1;
            end
`endif
            if (n_writes != N_OUT) begin
                $display("  image %0d: %0d writes, expected %0d", i, n_writes, N_OUT);
                errors = errors + 1;
            end

            // read fmap_ram back through its read port, one address per cycle,
            // as maxpool will; rdata must not follow raddr before the clock edge
            rd_addr = 11'd0;
            for (k = 0; k < N_OUT; k = k + 1) begin
                @(negedge clk);
                got  = rd_data;
                want = golden[i*N_OUT + k];
                if (k + 1 < N_OUT) begin
                    rd_addr = k + 1;
                    #1;
                    if (rd_data !== got) begin
                        if (bad_handshake < 5)
                            $display("  fmap_ram rdata changed before the clock edge (read must take 1 cycle)");
                        bad_handshake = bad_handshake + 1;
                    end
                end
                if (got !== want) begin
                    if (mismatches < 10)
                        $display("  image %0d: fmap[%0d] (filter %0d, row %0d, col %0d) = %0d, golden %0d",
                                 i, k, k / 196, (k % 196) / 14, k % 14, got, want);
                    mismatches = mismatches + 1;
                end
            end
            $display("  image %2d: %0d cycles, ovf %0d", i, cycles, ovf);
        end

        errors = errors + mismatches + bad_writes + bad_handshake;
        if (errors == 0)
            $display("PASS conv_engine_tb: %0d images x %0d activations bit-exact, %0d cycles per image",
                     N_IMG, N_OUT, first_cycles);
        else
            $display("FAIL conv_engine_tb: %0d mismatches, %0d other errors",
                     mismatches, errors - mismatches);
        $finish;
    end

endmodule

`default_nettype wire
