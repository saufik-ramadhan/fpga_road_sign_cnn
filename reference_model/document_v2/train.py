"""Train the document-based 16x16 candidate with equalization and augmentation."""
import argparse,csv,hashlib,json,random,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import torch
from torch.utils.data import DataLoader,TensorDataset
from model import SignCNN,architecture_cost
from train import evaluate
from document_v2.data import build_manifest,prepare,augment,PREPROCESSING


def train_run(args,seed,manifest,x,y,v):
    folder=args.output/f'size_16_seed_{seed}';folder.mkdir()
    random.seed(seed);np.random.seed(seed);torch.manual_seed(seed)
    model=SignCNN(16)
    train=DataLoader(TensorDataset(x[~v],y[~v]),batch_size=128,shuffle=True,
                     generator=torch.Generator().manual_seed(seed))
    val=DataLoader(TensorDataset(x[v],y[v]),batch_size=256)
    teval=DataLoader(TensorDataset(x[~v],y[~v]),batch_size=256)
    counts=torch.bincount(y[~v],minlength=8).float()
    criterion=torch.nn.CrossEntropyLoss(weight=(~v).sum()/(8*counts))
    optimizer=torch.optim.Adam(model.parameters(),lr=.001)
    config=dict(version='document-v2',image_size=16,seed=seed,split_seed=2026,
                epochs_max=args.epochs,patience=12,batch_size=128,learning_rate=.001,
                optimizer='Adam',class_weighted_loss=True,preprocessing=PREPROCESSING,
                class_map=manifest['class_map'],cost=architecture_cost(16),torch_version=torch.__version__,
                numpy_version=np.__version__,split_sha256=hashlib.sha256((args.output/'split_manifest.json').read_bytes()).hexdigest())
    (folder/'config.json').write_text(json.dumps(config,indent=2))
    history=[];best=-1;stale=0;started=time.perf_counter()
    for epoch in range(1,args.epochs+1):
        model.train();correct=seen=0
        for bx,by in train:
            optimizer.zero_grad(set_to_none=True);logits=model(augment(bx));loss=criterion(logits,by)
            loss.backward();optimizer.step();correct+=int((logits.argmax(1)==by).sum());seen+=len(by)
        metrics,_=evaluate(model,val)
        history.append(dict(epoch=epoch,train_online_accuracy=correct/seen,
                            validation_accuracy=metrics['accuracy'],validation_loss=metrics['loss']))
        if metrics['accuracy']>best:
            best=metrics['accuracy'];stale=0
            torch.save(dict(state_dict=model.state_dict(),config=config,epoch=epoch),folder/'best.pt')
        else:stale+=1
        print(f'document-v2 seed={seed} epoch={epoch:02d} train_aug={correct/seen:.4f} val={metrics["accuracy"]:.4f}',flush=True)
        if stale>=12:break
    saved=torch.load(folder/'best.pt',map_location='cpu',weights_only=False);model.load_state_dict(saved['state_dict'])
    vm,pred=evaluate(model,val);tm,_=evaluate(model,teval)
    result=dict(image_size=16,seed=seed,best_epoch=saved['epoch'],epochs_run=len(history),
                elapsed_seconds=time.perf_counter()-started,training=tm,validation=vm,
                proposed_gate_passed=vm['accuracy']>=.95,test_set_used=False)
    (folder/'metrics.json').write_text(json.dumps(result,indent=2))
    with (folder/'history.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(history[0]));w.writeheader();w.writerows(history)
    with (folder/'validation_predictions.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['path','track','true_index','predicted_index'])
        w.writerows((s['path'],s['track'],s['label'],int(p)) for s,p in zip([s for s in manifest['samples'] if s['split']=='validation'],pred))
    print('COMPLETED',json.dumps(result),flush=True)


if __name__=='__main__':
    root=Path(__file__).resolve().parents[2]
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,default=root.parent/'dataset')
    parser.add_argument('--output',type=Path,default=root/'build/reference_model/document_v2')
    parser.add_argument('--seeds',type=int,nargs='+',default=[42,43,44])
    parser.add_argument('--epochs',type=int,default=60)
    args=parser.parse_args()
    if args.output.exists():raise ValueError('Choose a new output directory')
    args.output.mkdir(parents=True);torch.set_num_threads(4);torch.use_deterministic_algorithms(True)
    manifest=build_manifest(args.dataset,args.output);prepare(args.dataset,args.output,manifest)
    with np.load(args.output/'pixels_16.npz') as c:
        x=torch.from_numpy(c['pixels'].copy()).float()/255;y=torch.from_numpy(c['labels'].copy());v=c['is_validation'].copy()
    for seed in args.seeds:train_run(args,seed,manifest,x,y,v)
