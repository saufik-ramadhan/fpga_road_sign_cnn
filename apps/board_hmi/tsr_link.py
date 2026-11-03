"""
tsr_link.py  -  laptop side of the USB cable (P5)

Sends a 16x16 grayscale picture to the Basys3 and prints the answer.

  python apps/board_hmi/tsr_link.py COM5                  send a test picture to the board
  python apps/board_hmi/tsr_link.py COM5 --image sign.png send your own picture (needs: pip install pillow)
  python apps/board_hmi/tsr_link.py COM5 --dummy          also check the DUMMY CNN's answer (class = pixel sum mod 8)
  python apps/board_hmi/tsr_link.py --selftest            test this script without a board

Needs:  pip install pyserial

Message format (must match frame_ctrl.v):
  REQUEST  259 bytes: A5 | CMD(01) | 256 pixels | CHK
  REPLY     32 bytes: 5A | STATUS | CLASS | CYCLES(4) | 8 x SCORE(3) | CHK
  CHK = low 8 bits of the sum of the bytes between the sync byte and CHK.
"""
import argparse
import sys
from pathlib import Path

SYNC_REQUEST = 0xA5
SYNC_REPLY = 0x5A
CMD_CLASSIFY = 0x01
IMAGE_SIZE = 16 * 16          # 256 pixels
REPLY_SIZE = 32
BAUD = 115200
CLOCK_MHZ = 100               # board clock, used to turn cycles into microseconds
REPLY_TIMEOUT_S = 0.200       # no reply within 200 ms -> resend once

STATUS_TEXT = {0: "OK", 1: "bad checksum", 2: "timeout", 3: "unknown command"}
# Class indices from the active p2-doc-int-v2 contract.
CLASS_NAMES = ["StOP", "yLd", "no E", "PrIo", "CAUt", "rIGt", "30", "50"]


def checksum(data):
    """Low 8 bits of the sum of all bytes."""
    return sum(data) & 0xFF


def build_request(pixels, cmd=CMD_CLASSIFY):
    """Make the 259-byte message for one picture."""
    if len(pixels) != IMAGE_SIZE:
        raise ValueError("need exactly 256 pixels, got %d" % len(pixels))
    body = bytes([cmd]) + bytes(pixels)
    return bytes([SYNC_REQUEST]) + body + bytes([checksum(body)])


def parse_reply(data):
    """Turn the 32 reply bytes into a dictionary. Raises ValueError if damaged."""
    if len(data) != REPLY_SIZE:
        raise ValueError("reply has %d bytes, expected %d" % (len(data), REPLY_SIZE))
    if data[0] != SYNC_REPLY:
        raise ValueError("reply does not start with 5A")
    if checksum(data[1:31]) != data[31]:
        raise ValueError("reply checksum is wrong")

    status = data[1]
    cycles = int.from_bytes(data[3:7], "big")
    scores = [int.from_bytes(data[7 + 3 * k: 10 + 3 * k], "big", signed=True) for k in range(8)]
    return {
        "status": status,
        "status_text": STATUS_TEXT.get(status, "?"),
        "class": data[2],
        "class_name": CLASS_NAMES[data[2]] if data[2] < 8 else "?",
        "cycles": cycles,
        "time_us": cycles / CLOCK_MHZ,
        "scores": scores,
    }


class TsrLink:
    """Wraps a serial port. `port` can be a name like 'COM5' or an already-open serial object."""

    def __init__(self, port):
        if isinstance(port, str):
            import serial
            self.ser = serial.Serial(port, BAUD, timeout=REPLY_TIMEOUT_S)
        else:
            self.ser = port

    def classify(self, pixels):
        """Send one picture, return the parsed reply. Resends once if no reply."""
        request = build_request(pixels)
        for attempt in (1, 2):
            self.ser.reset_input_buffer()
            self.ser.write(request)
            data = self.ser.read(REPLY_SIZE)         # waits up to 200 ms
            if len(data) == REPLY_SIZE:
                return parse_reply(data)
            print("no reply (attempt %d of 2)" % attempt)
        raise TimeoutError("board did not answer. Check: CNN bitstream loaded? right COM port?")

    def close(self):
        self.ser.close()


# ----------------------------------------------------------------------
# helpers for the command line
# ----------------------------------------------------------------------
def test_picture():
    """A simple known picture: pixel k = (k % 7) * 3."""
    return [(k % 7) * 3 for k in range(IMAGE_SIZE)]


def parse_roi(text):
    """Parse the optional GUI ROI as x1,y1,x2,y2 (inclusive maxima)."""
    if not text.strip():
        return None
    try:
        values = tuple(int(v.strip()) for v in text.split(','))
    except ValueError as exc:
        raise ValueError('ROI: use x1,y1,x2,y2 integer coordinates') from exc
    if len(values) != 4:
        raise ValueError('ROI: use x1,y1,x2,y2 integer coordinates')
    return values


def load_picture(path, roi=None, prepared=False):
    """Load document-v2 UART bytes, or an explicitly prepared 16x16 L image."""
    from PIL import Image
    # Script entrypoints must also work outside the repository's working directory.
    repo = str(Path(__file__).resolve().parents[2])
    if repo not in sys.path:
        sys.path.insert(0, repo)
    from reference_model.document_v2.preprocessing import preprocess_image
    with Image.open(path) as img:
        if prepared:
            if roi is not None:
                raise ValueError('Prepared input cannot be combined with ROI')
            if img.mode != 'L' or img.size != (16, 16):
                raise ValueError('Prepared input must be a 16 x 16 grayscale L image')
            return list(img.tobytes())
        return list(preprocess_image(img, roi).tobytes())


def print_result(r):
    print("status : %d (%s)" % (r["status"], r["status_text"]))
    print("class  : %d  (%s)" % (r["class"], r["class_name"]))
    print("time   : %d cycles = %.1f us" % (r["cycles"], r["time_us"]))
    print("scores : " + "  ".join("%d" % s for s in r["scores"]))


# ----------------------------------------------------------------------
# selftest: a Python "fake board" that behaves like the dummy CNN
# ----------------------------------------------------------------------
class FakeBoard:
    """Looks like a serial port. Drops the first request if drop_first=True."""

    def __init__(self, drop_first=False, delay=0.0):
        self.rx = bytearray()
        self.tx = bytearray()
        self.drop_first = drop_first
        self.delay = delay                           # seconds; mimics the time the cable takes

    def reset_input_buffer(self):
        self.tx.clear()

    def write(self, data):
        self.rx += data
        if len(self.rx) < 259:
            return
        frame, self.rx = bytes(self.rx[:259]), bytearray(self.rx[259:])
        if self.drop_first:
            self.drop_first = False
            return                                   # pretend the frame was lost
        self.tx += self._reply_for(frame)

    def read(self, n):
        if self.tx and self.delay:
            import time
            time.sleep(self.delay)
        out, self.tx = bytes(self.tx[:n]), bytearray(self.tx[n:])
        return out

    @staticmethod
    def _reply_for(frame):
        if checksum(frame[1:258]) != frame[258]:
            status, cls, cycles, scores = 1, 0, 0, [0] * 8
        elif frame[1] != CMD_CLASSIFY:
            status, cls, cycles, scores = 3, 0, 0, [0] * 8
        else:
            cls = sum(frame[2:258]) % 8
            status, cycles = 0, 260
            scores = [1000 if k == cls else k * 10 for k in range(8)]
        body = bytes([status, cls]) + cycles.to_bytes(4, "big")
        for s in scores:
            body += s.to_bytes(3, "big", signed=True)
        return bytes([SYNC_REPLY]) + body + bytes([checksum(body)])

    def close(self):
        pass


def selftest():
    pix = test_picture()
    expected_class = sum(pix) % 8

    link = TsrLink(FakeBoard())
    r = link.classify(pix)
    assert r["status"] == 0 and r["class"] == expected_class, r
    assert r["scores"][expected_class] == 1000
    print("1. normal picture ........... OK  (class %d)" % r["class"])

    link = TsrLink(FakeBoard(drop_first=True))
    r = link.classify(pix)
    assert r["status"] == 0
    print("2. lost frame, resend ....... OK")

    bad = bytearray(build_request(pix))
    bad[-1] ^= 0xFF
    board = FakeBoard()
    board.write(bytes(bad))
    r = parse_reply(bytes(board.tx))
    assert r["status"] == 1
    print("3. bad checksum -> status 1 . OK")

    try:
        parse_reply(b"\x00" * 32)
        raise SystemExit("parse_reply should have rejected junk")
    except ValueError:
        print("4. damaged reply rejected ... OK")
    print("selftest passed")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("port", nargs="?", help="serial port, e.g. COM5 or /dev/ttyUSB1")
    ap.add_argument("--image", help="cropped sign image, prepared using document-v2")
    options = ap.add_mutually_exclusive_group()
    options.add_argument("--roi", nargs=4, type=int, metavar=('X1', 'Y1', 'X2', 'Y2'),
                         help="sign ROI in decoded pixels; maximum coordinates inclusive")
    options.add_argument("--prepared-input", action="store_true",
                         help="send an already prepared 16x16 L image without preprocessing")
    ap.add_argument("--dummy", action="store_true", help="check the answer of the dummy CNN")
    ap.add_argument("--selftest", action="store_true", help="test this script without a board")
    args = ap.parse_args()

    if args.selftest:
        selftest()
        return
    if not args.port:
        ap.error("give the serial port (or use --selftest)")
    if (args.roi is not None or args.prepared_input) and not args.image:
        ap.error("--roi and --prepared-input require --image")

    try:
        pixels = load_picture(args.image, args.roi, args.prepared_input) if args.image else test_picture()
    except (OSError, ValueError) as exc:
        ap.error(str(exc))
    link = TsrLink(args.port)
    try:
        result = link.classify(pixels)
    finally:
        link.close()
    print_result(result)

    if args.dummy:
        want = sum(pixels) % 8
        ok = result["status"] == 0 and result["class"] == want
        print("dummy check: expected class %d -> %s" % (want, "PASS" if ok else "FAIL"))
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
