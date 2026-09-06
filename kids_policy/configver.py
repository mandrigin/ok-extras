import datetime as dt
import json
from pathlib import Path

from kids_policy import ALLOWLIST_SCHEMA, POLICY_SCHEMA
from kids_policy.migrate import default_config
from kids_policy.paths import HISTORY
from kids_policy.store import read_json, write_json


def backup(path, kind):
    path = Path(path)
    if not path.is_file():
        return None
    HISTORY.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime('%Y%m%dT%H%M%S')
    try:
        version = json.loads(path.read_text()).get('schema_version', 0)
    except (OSError, json.JSONDecodeError):
        version = 0
    dest = HISTORY / f'{kind}-v{version}-{stamp}{path.suffix}'
    dest.write_bytes(path.read_bytes())
    dest.chmod(0o644)
    prune(kind, keep=30)
    return dest


def prune(kind, keep=30):
    files = sorted(HISTORY.glob(f'{kind}-v*-*'), reverse=True)
    for old in files[keep:]:
        old.unlink(missing_ok=True)


def history(kind=None):
    pattern = f'{kind}-v*-*' if kind else '*-v*-*'
    return [path.name for path in sorted(HISTORY.glob(pattern))]


def migrate_allowlist(data):
    original = data
    if not data:
        data = {}
    if isinstance(data, list):
        data = {'games': list(data), 'videos': [], 'tools': ['screentime']}
    migrated = {
        'schema_version': ALLOWLIST_SCHEMA,
        'games': list(data.get('games') or []),
        'videos': list(data.get('videos') or ['vlc']),
        'tools': list(data.get('tools') or ['screentime']),
    }
    changed = not isinstance(original, dict) or original.get('schema_version') != ALLOWLIST_SCHEMA
    return migrated, changed


def migrate_policy(data, uid=1000):
    base = default_config(uid)
    if not data:
        return base, True
    changed = int(data.get('schema_version') or 0) < POLICY_SCHEMA
    merged = dict(base)
    for key, value in data.items():
        if key == 'apps' and isinstance(value, dict):
            merged['apps'] = {**base['apps'], **value}
        elif key != 'schema_version':
            merged[key] = value
    merged['schema_version'] = POLICY_SCHEMA
    merged.setdefault('vlc_daily_minutes', 60)
    merged.setdefault('extra_minute_tiers', [15, 30, 60])
    return merged, changed or merged != data


def load_or_migrate(path, kind, migrator):
    current = read_json(path, None)
    migrated, changed = migrator(current)
    if changed or current is None:
        if current is not None:
            backup(path, kind)
        write_json(path, migrated)
    return migrated
