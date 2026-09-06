from pathlib import Path

CONFIG = Path('/etc/omarchy-kids/policy.json')
ALLOWLIST = Path('/etc/omarchy-kids/allowlist.json')
LEGACY_CONFIG = Path('/etc/omarchy-kids/game-limits.json')
STATE = Path('/var/lib/omarchy-kids/state.json')
USAGE = Path('/var/lib/omarchy-kids/usage.json')
FAILCLOSED = Path('/var/lib/omarchy-kids/failclosed')
SOCKET = Path('/run/omarchy-kids/control.sock')
CGROUP_ROOT = Path('/sys/fs/cgroup/omarchy-kids')
MEDIA = Path('/srv/kids-media/videos')
PLAYLIST = MEDIA / 'kids-videos.m3u'
STAGING = Path('/srv/kids-media/staging')
HISTORY = Path('/var/lib/omarchy-kids/config-history')
