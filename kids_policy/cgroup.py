import os
from pathlib import Path


class CgroupTree:
    def __init__(self, root=None):
        self.root = Path(root or '/sys/fs/cgroup/omarchy-kids')
        self.ok = False

    def setup(self, apps):
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            (self.root / 'cgroup.subtree_control').write_text('')
        except OSError:
            pass
        try:
            for app in apps:
                path = self.root / app
                path.mkdir(parents=True, exist_ok=True)
                if not (path / 'cgroup.freeze').exists():
                    self.ok = False
                    return False
            self.ok = True
            return True
        except OSError:
            self.ok = False
            return False

    def path_for(self, app):
        return self.root / app

    def adopt(self, app, pid):
        if not self.ok:
            return False
        try:
            (self.path_for(app) / 'cgroup.procs').write_text(str(pid))
            return True
        except OSError:
            return False

    def freeze(self, app, frozen):
        if not self.ok:
            return False
        try:
            (self.path_for(app) / 'cgroup.freeze').write_text('1' if frozen else '0')
            return True
        except OSError:
            return False

    def freeze_all(self, apps, frozen=True):
        return all(self.freeze(app, frozen) for app in apps)

    def pids(self, app):
        try:
            text = (self.path_for(app) / 'cgroup.procs').read_text()
        except OSError:
            return []
        return [int(line) for line in text.splitlines() if line.strip().isdigit()]


def write_failclosed(path, enabled):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text('1\n' if enabled else '0\n')
    tmp.chmod(0o644)
    os.replace(tmp, path)
