import datetime as dt
import unittest

from kids_policy.schedule import in_play_window, minutes_until_cutoff, next_open_label


WINDOWS = {
    'weekday': {'start': '09:00', 'end': '21:00'},
    'weekend': {'start': '08:00', 'end': '21:00'},
}


class ScheduleTests(unittest.TestCase):
    def test_weekday_bounds(self):
        monday = dt.datetime(2026, 9, 7, 9, 0)
        self.assertTrue(in_play_window(monday, WINDOWS))
        self.assertFalse(in_play_window(dt.datetime(2026, 9, 7, 8, 59), WINDOWS))
        self.assertFalse(in_play_window(dt.datetime(2026, 9, 7, 21, 0), WINDOWS))
        self.assertTrue(in_play_window(dt.datetime(2026, 9, 7, 20, 59), WINDOWS))

    def test_weekend_opens_earlier(self):
        self.assertTrue(in_play_window(dt.datetime(2026, 9, 5, 8, 0), WINDOWS))
        self.assertFalse(in_play_window(dt.datetime(2026, 9, 5, 7, 59), WINDOWS))
        self.assertFalse(in_play_window(dt.datetime(2026, 9, 5, 22, 9), WINDOWS))

    def test_cutoff_countdown(self):
        now = dt.datetime(2026, 9, 5, 20, 55)
        self.assertEqual(minutes_until_cutoff(now, WINDOWS), 5)

    def test_next_open_after_saturday_cutoff(self):
        self.assertEqual(next_open_label(dt.datetime(2026, 9, 5, 21, 5), WINDOWS), 'Sunday 08:00')
