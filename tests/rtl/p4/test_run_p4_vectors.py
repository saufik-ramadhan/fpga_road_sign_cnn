"""Regression tests for malformed goldens and false-success simulator results."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import run_p4_vectors as runner


class RunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (runner.REPO / 'build').mkdir(exist_ok=True)
        cls.temp = tempfile.TemporaryDirectory(dir=runner.REPO / 'build')
        cls.root = Path(cls.temp.name)
        cls.vectors = cls.root / 'vectors'
        subprocess.run([sys.executable, '-I', str(runner.HERE / 'gen_golden_vectors.py'),
                        str(runner.PACKAGE), str(cls.vectors)], check=True,
                       capture_output=True, text=True, timeout=60)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_generator_uses_checked_repository_package(self):
        self.assertEqual(len(list(self.vectors.iterdir())), 15)
        runner.validate_mem(self.vectors / 'zeros/prediction.mem', 1, 8, 7)

    def test_malformed_or_unknown_memory_is_rejected(self):
        path = self.root / 'bad.mem'
        for content in ['xx', '', '01 02', '100', '08']:
            path.write_text(content)
            with self.subTest(content=content), self.assertRaises(ValueError):
                runner.validate_mem(path, 1, 8, 7)

    def test_simulator_exit_and_error_messages_override_pass(self):
        for code, stdout, stderr in [(1, 'PASS test', ''), (0, 'PASS test', 'ERROR bad'),
                                      (0, 'PASS test\nFAIL other', ''), (0, '', '')]:
            result = subprocess.CompletedProcess([], code, stdout, stderr)
            with self.subTest(code=code, stdout=stdout), patch.object(
                    runner.subprocess, 'run', return_value=result):
                ok, _ = runner.simulate(self.root / 'unused', self.root, 'verdict')
                self.assertFalse(ok)

    def test_empty_or_incomplete_vector_directory_fails_cli(self):
        vectors = self.root / 'invalid'
        vectors.mkdir()
        for incomplete in (False, True):
            if incomplete:
                (vectors / 'missing').mkdir()
            result = subprocess.run([sys.executable, str(runner.HERE / 'run_p4_vectors.py'),
                                     '--vectors', str(vectors), '--work', str(self.root / 'work')],
                                    capture_output=True, text=True, timeout=60)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('FAIL P4', result.stderr)

    @unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'), 'Icarus required')
    def test_unknown_prediction_fails_inside_chain_testbench(self):
        work = self.root / 'unknown'
        shutil.copytree(self.vectors / 'zeros', work)
        for name in ('fc_weight.mem', 'fc_bias.mem'):
            shutil.copyfile(runner.PACKAGE / 'mem' / name, work / name)
        (work / 'prediction.mem').write_text('xx\n')
        sims = runner.build(runner.HERE, work)
        ok, output = runner.simulate(sims['rantai'], work, 'unknown')
        self.assertFalse(ok)
        self.assertIn('FAIL: argmax', output)


if __name__ == '__main__':
    unittest.main()
