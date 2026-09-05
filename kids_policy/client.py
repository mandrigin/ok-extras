import json
import socket
from pathlib import Path

from kids_policy.paths import FAILCLOSED, SOCKET


def failclosed():
    try:
        return Path(FAILCLOSED).read_text().strip() == '1'
    except OSError:
        return not SOCKET.exists()


def request(payload, timeout=5):
    if failclosed() and payload.get('op') in {'may_launch', 'launch', 'adopt'}:
        raise RuntimeError('policy service is fail-closed')
    if not SOCKET.exists():
        raise RuntimeError('policy service is not running')
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    sock.connect(str(SOCKET))
    sock.sendall((json.dumps(payload) + '\n').encode())
    data = b''
    while b'\n' not in data:
        chunk = sock.recv(4096)
        if not chunk:
            break
        data += chunk
    sock.close()
    if not data:
        raise RuntimeError('empty reply')
    reply = json.loads(data.decode())
    if not reply.get('ok'):
        raise RuntimeError(reply.get('error') or 'request failed')
    return reply
