"""Regression tests for fail-closed P2 verification; no third-party test runner."""
import contextlib
import io
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

import run_p3_tests as runner


class RunnerTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'), 'Icarus required')
    def test_vectors_missing_dependencies_fails_at_cli(self):
        with tempfile.TemporaryDirectory() as folder:
            result = subprocess.run(
                [sys.executable, '-S', str(Path(runner.__file__)), '--vectors',
                 str(runner.DEFAULT_MODEL), '--out', str(Path(folder)/'output')],
                capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('FAIL  P2 models:', result.stdout)
        self.assertNotIn('0 of 0 passed', result.stdout)

    def test_missing_dependencies_fail_all_required_packages(self):
        with mock.patch.dict(sys.modules, {'p2_vectors': None}):
            lines, tests, failed = runner.p2_tests(
                Path('unused'), [Path('model_v1'), Path('model_v2')])
        self.assertEqual(failed, 2)
        self.assertFalse(tests)
        self.assertIn('FAIL', lines[0])

    def test_no_packages_fails(self):
        lines, tests, failed = runner.p2_tests(Path('unused'), [])
        self.assertGreater(failed, 0)
        self.assertFalse(tests)
        self.assertIn('FAIL', lines[0])

    def test_package_without_images_fails(self):
        fake = types.SimpleNamespace(any_set=lambda *_: {'images': 0, 'summary': 'empty'})
        with mock.patch.dict(sys.modules, {'p2_vectors': fake}):
            lines, tests, failed = runner.p2_tests(Path('unused'), [Path('empty')])
        self.assertEqual(failed, 1)
        self.assertFalse(tests)
        self.assertIn('no input images', lines[0])

    def test_valid_package_is_selected(self):
        fake = types.SimpleNamespace(any_set=lambda *_: {'images': 2, 'summary': 'loaded'})
        with mock.patch.dict(sys.modules, {'p2_vectors': fake}):
            _, tests, failed = runner.p2_tests(Path('unused'), [Path('candidate')])
        self.assertEqual(failed, 0)
        self.assertEqual(len(tests), 2)
        self.assertEqual(tests[0][4]['N_IMG'], 2)

    def test_mac_variants_repeat_only_engine_tests(self):
        tests = [('conv_engine_tb set', 'conv_engine_tb', Path('tb'), Path('set'), {'N_IMG': 2}),
                 ('requant_relu_tb set', 'requant_relu_tb', Path('tb'), Path('rq'), {'N_VEC': 5})]
        every = runner.with_mac_variants(tests, (1, 3, 9))
        self.assertEqual([t[0] for t in every], ['conv_engine_tb set', 'conv_engine_tb set mac3',
                                                 'conv_engine_tb set mac9', 'requant_relu_tb set'])
        self.assertEqual(every[0], tests[0])                    # N_MAC = 1 is the default build
        self.assertEqual(every[2][3], Path('set') / 'mac9')
        self.assertEqual(every[2][4], {'N_IMG': 2, 'N_MAC': 9})
        self.assertEqual(tests[0][4], {'N_IMG': 2})              # the base test is not changed
        only3 = runner.with_mac_variants(tests, (3,))
        self.assertEqual([t[0] for t in only3], ['conv_engine_tb set mac3', 'requant_relu_tb set'])

    def test_empty_selection_cannot_report_success(self):
        with tempfile.TemporaryDirectory() as folder:
            args = ['run_p3_tests.py', '--vectors', 'candidate', '--out', folder]
            with mock.patch.object(sys, 'argv', args), \
                 mock.patch.object(runner, 'Icarus'), \
                 mock.patch.object(runner, 'p2_tests', return_value=([], [], 0)), \
                 contextlib.redirect_stdout(io.StringIO()), \
                 self.assertRaises(SystemExit) as error:
                runner.main()
        self.assertIn('no tests selected', str(error.exception))


if __name__ == '__main__':
    unittest.main()
