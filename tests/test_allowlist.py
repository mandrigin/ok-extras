import unittest

from kids_policy.allowlist import is_allowed_window, is_session


from tests.fixtures import default_config
CONFIG = default_config()


class AllowlistTests(unittest.TestCase):
    def test_session_kept(self):
        self.assertTrue(is_session(class_name='Hyprland'))
        self.assertTrue(is_allowed_window(CONFIG, class_name='quickshell'))

    def test_allowed_game(self):
        self.assertTrue(is_allowed_window(CONFIG, title='D I G G E R', class_name='digger'))
        self.assertTrue(is_allowed_window(CONFIG, class_name='vlc'))

    def test_forbidden_app(self):
        self.assertFalse(is_allowed_window(CONFIG, title='YouTube', class_name='chromium'))
        self.assertFalse(is_allowed_window(CONFIG, class_name='discord'))
        self.assertFalse(is_allowed_window(CONFIG, class_name='foot'))
