"""Copy a verified integer parameter package into a Git-visible model directory."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path


def publish(source, destination):
    if destination.exists():
        raise FileExistsError('Use a new version directory; existing packages are not overwritten')
    source_hashes=json.loads((source/'checksums.json').read_text())
    files=['contract.json','parameters.npz','metrics.json','MEMORY_LAYOUT.md',
           'mem/conv_weight.mem','mem/conv_bias.mem','mem/fc_weight.mem','mem/fc_bias.mem']
    for name in files:
        if hashlib.sha256((source/name).read_bytes()).hexdigest()!=source_hashes[name]:
            raise ValueError(f'Source checksum mismatch: {name}')
    for name,count,width in [('conv_weight',72,2),('conv_bias',8,8),('fc_weight',3136,2),('fc_bias',8,8)]:
        words=(source/'mem'/f'{name}.mem').read_text().splitlines()
        if len(words)!=count or any(len(w)!=width or any(c not in '0123456789abcdefABCDEF' for c in w) for w in words):
            raise ValueError(f'Invalid memory encoding/depth: {name}')
    destination.mkdir(parents=True)
    for name in files:
        target=destination/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source/name,target)
    # Preserve byte checksums across Windows and Unix clones.
    (destination/'.gitattributes').write_bytes(b'* -text\n')
    (destination/'README.md').write_text('''# RTL parameter package p2-int-v1

Git-visible snapshot of the validated 16x16 eight-class integer model.
Status: provisional numerical contract for RTL review; no RTL/board validation yet.

## Files

- mem/conv_weight.mem: 72 signed 8-bit weights, OIHW order.
- mem/conv_bias.mem: eight signed 32-bit biases.
- mem/fc_weight.mem: 3,136 signed 8-bit weights, output class then CHW feature.
- mem/fc_bias.mem: eight signed 32-bit biases.
- contract.json: class mapping, widths, scales, M=34172, S=25 and bounds.
- MEMORY_LAYOUT.md: detailed word layout and ordering.
- parameters.npz: the same integer parameter arrays for Python.
- metrics.json: validation evidence (float and integer both 97.50%).
- checksums.json: SHA256 of package files, excluding itself.

One hexadecimal word per line, signed values use two's complement.
Each memory starts at zero. Keep the entire package together.
The local .gitattributes preserves exact bytes across Git checkouts.

## RTL loading

From a simulator launched at the repository root:

```systemverilog
logic signed [7:0] conv_weights [0:71];
initial $readmemh("reference_model/models/p2-int-v1/mem/conv_weight.mem", conv_weights);
```

Load biases and FC parameters similarly with the documented widths/depths.
Use the rescale formula in contract.json; weights alone are not the full model.
Internal memory latency, start/done and UART interfaces still require agreement.

## Integrity check from repository root

```powershell
python -c "import hashlib,json; from pathlib import Path; p=Path('reference_model/models/p2-int-v1'); h=json.loads((p/'checksums.json').read_text()); assert all(hashlib.sha256((p/k).read_bytes()).hexdigest()==v for k,v in h.items()); print('Checksums OK')"
```

No dataset images, training caches or vector images are included here.
The 25 golden layer-vector packages remain under local build/reference_model/integer_v1/vectors/.
Obtain those from P2 separately for RTL simulation; cloning only this package provides parameters.
See reference_model/INTEGER_CONTRACT.md and docs/P2_to_RTL_Handoff.docx.
The older handoff document uses local build paths; use this folder's mem/ paths for shared weights.

The selected float checkpoint hash is recorded in contract.json. Its checkpoint
and training artifacts remain in ignored build/; they are not required to load these RTL weights.
''',encoding='utf-8')
    hashes={p.relative_to(destination).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(destination.rglob('*')) if p.is_file()}
    (destination/'checksums.json').write_text(json.dumps(hashes,indent=2),encoding='utf-8')
    assert all(hashlib.sha256((destination/k).read_bytes()).hexdigest()==v for k,v in hashes.items())
    print(f'Published {len(hashes)+1} verified files to {destination}')


if __name__=='__main__':
    root=Path(__file__).resolve().parents[1]
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=root/'build/reference_model/integer_v1')
    parser.add_argument('--destination',type=Path,default=root/'reference_model/models/p2-int-v1')
    args=parser.parse_args();publish(args.source,args.destination)
