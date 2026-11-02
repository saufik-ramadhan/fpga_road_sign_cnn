`timescale 1ns / 1ps
`default_nettype none

// requant_relu_tb: drives N_VEC accumulator values through requant_relu and
// compares every result with the Python formula. The first half arrives with
// random gaps, the second half back to back. Also checks that results come out
// in order, exactly 2 cycles after their input, with their tag.
//
// Run it from the folder that holds the vectors (run_p3_tests.py does this):
//   rq_acc.mem   N_VEC lines, 6 hex digits, 24-bit two's complement
//   rq_q.mem     N_VEC lines, 2 hex digits, expected result
//   params.vh    CONV_M and CONV_S (on the include path)

`ifndef N_VEC
`define N_VEC 10000
`endif

module requant_relu_tb;

    `include "params.vh"

    localparam N_VEC   = `N_VEC;
    localparam LATENCY = 2;

    reg clk = 1'b0;
    always #5 clk = ~clk;

    reg               rst      = 1'b1;
    reg               in_valid = 1'b0;
    reg signed [23:0] acc      = 24'sd0;
    reg [15:0]        in_tag   = 16'd0;
    wire              out_valid;
    wire [7:0]        q;
    wire [15:0]       out_tag;

    requant_relu #(.M(CONV_M), .S(CONV_S), .TAG_W(16)) dut (
        .clk       (clk),
        .rst       (rst),
        .in_valid  (in_valid),
        .acc       (acc),
        .in_tag    (in_tag),
        .out_valid (out_valid),
        .q         (q),
        .out_tag   (out_tag)
    );

    reg [23:0] acc_vec [0:N_VEC-1];
    reg [7:0]  q_exp   [0:N_VEC-1];
    integer    sent_at [0:N_VEC-1];

    integer cyc = 0;
    always @(posedge clk)
        cyc <= cyc + 1;

    // ---- checker: results in order, on time, equal to the formula ----------
    integer n_out = 0;
    integer errors = 0;

    always @(posedge clk) begin
        if (!rst && out_valid) begin
            if (n_out >= N_VEC || out_tag !== n_out[15:0]) begin
                if (errors < 10)
                    $display("  result %0d: tag %0d, out of order", n_out, out_tag);
                errors = errors + 1;
            end else if (q !== q_exp[n_out]) begin
                if (errors < 10)
                    $display("  vector %0d: acc %0d -> %0d, expected %0d",
                             n_out, $signed(acc_vec[n_out]), q, q_exp[n_out]);
                errors = errors + 1;
            end else if (cyc - sent_at[n_out] != LATENCY) begin
                if (errors < 10)
                    $display("  vector %0d: latency %0d cycles, expected %0d",
                             n_out, cyc - sent_at[n_out], LATENCY);
                errors = errors + 1;
            end
            n_out = n_out + 1;
        end
    end

    // ---- waveform, when compiled with DUMP ---------------------------------
`ifdef DUMP
    initial begin
        $dumpfile("requant_relu_tb.vcd");
        $dumpvars(1, requant_relu_tb);
        $dumpvars(1, dut);
    end
`endif

    // ---- driver ------------------------------------------------------------
    integer i, seed;

    initial begin
        $readmemh("rq_acc.mem", acc_vec);
        $readmemh("rq_q.mem", q_exp);
        seed = 1;

        repeat (4) @(posedge clk);
        rst <= 1'b0;

        i = 0;
        while (i < N_VEC) begin
            @(posedge clk);
            if (i >= N_VEC / 2 || $random(seed) % 4 != 0) begin
                in_valid   <= 1'b1;
                acc        <= acc_vec[i];
                in_tag     <= i;
                sent_at[i]  = cyc + 1;      // the input is seen in the next cycle
                i = i + 1;
            end else begin
                in_valid <= 1'b0;
                acc      <= 24'hxxxxxx;     // data without valid must not matter
            end
        end
        @(posedge clk);
        in_valid <= 1'b0;
        repeat (LATENCY + 3) @(posedge clk);

        if (n_out != N_VEC) begin
            $display("  %0d results for %0d inputs", n_out, N_VEC);
            errors = errors + 1;
        end
        if (errors == 0)
            $display("PASS requant_relu_tb: M=%0d S=%0d, %0d values equal to the formula",
                     CONV_M, CONV_S, N_VEC);
        else
            $display("FAIL requant_relu_tb: M=%0d S=%0d, %0d errors", CONV_M, CONV_S, errors);
        $finish;
    end

endmodule

`default_nettype wire
