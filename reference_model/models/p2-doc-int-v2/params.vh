// Generated for p2-doc-int-v2. Include inside a module.
// Biases and scores are SIGNED 24-bit; byte containers may be wider.
`ifndef P2_DOC_INT_V2_PARAMS_VH
`define P2_DOC_INT_V2_PARAMS_VH
localparam integer P2_IMAGE_SIDE = 16;
localparam integer P2_FILTERS = 8;
localparam integer P2_CLASSES = 8;
localparam integer P2_FC_INPUTS = 392;
localparam integer P2_ACC_BITS = 24;
localparam integer P2_RESCALE_BITS = 48;
localparam [15:0] P2_RESCALE_M = 16'd43980;
localparam integer P2_RESCALE_S = 25;
localparam [47:0] P2_ROUND = 48'd16777216;
localparam signed [23:0] P2_CONV_BIAS_0 = 24'sh0012b5;
localparam signed [23:0] P2_CONV_BIAS_1 = 24'shffc389;
localparam signed [23:0] P2_CONV_BIAS_2 = 24'shffe5fe;
localparam signed [23:0] P2_CONV_BIAS_3 = 24'shffd4a2;
localparam signed [23:0] P2_CONV_BIAS_4 = 24'shffddc8;
localparam signed [23:0] P2_CONV_BIAS_5 = 24'sh002f21;
localparam signed [23:0] P2_CONV_BIAS_6 = 24'shfff048;
localparam signed [23:0] P2_CONV_BIAS_7 = 24'shfffb62;
localparam signed [23:0] P2_FC_BIAS_0 = 24'sh0000d6;
localparam signed [23:0] P2_FC_BIAS_1 = 24'sh0000e4;
localparam signed [23:0] P2_FC_BIAS_2 = 24'shfffe68;
localparam signed [23:0] P2_FC_BIAS_3 = 24'sh000092;
localparam signed [23:0] P2_FC_BIAS_4 = 24'sh000131;
localparam signed [23:0] P2_FC_BIAS_5 = 24'shffff51;
localparam signed [23:0] P2_FC_BIAS_6 = 24'shffff8a;
localparam signed [23:0] P2_FC_BIAS_7 = 24'shffff48;
`endif
