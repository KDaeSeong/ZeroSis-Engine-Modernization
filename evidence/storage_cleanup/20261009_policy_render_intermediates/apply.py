"""Apply the already reviewed exact three-candidate retirement once."""
import gzip
import json
import os
from pathlib import Path
import sys

FOLDER = Path(__file__).resolve().parent
ROOT = FOLDER.parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import prune_superseded_runtime_artifacts as p

plan_path = p.boundary(FOLDER / 'plan.json')
plan = json.loads(plan_path.read_text(encoding='utf8'))
assert plan['status'] == 'PREVIEW_ONLY' and plan['scope'] == 'EXACT_THREE_SUPERSEDED_POLICY_RENDER_CANDIDATES'
assert p.digest(ROOT / 'tools/prune_superseded_runtime_artifacts.py') == plan['helper_sha256'] == '99eed1b129e24139b435feb34e2a88172ba7332ffaf9a3e4d3d20f9dfa177baa'
assert p.digest(FOLDER / 'protected-final.json.gz') == plan['protected_sha256']
assert p.digest(FOLDER / 'retired-files.jsonl.gz') == plan['ledger_sha256']
assert not (FOLDER / 'cleanup.json').exists()
allowed = {'20261009T045057Z_bebb746a6d3f', '20261009T051500Z_social_policy_alpha_zero_01', '20261009T050344Z_24dcc6958207'}
targets = [p.boundary(ROOT / row['path']) for row in plan['targets']]
assert {path.name for path in targets} == allowed and all(path.parent == ROOT / 'Build/UiPopupPixels' for path in targets)
with gzip.open(FOLDER / 'protected-final.json.gz', 'rt', encoding='utf8') as stream:
    protected = json.load(stream)
with gzip.open(FOLDER / 'retired-files.jsonl.gz', 'rt', encoding='utf8') as stream:
    rows = [json.loads(line) for line in stream]
assert len(rows) == plan['files'] == 212
assert len({r['path'] for r in rows}) == len(rows)

def verify():
    cache = {}
    for name, expected in protected.items():
        path = p.boundary(Path(name))
        info = p.regular(path)
        assert not any(path.is_relative_to(target) for target in targets)
        identity = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
        if identity not in cache:
            cache[identity] = p.digest(path)
        assert cache[identity] == expected, name

p.no_active_host()
verify()
report = {'status': 'REMOVING', 'plan_sha256': p.digest(plan_path), 'protected_files': len(protected),
          'protected_hashes_verified_before': True, 'removed_files': 0, 'removed_logical_bytes': 0, 'errors': []}
output = FOLDER / 'cleanup.json'
def checkpoint():
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
checkpoint()
try:
    p.no_active_host()
    for row in rows:
        path = p.boundary(ROOT / row['path'])
        assert any(path.is_relative_to(target) for target in targets)
        info = p.regular(path)
        assert (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns) == (row['device'], row['file_id'], row['bytes'], row['mtime_ns']), str(path)
        assert p.digest(path) == row['sha256'], str(path)
        p.unlink_without_attribute_changes(path)
        report['removed_files'] += 1
        report['removed_logical_bytes'] += row['bytes']
    for target in targets:
        for current, dirs, files in os.walk(target, topdown=False, followlinks=False):
            assert not files
            p.boundary(Path(current)).rmdir()
    verify()
    report['protected_hashes_verified_after'] = True
    report['status'] = 'PASS_SUPERSEDED_POLICY_RENDER_RETIREMENT'
except Exception as error:
    report['status'] = 'FAILED_PARTIAL_RETIREMENT_RETAINED'
    report['errors'].append(repr(error))
    raise
finally:
    checkpoint()
    print(json.dumps(report))
