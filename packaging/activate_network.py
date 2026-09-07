"""Manage only the parental-control firewall table selected in policy.json."""
import json
from pathlib import Path
import subprocess
config = json.loads(Path('/etc/omarchy-kids/policy.json').read_text())
if config['network']['mode'] == 'offline':
    subprocess.run(['omarchy-pkg-add', 'nftables'], check=True)
    subprocess.run(['systemctl', 'enable', 'omarchy-kids-net.service'], check=True)
    subprocess.run(['systemctl', 'restart', 'omarchy-kids-net.service'], check=True)
else:
    subprocess.run(['systemctl', 'disable', '--now', 'omarchy-kids-net.service'], check=True)
