"""Install a narrow native-time hook without changing schedules or balances."""
import ast
from pathlib import Path
import shutil
import sys

SERVICE = Path('/usr/share/omarchy/lib/parent/omarchy_kids/screen_time/service.py')


def patched(source):
    if 'ok_extras_extension' in source:
        return source
    # Refuse unknown layouts before modifying the installed native service.
    tree = ast.parse(source)
    account = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'Account')
    methods = {node.name: node for node in account.body if isinstance(node, ast.FunctionDef)}
    block, status = methods['blocking_period'], methods['status']
    lines = source.splitlines(keepends=True)
    block_source = ''.join(lines[block.lineno - 1:block.end_lineno])
    status_source = ''.join(lines[status.lineno - 1:status.end_lineno])
    needle = '        return self._period(now, "block")'
    assert block_source.count(needle) == 1, 'Unsupported native bedtime implementation'
    assert status_source.count('        return payload') == 1, 'Unsupported native status implementation'
    source = source.replace(block_source, block_source.replace(needle,
        '        if extension_until(self.uid, now):\n            return None\n' + needle))
    source = source.replace(status_source, status_source.replace('        return payload',
        '        payload["extension_supported"] = True\n'
        '        payload["extension_until"] = extension_until(self.uid, now)\n'
        '        return payload'))
    source += '\n# ok_extras_extension: expiring, root-approved bedtime exceptions.\nfrom .ok_extras_extension import extension_until\n'
    compile(source, str(SERVICE), 'exec')
    return source


def main():
    source = SERVICE.read_text()
    updated = patched(source)
    if '--check' in sys.argv:
        print('Native desktop-time integration is compatible')
        return
    backup = SERVICE.with_suffix('.py.before-ok-extras')
    if not backup.exists():
        shutil.copy2(SERVICE, backup)
    helper = Path(__file__).resolve().parents[1] / 'kids_policy/native_extension.py'
    shutil.copyfile(helper, SERVICE.with_name('ok_extras_extension.py'))
    SERVICE.with_name('ok_extras_extension.py').chmod(0o644)
    stage = SERVICE.with_suffix('.tmp')
    stage.write_text(updated)
    stage.chmod(0o644)
    stage.replace(SERVICE)


if __name__ == '__main__':
    main()
