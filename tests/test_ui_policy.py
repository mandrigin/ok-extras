import copy
import datetime as dt
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

from kids_policy.budget import Policy, empty_day
from kids_policy.migrate import default_config
from kids_policy.presentation import app_view, fresh, window_app
from kids_policy.service import Daemon

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('configure_ui', ROOT / 'packaging/configure_ui.py')
configure_ui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(configure_ui)


class AllowanceTests(unittest.TestCase):
    def setUp(self):
        self.now = dt.datetime(2026, 9, 6, 12)
        self.daemon = Daemon.__new__(Daemon)
        self.daemon.uid = 1000
        self.daemon.config = default_config()
        self.daemon.config['allowlist'] = {'games': ['digger'], 'videos': ['vlc']}
        self.daemon.policy = Policy(empty_day('2026-09-06'), self.daemon.config, self.now, 0)
        self.daemon.policy.digger.used = 600

    def test_other_budgets_do_not_make_digger_available(self):
        permission = self.daemon.app_permission('digger', self.now)
        self.assertTrue(permission['blocked'])
        self.assertEqual(permission['reason'], 'Digger daily limit reached')
        self.assertFalse(self.daemon.app_permission('vlc', self.now)['blocked'])

    def test_hidden_game_cannot_be_launched_by_helper(self):
        permission = self.daemon.app_permission('minecraft', self.now)
        self.assertTrue(permission['blocked'])
        self.assertEqual(permission['code'], 'not_allowed')

    def test_allowlist_refusal_even_with_unused_time(self):
        with patch('kids_policy.service.games', return_value=({}, set())):
            self.assertFalse(self.daemon.may_launch('minecraft')['ok'])

    def test_free_minute_is_once_a_day_and_targets_selected_budget(self):
        with patch.object(self.daemon, 'grant', side_effect=lambda grant: {'ok': True, 'grant': grant}):
            result = self.daemon.free_minute('digger')
            self.assertEqual(result['grant']['budget'], 'digger')
            self.assertEqual(result['grant']['minutes'], 1)
            self.assertFalse(self.daemon.free_minute('vlc')['ok'])

    def test_invalid_budget_does_not_spend_free_minute(self):
        self.assertFalse(self.daemon.free_minute('anything')['ok'])
        self.assertFalse(self.daemon.policy.state['free_minute_used'])

    def test_ui_uses_authoritative_app_refusal(self):
        state = {'digger_remaining_seconds': 300, 'app_status': {'digger': {'blocked': True, 'reason': 'Too early'}}}
        view = app_view(state, 'digger')
        self.assertTrue(view['blocked'])
        self.assertEqual(view['remaining'], 300)

    def test_stale_state_is_not_presented_as_live(self):
        state = {'updated_at': '2026-09-06T12:00:00'}
        self.assertTrue(fresh(state, self.now))
        self.assertFalse(fresh(state, self.now + dt.timedelta(seconds=20)))
        self.assertFalse(fresh({}, self.now))

    def test_ui_windows_are_not_mistaken_for_games(self):
        self.assertIsNone(window_app({'title': 'Omarchy Kids · Digger', 'class': 'tk'}))
        self.assertEqual(window_app({'title': 'D I G G E R', 'class': 'digger'}), 'digger')


class BarUpgradeTests(unittest.TestCase):
    def test_upgrade_is_idempotent_and_keeps_native_widget_and_preferences(self):
        original = {'bar': {'position': 'top', 'layout': {'right': [
            {'id': 'omarchy.screen-time', 'custom': 42}, {'id': 'omarchy.audio'}]}},
            'plugins': ['some-plugin']}
        once = configure_ui.configure(copy.deepcopy(original))
        twice = configure_ui.configure(copy.deepcopy(once))
        self.assertEqual(once, twice)
        self.assertEqual(once['plugins'], original['plugins'])
        self.assertEqual(once['bar']['position'], 'top')
        entries = once['bar']['layout']['right']
        self.assertEqual([e['id'] for e in entries], [
            'ok-extras.desktop-label', 'omarchy.screen-time', 'ok-extras.apps', 'omarchy.audio'])
        self.assertEqual(entries[1]['custom'], 42)

    def test_upgrade_without_native_time_does_not_enable_it(self):
        result = configure_ui.configure({})
        self.assertEqual([e['id'] for e in result['bar']['layout']['right']], ['ok-extras.apps'])


if __name__ == '__main__':
    unittest.main()
