"""Single-use offline Host rebuild for the three-header plus one-header delta.

Reuse the attested parent recipes and immutable file identities. Never launch
the resulting Host, a game SDK, asset preparation, or a window.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import types

PROJECT = Path(__file__).absolute().parents[1]
STAGE_ROOT = PROJECT / 'evidence/original_world_hud/hover_repaint'
PARENT_ID = '20261024T055841Z_974a5be57533'
PARENT_ROOT = PROJECT / 'Build/UiWindowHost' / PARENT_ID
PARENT_REPORT = PROJECT / 'evidence/ui_window_host' / PARENT_ID / 'build_result.json'
PARENT_SHA = '6aa2ccdb8ce1308521fc01f88fa45745153244b6931754a0b3111dc2129d1302'
AUDIT_SHA = '80f806d06fc519005579ae421ebfcbbe8377173d2a11d4057f674e0f60e170de'
REQUIREMENTS_SHA = 'a642bc220023884a1fe26aad9055a9672c043fa926614f747434c01dd69e4fde'
UNITS = ('host_main', 'window', 'renderer', 'world_renderer', 'terrain_renderer')
STEMS = ('HostMain', 'BitmapWindow', 'BitmapRenderer', 'WorldViewRenderer', 'WorldTerrainRenderer')
COUNTS = (466, 266, 270, 279, 301)
LIBRARIES = {'msvcrt.lib', 'msvcprt.lib', 'vcruntime.lib', 'oldnames.lib',
             'bcrypt.lib', 'kernel32.lib', 'ucrt.lib', 'uuid.lib'}
MARKER = b'NATIVE_RESTORE_CONTRACT_VERIFIED=SOURCE_ORDER_V1|'


def key(path):
    return os.path.normcase(os.path.abspath(path))


def inside(path, root):
    return Path(key(path)).is_relative_to(Path(key(root)))


def ordinary(path):
    path = Path(os.path.abspath(path))
    for item in (path, *path.parents):
        if item.exists():
            assert not item.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT, item
    info = path.lstat()
    assert stat.S_ISREG(info.st_mode), path
    return info


def artifact(path):
    path = Path(os.path.abspath(path))
    before = ordinary(path)
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    after = ordinary(path)
    assert (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_file_attributes) == (
        after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_file_attributes), path
    return dict(path=str(path), bytes=after.st_size, sha256=digest,
                file_identity=[after.st_dev, after.st_ino], mtime_ns=after.st_mtime_ns,
                file_attributes=after.st_file_attributes)


def sealed(row, metadata=True):
    current = artifact(row['path'])
    for name in ('bytes', 'sha256'):
        assert current[name] == row[name], (row['path'], name)
    if metadata:
        for name in ('file_identity', 'mtime_ns', 'file_attributes'):
            if name in row:
                assert current[name] == row[name], (row['path'], name)
    return current


def pin(path, digest):
    row = artifact(path)
    assert row['sha256'] == digest, path
    return row


def sealed_bytes(row):
    with Path(row['path']).open('rb') as stream:
        raw = stream.read(row['bytes'] + 1)
    assert len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256']
    sealed(row)
    return raw


def load_pure(path, digest, name):
    row = pin(path, digest)
    raw = sealed_bytes(row)
    module = types.ModuleType(name)
    module.__file__ = str(path)
    sys.modules[name] = module
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    sealed(row)
    return module


def read(path):
    return json.loads(Path(path).read_bytes())


def dependency_paths(path):
    data = read(path)['Data']
    visits = [data['Source'], *data.get('Includes', [])]
    return {key(item) for item in visits}, len(visits)


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--preflight', action='store_true')
    options = cli.parse_args()
    assert os.name == 'nt' and sys.dont_write_bytecode and __debug__
    assert not any(value for name, value in os.environ.items() if name.upper() in ('CL', '_CL_', 'LINK'))
    parent_ref = pin(PARENT_REPORT, PARENT_SHA)
    base = json.loads(sealed_bytes(parent_ref))
    assert base['status'] == 'UI_WINDOW_HOST_CANDIDATE_BUILT' and base['build_id'] == PARENT_ID
    assert (len(base['compiler_inputs']), len(base['sources']), len(base['current_source_inputs'])) == (549, 85, 592)
    audit_ref = pin(STAGE_ROOT / 'component_audit.json', AUDIT_SHA)
    audit = json.loads(sealed_bytes(audit_ref))
    assert audit['status'] == 'PASS_CURRENT_SOURCE_COMPONENTS_AND_HOSTMAIN_SYNTAX_LINK_PENDING'
    requirements_ref = pin(STAGE_ROOT / 'requirements.json', REQUIREMENTS_SHA)
    requirements = json.loads(sealed_bytes(requirements_ref))
    current = {key(row['path']): sealed(row) for row in audit['production_sources']}
    assert len(current) == 4
    added = key(PROJECT / 'Source/Host/UiPanelRepaint.h')
    changed = set(current) - {added}
    old_compiler = {key(row['original_path']): row for row in base['compiler_inputs']}
    assert len(changed) == 3 and changed <= set(old_compiler) and added not in old_compiler
    revisions = []
    for item in requirements['baseline_sources'][:3]:
        before = item['before']
        assert key(before['path']) in changed
        parent = old_compiler[key(before['path'])]
        assert (parent['bytes'], parent['sha256']) == (before['bytes'], before['sha256'])
        sealed(item['backup'])
        raw = gzip.decompress(Path(item['backup']['path']).read_bytes())
        assert (len(raw), hashlib.sha256(raw).hexdigest()) == (before['bytes'], before['sha256'])
        revisions.append(dict(before=dict(original_path=before['path'], bytes=before['bytes'], sha256=before['sha256']),
                              backup=item['backup'], after=current[key(before['path'])]))
    live = {}
    for row in base['current_source_inputs']:
        expected = current.get(key(row['path']), row)
        live[key(row['path'])] = sealed(expected)
    live[added] = current[added]
    assert len(live) == 593
    donors = {}
    for group in ('compiler_inputs', 'sources', 'provider_inputs', 'system_libraries', 'implicit_libraries', 'build_tools'):
        for row in base[group]:
            assert inside(row['path'], PARENT_ROOT / 'frozen')
            donors[key(row['path'])] = sealed(row)
    for row in [*base['provider_reports'].values(), base['shared_lua_build'], base['ui_assets']]:
        assert inside(row['path'], PARENT_ROOT / 'frozen')
        donors[key(row['path'])] = sealed(row)
    assert len(donors) == 592
    cleanup_plan = pin(STAGE_ROOT / 'cleanup_plan.json',
                       'e408298ba15ba4e5559753db1c8d1a431fabe26f0573a830aed4d610c7be67fc')
    protected = [sealed(row) for row in json.loads(sealed_bytes(cleanup_plan))['protected']]
    assert len(protected) == 38
    for relative, expected in (
        ('evidence/save_menu/20261013_original_screen/current_progress.json', '4663a1c628911d8a530d04a620bc0a849713ece41c4cc1b8c12622fe32ee0441'),
        ('docs/ORIGINAL_WORLD_HUD.md', '6b4e39786f6916ca2179a07e4f6780d8f25e59417502662ebb498be23c3a4bb0'),
        ('evidence/original_world_hud/pair_preparation/execution/screen_verification_deferred.json', '8751696cbd8c3728f5a465b9556ad0e0e71a7418d89bc20cfa036da698ac1523')):
        protected.append(pin(PROJECT / relative, expected))
    tools = [sealed(base[name]) for name in ('compiler', 'linker', 'dumpbin')]
    toolchain_inputs = [sealed(row) for row in base['protected_artifacts']
                        if Path(row['path']).name.casefold() in ('c1xx.dll', 'c2.dll', 'cmd.exe')]
    assert {Path(row['path']).name.casefold() for row in toolchain_inputs} == {'c1xx.dll', 'c2.dll', 'cmd.exe'}
    vcvars = pin(Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat'),
                 next(row['sha256'] for row in base['protected_artifacts'] if Path(row['path']).name.casefold() == 'vcvars64.bat'))
    helper = load_pure(PROJECT / 'tools/build_native_restore_host.py',
                       '07f50b1ab7482591792b44cc8767f27c709884f5f487b0eada7459f28c8da558', 'hover_build_functions')
    parser = load_pure(PROJECT / 'evidence/goody_hut/owned_fonts/verify_candidate.py',
                       '723e8d4594ce148336149f34c2ee535512c14ad283165b4fd729473eb302123f', 'hover_build_static_pe')
    generated = pin(PROJECT / 'Source/Host/UiPopupAssets.generated.h',
                    '333cf40c942e2545c83372084ed276e2aec11ab9fd7cbf4744f8c0c4e7c48da9')
    arrays, order = parser.parse_catalog(sealed_bytes(generated))
    parent_pe = parser.PE(sealed_bytes(base['executable']))
    assert helper.catalog_summary(parent_pe.catalog(arrays, order)) == base['catalog']
    assert set(parent_pe.imports()) == set(base['imports']['dependencies'])
    assert len(parent_pe.occurrences(MARKER)) == 1
    units = base['final_compilation']['translation_units']
    assert tuple(row['translation_unit'] for row in units) == UNITS
    old_paths, response_texts = {}, {}
    for row in units:
        sealed(row['response']); sealed(row['dependency_report'])
        paths, _ = dependency_paths(row['dependency_report']['path'])
        old_paths[row['translation_unit']] = paths
        response_texts[row['translation_unit']] = sealed_bytes(row['response']).decode('utf-8-sig')
        assert not Path(row['object']['path']).exists(), 'Parent objects were already retired'
    assert set.union(*old_paths.values()) == {key(row['path']) for row in base['compiler_inputs']}
    sealed(base['link_response'])
    link_text = sealed_bytes(base['link_response']).decode('utf-8-sig')
    assert {row['name'].casefold() for row in base['implicit_libraries']} == LIBRARIES
    library_names = LIBRARIES | {Path(row['path']).name.casefold()
                                 for row in base['system_libraries'] + base['provider_inputs']}
    signature = hashlib.sha256((PARENT_SHA + '|' + AUDIT_SHA + '|' + REQUIREMENTS_SHA).encode('ascii')).hexdigest()[:20]
    stage = STAGE_ROOT / 'host_build' / signature
    identifier = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_') + signature[:12]
    build = PROJECT / 'Build/UiWindowHost' / identifier
    output = PROJECT / 'evidence/ui_window_host' / identifier
    for path in (stage, build, output):
        assert not os.path.lexists(path), 'Inspect the existing single-use attempt; never replay compilation'
    assert shutil.disk_usage(PROJECT).free >= 384 * 1024 * 1024
    if options.preflight:
        print(json.dumps(dict(status='PASS_HOVER_HOST_PREFLIGHT', signature=signature,
            current_source_count=593, compiler_dependency_count=550, source_manifest_count=86,
            planned_hardlinks=589, planned_copies=4, source_copy_bytes=sum(row['bytes'] for row in current.values()),
            planned_direct_children=7, created_files=0, child_commands=0, host_sdk_or_window_executed=False)))
        return

    roots = (stage, build, output)
    def writable(path):
        path = Path(path)
        assert any(inside(path, root) for root in roots), path
        for item in path.parents:
            if item.exists():
                assert not item.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT, item
        assert not os.path.lexists(path), path
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def write(path, value):
        with writable(path).open('x', encoding='utf-8', newline='\n') as stream:
            json.dump(value, stream, indent=2)
            stream.write('\n')

    def write_raw(path, value):
        with writable(path).open('xb') as stream:
            stream.write(value)

    def relocate(path):
        assert inside(path, PARENT_ROOT), path
        return build / Path(path).relative_to(PARENT_ROOT)

    def replace_root(text):
        result = text.replace(str(PARENT_ROOT), str(build)).replace(PARENT_ROOT.as_posix(), build.as_posix())
        assert str(PARENT_ROOT) not in result and PARENT_ROOT.as_posix() not in result
        return result

    for root in roots:
        root.mkdir(parents=True)
    completed, commands, materialized = [], [], {}
    started_path = stage / 'started.json'
    builder = artifact(__file__)
    write(started_path, dict(schema='zerosis.hover_host.started.v1', signature=signature, build_id=identifier,
        builder=builder, baseline_build=parent_ref, component_audit=audit_ref, requirements=requirements_ref,
        current_inputs=list(live.values()), frozen_donors=list(donors.values()), protected_runtime_inputs=protected,
        source_revisions=revisions, added_source=current[added], toolchain_inputs=toolchain_inputs,
        no_automatic_retry=True,
        host_sdk_or_window_execution_allowed=False))

    def freeze(row, original=None):
        target = relocate(row['path'])
        if key(target) in materialized:
            return materialized[key(target)]
        writable(target)
        expected = current[key(original)] if original and key(original) in current else row
        if original and key(original) in current:
            sealed(expected)
            raw = Path(original).read_bytes()
            assert hashlib.sha256(raw).hexdigest() == expected['sha256']
            write_raw(target, raw)
            os.chmod(target, stat.S_IREAD)
            method = 'owned_changed_source_copy'
        else:
            sealed(row)
            os.link(row['path'], target)
            method = 'attested_snapshot_hardlink'
        actual = artifact(target)
        assert (actual['bytes'], actual['sha256']) == (expected['bytes'], expected['sha256'])
        if method == 'attested_snapshot_hardlink':
            assert actual['file_identity'] == artifact(row['path'])['file_identity']
        else:
            assert actual['file_identity'] != expected['file_identity']
        value = {**row, **actual, 'materialization': method}
        value.pop('reused_from_path', None)
        if method == 'attested_snapshot_hardlink':
            value['reused_from_path'] = row['path']
        materialized[key(target)] = value
        return value

    def execute(command, cwd, log, phase, env=None):
        allowed = {key(tools[0]['path']), key(tools[1]['path']), key(Path(r'C:\Windows\System32\cmd.exe'))}
        assert key(command[0]) in allowed
        row = dict(command=[str(x) for x in command], cwd=str(cwd), phase=phase)
        commands.append(row)
        try:
            result = subprocess.run(row['command'], cwd=cwd, env=env, capture_output=True,
                timeout=300, creationflags=subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS)
        except subprocess.TimeoutExpired as error:
            partial = (error.stderr or b'') if phase == 'environment' else (error.stdout or b'') + (error.stderr or b'')
            write_raw(log, partial)
            row.update(error_type='TimeoutExpired', timed_out=True, log=artifact(log))
            raise
        except OSError as error:
            write_raw(log, (type(error).__name__ + ': ' + str(error)).encode('utf-8'))
            row.update(error_type=type(error).__name__, log=artifact(log))
            raise
        write_raw(log, result.stderr if phase == 'environment' else result.stdout + result.stderr)
        row.update(returncode=result.returncode, log=artifact(log))
        assert result.returncode == 0, str(log)
        assert phase == 'environment' or not re.search(rb'\bwarning\s+(?:C|LNK)\d+', result.stdout + result.stderr, re.I), str(log)
        return result

    try:
        compiler_inputs = [freeze(row, row['original_path']) for row in base['compiler_inputs']]
        new_row = dict(current[added], path=str(PARENT_ROOT / 'frozen/include_roots/project/Source/Host/UiPanelRepaint.h'),
                       original_path=str(PROJECT / 'Source/Host/UiPanelRepaint.h'), root_name='project',
                       relative_path='Source\\Host\\UiPanelRepaint.h')
        added_frozen = freeze(new_row, new_row['original_path'])
        compiler_inputs.append(added_frozen)
        sources = [{**freeze(row, row['original_source']), 'original_source': row['original_source']} for row in base['sources']]
        sources.append({**added_frozen, 'original_source': new_row['original_path']})
        providers, systems, build_tools, implicit = ([freeze(row) for row in base[group]] for group in (
            'provider_inputs', 'system_libraries', 'build_tools', 'implicit_libraries'))
        provider_reports = {name: freeze(row) for name, row in base['provider_reports'].items()}
        assets, shared_lua = freeze(base['ui_assets']), freeze(base['shared_lua_build'])
        assert len(materialized) == 593
        copies = [row for row in materialized.values() if row['materialization'] == 'owned_changed_source_copy']
        assert len(copies) == 4 and sum(row['bytes'] for row in copies) == 420065
        environment_script = build / 'read_build_environment.cmd'
        write_raw(environment_script, ('@echo off\ncall "' + vcvars['path'] + '" >nul\nif errorlevel 1 exit /b %errorlevel%\nset\n').encode('ascii'))
        raw_env = execute([str(Path(r'C:\Windows\System32\cmd.exe')), '/d', '/c', str(environment_script)],
                          build, stage / 'environment.stderr.log', 'environment')
        env = os.environ.copy()
        for line in raw_env.stdout.decode('mbcs').splitlines():
            if '=' in line and not line.startswith('='):
                name, value = line.split('=', 1)
                env[name] = value
        env.update({name: replace_root(value) for name, value in base['final_environment'].items()})
        (build / 'tmp').mkdir()
        closure = {key(row['path']) for row in compiler_inputs}
        union = set()
        for index, (unit, stem, parent) in enumerate(zip(UNITS, STEMS, units)):
            response = relocate(parent['response']['path'])
            write_raw(response, replace_root(response_texts[unit]).encode('utf-8'))
            (response.parent / 'obj').mkdir()
            execute([tools[0]['path'], '@' + str(response)], response.parent,
                    stage / ('compile_' + unit + '.log'), 'compile_' + unit, env)
            dependency = relocate(parent['dependency_report']['path'])
            actual, visits = dependency_paths(dependency)
            expected = {key(relocate(path)) for path in old_paths[unit]}
            if index == 0:
                expected.add(key(added_frozen['path']))
            assert actual == expected and actual <= closure and len(actual) == COUNTS[index], unit
            union.update(actual)
            obj = response.parent / 'obj' / (stem + '.obj')
            raw = obj.read_bytes()
            coff, defaults = parser.coff(raw), helper.object_defaults(raw)
            assert coff['machine_hex'] == '0x8664' and set(defaults) <= library_names
            record = dict(translation_unit=unit, response=artifact(response), dependency_report=artifact(dependency),
                object=artifact(obj), log=artifact(stage / ('compile_' + unit + '.log')), returncode=0,
                actual_dependency_count=len(actual), expected_dependency_count=len(expected), dependency_visits=visits,
                default_libraries=defaults, coff_machine=coff['machine_hex'])
            completed.append(record)
            write(stage / ('compiled_' + unit + '.json'), record)
            print(json.dumps(dict(phase='compiled', translation_unit=unit, object_bytes=record['object']['bytes'])), flush=True)
        assert union == closure and len(union) == 550 and len(sources) == 86
        link_response = relocate(base['link_response']['path'])
        rewritten = replace_root(link_text)
        object_paths = re.findall(r'^"([^"\n]+\.obj)"$', rewritten.replace('\r\n', '\n'), re.I | re.M)
        assert [key(path) for path in object_paths] == [key(row['object']['path']) for row in completed]
        write_raw(link_response, rewritten.encode('utf-8'))
        execute([tools[1]['path'], '@' + str(link_response)], link_response.parent, stage / 'link.log', 'link', env)
        executable, mapfile = relocate(base['executable']['path']), relocate(base['map']['path'])
        pe = parser.PE(executable.read_bytes())
        catalog = helper.catalog_summary(pe.catalog(arrays, order))
        for name in ('entry_count', 'stride', 'total_payload_bytes', 'ordered_payload_manifest_sha256'):
            assert catalog[name] == base['catalog'][name]
        imports = pe.imports()
        assert len(imports) == len(set(imports)) == 24 and set(imports) == set(base['imports']['dependencies'])
        markers = pe.occurrences(MARKER)
        assert len(markers) == 1
        map_text = mapfile.read_text(encoding='mbcs')
        mapped = {match.casefold().removesuffix('.lib') + '.lib' for match in re.findall(
            r'\s([\w.-]+):\S+\.(?:obj|dll)\s*$', map_text, re.I | re.M)}
        assert mapped <= library_names
        for row in [*live.values(), *donors.values(), *protected, *tools, *toolchain_inputs, vcvars, parent_ref, audit_ref, requirements_ref,
                    *materialized.values(), *[row['object'] for row in completed]]:
            sealed(row)
        assert len(commands) == 7 and all(row['returncode'] == 0 for row in commands)
        imports_path = stage / 'imports.static.json'
        write(imports_path, dict(source='PURE_FILE_BACKED_PE_IMPORT_DIRECTORY', dependencies=imports, image=artifact(executable)))
        by_original = {key(row['original_source']): row for row in sources}
        report = dict(schema=base['schema'], status='UI_WINDOW_HOST_CANDIDATE_BUILT', build_id=identifier,
            baseline_build=parent_ref, profile=audit_ref, hover_repaint_builder=builder, hover_repaint_component=audit_ref,
            native_restore_contract_component=base['native_restore_contract_component'],
            compiler=tools[0], linker=tools[1], dumpbin=tools[2], compiler_version=base['compiler_version'],
            toolchain=base['toolchain'], definitions=base['definitions'], system_include_roots=base['system_include_roots'],
            compiler_inputs=compiler_inputs, compiler_dependency_count=550, sources=sources,
            window_sources=[by_original[key(row['original_source'])] for row in base['window_sources']],
            provider_inputs=providers, system_libraries=systems, libraries=providers + systems,
            system_library_names=base['system_library_names'], implicit_libraries=implicit,
            implicit_libraries_before=base['implicit_libraries'], implicit_libraries_after=implicit,
            actual_implicit_library_namesfrommap=sorted(mapped & LIBRARIES), build_tools=build_tools,
            provider_reports=provider_reports, shared_lua_build=shared_lua, ui_assets=assets,
            ui_asset_preparation=dict(executed=False, status='UNCHANGED_ATTESTED_67_PAYLOAD_CATALOG_REUSED'),
            dependency_discovery=dict(executed=False, reason='Exact parent closure plus the one current-syntax-attested header'),
            final_compilation=dict(translation_units=completed),
            final_dependency_reports={row['translation_unit']: row['dependency_report'] for row in completed},
            response=completed[0]['response'], dependency_report=completed[0]['dependency_report'],
            link_response=artifact(link_response), link_log=artifact(stage / 'link.log'), map=artifact(mapfile),
            executable={**artifact(executable), 'pe': dict(architecture='x64', pe_format='PE32+', is_dll=False)},
            imports=dict(dependencies=imports, log=artifact(imports_path), source='PURE_PYTHON_STATIC_PE'),
            catalog=catalog, restore_contract_marker=dict(ascii=MARKER.decode('ascii'), rva=markers[0], inclusion_evidence_only=True),
            current_source_inputs=list(live.values()), protected_artifacts=protected, started=artifact(started_path),
            prepared_runtime_inputs=protected[:24], sources_changed_from_baseline=[current[path] for path in sorted(changed)],
            new_source_inputs=[current[added]], source_revision_provenance=revisions,
            final_environment={name: env.get(name, '') for name in base['final_environment']},
            frozen_input_reuse=dict(hardlinked_files=589, copied_files=4, copied_source_bytes=420065,
                donor_content_and_metadata_preserved=True),
            scope='Five current Host object compilations and one offline x64 link; no native Host/game execution.',
            source_inputs_unchanged=True, provider_inputs_unchanged=True, host_runtime_executed=False,
            gamecore_loaded=False, sdk_linked=False, mods_updated=False, stage_updated=False, default_promoted=False,
            sdk_restore_verified=False, native_restore_approved=False, full_engine_goal_complete=False)
        report_path = output / 'build_result.json'
        write(report_path, report)
        run = dict(schema='zerosis.hover_host.run.v1', status='PASS_CURRENT_HOVER_HOST_BUILD_ONLY',
            utc=datetime.now(timezone.utc).isoformat(), signature=signature, build_id=identifier, builder=builder,
            baseline_build=parent_ref, component_audit=audit_ref, started=artifact(started_path),
            build_result=artifact(report_path), commands=commands, compilation=completed,
            current_inputs=list(live.values()), materialized=list(materialized.values()), frozen_donors=list(donors.values()),
            protected_runtime_inputs=protected, actual_dependency_counts=list(COUNTS),
            host_sdk_or_window_executed=False, no_automatic_retry=True, full_engine_goal_complete=False)
        write(stage / 'run.json', run)
        print(json.dumps(dict(status=run['status'], run=artifact(stage / 'run.json'),
                              build_id=identifier, executable=artifact(executable))), flush=True)
    except BaseException as error:
        write(stage / 'failure.json', dict(status='FAILED_DO_NOT_REPLAY', error=type(error).__name__ + ': ' + str(error),
            commands=commands, completed_translation_units=completed, build_id=identifier,
            compilation_retry_allowed=False, host_sdk_or_window_executed=False))
        raise


if __name__ == '__main__':
    main()
