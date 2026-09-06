"""Coordinate parent-approved app time with Omarchy's desktop time service."""
import json
import math
import pwd
import socket
import time

from kids_policy import native_extension
from kids_policy.store import write_json

NATIVE_SOCKET = '/run/omarchy-kids/screen-time/sock'


def request(uid, command, **values):
    payload = dict(values, scope='time', user=pwd.getpwuid(uid).pw_name, cmd=command)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(2)
        sock.connect(NATIVE_SOCKET)
        sock.sendall((json.dumps(payload) + '\n').encode())
        data = b''
        while b'\n' not in data and len(data) <= 65536:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk
    reply = json.loads(data)
    if not reply.get('ok'):
        raise ValueError(reply.get('error', 'Desktop time service refused the request'))
    return reply


def status(uid):
    try:
        reply = request(uid, 'status')
        # Publish only what the app controls need, without quiz/history details.
        return {key: reply.get(key) for key in (
            'phase', 'remaining_seconds', 'blocked_label', 'locked',
            'extension_supported', 'extension_until', 'lock_in_seconds')}
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return {'error': 'Desktop time status unavailable: ' + str(exc)}


def refusal(desktop):
    if desktop.get('error'):
        return desktop['error'], 'desktop_unavailable'
    if desktop.get('phase') == 'bedtime':
        return 'Desktop blocked: ' + (desktop.get('blocked_label') or 'bedtime'), 'desktop_bedtime'
    if desktop.get('phase') in ('empty', 'exhausted') or desktop.get('remaining_seconds') == 0:
        return 'Desktop time is up', 'desktop_limit'
    return '', ''


def approve(uid, minutes, after_bedtime=False, grant_id='', now=None):
    """Called only by the root policy daemon after parent authentication.

    Top up the desktop to at least the approved interval, never double-credit
    an already sufficient desktop balance. Ordinary grants cannot change hours.
    """
    now = time.time() if now is None else now
    current = status(uid)
    reason, code = refusal(current)
    if code == 'desktop_unavailable':
        raise ValueError(reason)
    if code == 'desktop_bedtime' and not after_bedtime:
        raise ValueError(reason + '. Choose the parent option to play past bedtime.')
    if after_bedtime and not current.get('extension_supported'):
        raise ValueError('Install the desktop-time integration before extending bedtime.')
    needed = max(0, math.ceil((minutes * 60 - float(current.get('remaining_seconds') or 0)) / 60))
    if needed:
        request(uid, 'grant', minutes=needed)
    if after_bedtime:
        expires = max(native_extension.extension_until(uid, now), now + minutes * 60)
        write_json(native_extension.DIRECTORY / f'desktop-extension-{uid}.json',
                   {'uid': uid, 'created': now, 'expires': expires, 'grant_id': grant_id}, mode=0o644)
    verified = status(uid)
    reason, code = refusal(verified)
    if code:
        raise ValueError(reason + '. App time was not added; check Desktop time.')
    if after_bedtime and not verified.get('extension_until'):
        raise ValueError('Desktop service did not accept the bedtime extension; app time was not added.')
    return verified
