"""Exercise only the existing Python package readers, with native launch blocked."""
from pathlib import Path
import ctypes
import hashlib
import json
import os
import subprocess
import sys

PROJECT = Path(__file__).absolute().parents[3]
STAGE = Path(__file__).absolute().parent
SHA = 'fbb3b9ec4b43242cbee022b9cdf712f37ccbdf6290015ee2ee27b6547a570573'
ROOT = PROJECT / 'Build/UnitAssets' / SHA
BASE = PROJECT / 'Build/UnitAssets/480678966a78bedbee642040285010aa86f8a2cc34b0929c2774dcee8ab54266'


def artifact(path):
    path = Path(path)
    with path.open('rb') as stream:
        sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha}


def main():
    output = STAGE / 'preparation_contract.json'
    assert not output.exists(), 'Do not overwrite a completed proof'
    blocked = []
    def audit(event, args):
        if event in ('subprocess.Popen', 'os.system', 'os.startfile', 'os.startfile/2', 'ctypes.dlopen'):
            blocked.append(event)
            raise RuntimeError('Native execution/library launch is held: ' + event)
        if event == 'open' and isinstance(args[0], (str, bytes, os.PathLike)):
            path = os.path.abspath(os.fsdecode(args[0])).replace('\\', '/').casefold()
            forbidden = '/my games/sid meier\'s civilization 5/'
            if forbidden in path:
                blocked.append('retail_user_state_open')
                raise RuntimeError('Original mod-test user state is held')
    sys.addaudithook(audit)
    sys.path.insert(0, str(PROJECT / 'tools'))
    import run_interactive_game
    import unit_animation_assets
    before = [artifact(path) for path in (
        PROJECT / 'tools/run_interactive_game.py', PROJECT / 'tools/unit_animation_assets.py',
        ROOT / 'unit-assets.bin', ROOT / 'unit-assets.manifest.json',
        BASE / 'unit-assets.bin', BASE / 'unit-assets.manifest.json')]
    assert before[0]['sha256'] == 'b625fd17b3c7b1315696e7caaf63724fb6aad8dd75460921f93843a9974d4311'
    assert before[2]['sha256'] == SHA and before[3]['sha256'] == '5fcfbdc669ffd233c4ec64118e8e938656079527028a7ac052659421c6b24e7a'
    manifest, package = run_interactive_game.read_unit_assets_manifest(ROOT / 'unit-assets.manifest.json')
    assert manifest == before[3] and package == before[2]
    old = unit_animation_assets.embedded_assets(BASE / 'unit-assets.bin')
    new = unit_animation_assets.embedded_assets(ROOT / 'unit-assets.bin')
    assert old == new and set(new) == unit_animation_assets.RAW_NAMES
    assert not blocked
    assert before == [artifact(Path(row['path'])) for row in before]
    record = {'status': 'PASS_EXISTING_PYTHON_PREPARATION_READERS_ONLY',
              'inputs_before': before, 'inputs_after': before, 'runner': artifact(Path(__file__)),
              'manifest_reader': 'run_interactive_game.read_unit_assets_manifest',
              'embedded_reader': 'unit_animation_assets.embedded_assets',
              'package': package, 'manifest': manifest,
              'old_and_new_embedded_inputs_equal': True,
              'embedded_inputs': [{'name': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()} for name, data in sorted(new.items())],
              'audit_scope': 'After standard-library initialization; before project imports and package-reader calls.',
              'forbidden_attempts': blocked, 'process_or_ctypes_library_calls_after_guard': 0,
              'host_gamecore_gpu_hwnd_executed': False, 'runtime_materialized': False,
              'default_promoted': False, 'actual_screen_verified': False,
              'limits': ['Existing Python package reader acceptance is not native loader, GPU, animation or game acceptance.']}
    with output.open('x', encoding='utf8') as stream:
        json.dump(record, stream, indent=2)
        stream.write('\n')
    print(json.dumps({'status': record['status'], 'report': artifact(output), 'embedded_inputs': len(new), 'forbidden_attempts': blocked}))


if __name__ == '__main__':
    main()
