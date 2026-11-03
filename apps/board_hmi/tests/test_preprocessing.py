"""Regression evidence for P2 prepared pixels reaching the UART unchanged."""
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from apps.board_hmi import tsr_link


class PreprocessingTests(unittest.TestCase):
    def setUp(self):
        (ROOT / 'build').mkdir(exist_ok=True)
        self.folder = tempfile.TemporaryDirectory(dir=ROOT / 'build')
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / 'source.png'
        self.rgb = np.fromfunction(lambda y, x, c: (x*17+y*29+c*41) % 256,
                                   (23, 31, 3), dtype=int).astype(np.uint8)
        Image.fromarray(self.rgb).save(self.path)

    def test_original_p2_bytes_and_uart_payload(self):
        # Digests captured from the unmodified P2 preprocess at 4b3d8302.
        cases = [((3, 2, 28, 20), '5960eb15a1f167fd2a956c0b668040dfea460e469bb467a1eb8a200068f1f2eb'),
                 (None, 'ea2bc5f858cf0f0c76adfe2031addcfa15ff456f90acaa37261876df480206b2')]
        for roi, digest in cases:
            with self.subTest(roi=roi):
                pixels = tsr_link.load_picture(self.path, roi)
                self.assertEqual(hashlib.sha256(bytes(pixels)).hexdigest(), digest)
                frame = tsr_link.build_request(pixels)
                self.assertEqual(len(frame), 259)
                self.assertEqual(frame[2:258], bytes(pixels))
                self.assertEqual(frame[-1], sum(frame[1:-1]) & 255)

    def test_all_published_prepared_inputs_are_not_reprocessed(self):
        vectors = ROOT / 'reference_model/models/p2-doc-int-v2/vectors'
        for source in sorted(vectors.glob('*/input.mem')):
            raw = bytes(int(v, 16) for v in source.read_text().split())
            path = Path(self.folder.name) / 'prepared.png'
            Image.frombytes('L', (16, 16), raw).save(path)
            with self.subTest(vector=source.parent.name):
                self.assertEqual(bytes(tsr_link.load_picture(path, prepared=True)), raw)
        self.assertEqual(len(list(vectors.glob('*/input.mem'))), 25)

    def test_invalid_roi_and_prepared_input_fail(self):
        for roi in [(-1, 0, 5, 5), (0, 0, 31, 22), (5, 2, 3, 8),
                    (1, 2, 1, 5), (1, 2, 5), (1.5, 2, 5, 6)]:
            with self.subTest(roi=roi), self.assertRaises(ValueError):
                tsr_link.load_picture(self.path, roi)
        with self.assertRaises(ValueError):
            tsr_link.load_picture(self.path, prepared=True)
        with self.assertRaises(ValueError):
            tsr_link.load_picture(self.path, (1, 1, 5, 5), prepared=True)

    def test_roi_parser(self):
        self.assertIsNone(tsr_link.parse_roi(' '))
        self.assertEqual(tsr_link.parse_roi('3, 2,28,20'), (3, 2, 28, 20))
        for text in ['1,2,3', 'a,2,3,4', '1.5,2,3,4']:
            with self.assertRaises(ValueError):
                tsr_link.parse_roi(text)

    def test_cli_validation_before_opening_serial_port(self):
        script = ROOT / 'apps/board_hmi/tsr_link.py'
        for options in [('--roi', '0', '0', '4', '4'), ('--prepared-input',)]:
            result = subprocess.run([sys.executable, str(script), 'INVALID', *options],
                                    cwd=self.folder.name, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn('require --image', result.stderr)

    def test_hmi_uses_same_bytes_and_invalidates_stale_preview(self):
        # Exercise handlers without a display server; no board or Tk window required.
        from apps.board_hmi.hmi_live import Hmi
        from unittest.mock import Mock
        hmi = Hmi.__new__(Hmi)
        hmi.picture_path = self.path
        hmi.roi_text = Mock()
        hmi.roi_text.get.return_value = '3,2,28,20'
        hmi.prepared_input = Mock()
        hmi.prepared_input.get.return_value = False
        hmi.refresh_preview = Mock()
        hmi.set_buttons = Mock()
        hmi.log = Mock()
        hmi.prepare_picture()
        self.assertEqual(hmi.pixels, tsr_link.load_picture(self.path, (3, 2, 28, 20)))
        hmi.invalidate_picture()
        self.assertIsNone(hmi.pixels)
        hmi.roi_text.get.return_value = '3,2,999,20'
        with patch('apps.board_hmi.hmi_live.messagebox.showerror') as error:
            hmi.prepare_picture()
            error.assert_called_once()
        self.assertIsNone(hmi.pixels)


if __name__ == '__main__':
    unittest.main()
