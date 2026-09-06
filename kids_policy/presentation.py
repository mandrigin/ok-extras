"""Shared, read-only view of app allowances; never authorizes a launch."""
import datetime as dt

APPS = {
    'digger': ('Digger', 'digger', 'digger_remaining_seconds'),
    'micropolis': ('Micropolis', 'micropolis', 'micropolis_remaining_seconds'),
    'retro': ('Retro games', 'retro', 'retro_remaining_seconds'),
    'minecraft': ('Minecraft', 'shared', 'remaining_seconds'),
    'stardew_valley': ('Stardew Valley', 'shared', 'remaining_seconds'),
    'vlc': ('Videos', 'vlc', 'vlc_remaining_seconds'),
}


def fmt(seconds):
    seconds = max(0, int(seconds or 0))
    return f'{seconds // 60}:{seconds % 60:02d}'


def enabled_apps(config):
    allow = config.get('allowlist', config)
    return [app for app in APPS if any(app in allow.get(group, []) for group in ('games', 'videos'))]


def app_view(state, app):
    label, budget, field = APPS[app]
    authoritative = state.get('app_status', {}).get(app)
    remaining = max(0, float(state.get(field) or 0))
    if authoritative is not None:
        return {**authoritative, 'app': app, 'label': label, 'budget': budget, 'remaining': remaining}
    blocked = remaining <= 0 or not state.get('play_allowed', False)
    return {'app': app, 'label': label, 'budget': budget, 'remaining': remaining,
            'blocked': blocked, 'reason': state.get('play_blocked_reason') or f'{label} daily limit reached'}


def fresh(state, now=None):
    try:
        updated = dt.datetime.fromisoformat(state['updated_at'])
        age = ((now or dt.datetime.now()) - updated).total_seconds()
        return -5 <= age <= 15 and not state.get('failclosed', False)
    except (KeyError, TypeError, ValueError):
        return False


def window_app(window):
    blob = f"{window.get('class', '')} {window.get('title', '')}".lower()
    if 'omarchy' in blob or 'kids-' in blob:
        return None
    for app, markers in (
        ('digger', ('digger', 'd i g g e r')),
        ('micropolis', ('micropolis',)),
        ('retro', ('retroarch',)),
        ('minecraft', ('minecraft', 'prism')),
        ('stardew_valley', ('stardew', 'steam_app_413150')),
        ('vlc', ('vlc', 'kids videos')),
    ):
        if any(marker in blob for marker in markers):
            return app
    return None
