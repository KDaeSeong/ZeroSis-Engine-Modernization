"""Stage database loader ownership source, compiled callers and real database evidence."""
import json
import shutil
from pathlib import Path
from collect_baseline import PROJECT, digest
from database_loader_evidence import validate
from stage_world_builder_map_bridge import artifacts


def files_for_review():
    build, result, entry = validate()
    declared = json.loads(Path(entry['caller_plan']['path']).read_text(encoding='utf-8'))
    paths = set(artifacts([build, result, entry, declared]))
    paths.update(PROJECT / 'Source/SDK_BNW_x64' / f for f in declared['files'])
    paths.update(PROJECT / f for f in ('tools/define_database_loader_patches.py', 'tools/build_database_loader.py',
        'tools/verify_database_loader.py', 'tools/database_loader_evidence.py', 'tools/stage_database_loader.py',
        'docs/M3_DATABASE_LOADER.md', 'tools/refresh_database_loader_integration.py', 'tools/refresh_database_loader_stage.py',
        'tools/audit_gc_initialization.py', 'evidence/gc_initialization/source_audit.json'))
    return sorted(p for p in paths if p.is_relative_to(PROJECT))


def main():
    _, result, _ = validate()
    root = PROJECT / 'Stage/DatabaseLoader'
    manifest = root / 'review_bundle.json'
    prior = json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else {'files': []}
    known = {r['path']: r['sha256'] for r in prior['files']}
    copies = []
    for source in files_for_review():
        target = root / source.relative_to(PROJECT)
        sha = digest(source)
        if target.is_file() and digest(target) not in (sha, known.get(str(target))):
            raise RuntimeError('Untracked database loader review edit: ' + str(target))
        copies.append((source, target, sha))
    files = []
    for source, target, sha in copies:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        if digest(source) != sha or digest(target) != sha:
            raise RuntimeError('Database loader review copy changed')
        files.append({'source': str(source), 'path': str(target), 'sha256': sha})
    report = {'status': 'DATABASE_LOADER_CALLERS_REVIEW_READY', 'files': files,
              'native_checks': sum(r['checks'] for r in result['runs']), 'compiled_sdk_objects': 161,
              'other_game_owners_and_prefetch_instrumented': True, 'sdk_callers_compiled': True,
              'whole_gc_lifecycle_verified': False, 'gamecore_loaded': False, 'game_launched': False,
              'scope': 'EXACT_SDK_LOADER_REFCOUNTS_CACHE_REAL_HEAP_SQLITE_NOT_FULL_GAMECORE_RUNTIME'}
    manifest.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': report['status'], 'files': len(files), 'checks': report['native_checks']}))


if __name__ == '__main__':
    main()
