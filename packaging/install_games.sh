#!/bin/bash
# Pinned upstream releases; build Digger without root and replace atomically.
set -euo pipefail
SRC=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
stage=$(mktemp -d /var/tmp/ok-extras-games-XXXXXXXX)
trap 'rm -rf -- "$stage"' EXIT
curl -fsSL --retry 3 https://codeload.github.com/sobomax/digger/tar.gz/e85cab1164f0304b3e66f371a5997d83f7a0090a -o "$stage/digger.tar.gz"
curl -fsSL --retry 3 https://github.com/dheid/micropolis/releases/download/v2.0.0/micropolis-2.0.0.tar -o "$stage/micropolis.tar"
printf '%s  %s\n' \
  639624228aa8f8623a381085389fd9c6694e49f3b0a8ecf386292554533d7788 "$stage/digger.tar.gz" \
  75355e0ac649f27a48d5ced9782f4feab381e0fbaf2a8193a5c61ff980f7128a "$stage/micropolis.tar" | sha256sum -c -
mkdir "$stage/build"
cp "$SRC/digger-resizable.patch" "$stage/build/"
chmod 755 "$stage"
chown -R nobody "$stage/build"
runuser -u nobody -- tar -xzf "$stage/digger.tar.gz" -C "$stage/build"
runuser -u nobody -- tar -xf "$stage/micropolis.tar" -C "$stage/build"
build="$stage/build/digger-e85cab1164f0304b3e66f371a5997d83f7a0090a"
runuser -u nobody -- sh -c 'cd "$1" && patch -p1 < ../digger-resizable.patch && nice -n 19 make BUILD_TYPE=production -j2' sh "$build"
install -d -m 0755 /usr/local/lib/digger /opt/micropolis-2.0.0 /usr/local/bin
if [[ -f /usr/local/lib/digger/digger && ! -f /usr/local/lib/digger/digger.before-resizable ]]; then
  cp -a /usr/local/lib/digger/digger /usr/local/lib/digger/digger.before-resizable
fi
install -m 0755 "$build/digger" /usr/local/lib/digger/digger.kids-new
mv -f /usr/local/lib/digger/digger.kids-new /usr/local/lib/digger/digger
cp -a "$stage/build/micropolis-2.0.0/." /opt/micropolis-2.0.0/
chown -R root:root /opt/micropolis-2.0.0
cat > /usr/local/bin/micropolis <<'SH'
#!/bin/sh
# XWayland Java/Swing needs this hint under Hyprland.
export _JAVA_AWT_WM_NONREPARENTING=1
mkdir -p "$HOME/.local/share/micropolis"
cd "$HOME/.local/share/micropolis" || exit 1
exec /usr/bin/java -Dsun.java2d.uiScale=1.5 -cp /opt/micropolis-2.0.0/lib/micropolis-2.0.0.jar micropolisj.Micropolis "$@"
SH
chmod 0755 /usr/local/bin/micropolis
echo 'Installed Micropolis and resizable Digger. Running games keep their current executable.'
