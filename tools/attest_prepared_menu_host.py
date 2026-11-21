"""File-only attestation, exact intermediate cleanup, and explicit pair profile.

This does not change the globally selected Host and cannot launch a runtime.
The old attestor and cleanup implementations are reused at exact byte pins.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys

PROJECT = Path(__file__).absolute().parents[1]
STAGE = PROJECT / 'evidence/world_terrain_original/phase12/pair_preparation'
sys.path.insert(0, str(PROJECT / 'tools'))
import retained_host_runtime_input as retained
import retained_menu_suite_host_input as menu


def require(value, message):
    if not value:
        raise RuntimeError(message)


def load(relative, digest, name):
    path = PROJECT / relative
    require(hashlib.sha256(path.read_bytes()).hexdigest() == digest, 'Reviewed file-only helper changed')
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def artifact(path):
    path = Path(path).absolute()
    files = retained._Files(check_metadata=True)
    result = files.verify(dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    files.finish()
    return result


def write_new(path, value):
    require(path.is_relative_to(STAGE) and not os.path.lexists(path), 'Proof must be a fresh owned leaf')
    with path.open('x', encoding='utf8') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def seal(args):
    files = retained._Files(check_metadata=True)
    report_ref = files.verify(dict(path=str(args.build_report.absolute()), sha256=args.report_sha256))
    build = files.json(report_ref)
    identifier = build['build_id']
    directory = STAGE / identifier
    require(re.fullmatch(r'\d{8}T\d{6}Z_[0-9a-f]{12}', identifier) and
            Path(report_ref['path']) == PROJECT / 'evidence/ui_window_host' / identifier / 'build_result.json',
            'Report escaped its exact current Host role')
    require(build['menu_suite_builder']['sha256'] == args.builder_sha256 and
            artifact(PROJECT / 'tools/build_menu_suite_host.py')['sha256'] == args.builder_sha256,
            'Current successful builder differs')
    refs = dict(report=report_ref)
    for name in ('attestation', 'cleanup_plan', 'cleanup_result'):
        leaf = {'attestation': 'independent_attestation.json'}.get(name, name + '.json')
        digest = getattr(args, name + '_sha256')
        require(re.fullmatch('[0-9a-f]{64}', digest or ''), 'Every completed proof needs an explicit SHA256')
        refs[name] = files.verify(dict(path=str(directory / leaf), sha256=digest))
    att, plan, result = (files.json(refs[name]) for name in ('attestation', 'cleanup_plan', 'cleanup_result'))
    require(build['status'] == 'UI_WINDOW_HOST_CANDIDATE_BUILT' and
            att['status'] == 'PASS_INDEPENDENT_CURRENT_MENU_SUITE_HOST_BYTES_AND_INPUTS' and
            menu.same(att['build_result'], report_ref) and menu.same(att['image'], build['executable']) and
            att['host_or_sdk_or_dll_or_window_execution'] is False and
            att['full_native_or_original_ui_acceptance'] is False,
            'Successful actual Host attestation differs')
    for row in build['current_source_inputs']:
        files.verify(row)
    frozen, current = menu.frozen_rows(build), menu.rows(build['current_source_inputs'])
    for row in frozen.values():
        files.verify(row)
    refs['run'] = artifact(Path(build['started']['path']).with_name('run.json'))
    run = files.json(refs['run'])
    require(run['build_id'] == result['build_id'] == identifier and
            run['status'] == 'PASS_CURRENT_MENU_SUITE_HOST_OFFLINE_BUILD_ONLY' and
            menu.same(run['build_result'], report_ref) and run['host_sdk_clr_window_gpu_or_dll_executed'] is False and
            result['files_deleted'] == 6 and result['all_candidates_absent'] is True and
            result['current_image_unchanged'] is True and result['plan_sha256'] == refs['cleanup_plan']['sha256'] and
            result['protected_objects_or_sources_deleted'] is False and result['runtime_default_or_saves_deleted'] is False,
            'Exact six-intermediate cleanup is not bound to this successful compile')
    units = build['final_compilation']['translation_units']
    require(len(units) == 5 and len(plan['candidates']) == 6, 'Only five COFF objects and the environment script may retire')
    objects = {menu.key(unit['object']['path']): unit['translation_unit'] for unit in units}
    retired = []
    for row in plan['candidates']:
        require(not os.path.lexists(row['path']), 'Retired intermediate still exists')
        key = menu.key(row['path'])
        retired.append(dict(path=row['path'], bytes=row['bytes'], sha256=row['sha256'],
            role='FINAL_COFF_OBJECT' if key in objects else 'BUILD_ENVIRONMENT_SCRIPT', translation_unit=objects.get(key)))
    ledger = dict(schema='zerosis.menu_host.typed_retirement.v1', build_id=identifier,
        **{name: refs[name] for name in ('report', 'attestation', 'cleanup_plan', 'cleanup_result')}, retired=retired,
        historical_only=True, missing_input_exception_scope='EXACT_TYPED_SIX_INTERMEDIATES', native_execution=False)
    temporary_spec = dict(cleanup_status=result['status'])
    for name in ('report', 'attestation', 'cleanup_plan', 'cleanup_result'):
        temporary_spec[name + '_path'] = str(Path(refs[name]['path']).relative_to(PROJECT))
        temporary_spec[name + '_sha256'] = refs[name]['sha256']
    menu._retirement(build, PROJECT, temporary_spec,
        dict(retirement_ledger=ledger, cleanup_plan=plan, cleanup_result=result), files)
    require(args.sidecar and re.fullmatch('[0-9a-f]{64}', args.sidecar_sha256 or ''), 'Required sidecar proof needs an explicit SHA256')
    sidecar_ref = files.verify(dict(path=str(args.sidecar.absolute()), sha256=args.sidecar_sha256))
    sidecar = files.json(sidecar_ref)
    require(sidecar['build_id'] == identifier and menu.same(sidecar['build_report'], report_ref) and
            sidecar['host_or_sdk_or_window_executed'] is False and
            sidecar['additional_unique_payload_bytes'] == 0, 'Sidecar receipt is not this Host image')
    descriptor = sidecar['required_sidecar']
    sidecar_check = menu.validate_required_sidecars(PROJECT, identifier, descriptor, files)
    image = files.verify(build['executable'])
    files.finish()
    write_new(directory / 'typed_retirement.json', ledger)
    refs['retirement_ledger'] = artifact(directory / 'typed_retirement.json')
    audit = dict(schema='zerosis.menu_suite_host.final_audit.v1',
        status='PASS_CURRENT_MENU_SUITE_HOST_ATTESTED_AND_INTERMEDIATES_RETIRED_NOT_EXECUTED',
        build_id=identifier, build_result=refs['report'], executable=image,
        independent_static_attestation=refs['attestation'], cleanup=refs['cleanup_result'],
        typed_retirement=refs['retirement_ledger'], required_sidecar_receipt=sidecar_ref,
        required_sidecar_validation=sidecar_check, original_Host_SDK_game_window_or_GPU_execution=False,
        current_native_or_screen_relaunch_allowed=False, screen_verification_deferred=True,
        default_promoted=False, globally_registered=False, full_engine_goal_complete=False)
    write_new(directory / 'final_audit.json', audit)
    refs['audit'] = artifact(directory / 'final_audit.json')
    origins = {menu.key(row['origin']) for row in frozen.values()}
    profile = dict(schema='zerosis.retained_menu_host.profile.v1', kind='retained_menu_suite', build_id=identifier,
        executable_bytes=image['bytes'], executable_sha256=image['sha256'], catalog=att['catalog'],
        required_payloads=['ZeroSisUiScene', 'ExitConfirm', 'ExitConfirmLayout', 'TouchControlsMenu', 'SaveMapMenu',
                           'MenuOptionsLayout', 'TouchHelpLayout', 'MapMenuLayout'],
        compiler_dependency_count=att['compiler_input_count'], current_source_count=att['current_input_count'],
        source_manifest_count=att['source_manifest_count'], materialized_input_count=att['frozen_input_count'],
        donor_hardlinks=att['hardlinked_files'], private_source_copies=att['private_copies'],
        dependency_counts=att['actual_tu_dependency_counts'], import_count=len(att['imports']),
        nonfrozen_current_inputs=[str(Path(row['path']).relative_to(PROJECT)) if Path(row['path']).is_relative_to(PROJECT)
                                 else row['path'] for key, row in current.items() if key not in origins],
        attestation_schema=att['schema'], attestation_status=att['status'], run_schema=run['schema'], run_status=run['status'],
        audit_schema=audit['schema'], audit_status=audit['status'], cleanup_status=result['status'],
        required_sidecar=descriptor, prepared_profile_only=True, globally_registered=False, native_execution=False)
    for name, row in refs.items():
        profile[name + '_path'] = str(Path(row['path']).relative_to(PROJECT))
        profile[name + '_sha256'] = row['sha256']
    write_new(directory / 'prepared_profile.json', profile)
    print(json.dumps(dict(status='PASS_EXPLICIT_PREPARED_PROFILE_SEALED_NOT_REGISTERED_OR_EXECUTED',
        build_id=identifier, profile=artifact(directory / 'prepared_profile.json'), sidecar_files=sidecar_check['file_count'])))


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('operation', choices=('attest', 'tidy', 'seal'))
    cli.add_argument('--build-report', type=Path)
    cli.add_argument('--report-sha256')
    cli.add_argument('--builder-sha256')
    cli.add_argument('--plan', type=Path)
    cli.add_argument('--plan-sha256')
    for name in ('attestation', 'cleanup-plan', 'cleanup-result'):
        cli.add_argument('--' + name + '-sha256')
    cli.add_argument('--sidecar', type=Path)
    cli.add_argument('--sidecar-sha256')
    args = cli.parse_args()
    require(sys.dont_write_bytecode and __debug__, 'Use Python -B without optimization')
    if args.operation == 'attest':
        require(re.fullmatch('[0-9a-f]{64}', args.builder_sha256 or ''), 'Exact builder SHA256 required')
        module = load('evidence/game_menu/offline_menu_suite/pair_preparation/attest_current_candidate.py',
            'ebe5a2a7d259d91c7a15f61cafe3902aace4c03c6cc37aaf7a38eb2eeda0ebc3', '_prepared_menu_attestor')
        module.STAGE = STAGE
        module.BUILDER_SHA = args.builder_sha256
        STAGE.mkdir(parents=True, exist_ok=True)
        sys.argv = [sys.argv[0], '--build-report', str(args.build_report), '--report-sha256', str(args.report_sha256)]
        module.main()
    elif args.operation == 'tidy':
        module = load('tools/tidy_menu_suite_intermediates.py',
            '5d9335cbc62f2d18710ec85ae493461dd87a0badd62835908fb448ba5a0dd4ca', '_prepared_menu_tidy')
        module.audit.STAGE = STAGE.parent
        sys.argv = [sys.argv[0], '--plan', str(args.plan), '--sha256', str(args.plan_sha256)]
        module.main()
    else:
        seal(args)


if __name__ == '__main__':
    main()
