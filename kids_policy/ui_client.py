"""Unprivileged entry points to the single desktop UI process."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time


def runtime():
    directory = Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')) / 'omarchy-kids-ui'
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    return directory


def send(message, start=True):
    payload = json.dumps(message).encode()
    address = str(runtime() / 'control.sock')

    def attempt():
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
                sock.sendto(payload, address)
            return True
        except OSError:
            return False

    if attempt():
        return True
    if not start:
        return False
    with (runtime() / 'startup.log').open('ab') as output:
        subprocess.Popen([sys.executable, str(Path(__file__).resolve().parents[1] / 'hud.py')],
                         stdin=subprocess.DEVNULL, stdout=output, stderr=output, start_new_session=True)
    for _ in range(50):
        time.sleep(0.1)
        if attempt():
            return True
    error = 'Screen-time controls could not start. Run the ok-extras upgrade to install the UI dependencies.'
    print(error, file=sys.stderr)
    subprocess.run(['/usr/share/omarchy/bin/omarchy-notification-send', 'Screen time', error], check=False)
    return False
