"""Acceptance tests for real MNIST parameters, drawing preprocessing and HTTP."""
import base64
import importlib.util
import io
import json
from pathlib import Path
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import urlopen, Request

import numpy as np
from PIL import Image, ImageDraw, ImageOps

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('mnist_app',ROOT/'visualizer.py')
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)
from golden import scalar_infer, STAGES


class MnistTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parameters,cls.contract=app.debugger.load_verified_model(app.MODEL)
        with np.load(app.MODEL/'samples.npz',allow_pickle=False) as data:
            cls.samples=data['pixels'].copy()
        cls.metrics=json.loads((app.MODEL/'metrics.json').read_text())
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),app.make_mnist_handler(
            cls.parameters,cls.contract,cls.samples,cls.metrics))
        cls.worker=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.worker.start()
        cls.url=f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join()

    def test_all_digits_exact_input_and_independent_layer_oracle(self):
        for digit,image in enumerate(self.samples):
            result=app.analyze_digit(Image.fromarray(image[0]),None,self.parameters,self.contract)
            np.testing.assert_array_equal(result['trace']['input'],image)
            oracle=scalar_infer(image,self.parameters,self.contract)
            for stage in STAGES:
                np.testing.assert_array_equal(result['trace'][stage],oracle[stage],err_msg=f'{digit}/{stage}')
            self.assertEqual(len(result['trace']['flat']),1352)
            self.assertEqual(len(result['trace']['scores']),10)
            np.testing.assert_array_equal(np.array(result['trace']['contributions']).sum(1)+
                self.parameters['fc_bias'],result['trace']['scores'])

    def test_drawing_polarity_centering_and_transparency(self):
        image=Image.new('L',(280,280),0)
        ImageDraw.Draw(image).line([(50,50),(50,190),(120,190)],fill=255,width=20)
        *_,a,_=app.prepare_digit(image)
        *_,b,metadata=app.prepare_digit(ImageOps.invert(image))
        np.testing.assert_array_equal(np.asarray(a),np.asarray(b))
        self.assertTrue(metadata['inverted'])
        values=np.asarray(a,dtype=float); yy,xx=np.indices(values.shape)
        self.assertLess(abs((values*xx).sum()/values.sum()-13.5),.6)
        self.assertLess(abs((values*yy).sum()/values.sum()-13.5),.6)
        transparent=Image.new('RGBA',(100,100),(0,0,0,0))
        ImageDraw.Draw(transparent).line([(50,10),(50,90)],fill=(0,0,0,255),width=10)
        self.assertGreater(np.asarray(app.prepare_digit(transparent)[3]).max(),0)

    def test_blank_and_manual_roi_rejected(self):
        for background in (0,255):
            with self.assertRaises(ValueError):
                app.prepare_digit(Image.new('L',(280,280),background))
        with self.assertRaises(ValueError):
            app.analyze_digit(Image.fromarray(self.samples[0,0]),[0,0,27,27],self.parameters,self.contract)

    def test_http_sample_upload_and_metrics(self):
        for path, content_type in (('/', 'text/html'), ('/network_diagram.js', 'text/javascript')):
            with urlopen(self.url+path) as response:
                self.assertIn(content_type, response.headers['Content-Type'])
                self.assertGreater(len(response.read()), 100)
        with urlopen(self.url+'/api/sample?digit=7') as response:
            sample=json.load(response)
        request=Request(self.url+'/api/infer',json.dumps({'image':sample['image']}).encode(),
                        {'Content-Type':'application/json'})
        with urlopen(request) as response:
            trace=json.load(response)['trace']
        self.assertEqual(sample['label'],7)
        self.assertEqual(np.shape(trace['conv_acc']),(8,26,26))
        with urlopen(self.url+'/api/metrics') as response:
            metrics=json.load(response)
        self.assertEqual(metrics['official_test_integer']['count'],10000)
        self.assertFalse(metrics['test_used_for_training_or_selection'])
        with self.assertRaises(HTTPError) as error:
            urlopen(self.url+'/api/sample?digit=10')
        error.exception.close()


if __name__=='__main__':
    unittest.main()
