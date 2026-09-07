"""Add the generated allow-list filter to Omarchy's existing app library."""
from pathlib import Path
import shutil
import sys

LIBRARY = Path('/usr/share/omarchy/shell/services/AppLibrary.qml')
MENU = Path('/usr/share/omarchy/shell/plugins/menu/Menu.qml')
MARKER = '// ok-extras: launcher follows the parent allow-list'


def patched(source):
    if MARKER in source:
        return source
    anchors = ('import "AppSearch.js" as AppSearch', '  function isHiddenEntry(entry) {',
               '  function launch(desktopId, name) {')
    if any(source.count(anchor) != 1 for anchor in anchors):
        raise ValueError('Unsupported Omarchy AppLibrary; launcher upgrade refused')
    source = source.replace(anchors[0], anchors[0] + '\nimport "KidsLauncherPolicy.js" as KidsLauncherPolicy')
    source = source.replace(anchors[1], '''  // ok-extras: launcher follows the parent allow-list
  property var kidsLaunchers: ({})
  readonly property bool kidsManaged: root.kidsLaunchers.user === Quickshell.env("USER")
  FileView {
    path: "/var/lib/omarchy-kids/launcher.json"
    watchChanges: true
    printErrors: false
    onLoaded: {
      try {
        var next = JSON.parse(text())
        if (typeof next.user !== "string" || !Array.isArray(next.desktop_ids)) throw new Error("invalid launcher manifest")
        root.kidsLaunchers = next
      } catch (error) {
        if (root.kidsLaunchers.user) root.kidsLaunchers = { user: root.kidsLaunchers.user, desktop_ids: [] }
      }
      root.appsChanged()
    }
    onFileChanged: reload()
    onLoadFailed: {
      if (root.kidsLaunchers.user) root.kidsLaunchers = { user: root.kidsLaunchers.user, desktop_ids: [] }
      root.appsChanged()
    }
  }

''' + anchors[1] + '''
    if (!KidsLauncherPolicy.permits(root.kidsLaunchers, Quickshell.env("USER"), (entry || {}).id)) return true''')
    source = source.replace(anchors[2], anchors[2] + '''
    if (!KidsLauncherPolicy.permits(root.kidsLaunchers, Quickshell.env("USER"), desktopId)) return''')
    return source


def patched_menu(source):
    marker = '// ok-extras: child launcher uses only generated app rows'
    if marker in source:
        return source
    visible = '  function isVisible(entry) {'
    opening = '  function openExistingMenu(initialMenu) {'
    if source.count(visible) != 1 or source.count(opening) != 1:
        raise ValueError('Unsupported Omarchy menu; launcher upgrade refused')
    source = source.replace(visible, '''  // ok-extras: child launcher uses only generated app rows
  readonly property bool kidsAppsOnly: root.appLibrary && root.appLibrary.kidsManaged === true

''' + visible + '''
    if (root.kidsAppsOnly && (root.activeMenu === "root" || root.activeMenu === "apps")) {
      if (!entry || (entry.id !== "apps" && entry.kind !== "app")) return false
      if (entry.kind === "app" && root.appLibrary.isHiddenEntry({ id: entry.appId })) return false
    }''')
    source = source.replace(opening, opening + '''
    if (root.kidsAppsOnly && (!initialMenu || initialMenu === "root")) initialMenu = "apps"''')
    return source


def main():
    updated = patched(LIBRARY.read_text())
    menu = patched_menu(MENU.read_text())
    if '--check' in sys.argv:
        print('Native launcher integration is compatible')
        return
    backup = LIBRARY.with_suffix('.qml.before-ok-extras')
    if not backup.exists():
        shutil.copy2(LIBRARY, backup)
    helper = Path(__file__).resolve().parents[1] / 'shell/LauncherPolicy.js'
    shutil.copyfile(helper, LIBRARY.with_name('KidsLauncherPolicy.js'))
    LIBRARY.with_name('KidsLauncherPolicy.js').chmod(0o644)
    stage = LIBRARY.with_suffix('.tmp')
    stage.write_text(updated)
    stage.chmod(0o644)
    stage.replace(LIBRARY)
    backup = MENU.with_suffix('.qml.before-ok-extras')
    if not backup.exists():
        shutil.copy2(MENU, backup)
    stage = MENU.with_suffix('.tmp')
    stage.write_text(menu)
    stage.chmod(0o644)
    stage.replace(MENU)


if __name__ == '__main__':
    main()
