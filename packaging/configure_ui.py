"""Install bar settings without disabling the native desktop-time service."""
import json
import os
from pathlib import Path
import pwd
import sys


def configure(data, source='/opt/omarchy-kids-policy/shell'):
    data.setdefault('bar', {}).setdefault('layout', {})
    layout = data['bar']['layout']
    for section in ('left', 'center', 'right'):
        layout.setdefault(section, [])
        layout[section] = [entry for entry in layout[section]
                           if (entry.get('id') if isinstance(entry, dict) else entry)
                           not in ('ok-extras.apps', 'ok-extras.desktop-label')]
    label = {'id': 'ok-extras.desktop-label', 'type': 'qml', 'source': source + '/DesktopLabel.qml'}
    apps = {'id': 'ok-extras.apps', 'type': 'qml', 'source': source + '/BarWidget.qml'}
    for entries in layout.values():
        for i, entry in enumerate(entries):
            if (entry.get('id') if isinstance(entry, dict) else entry) == 'omarchy.screen-time':
                entries.insert(i, label)
                entries.insert(i + 2, apps)
                return data
    layout['right'].append(apps)
    return data


def main():
    account = pwd.getpwnam(sys.argv[1])
    path = Path(account.pw_dir) / '.config/omarchy/shell.json'
    source = path if path.exists() else Path('/usr/share/omarchy/config/omarchy/shell.json')
    data = configure(json.loads(source.read_text()))
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chown(path.parent, account.pw_uid, account.pw_gid)
    stage = path.with_suffix('.kids-ui.tmp')
    stage.write_text(json.dumps(data, indent=2) + '\n')
    os.chown(stage, account.pw_uid, account.pw_gid)
    stage.chmod(0o644)
    stage.replace(path)


if __name__ == '__main__':
    main()
