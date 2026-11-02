// image_input.v  -  P5 "Image input" box
// Holds two sources of pictures and lets the CNN read ONE of them:
//   live_mode = 1 : the picture the laptop just sent  (SW15 = 1)
//   live_mode = 0 : one of the 16 stored signs        (SW3..SW0 choose which)
// The CNN reads a pixel by giving an address (0..255); the pixel comes out
// ONE clock tick later.
module image_input #(
    parameter STORED_FILE = ""              // P2's .mem file (4096 lines of hex). "" = dummy pictures
)(
    input  wire       clk,
    input  wire       live_mode,            // SW15
    input  wire [3:0] stored_sel,           // SW3..SW0

    // write side: used by frame_ctrl when a picture arrives from the laptop
    input  wire       we,
    input  wire [7:0] waddr,
    input  wire [7:0] wdata,

    // read side: used by the CNN
    input  wire [7:0] raddr,
    output wire [7:0] rdata
);
    reg [7:0] live_ram   [0:255];           // 1 picture  (16 x 16 pixels)
    reg [7:0] stored_rom [0:4095];          // 16 pictures x 256 pixels

    integer i;
    initial begin
        for (i = 0; i < 256; i = i + 1) live_ram[i] = 8'd0;
        if (STORED_FILE != "")
            $readmemh(STORED_FILE, stored_rom);
        else                                // dummy pictures: picture n has n pixels equal to 1, the rest 0
            for (i = 0; i < 4096; i = i + 1)
                stored_rom[i] = (i[7:0] < i[11:8]) ? 8'd1 : 8'd0;
    end

    reg [7:0] live_pixel   = 8'd0;
    reg [7:0] stored_pixel = 8'd0;

    always @(posedge clk) begin
        if (we) live_ram[waddr] <= wdata;           // laptop writes
        live_pixel   <= live_ram[raddr];            // CNN reads (both memories)
        stored_pixel <= stored_rom[{stored_sel, raddr}];
    end

    assign rdata = live_mode ? live_pixel : stored_pixel;   // SW15 picks the source
endmodule
