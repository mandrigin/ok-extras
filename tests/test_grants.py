import datetime as dt
import unittest

from kids_policy.grants import Grant, extra_seconds, revoke_grant, upsert_grant


class GrantTests(unittest.TestCase):
    def test_idempotent_id(self):
        grant = Grant('g1', 'minutes', '2026-09-05', 1000, 'root', 't', minutes=15, budget='shared')
        grants, stored, created = upsert_grant([], grant)
        self.assertTrue(created)
        grants, stored, created = upsert_grant(grants, grant)
        self.assertFalse(created)
        self.assertEqual(len(grants), 1)
        self.assertEqual(extra_seconds(grants, 'shared', '2026-09-05'), 900)

    def test_revoke(self):
        grant = Grant('g1', 'minutes', '2026-09-05', 1000, 'root', 't', minutes=15, budget='shared')
        grants, _stored, _created = upsert_grant([], grant)
        grants, removed = revoke_grant(grants, 'g1')
        self.assertTrue(removed)
        self.assertEqual(extra_seconds(grants, 'shared', '2026-09-05'), 0)
