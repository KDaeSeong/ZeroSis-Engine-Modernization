"""Seal an already attested/cleaned latest candidate; never register or run it."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[3]
sys.path.insert(0, str(PROJECT / 'tools'))
import retained_host_runtime_input as retained
import retained_menu_suite_host_input as menu


def require(value, message):
    if not value:
        raise RuntimeError(message)


def artifact(path):
    path = Path(path).absolute()
    files = retained._Files(check_metadata=True)
    info = files.ordinary(path)
    with path.open('rb') as stream:
        sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    result = files.verify(dict(path=str(path), bytes=info.st_size, sha256=sha))
    files.finish()
    return result


def write_new(path, value):
    require(path.parent.is_relative_to(STAGE) and not path.exists(), 'Profile publication must be a fresh owned file')
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--build-id', required=True)
    cli.add_argument('--report-sha256', required=True)
    cli.add_argument('--attestation-sha256', required=True)
    cli.add_argument('--cleanup-plan-sha256', required=True)
    cli.add_argument('--cleanup-result-sha256', required=True)
    options = cli.parse_args()
    require(__debug__ and sys.dont_write_bytecode and re.fullmatch(r'\d{8}T\d{6}Z_[0-9a-f]{12}', options.build_id),
            'Use Python -B with the exact current candidate ID')
    directory = STAGE / options.build_id
    files = retained._Files(check_metadata=True)
    refs = {}
    for name, path, digest in (
        ('report', PROJECT / 'evidence/ui_window_host' / options.build_id / 'build_result.json', options.report_sha256),
        ('attestation', directory / 'independent_attestation.json', options.attestation_sha256),
        ('cleanup_plan', directory / 'cleanup_plan.json', options.cleanup_plan_sha256),
        ('cleanup_result', directory / 'cleanup_result.json', options.cleanup_result_sha256)):
        require(re.fullmatch('[0-9a-f]{64}', digest), 'Every reviewed candidate proof needs its exact SHA256')
        refs[name] = files.verify(dict(path=str(path), sha256=digest))
    build, att, plan, result = (files.json(refs[name]) for name in ('report', 'attestation', 'cleanup_plan', 'cleanup_result'))
    require(build.get('build_id') == options.build_id and build.get('status') == 'UI_WINDOW_HOST_CANDIDATE_BUILT' and
            att.get('status') == 'PASS_INDEPENDENT_CURRENT_MENU_SUITE_HOST_BYTES_AND_INPUTS' and
            menu.same(att['build_result'], refs['report']) and menu.same(att['image'], build['executable']) and
            att.get('host_or_sdk_or_dll_or_window_execution') is False,
            'Current candidate attestation is not bound to the successful report/image')
    # A preserved older frozen Host may still attest, but cannot be registered
    # as the latest candidate after a production-source correction.
    for row in build['current_source_inputs']:
        files.verify(row)
    frozen, current = menu.frozen_rows(build), menu.rows(build['current_source_inputs'])
    origins = {menu.key(row['origin']) for row in frozen.values()}
    for row in frozen.values():
        files.verify(row)
    run_ref = artifact(Path(build['started']['path']).with_name('run.json'))
    run = files.json(run_ref)
    require(run.get('build_id') == options.build_id and run.get('status') == 'PASS_CURRENT_MENU_SUITE_HOST_OFFLINE_BUILD_ONLY' and
            menu.same(run['build_result'], refs['report']) and
            result.get('build_id') == options.build_id and result.get('files_deleted') == 6 and
            result.get('all_candidates_absent') is True and result.get('current_image_unchanged') is True and
            result.get('plan_sha256') == refs['cleanup_plan']['sha256'] and
            result.get('protected_objects_or_sources_deleted') is False and result.get('runtime_default_or_saves_deleted') is False,
            'Candidate cleanup/run provenance differs from the reviewed exact-six action')
    units = build['final_compilation']['translation_units']
    require(len(units) == 5 and len(plan['candidates']) == 6, 'Candidate retirement must cover five objects and one build script')
    object_names = {menu.key(unit['object']['path']): unit['translation_unit'] for unit in units}
    retired = []
    for row in plan['candidates']:
        path = menu.key(row['path'])
        require(not os.path.lexists(row['path']), 'A supposedly retired candidate intermediate still exists')
        retired.append(dict(path=row['path'], bytes=row['bytes'], sha256=row['sha256'],
            role='FINAL_COFF_OBJECT' if path in object_names else 'BUILD_ENVIRONMENT_SCRIPT',
            translation_unit=object_names.get(path)))
    ledger = dict(schema='zerosis.menu_host.typed_retirement.v1', build_id=options.build_id,
        **refs, retired=retired, historical_only=True, missing_input_exception_scope='EXACT_TYPED_SIX_INTERMEDIATES', native_execution=False)
    temporary_spec = {}
    for name, row in refs.items():
        temporary_spec[name + '_path'] = str(Path(row['path']).relative_to(PROJECT))
        temporary_spec[name + '_sha256'] = row['sha256']
    temporary_spec['cleanup_status'] = result['status']
    menu._retirement(build, PROJECT, temporary_spec,
        dict(retirement_ledger=ledger, cleanup_plan=plan, cleanup_result=result), files)
    image = files.verify(build['executable'])
    files.finish()
    ledger_path = directory / 'typed_retirement.json'
    audit_path = directory / 'final_audit.json'
    profile_path = directory / 'registered_profile.json'
    require(not any(path.exists() for path in (ledger_path, audit_path, profile_path)),
            'Inspect an existing profile publication instead of replacing it')
    write_new(ledger_path, ledger)
    refs['retirement_ledger'] = artifact(ledger_path)
    audit = dict(schema='zerosis.menu_suite_host.final_audit.v1',
        status='PASS_CURRENT_MENU_SUITE_HOST_ATTESTED_AND_INTERMEDIATES_RETIRED_NOT_EXECUTED',
        build_id=options.build_id, build_result=refs['report'], executable=image,
        independent_static_attestation=refs['attestation'], cleanup=refs['cleanup_result'],
        typed_retirement=refs['retirement_ledger'], original_Host_SDK_game_window_or_GPU_execution=False,
        current_native_or_screen_relaunch_allowed=False, screen_verification_deferred=True,
        default_promoted=False, full_engine_goal_complete=False)
    write_new(audit_path, audit)
    refs['audit'], refs['run'] = artifact(audit_path), run_ref
    profile = dict(schema='zerosis.retained_menu_host.profile.v1', kind='retained_menu_suite', build_id=options.build_id,
        executable_bytes=image['bytes'], executable_sha256=image['sha256'], catalog=att['catalog'],
        required_payloads=['ZeroSisUiScene','ExitConfirm','ExitConfirmLayout','TouchControlsMenu','SaveMapMenu',
                           'MenuOptionsLayout','TouchHelpLayout','MapMenuLayout'],
        compiler_dependency_count=att['compiler_input_count'], current_source_count=att['current_input_count'],
        source_manifest_count=att['source_manifest_count'], materialized_input_count=att['frozen_input_count'],
        donor_hardlinks=att['hardlinked_files'], private_source_copies=att['private_copies'],
        dependency_counts=att['actual_tu_dependency_counts'], import_count=len(att['imports']),
        nonfrozen_current_inputs=[str(Path(row['path']).relative_to(PROJECT)) if Path(row['path']).is_relative_to(PROJECT)
                                  else row['path'] for path, row in current.items() if path not in origins],
        attestation_schema=att['schema'], attestation_status=att['status'], run_schema=run['schema'], run_status=run['status'],
        audit_schema=audit['schema'], audit_status=audit['status'], cleanup_status=result['status'])
    for name, row in refs.items():
        profile[name + '_path'] = str(Path(row['path']).relative_to(PROJECT))
        profile[name + '_sha256'] = row['sha256']
    write_new(profile_path, profile)
    print(json.dumps(dict(status='SEALED_CURRENT_PROFILE_NOT_REGISTERED_OR_MATERIALIZED', build_id=options.build_id,
        profile=artifact(profile_path), typed_retirement=refs['retirement_ledger'], audit=refs['audit'],
        registry_key=str(profile_path.relative_to(STAGE)), native_execution=False)))


if __name__ == '__main__':
    main()
