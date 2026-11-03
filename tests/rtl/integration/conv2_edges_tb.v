`timescale 1ns / 1ps
`default_nettype none
module conv2_edges_tb;
    reg clk=0;
    always #5 clk=~clk;
    reg rst=1, start=0;
    reg [7:0] input_value=127;
    reg [7:0] read_data;
    wire done, ovf, write_en;
    wire [8:0] read_addr, write_addr;
    wire [7:0] write_data;
    conv2_padded #(.WEIGHT_FILE("conv2_edge_weight.mem"),
                   .BIAS_FILE("conv2_edge_bias.mem")) dut (
        .clk(clk), .rst(rst), .start(start), .done(done), .ovf(ovf),
        .read_addr(read_addr), .read_data(read_data), .write_en(write_en),
        .write_addr(write_addr), .write_data(write_data)
    );
    always @(posedge clk) read_data <= input_value;
    initial begin
        repeat(3) @(negedge clk); rst=0;
        start=1; @(negedge clk); start=0;
        wait(write_en === 1'b1);
        // Center and right taps cancel at (0,0), but the first tap overflowed.
        if(write_addr!==0 || dut.acc!==24'h7ffff0 || ovf!==1)
            $fatal(1,"FAIL Conv2 partial-sum overflow detection");
        @(negedge clk); rst=1; input_value=0;
        repeat(3) @(negedge clk); rst=0;
        start=1; @(negedge clk); start=0;
        wait(done === 1'b1);
        if(ovf!==0) $fatal(1,"FAIL Conv2 overflow did not clear");
        $display("PASS conv2_edges_tb: canceled partial overflow and reset recovery");
        $finish;
    end
    initial begin #1_000_000; $fatal(1,"FAIL Conv2 edge watchdog"); end
endmodule
`default_nettype wire
