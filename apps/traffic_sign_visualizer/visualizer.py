"""Local, dependency-light visual debugger for the published integer CNN.

Run: python apps/traffic_sign_visualizer/visualizer.py --port 8765
Only NumPy and Pillow are required. No image is saved or sent to a cloud service.
"""
import argparse
import base64
import binascii
import hashlib
import io
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError

import sys
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'reference_model'))

from data import preprocess
from golden import infer, load_model

ROOT = Path(__file__).resolve().parent
MODEL = REPO / 'experiments' / 'traffic_sign_32' / 'models' / 'p2-int-32-v1'
MAX_REQUEST = 16 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 16_000_000


def png_uri(image):
    output = io.BytesIO()
    image.save(output, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(output.getvalue()).decode('ascii')


def load_verified_model(directory=MODEL):
    directory = Path(directory)
    checksums = json.loads((directory / 'checksums.json').read_text())
    for name, digest in checksums.items():
        if hashlib.sha256((directory / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f'Model checksum mismatch: {name}')
    parameters, contract = load_model(directory)
    side, channels = contract['image_size'], contract['filters']
    classes = len(contract['classes'])
    if side not in (16, 28, 32):
        raise ValueError('Supported model sizes: 16, 28 and 32')
    expected = {'conv_weight': (channels, 1, 3, 3), 'conv_bias': (channels,),
                'fc_weight': (classes, channels * ((side - 2) // 2) ** 2),
                'fc_bias': (classes,)}
    if any(parameters[name].shape != shape for name, shape in expected.items()):
        raise ValueError('Parameter dimensions do not match the model contract')
    return parameters, contract


def demo_image():
    """A clearly labelled synthetic image; never a quality benchmark."""
    image = Image.new('RGB', (180, 180), '#ccd9df')
    draw = ImageDraw.Draw(image)
    draw.regular_polygon((90, 86, 70), 8, rotation=22.5, fill='#bf2525', outline='white', width=5)
    draw.text((64, 80), 'STOP', fill='white', stroke_width=1)
    return image


def analyze_image(image, roi, parameters, contract):
    # EXIF orientation is applied before interpreting the user-visible ROI.
    image = ImageOps.exif_transpose(image).convert('RGB')
    if min(image.size) < 2:
        raise ValueError('Gambar minimal 2 × 2 pixel.')
    if image.width * image.height > Image.MAX_IMAGE_PIXELS:
        raise ValueError('Gambar terlalu besar; maksimal 16 megapixel.')
    if roi is None:
        roi = [0, 0, image.width - 1, image.height - 1]
    if not isinstance(roi, list) or len(roi) != 4 or any(type(v) is not int for v in roi):
        raise ValueError('ROI harus berisi empat koordinat integer.')
    pixels = preprocess(image, roi, contract['image_size'])
    crop = image.crop((roi[0], roi[1], roi[2] + 1, roi[3] + 1))
    tensors = infer(pixels[None, None], parameters, contract)
    trace = {key: value[0].tolist() for key, value in tensors.items()}
    trace['relu'] = np.maximum(tensors['conv_acc'][0], 0).tolist()
    trace['flat'] = tensors['pool'][0].reshape(-1).tolist()
    trace['contributions'] = (parameters['fc_weight'].astype(np.int64) *
                              tensors['pool'][0].reshape(1, -1)).tolist()
    # Preview images are bounded; numerical tensors always use the actual ROI.
    image.thumbnail((720, 720))
    crop.thumbnail((720, 720))
    gray = crop.convert('L')
    return dict(trace=trace, roi=roi, original=png_uri(image), crop=png_uri(crop),
                grayscale=png_uri(gray), resized=png_uri(Image.fromarray(pixels)))


def make_handler(parameters, contract, *, analyzer=analyze_image, ui_path=None, demo_factory=demo_image):
    ui_path = ui_path or ROOT / 'ui' / 'index.html'
    class Handler(BaseHTTPRequestHandler):
        def send(self, status, payload, content_type='application/json; charset=utf-8'):
            data = payload if isinstance(payload, bytes) else json.dumps(payload).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path in ('/', '/index.html'):
                self.send(200, ui_path.read_bytes(), 'text/html; charset=utf-8')
            elif self.path == '/network_diagram.js':
                self.send(200, (ROOT / 'ui' / 'network_diagram.js').read_bytes(),
                          'text/javascript; charset=utf-8')
            elif self.path == '/api/model':
                self.send(200, dict(contract=contract, parameters={k: v.tolist() for k, v in parameters.items()}))
            else:
                self.send(404, {'error': 'Halaman tidak ditemukan.'})

        def do_POST(self):
            if self.path != '/api/infer':
                return self.send(404, {'error': 'Endpoint tidak ditemukan.'})
            # Browser cross-origin requests must not read/process local user data.
            origin = self.headers.get('Origin')
            if origin and origin != 'http://' + self.headers.get('Host', ''):
                return self.send(403, {'error': 'Origin tidak diizinkan.'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= MAX_REQUEST:
                    return self.send(413, {'error': 'Ukuran upload maksimal 12 MB.'})
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError('Request harus berupa object JSON.')
                if payload.get('demo') is True:
                    image = demo_factory()
                else:
                    encoded = payload.get('image', '')
                    if not isinstance(encoded, str):
                        raise ValueError('Format gambar tidak valid.')
                    raw = base64.b64decode(encoded.split(',')[-1], validate=True)
                    image = Image.open(io.BytesIO(raw))
                with image:
                    result = analyzer(image, payload.get('roi'), parameters, contract)
                result['demo'] = payload.get('demo') is True
                self.send(200, result)
            except (ValueError, TypeError, KeyError, binascii.Error, UnidentifiedImageError,
                    OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
                self.send(400, {'error': str(error) or 'Gambar tidak dapat dibaca.'})

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--model', type=Path, default=MODEL,
                        help='Verified model package (default: p2-int-32-v1)')
    args = parser.parse_args()
    parameters, contract = load_verified_model(args.model)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(parameters, contract))
    print(f'CNN Visual Lab: http://127.0.0.1:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
