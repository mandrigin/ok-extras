import datetime as dt
import json
import logging
import os
import pwd
import signal
import socket
import time
from pathlib import Path

from kids_policy.budget import Policy
from kids_policy.cgroup import CgroupTree, write_failclosed
from kids_policy.classify import SCHEDULED
from kids_policy.grants import Grant, revoke_grant, upsert_grant
from kids_policy.migrate import default_config, migrate_state
from kids_policy.paths import CGROUP_ROOT, CONFIG, FAILCLOSED, LEGACY_CONFIG, SOCKET, STATE, USAGE
from kids_policy.scan import games, identity
from kids_policy.schedule import minutes_until_cutoff, next_open_label
from kids_policy.store import read_json, write_json
from kids_policy.windows import hide_pids, show_pids

LOG = logging.getLogger('omarchy-kids-policy')



def load_config():
    config = default_config()
    legacy = read_json(LEGACY_CONFIG, {}) or {}
    if legacy:
        config['child_uid'] = int(legacy.get('uid', config['child_uid']))
        config['shared_daily_minutes'] = float(legacy.get('daily_minutes', config['shared_daily_minutes']))
        config['digger_daily_minutes'] = float(legacy.get('digger_daily_minutes', config['digger_daily_minutes']))
    loaded = read_json(CONFIG, {}) or {}
    config.update({key: value for key, value in loaded.items() if key != 'apps'})
    if isinstance(loaded.get('apps'), dict):
        config['apps'].update(loaded['apps'])
    return config


class PidfdFallback:
    def __init__(self):
        self.stopped = {}
        self.supported = callable(getattr(os, 'pidfd_open', None)) and callable(getattr(signal, 'pidfd_send_signal', None))

    def block(self, ident, reason):
        if ident in self.stopped:
            return None
        if not self.supported or identity(ident.pid) != ident:
            return None
        try:
            pidfd = os.pidfd_open(ident.pid)
        except OSError:
            return None
        if identity(ident.pid) != ident:
            os.close(pidfd)
            return None
        try:
            signal.pidfd_send_signal(pidfd, signal.SIGSTOP)
        except OSError:
            os.close(pidfd)
            return None
        self.stopped[ident] = pidfd
        return f'blocked pid {ident.pid} ({reason})'

    def release(self, keep):
        events = []
        for ident, pidfd in list(self.stopped.items()):
            if ident in keep:
                continue
            try:
                if identity(ident.pid) == ident:
                    signal.pidfd_send_signal(pidfd, signal.SIGCONT)
                    events.append(f'released pid {ident.pid}')
            except OSError:
                pass
            try:
                os.close(pidfd)
            except OSError:
                pass
            self.stopped.pop(ident, None)
        return events


class Daemon:
    def __init__(self):
        self.config = load_config()
        self.uid = int(self.config['child_uid'])
        saved = migrate_state(read_json(STATE, read_json(USAGE, {})))
        now = dt.datetime.now()
        self.policy = Policy(saved, self.config, now, time.monotonic())
        self.cgroups = CgroupTree(CGROUP_ROOT)
        self.cgroups.setup(SCHEDULED)
        self.fallback = PidfdFallback()
        self.running = True
        self.events = []
        self.sock = None
        self.hidden_pids = set()

    def stop(self, *_args):
        self.running = False

    def bind_socket(self):
        SOCKET.parent.mkdir(parents=True, exist_ok=True)
        if SOCKET.exists():
            SOCKET.unlink()
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(str(SOCKET))
        os.chmod(SOCKET, 0o660)
        sock.listen(8)
        sock.setblocking(False)
        self.sock = sock

    def publish(self, now, found, blocked, reasons):
        snap = self.policy.snapshot(now)
        snap.update({
            'running': {app: len(pids) for app, pids in found.items()},
            'blocked': len(blocked),
            'blocked_reasons': reasons,
            'events': self.events[-20:],
            'downtime': None if snap['play_allowed'] else snap['play_blocked_reason'],
            'updated_at': now.isoformat(timespec='seconds'),
            'mode': 'enforce',
            'cgroup': self.cgroups.ok,
            'next_open': next_open_label(now, self.config['play_windows']),
        })
        state = self.policy.apply_snapshot_usage()
        state.update({'grants': snap['grants'], 'schema_version': 2, 'failclosed': False})
        write_json(STATE, state)
        write_json(USAGE, snap)
        write_failclosed(FAILCLOSED, False)
        return snap

    def notify(self, title, body):
        runtime = Path(f'/run/user/{self.uid}')
        if not runtime.exists():
            return
        try:
            import subprocess
            subprocess.run(
                ['runuser', '-u', pwd.getpwuid(self.uid).pw_name, '--',
                 'env', f'XDG_RUNTIME_DIR={runtime}', f'DBUS_SESSION_BUS_ADDRESS=unix:path={runtime}/bus',
                 'omarchy-notification-send', title, body],
                check=False, timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass

    def warnings(self, now, snap):
        flags = self.policy.state.setdefault('warnings', {})
        for name, remaining in (('shared', snap['remaining_seconds']), ('digger', snap['digger_remaining_seconds'])):
            for mark in self.config.get('warnings_minutes', [5, 1]):
                key = f'{name}_{mark}'
                if 0 < remaining <= mark * 60 and not flags.get(key):
                    flags[key] = True
                    self.notify('Screen time', f'{mark} minute(s) left for {name} games')
        until = minutes_until_cutoff(now, self.config['play_windows'])
        for mark in self.config.get('warnings_minutes', [5, 1]):
            key = f'schedule_{mark}'
            if snap['play_allowed'] and 0 < until <= mark and not flags.get(key):
                flags[key] = True
                self.notify('Bedtime soon', f'Play window closes in {mark} minute(s)')

    def enforce(self, found, blocked, reasons):
        events = []
        keep = set()
        reason = '; '.join(reasons) if reasons else 'blocked'
        for app in SCHEDULED:
            freeze = app in blocked
            self.cgroups.freeze(app, freeze)
            for ident in found.get(app, set()):
                self.cgroups.adopt(app, ident.pid)
                if freeze:
                    keep.add(ident)
                    event = self.fallback.block(ident, reason)
                    if event:
                        events.append(event)
        events.extend(self.fallback.release(keep))
        blocked_pids = {ident.pid for app, idents in found.items() if app in blocked for ident in idents}
        hide_pids(self.uid, blocked_pids - self.hidden_pids)
        show_pids(self.uid, self.hidden_pids - blocked_pids)
        self.hidden_pids = blocked_pids
        return events

    def may_launch(self, app):
        spec = self.config.get('apps', {}).get(app)
        if not spec:
            return {'ok': False, 'error': 'unknown app'}
        now = dt.datetime.now()
        _found, running = games(self.uid)
        blocked, reasons = self.policy.tick(now, time.monotonic(), running)
        if app in blocked:
            return {'ok': False, 'error': '; '.join(reasons) or 'not allowed now'}
        argv = list(spec['argv'])
        if not argv or not Path(argv[0]).exists():
            return {'ok': False, 'error': f'{app} is not installed'}
        return {'ok': True}

    def adopt(self, app, pid):
        if app not in self.config.get('apps', {}):
            return {'ok': False, 'error': 'unknown app'}
        self.cgroups.adopt(app, int(pid))
        return {'ok': True, 'pid': int(pid)}

    def grant(self, payload):
        grant = Grant.from_dict(payload)
        grants = self.policy.grant_objects()
        grants, stored, created = upsert_grant(grants, grant)
        self.policy.state['grants'] = [item.to_dict() for item in grants]
        today = self.policy.state['date']
        from kids_policy.grants import extra_seconds
        self.policy.shared.limit = float(self.config['shared_daily_minutes']) * 60 + extra_seconds(grants, 'shared', today)
        self.policy.digger.limit = float(self.config['digger_daily_minutes']) * 60 + extra_seconds(grants, 'digger', today)
        found, _running = games(self.uid)
        self.publish(dt.datetime.now(), found, set(), [])
        return {'ok': True, 'created': created, 'grant': stored.to_dict()}

    def revoke(self, grant_id):
        grants = self.policy.grant_objects()
        grants, removed = revoke_grant(grants, grant_id)
        self.policy.state['grants'] = [item.to_dict() for item in grants]
        return {'ok': True, 'removed': removed}

    def handle(self, request):
        op = request.get('op')
        if op == 'status':
            return {'ok': True, 'status': read_json(USAGE, {})}
        if op == 'may_launch':
            return self.may_launch(str(request.get('app', '')))
        if op == 'adopt':
            return self.adopt(str(request.get('app', '')), request.get('pid'))
        if op == 'grant':
            return self.grant(request['grant'])
        if op == 'revoke':
            return self.revoke(str(request.get('id', '')))
        return {'ok': False, 'error': 'unknown op'}

    def accept(self):
        if self.sock is None:
            return
        while True:
            try:
                conn, _addr = self.sock.accept()
            except BlockingIOError:
                return
            with conn:
                conn.settimeout(2)
                try:
                    data = b''
                    while b'\n' not in data:
                        chunk = conn.recv(4096)
                        if not chunk:
                            break
                        data += chunk
                    if not data:
                        continue
                    request = json.loads(data.decode())
                    reply = self.handle(request)
                except (OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
                    reply = {'ok': False, 'error': str(exc)}
                conn.sendall((json.dumps(reply) + '\n').encode())

    def loop(self):
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)
        self.bind_socket()
        LOG.info('policy service uid=%s cgroup=%s', self.uid, self.cgroups.ok)
        try:
            while self.running:
                now = dt.datetime.now()
                found, running = games(self.uid)
                blocked, reasons = self.policy.tick(now, time.monotonic(), running)
                events = self.enforce(found, blocked, reasons)
                self.events = (self.events + events)[-20:]
                for event in events:
                    LOG.info('%s', event)
                snap = self.publish(now, found, blocked, reasons)
                self.warnings(now, snap)
                self.accept()
                time.sleep(1)
        finally:
            if self.sock:
                self.sock.close()
            if SOCKET.exists():
                SOCKET.unlink()


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
    Daemon().loop()


if __name__ == '__main__':
    main()
