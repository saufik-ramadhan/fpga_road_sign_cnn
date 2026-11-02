import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import pytest
import torch
from PIL import Image,ImageOps
from document_v2.data import preprocess,CLASSES,augment


def test_equalization_order_and_class_map():
    image=Image.fromarray(np.arange(100,dtype=np.uint8).reshape(10,10)+50)
    expected=np.asarray(ImageOps.equalize(image.convert('RGB').crop((1,1,9,9)).convert('L')).resize((16,16),Image.Resampling.BILINEAR))
    assert np.array_equal(preprocess(image,(1,1,8,8)),expected)
    assert list(CLASSES)==[14,13,17,12,18,38,1,2]
    assert preprocess(image,(1,1,8,8)).dtype==np.uint8


def test_augmentation_is_repeatable_and_bounded():
    x=torch.arange(256).reshape(1,1,16,16).float()/255
    torch.manual_seed(42);a=augment(x)
    torch.manual_seed(42);b=augment(x)
    assert torch.equal(a,b) and a.shape==x.shape
    assert a.min()>=0 and a.max()<=1 and not torch.equal(a,x)


def test_int24_contract_bounds_and_rounding():
    from document_v2.golden import checked24,requant_relu
    assert checked24(np.array([-8388608,8388607])).tolist()==[-8388608,8388607]
    with pytest.raises(OverflowError):checked24(np.array([8388608]))
    with pytest.raises(OverflowError):checked24(np.array([-8388609]))
    assert requant_relu(np.array([-1,0,1,2,3,255]),1,1).tolist()==[0,0,1,1,2,127]


def test_published_memory_and_coe_are_exact():
    import hashlib,json
    root=Path(__file__).resolve().parents[1]/'models/p2-doc-int-v2'
    if not root.exists():pytest.skip('Review package not present')
    h=json.loads((root/'checksums.json').read_text())
    assert all(hashlib.sha256((root/k).read_bytes()).hexdigest()==v for k,v in h.items())
    with np.load(root/'parameters.npz') as p:
        for name in p.files:
            bits=8 if 'weight' in name else 24
            words=(root/'mem'/f'{name}.mem').read_text().splitlines()
            raw=np.array([int(v,16) for v in words],dtype=np.int64)
            decoded=np.where(raw >= (1<<(bits-1)),raw-(1<<bits),raw)
            assert np.array_equal(decoded,p[name].ravel())
            coe=(root/'mem'/f'{name}.coe').read_text().split('memory_initialization_vector=')[1].strip().rstrip(';').replace('\n','').split(',')
            assert coe==words
    assert len((root/'signs.mem').read_text().splitlines())==4096
    assert len((root/'labels.mem').read_text().splitlines())==16


@pytest.mark.parametrize('header_source', ['published', 'generated'])
def test_generated_verilog_header_compiles_in_two_modules(tmp_path, header_source):
    import shutil,subprocess
    from document_v2.golden import load_model
    from document_v2.make_mem import write_params
    root=Path(__file__).resolve().parents[1]/'models/p2-doc-int-v2'
    compiler=shutil.which('iverilog');runtime=shutil.which('vvp')
    if not compiler or not runtime or not root.exists():pytest.skip('Icarus/package unavailable')
    params,contract=load_model(root)
    generated=tmp_path/'params.vh'
    write_params(generated,params,contract)
    assert generated.read_bytes()==(root/'params.vh').read_bytes()
    include_dir=root if header_source=='published' else tmp_path
    modules=[]
    for name in ('conv_consumer','fc_consumer'):
        modules.append(f'''module {name};
`include "params.vh"
initial begin
if (P2_ACC_BITS != 24 || P2_FC_INPUTS != 392 ||
    P2_RESCALE_M != {contract['requantization']['multiplier']} ||
    P2_RESCALE_S != {contract['requantization']['shift']} ||
    P2_CONV_BIAS_0 != {int(params['conv_bias'][0])} ||
    P2_FC_BIAS_0 != {int(params['fc_bias'][0])}) $fatal(1,"constants");
$display("HEADER PASS {name}");
end
endmodule
''')
    source=tmp_path/'header_test.v';source.write_text(''.join(modules))
    exe=tmp_path/'header.vvp'
    subprocess.run([compiler,'-g2005','-I',str(include_dir),'-o',str(exe),str(source)],check=True,capture_output=True,text=True)
    result=subprocess.run([runtime,str(exe)],check=True,capture_output=True,text=True)
    assert 'FATAL' not in result.stdout
    assert 'HEADER PASS conv_consumer' in result.stdout
    assert 'HEADER PASS fc_consumer' in result.stdout


def numerical_case():
    # 6x6 -> 4x4 conv -> 2x2 pool, one filter and one classifier.
    params=dict(conv_weight=np.zeros((1,1,3,3),dtype=np.int8),
                conv_bias=np.zeros(1,dtype=np.int64),
                fc_weight=np.zeros((1,4),dtype=np.int8),
                fc_bias=np.zeros(1,dtype=np.int64))
    contract=dict(image_size=6,requantization=dict(multiplier=1,shift=1))
    return np.full((1,1,6,6),255,dtype=np.uint8),params,contract


@pytest.mark.parametrize('stage', ['conv', 'fc'])
@pytest.mark.parametrize('sign', [1, -1])
def test_partial_overflow_before_cancellation_is_rejected(stage, sign):
    from document_v2.golden import infer,scalar_infer,INT24_MAX,INT24_MIN
    image,params,contract=numerical_case()
    limit=INT24_MAX if sign==1 else INT24_MIN
    params[stage+'_bias'][0]=limit-sign*7
    if stage=='conv':
        params['conv_weight'][0,0,0,:2]=[sign,-sign]
    else:
        params['conv_weight'][0,0,1,1]=1  # all pooled activations equal 127
        params['fc_weight'][0,:2]=[sign,-sign]
    # Final mathematical sum equals the in-range bias; the first MAC overflows.
    with pytest.raises(OverflowError):infer(image,params,contract)
    with pytest.raises(OverflowError):scalar_infer(image[0],params,contract)


@pytest.mark.parametrize('stage', ['conv', 'fc'])
@pytest.mark.parametrize('sign', [1, -1])
def test_partial_sum_at_exact_limit_remains_valid(stage, sign):
    from document_v2.golden import infer,scalar_infer,STAGES,INT24_MAX,INT24_MIN
    image,params,contract=numerical_case()
    limit=INT24_MAX if sign==1 else INT24_MIN
    if stage=='conv':
        params['conv_bias'][0]=limit-sign*255
        params['conv_weight'][0,0,0,:2]=[sign,-sign]
    else:
        params['conv_weight'][0,0,1,1]=1
        params['fc_bias'][0]=limit-sign*127
        params['fc_weight'][0,:2]=[sign,-sign]
    trace=infer(image,params,contract);serial=scalar_infer(image[0],params,contract)
    for part in STAGES:assert np.array_equal(trace[part][0],serial[part]),part


@pytest.mark.parametrize('stage', ['conv', 'fc'])
@pytest.mark.parametrize('sign', [1, -1])
def test_invalid_initial_bias_cannot_be_cancelled(stage, sign):
    from document_v2.golden import infer,scalar_infer,INT24_MAX,INT24_MIN
    image,params,contract=numerical_case()
    params[stage+'_bias'][0]=(INT24_MAX+1) if sign==1 else (INT24_MIN-1)
    if stage=='conv':params['conv_weight'][0,0,0,0]=-sign
    else:
        params['conv_weight'][0,0,1,1]=1
        params['fc_weight'][0,0]=-sign
    with pytest.raises(OverflowError):infer(image,params,contract)
    with pytest.raises(OverflowError):scalar_infer(image[0],params,contract)


def test_all_published_vectors_match_inference_and_serial_oracle():
    from document_v2.golden import infer,scalar_infer,load_model,STAGES
    root=Path(__file__).resolve().parents[1]/'models/p2-doc-int-v2'
    params,contract=load_model(root)
    folders=sorted(p for p in (root/'vectors').iterdir() if p.is_dir())
    assert len(folders)==25
    for folder in folders:
        with np.load(folder/'layers.npz',allow_pickle=False) as saved:
            trace=infer(saved['input'][None],params,contract)
            serial=scalar_infer(saved['input'],params,contract)
            for stage in STAGES:
                assert np.array_equal(trace[stage][0],saved[stage]),(folder.name,stage)
                assert np.array_equal(trace[stage][0],serial[stage]),(folder.name,stage)


def test_batched_multichannel_inference_matches_serial_oracle():
    from document_v2.golden import infer,scalar_infer,STAGES
    rng=np.random.default_rng(2026)
    params=dict(conv_weight=rng.integers(-127,128,(2,1,3,3),dtype=np.int16).astype(np.int8),
                conv_bias=np.array([-500,100],dtype=np.int64),
                fc_weight=rng.integers(-127,128,(3,8),dtype=np.int16).astype(np.int8),
                fc_bias=np.array([-17,200,31],dtype=np.int64))
    contract=dict(image_size=6,requantization=dict(multiplier=3,shift=9))
    pixels=rng.integers(0,256,(2,1,6,6),dtype=np.uint8)
    trace=infer(pixels,params,contract)
    for i in range(len(pixels)):
        serial=scalar_infer(pixels[i],params,contract)
        for stage in STAGES:assert np.array_equal(trace[stage][i],serial[stage]),stage
