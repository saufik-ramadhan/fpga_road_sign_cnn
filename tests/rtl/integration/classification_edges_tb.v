`timescale 1ns / 1ps
`default_nettype none
module classification_edges_tb;
    reg clk=0;
    always #5 clk=~clk;
    reg rst=1, fc_start=0, arg_start=0;
    wire fc_busy, fc_done, ovf, arg_busy, arg_done;
    wire [8:0] addr;
    wire [191:0] fc_scores;
    reg [191:0] test_scores;
    wire [2:0] prediction;
    fc_engine #(.WEIGHT_FILE("edge_weight.mem"), .BIAS_FILE("edge_bias.mem")) fc (
        .clk(clk), .rst(rst), .start(fc_start), .busy(fc_busy), .done(fc_done),
        .ovf(ovf), .pool_addr(addr), .pool_data(8'd127), .scores(fc_scores)
    );
    argmax arg (.clk(clk), .rst(rst), .start(arg_start), .scores(test_scores),
        .busy(arg_busy), .done(arg_done), .class_id(prediction));
    task check_arg(input [2:0] want);
        begin
            arg_start=1; @(negedge clk); arg_start=0;
            while(arg_done!==1) @(negedge clk);
            if(prediction!==want) $fatal(1,"FAIL signed/tie argmax expected %0d got %0d",want,prediction);
            @(negedge clk);
        end
    endtask
    integer i;
    initial begin
        repeat(4) @(negedge clk); rst=0;
        test_scores={8{24'hffffff}}; check_arg(0); // all negative, first tie
        test_scores[24*7 +:24]=24'h000001; check_arg(7); // last class positive
        test_scores[24*3 +:24]=24'h000001; check_arg(3); // first equal maximum
        test_scores={8{24'h800000}}; test_scores[24*5 +:24]=24'hffffff; check_arg(5);
        fc_start=1; @(negedge clk); fc_start=0;
        while(fc_done!==1) @(negedge clk);
        // +127 then -127 cancel in the final sum, but the first step overflows.
        if(ovf!==1 || fc_scores[23:0]!==24'h7ffff0) $fatal(1,"FAIL partial-sum overflow detection");
        for(i=1;i<8;i=i+1) if(fc_scores[24*i +:24]!==0) $fatal(1,"FAIL zero FC row");
        $display("PASS classification_edges_tb: signed argmax/ties and canceled partial-sum overflow");
        $finish;
    end
    initial begin #1_000_000; $fatal(1,"FAIL classification watchdog"); end
endmodule
`default_nettype wire
