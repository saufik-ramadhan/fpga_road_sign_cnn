"""Publish a complete document-v2 review package outside ignored build/."""
import argparse,hashlib,json,shutil
from pathlib import Path


def publish(source,target):
    if target.exists():raise FileExistsError('Choose a new version; never overwrite a published package')
    hashes=json.loads((source/'checksums.json').read_text())
    for name,digest in hashes.items():
        if hashlib.sha256((source/name).read_bytes()).hexdigest()!=digest:raise ValueError(name)
    target.mkdir(parents=True)
    files=['contract.json','parameters.npz','metrics.json','MEMORY_LAYOUT.md','params.vh',
           'signs.mem','signs.coe','labels.mem','labels.coe','stored_manifest.json']
    files += [p.relative_to(source).as_posix() for folder in ('mem','vectors') for p in (source/folder).rglob('*') if p.is_file()]
    for name in files:
        dest=target/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/name,dest)
    (target/'.gitattributes').write_bytes(b'* -text\n')
    (target/'README.md').write_text('''# p2-doc-int-v2 review package

Document-based 16x16 eight-class candidate. This package supersedes p2-int-v1
as the current review candidate, not a team-approved hardware release.

- Preprocessing: crop ROI, grayscale, Pillow histogram equalization, bilinear resize.
- Class indices: Stop, Yield, No entry, Priority road, General caution, Keep right, 30, 50.
- Signed weights: int8; biases, MAC accumulators and scores: logical int24.
- Activation: 0..127 in uint8 storage. Rescale intermediate: signed 48-bit.
- Actual multiplier and shift are in contract.json and params.vh. Never reuse v1 constants.
- Float validation accuracy 96.92%; integer 96.63%. Speed-limit 30 integer recall 85.56%.
- 95% overall threshold met on validation; official test and hardware results are pending.

mem/: weight and bias files for readmemh, plus matching .coe files.
params.vh: include inside the consuming module; contains dimensions, rescale and biases.
vectors/: 20 real and five synthetic input/layer-output packages with a source manifest.
signs.mem / signs.coe: 16 stored pictures, 256 bytes each, stored_index*256+pixel_address.
labels.mem / labels.coe: 16 ground-truth class indices, not golden predictions.
stored_manifest.json: picture indices, source IDs, labels, predictions and golden scores.
Synthetic vectors have no semantic label. Golden scores and labels are distinct.

All .mem files contain one hexadecimal word per line. Signed int24 uses six hex
digits in two's complement. Activations/pixels use two digits. C/CHW flattening
and memory addresses are described in MEMORY_LAYOUT.md and contract.json.
Parameters.npz uses wider NumPy containers for logical int24 data.

checksums.json covers this package except itself. The local .gitattributes
preserves exact bytes across checkouts. No real FPGA cycle counts are provided.
The 31-byte reply metadata is a protocol target: P5 has not been migrated here.
No RTL/board test is claimed. Python scalar/vectorized arithmetic matched 25 vectors.
''')
    checks={p.relative_to(target).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(target.rglob('*')) if p.is_file()}
    (target/'checksums.json').write_text(json.dumps(checks,indent=2))
    print('Published review package',target,'files',len(checks)+1)


if __name__=='__main__':
    root=Path(__file__).resolve().parents[2]
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=root/'build/reference_model/document_integer_v2_checked')
    parser.add_argument('--destination',type=Path,default=root/'reference_model/models/p2-doc-int-v2')
    args=parser.parse_args();publish(args.source,args.destination)
