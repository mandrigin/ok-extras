#!/usr/bin/python3
import grp
import json
import os
from pathlib import Path
import pwd
import sys
import subprocess

sys.path.insert(0, str(Path(__file__).resolve().parent))
from retro import LIBRARY, refresh_playlist


def main():
    child = pwd.getpwnam(sys.argv[1])
    policy_path = Path('/etc/omarchy-kids/policy.json')
    policy = json.loads(policy_path.read_text())
    parent = pwd.getpwnam(policy.get('parent_user', 'parent'))
    try:
        media_gid = grp.getgrnam('kids-media').gr_gid
    except KeyError:
        subprocess.run(['groupadd', 'kids-media'], check=True)
        media_gid = grp.getgrnam('kids-media').gr_gid
    for name in (child.pw_name, parent.pw_name):
        subprocess.run(['usermod', '-aG', 'kids-media', name], check=True)
    LIBRARY.mkdir(parents=True, mode=0o750, exist_ok=True)
    os.chown(LIBRARY, parent.pw_uid, media_gid)
    playlists = LIBRARY / 'playlists'
    playlists.mkdir(mode=0o755, exist_ok=True)
    os.chown(playlists, parent.pw_uid, media_gid)
    refresh_playlist()
    os.chown(playlists / 'Retro Games.lpl', parent.pw_uid, media_gid)
    save_root = Path(child.pw_dir, '.local/share/retroarch')
    for directory in (save_root, save_root / 'saves', save_root / 'states', save_root / 'system'):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chown(directory, child.pw_uid, child.pw_gid)
    settings = json.loads(Path(__file__).with_name('player.json').read_text())
    settings.update({'rgui_browser_directory': str(LIBRARY), 'playlist_directory': str(playlists),
                     'savefile_directory': str(save_root / 'saves'), 'savestate_directory': str(save_root / 'states'),
                     'system_directory': str(save_root / 'system')})
    target = Path('/etc/omarchy-kids/retroarch.cfg')
    if not target.exists():
        target.write_text(''.join(f'{key} = {json.dumps(value)}\n' for key, value in settings.items()))
        target.chmod(0o644)


if __name__ == '__main__':
    main()
