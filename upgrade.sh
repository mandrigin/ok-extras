#!/bin/bash
# Upgrade an existing installation without rerunning account/network provisioning.
set -euo pipefail
if (( EUID != 0 )); then
  echo 'Run: sudo bash upgrade.sh' >&2
  exit 1
fi
SRC=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
export OMARCHY_PATH=/usr/share/omarchy
export PATH="$OMARCHY_PATH/bin:/usr/local/bin:/usr/bin"
[[ -f /etc/omarchy-kids/policy.json ]] || { echo 'Install ok-extras before using this upgrade.' >&2; exit 1; }
read -r CHILD CHILD_UID CHILD_GID CHILD_HOME < <(python3 - <<'PY'
import json,pwd
config=json.load(open('/etc/omarchy-kids/policy.json'))
a=pwd.getpwuid(int(config['child_uid']))
assert a.pw_uid >= 1000 and a.pw_name != 'nobody'
print(a.pw_name,a.pw_uid,a.pw_gid,a.pw_dir)
PY
)
[[ -n ${CHILD:-} ]] || exit 1
cd "$SRC"
python3 packaging/configure_desktop.py --check
python3 packaging/configure_launcher.py --check
omarchy-pkg-add tk python-pillow gcc make patch pkgconf sdl2-compat zlib libx11 vlc-plugin-ffmpeg retroarch libretro-genesis-plus-gx libretro-nestopia retroarch-assets-ozone
command -v java >/dev/null || omarchy-pkg-add jre21-openjdk
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
python3 -c 'import tkinter; from PIL import Image, ImageTk'

BACKUP=$(mktemp -d /var/lib/omarchy-kids/upgrade-backup-XXXXXXXX)
chmod 700 "$BACKUP"
cp -a /opt/omarchy-kids-policy "$BACKUP/code"
cp -a /etc/omarchy-kids "$BACKUP/config"
cp -a /usr/share/omarchy/lib/parent/omarchy_kids/screen_time/service.py "$BACKUP/native-time-service.py"
cp -a /usr/share/omarchy/shell/services/AppLibrary.qml "$BACKUP/AppLibrary.qml"
cp -a /usr/share/omarchy/shell/plugins/menu/Menu.qml "$BACKUP/Menu.qml"
cp -a /etc/sudoers.d/zzz-omarchy-kids-launch "$BACKUP/sudoers"
[[ ! -f $CHILD_HOME/.config/omarchy/shell.json ]] || cp -a "$CHILD_HOME/.config/omarchy/shell.json" "$BACKUP/shell.json"
echo "Backup: $BACKUP"
bash packaging/install_games.sh
python3 packaging/configure_retro.py "$CHILD"

as_child() {
  runuser -u "$CHILD" -- env OMARCHY_PATH="$OMARCHY_PATH" PATH="$PATH" \
    XDG_RUNTIME_DIR="/run/user/$CHILD_UID" \
    DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$CHILD_UID/bus" "$@"
}
# Ask any old UI to restore hidden windows before replacing its files.
if [[ -x /usr/bin/omarchy-kids-ui ]]; then
  as_child /usr/bin/omarchy-kids-ui --quit || true
fi
as_child systemctl --user stop omarchy-kids-hud.service omarchy-kids-game-time-dashboard.service 2>/dev/null || true

install -d -m 0755 /opt/omarchy-kids-policy
cp -a kids_policy hud.py viewer.py shell /opt/omarchy-kids-policy/
chown -R root:root /opt/omarchy-kids-policy
python3 packaging/configure_desktop.py
python3 packaging/configure_launcher.py
if ! systemctl restart omarchy-kids-timed.service; then
  cp -a "$BACKUP/native-time-service.py" /usr/share/omarchy/lib/parent/omarchy_kids/screen_time/service.py
  systemctl restart omarchy-kids-timed.service
  echo 'Native time service restored; desktop integration upgrade failed.' >&2
  exit 1
fi
python3 - "$CHILD_UID" <<'PY'
import sys,time
sys.path.insert(0, '/opt/omarchy-kids-policy')
from kids_policy.desktop import status
for attempt in range(10):
    current = status(int(sys.argv[1]))
    if current.get('extension_supported'):
        break
    time.sleep(0.5)
else:
    raise SystemExit('Native desktop-time integration did not become ready')
PY
install -m 0755 bin/* /usr/bin/
install -m 0644 polkit/com.omarchy.kids.policy /usr/share/polkit-1/actions/com.omarchy.kids.policy

SUDO_STAGE=$(mktemp)
trap 'rm -f "$SUDO_STAGE"' EXIT
python3 - "$CHILD" > "$SUDO_STAGE" <<'PY'
import sys
child=sys.argv[1]
print(f'{child} ALL=(root) NOPASSWD: /usr/bin/omarchy-kids-launch')
print(f'{child} ALL=(root) NOPASSWD: /usr/bin/omarchy-kids-grant --free-minute')
for budget in ('digger','shared','vlc','micropolis','retro'):
    print(f'{child} ALL=(root) NOPASSWD: /usr/bin/omarchy-kids-grant --free-minute --budget {budget}')
print('Defaults!/usr/bin/omarchy-kids-launch env_keep += "DISPLAY WAYLAND_DISPLAY XDG_RUNTIME_DIR DBUS_SESSION_BUS_ADDRESS HYPRLAND_INSTANCE_SIGNATURE XDG_SESSION_TYPE XDG_CURRENT_DESKTOP LIBGL_ALWAYS_SOFTWARE"')
print('Defaults:parent !rootpw')
PY
visudo -cf "$SUDO_STAGE"
install -m 0440 "$SUDO_STAGE" /etc/sudoers.d/zzz-omarchy-kids-launch

install -d -o "$CHILD_UID" -g "$CHILD_GID" "$CHILD_HOME/.local/share/applications" "$CHILD_HOME/.config/systemd/user"
# The allow-list reconciler generates the child's app launchers from policy.json.
install -d -m 0755 /usr/local/share/applications
install -m 0644 desktop/digger.desktop desktop/kids-videos.desktop desktop/micropolis.desktop /usr/local/share/applications/
install -m 0644 -o "$CHILD_UID" -g "$CHILD_GID" user-systemd/omarchy-kids-hud.service "$CHILD_HOME/.config/systemd/user/omarchy-kids-hud.service"
python3 packaging/configure_ui.py "$CHILD"
/usr/bin/omarchy-kids-reload
as_child systemctl --user daemon-reload
as_child systemctl --user enable --now omarchy-kids-hud.service
as_child omarchy-shell shell reloadConfig
as_child omarchy-restart-shell
sleep 2
systemctl is-active omarchy-kids-policy.service
as_child systemctl --user is-active omarchy-kids-hud.service
python3 - <<'PY'
import json
state=json.load(open('/var/lib/omarchy-kids/usage.json'))
assert 'app_status' in state, 'Policy daemon did not load the new version'
print('App allowances:',state['enabled_apps'])
PY
printf '%s\n' 'Upgraded: app controls now show desktop restrictions and offer a parent-approved bedtime extension.'
