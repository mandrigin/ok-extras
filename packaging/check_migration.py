"""Read-only, on-device migration check. Prints no household configuration."""
import datetime as dt
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kids_policy.configver import migrate_policy, migrate_allowlist
from kids_policy.migrate import migrate_state
from kids_policy.budget import Policy
from kids_policy.grants import Grant, extra_seconds
from kids_policy.allowlist import enabled_ids

original = json.loads(Path('/etc/omarchy-kids/policy.json').read_text())
allow = json.loads(Path('/etc/omarchy-kids/allowlist.json').read_text())
state = json.loads(Path('/var/lib/omarchy-kids/state.json').read_text())
updated, changed = migrate_policy(original)
updated['allowlist'], _ = migrate_allowlist(allow)
assert set(enabled_ids(updated)) == set(enabled_ids({'allowlist': allow})), 'Allow-list changed'
assert updated['child_uid'] == original['child_uid'], 'Account changed'
assert updated['play_windows'] == original['play_windows'], 'Schedule changed'
for name, spec in original.get('apps', {}).items():
    assert updated['apps'][name]['argv'] == spec['argv'], 'Launch command changed'
converted = migrate_state(state)
assert converted['grants'] == state.get('grants', []), 'Grants changed'
assert converted['apps'] == state.get('apps', {}), 'App usage changed'
for name, spec in updated['budgets'].items():
    fields = spec.get('legacy_fields', {})
    if fields:
        assert converted['budgets_used_seconds'].get(name, 0) == state.get(fields['used'], 0), 'Budget usage changed'
        assert spec['daily_minutes'] == original[name + '_daily_minutes'], 'Daily allowance changed'
again, changed_again = migrate_policy(updated)
assert not changed_again and again == updated, 'Migration is not idempotent'
print('PASS: account, schedule, allow-list, launch commands, daily limits, usage and grants preserved.')
print('PASS: migration is idempotent. No files or running services were changed.')
