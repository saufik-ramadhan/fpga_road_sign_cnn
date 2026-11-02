`timescale 1ns / 1ps
`default_nettype none

// Existing P5 stored-image input drives the P3 public wrapper directly.
// This is an inter-subsystem timing test, not a complete CNN classifier.
module subsystems_tb;
    `include "params.vh"
    reg clk=0;
    always #5 clk=~clk;
    reg rst=1, start=0;
    reg [3:0] selected=0;
    wire [7:0] pixel_address, pixel;
    wire pix_rd, busy, done, ovf, uart_start, uart_err, tx;
    reg [10:0] rd_addr=0;
    wire [7:0] rd_data;
    comm_top #(.STORED_FILE("signs.mem")) input_subsystem (
        .clk(clk), .rx(1'b1), .tx(tx), .live_mode(1'b0), .stored_sel(selected),
        .img_raddr(pixel_address), .img_rdata(pixel), .cnn_start(uart_start),
        .cnn_done(1'b0), .cnn_class(3'd0), .cnn_scores(192'd0), .cnn_cycles(32'd0),
        .uart_err(uart_err)
    );
    feature_extraction #(.M(CONV_M), .S(CONV_S), .ACC_W(CONV_ACC_W)) features (
        .clk(clk), .rst(rst), .start(start), .busy(busy), .done(done), .ovf(ovf),
        .pix_rd(pix_rd), .pix_addr(pixel_address), .pix_data(pixel),
        .rd_addr(rd_addr), .rd_data(rd_data)
    );
    reg [7:0] expected[0:16*1568-1];
    integer image, address, cycles, errors=0;
    initial begin
        $readmemh("stored_conv_out.mem",expected);
        repeat(4) @(negedge clk);
        rst=0;
        for(image=0; image<16; image=image+1) begin
            @(negedge clk);selected=image;
            @(negedge clk);start=1;
            @(negedge clk);start=0;
            cycles=0;
            while(done!==1'b1 && cycles<100000) begin
                @(negedge clk);cycles=cycles+1;
            end
            if(done!==1'b1 || busy!==0 || ovf!==0 || cycles!=14117) begin
                $display("FAIL subsystems_tb: stored image %0d handshake/cycles",image);
                $finish;
            end
            rd_addr=0;
            for(address=0; address<1568; address=address+1) begin
                @(negedge clk);
                if(rd_data!==expected[image*1568+address]) errors=errors+1;
                rd_addr=address+1;
            end
            if(uart_start!==0 || uart_err!==0) errors=errors+1;
        end
        if(errors) $display("FAIL subsystems_tb: %0d stored-input/readback mismatches",errors);
        else $display("PASS subsystems_tb: P5 stored input -> P3, 16 images x 1568 activations, 14117 cycles/image");
        $finish;
    end
endmodule
`default_nettype wire
