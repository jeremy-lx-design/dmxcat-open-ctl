"""Serial helper for the DMXcat test bridge (Arduino).

Usage:
  ser.py "CMD1;CMD2;..." [read_seconds] [port]

Opens the port at 115200, prints the boot banner and any responses, sends each
';'-separated command, and keeps reading for read_seconds after the last one.
"""
import sys
import time

import serial

PORT = "COM6"
BAUD = 115200


def main():
    cmds = sys.argv[1].split(";") if len(sys.argv) > 1 and sys.argv[1] else []
    read_s = float(sys.argv[2]) if len(sys.argv) > 2 else 2.0
    port = sys.argv[3] if len(sys.argv) > 3 else PORT

    with serial.Serial(port, BAUD, timeout=0.1) as s:
        time.sleep(0.3)
        # drain boot banner (board resets on port open; wait for boot)
        t0 = time.time()
        while time.time() - t0 < 2.2:
            line = s.readline()
            if line:
                print("<", line.decode(errors="replace").rstrip())
        for c in cmds:
            c = c.strip()
            if not c:
                continue
            print(">", c)
            s.write((c + "\n").encode())
            s.flush()
            time.sleep(0.15)
            t1 = time.time()
            while time.time() - t1 < 0.4:
                line = s.readline()
                if line:
                    print("<", line.decode(errors="replace").rstrip())
        # trailing read
        t2 = time.time()
        while time.time() - t2 < read_s:
            line = s.readline()
            if line:
                print("<", line.decode(errors="replace").rstrip())


if __name__ == "__main__":
    main()
