"""Create a parent-managed offline library; no videos are bundled."""
import grp
import json
import os
from pathlib import Path
import pwd
import subprocess
config = json.loads(Path('/etc/omarchy-kids/policy.json').read_text())
child = pwd.getpwuid(config['child_uid'])
parent = pwd.getpwnam(config['parent_user'])
try:
    group = grp.getgrnam('kids-media')
except KeyError:
    subprocess.run(['groupadd', 'kids-media'], check=True)
    group = grp.getgrnam('kids-media')
for user in (child.pw_name, parent.pw_name):
    subprocess.run(['usermod', '-aG', 'kids-media', user], check=True)
for name in ('videos', 'staging'):
    directory = Path('/srv/kids-media') / name
    directory.mkdir(parents=True, exist_ok=True)
    os.chown(directory, parent.pw_uid, group.gr_gid)
    directory.chmod(0o750 if name == 'videos' else 0o700)
playlist = Path('/srv/kids-media/videos/kids-videos.m3u')
if not playlist.exists():
    playlist.write_text('#EXTM3U\n')
    os.chown(playlist, parent.pw_uid, group.gr_gid)
    playlist.chmod(0o644)
