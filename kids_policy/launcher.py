"""Generate and reconcile launchers from the same allow-list as enforcement."""
import json
import os
from pathlib import Path
import re

from kids_policy.allowlist import enabled_ids
from kids_policy.configver import migrate_policy

MANIFEST = Path('/var/lib/omarchy-kids/launcher.json')
SYSTEM_ROOTS = (Path('/usr/share/applications'), Path('/usr/local/share/applications'),
                Path('/var/lib/flatpak/exports/share/applications'))


def launcher_entries(config):
    defaults = migrate_policy(config)[0]['apps']
    result = []
    for app in dict.fromkeys(enabled_ids(config)):
        if not isinstance(app, str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}', app):
            raise ValueError('Invalid allow-list app ID')
        spec = {**defaults.get(app, {}), **config.get('apps', {}).get(app, {})}
        filename = spec.get('desktop')
        if not filename:
            continue  # Unknown IDs never expose an unrelated installed app.
        if not re.fullmatch(r'[A-Za-z0-9_.-]+\.desktop', filename) or filename.startswith('.'):
            raise ValueError('Invalid desktop filename for ' + app)
        argv = spec.get('launcher_argv', ['/usr/bin/omarchy-kids-open', app])
        if not isinstance(argv, list) or not argv or any(not isinstance(arg, str) for arg in argv):
            raise ValueError('Invalid launcher command for ' + app)
        result.append({'app': app, 'desktop': filename, 'label': spec.get('label', app),
                       'icon': spec.get('icon', 'application-x-executable'), 'argv': argv,
                       'categories': spec.get('desktop_categories', ['Utility'])})
    if len({entry['desktop'] for entry in result}) != len(result):
        raise ValueError('Two allowed apps use the same desktop filename')
    return result


def value(text):
    text = str(text)
    if any(char in text for char in ('\n', '\r', '\0')):
        raise ValueError('Launcher values must be single-line strings')
    return text.replace('\\', '\\\\')


def exec_arg(text):
    value(text)  # Reject control characters before serializing Exec.
    if re.fullmatch(r'[A-Za-z0-9_/.:=+-]+', text):
        return text
    escaped = text.replace('%', '%%')
    # Desktop Entry Exec uses double quotes and its own escaping, not a shell.
    for char in ('\\', '"', '`', '$'):
        escaped = escaped.replace(char, '\\' + char)
    return '"' + escaped.replace('\\', '\\\\') + '"'


def render(entry):
    return ('[Desktop Entry]\nType=Application\n'
            f'Name={value(entry["label"])}\n'
            f'Exec={" ".join(exec_arg(arg) for arg in entry["argv"])}\n'
            f'Icon={value(entry["icon"])}\nTerminal=false\n'
            f'Categories={value(";".join(entry.get("categories", ["Utility"])))};\n'
            'NoDisplay=false\nHidden=false\nX-Omarchy-Kids-Managed=true\n')


def replace_if_changed(path, contents, owner=None):
    path = Path(path)
    # Replace symlinks rather than following a child's launcher outside this directory.
    if not path.is_symlink() and path.exists() and path.read_text() == contents:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    import tempfile
    fd, temporary = tempfile.mkstemp(prefix='.kids-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(contents)
            os.fchmod(stream.fileno(), 0o644)
            if owner is not None:
                os.fchown(stream.fileno(), *owner)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return True


def sync_desktop_files(home, config, roots=None, owner=None):
    home = Path(home)
    dest = home / '.local/share/applications'
    if not dest.resolve().is_relative_to(home.resolve()):
        raise ValueError('Child application directory resolves outside the child home')
    entries = launcher_entries(config)
    allowed = {entry['desktop']: entry for entry in entries}
    roots = list(SYSTEM_ROOTS if roots is None else roots)
    roots += [home / '.local/share/flatpak/exports/share/applications', dest]
    filenames = set(allowed)
    for root in roots:
        if root.is_dir():
            filenames.update(path.relative_to(root).as_posix().replace('/', '-') for path in root.rglob('*.desktop'))
    hidden = 0
    for filename in sorted(filenames):
        target = dest / filename
        if filename in allowed:
            contents = render(allowed[filename])
        else:
            contents = ('[Desktop Entry]\nType=Application\nName=Unavailable app\n'
                        'Exec=/usr/bin/true\nNoDisplay=true\nHidden=true\nX-Omarchy-Kids-Managed=true\n')
            hidden += 1
        if target.is_file() and not target.is_symlink():
            original = target.read_text()
            if 'X-Omarchy-Kids-Managed=true' not in original:
                backup = home / '.local/share/omarchy-kids/launcher-backups' / filename
                if not backup.exists():
                    replace_if_changed(backup, original, owner)
        replace_if_changed(target, contents, owner)
    return hidden


def sync(home, config, user, owner=None, manifest=None):
    # Publish the filter first: removals are hidden before desktop-file cleanup.
    entries = launcher_entries(config)
    data = {'user': user, 'desktop_ids': [entry['desktop'][:-8] for entry in entries]}
    replace_if_changed(manifest or MANIFEST, json.dumps(data, indent=2) + '\n')
    return sync_desktop_files(home, config, owner=owner)
