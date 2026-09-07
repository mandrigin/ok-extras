# Configure your family's parental controls

All household settings live on the child computer, outside this repository:

| File | Purpose |
| --- | --- |
| `/etc/omarchy-kids/policy.json` | Selected account, app registry, allowance groups, optional app hours, network mode |
| `/etc/omarchy-kids/allowlist.json` | Which configured apps may run and appear in the launcher |
| `/etc/omarchy-kids/extensions/` | Optional extension configuration |
| `/var/lib/omarchy-kids/` | Private installation state, grants, usage and configuration backups |

Native Omarchy's parent controls own the computer's overall allowance and bedtime. Set the overall allowance to 24 hours if you want only bedtime there; app allowances continue independently.

Open **Screen Time** to see enabled apps and add time. Successful approval closes the window and returns focus to the app. Outside allowed hours, the explicitly labeled bedtime exception requires parent authentication.

To add software, install it independently or select an optional extension, define its command and matching rules in `policy.json`, assign an allowance group (or `null` for unlimited), then list its ID in `allowlist.json`. See [README.md](README.md) for a complete example. Games are optional integrations, not part of the parental-control core.

`sudo omarchy-kids-reload` validates and applies app configuration. Invalid configuration is rejected. Existing usage and grants survive reloads and upgrades.

Parent-approved changes are backed up under `/var/lib/omarchy-kids/config-history/`. List them with `sudo omarchy-kids-config-history`. Keep machine addresses, real child names, personal libraries and passwords out of shared source control. The ignored `private/` and `*.local.json` paths are available for local development notes; deployment configuration belongs under `/etc/omarchy-kids/`.
