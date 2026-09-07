import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from kids_policy import ALLOWLIST_SCHEMA, POLICY_SCHEMA
from kids_policy.configver import migrate_allowlist, migrate_policy


class ConfigVerTests(unittest.TestCase):
    def test_allowlist_list_becomes_categories(self):
        migrated, changed = migrate_allowlist(['digger', 'vlc'])
        self.assertTrue(changed)
        self.assertEqual(migrated['schema_version'], ALLOWLIST_SCHEMA)
        self.assertEqual(migrated['games'], ['digger', 'vlc'])
        self.assertEqual(migrated['videos'], [])

    def test_allowlist_current_is_stable(self):
        data = {'schema_version': ALLOWLIST_SCHEMA, 'games': ['digger'], 'videos': ['vlc'], 'tools': ['screentime']}
        migrated, changed = migrate_allowlist(data)
        self.assertFalse(changed)
        self.assertEqual(migrated['games'], ['digger'])

    def test_policy_fills_vlc_minutes(self):
        migrated, changed = migrate_policy({'schema_version': 2, 'shared_daily_minutes': 45, 'child_uid': 1000})
        self.assertTrue(changed)
        self.assertEqual(migrated['schema_version'], POLICY_SCHEMA)
        self.assertEqual(migrated['shared_daily_minutes'], 45)
        self.assertEqual(migrated['vlc_daily_minutes'], 60)
