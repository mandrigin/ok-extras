"""Desktop presentation; launches and grants always go through root helpers."""
import concurrent.futures
import fcntl
import json
import logging
import os
from pathlib import Path
import socket
import subprocess
import time
import tkinter as tk
from tkinter import ttk
import uuid

from PIL import Image, ImageEnhance, ImageOps, ImageTk
from kids_policy.paths import ALLOWLIST, CONFIG, USAGE
from kids_policy.presentation import definitions, app_view, enabled_apps, fmt, fresh, window_app, needs_schedule_approval
from kids_policy.store import read_json
from kids_policy.ui_client import runtime

LOG = logging.getLogger('kids-ui')


def hypr(*args):
    result = subprocess.run(['hyprctl', *args], capture_output=True, text=True, timeout=3)
    return result.stdout


def clients():
    try:
        return json.loads(hypr('-j', 'clients'))
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return []


def dispatch(name, window, **values):
    values = {'window': 'address:' + window['address'], **values}
    fields = ', '.join(f'{key} = {json.dumps(value)}' for key, value in values.items())
    try:
        hypr('dispatch', f'hl.dsp.window.{name}({{ {fields} }})')
    except (OSError, subprocess.TimeoutExpired):
        LOG.exception('Could not position a window')


class DesktopUI:
    def __init__(self, root, sock):
        self.root, self.sock = root, sock
        root.withdraw()
        root.title('Omarchy Kids Screen Time')
        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        self.jobs, self.buttons = [], []
        # Existing games keep their position when the UI is upgraded mid-session.
        self.pending, self.sized = set(), {w['address']: None for w in clients()}
        self.busy = False
        self.grant_mode = False
        self.state = read_json(USAGE, {}) or {}
        self.dashboard, self.overlay, self.overlay_app = None, None, None
        self.rows, self.hidden = {}, []
        self.last_free, self.last_capture = None, 0
        self.cache = Path.home() / '.cache/omarchy-kids/previews'
        self.cache.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.selected = None
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('.', background='#222532', foreground='#f1f2f6', font=('DejaVu Sans', 12))
        style.configure('TButton', padding=(12, 8), background='#34394b')
        style.map('TButton', background=[('active', '#48516b')])
        self.root.after(0, self.refresh)

    def background(self, command, callback):
        def run():
            try:
                return subprocess.run(command, capture_output=True, text=True, timeout=180)
            except (OSError, subprocess.TimeoutExpired) as exc:
                return subprocess.CompletedProcess(command, 1, '', str(exc))
        self.jobs.append((self.pool.submit(run), callback))

    def launch(self, app):
        if app not in definitions(self.state) or app in self.pending:
            return
        self.pending.add(app)

        def done(result):
            self.pending.discard(app)
            if result.returncode:
                self.state = read_json(USAGE, {}) or {}
                reason = (result.stderr or result.stdout).strip() or 'The app could not start.'
                self.show_blocked(app, reason, retry=True)
            elif self.overlay_app == app:
                self.dismiss()
        self.background(['sudo', '-n', '/usr/bin/omarchy-kids-launch', app], done)

    def grant(self, app, minutes=None, after_bedtime=False):
        if self.busy:
            return
        if app not in definitions(self.state):
            self.show_message('This app is no longer configured.')
            return
        budget = definitions(self.state)[app].get('budget')
        schedule_only = app_view(self.state, app)['unlimited']
        if schedule_only and (not after_bedtime or minutes is None):
            self.show_message('This app has no daily limit.')
            return
        if minutes is None:
            command = ['sudo', '-n', '/usr/bin/omarchy-kids-free-minute', budget]
        else:
            command = ['pkexec', '/usr/bin/omarchy-kids-grant', '--minutes', str(minutes),
                       '--id', str(uuid.uuid4()), '--with-desktop']
            command += ['--schedule-only'] if schedule_only else ['--budget', budget]
            if after_bedtime:
                command.append('--after-bedtime')
        self.busy = True
        self.update_buttons()

        def done(result):
            self.busy = False
            self.update_buttons()
            if result.returncode:
                message = (result.stderr or result.stdout).strip() or 'No extra time was added.'
                self.show_message(message)
            else:
                self.state = read_json(USAGE, {}) or {}
                if not app_view(self.state, app)['blocked']:
                    self.return_to_game(app)
                else:
                    self.show_message('Time added, but this app is still blocked by the current schedule or allow-list.')
        self.background(command, done)

    def return_to_game(self, app):
        retry = self.overlay_app == app and self.retry
        if self.dashboard is not None:
            self.close_dashboard()
        if self.overlay_app == app:
            self.dismiss()
        matching = [w for w in clients() if window_app(w, self.state) == app]
        if matching:
            window = matching[0]
            dispatch('alter_zorder', window, mode='top')
            try:
                selector = json.dumps('address:' + window['address'])
                hypr('dispatch', 'hl.dsp.focus({ window = ' + selector + ' })')
            except (OSError, subprocess.TimeoutExpired):
                LOG.exception('Could not focus resumed game')
        elif retry:
            self.launch(app)

    def update_buttons(self):
        self.buttons = [button for button in self.buttons if button.winfo_exists()]
        for button in self.buttons:
            button.configure(state='disabled' if self.busy else 'normal')

    def show_message(self, message):
        if self.overlay is not None:
            self.overlay_message.configure(text=message[:300])
        if self.dashboard is not None:
            self.dashboard_message.configure(text=message[:300])

    def grant_buttons(self, parent, app):
        if app_view(self.state, app)['unlimited'] and not needs_schedule_approval(self.state, app):
            ttk.Label(parent, text='No daily app limit. The desktop schedule still applies.').pack()
            return
        desktop = self.state.get('desktop', {})
        outside = needs_schedule_approval(self.state, app)
        self.grant_mode = outside
        frame = ttk.Frame(parent)
        frame.pack(pady=8)
        if self.state.get('free_minute_available', False) and not outside and desktop.get('remaining_seconds', 60) > 0:
            button = ttk.Button(frame, text='1 more minute', command=lambda: self.grant(app))
            button.pack(side='left', padx=4)
            self.buttons.append(button)
        text = ('Outside allowed hours. Parent approval overrides bedtime for this interval only.' if outside
                else 'Ask a parent: adds app time and ensures enough desktop time.')
        ttk.Label(parent, text=text, wraplength=530).pack(pady=(8, 0))
        frame = ttk.Frame(parent)
        frame.pack(pady=8)
        for minutes in (self.state.get('extra_minute_tiers') or [15, 30, 60])[:3]:
            button = ttk.Button(frame, text=f'Allow {minutes} min past bedtime' if outside else f'+{minutes} min',
                                command=lambda m=minutes: self.grant(app, m, after_bedtime=outside))
            button.pack(side='top' if outside else 'left', padx=4, pady=2)
            self.buttons.append(button)
        self.update_buttons()

    def show_dashboard(self, selected=None):
        self.selected = selected or self.selected
        if self.dashboard is not None:
            self.dashboard.destroy()
        self.dashboard = window = tk.Toplevel(self.root)
        self.dashboard_free = self.state.get('free_minute_available')
        window.title('Omarchy Kids · App allowances')
        window.geometry('760x850')
        window.protocol('WM_DELETE_WINDOW', self.close_dashboard)
        body = ttk.Frame(window, padding=24)
        body.pack(fill='both', expand=True)
        ttk.Label(body, text='App allowances', font=('sans', 22, 'bold')).pack(anchor='w')
        self.desktop_label = ttk.Label(body, wraplength=570)
        self.desktop_label.pack(anchor='w', pady=12)
        apps = self.state.get('enabled_apps', enabled_apps(read_json(ALLOWLIST, {}) or {}))
        if self.selected not in apps:
            self.selected = next(iter(apps), None)
        self.rows = {}
        list_area = ttk.Frame(body)
        list_area.pack(fill='x', pady=4)
        canvas = tk.Canvas(list_area, height=min(240, max(60, 48 * len(apps))), background='#222532', highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_area, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side='left', fill='both', expand=True)
        app_rows = ttk.Frame(canvas)
        item = canvas.create_window((0, 0), window=app_rows, anchor='nw')
        def fit_rows(event):
            canvas.configure(scrollregion=canvas.bbox('all'), height=min(240, max(60, event.height)))
            if event.height > 240:
                scrollbar.pack(side='right', fill='y')
            else:
                scrollbar.pack_forget()
        app_rows.bind('<Configure>', fit_rows)
        canvas.bind('<Configure>', lambda event: canvas.itemconfigure(item, width=event.width))
        for app in apps:
            if app not in definitions(self.state):
                continue
            row = ttk.Frame(app_rows)
            row.pack(fill='x', pady=6)
            label = ttk.Label(row, font=('sans', 16, 'bold'))
            label.pack(side='left')
            self.rows[app] = label
            ttk.Button(row, text='Controls' if app_view(self.state, app)['unlimited'] else 'Extra time', command=lambda a=app: self.show_dashboard(a)).pack(side='right')
        self.schedule_label = ttk.Label(body, wraplength=570)
        self.schedule_label.pack(anchor='w', pady=12)
        if self.selected in definitions(self.state):
            group = ttk.LabelFrame(body, text=definitions(self.state)[self.selected]['label'], padding=12)
            group.pack(fill='x', pady=8)
            self.grant_buttons(group, self.selected)
            ttk.Button(group, text='Open ' + definitions(self.state)[self.selected]['label'], command=lambda: self.launch(self.selected)).pack(pady=6)
        self.dashboard_message = ttk.Label(body, wraplength=570)
        self.dashboard_message.pack(pady=10)
        self.update_dashboard()
        window.lift()
        def position():
            if self.dashboard is not window:
                return
            for candidate in clients():
                if candidate.get('title') == 'Omarchy Kids · App allowances':
                    if not candidate.get('floating'):
                        dispatch('float', candidate, action='toggle')
                    dispatch('resize', candidate, x=760, y=850)
                    dispatch('center', candidate)
        window.after(150, position)

    def close_dashboard(self):
        self.dashboard.destroy()
        self.dashboard = None

    def update_dashboard(self):
        if self.dashboard is None:
            return
        desktop = self.state.get('desktop', {})
        left = desktop.get('remaining_seconds')
        note = desktop.get('error') or ('Blocked: ' + desktop.get('blocked_label', 'Bedtime')
                                       if desktop.get('phase') == 'bedtime' else '')
        if desktop.get('extension_until'):
            note = 'Parent approved play until ' + time.strftime('%H:%M', time.localtime(desktop['extension_until']))
        budgets = desktop.get('budget_minutes', {})
        unlimited = len(budgets) == 7 and all(value == 1440 for value in budgets.values())
        caption = 'Desktop: unlimited within allowed hours. ' if unlimited else (f'Desktop: {fmt(left)} remaining. ' if left is not None else '')
        self.desktop_label.configure(text=caption + note)
        for app, row in self.rows.items():
            view = app_view(self.state, app)
            row.configure(text=f"{view['label']}: {fmt(view['remaining'])}" + (' · blocked' if view['blocked'] else ''))
        windows = self.state.get('play_windows', (read_json(CONFIG, {}) or {}).get('play_windows', {}))
        if windows and all(value['start'] == value['end'] for value in windows.values()):
            schedule = 'Apps follow the desktop schedule.'
        else:
            schedule = '\n'.join(f"{'Weekday' if key == 'weekday' else 'Weekend'} app hours: {value['start']}–{value['end']}"
                                 for key, value in windows.items())
        self.schedule_label.configure(text=schedule)
        if not fresh(self.state):
            self.dashboard_message.configure(text='Waiting for the time service. Displayed allowances may be out of date.')

    def capture(self, app, window):
        x, y = window['at']
        width, height = window['size']
        if width < 1 or height < 1 or x > 4000:
            return None
        path = self.cache / (app + '.png')
        stage = path.with_suffix('.new.png')
        try:
            result = subprocess.run(['grim', '-g', f'{x},{y} {width}x{height}', str(stage)],
                                    capture_output=True, timeout=4)
            if result.returncode == 0:
                stage.replace(path)
                return path
        except (OSError, subprocess.TimeoutExpired):
            LOG.exception('Could not capture game')
        return path if path.exists() else None

    def show_blocked(self, app, reason=None, retry=False):
        if self.overlay_app == app:
            self.retry = self.retry or retry
            return
        self.dismiss()
        self.overlay_app, self.retry = app, retry
        view = app_view(self.state, app)
        self.waiting_for_allowance = view['blocked']
        matching = [w for w in clients() if window_app(w, self.state) == app and w.get('at', [8000])[0] < 4000]
        source = matching[0] if matching else None
        path = self.capture(app, source) if source else self.cache / (app + '.png')
        width, height = source['size'] if source else (900, 650)
        width, height = max(600, width), max(600, height)
        x, y = source['at'] if source else (100, 100)
        self.overlay = window = tk.Toplevel(self.root)
        window.title('omarchy-kids-block')
        window.geometry(f'{width}x{height}+{x}+{y}')
        window.configure(bg='#15151c')
        window.protocol('WM_DELETE_WINDOW', self.dismiss)
        canvas = tk.Canvas(window, bg='#15151c', highlightthickness=0)
        canvas.pack(fill='both', expand=True)
        if path and path.is_file():
            try:
                with Image.open(path) as original:
                    image = ImageOps.fit(original.convert('RGB'), (width, height), method=Image.Resampling.LANCZOS)
                image = ImageEnhance.Brightness(ImageOps.grayscale(image)).enhance(0.45)
                self.photo = ImageTk.PhotoImage(image, master=canvas)
                canvas.create_image(0, 0, anchor='nw', image=self.photo)
            except (OSError, tk.TclError):
                LOG.exception('Could not display game preview')
        card = ttk.Frame(canvas, padding=24)
        heading = 'Time is up' if view['blocked'] else 'Unable to open ' + view['label']
        ttk.Label(card, text=heading, font=('sans', 24, 'bold')).pack(pady=8)
        ttk.Label(card, text=f"{view['label']} · {fmt(view['remaining'])} remaining", font=('sans', 16)).pack(pady=8)
        self.overlay_message = ttk.Label(card, text=reason or view['reason'], wraplength=460, justify='center')
        self.overlay_message.pack(pady=8)
        if view['blocked'] and view.get('code') != 'not_allowed':
            self.grant_buttons(card, app)
        else:
            ttk.Button(card, text='Close', command=self.dismiss).pack(pady=8)
        canvas.create_window(width // 2, height // 2, window=card, anchor='center')
        self.hidden = matching
        self.last_free = self.state.get('free_minute_available')

        def position():
            if self.overlay is not window:
                return
            for candidate in clients():
                if candidate.get('title') == 'omarchy-kids-block':
                    if not candidate.get('floating'):
                        dispatch('float', candidate, action='toggle')
                    dispatch('resize', candidate, x=width, y=height)
                    dispatch('move', candidate, x=x, y=y)
                    dispatch('alter_zorder', candidate, mode='top')
            for game in self.hidden:
                if game.get('fullscreen'):
                    dispatch('fullscreen_state', game, internal=0, client=0)
                if not game.get('floating'):
                    dispatch('float', game, action='toggle')
                dispatch('move', game, x=8000, y=8000)
        window.after(150, position)

    def dismiss(self):
        if self.overlay is not None:
            self.overlay.destroy()
        self.overlay = None
        self.overlay_app = None
        live = {w['address'] for w in clients()}
        for window in self.hidden:
            if window['address'] not in live:
                continue
            dispatch('move', window, x=window['at'][0], y=window['at'][1])
            if not window.get('floating'):
                dispatch('float', window, action='toggle')
            if window.get('fullscreen'):
                dispatch('fullscreen_state', window, internal=window['fullscreen'], client=window.get('fullscreenClient', 0))
        self.hidden = []

    def size_games(self, windows):
        live = {w['address'] for w in windows}
        self.sized = {address: stamp for address, stamp in self.sized.items() if address in live}
        for window in windows:
            app = window_app(window, self.state)
            geometry = definitions(self.state).get(app, {}).get('window')
            if not geometry:
                continue
            first = self.sized.setdefault(window['address'], time.monotonic())
            if first is None or time.monotonic() - first < 2 or window.get('fullscreen'):
                continue
            try:
                monitors = json.loads(hypr('-j', 'monitors'))
                monitor = next(m for m in monitors if m['id'] == window['monitor'])
                scale = float(monitor['scale'])
                factor = float(geometry['scale'])
                base_w, base_h = float(geometry['width']), float(geometry['height'])
                max_w, max_h = monitor['width'] / scale - 48, monitor['height'] / scale - 80
                factor = min(max(1, factor), max_w * scale / base_w, max_h * scale / base_h)
                width, height = round(base_w * factor / scale), round(base_h * factor / scale)
                if not window.get('floating'):
                    dispatch('float', window, action='toggle')
                dispatch('resize', window, x=width, y=height)
                dispatch('center', window)
                self.sized[window['address']] = None
            except (ValueError, KeyError, StopIteration, OSError, subprocess.TimeoutExpired):
                LOG.exception('Could not apply configured window size')

    def refresh(self):
        try:
            while True:
                try:
                    message = json.loads(self.sock.recv(4096))
                except BlockingIOError:
                    break
                if message.get('op') == 'quit':
                    self.dismiss()
                    self.root.destroy()
                    return
                app = message.get('app')
                if message.get('op') == 'launch' and app in definitions(self.state):
                    self.launch(app)
                elif message.get('op') == 'dashboard':
                    self.show_dashboard(app)
            for future, callback in list(self.jobs):
                if future.done():
                    self.jobs.remove((future, callback))
                    callback(future.result())
            previous_definitions = self.state.get('app_definitions')
            previous_apps = self.state.get('enabled_apps')
            self.state = read_json(USAGE, {}) or {}
            outside = needs_schedule_approval(self.state, self.selected)
            if self.dashboard and not self.busy and (self.dashboard_free != self.state.get('free_minute_available')
                                                     or self.grant_mode != outside or previous_apps != self.state.get('enabled_apps') or previous_definitions != self.state.get('app_definitions')):
                self.show_dashboard(self.selected)
            if self.overlay_app and self.overlay_app not in definitions(self.state):
                self.dismiss()
            self.update_dashboard()
            windows = clients()
            if not self.overlay:
                self.size_games(windows)
            if fresh(self.state):
                if self.overlay_app:
                    if self.waiting_for_allowance and not app_view(self.state, self.overlay_app)['blocked'] and not self.busy:
                        self.return_to_game(self.overlay_app)
                    elif (self.last_free != self.state.get('free_minute_available')
                          or self.grant_mode != needs_schedule_approval(self.state, self.overlay_app)) and not self.busy:
                        app, retry = self.overlay_app, self.retry
                        self.dismiss()
                        self.show_blocked(app, retry=retry)
                else:
                    for window in windows:
                        app = window_app(window, self.state)
                        if app in definitions(self.state) and app_view(self.state, app)['blocked']:
                            self.show_blocked(app)
                            break
                    if time.monotonic() - self.last_capture > 5 and not self.overlay:
                        focused = next((w for w in windows if w.get('focusHistoryID') == 0), None)
                        app = window_app(focused or {}, self.state)
                        if app and not app_view(self.state, app)['blocked']:
                            self.capture(app, focused)
                            self.last_capture = time.monotonic()
        except Exception:
            LOG.exception('UI refresh failed')
        self.root.after(500, self.refresh)


def main():
    logging.basicConfig(level=logging.INFO)
    directory = runtime()
    with (directory / 'instance.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        path = directory / 'control.sock'
        path.unlink(missing_ok=True)
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
            sock.bind(str(path))
            os.chmod(path, 0o600)
            sock.setblocking(False)
            root = tk.Tk()
            ui = DesktopUI(root, sock)
            try:
                root.mainloop()
            finally:
                ui.pool.shutdown(wait=False)
                path.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
