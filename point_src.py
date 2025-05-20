import subprocess
import threading
import re
import sys
import keyboard

def main():
    # Start app.py as a subprocess
    proc = subprocess.Popen(
        [sys.executable, "app.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    coords = []
    last_position = None
    pattern = re.compile(r"Sending message in topic Update volume viewer pointer with data \{'position': \[([^\]]+)\]\}")

    def read_stdout():
        nonlocal last_position
        for line in proc.stdout:
            match = pattern.search(line)
            if match:
                pos_str = match.group(1)
                last_position = [float(x.strip()) for x in pos_str.split(",")]
                # print(f"Detected position: {last_position}")

    def on_ctrl_t():
        if last_position is not None:
            coords.append(last_position.copy())
        if len(coords) == 2:
            print(f"{coords[0]};{coords[1]}")
            proc.terminate()
            sys.exit(0)

    # Start reading stdout in a separate thread
    t = threading.Thread(target=read_stdout, daemon=True)
    t.start()

    # Register Ctrl+A hotkey
    keyboard.add_hotkey('ctrl+a', on_ctrl_t)

    # print("Waiting for two points. Press Ctrl+A after each desired message appears.")
    proc.wait()

if __name__ == "__main__":
    main()