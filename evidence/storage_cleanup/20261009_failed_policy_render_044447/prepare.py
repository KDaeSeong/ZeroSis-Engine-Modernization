"""Inventory the exact retired policy run and host; seal only after source edits stop."""
import argparse
import gzip
import json
from pathlib import Path
import shutil
import sys

FOLDER = Path(__file__).resolve().parent
ROOT = FOLDER.parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import prune_superseded_runtime_artifacts as p

def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf8')

def inventory():
    assert not (FOLDER / 'inventory.json').exists()
    run = ROOT / 'Build/InteractiveGameRuntime/20261009T044447Z_88730f00e24b'
    session = run / 'sessions/c90eeeaa202df7b7f39061a9d361c12e'
    evidence = ROOT / 'evidence/interactive_game/20261009T044447Z_88730f00e24b'
    host = ROOT / 'Build/UiWindowHost/20261009T044208Z_dac2a6976a8f'
    host_evidence = ROOT / 'evidence/ui_window_host/20261009T044208Z_dac2a6976a8f'
    mapping = [(session / 'play-ui-21.json', 'run07-play-ui-21.json.gz'),
               (session / 'rules.db', 'run07-session-rules.db.gz'),
               *[(evidence / source, 'run07-' + target) for source, target in (
                   ('result.json', 'result.json.gz'), ('driver_result.json', 'driver-result.json.gz'),
                   ('request.json', 'request.json.gz'), ('stdout.log', 'stdout.log.gz'),
                   ('stderr.log', 'stderr.log.gz'), ('social_policy_validation.json', 'policy-validation.json.gz'))],
               (host_evidence / 'build_result.json', 'host09-build-result.json.gz')]
    preserved = []
    for source, name in mapping:
        source = p.boundary(source)
        info = p.regular(source)
        before = p.digest(source)
        destination = FOLDER / name
        assert not destination.exists()
        with source.open('rb') as inp, gzip.open(destination, 'wb', compresslevel=9) as out:
            shutil.copyfileobj(inp, out)
        import hashlib
        with gzip.open(destination, 'rb') as stream:
            assert hashlib.file_digest(stream, 'sha256').hexdigest() == before
        assert p.digest(source) == before
        preserved.append({'source': str(source), 'source_bytes': info.st_size,
                          'uncompressed_sha256': before, 'path': str(destination),
                          'sha256': p.digest(destination), 'bytes': destination.stat().st_size})
    expected = ['6f7d300daa716ffdcde4aeab1fe705f5e5ba849f80a85830e775011ed4b5f70e',
                '1845f3a07feb400721695e0cc3e9be1c1badd15fd2fce83efccb84d59fc77beb']
    assert [item['uncompressed_sha256'] for item in preserved[:2]] == expected
    summaries = []
    identities = {}
    hashes = {}
    ledger = FOLDER / 'retired-files.jsonl.gz'
    with gzip.open(ledger, 'wt', encoding='utf8') as stream:
        for directory in (run, evidence, host, host_evidence):
            directory = p.legal_target(directory)
            count = size = 0
            for path, info in p.inventory(directory):
                identity = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
                if identity not in hashes:
                    hashes[identity] = p.digest(path)
                stored = identities.setdefault((info.st_dev, info.st_ino),
                    {'links': info.st_nlink, 'count': 0, 'stored': p.stored(path)})
                stored['count'] += 1
                row = {'path': str(path.relative_to(ROOT)), 'sha256': hashes[identity], 'bytes': info.st_size,
                       'mtime_ns': info.st_mtime_ns, 'device': info.st_dev, 'file_id': info.st_ino}
                stream.write(json.dumps(row) + '\n')
                count += 1
                size += info.st_size
            summaries.append({'path': str(directory.relative_to(ROOT)), 'files': count, 'logical_bytes': size})
    report = {'root': str(ROOT), 'status': 'INVENTORY_ONLY_NOT_SEALED',
              'scope': 'EXACT_FAILED_POLICY_RENDER_RUN_AND_SUPERSEDED_HOST',
              'script_sha256': p.digest(ROOT / 'tools/prune_superseded_runtime_artifacts.py'),
              'ledger': {'path': str(ledger), 'sha256': p.digest(ledger)},
              'directories': summaries, 'files': sum(row['files'] for row in summaries),
              'logical_bytes': sum(row['logical_bytes'] for row in summaries),
              'estimated_reclaimable_file_storage': sum(v['stored'] for v in identities.values() if v['count'] == v['links']),
              'preserved_compressed_inputs_and_diagnostics': preserved,
              'latest_host': '20261009T050937Z_6cab04929d86', 'latest_failed_run': '20261009T051138Z_c2235f6a7d52',
              'user_saves_or_manual_runtime_deleted': False}
    write(FOLDER / 'inventory.json', report)
    print(json.dumps({k: report[k] for k in ('status', 'files', 'logical_bytes', 'estimated_reclaimable_file_storage')}))

def seal():
    assert not (FOLDER / 'plan.json').exists()
    report = json.loads((FOLDER / 'inventory.json').read_text(encoding='utf8'))
    assert p.digest(Path(report['ledger']['path'])) == report['ledger']['sha256']
    with gzip.open(ROOT / 'evidence/storage_cleanup/20261009_policy_render_intermediates/protected-final.json.gz', 'rt', encoding='utf8') as stream:
        names = json.load(stream)
    for group in ('Source', 'Tests', 'tools'):
        for path in (ROOT / group).rglob('*'):
            if path.is_file():
                names[str(path)] = None
    for row in report['preserved_compressed_inputs_and_diagnostics']:
        assert p.digest(Path(row['path'])) == row['sha256']
        names[row['path']] = None
    for group, identity in [('Build/UiWindowHost', report['latest_host']),
                            ('evidence/ui_window_host', report['latest_host']),
                            ('Build/InteractiveGameRuntime', report['latest_failed_run']),
                            ('evidence/interactive_game', report['latest_failed_run'])]:
        for path in (ROOT / group / identity).rglob('*'):
            if path.is_file():
                names[str(path)] = None
    protected = {}
    hashes = {}
    targets = [p.legal_target(ROOT / row['path']) for row in report['directories']]
    for name in names:
        path = p.boundary(Path(name))
        assert not any(path.is_relative_to(target) for target in targets)
        info = p.regular(path)
        identity = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
        if identity not in hashes:
            hashes[identity] = p.digest(path)
        protected[name] = hashes[identity]
    destination = FOLDER / 'protected-final.json.gz'
    with gzip.open(destination, 'wt', encoding='utf8') as stream:
        json.dump(protected, stream)
    report.update(status='PREVIEW_ONLY', protected={'path': str(destination), 'sha256': p.digest(destination)},
                  protected_files=len(protected))
    write(FOLDER / 'plan.json', report)
    print(json.dumps({'status': report['status'], 'plan': str(FOLDER / 'plan.json'),
                      'files': report['files'], 'logical_bytes': report['logical_bytes'],
                      'protected_files': len(protected), 'directories': report['directories']}))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--seal', action='store_true')
    args = parser.parse_args()
    seal() if args.seal else inventory()
