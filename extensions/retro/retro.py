"""Optional ROM library extension. Games and cores are configuration, not policy."""
import json
import os
from pathlib import Path
import shutil
import tempfile

CONFIG = Path('/etc/omarchy-kids/extensions/retro.json')
LIBRARY = Path('/srv/kids-media/roms')


def settings():
    path = CONFIG if CONFIG.exists() else Path(__file__).with_name('catalog.json')
    return json.loads(path.read_text())


def core_for(path, config, selected=None):
    choices = [name for name, spec in config['cores'].items() if path.suffix.lower() in spec['extensions']]
    if selected is not None:
        if selected not in choices:
            raise ValueError('Selected core does not support this file extension')
        return selected
    if len(choices) != 1:
        raise ValueError('Choose a configured core for this file extension')
    return choices[0]


def refresh_playlist(library=LIBRARY):
    config = settings()
    metadata = library / '.games.json'
    records = json.loads(metadata.read_text()) if metadata.exists() else {}
    items = []
    for source in sorted(library.iterdir()):
        if not source.is_file() or source.name.startswith('.'):
            continue
        record = records.get(source.name, {})
        try:
            core = core_for(source, config, record.get('core'))
        except ValueError:
            continue
        spec = config['cores'][core]
        items.append({'path': str(source), 'label': record.get('title', source.stem.replace('_', ' ').title()),
                      'core_path': spec.get('path', f'/usr/lib/libretro/{core}_libretro.so'),
                      'core_name': spec['label'], 'crc32': '00000000|crc', 'db_name': ''})
    directory = library / 'playlists'
    directory.mkdir(exist_ok=True, mode=0o755)
    data = {'version': '1.5', 'default_core_path': '', 'default_core_name': '',
            'label_display_mode': 0, 'right_thumbnail_mode': 0, 'left_thumbnail_mode': 0,
            'sort_mode': 0, 'items': items}
    write(directory / 'Retro Games.lpl', data)
    return items


def write(path, data):
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.retro-')
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(data, stream, indent=2)
            stream.write('\n')
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def import_rom(game, source, library=LIBRARY, core=None, title=None):
    import re
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,80}', game):
        raise ValueError('Use a simple game ID containing letters, digits, hyphens or underscores')
    source = Path(source)
    config = settings()
    if not source.is_file():
        raise ValueError('Provide an extracted ROM file')
    core = core_for(source, config, core)
    if not 16 <= source.stat().st_size <= config.get('max_bytes', 512 * 1024 * 1024):
        raise ValueError('Unexpected ROM size')
    if source.suffix.lower() == '.nes':
        with source.open('rb') as stream:
            if stream.read(4) != b'NES\x1a':
                raise ValueError('Not an iNES/NES 2.0 ROM')
    if any(path.stem == game for path in library.iterdir() if path.is_file()):
        raise ValueError('This game is already imported; existing ROM and saves were kept')
    destination = library / (game + source.suffix.lower())
    fd, temporary = tempfile.mkstemp(dir=library, prefix='.rom-')
    os.close(fd)
    try:
        shutil.copyfile(source, temporary)
        os.chmod(temporary, 0o644)
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)
    metadata = library / '.games.json'
    records = json.loads(metadata.read_text()) if metadata.exists() else {}
    records[destination.name] = {'core': core, 'title': title or game.replace('_', ' ').title()}
    write(metadata, records)
    refresh_playlist(library)
    return destination
