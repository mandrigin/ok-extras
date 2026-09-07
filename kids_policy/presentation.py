"""Read-only UI data derived from published policy definitions."""
import datetime as dt
from kids_policy.registry import window_app as match_window


def definitions(state):
    return {key: spec for key, spec in state.get('app_definitions', {}).items() if not spec.get('control')}


def fmt(seconds):
    if seconds is None:
        return 'Unlimited'
    seconds = max(0, int(seconds))
    return f'{seconds // 60}:{seconds % 60:02d}'


def enabled_apps(config):
    from kids_policy.allowlist import enabled_ids
    return [key for key in definitions({'app_definitions': config.get('apps', {})}) if key in enabled_ids(config)]


def app_view(state, app):
    spec = definitions(state).get(app, {})
    budget = spec.get('budget')
    record = state.get('budgets', {}).get(budget, {})
    remaining = record.get('remaining_seconds') if budget else None
    permission = state.get('app_status', {}).get(app)
    if permission is None:
        permission = {'blocked': True, 'reason': 'Waiting for authoritative app permissions', 'code': 'unavailable'}
    return {**permission, 'app': app, 'label': spec.get('label', app), 'budget': budget,
            'remaining': remaining, 'unlimited': budget is None or record.get('unlimited', False)}


def fresh(state, now=None):
    try:
        updated = dt.datetime.fromisoformat(state['updated_at'])
        age = ((now or dt.datetime.now()) - updated).total_seconds()
        return -5 <= age <= 15 and not state.get('failclosed', False)
    except (KeyError, TypeError, ValueError):
        return False


def needs_schedule_approval(state, app):
    desktop = state.get('desktop', {})
    return (desktop.get('phase') == 'bedtime' or bool(desktop.get('extension_until'))
            or app_view(state, app).get('code') == 'schedule')


def window_app(window, state):
    return match_window({'apps': state.get('app_definitions', {})}, window)
