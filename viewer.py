"""Read-only budget view plus parent-authenticated extra time."""
import json
import subprocess
import uuid
from pathlib import Path
import tkinter as tk
from tkinter import simpledialog, ttk

STATE = Path('/var/lib/omarchy-kids/usage.json')

root = tk.Tk()
root.title('Omarchy Kids · Game time')
root.geometry('620x560')
frame = ttk.Frame(root, padding=24)
frame.pack(fill='both', expand=True)
ttk.Label(frame, text='Minecraft + Stardew Valley', font=('sans', 20, 'bold')).pack(anchor='w')
remaining = ttk.Label(frame, font=('sans', 26, 'bold'))
remaining.pack(anchor='w', pady=12)
details = ttk.Label(frame, justify='left', font=('sans', 12))
details.pack(anchor='w')
digger = ttk.Label(frame, font=('sans', 18, 'bold'))
digger.pack(anchor='w', pady=12)
schedule = ttk.Label(frame, wraplength=560, font=('sans', 12))
schedule.pack(anchor='w')
status = ttk.Label(frame, wraplength=560)
status.pack(anchor='w', pady=12)
buttons = ttk.Frame(frame)
buttons.pack(anchor='w', pady=8)


def grant(kind, **kwargs):
    cmd = ['pkexec', '/usr/bin/omarchy-kids-grant', '--id', str(uuid.uuid4())]
    if kind == 'minutes':
        cmd += ['--minutes', str(kwargs['minutes']), '--budget', kwargs.get('budget', 'shared')]
    else:
        cmd += ['--until', kwargs['until']]
    subprocess.run(cmd, check=False)


def ask_minutes(budget):
    value = simpledialog.askinteger('Extra minutes', 'Minutes to add today', minvalue=1, maxvalue=180, parent=root)
    if value:
        grant('minutes', minutes=value, budget=budget)


def ask_until():
    value = simpledialog.askstring('Play past bedtime', 'Allow until (HH:MM)', parent=root)
    if value:
        grant('until', until=value)


ttk.Button(buttons, text='+15 min games', command=lambda: grant('minutes', minutes=15, budget='shared')).grid(row=0, column=0, padx=4, pady=4)
ttk.Button(buttons, text='+15 min Digger', command=lambda: grant('minutes', minutes=15, budget='digger')).grid(row=0, column=1, padx=4, pady=4)
ttk.Button(buttons, text='Custom minutes', command=lambda: ask_minutes('shared')).grid(row=0, column=2, padx=4, pady=4)
ttk.Button(buttons, text='Allow past bedtime', command=ask_until).grid(row=1, column=0, padx=4, pady=4)


def refresh():
    try:
        state = json.loads(STATE.read_text())
        seconds = int(state['remaining_seconds'])
        remaining.config(text=f'{seconds // 60}:{seconds % 60:02d} remaining today')
        apps = state.get('apps', {})
        details.config(text=(
            f"Minecraft: {apps.get('minecraft', 0) / 60:.1f} min\n"
            f"Stardew Valley: {apps.get('stardew_valley', 0) / 60:.1f} min\n"
            f"Shared daily limit: {state['daily_limit_minutes']:g} min"
        ))
        digger_seconds = int(state['digger_remaining_seconds'])
        digger.config(text=f"Digger: {digger_seconds // 60}:{digger_seconds % 60:02d} remaining ({state['digger_daily_limit_minutes']:g} min/day)")
        if state.get('play_allowed'):
            cutoff = int(state.get('minutes_until_cutoff') or 0)
            schedule.config(text=f'Play window open. About {cutoff} min until bedtime.')
        else:
            schedule.config(text=f"Play window closed. Opens {state.get('next_open', 'later')}. Extra minutes do not cross bedtime.")
        status.config(text='; '.join(state.get('blocked_reasons', [])) or 'Game limits are active.')
    except (OSError, ValueError, KeyError):
        remaining.config(text='Waiting for the tracker…')
        status.config(text='The policy service has not published its status yet.')
    root.after(2000, refresh)


refresh()
root.mainloop()
