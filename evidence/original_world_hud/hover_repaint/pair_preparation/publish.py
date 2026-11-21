"""Audit and publish one prepared pair without launching its native images."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys
import types

STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[3]
RUN_ID = '20261024T091253Z_713037fbac49'
HOST_ID = '20261024T082423Z_b604cddf0d2d'
RUNTIME = PROJECT / 'Build/InteractiveGameRuntime' / RUN_ID
EVIDENCE = PROJECT / 'evidence/interactive_game' / RUN_ID
PROGRESS = PROJECT / 'evidence/save_menu/20261013_original_screen/current_progress.json'
DOCUMENT = PROJECT / 'docs/ORIGINAL_WORLD_HUD.md'


def load(path, digest, name):
    before = path.stat()
    with path.open('rb') as stream:
        raw = stream.read(before.st_size + 1)
    after = path.stat()
    assert (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) == (
        after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    assert len(raw) == before.st_size and hashlib.sha256(raw).hexdigest() == digest
    module = types.ModuleType(name)
    module.__file__ = str(path)
    sys.modules[name] = module
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


def main():
    assert __debug__ and sys.dont_write_bytecode
    assert not (STAGE / 'publication.json').exists() and not (STAGE / 'final_audit.json').exists()
    b = load(PROJECT / 'tools/build_hud_hover_repaint_host.py',
        'b1a18dcfedddeb851a0c1d236725d47a3a6dece9657e0d290af7627a64190043', 'hover_pair_publication_files')
    load(PROJECT / 'tools/prepare_current_sdk_play.py',
        '1254720f955671dc895c45109a9417a088211f0f5823d9c26e1d8b2ebf90e8ae', 'prepare_current_sdk_play')
    allocation = load(PROJECT / 'evidence/native_restore_contract/pair_preparation/publish.py',
        '1f4771576092bfbfcd34d899b0ac0ce03fa0a43ac50b5b37825784c4e8da1406', 'hover_pair_publication_storage')
    result_ref = b.pin(STAGE / 'materialization/result.json',
        '144bd6e158a2ccf85ee67c61b8a63cc8ef8cbd099f33d0885e0628485f493a41')
    result = json.loads(b.sealed_bytes(result_ref))
    request_ref = b.sealed(result['request'])
    assert request_ref['sha256'] == 'b4ac385463c3f37e27ce2ad685de92e1145776ba80af61398ff093d9f627dfe4'
    request = json.loads(b.sealed_bytes(request_ref))
    assert result['status'] == 'PASS_CURRENT_HOST_AND_GREAT_WORK_SDK_PREPARED_NOT_EXECUTED'
    assert result['run_id'] == request['run_id'] == RUN_ID and result['host_build_id'] == HOST_ID
    assert result['native_attempts'] == 0 and result['guard_denials'] == [] and not result['host_or_sdk_executed']
    assert result['current_hover_repaint_included'] and result['current_original_world_hud_included']
    assert not result['default_promoted'] and not result['prior_bundle_migrated'] and not result['full_engine_goal_complete']
    assert b.key(request['cwd']) == b.key(RUNTIME) and not request['smoke'] and request['resume_from'] is None
    assert not (RUNTIME / 'sessions').exists()
    runtime_files = [path for path in RUNTIME.rglob('*') if path.is_file()]
    assert len(runtime_files) == 35
    for path in runtime_files:
        b.ordinary(path)
    inputs = {Path(row['path']).name: row for row in request['runtime_inputs']}
    assert len(inputs) == len(request['runtime_inputs']) == 24
    for row in inputs.values():
        assert b.key(Path(row['path']).parent) == b.key(RUNTIME)
        actual = b.artifact(row['path'])
        assert actual['sha256'] == row['sha256'] and actual['bytes'] == row.get('bytes', actual['bytes'])
    assert inputs['ZeroSisHost_x64.exe']['sha256'] == '8e24b066b8f00c1c473def10da9d11c920ee460f03ef223123fcecc1b8fc4741'
    assert inputs['CvGameCoreDLL_Expansion2_x64.dll']['sha256'] == '430f3122d0b555d6daae14aa7c011ef43ce8f978270477c8af596ca4b0493ab9'

    def write(path, value):
        assert b.inside(path, STAGE) and not os.path.lexists(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('x', encoding='utf-8', newline='\n') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')

    before_ref = b.pin(STAGE / 'before_materialization.json',
        'be2412741d799e72e05597ce6fb5177cbb973fe3ff5c07d4a2234d7db85aff12')
    before = json.loads(b.sealed_bytes(before_ref))
    expected_link_additions = Counter()
    immutable = []
    private = []
    for item in request['materializations']:
        target = Path(item['target'])
        info = b.ordinary(target)
        if item['materialization_method'] == 'hardlink':
            cache = Path(item['cache'])
            assert b.inside(cache, PROJECT / 'Build/RuntimeInputCache')
            cache_ref = b.pin(cache, item['sha256'])
            target_ref = b.pin(target, item['sha256'])
            assert cache_ref['file_identity'] == target_ref['file_identity']
            assert info.st_file_attributes & 1
            expected_link_additions[tuple(target_ref['file_identity'])] += 1
            immutable.append(dict(cache=cache_ref, target=target_ref))
        else:
            assert item['materialization_method'] == 'private-copy' and target.name in ('rules.db', 'localization.db')
            assert info.st_nlink == 1 and not info.st_file_attributes & 1
            row = b.artifact(target)
            assert tuple(row['file_identity']) not in {tuple(x['file_identity']) for x in before['protected']}
            private.append(row)
    assert len(immutable) == 15 and len(private) == 2
    topology_changes = []
    for row in before['protected']:
        actual = b.sealed(row)
        info = b.ordinary(row['path'])
        addition = expected_link_additions[tuple(actual['file_identity'])]
        assert info.st_nlink == row['nlinks'] + addition, row['path']
        if addition:
            topology_changes.append(dict(path=row['path'], added_aliases=addition))
    support = request['interactive_ui_support_inventory']
    expected_tools = {'interactive_ui_driver.py', 'render_ui_popup.py', 'ui_pixel_scene.py',
                      'ui_bitmap_fonts.py', 'civ5_ui_assets.py', 'found_value_runtime_options.py'}
    assert set(support['tools']) == expected_tools
    for name, row in support['tools'].items():
        source = row['source']
        frozen = row['frozen']
        assert b.key(frozen['path']) == b.key(RUNTIME / 'interactive_ui_support/tools' / name)
        actual = b.artifact(frozen['path'])
        assert actual['sha256'] == source['sha256'] == frozen['sha256']
        assert actual['bytes'] == source['bytes']
        b.pin(Path(source['original_path']), source['sha256'])
    launcher = b.pin(Path(request['launcher']['path']), request['launcher']['sha256'])
    resume = b.pin(Path(request['resume_launcher']['path']), request['resume_launcher']['sha256'])
    assert "throw 'Save loading is disabled" in Path(resume['path']).read_text(encoding='utf-8-sig')
    assert "$env:ZEROSIS_UI_POLICY_INFO = '1'" in Path(launcher['path']).read_text(encoding='utf-8-sig')
    assert request['policy_info_options']['policy_info'] == 1
    assert request['host_runtime_validation']['registered_build_id'] == HOST_ID
    assert not request['host_runtime_validation']['execution_authorized']
    scope = request['runtime_sdk_candidate_scope']
    assert scope['new_game_only'] and not scope['host_sdk_execution_verified'] and not scope['default_release_changed']
    gate_ref = b.artifact(STAGE / 'actual_host_input_gate.json')
    operations_ref = b.pin(STAGE / 'operational_revisions.json',
        '9dba1cb89f64c356b8bd0b10028d4853c651ccfd3d728cd77a8f9564af007573')
    audit = dict(schema='zerosis.hover_pair.prepared_audit.v1', status='PASS_PREPARED_HOVER_PAIR_NOT_EXECUTED',
        prepared_result=result_ref, request=request_ref, run_id=RUN_ID, host_build_id=HOST_ID,
        runtime_inputs=24, runtime_file_count=len(runtime_files), immutable_aliases=immutable,
        private_databases=private, ui_support_tools=6, prior_input_baseline=before_ref,
        old_inputs_preserved=len(before['protected']), permitted_alias_topology_changes=topology_changes,
        current_host_input_gate=gate_ref, operational_revisions=operations_ref, launcher=launcher, resume_launcher=resume,
        explicit_policy_info_environment=1, native_attempts=0, guard_denials=[], default_promoted=False,
        new_runtime_sessions_absent=True, screen_verification_deferred=True, full_engine_goal_complete=False)
    write(STAGE / 'audit.json', audit)
    progress_before = b.pin(PROGRESS, 'b1dc214e1c00f2324ed295d730ef07723414c119e4c81c5e5e3344dad0518e6e')
    doc_before = b.pin(DOCUMENT, '0b8739e0b34c53d23fc121eedc18e0643b40439c22ccc2a8ea624727db28e066')
    backups = []
    for row, name in ((progress_before, 'current_progress.before_prepared_pair.gz'),
                      (doc_before, 'ORIGINAL_WORLD_HUD.before_prepared_pair.gz')):
        raw = b.sealed_bytes(row)
        path = STAGE / 'source_backups' / name
        assert not path.exists()
        with path.open('xb') as stream:
            stream.write(gzip.compress(raw, compresslevel=9, mtime=0))
        assert gzip.decompress(path.read_bytes()) == raw
        backups.append((row, b.artifact(path)))
    progress = json.loads(b.sealed_bytes(progress_before))
    previous = progress['current_prepared_runtime']
    assert previous['run_id'] == '20261024T070230Z_cbbd79f1cbb6'
    previous.update(status='SUPERSEDED_EXECUTED_PRIOR_PAIR_PRESERVED_SCREEN_DEFERRED',
                    historical_runtime=True, superseded_by_prepared_run=RUN_ID)
    progress['prior_current_prepared_runtime_metadata'] = previous
    progress['original_world_hud_pair_preparation_stage'].update(
        status='SUPERSEDED_EXECUTED_PRIOR_PAIR_PRESERVED_SCREEN_DEFERRED',
        historical_runtime=True, superseded_by_prepared_run=RUN_ID)
    current = dict(status='CURRENT_HOVER_HOST_AND_SELECTED_SDK_PREPARED_NOT_EXECUTED_SCREEN_DEFERRED',
        run_id=RUN_ID, host_build_id=HOST_ID, host=result['host'], gamecore=result['gamecore'], bundle_manifest=result['bundle_manifest'],
        proofs=dict(preparation=result_ref, request=request_ref, audit=b.artifact(STAGE / 'audit.json'),
                    host_input_gate=gate_ref, operational_revisions=operations_ref),
        runtime_input_count=24, immutable_hardlinks=15, private_databases=2, current_python_support_count=6,
        new_game_only=True, save_loading_launcher_disabled=True, current_source_candidate=True,
        current_host_source_closure_matches_candidate=True, selected_sdk_includes_current_great_work_guard=True,
        current_candidate_prepared=True, latest_linked_candidate_matches_frozen_runtime=True,
        working_host_source_differs_from_runtime=False, current_hover_repaint_included=True,
        host_executed=False, gamecore_loaded=False, window_created=False, city_founding_verified=False,
        turn_advancement_verified=False, actual_windows_wheel_routing_verified=False, save_compatibility_verified=False,
        original_ui_accepted=False, prior_bundle_save_migration_performed=False, default_promoted=False,
        physical_multicore_verified=False, performance_improvement_verified=False,
        full_original_ui_3d_campaign_verified=False, full_engine_goal_complete=False)
    progress.update(utc=datetime.now(timezone.utc).isoformat(),
        status='PASS_CURRENT_HOVER_HOST_AND_SDK_PREPARED_NOT_EXECUTED_SCREEN_DEFERRED',
        prior_goal_turn_classification='progress', current_goal_turn_classification='progress',
        current_prepared_runtime=current, hud_hover_repaint_pair_preparation_stage=current,
        latest_host_sdk_preparation_stage=current,
        prepared_runtime_matches_current_linked_candidate=True, prepared_runtime_matches_latest_source=True,
        latest_private_prepared_pair_matches_current_host_and_selected_sdk_sources=True,
        default_prepared_runtime_matches_latest_source=False, current_native_or_screen_relaunch_allowed=False,
        screen_verification_deferred=True, full_engine_goal_complete=False)
    progress['hud_hover_repaint_stage'].update(status='PASS_COMPONENTS_LINK_STATIC_ATTESTATION_AND_PREPARATION_SCREEN_DEFERRED',
        current_prepared_runtime_contains_fix=True, latest_prepared_runtime=RUN_ID,
        preserved_previous_runtime_id=previous['run_id'], preparation=result_ref)
    progress['original_world_hud_stage'].update(
        status='CURRENT_HOVER_PAIR_PREPARED_PRIOR_NATIVE_WORLD_HUD_TRIAL_PARTIAL_SCREEN_DEFERRED',
        current_run_id=RUN_ID, last_observed_run_id=previous['run_id'],
        latest_prepared_pair_contains_hover_fix=True, latest_prepared_pair_contains_changes=True,
        latest_pair_native_executed=False)
    text = b.sealed_bytes(doc_before).decode('utf-8-sig')
    old = ('The current prepared runtime still uses the earlier 974a Host. The new\n'
           'Host has not been prepared, launched, or accepted in a native UI test.\n')
    assert text.count(old) == 1
    text = text.replace(old, (
        f'The prepared runtime `{RUN_ID}` now pairs this Host\n'
        'with the selected `430f3122` SDK. It has not been launched or accepted in a\n'
        'native UI test. The earlier cbbd trial and its partial native observations remain.\n'), 1)
    text += ('\n## Prepared hover pair\n\n'
        f'`{RUN_ID}` contains 24 backend inputs and 35 runtime files.\n'
        'Fifteen immutable inputs share cache identities, two databases have private\n'
        'file identities, and six Python UI support files match their sources. Only\n'
        'the new Host payload was added to the shared cache. The preparation guard\n'
        'recorded zero native attempts and no denied operations. Fifty-six retained\n'
        'runtime/save/default inputs preserve their bytes, identities and attributes;\n'
        'only the expected new immutable aliases change link counts.\n\n'
        'Play.ps1 explicitly sets ZEROSIS_UI_POLICY_INFO=1 from the preserved private\n'
        'settings. Resume.ps1 rejects cross-bundle save loading. No default release,\n'
        'installed game, mod or user save was promoted or migrated. Actual input,\n'
        'turn advancement, restore, original UI equivalence and performance remain\n'
        'unverified, and the user screen hold remains in force. Receipts are under\n'
        '`evidence/original_world_hud/hover_repaint/pair_preparation/`.\n')
    with DOCUMENT.open('w', encoding='utf-8', newline='\n') as stream:
        stream.write(text)
    doc_after = b.artifact(DOCUMENT)
    progress['hud_hover_repaint_stage']['documentation'] = doc_after
    progress['original_world_hud_stage']['proofs']['documentation'] = doc_after
    with PROGRESS.open('w', encoding='utf-8', newline='\n') as stream:
        json.dump(progress, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    progress_after = b.artifact(PROGRESS)
    changes = []
    for (before_ref, backup), after in zip(backups, (progress_after, doc_after), strict=True):
        changes.append(dict(before=dict(original_path=before_ref['path'], bytes=before_ref['bytes'], sha256=before_ref['sha256']),
                            backup=backup, after=after, gzip_roundtrip_verified=True))
    write(STAGE / 'publication.json', dict(schema='zerosis.hover_pair.publication.v1',
        status='PASS_CURRENT_HOVER_PAIR_METADATA_PUBLISHED_NOT_EXECUTED', changed_metadata=changes,
        run_id=RUN_ID, current_runtime=current, prior_runtime_preserved=previous['run_id'], native_attempts=0,
        default_promoted=False, screen_verification_deferred=True, full_engine_goal_complete=False))
    excluded_ids = {tuple(row['file_identity']) for row in before['protected']}
    host_run_ref = b.pin(STAGE.parent / 'host_build/b604cddf0d2d34d1c183/run.json',
        'd4dc27b269ce8d8ce664aa0a9448ea602f5a24fe7489ce1fbc94d71ae2d37a7d')
    host_run = json.loads(b.sealed_bytes(host_run_ref))
    excluded_ids.update(tuple(row['file_identity']) for row in [*host_run['materialized'], *host_run['current_inputs']])
    cache = Path(before['new_host_cache_path'])
    roots = [STAGE, RUNTIME, EVIDENCE, cache]
    unique = {}
    logical = count = 0
    for root in roots:
        paths = [root] if root.is_file() else (Path(folder) / name for folder, dirs, names in os.walk(root, followlinks=False) for name in names)
        for path in paths:
            info = b.ordinary(path)
            fid = (info.st_dev, info.st_ino)
            count += 1; logical += info.st_size
            unique.setdefault(fid, allocation.allocation(path))
    retained = {fid: size for fid, size in unique.items() if fid not in excluded_ids}
    measured = dict(schema='zerosis.hover_pair.scoped_storage.v1', scope_roots=[str(root) for root in roots],
        logical_path_bytes=logical, file_aliases=count, unique_file_ids=len(unique),
        allocated_bytes=sum(unique.values()), prior_existing_ids_excluded=len(set(unique) & excluded_ids),
        existing_host_input_id_provenance=host_run_ref,
        new_scope_allocated_bytes_excluding_existing_inputs=sum(retained.values()),
        current_stage_disposable_bytes=0, regenerated_whole_project_or_asset_copies=0,
        whole_project_or_whole_build_net_change_measured=False,
        measured_before_this_storage_receipt_and_final_audit=True)
    write(STAGE / 'storage.json', measured)
    for row in before['protected']:
        actual = b.sealed(row)
        assert b.ordinary(row['path']).st_nlink == row['nlinks'] + expected_link_additions[tuple(actual['file_identity'])]
    for row in inputs.values():
        assert b.artifact(row['path'])['sha256'] == row['sha256']
    assert not (RUNTIME / 'sessions').exists()
    final = dict(schema='zerosis.hover_pair.final_audit.v1', status='PASS_CURRENT_HOVER_PAIR_PREPARATION_AND_PUBLICATION',
        current_goal_turn_classification='progress', preparation=result_ref, request=request_ref,
        audit=b.artifact(STAGE / 'audit.json'), publication=b.artifact(STAGE / 'publication.json'),
        storage=b.artifact(STAGE / 'storage.json'), progress=progress_after, documentation=doc_after,
        run_id=RUN_ID, host=result['host'], gamecore=result['gamecore'],
        current_native_or_screen_relaunch_allowed=False, screen_verification_deferred=True,
        old_runtime_and_native_saves_preserved=True, protected_old_files_reverified_after_publication=56,
        new_runtime_inputs_reverified_after_publication=24, default_promoted=False,
        native_attempts=0, full_engine_goal_complete=False)
    write(STAGE / 'final_audit.json', final)
    print(json.dumps(dict(status=final['status'], final_audit=b.artifact(STAGE / 'final_audit.json'),
        new_scope_allocated_bytes=sum(retained.values()), runtime_files=35, native_attempts=0)))


if __name__ == '__main__':
    main()
