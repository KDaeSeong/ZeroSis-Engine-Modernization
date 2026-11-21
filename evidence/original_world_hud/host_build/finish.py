"""Retire one attested build's six intermediates and publish its static status.

This fixed receipt writer never executes a compiler, Host, SDK, or game window.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import types

PROJECT = Path(__file__).absolute().parents[3]
STAGE = Path(__file__).absolute().parent / '974a5be5753302c4498c'
BUILD_ID = '20261024T055841Z_974a5be57533'
BUILD = PROJECT / 'Build/UiWindowHost' / BUILD_ID
OUTPUT = PROJECT / 'evidence/ui_window_host' / BUILD_ID
PROGRESS = PROJECT / 'evidence/save_menu/20261013_original_screen/current_progress.json'
PROGRESS_SHA = '425207b7b86a5fc104c3f676df8f34ee5a18cfe7262ba08145fa5559292440ea'
DOC = PROJECT / 'docs/ORIGINAL_WORLD_HUD.md'
DOC_SHA = '2caed5070927354cdd0fa4a6d44edb32ed0cb4078897011f0afc0eb86ae3843f'
HELPER = PROJECT / 'evidence/native_restore_contract/pair_preparation/publish.py'
HELPER_SHA = '1f4771576092bfbfcd34d899b0ac0ce03fa0a43ac50b5b37825784c4e8da1406'
HOLD = PROJECT / 'evidence/goody_hut/runtime_fonts/system_freeze_hold.json'
HOLD_SHA = '6e7443f5ef796c9eadee4f7fdbc4123545467031be1d5c641159283078f56a5b'


def require(value, message):
    if not value:
        raise RuntimeError(message)


def key(path):
    return os.path.normcase(os.path.abspath(path))


def inside(path, root):
    return key(path).startswith(key(root) + os.sep)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-sha256', required=True)
    parser.add_argument('--attestation-sha256', required=True)
    args = parser.parse_args()
    require(os.name == 'nt' and sys.dont_write_bytecode and not sys.flags.optimize, 'Use Windows Python -B')
    def load_source(path, expected_sha, name):
        require(inside(path, PROJECT), 'Helper escaped the workspace')
        for ancestor in (path, *path.parents):
            require(not ancestor.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT, 'Reparse helper path')
        before = path.stat()
        with path.open('rb') as stream:
            raw = stream.read(512 * 1024 + 1)
        after = path.stat()
        require(stat.S_ISREG(before.st_mode) and len(raw) <= 512 * 1024 and
                hashlib.sha256(raw).hexdigest() == expected_sha and
                (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_file_attributes) ==
                (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_file_attributes),
                'Authenticated helper changed')
        module = types.ModuleType(name)
        module.__file__ = str(path)
        sys.modules[name] = module
        exec(compile(raw, str(path), 'exec'), module.__dict__)
        return module

    load_source(PROJECT / 'tools/prepare_current_sdk_play.py',
        '1254720f955671dc895c45109a9417a088211f0f5823d9c26e1d8b2ebf90e8ae', 'prepare_current_sdk_play')
    helper = load_source(HELPER, HELPER_SHA, 'world_hud_build_storage')
    base = helper.base
    allowed_external_reads = set()

    def read_info(path):
        path = Path(path)
        if inside(path, PROJECT):
            return base.ordinary(path)
        require(key(path) in allowed_external_reads and path.is_absolute() and
                str(path) == os.path.abspath(path) and not str(path).startswith('\\\\'),
                'Unregistered external read')
        for ancestor in (path, *path.parents):
            require(not ancestor.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT,
                    'Reparse external input path')
        info = path.lstat()
        require(stat.S_ISREG(info.st_mode), 'External input is not an ordinary file')
        return info

    def snapshot(path):
        path = Path(path)
        before = read_info(path)
        require(before.st_size <= 128 * 1024 * 1024, 'Snapshot exceeded its read bound')
        with path.open('rb') as stream:
            opened = os.fstat(stream.fileno())
            require((before.st_dev, before.st_ino, before.st_size) ==
                    (opened.st_dev, opened.st_ino, opened.st_size), 'Input changed while opening')
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        info = read_info(path)
        require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_file_attributes, before.st_nlink) ==
                (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_file_attributes, info.st_nlink),
                'Input changed while hashing')
        return dict(path=str(path), bytes=info.st_size, sha256=digest,
                    file_identity=[info.st_dev, info.st_ino], mtime_ns=info.st_mtime_ns,
                    file_attributes=info.st_file_attributes, link_count=info.st_nlink)

    def check(row):
        current = snapshot(Path(row['path']))
        for field in ('bytes', 'sha256', 'file_identity', 'mtime_ns', 'file_attributes', 'link_count'):
            if field in row:
                require(current[field] == row[field], 'Changed retained input: ' + row['path'])
        return current

    def pinned(path, sha):
        row = snapshot(path)
        require(row['sha256'] == sha, 'Pinned receipt changed: ' + str(path))
        return row, base.read(path)

    run_ref, run = pinned(STAGE / 'run.json', args.run_sha256)
    att_ref, att = pinned(STAGE / 'attestation.json', args.attestation_sha256)
    require(run['status'] == 'PASS_CURRENT_ORIGINAL_WORLD_HUD_HOST_BUILD_ONLY' and run['build_id'] == BUILD_ID,
            'Unexpected build result')
    require(att['status'] == 'PASS_CURRENT_ORIGINAL_WORLD_HUD_HOST_STATIC_ATTESTATION' and att['build_id'] == BUILD_ID,
            'Independent attestation did not pass')
    require(att['run']['sha256'] == run_ref['sha256'] and att['run']['path'] == run_ref['path'], 'Attestation binds another run')
    require(run['host_or_sdk_or_window_executed'] is False and att['host_or_sdk_or_window_executed'] is False,
            'Native execution is outside this finish operation')
    report_ref = check(run['build_result'])
    report = base.read(Path(report_ref['path']))
    require(Path(report_ref['path']) == OUTPUT / 'build_result.json' and report['build_id'] == BUILD_ID,
            'Build report escaped the fixed output')
    require(len(run['commands']) == 7 and len(run['actual_objects']) == 5 and
            len(report['current_source_inputs']) == 592 and len(report['compiler_inputs']) == 549,
            'Actual build inventory differs')
    allowed_external_reads.update(key(row['path']) for row in report['current_source_inputs']
                                  if not inside(row['path'], PROJECT))
    hold_ref, _ = pinned(HOLD, HOLD_SHA)
    before_ref, progress = pinned(PROGRESS, PROGRESS_SHA)
    doc_ref = snapshot(DOC)
    require(doc_ref['sha256'] == DOC_SHA, 'Checkpoint documentation changed')
    doc_raw = DOC.read_bytes()
    old_paragraph = ('latest linked Host and private run 20261024T050152Z_fd0465b26387 predate these\n'
                     'five source changes. A new Host link and runtime verification are still needed.')
    doc_text = doc_raw.decode('utf-8').replace('\r\n', '\n')
    require(doc_text.count(old_paragraph) == 1, 'Expected documentation checkpoint is absent')
    require(progress['original_world_hud_stage']['current_host_linked_with_changes'] is False,
            'Progress was already updated')

    retirement = STAGE / 'retirement'
    publication = STAGE / 'publication'
    require(not retirement.exists() and not publication.exists(), 'Do not replay an existing finish operation')
    for root in (BUILD, OUTPUT, STAGE):
        require(inside(root, PROJECT), 'Output escaped the engine workspace')
        for ancestor in (root, *root.parents):
            require(not ancestor.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT, 'Reparse output path')

    units = report['final_compilation']['translation_units']
    names = ('host_main', 'window', 'renderer', 'world_renderer', 'terrain_renderer')
    stems = ('HostMain', 'BitmapWindow', 'BitmapRenderer', 'WorldViewRenderer', 'WorldTerrainRenderer')
    expected = [BUILD / f'final/tu_{i:02d}_{name}/obj/{stem}.obj'
                for i, (name, stem) in enumerate(zip(names, stems))]
    require([Path(row['object']['path']) for row in units] == expected and
            [row['object'] for row in units] == run['actual_objects'], 'Unexpected object targets')
    environment = BUILD / 'read_build_environment.cmd'
    require(Path(run['commands'][0]['command'][3]) == environment, 'Unexpected environment script target')
    targets = [check(row) for row in run['actual_objects']] + [snapshot(environment)]
    require(targets[-1]['bytes'] == 140 and
            targets[-1]['sha256'] == 'fbea552a6bb1afe675455702d2bcb52b666cb58115922a59f508f1cefc0e55bf',
            'The exact generated environment script changed')
    for row in targets:
        path = Path(row['path'])
        require(path in expected + [environment] and inside(path.resolve(strict=True), BUILD), 'Deletion escaped fixed build')
        require(row['link_count'] == 1 and not row['file_attributes'] & stat.FILE_ATTRIBUTE_READONLY,
                'An intermediate is shared or read-only')
        row['allocated_file_data_bytes'] = helper.allocation(path)

    retained = []
    seen = set()
    for row in [report['executable'], report['map'], *report['current_source_inputs'],
                *report['compiler_inputs'], *report['sources'], *report['provider_inputs'],
                *report['system_libraries'], *report['build_tools'], *report['implicit_libraries'],
                *report['provider_reports'].values(), report['ui_assets'], *run['retained_runtime_inputs']]:
        if key(row['path']) not in seen:
            retained.append(check(row)); seen.add(key(row['path']))
    retirement.mkdir()
    plan_path = retirement / 'plan.json'
    helper.write_new(plan_path, dict(schema='zerosis.original_world_hud.host_retirement_plan.v1',
        run=run_ref, independent_attestation=att_ref, build_result=report_ref, targets=targets,
        target_files=6, retained_path_count=len(retained), large_binary_backup_created=False,
        host_or_sdk_or_window_executed=False))
    plan_ref = snapshot(plan_path)
    for row in targets:
        check(row)
    for row in targets:
        path = Path(row['path'])
        check(row)
        require(helper.allocation(path) == row['allocated_file_data_bytes'], 'Allocation changed before unlink')
        path.unlink()
        require(not os.path.lexists(path), 'Intermediate still exists after unlink')
    removed_dirs = []
    for directory in [*(path.parent for path in expected), BUILD / 'tmp']:
        require(inside(directory.resolve(strict=True), BUILD) and
                not directory.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT,
                'Empty directory escaped the fixed build')
        require(not any(directory.iterdir()), 'An intermediate directory is not empty')
        directory.rmdir(); removed_dirs.append(str(directory))
    for row in retained:
        check(row)
    cleanup_path = retirement / 'result.json'
    helper.write_new(cleanup_path, dict(schema='zerosis.original_world_hud.host_retirement.v1',
        status='PASS_VERIFIED_CURRENT_WORLD_HUD_HOST_INTERMEDIATES_RETIRED', plan=plan_ref,
        run=run_ref, independent_attestation=att_ref, deleted_files=6, deleted_paths=[row['path'] for row in targets],
        deleted_empty_directories=len(removed_dirs), removed_directories=removed_dirs,
        retired_logical_bytes=sum(row['bytes'] for row in targets),
        retired_allocated_file_data_bytes=sum(row['allocated_file_data_bytes'] for row in targets),
        allocation_metric='Last-link FileStandardInfo.AllocationSize; excludes directory metadata and volume-free estimates',
        all_targets_absent=True, retained_inputs_rehashed=len(retained), executable=check(report['executable']),
        large_binary_backup_created=False, host_or_sdk_or_window_executed=False, full_engine_goal_complete=False))

    publication.mkdir()
    raw = PROGRESS.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == before_ref['sha256'], 'Progress changed before backup')
    backup = publication / 'current_progress.json.before.gz'
    with backup.open('xb') as stream:
        stream.write(gzip.compress(raw, mtime=0))
    require(gzip.decompress(backup.read_bytes()) == raw, 'Progress backup roundtrip failed')
    doc_backup = publication / 'ORIGINAL_WORLD_HUD.md.before.gz'
    check(doc_ref)
    with doc_backup.open('xb') as stream:
        stream.write(gzip.compress(doc_raw, mtime=0))
    require(gzip.decompress(doc_backup.read_bytes()) == doc_raw, 'Documentation backup roundtrip failed')
    helper.write_new(publication / 'pre_edit.json', dict(changed_metadata=[
        dict(before=before_ref, backup=snapshot(backup), gzip_roundtrip_verified=True),
        dict(before=doc_ref, backup=snapshot(doc_backup), gzip_roundtrip_verified=True)]))
    now = datetime.now(timezone.utc).isoformat()
    cleanup_ref = snapshot(cleanup_path)
    progress['previous_linked_candidate_compile_link_proof'] = progress['last_linked_candidate_compile_link_proof']
    progress['previous_linked_candidate_pe_attestation'] = progress['last_linked_candidate_pe_attestation']
    progress.update(status='CURRENT_WORLD_HUD_HOST_LINK_AND_STATIC_ATTESTATION_PASS_RUNTIME_PENDING',
        current_host_build_id=BUILD_ID, latest_source_matches_linked_candidate=True,
        last_linked_candidate_compile_link_proof=report_ref, last_linked_candidate_pe_attestation=att_ref,
        latest_actual_host_syntax_proof=att_ref,
        latest_host_source_matches_current_link_proof=True, latest_current_source_actual_cpp_compilation_verified=True,
        latest_cpp_source_matches_actual_host_syntax_proof=True,
        latest_actual_host_syntax_proof_scope='Five actual current Host units compiled and linked; native window behavior remains unverified.',
        prepared_runtime_matches_current_linked_candidate=False, prepared_runtime_matches_latest_source=False,
        latest_private_prepared_pair_matches_current_host_and_selected_sdk_sources=False,
        default_prepared_runtime_matches_latest_source=False, current_goal_turn_classification='progress',
        full_engine_goal_complete=False)
    stage = progress['original_world_hud_stage']
    stage.update(status='PASS_CURRENT_HOST_LINK_AND_STATIC_ATTESTATION_RUNTIME_PENDING', utc=now,
        current_host_linked_with_changes=True, latest_prepared_pair_contains_changes=False,
        current_host_build_id=BUILD_ID, current_host_build_result=report_ref, current_host_static_attestation=att_ref,
        current_host_executable=check(report['executable']), current_host_retirement=cleanup_ref,
        actual_windows_wheel_routing_verified=False, actual_gpu_terrain_viewport_verified=False,
        host_or_sdk_or_window_executed=False, physical_escape_hold_respected=True,
        full_original_ui_3d_campaign_verified=False, full_engine_goal_complete=False)
    for field in ('latest_host_sdk_preparation_stage', 'native_restore_pair_preparation_stage'):
        progress[field].update(status='PREPARED_PAIR_PREDATES_CURRENT_WORLD_HUD_HOST_NOT_EXECUTED',
            current_host_source_closure_matches_candidate=False, new_current_host_included=False,
            latest_private_pair_matches_current_selected_sources=False, current_world_hud_changes_included=False,
            newer_linked_host_not_materialized=BUILD_ID)
    progress['native_restore_contract_stage'].update(host_source_matches_current_tree=False,
        newer_host_preserves_unchanged_restore_contract=True, newer_host_static_attestation=att_ref)
    temporary = publication / 'current_progress.json.next'
    with temporary.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(progress, stream, indent=2, ensure_ascii=False); stream.write('\n')
    check(before_ref)
    os.replace(temporary, PROGRESS)
    new_paragraph = (f'new linked Host `{BUILD_ID}` includes these five source changes. All five\n'
        'translation units compiled, linked and passed independent static attestation.\n'
        'The private run `20261024T050152Z_fd0465b26387` still contains the older Host;\n'
        'it has not been rematerialized or executed with this change. Actual native\n'
        'wheel routing and GPU viewport behavior still need runtime verification.\n'
        'Build, attestation and intermediate-retirement receipts are retained under\n'
        '`evidence/original_world_hud/host_build/974a5be5753302c4498c/`.')
    doc_temporary = publication / 'ORIGINAL_WORLD_HUD.md.next'
    with doc_temporary.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(doc_text.replace(old_paragraph, new_paragraph))
    check(doc_ref)
    os.replace(doc_temporary, DOC)
    publication_path = publication / 'result.json'
    helper.write_new(publication_path, dict(schema='zerosis.original_world_hud.host_publication.v1',
        status='PASS_CURRENT_WORLD_HUD_HOST_PUBLISHED_WITHOUT_RUNTIME_PROMOTION', utc=now,
        run=run_ref, build_result=report_ref, independent_attestation=att_ref, retirement=cleanup_ref,
        changed_metadata=[dict(before=before_ref, backup=snapshot(backup), after=snapshot(PROGRESS), gzip_roundtrip_verified=True),
            dict(before=doc_ref, backup=snapshot(doc_backup), after=snapshot(DOC), gzip_roundtrip_verified=True)],
        old_prepared_pair_unchanged=True, old_prepared_pair_contains_new_host=False,
        physical_escape_hold=check(hold_ref), native_runtime_attempts=0,
        host_or_sdk_or_window_executed=False, full_engine_goal_complete=False))

    started_ref = check(report['started'])
    started = base.read(Path(started_ref['path']))
    check(started_ref)
    donors = started['frozen_donors']
    require(len(donors) == len({key(row['path']) for row in donors}) == 592, 'Donor identity inventory differs')
    donor_ids = {tuple(check(row)['file_identity']) for row in donors}
    paths = set()
    for root in (BUILD, OUTPUT, STAGE):
        for directory, children, files in os.walk(root, followlinks=False):
            for name in children:
                require(not (Path(directory) / name).lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT,
                        'Reparse directory in storage scope')
            paths.update(Path(directory) / name for name in files)
    paths.update((Path(__file__).absolute(), STAGE.parent / 'inputs.json',
        STAGE.parent / 'preflight_initial_path_case_failure.json',
        PROJECT / 'tools/build_original_world_hud_host.py', PROJECT / 'tools/verify_original_world_hud_host.py'))
    unique, new, aliases, link_counts = {}, {}, {}, {}
    logical = 0
    for path in sorted(paths):
        info = base.ordinary(path)
        identity = (info.st_dev, info.st_ino)
        logical += info.st_size
        aliases[identity] = aliases.get(identity, 0) + 1
        require(identity not in link_counts or link_counts[identity] == info.st_nlink, 'Link count changed within storage scan')
        link_counts[identity] = info.st_nlink
        if identity not in unique:
            unique[identity] = (info.st_size, helper.allocation(path))
    external_shared = set()
    for identity, amounts in unique.items():
        require(link_counts[identity] >= aliases[identity], 'Storage aliases exceed the actual link count')
        if identity not in donor_ids:
            if link_counts[identity] == aliases[identity]:
                new[identity] = amounts
            else:
                external_shared.add(identity)
    storage_path = STAGE / 'storage.json'
    helper.write_new(storage_path, dict(schema='zerosis.original_world_hud.host_storage.v1',
        scope='New build, build reports, fixed build tools/profile/finish receipts only; excludes pre-existing changed sources/metadata and project-wide totals',
        allocation_metric='FileStandardInfo.AllocationSize deduplicated by physical file identity; directory metadata excluded',
        observed_paths=len(paths), logical_path_bytes=logical, unique_file_ids=len(unique),
        reused_donor_file_ids_excluded=len(set(unique) & donor_ids),
        additional_external_shared_file_ids_excluded=len(external_shared),
        additional_external_shared_allocated_bytes_excluded=sum(unique[item][1] for item in external_shared),
        retained_new_unique_file_ids=len(new), retained_new_logical_bytes=sum(row[0] for row in new.values()),
        retained_new_allocated_file_data_bytes=sum(row[1] for row in new.values()),
        measurement_excludes_own_storage_and_final_audit_files=True, project_net_change_claimed=False))
    for row in [run_ref, att_ref, report_ref, hold_ref]:
        check(row)
    audit_path = STAGE / 'final_audit.json'
    helper.write_new(audit_path, dict(schema='zerosis.original_world_hud.host_finish_audit.v1',
        status='PASS_CURRENT_WORLD_HUD_HOST_BUILD_PUBLICATION_AND_CLEANUP_AUDIT', build_id=BUILD_ID,
        build_result=report_ref, run=run_ref, independent_attestation=att_ref,
        retirement=snapshot(cleanup_path), publication=snapshot(publication_path), storage=snapshot(storage_path),
        executable=check(report['executable']), current_source_inputs_rehashed=592,
        frozen_donor_metadata_preserved=True, current_source_matches_new_link=True,
        prepared_runtime_updated=False, native_runtime_attempts=0, physical_escape_hold=check(hold_ref),
        actual_windows_wheel_routing_verified=False, actual_gpu_terrain_viewport_verified=False,
        host_or_sdk_or_window_executed=False, original_game_or_user_state_accessed=False,
        default_runtime_or_mods_changed=False, full_engine_goal_complete=False))
    print(json.dumps(dict(status='PASS_CURRENT_WORLD_HUD_HOST_BUILD_PUBLICATION_AND_CLEANUP_AUDIT',
        build_id=BUILD_ID, final_audit=snapshot(audit_path),
        deleted_intermediate_files=6, retired_allocated_file_data_bytes=sum(row['allocated_file_data_bytes'] for row in targets),
        scoped_retained_new_allocated_file_data_bytes=sum(row[1] for row in new.values()),
        executable=check(report['executable']), native_runtime_attempts=0)))


if __name__ == '__main__':
    main()
