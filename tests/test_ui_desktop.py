"""Run under xvfb-run to exercise real Tk widgets without a child session."""
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

AVAILABLE = os.environ.get('OK_EXTRAS_UI_TEST') == '1' and bool(os.environ.get('DISPLAY')) and importlib.util.find_spec('PIL') is not None


@unittest.skipUnless(AVAILABLE, 'needs DISPLAY, Tk and Pillow (run with xvfb-run)')
class DesktopTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        from PIL import Image
        from kids_policy import ui
        self.tk, self.module = tk, ui
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.state = {'updated_at': dt.datetime.now().isoformat(), 'digger_remaining_seconds': 0,
                      'remaining_seconds': 3600, 'vlc_remaining_seconds': 1200, 'play_allowed': True,
                      'enabled_apps': ['digger', 'vlc'], 'free_minute_available': True,
                      'extra_minute_tiers': [15, 30, 60], 'play_windows': {},
                      'app_status': {'digger': {'blocked': True, 'reason': 'Digger daily limit reached', 'code': 'limit'},
                                     'vlc': {'blocked': False, 'reason': '', 'code': ''}}}
        self.statefile = self.path / 'usage.json'
        self.statefile.write_text(json.dumps(self.state))
        self.patch(ui, 'USAGE', self.statefile)
        self.patch(ui, 'CONFIG', self.path / 'missing-config')
        self.patch(ui, 'ALLOWLIST', self.path / 'missing-allowlist')
        self.game = {'address': '0xabc', 'title': 'D I G G E R', 'class': 'digger',
                     'at': [30, 30], 'size': [900, 600], 'floating': True, 'fullscreen': 0}
        self.video = {'address': '0xdef', 'title': 'VLC', 'class': 'vlc',
                      'at': [1000, 50], 'size': [300, 200], 'floating': True, 'fullscreen': 0}
        self.windows = self.patch(ui, 'clients', return_value=[self.game, self.video])
        self.dispatch = self.patch(ui, 'dispatch')
        self.root = tk.Tk()
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.sock.setblocking(False)
        self.sock.bind(str(self.path / 'ui.sock'))
        self.desktop = ui.DesktopUI(self.root, self.sock)
        self.desktop.state = self.state
        self.desktop.cache = self.path
        self.desktop.size_games = lambda windows: None
        preview = self.path / 'digger.png'
        Image.new('RGB', (1350, 900), '#00a050').save(preview)
        self.capture = self.patch(self.desktop, 'capture', return_value=preview)

    def patch(self, obj, name, *args, **kwargs):
        p = patch.object(obj, name, *args, **kwargs)
        self.addCleanup(p.stop)
        return p.start()

    def tearDown(self):
        self.desktop.pool.shutdown(wait=True)
        for timer in self.root.tk.call('after', 'info'):
            self.root.tk.call('after', 'cancel', timer)
        self.root.update_idletasks()
        self.root.destroy()
        self.sock.close()

    def widgets(self, widget=None):
        widget = widget or self.root
        result = []
        for child in widget.winfo_children():
            result.append(child)
            result += self.widgets(child)
        return result

    def button_texts(self):
        return [w.cget('text') for w in self.widgets() if w.winfo_class() == 'TButton']

    def test_running_game_has_gray_preview_and_parent_controls(self):
        self.desktop.show_blocked('digger')
        self.root.update()
        time.sleep(0.2)
        self.root.update()
        self.assertEqual(self.desktop.overlay_app, 'digger')
        self.assertEqual(self.desktop.photo.width(), 900)
        self.assertIn('1 more minute', self.button_texts())
        self.assertIn('+15 min', self.button_texts())
        hidden = [c.args[1]['address'] for c in self.dispatch.call_args_list if c.args[0] == 'move' and c.kwargs.get('x') == 8000]
        self.assertIn('0xabc', hidden)
        self.assertNotIn('0xdef', hidden)
        # Retain a real X11 rendering for visual inspection outside the test run.
        from PIL import ImageGrab
        ImageGrab.grab().save('/tmp/ok-extras-overlay.png')

    def test_denied_launch_shows_controls_without_a_game_process(self):
        self.windows.return_value = []
        def run(command, callback):
            self.assertEqual(command, ['sudo', '-n', '/usr/bin/omarchy-kids-launch', 'digger'])
            callback(subprocess.CompletedProcess(command, 1, '', 'Digger daily limit reached'))
        self.desktop.background = run
        self.desktop.launch('digger')
        self.root.update()
        self.assertIsNotNone(self.desktop.overlay)
        self.assertTrue(self.desktop.retry)
        self.assertIn('+30 min', self.button_texts())

    def test_parent_grant_targets_only_digger_and_uses_polkit(self):
        commands = []
        self.desktop.background = lambda command, callback: commands.append(command)
        self.desktop.grant('digger', 15)
        self.assertEqual(commands[0][:5], ['pkexec', '/usr/bin/omarchy-kids-grant', '--budget', 'digger', '--minutes'])
        self.assertNotIn('all', commands[0])
        self.assertTrue(self.desktop.busy)

    def test_free_minute_uses_restricted_helper(self):
        commands = []
        self.desktop.background = lambda command, callback: commands.append(command)
        self.desktop.grant('vlc')
        self.assertEqual(commands[0], ['sudo', '-n', '/usr/bin/omarchy-kids-grant', '--free-minute', '--budget', 'vlc'])

    def test_bedtime_buttons_are_explicit_and_require_parent_authentication(self):
        self.state['desktop'] = {'phase': 'bedtime', 'remaining_seconds': 2100,
                                 'blocked_label': 'Weekend downtime'}
        self.state['app_status']['digger'] = {'blocked': True, 'reason': 'Desktop blocked: Weekend downtime',
                                             'code': 'desktop_bedtime'}
        self.statefile.write_text(json.dumps(self.state))
        self.desktop.show_dashboard('digger')
        self.desktop.show_blocked('digger')
        self.root.update()
        self.assertNotIn('1 more minute', self.button_texts())
        self.assertNotIn('+15 min', self.button_texts())
        self.assertIn('Allow 15 min past bedtime', self.button_texts())
        self.assertIn('35:00', self.desktop.desktop_label.cget('text'))
        self.assertIn('Weekend downtime', self.desktop.desktop_label.cget('text'))
        commands = []
        self.desktop.background = lambda command, callback: commands.append(command)
        button = next(w for w in self.widgets() if w.winfo_class() == 'TButton' and w.cget('text') == 'Allow 15 min past bedtime')
        button.invoke()
        self.assertEqual(commands[0][0], 'pkexec')
        self.assertIn('--with-desktop', commands[0])
        self.assertIn('--after-bedtime', commands[0])
        from PIL import ImageGrab
        ImageGrab.grab().save('/tmp/ok-extras-bedtime.png')

    def test_desktop_block_keeps_controls_open_even_after_app_grant(self):
        self.state['app_status']['digger'] = {'blocked': True, 'reason': 'Desktop time is up', 'code': 'desktop_limit'}
        self.statefile.write_text(json.dumps(self.state))
        self.desktop.show_blocked('digger')
        self.desktop.background = lambda command, callback: callback(subprocess.CompletedProcess(command, 0, '', ''))
        self.desktop.grant('digger', 15)
        self.assertIsNotNone(self.desktop.overlay)

    def test_successful_extension_closes_controls_restores_and_focuses_game(self):
        hypr = self.patch(self.module, 'hypr')
        self.desktop.show_dashboard('digger')
        self.desktop.show_blocked('digger')
        def grant(command, callback):
            self.state['app_status']['digger']['blocked'] = False
            self.state['digger_remaining_seconds'] = 900
            self.statefile.write_text(json.dumps(self.state))
            callback(subprocess.CompletedProcess(command, 0, '', ''))
        self.desktop.background = grant
        self.desktop.grant('digger', 15)
        self.assertIsNone(self.desktop.dashboard)
        self.assertIsNone(self.desktop.overlay)
        self.dispatch.assert_any_call('move', self.game, x=30, y=30)
        hypr.assert_called_with('dispatch', 'hl.dsp.focus({ window = "address:0xabc" })')

    def test_canceled_auth_keeps_controls_and_does_not_focus_game(self):
        hypr = self.patch(self.module, 'hypr')
        self.desktop.show_dashboard('digger')
        self.desktop.show_blocked('digger')
        self.desktop.background = lambda command, callback: callback(subprocess.CompletedProcess(command, 126, '', ''))
        self.desktop.grant('digger', 15)
        self.assertIsNotNone(self.desktop.dashboard)
        self.assertIsNotNone(self.desktop.overlay)
        self.assertEqual(self.desktop.overlay_message.cget('text'), 'No extra time was added.')
        self.assertFalse(self.desktop.busy)
        hypr.assert_not_called()

    def test_extension_cannot_dismiss_schedule_block(self):
        self.desktop.show_blocked('digger')
        self.desktop.background = lambda command, callback: callback(subprocess.CompletedProcess(command, 0, '', ''))
        self.desktop.grant('digger', 15)
        self.assertIsNotNone(self.desktop.overlay)
        self.assertIn('still blocked', self.desktop.overlay_message.cget('text'))

    def test_dashboard_lists_enabled_apps_and_removes_used_free_minute(self):
        self.windows.return_value = []
        self.desktop.show_dashboard('digger')
        self.assertEqual(set(self.desktop.rows), {'digger', 'vlc'})
        self.assertIn('1 more minute', self.button_texts())
        self.state['free_minute_available'] = False
        self.statefile.write_text(json.dumps(self.state))
        self.desktop.refresh()
        self.assertNotIn('1 more minute', self.button_texts())
        self.root.update()
        from PIL import ImageGrab
        ImageGrab.grab().save('/tmp/ok-extras-dashboard.png')

    def test_non_budget_launch_error_does_not_loop_or_disappear(self):
        self.windows.return_value = []
        self.state['app_status']['digger']['blocked'] = False
        self.state['digger_remaining_seconds'] = 100
        self.statefile.write_text(json.dumps(self.state))
        self.desktop.state = self.state
        self.desktop.show_blocked('digger', 'Digger is not installed', retry=True)
        self.desktop.launch = lambda app: self.fail('a failed executable must not be retried automatically')
        self.desktop.refresh()
        self.assertIsNotNone(self.desktop.overlay)
        self.assertFalse(self.desktop.waiting_for_allowance)


if __name__ == '__main__':
    unittest.main()
