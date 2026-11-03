"""GTSRB training-only preparation. The official test set is never opened."""
import csv
import hashlib
import io
import json
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

CLASS_NAMES = {1: 'Speed limit 30', 2: 'Speed limit 50', 12: 'Priority road',
               13: 'Yield', 14: 'Stop', 17: 'No entry', 18: 'General caution',
               38: 'Keep right'}


def track_id(row):
    # GTSRB filename: class_track_frame.png. Include class in the grouping key.
    parts = Path(row['Path']).stem.split('_')
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise ValueError(f"Unrecognized GTSRB track filename: {row['Path']}")
    if int(parts[0]) != int(row['ClassId']):
        raise ValueError('Filename class and CSV class disagree')
    return f"{int(row['ClassId'])}:{int(parts[1])}"


def build_manifest(dataset, destination, seed=2026, val_fraction=.2, *, class_names=CLASS_NAMES):
    raw_csv = (dataset / 'Train.csv').read_bytes()
    rows = [r for r in csv.DictReader(io.StringIO(raw_csv.decode('utf-8-sig')))
            if int(r['ClassId']) in class_names]
    paths = [r['Path'] for r in rows]
    if len(paths) != len(set(paths)):
        raise ValueError('Duplicate CSV paths')
    rows.sort(key=lambda r: r['Path'])
    rng = np.random.default_rng(seed)
    val_groups = set()
    for cid in class_names:
        groups = sorted({track_id(r) for r in rows if int(r['ClassId']) == cid})
        if len(groups) < 2:
            raise ValueError(f'Class {cid} has too few independent tracks')
        count = max(1, min(len(groups) - 1, round(len(groups) * val_fraction)))
        val_groups.update(rng.permutation(groups)[:count].tolist())
    mapping = {cid: index for index, cid in enumerate(class_names)}
    samples = [dict(path=r['Path'], original_class=int(r['ClassId']),
                    label=mapping[int(r['ClassId'])], track=track_id(r),
                    split='validation' if track_id(r) in val_groups else 'train',
                    width=int(r['Width']), height=int(r['Height']),
                    roi=[int(r[k]) for k in ('Roi.X1', 'Roi.Y1', 'Roi.X2', 'Roi.Y2')])
               for r in rows]
    for split in ('train', 'validation'):
        if {s['original_class'] for s in samples if s['split'] == split} != set(class_names):
            raise ValueError(f'Missing class in {split}')
    manifest = dict(split_seed=seed, validation_fraction_requested=val_fraction,
                    train_csv_sha256=hashlib.sha256(raw_csv).hexdigest(),
                    class_map=[dict(index=mapping[c], gtsrb_id=c, name=n)
                               for c, n in class_names.items()], samples=samples)
    encoded = json.dumps(manifest, indent=2)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.read_text() != encoded:
        raise ValueError('Existing split manifest differs; choose a new output directory')
    destination.write_text(encoded)
    return manifest


def preprocess(image, roi, size):
    x1, y1, x2, y2 = roi
    if not (0 <= x1 < x2 < image.width and 0 <= y1 < y2 < image.height):
        raise ValueError(f'Invalid inclusive ROI {roi} for {image.size}')
    # GTSRB ROI max coordinates are included; Pillow crop right/bottom are excluded.
    return np.asarray(image.convert('RGB').crop((x1, y1, x2+1, y2+1))
                      .convert('L').resize((size, size), Image.Resampling.BILINEAR),
                      dtype=np.uint8)


def prepare(dataset, output, sizes, manifest):
    """Decode once, validate metadata and cache prepared pixels for all sizes."""
    samples = manifest['samples']
    arrays = {n: np.empty((len(samples), 1, n, n), dtype=np.uint8) for n in sizes}
    digest = hashlib.sha256()
    modes = Counter()
    for i, sample in enumerate(samples):
        source = dataset / sample['path']
        if not source.resolve().is_relative_to(dataset.resolve()):
            raise ValueError('CSV path escapes dataset')
        raw = source.read_bytes()
        digest.update(sample['path'].encode()); digest.update(hashlib.sha256(raw).digest())
        with Image.open(io.BytesIO(raw)) as image:
            image.load()
            if image.size != (sample['width'], sample['height']):
                raise ValueError(f"Dimension mismatch: {sample['path']}")
            modes[image.mode] += 1
            for size in sizes:
                arrays[size][i, 0] = preprocess(image, sample['roi'], size)
        if (i+1) % 2000 == 0:
            print(f'Decoded {i+1}/{len(samples)} selected images', flush=True)
    labels = np.array([s['label'] for s in samples], dtype=np.int64)
    is_val = np.array([s['split'] == 'validation' for s in samples])
    for size, pixels in arrays.items():
        np.savez_compressed(output / f'pixels_{size}.npz', pixels=pixels,
                            labels=labels, is_validation=is_val)
    audit = dict(decoded_images=len(samples), selected_source_sha256=digest.hexdigest(),
                 modes=dict(modes), train_count=int((~is_val).sum()),
                 validation_count=int(is_val.sum()), test_set_used=False,
                 preprocessing='inclusive ROI, RGB to Pillow L, bilinear resize, uint8 / 255',
                 augmentation='none', histogram_equalization=False,
                 train_tracks=len({s['track'] for s in samples if s['split']=='train'}),
                 validation_tracks=len({s['track'] for s in samples if s['split']=='validation'}))
    (output / 'data_audit.json').write_text(json.dumps(audit, indent=2))
    print(json.dumps(audit, indent=2), flush=True)
