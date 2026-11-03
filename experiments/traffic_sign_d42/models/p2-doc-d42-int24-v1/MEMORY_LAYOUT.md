# D42 memory layout

One hexadecimal word per line. Multi-dimensional arrays flatten in C order.
Conv weights are OIHW; FC weights are [class, CHW feature]. Weights are signed8.
Bias, conv_acc, conv2_acc and scores are signed24 two's complement.
Input is CHW 1×16×16. Conv1 acc and activation are 8×14×14.
Pool, Conv2 acc and activation2 are 8×7×7. FC uses activation2, not pool.
Scores are in class-index order. signs.mem contains 16 row-major images.
labels.mem contains ground truth; stored_manifest.json has golden predictions.
This is an experimental software reference for future D42 RTL.
