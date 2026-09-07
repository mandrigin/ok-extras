"""Refresh optional helper code for already configured extensions; install no apps."""
import json
from pathlib import Path
import shutil
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
root = Path('/opt/omarchy-kids-policy/extensions')
config = json.loads(Path('/etc/omarchy-kids/policy.json').read_text())
for name in config.get('extensions', []):
    from kids_policy.registry import identifier
    directory = root / identifier(name)
    for path in (directory / 'bin').glob('*'):
        shutil.copy2(path, Path('/usr/bin') / path.name)
        (Path('/usr/bin') / path.name).chmod(0o755)
    catalog = directory / 'catalog.json'
    target = Path('/etc/omarchy-kids/extensions') / (name + '.json')
    if catalog.is_file() and not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(catalog, target)
