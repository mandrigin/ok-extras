"""Validated app and budget definitions. No application catalogue belongs here."""
import copy
import math
import re
from pathlib import Path

ID = re.compile(r'^[a-z][a-z0-9_-]{0,63}$')


def identifier(value):
    if not isinstance(value, str) or not ID.fullmatch(value) or value == 'all':
        raise ValueError('Invalid app or budget ID: ' + str(value))
    return value


def text_value(value):
    return isinstance(value, str) and bool(value.strip()) and not any(c in value for c in '\0\r\n')


def validate(config):
    if not isinstance(config, dict):
        raise ValueError('Policy must be an object')
    data = copy.deepcopy(config)
    if type(data.get('child_uid')) is not int or data['child_uid'] < 1000:
        raise ValueError('Choose a non-system child account (UID >= 1000)')
    if not isinstance(data.get('network'), dict) or data['network'].get('mode') not in ('unchanged', 'offline'):
        raise ValueError('network.mode must be unchanged or offline')
    for key in ('apps', 'budgets'):
        if not isinstance(data.get(key), dict):
            raise ValueError(key + ' must be an object')
    for key, maximum in (('warnings_minutes', None), ('extra_minute_tiers', 60)):
        values = data.get(key, [])
        if not isinstance(values, list) or any(type(v) is not int or v <= 0 or (maximum and v > maximum) for v in values):
            raise ValueError(key + ' must contain positive whole minutes' + (' up to 60' if maximum else ''))
    if not isinstance(data.get('extensions', []), list):
        raise ValueError('extensions must be a list')
    for name in data.get('extensions', []):
        identifier(name)
    for name, spec in data['budgets'].items():
        identifier(name)
        if not isinstance(spec, dict):
            raise ValueError('Invalid budget definition')
        limit = spec.get('daily_minutes')
        if limit is not None and (type(limit) not in (int, float) or not math.isfinite(limit) or limit < 0):
            raise ValueError('daily_minutes must be nonnegative or null for unlimited')
        spec.setdefault('label', name)
        if not text_value(spec['label']):
            raise ValueError(name + ': invalid budget label')
        fields = spec.get('legacy_fields', {})
        if not isinstance(fields, dict) or set(fields) - {'used', 'remaining', 'limit'} or any(not text_value(v) for v in fields.values()):
            raise ValueError(name + ': invalid legacy fields')
    for name, spec in data['apps'].items():
        identifier(name)
        if not isinstance(spec, dict):
            raise ValueError('Invalid app definition')
        argv = spec.get('argv')
        if (not isinstance(argv, list) or not argv or not all(isinstance(arg, str) and '\0' not in arg for arg in argv)
                or not Path(argv[0]).is_absolute()):
            raise ValueError(name + ': argv must start with an absolute executable path')
        environment = spec.get('env', {})
        if not isinstance(environment, dict) or any(not isinstance(key, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', key) or not isinstance(value, str) or '\0' in value for key, value in environment.items()):
            raise ValueError(name + ': invalid environment')
        budget = spec.get('budget')
        if budget is not None and (not isinstance(budget, str) or budget not in data['budgets']):
            raise ValueError(name + ': unknown budget ' + str(budget))
        spec.setdefault('label', name)
        spec.setdefault('desktop', name + '.desktop')
        spec.setdefault('icon', 'application-x-executable')
        spec.setdefault('category', 'apps')
        spec.setdefault('schedule', True)
        spec.setdefault('budget', None)
        for key in ('label', 'desktop', 'icon', 'category'):
            if not text_value(spec[key]):
                raise ValueError(name + ': invalid ' + key)
        if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]*\.desktop', spec['desktop']):
            raise ValueError(name + ': invalid desktop filename')
        categories = spec.get('desktop_categories', ['Utility'])
        if not isinstance(categories, list) or any(not text_value(v) for v in categories):
            raise ValueError(name + ': invalid desktop categories')
        for key in ('control', 'schedule'):
            if key in spec and type(spec[key]) is not bool:
                raise ValueError(name + ': ' + key + ' must be boolean')
        match = spec.setdefault('match', {})
        if not isinstance(match, dict) or not isinstance(match.get('process', []), list):
            raise ValueError(name + ': invalid matching rules')
        for key in ('windows',):
            values = match.get(key, [])
            if not isinstance(values, list) or any(not isinstance(v, str) or not v.strip() for v in values):
                raise ValueError(name + ': invalid window match')
        for rule in match.get('process', []):
            if not isinstance(rule, dict) or not rule or set(rule) - {'names', 'executables', 'command_contains'}:
                raise ValueError(name + ': invalid process match')
            for values in rule.values():
                if not isinstance(values, list) or not values or any(not isinstance(v, str) or not v.strip() for v in values):
                    raise ValueError(name + ': empty process match')
        if not spec.get('control') and not match.get('process'):
            raise ValueError(name + ': process matching is required for enforcement')
        if not match.get('windows'):
            raise ValueError(name + ': window matching is required for the allow-list')
        if spec.get('control') and name != 'screentime':
            raise ValueError('Only the built-in Screen Time UI can be a control app')
        window = spec.get('window')
        if window is not None:
            if not isinstance(window, dict):
                raise ValueError(name + ': invalid window geometry')
            for key in ('width', 'height', 'scale'):
                value = window.get(key)
                if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                    raise ValueError(name + ': invalid window geometry')
    from kids_policy.schedule import parse_hhmm
    if not isinstance(data.get('play_windows'), dict):
        raise ValueError('play_windows must be an object')
    for key in ('weekday', 'weekend'):
        window = data['play_windows'].get(key)
        if not isinstance(window, dict) or not {'start', 'end'} <= window.keys():
            raise ValueError('play_windows requires weekday/weekend start and end')
        parse_hhmm(window['start'])
        parse_hhmm(window['end'])
    return data


def managed_apps(config):
    return {key: spec for key, spec in config.get('apps', {}).items() if not spec.get('control')}


def process_matches(rule, name, executable, command, cwd):
    names = rule.get('names', [])
    executables = rule.get('executables', [])
    identity = (name.lower() in [v.lower() for v in names] or
                any(executable.lower() == v.lower() if '/' in v else Path(executable).name.lower() == v.lower()
                    for v in executables)) if names or executables else True
    evidence = (command + ' ' + cwd).lower()
    contains = rule.get('command_contains', [])
    return identity and (not contains or any(value.lower() in evidence for value in contains))


def classify(config, name, executable='', command='', cwd=''):
    matches = [app for app, spec in managed_apps(config).items()
               if any(process_matches(rule, name, executable, command, cwd)
                      for rule in spec.get('match', {}).get('process', []))]
    # Overlapping definitions are a configuration error; never silently select a budget.
    if len(matches) > 1:
        raise ValueError('Ambiguous process match: ' + ', '.join(matches))
    return next(iter(matches), None)


def window_app(config, window):
    blob = f"{window.get('class', '')} {window.get('title', '')}".lower()
    for name, spec in config.get('apps', {}).items():
        if spec.get('control') and any(v.lower() in blob for v in spec.get('match', {}).get('windows', [])):
            return None
    return next((name for name, spec in managed_apps(config).items()
                 if any(v.lower() in blob for v in spec.get('match', {}).get('windows', []))), None)
