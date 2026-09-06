from pathlib import Path

DEFAULT_ALLOWLIST = ('digger', 'minecraft', 'stardew_valley', 'vlc', 'screentime')

ALLOWED_DESKTOPS = {
    'digger': 'digger.desktop',
    'minecraft': 'minecraft-vm.desktop',
    'stardew_valley': 'stardew-valley.desktop',
    'vlc': 'kids-videos.desktop',
    'screentime': 'omarchy-kids-screentime.desktop',
}

ALLOWED_WINDOW = {
    'digger': ('digger', 'd i g g e r'),
    'minecraft': ('minecraft', 'prismlauncher', 'org.prismlauncher'),
    'stardew_valley': ('stardew', 'steam_app_413150'),
    'vlc': ('vlc', 'kids videos'),
    'screentime': ('omarchy kids', 'omarchy-kids-screentime', 'omarchy-kids-hud', 'omarchy-kids-block'),
}

SESSION_MARKERS = (
    'hyprland', 'quickshell', 'omarchy-shell', 'omarchy-menu',
    'xdg-desktop-portal', 'pipewire', 'wireplumber', 'dbus-daemon',
    'systemd', 'uwsm', 'swww', 'hyprpaper', 'xdg-document-portal',
    'xdg-permission-store', 'at-spi', 'dconf', 'gnome-keyring',
    'xwayland', 'hyprctl', 'grim', 'hyprland-dialog', 'hyprland-guiutils',
    'omarchy-notification', 'omarchy-kids-hud', 'omarchy-kids-block',
    'omarchy-kids-policy',
)


def enabled_ids(config):
    listed = config.get('allowlist')
    if isinstance(listed, dict):
        ids = []
        for key, group in listed.items():
            if key == 'schema_version' or not isinstance(group, list):
                continue
            ids.extend(group)
        return tuple(ids)
    if listed:
        return tuple(listed)
    return DEFAULT_ALLOWLIST


def allowed_desktop_names(config):
    names = set()
    for app_id in enabled_ids(config):
        desktop = ALLOWED_DESKTOPS.get(app_id)
        if desktop:
            names.add(desktop)
    return names


def is_session(title='', class_name='', executable='', command=''):
    blob = f'{title} {class_name} {executable} {command}'.lower()
    return any(marker in blob for marker in SESSION_MARKERS)


def is_allowed_window(config, title='', class_name='', executable='', command=''):
    blob = f'{title} {class_name} {executable} {command}'.lower()
    if is_session(title, class_name, executable, command):
        return True
    for app_id in enabled_ids(config):
        for marker in ALLOWED_WINDOW.get(app_id, ()):
            if marker in blob:
                return True
    return False


def hide_desktop_files(home: Path, config):
    allowed = allowed_desktop_names(config)
    dest = Path(home) / '.local/share/applications'
    dest.mkdir(parents=True, exist_ok=True)
    seen = set()
    roots = [
        Path('/usr/share/applications'),
        Path('/usr/local/share/applications'),
        dest,
    ]
    hidden = 0
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.glob('*.desktop'):
            name = path.name
            if name in allowed or name in seen:
                continue
            seen.add(name)
            override = dest / name
            if name in allowed:
                continue
            override.write_text(
                '[Desktop Entry]\n'
                'Type=Application\n'
                f'Name={path.stem}\n'
                'Exec=/usr/bin/true\n'
                'NoDisplay=true\n'
                'Hidden=true\n'
            )
            hidden += 1
    return hidden
