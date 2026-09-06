"""Curated ROM import and RetroArch playlist; game files are supplied separately."""
import json
import os
from pathlib import Path
import shutil
import tempfile

LIBRARY = Path('/srv/kids-media/roms')
GAMES = {
    'lion_king': ('The Lion King', 'genesis_plus_gx', ('.md', '.gen', '.bin', '.smd')),
    'aladdin': ('Aladdin', 'genesis_plus_gx', ('.md', '.gen', '.bin', '.smd')),
    'super_mario_bros': ('Super Mario Bros.', 'nestopia', ('.nes',)),
    'theme_park': ('Theme Park', 'genesis_plus_gx', ('.md', '.gen', '.bin', '.smd')),
}


def refresh_playlist(library=LIBRARY):
    items = []
    for game, (label, core, extensions) in GAMES.items():
        source = next((library / (game + ext) for ext in extensions if (library / (game + ext)).is_file()), None)
        if source:
            items.append({'path': str(source), 'label': label,
                          'core_path': f'/usr/lib/libretro/{core}_libretro.so',
                          'core_name': 'Genesis Plus GX' if core == 'genesis_plus_gx' else 'Nestopia',
                          'crc32': '00000000|crc', 'db_name': ''})
    directory = library / 'playlists'
    directory.mkdir(exist_ok=True, mode=0o755)
    target = directory / 'Retro Games.lpl'
    data = {'version': '1.5', 'default_core_path': '', 'default_core_name': '',
            'label_display_mode': 0, 'right_thumbnail_mode': 0, 'left_thumbnail_mode': 0,
            'sort_mode': 0, 'items': items}
    fd, temporary = tempfile.mkstemp(dir=directory, prefix='.playlist-')
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(data, stream, indent=2)
            stream.write('\n')
        os.chmod(temporary, 0o644)
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return items


def import_rom(game, source, library=LIBRARY):
    if game not in GAMES:
        raise ValueError('Unknown game: ' + game)
    source = Path(source)
    extensions = GAMES[game][2]
    suffix = source.suffix.lower()
    if not source.is_file() or suffix not in extensions:
        raise ValueError('Provide an extracted ROM file with extension ' + ', '.join(extensions))
    if not 16 <= source.stat().st_size <= 32 * 1024 * 1024:
        raise ValueError('Unexpected ROM size')
    if suffix == '.nes':
        with source.open('rb') as stream:
            if stream.read(4) != b'NES\x1a':
                raise ValueError('Not an iNES/NES 2.0 ROM')
    if any((library / (game + ext)).exists() for ext in extensions):
        raise ValueError('This game is already imported; existing ROM and saves were kept')
    destination = library / (game + suffix)
    fd, temporary = tempfile.mkstemp(dir=library, prefix='.rom-')
    os.close(fd)
    try:
        shutil.copyfile(source, temporary)
        os.chmod(temporary, 0o644)
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)
    refresh_playlist(library)
    return destination
