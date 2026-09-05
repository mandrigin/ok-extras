# Omarchy Kids extras

Local extras for the **Omarchy Kids Test** VM. This repository is private/local. It is not an upstream Omarchy PR.

Base: Omarchy kids foundation `97a571f` ([PR #9750](https://github.com/omacom/omarchy/pull/9750), `peterholko/omarchy:kids/child-profile`).

Paid Minecraft/Stardew content is still not installed.

## Features

- Parent desktop account `parent` (wheel, private home). Elevation for the child still uses the kids parent/root password; `parent` sudo uses the parent login password.
- Child UID nftables isolation (IPv4/IPv6). Localhost IPC allowed except DNS to `127.0.0.53`.
- Policy service: shared 60-minute Minecraft/Stardew budget, separate 10-minute Digger budget, weekday 09:00–21:00 and weekend 08:00–21:00 windows, cgroup freeze with pidfd fallback, fail-closed on service failure.
- Parent extensions: +minutes (does not cross bedtime) and allow-until schedule override, via polkit.
- Offline video library: VLC `--no-network`, `/srv/kids-media/videos`, parent publish/download helpers.
- Approved launchers go through `omarchy-kids-launch`. Steam/Prism menu entries are hidden.

## Layout

| Path | Role |
| --- | --- |
| `kids_policy/` | Authoritative policy logic |
| `bin/` | launch, grant, publish, download, policy daemon |
| `systemd/` | cgroup, policy, fail-closed, net |
| `nft/net.nft` | child `meta skuid` isolation |
| `../omarchy-fork/` | local Omarchy worktree stacked on the kids PR |

## Guest paths

- Config: `/etc/omarchy-kids/policy.json`
- State: `/var/lib/omarchy-kids/state.json` and `usage.json`
- Media: `/srv/kids-media/videos`
- Parent login password (first create only): `/root/parent-login-password`
