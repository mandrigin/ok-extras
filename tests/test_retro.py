import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest

from kids_policy.budget import Policy, empty_day
from tests.fixtures import classify
from tests.fixtures import default_config
from tests.fixtures import window_app
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'extensions/retro'))
from retro import import_rom, refresh_playlist


class RetroBudgetTests(unittest.TestCase):
    def test_shared_emulator_time_is_independent_and_survives_restart(self):
        now = dt.datetime(2026, 9, 6, 12)
        policy = Policy(empty_day(str(now.date())), default_config(), now, 0)
        policy.tick(now, 0, {'retro'})
        blocked, _ = policy.tick(now, 1800, {'retro'})
        self.assertIn('retro', blocked)
        self.assertEqual(policy.remaining('micropolis'), 1800)
        self.assertEqual(policy.remaining('digger'), 600)
        self.assertEqual(policy.remaining('vlc'), 3600)
        restarted = Policy(policy.apply_snapshot_usage(), default_config(), now, 1800)
        self.assertEqual(restarted.remaining('retro'), 0)
        restarted.tick(now + dt.timedelta(days=1), 1801, set())
        self.assertEqual(restarted.remaining('retro'), 1800)

    def test_all_cores_and_games_are_counted_as_retro(self):
        for command in ('retroarch -L genesis_plus_gx.so lion_king.md', 'retroarch -L nestopia.so mario.nes', 'retroarch --menu'):
            self.assertEqual(classify('retroarch', '/usr/bin/retroarch', command), 'retro')
        self.assertEqual(window_app({'class': 'retroarch', 'title': 'The Lion King'}), 'retro')

    def test_school_schedule_blocks_emulation(self):
        now = dt.datetime(2026, 9, 7, 10)
        config = default_config()
        config['play_windows']['weekday'] = {'start': '14:00', 'end': '21:00'}
        policy = Policy(empty_day(str(now.date())), config, now, 0)
        self.assertIn('retro', policy.tick(now, 0, {'retro'})[0])


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.library = self.path / 'library'
        self.library.mkdir()
        self.source = self.path / 'my-dump.nes'
        self.source.write_bytes(b'NES\x1a' + b'\0' * 12)

    def test_nes_import_preserves_source_and_selects_nes_core(self):
        target = import_rom('super_mario_bros', self.source, self.library)
        self.assertEqual(target.read_bytes(), self.source.read_bytes())
        self.assertEqual(target.stat().st_mode & 0o777, 0o644)
        playlist = json.loads((self.library/'playlists/Retro Games.lpl').read_text())
        self.assertEqual(len(playlist['items']), 1)
        self.assertEqual(playlist['items'][0]['core_name'], 'Nestopia')
        self.assertEqual(playlist['items'][0]['path'], str(target))

    def test_duplicate_import_never_overwrites_game(self):
        target = import_rom('super_mario_bros', self.source, self.library)
        original = target.read_bytes()
        self.source.write_bytes(original + b'different')
        with self.assertRaisesRegex(ValueError, 'already imported'):
            import_rom('super_mario_bros', self.source, self.library)
        self.assertEqual(target.read_bytes(), original)

    def test_invalid_id_wrong_core_and_bad_header_are_rejected(self):
        for game in ('../escape', 'bad/name'):
            with self.assertRaises(ValueError):
                import_rom(game, self.source, self.library)
        with self.assertRaises(ValueError):
            import_rom('new_title', self.source, self.library, core='genesis_plus_gx')
        self.source.write_bytes(b'not a nes header')
        with self.assertRaisesRegex(ValueError, 'iNES'):
            import_rom('super_mario_bros', self.source, self.library)
        self.assertEqual(refresh_playlist(self.library), [])
