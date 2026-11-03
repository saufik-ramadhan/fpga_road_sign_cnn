`timescale 1ns / 1ps
`default_nettype none
`ifndef N_IMG
`define N_IMG 25
`endif
module cnn_core_tb;
    parameter CONV_MAC = 1, FC_MAC = 1;
    reg clk=0;
    always #5 clk=~clk;
    reg rst=1, start=0;
    wire busy, done, ovf, pix_rd;
    wire [7:0] pix_addr;
    reg [7:0] pix_data;
    wire [2:0] class_id;
    wire [191:0] scores;
    wire [31:0] cycles;
`ifdef TEST_D42
    `include "params.vh"
    cnn_core #(.M(D42_CONV_M), .S(D42_CONV_S), .ENABLE_CONV2(1),
               .CONV2_M(D42_CONV2_M), .CONV2_S(D42_CONV2_S)) dut (
`else
    cnn_core #(.N_MAC(CONV_MAC), .FC_MAC(FC_MAC)) dut (
`endif
        .clk(clk), .rst(rst), .start(start), .busy(busy), .done(done), .ovf(ovf),
        .cycles(cycles), .pix_addr(pix_addr), .pix_rd(pix_rd), .pix_data(pix_data),
        .class_id(class_id), .scores(scores)
    );
    reg [7:0] pixels[0:`N_IMG*256-1], pools[0:`N_IMG*392-1], predictions[0:`N_IMG-1];
    reg [23:0] expected_scores[0:`N_IMG*8-1];
    integer image=0, count, first_cycles=0, checked_pool=0, i;
`ifdef TEST_D42
    reg [23:0] acc1[0:`N_IMG*1568-1], acc2[0:`N_IMG*392-1];
    reg [7:0] act1[0:`N_IMG*1568-1], act2[0:`N_IMG*392-1];
    integer n_acc1=0, n_act1=0, n_act2=0;
    initial begin
        $readmemh("conv_acc.mem",acc1); $readmemh("activation.mem",act1);
        $readmemh("conv2_acc.mem",acc2); $readmemh("activation2.mem",act2);
    end
    always @(posedge clk) begin
        if (rst) begin n_acc1=0; n_act1=0; n_act2=0; end
        else begin
            if (dut.u_features.u_conv.acc_valid) begin
                if (dut.u_features.u_conv.acc !== acc1[image*1568+dut.u_features.u_conv.acc_oaddr])
                    $fatal(1,"FAIL Conv1 accumulator image %0d",image);
                n_acc1=n_acc1+1;
            end
            if (dut.u_features.fm_we) begin
                if (dut.u_features.fm_data !== act1[image*1568+dut.u_features.fm_addr])
                    $fatal(1,"FAIL Conv1 activation image %0d",image);
                n_act1=n_act1+1;
            end
            if (dut.u_classifier.d42.write_en) begin
                if (dut.u_classifier.d42.u_conv2.acc !== acc2[image*392+dut.u_classifier.d42.addr]
                        || dut.u_classifier.d42.data !== act2[image*392+dut.u_classifier.d42.addr])
                    $fatal(1,"FAIL Conv2 image %0d address %0d",image,dut.u_classifier.d42.addr);
                n_act2=n_act2+1;
            end
        end
    end
`endif
    always @(posedge clk) begin
        pix_data <= pix_rd ? pixels[image*256+pix_addr] : 8'hxx;
        if (rst) checked_pool=0;
        else if (dut.u_classifier.pool_we) begin
            if (dut.u_classifier.write_data !== pools[image*392+dut.u_classifier.write_addr])
                $fatal(1,"FAIL pool mismatch image %0d address %0d", image,dut.u_classifier.write_addr);
            checked_pool=checked_pool+1;
        end
    end
    initial begin
        $readmemh("pixels.mem",pixels); $readmemh("pool.mem",pools);
        $readmemh("scores.mem",expected_scores); $readmemh("prediction.mem",predictions);
        repeat(4) @(negedge clk); rst=0;
        // Reset during convolution must discard that run and recover cleanly.
        start=1; @(negedge clk); start=0;
`ifdef TEST_D42
        wait(dut.u_classifier.conv2_start);
`endif
        repeat(100) @(negedge clk); rst=1;
        repeat(3) @(negedge clk); rst=0;
        if(busy!==0 || done!==0) $fatal(1,"FAIL reset recovery");
        for(image=0; image<`N_IMG; image=image+1) begin
            start=1; @(negedge clk); start=0; count=0;
            while(done!==1 && count<100000) begin
                @(negedge clk); count=count+1;
`ifdef TEST_D42
                start=(image==1 && count==20000);
`else
                start=(image==1 && count==1000);
`endif
            end
            start=0;
            if(done!==1 || busy!==0 || ovf!==0 || cycles!==count)
                $fatal(1,"FAIL CNN handshake/count/overflow image %0d, observed %0d reported %0d",image,count,cycles);
            if(image==0) first_cycles=count;
            if(count!=first_cycles) $fatal(1,"FAIL non-deterministic latency");
            if(class_id!==predictions[image][2:0]) $fatal(1,"FAIL prediction image %0d",image);
            for(i=0;i<8;i=i+1)
                if(scores[24*i +: 24]!==expected_scores[image*8+i])
                    $fatal(1,"FAIL score image %0d class %0d got %h expected %h",image,i,scores[24*i +: 24],expected_scores[image*8+i]);
            @(negedge clk);
            if(done!==0) $fatal(1,"FAIL done not one-cycle");
        end
        if(checked_pool!=`N_IMG*392) $fatal(1,"FAIL pool write count %0d",checked_pool);
`ifdef TEST_D42
        if(n_acc1!=`N_IMG*1568 || n_act1!=`N_IMG*1568 || n_act2!=`N_IMG*392)
            $fatal(1,"FAIL D42 layer write counts");
        $display("D42: Conv1 and Conv2 accumulators and activations checked");
`else
        if(first_cycles != (CONV_MAC == 1 ? 14117 : CONV_MAC == 3 ? 4770 : 1636)
                         + 3153 + 6272/FC_MAC) $fatal(1,"FAIL baseline latency changed");
`endif
        $display("PASS cnn_core_tb: %0d images, all pool/features, 8 signed24 scores and predictions; %0d cycles/image, reset/busy restart",`N_IMG,first_cycles);
        $finish;
    end
    initial begin #30_000_000; $fatal(1,"FAIL core watchdog"); end
endmodule
`default_nettype wire
