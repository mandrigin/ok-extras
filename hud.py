"""Nintendo Switch-style remaining-time counter and Time's up overlay."""
import json
import subprocess
import uuid
from pathlib import Path
import tkinter as tk

STATE = Path('/var/lib/omarchy-kids/usage.json')
BG = '#1a1c28'
FG = '#f4f4f4'
LOW = '#ff9f0a'
OUT = '#ff453a'


def fmt(seconds):
    seconds = max(0, int(seconds))
    return f'{seconds // 60}:{seconds % 60:02d}'


def grant_one_minute():
    subprocess.run(
        ['pkexec', '/usr/bin/omarchy-kids-grant', '--id', str(uuid.uuid4()), '--minutes', '1', '--budget', 'all'],
        check=False,
    )


root = tk.Tk()
root.title('omarchy-kids-hud')
root.configure(bg=BG)
root.attributes('-topmost', True)
root.resizable(False, False)
root.overrideredirect(True)

frame = tk.Frame(root, bg=BG, padx=18, pady=12)
frame.pack(fill='both', expand=True)
clock = tk.Label(frame, text='--:--', fg=FG, bg=BG, font=('DejaVu Sans Mono', 28, 'bold'))
clock.pack()
caption = tk.Label(frame, text='Play time', fg='#b0b4c4', bg=BG, font=('sans', 11))
caption.pack()
message = tk.Label(frame, text='', fg=FG, bg=BG, font=('sans', 13), wraplength=360, justify='center')
ask = tk.Button(
    frame, text='Ask for 1 more minute', command=grant_one_minute,
    bg='#2c2f3f', fg=FG, activebackground='#3a3e52', activeforeground=FG,
    relief='flat', font=('sans', 12), padx=12, pady=8,
)
blocked_mode = False


def layout(blocked):
    global blocked_mode
    if blocked == blocked_mode:
        return
    blocked_mode = blocked
    if blocked:
        message.pack(pady=8)
        ask.pack(pady=8)
        root.geometry('420x260+40+40')
        clock.config(font=('DejaVu Sans Mono', 40, 'bold'))
    else:
        message.pack_forget()
        ask.pack_forget()
        root.geometry('168x92-24-24')
        clock.config(font=('DejaVu Sans Mono', 28, 'bold'))


def refresh():
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
            left, label = max(shared, digger), 'Videos'
        else:
            left, label = max(shared, digger), 'Play time'
        blocked = left <= 0
        layout(blocked)
        clock.config(text=fmt(left), fg=OUT if blocked else LOW if left <= 60 else FG)
        caption.config(text='Time is up' if blocked else label)
        if blocked:
            reason = state.get('play_blocked_reason') or 'Time is up'
            if state.get('bedtime'):
                message.config(text='Bedtime. This app is not allowed until more time is approved.')
            else:
                message.config(text=f'{reason}. This app is not allowed until more time is approved.')
    except (OSError, ValueError, KeyError, TypeError):
        clock.config(text='--:--')
    root.after(500, refresh)


def start_move(event):
    root._ox, root._oy = event.x, event.y


def on_move(event):
    root.geometry(f'+{root.winfo_x() + event.x - root._ox}+{root.winfo_y() + event.y - root._oy}')


frame.bind('<Button-1>', start_move)
frame.bind('<B1-Motion>', on_move)
clock.bind('<Button-1>', start_move)
clock.bind('<B1-Motion>', on_move)

layout(False)
refresh()
root.mainloop()
