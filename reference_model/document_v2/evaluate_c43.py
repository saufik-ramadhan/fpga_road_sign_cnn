"""Evaluate frozen C-43 seed 44 and export official-test RTL vectors."""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path

import numpy as np
from PIL import Image
import torch

from quantize_experiments import SignCNN, bound, infer, metrics, write_mem
from document_v2.preprocessing import preprocess_image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--quantized', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    torch.set_num_threads(4)
    source = json.loads((args.quantized / 'metrics.json').read_text())
    checkpoint_bytes = args.checkpoint.read_bytes()
    checkpoint_hash = hashlib.sha256(checkpoint_bytes).hexdigest()
    if (source['profile'], source['classes'], source['seed'], source['checkpoint_sha256']) != (
            'C', 43, 44, checkpoint_hash):
        raise ValueError('Expected the frozen C-43 seed 44 checkpoint and matching quantized parameters')
    checkpoint = torch.load(io.BytesIO(checkpoint_bytes), map_location='cpu', weights_only=False)
    if [entry['gtsrb_id'] for entry in source['class_map']] != list(range(43)):
        raise ValueError('Expected identity GTSRB class order')
    model = SignCNN(16, classes=43, filters=16).eval()
    model.load_state_dict(checkpoint['state_dict'])
    parameter_file = args.quantized / 'parameters.npz'
    parameter_bytes = parameter_file.read_bytes()
    q = source['layers']['conv']
    layers = []
    with np.load(io.BytesIO(parameter_bytes), allow_pickle=False) as params:
        for name, shape, bits in [('conv', (16, 1, 3, 3), 255), ('fc', (43, 784), 127)]:
            weight, bias = params[name+'_weight'], params[name+'_bias']
            if (weight.shape != shape or bias.shape != (shape[0],) or weight.dtype != np.int8
                    or bias.dtype != np.int32
                    or bound(weight, bias, bits) != source['layers'][name]['partial_sum_bound']):
                raise ValueError(f'Invalid frozen {name} parameters')
            layers.append((weight, bias, (q['multiplier'], q['shift']) if name == 'conv' else None))
    test_csv = (args.dataset / 'Test.csv').read_bytes()
    rows = list(csv.DictReader(io.StringIO(test_csv.decode('utf-8-sig'))))
    truth = np.array([int(row['ClassId']) for row in rows], dtype=np.int64)
    if len(rows) != 12630 or set(truth) != set(range(43)) or len({row['Path'] for row in rows}) != len(rows):
        raise ValueError('Expected 12,630 unique official test entries covering 43 classes')
    dataset = args.dataset.resolve()
    pixels = np.empty((len(rows), 1, 16, 16), dtype=np.uint8)
    for index, row in enumerate(rows):
        path = (dataset / row['Path']).resolve()
        if not path.is_relative_to(dataset / 'Test'):
            raise ValueError(f'Expected a file under Test/: {path}')
        with Image.open(path) as image:
            if image.size != (int(row['Width']), int(row['Height'])):
                raise ValueError(f'Image size mismatch: {path}')
            roi = tuple(int(row[key]) for key in ('Roi.X1', 'Roi.Y1', 'Roi.X2', 'Roi.Y2'))
            pixels[index, 0] = np.asarray(preprocess_image(image, roi))
    float_parts, int_parts = [], []
    with torch.inference_mode():
        for start in range(0, len(pixels), 128):
            batch = pixels[start:start+128]
            float_parts.append(model(torch.from_numpy(batch).float()/255).numpy())
            int_parts.append(infer(batch, layers)[1])
    logits, scores = np.concatenate(float_parts), np.concatenate(int_parts)
    result = dict(profile='C', classes=43, seed=44, count=len(rows),
                  split_sha256=source['split_sha256'], checkpoint_sha256=checkpoint_hash,
                  parameters_sha256=hashlib.sha256(parameter_bytes).hexdigest(),
                  test_csv_sha256=hashlib.sha256(test_csv).hexdigest(),
                  float=metrics(truth, logits.argmax(1), 43), integer=metrics(truth, scores.argmax(1), 43),
                  changed_predictions=int((logits.argmax(1) != scores.argmax(1)).sum()))
    out = args.output
    out.mkdir(parents=True)
    (out / 'official_metrics.json').write_text(json.dumps(result, indent=2))
    np.savez_compressed(out / 'official_outputs.npz', labels=truth, float_logits=logits, integer_scores=scores)

    # Select inputs by label before looking at predictions, plus arithmetic edge patterns.
    selected = [int(np.flatnonzero(truth == label)[0]) for label in range(43)]
    patterns = np.stack([np.zeros((16, 16), dtype=np.uint8),
                         np.full((16, 16), 255, dtype=np.uint8),
                         np.arange(256, dtype=np.uint8).reshape(16, 16)])[:, None]
    vectors = np.concatenate((pixels[selected], patterns))
    stages, vector_scores = infer(vectors, layers)
    accumulator, activation = stages[0]
    pool = activation.reshape(len(vectors), 16, 7, 2, 7, 2).max(axis=(3, 5))
    if not np.array_equal(vector_scores[:len(selected)], scores[selected]):
        raise ValueError('Vector scores disagree with official test scores')
    (out / 'rtl_vectors.json').write_text(json.dumps(dict(
        sources=[rows[i]['Path'] for i in selected] + ['zeros', 'maximum', 'ramp'],
        multiplier=q['multiplier'], shift=q['shift']), indent=2))
    for name, values, bits in (
        ('input', vectors, 8), ('conv_acc', accumulator, 24), ('activation', activation, 8),
        ('pool', pool, 8), ('scores', vector_scores, 24), ('prediction', vector_scores.argmax(1), 8),
        ('conv_weight', layers[0][0], 8), ('conv_bias', layers[0][1], 24),
        ('fc_weight', layers[1][0], 8), ('fc_bias', layers[1][1], 24),
    ):
        write_mem(out / (name+'.mem'), values, bits)
    print(f'Official test: {len(rows)} images, float {result["float"]["accuracy"]:.4%}, '
          f'integer {result["integer"]["accuracy"]:.4%}, {len(vectors)} RTL vectors')


if __name__ == '__main__':
    main()
