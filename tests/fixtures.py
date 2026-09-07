"""Explicit legacy household fixture; product defaults intentionally contain no games."""
import json
from pathlib import Path
from kids_policy.legacy import legacy_config
from kids_policy.registry import classify as match_process, window_app as match_window


def default_config(uid=1000):
    config = legacy_config(uid)
    config['schema_version'] = 3
    config['apps'] = json.loads((Path(__file__).resolve().parents[1] / 'kids_policy/legacy-apps.json').read_text())
    config['allowlist']['games'] += ['micropolis', 'retro']
    return config


def classify(name, executable='', command='', cwd=''):
    return match_process(default_config(), name, executable, command, cwd)


def window_app(window):
    return match_window(default_config(), window)
