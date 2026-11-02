# Memory layout for p2-int-32-v1

One hex word per line, no header. Negative words use two's complement.
conv_weight: [filter, input_channel, kernel_row, kernel_column], int8.
fc_weight: [output_class, CHW_input_index], int8. Biases are int32.
Images: CHW [1,32,32], uint8. Conv accumulators: [8,30,30], int32.
Activation: [8,30,30], uint8. Pool: [8,15,15], uint8. Scores: [8], int32.
Argmax output: one uint8 word. All arrays use C order, last axis changes fastest.
Each weight/bias layer has a separate file starting at address zero.
Within a word, hexadecimal digits are most significant first; UART byte order is not defined here.
See contract.json for multiplier/shift, exact rounding and scales.
Synthetic vectors have no class label. No RTL simulator has been run.
