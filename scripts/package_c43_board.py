"""Prepare the local C-43 seed 44 package from verified official-test outputs."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('vectors', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    source, out = args.vectors, args.output
    metadata = json.loads((source / 'rtl_vectors.json').read_text())
    result = json.loads((source / 'official_metrics.json').read_text())
    if (result['parameters_sha256'], metadata['multiplier'], metadata['shift']) != (
            '8527f1289204aaaaf684b6bbbd8bf14555090ce984393766173057512ae29a2b', 38660, 24):
        raise ValueError('Expected C-43 seed 44 frozen parameters')
    pixels = (source / 'input.mem').read_text().splitlines()
    predictions = (source / 'prediction.mem').read_text().splitlines()
    indices = [i * 42 // 15 for i in range(16)]
    (out / 'mem').mkdir(parents=True)
    for name in ('conv_weight', 'conv_bias', 'fc_weight', 'fc_bias'):
        shutil.copyfile(source / (name + '.mem'), out / 'mem' / (name + '.mem'))
    (out / 'signs.mem').write_bytes(('\n'.join(word for i in indices for word in pixels[i*256:(i+1)*256]) + '\n').encode())
    (out / 'stored_manifest.json').write_text(json.dumps([
        dict(index=slot, source=metadata['sources'][i], golden_class=int(predictions[i], 16))
        for slot, i in enumerate(indices)
    ], indent=2))
    (out / 'contract.json').write_text(json.dumps(dict(
        version='p2-doc-c43-s44-int24-v1', seed=44, classes=43, filters=16,
        multiplier=38660, shift=24, input_shape=[1, 16, 16], features=784,
        score_bits=24, mode='stored only', checkpoint_sha256=result['checkpoint_sha256'],
        parameters_sha256=result['parameters_sha256']
    ), indent=2))
    files = sorted(out.rglob('*'))
    (out / 'checksums.json').write_text(json.dumps({
        path.relative_to(out).as_posix(): sha(path) for path in files if path.is_file()
    }, indent=2))


if __name__ == '__main__':
    main()
