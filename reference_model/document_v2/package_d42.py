"""Seal the D seed 42 software reference for subsequent RTL implementation."""
import argparse
import json
from pathlib import Path
import shutil
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from document_v2.quantize import bound, write_mem
from document_v2.quantize_experiments import infer, pool, scalar_check, sha


MODEL = 'p2-doc-d42-int24-v1'
SHAPES = {
    'conv': (8, 1, 3, 3),
    'conv2': (8, 8, 3, 3),
    'fc': (8, 392),
}


def json_file(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def seal(output):
    checks = {}
    for path in sorted(output.rglob('*')):
        if not path.is_file() or path == output/'checksums.json':
            continue
        data = path.read_bytes()
        if path.suffix in {'.mem', '.json', '.md', '.vh'}:
            data = data.replace(b'\r\n', b'\n')
            path.write_bytes(data)
        checks[path.relative_to(output).as_posix()] = sha(data)
    (output/'checksums.json').write_bytes((json.dumps(checks, indent=2) + '\n').encode('utf-8'))
    if any(sha((output/name).read_bytes()) != digest for name,digest in checks.items()):
        raise ValueError('Package checksum verification failed')
    return len(checks)


def publish(run, quantized, output):
    report = json.loads((quantized/'metrics.json').read_text())
    if (report['profile'], report['seed']) != ('D', 42):
        raise ValueError('Expected the quantized D seed 42 result')
    manifest = (run/'split_manifest.json').read_bytes()
    config = json.loads((run/'size_16_seed_42/config.json').read_text())
    checkpoint = run/'size_16_seed_42/best.pt'
    if (sha(manifest) != report['split_sha256'] or config['split_sha256'] != report['split_sha256']
            or sha(checkpoint.read_bytes()) != report['checkpoint_sha256']
            or (config['profile'], config['seed'], config['image_size'], config['filters'],
                config['second_conv']) != ('D', 42, 16, 8, True)):
        raise ValueError('Training and quantized artifact identities disagree')
    samples = json.loads(manifest)['samples']
    selected = [s for s in samples if s['split'] == 'validation']
    with np.load(run/'pixels_16.npz', allow_pickle=False) as cache:
        mask = cache['is_validation']
        if not np.array_equal(mask, [s['split'] == 'validation' for s in samples]):
            raise ValueError('Validation mask does not match split')
        pixels, truth = cache['pixels'][mask], cache['labels'][mask]
    if (pixels.dtype != np.uint8 or pixels.shape != (len(selected), 1, 16, 16)
            or not np.array_equal(truth, [s['label'] for s in selected])):
        raise ValueError('Validation cache does not match split')

    layers = []
    with np.load(quantized/'parameters.npz', allow_pickle=False) as params:
        for name, shape in SHAPES.items():
            weight, bias = params[name+'_weight'], params[name+'_bias']
            detail = report['layers'][name]
            if (weight.shape != shape or weight.dtype != np.int8 or np.any(weight == -128)
                    or bias.shape != (8,) or bias.dtype != np.int32
                    or bound(weight, bias, 255 if name == 'conv' else 127) != detail['partial_sum_bound']):
                raise ValueError(f'Parameter mismatch: {name}')
            q = None
            if name != 'fc':
                m, s = detail['multiplier'], detail['shift']
                if not (1 <= m <= 65535 and 0 <= s <= 47):
                    raise ValueError(f'Invalid requantization: {name}')
                rescale = detail['partial_sum_bound'] * m + (1 << (s-1) if s else 0)
                if rescale != detail['rescale_bound'] or rescale >= 1 << 47:
                    raise ValueError(f'Rescale bound mismatch: {name}')
                q = (m, s)
            layers.append((weight, bias, q))
    scores = np.concatenate([infer(pixels[i:i+128], layers)[1] for i in range(0, len(pixels), 128)])
    with np.load(quantized/'validation_outputs.npz', allow_pickle=False) as reference:
        if not np.array_equal(reference['labels'], truth) or not np.array_equal(reference['integer_scores'], scores):
            raise ValueError('Validation scores differ from quantization run')

    # Stored bank: two independent validation tracks per class.
    stored = []
    for k in range(8):
        tracks = set()
        for i in np.flatnonzero(truth == k):
            track = selected[i]['track']
            if track not in tracks:
                stored.append(int(i))
                tracks.add(track)
            if len(tracks) == 2:
                break
        if len(tracks) != 2:
            raise ValueError(f'Need two validation tracks for class {k}')
    mistakes = [int(i) for i in np.flatnonzero(scores.argmax(1) != truth) if i not in stored]
    real = stored + mistakes[:4]
    synthetic = {
        'zeros': np.zeros((1, 16, 16), np.uint8),
        'maximum': np.full((1, 16, 16), 255, np.uint8),
        'checkerboard': (np.indices((16, 16)).sum(0)[None] % 2 * 255).astype(np.uint8),
        'ramp': np.arange(256, dtype=np.uint8).reshape(1, 16, 16),
        'impulse': np.pad(np.array([[[255]]], dtype=np.uint8), ((0, 0), (8, 7), (8, 7))),
    }
    cases = [(f'val_{i:05d}', pixels[i], selected[i]) for i in real]
    cases.extend((name, image, None) for name, image in synthetic.items())

    output.mkdir(parents=True)
    (output/'.gitattributes').write_bytes(b'* -text\n')
    mem = output/'mem'
    mem.mkdir()
    shutil.copyfile(quantized/'parameters.npz', output/'parameters.npz')
    json_file(output/'training_config.json', config)
    json_file(output/'metrics.json', report)
    contract = dict(version=MODEL, qualification='software golden only', input_shape=[1,16,16],
                    image_size=16, filters=8, classes=config['class_map'],
                    preprocessing=config['preprocessing'], input_dtype='uint8', input_scale=1/255,
                    weight_dtype='int8', accumulator_dtype='int24', score_dtype='int24',
                    mac_order='bias first, CHW', activation_range=[0,127],
                    requantization='min(127, (max(0, acc)*M + rounding) >> S); rounding=2^(S-1) for S>0 else 0',
                    architecture=['conv 1x8 valid 3x3', 'relu requant', 'maxpool 2x2 stride 2',
                                  'conv2 8x8 zero padded 3x3', 'relu requant', 'flatten CHW', 'fc 392x8'],
                    weight_shapes=SHAPES, layers=report['layers'], tie_break='lowest class index',
                    checkpoint_sha256=report['checkpoint_sha256'], split_sha256=report['split_sha256'],
                    uart_target=dict(baud=115200, request_bytes=259, reply_bytes=32, cycle_bits=32,
                                     score_bits=24), test_set_used=False)
    json_file(output/'contract.json', contract)
    header = ['// D42 experiment. Include inside the consuming Verilog module.']
    for name, (weight, bias, q) in zip(SHAPES, layers):
        write_mem(mem/(name+'_weight.mem'), weight, 8)
        write_mem(mem/(name+'_bias.mem'), bias, 24)
        if q:
            prefix = f'D42_{name.upper()}'
            header.extend([f"localparam [15:0] {prefix}_M = 16'd{q[0]};",
                           f'localparam integer {prefix}_S = {q[1]};'])
    (output/'params.vh').write_text('\n'.join(header)+'\n', encoding='ascii')
    vectors = []
    for name, image, metadata in cases:
        trace, logits = infer(image[None], layers)
        pooled = scalar_check(image, layers, trace, logits)
        vector_pool = pool(trace[0][1])[0]
        if not np.array_equal(pooled, vector_pool):
            raise ValueError('Pooling mismatch')
        result = dict(input=image, conv_acc=trace[0][0][0], activation=trace[0][1][0],
                      pool=vector_pool, conv2_acc=trace[1][0][0], activation2=trace[1][1][0],
                      scores=logits[0], prediction=np.array([logits.argmax(1)[0]], dtype=np.uint8))
        folder = output/'vectors'/name
        folder.mkdir(parents=True)
        np.savez_compressed(folder/'layers.npz', **result)
        for stage, values in result.items():
            write_mem(folder/(stage+'.mem'), values, 24 if stage.endswith('_acc') or stage == 'scores' else 8)
        vectors.append(dict(name=name, sample=metadata, prediction=int(result['prediction'][0])))
    json_file(output/'vectors/manifest.json', vectors)
    write_mem(output/'signs.mem', pixels[stored], 8)
    write_mem(output/'labels.mem', truth[stored], 8)
    json_file(output/'stored_manifest.json', [dict(index=i, **v) for i,v in enumerate(vectors[:16])])
    (output/'MEMORY_LAYOUT.md').write_text(
        '# D42 memory layout\n\n'
        'One hexadecimal word per line. Multi-dimensional arrays flatten in C order.\n'
        'Conv weights are OIHW; FC weights are [class, CHW feature]. Weights are signed8.\n'
        'Bias, conv_acc, conv2_acc and scores are signed24 two\'s complement.\n'
        'Input is CHW 1×16×16. Conv1 acc and activation are 8×14×14.\n'
        'Pool, Conv2 acc and activation2 are 8×7×7. FC uses activation2, not pool.\n'
        'Scores are in class-index order. signs.mem contains 16 row-major images.\n'
        'labels.mem contains ground truth; stored_manifest.json has golden predictions.\n'
        'This is an experimental software reference for future D42 RTL.\n', encoding='utf-8')
    print(f'{MODEL}: {len(scores)} validation score rows reproduced, '
          f'{len(vectors)} scalar-checked golden vectors, {seal(output)} sealed files')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--quantized', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    publish(args.run, args.quantized, args.output)
