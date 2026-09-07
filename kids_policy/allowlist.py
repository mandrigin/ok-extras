from pathlib import Path

DEFAULT_ALLOWLIST = ('digger', 'minecraft', 'stardew_valley', 'vlc', 'screentime')

ALLOWED_WINDOW = {
    'digger': ('digger', 'd i g g e r'),
    'micropolis': ('micropolis',),
    'retro': ('retroarch',),
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
    'hyprpolkitagent', 'polkit',
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
    if isinstance(listed, (list, tuple)):
        return tuple(listed)
    return DEFAULT_ALLOWLIST


def allowed_desktop_names(config):
    from kids_policy.launcher import launcher_entries
    return {entry['desktop'] for entry in launcher_entries(config)}


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
    from kids_policy.launcher import sync_desktop_files
    return sync_desktop_files(home, config)
