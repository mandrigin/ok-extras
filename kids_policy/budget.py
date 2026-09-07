"""Account for configurable allowance groups; apps are registry entries."""
import math
from kids_policy.grants import extra_seconds
from kids_policy.schedule import after_cutoff, in_play_window, minutes_until_cutoff


def empty_day(today):
    return {'schema_version': 3, 'date': today, 'budgets_used_seconds': {}, 'apps': {},
            'grants': [], 'failclosed': False, 'warnings': {}, 'free_minute_used': False}


def roll_date(state, today):
    stored = state.get('date')
    if stored is None or today > stored:
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
        if charged:
            per_app = {app: charged / len(active) for app in active}
            self.used += charged
        self.previous = set(running)
        return charged, per_app, self.used >= self.limit


class Policy:
    def __init__(self, state, config, now, mono):
        from kids_policy.migrate import migrate_state
        self.state, _ = roll_date(migrate_state(state), str(now.date()))
        self.apps = dict(self.state.get('apps', {}))
        self.budgets = {}
        self.mono = mono
        self.configure(config)

    def __getattr__(self, name):
        # Attribute access remains usable for older integrations, without a fixed catalogue.
        if name in self.__dict__.get('budgets', {}):
            return self.budgets[name]
        raise AttributeError(name)

    def configure(self, config):
        from kids_policy.configver import migrate_policy
        from kids_policy.registry import managed_apps
        updated, _ = migrate_policy(config)
        # Retain usage even if a group is removed and later re-added today.
        saved = self.state.setdefault('budgets_used_seconds', {})
        for name, budget in self.budgets.items():
            saved[name] = budget.used
        for name in list(self.budgets):
            if name not in updated['budgets']:
                del self.budgets[name]
        old_apps = self.config.get('apps', {}) if hasattr(self, 'config') else {}
        for name, spec in updated['budgets'].items():
            value = spec.get('daily_minutes')
            limit = math.inf if value is None else value * 60 + extra_seconds(self.grant_objects(), name, self.state['date'])
            if name not in self.budgets:
                self.budgets[name] = Budget(saved.get(name, 0), limit, self.mono)
            self.budgets[name].limit = limit
            self.budgets[name].previous = {app for app in self.budgets[name].previous
                if app in updated['apps'] and updated['apps'][app].get('budget') == old_apps.get(app, {}).get('budget')}
        self.config = updated
        self.managed = managed_apps(updated)

    def grant_objects(self):
        from kids_policy.grants import Grant
        return [Grant.from_dict(item) if not isinstance(item, Grant) else item for item in self.state.get('grants', [])]

    def bedtime(self, now):
        return not in_play_window(now, self.config['play_windows'])

    def play_allowed(self, now):
        if getattr(self, 'schedule_extension_until', 0) > now.timestamp() or not self.bedtime(now):
            return True, None
        return False, 'Bedtime' if after_cutoff(now, self.config['play_windows']) else 'Too early'

    def tick(self, now, mono, running):
        self.mono = mono
        self.state, reset = roll_date(self.state, str(now.date()))
        if reset:
            self.apps = {}
            self.budgets = {}
            self.unlimited_previous, self.unlimited_last = set(), mono
            self.configure(self.config)
        allowed, reason = self.play_allowed(now)
        from kids_policy.allowlist import enabled_ids
        enabled = set(enabled_ids(self.config))
        eligible = {app for app in running if app in enabled and app in self.managed
                    and (allowed or not self.managed[app].get('schedule', True))}
        for name, budget in self.budgets.items():
            members = {app for app in eligible if self.managed[app].get('budget') == name}
            _, per_app, _ = budget.tick(mono, members)
            for app, seconds in per_app.items():
                self.apps[app] = self.apps.get(app, 0) + seconds
        # Apps with no allowance are unlimited, but still honor the schedule and allow-list.
        unlimited = {app for app in eligible if self.managed[app].get('budget') is None}
        previous = getattr(self, 'unlimited_previous', set())
        elapsed = max(0, mono - getattr(self, 'unlimited_last', mono))
        for app in previous & unlimited:
            self.apps[app] = self.apps.get(app, 0) + elapsed
        self.unlimited_previous, self.unlimited_last = unlimited, mono
        blocked, reasons = set(), []
        for app, spec in self.managed.items():
            budget = spec.get('budget')
            if app not in enabled:
                blocked.add(app)
            elif spec.get('schedule', True) and not allowed:
                blocked.add(app)
                reasons.append(reason)
            elif budget is not None and self.remaining(budget) <= 0:
                blocked.add(app)
                reasons.append(self.config['budgets'][budget]['label'] + ' daily limit reached')
        return blocked, list(dict.fromkeys(reasons))

    def remaining(self, name):
        if name is None:
            return math.inf
        budget = self.budgets[name]
        return max(0.0, budget.limit - budget.used)

    def snapshot(self, now):
        allowed, reason = self.play_allowed(now)
        records = {}
        for name, budget in self.budgets.items():
            records[name] = {'label': self.config['budgets'][name]['label'], 'used_seconds': budget.used,
                'remaining_seconds': self.remaining(name) if math.isfinite(budget.limit) else None,
                'daily_limit_minutes': budget.limit / 60 if math.isfinite(budget.limit) else None,
                'unlimited': not math.isfinite(budget.limit)}
        categories = {}
        for app, seconds in self.apps.items():
            group = self.config['apps'].get(app, {}).get('category', 'apps')
            categories[group] = categories.get(group, 0) + seconds
        snap = {'schema_version': 3, 'date': self.state['date'], 'apps': dict(self.apps),
            'budgets': records, 'app_definitions': {name: {**{key: spec[key] for key in
                ('label', 'budget', 'category', 'icon', 'window', 'control', 'schedule') if key in spec},
                'match': {'windows': spec.get('match', {}).get('windows', [])}}
                for name, spec in self.config['apps'].items()}, 'categories': categories,
            'play_allowed': allowed, 'play_blocked_reason': reason, 'bedtime': self.bedtime(now),
            'minutes_until_cutoff': 0 if self.bedtime(now) else minutes_until_cutoff(now, self.config['play_windows']),
            'grants': [grant.to_dict() for grant in self.grant_objects()], 'schedule_override': None,
            'warnings': dict(self.state.get('warnings', {})), 'failclosed': bool(self.state.get('failclosed', False)),
            'free_minute_used': bool(self.state.get('free_minute_used')),
            'free_minute_available': not bool(self.state.get('free_minute_used')),
            'extra_minute_tiers': self.config['extra_minute_tiers']}
        # Version-3 migration can retain fields for existing remote scripts.
        for name, spec in self.config['budgets'].items():
            for kind, field in spec.get('legacy_fields', {}).items():
                if field in snap:
                    continue
                snap[field] = records[name][{'used': 'used_seconds', 'remaining': 'remaining_seconds', 'limit': 'daily_limit_minutes'}[kind]]
        return snap

    def apply_snapshot_usage(self):
        self.state.setdefault('budgets_used_seconds', {}).update({name: value.used for name, value in self.budgets.items()})
        self.state['apps'] = dict(self.apps)
        return self.state
