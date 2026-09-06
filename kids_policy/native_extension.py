"""Read an expiring parent exception; also installed inside native screen time.

No dependency on the extras daemon: expiry still works if it stops or restarts.
"""
import json
import math
import os
import stat
from pathlib import Path

DIRECTORY = Path('/var/lib/omarchy-kids')


def extension_until(uid, now):
    try:
        path = DIRECTORY / f'desktop-extension-{int(uid)}.json'
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd) as stream:
            info = os.fstat(stream.fileno())
            if info.st_uid != 0 or info.st_mode & 0o022 or not stat.S_ISREG(info.st_mode):
                return 0
            data = json.loads(stream.read(4096))
        start, end = float(data['created']), float(data['expires'])
        if (data['uid'] == int(uid) and math.isfinite(start) and math.isfinite(end)
                and 0 < end - start <= 3600 and start <= now < end):
            return end
    except (OSError, ValueError, TypeError, KeyError):
        pass
    return 0
