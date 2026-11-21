"""Stage ownership source, compiled callers and isolated native evidence."""
import json
import shutil
from pathlib import Path
from collect_baseline import PROJECT, digest
from host_binding_evidence import validate
from stage_world_builder_map_bridge import artifacts


def files_for_review():
    build, result, entry = validate()
    declared = json.loads(Path(entry['caller_plan']['path']).read_text(encoding='utf-8'))
    paths = set(artifacts([build, result, entry, declared]))
    for executable in build['builds'].values():
        paths.update(Path(executable['executable'][key]) for key in ('log', 'map'))
    paths.update(PROJECT / 'Source/SDK_BNW_x64' / f for f in declared['files'])
    paths.update(PROJECT / f for f in ('tools/define_host_binding_patches.py', 'tools/build_host_binding.py',
        'tools/verify_host_binding.py', 'tools/host_binding_evidence.py', 'tools/stage_host_binding.py',
        'docs/M3_HOST_BINDING.md'))
    return sorted(p for p in paths if p.is_relative_to(PROJECT))


def main():
    _, result, _ = validate()
    root = PROJECT / 'Stage/HostBinding'
    manifest = root / 'review_bundle.json'
    prior = json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else {'files': []}
    known = {r['path']: r['sha256'] for r in prior['files']}
    copies = []
    for source in files_for_review():
        target = root / source.relative_to(PROJECT)
        sha = digest(source)
        if target.is_file() and digest(target) not in (sha, known.get(str(target))):
            raise RuntimeError('Untracked host binding review edit: ' + str(target))
        copies.append((source, target, sha))
    files = []
    for source, target, sha in copies:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        if digest(source) != sha or digest(target) != sha:
            raise RuntimeError('Host binding review copy changed')
        files.append({'source': str(source), 'path': str(target), 'sha256': sha})
    report = {'status': 'HOST_BINDING_CALLERS_REVIEW_READY', 'files': files,
              'native_checks': sum(r['checks'] for r in result['runs']), 'compiled_sdk_objects': 161,
              'host_and_context_instrumented': True, 'sdk_callers_compiled': True,
              'whole_gc_lifecycle_verified': False, 'gamecore_loaded': False, 'game_launched': False,
              'scope': 'EXACT_SDK_OWNERSHIP_CALLERS_WITH_INSTRUMENTED_HOST_CONTEXT_NOT_FULL_GAMECORE_RUNTIME'}
    manifest.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': report['status'], 'files': len(files), 'checks': report['native_checks']}))


if __name__ == '__main__':
    main()
