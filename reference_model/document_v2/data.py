"""Deterministic document preprocessing with explicit class order."""
import json
from pathlib import Path
import numpy as np
import torch
from PIL import Image
from .preprocessing import preprocess_image
from data import build_manifest as old_manifest

CLASSES={14:'Stop',13:'Yield',17:'No entry',12:'Priority road',18:'General caution',
         38:'Keep right',1:'Speed limit 30',2:'Speed limit 50'}
PREPROCESSING={'version':'document-v2','roi':'inclusive maximum coordinates',
               'order':['RGB ROI crop','Pillow grayscale L','Pillow ImageOps.equalize','bilinear resize'],
               'image_size':16,'pixels':'uint8 row-major 0..255','float_input':'pixels / 255',
               'augmentation':{'training_only':True,'after_base_preprocessing':True,
                               'rotation_degrees':[-5,5],'translation_pixels':[-1,1],
                               'brightness_multiplier':[.9,1.1],
                               'interpolation':'bilinear grid_sample, zero padding, align_corners=False'}}


def preprocess(image,roi,size=16):
    return np.asarray(preprocess_image(image, roi, size), dtype=np.uint8)


def build_manifest(dataset,output):
    # Preserve the previously reviewed track split to avoid changing two variables.
    old=old_manifest(dataset,output/'source_split.json',2026)
    mapping={cid:i for i,cid in enumerate(CLASSES)}
    for sample in old['samples']:sample['label']=mapping[sample['original_class']]
    old['class_map']=[dict(index=mapping[c],gtsrb_id=c,name=n) for c,n in CLASSES.items()]
    old['preprocessing']=PREPROCESSING
    (output/'split_manifest.json').write_text(json.dumps(old,indent=2))
    return old


def prepare(dataset,output,manifest):
    pixels=np.empty((len(manifest['samples']),1,16,16),dtype=np.uint8)
    for i,s in enumerate(manifest['samples']):
        with Image.open(dataset/s['path']) as im:
            im.load()
            if im.size!=(s['width'],s['height']):raise ValueError('Image dimensions disagree')
            pixels[i,0]=preprocess(im,s['roi'])
        if (i+1)%3000==0:print(f'Prepared {i+1}/{len(pixels)} equalized images',flush=True)
    np.savez_compressed(output/'pixels_16.npz',pixels=pixels,
                        labels=np.array([s['label'] for s in manifest['samples']],dtype=np.int64),
                        is_validation=np.array([s['split']=='validation' for s in manifest['samples']]))
    (output/'preprocessing.json').write_text(json.dumps(PREPROCESSING,indent=2))


def augment(x):
    """Small batch transforms; no effect on evaluation/prepared UART bytes."""
    n=x.shape[0];angle=(torch.rand(n)*10-5)*np.pi/180
    theta=torch.zeros(n,2,3)
    theta[:,0,0]=theta[:,1,1]=angle.cos()
    theta[:,0,1]=-angle.sin();theta[:,1,0]=angle.sin()
    theta[:,:,2]=(torch.rand(n,2)*2-1)*(2/x.shape[-1])
    grid=torch.nn.functional.affine_grid(theta,x.size(),align_corners=False)
    shifted=torch.nn.functional.grid_sample(x,grid,mode='bilinear',padding_mode='zeros',align_corners=False)
    brightness=(.9+torch.rand(n,1,1,1)*.2)
    return (shifted*brightness).clamp(0,1)
