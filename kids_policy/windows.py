import json
import os
import pwd
import subprocess
from pathlib import Path


def hypr_signature(uid):
    root = Path(f'/run/user/{uid}/hypr')
    if not root.is_dir():
        return None
    for entry in root.iterdir():
        if entry.is_dir():
            return entry.name
    return None


def hyprctl(uid, args, timeout=3):
    sig = hypr_signature(uid)
    if not sig:
        return None
    user = pwd.getpwuid(uid).pw_name
    env = {
        'XDG_RUNTIME_DIR': f'/run/user/{uid}',
        'HYPRLAND_INSTANCE_SIGNATURE': sig,
        'PATH': '/usr/bin',
    }
    try:
        result = subprocess.run(
            ['runuser', '-u', user, '--', 'env', *[f'{k}={v}' for k, v in env.items()], 'hyprctl', *args],
            check=False, capture_output=True, timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.decode(errors='replace')


def close_window(uid, address):
    lua = f'hl.dsp.window.close({{ window = "address:{address}" }})'
    hyprctl(uid, ['dispatch', lua])


def clients(uid):
    raw = hyprctl(uid, ['-j', 'clients'])
    if not raw:
        return []
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return []


def hide_pids(uid, pids, workspace='special:screentime'):
    wanted = {int(pid) for pid in pids}
    hidden = []
    for client in clients(uid):
        pid = int(client.get('pid') or 0)
        if pid not in wanted:
            continue
        address = client.get('address')
        if not address:
            continue
        hyprctl(uid, ['dispatch', 'movetoworkspacesilent', f'{workspace},address:{address}'])
        hidden.append(address)
    return hidden


def show_pids(uid, pids, workspace='1'):
    wanted = {int(pid) for pid in pids}
    for client in clients(uid):
        pid = int(client.get('pid') or 0)
        if pid not in wanted:
            continue
        address = client.get('address')
        if address:
            hyprctl(uid, ['dispatch', 'movetoworkspacesilent', f'{workspace},address:{address}'])
