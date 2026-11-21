"""Build one overwrite candidate and materialize it without native execution."""
from datetime import datetime, timezone
import argparse
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys

PROJECT = Path(__file__).absolute().parents[3]
STAGE = Path(__file__).absolute().parent
DONOR = '20261016T110835Z_800f48fd88c0'
SOURCE_STAGE = PROJECT / 'evidence/save_overwrite/source_contract'
PROGRESS = PROJECT / 'evidence/save_menu/20261013_original_screen/current_progress.json'
BASE = PROJECT / 'evidence/save_delete/linked_candidate/run_stage.py'
spec = importlib.util.spec_from_file_location('_preserved_delete_stage_common', BASE)
common = importlib.util.module_from_spec(spec)
spec.loader.exec_module(common)
common.PROJECT, common.STAGE = PROJECT, STAGE
artifact, read, write, require = common.artifact, common.read, common.write, common.require


def start():
    output = STAGE / 'scope.json'
    require(not output.exists(), 'Do not overwrite the linked-stage scope')
    progress = read(PROGRESS)
    require(progress['status'] == 'OVERWRITE_SOURCE_COMPONENTS_PASS_LINK_AND_NATIVE_ACCEPTANCE_PENDING',
            'The source-only stage must pass before integration')
    source_path = SOURCE_STAGE / 'conformance.json'
    require(artifact(source_path)['sha256'] == '7b69f3fca41b188d7ff6b403183f0cc2964d47d2e9f135ad9b339f7ff04e43cb',
            'The approved overwrite source receipt differs')
    source = read(source_path)
    require(source['status'] == 'PASS_SOURCE_AND_COMPONENT_ONLY', 'Source component acceptance is missing')
    for row in source['sources']:
        require(artifact(Path(row['path'])) == row, 'An approved source changed')
    before = STAGE / 'source_before/current_progress.json'
    before.parent.mkdir(exist_ok=False)
    before.write_bytes(PROGRESS.read_bytes())
    donor_path = PROJECT / f'evidence/ui_window_host/{DONOR}/build_result.json'
    donor = read(donor_path)
    require(donor['status'] == 'UI_WINDOW_HOST_CANDIDATE_BUILT' and donor['build_id'] == DONOR, 'Donor failed')
    headers = [row for row in donor['compiler_inputs'] if Path(row['path']).name.casefold() == 'uipopupassets.generated.h']
    require(len(headers) == 1, 'Expected one frozen generated-header recovery input')
    require(artifact(Path(headers[0]['path']))['sha256'] == headers[0]['sha256'], 'Donor recovery header differs')
    protected = {row['path']: artifact(Path(row['path'])) for row in
                 read(SOURCE_STAGE / 'baseline_protection.json')['files']}
    protected[str(source_path)] = artifact(source_path)
    protected[str(SOURCE_STAGE / 'storage_after.json')] = artifact(SOURCE_STAGE / 'storage_after.json')
    unchanged = {relative: artifact(PROJECT / relative) for relative in
                 ('Source/Host/UiLoadMenuContract.h', 'tools/prepare_ui_popup_assets.py')}
    require(not list((PROJECT / 'Build').glob('pull-down-compositor-load-driver-owned-overwrite-*')),
            'Source-stage temporary renderer output remains')
    write(output, {'schema': 'zerosis.owned_save_overwrite_linked_scope.v1',
        'utc': datetime.now(timezone.utc).isoformat(), 'previous_goal_turn': 'PROGRESS',
        'requirements': [
            'Retain the full original UI/gameplay x64/multicore and retail save/mod compatibility endpoint.',
            'Embed current overwrite Lua and presentation input; compile and link one current x64 Host.',
            'Reuse attested B6 immutable snapshots without hardlinking mutable Source.',
            'Read actual PE registry/payload bytes and current frozen compilation closure.',
            'Prepare a matching private runtime with private policy settings and no native execution.',
            'Preserve EA0.6/default, B6/R6, recovery candidates and archive schema.',
            'Do not access retail MODS/user saves/settings/processes during human mod testing.',
            'Retire owned compiler intermediates and only superseded inputs proven unnecessary; measure unique file allocation.'],
        'prior_source_conformance': artifact(source_path), 'source19_seals': source['sources'],
        'unchanged_baseline_seals': unchanged, 'progress_before': artifact(PROGRESS),
        'progress_backup': artifact(before), 'generated_header_before': artifact(PROJECT / 'Source/Host/UiPopupAssets.generated.h'),
        'header_recovery': artifact(Path(headers[0]['path'])), 'prepared_assets_recovery': donor['ui_assets'],
        'donor_build': artifact(donor_path), 'protected_artifacts': protected,
        'storage_before': artifact(Path(read(SOURCE_STAGE / 'storage_after.json')['audit']['path'])),
        'common_helper': artifact(BASE),
        'cleanup_at_start': 'Previous source stage removed component scratch and four repeated native builds; latest component proof and frozen recovery inputs retained.',
        'retail_mod_test_hold_active': True, 'default_promoted': False, 'host_gamecore_hwnd_executed': False})
    print(json.dumps({'status': 'SCOPED', 'scope': artifact(output)}, ensure_ascii=False))


def run_command(name, arguments):
    # The preserved helper writes single-use invocation receipts and owns the
    # child until terminal. Only this parent call gets the quiet, lower priority.
    original_run = common.subprocess.run
    def background(*args, **kwargs):
        kwargs['creationflags'] = kwargs.get('creationflags', 0) | subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS
        return original_run(*args, **kwargs)
    common.subprocess.run = background
    try:
        return common.run_command(name, arguments)
    finally:
        common.subprocess.run = original_run


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('start', 'build', 'prepare'))
    parser.add_argument('--build-id')
    args = parser.parse_args()
    if args.action == 'start':
        start()
    elif args.action == 'build':
        raise SystemExit(run_command('build', [str(PROJECT / 'tools/build_ui_window_host.py'), '--reuse-frozen-build', DONOR]))
    else:
        require(args.build_id is not None and re.fullmatch(r'\d{8}T\d{6}Z_[0-9a-f]{12}', args.build_id), 'Exact build ID required')
        invocation = read(STAGE / 'build_invocation.json')
        require(invocation['exit_code'] == 0 and invocation['result']['build_id'] == args.build_id, 'Preparation must use this successful build')
        policy = STAGE / 'PolicyInfo.ini'
        require(not policy.exists(), 'Inspect previous preparation instead of repeating it')
        policy.write_bytes(b'[UserSettings]\r\nPolicyInfo = 1\r\n')
        raise SystemExit(run_command('prepare', [str(STAGE / 'prepare_candidate.py'), '--build-id', args.build_id]))
