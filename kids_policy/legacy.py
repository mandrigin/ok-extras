SCHEMA_VERSION = 2
from kids_policy.budget import empty_day


def migrate_state(saved):
    if not saved:
        return empty_day(None)
    if saved.get('schema_version') == SCHEMA_VERSION:
        state = dict(saved)
        state.setdefault('grants', [])
        state.setdefault('warnings', {})
        state.setdefault('failclosed', False)
        state.setdefault('free_minute_used', False)
        state.setdefault('apps', {})
        state.setdefault('shared_used_seconds', saved.get('shared_used_seconds', 0))
        state.setdefault('digger_used_seconds', saved.get('digger_used_seconds', 0))
        return state
    today = saved.get('date')
    state = empty_day(today)
    state['shared_used_seconds'] = float(saved.get('shared_used_seconds', saved.get('categories', {}).get('games', 0)))
    if 'digger_used_seconds' in saved:
        state['digger_used_seconds'] = float(saved['digger_used_seconds'])
        state['shared_used_seconds'] = float(saved.get('shared_used_seconds', 0))
    else:
        apps = saved.get('apps', {})
        state['digger_used_seconds'] = float(apps.get('digger', 0))
        state['shared_used_seconds'] = float(sum(value for key, value in apps.items() if key != 'digger') or saved.get('categories', {}).get('games', 0))
    state['apps'] = dict(saved.get('apps', {}))
    state['schema_version'] = SCHEMA_VERSION
    return state


def legacy_config(uid=1000):
    import json
    from pathlib import Path
    data = json.loads(Path(__file__).with_name('legacy-v3.json').read_text())
    data['child_uid'] = int(uid)
    return data


def upgrade_policy(data, uid):
    import json
    from pathlib import Path
    base = legacy_config(uid)
    base.update({key: value for key, value in data.items() if key != 'apps'})
    definitions = json.loads(Path(__file__).with_name('legacy-apps.json').read_text())
    for app, spec in data.get('apps', {}).items():
        definitions[app] = {**definitions.get(app, {}), **spec}
    # Legacy VLC used a null budget in metadata despite a separate enforced allowance.
    definitions['vlc']['budget'] = 'vlc'
    if 'window_scale' in definitions['digger']:
        definitions['digger']['window']['scale'] = definitions['digger'].pop('window_scale')
    base['apps'] = definitions
    base['budgets'] = {}
    labels = {'shared': 'Games', 'digger': 'Digger', 'vlc': 'Videos',
              'micropolis': 'Micropolis', 'retro': 'Retro games'}
    for name, label in labels.items():
        base['budgets'][name] = {'label': label, 'daily_minutes': base.pop(name + '_daily_minutes'),
            'legacy_fields': {'used': name + '_used_seconds',
                              'remaining': 'remaining_seconds' if name == 'shared' else name + '_remaining_seconds',
                              'limit': 'daily_limit_minutes' if name == 'shared' else name + '_daily_limit_minutes'}}
    base['network'] = {'mode': 'offline'}
    base['extensions'] = ['offline-video', 'retro']
    base['schema_version'] = 4
    data = base
    return data
