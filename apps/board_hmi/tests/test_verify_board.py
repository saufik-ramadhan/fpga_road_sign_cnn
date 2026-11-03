"""Check that the board verifier rejects wrong scores even with the right class."""
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from apps.board_hmi.verify_board import check_result, load_cases
from apps.board_hmi import verify_board


class BoardVerifierTests(unittest.TestCase):
    def test_sealed_published_cases_are_complete(self):
        cases, _, contract = load_cases()
        self.assertEqual(contract['version'], 'p2-doc-int-v2')
        self.assertEqual(len(cases), 25)
        for case in cases:
            self.assertEqual(len(case['pixels']), 256)
            self.assertEqual(len(case['scores']), 8)

    def test_wrong_score_with_correct_class_is_rejected(self):
        case = dict(scores=[-5, 12, 0, 1, 2, 3, 4, 5], prediction=1)
        result = dict(status=0, cycles=23542, scores=case['scores'].copy(), **{'class': 1})
        self.assertEqual(check_result(result, case), [])
        result['scores'][0] += 1
        self.assertIn('signed24 scores mismatch', check_result(result, case))

    def test_status_cycles_and_class_are_checked(self):
        case = dict(scores=[0]*8, prediction=0)
        result = dict(status=1, cycles=0, scores=[0]*8, **{'class': 7})
        self.assertEqual(len(check_result(result, case)), 3)

    def test_interrupted_run_is_recorded_as_failure(self):
        (verify_board.ROOT / 'build').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=verify_board.ROOT / 'build') as folder:
            bitstream = Path(folder) / 'test.bit'
            bitstream.write_bytes(b'test fixture, not a real bitstream')
            report_path = Path(folder) / 'report.json'
            port = MagicMock()
            port.write.side_effect = KeyboardInterrupt
            connection = MagicMock()
            connection.__enter__.return_value = port
            argv = ['verify_board.py', 'MOCK_PORT', '--rounds', '1', '--random', '0',
                    '--bitstream', str(bitstream), '--report', str(report_path)]
            with patch.object(sys, 'argv', argv), patch('serial.Serial', return_value=connection):
                self.assertEqual(verify_board.main(), 1)
            report = json.loads(report_path.read_text())
            self.assertFalse(report['pass'])
            self.assertFalse(report['completed'])
            self.assertIn('KeyboardInterrupt', report['failures'][0]['exception'])


if __name__ == '__main__':
    unittest.main()
