import subprocess
import threading
import re
import sys
import keyboard
import argparse

def main():
    parser = argparse.ArgumentParser(description="Extract crop limits from app.py log.")
    parser.add_argument("-i", "--import", dest="dicom_dir", help="DICOM directory to import", default=None)
    args = parser.parse_args()

    # Build the command for subprocess
    cmd = [sys.executable, "app.py"]
    if args.dicom_dir:
        cmd += ["-i", args.dicom_dir]

    # Start app.py as a subprocess
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    crop_limits = None
    pattern = re.compile(
        r"Sending message in topic Update crop limits into gui with data \{'limits': \[([^\]]+)\]\}"
    )

    def read_stdout():
        nonlocal crop_limits
        for line in proc.stdout:
            match = pattern.search(line)
            if match:
                limits_str = match.group(1)
                crop_limits = [int(x.strip()) for x in limits_str.split(",")]

    def on_ctrl_a():
        if crop_limits is not None:
            print(f"{crop_limits}")
            proc.terminate()
            sys.exit(0)

    # Start reading stdout in a separate thread
    t = threading.Thread(target=read_stdout, daemon=True)
    t.start()

    # Register Ctrl+A hotkey
    keyboard.add_hotkey('ctrl+a', on_ctrl_a)

    proc.wait()

if __name__ == "__main__":
    main()