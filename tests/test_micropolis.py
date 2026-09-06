import datetime as dt
import unittest

from kids_policy.budget import Policy, empty_day
from kids_policy.classify import classify
from kids_policy.migrate import default_config


class MicropolisTests(unittest.TestCase):
    def test_independent_thirty_minutes_and_persistence(self):
        now = dt.datetime(2026, 9, 6, 12)
        config = default_config()
        policy = Policy(empty_day(str(now.date())), config, now, 0)
        policy.tick(now, 0, {'micropolis'})
        blocked, _ = policy.tick(now, 1800, {'micropolis'})
        self.assertIn('micropolis', blocked)
        self.assertEqual(policy.remaining('micropolis'), 0)
        self.assertEqual(policy.remaining('digger'), 600)
        self.assertEqual(policy.remaining('vlc'), 3600)
        restored = Policy(policy.apply_snapshot_usage(), config, now, 1800)
        self.assertEqual(restored.remaining('micropolis'), 0)
        tomorrow = now + dt.timedelta(days=1)
        restored.tick(tomorrow, 1801, set())
        self.assertEqual(restored.remaining('micropolis'), 1800)

    def test_java_process_classification(self):
        self.assertEqual(classify('java', '/usr/bin/java', 'java -cp /opt/micropolis-2.0.0/lib/micropolis-2.0.0.jar micropolisj.Micropolis'), 'micropolis')
        self.assertIsNone(classify('java', '/usr/bin/java', 'java unrelated.App'))

    def test_extension_targets_only_micropolis(self):
        now = dt.datetime(2026, 9, 6, 12)
        state = empty_day(str(now.date()))
        state['grants'] = [{'id': 'one', 'kind': 'minutes', 'date': str(now.date()),
                            'child_uid': 1000, 'approver': 'parent', 'created_at': now.isoformat(),
                            'budget': 'micropolis', 'minutes': 15}]
        policy = Policy(state, default_config(), now, 0)
        self.assertEqual(policy.remaining('micropolis'), 2700)
        self.assertEqual(policy.remaining('shared'), 3600)
        self.assertEqual(policy.remaining('digger'), 600)

    def test_school_time_blocks_micropolis(self):
        now = dt.datetime(2026, 9, 7, 10)
        config = default_config()
        config['play_windows']['weekday'] = {'start': '14:00', 'end': '21:00'}
        policy = Policy(empty_day(str(now.date())), config, now, 0)
        blocked, _ = policy.tick(now, 0, {'micropolis'})
        self.assertIn('micropolis', blocked)
