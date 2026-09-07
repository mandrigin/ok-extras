import ast
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from kids_policy import desktop, native_extension
from kids_policy.budget import Policy, empty_day
from tests.fixtures import default_config
from kids_policy.service import Daemon

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('configure_desktop', ROOT / 'packaging/configure_desktop.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class DesktopBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.now = 1788721200.0
        self.balance, self.bedtime, self.support = 0, False, True
        self.calls = []
        for target, kwargs in (
            ('kids_policy.native_extension.DIRECTORY', {'new': self.path}),
            ('kids_policy.native_extension.os.fstat', {'return_value': SimpleNamespace(st_uid=0, st_mode=stat.S_IFREG | 0o644)}),
            ('kids_policy.desktop.request', {'side_effect': self.native}),
        ):
            p = patch(target, **kwargs)
            p.start()
            self.addCleanup(p.stop)

    def native(self, uid, command, **values):
        self.calls.append((uid, command, values))
        if command == 'grant':
            self.balance += values['minutes'] * 60
        end = native_extension.extension_until(uid, self.now)
        phase = 'bedtime' if self.bedtime and not end else ('running' if self.balance else 'empty')
        return {'ok': True, 'phase': phase, 'remaining_seconds': self.balance,
                'extension_supported': self.support, 'extension_until': end,
                'blocked_label': 'Weekend downtime' if phase == 'bedtime' else ''}

    def test_normal_parent_grant_fills_only_missing_desktop_time(self):
        self.balance = 600
        result = desktop.approve(1000, 15, now=self.now)
        self.assertEqual(result['remaining_seconds'], 900)
        self.assertIn((1000, 'grant', {'minutes': 5}), self.calls)
        self.assertEqual(list(self.path.iterdir()), [])

    def test_sufficient_desktop_balance_is_not_credited_twice(self):
        self.balance = 2100
        desktop.approve(1000, 15, now=self.now)
        self.assertFalse(any(command == 'grant' for _, command, _ in self.calls))

    def test_bedtime_with_balance_rejects_ordinary_grant_without_changes(self):
        self.bedtime, self.balance = True, 2100
        with self.assertRaisesRegex(ValueError, 'past bedtime'):
            desktop.approve(1000, 15, now=self.now)
        self.assertEqual(self.balance, 2100)
        self.assertEqual(list(self.path.iterdir()), [])

    def test_explicit_extension_covers_both_and_expires_without_daemon(self):
        self.bedtime = True
        result = desktop.approve(1000, 15, True, 'parent-grant', now=self.now)
        self.assertEqual(result['phase'], 'running')
        self.assertEqual(self.balance, 900)
        self.assertEqual(result['extension_until'], self.now + 900)
        self.assertEqual(native_extension.extension_until(1000, self.now + 899), self.now + 900)
        self.assertEqual(native_extension.extension_until(1000, self.now + 900), 0)
        self.assertEqual(native_extension.extension_until(1001, self.now), 0)
        self.assertEqual(native_extension.extension_until(1000, self.now - 1), 0)

    def test_missing_hook_refuses_before_adding_time(self):
        self.support = False
        with self.assertRaisesRegex(ValueError, 'integration'):
            desktop.approve(1000, 15, True, now=self.now)
        self.assertEqual(self.balance, 0)

    def test_desktop_failure_cannot_appear_as_success(self):
        with patch('kids_policy.desktop.request', side_effect=OSError('offline')):
            with self.assertRaisesRegex(ValueError, 'unavailable'):
                desktop.approve(1000, 15, now=self.now)

    def test_untrusted_writable_and_malformed_exception_files_are_ignored(self):
        desktop.approve(1000, 15, True, now=self.now)
        for owner, mode in ((1000, 0o644), (0, 0o666)):
            with patch('kids_policy.native_extension.os.fstat', return_value=SimpleNamespace(st_uid=owner, st_mode=stat.S_IFREG | mode)):
                self.assertEqual(native_extension.extension_until(1000, self.now), 0)
        path = self.path / 'desktop-extension-1000.json'
        for contents in ('broken', json.dumps({'uid': 1000, 'created': self.now, 'expires': self.now + 7200})):
            path.write_text(contents)
            self.assertEqual(native_extension.extension_until(1000, self.now), 0)
        path.unlink()
        path.symlink_to(self.path / 'missing')
        self.assertEqual(native_extension.extension_until(1000, self.now), 0)


class CoordinatedPolicyTests(unittest.TestCase):
    def setUp(self):
        self.now = dt.datetime.now()
        self.daemon = Daemon.__new__(Daemon)
        self.daemon.uid = 1000
        self.daemon.config = default_config()
        self.daemon.policy = Policy(empty_day(str(self.now.date())), self.daemon.config, self.now, 0)
        self.daemon.desktop = {'phase': 'bedtime', 'remaining_seconds': 2100, 'blocked_label': 'Weekend downtime'}
        self.grant = {'id': 'test', 'kind': 'minutes', 'date': str(self.now.date()),
                      'child_uid': 1000, 'approver': 'root', 'created_at': self.now.isoformat(),
                      'minutes': 15, 'budget': 'shared'}

    def test_desktop_bedtime_wins_over_unused_app_time(self):
        result = self.daemon.app_permission('stardew_valley', self.now)
        self.assertEqual(result['code'], 'desktop_bedtime')
        self.assertTrue(result['blocked'])

    def test_offline_desktop_blocks_launch(self):
        self.daemon.desktop = {'error': 'Desktop service unavailable'}
        self.assertEqual(self.daemon.app_permission('stardew_valley', self.now)['code'], 'desktop_unavailable')

    def test_frozen_game_does_not_spend_app_time_while_desktop_is_blocked(self):
        noon = self.now.replace(hour=12)
        self.daemon.policy = Policy(empty_day(str(noon.date())), self.daemon.config, noon, 0)
        self.daemon.desktop = {'phase': 'running', 'remaining_seconds': 600}
        self.daemon.tick_policy(noon, 0, {'stardew_valley'})
        self.daemon.tick_policy(noon, 60, {'stardew_valley'})
        used = self.daemon.policy.shared.used
        self.daemon.desktop = {'phase': 'empty', 'remaining_seconds': 0}
        blocked, _ = self.daemon.tick_policy(noon, 660, {'stardew_valley'})
        self.assertIn('stardew_valley', blocked)
        self.assertEqual(self.daemon.policy.shared.used, used)
        self.daemon.desktop = {'phase': 'running', 'remaining_seconds': 900}
        self.daemon.tick_policy(noon, 661, {'stardew_valley'})
        self.daemon.tick_policy(noon, 721, {'stardew_valley'})
        self.assertEqual(self.daemon.policy.shared.used, used + 60)

    def test_free_minute_does_not_override_desktop_or_spend_token(self):
        with patch.object(self.daemon, 'refresh_desktop'):
            self.assertFalse(self.daemon.free_minute('shared')['ok'])
        self.assertFalse(self.daemon.policy.state['free_minute_used'])

    def test_replayed_request_does_not_add_time_again(self):
        self.daemon.policy.state['grants'] = [self.grant]
        with patch('kids_policy.desktop.approve') as approve:
            self.assertFalse(self.daemon.play_grant(self.grant, True)['created'])
            approve.assert_not_called()

    def test_failed_desktop_approval_does_not_grant_app_time(self):
        with patch('kids_policy.desktop.approve', side_effect=ValueError('offline')):
            with self.assertRaisesRegex(ValueError, 'offline'):
                self.daemon.play_grant(self.grant, True)
        self.assertEqual(self.daemon.policy.state['grants'], [])

    def test_invalid_duration_or_account_is_rejected_before_native_request(self):
        for changes in ({'minutes': float('nan')}, {'minutes': 0}, {'minutes': 61}, {'child_uid': 1001}):
            with patch('kids_policy.desktop.approve') as approve:
                with self.assertRaises(ValueError):
                    self.daemon.play_grant(dict(self.grant, **changes), True)
                approve.assert_not_called()


class NativeHookTests(unittest.TestCase):
    SOURCE = '''class Account:
    def blocking_period(self, now):
        return self._period(now, "block")
    def status(self, now):
        payload = {"remaining_seconds": 2100}
        return payload
'''

    def test_installer_is_idempotent_and_preserves_native_checks(self):
        modified = installer.patched(self.SOURCE)
        self.assertEqual(installer.patched(modified), modified)
        self.assertIn('return self._period(now, "block")', modified)
        self.assertIn('extension_supported', modified)

    def test_unknown_native_layout_is_refused(self):
        with self.assertRaises(AssertionError):
            installer.patched(self.SOURCE.replace('return self._period(now, "block")', 'return None'))

    def test_native_restarts_still_observe_expiry_and_original_schedule(self):
        tree = ast.parse(installer.patched(self.SOURCE))
        # Execute only the patched class; stand in for the file-backed reader.
        namespace = {'extension_until': lambda uid, now: 1900 if 1000 <= now < 1900 else 0}
        exec(compile(ast.Module(body=[tree.body[0]], type_ignores=[]), '<native>', 'exec'), namespace)
        account = namespace['Account']()
        account.uid = 1000
        account._period = lambda now, mode: {'label': 'Weekend downtime'}
        self.assertEqual(account.blocking_period(999)['label'], 'Weekend downtime')
        self.assertIsNone(account.blocking_period(1000))
        restarted = namespace['Account']()
        restarted.uid, restarted._period = account.uid, account._period
        self.assertIsNone(restarted.blocking_period(1899))
        self.assertEqual(restarted.blocking_period(1900)['label'], 'Weekend downtime')
        self.assertEqual(restarted.status(1900)['extension_until'], 0)


if __name__ == '__main__':
    unittest.main()
