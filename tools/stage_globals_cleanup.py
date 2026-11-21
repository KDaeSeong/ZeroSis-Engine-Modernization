"""Stage verified globals_cleanup source, caller deltas and native boundary evidence."""
import json
import shutil
from pathlib import Path
from collect_baseline import PROJECT, digest
from globals_cleanup_evidence import validate
from stage_world_builder_map_bridge import artifacts


def files_for_review():
    build, result, entry = validate()
    declared = json.loads(Path(entry['caller_plan']['path']).read_text(encoding='utf-8'))
    paths = set(artifacts([build, result, entry, declared]))
    for executable in build['builds'].values():
        paths.update(Path(executable['executable'][key]) for key in ('log', 'map'))
    paths.update(PROJECT / 'Source/SDK_BNW_x64' / file for file in declared['files'])
    paths.update(PROJECT / relative for relative in (
        'tools/define_globals_cleanup_patches.py', 'tools/build_globals_cleanup.py', 'tools/verify_globals_cleanup.py',
        'tools/globals_cleanup_evidence.py', 'tools/stage_globals_cleanup.py', 'docs/M3_GLOBALS_CLEANUP.md'))
    return sorted(p for p in paths if p.is_relative_to(PROJECT))


def main():
    _, result, _ = validate()
    root = PROJECT / 'Stage/GlobalsCleanup'
    manifest = root / 'review_bundle.json'
    prior = json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else {'files': []}
    known = {r['path']: r['sha256'] for r in prior['files']}
    copies = []
    for source in files_for_review():
        target = root / source.relative_to(PROJECT)
        sha = digest(source)
        if target.is_file() and digest(target) not in (sha, known.get(str(target))):
            raise RuntimeError('Untracked globals_cleanup review edit: ' + str(target))
        copies.append((source, target, sha))
    files = []
    for source, target, sha in copies:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        if digest(source) != sha or digest(target) != sha:
            raise RuntimeError('GlobalsCleanup review copy changed')
        files.append({'source': str(source), 'path': str(target), 'sha256': sha})
    report = {'status': 'GLOBALS_CLEANUP_CALLERS_REVIEW_READY', 'files': files,
              'native_checks': sum(r['checks'] for r in result['runs'][:2]), 'compiled_sdk_objects': 161,
              'other_owners_and_host_instrumented': True, 'sdk_callers_compiled': True,
              'whole_gc_init_uninit_verified': False, 'gamecore_loaded': False, 'game_launched': False,
              'scope': 'EXACT_SDK_CLEANUP_BODIES_WITH_INSTRUMENTED_DEPENDENCIES_NOT_FULL_GAMECORE_RUNTIME'}
    manifest.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': report['status'], 'files': len(files), 'checks': report['native_checks']}))


if __name__ == '__main__':
    main()
