"""Empty product defaults and versioned migration entry points."""
from kids_policy import SCHEMA_VERSION


def default_config(uid=1000):
    return {
        'schema_version': 4, 'child_uid': int(uid), 'parent_user': 'parent',
        'budgets': {}, 'apps': {
            'screentime': {
                'label': 'Screen Time', 'desktop': 'omarchy-kids-screentime.desktop',
                'icon': 'preferences-system-time', 'category': 'tools',
                'control': True, 'schedule': False, 'budget': None,
                'argv': ['/usr/bin/omarchy-kids-ui'],
                'launcher_argv': ['/usr/bin/omarchy-kids-ui'],
                'match': {'windows': ['omarchy kids', 'omarchy-kids-screentime', 'omarchy-kids-hud', 'omarchy-kids-block']},
            },
        },
        'allowlist': {'apps': [], 'tools': ['screentime']},
        'play_windows': {key: {'start': '00:00', 'end': '00:00'} for key in ('weekday', 'weekend')},
        'warnings_minutes': [5, 1], 'extra_minute_tiers': [15, 30, 60],
        'network': {'mode': 'unchanged'}, 'extensions': [],
    }


def migrate_state(saved):
    from kids_policy.budget import empty_day
    if not saved:
        return empty_day(None)
    state = dict(saved)
    if state.get('schema_version', 0) < 3:
        from kids_policy.legacy import migrate_state as old_state
        state = old_state(state)
        state['budgets_used_seconds'] = {key[:-13]: value for key, value in state.items()
                                         if key.endswith('_used_seconds')}
    state['schema_version'] = 3
    state.setdefault('budgets_used_seconds', {})
    state.setdefault('apps', {})
    state.setdefault('grants', [])
    state.setdefault('warnings', {})
    state.setdefault('free_minute_used', False)
    return state
