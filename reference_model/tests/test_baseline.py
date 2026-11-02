import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import csv
import numpy as np
import pytest
import torch
from PIL import Image
from data import CLASS_NAMES, build_manifest, preprocess
from model import SignCNN, architecture_cost


def test_track_split_keeps_neighbor_frames_together(tmp_path):
    rows=[]
    for cid in CLASS_NAMES:
        for track in range(5):
            for frame in range(3):
                rows.append(dict(Path=f'Train/{cid}/{cid:05d}_{track:05d}_{frame:05d}.png',ClassId=cid,
                                 Width=8,Height=8,**{'Roi.X1':1,'Roi.Y1':1,'Roi.X2':6,'Roi.Y2':6}))
    with (tmp_path/'Train.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    a=build_manifest(tmp_path,tmp_path/'split.json')
    b=build_manifest(tmp_path,tmp_path/'split.json')
    assert a==b
    train={s['track'] for s in a['samples'] if s['split']=='train'}
    validation={s['track'] for s in a['samples'] if s['split']=='validation'}
    assert train.isdisjoint(validation)
    assert len(validation)==len(CLASS_NAMES)


def test_inclusive_roi_keeps_last_pixel():
    pixels=np.zeros((4,4,3),dtype=np.uint8);pixels[2,2]=255
    actual=preprocess(Image.fromarray(pixels),(1,1,2,2),2)
    assert actual.shape==(2,2) and actual.dtype==np.uint8
    assert actual.tolist()==[[0,0],[0,255]]
    with pytest.raises(ValueError):preprocess(Image.fromarray(pixels),(1,1,4,4),2)


@pytest.mark.parametrize('size,weights,macs',[(16,3208,17248),(32,14472,79200)])
def test_model_dimensions_and_hardware_budget(size,weights,macs):
    model=SignCNN(size)
    assert model(torch.zeros(3,1,size,size)).shape==(3,8)
    cost=architecture_cost(size)
    assert cost['weights']==weights and cost['macs']==macs
    assert sum(p.numel() for p in model.parameters())==weights+16
