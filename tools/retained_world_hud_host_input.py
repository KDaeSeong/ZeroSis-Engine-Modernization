"""Read-only gate for the single attested original-world-HUD Host.

Historical references are accepted only in their declared metadata roles. The
prior, never-executed prepared pair is context, not an input to this linked PE.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
from pathlib import Path


BUILD_ID = '20261024T055841Z_974a5be57533'
STAGE = 'evidence/original_world_hud/host_build/974a5be5753302c4498c'
PRIOR_ID = '20261024T050152Z_fd0465b26387'
PARENT_ID = '20261024T042219Z_e6399c82ee5c'
PROGRESS = 'evidence/save_menu/20261013_original_screen/current_progress.json'
M7 = 'docs/M7_RETAIL_SAVE_BOUNDARY.md'
DOCUMENT = 'docs/ORIGINAL_WORLD_HUD.md'
HELPER = 'tools/retained_world_hud_host_input.py'
OPERATIONS = ('tools/retained_host_runtime_input.py', 'tools/prepare_latest_engine_pair.py')
SOURCE_NAMES = ('Source/Presentation/WorldViewRenderer.cpp', 'Source/Presentation/BitmapWindow.h',
                'Source/Presentation/BitmapWindow.cpp', 'Source/Host/InteractiveGameLoop.h',
                'Source/Presentation/WorldCameraControls.h')
UNITS = (('host_main', 'HostMain'), ('window', 'BitmapWindow'), ('renderer', 'BitmapRenderer'),
         ('world_renderer', 'WorldViewRenderer'), ('terrain_renderer', 'WorldTerrainRenderer'))
PINS = {
    'run': ('run.json', '50e68a7d72a95572c8e40439ac14e9961a73d21fcc266ae67604597aa8b4475e'),
    'attestation': ('attestation.json', '476953a732f62125b3165152159c6d8230857e50b8be58e8e23da26e6ef5fca3'),
    'retirement': ('retirement/result.json', '9ca8b9339c52aa16b81880b6379363853702d8cc0d2a9c2fdf83634e15fd425a'),
    'plan': ('retirement/plan.json', 'fcdcf8ca35cac32ef24f3ac229ef03a3cd42efe408e22d0191f4d7ff6d2d3852'),
    'publication': ('publication/result.json', '6cfc3e2943f9edb57990c004f109b390e62c9d16bafad77ca4953cefa0ed41a5'),
    'audit': ('final_audit.json', 'd7d58d16e7c0f63365d39d4d8002f00bb9d024998dce57e89674747e30382e8a'),
    'post_audit': ('post_publication_audit.json', '1629061347856671c209cb16b73990dc6e2764e38d2d08a72f86172c292001be'),
}


def registered_host_spec():
    spec = dict(kind='original_world_hud', build_id=BUILD_ID,
        report_path=f'evidence/ui_window_host/{BUILD_ID}/build_result.json',
        report_sha256='6aa2ccdb8ce1308521fc01f88fa45745153244b6931754a0b3111dc2129d1302',
        executable_sha256='600b3806b2bec50de07f85425f1532c259df3877d443cadd46de31bc3d935cd5',
        authority_path='evidence/original_world_hud/host_build/inputs.json',
        authority_sha256='db8dbd4d0c3e854dda26cf6786f4d34de3fb0b0750a8f8fe2d9b8d764c3ad594',
        prior_request_path=f'evidence/interactive_game/{PRIOR_ID}/request.json',
        prior_request_sha256='84c8b56d70dda98f9f6c1b8d3f894f0b6ea298564cab2d1130e8ef51ef22d3a4',
        operational_revisions_path='evidence/original_world_hud/pair_preparation/operational_revisions.json',
        operational_backup_root='evidence/original_world_hud/pair_preparation/source_backups',
        operational_before={OPERATIONS[0]: dict(bytes=31372,
            sha256='f0edc1fae8bc5d9deecc89b93a819ae684650fb10471e8abad2714127490e940'),
            OPERATIONS[1]: dict(bytes=13471,
            sha256='a611eaf9b48bf6d347bf7584fae233d98da341d239b3bf9d541227e44c5b4357')},
        compiler_dependency_count=549, current_source_count=592, source_manifest_count=85,
        protected_artifact_count=1961, dependency_counts=(465, 266, 270, 279, 301),
        materialized_input_count=592, private_source_copies=5, donor_hardlinks=587)
    for name, (relative, digest) in PINS.items():
        spec[name + '_path'], spec[name + '_sha256'] = STAGE + '/' + relative, digest
    return spec


def require(value, message):
    if not value:
        raise RuntimeError(message)


def key(path):
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def pair(row):
    require(isinstance(row, dict) and type(row.get('path')) is str and type(row.get('sha256')) is str,
            'Malformed world HUD Host artifact')
    return key(row['path']), row['sha256']


def same(left, right):
    return pair(left) == pair(right) and left.get('bytes', right.get('bytes')) == right.get('bytes', left.get('bytes'))


def rows(value, label):
    require(type(value) is list, 'Malformed ' + label)
    result = {}
    for row in value:
        path = pair(row)[0]
        require(path not in result, 'Duplicate ' + label + ' path')
        result[path] = row
    return result


def walk(value):
    if isinstance(value, dict):
        if type(value.get('path')) is str and 'sha256' in value:
            yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def ref(project, spec, name):
    relative = Path(spec[name + '_path'])
    require(not relative.is_absolute() and '..' not in relative.parts, 'Invalid registered world HUD evidence path')
    return dict(path=str(project / relative), sha256=spec[name + '_sha256'])


def recover(files, backup, before, root):
    require(Path(backup['path']).is_relative_to(root) and type(before.get('bytes')) is int and
            0 <= before['bytes'] <= 8 * 1024 * 1024, 'Historical world HUD backup escaped its role')
    files.verify(backup)
    with gzip.open(backup['path'], 'rb') as stream:
        raw = stream.read(before['bytes'] + 1)
    require(len(raw) == before['bytes'] and hashlib.sha256(raw).hexdigest() == before['sha256'],
            'Historical world HUD backup does not restore its declared identity')


def historical_provenance(files, project, build, current):
    groups = (
        ('source_revision_provenance', 'production_source', SOURCE_NAMES, 'evidence/original_world_hud/source_backups'),
        ('historical_operational_recovery', 'operational_source', (*OPERATIONS, 'tools/run_interactive_game.py'),
         'evidence/native_restore_contract/pair_preparation/source_backups'),
        ('historical_metadata_recovery', 'metadata', (PROGRESS, M7), 'evidence/native_restore_contract/publication'))
    afters = {}
    for field, category, names, backup_root in groups:
        expected = {key(project / name) for name in names}
        found = set()
        require(type(build.get(field)) is list and len(build[field]) == len(expected), 'Historical world HUD inventory differs')
        for revision in build[field]:
            before, after = revision['before'], revision['after']
            path = key(before['original_path'])
            require(revision.get('category') == category and 'path' not in before and path in expected and path not in found and
                    pair(after)[0] == path, 'Historical world HUD annotation exceeds its exact source role')
            recover(files, before['backup'], before, project / backup_root)
            if category == 'production_source':
                require(path in current and same(after, current[path]), 'Current world HUD source differs from its revision proof')
            found.add(path)
            afters[path] = after
        require(found == expected, 'Incomplete historical world HUD source annotations')
    inherited = build['inherited_historical_metadata_recovery']
    require(type(inherited) is list and len(inherited) == 2, 'Inherited world HUD metadata inventory differs')
    found = set()
    for before in inherited:
        path = key(before['original_path'])
        require('path' not in before and path in {key(project / PROGRESS), key(project / M7)} and path not in found,
                'Unrelated inherited world HUD metadata')
        recover(files, before['backup'], before,
                project / 'evidence/native_save_archive/host_relink/18bbd0dd26e70e623276/publication')
        found.add(path)
    return afters


def operational_revisions(files, project, build, spec, report_ref, current, compiler, sources):
    require(set(spec['operational_before']) == set(OPERATIONS), 'World HUD operational source allowlist differs')
    expected = {key(project / name): row for name, row in spec['operational_before'].items()}
    compiled = set(current) | {key(row['original_path']) for row in compiler.values()}
    compiled.update(key(row.get('original_source', row.get('original_path'))) for row in sources.values())
    require(not set(expected) & compiled and key(project / HELPER) not in compiled,
            'Operational revision intersects the compiled world HUD closure')
    protected = rows(build['protected_artifacts'], 'protected world HUD artifact')
    for path, before in expected.items():
        require(path in protected and all(protected[path][name] == before[name] for name in ('bytes', 'sha256')),
                'Operational before identity differs from the registered Host report')
    path = project / spec['operational_revisions_path']
    info = files.ordinary(path)
    require(info.st_size <= 8 * 1024 * 1024, 'World HUD operational ledger exceeds bound')
    raw = path.read_bytes()
    require(len(raw) == info.st_size and files.state(info) == files.state(path.stat()),
            'World HUD operational ledger changed while reading')
    ledger_ref = files.verify(dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()))
    ledger = files.json(ledger_ref)
    require(ledger.get('schema') == 'zerosis.original_world_hud.operational_revisions.v1' and
            ledger.get('build_id') == spec['build_id'] and same(ledger['build_result'], report_ref) and
            ledger.get('compiled_host_sources_changed') is False and ledger.get('host_or_sdk_executed') is False and
            type(ledger.get('revisions')) is list and len(ledger['revisions']) == 2,
            'World HUD operational ledger exceeds the exact source-only authority')
    historical, afters = {}, []
    for revision in ledger['revisions']:
        before, after = revision['before'], revision['after']
        path_key = pair(before)[0]
        require(path_key in expected and pair(before) not in historical and same(before, protected[path_key]) and
                pair(after)[0] == path_key, 'Unrelated or duplicate world HUD operational revision')
        recover(files, revision['backup'], before, project / spec['operational_backup_root'])
        historical[pair(before)] = before
        afters.append(files.verify(after))
    require({item[0] for item in historical} == set(expected), 'Incomplete world HUD operational revisions')
    added = ledger.get('added_operational_sources')
    require(type(added) is list and len(added) == 1 and key(project / HELPER) == pair(added[0])[0] and
            spec['helper_path'] == HELPER and added[0]['sha256'] == spec['helper_sha256'],
            'World HUD added operational helper differs from its authenticated implementation')
    helper = files.verify(added[0])
    return historical, ledger_ref, afters, helper


def prior_context(files, project, build, run, request_ref):
    request = files.json(request_ref)
    root = project / 'Build/InteractiveGameRuntime' / PRIOR_ID
    require(request.get('run_id') == PRIOR_ID and key(request['cwd']) == key(root) and request.get('smoke') is False,
            'Prior prepared-pair context is not the exact unexecuted request')
    expected = rows(request['runtime_inputs'], 'prior request runtime context')
    prepared = rows(build['prepared_runtime_inputs'], 'prior prepared runtime context')
    retained = rows(run['retained_runtime_inputs'], 'prior build-run runtime context')
    require(len(expected) == len(prepared) == len(retained) == 24 and
            {pair(row) for row in expected.values()} == {pair(row) for row in prepared.values()} ==
            {pair(row) for row in retained.values()} and all(Path(row['path']).is_relative_to(root) for row in expected.values()),
            'Prior unexecuted runtime context differs from its exact 24 references')
    for path, row in prepared.items():
        require(same(row, retained[path]), 'Prior runtime context size differs')
    return files.verify(request_ref)


def validate_retained_world_hud_host_runtime(build, project, spec, files):
    project = Path(project).absolute()
    require(spec.get('kind') == 'original_world_hud' and spec.get('build_id') == BUILD_ID, 'Unregistered world HUD Host profile')
    report_ref = ref(project, spec, 'report')
    sealed = files.json(report_ref)
    require(json.dumps(build, sort_keys=True, separators=(',', ':')) == json.dumps(sealed, sort_keys=True, separators=(',', ':')) and
            build.get('build_id') == BUILD_ID and build.get('schema') == 'zerosis.ui_window_host_build.v1' and
            build.get('status') == 'UI_WINDOW_HOST_CANDIDATE_BUILT' and build.get('source_inputs_unchanged') is True and
            build.get('provider_inputs_unchanged') is True and build.get('host_runtime_executed') is False and
            build.get('gamecore_loaded') is False and build.get('native_restore_approved') is False,
            'World HUD Host report differs from its registered immutable build')
    refs = {name: ref(project, spec, name) for name in (*PINS, 'authority', 'prior_request')}
    proof = {name: files.json(row) for name, row in refs.items() if name != 'prior_request'}
    run, att = proof['run'], proof['attestation']
    plan, retired_proof = proof['plan'], proof['retirement']
    publication, audit, post = proof['publication'], proof['audit'], proof['post_audit']
    statuses = {'run': 'PASS_CURRENT_ORIGINAL_WORLD_HUD_HOST_BUILD_ONLY',
        'attestation': 'PASS_CURRENT_ORIGINAL_WORLD_HUD_HOST_STATIC_ATTESTATION',
        'retirement': 'PASS_VERIFIED_CURRENT_WORLD_HUD_HOST_INTERMEDIATES_RETIRED',
        'publication': 'PASS_CURRENT_WORLD_HUD_HOST_PUBLISHED_WITHOUT_RUNTIME_PROMOTION',
        'audit': 'PASS_CURRENT_WORLD_HUD_HOST_BUILD_PUBLICATION_AND_CLEANUP_AUDIT',
        'post_audit': 'PASS_CURRENT_WORLD_HUD_HOST_LINK_METADATA_AND_CLEANUP_READBACK'}
    for name, status in statuses.items():
        require(proof[name].get('status') == status, 'World HUD proof status differs: ' + name)
    require(all(value.get('build_id', BUILD_ID) == BUILD_ID for value in proof.values()) and
            all(same(value['build_result'], report_ref) for value in (run, att, plan, publication, audit, post)) and
            all(same(value['independent_attestation'], refs['attestation']) for value in (plan, retired_proof, publication, audit, post)) and
            all(same(value['run'], refs['run']) for value in (att, plan, retired_proof, publication, audit)) and
            all(same(value['retirement'], refs['retirement']) for value in (publication, audit, post)) and
            same(att['authority'], refs['authority']) and same(run['profile'], refs['authority']) and
            same(att['started'], run['started']) and same(run['started'], build['started']) and
            same(audit['publication'], refs['publication']) and same(post['previous_finish_audit'], refs['audit']),
            'World HUD publication or attestation belongs to another graph')
    require(all(value.get('host_or_sdk_or_window_executed') is False for value in (run, att, plan, retired_proof, publication, audit)) and
            all(value.get('full_engine_goal_complete') is False for value in (run, att, retired_proof, publication, audit, post)) and
            run.get('sdk_restore_verified') is False and run.get('native_restore_approved') is False and
            att.get('sdk_restore_verified') is False and att.get('native_restore_approved') is False and
            audit.get('prepared_runtime_updated') is False and post.get('new_host_materialized_in_prepared_runtime') is False and
            post.get('native_runtime_attempts') == 0 and post.get('retired_files_absent') == 6 and
            audit.get('current_source_matches_new_link') is True and audit.get('frozen_donor_metadata_preserved') is True,
            'World HUD scope exceeds static build and retirement proof')
    commands = run['commands']
    require(len(commands) == 7 and [item['phase'] for item in commands] == ['environment'] + ['compile'] * 5 + ['link'] and
            all(type(item['returncode']) is int and item['returncode'] == 0 for item in commands) and
            att.get('seven_recorded_commands_verified') is True and att.get('returncodes') == [0] * 7 and
            att.get('exact_response_relocation_verified') is True and run.get('input_files_unchanged') is True,
            'World HUD compile/link command proof differs')
    for artifact in (run['started'], run['builder'], run['baseline_build'], att['baseline_attestation']):
        files.verify(artifact)
    require(same(build['baseline_build'], run['baseline_build']) and same(build['baseline_build'], att['baseline_build']),
            'World HUD parent build references differ')
    baseline = files.json(build['baseline_build'])
    require(baseline.get('build_id') == PARENT_ID, 'World HUD donor parent is not the registered restore Host')
    protected = rows(build['protected_artifacts'], 'world HUD protected artifact')
    for index, item in enumerate(commands):
        executable = key(item['executable'])
        require(executable in protected and type(item['command']) is list and len(item['command']) > 0 and
                key(item['command'][0]) == executable and
                (index == 0 or executable == key(build['compiler' if index < 6 else 'linker']['path'])),
                'World HUD recorded command executable lacks its protected identity')
        files.verify(protected[executable]); files.verify(item['log'])
    units = build['final_compilation']['translation_units']
    require(len(units) == len(att['units']) == len(run['actual_objects']) == len(att['actual_objects']) == 5,
            'World HUD five-object inventory differs')
    targets = rows(plan['targets'], 'world HUD retirement target')
    root = project / 'Build/UiWindowHost' / BUILD_ID
    retired, expected_targets = {}, {key(root / 'read_build_environment.cmd')}
    for index, (unit, item, (name, stem)) in enumerate(zip(units, att['units'], UNITS)):
        obj = unit['object']; expected = root / f'final/tu_{index:02d}_{name}/obj/{stem}.obj'
        require(unit['translation_unit'] == item['translation_unit'] == name and type(unit['returncode']) is int and
                unit['returncode'] == item['returncode'] == 0 and item['coff_machine'] == unit['coff_machine'] == '0x8664' and
                item['object_bytes'] == obj['bytes'] and pair(obj)[0] == key(expected) and key(expected) in targets and
                same(obj, targets[key(expected)]) and same(obj, run['actual_objects'][index]) and same(obj, att['actual_objects'][index]),
                'World HUD retired object lacks exact compile and attestation provenance')
        retired[pair(obj)] = obj; expected_targets.add(key(expected))
    environment = targets.get(key(root / 'read_build_environment.cmd'))
    require(environment is not None and environment['bytes'] == 140 and
            environment['sha256'] == 'fbea552a6bb1afe675455702d2bcb52b666cb58115922a59f508f1cefc0e55bf' and
            plan.get('schema') == 'zerosis.original_world_hud.host_retirement_plan.v1' and plan.get('target_files') == 6 and
            retired_proof.get('all_targets_absent') is True and retired_proof.get('deleted_files') == 6 and
            same(retired_proof['plan'], refs['plan']) and set(targets) == expected_targets and
            {key(path) for path in retired_proof['deleted_paths']} == expected_targets and
            not any(os.path.lexists(row['path']) for row in targets.values()), 'World HUD retirement is not the exact absent six-file plan')
    compiler = rows(build['compiler_inputs'], 'world HUD compiler input')
    sources = rows(build['sources'], 'world HUD source manifest')
    current = rows(build['current_source_inputs'], 'world HUD current source')
    require(len(compiler) == build['compiler_dependency_count'] == att['compiler_dependency_union'] == spec['compiler_dependency_count'] and
            len(current) == att['current_inputs_verified'] == spec['current_source_count'] and
            len(sources) == att['source_manifest_verified'] == spec['source_manifest_count'] and
            len(rows(build['protected_artifacts'], 'world HUD protected artifact')) == att['protected_artifacts_verified'] == spec['protected_artifact_count'],
            'World HUD current source inventories differ')
    union = set()
    for index, unit in enumerate(units):
        dependency = files.json(unit['dependency_report']); data = dependency.get('Data', {})
        require(dependency.get('Version') == '1.2' and type(data.get('Source')) is str and type(data.get('Includes')) is list and
                all(type(path) is str for path in data['Includes']) and not data.get('ProvidedModule') and
                not data.get('ImportedModules') and not data.get('ImportedHeaderUnits'), 'Unexpected world HUD dependency schema')
        actual = {key(path) for path in (data['Source'], *data['Includes'])}
        require(actual <= set(compiler) and len(actual) == unit['expected_dependency_count'] == unit['actual_dependency_count'] ==
                att['units'][index]['dependencies'] == spec['dependency_counts'][index] and commands[index + 1]['command'] == unit['command'],
                'World HUD actual translation-unit closure differs')
        union.update(actual)
    require(union == set(compiler), 'World HUD actual compiler dependency union differs')
    materialized = {}
    for name in ('sources', 'compiler_inputs', 'provider_inputs', 'system_libraries', 'build_tools', 'implicit_libraries', 'provider_reports', 'ui_assets'):
        for row in walk(build[name]):
            path = pair(row)[0]
            require(path not in materialized or same(row, materialized[path]), 'Conflicting materialized world HUD input')
            materialized[path] = row
    implicit = rows(build['implicit_libraries'], 'world HUD implicit library')
    parent_implicit = rows(baseline['implicit_libraries'], 'parent implicit library')
    require(len(implicit) == att['implicit_libraries_verified'] == 8 and len(materialized) == spec['materialized_input_count'],
            'World HUD frozen input inventory differs')
    require(len(parent_implicit) == 8 and {key(row['reused_from_path']) for row in implicit.values()} == set(parent_implicit),
            'World HUD implicit libraries differ from the exact eight parent inputs')
    for row in implicit.values():
        parent = parent_implicit[key(row['reused_from_path'])]
        require(row['sha256'] == parent['sha256'] and row['bytes'] == parent['bytes'] and
                key(row['original_path']) == key(parent['original_path']) and
                row.get('file_identity') == parent.get('file_identity'), 'World HUD implicit library donor provenance differs')
    origins, copies, links = set(), set(), 0
    for row in materialized.values():
        original = key(row.get('original_path', row.get('original_source')))
        require(original not in origins and Path(row['path']).is_relative_to(root / 'frozen'), 'World HUD frozen origin is duplicate or outside its snapshot')
        origins.add(original)
        if original in current:
            require(row['sha256'] == current[original]['sha256'] and row['bytes'] == current[original]['bytes'], 'World HUD frozen/current bytes differ')
        else:
            require(pair(row)[0] in implicit, 'Only the eight attested implicit libraries may lack current-source origins')
        actual = files.verify(row)
        if row.get('materialization') == 'owned_changed_source_copy':
            require(original in {key(project / name) for name in SOURCE_NAMES} and original in current and
                    actual['file_identity'] != files.verify(current[original])['file_identity'], 'World HUD private source copy is not independent')
            copies.add(original)
        else:
            require(row.get('materialization') == 'attested_snapshot_hardlink' and
                    Path(row['reused_from_path']).is_relative_to(project / 'Build/UiWindowHost' / PARENT_ID / 'frozen'),
                    'World HUD donor is not the exact attested parent snapshot')
            donor = dict(row, path=row['reused_from_path'])
            require(actual['file_identity'] == files.verify(donor)['file_identity'], 'World HUD snapshot donor no longer shares identity')
            links += 1
    require(origins - set(current) == {key(row['original_path']) for row in implicit.values()} and
            copies == {key(project / name) for name in SOURCE_NAMES} and len(copies) == spec['private_source_copies'] and
            links == spec['donor_hardlinks'] and att['materialization']['private_source_copies'] == len(copies) and
            att['materialization']['donor_hardlinks'] == links, 'World HUD private-copy/shared-donor counts differ')
    image = build['executable']; imports = files.json(build['imports']['log'])
    require(image['sha256'] == spec['executable_sha256'] and pair(image)[0] == key(root / 'final/ZeroSisHost_x64.exe') and
            image['pe']['architecture'] == 'x64' and image['pe']['pe_format'] == 'PE32+' and image['pe']['is_dll'] is False and
            all(same(value['executable'], image) for value in (att, retired_proof, audit, post)) and
            att['imports_verified'] == len(build['imports']['dependencies']) == len(set(build['imports']['dependencies'])) == 24 and
            build['imports']['dependencies'] == att['imports'] == imports['dependencies'] and same(imports['image'], image) and
            imports.get('source') == 'PURE_FILE_BACKED_PE_IMPORT_DIRECTORY' and
            build['catalog'] == att['catalog'] == run['catalog'] and build['catalog']['entry_count'] == 67 and
            build['catalog']['ordered_payload_manifest_sha256'] == 'db76873a3dff1360b89a4b57cc6c0da51893ace2efb234c5f83b739227bb411c' and
            build['restore_contract_marker'] == att['restore_contract_marker'] == run['restore_contract_marker'] and
            build['restore_contract_marker']['ascii'] == 'NATIVE_RESTORE_CONTRACT_VERIFIED=SOURCE_ORDER_V1|' and
            build['restore_contract_marker']['inclusion_evidence_only'] is True, 'World HUD immutable PE/payload/import provenance differs')
    historical_provenance(files, project, build, current)
    historical, ledger_ref, after_rows, helper_ref = operational_revisions(files, project, build, spec, report_ref, current, compiler, sources)
    revisions = publication['changed_metadata']
    require(type(revisions) is list and len(revisions) == 2, 'World HUD publication metadata inventory differs')
    metadata = {}
    for revision in revisions:
        before, after = revision['before'], revision['after']; path = pair(before)[0]
        require(path in {key(project / PROGRESS), key(project / DOCUMENT)} and path not in metadata and pair(after)[0] == path and
                revision.get('gzip_roundtrip_verified') is True, 'World HUD publication exceeds its two metadata roles')
        recover(files, revision['backup'], before, project / STAGE / 'publication')
        metadata[path] = revision
    progress = metadata[key(project / PROGRESS)]
    historical[pair(progress['before'])] = progress['before']
    correction = files.json(post['metadata_correction'])
    require(correction.get('status') == 'PASS_CURRENT_SOURCE_PROOF_ALIASES_AND_DOCUMENTATION_REFERENCE_CORRECTED' and
            correction.get('binary_or_source_changes') is False and correction.get('host_sdk_or_window_executed') is False and
            same(correction['build_result'], report_ref) and same(correction['independent_attestation'], refs['attestation']) and
            same(correction['before'], progress['after']) and same(correction['after'], post['current_progress']) and
            same(correction['current_documentation'], post['current_documentation']) and
            same(post['current_documentation'], metadata[key(project / DOCUMENT)]['after']), 'World HUD metadata correction chain differs')
    recover(files, correction['backup'], correction['before'], project / STAGE / 'publication')
    context_ref = prior_context(files, project, build, run, refs['prior_request'])
    historical_visits, retired_visits = set(), set()
    # Only this top-level field is context. Identical references in any other
    # field remain ordinary live dependencies and must still exist.
    for name, value in build.items():
        if name == 'prepared_runtime_inputs':
            continue
        for row in walk(value):
            item = pair(row)
            if item in retired:
                require(row.get('bytes', retired[item]['bytes']) == retired[item]['bytes'], 'Retired world HUD object size differs')
                retired_visits.add(item)
            elif item in historical:
                require(row.get('bytes', historical[item]['bytes']) == historical[item]['bytes'], 'Historical world HUD input size differs')
                historical_visits.add(item)
            else:
                files.verify(row)
    require(retired_visits == set(retired) and historical_visits == set(historical), 'Unconsumed world HUD historical input')
    files.finish()
    return dict(scope='RETAINED_ORIGINAL_WORLD_HUD_HOST_WITH_ATTESTED_FINAL_OBJECT_RETIREMENT',
        registered_build_id=BUILD_ID, build_result=files.verify(report_ref), attestation=files.verify(refs['attestation']),
        retirement=files.verify(refs['retirement']), publication_audit=files.verify(refs['post_audit']),
        retained_artifact_identities_verified=len(files.checked), compiler_dependency_count=len(compiler),
        current_source_count=len(current), source_manifest_count=len(sources), materialized_input_count=len(materialized),
        private_source_copies=len(copies), donor_hardlinks=links, absent_discovery_objects=[],
        absent_final_objects=[dict(original_path=row['path'], bytes=row['bytes'], sha256=row['sha256']) for row in retired.values()],
        absent_environment_setup=dict(original_path=environment['path'], bytes=environment['bytes'], sha256=environment['sha256']),
        historical_source_backups_verified=5, historical_operational_backups_verified=5, historical_metadata_backups_verified=7,
        operational_revisions=files.verify(ledger_ref), current_operational_sources=after_rows,
        added_operational_sources=[helper_ref], prior_prepared_pair_request=context_ref,
        prior_unexecuted_prepared_pair_context_historical=True, prior_prepared_pair_context_inputs=24,
        current_original_world_hud_linked=True, host_executed=False, sdk_restore_verified=False,
        native_restore_approved=False, save_compatibility_verified=False, actual_window_wheel_routing_verified=False)
