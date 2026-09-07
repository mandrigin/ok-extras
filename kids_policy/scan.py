import os
from pathlib import Path

from kids_policy.classify import classify


class ProcessIdentity:
    def __init__(self, pid, uid, start_time):
        self.pid = pid
        self.uid = uid
        self.start_time = start_time

    def __hash__(self):
        return hash((self.pid, self.uid, self.start_time))

    def __eq__(self, other):
        return isinstance(other, ProcessIdentity) and (self.pid, self.uid, self.start_time) == (other.pid, other.uid, other.start_time)


def identity(pid):
    try:
        stat = Path('/proc', str(pid), 'stat').read_text(errors='replace')
        stat_fields = stat.rsplit(') ', 1)[1].split()
        start_time = int(stat_fields[19])
        status = Path('/proc', str(pid), 'status').read_text(errors='replace')
        uid_line = next(line for line in status.splitlines() if line.startswith('Uid:'))
        uid = int(uid_line.split()[1])
        return ProcessIdentity(pid, uid, start_time)
    except (OSError, StopIteration, ValueError, IndexError):
        return None


def is_stopped(pid):
    try:
        stat = Path('/proc', str(pid), 'stat').read_text(errors='replace')
        return stat.rsplit(') ', 1)[1][:1] in {'T', 't'}
    except (FileNotFoundError, PermissionError, IndexError):
        return False


def games(uid, config):
    found = {}
    running = set()
    for entry in os.listdir('/proc'):
        if not entry.isdigit():
            continue
        pid = int(entry)
        ident = identity(pid)
        if ident is None or ident.uid != uid:
            continue
        proc = Path('/proc', str(pid))
        try:
            executable = os.readlink(proc / 'exe')
            command = (proc / 'cmdline').read_bytes().replace(b'\0', b' ').decode(errors='replace')
            cwd = os.readlink(proc / 'cwd')
            comm = (proc / 'comm').read_text(errors='replace').strip()
            membership = (proc / 'cgroup').read_text()
            owned = [line.rsplit('/', 1)[-1] for line in membership.splitlines()
                     if line.startswith('0::/omarchy-kids/') and line.count('/') == 2]
            app = next((name for name in owned if name in config.get('apps', {})), None)
            if app is None:
                app = classify(config, comm, executable, command, cwd)
            if app and identity(pid) == ident:
                found.setdefault(app, set()).add(ident)
                if not is_stopped(pid):
                    running.add(app)
        except OSError:
            continue
    return found, running
