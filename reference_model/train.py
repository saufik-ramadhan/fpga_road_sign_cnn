"""Reproducible float baseline; reports validation results, never test accuracy."""
import argparse
import csv
import hashlib
import json
import random
import time
from pathlib import Path

import numpy as np
import PIL
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from data import CLASS_NAMES, build_manifest, prepare
from model import SignCNN, architecture_cost


def evaluate(model, loader, classes=len(CLASS_NAMES)):
    model.eval(); total_loss=0.; predictions=[]; labels=[]
    with torch.no_grad():
        for x, y in loader:
            logits=model(x)
            total_loss += nn.functional.cross_entropy(logits, y, reduction='sum').item()
            predictions.extend(logits.argmax(1).tolist()); labels.extend(y.tolist())
    truth=np.array(labels); pred=np.array(predictions)
    confusion=np.zeros((classes, classes), dtype=int)
    np.add.at(confusion,(truth,pred),1)
    recalls=np.diag(confusion)/confusion.sum(1)
    return dict(accuracy=float((truth==pred).mean()),loss=total_loss/len(truth),
                recalls=recalls.tolist(),macro_recall=float(recalls.mean()),
                confusion=confusion.tolist()), pred


def train_one(args, size, seed, manifest):
    folder=args.output/f'size_{size}_seed_{seed}'
    if folder.exists():
        raise ValueError(f'Refusing to overwrite run: {folder}')
    folder.mkdir()
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True)
    with np.load(args.output/f'pixels_{size}.npz') as cached:
        x=torch.from_numpy(cached['pixels'].copy()).float()/255.
        y=torch.from_numpy(cached['labels'].copy()); v=cached['is_validation'].copy()
    train_data=TensorDataset(x[~v],y[~v]); val_data=TensorDataset(x[v],y[v])
    generator=torch.Generator().manual_seed(seed)
    training=DataLoader(train_data,batch_size=args.batch_size,shuffle=True,
                        generator=generator,num_workers=0)
    validation=DataLoader(val_data,batch_size=256,shuffle=False,num_workers=0)
    train_eval=DataLoader(train_data,batch_size=256,shuffle=False,num_workers=0)
    model=SignCNN(size)
    counts=torch.bincount(y[~v],minlength=len(CLASS_NAMES)).float()
    loss_fn=nn.CrossEntropyLoss(weight=len(train_data)/(len(CLASS_NAMES)*counts))
    optimizer=torch.optim.Adam(model.parameters(),lr=args.lr)
    config=dict(image_size=size,seed=seed,split_seed=args.split_seed,
                epochs_max=args.epochs,patience=args.patience,batch_size=args.batch_size,
                learning_rate=args.lr,optimizer='Adam',class_weighted_loss=True,
                augmentation='none',histogram_equalization=False,device='cpu',
                torch_version=torch.__version__,numpy_version=np.__version__,
                pillow_version=PIL.__version__,threads=args.threads,
                class_map=manifest['class_map'],cost=architecture_cost(size),
                split_sha256=hashlib.sha256((args.output/'split_manifest.json').read_bytes()).hexdigest())
    (folder/'config.json').write_text(json.dumps(config,indent=2))
    history=[]; best=-1.; stale=0; started=time.perf_counter()
    for epoch in range(1,args.epochs+1):
        model.train(); correct=0; seen=0
        for inputs, targets in training:
            optimizer.zero_grad(set_to_none=True)
            scores=model(inputs); loss=loss_fn(scores,targets)
            loss.backward(); optimizer.step()
            correct+=(scores.argmax(1)==targets).sum().item(); seen+=len(targets)
        metrics,_=evaluate(model,validation)
        history.append(dict(epoch=epoch,train_online_accuracy=correct/seen,
                            validation_accuracy=metrics['accuracy'],validation_loss=metrics['loss']))
        if metrics['accuracy']>best:
            best=metrics['accuracy']; stale=0
            torch.save(dict(state_dict=model.state_dict(),config=config,epoch=epoch),folder/'best.pt')
        else: stale+=1
        print(f'{size}x{size} seed={seed} epoch={epoch:02d} train={correct/seen:.4f} val={metrics["accuracy"]:.4f} best={best:.4f}',flush=True)
        if stale>=args.patience: break
    checkpoint=torch.load(folder/'best.pt',map_location='cpu',weights_only=False)
    model.load_state_dict(checkpoint['state_dict'])
    validation_metrics,pred=evaluate(model,validation)
    training_metrics,_=evaluate(model,train_eval)
    result=dict(image_size=size,seed=seed,best_epoch=checkpoint['epoch'],
                epochs_run=len(history),elapsed_seconds=time.perf_counter()-started,
                training=training_metrics,validation=validation_metrics,
                proposed_gate_passed=validation_metrics['accuracy']>=.95 and min(validation_metrics['recalls'])>=.9,
                gate_status='proposed working targets, not lecturer requirements',test_set_used=False)
    (folder/'metrics.json').write_text(json.dumps(result,indent=2))
    with (folder/'history.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(history[0]));writer.writeheader();writer.writerows(history)
    val_samples=[s for s in manifest['samples'] if s['split']=='validation']
    with (folder/'validation_predictions.csv').open('w',newline='') as f:
        writer=csv.writer(f);writer.writerow(['path','track','true_index','predicted_index'])
        writer.writerows((s['path'],s['track'],s['label'],int(p)) for s,p in zip(val_samples,pred))
    print('COMPLETED',json.dumps({k:result[k] for k in ['image_size','seed','best_epoch','proposed_gate_passed','elapsed_seconds']}),flush=True)


def main():
    root=Path(__file__).resolve().parents[1]
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,default=root.parent/'dataset')
    parser.add_argument('--output',type=Path,default=root/'build/reference_model/baseline_v1')
    parser.add_argument('--sizes',type=int,nargs='+',default=[16,32])
    parser.add_argument('--seeds',type=int,nargs='+',default=[42,43,44])
    parser.add_argument('--split-seed',type=int,default=2026)
    parser.add_argument('--epochs',type=int,default=40)
    parser.add_argument('--patience',type=int,default=12)
    parser.add_argument('--batch-size',type=int,default=128)
    parser.add_argument('--lr',type=float,default=.001)
    parser.add_argument('--threads',type=int,default=4)
    args=parser.parse_args()
    if any(n not in (16,32) for n in args.sizes):parser.error('Supported experiment sizes: 16 and 32')
    if args.epochs<1 or args.patience<1 or args.batch_size<1:parser.error('Counts must be positive')
    args.output.mkdir(parents=True,exist_ok=True)
    torch.set_num_threads(args.threads)
    manifest=build_manifest(args.dataset,args.output/'split_manifest.json',args.split_seed)
    prepare(args.dataset,args.output,args.sizes,manifest)
    for size in args.sizes:
        for seed in args.seeds:train_one(args,size,seed,manifest)
    from report import summarize
    summarize(args.output)


if __name__=='__main__':main()
