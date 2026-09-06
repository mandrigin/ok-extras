# ok-extras

Extras on top of [peterholko/omarchy-kids](https://github.com/peterholko/omarchy-kids).

**Principle: allow-list, default deny.** The kid only gets what is in `/etc/omarchy-kids/allowlist.json`. Everything else is not enabled (hidden and closed). This is always on, not only during school hours. Parent (or AI) edits that file; `sudo omarchy-kids-reload` applies it.

Also: per-category time (games / Digger / videos), bedtime, offline VLC library, child network isolation, remaining-time HUD.

This repo does **not** replace Kids core, School, DNS, or Number Grove. Install `omarchy-kids` first, then this overlay.

## Depends on

- [peterholko/omarchy-kids](https://github.com/peterholko/omarchy-kids) (`omarchy-kids-core`; `omarchy-kids-time` recommended)
- A child account (UID in `policy.json`)

## What this adds

- `/etc/omarchy-kids/allowlist.json` — anything not listed is hidden and closed
- Separate budgets: shared games, Digger, Micropolis (30 minutes), VLC
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
sudo bash update.sh
```

The updater fetches a clean copy of this repo and runs `upgrade.sh`. It preserves
machine-specific edits in your checkout, existing budgets, schedules and daily
usage. Backups go to `/var/lib/omarchy-kids/upgrade-backup-*`.

This upgrade installs Micropolis, enables its menu entry and gives it an independent
30-minute daily budget. It builds a pinned Digger release with a resizable SDL
window. Digger opens at four times its native pixel dimensions, fitted to the
monitor and floating. Existing running games retain their executable and position.

The bar labels the native overall budget **Desktop** and shows separate app
allowances. Click an app allowance for parent +15/+30/+60 controls. Successful
extensions close the controls and return focus to the game; canceled authentication
leaves the controls open. When an app runs out of time, its frozen window appears
as a darkened grayscale preview with extension buttons. A denied launch opens the
same controls, using the last captured preview when available.

The persistent user UI needs Tk and Pillow, installed by the upgrade. The root
policy daemon remains responsible for enforcing limits. Desktop time is a separate
native limit: extending an app does not extend overall desktop time.

Tests: `python3 -m unittest discover -s tests -v`. For real widget tests, install
Tk, Pillow and Xvfb, then run
`OK_EXTRAS_UI_TEST=1 xvfb-run -a python3 -m unittest discover -s tests -v`.
