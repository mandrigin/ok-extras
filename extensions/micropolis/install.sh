#!/bin/bash
set -euo pipefail
omarchy-pkg-add jre21-openjdk
stage=$(mktemp -d /var/tmp/ok-extras-micropolis-XXXXXXXX)
trap 'rm -rf -- "$stage"' EXIT
curl -fsSL --retry 3 https://github.com/dheid/micropolis/releases/download/v2.0.0/micropolis-2.0.0.tar -o "$stage/micropolis.tar"
printf '%s  %s\n' 75355e0ac649f27a48d5ced9782f4feab381e0fbaf2a8193a5c61ff980f7128a "$stage/micropolis.tar" | sha256sum -c -
tar -xf "$stage/micropolis.tar" -C "$stage"
install -d /opt/micropolis-2.0.0 /usr/local/bin
cp -a "$stage/micropolis-2.0.0/." /opt/micropolis-2.0.0/
cat > /usr/local/bin/micropolis <<'SH'
#!/bin/sh
# XWayland Java/Swing needs this hint under Hyprland.
export _JAVA_AWT_WM_NONREPARENTING=1
mkdir -p "$HOME/.local/share/micropolis"
cd "$HOME/.local/share/micropolis" || exit 1
exec /usr/bin/java -cp /opt/micropolis-2.0.0/lib/micropolis-2.0.0.jar micropolisj.Micropolis "$@"
SH
chmod 0755 /usr/local/bin/micropolis
