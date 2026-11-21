"""Publish the verified private preparation without promoting or executing it."""
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[2]
INDEX = PROJECT / 'evidence/save_menu/20261013_original_screen/current_progress.json'
BACKUP = STAGE / 'current_progress.before_runtime_fonts.json.gz'
CONFORMANCE = STAGE / 'conformance.json'
RECEIPT = STAGE / 'progress_update.json'
TEMP = INDEX.with_name('current_progress.runtime_fonts.tmp')


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def artifact(path):
    path = Path(path)
    require(path.is_absolute() and path.is_relative_to(PROJECT) and path.resolve(strict=True) == path,
            'Noncanonical or external publication input')
    require(all(not p.lstat().st_file_attributes & 0x400 for p in (path, *path.parents)), 'Reparse publication input')
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return dict(path=str(path), bytes=path.stat().st_size, sha256=digest)


def verify(row):
    actual = artifact(row['path'])
    require(actual['sha256'] == row['sha256'] and ('bytes' not in row or actual['bytes'] == row['bytes']), 'Publication input changed')
    return actual


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_new(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2);stream.write('\n')
        stream.flush();os.fsync(stream.fileno())


def main():
    incident = read(STAGE / 'system_freeze_hold.json')
    require(type(incident) is dict and incident.get('engine_build_preparation_and_large_io_stopped') is False,
            'Original Windows freeze hold is active; heavy engine work is forbidden')
    require(not sys.flags.optimize and len(sys.argv) == 1, 'Unexpected publication invocation')
    require(all(not os.path.lexists(p) for p in (BACKUP, CONFORMANCE, RECEIPT, TEMP)), 'Publication is single-use')
    scope = read(STAGE / 'scope.json')
    verify(scope['progress_before'])
    require(Path(scope['progress_before']['path']) == INDEX, 'Wrong current index')
    original = INDEX.read_bytes()
    old = json.loads(original)
    require(old['full_goal_redefined'] is False and old['full_engine_goal_complete'] is False, 'Full goal changed')
    prepared = read(STAGE / 'prepared.json')
    identity = read(STAGE / 'preparation_identity_audit.json')
    tests = read(STAGE / 'frontend_tests_retry_03.json')
    before = read(STAGE / 'storage_resume_before.json')
    after = read(STAGE / 'storage_after.json')
    require(prepared['status'] == 'PREPARED_NOT_EXECUTED' and identity['status'] == 'PASS_PREPARED_NOT_EXECUTED' and
            identity['inputs_unchanged'] is True and identity['font_payloads_copied'] == 0 and
            not identity['forbidden_access_attempts'] and identity['actual_runner_main_calls'] == 1,
            'Actual runtime identity is incomplete')
    require(all(identity[k] is False for k in ('host_executed', 'gamecore_loaded', 'hwnd_created',
                'retail_user_state_or_game_processes_accessed', 'default_promoted', 'full_engine_goal_complete')),
            'Runtime execution or promotion occurred')
    require(tests['status'] == 'PASS_PYTHON_COMPONENTS_NO_NATIVE' and tests['inputs_unchanged'] is True and
            not tests['forbidden_access_attempts'] and tests['component_scratch_remaining'] is False and
            len(tests['results']) == 2 and all(row['returncode'] == 0 for row in tests['results']), 'Frontend tests did not pass')
    own, geometry = [json.loads(row['stdout']) for row in tests['results']]
    require(own['tests_run'] == 16 and len(own['frozen_carrier_contexts_before_compiler']) == 20 and
            geometry['checks'] == 199 and own['owned_inputs_unchanged'] is True, 'Unexpected component test coverage')
    for row in tests['inputs']:
        verify(row)
    for row in scope['source_inputs'].values():
        verify(row)
    request_ref = verify(prepared['request'])
    request = read(request_ref['path'])
    prior_prepared = old['current_prepared_runtime'].copy()
    require(prepared['run_id'] == request['run_id'] == identity['run_id'] and
            prepared['host_build_id'] == scope['host_build_id'] and
            len(request['runtime_inputs']) == 24 and not request['smoke'], 'Prepared IDs or runtime input count differ')
    for row in request['runtime_inputs']:
        verify(row)
    inventory = request['interactive_ui_support_inventory']
    require(len(inventory['tools']) == 6, 'Wrong frozen frontend count')
    for name, row in inventory['tools'].items():
        require(verify(row['frozen'])['sha256'] == scope['source_inputs']['tools/' + name]['sha256'], 'Frozen frontend is stale')
    for row in scope['font_inputs']:
        verify(row)
    require(len(identity['private_databases']) == 2 and prepared['hardlinks'] == 15, 'Private identity count differs')
    require(all(r['status'] == 'PASS_METADATA_ONLY' and not r['audit']['errors'] and not r['audit']['skipped']
                for r in (before, after)), 'Storage snapshot incomplete')
    runtime_root = PROJECT / 'Build/InteractiveGameRuntime' / request['run_id']
    require(not (runtime_root / 'sessions').exists(), 'Prepared runtime has been executed')
    refs = {name: artifact(STAGE / name) for name in ('scope.json', 'prepared.json', 'preparation_identity_audit.json',
            'frontend_tests_retry_03.json', 'font_drift_review.json', 'source_before.zip', 'storage_resume_before.json', 'storage_after.json')}
    stage = dict(status='PASS_CURRENT_X64_CANDIDATE_PRIVATE_PREPARED_NATIVE_PENDING', build_id=scope['host_build_id'],
        run_id=request['run_id'], scope=refs['scope.json'], prepared=refs['prepared.json'], request=request_ref,
        identity=refs['preparation_identity_audit.json'], frontend_tests=refs['frontend_tests_retry_03.json'],
        source_inputs=scope['source_inputs'], font_drift_review=refs['font_drift_review.json'],
        owned_font_inputs=15, owned_font_payloads_copied=0, support_tools=6, runtime_inputs=24,
        native_runtime_inputs_unchanged_from_previous=22, readonly_native_hardlinks=15, private_databases=2,
        font_binding_tests=16, scene_carrier_contexts=20, selected_geometry_checks=199,
        cpp_sources_changed_this_stage=False, cpp_rebuilt_this_stage=False,
        native_host_gamecore_hwnd_executed=False, retail_user_state_or_game_processes_accessed=False,
        retail_mod_test_hold_active=True, default_promoted=False, full_engine_goal_complete=False)
    storage = dict(before=refs['storage_resume_before.json'], after=refs['storage_after.json'],
        original_stage_before=artifact(STAGE / 'storage_before.json'),
        before_unique_GetCompressedFileSizeW_bytes=before['audit']['unique_allocated_bytes'],
        after_unique_GetCompressedFileSizeW_bytes=after['audit']['unique_allocated_bytes'],
        net_unique_growth_bytes=after['audit']['unique_allocated_bytes']-before['audit']['unique_allocated_bytes'],
        test_scratch_remaining=False, accounting='Deduplicated whole engine root; not volume free space or exact cluster allocation')
    cleanup = STAGE / 'retention_cleanup.json'
    if cleanup.exists():
        storage['retention_cleanup'] = artifact(cleanup)
    failed_preparation_cleanup = STAGE / 'preparation_attempt_01.json'
    if failed_preparation_cleanup.exists():
        storage['failed_preparation_cleanup'] = artifact(failed_preparation_cleanup)
    conformance = dict(schema='zerosis.goody_hut.font_runtime_conformance.v1', utc=datetime.now(timezone.utc).isoformat(),
        status=stage['status'], prior_goal_turn_classification=old.get('current_goal_turn_classification', 'no_progress'), current_goal_turn_classification='progress',
        full_goal=old['full_goal'], full_goal_redefined=False, full_engine_goal_complete=False, stage=stage,
        source_backup=refs['source_before.zip'], storage=storage,
        requirements=[
            'Use exactly the captured fifteen-file owned font input set from frozen preparation provenance.',
            'Preserve all selected glyph records and existing geometry assertions; never fall back to mutable installed fonts for the owned candidate.',
            'Keep general UI/styles/icons at their existing sources and preserve the existing six-tool transport.',
            'Prepare the real current x64 Host privately with exact runtime provenance, without Host/GameCore/HWND execution or retail-state access.',
            'Keep the original full-engine acceptance gates and published default unchanged.'],
        remaining=old['full_goal_outstanding'], limits=[
            'Python component tests and a prepared private runtime do not establish real window, campaign, original-save or mod compatibility.',
            'Four-worker policy selection is configuration proof; real multicore speedup and stability remain unmeasured.',
            'The original selected font maps include 2350 modern Hangul syllables; unrestricted Korean/mod character coverage is not proved.',
            'The storage snapshot precedes this small publication and excludes directory/MFT overhead.'])
    write_new(CONFORMANCE, conformance)
    stage['conformance'] = artifact(CONFORMANCE)
    old.update(utc=conformance['utc'], status=stage['status'], prior_goal_turn_classification=conformance['prior_goal_turn_classification'],
        current_goal_turn_classification='progress', current_host_build_id=scope['host_build_id'],
        latest_source_matches_linked_candidate=True, prepared_runtime_matches_current_linked_candidate=True,
        prepared_runtime_matches_latest_source=True, goody_hut_runtime_font_stage=stage)
    old['current_prepared_runtime'].update(run_id=request['run_id'], host_build_id=scope['host_build_id'],
        status='PREPARED_NOT_EXECUTED', request=request_ref, prepared=refs['prepared.json'],
        runtime_identity_audit=refs['preparation_identity_audit.json'], existing_cache_hits=prepared['cache_hits'],
        new_host_and_unit_cache_objects=prepared['new_cache_objects'], current_source_candidate=True,
        found_value_worker_policy=request['found_value_worker_policy'])
    old['goody_hut_link_stage'].update(renderer_owned_font_root_binding_complete=True,
        new_source_matching_runtime_prepared=True,
        next_required=[
            'After explicit human mod-test release, verify the actual x64 UI/3D, original Goody/Pantheon pixels, input, SDK effects and following turn.',
            'Complete full campaign, original save/mod compatibility and measured useful multicore/stability acceptance.'])
    old['proofs']['goody_hut_current_runtime_font_binding'] = artifact(CONFORMANCE)
    old['latest_storage_audit'] = refs['storage_after.json']
    old['storage']['latest_measured_unique_GetCompressedFileSizeW_bytes'] = after['audit']['unique_allocated_bytes']
    old['storage']['latest_measured_utc'] = after['completed_utc']
    old['storage']['goody_hut_runtime_font_stage'] = storage
    old['runtime_worker_policy_stage']['latest_current_prepared_runtime'].update(
        run_id=request['run_id'], host_build_id=scope['host_build_id'],
        identity=refs['preparation_identity_audit.json'],
        found_value_worker_policy=request['found_value_worker_policy'], native_consumption_verified=False)
    retention = old['superseded_retention_stage']
    additional_prior = dict(build_id=retention['immediate_prepared_rollback_build'],
        run_id=retention['immediate_prepared_rollback_runtime'],
        reason='Retained pending refreshed dependency and save-preservation review; not claimed as a verified native comparison.')
    retention.update(current_source_build=scope['host_build_id'], current_prepared_runtime=request['run_id'],
        immediate_prepared_rollback_build=prior_prepared['host_build_id'],
        immediate_prepared_rollback_runtime=prior_prepared['run_id'],
        prepared_role_update_evidence=refs['preparation_identity_audit.json'],
        additional_prior_prepared_pair=additional_prior)
    require(old['latest_native_acceptance']['final_acceptance_percent'] == 0 and
            old['latest_native_acceptance']['overall_development_percent'] is None, 'Unproved overall completion claim')
    with BACKUP.open('xb') as stream:
        stream.write(gzip.compress(original, mtime=0))
    require(gzip.decompress(BACKUP.read_bytes()) == original, 'Index backup is not exact')
    write_new(TEMP, old)
    require(INDEX.read_bytes() == original, 'Concurrent index publication')
    os.replace(TEMP, INDEX)
    write_new(RECEIPT, dict(schema='zerosis.goody_hut.font_runtime_progress_update.v1', status='PUBLISHED_PRIVATE_PREPARATION_NATIVE_PENDING',
        before=scope['progress_before'], exact_before_gzip=artifact(BACKUP), after=artifact(INDEX),
        conformance=artifact(CONFORMANCE), full_goal_redefined=False, default_promoted=False,
        final_native_acceptance_percent=0, overall_development_percent=None))
    print(json.dumps(dict(status='PUBLISHED_PRIVATE_PREPARATION_NATIVE_PENDING', build_id=scope['host_build_id'],
                         run_id=request['run_id'], conformance=artifact(CONFORMANCE), index=artifact(INDEX), storage=storage)))


if __name__ == '__main__':
    main()
