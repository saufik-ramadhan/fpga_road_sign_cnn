`timescale 1ns / 1ps
`default_nettype none

// conv_engine_tb: runs conv_engine into fmap_ram, wired as in cnn_core, on
// N_IMG images. For each image it checks all 1,568 accumulators before the
// rescale, then all 1,568 activations read back from fmap_ram, bit-exact: the
// order P2's handoff asks for. It also checks, for every output, whether one
// of its partial sums left the ACC_W-bit range.
//
// Run it from the folder that holds the vectors (run_p3_tests.py does this):
//   pixels.mem       N_IMG*256 lines, 2 hex digits, image after image, row*16+col
//   conv_weight.mem  72 lines, 2 hex digits, two's complement (read by the DUT)
//   conv_bias.mem    8 lines, ACC_W/4 hex digits, two's complement (read by the DUT)
//   conv_acc.mem     N_IMG*1568 lines, 8 hex digits (32-bit, sign-extended),
//                    filter*196 + row*14 + col
//   conv_out.mem     N_IMG*1568 lines, 2 hex digits, the same order
//   conv_ovf.mem     N_IMG*1568 lines, 1 digit, the same order: 1 if a partial
//                    sum of that output (P2's serial order) left the range
//   params.vh        CONV_M, CONV_S and CONV_ACC_W (on the include path)
//
// N_MAC picks the engine version: 1, 3 or 9 multipliers. Compiled with
// P2_DEFAULTS, the DUT gets no parameters but N_MAC (none at all when N_MAC
// is not defined), as from a top that passes none, and params.vh is not read:
// the run then checks that the defaults are P2's model.
//
// Also checks: every address written exactly once with a value of 0..127, a
// one-cycle done with busy falling, the version's cycle count for every
// image, start ignored while busy (image 1), the overflow flag at done (set
// exactly for the images with an overflowing output), and a reset in mid-run
// after the last image (busy, done, reads and writes stop).

`ifndef N_IMG
`define N_IMG 20
`endif

module conv_engine_tb;

`ifndef P2_DEFAULTS
    `include "params.vh"
`endif

`ifdef N_MAC
    localparam N_MAC = `N_MAC;
`else
    localparam N_MAC = 1;           // the engine's default
`endif

    localparam N_IMG   = `N_IMG;
    localparam N_PIX   = 256;
    localparam N_OUT   = 1568;
    localparam TIMEOUT = 100000;    // cycles per image
    // start to done, the same for every image: 1,568 x 9 / N_MAC multiply
    // steps, the cycles in which the window fills (N_MAC = 3 and 9), and the
    // pipeline
    localparam CYCLES  = (N_MAC == 9) ? 1636 : (N_MAC == 3) ? 4770 : 14117;

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

`ifdef P2_DEFAULTS
`ifdef N_MAC
    conv_engine #(
        .N_MAC (N_MAC)
    ) dut (
`else
    conv_engine dut (
`endif
`else
    conv_engine #(
        .M     (CONV_M),
        .S     (CONV_S),
        .ACC_W (CONV_ACC_W),
        .N_MAC (N_MAC)
    ) dut (
`endif
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
    reg [7:0]  pixels     [0:N_IMG*N_PIX-1];
    reg [7:0]  golden     [0:N_IMG*N_OUT-1];
    reg [31:0] golden_acc [0:N_IMG*N_OUT-1];
    reg        golden_ovf [0:N_IMG*N_OUT-1];
    integer    img = 0;

    always @(posedge clk)
        pix_data <= pix_rd ? pixels[img*N_PIX + pix_addr] : 8'hxx;

    // ---- accumulator monitor: each finished sum, before the rescale --------
    // Watches the DUT's accumulator stage through its hierarchical names. The
    // accumulator is ACC_W bits wide; it is sign-extended to the file's 32.
    wire signed [31:0] dut_acc = dut.acc;
    integer n_accs = 0;
    integer acc_mismatches = 0;

    always @(posedge clk) begin
        if (!rst && dut.acc_valid) begin
            n_accs = n_accs + 1;
            if (dut_acc !== golden_acc[img*N_OUT + dut.acc_oaddr]) begin
                if (acc_mismatches < 10)
                    $display("  image %0d: acc[%0d] (filter %0d, row %0d, col %0d) = %0d, golden %0d",
                             img, dut.acc_oaddr, dut.acc_oaddr / 196, (dut.acc_oaddr % 196) / 14,
                             dut.acc_oaddr % 14, dut_acc, $signed(golden_acc[img*N_OUT + dut.acc_oaddr]));
                acc_mismatches = acc_mismatches + 1;
            end
        end
    end

    // ---- overflow monitor: the outputs with a partial sum out of range ------
    // Every engine version presents its accumulator's last step under the same
    // names: dut.p_valid, and dut.acc_ovf for the sum of output dut.p_oaddr.
    reg     ovf_seen [0:N_OUT-1];
    integer ovf_mismatches = 0;

    always @(posedge clk)
        if (!rst && dut.p_valid && dut.acc_ovf)
            ovf_seen[dut.p_oaddr] = 1'b1;

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
        $dumpvars(0, dut);
        $dumpoff;
        wait (img == DUMP_AT);
        $dumpon;
        wait (img == DUMP_AT + 1);
        $dumpoff;
    end
`endif

    // ---- test sequence -----------------------------------------------------
    integer i, k, cycles, mismatches, errors;
    reg [7:0] got, want;
    reg       want_ovf;

    initial begin
        $readmemh("pixels.mem", pixels);
        $readmemh("conv_out.mem", golden);
        $readmemh("conv_acc.mem", golden_acc);
        $readmemh("conv_ovf.mem", golden_ovf);

        errors     = 0;
        mismatches = 0;
        if (golden_ovf[N_IMG*N_OUT-1] !== 1'b0 && golden_ovf[N_IMG*N_OUT-1] !== 1'b1) begin
            $display("  conv_ovf.mem is missing or too short");
            errors = errors + 1;
        end

        repeat (4) @(negedge clk);
        rst = 1'b0;
        @(negedge clk);

        for (i = 0; i < N_IMG; i = i + 1) begin
            img = i;
            for (k = 0; k < N_OUT; k = k + 1) begin
                u_fmap.mem[k] = 8'hxx;      // a missed write reads back as X
                written[k]    = 1'b0;
                ovf_seen[k]   = 1'b0;
            end
            n_writes = 0;
            n_accs   = 0;

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
            if (cycles != CYCLES) begin
                $display("  image %0d took %0d cycles, N_MAC = %0d takes %0d", i, cycles, N_MAC, CYCLES);
                errors = errors + 1;
            end
            if (n_writes != N_OUT || n_accs != N_OUT) begin
                $display("  image %0d: %0d accumulators and %0d writes, expected %0d of each",
                         i, n_accs, n_writes, N_OUT);
                errors = errors + 1;
            end

            // overflow: each output's flag, then ovf at done
            want_ovf = 1'b0;
            for (k = 0; k < N_OUT; k = k + 1) begin
                if (ovf_seen[k] !== golden_ovf[i*N_OUT + k]) begin
                    if (ovf_mismatches < 10)
                        $display("  image %0d: output %0d (filter %0d, row %0d, col %0d) overflow %0d, expected %0d",
                                 i, k, k / 196, (k % 196) / 14, k % 14, ovf_seen[k], golden_ovf[i*N_OUT + k]);
                    ovf_mismatches = ovf_mismatches + 1;
                end
                want_ovf = want_ovf | golden_ovf[i*N_OUT + k];
            end
            if (ovf !== want_ovf) begin
                $display("  image %0d: ovf %0d at done, expected %0d", i, ovf, want_ovf);
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

        // a reset in mid-run stops the engine: no busy, done, reads or writes
        // until the next start
        for (k = 0; k < N_OUT; k = k + 1)
            written[k] = 1'b0;
        start = 1'b1;
        @(negedge clk);
        start = 1'b0;
        repeat (CYCLES / 2) @(negedge clk);
        rst = 1'b1;
        @(negedge clk);
        rst = 1'b0;
        for (k = 0; k < 20; k = k + 1) begin
            if (busy !== 1'b0 || done !== 1'b0 || pix_rd !== 1'b0 || fm_we !== 1'b0) begin
                if (bad_handshake < 5)
                    $display("  still running after a reset in mid-run");
                bad_handshake = bad_handshake + 1;
            end
            @(negedge clk);
        end

        errors = errors + acc_mismatches + mismatches + ovf_mismatches + bad_writes + bad_handshake;
        if (errors == 0)
            $display("PASS conv_engine_tb: N_MAC=%0d, %0d images x %0d accumulators, activations and overflow flags bit-exact, %0d cycles per image",
                     N_MAC, N_IMG, N_OUT, CYCLES);
        else
            $display("FAIL conv_engine_tb: N_MAC=%0d, %0d accumulator, %0d activation and %0d overflow-flag mismatches, %0d other errors",
                     N_MAC, acc_mismatches, mismatches, ovf_mismatches,
                     errors - acc_mismatches - mismatches - ovf_mismatches);
        $finish;
    end

endmodule

`default_nettype wire
