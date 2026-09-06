from pathlib import Path

SHARED_GAMES = ('minecraft', 'stardew_valley')
GAMES = ('digger', 'minecraft', 'stardew_valley', 'micropolis')
SCHEDULED = ('digger', 'minecraft', 'stardew_valley', 'vlc', 'micropolis')
BUDGET_FOR = {
    'digger': 'digger',
    'micropolis': 'micropolis',
    'minecraft': 'shared',
    'stardew_valley': 'shared',
    'vlc': None,
}


def classify(name, executable='', command='', cwd=''):
    name = name.lower()
    executable = Path(executable).name.lower()
    command = command.lower()
    cwd = cwd.lower()
    if name == 'micropolis' or executable == 'micropolis':
        return 'micropolis'
    if name == 'digger' or executable == 'digger':
        return 'digger'
    if name in {'stardew valley', 'stardewvalley', 'stardewmoddingap'} or executable in {
        'stardew valley', 'stardewvalley', 'stardewmoddingapi',
    }:
        return 'stardew_valley'
    if name in {'vlc', 'vlc-wrapper'} or executable in {'vlc', 'vlc-wrapper'}:
        return 'vlc'
    if name in {'java', 'javaw'} or executable in {'java', 'javaw'}:
        evidence = f'{command} {cwd}'
        if 'micropolis' in evidence:
            return 'micropolis'
        if any(marker in evidence for marker in ('minecraft', 'prismlauncher', 'multimc')):
            return 'minecraft'
    return None
