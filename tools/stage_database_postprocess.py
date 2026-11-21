"""Stage SQL postprocessing source, compiled callers and real database evidence."""
import json
import shutil
from pathlib import Path
from collect_baseline import PROJECT, digest
from database_postprocess_evidence import validate
from stage_world_builder_map_bridge import artifacts


def files_for_review():
    build, result, entry = validate()
    declared = json.loads(Path(entry['caller_plan']['path']).read_text(encoding='utf-8'))
    paths = set(artifacts([build, result, entry, declared]))
    paths.update(PROJECT / 'Source/SDK_BNW_x64' / f for f in declared['files'])
    paths.update(PROJECT / f for f in ('tools/define_database_postprocess_patches.py', 'tools/build_database_postprocess.py',
        'tools/verify_database_postprocess.py', 'tools/database_postprocess_evidence.py', 'tools/stage_database_postprocess.py',
        'docs/M3_DATABASE_POSTPROCESS.md', 'tools/refresh_database_postprocess_integration.py', 'tools/refresh_database_postprocess_stage.py',
        'tools/audit_gc_initialization.py', 'evidence/gc_initialization/source_audit.json'))
    return sorted(p for p in paths if p.is_relative_to(PROJECT))


def main():
    _, result, _ = validate()
    root = PROJECT / 'Stage/DatabasePostprocess'
    manifest = root / 'review_bundle.json'
    prior = json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else {'files': []}
    known = {r['path']: r['sha256'] for r in prior['files']}
    copies = []
    for source in files_for_review():
        target = root / source.relative_to(PROJECT)
        sha = digest(source)
        if target.is_file() and digest(target) not in (sha, known.get(str(target))):
            raise RuntimeError('Untracked database postprocessing review edit: ' + str(target))
        copies.append((source, target, sha))
    files = []
    for source, target, sha in copies:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        if digest(source) != sha or digest(target) != sha:
            raise RuntimeError('Database postprocessing review copy changed')
        files.append({'source': str(source), 'path': str(target), 'sha256': sha})
    report = {'status': 'DATABASE_POSTPROCESS_CALLERS_REVIEW_READY', 'files': files,
              'native_checks': sum(r['checks'] for r in result['runs']), 'compiled_sdk_objects': 161,
              'global_database_accessor_instrumented': True, 'sdk_callers_compiled': True,
              'whole_gc_lifecycle_verified': False, 'gamecore_loaded': False, 'game_launched': False,
              'scope': 'EXACT_SDK_SQL_POSTPROCESSING_REAL_X64_DATABASE_NOT_FULL_GAMECORE_RUNTIME'}
    manifest.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': report['status'], 'files': len(files), 'checks': report['native_checks']}))


if __name__ == '__main__':
    main()
