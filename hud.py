"""Tiny remaining-time pill, plus a dimmed screenshot overlay when blocked."""
import json
import subprocess
import traceback
import uuid
from pathlib import Path
import tkinter as tk

STATE = Path('/var/lib/omarchy-kids/usage.json')
LOG = Path('/tmp/omarchy-kids-hud.log')
RAW = Path('/tmp/omarchy-kids-block-raw.png')
DIM = Path('/tmp/omarchy-kids-block.png')
BG = '#1a1c28'
FG = '#f4f4f4'
LOW = '#ff9f0a'
OUT = '#ff453a'


def log(msg):
    with LOG.open('a') as handle:
        handle.write(msg + '\n')


def fmt(seconds):
    seconds = max(0, int(seconds))
    return f'{seconds // 60}:{seconds % 60:02d}'


def grant_one_minute():
    subprocess.run(['sudo', '-n', '/usr/bin/omarchy-kids-grant', '--free-minute'], check=False)


def grant_tier(minutes):
    subprocess.run(
        ['pkexec', '/usr/bin/omarchy-kids-grant', '--id', str(uuid.uuid4()), '--minutes', str(minutes), '--budget', 'all'],
        check=False,
    )


def hyprctl(*args):
    try:
        return subprocess.run(['hyprctl', *args], check=False, capture_output=True, text=True, timeout=2)
    except (OSError, subprocess.TimeoutExpired):
        return None


def dsp(lua):
    import shlex
    cmd = f'hyprctl dispatch {shlex.quote(lua)}'
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=2)
    except (OSError, subprocess.TimeoutExpired) as exc:
        log(f'dsp timeout {exc}')
        return
    log(f'dsp {result.returncode} {result.stdout.strip()} {result.stderr.strip()[:160]}')


def clients():
    result = hyprctl('-j', 'clients')
    if not result or not result.stdout:
        return []
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return []


def is_game(client):
    blob = f"{client.get('title', '')} {client.get('class', '')}".lower()
    if 'omarchy-kids' in blob:
        return False
    return any(name in blob for name in ('digger', 'minecraft', 'prism', 'stardew', 'vlc'))


def addr(client):
    return f'address:{client["address"]}'


def hide_games():
    for client in clients():
        if not is_game(client):
            continue
        window = addr(client)
        dsp(f'hl.dsp.window.move({{ window = "{window}", x = 8000, y = 8000 }})')
        log(f'hide {client.get("title")}')


def show_games(x=320, y=213):
    for client in clients():
        if not is_game(client):
            continue
        window = addr(client)
        dsp(f'hl.dsp.window.move({{ window = "{window}", x = {int(x)}, y = {int(y)} }})')


def place_overlay(x, y, w, h):
    for client in clients():
        if client.get('title') != 'omarchy-kids-block':
            continue
        window = addr(client)
        if not client.get('floating'):
            dsp(f'hl.dsp.window.float({{ window = "{window}", action = "toggle" }})')
        dsp(f'hl.dsp.window.resize({{ window = "{window}", x = {int(w)}, y = {int(h)} }})')
        dsp(f'hl.dsp.window.move({{ window = "{window}", x = {int(x)}, y = {int(y)} }})')
        dsp(f'hl.dsp.window.alter_zorder({{ window = "{window}", mode = "top" }})')
        dsp(f'hl.dsp.window.bring_to_top({{ window = "{window}" }})')
        return


log('start')
root = tk.Tk()
root.title('omarchy-kids-hud')
root.configure(bg=BG)
root.attributes('-topmost', True)
root.resizable(False, False)
root.geometry('72x28-16-16')
clock = tk.Label(root, text='--:--', fg=FG, bg=BG, font=('DejaVu Sans Mono', 12, 'bold'), padx=8, pady=3)
clock.pack()

overlay = None
photo = None
blocked_mode = False
capturing = False
game_box = (320, 213, 640, 400)


def destroy_overlay():
    global overlay, photo
    if overlay is not None:
        try:
            overlay.destroy()
        except tk.TclError:
            pass
    overlay = None
    photo = None


def snapshot_and_dim(x, y, w, h):
    subprocess.run(['grim', '-g', f'{x},{y} {w}x{h}', str(DIM)], check=False, timeout=4)


def build_overlay(label, bedtime, x, y, w, h):
    global overlay, photo, capturing
    capturing = False
    log(f'overlay {label} {w}x{h}+{x}+{y}')
    snapshot_and_dim(x, y, w, h)
    overlay = tk.Toplevel(root)
    overlay.title('omarchy-kids-block')
    overlay.configure(bg='#000')
    overlay.attributes('-topmost', True)
    overlay.geometry(f'{w}x{h}+{x}+{y}')
    canvas = tk.Canvas(overlay, width=w, height=h, highlightthickness=0, bg='#000')
    canvas.pack(fill='both', expand=True)
    if DIM.exists():
        try:
            photo = tk.PhotoImage(file=str(DIM))
            canvas.create_image(0, 0, image=photo, anchor='nw')
            canvas.create_rectangle(0, 0, w, h, fill='black', stipple='gray50')
            log('image ok')
        except tk.TclError as exc:
            log(f'image fail {exc}')
    canvas.create_rectangle(36, h // 2 - 80, w - 36, h // 2 + 80, fill='#1a1c28', outline='#ff453a', width=2)
    canvas.create_text(w // 2, h // 2 - 44, text='Bedtime' if bedtime else 'Time is up', fill=OUT, font=('sans', 22, 'bold'))
    canvas.create_text(
        w // 2, h // 2,
        text=f'{label} is not allowed.\nAsk a parent for more minutes.',
        fill=FG, font=('sans', 13), justify='center',
    )
    try:
        snap = json.loads(STATE.read_text())
    except (OSError, json.JSONDecodeError):
        snap = {}
    free = snap.get('free_minute_available', True)
    tiers = list(snap.get('extra_minute_tiers') or [15, 30, 60])
    if free:
        ask = tk.Button(overlay, text='1 more minute', command=grant_one_minute, bg='#2c2f3f', fg=FG, relief='flat', font=('sans', 12), padx=10, pady=6)
        canvas.create_window(w // 2, h // 2 + 48, window=ask)
    else:
        bar = tk.Frame(overlay, bg='#1a1c28')
        for minutes in tiers[:3]:
            label = f'{minutes} min' if minutes < 60 else f'{minutes // 60} h'
            tk.Button(
                bar, text=label, command=lambda m=minutes: grant_tier(m),
                bg='#2c2f3f', fg=FG, relief='flat', font=('sans', 11), padx=8, pady=5,
            ).pack(side='left', padx=4)
        canvas.create_window(w // 2, h // 2 + 48, window=bar)

    def finish():
        place_overlay(x, y, w, h)
        hide_games()

    overlay.after(120, finish)
    overlay.after(400, finish)


def show_overlay(label, bedtime, x, y, w, h):
    global capturing
    if overlay is not None:
        place_overlay(x, y, w, h)
        hide_games()
        return
    capturing = True
    show_games(x, y)
    root.after(450, lambda: build_overlay(label, bedtime, x, y, w, h))


def refresh():
    global blocked_mode, game_box
    try:
        state = json.loads(STATE.read_text())
        running = state.get('running') or {}
        shared = float(state.get('remaining_seconds') or 0)
        digger = float(state.get('digger_remaining_seconds') or 0)
        if running.get('digger'):
            left, label = digger, 'Digger'
        elif running.get('minecraft') or running.get('stardew_valley'):
            left, label = shared, 'Games'
        elif running.get('vlc'):
            left, label = float(state.get('vlc_remaining_seconds') or 0), 'Videos'
        else:
            left, label = max(shared, digger), 'Play time'
        games = [client for client in clients() if is_game(client) and client.get('at') and client['at'][0] < 4000]
        if games:
            game_box = (*games[0]['at'], *games[0]['size'])
        blocked = left <= 0 and bool(running)
        clock.config(text=fmt(left), fg=OUT if left <= 0 else LOW if left <= 60 else FG)
        if blocked and not blocked_mode:
            log(f'enter blocked {label} left={left} box={game_box}')
            blocked_mode = True
            show_overlay(label, bool(state.get('bedtime')), *game_box)
        elif not blocked and blocked_mode:
            log('leave blocked')
            blocked_mode = False
            destroy_overlay()
            show_games(game_box[0], game_box[1])
        if blocked and overlay is not None and not capturing:
            place_overlay(*game_box)
            hide_games()
    except Exception:
        log(traceback.format_exc())
    root.after(500, refresh)


refresh()
root.mainloop()
