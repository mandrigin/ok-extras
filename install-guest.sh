#!/bin/bash
# Install parental controls for explicitly selected, existing local accounts.
set -euo pipefail
if (( EUID != 0 )); then
  echo 'Run: sudo bash install-guest.sh --child CHILD --parent PARENT [--offline]' >&2
  exit 1
fi
SRC=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
export OMARCHY_PATH=/usr/share/omarchy
export PATH="$OMARCHY_PATH/bin:/usr/local/bin:/usr/bin"
python3 "$SRC/packaging/configure_host.py" --check "$@"
python3 "$SRC/packaging/configure_desktop.py" --check
python3 "$SRC/packaging/configure_launcher.py" --check
omarchy-pkg-add tk python-pillow
# On an existing machine use upgrade.sh; never race its active policy migration.
if [[ -f /etc/omarchy-kids/policy.json ]]; then
  echo 'Existing installation found. Use sudo bash upgrade.sh; its configuration is preserved.' >&2
  exit 1
fi
install -d -m 0755 /opt/omarchy-kids-policy /usr/lib/omarchy-kids /etc/omarchy-kids /var/lib/omarchy-kids
cp -a "$SRC/kids_policy" "$SRC/packaging" "$SRC/extensions" "$SRC/shell" "$SRC/hud.py" "$SRC/viewer.py" /opt/omarchy-kids-policy/
chown -R root:root /opt/omarchy-kids-policy
install -m 0755 "$SRC/bin/"* /usr/bin/
install -m 0755 "$SRC/lib/"* /usr/lib/omarchy-kids/
install -m 0644 "$SRC/systemd/"*.service /etc/systemd/system/
install -m 0644 "$SRC/polkit/com.omarchy.kids.policy" /usr/share/polkit-1/actions/com.omarchy.kids.policy
python3 "$SRC/packaging/configure_host.py" "$@"
bash "$SRC/upgrade.sh"
