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
- Separate budgets: shared games, Digger, Micropolis (30 minutes), Retro games (30 minutes shared), VLC
- One free “1 more minute”, then parent 15/30/60
- Offline Kids Videos (`yt-dlp` as parent → VLC `--no-network`)
- Child UID nftables block; parent keeps internet
- Config `schema_version` + `/var/lib/omarchy-kids/config-history/`

Parent/AI edits JSON, then `sudo omarchy-kids-reload`. See [PARENT.md](PARENT.md).

## Install

```sh
sudo bash install-guest.sh /path/to/ok-extras
sudo bash upgrade.sh
```

Do not blindly rerun install on a live machine if you already have parent-edited `policy.json` / `allowlist.json`; current install migrates those instead of clobbering them.

## Upgrade

```sh
sudo bash update.sh
```

App controls show both the selected game's time and Desktop time. A parent's
ordinary +15/+30/+60 grant adds game time and tops up Desktop time only when
needed to cover that interval. It never changes allowed hours. Outside allowed
hours, the separate **Allow 15/30/60 min past bedtime** action requires parent
authentication and temporarily permits both the game and desktop. The exception
expires automatically, including after a daemon restart; weekly schedules are
unchanged. The free minute cannot override desktop limits or bedtime.

The upgrade installs a small compatibility hook in Omarchy's native screen-time
service, backed up beside the original file and in the upgrade backup. Reapply
this upgrade after an Omarchy update that replaces that service. Unsupported
native layouts are rejected before installation, and missing desktop status
keeps games blocked rather than reporting a successful extension.

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
native limit: parent grants from the app controls now coordinate both limits.

Tests: `python3 -m unittest discover -s tests -v`. For real widget tests, install
Tk, Pillow and Xvfb, then run
`OK_EXTRAS_UI_TEST=1 xvfb-run -a python3 -m unittest discover -s tests -v`.

## Retro games

The upgrade installs RetroArch, Genesis Plus GX for Sega Mega Drive/Genesis,
Nestopia for NES, and a **Retro Games** menu entry. All emulated games share
`retro_daily_minutes` (default 30), with the same schedule and parent extension UI.
Existing Digger, Micropolis and video allowances remain separate.

Commercial ROMs are supplied separately. As `parent`, import an extracted file:

```sh
omarchy-kids-import-rom lion_king '/path/to/Lion King.md'
omarchy-kids-import-rom aladdin '/path/to/Aladdin.md'
omarchy-kids-import-rom super_mario_bros '/path/to/Super Mario Bros.nes'
omarchy-kids-import-rom theme_park '/path/to/Theme Park.md'
```

The Sega games accept `.md`, `.gen`, `.bin` and `.smd`; Super Mario Bros. accepts
an iNES/NES 2.0 `.nes` file. The importer keeps the source file, refuses overwrites,
and adds the game to the **Retro Games** playlist with the correct emulator core.
The library lives in `/srv/kids-media/roms`, owned by `parent` and readable by the
child. It contains no bundled commercial ROMs.

Open **Retro Games**, select its playlist, then a game and **Run**. Arrow keys move;
`Z`/`X` are NES B/A; `A`/`Z`/`X` are Sega A/B/C; Enter is Start. F1 opens the
emulator menu and Escape exits. Autosave states resume on the next launch; saves
stay in the child's `~/.local/share/retroarch`. Play starts in a window.
