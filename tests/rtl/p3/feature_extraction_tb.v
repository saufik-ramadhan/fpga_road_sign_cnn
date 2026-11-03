`timescale 1ns / 1ps
`default_nettype none
`ifndef N_IMG
`define N_IMG 25
`endif

// Public integration interface: image read port -> P3 -> fmap read port.
// Run against P2 packages at 24 and 32 accumulator bits. N_MAC picks the
// conv_engine version (1, 3 or 9 multipliers), passed through the wrapper.
module feature_extraction_tb;
`ifndef P2_DEFAULTS
    `include "params.vh"
`endif
`ifdef N_MAC
    localparam N_MAC = `N_MAC;
`else
    localparam N_MAC = 1;
`endif
    localparam N_IMG = `N_IMG;
    localparam N_OUT = 1568;
    localparam CYCLES = (N_MAC == 9) ? 1636 : (N_MAC == 3) ? 4770 : 14117;
    reg clk = 0;
    always #5 clk = ~clk;
    reg rst = 1, start = 0;
    wire busy, done, ovf, pix_rd;
    wire [7:0] pix_addr;
    reg [7:0] pix_data;
    reg [10:0] rd_addr = 0;
    wire [7:0] rd_data;
`ifdef P2_DEFAULTS
`ifdef N_MAC
    feature_extraction #(.N_MAC(N_MAC)) dut (
`else
    feature_extraction dut (
`endif
`else
    feature_extraction #(.M(CONV_M), .S(CONV_S), .ACC_W(CONV_ACC_W), .N_MAC(N_MAC)) dut (
`endif
        .clk(clk), .rst(rst), .start(start), .busy(busy), .done(done), .ovf(ovf),
        .pix_rd(pix_rd), .pix_addr(pix_addr), .pix_data(pix_data),
        .rd_addr(rd_addr), .rd_data(rd_data)
    );
    reg [7:0] pixels [0:N_IMG*256-1];
    reg [7:0] expected [0:N_IMG*N_OUT-1];
    integer image = 0;
    always @(posedge clk)
        pix_data <= pix_rd ? pixels[image*256+pix_addr] : 8'hxx;
    reg prev_done = 0;
    integer errors = 0;
    always @(posedge clk) begin
        prev_done <= done;
        if (!rst && done && (prev_done || busy)) errors = errors + 1;
    end
    integer i, address, cycles;
    reg [7:0] previous_data;
    initial begin
        $readmemh("pixels.mem", pixels);
        $readmemh("conv_out.mem", expected);
        repeat (4) @(negedge clk);
        rst = 0;
        @(negedge clk);
        for (i=0; i<N_IMG; i=i+1) begin
            image = i;
            start = 1;
            @(negedge clk);
            start = 0;
            cycles = 0;
            while (done !== 1'b1 && cycles < 100000) begin
                @(negedge clk);
                cycles = cycles + 1;
                start = (i == 1 && cycles == 1000);
            end
            start = 0;
            if (done !== 1'b1 || cycles != CYCLES || busy !== 0 || ovf !== 0) begin
                $display("FAIL feature_extraction_tb: image %0d handshake/cycles/overflow",i);
                $finish;
            end
            rd_addr = 0;
            for (address=0; address<N_OUT; address=address+1) begin
                @(negedge clk);
                if (rd_data !== expected[image*N_OUT+address]) errors = errors + 1;
                previous_data = rd_data;
                if (address+1<N_OUT) begin
                    rd_addr = address+1;
                    #1;
                    if (rd_data !== previous_data) errors = errors + 1;
                end
            end
        end
        if (errors) $display("FAIL feature_extraction_tb: %0d readback/handshake errors", errors);
        else $display("PASS feature_extraction_tb: N_MAC=%0d, %0d images x 1568 readback activations, %0d cycles/image",
                      N_MAC, N_IMG, CYCLES);
        $finish;
    end
endmodule
`default_nettype wire
