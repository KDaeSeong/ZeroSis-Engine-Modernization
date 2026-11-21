"""Publish bounded prepared-pair and actual-launch facts, without native work."""
from pathlib import Path
import datetime
import gzip
import hashlib
import json
import stat

PROJECT = Path(__file__).absolute().parents[4]
STAGE = Path(__file__).absolute().parents[1]
OUTPUT = Path(__file__).absolute().parent
NEW = '20261024T070230Z_cbbd79f1cbb6'
OLD = '20261024T050152Z_fd0465b26387'
BUILD = '20261024T055841Z_974a5be57533'
PROGRESS = PROJECT / 'evidence/save_menu/20261013_original_screen/current_progress.json'
DOCUMENT = PROJECT / 'docs/ORIGINAL_WORLD_HUD.md'


def ordinary(path):
    path = Path(path).absolute()
    assert path.is_relative_to(PROJECT) and path.resolve(strict=True) == path
    for item in (path, *path.parents):
        assert not item.lstat().st_file_attributes & 0x400, item
        if item == PROJECT:
            break
    assert stat.S_ISREG(path.lstat().st_mode)
    return path


def artifact(path):
    path = ordinary(path)
    before = path.stat()
    body = path.read_bytes()
    after = path.stat()
    assert (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) == (
        after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    return dict(path=str(path), bytes=len(body), sha256=hashlib.sha256(body).hexdigest())


def read(path):
    return json.loads(ordinary(path).read_text(encoding='utf-8-sig'))


def create(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def main():
    assert not (OUTPUT / 'result.json').exists()
    before_progress = artifact(PROGRESS)
    before_document = artifact(DOCUMENT)
    assert before_progress['sha256'] == 'a1017b7c16079a0455c9582c9a92e0d681ad8759c1a49d48a64a4d70a83cceef'
    assert before_document['sha256'] == '423768aad77ab2e786bd1a7979b195066294f131b222727c79c68a355705dc89'
    prepared_path = STAGE / 'materialization/result.json'
    assert artifact(prepared_path)['sha256'] == 'c8eeb0626f305ed8d60e714cfc0abfb5bc814628a686610e70171e66590cee41'
    prepared = read(prepared_path)
    assert prepared['run_id'] == NEW and prepared['host_build_id'] == BUILD
    assert prepared['runtime_input_count'] == 24 and prepared['immutable_links'] == 15
    assert prepared['current_original_world_hud_included'] is True
    assert artifact(prepared['host']['path']) == prepared['host']
    assert artifact(prepared['gamecore']['path']) == prepared['gamecore']
    request = read(prepared['request']['path'])
    assert artifact(prepared['request']['path']) == prepared['request']
    assert not request['smoke'] and request['resume_from'] is None
    process = read(STAGE / 'execution/backend_process.json')
    assert process['returncode'] == 0 and process['error'] is None
    assert process['wrapper_timeout'] is False and process['wrapper_completed'] is True
    driver_path = Path(process['driver_report_path'])
    driver = read(driver_path)
    assert driver['status'] == 'INTERACTIVE_UI_DRIVER_PASS'
    assert driver['returncode'] == 0 and driver['error'] is None
    assert driver['stop_action'] is None
    terminal = artifact(STAGE / 'execution/terminal_audit.json')
    defer = read(STAGE / 'execution/screen_verification_deferred.json')
    assert defer['answer'] == '지금은 화면 확인을 미룸'
    assert defer['screen_verification_deferred'] is True
    assert defer['new_host_sdk_or_ui_trial_relaunch_for_screen_check_allowed'] is False
    protected = [artifact(PROJECT / name) for name in (
        'Play/EarlyAccess/release.json', 'tools/Start-Engine.ps1',
        'docs/M7_RETAIL_SAVE_BOUNDARY.md',
        'evidence/goody_hut/runtime_fonts/system_freeze_hold.json')]
    for ref in prepared['host'], prepared['gamecore'], prepared['bundle_manifest']:
        assert artifact(ref['path']) == ref
    backups = []
    for path, ref in ((PROGRESS, before_progress), (DOCUMENT, before_document)):
        body = path.read_bytes()
        backup = OUTPUT / (path.name + '.before.gz')
        packed = gzip.compress(body, mtime=0)
        assert gzip.decompress(packed) == body
        with backup.open('xb') as stream:
            stream.write(packed)
        backups.append(dict(before=ref, backup=artifact(backup), gzip_roundtrip_verified=True))

    document = DOCUMENT.read_text(encoding='utf-8')
    old = (
        'The private run `20261024T050152Z_fd0465b26387` still contains the older Host;\n'
        'it has not been rematerialized or executed with this change. Actual native\n'
        'wheel routing and GPU viewport behavior still need runtime verification.\n')
    assert document.count(old) == 1
    document = document.replace(old, (
        'The private run `20261024T070230Z_cbbd79f1cbb6` now contains this Host and\n'
        'the selected `430f3122` SDK. It was executed once after direct human approval.\n'
        'The actual hardware terrain output used 1920x1080 with map width 1920;\n'
        'the initial visible window showed the original unit panel without the\n'
        'diagnostic right panel. This is partial presentation evidence, not full\n'
        'original UI/3D equivalence or camera-wheel acceptance.\n'))
    old = 'The second physical Escape hold remains in force for Host/SDK/window execution.\n'
    assert document.count(old) == 1
    document = document.replace(old, (
        'The old stop records are preserved. Direct human approval resumed only this\n'
        'trial. The user subsequently deferred screen verification; no further\n'
        'Host/SDK/window trial is authorized by automatic continuation.\n\n'
        'The driver exited normally with return code 0, no error and SDK unload.\n'
        'An initial autosave and final native checkpoint were written at turn 0.\n'
        'The initial and final states both contain no cities and two units.\n'
        'Recorded unit-panel events are pointer movement, not a successful click.\n'
        'No world-wheel or next-human-turn event was observed. Later screen captures\n'
        'returned another window even after one target reselection, so app input\n'
        'stopped. City founding, turn advancement, wheel routing and save loading\n'
        'remain unverified. The empty top information stack at city count 0 is the\n'
        'original TopPanel Lua branch and does not require a production change.\n'
        'The trial wrapper did not explicitly set ZEROSIS_UI_POLICY_INFO; its\n'
        'inherited value was not measured. A future authorized trial should set the\n'
        'prepared value 1 before opening the Social Policy context.\n'
        'Exact inputs, process results and native save hashes are recorded under\n'
        '`evidence/original_world_hud/pair_preparation/execution/`.\n'))
    DOCUMENT.write_text(document, encoding='utf-8', newline='\n')
    documentation = artifact(DOCUMENT)
    progress = read(PROGRESS)
    assert progress['current_host_build_id'] == BUILD
    assert progress['native_restore_pair_preparation_stage']['run_id'] == OLD
    assert progress['latest_current_source_compile_link_proof']['sha256'] == (
        '6aa2ccdb8ce1308521fc01f88fa45745153244b6931754a0b3111dc2129d1302')
    assert progress['latest_current_source_pe_attestation']['sha256'] == (
        '476953a732f62125b3165152159c6d8230857e50b8be58e8e23da26e6ef5fca3')
    proofs = dict(preparation=artifact(prepared_path), request=prepared['request'],
        host_input_gate=artifact(STAGE / 'actual_host_input_gate.json'),
        selected_sdk_gate=artifact(STAGE / 'actual_sdk_input_gate.json'),
        operational_revisions=artifact(STAGE / 'operational_revisions.json'),
        prelaunch_input_audit=artifact(STAGE / 'execution/prelaunch_input_audit.json'),
        direct_human_authorization=artifact(STAGE / 'execution/direct_user_authorization.json'),
        launch=artifact(STAGE / 'execution/launch.json'),
        driver_result=artifact(driver_path), terminal_audit=terminal,
        backend_process=artifact(STAGE / 'execution/backend_process.json'),
        screen_deferred=artifact(STAGE / 'execution/screen_verification_deferred.json'))
    current = dict(status='EXECUTED_NORMAL_CLOSE_INTERACTION_PENDING_SCREEN_DEFERRED',
        run_id=NEW, host_build_id=BUILD, host=prepared['host'], gamecore=prepared['gamecore'],
        bundle_manifest=prepared['bundle_manifest'], proofs=proofs,
        runtime_input_count=24, immutable_hardlinks=15, private_databases=2,
        current_python_support_count=6, new_game_only=True,
        save_loading_launcher_disabled=True, current_source_candidate=True,
        current_host_source_closure_matches_candidate=True,
        selected_sdk_includes_current_great_work_guard=True,
        current_candidate_prepared=True, host_executed=True, gamecore_loaded=True,
        window_created=True, actual_hardware_map_width=1920,
        diagnostic_right_panel_visibly_absent=True,
        city_founding_verified=False, turn_advancement_verified=False,
        actual_windows_wheel_routing_verified=False,
        save_compatibility_verified=False, original_ui_accepted=False,
        prior_bundle_save_migration_performed=False, default_promoted=False,
        physical_multicore_verified=False, performance_improvement_verified=False,
        full_original_ui_3d_campaign_verified=False, full_engine_goal_complete=False)
    if 'prior_current_prepared_runtime_metadata' not in progress:
        progress['prior_current_prepared_runtime_metadata'] = dict(
            historical_only=True, payload=progress['current_prepared_runtime'])
    progress['current_prepared_runtime'] = current
    progress['original_world_hud_pair_preparation_stage'] = current
    progress['status'] = 'CURRENT_WORLD_HUD_PAIR_EXECUTED_INTERACTION_PENDING_SCREEN_DEFERRED'
    progress['prepared_runtime_matches_current_linked_candidate'] = True
    progress['prepared_runtime_matches_latest_source'] = True
    progress['latest_private_prepared_pair_matches_current_host_and_selected_sdk_sources'] = True
    progress['latest_full_source_embedding_limit'] = (
        'Five complete current x64 Host units compiled and linked using 549 exact '
        'dependencies and eight fixed library inputs; all 67 catalog payloads '
        'matched the PE. The new Host and selected SDK executed once in an isolated '
        'new-game trial with a 1920-wide hardware map and normal checkpoint/shutdown. '
        'City founding, turn advancement, wheel input, save restore, full original '
        'UI/3D/campaign acceptance and useful multicore performance remain unverified.')
    progress['latest_actual_host_syntax_proof_scope'] = (
        'Five current Host units compiled and linked; actual isolated window and '
        'hardware map were observed, while gameplay input acceptance remains pending.')
    progress['current_goal_turn_classification'] = 'progress'
    progress['full_engine_goal_complete'] = False
    prior = progress['native_restore_pair_preparation_stage']
    prior.update(status='SUPERSEDED_PREPARED_PAIR_BUILD_PAYLOAD_RETIREMENT_PLANNED',
        current=False, payload_retirement_planned=True, superseded_by_run_id=NEW)
    world = progress['original_world_hud_stage']
    world.update(status='PASS_LINK_PREPARATION_AND_LAUNCH_INTERACTION_PENDING_SCREEN_DEFERRED',
        latest_prepared_pair_contains_changes=True, host_or_sdk_or_window_executed=True,
        actual_gpu_terrain_viewport_verified=True,
        actual_windows_wheel_routing_verified=False,
        current_run_id=NEW, actual_execution=terminal,
        screen_verification_deferred=True,
        full_original_ui_3d_campaign_verified=False, full_engine_goal_complete=False)
    world['proofs']['documentation'] = documentation
    progress['screen_verification_deferred'] = proofs['screen_deferred']
    progress['current_native_or_screen_relaunch_allowed'] = False
    PROGRESS.write_text(json.dumps(progress, ensure_ascii=False, indent=2) + '\n',
                        encoding='utf-8', newline='\n')
    for ref in protected:
        assert artifact(ref['path']) == ref
    for row in backups:
        row['after'] = artifact(row['before']['path'])
    result = dict(schema='zerosis.original_world_hud.pair_publication.v1',
        status='PASS_CURRENT_PAIR_AND_PARTIAL_NATIVE_FACTS_PUBLISHED',
        utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        run_id=NEW, changed_metadata=backups, protected_unchanged=protected,
        current_progress=artifact(PROGRESS), documentation=documentation,
        terminal_audit=terminal, no_native_or_screen_execution_by_publication=True,
        no_compiled_or_operational_source_changes=True, full_engine_goal_complete=False)
    create(OUTPUT / 'result.json', result)
    print(json.dumps(dict(status=result['status'], run_id=NEW,
        current_progress=result['current_progress'], documentation=documentation), ensure_ascii=False))


if __name__ == '__main__':
    main()
