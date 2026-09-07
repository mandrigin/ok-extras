import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from kids_policy import ALLOWLIST_SCHEMA, POLICY_SCHEMA
from kids_policy.configver import backup, load_or_migrate, migrate_allowlist, migrate_policy


class ConfigVerTests(unittest.TestCase):
    def test_invalid_existing_config_is_never_replaced_with_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'policy.json'
            for content in ('{"apps":', 'null'):
                path.write_text(content)
                with self.assertRaises(ValueError):
                    load_or_migrate(path, 'policy', migrate_policy)
                self.assertEqual(path.read_text(), content)

    def test_legacy_list_is_backed_up_before_migration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'allowlist.json'
            path.write_text('["drawing"]')
            with mock.patch('kids_policy.configver.HISTORY', root / 'history'):
                migrated = load_or_migrate(path, 'allowlist', migrate_allowlist)
            self.assertEqual(migrated['games'], ['drawing'])
            saved = list((root / 'history').glob('*'))
            self.assertEqual(len(saved), 1)
            self.assertEqual(json.loads(saved[0].read_text()), ['drawing'])

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
        self.assertEqual(migrated['budgets']['shared']['daily_minutes'], 45)
        self.assertEqual(migrated['budgets']['vlc']['daily_minutes'], 60)
