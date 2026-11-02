import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import pytest
from golden import requant_relu, infer, scalar_infer, STAGES, checked32
from quantize import multiplier_shift, bound, write_mem


def test_relu_rounding_saturation_and_zero_shift():
    acc=np.array([-3,-1,0,1,2,3,253,254,255,256],dtype=np.int64)
    assert requant_relu(acc,1,1).tolist()==[0,0,0,1,1,2,127,127,127,127]
    assert requant_relu(np.array([0,1,126,127,128]),1,0).tolist()==[0,1,126,127,127]
    assert requant_relu(np.array([-(1<<31),(1<<31)-1],dtype=np.int64),65535,47).tolist()==[0,1]


def test_overflow_is_an_error():
    with pytest.raises(OverflowError):checked32(np.array([1<<31],dtype=np.int64))
    with pytest.raises(OverflowError):checked32(np.array([-(1<<31)-1],dtype=np.int64))
    with pytest.raises(OverflowError):bound(np.array([[127]*10]),np.array([(1<<31)-1]),255)
    with pytest.raises(ValueError):requant_relu(np.array([1]),0,1)


def test_integer_mac_layout_pooling_and_tie_oracle():
    # Small spatial size exercises exact CHW flattening with mixed signed weights.
    rng=np.random.default_rng(123)
    params=dict(conv_weight=rng.integers(-127,128,(2,1,3,3),dtype=np.int16).astype(np.int8),
                conv_bias=np.array([-500,100],dtype=np.int32),
                fc_weight=rng.integers(-127,128,(3,8),dtype=np.int16).astype(np.int8),
                fc_bias=np.array([-17,200,31],dtype=np.int32))
    contract=dict(image_size=6,requantization=dict(multiplier=3,shift=9))
    pixels=rng.integers(0,256,(2,1,6,6),dtype=np.uint8)
    vector=infer(pixels,params,contract)
    for i in range(2):
        serial=scalar_infer(pixels[i],params,contract)
        for stage in STAGES:assert np.array_equal(vector[stage][i],serial[stage]),stage
    params['fc_weight'][:]=0;params['fc_bias'][:]=0
    assert infer(pixels,params,contract)['prediction'].tolist()==[0,0]
    assert scalar_infer(pixels[0],params,contract)['prediction']==0


def test_multiplier_accuracy_and_twos_complement(tmp_path):
    ratio=0.00012345;m,s=multiplier_shift(ratio)
    assert 1<=m<=65535 and 0<=s<=47
    assert abs(m/(1<<s)-ratio)/ratio<.0001
    write_mem(tmp_path/'weights.mem',np.array([-127,-1,0,1,127]),8)
    assert (tmp_path/'weights.mem').read_text().splitlines()==['81','ff','00','01','7f']
    write_mem(tmp_path/'scores.mem',np.array([-(1<<31),-1,0,(1<<31)-1]),32)
    assert (tmp_path/'scores.mem').read_text().splitlines()==['80000000','ffffffff','00000000','7fffffff']
