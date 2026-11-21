"""Stage the inspected symbol service and link-only DLL as development artifacts."""
import json
import shutil
from pathlib import Path
from collect_baseline import PROJECT, digest
from debug_evidence import validate
from stage_world_builder_map_bridge import artifacts


def files_for_review():
    build, result, link = validate()
    reference_path = PROJECT / 'evidence/debug/reference/entrypoint_disassembly.json'
    reference = json.loads(reference_path.read_text(encoding='utf-8'))
    from debug_stack_evidence import validate as validate_stack
    _, stack, stack_entry = validate_stack()
    declared = json.loads((PROJECT / 'evidence/debug/stack/caller_patch_plan.json').read_text(encoding='utf-8'))
    paths = set(artifacts([build, result, link, reference, stack, stack_entry, declared]))
    paths = {p for p in paths if p.is_relative_to(PROJECT)}
    paths.add(reference_path)
    paths.update(PROJECT / relative for relative in (
        'tools/build_debug_provider.py', 'tools/verify_debug_provider.py', 'tools/probe_debug_link.py',
        'tools/debug_evidence.py', 'tools/stage_debug_provider.py', 'docs/M2_DEBUG_PROVIDER.md',
        'evidence/debug/build_result.json', 'evidence/debug/conformance.json', 'evidence/debug/link_trial.json',
        'tools/define_debug_caller_patches.py', 'tools/debug_stack_evidence.py', 'tools/verify_debug_stack.py',
        'docs/M2_DEBUG_STACK.md'))
    return sorted(paths)


def main():
    build, result, link = validate()
    from debug_stack_evidence import validate as validate_stack
    _, stack, _ = validate_stack()
    root = PROJECT / 'Stage/Debug'
    manifest = root / 'review_bundle.json'
    prior = json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else {'files': []}
    known = {r['path']: r['sha256'] for r in prior['files']}
    copies = []
    for source in files_for_review():
        target = root / source.relative_to(PROJECT)
        sha = digest(source)
        if target.is_file() and digest(target) not in (sha, known.get(str(target))):
            raise RuntimeError('Untracked debug review edit: ' + str(target))
        copies.append((source, target, sha))
    files = []
    for source, target, sha in copies:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        if digest(source) != sha or digest(target) != sha:
            raise RuntimeError('Debug review copy changed')
        files.append({'source': str(source), 'path': str(target), 'sha256': sha})
    report = {'status': 'DEBUG_SYMBOL_AND_LINK_CANDIDATE_REVIEW_READY', 'files': files,
              'native_checks': result['execution']['checks'], 'candidate_unresolved': link['after'],
              'sdk_stack_walk_checks': stack['execution']['checks'], 'sdk_stack_walk_verified': True,
              'official_unresolved': link['official_unresolved_symbols'], 'candidate_dll_built': True,
              'explicit_bootstrap_integrated': True,
              'loader_lock_bootstrap_fixed': False, 'gamecore_loaded': False, 'game_launched': False,
              'scope': 'SYMBOL_COMPONENT_AND_EXPLICIT_BOOTSTRAP_LINKED_DLL; GAMECORE_RUNTIME_PENDING'}
    manifest.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': report['status'], 'files': len(files)}))


if __name__ == '__main__':
    main()
