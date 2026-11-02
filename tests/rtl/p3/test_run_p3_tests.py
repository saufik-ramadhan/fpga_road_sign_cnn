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
        self.assertEqual(len(tests), 1)
        self.assertEqual(tests[0][4]['N_IMG'], 2)

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
