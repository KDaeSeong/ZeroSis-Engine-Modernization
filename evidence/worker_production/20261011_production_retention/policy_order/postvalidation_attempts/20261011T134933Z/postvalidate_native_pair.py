"""Recheck preserved native artifacts without rewriting their original verdicts.

This follow-up checks the natural worker/UI contracts and checkpoint pair only.
It does not replace the native aggregate result or promote a manual release.
"""
from __future__ import annotations

import ast
import hashlib
import importlib
import json
import re
import shutil
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

project = Path(__file__).resolve().parents[4]
output = Path(__file__).resolve().parent
fresh_id = '20261011T124731Z_b821f4b6c26a'
restore_id = '20261011T125838Z_2f697438e208'
seal = hashlib.sha256(b''.join((project / 'tools' / name).read_bytes() for name in
                     ('worker_research_timeline.py', 'verify_interactive_decisions.py',
                      'action_info_panel_timeline.py'))).hexdigest()[:16]
frozen = output / 'corrected_verifiers' / seal
attempt = output / 'postvalidation_attempts' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
attempt.mkdir(parents=True, exist_ok=False)
script_copy = attempt / Path(__file__).name
shutil.copy2(Path(__file__), script_copy)

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def artifact(path):
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha(path)}

def require(condition, reason):
    if not condition:
        raise RuntimeError(reason)

def announce(stage):
    print(stage, flush=True)

def freeze_dependencies():
    pending = ['verify_interactive_decisions', 'action_info_panel_timeline']
    names = set()
    while pending:
        name = pending.pop()
        source = project / 'tools' / (name + '.py')
        if name in names or not source.is_file():
            continue
        names.add(name)
        for node in ast.walk(ast.parse(source.read_text('utf-8'))):
            imports = [node.module] if isinstance(node, ast.ImportFrom) else \
                      [alias.name for alias in node.names] if isinstance(node, ast.Import) else []
            pending.extend(value.split('.')[0] for value in imports if value)
    frozen.mkdir(parents=True, exist_ok=True)
    inventory = []
    for name in sorted(names):
        source, target = project / 'tools' / (name + '.py'), frozen / (name + '.py')
        if not target.exists():
            shutil.copy2(source, target)
        require(sha(source) == sha(target), 'Corrected frozen verifier differs from the tested source: ' + name)
        inventory.append({'source': artifact(source), 'frozen': artifact(target)})
    (output / 'corrected_verifier_inventory.json').write_text(json.dumps(inventory, indent=2) + '\n', encoding='utf-8')
    return inventory

def read_json(path):
    return json.loads(path.read_text('utf-8'))

report = {'status': 'FAILED', 'scope': 'PRESERVED_NATURAL_WORKER_UI_AND_CHECKPOINT_PAIR',
          'native_results_reclassified': False, 'manual_release_promoted': False,
          'full_gameplay_verified': False, 'retail_save_compatibility_verified': False}
protected = []
for run in (fresh_id, restore_id):
    evidence = project / 'evidence/interactive_game' / run
    protected.extend(evidence / name for name in ('request.json', 'result.json', 'attempt.json',
                                                 'stdout.log', 'stderr.log', 'driver_result.json'))
    protected.extend((evidence / 'frozen_inputs').glob('*.py'))
protected.extend(project / name for name in ('Source/Host/UiPopupContext.h', 'Source/Host/InteractiveUiSession.h',
                                            'tools/worker_research_timeline.py', 'Tests/test_worker_research_timeline.py'))
before = {str(path): sha(path) for path in protected}
try:
    inventory = freeze_dependencies()
    sys.path.insert(0, str(frozen))
    verifier = importlib.import_module('verify_interactive_decisions')
    hud = importlib.import_module('action_info_panel_timeline')
    # The copied modules retain their exact source bytes. Their common workspace
    # root is rebound explicitly because the copies live in an evidence folder.
    for module in tuple(sys.modules.values()):
        module_path = getattr(module, '__file__', None)
        if module_path and Path(module_path).parent == frozen and hasattr(module, 'PROJECT'):
            module.PROJECT = project
    verifier.EVIDENCE = project / 'evidence/interactive_game'
    verifier.RUNTIME = project / 'Build/InteractiveGameRuntime'
    verifier.base.ROOT = verifier.EVIDENCE
    verifier.base.RUNTIME_ROOT = verifier.RUNTIME
    report['corrected_verifiers'] = inventory
    runs = []
    loaded = []
    known_reason = 'Worker research: policy popup did not follow the original notification'
    expected_failures = ['Natural worker policy validation failed: ' + known_reason,
                         'Natural worker production validation failed: ' + known_reason,
                         'ActionInfoPanel input dispatch validation failed: ' + known_reason]
    for run_id in (fresh_id, restore_id):
        announce('CHECKING_PRESERVED_NATIVE_RUN=' + run_id)
        evidence = verifier.EVIDENCE / run_id
        request, result = (read_json(evidence / name) for name in ('request.json', 'result.json'))
        runtime = Path(request['cwd']).resolve(strict=True)
        require(runtime == (verifier.RUNTIME / run_id).resolve(strict=True), 'Private runtime identity differs')
        require(request['run_id'] == result['run_id'] == run_id, 'Native run identity differs')
        require(result['status'] == ('CONTINUOUS_INTERACTIVE_SDK_WORKER_BUILD_SMOKE_PASS' if run_id == fresh_id else
                                    'CONTINUOUS_INTERACTIVE_SDK_WORKER_BUILD_RESTORE_SMOKE_FAILED'),
                'Unexpected original verdict; this follow-up is scoped to the preserved pair')
        require(result.get('failures') == ([] if run_id == fresh_id else expected_failures),
                'Native result has another failure outside the diagnosed validator ordering defect')
        verifier.check_artifacts(request)
        verifier.check_artifacts({key: value for key, value in result.items() if key != 'generated_files'})
        verifier.exact_artifact(result['request'], evidence / 'request.json', 'native request')
        stdout = verifier.text_artifact(result['stdout'], evidence / 'stdout.log', 'native stdout')
        stderr = verifier.text_artifact(result['stderr'], evidence / 'stderr.log', 'native stderr')
        process = read_json(verifier.exact_artifact(result['attempt'], evidence / 'attempt.json', 'process attempt'))
        require(result['returncode'] == process['returncode'] == 0 and
                result['timed_out'] is process['timed_out'] is False and process['status'] == 'FINISHED' and
                process['pid'] == result['driver_pid'], 'Native driver/process did not finish normally')
        require(result.get('runtime_inputs_unchanged') is True and
                request.get('stage_or_mods_changed') is result.get('stage_or_mods_changed') is False,
                'Native runtime input/deployment preservation failed')
        # The original sequence booleans depend on aggregate success. Do not
        # manufacture PASS flags to use a PASS-only reader; recheck the exact
        # request and the actual timelines/packets through their independent APIs.
        require(verifier.exact_worker_research_profile(request) and
                request.get('input_profile') == 'POSTED_HWND_CONTINUOUS_TREE_DECISION_UI_LOOP' and
                result.get('decision_ui_smoke_requested') is result.get('research_tree_requested') is True and
                not any(line.startswith('INTERACTIVE_GAME_MENU_') for line in stdout.splitlines()),
                'Not the exact isolated worker/full-HUD/tree input profile')
        verifier.verify_native_failure_markers(stdout, stderr, notification_panel_requested=True,
                                               restored=run_id == restore_id)
        provenance = verifier.provenance(request, result, runtime, research_tree=True)
        by_name, generated = verifier.generated_files(result, runtime)
        driver = read_json(Path(result['interactive_ui_driver']['path']))
        require(driver.get('status') == 'INTERACTIVE_UI_DRIVER_PASS' and driver.get('returncode') == 0 and
                driver.get('error') is None, 'Actual original scene driver failed')
        flags = [function(request) for function in
                 (verifier.worker_research_contract_required, verifier.worker_policy_contract_required,
                  verifier.worker_production_contract_required, verifier.worker_unstack_contract_required)]
        require(flags == [True] * 4, 'Native source/frozen original verifier contract differs')
        restore_state = (request.get('resume_from') or {}).get('expected_state')
        unit = verifier.verify_unit_panel_integration(stdout, runtime, driver, result['frames'], required=True,
                   restored=run_id == restore_id, unit_actions=True, worker_build=True, decisions=True,
                   expected_restore_state=Path(restore_state['path']) if restore_state else None)
        research = verifier.verify_worker_research_integration(stdout, runtime, driver, result['frames'], required=True)
        policy = verifier.verify_worker_policy_integration(stdout, runtime, driver, result['frames'], required=True,
                                                           generated=generated)
        production = verifier.verify_worker_production_integration(stdout, runtime, driver, result['frames'],
                      required=True, generated=generated, unstack_required=True)
        hud_ok, hud_error = hud.verify_action_info_panel_timeline(stdout, run_id == restore_id, True, *flags)
        require(hud_ok is True and hud_error is None, 'Original HUD dispatch failed: ' + str(hud_error))
        started = verifier.rows(stdout, 'INTERACTIVE_GAME_STARTED', r'^INTERACTIVE_GAME_STARTED=(\d+)\|(\d+)\|(\d+)\|(\d+)$')
        closed = verifier.rows(stdout, 'INTERACTIVE_PLAY_CLOSED', r'^INTERACTIVE_PLAY_CLOSED=(\d+)\|NATIVE_CHECKPOINT_WRITTEN$')
        require(len(started) == len(closed) == 1 and
                'INTERACTIVE_PLAY_SHUTDOWN_PASS GAMECORE_LOADED=true GAMECORE_UNLOADED=true' in stdout,
                'Native game did not write a checkpoint and shut down normally')
        saves = verifier.rows(stdout, 'INTERACTIVE_NATIVE_SAVE', r'^INTERACTIVE_NATIVE_SAVE=(\d+)\|(.+)$')
        require(len(saves) == 2 and len({path for _, path in saves}) == 2, 'Native repeated save pair is missing')
        save_proof = []
        for turn, name in saves:
            path = verifier.base.generated(result, Path(name), runtime)
            header, sections = verifier.parse_native_archive(path)
            require(header['turn'] == int(turn) == int(closed[0]) and len(sections) == 133,
                    'Native final save turn/header/sections differ')
            save_proof.append({'artifact': artifact(path), 'header': header})
        row = {'run_id': run_id, 'original_status': result['status'],
               'original_result': artifact(evidence / 'result.json'),
               'original_fresh_process_restore_verified': result.get('fresh_process_restore_verified'),
               'original_research_tree_sequence_verified': result.get('research_tree_sequence_verified'),
               'startup_turn': int(started[0][0]), 'final_turn': int(closed[0]),
               'host_pid': result['pid'], 'driver_pid': result['driver_pid'],
               'generated_file_count': len(generated), 'runtime_inputs_unchanged': True,
               'unit_panel': unit, 'worker_research': research, 'worker_policy': policy,
               'worker_production': production, 'original_hud_dispatch_verified': True,
               'native_saves': save_proof,
               'compiled_source_count': len(provenance['compiled_source_rows'])}
        runs.append(row)
        loaded.append((request, result, stdout, runtime, by_name, saves))
        announce('PRESERVED_NATIVE_RUN_CONTRACTS_PASS=' + run_id)
    source_request, source_result, source_out, source_runtime, source_files, source_saves = loaded[0]
    current_request, current_result, current_out, current_runtime, current_files, current_saves = loaded[1]
    resume = current_request.get('resume_from')
    require(isinstance(resume, dict) and resume['run_id'] == fresh_id and
            current_result['resume_from_run'] == fresh_id, 'Checkpoint source run is not the preserved fresh run')
    identities = [row[key] for row in runs for key in ('host_pid', 'driver_pid')]
    require(all(type(value) is int and value > 0 for value in identities) and len(set(identities)) == 4,
            'Native fresh/restore Host and driver did not use distinct process identities')
    source_checkpoint = verifier.base.generated(source_result, Path(source_saves[-1][1]), source_runtime)
    source_ref = verifier.exact_artifact(resume['checkpoint_source'], source_checkpoint, 'source checkpoint')
    checkpoint_input = verifier.exact_artifact(resume['checkpoint_input'], current_runtime / 'checkpoint-input.zssave', 'private checkpoint')
    require(source_ref.read_bytes() == checkpoint_input.read_bytes(), 'Source checkpoint and restore input differ')
    copied_result = verifier.exact_artifact(resume['run_result'], verifier.EVIDENCE / restore_id / 'resume-source-result.json', 'copied source result')
    require(copied_result.read_bytes() == (verifier.EVIDENCE / fresh_id / 'result.json').read_bytes(),
            'Frozen source result differs from the original fresh verdict')
    source_state, restored_state = source_files['play-final-state.txt'], current_files['play-initial-state.txt']
    expected_state = verifier.exact_artifact(resume['expected_state'], verifier.EVIDENCE / restore_id / 'checkpoint-state.txt', 'expected semantic state')
    verifier.exact_artifact(resume['checkpoint_source_state'], source_state, 'source final semantic state')
    require(source_state.read_bytes() == restored_state.read_bytes() == expected_state.read_bytes(),
            'Source final and restored initial SDK semantic states differ')
    require(runs[0]['final_turn'] == runs[1]['startup_turn'] == resume['turn'] == 6 and
            runs[0]['startup_turn'] == 0 and runs[1]['final_turn'] == 12,
            'Native pair did not traverse the expected 0→6→12 turns')
    markers = verifier.rows(current_out, 'INTERACTIVE_RESTORE_CHECKPOINT', r'^INTERACTIVE_RESTORE_CHECKPOINT=(.+)$')
    require(len(markers) == 1 and Path(markers[0]).resolve(strict=True) == checkpoint_input,
            'Native restore marker names a different checkpoint')
    reload_proof = verifier.verify_reload_archive_delta(source_checkpoint, current_files['play-restored-checkpoint.zssave'],
                                                       current_request['language'], current_out)
    report.update(status='PRESERVED_NATURAL_WORKER_UI_AND_CHECKPOINT_PAIR_PASS', runs=runs,
                  distinct_process_checkpoint_restore_verified=True, semantic_restore_equal=True,
                  source_checkpoint=artifact(source_checkpoint), private_checkpoint=artifact(checkpoint_input),
                  restored_initial_state=artifact(restored_state), native_archive_reload=reload_proof,
                  source_and_private_checkpoint_byte_equal=True,
                  source_and_restored_archive_byte_equal=False, full_rng_equivalence_verified=False)
except Exception as error:
    report['error'] = str(error)
    (attempt / 'failure.log').write_text(traceback.format_exc(), encoding='utf-8')
after = {str(path): sha(path) for path in protected}
report['protected_native_results_sources_and_original_frozen_verifiers_unchanged'] = before == after
report['protected_before'] = before
report['protected_after'] = after
report['validator_script'] = artifact(script_copy)
report['checked_utc'] = datetime.now(timezone.utc).isoformat()
if before != after:
    report['status'] = 'FAILED'
    report['preservation_error'] = 'A protected original source or native artifact changed during validation'
result_path = attempt / 'result.json'
result_path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
(output / 'postvalidation_latest.json').write_text(json.dumps(artifact(result_path), indent=2) + '\n', encoding='utf-8')
print(json.dumps({'status': report['status'], 'result': str(result_path), 'error': report.get('error'),
                  'protected_unchanged': before == after}), flush=True)
sys.exit(0 if report['status'].endswith('_PASS') else 1)
