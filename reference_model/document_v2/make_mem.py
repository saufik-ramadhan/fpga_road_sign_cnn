"""Document-specific COE, Verilog constants and 16-image bank exports."""
import json
from pathlib import Path
import numpy as np


def write_coe(path,words):
    path.write_text('memory_initialization_radix=16;\nmemory_initialization_vector=\n'+',\n'.join(words)+';\n')
    recovered=path.read_text().split('memory_initialization_vector=')[1].strip().rstrip(';').replace('\n','').split(',')
    if recovered!=words:raise AssertionError('COE round-trip failed')


def export_additional(output,params,contract):
    output=Path(output)
    for f in (output/'mem').glob('*.mem'):write_coe(f.with_suffix('.coe'),f.read_text().splitlines())
    q=contract['requantization']
    lines=['// Generated for p2-doc-int-v2. Include inside a module.',
           '// Biases and scores are SIGNED 24-bit; byte containers may be wider.',
           "`ifndef P2_DOC_INT_V2_PARAMS_VH","`define P2_DOC_INT_V2_PARAMS_VH",
           'localparam integer P2_IMAGE_SIDE = 16;',
           'localparam integer P2_FILTERS = 8;', 'localparam integer P2_CLASSES = 8;',
           'localparam integer P2_FC_INPUTS = 392;', 'localparam integer P2_ACC_BITS = 24;',
           'localparam integer P2_RESCALE_BITS = 48;',
           f"localparam [15:0] P2_RESCALE_M = 16'd{q['multiplier']};",
           f"localparam integer P2_RESCALE_S = {q['shift']};",
           f"localparam [47:0] P2_ROUND = 48'd{(1<<(q['shift']-1)) if q['shift'] else 0};"]
    for key,prefix in [('conv_bias','CONV'),('fc_bias','FC')]:
        for i,value in enumerate(params[key]):lines.append(f"localparam signed [23:0] P2_{prefix}_BIAS_{i} = 24'sh{int(value)&0xffffff:06x};")
    lines+=['`endif',''];(output/'params.vh').write_text('\n'.join(lines))
    real=[v for v in json.loads((output/'vectors/manifest.json').read_text()) if 'label' in v][:16]
    if len(real)!=16:raise ValueError('Need 16 real golden vectors')
    pixels=[];labels=[];stored=[]
    for i,v in enumerate(real):
        folder=output/'vectors'/v['name']
        words=(folder/'input.mem').read_text().splitlines();pixels+=words;labels.append(f"{v['label']:02x}")
        with np.load(folder/'layers.npz') as f:scores=f['scores'].tolist()
        stored.append(dict(index=i,source=v['source'],label=v['label'],
                           prediction=v['integer_prediction'],scores=scores))
    (output/'signs.mem').write_text('\n'.join(pixels)+'\n');write_coe(output/'signs.coe',pixels)
    (output/'labels.mem').write_text('\n'.join(labels)+'\n');write_coe(output/'labels.coe',labels)
    (output/'stored_manifest.json').write_text(json.dumps(stored,indent=2))
