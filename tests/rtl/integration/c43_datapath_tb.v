`timescale 1ns / 1ps
`default_nettype none

module c43_datapath_tb;
    parameter N_IMG = 46;
    parameter [15:0] M = 38660;
    parameter S = 24;
    localparam FM_DEPTH = 3136, FEATURES = 784, CLASSES = 43;
    reg clk = 0;
    always #5 clk = !clk;
    reg rst = 1, start = 0;
    reg [7:0] pixels [0:N_IMG*256-1];
    reg signed [23:0] expected_acc [0:N_IMG*FM_DEPTH-1];
    reg [7:0] expected_activation [0:N_IMG*FM_DEPTH-1];
    reg [7:0] expected_pool [0:N_IMG*FEATURES-1];
    reg signed [23:0] expected_scores [0:N_IMG*CLASSES-1];
    reg [7:0] expected_class [0:N_IMG-1];
    reg [7:0] pool_mem [0:FEATURES-1];
    reg [7:0] pix_data, fc_data;
    wire [7:0] pix_addr, fm_write_data, fm_read_data, pool_data;
    wire [11:0] fm_write_addr, fm_read_addr;
    wire [9:0] pool_write_addr, pool_read_addr;
    wire conv_done, pool_done, fc_done, arg_done, fm_we, pool_we, conv_ovf, fc_ovf;
    wire [24*CLASSES-1:0] scores;
    wire [5:0] class_id;
    integer image = 0, act_count = 0, acc_count = 0, pool_count = 0;
    integer cycles, latency, k;
    reg checking = 0;

    conv_engine #(.FILTERS(16), .FILTER_W(4), .FM_ADDR_W(12), .M(M), .S(S)) conv (
        .clk(clk), .rst(rst), .start(start), .busy(), .done(conv_done), .ovf(conv_ovf),
        .pix_rd(), .pix_addr(pix_addr), .pix_data(pix_data),
        .fm_we(fm_we), .fm_addr(fm_write_addr), .fm_data(fm_write_data)
    );
    fmap_ram #(.DEPTH(FM_DEPTH), .ADDR_W(12)) fmap (
        .clk(clk), .we(fm_we), .waddr(fm_write_addr), .wdata(fm_write_data),
        .raddr(fm_read_addr), .rdata(fm_read_data)
    );
    maxpool2d #(.FILTERS(16), .FILTER_W(4), .FM_ADDR_W(12), .POOL_ADDR_W(10)) pool (
        .clk(clk), .rst(rst), .start(conv_done), .busy(), .done(pool_done),
        .fmap_addr(fm_read_addr), .fmap_data(fm_read_data),
        .pool_we(pool_we), .pool_addr(pool_write_addr), .pool_data(pool_data)
    );
    fc_engine #(.FEATURES(FEATURES), .CLASSES(CLASSES), .FEATURE_W(10),
                .CLASS_W(6), .WEIGHT_ADDR_W(16)) fc (
        .clk(clk), .rst(rst), .start(pool_done), .busy(), .done(fc_done), .ovf(fc_ovf),
        .pool_addr(pool_read_addr), .pool_data(fc_data), .scores(scores)
    );
    argmax #(.CLASSES(CLASSES), .CLASS_W(6)) argmax_dut (
        .clk(clk), .rst(rst), .start(fc_done), .busy(), .done(arg_done),
        .scores(scores), .class_id(class_id)
    );

    task fail;
        input [255:0] stage;
        input integer index;
        begin
            $display("FAIL %0s image=%0d index=%0d", stage, image, index);
            $finish;
        end
    endtask

    always @(posedge clk) begin
        pix_data <= pixels[image*256 + pix_addr];
        fc_data <= pool_mem[pool_read_addr];
        if (pool_we)
            pool_mem[pool_write_addr] <= pool_data;
        if (checking) begin
            if (conv.acc_valid) begin
                if (conv.acc_oaddr !== acc_count[11:0] ||
                    conv.acc !== expected_acc[image*FM_DEPTH + acc_count])
                    fail("Conv accumulator", acc_count);
                acc_count = acc_count + 1;
            end
            if (fm_we) begin
                if (fm_write_addr !== act_count[11:0] ||
                    fm_write_data !== expected_activation[image*FM_DEPTH + act_count])
                    fail("Conv activation", act_count);
                act_count = act_count + 1;
            end
            if (pool_we) begin
                if (pool_write_addr !== pool_count[9:0] ||
                    pool_data !== expected_pool[image*FEATURES + pool_count])
                    fail("pool", pool_count);
                pool_count = pool_count + 1;
            end
        end
    end

    initial begin
        $readmemh("input.mem", pixels);
        $readmemh("conv_acc.mem", expected_acc);
        $readmemh("activation.mem", expected_activation);
        $readmemh("pool.mem", expected_pool);
        $readmemh("scores.mem", expected_scores);
        $readmemh("prediction.mem", expected_class);
        repeat (2) @(negedge clk);
        rst = 0;
        latency = 0;
        for (image = 0; image < N_IMG; image = image + 1) begin
            act_count = 0;
            acc_count = 0;
            pool_count = 0;
            checking = 1;
            start = 1;
            @(negedge clk);
            start = 0;
            cycles = 0;
            while (arg_done !== 1 && cycles < 110000) begin
                @(negedge clk);
                cycles = cycles + 1;
            end
            if (arg_done !== 1 || conv_ovf !== 0 || fc_ovf !== 0)
                fail("timeout or overflow", cycles);
            if (act_count != FM_DEPTH || acc_count != FM_DEPTH || pool_count != FEATURES)
                fail("layer count", pool_count);
            for (k = 0; k < CLASSES; k = k + 1)
                if (scores[24*k +: 24] !== expected_scores[image*CLASSES + k])
                    fail("FC score", k);
            if ({2'b0, class_id} !== expected_class[image])
                fail("argmax", class_id);
            if (image == 0) latency = cycles;
            if (latency != cycles) fail("latency", cycles);
            checking = 0;
            @(negedge clk);
            if (arg_done !== 0) fail("done pulse", cycles);
        end
        $display("PASS C-43 datapath: %0d images, all layers and 43 scores bit-exact, %0d cycles", N_IMG, latency);
        $finish;
    end
endmodule

`default_nettype wire
