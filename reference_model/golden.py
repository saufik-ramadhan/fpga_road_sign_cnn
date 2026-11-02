"""Integer-only CNN reference for numerical contract p2-int-v1.

No floating point is used during inference. NumPy int64 is the execution
container; checked int32 accumulators and checked int64 rescaling define RTL.
"""
import json
from pathlib import Path
import numpy as np

INT32_MIN, INT32_MAX = -(1 << 31), (1 << 31) - 1
STAGES = ('input', 'conv_acc', 'activation', 'pool', 'scores', 'prediction')


def checked32(values):
    if np.any(values < INT32_MIN) or np.any(values > INT32_MAX):
        raise OverflowError('Signed 32-bit accumulator overflow')
    return values


def requant_relu(accumulator, multiplier, shift):
    if not (1 <= multiplier <= 65535 and 0 <= shift <= 47):
        raise ValueError('Invalid unsigned 16-bit multiplier or shift')
    checked32(accumulator)
    positive = np.maximum(accumulator, 0).astype(np.int64)
    rounding = (1 << (shift - 1)) if shift else 0
    if int(positive.max(initial=0)) * multiplier + rounding > np.iinfo(np.int64).max:
        raise OverflowError('Signed 64-bit rescale overflow')
    return np.clip((positive * multiplier + rounding) >> shift, 0, 127).astype(np.uint8)


def conv_accumulate(pixels, weights, bias):
    windows = np.lib.stride_tricks.sliding_window_view(pixels[:, 0], (3, 3), axis=(1, 2))
    result = np.einsum('nhwij,fij->nfhw', windows.astype(np.int64),
                       weights[:, 0].astype(np.int64), optimize=False)
    return checked32(result + bias.astype(np.int64)[None, :, None, None])


def infer(pixels, parameters, contract):
    pixels = np.asarray(pixels)
    side = contract['image_size']
    if pixels.dtype != np.uint8 or pixels.ndim != 4 or pixels.shape[1:] != (1, side, side) or not len(pixels):
        raise ValueError('Expected a nonempty NCHW uint8 input batch')
    acc = conv_accumulate(pixels, parameters['conv_weight'], parameters['conv_bias'])
    q = contract['requantization']
    activation = requant_relu(acc, q['multiplier'], q['shift'])
    n, channels, height, width = activation.shape
    pool = activation.reshape(n, channels, height//2, 2, width//2, 2).max(axis=(3, 5))
    scores = checked32(pool.reshape(n, -1).astype(np.int64) @
                       parameters['fc_weight'].astype(np.int64).T + parameters['fc_bias'])
    return dict(input=pixels, conv_acc=acc, activation=activation, pool=pool,
                scores=scores, prediction=scores.argmax(axis=1).astype(np.uint8))


def scalar_infer(image, parameters, contract):
    """Independent serial MAC oracle using Python integers, including each partial sum."""
    side = contract['image_size']; filters = len(parameters['conv_bias'])
    acc = np.empty((filters, side-2, side-2), dtype=np.int64)
    active = np.empty_like(acc, dtype=np.uint8)
    q = contract['requantization']; m, shift = q['multiplier'], q['shift']
    rounding = (1 << (shift-1)) if shift else 0
    for f in range(filters):
        for y in range(side-2):
            for x in range(side-2):
                value = int(parameters['conv_bias'][f])
                for ky in range(3):
                    for kx in range(3):
                        value += int(image[0,y+ky,x+kx]) * int(parameters['conv_weight'][f,0,ky,kx])
                        if not INT32_MIN <= value <= INT32_MAX:
                            raise OverflowError('Scalar convolution partial sum overflow')
                acc[f,y,x] = value
                product = max(0, value) * m + rounding
                if product > (1 << 63)-1: raise OverflowError('Scalar rescale overflow')
                active[f,y,x] = min(127, product >> shift)
    pool = np.empty((filters,(side-2)//2,(side-2)//2), dtype=np.uint8)
    for f in range(filters):
        for y in range(pool.shape[1]):
            for x in range(pool.shape[2]):
                pool[f,y,x] = max(int(active[f,2*y+dy,2*x+dx]) for dy in range(2) for dx in range(2))
    flat = pool.flatten().tolist(); scores=[]
    for output, bias in enumerate(parameters['fc_bias']):
        value=int(bias)
        for index, activation in enumerate(flat):
            value += activation * int(parameters['fc_weight'][output,index])
            if not INT32_MIN <= value <= INT32_MAX:
                raise OverflowError('Scalar FC partial sum overflow')
        scores.append(value)
    return dict(input=image,conv_acc=acc,activation=active,pool=pool,
                scores=np.array(scores,dtype=np.int64),prediction=np.uint8(max(range(len(scores)),key=lambda i:scores[i])))


def load_model(directory):
    directory=Path(directory)
    with np.load(directory/'parameters.npz',allow_pickle=False) as f:
        params={key:f[key].copy() for key in f.files}
    return params,json.loads((directory/'contract.json').read_text())


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description='Run integer inference on prepared uint8 NCHW .npy input')
    p.add_argument('model',type=Path);p.add_argument('pixels',type=Path);p.add_argument('output',type=Path)
    args=p.parse_args();params,contract=load_model(args.model)
    np.savez_compressed(args.output,**infer(np.load(args.pixels,allow_pickle=False),params,contract))
