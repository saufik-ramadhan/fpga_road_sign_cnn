"""Summarize completed validation runs and plot learning curves and mistakes."""
import argparse
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def summarize(output):
    manifest=json.loads((output/'split_manifest.json').read_text())
    labels=[c['name'] for c in manifest['class_map']]
    results=[]
    for metrics_file in sorted(output.glob('size_*/metrics.json')):
        folder=metrics_file.parent; m=json.loads(metrics_file.read_text());results.append(m)
        with (folder/'history.csv').open() as f:history=list(csv.DictReader(f))
        fig,axes=plt.subplots(1,2,figsize=(10,3.6),layout='constrained')
        epochs=[int(h['epoch']) for h in history]
        axes[0].plot(epochs,[float(h['train_online_accuracy']) for h in history],label='Training during updates')
        axes[0].plot(epochs,[float(h['validation_accuracy']) for h in history],label='Validation')
        axes[0].axvline(m['best_epoch'],color='gray',ls='--',lw=1)
        axes[0].set(xlabel='Epoch',ylabel='Accuracy',ylim=(0,1));axes[0].legend(fontsize=8)
        axes[1].plot(epochs,[float(h['validation_loss']) for h in history])
        axes[1].set(xlabel='Epoch',ylabel='Unweighted validation cross entropy')
        fig.suptitle(f"{m['image_size']} x {m['image_size']} — seed {m['seed']}")
        fig.savefig(folder/'learning_curves.png',dpi=150);plt.close(fig)
        cm=np.array(m['validation']['confusion'])
        fig,ax=plt.subplots(figsize=(8,7),layout='constrained')
        im=ax.imshow(cm,cmap='Blues')
        ax.set(xticks=range(8),xticklabels=labels,yticks=range(8),yticklabels=labels,
               xlabel='Predicted class',ylabel='True class',title='Validation confusion matrix at best epoch')
        plt.setp(ax.get_xticklabels(),rotation=45,ha='right',fontsize=8)
        for i in range(8):
            for j in range(8):ax.text(j,i,str(cm[i,j]),ha='center',va='center',fontsize=9,color='white' if cm[i,j]>cm.max()/2 else 'black')
        fig.colorbar(im,ax=ax,shrink=.7);fig.savefig(folder/'confusion_matrix.png',dpi=150);plt.close(fig)
        with (folder/'validation_predictions.csv').open() as f:predictions=list(csv.DictReader(f))
        wrong=[(i,r) for i,r in enumerate(predictions) if r['true_index']!=r['predicted_index']][:12]
        if wrong:
            with np.load(output/f"pixels_{m['image_size']}.npz") as cache:pixels=cache['pixels'][cache['is_validation']]
            fig,axes=plt.subplots(3,4,figsize=(10,7),layout='constrained')
            for ax in axes.flat:ax.axis('off')
            for ax,(idx,row) in zip(axes.flat,wrong):
                ax.imshow(pixels[idx,0],cmap='gray',vmin=0,vmax=255,interpolation='nearest')
                ax.set_title('True: '+labels[int(row['true_index'])]+'\nPred: '+labels[int(row['predicted_index'])],fontsize=8)
            fig.suptitle('First validation mistakes in fixed path order')
            fig.savefig(folder/'validation_mistakes.png',dpi=150);plt.close(fig)
    lines=['# Float CNN validation experiment','',
           'Training data: eight selected GTSRB classes. Official test data was not used.',
           'Split: stratified by class at physical-sign track level; split seed 2026.',
           'Preprocessing: inclusive ROI crop, Pillow grayscale, bilinear resize, divide by 255.',
           'Training: Adam, class-weighted cross entropy, no augmentation or histogram equalization.',
           'Each run selects its best validation-accuracy checkpoint. Results are exploratory validation estimates.',
           'The 32x32 model has more classifier parameters, so this is not a pure resolution-only ablation.','',
           '| Size | Seed | Epoch | Train accuracy | Validation accuracy | Macro recall | Minimum class recall | Proposed gate |',
           '|---|---|---|---|---|---|---|---|']
    for m in results:
        v=m['validation'];lines.append(f"| {m['image_size']} | {m['seed']} | {m['best_epoch']} | {m['training']['accuracy']:.2%} | {v['accuracy']:.2%} | {v['macro_recall']:.2%} | {min(v['recalls']):.2%} | {'Pass' if m['proposed_gate_passed'] else 'Below target'} |")
    lines+=['','## Per class validation recall','', '| Class | '+' | '.join(f"{m['image_size']} seed {m['seed']}" for m in results)+' |', '|---|'+'---|'*len(results)]
    for i,label in enumerate(labels):lines.append('| '+label+' | '+' | '.join(f"{m['validation']['recalls'][i]:.2%}" for m in results)+' |')
    lines+=['','## Repeated seed summary','']
    aggregates={}
    for size in sorted({m['image_size'] for m in results}):
        values=[m['validation']['accuracy'] for m in results if m['image_size']==size]
        aggregates[size]=dict(runs=len(values),mean_accuracy=float(np.mean(values)),seed_sd=float(np.std(values)))
        lines.append(f'{size}x{size}: {len(values)} runs, mean accuracy {np.mean(values):.2%}, population SD across seeds {np.std(values):.2%}.')
    lines+=['','Working targets: at least 95% validation accuracy and 90% recall in every selected class. These are proposed project criteria, not lecturer requirements.',
            'Seed variation does not measure uncertainty across new sign tracks. No integer accuracy or FPGA latency has been measured.',
            'Before architecture freeze, review mistakes and quantization degradation. Keep the official test split reserved until decisions are frozen.']
    (output/'SUMMARY.md').write_text('\n'.join(lines)+'\n')
    (output/'summary.json').write_text(json.dumps(dict(runs=results,aggregates=aggregates),indent=2))
    if results:
        fig,ax=plt.subplots(figsize=(7,4.5),layout='constrained')
        sizes=sorted(aggregates)
        for x,size in enumerate(sizes):
            subset=[m for m in results if m['image_size']==size]
            values=[m['validation']['accuracy']*100 for m in subset]
            offsets=np.linspace(-.12,.12,len(values))
            ax.scatter(x+offsets,values,s=65,color='#197A83',zorder=3)
            for offset,value,m in zip(offsets,values,subset):
                ax.annotate(str(m['seed']),(x+offset,value),xytext=(5,5),textcoords='offset points',fontsize=8)
            ax.plot([x-.2,x+.2],[np.mean(values)]*2,color='#19364D',lw=3)
        ax.axhline(95,color='gray',ls='--',lw=1,label='Proposed overall target (95%)')
        ax.set(xticks=range(len(sizes)),xticklabels=[f'{s} x {s}' for s in sizes],
               ylabel='Best-checkpoint validation accuracy (%)',ylim=(90,100),
               title='Same sign-track split, three initialization seeds')
        ax.legend(loc='lower left',fontsize=8)
        fig.savefig(output/'resolution_comparison.png',dpi=160);plt.close(fig)
    print('\n'.join(lines[:20]),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('output',type=Path)
    summarize(parser.parse_args().output)
