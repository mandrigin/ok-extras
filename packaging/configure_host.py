"""Render account-specific policy integration from configuration."""
import argparse
import json
import os
from pathlib import Path
import pwd
import re
import subprocess
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kids_policy.configver import migrate_policy, migrate_allowlist
from kids_policy.migrate import default_config
from kids_policy.store import write_json


def account(name):
    if not re.fullmatch(r'[a-z_][a-z0-9_-]*\$?', name):
        raise ValueError('Unsupported account name')
    return pwd.getpwnam(name)


def sudoers(child, parent):
    for name in (child, parent):
        if not re.fullmatch(r'[a-z_][a-z0-9_-]*\$?', name):
            raise ValueError('Unsupported account name')
    return '\n'.join([
        f'{child} ALL=(root) NOPASSWD: /usr/bin/omarchy-kids-launch *',
        f'{child} ALL=(root) NOPASSWD: /usr/bin/omarchy-kids-free-minute *',
        'Defaults!/usr/bin/omarchy-kids-launch env_keep += "DISPLAY WAYLAND_DISPLAY XDG_RUNTIME_DIR DBUS_SESSION_BUS_ADDRESS HYPRLAND_INSTANCE_SIGNATURE XDG_SESSION_TYPE XDG_CURRENT_DESKTOP LIBGL_ALWAYS_SOFTWARE"',
        f'Defaults:{parent} !rootpw', ''])


def firewall(uid):
    if type(uid) is not int or uid < 1000:
        raise ValueError('Refusing to restrict a system account')
    return f'''table inet omarchy-kids-net {{
  chain output {{
    type filter hook output priority 10; policy accept;
    meta skuid != {uid} accept
    ip daddr 127.0.0.53 drop
    ip6 daddr ::1 udp dport 53 drop
    ip6 daddr ::1 tcp dport 53 drop
    ip daddr 127.0.0.0/8 accept
    ip6 daddr ::1 accept
    drop
  }}
}}
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--child')
    parser.add_argument('--parent')
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    path = Path('/etc/omarchy-kids/policy.json')
    if path.exists():
        before = json.loads(path.read_text())
        config, _ = migrate_policy(before)
        child = pwd.getpwuid(config['child_uid'])
        if args.child and args.child != child.pw_name:
            raise ValueError('Existing policy belongs to another child; configure that account separately')
    else:
        if not args.child or not args.parent:
            raise ValueError('Fresh installation requires --child EXISTING_ACCOUNT --parent EXISTING_ACCOUNT')
        child = account(args.child)
        config = default_config(child.pw_uid)
    if args.parent:
        config['parent_user'] = args.parent
    parent = account(config['parent_user'])
    if child.pw_uid == parent.pw_uid:
        raise ValueError('Child and parent must be different accounts')
    if args.offline:
        config['network'] = {'mode': 'offline'}
    config, _ = migrate_policy(config)
    text = sudoers(child.pw_name, parent.pw_name)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.sudoers') as stage:
        stage.write(text)
        stage.flush()
        subprocess.run(['visudo', '-cf', stage.name], check=True)
    if args.check:
        print('Account and policy configuration valid:', child.pw_name)
        return
    from kids_policy.configver import backup
    if path.exists():
        backup(path, 'policy')
    write_json(path, config)
    allow = path.with_name('allowlist.json')
    original = json.loads(allow.read_text()) if allow.exists() else config['allowlist']
    permitted, changed = migrate_allowlist(original)
    if changed and allow.exists():
        backup(allow, 'allowlist')
    write_json(allow, permitted)
    target = Path('/etc/sudoers.d/zzz-omarchy-kids-launch')
    target.write_text(text)
    target.chmod(0o440)
    if config['network']['mode'] == 'offline':
        path.with_name('net.nft').write_text(firewall(child.pw_uid))
    print('Configured child:', child.pw_name, 'parent:', parent.pw_name)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError) as error:
        raise SystemExit(str(error))
