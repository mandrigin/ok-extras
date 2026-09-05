from kids_policy.grants import active_override, extra_seconds
from kids_policy.schedule import in_play_window, minutes_until_cutoff


def empty_day(today):
    return {
        'schema_version': 2,
        'date': today,
        'shared_used_seconds': 0.0,
        'digger_used_seconds': 0.0,
        'apps': {},
        'grants': [],
        'failclosed': False,
        'warnings': {},
    }


def roll_date(state, today):
    stored = state.get('date')
    if stored is None:
        reset = empty_day(today)
        reset['grants'] = []
        return reset, True
    if today < stored:
        return state, False
    if today > stored:
        reset = empty_day(today)
        reset['grants'] = [grant for grant in state.get('grants', []) if grant.get('date') == today]
        return reset, True
    return state, False


class Budget:
    def __init__(self, used, limit, mono):
        self.used = float(used)
        self.limit = float(limit)
        self.last = mono
        self.previous = set()

    def tick(self, mono, running):
        elapsed = max(0.0, mono - self.last)
        self.last = mono
        active = self.previous & set(running)
        remaining = max(0.0, self.limit - self.used)
        charged = min(elapsed, remaining) if active else 0.0
        per_app = {}
        if charged and active:
            share = charged / len(active)
            per_app = {app: share for app in active}
            self.used += charged
        self.previous = set(running)
        return charged, per_app, self.used >= self.limit and self.limit >= 0


class Policy:
    def __init__(self, state, config, now, mono):
        self.config = config
        self.state, _reset = roll_date(state, str(now.date()))
        today = self.state['date']
        grants = self.state.get('grants', [])
        shared_limit = float(config['shared_daily_minutes']) * 60 + extra_seconds(self.grant_objects(), 'shared', today)
        digger_limit = float(config['digger_daily_minutes']) * 60 + extra_seconds(self.grant_objects(), 'digger', today)
        self.shared = Budget(self.state.get('shared_used_seconds', 0), shared_limit, mono)
        self.digger = Budget(self.state.get('digger_used_seconds', 0), digger_limit, mono)
        self.apps = dict(self.state.get('apps', {}))

    def grant_objects(self):
        from kids_policy.grants import Grant
        return [Grant.from_dict(item) if not isinstance(item, Grant) else item for item in self.state.get('grants', [])]

    def play_allowed(self, now):
        grants = self.grant_objects()
        if active_override(grants, now):
            return True, None
        if in_play_window(now, self.config['play_windows']):
            return True, None
        return False, 'Play window closed'

    def tick(self, now, mono, running):
        self.state, reset = roll_date(self.state, str(now.date()))
        if reset:
            self.apps = {}
            self.shared.used = 0
            self.digger.used = 0
            self.shared.previous = set()
            self.digger.previous = set()
            today = self.state['date']
            self.shared.limit = float(self.config['shared_daily_minutes']) * 60 + extra_seconds(self.grant_objects(), 'shared', today)
            self.digger.limit = float(self.config['digger_daily_minutes']) * 60 + extra_seconds(self.grant_objects(), 'digger', today)
            self.state['warnings'] = {}
        allowed, reason = self.play_allowed(now)
        shared_running = set(running) & {'minecraft', 'stardew_valley'}
        digger_running = set(running) & {'digger'}
        chargeable_shared = shared_running if allowed else set()
        chargeable_digger = digger_running if allowed else set()
        _charged, shared_apps, shared_out = self.shared.tick(mono, chargeable_shared)
        _charged, digger_apps, digger_out = self.digger.tick(mono, chargeable_digger)
        for app, value in {**shared_apps, **digger_apps}.items():
            self.apps[app] = self.apps.get(app, 0) + value
        blocked = set()
        reasons = []
        if not allowed:
            blocked.update({'digger', 'minecraft', 'stardew_valley', 'vlc'})
            reasons.append(reason)
        if shared_out:
            blocked.update({'minecraft', 'stardew_valley'})
            reasons.append('Minecraft + Stardew daily limit reached')
        if digger_out:
            blocked.add('digger')
            reasons.append('Digger daily limit reached')
        return blocked, reasons

    def remaining(self, name):
        budget = self.shared if name == 'shared' else self.digger
        return max(0.0, budget.limit - budget.used)

    def snapshot(self, now):
        allowed, reason = self.play_allowed(now)
        grants = [grant.to_dict() if hasattr(grant, 'to_dict') else grant for grant in self.grant_objects()]
        override = active_override(self.grant_objects(), now)
        return {
            'schema_version': 2,
            'date': self.state['date'],
            'apps': dict(self.apps),
            'categories': {'games': self.shared.used + self.digger.used},
            'shared_used_seconds': self.shared.used,
            'digger_used_seconds': self.digger.used,
            'daily_limit_minutes': self.shared.limit / 60,
            'digger_daily_limit_minutes': self.digger.limit / 60,
            'remaining_seconds': self.remaining('shared'),
            'digger_remaining_seconds': self.remaining('digger'),
            'play_allowed': allowed,
            'play_blocked_reason': reason,
            'minutes_until_cutoff': minutes_until_cutoff(now, self.config['play_windows']) if allowed and not override else 0,
            'grants': grants,
            'schedule_override': override.to_dict() if override else None,
            'warnings': dict(self.state.get('warnings', {})),
            'failclosed': bool(self.state.get('failclosed', False)),
        }

    def apply_snapshot_usage(self):
        self.state['shared_used_seconds'] = self.shared.used
        self.state['digger_used_seconds'] = self.digger.used
        self.state['apps'] = dict(self.apps)
        return self.state
