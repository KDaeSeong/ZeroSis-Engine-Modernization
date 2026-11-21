"""Adopt one complete, unexecuted runtime after its metadata scope false positive."""
from __future__ import annotations
import gzip
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

PROJECT = Path(__file__).absolute().parents[4]
sys.dont_write_bytecode = True
sys.path.insert(0, str(PROJECT / 'tools'))
import prepare_latest_engine_pair as pair
import prepare_current_sdk_play as base
import retained_host_runtime_input as retained

RUN_ID = '20261101T080450Z_424fb64608b2'
HOST_ID = '20261101T074006Z_c2fd2fe9be38'
ROOT = Path(__file__).absolute().parent
CREATION = ROOT / 'materialization_retry03'
STAGE = ROOT / 'materialization_retry03_adoption_retry02'
RUNTIME = PROJECT / 'Build/InteractiveGameRuntime' / RUN_ID
EVIDENCE = PROJECT / 'evidence/interactive_game' / RUN_ID
REQUEST = EVIDENCE / 'request.json'
BACKUP = ROOT / 'source_backups/prepare_latest_engine_pair.before_external_source_recheck.gz'


class FileOnlyGuard:
    def __init__(self):
        self.native_attempts = 0
        self.denied = []

    def audit(self, event, args):
        native = (event == 'subprocess.Popen' or event == 'os.system' or
                  event.startswith(('os.exec', 'os.spawn', 'socket.')) or event == 'ctypes.dlopen')
        if native:
            self.native_attempts += 1
            self.denied.append(event)
            raise RuntimeError('File-only adoption prohibits execution/network/native library loading: ' + event)
        target = None
        if event == 'open':
            mode = args[1] if len(args) > 1 else ''
            flags = args[2] if len(args) > 2 else 0
            if (isinstance(mode, str) and any(c in mode for c in 'wax+')) or (
                    isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC)):
                target = args[0]
        elif event == 'os.mkdir':
            target = args[0]
        elif event in ('os.remove', 'os.rmdir', 'os.rename', 'os.chmod', 'os.utime', 'os.truncate'):
            self.denied.append(event)
            raise RuntimeError('Adoption may not mutate existing payloads: ' + event)
        if target is not None and (not isinstance(target, (str, bytes, os.PathLike)) or
                                   not base.within(target, STAGE)):
            self.denied.append(event)
            raise RuntimeError('Adoption writes escaped its new evidence stage')


def checked(row):
    return base.checked(row)


def source_annotation(row):
    base.require(set(row) == {'original_path', 'sha256', 'bytes'}, 'Unexpected source annotation schema')
    return checked(dict(path=row['original_path'], sha256=row['sha256'], bytes=row['bytes']))


def inventory(root):
    rows = []
    for path in sorted(root.rglob('*')):
        info = path.lstat()
        base.require(not stat.S_ISLNK(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & base.REPARSE,
                     'Adopted runtime contains a reparse point')
        if stat.S_ISREG(info.st_mode):
            rows.append(dict(base.artifact(path), file_identity=[info.st_dev, info.st_ino],
                             file_attributes=getattr(info, 'st_file_attributes', 0), links=info.st_nlink))
    return rows


def run(guard):
    failure_ref, started_ref = base.artifact(CREATION / 'failure.json'), base.artifact(CREATION / 'started.json')
    failure, started = base.read(failure_ref['path']), base.read(started_ref['path'])
    base.require(failure == dict(status='FAILED_PREPARATION_ONLY',
        error='RuntimeError: Input escaped the engine project', run_id=RUN_ID,
        failed_phase='POST_MATERIALIZATION_VALIDATION', denied=[], native_attempts=0),
        'Only the exact protected-input scope failure may be adopted')
    base.require(started['host_build_id'] == HOST_ID and started['native_execution_allowed'] is False and
                 started['default_promotion_allowed'] is False and '--smoke' not in started['runner_argv'],
                 'Creation was not the exact preparation-only operation')
    creation_log = (CREATION / 'stdout.log').read_text(encoding='utf8')
    summaries = [json.loads(line) for line in creation_log.splitlines() if line.startswith('{')]
    base.require(len(summaries) == 1 and summaries[0]['status'] == 'PRIVATE_CONTINUOUS_GAME_PREPARED' and
                 summaries[0]['run_id'] == RUN_ID and base.key(summaries[0]['request']) == base.key(REQUEST),
                 'Creator never completed this private runtime')
    request_ref = base.artifact(REQUEST)
    request = base.read(REQUEST)
    original = base.read(checked(dict(path=str(PROJECT / f'evidence/interactive_game/{pair.SOURCE_RUN}/request.json'),
                                     sha256=pair.SOURCE_REQUEST_SHA))['path'])
    spec = retained.registered_host_spec(HOST_ID)
    base.require(retained.MENU_SUITE_BUILD_ID == HOST_ID and spec['build_id'] == HOST_ID,
                 'Adoption must use the registered latest Host')
    checked(started['host']); checked(started['sdk']); checked(started['source_request'])
    host = base.read(started['host']['path'])
    gate = retained.validate_retained_host_runtime(host, PROJECT)
    source_closure = retained.check_current_menu_host_sources(host, PROJECT)
    base.require(source_closure['source_count'] == 636 and gate['static_catalog_payloads'] == 74,
                 'Adoption lost its current source or embedded payload closure')

    # The original creator is retained byte-for-byte. Only its later local-only
    # metadata rechecker is revised; no new creator or materialization is claimed.
    adapter_path = PROJECT / 'tools/prepare_latest_engine_pair.py'
    creator = [row for row in started['protected_inputs'] if base.key(row['path']) == base.key(adapter_path)]
    base.require(len(creator) == 1, 'Creator adapter pin is not unique')
    recovery = gzip.decompress(BACKUP.read_bytes())
    base.require(hashlib.sha256(recovery).hexdigest() == creator[0]['sha256'] and
                 len(recovery) == creator[0]['bytes'], 'Historical creator recovery differs')
    current_adapter = base.artifact(adapter_path)
    protected = [current_adapter if base.key(row['path']) == base.key(adapter_path) else row
                 for row in started['protected_inputs']]
    final_closure = pair.recheck_protected_inputs(protected, host, source_closure)
    outside = [row for row in final_closure['verified_inputs'] if not base.within(row['path'], PROJECT)]
    base.require(len(outside) == 339, 'The sealed external read-only toolchain set changed')

    current, prior = {}, {Path(row['path']).name: row for row in original['runtime_inputs']}
    for row in request['runtime_inputs']:
        name = Path(row['path']).name
        base.require(name.casefold() not in {n.casefold() for n in current} and
                     base.key(row['path']) == base.key(RUNTIME / name), 'Runtime basename collision or path escape')
        current[name] = checked(row)
    base.require(len(current) == len(prior) == 24 and set(current) == set(prior) and
                 {'terrain-assets.bin', 'unit-assets.bin'} <= current.keys(), 'The exact 24 payloads are required')
    changes = sorted(name for name in current if current[name]['sha256'] != prior[name]['sha256'])
    base.require(changes == ['CvGameCoreDLL_Expansion2_x64.dll', 'ZeroSisHost_x64.exe', 'bundle.manifest'] and
                 current['ZeroSisHost_x64.exe']['sha256'] == spec['executable_sha256'] and
                 current['CvGameCoreDLL_Expansion2_x64.dll']['sha256'] == pair.SDK_SHA,
                 'Adoption changed the accepted Host/SDK pair or another payload')
    expected_manifest = 'ZEROSIS_HOST_BUNDLE_V4\n' + ''.join(
        Path(row['path']).name + '|' + row['sha256'] + '\n' for row in request['runtime_inputs']
        if Path(row['path']).name != 'bundle.manifest')
    base.require((RUNTIME / 'bundle.manifest').read_text(encoding='ascii') == expected_manifest,
                 'Bundle identity is not the exact payload hash sequence')
    base.require(request['run_id'] == RUN_ID and request['smoke'] is False and request['resume_from'] is None and
                 request['ui_support_from_run'] is None and request['stage_or_mods_changed'] is False and
                 request['input_profile'] == 'MANUAL_CONTINUOUS_GAME_LOOP' and request['language'] == 'ko_KR' and
                 all(request[name] is True for name in ('top_panel', 'action_info_panel', 'notification_panel')),
                 'Adopted request is not the fixed unexecuted new-game profile')
    scope = request['runtime_sdk_candidate_scope']
    base.require(scope['status'] == 'PREPARED_NOT_EXECUTED' and scope['new_game_only'] is True and
                 all(scope[name] is False for name in ('host_sdk_execution_verified', 'retail_save_restore_verified',
                     'prior_bundle_save_migration_performed', 'default_release_changed')), 'Candidate execution scope changed')
    for ref in request['provenance'].values():
        checked(ref)
    base.require(request['provenance']['host_build']['sha256'] == spec['report_sha256'], 'Frozen Host report differs')
    registration = request['menu_host_preparation_scope']['frozen_host_registration']
    actual_profile = retained._menu_suite_helper().registration_reference(HOST_ID)
    base.require(registration['retained_menu_suite_host_profile']['sha256'] == actual_profile['sha256'] and
                 registration['retained_menu_suite_host_input']['sha256'] == spec['helper_sha256'],
                 'Frozen registration is not authenticated by the current dispatcher')

    support = request['interactive_ui_support_inventory']
    support_audit = pair.audit_python_support_closure(RUNTIME / 'interactive_ui_support/tools', support['tools'])
    base.require(support_audit['module_count'] == 6 and support_audit == request['frozen_python_support_import_closure'],
                 'The frozen Python sibling import closure changed')
    expected_files = {base.key(row['path']) for row in current.values()}
    for rows in support['tools'].values():
        base.require(source_annotation(rows['source'])['sha256'] == checked(rows['frozen'])['sha256'], 'Frozen backend differs from source')
        expected_files.add(base.key(rows['frozen']['path']))
    for name in ('inline_icons', 'asset_preparation_provenance'):
        rows = support[name]
        base.require(source_annotation(rows['source'])['sha256'] == checked(rows['frozen'])['sha256'], 'Frozen support asset differs')
        expected_files.add(base.key(rows['frozen']['path']))
    checked(support['frozen_support_manifest'])
    expected_files.add(base.key(support['frozen_support_manifest']['path']))
    checked(request['interactive_ui_support'])
    data_bindings = pair.audit_menu_data_bindings(base.read(support['asset_preparation_provenance']['frozen']['path']))
    base.require(data_bindings == request['private_menu_data_bindings'], 'Private menu/font data bindings changed')
    control = request['launcher_control_metadata']
    for name, ref in control.items():
        if name == 'python':
            prior_python = original['launcher_control_metadata']['python']
            base.require(ref == prior_python and base.key(ref['path']) == base.key(sys.executable),
                         'Launcher Python escaped the exact retained interpreter pin')
            files = retained._Files(); files.verify(ref); files.finish()
        else:
            checked(ref)
    for field, filename in (('launcher', 'Play.ps1'), ('resume_launcher', 'Resume.ps1')):
        checked(request[field])
        base.require(base.key(request[field]['path']) == base.key(RUNTIME / filename), 'Launcher escaped runtime')
        expected_files.add(base.key(request[field]['path']))
    resume = (RUNTIME / 'Resume.ps1').read_text(encoding='utf-8-sig')
    play = (RUNTIME / 'Play.ps1').read_text(encoding='utf-8-sig')
    base.require("throw 'Save loading is disabled" in resume and not any(
        token in resume for token in ('play-load', 'ShowDialog', '$Checkpoint')), 'Save loading was enabled')
    base.require(RUN_ID in play and "--host (Join-Path $PSScriptRoot 'ZeroSisHost_x64.exe')" in play and
                 '--cwd $PSScriptRoot --runtime $PSScriptRoot' in play and
                 'interactive_ui_support' in play and str(PROJECT / 'tools') not in play and '--smoke' not in play,
                 'Play launcher lost its exact private Host/support path contract')
    links, private = [], []
    for row in request['materializations']:
        target = Path(row['target']); info = base.ordinary(target)
        base.require(target.parent == RUNTIME and target.name in current, 'Materialization escaped runtime')
        if row['materialization_method'] == 'hardlink':
            cache = Path(row['cache']); cache_info = base.ordinary(cache)
            base.require(cache == PROJECT / 'Build/RuntimeInputCache' / row['sha256'][:2] / row['sha256'] and
                         (info.st_dev, info.st_ino) == (cache_info.st_dev, cache_info.st_ino) and
                         getattr(info, 'st_file_attributes', 0) & base.READONLY and
                         checked(dict(path=str(cache), sha256=row['sha256']))['sha256'] == current[target.name]['sha256'],
                         'Immutable cache alias or read-only attribute differs')
            links.append(dict(target=str(target), cache=str(cache), file_identity=[info.st_dev, info.st_ino]))
        else:
            base.require(row['materialization_method'] == 'private-copy' and target.name in ('rules.db', 'localization.db') and
                         info.st_nlink == 1 and (info.st_dev, info.st_ino) !=
                         tuple(getattr(base.ordinary(prior[target.name]['path']), attr) for attr in ('st_dev', 'st_ino')),
                         'Mutable databases must retain independent private identities')
            private.append(str(target))
    base.require(len(links) == 15 and len(private) == 2, 'Exact immutable/private materialization roles differ')
    base.require((not (RUNTIME / 'sessions').exists() or
                  ((RUNTIME / 'sessions').is_dir() and not any((RUNTIME / 'sessions').iterdir()))) and
                 not any((EVIDENCE / name).exists() for name in ('attempt.json', 'driver_result.json', 'stdout.log', 'stderr.log')),
                 'The prepared runtime contains a native attempt or generated session')
    physical = inventory(RUNTIME)
    base.require(len(physical) == 35 and {base.key(row['path']) for row in physical} == expected_files,
                 'Physical runtime has missing, duplicate or extra files')
    checked(request_ref)
    base.require(pair.recheck_protected_inputs(protected, host, final_closure) == final_closure and
                 not guard.denied and guard.native_attempts == 0, 'Adoption changed source or crossed native hold')
    adoption = dict(creation_attempt=started_ref, creation_failure=failure_ref,
        creator_adapter=creator[0], creator_adapter_recovery=base.artifact(BACKUP),
        current_metadata_rechecker=current_adapter, adoption_tool=base.artifact(Path(__file__).absolute()),
        former_false_positive='Project-only rechecker rejected 339 sealed, read-only external compiler headers.',
        original_creation_provenance_preserved=True, request_and_payloads_rewritten=False,
        materialization_replayed=False, new_runtime_files_created=0, original_failure_retained=True)
    result = dict(schema='zerosis.latest_pair.prepared.v1',
        status='PASS_CURRENT_HOST_AND_GREAT_WORK_SDK_PREPARED_NOT_EXECUTED', request=request_ref, run_id=RUN_ID,
        host=current['ZeroSisHost_x64.exe'], gamecore=current['CvGameCoreDLL_Expansion2_x64.dll'], host_build_id=HOST_ID,
        bundle_manifest=current['bundle.manifest'], changed_backend_inputs=changes, runtime_input_count=24,
        immutable_links=15, private_database_copies=2, physical_runtime_files=35, cache_created=[],
        protected_inputs_unchanged=len(protected)-1, protected_inputs_checked=len(protected), operational_revision_count=1,
        actual_menu_source_closure_rechecked=True, final_current_source_count=636,
        frozen_menu_registration=registration, frozen_python_support_import_closure=support_audit,
        guard_denials=[], native_attempts=0, new_game_only=True, host_or_sdk_executed=False, default_promoted=False,
        save_compatibility_verified=False, prior_bundle_migrated=False, original_ui_accepted=False,
        full_engine_goal_complete=False, adopted_unexecuted_preparation=True, adoption=adoption)
    base.write_new(STAGE / 'result.json', result)
    audit = dict(schema='zerosis.menu_suite_pair.final_preparation_audit.v1',
        status='PASS_EXACT_CURRENT_MENU_PAIR_PREPARED_NOT_EXECUTED', run_id=RUN_ID,
        request=request_ref, preparation_result=base.artifact(STAGE / 'result.json'),
        current_source_closure=final_closure, external_toolchain_originals_rechecked=len(outside),
        retained_host_gate=gate, runtime_input_count=24, physical_runtime_file_count=35,
        runtime_files=physical, immutable_cache_links=links, private_databases=private,
        bundle_manifest_sequence_verified=True, mandatory_terrain_and_units_present=True,
        frozen_python_support_import_closure=support_audit, private_menu_data_bindings=data_bindings,
        launchers_verified=True, save_loading_disabled=True, sessions_empty=True, driver_outputs_absent=True,
        native_attempts=0, guard_denials=[], native_execution=False, host_or_sdk_executed=False,
        new_game_only=True, default_promoted=False, source_and_request_unchanged=True, adoption=adoption)
    base.write_new(STAGE / 'final_prepared_pair_audit.json', audit)
    print(json.dumps(dict(status=result['status'], run_id=RUN_ID, result=str(STAGE / 'result.json'),
                         audit=str(STAGE / 'final_prepared_pair_audit.json'), native_attempts=0)))


def main():
    base.require(not sys.flags.optimize and not STAGE.exists(), 'One-use adoption stage already exists or optimization enabled')
    guard = FileOnlyGuard()
    sys.addaudithook(guard.audit)
    STAGE.mkdir(exist_ok=False)
    base.write_new(STAGE / 'started.json', dict(run_id=RUN_ID, creation_attempt=str(CREATION),
        request=base.artifact(REQUEST), tool=base.artifact(Path(__file__).absolute()),
        native_execution_allowed=False, new_materialization_allowed=False, runtime_writes_allowed=False))
    try:
        run(guard)
    except BaseException as error:
        base.write_new(STAGE / 'failure.json', dict(status='FAILED_FILE_ONLY_ADOPTION',
            error=type(error).__name__ + ': ' + str(error), native_attempts=guard.native_attempts, denied=guard.denied))
        raise
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
