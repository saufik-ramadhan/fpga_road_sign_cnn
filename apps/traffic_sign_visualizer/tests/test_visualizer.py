"""Numerical and HTTP acceptance checks for the visual debugger."""
import base64
import io
import json
from pathlib import Path
import sys
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / 'reference_model'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from golden import STAGES, scalar_infer
from visualizer import analyze_image, load_verified_model, make_handler


class VisualizerTests(unittest.TestCase):
    model_path = REPO / 'reference_model' / 'models' / 'p2-int-v1'
    @classmethod
    def setUpClass(cls):
        cls.params, cls.contract = load_verified_model(cls.model_path)
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(cls.params, cls.contract))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def post(self, data, origin=None):
        headers = {'Content-Type': 'application/json'}
        if origin:
            headers['Origin'] = origin
        request = Request(self.url + '/api/infer', json.dumps(data).encode(), headers)
        with urlopen(request) as response:
            return json.load(response)

    def test_real_package_matches_independent_oracle_and_fc_trace(self):
        rng = np.random.default_rng(19)
        image = Image.fromarray(rng.integers(0, 256, (36, 40, 3), dtype=np.uint8))
        trace = analyze_image(image, [2, 3, 31, 29], self.params, self.contract)['trace']
        oracle = scalar_infer(np.array(trace['input'], dtype=np.uint8), self.params, self.contract)
        for stage in STAGES:
            np.testing.assert_array_equal(trace[stage], oracle[stage], err_msg=stage)
        scores = np.array(trace['contributions']).sum(axis=1) + self.params['fc_bias']
        np.testing.assert_array_equal(scores, trace['scores'])
        self.assertEqual(len(trace['flat']), 8 * ((self.contract['image_size'] - 2) // 2) ** 2)
        self.assertEqual(np.shape(trace['conv_acc']), (8, self.contract['image_size'] - 2, self.contract['image_size'] - 2))

    def test_http_upload_and_inclusive_crop(self):
        image = Image.new('RGB', (24, 24), 'white')
        image.putpixel((16, 16), (0, 0, 0))
        raw = io.BytesIO()
        image.save(raw, format='PNG')
        encoded = base64.b64encode(raw.getvalue()).decode()
        result = self.post({'image': encoded, 'roi': [1, 1, 16, 16]})
        self.assertEqual(result['trace']['input'][0][-1][-1], 0)
        self.assertFalse(result['demo'])
        self.assertEqual(result['roi'], [1, 1, 16, 16])

    def test_invalid_upload_roi_and_cross_origin_rejected(self):
        for payload in ({'image': 'garbage'}, {'demo': True, 'roi': [-1, 0, 20, 20]},
                        {'demo': True, 'roi': [0, 0, 1.5, 4]}, []):
            with self.assertRaises(HTTPError) as error:
                self.post(payload)
            self.assertEqual(error.exception.code, 400)
            error.exception.close()
        with self.assertRaises(HTTPError) as error:
            self.post({'demo': True}, origin='https://other.example')
        self.assertEqual(error.exception.code, 403)
        error.exception.close()

    def test_model_and_demo_available(self):
        for path, content_type in (('/', 'text/html'), ('/network_diagram.js', 'text/javascript')):
            with urlopen(self.url + path) as response:
                self.assertIn(content_type, response.headers['Content-Type'])
                self.assertGreater(len(response.read()), 100)
        with urlopen(self.url + '/api/model') as response:
            self.assertEqual(json.load(response)['contract']['version'], self.contract['version'])
        result = self.post({'demo': True})
        self.assertTrue(result['demo'])
        self.assertEqual(len(result['trace']['scores']), 8)


class Visualizer32Tests(VisualizerTests):
    model_path = REPO / 'experiments' / 'traffic_sign_32' / 'models' / 'p2-int-32-v1'


if __name__ == '__main__':
    unittest.main()
