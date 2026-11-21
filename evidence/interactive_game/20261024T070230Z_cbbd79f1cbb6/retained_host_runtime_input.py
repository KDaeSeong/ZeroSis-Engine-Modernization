"""Read-only runtime input gate for the attested Host after object retirement.

This accepts registered published builds, not arbitrary missing linker inputs. Five
objects are historical only after the exact attestation and retirement receipt;
two documentation identities are verified from their publication backups.
Executable sources, libraries, dependencies and the retained PE remain required.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
from pathlib import Path
import stat
import types


BUILD_ID = '20261024T021245Z_18bbd0dd26e7'
REPORT_SHA = '26edcf537984d5bf6cc74be3a908dcec92fda946ba03a2e5188fb32a22fbf5f2'
AUDIT_SHA = '633586ca57bbf9343113e364e8b35bea8c16934e01a99719c065bdd9c0222aba'
UPDATE_SHA = '5a8250cf26f4d5bb0a595677eac5970c60fdd3b42d93a9558f46963dfe95dc1d'
RESTORE_BUILD_ID = '20261024T042219Z_e6399c82ee5c'
RESTORE_REPORT_SHA = '8746bbe6614cc206e6fa87a1fb62b0f636a160e2dcb76e0a15214aad93d09300'
RESTORE_EXECUTABLE_SHA = '2212f0e59812b68330990e4b0c0c974ad3baba78727f15fbd701b2a1b7d24da8'
RESTORE_ATTESTATION_SHA = '87a0ef71a309ef0151eaf005b4b7d7a2475496b4cdfbc41eda316a2ca31a3198'
RESTORE_RETIREMENT_SHA = '0d2902ac9cc8b135b630b63b49835fb8301cc07ffc761daa3cd279fb93389597'
RESTORE_PLAN_SHA = 'cee80bc05c19c733824e21464c3c3282c7fac82b3de65d27970d9fb22ef5bad4'
RESTORE_UPDATE_SHA = 'bd734dcf34bd471c9a3d7f9c626d2ebeadbcc35c39438307008ef6f474aec859'
RESTORE_AUDIT_SHA = 'edbb1e90f4b66e8a1d56f5848a5c8702a4138a9ec390abdfd791c89faca6ef5d'
RESTORE_PRE_EDIT_SHA = '435543ec412350b744805bfe251854c00b807a2a52664c4bb9272a0ddd172605'
RESTORE_STAGE = 'evidence/native_restore_contract/host_build/e6399c82ee5c15c73b86'
RESTORE_OPERATIONAL_BEFORE = {
    'tools/run_interactive_game.py': (247217, 'f79fc7513ddf1ce04c6c12416c7b633940345e1f2b9bba2bb6bf3f3f95cbe10d'),
    'tools/retained_host_runtime_input.py': (10097, '3bf6e8deb533a39e8a2d25f0cf3913d5d2f0dca866d969e3046d0c558bb41cc2'),
    'tools/prepare_latest_engine_pair.py': (12261, '98730f2d6abc71c1996fdaaa7a7c6e42533c4fec4c66b4f8aafb7c918290e6a2'),
}
HUD_BUILD_ID = '20261024T055841Z_974a5be57533'
HUD_HELPER_SHA = 'b62b2105c6d6049efaac830650d0c5b9158482e989d62e6b3106c0e06033a91d'
UNITS = (('host_main', 'HostMain'), ('window', 'BitmapWindow'),
         ('renderer', 'BitmapRenderer'), ('world_renderer', 'WorldViewRenderer'),
         ('terrain_renderer', 'WorldTerrainRenderer'))


def registered_host_spec(build_id):
    """Return a fresh pinned specification; report_path is project relative."""
    if build_id == HUD_BUILD_ID:
        spec = _world_hud_helper().registered_host_spec()
        spec.update(helper_path='tools/retained_world_hud_host_input.py', helper_sha256=HUD_HELPER_SHA)
        return spec
    if build_id == BUILD_ID:
        return dict(kind='legacy_native_envelope', build_id=BUILD_ID,
                    report_path=f'evidence/ui_window_host/{BUILD_ID}/build_result.json', report_sha256=REPORT_SHA,
                    executable_sha256='b96055dc020cec0bea86ad4e53f4335b2cad88694d27b56d63137bb4ff852aea')
    if build_id != RESTORE_BUILD_ID:
        return None
    return dict(kind='current_native_restore_contract', build_id=RESTORE_BUILD_ID,
        report_path=f'evidence/ui_window_host/{RESTORE_BUILD_ID}/build_result.json', report_sha256=RESTORE_REPORT_SHA,
        executable_sha256=RESTORE_EXECUTABLE_SHA,
        attestation_path=RESTORE_STAGE + '/attestation.json', attestation_sha256=RESTORE_ATTESTATION_SHA,
        retirement_path=RESTORE_STAGE + '/retirement/result.json', retirement_sha256=RESTORE_RETIREMENT_SHA,
        plan_path=RESTORE_STAGE + '/retirement/plan.json', plan_sha256=RESTORE_PLAN_SHA,
        publication_path='evidence/native_restore_contract/publication/progress_update.json', publication_sha256=RESTORE_UPDATE_SHA,
        audit_path='evidence/native_restore_contract/publication/final_audit.json', audit_sha256=RESTORE_AUDIT_SHA,
        pre_edit_path='evidence/native_restore_contract/publication/pre_edit.json', pre_edit_sha256=RESTORE_PRE_EDIT_SHA,
        operational_revisions_path='evidence/native_restore_contract/pair_preparation/operational_revisions.json',
        operational_backup_root='evidence/native_restore_contract/pair_preparation/source_backups',
        operational_before={name: dict(bytes=value[0], sha256=value[1]) for name, value in RESTORE_OPERATIONAL_BEFORE.items()},
        compiler_dependency_count=549, current_source_count=592, source_manifest_count=85,
        protected_artifact_count=1961, dependency_counts=(465, 266, 270, 279, 301))


def _require(condition, message):
    if not condition:
        raise RuntimeError(message)


def _key(path):
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def _pair(row):
    _require(isinstance(row, dict) and isinstance(row.get('path'), str) and
             isinstance(row.get('sha256'), str), 'Malformed retained Host artifact')
    return _key(row['path']), row['sha256']


def _snapshot(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


class _Files:
    def __init__(self, check_metadata=False):
        self.checked = {}
        self.check_metadata = check_metadata

    def state(self, info):
        value = _snapshot(info)
        return value + (getattr(info, 'st_file_attributes', None),) if self.check_metadata else value

    def metadata(self, info, row):
        if not self.check_metadata:
            return
        _require(('file_identity' not in row or row['file_identity'] == [info.st_dev, info.st_ino]) and
                 ('mtime_ns' not in row or row['mtime_ns'] == info.st_mtime_ns) and
                 ('file_attributes' not in row or row['file_attributes'] == getattr(info, 'st_file_attributes', None)),
                 'Retained Host input metadata differs')

    def ordinary(self, path):
        path = Path(path)
        _require(path.is_absolute() and '..' not in path.parts, 'Noncanonical Host artifact path')
        for parent in (path, *path.parents):
            info = parent.lstat()
            _require(not stat.S_ISLNK(info.st_mode) and
                     not getattr(info, 'st_file_attributes', 0) & 0x400,
                     'Reparse Host artifact path: ' + str(parent))
        info = path.stat()
        _require(stat.S_ISREG(info.st_mode), 'Host artifact is not a regular file')
        return info

    def verify(self, row):
        pair = _pair(row)
        path = Path(row['path'])
        before = self.ordinary(path)
        self.metadata(before, row)
        if pair in self.checked:
            _require(self.state(before) == self.checked[pair][1] and
                     ('bytes' not in row or (type(row['bytes']) is int and
                                            row['bytes'] == self.checked[pair][0]['bytes'])),
                     'Host input identity or byte count changed during validation')
            return self.checked[pair][0]
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(block)
        _require(digest.hexdigest() == row['sha256'] and
                 ('bytes' not in row or (type(row['bytes']) is int and row['bytes'] == before.st_size)) and
                 self.state(before) == self.state(path.stat()), 'Changed retained Host input: ' + str(path))
        actual = dict(path=str(path), bytes=before.st_size, sha256=digest.hexdigest())
        if self.check_metadata:
            actual.update(file_identity=[before.st_dev, before.st_ino], mtime_ns=before.st_mtime_ns)
            if hasattr(before, 'st_file_attributes'):
                actual['file_attributes'] = before.st_file_attributes
        self.checked[pair] = actual, self.state(before)
        return actual

    def json(self, row, compressed=False):
        actual = self.verify(row)
        _require(actual['bytes'] <= 8 * 1024 * 1024, 'Host evidence exceeds bound')
        raw = Path(actual['path']).read_bytes()
        _require(hashlib.sha256(raw).hexdigest() == actual['sha256'], 'Host evidence changed while reading')
        if compressed:
            with gzip.open(actual['path'], 'rb') as stream:
                raw = stream.read(8 * 1024 * 1024 + 1)
            _require(len(raw) <= 8 * 1024 * 1024, 'Host backup exceeds bound')
        if self.check_metadata:
            def unique(pairs):
                value = {}
                for name, item in pairs:
                    _require(name not in value, 'Duplicate retained Host JSON key')
                    value[name] = item
                return value
            return json.loads(raw.decode('utf-8-sig'), object_pairs_hook=unique,
                              parse_constant=lambda value: _require(False, 'Nonfinite retained Host JSON number'))
        return json.loads(raw.decode('utf-8-sig'))

    def finish(self):
        for row, snapshot in self.checked.values():
            _require(self.state(self.ordinary(row['path'])) == snapshot, 'Host input changed before completion')


def _walk(value):
    if isinstance(value, dict):
        if isinstance(value.get('path'), str) and 'sha256' in value:
            yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _world_hud_helper():
    """Load only authenticated source, without import caches or bytecode writes."""
    path = Path(__file__).with_name('retained_world_hud_host_input.py').absolute()
    files = _Files(check_metadata=True)
    info = files.ordinary(path)
    _require(info.st_size <= 128 * 1024, 'World HUD runtime helper exceeds bound')
    artifact = files.verify(dict(path=str(path), bytes=info.st_size, sha256=HUD_HELPER_SHA))
    raw = path.read_bytes()
    _require(len(raw) == artifact['bytes'] and hashlib.sha256(raw).hexdigest() == HUD_HELPER_SHA,
             'World HUD runtime helper changed before loading')
    module = types.ModuleType('_zerosis_retained_world_hud_host_input')
    module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    files.finish()
    return module


def _validate_legacy_retained_host_runtime(build, project):
    """Rehash retained inputs, keeping exact retired objects as historical proof."""
    project = Path(project).absolute()
    files = _Files()
    report_ref = dict(path=str(project / f'evidence/ui_window_host/{BUILD_ID}/build_result.json'),
                      sha256=REPORT_SHA)
    sealed = files.json(report_ref)
    _require(json.dumps(build, sort_keys=True, separators=(',', ':')) ==
             json.dumps(sealed, sort_keys=True, separators=(',', ':')) and build.get('build_id') == BUILD_ID,
             'Runtime Host report differs from the published build')
    stage = project / 'evidence/native_save_archive/host_relink/18bbd0dd26e70e623276'
    audit_ref = dict(path=str(stage / 'publication/final_audit.json'), sha256=AUDIT_SHA)
    audit = files.json(audit_ref)
    _require(audit['status'] == 'PASS_FRESH_CURRENT_HOST_LINK_PUBLICATION_AND_RETIREMENT_AUDIT' and
             audit['human_escape_stop_respected'] is True and audit['new_host_runtime_executed'] is False,
             'Host publication scope differs')
    attestation = files.json(audit['attestation'])
    post = files.json(audit['post'])
    update_ref = dict(path=str(stage / 'publication/progress_update.json'), sha256=UPDATE_SHA)
    update = files.json(update_ref)
    _require(attestation['status'] == 'PASS_RELINKED_NATIVE_HOST_STATIC_ATTESTATION' and
             _pair(attestation['build_result']) == _pair(report_ref) and
             _pair(update['build_result']) == _pair(report_ref) and
             _pair(update['attestation']) == _pair(audit['attestation']) and
             _pair(audit['executable']) == _pair(build['executable']), 'Host attestation belongs to another build')
    retirement = files.json(update['cleanup'])
    plan = files.json(retirement['plan'], compressed=True)
    _require(retirement['status'] == 'PASS_FIVE_ATTESTED_OBJECTS_AND_TWO_PRECOMPILE_FAILED_SNAPSHOTS_RETIRED' and
             _pair(retirement['attestation']) == _pair(audit['attestation']) and
             _pair(plan['build_result']) == _pair(report_ref) and
             _pair(plan['attestation']) == _pair(audit['attestation']), 'Host retirement belongs to another build')
    units = build['final_compilation']['translation_units']
    _require(len(units) == len(attestation['actual_coff_objects']) == 5, 'Host object inventory differs')
    targets = {_pair(row): row for row in plan['targets']}
    retired = {}
    for index, (unit, proof, (name, stem)) in enumerate(zip(units, attestation['actual_coff_objects'], UNITS)):
        row = unit['object']
        expected = project / f'Build/UiWindowHost/{BUILD_ID}/final/tu_{index:02d}_{name}/obj/{stem}.obj'
        _require(unit['translation_unit'] == proof['translation_unit'] == name and
                 type(unit['returncode']) is int and unit['returncode'] == 0 and
                 _key(row['path']) == _key(expected) and _pair(row) == _pair(proof['object']) and
                 _pair(row) in targets and row['bytes'] == targets[_pair(row)]['bytes'] and
                 not os.path.lexists(expected), 'Unattested or present retired Host object')
        retired[_pair(row)] = row
    revisions = update['changed_metadata']
    _require(revisions == post['authorized_metadata_revisions'] and len(revisions) == 2,
             'Host metadata publication proof differs')
    expected_metadata = { _key(project / path) for path in (
        'evidence/save_menu/20261013_original_screen/current_progress.json', 'docs/M7_RETAIL_SAVE_BOUNDARY.md') }
    historical = {}
    for revision in revisions:
        before, after = revision['before'], revision['after']
        _require(_key(before['path']) in expected_metadata and _key(before['path']) == _key(after['path']) and
                 revision['backup_roundtrip_verified'] is True, 'Unrelated historical Host metadata')
        backup = files.verify(revision['backup'])
        with gzip.open(backup['path'], 'rb') as stream:
            raw = stream.read(8 * 1024 * 1024 + 1)
        _require(len(raw) == before['bytes'] and hashlib.sha256(raw).hexdigest() == before['sha256'],
                 'Host metadata backup does not restore its build-time identity')
        historical[_pair(before)] = before
    _require(len(historical) == 2, 'Duplicate historical Host metadata')
    _require({pair[0] for pair in historical} == expected_metadata, 'Historical Host metadata paths differ')
    historical_visits, retired_visits = set(), set()
    for row in _walk(build):
        pair = _pair(row)
        if pair in retired:
            _require(row.get('bytes', retired[pair]['bytes']) == retired[pair]['bytes'], 'Retired object size differs')
            retired_visits.add(pair)
        elif pair in historical:
            _require(row.get('bytes', historical[pair]['bytes']) == historical[pair]['bytes'], 'Metadata size differs')
            historical_visits.add(pair)
        else:
            files.verify(row)
    _require(retired_visits == set(retired) and historical_visits == set(historical), 'Host historical inventory not consumed')
    files.finish()
    return dict(scope='RETAINED_HOST_RUNTIME_INPUTS_WITH_ATTESTED_FINAL_OBJECT_RETIREMENT',
                publication_audit=files.verify(audit_ref), attestation=files.verify(audit['attestation']),
                retirement=files.verify(update['cleanup']),
                retained_artifact_identities_verified=len(files.checked),
                absent_discovery_objects=[], absent_final_objects=[
                    dict(original_path=row['path'], sha256=row['sha256'], bytes=row['bytes']) for row in retired.values()],
                historical_metadata_backups_verified=2, host_executed=False, save_compatibility_verified=False)


def _registered_ref(project, spec, name):
    relative = Path(spec[name + '_path'])
    _require(not relative.is_absolute() and '..' not in relative.parts, 'Invalid registered Host evidence path')
    return dict(path=str(project / relative), sha256=spec[name + '_sha256'])


def _same(left, right):
    return _pair(left) == _pair(right) and left.get('bytes', right.get('bytes')) == right.get('bytes', left.get('bytes'))


def _recover(files, backup, before, root):
    path = Path(backup['path'])
    _require(path.is_relative_to(root) and type(before.get('bytes')) is int and 0 <= before['bytes'] <= 8 * 1024 * 1024,
             'Historical Host backup escaped its exact role')
    files.verify(backup)
    with gzip.open(path, 'rb') as stream:
        raw = stream.read(before['bytes'] + 1)
    _require(len(raw) == before['bytes'] and hashlib.sha256(raw).hexdigest() == before['sha256'],
             'Historical Host backup does not recover its declared bytes')


def _rows(rows, label):
    _require(type(rows) is list, 'Malformed ' + label)
    result = {}
    for row in rows:
        pair = _pair(row)
        _require(pair[0] not in result, 'Duplicate ' + label + ' path')
        result[pair[0]] = row
    return result


def _operational_revisions(files, project, build, spec, report_ref):
    expected_names = set(RESTORE_OPERATIONAL_BEFORE)
    _require(set(spec['operational_before']) == expected_names, 'Operational source allowlist differs')
    expected = {_key(project / name): value for name, value in spec['operational_before'].items()}
    source_paths = {_key(row['original_path']) for row in build['compiler_inputs']}
    source_paths.update(_key(row['original_source']) for row in build['sources'])
    source_paths.update(_key(row['path']) for row in build['current_source_inputs'])
    _require(not set(expected) & source_paths, 'An operational exception intersects the current Host source closure')
    anchors = {}
    for row in build['protected_artifacts']:
        path = _pair(row)[0]
        if path in expected:
            _require(path not in anchors and all(row[name] == expected[path][name] for name in ('bytes', 'sha256')),
                     'Operational before identity differs from the pinned build report')
            anchors[path] = row
    _require(set(anchors) == set(expected), 'Missing protected operational before identity')
    ledger_path = project / spec['operational_revisions_path']
    ledger_ref = files.verify(dict(path=str(ledger_path), sha256=_file_sha(ledger_path)))
    ledger = files.json(ledger_ref)
    _require(ledger.get('schema') == 'zerosis.native_restore.operational_revisions.v1' and
             ledger.get('build_id') == spec['build_id'] and _same(ledger['build_result'], report_ref) and
             ledger.get('compiled_host_sources_changed') is False and ledger.get('host_or_sdk_executed') is False and
             type(ledger.get('revisions')) is list and len(ledger['revisions']) == 3,
             'Operational revision ledger exceeds the exact source-only authority')
    historical, after_rows = {}, []
    backup_root = project / spec['operational_backup_root']
    for revision in ledger['revisions']:
        before, after = revision['before'], revision['after']
        path = _pair(before)[0]
        _require(path in anchors and _pair(before) not in historical and _same(before, anchors[path]) and
                 _key(after['path']) == path, 'Unrelated or duplicate operational source revision')
        _recover(files, revision['backup'], before, backup_root)
        after_rows.append(files.verify(after))
        historical[_pair(before)] = before
    _require({pair[0] for pair in historical} == set(expected), 'Incomplete operational source revisions')
    return historical, ledger_ref, after_rows


def _file_sha(path):
    # The ledger is deliberately not self-pinned: its exact old identities come
    # from the registered build; the preparer pins this observed receipt hash.
    before = _Files().ordinary(path)
    _require(before.st_size <= 8 * 1024 * 1024, 'Operational revision ledger exceeds bound')
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    _require(_snapshot(before) == _snapshot(Path(path).stat()), 'Operational ledger changed while hashing')
    return digest.hexdigest()


def _validate_restore_retained_host_runtime(build, project, spec):
    files = _Files(check_metadata=True)
    report_ref = _registered_ref(project, spec, 'report')
    sealed = files.json(report_ref)
    _require(json.dumps(build, sort_keys=True, separators=(',', ':')) == json.dumps(sealed, sort_keys=True, separators=(',', ':')) and
             build.get('build_id') == spec['build_id'] and build.get('schema') == 'zerosis.ui_window_host_build.v1' and
             build.get('status') == 'UI_WINDOW_HOST_CANDIDATE_BUILT' and build.get('source_inputs_unchanged') is True and
             build.get('provider_inputs_unchanged') is True and build.get('error') is None,
             'Current restore Host report differs from its registered build')
    refs = {name: _registered_ref(project, spec, name) for name in ('attestation', 'retirement', 'plan', 'publication', 'audit', 'pre_edit')}
    proof = {name: files.json(row) for name, row in refs.items()}
    attestation, retirement, plan = proof['attestation'], proof['retirement'], proof['plan']
    update, audit = proof['publication'], proof['audit']
    _require(attestation.get('status') == 'PASS_CURRENT_NATIVE_RESTORE_HOST_STATIC_ATTESTATION' and
             attestation.get('build_id') == spec['build_id'] and _same(attestation['build_result'], report_ref) and
             _same(attestation['executable'], build['executable']) and attestation.get('host_or_sdk_or_window_executed') is False and
             attestation.get('sdk_restore_verified') is False and attestation.get('native_restore_approved') is False,
             'Restore Host attestation scope or identity differs')
    _require(audit.get('status') == 'PASS_CURRENT_RESTORE_HOST_PUBLICATION_RETIREMENT_AND_INPUT_AUDIT' and
             audit.get('second_human_escape_stop_respected') is True and audit.get('current_host_executed') is False and
             audit.get('sdk_restore_or_reopen_verified') is False and audit.get('default_runtime_promoted') is False and
             _same(audit['publication'], refs['publication']) and _same(audit['build_result'], report_ref) and
             _same(audit['static_attestation'], refs['attestation']) and _same(audit['retirement'], refs['retirement']) and
             _same(audit['executable'], build['executable']), 'Restore Host final audit belongs to another graph')
    _require(update.get('status') == 'PASS_CURRENT_RESTORE_HOST_PROOF_PUBLISHED_WITHOUT_RUNTIME_PROMOTION' and
             update.get('current_host_source_matches_linked_candidate') is True and update.get('new_host_executed') is False and
             _same(update['build_result'], report_ref) and _same(update['static_attestation'], refs['attestation']) and
             _same(update['retirement'], refs['retirement']) and _same(update['pre_edit'], refs['pre_edit']),
             'Restore Host publication belongs to another graph')
    _require(retirement.get('status') == 'PASS_VERIFIED_CURRENT_HOST_INTERMEDIATES_RETIRED' and
             retirement.get('all_targets_absent') is True and retirement.get('host_sdk_or_ui_executed') is False and
             retirement.get('deleted_files') == 6 and retirement.get('deleted_empty_directories') == 6 and
             _same(retirement['plan'], refs['plan']) and _same(retirement['independent_static_attestation'], refs['attestation']) and
             _same(retirement['executable'], build['executable']) and
             plan.get('schema') == 'zerosis.native_restore.host_intermediate_retirement_plan.v1' and
             plan.get('target_files') == 6 and plan.get('independent_attestation_required_before_deletion') is True and
             _same(plan['build_result'], report_ref) and _same(plan['executable'], build['executable']),
             'Restore Host retirement is not the exact plain-JSON six-file plan')
    run = files.json(attestation['run'])
    _require(run.get('status') == 'PASS_CURRENT_NATIVE_RESTORE_HOST_BUILD_ONLY' and run.get('build_id') == spec['build_id'] and
             _same(run['build_result'], report_ref) and run.get('host_or_sdk_or_window_executed') is False,
             'Restore Host compiled-object provenance differs')
    units = build['final_compilation']['translation_units']
    _require(len(units) == len(attestation['units']) == len(run['actual_objects']) == 5, 'Restore Host TU inventory differs')
    targets = _rows(plan['targets'], 'retirement target')
    root = project / 'Build/UiWindowHost' / spec['build_id']
    retired = {}
    expected_targets = {_key(root / 'read_build_environment.cmd')}
    for index, (unit, item, obj, (name, stem)) in enumerate(zip(units, attestation['units'], run['actual_objects'], UNITS)):
        row = unit['object']
        expected = root / f'final/tu_{index:02d}_{name}/obj/{stem}.obj'
        path = _key(expected)
        _require(unit['translation_unit'] == item['translation_unit'] == name and
                 type(unit.get('returncode')) is int and unit['returncode'] == item['returncode'] == 0 and
                 item['coff_machine'] == '0x8664' and item['object_bytes'] == row['bytes'] and
                 _pair(row)[0] == path and _same(row, obj) and path in targets and _same(row, targets[path]) and
                 not os.path.lexists(expected), 'Unattested or present current Host object')
        retired[_pair(row)] = row; expected_targets.add(path)
    environment = targets.get(_key(root / 'read_build_environment.cmd'))
    _require(environment is not None and environment['bytes'] == 140 and
             environment['sha256'] == 'fbea552a6bb1afe675455702d2bcb52b666cb58115922a59f508f1cefc0e55bf' and
             set(targets) == expected_targets and not any(os.path.lexists(row['path']) for row in targets.values()) and
             {_key(path) for path in retirement['deleted_paths']} == expected_targets,
             'Retirement targets differ from the five objects and exact environment command')
    compiler = _rows(build['compiler_inputs'], 'compiler input')
    sources = _rows(build['sources'], 'source manifest')
    current = _rows(build['current_source_inputs'], 'current source input')
    _require(len(compiler) == build['compiler_dependency_count'] == attestation['compiler_dependency_union'] == spec['compiler_dependency_count'] and
             len(sources) == attestation['source_manifest_verified'] == spec['source_manifest_count'] and
             len(current) == attestation['current_inputs_verified'] == spec['current_source_count'] and
             len(build['protected_artifacts']) == attestation['protected_artifacts_verified'] == spec['protected_artifact_count'],
             'Restore Host source inventory counts differ')
    union = set()
    for index, unit in enumerate(units):
        dependency = files.json(unit['dependency_report'])
        data = dependency.get('Data', {})
        _require(dependency.get('Version') == '1.2' and type(data.get('Source')) is str and type(data.get('Includes')) is list and
                 all(type(path) is str for path in data['Includes']) and not data.get('ProvidedModule') and
                 not data.get('ImportedModules') and not data.get('ImportedHeaderUnits'), 'Unexpected current Host dependency schema')
        actual = {_key(path) for path in (data['Source'], *data['Includes'])}
        _require(actual <= set(compiler) and len(actual) == unit['expected_dependency_count'] == unit['actual_dependency_count'] ==
                 attestation['units'][index]['dependencies'] == spec['dependency_counts'][index], 'Actual current Host TU closure differs')
        union.update(actual)
    _require(union == set(compiler), 'Actual current Host dependency union differs')
    image = build['executable']
    _require(image['sha256'] == spec['executable_sha256'] and _key(image['path']) == _key(root / 'final/ZeroSisHost_x64.exe') and
             image['pe']['architecture'] == 'x64' and image['pe']['pe_format'] == 'PE32+' and image['pe']['is_dll'] is False and
             attestation['imports_verified'] == len(build['imports']['dependencies']) == 24 and
             build['catalog'] == attestation['catalog'] and build['catalog']['entry_count'] == 67 and
             build['catalog']['ordered_payload_manifest_sha256'] == 'db76873a3dff1360b89a4b57cc6c0da51893ace2efb234c5f83b739227bb411c' and
             build['restore_contract_marker'] == attestation['restore_contract_marker'] and
             build['restore_contract_marker']['ascii'] == 'NATIVE_RESTORE_CONTRACT_VERIFIED=SOURCE_ORDER_V1|' and
             build['restore_contract_marker']['inclusion_evidence_only'] is True,
             'Restore Host PE/payload/contract inclusion provenance differs')
    expected_metadata = {_key(project / path) for path in (
        'evidence/save_menu/20261013_original_screen/current_progress.json', 'docs/M7_RETAIL_SAVE_BOUNDARY.md')}
    historical = {}
    _require(len(update['changed_metadata']) == 2, 'Restore Host metadata revision inventory differs')
    for revision in update['changed_metadata']:
        before, after = revision['before'], revision['after']
        _require(_pair(before)[0] in expected_metadata and _key(after['path']) == _pair(before)[0] and
                 revision.get('gzip_roundtrip_verified') is True and _pair(before) not in historical,
                 'Unrelated or duplicate historical restore Host metadata')
        _recover(files, revision['backup'], before, project / 'evidence/native_restore_contract/publication')
        historical[_pair(before)] = before
    _require({pair[0] for pair in historical} == expected_metadata, 'Incomplete historical restore Host metadata')
    operational, ledger_ref, after_rows = _operational_revisions(files, project, build, spec, report_ref)
    historical.update(operational)
    historical_visits, retired_visits = set(), set()
    for row in _walk(build):
        pair = _pair(row)
        if pair in retired:
            _require(row.get('bytes', retired[pair]['bytes']) == retired[pair]['bytes'], 'Historical object byte count differs')
            retired_visits.add(pair)
        elif pair in historical:
            _require(row.get('bytes', historical[pair]['bytes']) == historical[pair]['bytes'], 'Historical source byte count differs')
            historical_visits.add(pair)
        else:
            files.verify(row)
    _require(retired_visits == set(retired) and historical_visits == set(historical), 'Unconsumed historical restore Host input')
    files.finish()
    return dict(scope='RETAINED_CURRENT_RESTORE_HOST_INPUTS_WITH_ATTESTED_FINAL_OBJECT_RETIREMENT',
        registered_build_id=spec['build_id'], build_result=files.verify(report_ref), publication_audit=files.verify(refs['audit']),
        attestation=files.verify(refs['attestation']), retirement=files.verify(refs['retirement']),
        retained_artifact_identities_verified=len(files.checked), compiler_dependency_count=len(compiler),
        source_manifest_count=len(sources), current_source_count=len(current), absent_discovery_objects=[],
        absent_final_objects=[dict(original_path=row['path'], bytes=row['bytes'], sha256=row['sha256']) for row in retired.values()],
        absent_environment_setup=dict(original_path=environment['path'], bytes=environment['bytes'], sha256=environment['sha256']),
        historical_metadata_backups_verified=2, historical_operational_backups_verified=3,
        operational_revisions=files.verify(ledger_ref), current_operational_sources=after_rows,
        current_restore_contract_linked=True, host_executed=False, sdk_restore_verified=False,
        native_restore_approved=False, save_compatibility_verified=False)


def validate_retained_host_runtime(build, project):
    """Dispatch only the registered immutable report; never infer a missing-input exception."""
    spec = registered_host_spec(build.get('build_id'))
    _require(spec is not None, 'Unregistered retained Host build')
    if spec['kind'] == 'legacy_native_envelope':
        return _validate_legacy_retained_host_runtime(build, project)
    if spec['kind'] == 'original_world_hud':
        return _world_hud_helper().validate_retained_world_hud_host_runtime(
            build, Path(project).absolute(), spec, _Files(check_metadata=True))
    _require(spec['kind'] == 'current_native_restore_contract', 'Unrecognized retained Host profile')
    return _validate_restore_retained_host_runtime(build, Path(project).absolute(), spec)
