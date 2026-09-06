from kids_policy.grants import extra_seconds
from kids_policy.schedule import after_cutoff, in_play_window, minutes_until_cutoff


def empty_day(today):
    return {
        'schema_version': 2,
        'date': today,
        'shared_used_seconds': 0.0,
        'digger_used_seconds': 0.0,
        'vlc_used_seconds': 0.0,
        'micropolis_used_seconds': 0.0,
        'retro_used_seconds': 0.0,
        'apps': {},
        'grants': [],
        'failclosed': False,
        'warnings': {},
        'free_minute_used': False,
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
        vlc_limit = float(config.get('vlc_daily_minutes', 60)) * 60 + extra_seconds(self.grant_objects(), 'vlc', today)
        self.shared = Budget(self.state.get('shared_used_seconds', 0), shared_limit, mono)
        self.digger = Budget(self.state.get('digger_used_seconds', 0), digger_limit, mono)
        micropolis_limit = float(config.get('micropolis_daily_minutes', 30)) * 60 + extra_seconds(self.grant_objects(), 'micropolis', today)
        self.micropolis = Budget(self.state.get('micropolis_used_seconds', 0), micropolis_limit, mono)
        retro_limit = float(config.get('retro_daily_minutes', 30)) * 60 + extra_seconds(self.grant_objects(), 'retro', today)
        self.retro = Budget(self.state.get('retro_used_seconds', 0), retro_limit, mono)
        self.vlc = Budget(self.state.get('vlc_used_seconds', 0), vlc_limit, mono)
        self.apps = dict(self.state.get('apps', {}))

    def grant_objects(self):
        from kids_policy.grants import Grant
        return [Grant.from_dict(item) if not isinstance(item, Grant) else item for item in self.state.get('grants', [])]

    def bedtime(self, now):
        return not in_play_window(now, self.config['play_windows'])

    def burn_unused_at_bedtime(self, now):
        if not after_cutoff(now, self.config['play_windows']):
            return False
        base_shared = float(self.config['shared_daily_minutes']) * 60
        base_digger = float(self.config['digger_daily_minutes']) * 60
        base_vlc = float(self.config.get('vlc_daily_minutes', 60)) * 60
        self.shared.used = max(self.shared.used, base_shared)
        self.digger.used = max(self.digger.used, base_digger)
        self.vlc.used = max(self.vlc.used, base_vlc)
        self.micropolis.used = max(self.micropolis.used, float(self.config.get('micropolis_daily_minutes', 30)) * 60)
        self.retro.used = max(self.retro.used, float(self.config.get('retro_daily_minutes', 30)) * 60)
        return True

    def play_allowed(self, now):
        self.burn_unused_at_bedtime(now)
        if in_play_window(now, self.config['play_windows']):
            if any(self.remaining(name) > 0 for name in ('shared', 'digger', 'vlc', 'micropolis', 'retro')):
                return True, None
            return False, 'Time is up'
        if after_cutoff(now, self.config['play_windows']):
            if any(self.remaining(name) > 0 for name in ('shared', 'digger', 'vlc', 'micropolis', 'retro')):
                return True, None
            return False, 'Bedtime'
        return False, 'Too early'

    def tick(self, now, mono, running):
        self.state, reset = roll_date(self.state, str(now.date()))
        if reset:
            self.apps = {}
            self.shared.used = 0
            self.digger.used = 0
            self.vlc.used = 0
            self.micropolis.used = 0
            self.retro.used = 0
            self.retro.previous = set()
            self.micropolis.previous = set()
            self.shared.previous = set()
            self.digger.previous = set()
            self.vlc.previous = set()
            today = self.state['date']
            self.shared.limit = float(self.config['shared_daily_minutes']) * 60 + extra_seconds(self.grant_objects(), 'shared', today)
            self.digger.limit = float(self.config['digger_daily_minutes']) * 60 + extra_seconds(self.grant_objects(), 'digger', today)
            self.micropolis.limit = float(self.config.get('micropolis_daily_minutes', 30)) * 60 + extra_seconds(self.grant_objects(), 'micropolis', today)
            self.retro.limit = float(self.config.get('retro_daily_minutes', 30)) * 60 + extra_seconds(self.grant_objects(), 'retro', today)
            self.vlc.limit = float(self.config.get('vlc_daily_minutes', 60)) * 60 + extra_seconds(self.grant_objects(), 'vlc', today)
            self.state['warnings'] = {}
        evening = self.burn_unused_at_bedtime(now)
        early = self.bedtime(now) and not evening
        shared_running = set(running) & {'minecraft', 'stardew_valley'}
        digger_running = set(running) & {'digger'}
        vlc_running = set(running) & {'vlc'}
        _charged, shared_apps, _shared_out = self.shared.tick(mono, shared_running)
        _charged, digger_apps, _digger_out = self.digger.tick(mono, digger_running)
        _charged, vlc_apps, _vlc_out = self.vlc.tick(mono, vlc_running)
        _charged, micropolis_apps, _out = self.micropolis.tick(mono, set(running) & {'micropolis'})
        _charged, retro_apps, _out = self.retro.tick(mono, set(running) & {'retro'})
        for app, value in {**shared_apps, **digger_apps, **vlc_apps, **micropolis_apps, **retro_apps}.items():
            self.apps[app] = self.apps.get(app, 0) + value
        blocked = set()
        reasons = []
        if self.remaining('shared') <= 0:
            blocked.update({'minecraft', 'stardew_valley'})
            reasons.append('Minecraft + Stardew daily limit reached')
        if self.remaining('digger') <= 0:
            blocked.add('digger')
            reasons.append('Digger daily limit reached')
        if self.remaining('vlc') <= 0:
            blocked.add('vlc')
            reasons.append('Videos daily limit reached')
        if self.remaining('micropolis') <= 0:
            blocked.add('micropolis')
            reasons.append('Micropolis daily limit reached')
        if self.remaining('retro') <= 0:
            blocked.add('retro')
            reasons.append('Retro games daily limit reached')
        if early:
            blocked.update({'digger', 'minecraft', 'stardew_valley', 'vlc', 'micropolis', 'retro'})
            reasons.append('Too early')
        if evening and all(self.remaining(name) <= 0 for name in ('shared', 'digger', 'vlc', 'micropolis', 'retro')):
            reasons.append('Bedtime')
        return blocked, reasons

    def remaining(self, name):
        budgets = {'shared': self.shared, 'digger': self.digger, 'vlc': self.vlc, 'micropolis': self.micropolis, 'retro': self.retro}
        budget = budgets[name]
        return max(0.0, budget.limit - budget.used)

    def snapshot(self, now):
        allowed, reason = self.play_allowed(now)
        grants = [grant.to_dict() if hasattr(grant, 'to_dict') else grant for grant in self.grant_objects()]
        bedtime = self.bedtime(now)
        return {
            'schema_version': 2,
            'date': self.state['date'],
            'apps': dict(self.apps),
            'categories': {
                'games': self.shared.used + self.digger.used + self.micropolis.used + self.retro.used,
                'videos': self.vlc.used,
            },
            'shared_used_seconds': self.shared.used,
            'digger_used_seconds': self.digger.used,
            'vlc_used_seconds': self.vlc.used,
            'micropolis_used_seconds': self.micropolis.used,
            'retro_used_seconds': self.retro.used,
            'retro_daily_limit_minutes': self.retro.limit / 60,
            'retro_remaining_seconds': self.remaining('retro'),
            'micropolis_daily_limit_minutes': self.micropolis.limit / 60,
            'micropolis_remaining_seconds': self.remaining('micropolis'),
            'daily_limit_minutes': self.shared.limit / 60,
            'digger_daily_limit_minutes': self.digger.limit / 60,
            'vlc_daily_limit_minutes': self.vlc.limit / 60,
            'remaining_seconds': self.remaining('shared'),
            'digger_remaining_seconds': self.remaining('digger'),
            'vlc_remaining_seconds': self.remaining('vlc'),
            'play_allowed': allowed,
            'play_blocked_reason': reason,
            'bedtime': bedtime,
            'minutes_until_cutoff': 0 if bedtime else minutes_until_cutoff(now, self.config['play_windows']),
            'grants': grants,
            'schedule_override': None,
            'warnings': dict(self.state.get('warnings', {})),
            'failclosed': bool(self.state.get('failclosed', False)),
            'free_minute_used': bool(self.state.get('free_minute_used')),
            'free_minute_available': not bool(self.state.get('free_minute_used')),
            'extra_minute_tiers': list(self.config.get('extra_minute_tiers') or [15, 30, 60]),
        }

    def apply_snapshot_usage(self):
        self.state['shared_used_seconds'] = self.shared.used
        self.state['digger_used_seconds'] = self.digger.used
        self.state['vlc_used_seconds'] = self.vlc.used
        self.state['micropolis_used_seconds'] = self.micropolis.used
        self.state['retro_used_seconds'] = self.retro.used
        self.state['apps'] = dict(self.apps)
        return self.state
