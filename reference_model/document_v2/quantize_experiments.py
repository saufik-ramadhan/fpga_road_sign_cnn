"""Quantize C/D checkpoints and evaluate their original validation split."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from model import SignCNN
from document_v2.golden import checked24, requant_relu
from document_v2.quantize import bound, metrics, multiplier_shift, quantized_bias, quantized_weights, write_mem


def sha(data):
    return hashlib.sha256(data).hexdigest()


def pool(x):
    n, channels, h, w = x.shape
    return x.reshape(n, channels, h // 2, 2, w // 2, 2).max(axis=(3, 5))


def infer(pixels, layers):
    x = pixels
    stages = []
    for index, (weight, bias, q) in enumerate(layers[:-1]):
        if index:
            x = np.pad(x, ((0, 0), (0, 0), (1, 1), (1, 1)))
        windows = np.lib.stride_tricks.sliding_window_view(x, (3, 3), axis=(2, 3))
        # The exported absolute bounds prove every bias-first partial sum fits.
        acc = checked24(np.einsum('ncyxij,fcij->nfyx', windows, weight,
                                  dtype=np.int64) + bias[None, :, None, None])
        activation = requant_relu(acc, *q)
        stages.append((acc, activation))
        x = pool(activation) if index == 0 else activation
    weight, bias, _ = layers[-1]
    scores = checked24(x.reshape(len(x), -1).astype(np.int64) @ weight.T + bias)
    return stages, scores


def scalar_check(image, layers, stages, scores):
    """Independent CHW Python integer MAC and requantization for sampled inputs."""
    x = image
    for index, (weight, bias, (m, s)) in enumerate(layers[:-1]):
        if index:
            x = np.pad(x, ((0, 0), (1, 1), (1, 1)))
        acc, activation = stages[index]
        for f, y, col in np.ndindex(activation.shape[1:]):
            value = int(bias[f])
            for channel, ky, kx in np.ndindex(weight.shape[1:]):
                value += int(x[channel, y + ky, col + kx]) * int(weight[f, channel, ky, kx])
                if not -(1 << 23) <= value < 1 << 23:
                    raise OverflowError('Scalar convolution partial sum')
            expected = min(127, (max(0, value) * m + (1 << (s - 1) if s else 0)) >> s)
            if value != acc[0, f, y, col] or expected != activation[0, f, y, col]:
                raise ValueError('Scalar convolution mismatch')
        x = activation[0]
        if index == 0:
            x = np.stack([np.array([[max(ch[y:y+2, col:col+2].flat)
                         for col in range(0, ch.shape[1], 2)]
                         for y in range(0, ch.shape[0], 2)]) for ch in x])
            pooled = x
    weight, bias, _ = layers[-1]
    for k, expected in enumerate(scores[0]):
        value = int(bias[k])
        for a, w in zip(x.flat, weight[k]):
            value += int(a) * int(w)
            if not -(1 << 23) <= value < 1 << 23:
                raise OverflowError('Scalar FC partial sum')
        if value != expected:
            raise ValueError('Scalar FC mismatch')
    return pooled


def evaluate_run(run, split_bytes, output):
    manifest = json.loads(split_bytes)
    split_sha = sha(split_bytes)
    class_map = manifest['class_map']
    classes = len(class_map)
    class_indices = {item['gtsrb_id']: item['index'] for item in class_map}
    if (run / 'split_manifest.json').read_bytes() != split_bytes:
        raise ValueError(f'Split mismatch: {run}')
    summary = json.loads((run / 'summary.json').read_text())
    profile = summary['profile']
    architecture = {'C': (16, False), 'D': (8, True)}
    filters, second = architecture[profile]
    if summary['seeds'] != [42, 43, 44] or summary['split_sha256'] != split_sha:
        raise ValueError('Expected completed C/D runs for seeds 42/43/44 on the shared split')
    with np.load(run / 'pixels_16.npz', allow_pickle=False) as data:
        pixels, labels, validation = (data[key] for key in ('pixels', 'labels', 'is_validation'))
    if (pixels.dtype != np.uint8 or pixels.shape != (len(manifest['samples']), 1, 16, 16)
            or not np.array_equal(labels, [s['label'] for s in manifest['samples']])
            or not np.array_equal(validation, [s['split'] == 'validation' for s in manifest['samples']])):
        raise ValueError('Pixel cache does not match split')
    train, val, truth = pixels[~validation], pixels[validation], labels[validation]
    if set(truth) != set(range(classes)) or set(labels[~validation]) != set(range(classes)):
        raise ValueError('Both splits must cover the full class map')
    reports = []
    for seed in summary['seeds']:
        source = run / f'size_16_seed_{seed}'
        checkpoint_path = source / 'best.pt'
        checkpoint_bytes = checkpoint_path.read_bytes()
        # Checkpoints originate from the local trainer.
        import io
        checkpoint = torch.load(io.BytesIO(checkpoint_bytes), map_location='cpu', weights_only=False)
        config = checkpoint['config']
        if (config['profile'], config['seed'], config['split_sha256'], config['class_map']) != (
                profile, seed, split_sha, manifest['class_map']):
            raise ValueError(f'Checkpoint identity mismatch: {checkpoint_path}')
        model = SignCNN(16, classes=classes, filters=filters, second_conv=second).eval()
        model.load_state_dict(checkpoint['state_dict'])
        modules = [model.conv] + ([model.conv2] if second else [])
        maxima = [0.] * len(modules)
        with torch.inference_mode():
            for start in range(0, len(train), 256):
                x = torch.from_numpy(train[start:start+256]).float() / 255
                for i, module in enumerate(modules):
                    x = torch.relu(module(x))
                    maxima[i] = max(maxima[i], x.max().item())
                    if i == 0:
                        x = model.pool(x)
        layers, details, params = [], {}, {}
        scale = 1 / 255
        for index, module in enumerate(modules + [model.fc]):
            name = ('conv' if index == 0 else 'conv2') if index < len(modules) else 'fc'
            weights, weight_scale = quantized_weights(module.weight.detach().numpy())
            bias = quantized_bias(module.bias.detach().numpy(), scale * weight_scale)
            partial = bound(weights, bias, 255 if index == 0 else 127)
            layer = dict(input_scale=scale, weight_scale=weight_scale, bias_scale=scale * weight_scale,
                         partial_sum_bound=partial)
            q = None
            if name != 'fc':
                scale = maxima[index] / 127 if maxima[index] else 1.
                q = multiplier_shift(layer['bias_scale'] / scale)
                m, s = q
                rescale_bound = partial * m + (1 << (s - 1) if s else 0)
                if rescale_bound >= 1 << 47:
                    raise OverflowError('Rescale bound exceeds signed48')
                layer.update(output_scale=scale, training_relu_max=maxima[index], multiplier=m, shift=s,
                             rescale_bound=rescale_bound)
            details[name] = layer
            layers.append((weights, bias, q))
            params.update({name + '_weight': weights, name + '_bias': bias})
        parts, float_parts = [], []
        with torch.inference_mode():
            for start in range(0, len(val), 128):
                batch = val[start:start+128]
                parts.append(infer(batch, layers)[1])
                float_parts.append(model(torch.from_numpy(batch).float()/255).numpy())
        scores, floats = np.concatenate(parts), np.concatenate(float_parts)
        float_result = metrics(truth, floats.argmax(1), classes)
        expected = json.loads((source / 'metrics.json').read_text())['validation']['confusion']
        if float_result['confusion'] != expected:
            raise ValueError('Float validation does not reproduce checkpoint metrics')
        for index in range(classes):
            sample = val[np.flatnonzero(truth == index)[0]]
            trace, logits = infer(sample[None], layers)
            scalar_check(sample, layers, trace, logits)
        result = dict(profile=profile, classes=classes, class_map=class_map, seed=seed, epoch=checkpoint['epoch'], split_sha256=split_sha,
                      checkpoint_sha256=sha(checkpoint_bytes), float=float_result,
                      integer=metrics(truth, scores.argmax(1), classes), validation_count=len(val),
                      calibration_count=len(train), scalar_checks=classes,
                      changed_predictions=int((scores.argmax(1) != floats.argmax(1)).sum()),
                      layers=details, test_set_used=False)
        folder = output / f'{profile}-seed-{seed}'
        folder.mkdir()
        np.savez_compressed(folder/'parameters.npz', **params)
        for name, values in params.items():
            write_mem(folder/(name+'.mem'), values, 8 if name.endswith('_weight') else 24)
        np.savez_compressed(folder/'validation_outputs.npz', labels=truth, integer_scores=scores, float_logits=floats)
        (folder/'metrics.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        reports.append(result)
        speed30 = result['integer']['recalls'][class_indices[1]]
        print(f'{profile}/{seed}: float {float_result["accuracy"]:.2%}, integer '
              f'{result["integer"]["accuracy"]:.2%}, Speed 30 {speed30:.2%}', flush=True)
    return reports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', type=Path, nargs='+', required=True)
    parser.add_argument('--shared-split', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    profiles = [json.loads((p/'summary.json').read_text())['profile'] for p in args.runs]
    if not set(profiles) <= {'C', 'D'} or len(profiles) != len(set(profiles)):
        parser.error('Select a completed C or D run, at most one per profile')
    torch.set_num_threads(4)
    split_bytes = args.shared_split.read_bytes()
    args.output.mkdir(parents=True)
    (args.output/'split_manifest.json').write_bytes(split_bytes)
    reports = [report for run in args.runs for report in evaluate_run(run, split_bytes, args.output)]
    (args.output/'summary.json').write_text(json.dumps(reports, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
