"""Train and export a separate MNIST integer CNN with held-out evaluation."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import struct
import sys
import urllib.request

import numpy as np
import torch
from torch import nn

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'reference_model'))
from model import SignCNN
from golden import infer, scalar_infer, STAGES
from quantize import quantized_weights, quantized_bias, multiplier_shift, bound, write_mem

RESOURCES = {
    'train-images-idx3-ubyte.gz': 'f68b3c2dcbeaaa9fbdd348bbdeb94873',
    'train-labels-idx1-ubyte.gz': 'd53e105ee54ea40749a09fcbcd1e9432',
    't10k-images-idx3-ubyte.gz': '9fb629c4189551a2d022fa330f9573f3',
    't10k-labels-idx1-ubyte.gz': 'ec29112dd5afa0611ce80d1b7f02629c',
}
MIRROR = 'https://ossci-datasets.s3.amazonaws.com/mnist/'


def load_idx(folder, name):
    path = folder / name
    if not path.exists():
        print('Downloading', name, flush=True)
        raw = urllib.request.urlopen(MIRROR + name, timeout=90).read()
        if hashlib.md5(raw).hexdigest() != RESOURCES[name]:
            raise ValueError('MNIST download integrity failure')
        path.write_bytes(raw)
    if hashlib.md5(path.read_bytes()).hexdigest() != RESOURCES[name]:
        raise ValueError(f'Bad dataset checksum: {path}')
    data = gzip.decompress(path.read_bytes())
    magic, count = struct.unpack('>II', data[:8])
    if magic == 2051:
        rows, cols = struct.unpack('>II', data[8:16])
        return np.frombuffer(data, np.uint8, offset=16).reshape(count, 1, rows, cols).copy()
    if magic != 2049:
        raise ValueError('Invalid IDX file')
    return np.frombuffer(data, np.uint8, offset=8).reshape(count).copy()


def measure(labels, prediction):
    cm = np.zeros((10, 10), dtype=np.int64)
    np.add.at(cm, (labels, prediction), 1)
    return {'accuracy': float((labels == prediction).mean()),
            'per_digit_recall': (np.diag(cm) / cm.sum(1)).tolist(),
            'confusion': cm.tolist(), 'count': len(labels)}


def float_scores(model, pixels):
    with torch.no_grad():
        return np.concatenate([model(torch.from_numpy(batch).float()/255).numpy()
                               for batch in np.array_split(pixels, max(1, (len(pixels)+255)//256))])


def integer_scores(parameters, contract, pixels):
    return np.concatenate([infer(batch, parameters, contract)['scores']
                           for batch in np.array_split(pixels, max(1, (len(pixels)+255)//256))])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--epochs', type=int, default=12)
    parser.add_argument('--output', type=Path, default=ROOT/'build/mnist_digit/v1')
    parser.add_argument('--package', type=Path, default=ROOT/'experiments/mnist_digit/models/mnist-int-v1')
    args = parser.parse_args()
    if args.epochs < 1:
        parser.error('Epoch count must be positive')
    if args.output.exists() or args.package.exists():
        raise ValueError('Choose fresh output and package folders; existing runs are preserved')
    args.output.mkdir(parents=True)
    cache = ROOT/'build/mnist_digit/dataset'
    cache.mkdir(parents=True, exist_ok=True)
    pixels = load_idx(cache, 'train-images-idx3-ubyte.gz')
    labels = load_idx(cache, 'train-labels-idx1-ubyte.gz')
    rng = np.random.default_rng(2026)
    validation = np.zeros(len(labels), dtype=bool)
    for digit in range(10):
        ids = np.flatnonzero(labels == digit)
        validation[rng.permutation(ids)[:round(len(ids)/12)]] = True
    np.savez_compressed(args.output/'split.npz', training=np.flatnonzero(~validation),
                        validation=np.flatnonzero(validation))
    torch.set_num_threads(4)
    torch.manual_seed(42)
    torch.use_deterministic_algorithms(True)
    model = SignCNN(image_size=28, classes=10, filters=8)
    x = torch.from_numpy(pixels[~validation]).float()/255
    y = torch.from_numpy(labels[~validation].astype(np.int64))
    loader = torch.utils.data.DataLoader(torch.utils.data.TensorDataset(x, y),
        batch_size=128, shuffle=True, generator=torch.Generator().manual_seed(42))
    optimizer = torch.optim.Adam(model.parameters(), lr=.001)
    history = []
    best = -1
    for epoch in range(1, args.epochs+1):
        model.train()
        for image, label in loader:
            optimizer.zero_grad(set_to_none=True)
            loss = nn.functional.cross_entropy(model(image), label)
            loss.backward()
            optimizer.step()
        model.eval()
        report = measure(labels[validation], float_scores(model, pixels[validation]).argmax(1))
        history.append({'epoch': epoch, 'validation_accuracy': report['accuracy']})
        if report['accuracy'] > best:
            best = report['accuracy']
            torch.save({'state_dict': model.state_dict(), 'epoch': epoch,
                        'config': {'image_size': 28, 'filters': 8, 'classes': 10,
                                   'seed': 42, 'split_seed': 2026}}, args.output/'best.pt')
        print(f"Epoch {epoch:02}: validation={report['accuracy']:.4%}, best={best:.4%}", flush=True)
    checkpoint = torch.load(args.output/'best.pt', map_location='cpu', weights_only=True)
    model.load_state_dict(checkpoint['state_dict'])
    model.eval()
    maximum = 0.
    with torch.no_grad():
        for batch in np.array_split(pixels[~validation], 120):
            maximum = max(maximum, float(torch.relu(model.conv(torch.from_numpy(batch).float()/255)).max()))
    sx = 1/255
    sa = maximum/127 if maximum else 1.
    cw, sc = quantized_weights(model.conv.weight.detach().numpy())
    fw, sf = quantized_weights(model.fc.weight.detach().numpy())
    parameters = {'conv_weight': cw, 'conv_bias': quantized_bias(model.conv.bias.detach().numpy(), sx*sc),
                  'fc_weight': fw, 'fc_bias': quantized_bias(model.fc.bias.detach().numpy(), sa*sf)}
    m, s = multiplier_shift(sx*sc/sa)
    bounds = {'conv_absolute_partial_sum': bound(cw, parameters['conv_bias'], 255),
              'fc_absolute_partial_sum': bound(fw, parameters['fc_bias'], 127)}
    bounds['rescale_including_rounding'] = bounds['conv_absolute_partial_sum']*m+(1<<(s-1) if s else 0)
    if bounds['rescale_including_rounding'] > 2**53-1:
        raise OverflowError('Browser integer inspector cannot exactly represent rescale intermediate')
    contract = {'version': 'mnist-int-v1', 'dataset': 'MNIST', 'image_size': 28, 'filters': 8,
        'classes': [{'index': i, 'name': f'Digit {i}', 'digit': i} for i in range(10)],
        'input': {'dtype': 'uint8', 'range': [0,255], 'scale': sx, 'zero_point': 0},
        'weights': {'dtype': 'int8', 'conv_scale': sc, 'fc_scale': sf},
        'bias': {'dtype': 'int32'}, 'accumulator': {'dtype': 'int32', 'overflow': 'forbidden'},
        'activation': {'dtype': 'uint8', 'range': [0,127], 'scale': sa,
                       'calibration': 'training only', 'training_maximum': maximum},
        'requantization': {'multiplier': m, 'shift': s, 'intermediate_bits': 64,
                          'rounding': 'nearest, halfway upward after ReLU'},
        'parameter_rounding': 'nearest ties to even', 'pool': '2x2 max, stride 2',
        'flatten': 'CHW; index=(channel*13+row)*13+column',
        'scores': {'dtype': 'int32', 'scale': sa*sf, 'rescale': False},
        'argmax': 'lowest index on ties', 'bounds': bounds,
        'checkpoint_sha256': hashlib.sha256((args.output/'best.pt').read_bytes()).hexdigest()}
    val_float = float_scores(model, pixels[validation])
    val_integer = integer_scores(parameters, contract, pixels[validation])
    # The official test is opened only after checkpoint selection and calibration.
    test_pixels = load_idx(cache, 't10k-images-idx3-ubyte.gz')
    test_labels = load_idx(cache, 't10k-labels-idx1-ubyte.gz')
    test_float = float_scores(model, test_pixels)
    test_integer = integer_scores(parameters, contract, test_pixels)
    evidence = {'training_count': int((~validation).sum()), 'validation_count': int(validation.sum()),
        'best_epoch': checkpoint['epoch'], 'history': history,
        'validation_float': measure(labels[validation], val_float.argmax(1)),
        'validation_integer': measure(labels[validation], val_integer.argmax(1)),
        'official_test_float': measure(test_labels, test_float.argmax(1)),
        'official_test_integer': measure(test_labels, test_integer.argmax(1)),
        'test_prediction_agreement': float((test_float.argmax(1)==test_integer.argmax(1)).mean()),
        'test_used_for_training_or_selection': False, 'rtl_simulation_run': False}
    val_pixels, val_labels = pixels[validation], labels[validation]
    selected = [int(np.flatnonzero(val_labels==i)[0]) for i in range(10)]
    samples = [val_pixels[i] for i in selected]
    directed = [np.zeros((1,28,28), np.uint8), np.full((1,28,28),255,np.uint8),
                (np.arange(784)%256).astype(np.uint8).reshape(1,28,28)]
    for image in samples+directed:
        vector = infer(image[None], parameters, contract)
        oracle = scalar_infer(image, parameters, contract)
        for stage in STAGES:
            np.testing.assert_array_equal(vector[stage][0], oracle[stage], err_msg=stage)
    evidence['scalar_oracle_vectors_passed'] = len(samples)+len(directed)
    args.package.mkdir(parents=True)
    np.savez_compressed(args.package/'parameters.npz', **parameters)
    np.savez_compressed(args.package/'samples.npz', pixels=np.array(samples), labels=np.arange(10))
    np.savez_compressed(args.package/'weights_float32.npz', **{k:v.numpy() for k,v in model.state_dict().items()})
    (args.package/'contract.json').write_text(json.dumps(contract, indent=2))
    (args.package/'metrics.json').write_text(json.dumps(evidence, indent=2))
    mem = args.package/'mem'
    mem.mkdir()
    for name, values in parameters.items():
        write_mem(mem/(name+'.mem'), values, 8 if 'weight' in name else 32)
    (args.package/'.gitattributes').write_bytes(b'* -text\n')
    (args.package/'checksums.json').write_text(json.dumps({p.relative_to(args.package).as_posix():
        hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(args.package.rglob('*')) if p.is_file()},indent=2))
    print(json.dumps({k:v for k,v in evidence.items() if k!='history'}, indent=2), flush=True)
    print('MNIST package:', args.package, flush=True)


if __name__ == '__main__':
    main()
