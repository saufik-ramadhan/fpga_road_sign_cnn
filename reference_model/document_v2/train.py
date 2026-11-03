"""Train the document-based 16x16 candidate with equalization and augmentation."""
import argparse,csv,hashlib,json,random,sys,time
import os
import tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import torch
from torch.utils.data import DataLoader,TensorDataset
from model import SignCNN,architecture_cost
from train import evaluate
from document_v2.data import class_names,build_manifest,prepare,augment,PREPROCESSING

ARCHITECTURES = {
    'A': (16, 8, False),
    'B': (32, 8, False),
    'C': (16, 16, False),
    'D': (16, 8, True),
}


def experiment_split(dataset, shared, output, classes=8):
    """Publish a complete split once, then copy its exact bytes into each run."""
    shared.parent.mkdir(parents=True, exist_ok=True)
    if not shared.exists():
        with tempfile.TemporaryDirectory(dir=shared.parent) as directory:
            temporary = Path(directory)
            build_manifest(dataset, temporary, classes)
            try:
                os.link(temporary / 'split_manifest.json', shared)
            except FileExistsError:
                pass  # Another training process already published the split.
    encoded = shared.read_bytes()
    manifest = json.loads(encoded)
    if manifest['train_csv_sha256'] != hashlib.sha256((dataset / 'Train.csv').read_bytes()).hexdigest():
        raise ValueError('Shared split belongs to another Train.csv. Select a new shared split path.')
    expected = [dict(index=i, gtsrb_id=cid, name=name) for i, (cid, name) in enumerate(class_names(classes).items())]
    if manifest['class_map'] != expected or manifest['preprocessing'] != PREPROCESSING:
        raise ValueError('Shared split must use the document-v2 class order and recipe.')
    tracks = {}
    for sample in manifest['samples']:
        key = sample['track']
        split = sample['split']
        if split not in ('train', 'validation') or tracks.setdefault(key, split) != split:
            raise ValueError('Shared split contains an invalid or overlapping track assignment.')
        if sample['label'] not in range(classes) or expected[sample['label']]['gtsrb_id'] != sample['original_class']:
            raise ValueError('Shared split label mismatch.')
    for split in ('train', 'validation'):
        if {s['label'] for s in manifest['samples'] if s['split'] == split} != set(range(classes)):
            raise ValueError(f'Shared split lacks classes in {split}.')
    (output / 'split_manifest.json').write_bytes(encoded)
    return manifest


def train_run(args,seed,manifest,x,y,v):
    size, filters, second_conv = ARCHITECTURES[args.profile]
    folder=args.output/f'size_{size}_seed_{seed}';folder.mkdir()
    random.seed(seed);np.random.seed(seed);torch.manual_seed(seed)
    classes = len(manifest['class_map'])
    model=SignCNN(size, classes=classes, filters=filters, second_conv=second_conv)
    train=DataLoader(TensorDataset(x[~v],y[~v]),batch_size=128,shuffle=True,
                     generator=torch.Generator().manual_seed(seed))
    val=DataLoader(TensorDataset(x[v],y[v]),batch_size=256)
    teval=DataLoader(TensorDataset(x[~v],y[~v]),batch_size=256)
    counts=torch.bincount(y[~v],minlength=classes).float()
    criterion=torch.nn.CrossEntropyLoss(weight=(~v).sum()/(classes*counts))
    optimizer=torch.optim.Adam(model.parameters(),lr=.001)
    config=dict(version='document-v2',image_size=size,seed=seed,split_seed=manifest['split_seed'],
                profile=args.profile,classes=classes,filters=filters,second_conv=second_conv,
                epochs_max=args.epochs,patience=12,batch_size=128,learning_rate=.001,
                optimizer='Adam',class_weighted_loss=True,preprocessing=dict(PREPROCESSING, image_size=size),
                class_map=manifest['class_map'],cost=architecture_cost(size, classes=classes, filters=filters, second_conv=second_conv),torch_version=torch.__version__,
                numpy_version=np.__version__,split_sha256=hashlib.sha256((args.output/'split_manifest.json').read_bytes()).hexdigest())
    (folder/'config.json').write_text(json.dumps(config,indent=2))
    history=[];best=-1;stale=0;started=time.perf_counter()
    for epoch in range(1,args.epochs+1):
        model.train();correct=seen=0
        for bx,by in train:
            optimizer.zero_grad(set_to_none=True);logits=model(augment(bx));loss=criterion(logits,by)
            loss.backward();optimizer.step();correct+=int((logits.argmax(1)==by).sum());seen+=len(by)
        metrics,_=evaluate(model,val,classes)
        history.append(dict(epoch=epoch,train_online_accuracy=correct/seen,
                            validation_accuracy=metrics['accuracy'],validation_loss=metrics['loss']))
        if metrics['accuracy']>best:
            best=metrics['accuracy'];stale=0
            torch.save(dict(state_dict=model.state_dict(),config=config,epoch=epoch),folder/'best.pt')
        else:stale+=1
        print(f'document-v2 seed={seed} epoch={epoch:02d} train_aug={correct/seen:.4f} val={metrics["accuracy"]:.4f}',flush=True)
        if stale>=12:break
    saved=torch.load(folder/'best.pt',map_location='cpu',weights_only=False);model.load_state_dict(saved['state_dict'])
    vm,pred=evaluate(model,val,classes);tm,_=evaluate(model,teval,classes)
    result=dict(image_size=size,classes=classes,seed=seed,best_epoch=saved['epoch'],epochs_run=len(history),
                elapsed_seconds=time.perf_counter()-started,training=tm,validation=vm,
                proposed_gate_passed=vm['accuracy']>=.95,test_set_used=False)
    (folder/'metrics.json').write_text(json.dumps(result,indent=2))
    with (folder/'history.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(history[0]));w.writeheader();w.writerows(history)
    with (folder/'validation_predictions.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['path','track','true_index','predicted_index'])
        w.writerows((s['path'],s['track'],s['label'],int(p)) for s,p in zip([s for s in manifest['samples'] if s['split']=='validation'],pred))
    print('COMPLETED',json.dumps(result),flush=True)
    return dict(seed=seed, best_epoch=saved['epoch'], validation=vm)


if __name__=='__main__':
    root=Path(__file__).resolve().parents[2]
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,default=root.parent/'dataset')
    parser.add_argument('--output',type=Path,default=root/'build/reference_model/document_v2')
    parser.add_argument('--seeds',type=int,nargs='+',default=[42,43,44])
    parser.add_argument('--epochs',type=int,default=60)
    parser.add_argument('--profile', choices=ARCHITECTURES, default='A')
    parser.add_argument('--classes', type=int, choices=(8, 43), default=8)
    parser.add_argument('--shared-split', type=Path)
    args=parser.parse_args()
    if args.epochs < 1 or len(set(args.seeds)) != len(args.seeds):
        parser.error('Use positive epochs and distinct seeds')
    if args.profile != 'A' and args.shared_split is None:
        parser.error('Architecture experiments require --shared-split')
    if args.output.exists():raise ValueError('Choose a new output directory')
    args.output.mkdir(parents=True);torch.set_num_threads(4);torch.use_deterministic_algorithms(True)
    size, filters, second_conv = ARCHITECTURES[args.profile]
    classes = args.classes
    manifest = (experiment_split(args.dataset, args.shared_split, args.output, classes)
                if args.shared_split else build_manifest(args.dataset, args.output, classes))
    prepare(args.dataset,args.output,manifest,size)
    with np.load(args.output/f'pixels_{size}.npz') as c:
        x=torch.from_numpy(c['pixels'].copy()).float()/255;y=torch.from_numpy(c['labels'].copy());v=c['is_validation'].copy()
    runs = [train_run(args, seed, manifest, x, y, v) for seed in args.seeds]
    accuracies = [run['validation']['accuracy'] for run in runs]
    summary = dict(profile=args.profile, classes=classes, split_sha256=hashlib.sha256(
        (args.output/'split_manifest.json').read_bytes()).hexdigest(),
        epochs_max=args.epochs, seeds=args.seeds, class_map=manifest['class_map'],
        image_size=size, filters=filters, second_conv=second_conv,
        cost=architecture_cost(size, classes=classes, filters=filters, second_conv=second_conv),
        mean_accuracy=float(np.mean(accuracies)), std_accuracy=float(np.std(accuracies)),
        mean_recalls=np.mean([run['validation']['recalls'] for run in runs],axis=0).tolist(),
        runs=runs, test_set_used=False)
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2))
