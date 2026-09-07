#!/bin/bash
# Upgrade controls and regenerate system rules from the existing configuration.
set -Eeuo pipefail
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
omarchy-pkg-add tk python-pillow
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
python3 -c 'import tkinter; from PIL import Image, ImageTk'

BACKUP=$(mktemp -d /var/lib/omarchy-kids/upgrade-backup-XXXXXXXX)
chmod 700 "$BACKUP"
cp -a /opt/omarchy-kids-policy "$BACKUP/code"
cp -a /etc/omarchy-kids "$BACKUP/config"
cp -a /usr/share/omarchy/lib/parent/omarchy_kids/screen_time/service.py "$BACKUP/native-time-service.py"
cp -a /usr/share/omarchy/shell/services/AppLibrary.qml "$BACKUP/AppLibrary.qml"
cp -a /usr/share/omarchy/shell/plugins/menu/Menu.qml "$BACKUP/Menu.qml"
[[ ! -f /etc/sudoers.d/zzz-omarchy-kids-launch ]] || cp -a /etc/sudoers.d/zzz-omarchy-kids-launch "$BACKUP/sudoers"
[[ ! -f $CHILD_HOME/.config/omarchy/shell.json ]] || cp -a "$CHILD_HOME/.config/omarchy/shell.json" "$BACKUP/shell.json"
install -d "$BACKUP/bin"
install -d "$BACKUP/lib" "$BACKUP/systemd"
for file in /usr/lib/omarchy-kids/*; do
  [[ ! -f $file ]] || cp -a "$file" "$BACKUP/lib/"
done
for file in /etc/systemd/system/omarchy-kids-*.service; do
  [[ ! -f $file ]] || cp -a "$file" "$BACKUP/systemd/"
done
[[ ! -f /usr/share/polkit-1/actions/com.omarchy.kids.policy ]] || cp -a /usr/share/polkit-1/actions/com.omarchy.kids.policy "$BACKUP/polkit"
[[ ! -f $CHILD_HOME/.config/systemd/user/omarchy-kids-hud.service ]] || cp -a "$CHILD_HOME/.config/systemd/user/omarchy-kids-hud.service" "$BACKUP/user-hud.service"
for file in /usr/bin/omarchy-kids-*; do
  [[ ! -f $file ]] || cp -a "$file" "$BACKUP/bin/"
done
for name in state.json usage.json launcher.json; do
  [[ ! -f /var/lib/omarchy-kids/$name ]] || cp -a "/var/lib/omarchy-kids/$name" "$BACKUP/$name"
done
ROLLBACK_READY=0
rollback() {
  result=$?
  trap - ERR
  set +e
  if (( ROLLBACK_READY )); then
    systemctl stop omarchy-kids-policy.service
    cp -a "$BACKUP/code/." /opt/omarchy-kids-policy/
    cp -a "$BACKUP/config/." /etc/omarchy-kids/
    cp -a "$BACKUP/bin/." /usr/bin/
    cp -a "$BACKUP/lib/." /usr/lib/omarchy-kids/
    cp -a "$BACKUP/systemd/." /etc/systemd/system/
    [[ ! -f $BACKUP/polkit ]] || cp -a "$BACKUP/polkit" /usr/share/polkit-1/actions/com.omarchy.kids.policy
    [[ ! -f $BACKUP/user-hud.service ]] || cp -a "$BACKUP/user-hud.service" "$CHILD_HOME/.config/systemd/user/omarchy-kids-hud.service"
    cp -a "$BACKUP/native-time-service.py" /usr/share/omarchy/lib/parent/omarchy_kids/screen_time/service.py
    cp -a "$BACKUP/AppLibrary.qml" /usr/share/omarchy/shell/services/AppLibrary.qml
    cp -a "$BACKUP/Menu.qml" /usr/share/omarchy/shell/plugins/menu/Menu.qml
    [[ ! -f $BACKUP/sudoers ]] || cp -a "$BACKUP/sudoers" /etc/sudoers.d/zzz-omarchy-kids-launch
    for name in state.json usage.json launcher.json; do
      [[ ! -f $BACKUP/$name ]] || cp -a "$BACKUP/$name" "/var/lib/omarchy-kids/$name"
    done
    [[ ! -f $BACKUP/shell.json ]] || cp -a "$BACKUP/shell.json" "$CHILD_HOME/.config/omarchy/shell.json"
    systemctl daemon-reload
    systemctl restart omarchy-kids-timed.service omarchy-kids-policy.service
    as_child systemctl --user restart omarchy-kids-hud.service
    echo "Upgrade failed; previous code and configuration restored. Backup: $BACKUP" >&2
  fi
  exit "$result"
}
trap rollback ERR
echo "Backup: $BACKUP"
python3 packaging/configure_host.py --check

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
ROLLBACK_READY=1
systemctl stop omarchy-kids-policy.service
cp -a kids_policy hud.py viewer.py shell packaging extensions /opt/omarchy-kids-policy/
python3 packaging/configure_host.py
chown -R root:root /opt/omarchy-kids-policy
python3 packaging/configure_desktop.py
python3 packaging/configure_launcher.py
systemctl restart omarchy-kids-timed.service
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

# Compatibility commands are extension-owned; update existing integrations only.
python3 packaging/refresh_extensions.py
install -m 0755 lib/* /usr/lib/omarchy-kids/
install -m 0644 systemd/*.service /etc/systemd/system/
systemctl daemon-reload
python3 packaging/activate_network.py

install -d -o "$CHILD_UID" -g "$CHILD_GID" "$CHILD_HOME/.local/share/applications" "$CHILD_HOME/.config/systemd/user"
install -m 0644 -o "$CHILD_UID" -g "$CHILD_GID" user-systemd/omarchy-kids-hud.service "$CHILD_HOME/.config/systemd/user/omarchy-kids-hud.service"
python3 packaging/configure_ui.py "$CHILD"
systemctl enable omarchy-kids-cgroup.service omarchy-kids-policy.service
/usr/bin/omarchy-kids-reload
if [[ -S /run/user/$CHILD_UID/bus ]]; then
  as_child systemctl --user daemon-reload
  as_child systemctl --user enable --now omarchy-kids-hud.service
  as_child omarchy-shell shell reloadConfig
  if ! as_child omarchy-restart-shell; then
    echo 'Controls updated. Log out/in once the child is finished to refresh the shell.'
  fi
  as_child systemctl --user is-active omarchy-kids-hud.service
else
  install -d -o "$CHILD_UID" -g "$CHILD_GID" "$CHILD_HOME/.config/systemd/user/default.target.wants"
  ln -sfn ../omarchy-kids-hud.service "$CHILD_HOME/.config/systemd/user/default.target.wants/omarchy-kids-hud.service"
  echo 'Controls will start when the child next logs in.'
fi
sleep 2
systemctl is-active omarchy-kids-policy.service
python3 - <<'PY'
import json
state=json.load(open('/var/lib/omarchy-kids/usage.json'))
assert state.get('schema_version') == 3 and 'app_definitions' in state and 'budgets' in state, 'Policy daemon did not load the new version'
print('App allowances:',state['enabled_apps'])
PY
trap - ERR
printf '%s\n' 'Upgraded parental controls: configured apps and budgets preserved; no games installed.'
