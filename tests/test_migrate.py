import unittest

from kids_policy.migrate import migrate_state


class MigrateTests(unittest.TestCase):
    def test_v1_splits_digger(self):
        saved = {
            'date': '2026-09-05',
            'apps': {'digger': 600, 'minecraft': 12},
            'categories': {'games': 612},
            'shared_used_seconds': 12,
            'digger_used_seconds': 600,
        }
        state = migrate_state(saved)
        self.assertEqual(state['schema_version'], 2)
        self.assertEqual(state['digger_used_seconds'], 600)
        self.assertEqual(state['shared_used_seconds'], 12)
        self.assertEqual(state['grants'], [])
