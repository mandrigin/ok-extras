# Parent configuration

Log in as **parent** (not the kid). That account has internet. AI tools and a browser work there.

Edit these files, then apply:

```sh
sudo omarchy-kids-reload
```

## Allow-list

`/etc/omarchy-kids/allowlist.json` — anything not listed is hidden and closed for the kid.

```json
{
  "games": ["digger", "minecraft", "stardew_valley"],
  "videos": ["vlc"],
  "tools": ["screentime"]
}
```

Known ids: `digger`, `minecraft`, `stardew_valley`, `vlc`, `screentime`.

## Time limits

`/etc/omarchy-kids/policy.json`

- `shared_daily_minutes` — Minecraft + Stardew
- `digger_daily_minutes`
- `vlc_daily_minutes` — videos, separate category
- `extra_minute_tiers` — parent extra-time buttons, default `[15, 30, 60]`
- `play_windows` — weekday/weekend

An AI can edit these JSON files; reload after saving.

## Versioning

Each file has `schema_version`. Reload migrates old files and keeps copies in `/var/lib/omarchy-kids/config-history/` (`policy-v3-20260906T082421.json`, etc.). Last 30 of each kind are kept.

```sh
sudo omarchy-kids-config-history
sudo omarchy-kids-config-history allowlist
```
