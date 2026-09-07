"""The app must not execute until its launcher has completed adoption."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


@unittest.skipUnless(os.geteuid() == 0, 'requires root in a disposable Linux test environment')
class LaunchTests(unittest.TestCase):
    def test_fast_runtime_waits_for_adoption(self):
        helper = Path(__file__).resolve().parents[1] / 'bin/omarchy-kids-launch'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            adopted, result = root / 'adopted', root / 'result'
            runtime = f'from pathlib import Path; Path({str(result)!r}).write_text(str(Path({str(adopted)!r}).exists()))'
            script = f'''
import runpy, sys, time
from pathlib import Path
from unittest.mock import patch
config = {{'child_uid': 0, 'apps': {{'runtime': {{'argv': [sys.executable, '-c', {runtime!r}]}}}}}}
def request(payload):
    if payload['op'] == 'adopt':
        time.sleep(0.2)
        Path({str(adopted)!r}).touch()
    return {{'ok': True}}
with patch('kids_policy.client.request', side_effect=request), patch('kids_policy.service.load_config', return_value=config):
    sys.argv = [{str(helper)!r}, 'runtime']
    runpy.run_path({str(helper)!r}, run_name='__main__')
for attempt in range(100):
    if Path({str(result)!r}).exists(): break
    time.sleep(0.02)
'''
            subprocess.run([sys.executable, '-c', script], check=True, timeout=10)
            self.assertEqual(result.read_text(), 'True')
