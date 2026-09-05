from kids_policy import SCHEMA_VERSION
from kids_policy.budget import empty_day


def migrate_state(saved):
    if not saved:
        return empty_day(None)
    if saved.get('schema_version') == SCHEMA_VERSION:
        state = dict(saved)
        state.setdefault('grants', [])
        state.setdefault('warnings', {})
        state.setdefault('failclosed', False)
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


def default_config(uid=1000):
    return {
        'schema_version': SCHEMA_VERSION,
        'child_uid': int(uid),
        'parent_user': 'parent',
        'shared_daily_minutes': 60,
        'digger_daily_minutes': 10,
        'play_windows': {
            'weekday': {'start': '09:00', 'end': '21:00'},
            'weekend': {'start': '08:00', 'end': '21:00'},
        },
        'warnings_minutes': [5, 1],
        'apps': {
            'digger': {
                'label': 'Digger',
                'budget': 'digger',
                'schedule': True,
                'argv': ['/usr/local/bin/digger'],
            },
            'minecraft': {
                'label': 'Minecraft',
                'budget': 'shared',
                'schedule': True,
                'argv': ['/usr/local/bin/minecraft-vm'],
            },
            'stardew_valley': {
                'label': 'Stardew Valley',
                'budget': 'shared',
                'schedule': True,
                'argv': ['/usr/bin/steam', 'steam://rungameid/413150'],
            },
            'vlc': {
                'label': 'Kids Videos',
                'budget': None,
                'schedule': True,
                'argv': ['/usr/bin/vlc', '--no-network', '/srv/kids-media/videos/kids-videos.m3u'],
            },
        },
    }
