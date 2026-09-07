import importlib.util
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from kids_policy.allowlist import enabled_ids
from kids_policy.configver import migrate_allowlist
from kids_policy.launcher import launcher_entries, sync_desktop_files, sync
from kids_policy.migrate import default_config
from kids_policy.budget import Policy, empty_day
from kids_policy.service import Daemon

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('configure_launcher', ROOT / 'packaging/configure_launcher.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / 'child'
        self.system = Path(self.tmp.name) / 'system'
        self.system.mkdir()
        self.dest = self.home / '.local/share/applications'
        self.config = default_config()
        self.config['allowlist'] = {'games': ['digger'], 'videos': [], 'tools': []}

    def apply(self):
        return sync_desktop_files(self.home, self.config, roots=[self.system])

    def visible(self):
        return {p.name for p in self.dest.glob('*.desktop') if 'Hidden=false' in p.read_text()}

    def test_only_allowlisted_apps_appear_even_with_new_installs(self):
        (self.system / 'browser.desktop').write_text('[Desktop Entry]\nName=Browser\nExec=browser\n')
        self.apply()
        self.assertEqual(self.visible(), {'digger.desktop'})
        (self.system / 'another.desktop').write_text('[Desktop Entry]\nName=Another\n')
        self.apply()
        self.assertIn('Hidden=true', (self.dest / 'another.desktop').read_text())
        self.assertEqual(self.visible(), {'digger.desktop'})

    def test_remove_then_reallow_restores_a_real_guarded_launcher(self):
        self.apply()
        self.config['allowlist']['games'] = []
        self.apply()
        self.assertEqual(self.visible(), set())
        self.config['allowlist']['games'] = ['digger']
        self.apply()
        self.assertEqual(self.visible(), {'digger.desktop'})
        self.assertIn('Exec=/usr/bin/omarchy-kids-open digger', (self.dest / 'digger.desktop').read_text())

    def test_empty_allowlist_stays_empty_through_migration(self):
        for allow in ({'schema_version': 1, 'games': [], 'videos': [], 'tools': []}, []):
            migrated, _ = migrate_allowlist(allow)
            self.assertEqual(enabled_ids({'allowlist': migrated}), ())
        self.assertEqual(enabled_ids({'allowlist': []}), ())

    def test_custom_metadata_and_legacy_policy_specs_are_merged(self):
        self.config['apps']['digger'] = {'argv': ['/usr/local/bin/digger'], 'label': 'Digging game'}
        self.apply()
        self.assertIn('Name=Digging game', (self.dest / 'digger.desktop').read_text())
        self.assertEqual(launcher_entries(self.config)[0]['desktop'], 'digger.desktop')

    def test_unknown_or_invalid_ids_cannot_expose_unrelated_apps(self):
        self.config['allowlist']['games'] = ['browser']
        self.assertEqual(launcher_entries(self.config), [])
        self.config['allowlist']['games'] = ['../escape']
        with self.assertRaises(ValueError):
            launcher_entries(self.config)

    def test_existing_custom_launcher_is_backed_up_and_sync_is_idempotent(self):
        self.dest.mkdir(parents=True)
        original = '[Desktop Entry]\nName=Custom game\nExec=custom\n'
        (self.dest / 'digger.desktop').write_text(original)
        self.apply()
        backup = self.home / '.local/share/omarchy-kids/launcher-backups/digger.desktop'
        self.assertEqual(backup.read_text(), original)
        stamp = (self.dest / 'digger.desktop').stat().st_mtime_ns
        self.apply()
        self.assertEqual((self.dest / 'digger.desktop').stat().st_mtime_ns, stamp)
        self.assertEqual(backup.read_text(), original)

    def test_symlink_target_is_not_overwritten(self):
        self.dest.mkdir(parents=True)
        other = self.system / 'untouched'
        other.write_text('original')
        (self.dest / 'digger.desktop').symlink_to(other)
        self.apply()
        self.assertEqual(other.read_text(), 'original')
        self.assertFalse((self.dest / 'digger.desktop').is_symlink())

    def test_manifest_matches_launchers_and_includes_allowed_tools(self):
        self.config['allowlist']['tools'] = ['screentime']
        manifest = self.home / 'launcher.json'
        with patch('kids_policy.launcher.SYSTEM_ROOTS', [self.system]):
            sync(self.home, self.config, 'valentin', manifest=manifest)
        ids = json.loads(manifest.read_text())
        self.assertEqual(ids['user'], 'valentin')
        self.assertEqual(set(ids['desktop_ids']), {name[:-8] for name in self.visible()})
        self.assertIn('Exec=/usr/bin/omarchy-kids-ui', (self.dest / 'omarchy-kids-screentime.desktop').read_text())

    def test_live_config_change_updates_menu_and_permissions_without_resetting_usage(self):
        uid = os.getuid()
        self.config['child_uid'] = uid
        policy = self.system / 'policy.json'
        allow = self.system / 'allowlist.json'
        manifest = self.system / 'launcher.json'
        policy.write_text(json.dumps(self.config))
        allow.write_text(json.dumps(dict(self.config['allowlist'], schema_version=1)))
        daemon = Daemon.__new__(Daemon)
        daemon.uid, daemon.config, daemon.launcher_signature = uid, self.config, None
        noon = dt.datetime.now().replace(hour=12)
        daemon.policy = Policy(empty_day(str(noon.date())), self.config, noon, 0)
        daemon.policy.digger.used = 123
        account = SimpleNamespace(pw_dir=str(self.home), pw_uid=uid, pw_gid=os.getgid(), pw_name='valentin')
        with patch('kids_policy.service.CONFIG', policy), patch('kids_policy.service.ALLOWLIST', allow), \
             patch('kids_policy.configver.HISTORY', self.system / 'history'), \
             patch('kids_policy.service.pwd.getpwuid', return_value=account), \
             patch('kids_policy.launcher.MANIFEST', manifest), patch('kids_policy.launcher.SYSTEM_ROOTS', [self.system]):
            daemon.sync_configuration()
            self.assertEqual(self.visible(), {'digger.desktop'})
            allow.write_text(json.dumps({'schema_version': 1, 'games': ['micropolis'], 'videos': [], 'tools': []}))
            daemon.sync_configuration()
            self.assertEqual(self.visible(), {'micropolis.desktop'})
            self.assertEqual(daemon.app_permission('digger', noon)['code'], 'not_allowed')
            self.assertFalse(daemon.app_permission('micropolis', noon)['blocked'])
            self.assertEqual(daemon.policy.digger.used, 123)

    @unittest.skipUnless(importlib.util.find_spec('gi'), 'requires Linux GIO desktop parser')
    def test_linux_desktop_parser_accepts_generated_entries_and_hides_denied_apps(self):
        import gi
        gi.require_version('Gio', '2.0')
        from gi.repository import Gio
        # The parser checks that the executable exists on this test machine.
        self.config['apps']['digger']['launcher_argv'] = ['/usr/bin/true', 'digger']
        self.apply()
        entry = Gio.DesktopAppInfo.new_from_filename(str(self.dest / 'digger.desktop'))
        self.assertIsNotNone(entry)
        self.assertTrue(entry.should_show())
        self.assertEqual(entry.get_executable(), '/usr/bin/true')
        self.config['allowlist']['games'] = []
        self.apply()
        try:
            denied = Gio.DesktopAppInfo.new_from_filename(str(self.dest / 'digger.desktop'))
        except TypeError:
            denied = None
        self.assertTrue(denied is None or not denied.should_show())


class NativeLauncherTests(unittest.TestCase):
    SOURCE = '''import "AppSearch.js" as AppSearch
Item {
  function isHiddenEntry(entry) {
    return false
  }
  function launch(desktopId, name) {
    doLaunch(desktopId)
  }
}
'''

    def test_adapter_is_idempotent_and_checks_launch_as_well_as_visibility(self):
        updated = installer.patched(self.SOURCE)
        self.assertEqual(updated, installer.patched(updated))
        self.assertEqual(updated.count('KidsLauncherPolicy.permits('), 2)
        self.assertIn('watchChanges: true', updated)
        with self.assertRaises(ValueError):
            installer.patched('unrecognized launcher')

    def test_main_menu_redirects_to_apps_and_filters_static_shortcuts(self):
        source = 'Item {\n  function isVisible(entry) {\n return true\n}\n  function openExistingMenu(initialMenu) {\n open(initialMenu)\n}\n}'
        updated = installer.patched_menu(source)
        self.assertEqual(installer.patched_menu(updated), updated)
        self.assertIn('initialMenu = "apps"', updated)
        self.assertIn('entry.kind !== "app"', updated)
        self.assertIn('root.activeMenu === "root" || root.activeMenu === "apps"', updated)

    @unittest.skipUnless(shutil.which('node'), 'requires node for QML JavaScript policy tests')
    def test_live_filter_rejects_removed_and_new_apps_without_affecting_parent(self):
        code = (ROOT / 'shell/LauncherPolicy.js').read_text() + '''
const assert = require('node:assert/strict');
let m = {user: 'valentin', desktop_ids: ['digger', 'kids-videos']};
assert.equal(permits(m, 'valentin', 'digger.desktop'), true);
assert.equal(permits(m, 'valentin', 'steam'), false);
assert.equal(permits(m, 'valentin', 'newly-installed'), false);
assert.equal(permits(m, 'parent', 'steam'), true);
m.desktop_ids = [];
assert.equal(permits(m, 'valentin', 'digger'), false);
m.desktop_ids = ['micropolis'];
assert.equal(permits(m, 'valentin', 'micropolis'), true);
assert.equal(permits(m, 'valentin', 'digger'), false);
'''
        subprocess.run(['node', '-e', code], check=True)
