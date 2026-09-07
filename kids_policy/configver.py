import datetime as dt
import json
from pathlib import Path

from kids_policy import ALLOWLIST_SCHEMA, POLICY_SCHEMA
from kids_policy.migrate import default_config
from kids_policy.paths import HISTORY
from kids_policy.store import write_json


def backup(path, kind):
    path = Path(path)
    if not path.is_file():
        return None
    HISTORY.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime('%Y%m%dT%H%M%S')
    try:
        data = json.loads(path.read_text())
        version = data.get('schema_version', 0) if isinstance(data, dict) else 0
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
    if data is None:
        data = {'apps': [], 'tools': ['screentime']}
    original = data
    if isinstance(data, list):
        data = {'games': data, 'videos': [], 'tools': []}
    if not isinstance(data, dict):
        raise ValueError('Allow-list must be an object or list')
    if int(data.get('schema_version', 0)) > ALLOWLIST_SCHEMA:
        raise ValueError('Allow-list is newer than this version of parental controls')
    from kids_policy.registry import identifier
    migrated = {'schema_version': ALLOWLIST_SCHEMA}
    for key, group in data.items():
        if key == 'schema_version':
            continue
        if not isinstance(group, list):
            raise ValueError('Allow-list groups must be lists')
        migrated[key] = list(dict.fromkeys(identifier(app) for app in group))
    return migrated, migrated != original


def migrate_policy(data, uid=1000):
    from kids_policy.registry import validate
    original = data
    if data is None:
        return validate(default_config(uid)), True
    if not isinstance(data, dict):
        raise ValueError('Policy must be an object')
    if int(data.get('schema_version', 0)) > POLICY_SCHEMA:
        raise ValueError('Policy is newer than this version of parental controls')
    if int(data.get('schema_version', 0)) < 4:
        from kids_policy.legacy import upgrade_policy
        data = upgrade_policy(data, uid)
    merged = {**default_config(uid), **data}
    merged['schema_version'] = POLICY_SCHEMA
    migrated = validate(merged)
    return migrated, migrated != original


def load_or_migrate(path, kind, migrator):
    path = Path(path)
    # A malformed existing file is an error, never a request for fresh defaults.
    current = json.loads(path.read_text()) if path.exists() else None
    if path.exists() and current is None:
        raise ValueError('Existing configuration cannot be null: ' + str(path))
    migrated, changed = migrator(current)
    if changed or current is None:
        if current is not None:
            backup(path, kind)
        write_json(path, migrated)
    return migrated
