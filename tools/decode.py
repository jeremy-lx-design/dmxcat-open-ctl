"""Decode a session.py capture log.

Reconstructs the 512-byte DMX buffer from c102 [offset:LE16][data] chunks and
reports non-zero channels, plus prints every non-c102 event (writes, reads,
notifications on other characteristics) for easy analysis.
"""
import re
import sys

NOTIFY_RE = re.compile(r"NOTIFY (\w+)\s+([0-9a-f]*)\s")
LINE_RE = re.compile(r"\[\s*([0-9.]+)s\]\s+(.*)")


def summarize_buffer(buf):
    nz = [(i + 1, v) for i, v in enumerate(buf) if v]  # 1-based channel numbers
    if not nz:
        return "    (all 512 channels = 0)"
    parts = [f"ch{c}={v}" for c, v in nz[:40]]
    extra = "" if len(nz) <= 40 else f" ... (+{len(nz)-40} more)"
    return "    nonzero: " + ", ".join(parts) + extra


def main(path):
    buf = [0] * 512
    dumping = False
    dump_idx = 0
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = LINE_RE.search(line)
            if not m:
                continue
            t, body = m.groups()
            nm = NOTIFY_RE.search(body)
            if nm and nm.group(1) == "c102":
                hexdata = nm.group(2)
                raw = bytes.fromhex(hexdata)
                if len(raw) >= 2:
                    off = raw[0] | (raw[1] << 8)
                    data = raw[2:]
                    if off == 0:
                        if dumping:
                            print(f"[dump complete]")
                            print(summarize_buffer(buf))
                        buf = [0] * 512
                        dumping = True
                    for i, b in enumerate(data):
                        if off + i < 512:
                            buf[off + i] = b
                continue
            # non-c102 event
            print(f"[{t:>7}s] {body}")
    if dumping:
        print(f"[final dump]")
        print(summarize_buffer(buf))


if __name__ == "__main__":
    main(sys.argv[1])
