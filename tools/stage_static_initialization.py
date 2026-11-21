"""Copy current read-only startup audit evidence into a separate review bundle."""
import json
import shutil
from pathlib import Path
from collect_baseline import PROJECT, digest
from verify_static_initialization import validate
from stage_world_builder_map_bridge import artifacts


def main():
    report = validate()
    root = PROJECT / 'Stage/BootstrapAudit'
    manifest = root / 'review_bundle.json'
    prior = json.loads(manifest.read_text(encoding='utf-8')) if manifest.is_file() else {'files': []}
    known = {r['path']: r['sha256'] for r in prior['files']}
    sources = {p for p in artifacts(report) if p.is_relative_to(PROJECT)}
    sources.update(PROJECT / relative for relative in (
        'evidence/bootstrap/static_initialization/inventory.json',
        'tools/audit_static_initialization.py', 'tools/verify_static_initialization.py',
        'tools/stage_static_initialization.py', 'docs/M3_STATIC_BOOTSTRAP_AUDIT.md'))
    copies = []
    for source in sorted(sources):
        target = root / source.relative_to(PROJECT); sha = digest(source)
        if target.is_file() and digest(target) not in (sha, known.get(str(target))):
            raise RuntimeError('Untracked bootstrap audit review edit: ' + str(target))
        copies.append((source, target, sha))
    files = []
    for source, target, sha in copies:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        if digest(source) != sha or digest(target) != sha:
            raise RuntimeError('Bootstrap audit changed during staging')
        files.append({'source': str(source), 'path': str(target), 'sha256': sha})
    result = {'status': 'STATIC_BOOTSTRAP_AUDIT_REVIEW_READY_RUNTIME_GATE_OPEN', 'files': files,
              'startup_entries': len(report['startup_entries']), 'direct_nodes': len(report['reachable_direct_nodes']),
              'gamecore_loaded': False, 'game_launched': False, 'runtime_loader_safety_verified': False,
              'ownership_findings_open': report['globals_ownership_review']['directly_allocated_fields_missing_from_uninit_deletes']}
    manifest.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': result['status'], 'files': len(files), 'runtime_verified': False}))


if __name__ == '__main__':
    main()
