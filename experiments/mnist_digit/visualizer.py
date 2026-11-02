"""MNIST Visual Lab. Run: python experiments/mnist_digit/visualizer.py (localhost:8766)."""
import argparse
import importlib.util
from pathlib import Path
import sys
from http.server import ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import numpy as np
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent
# Load the shared debugger by a unique name (both entry points are visualizer.py).
sys.path.insert(0, str(ROOT.parents[1] / 'reference_model'))
spec = importlib.util.spec_from_file_location('cnn_debugger', ROOT.parents[1]/'apps/traffic_sign_visualizer/visualizer.py')
debugger = importlib.util.module_from_spec(spec)
spec.loader.exec_module(debugger)
MODEL = ROOT/'models/mnist-int-v1'


def prepare_digit(image):
    image = ImageOps.exif_transpose(image)
    if image.width*image.height > 16_000_000:
        raise ValueError('Gambar terlalu besar; maksimal 16 megapixel.')
    if min(image.size) < 2:
        raise ValueError('Gambar minimal 2 × 2 pixel.')
    if 'A' in image.getbands() or 'transparency' in image.info:
        rgba = image.convert('RGBA')
        background = Image.new('RGBA', rgba.size, 'white')
        image = Image.alpha_composite(background, rgba).convert('RGB')
    original = image.convert('RGB')
    gray = original.convert('L')
    pixels = np.asarray(gray)
    border = np.concatenate([pixels[0],pixels[-1],pixels[:,0],pixels[:,-1]])
    inverted = bool(np.median(border) > 127)
    if inverted:
        gray = ImageOps.invert(gray)
    values = np.asarray(gray)
    y, x = np.where(values > 35)
    if len(x) < 3 or values.max()-int(values.min()) < 20:
        raise ValueError('Belum ada digit yang terlihat. Tulis satu angka dengan garis yang jelas.')
    bbox = (int(x.min()),int(y.min()),int(x.max())+1,int(y.max())+1)
    crop = gray.crop(bbox)
    if gray.size == (28,28):
        prepared = gray.copy()
        method = 'Input 28×28 dipertahankan; hanya polaritas diperiksa.'
    else:
        scale = 20/max(crop.size)
        resized = crop.resize((max(1,round(crop.width*scale)),max(1,round(crop.height*scale))),Image.Resampling.BILINEAR)
        prepared = Image.new('L',(28,28),0)
        prepared.paste(resized,((28-resized.width)//2,(28-resized.height)//2))
        p = np.asarray(prepared,dtype=np.float64)
        yy, xx = np.indices(p.shape)
        dx = round(13.5-float((p*xx).sum()/p.sum()))
        dy = round(13.5-float((p*yy).sum()/p.sum()))
        centered = Image.new('L',(28,28),0)
        centered.paste(prepared,(dx,dy))
        prepared = centered
        method = 'Crop digit → muat dalam 20×20 → kanvas 28×28 → pusat massa.'
    return original, gray, crop, prepared, {'inverted': inverted,'method': method,'foreground_bbox': bbox}


def analyze_digit(image, roi, parameters, contract):
    if roi is not None:
        raise ValueError('ROI manual tidak dipakai untuk MNIST; crop digit dilakukan otomatis.')
    original, gray, crop, prepared, metadata = prepare_digit(image)
    result = debugger.analyze_image(prepared,None,parameters,contract)
    original.thumbnail((720,720))
    gray.thumbnail((720,720))
    crop.thumbnail((720,720))
    result.update(original=debugger.png_uri(original),crop=debugger.png_uri(crop),
                  grayscale=debugger.png_uri(gray),preprocessing=metadata)
    return result


def make_mnist_handler(parameters, contract, samples, metrics):
    base = debugger.make_handler(parameters,contract,analyzer=analyze_digit,
        ui_path=ROOT/'ui/index.html',demo_factory=lambda:Image.fromarray(samples[0,0]))
    class Handler(base):
        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path == '/api/sample':
                try:
                    digit = int(parse_qs(parsed.query).get('digit',['0'])[0])
                    if not 0 <= digit <= 9:
                        raise ValueError('Digit harus 0–9.')
                    self.send(200,{'image':debugger.png_uri(Image.fromarray(samples[digit,0])),
                                   'label':digit,'source':'MNIST validation'})
                except ValueError as error:
                    self.send(400,{'error':str(error)})
            elif parsed.path == '/api/metrics':
                self.send(200,metrics)
            else:
                super().do_GET()
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8766)
    args=parser.parse_args()
    parameters,contract=debugger.load_verified_model(MODEL)
    with np.load(MODEL/'samples.npz',allow_pickle=False) as data:
        samples=data['pixels'].copy()
    import json
    metrics=json.loads((MODEL/'metrics.json').read_text())
    server=ThreadingHTTPServer(('127.0.0.1',args.port),make_mnist_handler(parameters,contract,samples,metrics))
    print(f'MNIST Visual Lab: http://127.0.0.1:{args.port}',flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__=='__main__':
    main()
