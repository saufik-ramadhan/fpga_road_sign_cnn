`timescale 1ns / 1ps
`default_nettype none
module top_basys3_tb;
    parameter CONV_MAC = 1, FC_MAC = 1;
    localparam CPB=16;
    reg clk=0;
    always #5 clk=~clk;
    reg rx=1, button=0;
    reg [15:0] sw=0;
    wire tx, dp;
    wire [15:0] led;
    wire [6:0] seg;
    wire [3:0] an;
    `ifdef TEST_D42
    `include "params.vh"
    `endif
    top_basys3 #(
        `ifdef TEST_D42
        .M(D42_CONV_M), .S(D42_CONV_S), .ENABLE_CONV2(1),
        .CONV2_M(D42_CONV2_M), .CONV2_S(D42_CONV2_S),
        `endif
        .N_MAC(CONV_MAC), .FC_MAC(FC_MAC), .CLKS_PER_BIT(CPB), .TIMEOUT_CLKS(3000),
        .BUTTON_STABLE_CLKS(4), .DISPLAY_DIGIT_CLKS(4)) dut (
        .clk(clk), .RsRx(rx), .RsTx(tx), .btnC(button), .sw(sw),
        .led(led), .seg(seg), .an(an), .dp(dp)
    );
    reg [23:0] stored_scores[0:127], live_scores[0:7];
    reg [7:0] stored_prediction[0:15], live_prediction[0:0], pixels[0:255], reply[0:31];
    integer completions=0, starts=0, tx_starts=0, i, j, observed_cycles;
    reg [7:0] checksum;
    always @(posedge clk) begin
        if(dut.done) completions=completions+1;
        if(dut.core_start) starts=starts+1;
        if(dut.u_comm.tx_send) tx_starts=tx_starts+1;
    end
    task press(input [3:0] selection);
        begin
            sw={12'd0,selection}; repeat(5) @(negedge clk);
            button=1; repeat(15) @(negedge clk); button=0;
            repeat(10) @(negedge clk);
        end
    endtask
    task check_stored(input integer selection);
        integer k;
        begin
            while(dut.done!==1) @(negedge clk);
            if(dut.class_id!==stored_prediction[selection][2:0] || dut.overflow!==0)
                $fatal(1,"FAIL stored prediction/overflow selection %0d",selection);
            for(k=0;k<8;k=k+1)
                if(dut.scores[24*k +:24]!==stored_scores[selection*8+k])
                    $fatal(1,"FAIL stored scores selection %0d class %0d",selection,k);
            @(negedge clk);
        end
    endtask
    task send_byte(input [7:0] value);
        integer b;
        begin
            rx=0; repeat(CPB) @(negedge clk);
            for(b=0;b<8;b=b+1) begin rx=value[b]; repeat(CPB) @(negedge clk); end
            rx=1; repeat(CPB) @(negedge clk);
        end
    endtask
    task send_request;
        integer k;
        reg [7:0] sum;
        begin
            sum=1; send_byte(8'ha5); send_byte(1);
            for(k=0;k<256;k=k+1) begin send_byte(pixels[k]); sum=sum+pixels[k]; end
            send_byte(sum);
        end
    endtask
    task receive_reply;
        integer k,b;
        begin
            for(k=0;k<32;k=k+1) begin
                @(negedge tx); repeat(CPB+CPB/2) @(negedge clk);
                for(b=0;b<8;b=b+1) begin reply[k][b]=tx; repeat(CPB) @(negedge clk); end
                if(tx!==1) $fatal(1,"FAIL UART reply stop bit");
            end
        end
    endtask
    initial begin
        $readmemh("stored_scores.mem",stored_scores); $readmemh("stored_prediction.mem",stored_prediction);
        $readmemh("live_pixels.mem",pixels); $readmemh("live_scores.mem",live_scores);
        $readmemh("live_prediction.mem",live_prediction);
        repeat(20) @(negedge clk);
        for(i=0;i<16;i=i+1) begin
            press(i);
            // Changes/extra presses while busy must not change the input bank.
            sw[3:0]=15-i;
            if(i==0) begin button=1; repeat(40) @(negedge clk); button=0; end
            check_stored(i);
            if(led[14]!==1 || led[15]!==0 || led[3]!==1) $fatal(1,"FAIL stored LED state");
            if(tx_starts!=0) $fatal(1,"FAIL unsolicited stored UART reply");
        end
        if(starts!=16) $fatal(1,"FAIL debounce/busy gating %0d starts",starts);
        // Finish a UART upload during a stored run: queue it, preserve stored
        // pixels, then execute the real live CNN and return its complete scores.
        fork
            send_request;
            receive_reply;
            begin repeat(33000) @(negedge clk); press(3); check_stored(3); end
        join
        checksum=0; for(j=1;j<31;j=j+1) checksum=checksum+reply[j];
        if(reply[0]!==8'h5a || reply[1]!==0 || reply[2]!==live_prediction[0] || reply[31]!==checksum)
            $fatal(1,"FAIL live UART header/class/checksum");
        observed_cycles={reply[3],reply[4],reply[5],reply[6]};
        if(observed_cycles!==dut.cycles || observed_cycles==0) $fatal(1,"FAIL UART cycle count");
        for(j=0;j<8;j=j+1)
            if({reply[7+3*j],reply[8+3*j],reply[9+3*j]}!==live_scores[j])
                $fatal(1,"FAIL UART signed score order class %0d",j);
        if(starts!=18 || completions!=18 || dut.pending_uart!==0 || tx_starts!=32)
            $fatal(1,"FAIL request queue counts: starts %0d completions %0d bytes %0d",starts,completions,tx_starts);
        // Each digit is scanned; known segment outputs and DP stays off.
        repeat(16) begin
            @(negedge clk);
            if(dp!==1 || (an!==4'b1110 && an!==4'b1101 && an!==4'b1011 && an!==4'b0111) || ^seg===1'bx)
                $fatal(1,"FAIL display scan");
        end
        $display("PASS top_basys3_tb: 16 stored + queued stored/live UART, complete golden scores, switch latch/button/display/status");
        $finish;
    end
    initial begin #30_000_000; $fatal(1,"FAIL board-top watchdog"); end
endmodule
`default_nettype wire
