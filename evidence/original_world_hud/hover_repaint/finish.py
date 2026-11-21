"""Retire this task's exact intermediates and publish its offline build result."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys
import types

STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[2]
BUILD_ID = '20261024T082423Z_b604cddf0d2d'
LINK_STAGE = STAGE / 'host_build/b604cddf0d2d34d1c183'
BUILD = PROJECT / 'Build/UiWindowHost' / BUILD_ID
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
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--attestation-sha256', required=True)
    options = cli.parse_args()
    assert __debug__ and sys.dont_write_bytecode
    b = load(PROJECT / 'tools/build_hud_hover_repaint_host.py',
             'b1a18dcfedddeb851a0c1d236725d47a3a6dece9657e0d290af7627a64190043', 'hover_finish_files')
    load(PROJECT / 'tools/prepare_current_sdk_play.py',
         '1254720f955671dc895c45109a9417a088211f0f5823d9c26e1d8b2ebf90e8ae', 'prepare_current_sdk_play')
    storage = load(PROJECT / 'evidence/native_restore_contract/pair_preparation/publish.py',
                   '1f4771576092bfbfcd34d899b0ac0ce03fa0a43ac50b5b37825784c4e8da1406', 'hover_finish_storage')
    run_ref = b.pin(LINK_STAGE / 'run.json', 'd4dc27b269ce8d8ce664aa0a9448ea602f5a24fe7489ce1fbc94d71ae2d37a7d')
    run = json.loads(b.sealed_bytes(run_ref))
    attestation = b.pin(LINK_STAGE / 'attestation.json', options.attestation_sha256)
    att = json.loads(b.sealed_bytes(attestation))
    assert att['status'] == 'PASS_CURRENT_HOVER_HOST_STATIC_ATTESTATION' and att['build_id'] == BUILD_ID
    assert not att['host_executed'] and not att['sdk_loaded'] and not att['window_created']
    report_ref = b.sealed(run['build_result'])
    report = json.loads(b.sealed_bytes(report_ref))
    assert report['build_id'] == BUILD_ID and report['status'] == 'UI_WINDOW_HOST_CANDIDATE_BUILT'
    for declared, expected in ((att['run'], run_ref), (att['build_result'], report_ref),
                               (att['executable'], report['executable'])):
        assert b.key(declared['path']) == b.key(expected['path'])
        assert all(declared[name] == expected[name] for name in ('bytes', 'sha256'))
        b.sealed(expected)
    progress_before = b.pin(PROGRESS, '4663a1c628911d8a530d04a620bc0a849713ece41c4cc1b8c12622fe32ee0441')
    doc_before = b.pin(DOCUMENT, '6b4e39786f6916ca2179a07e4f6780d8f25e59417502662ebb498be23c3a4bb0')
    assert not (STAGE / 'final_audit.json').exists() and not (STAGE / 'link_cleanup_plan.json').exists()

    def write(path, value):
        assert b.inside(path, STAGE) and not os.path.lexists(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('x', encoding='utf-8', newline='\n') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')

    def snapshot(path):
        row = b.artifact(path)
        info = b.ordinary(path)
        row.update(nlinks=info.st_nlink, allocated_bytes=storage.allocation(path))
        return row

    def unchanged(row):
        current = snapshot(Path(row['path']))
        assert current == row, row['path']
        return current

    def archive(row, path):
        raw = b.sealed_bytes(row)
        packed = gzip.compress(raw, compresslevel=9, mtime=0)
        assert not os.path.lexists(path) and b.inside(path, STAGE)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(packed)
        assert gzip.decompress(path.read_bytes()) == raw
        return b.artifact(path)

    originals = []
    for index, (unit, stem, row) in enumerate(zip(b.UNITS, b.STEMS, run['compilation'], strict=True)):
        expected_path = BUILD / 'final' / ('tu_%02d_%s' % (index, unit)) / 'obj' / (stem + '.obj')
        assert row['translation_unit'] == unit and b.key(row['object']['path']) == b.key(expected_path)
        b.sealed(row['object'])
        originals.append(snapshot(expected_path))
    environment_path = BUILD / 'read_build_environment.cmd'
    expected_environment = ('@echo off\ncall "C:\\Program Files\\Microsoft Visual Studio\\2022\\Community\\VC\\Auxiliary\\Build\\vcvars64.bat" >nul\n'
                            'if errorlevel 1 exit /b %errorlevel%\nset\n').encode('ascii')
    assert environment_path.read_bytes() == expected_environment
    originals.append(snapshot(environment_path))
    component_root = PROJECT / 'Build/UiPanelRepaint/current'
    generated = (
        ('lua_input/fixture/20261024T074849Z_457e2ec70d5d', 'research_timer0_input.lua'),
        ('lua_input/fixture/20261024T074849Z_457e2ec70d5d', 'ui_presentation_input.lua'),
        ('lua_input_retry01/fixture/20261024T075328Z_d6e31f2bc3a4', 'research_timer0_input.lua'),
        ('lua_input_retry01/fixture/20261024T075328Z_d6e31f2bc3a4', 'research_tree_timer1_horizontal_input.lua'),
        ('lua_input_retry01/fixture/20261024T075328Z_d6e31f2bc3a4', 'ui_presentation_input.lua'),
        ('lua_input_retry01/fixture/20261024T075328Z_d6e31f2bc3a4', 'unit_panel_consume_mouse_input.lua'))
    archives = []
    for relative, name in generated:
        path = component_root / relative / name
        row = snapshot(path)
        assert b.inside(path, component_root) and path.suffix == '.lua'
        packed_path = STAGE / 'retired_harnesses' / (Path(relative).parts[0] + '__' + name + '.gz')
        archives.append(dict(original=row, archive=archive(row, packed_path), gzip_roundtrip_verified=True))
        originals.append(row)
    assert len(originals) == 12 and len({b.key(row['path']) for row in originals}) == 12
    for row in originals:
        path = Path(row['path'])
        assert b.inside(path, BUILD) or b.inside(path, component_root)
        assert row['nlinks'] == 1 and not row['file_attributes'] & 1
    protected = {}
    for row in [*run['protected_runtime_inputs'], *run['current_inputs'], *run['materialized'],
                report_ref, run_ref, attestation, report['executable'], report['map']]:
        protected[b.key(row['path'])] = b.sealed(row)
    assert not {b.key(row['path']) for row in originals} & set(protected)
    plan = dict(schema='zerosis.hover_host.exact_retirement_plan.v1', targets=originals,
        source_harness_archives=archives, protected_files=list(protected.values()),
        logical_bytes=sum(row['bytes'] for row in originals),
        allocated_bytes=sum(row['allocated_bytes'] for row in originals),
        recursive_deletion=False, user_originals_or_saves_or_current_executable_deleted=False)
    write(STAGE / 'link_cleanup_plan.json', plan)
    write(STAGE / 'link_cleanup_started.json', dict(plan=b.artifact(STAGE / 'link_cleanup_plan.json'), automatic_retry_allowed=False))
    deleted = []
    try:
        for row in originals:
            unchanged(row)
            Path(row['path']).unlink()
            assert not os.path.lexists(row['path'])
            deleted.append(row)
        for row in protected.values():
            b.sealed(row)
        cleanup = dict(schema='zerosis.hover_host.exact_retirement_result.v1', status='PASS_EXACT_TWELVE_INTERMEDIATES_RETIRED',
            error=None, plan=b.artifact(STAGE / 'link_cleanup_plan.json'), deleted=deleted,
            logical_bytes=plan['logical_bytes'], allocated_bytes=plan['allocated_bytes'],
            protected_files_rehashed=len(protected), harness_archive_count=6,
            archive_logical_bytes=sum(row['archive']['bytes'] for row in archives),
            host_sdk_or_window_executed=False)
        write(STAGE / 'link_cleanup_result.json', cleanup)
    except BaseException as error:
        write(STAGE / 'link_cleanup_failure.json', dict(error=type(error).__name__ + ': ' + str(error),
            deleted=deleted, do_not_replay=True))
        raise

    progress_raw, doc_raw = b.sealed_bytes(progress_before), b.sealed_bytes(doc_before)
    progress_backup = archive(progress_before, STAGE / 'source_backups/current_progress.before_link_publication.gz')
    doc_backup = archive(doc_before, STAGE / 'source_backups/ORIGINAL_WORLD_HUD.before_hover_link.gz')
    cleanup_ref = b.artifact(STAGE / 'link_cleanup_result.json')
    component_ref = b.pin(STAGE / 'component_audit.json', '80f806d06fc519005579ae421ebfcbbe8377173d2a11d4057f674e0f60e170de')
    doc_text = doc_raw.decode('utf-8-sig').replace('Production changes are limited to WorldViewRenderer.cpp,',
        'The initial viewport/wheel production changes are limited to WorldViewRenderer.cpp,', 1)
    doc_text += (
        '\n## Pointer-hover repaint follow-up\n\n'
        'UiPanelRepaint.h separates input consumption from actual scene changes. The\n'
        'four HUD dispatch paths retain their existing return values and exception\n'
        'propagation. Pointer snapshots use the same owner clock without an SDK tick;\n'
        'only actual hover/tooltip changes request repaint. Keyboard, camera, modal,\n'
        'stale-generation and preparation protections remain in the original paths.\n'
        'InteractiveUiSession.h, InteractiveGameSession.h and InteractiveGameLoop.h\n'
        'use this helper. Save and mod schemas are unchanged.\n\n'
        'Actual native component runs passed 27 cases and 150 checks in each of O2\n'
        'and Od/RTC1. Seven retained-original Lua fixtures cover repeated hover,\n'
        'key-zero no-ops, actual hover/tooltip changes, and existing click/scroll\n'
        'behavior. ActionInfo performed 144 checks and Notification 149. These are\n'
        'component fixtures with synthetic SDK bindings, not live game behavior.\n\n'
        f'The current Host `{BUILD_ID}` compiled all five translation units and\n'
        'linked once with 550 actual compiler inputs, 86 source-manifest entries and\n'
        '593 current inputs. Independent file-only attestation checks its 67 exact\n'
        'embedded payloads, 24 imports, and restore marker. Four source copies total\n'
        '420,065 bytes; 589 immutable inputs share existing file identities.\n'
        'The current prepared runtime still uses the earlier 974a Host. The new\n'
        'Host has not been prepared, launched, or accepted in a native UI test.\n'
        'Screen verification remains deferred by the user. This fix is not evidence\n'
        'that the previously unobserved click or wheel is now working.\n\n'
        'Build and attestation receipts are under\n'
        '`evidence/original_world_hud/hover_repaint/host_build/b604cddf0d2d34d1c183/`.\n'
        'Five new Host objects, its environment script and six generated Lua\n'
        f'harness scripts were retired: {cleanup["logical_bytes"]:,} logical bytes and\n'
        f'{cleanup["allocated_bytes"]:,} allocated file-data bytes. The six harnesses\n'
        'are retained only as hash-verified, roundtrip-checked gzip files; old report\n'
        'references to uncompressed generated harnesses or objects are historical.\n'
        'Current executable, map, compiler dependencies, changed-file backups,\n'
        'component executables, prior runtime and six native trial saves remain.\n')
    with DOCUMENT.open('w', encoding='utf-8', newline='\n') as stream:
        stream.write(doc_text)
    doc_after = b.artifact(DOCUMENT)
    progress = json.loads(progress_raw)
    progress['previous_linked_candidate_compile_link_proof'] = progress['last_linked_candidate_compile_link_proof']
    progress['previous_linked_candidate_pe_attestation'] = progress['last_linked_candidate_pe_attestation']
    progress.update(utc=datetime.now(timezone.utc).isoformat(),
        status='PASS_CURRENT_HOVER_HOST_LINK_AND_STATIC_ATTESTATION_RUNTIME_PREPARATION_PENDING',
        prior_goal_turn_classification='progress', current_goal_turn_classification='progress',
        current_host_build_id=BUILD_ID, latest_source_matches_linked_candidate=True,
        latest_host_source_matches_current_link_proof=True,
        latest_current_source_actual_cpp_compilation_verified=True,
        latest_cpp_source_matches_actual_host_syntax_proof=True,
        latest_current_source_compile_link_proof=report_ref, latest_current_source_pe_attestation=attestation,
        last_linked_candidate_compile_link_proof=report_ref, last_linked_candidate_pe_attestation=attestation,
        latest_actual_host_syntax_proof=report_ref,
        latest_actual_host_syntax_proof_scope='Five actual current Host translation units compiled and linked once; static PE verified; native behavior pending.',
        prepared_runtime_matches_current_linked_candidate=False, prepared_runtime_matches_latest_source=False,
        latest_private_prepared_pair_matches_current_host_and_selected_sdk_sources=False,
        default_prepared_runtime_matches_latest_source=False, current_native_or_screen_relaunch_allowed=False,
        screen_verification_deferred=True, full_engine_goal_complete=False)
    stage = progress['hud_hover_repaint_stage']
    stage.update(status='PASS_COMPONENT_LUA_AND_FULL_HOST_LINK_STATIC_ATTESTATION_RUNTIME_PENDING',
        component_audit=component_ref, host_build_id=BUILD_ID, host_build_result=report_ref,
        host_static_attestation=attestation, executable=report['executable'], cleanup=cleanup_ref,
        native_cases_per_mode=27, native_checks_per_mode=150, lua_fixture_count=7,
        current_host_contains_fix=True, current_prepared_runtime_contains_fix=False,
        actual_click_or_world_wheel_fix_verified=False, screen_verification_deferred=True,
        host_sdk_window_execution_allowed=False, default_promoted=False,
        documentation=doc_after, save_wire_or_mod_schema_changed=False, full_engine_goal_complete=False)
    world = progress['original_world_hud_stage']
    world.update(current_host_build_id=BUILD_ID, current_host_build_result=report_ref,
        current_host_static_attestation=attestation, current_host_executable=report['executable'],
        current_host_retirement=cleanup_ref, latest_prepared_pair_contains_hover_fix=False)
    world['proofs']['documentation'] = doc_after
    for name in ('current_prepared_runtime', 'original_world_hud_pair_preparation_stage'):
        progress[name].update(status='EXECUTED_PRIOR_HOST_NORMAL_CLOSE_LATEST_HOST_NOT_PREPARED_SCREEN_DEFERRED',
            current_source_candidate=False, current_host_source_closure_matches_candidate=False,
            current_candidate_prepared=False, preparation_succeeded_for_its_frozen_sources=True,
            latest_linked_candidate_matches_frozen_runtime=False, working_host_source_differs_from_runtime=True)
    progress.setdefault('storage', {})['hud_hover_repaint_stage'] = dict(
        cleanup=cleanup_ref, retired_allocated_bytes=cleanup['allocated_bytes'],
        initial_component_cleanup_allocated_bytes=782624, whole_project_net_change_not_measured=True)
    with PROGRESS.open('w', encoding='utf-8', newline='\n') as stream:
        json.dump(progress, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    progress_after = b.artifact(PROGRESS)
    changes = []
    for before, backup, after in ((progress_before, progress_backup, progress_after), (doc_before, doc_backup, doc_after)):
        changes.append(dict(before=dict(original_path=before['path'], bytes=before['bytes'], sha256=before['sha256']),
                            backup=backup, after=after, gzip_roundtrip_verified=True))
    write(STAGE / 'publication.json', dict(schema='zerosis.hover_host.publication.v1',
        status='PASS_OFFLINE_HOST_LINK_PUBLICATION', changed_metadata=changes,
        current_host=report['executable'], build=report_ref, attestation=attestation,
        current_runtime_contains_new_host=False, host_sdk_or_window_executed=False))

    for row in [*run['current_inputs'], *run['materialized'], *run['protected_runtime_inputs']]:
        if b.key(row['path']) not in {b.key(PROGRESS), b.key(DOCUMENT)}:
            b.sealed(row)
    for row in originals:
        assert not os.path.lexists(row['path'])
    for row in archives:
        packed = b.sealed_bytes(row['archive'])
        raw = gzip.decompress(packed)
        assert (len(raw), hashlib.sha256(raw).hexdigest()) == (row['original']['bytes'], row['original']['sha256'])
    roots = [STAGE, component_root, BUILD, Path(report_ref['path']).parent]
    file_ids = {}
    aliases = logical = 0
    for root in roots:
        for folder, dirs, files in os.walk(root, followlinks=False):
            assert not Path(folder).lstat().st_file_attributes & 0x400
            for name in files:
                path = Path(folder) / name
                info = b.ordinary(path)
                aliases += 1; logical += info.st_size
                file_ids.setdefault((info.st_dev, info.st_ino), storage.allocation(path))
    donor_ids = {tuple(row['file_identity']) for row in run['frozen_donors']}
    exclusive = {fid: size for fid, size in file_ids.items() if fid not in donor_ids}
    before_storage = json.loads((STAGE / 'storage_before_host_link.json').read_bytes())
    measured = dict(schema='zerosis.hover_host.scoped_storage_after.v1',
        scope_roots=[str(root) for root in roots], files=aliases, logical_bytes=logical,
        unique_file_ids=len(file_ids), all_scoped_allocated_bytes=sum(file_ids.values()),
        existing_donor_file_ids_excluded=len(set(file_ids) & donor_ids),
        retained_allocation_excluding_existing_donors=sum(exclusive.values()),
        prelink_scoped_allocated_bytes=before_storage['allocated_bytes'],
        scoped_delta_from_prelink_excluding_existing_donors=sum(exclusive.values()) - before_storage['allocated_bytes'],
        freed_allocation_bytes=cleanup['allocated_bytes'], prior_component_freed_allocation_bytes=782624,
        whole_project_or_whole_build_net_change_measured=False,
        measured_before_this_storage_receipt_and_final_audit=True)
    write(STAGE / 'storage_after_host_link.json', measured)
    final = dict(schema='zerosis.hover_host.final_audit.v1',
        status='PASS_CURRENT_HOVER_HOST_LINK_PUBLICATION_AND_EXACT_RETIREMENT',
        current_goal_turn_classification='progress', component_audit=component_ref,
        build=report_ref, build_run=run_ref, attestation=attestation, executable=b.sealed(report['executable']),
        publication=b.artifact(STAGE / 'publication.json'), progress=progress_after, documentation=doc_after,
        cleanup=cleanup_ref, storage=b.artifact(STAGE / 'storage_after_host_link.json'),
        deleted_files=len(originals), source_harness_gzip_roundtrips=6,
        current_inputs_rehashed=593, materialized_inputs_rehashed=593,
        native_sdk_host_or_window_execution=False, current_runtime_contains_new_hover_fix=False,
        next_required_work='Prepare the attested Host with the selected SDK without launching it; actual input/turn/restore verification remains deferred.',
        screen_verification_deferred=True, full_engine_goal_complete=False)
    write(STAGE / 'final_audit.json', final)
    print(json.dumps(dict(status=final['status'], final_audit=b.artifact(STAGE / 'final_audit.json'),
        reclaimed_allocated_bytes=cleanup['allocated_bytes'],
        retained_scoped_allocated_bytes_excluding_existing_donors=sum(exclusive.values()),
        scoped_delta_excluding_existing_donors=measured['scoped_delta_from_prelink_excluding_existing_donors'])))


if __name__ == '__main__':
    main()
