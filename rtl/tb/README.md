# Verifikasi P3 — feature extraction

```powershell
python -m unittest discover -s rtl/tb -p test_run_p3_tests.py
python rtl/tb/run_p3_tests.py
```

- `conv_engine_tb.v`: accumulator, aktivasi, fmap RAM dan handshake.
- `requant_relu_tb.v`: aritmetika rescale, range, rounding dan latency.
- `p3_vectors.py`: generator directed/random; `p2_vectors.py`: adapter paket P2.
- `run_p3_tests.py`: runner simulasi; `test_run_p3_tests.py`: regresi runner.
- `p3_synth_top.v`, `synth_p3.tcl`: flow sintesis out-of-context.
- `conv_engine_tb.gtkw`: susunan waveform GTKWave.

Jalankan dari root repo. Output di `build/p3_sim/`; model dari
`reference_model/models/`. [Port dan detail pengujian](../../docs/p3_feature_extraction.md).
