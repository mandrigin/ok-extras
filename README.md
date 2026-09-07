# ok-extras: parental controls for Omarchy Kids

A configurable parental-control layer for an existing Omarchy Kids installation. The core manages approved applications, allowance groups, local launchers, parent-approved extra time, and blocked-window controls. It does not install games or choose a family's software.

## Responsibilities

| Component | Owns |
| --- | --- |
| Omarchy Kids | Login, parent authentication, school mode, desktop time and bedtime locking |
| ok-extras core | App registry, allow-list, per-app/shared allowances, process enforcement, launcher visibility, allowance UI |
| Optional extensions | Application installation, app-specific launch/matching defaults, ROM and offline-video libraries |
| Local configuration | Child/parent accounts, selected apps, limits, schedules, commands, window sizes, network policy and extension preferences |

Target platform: Omarchy Kids on Arch Linux with Hyprland, Quickshell and systemd. This is not a desktop-independent Linux parental-control package. One child account is managed by each installation; multiple simultaneous child profiles are not yet supported.

## Install

First install Omarchy Kids and create the child and parent accounts. Select them explicitly:

```sh
sudo bash install-guest.sh --child CHILD_ACCOUNT --parent PARENT_ACCOUNT
```

A fresh installation has no games, no app allowance groups, and only the Screen Time control enabled. Networking is unchanged. Add `--offline` to explicitly isolate the selected child's network access. Account names and the firewall UID are generated from configuration.

For an existing installation:

```sh
sudo bash update.sh
```

Updates install core dependencies only. They preserve the configured apps, launch commands, allow-list, usage, grants, schedules, emulator settings and media libraries. Existing version-3 installations migrate their game definitions into ordinary version-4 configuration. Compatibility data under `kids_policy/legacy*` is used only for migration, never to select apps for a fresh installation.

The update backs up installed code and configuration before migration and restores them if the core upgrade fails. A running child session gets the updated controls. If the shell cannot restart because the screen is locked, it can refresh at the next login. Running applications are not intentionally closed by the updater.

## Configure applications and allowances

`/etc/omarchy-kids/policy.json` contains an `apps` registry and a `budgets` map. Each app selects an allowance group, or uses `null` for no daily allowance. Multiple apps can share any group; overlapping processes in one group consume wall-clock time once.

Example additions to an existing policy:

```json
{
  "budgets": {
    "creative": {"label": "Creative time", "daily_minutes": 45}
  },
  "apps": {
    "drawing": {
      "label": "Drawing",
      "argv": ["/usr/bin/tuxpaint"],
      "desktop": "tuxpaint.desktop",
      "icon": "tuxpaint",
      "category": "creativity",
      "budget": "creative",
      "schedule": true,
      "match": {
        "process": [{"executables": ["tuxpaint"]}],
        "windows": ["tuxpaint"]
      }
    }
  }
}
```

Add its ID to `/etc/omarchy-kids/allowlist.json`:

```json
{"schema_version": 2, "creativity": ["drawing"], "tools": ["screentime"]}
```

App IDs and allowance IDs are independent. Allow-list groups are arbitrary organizational labels. Empty lists stay empty. An installed app is not permitted until its ID is listed. Install applications separately or explicitly choose an extension.

Process rules use `names` (process names), `executables` (absolute paths or executable basenames), and optional `command_contains` markers. Names and executables are alternatives; command markers further constrain a rule. Multiple rules are alternatives. For launchers such as Java, match the actual runtime and a distinctive command marker. Processes started through the controlled launcher also inherit their app's root-owned cgroup, so child processes retain the same allowance. Ambiguous process matches fail instead of silently choosing a budget.

Window markers are case-insensitive substrings of the window class/title. Choose distinctive markers. New apps use the same registry for launch permissions, window matching, launchers, budget accounting and UI—no source-code app list needs editing.

Optional app properties:

- `env`: application environment variables, passed after dropping root privileges.
- `window`: `{ "width": 640, "height": 400, "scale": 2 }` for a configured floating window size, clamped to the monitor.
- `desktop_categories`: freedesktop category names, default `["Utility"]`.
- `budget: null`: unlimited daily app use; the allow-list and desktop schedule still apply.
- A budget's `daily_minutes: null`: unlimited group with usage reporting.

Configuration and allow-list changes are watched live. Invalid definitions are rejected. To apply explicitly and restart the policy service:

```sh
sudo omarchy-kids-reload
```

Changing the managed account or network policy requires running setup/upgrade, because these also affect system rules. Never point another child's policy at the same service/state directory.

## Schedules and time grants

Omarchy's native desktop schedule remains authoritative. The optional `play_windows` map can further restrict app hours; fresh defaults (`00:00`–`00:00`) add no restriction. Legacy installations keep their existing windows. To use only bedtime at the overall level, configure the native daily allowance to 24 hours; the per-app limits remain separate.

Bedtime blocks apps without recording unused allowance as time spent. Apps with no daily limit still respect bedtime. Parent approvals close the controls and return focus to the app when it is permitted to resume.

```sh
sudo omarchy-kids-grant --budget creative --minutes 15 --with-desktop
sudo omarchy-kids-grant --budget creative --minutes 15 --after-bedtime
sudo omarchy-kids-grant --schedule-only --minutes 15 --after-bedtime
```

Ordinary grants preserve bedtime and ensure enough overall desktop time for the requested interval. Only the explicit `--after-bedtime` action changes allowed hours temporarily. The schedule-only form adds no app allowance. Parent grants support 1–60 minutes per request; repeated request IDs are idempotent.

The child may request one free minute per day through a dedicated restricted helper. It cannot override bedtime or execute an ordinary parent grant.

## Optional extensions

```sh
omarchy-kids-extension list
sudo omarchy-kids-extension install digger
```

Installation explicitly enables that extension's apps and adds missing default definitions. Existing definitions and limits are kept. Remove app IDs from the allow-list to disable their use; the core does not uninstall their packages or delete saved data.

Available integrations: `digger`, `micropolis`, `retro`, `offline-video`, `minecraft`, and `stardew-valley`. The last two register software installed separately; they do not download commercial games. Their launch commands can be configured before enabling them.

RetroArch's extension imports arbitrary parent-supplied titles. Core mappings live in `/etc/omarchy-kids/extensions/retro.json`; player preferences live in `/etc/omarchy-kids/retroarch.cfg`.

```sh
omarchy-kids-import-rom my_game /path/to/game.nes --title 'My Game'
omarchy-kids-import-rom another_game /path/to/game.bin --core genesis_plus_gx
```

The offline-video extension owns `omarchy-kids-download` and `omarchy-kids-publish`. Media remains parent-owned under `/srv/kids-media`; no videos, ROMs, installers, or family libraries are included in this repository.

## Compatibility and verification

Omarchy integration currently uses guarded adapters for its native screen-time service and launcher QML. Unsupported layouts fail preflight. Reapply an update if Omarchy replaces those files. The native school-mode allow-list can further restrict what the core allows.

Before upgrading, a read-only on-device migration check is available:

```sh
python3 packaging/check_migration.py
```

It checks local account, app, schedule, allowance, usage and grant preservation and prints only results. It does not export household records.

Run tests with:

```sh
python3 -m unittest discover -s tests -v
OK_EXTRAS_UI_TEST=1 xvfb-run -a python3 -m unittest discover -s tests -v
```

The second form requires Tk, Pillow, Xvfb and Xauth. Linux GIO and Node enable desktop-entry and QML JavaScript checks. Tests include arbitrary apps/groups, unlimited use, legacy migration, parent approval, launcher synchronization and real Tk controls.
