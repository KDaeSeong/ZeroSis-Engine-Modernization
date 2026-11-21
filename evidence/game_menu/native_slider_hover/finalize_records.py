"""Close the native slider hover wave with file-only records; native acceptance stays deferred.

usage: python -B -X utf8 finalize_records.py protect|docs-backup|publish
"""
from __future__ import annotations
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
sys.path.insert(0, str(PROJECT / 'tools'))
from menu_suite_storage import storage

BUILD = '20261108T002841Z_2b25aaa753e3'
RUN = '20261108T003146Z_40a8030edf08'
PREVIOUS_BUILD, PREVIOUS_RUN = '20261107T120745Z_986e193d1ed1', '20261107T121011Z_527ea94501fb'
OLD_BUILD, OLD_RUN = '20261105T133256Z_8837e4ca5f08', '20261105T133817Z_1fba743abc09'
DOCS = ['docs/CLAUDE_HANDOFF.md', 'docs/ORIGINAL_MENUS_OFFLINE.md', 'docs/ORIGINAL_WORLD_HUD.md',
        'evidence/save_menu/20261013_original_screen/current_progress.json']
PROOFS = dict(
    retail_slider_gate_probe=('evidence/game_menu/native_slider_hover/retail_slider_gate_probe.json', None),
    retail_slider_key_probe=('evidence/game_menu/native_offline_followup/retail_slider_key_probe.json', None),
    options_integration_hover=('evidence/game_menu/options_reward_popups/integration/e383cd7ce49a6b7e/result.json',
                               'PASS_SOURCE_REWARD_OPTIONS_V3_MIGRATION_AND_VIDEO_CONFIRMATION'),
    reward_options_view_9a1a=('evidence/game_menu/options_reward_popups/view/attempt04/result.json',
                              'PASS_ORIGINAL_REWARD_CALLBACK_STACK_AND_ACTUAL_V3_MODEL_VIEW_CXX14'),
    resolution_preview_view=('evidence/game_menu/options_video_preview/view/88621a701ee83444/result.json',
                             'PASS_ACTUAL_OPTIONS_MODEL_ORIGINAL_RESOLUTION_PREVIEW_VIEW'),
    plan_review=('evidence/game_menu/native_slider_hover/host_build/plan_review.json', 'PASS_FILE_ONLY_PLAN_REVIEW'),
    old_pair_retirement=('evidence/game_menu/native_slider_hover/retirement_result.json', 'PASS_OLDER_PAIR_RETIRED_EXACT_ENTRIES'))


def read(path):
    return json.loads(Path(path).read_text('utf8'))


def ref(path):
    path = Path(path).absolute()
    raw = path.read_bytes()
    return dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def write_new(path, value):
    with Path(path).open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write('\n')


def protect():
    """Re-verify every artifact the build plan protected, after build, tidy, sidecar and preparation."""
    plan = read(STAGE / 'host_build/plan.json')
    differences, aliases, ids = [], [], {}
    for row in plan['protected_artifacts']:
        now = storage.metadata(storage.ordinary(row['path']))
        identity = tuple(now['file_identity'])
        if identity not in ids:
            ids[identity] = storage.digest(row['path'])
        if any(now[k] != row[k] for k in ('bytes', 'file_identity', 'mtime_ns', 'file_attributes')) or ids[identity] != row['sha256']:
            differences.append(row['path'])
        if now['links'] != row['links']:
            aliases.append(dict(path=row['path'], before=row['links'], after=now['links']))
    value = dict(schema='zerosis.native_slider_hover.protection.v1', status='PASS' if not differences else 'FAIL',
                 plan=ref(STAGE / 'host_build/plan.json'), protected_paths=len(plan['protected_artifacts']),
                 unique_file_ids=len(ids), differences=differences, alias_changes=aliases,
                 alias_policy='Hardlink counts may rise when the new runtime aliases the immutable cache; content and identity must not change.',
                 native_execution=False)
    write_new(STAGE / 'protection_after.json', value)
    print(json.dumps(dict(status=value['status'], paths=value['protected_paths'], differences=len(differences), alias_changes=len(aliases))))
    return 0 if not differences else 1


def docs_backup():
    rows = []
    for name in DOCS:
        path = PROJECT / name
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        target = STAGE / 'source_before' / (name.replace('/', '__') + '.' + digest[:16] + '.gz')
        if not target.exists():
            with target.open('xb') as stream:
                stream.write(gzip.compress(raw, mtime=0))
        assert hashlib.sha256(gzip.decompress(target.read_bytes())).hexdigest() == digest
        rows.append(dict(path=name, bytes=len(raw), sha256=digest, backup=str(target.relative_to(PROJECT)).replace('\\', '/')))
    write_new(STAGE / 'docs_before.json', dict(utc=datetime.now(timezone.utc).isoformat(), changed_file_backups=rows,
                                               full_project_copy=False))
    print(json.dumps(dict(status='DOCS_KEPT', backups=len(rows))))
    return 0


IMPLEMENTED = [
    'Options volume arrow keys follow the retail Slider gate: retail state bit 0x10000 is the pointer-over state (set after '
    'Mouse.eMouseEnter=5, cleared after Mouse.eMouseExit=6), so keys move the slider only while the pointer is over it. '
    'Key events now carry the lifecycle hovered control; keyboard focus no longer selects the slider.',
    'The older 8837/1fba Host/runtime pair is retired by the user decision: the reward view test reads the shared 9a1a '
    'runtime, the builder drops 1fba from its protected roots and inherited rows, and 1121 exact entries and 107 directories '
    'were removed without clearing any readonly attribute.']
REMAINING = [
    'Actual Host/GameCore/window/GPU/gameplay/save/mod/multicore acceptance remains deferred and incomplete.',
    'Slider hover, WindowTrim and Locale behavior is retail-static and controlled-component verified only; no native screen was executed.',
    'The UI manager path that delivers WM_KEYUP to controls is not traced; retail pointer-over is proven necessary, not sufficient.',
    'Retail sliders move on WM_KEYUP; this window moves on the first WM_KEYDOWN of a press (auto-repeat filtered). A key-up '
    'queue would change the shared BitmapWindow and needs an HWND to verify.',
    'A hover is known only after a pointer move on the options page; a pointer resting on the slider when the page opens '
    'does not count until it moves.',
    'WindowTrim bottom 2 rows: the retail sampler address mode and FTXT tile-shader result for v>1 are unproven; V4 does not draw them.',
    'The volume model keeps integer percent; retail float32 accumulation is not modelled. Retail Locale.ToPercent formats the '
    'stored float with the ICU percent style; the engine label shows the integer percent.',
    'Localize still rejects nonfinite numbers and keeps Host key lookup and NUL rejection for string arguments.',
    'Seven supported front-end preference categories are connected, including conditional policy info; full original options and remaining menu branches need real backends.',
    'Actual display readback/confirmation timing/focus/close rollback and native UI geometry/filter/font equivalence are unexecuted.',
    'ReplayMap remains simplified; original3D map, retail replay wrapper/catalog and full original Lua execution are incomplete.']


def publish():
    verified = read(STAGE / 'prepared_runtime_verification.json')
    assert verified['status'] == 'PASS_SINGLE_CURRENT_PREPARED_RUNTIME_AND_FULL_SOURCE_CLOSURE_NOT_EXECUTED'
    assert (verified['build_id'], verified['run_id']) == (BUILD, RUN) and verified['sidecar_matches_v4_manifest'] is True
    protection = read(STAGE / 'protection_after.json')
    assert protection['status'] == 'PASS'
    retirement = read(STAGE / 'retirement_result.json')
    assert retirement['roots_absent'] is True and retirement['readonly_attributes_changed'] is False
    before, after = read(STAGE / 'storage_before.json'), read(STAGE / 'storage_after.json')
    assert not after['errors'] and not after.get('reparse_skipped')
    pair = STAGE / 'pair_preparation' / BUILD
    build = read(verified['build_result']['path'])
    att = read(pair / 'independent_attestation.json')
    counts = dict(compiler_dependency_count=att['compiler_input_count'], current_source_input_count=att['current_input_count'],
                  frozen_input_count=att['frozen_input_count'], source_manifest_count=att['source_manifest_count'])
    assert counts['current_source_input_count'] == verified['current_source_inputs_verified']
    changed = sorted(str(Path(row['path']).relative_to(PROJECT)) for row in build['sources_changed_from_baseline']
                     if Path(row['path']).is_relative_to(PROJECT))
    added = sorted(str(Path(row['path']).relative_to(PROJECT)) for row in build['new_source_inputs']
                   if isinstance(row, dict) and Path(row['path']).is_relative_to(PROJECT))
    for name in ('MenuFrontEndOptionsModel.h', 'MenuLifecycleWindow.h'):
        assert any(item.casefold() == ('source\\host\\' + name).casefold() for item in changed), name
    assert not any(item.casefold().startswith('source\\') for item in added), added
    proofs = {name: ref(PROJECT / path) for name, (path, _) in PROOFS.items()}
    statuses = {name: read(PROJECT / path).get('status') for name, (path, status) in PROOFS.items() if status}
    expected = {name: status for name, (_, status) in PROOFS.items() if status}
    assert statuses == expected, statuses
    options = read(PROJECT / PROOFS['options_integration_hover'][0])
    assert options['retail_slider_rules']['retail_gate'].startswith('control state bit 0x10000 = pointer-over')
    assert options['source_binding_checks']['volume_keys_receive_pointer_over'] is True and options['protected_inputs_unchanged'] is True
    host = dict(status='CURRENT_COMPILED_EXPLICIT_PREPARED_PROFILE_NOT_REGISTERED_OR_EXECUTED', build_id=BUILD,
                parent_build_id=PREVIOUS_BUILD, executable=build['executable'], build_result=verified['build_result'],
                independent_attestation=ref(pair / 'independent_attestation.json'), prepared_profile=verified['profile'],
                **counts, catalog_entries=74, required_sidecar_files=154, sidecar_asset_pack='Source/Assets/UIFrontEndV4',
                sources_changed_from_parent=changed, sources_added_from_parent=added,
                registered=False, globally_registered=False, prepared_profile_only=True, host_executed=False,
                gamecore_loaded=False, screen_verification_deferred=True, full_engine_goal_complete=False)
    runtime = Path(verified['runtime_directory'])
    prepared = dict(status='CURRENT_EXPLICIT_NATIVE_SLIDER_HOVER_HOST_V4_SIDECAR_AND_UNCHANGED_SDK_PREPARED_NOT_EXECUTED',
                    run_id=RUN, host_build_id=BUILD, runtime_directory=str(runtime), host=verified['host'],
                    gamecore=verified['gamecore'], bundle_manifest=ref(runtime / 'bundle.manifest'), request=verified['request'],
                    materialization=verified['materialization'], backend_inputs=24, sidecar_files=154, physical_file_paths=189,
                    frozen_python_modules=6, native_attempts=0, new_game_only=True, cross_bundle_load_allowed=False,
                    default_promoted=False)
    space = dict(before=ref(STAGE / 'storage_before.json'), after=ref(STAGE / 'storage_after.json'),
                 before_unique_allocated_bytes=before['unique_allocated_bytes'],
                 after_unique_allocated_bytes=after['unique_allocated_bytes'],
                 allocated_bytes_change=after['unique_allocated_bytes'] - before['unique_allocated_bytes'],
                 confirmed_disposable_bytes=0, threshold_bytes=10 * 1024 ** 3, full_project_copies_created=0,
                 intermediate_cleanup=ref(pair / 'cleanup_result.json'),
                 measurement='FileStandardInfo.AllocationSize once per real os.stat identity; directories excluded.',
                 retained_previous_pair=[PREVIOUS_BUILD, PREVIOUS_RUN], retirement=ref(STAGE / 'retirement_result.json'),
                 retired_pair=[OLD_BUILD, OLD_RUN], retired_files=retirement['files_removed'],
                 retired_directories=retirement['directories_removed'],
                 retired_single_link_allocated_bytes=retirement['released_allocated_bytes'],
                 retirement_note='Retired by the user decision of 2026-11-07; shared hardlinks kept their bytes and readonly flags.')
    supersedes = dict(
        native_offline_followup=ref(PROJECT / 'evidence/game_menu/native_offline_followup/current_work.json'),
        note='Its "gate bit 0x10000 is not proved" and "older 8837/1fba pair is retained" items are resolved here.')
    current = dict(schema='zerosis.native_slider_hover.current_work.v1', utc=datetime.now(timezone.utc).isoformat(),
                   status='PASS_CURRENT_X64_NATIVE_SLIDER_HOVER_PAIR_PREPARED_OFFLINE', goal_turn_classification='progress',
                   full_goal_redefined=False, full_engine_goal_complete=False, implemented=IMPLEMENTED,
                   slider_rules=options['retail_slider_rules'],
                   current_host=host, current_prepared_runtime=prepared,
                   working_source_matches_current_frozen_and_prepared_profile=True, proofs=proofs,
                   source_manifest=verified['source_manifest'], protection=ref(STAGE / 'protection_after.json'),
                   storage=space, supersedes=supersedes, remaining=REMAINING, native_execution=False,
                   current_native_or_screen_relaunch_allowed=False, screen_verification_deferred=True,
                   default_or_registration_changed=False)
    write_new(STAGE / 'current_work.json', current)
    compile_proof = dict(status='PASS_FIVE_ACTUAL_CXX14_TRANSLATION_UNITS_COMPILED_AND_LINKED_OFFLINE', build_id=BUILD,
                         build_result=verified['build_result'], prepared_pair_verification=ref(STAGE / 'prepared_runtime_verification.json'),
                         **counts, catalog_entries=74, required_sidecar_files=154, host_executed=False, SDK_executed=False,
                         native_acceptance=False)
    path = PROJECT / 'evidence/save_menu/20261013_original_screen/current_progress.json'
    progress = read(path)
    scope = (f"Current {BUILD}: {counts['current_source_input_count']} current and {counts['frozen_input_count']} frozen inputs, "
             f"{counts['compiler_dependency_count']} compiler dependencies, 74 payloads, 154 V4 sidecars and 189 runtime files verified. "
             'No Host/SDK execution or default/global registration change.')
    progress.update(utc=current['utc'], status=current['status'], full_engine_goal_complete=False, current_goal_turn_classification='progress',
                    current_host_build_id=BUILD, current_host_build=host, current_prepared_runtime=prepared,
                    latest_host_sdk_preparation_stage=prepared,
                    latest_private_prepared_pair_matches_current_host_and_selected_sdk_sources=True,
                    prepared_runtime_matches_current_linked_candidate=True, prepared_runtime_matches_latest_source=True,
                    latest_source_matches_integrated_syntax_proof=True, latest_source_matches_linked_candidate=True,
                    latest_cpp_source_matches_actual_host_syntax_proof=True, latest_current_source_actual_cpp_compilation_verified=True,
                    latest_host_source_matches_current_link_proof=True, latest_integrated_syntax_proof=compile_proof,
                    latest_current_source_compile_link_proof=compile_proof, latest_actual_host_syntax_proof=compile_proof,
                    latest_current_source_actual_cpp_compilation_verified_proof=compile_proof,
                    latest_current_source_pe_attestation=ref(pair / 'independent_attestation.json'),
                    latest_host_source_matches_current_link_proof_scope=scope, latest_source_matches_linked_candidate_scope=scope,
                    latest_actual_host_syntax_proof_scope='Five actual C++14 units compiled and linked offline, fp:strict, zero warnings. Host/SDK unexecuted.',
                    current_source_working_stage=str(STAGE), limits=REMAINING, screen_verification_deferred=True,
                    current_native_or_screen_relaunch_allowed=False, host_executed=False, gamecore_loaded=False,
                    hwnd_created=False, gpu_executed=False, default_promoted=False, native_acceptance_complete=False)
    progress['native_slider_hover_stage'] = dict(current, record=ref(STAGE / 'current_work.json'))
    progress.setdefault('storage', {})['latest_native_slider_hover_wave'] = space
    progress['storage']['older_fields_are_prior_wave_history'] = True
    path.write_text(json.dumps(progress, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps(dict(status=current['status'], build=BUILD, runtime=RUN, counts=counts,
                          allocated_change=space['allocated_bytes_change'], changed_sources=len(changed), added=added)))
    return 0


if __name__ == '__main__':
    commands = {'protect': protect, 'docs-backup': docs_backup, 'publish': publish}
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        raise SystemExit(__doc__)
    raise SystemExit(commands[sys.argv[1]]())
