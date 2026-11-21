"""Close the native offline follow-up wave with file-only records; native acceptance stays deferred.

usage: python -B -X utf8 finalize_records.py protect|prune-evaluation|docs-backup|publish
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

BUILD = '20261107T120745Z_986e193d1ed1'
RUN = '20261107T121011Z_527ea94501fb'
PREVIOUS_BUILD, PREVIOUS_RUN = '20261106T225828Z_b281e2cf6094', '20261106T230144Z_48d9fd363237'
OLD_BUILD, OLD_RUN = '20261105T133256Z_8837e4ca5f08', '20261105T133817Z_1fba743abc09'
DOCS = ['docs/CLAUDE_HANDOFF.md', 'docs/ORIGINAL_MENUS_OFFLINE.md', 'docs/ORIGINAL_WORLD_HUD.md',
        'evidence/save_menu/20261013_original_screen/current_progress.json']
PROOFS = dict(
    windowtrim_retail_image_probe=('evidence/game_menu/frontend_windowtrim/retail_image_probe.json', None),
    retail_slider_key_probe=('evidence/game_menu/native_offline_followup/retail_slider_key_probe.json', None),
    frontend_v4_render_check=('evidence/game_menu/native_offline_followup/frontend_v4_render_check.json',
                              'PASS_V4_DIFFERS_ONLY_INSIDE_WINDOWTRIM'),
    grid_layout_v4=('evidence/game_menu/replay_hover_frame/frame/attempt_64460fdd4697022ac2b8/result.json',
                    'PASS_ORIGINAL_PER_CAP_GRID_AND_ACTUAL_V3_SCENE'),
    options_integration_v4=('evidence/game_menu/options_reward_popups/integration/29585522bfa3d9c7/result.json',
                            'PASS_SOURCE_REWARD_OPTIONS_V3_MIGRATION_AND_VIDEO_CONFIRMATION'),
    restored_replay_scene_v4=('evidence/game_menu/replay_hover_frame/integration/scene/abab4e2f5907777f/result.json',
                              'PASS_SDK_FREE_REPLAY_ORIGINAL_LAYOUT_RICHTEXT_SCENE_INPUT_AND_BOUNDS'),
    reward_options_view_v4=('evidence/game_menu/options_reward_popups/view/attempt03/result.json',
                            'PASS_ORIGINAL_REWARD_CALLBACK_STACK_AND_ACTUAL_V3_MODEL_VIEW_CXX14'),
    resolution_preview_view_v4=('evidence/game_menu/options_video_preview/view/7215a2f111ed6af6/result.json',
                                'PASS_ACTUAL_OPTIONS_MODEL_ORIGINAL_RESOLUTION_PREVIEW_VIEW'),
    locale_arguments=('evidence/game_menu/native_offline_followup/locale_arguments/f97c66d003e8d605/result.json',
                      'PASS_RETAIL_LOCALE_ARGUMENT_DISPATCH_LUA51'),
    plan_review=('evidence/game_menu/native_offline_followup/host_build/plan_review.json', 'PASS_FILE_ONLY_PLAN_REVIEW'))


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
    value = dict(schema='zerosis.native_offline_followup.protection.v1', status='PASS' if not differences else 'FAIL',
                 plan=ref(STAGE / 'host_build/plan.json'), protected_paths=len(plan['protected_artifacts']),
                 unique_file_ids=len(ids), differences=differences, alias_changes=aliases,
                 alias_policy='Hardlink counts may rise when the new runtime aliases the immutable cache; content and identity must not change.',
                 native_execution=False)
    write_new(STAGE / 'protection_after.json', value)
    print(json.dumps(dict(status=value['status'], paths=value['protected_paths'], differences=len(differences), alias_changes=len(aliases))))
    return 0 if not differences else 1


def prune_evaluation():
    """Read-only evaluation of the older 8837/1fba pair; nothing is deleted."""
    roots = dict(host=PROJECT / 'Build/UiWindowHost' / OLD_BUILD, runtime=PROJECT / 'Build/InteractiveGameRuntime' / OLD_RUN)
    survey = {}
    for name, root in roots.items():
        files = single = allocated = single_allocated = 0
        saves = []
        for directory, names, leaves in os.walk(root, followlinks=False):
            for item in names:
                assert not os.stat(Path(directory) / item, follow_symlinks=False).st_file_attributes & 0x400
            for leaf in leaves:
                path = Path(directory) / leaf
                info = storage.ordinary(path)
                size = storage.allocated(path)
                files += 1
                allocated += size
                if info.st_nlink == 1:
                    single += 1
                    single_allocated += size
                if path.suffix.casefold() in ('.civ5save', '.sav') or path.relative_to(root).parts[0].casefold() in ('sessions', 'settings'):
                    saves.append(str(path.relative_to(root)))
        survey[name] = dict(root=str(root), files=files, single_link_files=single, allocated_bytes=allocated,
                            single_link_allocated_bytes=single_allocated, saves_sessions_or_settings=saves)
    builder = (PROJECT / 'tools/build_menu_suite_host.py').read_text('utf8')
    reward_view = (PROJECT / 'Tests/menu_reward_options_view.py').read_text('utf8')
    plan = read(STAGE / 'host_build/plan.json')
    protected_by_plan = sum(1 for row in plan['protected_artifacts'] if OLD_RUN in row['path'])
    built = read(PROJECT / 'evidence/ui_window_host' / BUILD / 'build_result.json')
    sealed_sources = {Path(row['path']).relative_to(PROJECT).as_posix().casefold() for row in built['current_source_inputs']
                      if Path(row['path']).is_relative_to(PROJECT)}
    blockers = []
    if OLD_RUN in builder:
        blockers.append('tools/build_menu_suite_host.py PROTECTED_ROOTS lists the 1fba runtime; the next plan requires it to exist.')
    if OLD_RUN in reward_view:
        blockers.append('Tests/menu_reward_options_view.py reads the 1fba localization.db as its RUNTIME input.')
    if protected_by_plan:
        blockers.append(f'This wave\'s sealed plan protects {protected_by_plan} 1fba files; deleting them now would falsify protection_after.json.')
    editing_needed = [name for name in ('tools/build_menu_suite_host.py', 'Tests/menu_reward_options_view.py') if name.casefold() in sealed_sources]
    value = dict(schema='zerosis.native_offline_followup.prune_evaluation.v1', utc=datetime.now(timezone.utc).isoformat(),
                 status='DEFERRED_PROTECTION_AND_SEALED_SOURCE_REFERENCES', old_pair=[OLD_BUILD, OLD_RUN], survey=survey,
                 freeable_single_link_bytes=sum(row['single_link_allocated_bytes'] for row in survey.values()),
                 blockers=blockers, sealed_current_sources_that_would_need_editing=editing_needed,
                 decision='Not deleted. Removing the pair needs two current source edits (builder PROTECTED_ROOTS and the reward '
                          'view RUNTIME), which would make the working source differ from the sealed current Host closure. '
                          'Do it at the start of the next build wave: retarget the reward view to a current runtime with the '
                          'identical localization.db, drop 1fba from PROTECTED_ROOTS, then retire both directories with a typed plan.',
                 identical_localization_db_runtimes=[PREVIOUS_RUN, RUN],
                 deleted_files=0, native_execution=False)
    write_new(STAGE / 'prune_evaluation.json', value)
    print(json.dumps(dict(status=value['status'], freeable_single_link_bytes=value['freeable_single_link_bytes'],
                          blockers=len(blockers), saves=sum(len(row['saves_sessions_or_settings']) for row in survey.values()))))
    return 0


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
    'WindowTrim V4: Source/Assets/UIFrontEndV4 draws WindowTrimLeft/Right with the retail default Image mapping '
    '(no StretchMode: Size pixels 1:1 from TextureOffset 0,0), i.e. source 82x394 of the active 98x394 texture; the 16 '
    'right texture columns are not drawn and the 2 rows below the texture are not drawn. 152 files are hardlinks of the '
    'immutable V3 pack, 2 packets changed, V3 untouched.',
    'Options volume slider follows retail Slider 0x5e03e0 with OptionsMenu.xml EffectsVolumeSlider WheelSteps="1": '
    'Left/Up subtract and Right/Down add one percent, Home/End and Shift no longer move it, and one wheel message moves '
    'one step whatever its magnitude. The previous reversed Up/Down direction is fixed.',
    'UiPopupContext::Localize dispatches arguments like retail Locale.Lookup/ConvertTextKey: boolean -> PushArgument(int 1/0), '
    'number -> PushArgument(double) including integral values, string -> looked-up text; booleans no longer raise.']
REMAINING = [
    'Actual Host/GameCore/window/GPU/gameplay/save/mod/multicore acceptance remains deferred and incomplete.',
    'WindowTrim, slider and Locale behavior is retail-static and controlled-component verified only; no native screen was executed.',
    'WindowTrim bottom 2 rows: the retail sampler address mode and FTXT tile-shader result for v>1 are unproven; V4 does not draw them.',
    'Retail sliders move on WM_KEYUP; this window moves on the first WM_KEYDOWN of a press (auto-repeat filtered), so one press '
    'still moves one step but at press time. A key-up queue would change the shared BitmapWindow and needs an HWND to verify.',
    'Retail slider gate bit 0x10000 (keys and wheel) is not proved; the engine routes keys by focus and the wheel by the slider rectangle.',
    'The volume model keeps integer percent; retail float32 accumulation and Locale.ToPercent display rounding are not modelled.',
    'Localize still rejects nonfinite numbers (retail formats or recurses on them) and keeps Host key lookup and NUL rejection for '
    'string arguments; the double path for integral numbers (including negative zero) is unexecuted in the real Localization library.',
    'Seven supported front-end preference categories are connected, including conditional policy info; full original options and remaining menu branches need real backends.',
    'Actual display readback/confirmation timing/focus/close rollback and native UI geometry/filter/font equivalence are unexecuted.',
    'ReplayMap remains simplified; original3D map, retail replay wrapper/catalog and full original Lua execution are incomplete.',
    'The older 8837/1fba pair is retained; see prune_evaluation.json for the next-wave retirement steps.']


def publish():
    verified = read(STAGE / 'prepared_runtime_verification.json')
    assert verified['status'] == 'PASS_SINGLE_CURRENT_PREPARED_RUNTIME_AND_FULL_SOURCE_CLOSURE_NOT_EXECUTED'
    assert (verified['build_id'], verified['run_id']) == (BUILD, RUN) and verified['sidecar_matches_v4_manifest'] is True
    protection = read(STAGE / 'protection_after.json')
    assert protection['status'] == 'PASS'
    prune = read(STAGE / 'prune_evaluation.json')
    assert prune['deleted_files'] == 0
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
    for name in ('MenuFrontEndOptionsModel.h', 'UiPopupContext.h'):
        assert any(item.casefold() == ('source\\host\\' + name).casefold() for item in changed), name
    assert any(item.casefold() == 'source\\host\\uilocalearguments.h' for item in added), added
    proofs = {name: ref(PROJECT / path) for name, (path, _) in PROOFS.items()}
    statuses = {name: read(PROJECT / path).get('status') for name, (path, status) in PROOFS.items() if status}
    expected = {name: status for name, (_, status) in PROOFS.items() if status}
    assert statuses == expected, statuses
    options = read(PROJECT / PROOFS['options_integration_v4'][0])
    locale = read(PROJECT / PROOFS['locale_arguments'][0])
    assert options['retail_slider_rules']['step_percent'] == 1 and options['protected_inputs_unchanged'] is True
    assert locale['checks'] == 20 and locale['protected_inputs_unchanged'] is True
    host = dict(status='CURRENT_COMPILED_EXPLICIT_PREPARED_PROFILE_NOT_REGISTERED_OR_EXECUTED', build_id=BUILD,
                parent_build_id=PREVIOUS_BUILD, executable=build['executable'], build_result=verified['build_result'],
                independent_attestation=ref(pair / 'independent_attestation.json'), prepared_profile=verified['profile'],
                **counts, catalog_entries=74, required_sidecar_files=154, sidecar_asset_pack='Source/Assets/UIFrontEndV4',
                sources_changed_from_parent=changed, sources_added_from_parent=added,
                registered=False, globally_registered=False, prepared_profile_only=True, host_executed=False,
                gamecore_loaded=False, screen_verification_deferred=True, full_engine_goal_complete=False)
    runtime = Path(verified['runtime_directory'])
    prepared = dict(status='CURRENT_EXPLICIT_NATIVE_OFFLINE_FOLLOWUP_HOST_V4_SIDECAR_AND_UNCHANGED_SDK_PREPARED_NOT_EXECUTED',
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
                 retained_previous_pair=[PREVIOUS_BUILD, PREVIOUS_RUN], prune_evaluation=ref(STAGE / 'prune_evaluation.json'),
                 next_prune_candidates_not_deleted=['Build/UiWindowHost/' + OLD_BUILD, 'Build/InteractiveGameRuntime/' + OLD_RUN],
                 prune_note=prune['decision'])
    supersedes = dict(
        windowtrim_record=ref(PROJECT / 'evidence/game_menu/frontend_windowtrim/current_work.json'),
        note='The WindowTrim evidence stage recorded the native mapping with implementation deferred; this wave implements it as V4.',
        replay_season_wheel_remaining='Its "Locale argument divergences remain recorded only" and "Four WindowTrim candidates" items are resolved here.')
    current = dict(schema='zerosis.native_offline_followup.current_work.v1', utc=datetime.now(timezone.utc).isoformat(),
                   status='PASS_CURRENT_X64_NATIVE_OFFLINE_FOLLOWUP_PAIR_PREPARED_OFFLINE', goal_turn_classification='progress',
                   full_goal_redefined=False, full_engine_goal_complete=False, implemented=IMPLEMENTED,
                   slider_rules=options['retail_slider_rules'], locale_dispatch=locale['retail_dispatch'],
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
    progress['native_offline_followup_stage'] = dict(current, record=ref(STAGE / 'current_work.json'))
    progress.setdefault('storage', {})['latest_native_offline_followup_wave'] = space
    progress['storage']['older_fields_are_prior_wave_history'] = True
    path.write_text(json.dumps(progress, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps(dict(status=current['status'], build=BUILD, runtime=RUN, counts=counts,
                          allocated_change=space['allocated_bytes_change'], changed_sources=len(changed), added=added)))
    return 0


if __name__ == '__main__':
    commands = {'protect': protect, 'prune-evaluation': prune_evaluation, 'docs-backup': docs_backup, 'publish': publish}
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        raise SystemExit(__doc__)
    raise SystemExit(commands[sys.argv[1]]())
