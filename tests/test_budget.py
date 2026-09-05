import datetime as dt
import unittest

from kids_policy.budget import Policy
from kids_policy.migrate import default_config, migrate_state


class BudgetTests(unittest.TestCase):
    now = dt.datetime(2026, 9, 5, 12)
    config = default_config()

    def policy(self, saved=None, now=None, mono=0):
        return Policy(migrate_state(saved or {'date': str(self.now.date())}), self.config, now or self.now, mono)

    def test_shared_overlap_charges_once(self):
        policy = self.policy()
        policy.tick(self.now, 0, {'minecraft'})
        blocked, _reasons = policy.tick(self.now, 1800, {'minecraft', 'stardew_valley'})
        self.assertFalse(blocked)
        blocked, _reasons = policy.tick(self.now, 3600, {'minecraft', 'stardew_valley'})
        self.assertEqual(blocked, {'minecraft', 'stardew_valley'})
        self.assertEqual(policy.shared.used, 3600)
        self.assertEqual(sum(policy.apps.values()), 3600)

    def test_digger_independent(self):
        policy = self.policy()
        policy.tick(self.now, 0, {'digger', 'minecraft'})
        blocked, _reasons = policy.tick(self.now, 600, {'digger', 'minecraft'})
        self.assertEqual(blocked, {'digger'})
        self.assertEqual(policy.remaining('digger'), 0)
        self.assertEqual(policy.remaining('shared'), 3000)

    def test_vlc_is_not_charged(self):
        policy = self.policy()
        policy.tick(self.now, 0, {'vlc'})
        policy.tick(self.now, 1200, {'vlc'})
        self.assertEqual(policy.shared.used, 0)
        self.assertEqual(policy.digger.used, 0)

    def test_clock_rollback_does_not_reset(self):
        saved = {'date': '2026-09-05', 'shared_used_seconds': 3600, 'digger_used_seconds': 0, 'schema_version': 2}
        policy = Policy(saved, self.config, dt.datetime(2026, 9, 4, 12), 0)
        self.assertEqual(policy.state['date'], '2026-09-05')
        self.assertEqual(policy.shared.used, 3600)

    def test_next_day_resets(self):
        saved = {'date': '2026-09-05', 'shared_used_seconds': 3600, 'digger_used_seconds': 600, 'schema_version': 2}
        policy = Policy(saved, self.config, dt.datetime(2026, 9, 6, 12), 0)
        self.assertEqual(policy.shared.used, 0)
        self.assertEqual(policy.digger.used, 0)

    def test_bedtime_zeros_unused_limits(self):
        now = dt.datetime(2026, 9, 5, 21, 5)
        policy = self.policy(now=now)
        blocked, reasons = policy.tick(now, 10, {'digger', 'vlc'})
        self.assertIn('vlc', blocked)
        self.assertIn('digger', blocked)
        self.assertIn('minecraft', blocked)
        self.assertEqual(policy.remaining('digger'), 0)
        self.assertEqual(policy.remaining('shared'), 0)
        self.assertEqual(policy.digger.used, 600)
        self.assertEqual(policy.shared.used, 3600)
        self.assertTrue(any('bedtime' in reason.lower() or 'limit' in reason.lower() for reason in reasons))

    def test_minute_grant_extends_shared_only(self):
        saved = {
            'date': '2026-09-05',
            'schema_version': 2,
            'shared_used_seconds': 3600,
            'digger_used_seconds': 0,
            'grants': [{
                'id': 'g1', 'kind': 'minutes', 'minutes': 15, 'budget': 'shared',
                'date': '2026-09-05', 'child_uid': 1000, 'approver': 'root', 'created_at': 't',
            }],
        }
        policy = Policy(saved, self.config, self.now, 0)
        self.assertEqual(policy.remaining('shared'), 900)
        blocked, _reasons = policy.tick(self.now, 0, {'minecraft'})
        self.assertNotIn('minecraft', blocked)

    def test_minutes_at_bedtime_use_same_engine(self):
        now = dt.datetime(2026, 9, 5, 21, 5)
        saved = {
            'date': '2026-09-05',
            'schema_version': 2,
            'shared_used_seconds': 0,
            'digger_used_seconds': 0,
            'grants': [{
                'id': 'g1', 'kind': 'minutes', 'minutes': 1, 'budget': 'all',
                'date': '2026-09-05', 'child_uid': 1000, 'approver': 'root', 'created_at': 't',
            }],
        }
        policy = Policy(saved, self.config, now, 0)
        blocked, _reasons = policy.tick(now, 0, {'minecraft', 'digger', 'vlc'})
        self.assertEqual(policy.remaining('shared'), 60)
        self.assertEqual(policy.remaining('digger'), 60)
        self.assertNotIn('minecraft', blocked)
        self.assertNotIn('digger', blocked)
        self.assertNotIn('vlc', blocked)
        blocked, _reasons = policy.tick(now, 60, {'minecraft'})
        self.assertIn('minecraft', blocked)
        self.assertEqual(policy.remaining('shared'), 0)
