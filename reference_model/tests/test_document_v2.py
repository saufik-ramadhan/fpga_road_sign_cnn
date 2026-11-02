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


def test_generated_verilog_header_compiles(tmp_path):
    import shutil,subprocess
    root=Path(__file__).resolve().parents[1]/'models/p2-doc-int-v2'
    compiler=shutil.which('iverilog');runtime=shutil.which('vvp')
    if not compiler or not runtime or not root.exists():pytest.skip('Icarus/package unavailable')
    source=tmp_path/'header_test.v'
    source.write_text('module header_test;\n`include "params.vh"\ninitial begin\n'
                      'if (P2_ACC_BITS != 24 || P2_FC_INPUTS != 392 || P2_RESCALE_M != 43980 || P2_RESCALE_S != 25) $fatal(1,"constants");\n'
                      '$display("HEADER PASS"); $finish; end endmodule\n')
    exe=tmp_path/'header.vvp'
    subprocess.run([compiler,'-g2012','-I',str(root),'-o',str(exe),str(source)],check=True,capture_output=True,text=True)
    result=subprocess.run([runtime,str(exe)],check=True,capture_output=True,text=True)
    assert 'HEADER PASS' in result.stdout
