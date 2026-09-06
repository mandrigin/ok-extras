def parse_hhmm(value):
    hours, minutes = (int(part) for part in str(value).split(':', 1))
    if not (0 <= hours <= 23 and 0 <= minutes <= 59):
        raise ValueError(value)
    return hours * 60 + minutes


def minutes_now(now):
    return now.hour * 60 + now.minute


def in_half_open_window(now_minutes, start, end):
    start_m = parse_hhmm(start)
    end_m = parse_hhmm(end)
    if start_m == end_m:
        return True
    if start_m < end_m:
        return start_m <= now_minutes < end_m
    return now_minutes >= start_m or now_minutes < end_m


def is_weekend(now):
    return now.weekday() >= 5


def play_window(now, windows):
    kind = 'weekend' if is_weekend(now) else 'weekday'
    return windows[kind], kind


def in_play_window(now, windows):
    window, _kind = play_window(now, windows)
    return in_half_open_window(minutes_now(now), window['start'], window['end'])


def window_end_minutes(now, windows):
    window, _kind = play_window(now, windows)
    return parse_hhmm(window['end'])


def after_cutoff(now, windows):
    return minutes_now(now) >= window_end_minutes(now, windows)


def minutes_until_cutoff(now, windows):
    remaining = window_end_minutes(now, windows) - minutes_now(now)
    if remaining <= 0:
        return 0
    return remaining


def next_open_label(now, windows):
    window, _kind = play_window(now, windows)
    if minutes_now(now) < parse_hhmm(window['start']):
        return f'today {window["start"]}'
    weekday = now.weekday()
    if weekday == 4:
        return f'Saturday {windows["weekend"]["start"]}'
    if weekday == 5:
        return f'Sunday {windows["weekend"]["start"]}'
    if weekday == 6:
        return f'Monday {windows["weekday"]["start"]}'
    return f'tomorrow {windows["weekday"]["start"]}'
