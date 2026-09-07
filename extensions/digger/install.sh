#!/bin/bash
# Pinned upstream releases; build Digger without root and replace atomically.
set -euo pipefail
omarchy-pkg-add gcc make patch pkgconf sdl2-compat zlib libx11
SRC=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
stage=$(mktemp -d /var/tmp/ok-extras-games-XXXXXXXX)
trap 'rm -rf -- "$stage"' EXIT
curl -fsSL --retry 3 https://codeload.github.com/sobomax/digger/tar.gz/e85cab1164f0304b3e66f371a5997d83f7a0090a -o "$stage/digger.tar.gz"
printf '%s  %s\n' 639624228aa8f8623a381085389fd9c6694e49f3b0a8ecf386292554533d7788 "$stage/digger.tar.gz" | sha256sum -c -
mkdir "$stage/build"
cp "$SRC/digger-resizable.patch" "$stage/build/"
chmod 755 "$stage"
chown -R nobody "$stage/build"
runuser -u nobody -- tar -xzf "$stage/digger.tar.gz" -C "$stage/build"
build="$stage/build/digger-e85cab1164f0304b3e66f371a5997d83f7a0090a"
runuser -u nobody -- sh -c 'cd "$1" && patch -p1 < ../digger-resizable.patch && nice -n 19 make BUILD_TYPE=production -j2' sh "$build"
install -d -m 0755 /usr/local/lib/digger /usr/local/bin
install -m 0755 "$build/digger" /usr/local/lib/digger/digger.kids-new
mv -f /usr/local/lib/digger/digger.kids-new /usr/local/lib/digger/digger
printf '%s\n' '#!/bin/bash' 'exec /usr/local/lib/digger/digger "$@"' > /usr/local/bin/digger
chmod 755 /usr/local/bin/digger
