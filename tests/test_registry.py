"""New apps must work through the entire control path without product edits."""
import copy
import datetime as dt
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from kids_policy.migrate import default_config, migrate_state
from kids_policy.registry import validate, classify, window_app
from kids_policy.budget import Policy, empty_day
from kids_policy.configver import migrate_policy, migrate_allowlist
from kids_policy.allowlist import is_allowed_window
from kids_policy.launcher import launcher_entries, render
from kids_policy.presentation import app_view
from kids_policy.service import Daemon


def custom_config():
    config = default_config(1204)
    config['budgets'] = {'creative': {'label': 'Creative time', 'daily_minutes': 20}}
    config['apps']['drawing-pad'] = {
        'label': 'Drawing Pad', 'argv': ['/usr/bin/true'], 'budget': 'creative',
        'match': {'process': [{'executables': ['drawing-runtime']}], 'windows': ['drawing-pad']}}
    config['apps']['reading'] = {
        'label': 'Reading', 'argv': ['/usr/bin/true'], 'budget': None,
        'match': {'process': [{'names': ['reading']}], 'windows': ['reader-window']}}
    config['allowlist'] = {'creativity': ['drawing-pad'], 'books': ['reading'], 'tools': ['screentime']}
    return validate(config)


class RegistryTests(unittest.TestCase):
    now = dt.datetime(2026, 9, 7, 15)

    def test_fresh_install_contains_only_controls_and_no_game_budgets(self):
        config = default_config()
        self.assertEqual(set(config['apps']), {'screentime'})
        self.assertEqual(config['budgets'], {})
        self.assertEqual(config['extensions'], [])
        self.assertEqual(config['network']['mode'], 'unchanged')

    def test_new_app_works_in_matching_launcher_permissions_budget_and_ui(self):
        config = custom_config()
        self.assertEqual(classify(config, 'renamed', '/opt/drawing-runtime'), 'drawing-pad')
        self.assertEqual(window_app(config, {'class': 'drawing-pad'}), 'drawing-pad')
        self.assertTrue(is_allowed_window(config, class_name='drawing-pad'))
        entries = launcher_entries(config)
        self.assertIn('/usr/bin/omarchy-kids-open drawing-pad', render(next(e for e in entries if e['app'] == 'drawing-pad')))
        daemon = Daemon.__new__(Daemon)
        daemon.config, daemon.uid = config, config['child_uid']
        daemon.policy = Policy(empty_day(str(self.now.date())), config, self.now, 0)
        self.assertFalse(daemon.app_permission('drawing-pad', self.now)['blocked'])
        daemon.policy.tick(self.now, 0, {'drawing-pad'})
        blocked, _ = daemon.policy.tick(self.now, 1200, {'drawing-pad'})
        self.assertIn('drawing-pad', blocked)
        permission = daemon.app_permission('drawing-pad', self.now)
        self.assertEqual(permission['code'], 'limit')
        state = daemon.policy.snapshot(self.now)
        state['app_status'] = {'drawing-pad': permission}
        view = app_view(state, 'drawing-pad')
        self.assertEqual((view['label'], view['remaining'], view['blocked']), ('Drawing Pad', 0, True))

    def test_unlimited_app_still_obeys_bedtime(self):
        config = custom_config()
        config['play_windows']['weekday'] = {'start': '09:00', 'end': '18:00'}
        policy = Policy(empty_day(str(self.now.date())), config, self.now, 0)
        policy.tick(self.now, 0, {'reading'})
        self.assertNotIn('reading', policy.tick(self.now, 7200, {'reading'})[0])
        self.assertIn('reading', policy.tick(self.now.replace(hour=19), 7201, {'reading'})[0])
        self.assertEqual(policy.apps['reading'], 7200)
        state = policy.snapshot(self.now)
        self.assertIsNone(app_view(state, 'reading')['remaining'])
        json.dumps(state, allow_nan=False)

    def test_unlimited_group_and_zero_group(self):
        config = custom_config()
        config['budgets']['creative']['daily_minutes'] = None
        policy = Policy(empty_day(str(self.now.date())), config, self.now, 0)
        policy.tick(self.now, 0, {'drawing-pad'})
        self.assertNotIn('drawing-pad', policy.tick(self.now, 90000, {'drawing-pad'})[0])
        self.assertIsNone(policy.snapshot(self.now)['budgets']['creative']['remaining_seconds'])
        config['budgets']['creative']['daily_minutes'] = 0
        policy.configure(config)
        self.assertIn('drawing-pad', policy.tick(self.now, 90001, {'drawing-pad'})[0])

    def test_arbitrary_shared_group_charges_once(self):
        config = custom_config()
        config['apps']['reading']['budget'] = 'creative'
        policy = Policy(empty_day(str(self.now.date())), config, self.now, 0)
        policy.tick(self.now, 0, {'drawing-pad', 'reading'})
        policy.tick(self.now, 600, {'drawing-pad', 'reading'})
        self.assertEqual(policy.budgets['creative'].used, 600)
        self.assertEqual(sum(policy.apps.values()), 600)

    def test_removed_and_readded_group_keeps_usage(self):
        config = custom_config()
        policy = Policy(empty_day(str(self.now.date())), config, self.now, 0)
        policy.budgets['creative'].used = 321
        reduced = copy.deepcopy(config)
        del reduced['apps']['drawing-pad']
        reduced['budgets'] = {}
        policy.configure(reduced)
        policy.configure(config)
        self.assertEqual(policy.budgets['creative'].used, 321)

    def test_custom_allowlist_categories_survive_migration(self):
        data = {'creativity': ['drawing-pad'], 'books': [], 'schema_version': 1}
        migrated, _ = migrate_allowlist(data)
        self.assertEqual(migrated['creativity'], ['drawing-pad'])
        self.assertEqual(migrated['books'], [])

    def test_invalid_configuration_cannot_escape_cgroup_or_lose_accounting(self):
        for change in ('id', 'budget', 'match', 'limit', 'uid', 'network', 'window', 'schedule', 'budget_type', 'env_key', 'label', 'tiers', 'extensions', 'desktop'):
            config = custom_config()
            if change == 'id': config['apps']['../escape'] = config['apps'].pop('reading')
            if change == 'budget': config['apps']['reading']['budget'] = 'missing'
            if change == 'match': config['apps']['reading']['match']['process'] = [{}]
            if change == 'limit': config['budgets']['creative']['daily_minutes'] = float('nan')
            if change == 'uid': config['child_uid'] = 0
            if change == 'network': config['network'] = None
            if change == 'window': config['apps']['reading']['window'] = 'large'
            if change == 'schedule': config['play_windows'] = {}
            if change == 'budget_type': config['apps']['reading']['budget'] = []
            if change == 'env_key': config['apps']['reading']['env'] = {5: 'value'}
            if change == 'label': config['apps']['reading']['label'] = []
            if change == 'tiers': config['extra_minute_tiers'] = [100]
            if change == 'extensions': config['extensions'] = 'retro'
            if change == 'desktop': config['apps']['reading']['desktop'] = '../outside.desktop'
            with self.assertRaises(ValueError): validate(config)

    def test_stable_schema_does_not_reintroduce_removed_apps(self):
        config = custom_config()
        del config['apps']['drawing-pad']
        migrated, changed = migrate_policy(config)
        self.assertFalse(changed)
        self.assertNotIn('drawing-pad', migrated['apps'])

    def test_legacy_migration_preserves_custom_commands_limits_schedule_and_grants(self):
        from tests.fixtures import default_config as legacy
        config = legacy(1204)
        config['apps']['stardew_valley']['argv'] = ['/opt/custom/game']
        config['apps']['digger']['window_scale'] = 3
        config['shared_daily_minutes'] = 47
        config['play_windows']['weekend'] = {'start': '10:00', 'end': '19:00'}
        migrated, changed = migrate_policy(config)
        self.assertTrue(changed)
        self.assertEqual(migrated['apps']['stardew_valley']['argv'], ['/opt/custom/game'])
        self.assertEqual(migrated['apps']['digger']['window']['scale'], 3)
        self.assertEqual(migrated['play_windows'], config['play_windows'])
        saved = {'schema_version': 2, 'date': str(self.now.date()), 'shared_used_seconds': 600,
                 'apps': {'stardew_valley': 600}, 'grants': [{'id': 'a', 'kind': 'minutes', 'budget': 'shared',
                 'minutes': 15, 'date': str(self.now.date()), 'child_uid': 1204, 'approver': 'root', 'created_at': 't'}]}
        policy = Policy(saved, migrated, self.now, 0)
        self.assertEqual(policy.remaining('shared'), (47 + 15) * 60 - 600)
        self.assertEqual(policy.state['grants'], saved['grants'])
        self.assertEqual(policy.apps, saved['apps'])
        self.assertEqual(policy.snapshot(self.now)['remaining_seconds'], policy.remaining('shared'))
        again, changed = migrate_policy(migrated)
        self.assertFalse(changed)
        self.assertEqual(again, migrated)

    def test_host_rules_use_selected_accounts(self):
        path = Path(__file__).resolve().parents[1] / 'packaging/configure_host.py'
        spec = importlib.util.spec_from_file_location('host', path)
        host = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(host)
        rules = host.sudoers('student', 'guardian')
        self.assertIn('student ALL=', rules)
        self.assertIn('Defaults:guardian !rootpw', rules)
        self.assertNotIn('omarchy-kids-grant --free-minute --budget *', rules)
        self.assertIn('meta skuid != 1204 accept', host.firewall(1204))
        with self.assertRaises(ValueError): host.sudoers('student\nALL', 'guardian')
        with self.assertRaises(ValueError): host.firewall(0)


class IntegrationEdgeTests(unittest.TestCase):
    def test_normal_stop_releases_frozen_apps_but_crash_keeps_enforcement(self):
        from kids_policy.cgroup import CgroupTree
        tree = CgroupTree()
        with patch.object(tree, 'freeze', side_effect=[False, True]) as freeze:
            self.assertFalse(tree.freeze_all(['missing', 'reading'], False))
            self.assertEqual(freeze.call_count, 2)
        for normal in (True, False):
            daemon = Daemon.__new__(Daemon)
            daemon.config, daemon.uid = custom_config(), 1204
            daemon.cgroups, daemon.fallback = Mock(), Mock()
            daemon.sock, daemon.running = None, True
            def stop_or_fail():
                if normal:
                    daemon.stop()
                else:
                    raise RuntimeError('crashed')
            with patch('kids_policy.service.signal.signal'), patch('kids_policy.service.time.sleep'), \
                 patch('kids_policy.service.SOCKET') as path, patch.object(daemon, 'bind_socket'), \
                 patch.object(daemon, 'sync_configuration', side_effect=stop_or_fail), \
                 patch('kids_policy.service.games', return_value=({}, set())), \
                 patch.object(daemon, 'refresh_desktop'), patch.object(daemon, 'tick_policy', return_value=(set(), [])), \
                 patch.object(daemon, 'enforce', return_value=[]), patch.object(daemon, 'publish'), patch.object(daemon, 'warnings'), \
                 patch.object(daemon, 'accept'):
                daemon.events = []
                if normal:
                    daemon.loop()
                    daemon.fallback.release.assert_called_once_with(set())
                    daemon.cgroups.freeze_all.assert_called_once()
                else:
                    with self.assertRaises(RuntimeError): daemon.loop()
                    daemon.fallback.release.assert_not_called()
                    daemon.cgroups.freeze_all.assert_not_called()

    def test_schedule_only_grant_is_authenticated_separate_and_idempotent(self):
        config = custom_config()
        now = dt.datetime.now()
        daemon = Daemon.__new__(Daemon)
        daemon.config, daemon.uid = config, config['child_uid']
        daemon.policy = Policy(empty_day(str(now.date())), config, now, 0)
        grant = {'id': 'schedule-1', 'kind': 'schedule', 'date': str(now.date()), 'child_uid': daemon.uid,
                 'approver': 'root', 'created_at': now.isoformat(), 'minutes': 15, 'budget': None}
        with patch('kids_policy.service.desktop.approve', return_value={'extension_until': now.timestamp() + 900}) as approve, \
             patch('kids_policy.service.games', return_value=({}, set())), patch.object(daemon, 'publish'):
            self.assertTrue(daemon.schedule_grant(grant)['created'])
            self.assertFalse(daemon.schedule_grant(grant)['created'])
            self.assertEqual(approve.call_count, 1)
            self.assertEqual(daemon.policy.remaining('creative'), 1200)
            with self.assertRaises(ValueError): daemon.schedule_grant(dict(grant, minutes=float('nan')))

    def test_published_ui_metadata_does_not_include_command_or_environment(self):
        config = custom_config()
        config['apps']['reading']['env'] = {'APP_SETTING': 'private-value'}
        now = dt.datetime.now()
        data = Policy(empty_day(str(now.date())), config, now, 0).snapshot(now)
        self.assertNotIn('env', data['app_definitions']['reading'])
        self.assertNotIn('argv', data['app_definitions']['reading'])

    def test_bar_model_uses_arbitrary_labels_and_deduplicates_only_shared_groups(self):
        import shutil, subprocess
        if not shutil.which('node'):
            self.skipTest('requires Node')
        source = (Path(__file__).resolve().parents[1] / 'shell/Allowances.js').read_text()
        script = source + """
const assert = require('assert');
let usage = {enabled_apps:['draw','read','other','hidden'],
 app_definitions:{draw:{budget:'constructor'},read:{label:'Books',budget:null},other:{budget:'constructor'}},
 budgets:{constructor:{label:'Creative',remaining_seconds:321}}};
assert.deepEqual(entries(usage),[{app:'draw',title:'Creative',remaining:321},{app:'read',title:'Books',remaining:null}]);
assert.deepEqual(entries({}), []);
"""
        subprocess.run(['node', '-e', script], check=True)
