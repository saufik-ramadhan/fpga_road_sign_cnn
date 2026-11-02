"""Integer-only CNN reference for numerical contract p2-doc-int-v2.

No floating point is used during inference. NumPy int64 is the execution
container; checked signed 24-bit accumulators and 48-bit rescaling define RTL.
"""
import json
from pathlib import Path
import numpy as np

INT24_MIN, INT24_MAX = -(1 << 23), (1 << 23) - 1
STAGES = ('input', 'conv_acc', 'activation', 'pool', 'scores', 'prediction')


def checked24(values):
    if np.any(values < INT24_MIN) or np.any(values > INT24_MAX):
        raise OverflowError('Signed 24-bit accumulator overflow')
    return values


def requant_relu(accumulator, multiplier, shift):
    if not (1 <= multiplier <= 65535 and 0 <= shift <= 47):
        raise ValueError('Invalid unsigned 16-bit multiplier or shift')
    checked24(accumulator)
    positive = np.maximum(accumulator, 0).astype(np.int64)
    rounding = (1 << (shift - 1)) if shift else 0
    if int(positive.max(initial=0)) * multiplier + rounding > (1 << 47) - 1:
        raise OverflowError('Signed 48-bit rescale overflow')
    return np.clip((positive * multiplier + rounding) >> shift, 0, 127).astype(np.uint8)


def conv_accumulate(pixels, weights, bias):
    windows = np.lib.stride_tricks.sliding_window_view(pixels[:, 0], (3, 3), axis=(1, 2))
    windows = windows.astype(np.int64)
    weights = weights.astype(np.int64)
    shape = (pixels.shape[0], len(bias), *windows.shape[1:3])
    result = np.broadcast_to(checked24(bias.astype(np.int64))[None, :, None, None], shape).copy()
    # Match RTL's bias-first, row-major serial MAC order. Later negative
    # products must not hide an earlier overflow.
    for ky in range(3):
        for kx in range(3):
            result = checked24(result + windows[:, None, :, :, ky, kx] *
                               weights[None, :, 0, ky, kx, None, None])
    return result


def fc_accumulate(pool, weights, bias):
    flat = pool.reshape(len(pool), -1).astype(np.int64)
    weights = weights.astype(np.int64)
    result = np.broadcast_to(checked24(bias.astype(np.int64)),
                             (len(pool), len(bias))).copy()
    for index in range(flat.shape[1]):
        result = checked24(result + flat[:, index, None] * weights[None, :, index])
    return result


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
    scores = fc_accumulate(pool, parameters['fc_weight'], parameters['fc_bias'])
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
                if not INT24_MIN <= value <= INT24_MAX:
                    raise OverflowError('Scalar convolution bias overflow')
                for ky in range(3):
                    for kx in range(3):
                        value += int(image[0,y+ky,x+kx]) * int(parameters['conv_weight'][f,0,ky,kx])
                        if not INT24_MIN <= value <= INT24_MAX:
                            raise OverflowError('Scalar convolution partial sum overflow')
                acc[f,y,x] = value
                product = max(0, value) * m + rounding
                if product > (1 << 47)-1: raise OverflowError('Scalar rescale overflow')
                active[f,y,x] = min(127, product >> shift)
    pool = np.empty((filters,(side-2)//2,(side-2)//2), dtype=np.uint8)
    for f in range(filters):
        for y in range(pool.shape[1]):
            for x in range(pool.shape[2]):
                pool[f,y,x] = max(int(active[f,2*y+dy,2*x+dx]) for dy in range(2) for dx in range(2))
    flat = pool.flatten().tolist(); scores=[]
    for output, bias in enumerate(parameters['fc_bias']):
        value=int(bias)
        if not INT24_MIN <= value <= INT24_MAX:
            raise OverflowError('Scalar FC bias overflow')
        for index, activation in enumerate(flat):
            value += activation * int(parameters['fc_weight'][output,index])
            if not INT24_MIN <= value <= INT24_MAX:
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
