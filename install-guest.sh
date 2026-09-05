#!/bin/bash
set -euo pipefail
exec > >(tee /var/tmp/omarchy-kids-extras-install.log) 2>&1
SRC=${1:-/opt/omarchy-kids-policy-src}
as_user() {
  runuser -u vltn -- env OMARCHY_PATH=/usr/share/omarchy XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus "$@"
}

snapper create --description 'Before kids extras' || true
cd "$SRC"
PYTHONPATH=. python3 -m unittest discover -s tests -v

install -d -m 0755 /opt/omarchy-kids-policy /usr/lib/omarchy-kids /etc/omarchy-kids /var/lib/omarchy-kids /run/omarchy-kids
cp -a "$SRC/kids_policy" "$SRC/viewer.py" "$SRC/tests" /opt/omarchy-kids-policy/
install -m 0755 "$SRC/bin/"* /usr/bin/
install -m 0755 "$SRC/lib/"* /usr/lib/omarchy-kids/
install -m 0644 "$SRC/systemd/"*.service /etc/systemd/system/
install -m 0644 "$SRC/nft/net.nft" /etc/omarchy-kids/net.nft
install -m 0644 "$SRC/polkit/com.omarchy.kids.policy" /usr/share/polkit-1/actions/com.omarchy.kids.policy
install -m 0440 "$SRC/sudoers/omarchy-kids-launch" /etc/sudoers.d/60-omarchy-kids-launch
visudo -cf /etc/sudoers.d/60-omarchy-kids-launch

python3 - <<'PY'
import json
from pathlib import Path
import sys
sys.path.insert(0, '/opt/omarchy-kids-policy')
from kids_policy.migrate import default_config
from kids_policy.store import write_json
config = default_config(1000)
legacy = Path('/etc/omarchy-kids/game-limits.json')
if legacy.exists():
    data = json.loads(legacy.read_text())
    config['child_uid'] = int(data.get('uid', 1000))
    config['shared_daily_minutes'] = float(data.get('daily_minutes', 60))
    config['digger_daily_minutes'] = float(data.get('digger_daily_minutes', 10))
write_json('/etc/omarchy-kids/policy.json', config)
PY

if ! getent group kids-media >/dev/null; then
  groupadd kids-media
fi
if ! id parent >/dev/null 2>&1; then
  useradd -m -s /usr/bin/bash parent
  password=$(openssl rand -base64 12 | tr -d '/+=' | head -c 16)
  printf 'parent:%s\n' "$password" | chpasswd
  umask 077
  printf '%s\n' "$password" > /root/parent-login-password
  chmod 600 /root/parent-login-password
fi
for g in wheel audio video lp storage optical input render kids-media; do
  if getent group "$g" >/dev/null; then
    usermod -aG "$g" parent || true
  fi
done
usermod -aG kids-media vltn
install -d -m 0750 -o parent -g kids-media /srv/kids-media/videos
install -d -m 0700 -o parent -g parent /srv/kids-media/staging
if [[ ! -f /srv/kids-media/videos/kids-videos.m3u ]]; then
  printf '%s\n' '#EXTM3U' > /srv/kids-media/videos/kids-videos.m3u
  chown parent:kids-media /srv/kids-media/videos/kids-videos.m3u
  chmod 644 /srv/kids-media/videos/kids-videos.m3u
fi

pacman -S --noconfirm --needed vlc

if command -v ffmpeg >/dev/null && [[ ! -f /srv/kids-media/videos/welcome.mp4 ]]; then
  ffmpeg -y -f lavfi -i testsrc=duration=3:size=320x240:rate=10 -f lavfi -i sine=frequency=440:duration=3 -shortest -pix_fmt yuv420p /srv/kids-media/videos/welcome.mp4
  chown parent:kids-media /srv/kids-media/videos/welcome.mp4
  chmod 644 /srv/kids-media/videos/welcome.mp4
  python3 /usr/bin/omarchy-kids-publish /srv/kids-media/videos/welcome.mp4 >/dev/null 2>&1 || python3 - <<'PY'
from pathlib import Path
media = Path('/srv/kids-media/videos')
files = sorted(p for p in media.iterdir() if p.suffix.lower() in {'.mp4', '.mkv', '.webm'} and p.is_file())
lines = ['#EXTM3U']
for path in files:
    lines += [f'#EXTINF:-1,{path.stem}', str(path)]
media.joinpath('kids-videos.m3u').write_text('\n'.join(lines) + '\n')
PY
fi

install -d /usr/local/share/applications /home/vltn/.local/share/applications
install -m 0644 "$SRC/desktop/digger.desktop" /usr/local/share/applications/digger.desktop
install -m 0644 "$SRC/desktop/kids-videos.desktop" /usr/local/share/applications/kids-videos.desktop
install -m 0644 "$SRC/desktop/omarchy-kids-screentime.desktop" /home/vltn/.local/share/applications/omarchy-kids-screentime.desktop
install -m 0644 "$SRC/desktop/minecraft-vm.desktop" /home/vltn/.local/share/applications/minecraft-vm.desktop
install -m 0644 "$SRC/desktop/stardew-valley.desktop" /home/vltn/.local/share/applications/stardew-valley.desktop
install -m 0644 "$SRC/desktop/steam.hidden.desktop" /usr/local/share/applications/steam.desktop
install -m 0644 "$SRC/desktop/prism.hidden.desktop" /usr/local/share/applications/org.prismlauncher.PrismLauncher.desktop
chown vltn:vltn /home/vltn/.local/share/applications/*.desktop
update-desktop-database /usr/local/share/applications >/dev/null 2>&1 || true

/usr/lib/omarchy-kids/setup-cgroups
systemctl stop omarchy-kids-screentime.service 2>/dev/null || true
systemctl disable omarchy-kids-screentime.service 2>/dev/null || true
systemctl daemon-reload
systemctl enable --now omarchy-kids-cgroup.service omarchy-kids-net.service omarchy-kids-policy.service
sleep 2
systemctl is-active omarchy-kids-policy.service
systemctl is-active omarchy-kids-net.service

as_user systemctl --user stop omarchy-kids-game-time-dashboard.service 2>/dev/null || true
as_user systemd-run --user --collect --unit=omarchy-kids-game-time-dashboard --setenv=WAYLAND_DISPLAY=wayland-1 /usr/bin/python3 /opt/omarchy-kids-policy/viewer.py || true
as_user omarchy shell io.github.virajshoor.kids-screentime refresh || true

echo EXTRAS_INSTALLED
systemctl is-active omarchy-kids-policy.service
test -f /etc/omarchy-kids/policy.json
id parent
nft list table inet omarchy-kids-net >/dev/null
echo PARENT_PASSWORD_FILE=/root/parent-login-password
