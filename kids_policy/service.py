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
from kids_policy.registry import managed_apps
from kids_policy.grants import Grant, revoke_grant, upsert_grant
from kids_policy.migrate import default_config, migrate_state
from kids_policy.allowlist import is_allowed_window, enabled_ids
from kids_policy.configver import load_or_migrate, migrate_allowlist, migrate_policy
from kids_policy.paths import ALLOWLIST, CGROUP_ROOT, CONFIG, FAILCLOSED, LEGACY_CONFIG, SOCKET, STATE, USAGE
from kids_policy.scan import games, identity
from kids_policy.schedule import minutes_until_cutoff, next_open_label
from kids_policy.store import read_json, write_json
from kids_policy import desktop
from kids_policy import launcher

LOG = logging.getLogger('omarchy-kids-policy')



def load_config():
    loaded = load_or_migrate(CONFIG, 'policy', migrate_policy)
    loaded['allowlist'] = load_or_migrate(ALLOWLIST, 'allowlist', migrate_allowlist)
    return loaded


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
        self.cgroups.setup(managed_apps(self.config))
        self.fallback = PidfdFallback()
        self.running = True
        self.events = []
        self.sock = None
        self.desktop = {}
        self.refresh_desktop()
        self.launcher_signature = None

    def sync_configuration(self):
        account = pwd.getpwuid(self.uid)
        home = Path(account.pw_dir)
        paths = [CONFIG, ALLOWLIST, *launcher.SYSTEM_ROOTS,
                 home / '.local/share/applications',
                 home / '.local/share/flatpak/exports/share/applications']
        signature = tuple((str(path), path.stat().st_mtime_ns if path.exists() else None) for path in paths)
        if signature == self.launcher_signature:
            return
        # Never turn a temporarily incomplete JSON write into default permissions.
        policy = json.loads(CONFIG.read_text())
        allowed = json.loads(ALLOWLIST.read_text())
        if not isinstance(policy, dict) or not isinstance(allowed, (dict, list)):
            raise ValueError('Invalid kids policy or allow-list')
        updated = load_config()
        if int(updated['child_uid']) != self.uid:
            raise ValueError('Changing the child account requires a service restart')
        launcher.sync(home, updated, account.pw_name, (account.pw_uid, account.pw_gid))
        for app in managed_apps(self.config).keys() - managed_apps(updated).keys():
            self.cgroups.freeze(app, False)
        self.config = updated
        self.policy.configure(updated)
        self.cgroups.setup(managed_apps(updated))
        self.launcher_signature = signature

    def refresh_desktop(self):
        self.desktop = desktop.status(self.uid)
        self.policy.schedule_extension_until = self.desktop.get('extension_until') or 0

    def tick_policy(self, now, mono, running):
        reason, code = desktop.refusal(getattr(self, 'desktop', {}))
        # Frozen games must not spend their remaining app allowance while
        # the separate desktop gate prevents the child from playing.
        blocked, reasons = self.policy.tick(now, mono, set() if code else running)
        if code:
            blocked.update(managed_apps(self.config))
            reasons.append(reason)
        return blocked, reasons

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
        snap['desktop'] = getattr(self, 'desktop', {})
        snap['enabled_apps'] = [app for app in managed_apps(self.config) if app in enabled_ids(self.config)]
        snap['app_status'] = {app: self.app_permission(app, now) for app in managed_apps(self.config)}
        snap['play_windows'] = self.config['play_windows']
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
        state.update({'grants': snap['grants'], 'schema_version': 3, 'failclosed': False})
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
        for name, record in snap['budgets'].items():
            remaining = record['remaining_seconds']
            if remaining is None:
                continue
            for mark in self.config.get('warnings_minutes', [5, 1]):
                key = f'{name}_{mark}'
                if 0 < remaining <= mark * 60 and not flags.get(key):
                    flags[key] = True
                    self.notify('Screen time', f'{mark} minute(s) left for {record["label"]}')
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
        for app in managed_apps(self.config):
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
        events.extend(self.enforce_allowlist())
        return events

    def enforce_allowlist(self):
        from kids_policy.windows import clients, close_window
        events = []
        for client in clients(self.uid):
            title = client.get('title') or ''
            class_name = client.get('class') or ''
            if is_allowed_window(self.config, title, class_name):
                continue
            address = client.get('address')
            if not address:
                continue
            close_window(self.uid, address)
            events.append(f'closed {title or class_name}')
        return events

    def app_permission(self, app, now):
        if app not in enabled_ids(self.config):
            return {'blocked': True, 'reason': 'This app is not on the parent allow-list', 'code': 'not_allowed'}
        if app not in self.config['apps']:
            return {'blocked': True, 'reason': 'Unknown app', 'code': 'unknown_app'}
        # Read the current allowance without changing the accounting clock.
        spec = self.config['apps'][app]
        label, budget = spec['label'], spec.get('budget')
        if spec.get('control'):
            return {'blocked': False, 'reason': '', 'code': ''}
        reason, code = desktop.refusal(getattr(self, 'desktop', {}))
        if code:
            return {'blocked': True, 'reason': reason, 'code': code}
        allowed, reason = self.policy.play_allowed(now)
        if spec.get('schedule', True) and not allowed:
            return {'blocked': True, 'reason': reason or 'Outside allowed hours',
                    'code': 'schedule' if self.policy.bedtime(now) else 'limit'}
        if budget is not None and self.policy.remaining(budget) <= 0:
            return {'blocked': True, 'reason': f'{label} daily limit reached', 'code': 'limit'}
        return {'blocked': False, 'reason': '', 'code': ''}

    def may_launch(self, app):
        now = dt.datetime.now()
        if hasattr(self, 'desktop'):
            try:
                self.sync_configuration()
            except (OSError, ValueError) as exc:
                return {'ok': False, 'error': 'Could not read current app permissions: ' + str(exc)}
            self.refresh_desktop()
        if app not in self.config.get('apps', {}):
            return {'ok': False, 'error': 'unknown app'}
        _found, running = games(self.uid, self.config)
        self.tick_policy(now, time.monotonic(), running)
        permission = self.app_permission(app, now)
        if permission['blocked']:
            return {'ok': False, 'error': permission['reason'], 'code': permission['code']}
        spec = self.config['apps'][app]
        argv = list(spec['argv'])
        if not argv or not Path(argv[0]).exists():
            return {'ok': False, 'error': f'{app} is not installed'}
        return {'ok': True}

    def adopt(self, app, pid):
        if app not in self.config.get('apps', {}):
            return {'ok': False, 'error': 'unknown app'}
        self.cgroups.adopt(app, int(pid))
        return {'ok': True, 'pid': int(pid)}

    def refresh_limits(self):
        self.policy.configure(self.config)

    def grant(self, payload):
        grant = Grant.from_dict(payload)
        import math
        if (grant.child_uid != self.uid or grant.date != self.policy.state['date']
                or grant.kind != 'minutes' or (grant.budget != 'all' and grant.budget not in self.policy.budgets)
                or type(grant.minutes) not in (int, float) or not math.isfinite(grant.minutes) or grant.minutes <= 0):
            raise ValueError('Invalid allowance grant')
        grants = self.policy.grant_objects()
        grants, stored, created = upsert_grant(grants, grant)
        self.policy.state['grants'] = [item.to_dict() for item in grants]
        self.refresh_limits()
        found, _running = games(self.uid, self.config)
        self.publish(dt.datetime.now(), found, set(), [])
        return {'ok': True, 'created': created, 'grant': stored.to_dict()}

    def free_minute(self, budget='all'):
        if budget != 'all' and budget not in self.policy.budgets:
            return {'ok': False, 'error': 'unknown budget'}
        if self.policy.state.get('free_minute_used'):
            return {'ok': False, 'error': 'already used today'}
        if hasattr(self, 'desktop'):
            self.refresh_desktop()
            reason, code = desktop.refusal(getattr(self, 'desktop', {}))
            if code or self.policy.bedtime(dt.datetime.now()):
                return {'ok': False, 'error': reason or 'Ask a parent to play outside allowed hours.'}
        today = self.policy.state['date']
        self.policy.state['free_minute_used'] = True
        return self.grant({
            'id': f'free-minute-{today}',
            'kind': 'minutes',
            'minutes': 1,
            'budget': budget,
            'date': today,
            'child_uid': self.uid,
            'approver': 'free-minute',
            'created_at': dt.datetime.now().isoformat(timespec='seconds'),
        })

    def play_grant(self, payload, after_bedtime=False):
        # The socket is root-only; the public helper requires polkit/sudo.
        grant = Grant.from_dict(payload)
        if (grant.kind != 'minutes' or grant.child_uid != self.uid
                or grant.budget not in self.policy.budgets
                or type(grant.minutes) not in (int, float)
                or not 1 <= grant.minutes <= 60):
            raise ValueError('Choose between 1 and 60 minutes for one app allowance.')
        for existing in self.policy.grant_objects():
            if existing.id == grant.id:
                return {'ok': True, 'created': False, 'grant': existing.to_dict()}
        now = dt.datetime.now()
        if grant.date != str(now.date()):
            raise ValueError('Grant date is no longer current. Try again.')
        if self.policy.bedtime(now) and not after_bedtime:
            raise ValueError('Outside allowed hours. Choose the parent option to play past bedtime.')
        self.desktop = desktop.approve(self.uid, grant.minutes, after_bedtime, grant.id)
        self.policy.schedule_extension_until = self.desktop.get('extension_until') or 0
        return self.grant(payload)

    def schedule_grant(self, payload):
        grant = Grant.from_dict(payload)
        now = dt.datetime.now()
        if (grant.kind != 'schedule' or grant.child_uid != self.uid or grant.budget is not None
                or grant.date != str(now.date()) or type(grant.minutes) not in (int, float)
                or not 1 <= grant.minutes <= 60):
            raise ValueError('Choose 1 to 60 minutes for a schedule exception')
        for existing in self.policy.grant_objects():
            if existing.id == grant.id:
                return {'ok': True, 'created': False, 'grant': existing.to_dict()}
        self.desktop = desktop.approve(self.uid, grant.minutes, True, grant.id)
        self.policy.schedule_extension_until = self.desktop.get('extension_until') or 0
        grants, stored, created = upsert_grant(self.policy.grant_objects(), grant)
        self.policy.state['grants'] = [item.to_dict() for item in grants]
        found, _ = games(self.uid, self.config)
        self.publish(now, found, set(), [])
        return {'ok': True, 'created': created, 'grant': stored.to_dict()}

    def revoke(self, grant_id):
        grants = self.policy.grant_objects()
        grants, removed = revoke_grant(grants, grant_id)
        self.policy.state['grants'] = [item.to_dict() for item in grants]
        self.refresh_limits()
        found, _ = games(self.uid, self.config)
        self.publish(dt.datetime.now(), found, set(), [])
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
        if op == 'schedule_grant':
            return self.schedule_grant(request['grant'])
        if op == 'play_grant':
            return self.play_grant(request['grant'], request.get('after_bedtime') is True)
        if op == 'free_minute':
            return self.free_minute(request.get('budget', 'all'))
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
                try:
                    self.sync_configuration()
                except (OSError, ValueError) as exc:
                    LOG.error('Launcher configuration not applied: %s', exc)
                found, running = games(self.uid, self.config)
                self.refresh_desktop()
                blocked, reasons = self.tick_policy(now, time.monotonic(), running)
                events = self.enforce(found, blocked, reasons)
                self.events = (self.events + events)[-20:]
                for event in events:
                    LOG.info('%s', event)
                snap = self.publish(now, found, blocked, reasons)
                self.warnings(now, snap)
                self.accept()
                time.sleep(1)
        finally:
            # A normal restart must not strand processes stopped by this daemon.
            # On unexpected failure leave enforcement in place for failclosed.
            if not self.running:
                self.fallback.release(set())
                self.cgroups.freeze_all(managed_apps(self.config), False)
            if self.sock:
                self.sock.close()
            if SOCKET.exists():
                SOCKET.unlink()


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
    Daemon().loop()


if __name__ == '__main__':
    main()
