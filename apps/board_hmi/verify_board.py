"""Verify the programmed full CNN over UART against sealed model goldens.

Run from the repo root: python apps/board_hmi/verify_board.py COM8 --rounds 10
This sends LIVE requests only. It does not program hardware or test buttons.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime, timezone

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from apps.board_hmi import tsr_link
from reference_model.document_v2 import golden
from reference_model.document_v2.preprocessing import preprocess_image

PACKAGE = ROOT / 'reference_model/models/p2-doc-int-v2'
D42_PACKAGE = ROOT / 'experiments/traffic_sign_d42/models/p2-doc-d42-int24-v1'


def read_words(path, bits, signed=False):
    values = [int(v, 16) for v in path.read_text().split()]
    if signed:
        values = [v - (1 << bits) if v >= 1 << (bits - 1) else v for v in values]
    return values


def load_cases(package=PACKAGE, expected='p2-doc-int-v2'):
    hashes = json.loads((package / 'checksums.json').read_text())
    for name, digest in hashes.items():
        if hashlib.sha256((package / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f'Package checksum mismatch: {name}')
    parameters, contract = golden.load_model(package)
    if contract['version'] != expected:
        raise ValueError(f'Expected {expected}')
    cases = []
    for folder in sorted((package / 'vectors').iterdir()):
        if folder.is_dir():
            pixels = read_words(folder / 'input.mem', 8)
            scores = read_words(folder / 'scores.mem', 24, True)
            prediction = read_words(folder / 'prediction.mem', 8)[0]
            cases.append(dict(name=folder.name, pixels=pixels, scores=scores, prediction=prediction))
    if len(cases) != 25:
        raise ValueError('Expected all 25 published golden inputs')
    return cases, parameters, contract


def oracle_case(name, pixels, parameters, contract):
    image = np.array(pixels, dtype=np.uint8).reshape(1, 16, 16)
    trace = golden.scalar_infer(image, parameters, contract)
    return dict(name=name, pixels=list(map(int, pixels)), scores=trace['scores'].tolist(),
                prediction=int(trace['prediction']))


def check_result(result, case, expected_cycles=23542):
    errors = []
    if result['status'] != 0:
        errors.append(f"status={result['status']}")
    if result['scores'] != case['scores']:
        errors.append('signed24 scores mismatch')
    if result['class'] != case['prediction']:
        errors.append('class mismatch')
    if result['cycles'] != expected_cycles:
        errors.append(f"cycles={result['cycles']}, expected {expected_cycles}")
    return errors


def baseline_extras(parameters, contract, random_count, report_dir):
    # Stored bank pixels are uploaded over LIVE UART; this does not exercise ROM selection.
    bank = read_words(PACKAGE / 'signs.mem', 8)
    extra = [oracle_case(f'stored_bank_as_live_{i:02d}', bank[i*256:(i+1)*256],
                         parameters, contract) for i in range(16)]
    rng = np.random.default_rng(20261103)
    for i in range(random_count):
        extra.append(oracle_case(f'random_{i:03d}', rng.integers(0, 256, 256).tolist(),
                                 parameters, contract))
    # Exercise real file preprocessing (crop/equalize/resize), not reprocessing goldens.
    for i in range(3):
        source = Image.fromarray(rng.integers(0, 256, (30, 40, 3), dtype=np.uint8))
        path = report_dir / f'preprocess_{i}.png'
        source.save(path)
        roi = (3, 4, 35, 26)
        pixels = tsr_link.load_picture(path, roi)
        if bytes(pixels) != preprocess_image(source, roi).tobytes():
            raise ValueError('CLI/P2 preprocessing mismatch')
        extra.append(oracle_case(f'preprocessed_rgb_{i}', pixels, parameters, contract))
    return extra


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('port')
    parser.add_argument('--model', choices=('baseline', 'd42'), default='baseline')
    parser.add_argument('--rounds', type=int, default=10)
    parser.add_argument('--random', type=int, dest='random_count')
    parser.add_argument('--expected-cycles', type=int, help='Override cycle count for a verified MAC variant')
    parser.add_argument('--bitstream', type=Path, required=True)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    d42 = args.model == 'd42'
    random_count = args.random_count if args.random_count is not None else (0 if d42 else 32)
    if args.rounds < 1 or random_count < 0 or (d42 and random_count):
        parser.error('Use positive rounds and a nonnegative random count. D42 uses published goldens only.')
    package = D42_PACKAGE if d42 else PACKAGE
    if args.expected_cycles is not None and not 0 < args.expected_cycles < 2**32:
        parser.error('--expected-cycles must be a positive unsigned32 value')
    expected_cycles = args.expected_cycles or (81168 if d42 else 23542)
    cases, parameters, contract = load_cases(package, 'p2-doc-d42-int24-v1' if d42 else 'p2-doc-int-v2')
    if args.report is None:
        args.report = ROOT / 'build/board_validation' / ('results_d42.json' if d42 else 'results.json')
    args.report.parent.mkdir(parents=True, exist_ok=True)
    extra = [] if d42 else baseline_extras(parameters, contract, random_count, args.report.parent)
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    report = dict(started_utc=datetime.now(timezone.utc).isoformat(), source_head=head,
                  harness_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  model=contract['version'], port=args.port, baud=115200,
                  bitstream_sha256=hashlib.sha256(args.bitstream.read_bytes()).hexdigest(),
                  rounds=args.rounds, published_unique_inputs=len(cases), expected_cycles=expected_cycles,
                  package_seal_sha256=hashlib.sha256((package/'checksums.json').read_bytes()).hexdigest(),
                  random_seed=20261103, transactions=[], failures=[])

    def exchange(port, frame, name):
        start = time.perf_counter()
        port.write(frame)
        raw = port.read(32)
        entry = dict(name=name, request_hex=frame.hex(), reply_hex=raw.hex(),
                     round_trip_ms=(time.perf_counter()-start)*1000)
        report['transactions'].append(entry)
        result = tsr_link.parse_reply(raw)
        entry.update(result)
        return result

    def classify(port, case, name=None):
        result = exchange(port, tsr_link.build_request(case['pixels']), name or case['name'])
        errors = check_result(result, case, expected_cycles)
        if errors:
            report['failures'].append(dict(name=name or case['name'], errors=errors))

    completed = False
    try:
        import serial
        with serial.Serial(args.port, 115200, timeout=1, write_timeout=1) as port:
            port.reset_input_buffer()
            # No automatic retries: missing replies must remain visible as failures.
            for r in range(args.rounds):
                for case in cases:
                    classify(port, case, f"round_{r+1}/{case['name']}")
                print(f'Golden round {r+1}/{args.rounds}: completed', flush=True)
            for case in extra:
                classify(port, case)
            base = cases[0]
            bad = bytearray(tsr_link.build_request(base['pixels']))
            bad[-1] ^= 255
            result = exchange(port, bytes(bad), 'bad_checksum')
            if result['status'] != 1 or result['cycles'] or any(result['scores']):
                report['failures'].append(dict(name='bad_checksum', result=result))
            classify(port, base, 'recovery_after_checksum')
            result = exchange(port, tsr_link.build_request(base['pixels'], cmd=0x7f), 'unknown_command')
            if result['status'] != 3 or result['cycles'] or any(result['scores']):
                report['failures'].append(dict(name='unknown_command', result=result))
            classify(port, base, 'recovery_after_command')
            partial = tsr_link.build_request(base['pixels'])[:20]
            port.write(partial)
            time.sleep(0.05)  # Hardware timeout is 10 ms; the partial frame is silently dropped.
            port.timeout = 0.05
            unexpected = port.read(32)
            port.timeout = 1
            report['partial_frame'] = dict(request_hex=partial.hex(), unexpected_reply_hex=unexpected.hex())
            if unexpected:
                report['failures'].append(dict(name='partial_frame_unexpected_reply'))
            classify(port, base, 'recovery_after_timeout')
            completed = True
    except (Exception, KeyboardInterrupt) as exc:
        report['failures'].append(dict(exception=repr(exc)))
    finally:
        report['finished_utc'] = datetime.now(timezone.utc).isoformat()
        report['completed'] = completed
        report['pass'] = completed and not report['failures']
        args.report.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(f"{'PASS' if report['pass'] else 'FAIL'}: {len(report['transactions'])} replies; "
          f"{len(report['failures'])} failures; report {args.report}")
    return 0 if report['pass'] else 1


if __name__ == '__main__':
    sys.exit(main())
