"""Calibrate on training data and simulate the p2-int-v1 contract on validation."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import numpy as np
import torch
from model import SignCNN
from golden import infer, scalar_infer, STAGES, INT32_MAX


def quantized_weights(values):
    scale=float(np.max(np.abs(values)))/127 if np.any(values) else 1.
    return np.clip(np.rint(values/scale),-127,127).astype(np.int8),scale


def quantized_bias(values, scale):
    result=np.rint(values.astype(np.float64)/scale)
    if np.any(np.abs(result)>INT32_MAX):raise OverflowError('Bias does not fit int32')
    return result.astype(np.int32)


def multiplier_shift(ratio):
    for shift in range(47,-1,-1):
        multiplier=int(round(ratio*(1<<shift)))
        if 1 <= multiplier <= 65535:return multiplier,shift
    raise ValueError('Scale cannot be represented by the requantization contract')


def bound(weights,bias,max_input):
    values=np.abs(weights.astype(np.int64)).reshape(len(bias),-1).sum(1)*max_input+np.abs(bias.astype(np.int64))
    if np.any(values>INT32_MAX):raise OverflowError('Conservative MAC bound exceeds int32')
    return int(values.max())


def metrics(truth,pred):
    cm=np.zeros((8,8),dtype=np.int64);np.add.at(cm,(truth,pred),1)
    recalls=np.diag(cm)/cm.sum(1)
    return dict(accuracy=float((truth==pred).mean()),recalls=recalls.tolist(),confusion=cm.tolist(),
                macro_recall=float(recalls.mean()))


def write_mem(path,values,bits):
    values=np.asarray(values);mask=(1<<bits)-1
    encoded=[format(int(v)&mask,f'0{bits//4}x') for v in values.ravel()]
    path.write_text('\n'.join(encoded)+'\n')
    # Verify exported two's complement values recover the exact integers.
    read=np.array([int(line,16) for line in path.read_text().splitlines()],dtype=np.int64)
    if np.any(values<0):read=np.where(read >= 1<<(bits-1),read-(1<<bits),read)
    if not np.array_equal(read,values.ravel()):raise AssertionError(f'Memory round-trip: {path}')


def main():
    root=Path(__file__).resolve().parents[1]
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline',type=Path,default=root/'build/reference_model/baseline_v1')
    p.add_argument('--checkpoint',type=Path)
    p.add_argument('--output',type=Path,default=root/'build/reference_model/integer_v1')
    args=p.parse_args();torch.set_num_threads(4)
    checkpoint_path=args.checkpoint or args.baseline/'size_16_seed_42/best.pt'
    if args.output.exists():raise ValueError('Choose a fresh output directory; no overwriting')
    args.output.mkdir(parents=True)
    manifest_bytes=(args.baseline/'split_manifest.json').read_bytes()
    manifest=json.loads(manifest_bytes)
    checkpoint=torch.load(checkpoint_path,map_location='cpu',weights_only=False)
    side=checkpoint['config']['image_size']
    if side not in (16,32):raise ValueError('Supported input sizes: 16 and 32')
    pool_side=(side-2)//2
    version='p2-int-v1' if side==16 else 'p2-int-32-v1'
    if checkpoint['config']['split_sha256']!=hashlib.sha256(manifest_bytes).hexdigest():
        raise ValueError('Checkpoint and split manifest disagree')
    if checkpoint['config']['class_map']!=manifest['class_map']:raise ValueError('Class mapping mismatch')
    model=SignCNN(side);model.load_state_dict(checkpoint['state_dict']);model.eval()
    with np.load(args.baseline/f'pixels_{side}.npz',allow_pickle=False) as f:
        pixels=f['pixels'];truth=f['labels'];is_val=f['is_validation']
    expected_labels=np.array([s['label'] for s in manifest['samples']])
    expected_val=np.array([s['split']=='validation' for s in manifest['samples']])
    if not np.array_equal(truth,expected_labels) or not np.array_equal(is_val,expected_val):
        raise ValueError('Cached data does not match manifest')
    # Training-only calibration uses the full post-ReLU maximum, no validation tuning.
    maximum=0.
    with torch.no_grad():
        for batch in np.array_split(pixels[~is_val],max(1,int((~is_val).sum())//256)):
            maximum=max(maximum,float(torch.relu(model.conv(torch.from_numpy(batch).float()/255)).max()))
    sx=1/255;sa=maximum/127 if maximum else 1.
    cw,sc=quantized_weights(model.conv.weight.detach().numpy())
    fw,sf=quantized_weights(model.fc.weight.detach().numpy())
    cb=quantized_bias(model.conv.bias.detach().numpy(),sx*sc)
    fb=quantized_bias(model.fc.bias.detach().numpy(),sa*sf)
    multiplier,shift=multiplier_shift(sx*sc/sa)
    params=dict(conv_weight=cw,conv_bias=cb,fc_weight=fw,fc_bias=fb)
    bounds=dict(conv_absolute_partial_sum=bound(cw,cb,255),fc_absolute_partial_sum=bound(fw,fb,127))
    bounds['rescale_including_rounding']=bounds['conv_absolute_partial_sum']*multiplier+((1<<(shift-1)) if shift else 0)
    if bounds['rescale_including_rounding']>(1<<63)-1:raise OverflowError('Rescale bound exceeds int64')
    contract=dict(version=version,image_size=side,filters=8,classes=manifest['class_map'],
                  input=dict(dtype='uint8',range=[0,255],scale=sx,zero_point=0),
                  weights=dict(dtype='int8',range=[-127,127],conv_scale=sc,fc_scale=sf,zero_point=0),
                  bias=dict(dtype='int32',conv_scale=sx*sc,fc_scale=sa*sf),
                  accumulator=dict(dtype='int32',overflow='forbidden; fail on overflow',mac_order='bias first then serial products'),
                  activation=dict(dtype='uint8',range=[0,127],scale=sa,calibration='training-only full ReLU maximum',training_maximum=maximum),
                  requantization=dict(multiplier=multiplier,shift=shift,multiplier_bits=16,intermediate_bits=64,
                                      formula='min(127, (max(0, acc)*M + (1<<(S-1))) >> S); rounding=0 if S=0',
                                      rounding='nearest, halfway upward after ReLU',ratio_requested=sx*sc/sa,ratio_actual=multiplier/(1<<shift)),
                  parameter_rounding='nearest ties to even (NumPy rint)',
                  pool='2x2 maximum, stride 2',flatten=f'CHW C order; index=(channel*{pool_side}+row)*{pool_side}+column',
                  scores=dict(dtype='int32',scale=sa*sf,rescale=False),argmax='lowest index on ties',
                  bounds=bounds,checkpoint_sha256=hashlib.sha256(checkpoint_path.read_bytes()).hexdigest(),
                  split_sha256=hashlib.sha256(manifest_bytes).hexdigest(),test_set_used=False)
    (args.output/'contract.json').write_text(json.dumps(contract,indent=2))
    np.savez_compressed(args.output/'parameters.npz',**params)
    (args.output/'split_manifest.json').write_bytes(manifest_bytes)
    mem=args.output/'mem';mem.mkdir()
    for name,value in params.items():write_mem(mem/(name+'.mem'),value,8 if 'weight' in name else 32)
    val_pixels=pixels[is_val];val_truth=truth[is_val]
    integer_parts=[];float_parts=[];saturated=0;active_count=0
    with torch.no_grad():
        for batch in np.array_split(val_pixels,max(1,len(val_pixels)//128)):
            trace=infer(batch,params,contract)
            integer_parts.append(trace['scores'])
            float_parts.append(model(torch.from_numpy(batch).float()/255).numpy())
            q=contract['requantization']; positive=np.maximum(trace['conv_acc'],0)
            raw=(positive*q['multiplier']+(1<<(q['shift']-1) if q['shift'] else 0))>>q['shift']
            saturated+=int((raw>127).sum());active_count+=raw.size
    scores=np.concatenate(integer_parts);floats=np.concatenate(float_parts)
    int_pred=scores.argmax(1);float_pred=floats.argmax(1)
    float_metrics=metrics(val_truth,float_pred);int_metrics=metrics(val_truth,int_pred)
    report=dict(float=float_metrics,integer=int_metrics,
                accuracy_drop_percentage_points=100*(float_metrics['accuracy']-int_metrics['accuracy']),
                prediction_agreement=float((int_pred==float_pred).mean()),changed_predictions=int((int_pred!=float_pred).sum()),
                activation_saturations=saturated,activation_values=active_count,
                dequantized_logit_mean_absolute_error=float(np.abs(scores*(sa*sf)-floats).mean()),
                integer_proposed_gate_passed=int_metrics['accuracy']>=.95 and min(int_metrics['recalls'])>=.9,
                validation_count=len(val_truth),calibration_count=int((~is_val).sum()),test_set_used=False)
    np.savez_compressed(args.output/'validation_outputs.npz',labels=val_truth,float_logits=floats,integer_scores=scores)
    val_samples=[s for s in manifest['samples'] if s['split']=='validation']
    with (args.output/'predictions.csv').open('w',newline='') as f:
        writer=csv.writer(f);writer.writerow(['path','track','label','float_prediction','integer_prediction'])
        writer.writerows((s['path'],s['track'],int(y),int(fp),int(ip)) for s,y,fp,ip in zip(val_samples,val_truth,float_pred,int_pred))
    # Two different tracks per class, then changed predictions up to 20 images.
    selected=[]
    for label in range(8):
        tracks=set()
        for i,s in enumerate(val_samples):
            if s['label']==label and s['track'] not in tracks:
                selected.append(i);tracks.add(s['track'])
                if len(tracks)==2:break
    for i in np.flatnonzero(int_pred!=float_pred):
        if len(selected)>=20:break
        if int(i) not in selected:selected.append(int(i))
    for i in range(len(val_samples)):
        if len(selected)>=20:break
        if i not in selected:selected.append(i)
    vectors=args.output/'vectors';vectors.mkdir();vector_manifest=[]
    directed=[('zeros',np.zeros((1,side,side),dtype=np.uint8)),('maximum',np.full((1,side,side),255,dtype=np.uint8)),
              ('checkerboard',((np.indices((side,side)).sum(0)%2)*255).astype(np.uint8)[None]),
              ('ramp',(np.arange(side*side)%256).astype(np.uint8).reshape(1,side,side))]
    impulse=np.zeros((1,side,side),dtype=np.uint8);impulse[0,side//2,side//2]=255;directed.append(('impulse',impulse))
    examples=[(f'val_{i:05d}',val_pixels[i],dict(source=val_samples[i]['path'],label=int(val_truth[i]))) for i in selected]
    examples += [(name,image,dict(source='synthetic numerical test; no semantic label')) for name,image in directed]
    for name,image,metadata in examples:
        vector=infer(image[None],params,contract);serial=scalar_infer(image,params,contract)
        for stage in STAGES:
            if not np.array_equal(vector[stage][0],serial[stage]):raise AssertionError(f'Oracle mismatch {name} {stage}')
        folder=vectors/name;folder.mkdir()
        np.savez_compressed(folder/'layers.npz',**{k:v[0] for k,v in vector.items()})
        for stage in STAGES:write_mem(folder/(stage+'.mem'),vector[stage][0],32 if stage in ('conv_acc','scores') else 8)
        vector_manifest.append(dict(name=name,**metadata,integer_prediction=int(vector['prediction'][0])))
    (vectors/'manifest.json').write_text(json.dumps(vector_manifest,indent=2))
    report['scalar_oracle_vectors_passed']=len(examples)
    report['rtl_simulation_run']=False
    (args.output/'metrics.json').write_text(json.dumps(report,indent=2))
    (args.output/'MEMORY_LAYOUT.md').write_text(f'# Memory layout for {version}\n\nOne hex word per line, no header. Negative words use two\'s complement.\nconv_weight: [filter, input_channel, kernel_row, kernel_column], int8.\nfc_weight: [output_class, CHW_input_index], int8. Biases are int32.\nImages: CHW [1,{side},{side}], uint8. Conv accumulators: [8,{side-2},{side-2}], int32.\nActivation: [8,{side-2},{side-2}], uint8. Pool: [8,{pool_side},{pool_side}], uint8. Scores: [8], int32.\nArgmax output: one uint8 word. All arrays use C order, last axis changes fastest.\nEach weight/bias layer has a separate file starting at address zero.\nWithin a word, hexadecimal digits are most significant first; UART byte order is not defined here.\nSee contract.json for multiplier/shift, exact rounding and scales.\nSynthetic vectors have no class label. No RTL simulator has been run.\n')
    files=[f for f in args.output.rglob('*') if f.is_file()]
    (args.output/'checksums.json').write_text(json.dumps({f.relative_to(args.output).as_posix():hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(files)},indent=2))
    print(json.dumps(report,indent=2));print('Integer simulation artifacts:',args.output)


if __name__=='__main__':main()
