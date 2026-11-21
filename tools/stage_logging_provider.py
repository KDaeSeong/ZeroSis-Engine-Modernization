"""Stage the SDK logger and its exact caller changes for review, never into the game."""
import json
import shutil
from pathlib import Path

from collect_baseline import PROJECT, digest
from logging_evidence import validate, validate_callers, validate_link
from stage_world_builder_map_bridge import artifacts


def files_for_review(build):
    _, conformance, _ = validate()
    link = validate_link()
    callers = validate_callers()
    regression = json.loads(Path(conformance['missing_error_code_regression']['path']).read_text(encoding='utf-8'))
    paths = set(artifacts([build, conformance, link, callers, regression]))
    paths = {p for p in paths if p.is_relative_to(PROJECT)}
    paths.update(PROJECT / 'Source/SDK_BNW_x64' / row['file'] for row in callers['calls'])
    paths.update(PROJECT / relative for relative in (
        'tools/define_logging_caller_patches.py', 'tools/build_logging_provider.py',
        'tools/verify_logging_provider.py', 'tools/logging_evidence.py',
        'tools/probe_logging_link.py', 'tools/stage_logging_provider.py',
        'docs/M2_LOGGING_PROVIDER.md', 'evidence/logging/build_result.json',
        'evidence/logging/conformance.json', 'evidence/logging/caller_patch_plan.json',
        'evidence/logging/link_trial.json'))
    return sorted(paths)


def main():
    build, conformance, _ = validate()
    link = validate_link()
    root = PROJECT / 'Stage/Logging'
    manifest = root / 'review_bundle.json'
    prior = json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else {'files': []}
    known = {row['path']: row['sha256'] for row in prior['files']}
    copies = []
    for source in files_for_review(build):
        target = root / source.relative_to(PROJECT)
        sha = digest(source)
        if target.is_file() and digest(target) not in (sha, known.get(str(target))):
            raise RuntimeError('Untracked logging review edit: ' + str(target))
        copies.append((source, target, sha))
    files = []
    for source, target, sha in copies:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        if digest(source) != sha or digest(target) != sha:
            raise RuntimeError('Logging review copy changed')
        files.append({'source': str(source), 'path': str(target), 'sha256': sha})
    report = {
        'status': 'LOGGING_REVIEW_READY', 'files': files,
        'native_checks': conformance['execution']['checks'],
        'failure_cases': conformance['execution']['fault_cases'],
        'literal_sdk_callers': conformance['sdk_caller_records'],
        'shared_log_records': conformance['shared_records'],
        'official_gamecore_unresolved': link['official_unresolved_symbols'],
        'gamecore_loaded': False, 'game_launched': False, 'game_multicore_verified': False,
        'original_concrete_logger_oracle_available': False, 'power_loss_recovery_verified': False,
    }
    manifest.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': report['status'], 'files': len(files), 'native_checks': report['native_checks']}))


if __name__ == '__main__':
    main()
