# ok-extras

Extras on top of [peterholko/omarchy-kids](https://github.com/peterholko/omarchy-kids): allow-list, per-category time (games / Digger / videos), bedtime, offline VLC library, network isolation, and the remaining-time HUD.

This repo does **not** replace Kids core, School, DNS, or Number Grove. Install `omarchy-kids` first, then this overlay.

## Depends on

- [peterholko/omarchy-kids](https://github.com/peterholko/omarchy-kids) (`omarchy-kids-core`; `omarchy-kids-time` recommended)
- A child account (UID in `policy.json`)

## What this adds

- `/etc/omarchy-kids/allowlist.json` — anything not listed is hidden and closed
- Separate budgets: shared games, Digger, VLC
- One free “1 more minute”, then parent 15/30/60
- Offline Kids Videos (`yt-dlp` as parent → VLC `--no-network`)
- Child UID nftables block; parent keeps internet
- Config `schema_version` + `/var/lib/omarchy-kids/config-history/`

Parent/AI edits JSON, then `sudo omarchy-kids-reload`. See [PARENT.md](PARENT.md).

## Install

```sh
sudo bash install-guest.sh /path/to/ok-extras
sudo omarchy-kids-reload
```

Do not blindly rerun install on a live machine if you already have parent-edited `policy.json` / `allowlist.json`; current install migrates those instead of clobbering them.

## Upgrade

```sh
git pull --ff-only
sudo omarchy-kids-reload
```

Replace code under `/opt/omarchy-kids-policy` and `/usr/bin/omarchy-kids-*`. Keep `/etc/omarchy-kids/*.json` and `/var/lib/omarchy-kids/state.json`.
