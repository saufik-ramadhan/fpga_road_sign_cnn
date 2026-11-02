"""Publish compact per-epoch training records outside ignored build outputs."""
import argparse
import csv
import hashlib
import json
import shutil
from pathlib import Path


def update_training_section(path, content):
    """Refresh the generated section without replacing hand-written results."""
    start, end = '<!-- TRAINING_LOG:START -->', '<!-- TRAINING_LOG:END -->'
    existing = path.read_text(encoding='utf-8') if path.exists() else '# Experiment results\n\n## Training log v1\n'
    if existing.count(start) != existing.count(end) or existing.count(start) > 1:
        raise ValueError('Training log markers are incomplete or duplicated')
    block = start + '\n' + content.rstrip() + '\n' + end
    if start in existing:
        first, last = existing.index(start), existing.index(end)
        if last < first:
            raise ValueError('Training log markers are out of order')
        updated = existing[:first] + block + existing[last+len(end):]
    else:
        updated = existing.rstrip() + '\n\n' + block + '\n'
    path.write_text(updated, encoding='utf-8')


def export_log(source, destination):
    runs=[]
    for folder in sorted(source.glob('size_*_seed_*')):
        if not (folder/'metrics.json').is_file():continue
        metrics=json.loads((folder/'metrics.json').read_text())
        config=json.loads((folder/'config.json').read_text())
        with (folder/'history.csv').open(newline='') as f:history=list(csv.DictReader(f))
        if [int(r['epoch']) for r in history]!=list(range(1,metrics['epochs_run']+1)):
            raise ValueError(f'Incomplete epoch history: {folder}')
        best=history[metrics['best_epoch']-1]
        if abs(float(best['validation_accuracy'])-metrics['validation']['accuracy'])>1e-12:
            raise ValueError(f'Checkpoint metrics and history disagree: {folder}')
        runs.append((folder,metrics,config))
    if not runs:raise ValueError('No completed training runs found')
    destination.mkdir(parents=True,exist_ok=True)
    logs=destination/'training_logs'/source.name;logs.mkdir(parents=True,exist_ok=True)
    lines=['### Training log export','','Source experiment: '+source.name+'. Records copied from actual saved run histories; no training was rerun.',
           '', 'An epoch is one pass over the training set. Each run saved the checkpoint with the highest validation accuracy, which can precede the final epoch.',
           '', '| Model/run | Epochs run | Best checkpoint epoch | Validation accuracy | Run time (s) | Epoch history |',
           '|---|---:|---:|---:|---:|---|']
    records=[]
    for folder,m,c in runs:
        target=logs/folder.name;target.mkdir(exist_ok=True)
        for name in ('history.csv','config.json','metrics.json'):shutil.copyfile(folder/name,target/name)
        record=dict(run=folder.name,image_size=m['image_size'],seed=m['seed'],epochs_run=m['epochs_run'],
                    best_epoch=m['best_epoch'],validation_accuracy=m['validation']['accuracy'],
                    elapsed_seconds=m['elapsed_seconds'],
                    checkpoint_sha256=hashlib.sha256((folder/'best.pt').read_bytes()).hexdigest())
        records.append(record)
        relative=target.relative_to(destination).as_posix()
        lines.append(f"| {folder.name} | {m['epochs_run']} | {m['best_epoch']} | {m['validation']['accuracy']:.2%} | {m['elapsed_seconds']:.2f} | [CSV]({relative}/history.csv) |")
    with (logs/'summary.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(records[0]));writer.writeheader();writer.writerows(records)
    lines+=['','## Selected model supplied to RTL','',
            'The provisional p2-int-v1 integer package derives from **size_16_seed_42**, trained for **40 epochs**, using the best checkpoint at **epoch 39**.',
            'Quantization used training-only calibration and **zero additional training epochs**. It did not train a second neural network or use quantization-aware training.',
            'See the shared package contract.json for the selected checkpoint hash. All source checkpoint hashes are recorded in the summary CSV.',
            '', '## What each per-epoch CSV contains','',
            '- epoch: completed training epoch number.',
            '- train_online_accuracy: training predictions collected while optimizer updates were occurring; this is not a separate evaluation of the final checkpoint.',
            '- validation_accuracy: accuracy after that epoch, with inference mode and no optimizer updates.',
            '- validation_loss: unweighted validation cross entropy after that epoch.',
            '', 'Each run folder also contains the original config.json and metrics.json. The latter includes training-set evaluation and per-class validation recall for the selected checkpoint.',
            '', '## Shared training settings','',
            'Adam, learning rate 0.001, batch size 128, maximum 40 epochs, patience 12 epochs without improved validation accuracy. All six runs reached epoch 40. Class-weighted training loss, no augmentation or histogram equalization. Same grouped sign-track split, split seed 2026, initialization seeds 42/43/44. See each config.json for exact environment and split identity.',
            '', 'Reported run time includes training plus selected-checkpoint evaluation; it excludes dataset decoding/preparation and is not FPGA inference latency.',
            'The official test set was not used. Accuracy comparisons are validation results; selecting a best epoch uses validation information.',
            '', '## Refresh the log','',
            'From repository root:', '', '```powershell',
            'python reference_model/export_training_log.py', '```',
            '', 'Default source: build/reference_model/baseline_v1/. Default destination: reference_model/results/. The exported records are Git-visible; source checkpoints and caches remain ignored.']
    rendered='\n'.join('#'+line if line.startswith('## ') else line for line in lines)+'\n'
    update_training_section(destination/'README.md',rendered)
    print(f'Exported {len(runs)} run histories and summary to {destination}')


if __name__=='__main__':
    root=Path(__file__).resolve().parents[1]
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=root/'build/reference_model/baseline_v1')
    parser.add_argument('--destination',type=Path,default=root/'reference_model/results')
    args=parser.parse_args();export_log(args.source,args.destination)
