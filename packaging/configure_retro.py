#!/usr/bin/python3
import grp
import json
import os
from pathlib import Path
import pwd
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kids_policy.retro import LIBRARY, refresh_playlist


def main():
    child = pwd.getpwnam(sys.argv[1])
    policy_path = Path('/etc/omarchy-kids/policy.json')
    policy = json.loads(policy_path.read_text())
    parent = pwd.getpwnam(policy.get('parent_user', 'parent'))
    media_gid = grp.getgrnam('kids-media').gr_gid
    LIBRARY.mkdir(mode=0o750, exist_ok=True)
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
    settings = {
        'menu_driver': 'ozone', 'assets_directory': '/usr/share/retroarch/assets',
        'video_fullscreen': 'false', 'video_scale': '4.0',
        'video_smooth': 'false', 'savestate_auto_save': 'true', 'savestate_auto_load': 'true',
        'config_save_on_exit': 'false', 'menu_show_online_updater': 'false',
        'menu_show_core_updater': 'false', 'rgui_browser_directory': str(LIBRARY),
        'playlist_directory': str(playlists), 'savefile_directory': str(save_root / 'saves'),
        'savestate_directory': str(save_root / 'states'), 'system_directory': str(save_root / 'system'),
        'input_player1_up': 'up', 'input_player1_down': 'down',
        'input_player1_left': 'left', 'input_player1_right': 'right',
        'input_player1_a': 'x', 'input_player1_b': 'z', 'input_player1_y': 'a',
        'input_player1_start': 'enter', 'input_player1_select': 'rshift',
        'input_menu_toggle': 'f1', 'input_exit_emulator': 'escape',
    }
    target = Path('/etc/omarchy-kids/retroarch.cfg')
    if not target.exists():
        target.write_text(''.join(f'{key} = {json.dumps(value)}\n' for key, value in settings.items()))
        target.chmod(0o644)
    policy.setdefault('retro_daily_minutes', 30)
    policy_path.write_text(json.dumps(policy, indent=2) + '\n')


if __name__ == '__main__':
    main()
