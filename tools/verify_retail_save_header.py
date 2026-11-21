"""Compile and execute only the portable retail metadata-prefix component."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys

sys.dont_write_bytecode = True
PROJECT = Path(__file__).absolute().parents[1]
STAGE = PROJECT / 'evidence/retail_save_container/header_prefix'
REPORT = STAGE / 'build_result.json'
SOURCE = PROJECT / 'Tests/retail_save_header.cpp'
HEADER = PROJECT / 'Source/Host/RetailSaveHeader.h'
VS = Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community')
COMPILER = VS / 'VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64/cl.exe'
COMPILER_SHA = '8a547dfca2d7df1b6be1e2d212132c1b3b5a661caf5b2ecce481e21b3c1860a6'


def require(value, message):
    if not value:
        raise RuntimeError(message)


def artifact(path):
    path = Path(path)
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return dict(path=str(path), bytes=path.stat().st_size, sha256=digest)


def key(path):
    return os.path.normcase(os.path.abspath(path))


def within(path, root):
    return key(path) == key(root) or key(path).startswith(key(root) + os.sep)


def pe_imports(path):
    data = path.read_bytes()
    pe = struct.unpack_from('<I', data, 0x3c)[0]
    require(data[pe:pe+4] == b'PE\0\0', 'Component is not a PE file')
    machine, sections = struct.unpack_from('<HH', data, pe+4)
    optional_size = struct.unpack_from('<H', data, pe+20)[0]
    optional = pe+24
    require(machine == 0x8664 and struct.unpack_from('<H', data, optional)[0] == 0x20b,
            'Component is not AMD64 PE32+')
    import_rva, import_size = struct.unpack_from('<II', data, optional+120)
    table = optional+optional_size

    def offset(rva):
        for i in range(sections):
            virtual_size, virtual_rva, raw_size, raw = struct.unpack_from('<IIII', data, table+i*40+8)
            if virtual_rva <= rva < virtual_rva+max(virtual_size, raw_size):
                delta = rva-virtual_rva
                require(delta < raw_size and raw+delta < len(data), 'Invalid component import RVA')
                return raw+delta
        raise RuntimeError('Unmapped component import RVA')

    require(import_rva and import_size >= 20, 'Component has no bounded import directory')
    imports = []
    at = offset(import_rva)
    for _ in range(import_size//20):
        row = struct.unpack_from('<IIIII', data, at)
        if not any(row):
            break
        start = offset(row[3])
        end = data.find(b'\0', start, min(start+260, len(data)))
        require(end != -1, 'Unterminated component import name')
        name = data[start:end].decode('ascii').lower()
        require(name in {'kernel32.dll', 'ntdll.dll'} or name.startswith('api-ms-win-crt-'),
                'Unexpected non-headless component dependency: '+name)
        imports.append(name)
        at += 20
    else:
        raise RuntimeError('Unterminated component import table')
    return sorted(set(imports))


def main():
    require(len(sys.argv) == 1 and not sys.flags.optimize, 'Unexpected component verification invocation')
    from native_build import environment_for, run
    from collect_baseline import pe_header
    fixtures = json.loads((STAGE/'fixtures.json').read_text(encoding='utf-8'))
    require(fixtures['status'] == 'PASS_PUBLIC_PREFIX_FIXTURES' and
            fixtures['user_save_accessed'] is False and len(fixtures['fixtures']) == 2,
            'The two immutable public prefix fixtures are required')
    fixture_paths = [PROJECT/'Tests/Fixtures/RetailSaveHeader'/name for name in ('bnw_279.prefix', 'community_patch.prefix')]
    for path, row in zip(fixture_paths, fixtures['fixtures']):
        require(artifact(path) == row['retained_prefix'] and row['full_blob_verified_in_memory'] is True and
                row['full_file_retained'] is False, 'Public fixture identity changed')
    upstream = json.loads((STAGE/'upstream.json').read_text(encoding='utf-8'))
    for row in upstream['files']:
        data = (PROJECT/row['local_path']).read_bytes()
        require(hashlib.sha1(b'blob '+str(len(data)).encode('ascii')+b'\0'+data).hexdigest() == row['git_blob_sha'],
                'Pinned reference source changed')
    inputs = [artifact(path) for path in (HEADER, SOURCE, Path(__file__).absolute(),
        PROJECT/'Source/Host/RetailSaveHeader.LICENSE.txt', PROJECT/'tools/native_build.py',
        PROJECT/'tools/collect_baseline.py', STAGE/'fixtures.json', STAGE/'upstream.json', *fixture_paths)]
    compiler = artifact(COMPILER)
    require(compiler['sha256'] == COMPILER_SHA, 'Reviewed x64 compiler changed')
    content_id = hashlib.sha256(json.dumps(dict(inputs=inputs,compiler=compiler),sort_keys=True).encode('utf-8')).hexdigest()[:16]
    build_root = PROJECT/'Build/RetailSaveHeader'/content_id
    require(build_root.is_relative_to(PROJECT/'Build/RetailSaveHeader'), 'Component build escaped its root')
    for part in (build_root, *build_root.parents):
        if part.exists():
            require(not part.lstat().st_file_attributes & 0x400, 'Reparse component build path')
    if REPORT.exists():
        old = json.loads(REPORT.read_text(encoding='utf-8'))
        require(old['status'] == 'PASS_X64_RETAIL_HEADER_COMPONENT' and old['inputs'] == inputs and old['compiler'] == compiler,
                'Preserve and inspect the previous result before rebuilding changed inputs')
        for result in old['results']:
            require(artifact(result['executable']['path']) == result['executable'], 'Retained component executable changed')
        print(json.dumps(dict(status=old['status'], reused=True, checks=[r['test']['checks'] for r in old['results']])))
        return
    require(not build_root.exists(), 'Inspect partial component build before retrying')
    protected_paths = [PROJECT/'Play/EarlyAccess/release.json',
        PROJECT/'evidence/save_menu/20261013_original_screen/current_progress.json',
        PROJECT/'evidence/goody_hut/runtime_fonts/preparation_identity_audit.json']
    protected = [artifact(path) for path in protected_paths]
    allowed, calls = set(), []
    setup = build_root/'read_build_environment.cmd'
    allowed.add(('cmd.exe', '/d', '/c', str(setup)))
    writable_reports = {key(STAGE/name) for name in ('build_started.json','build_result.json',
        'compile_O2.log','compile_Od.log','test_O2.log','test_Od.log')}

    def audit(event, args):
        if event == 'subprocess.Popen':
            if isinstance(args[1], str):
                command = next((item for item in allowed if subprocess.list2cmdline(item) == args[1]), None)
            else:
                command = tuple(str(x) for x in args[1])
            require(command in allowed, 'Unapproved component child command')
            require(args[0] is None or key(args[0]) == key(command[0]) or
                    Path(args[0]).name.casefold() == command[0].casefold() == 'cmd.exe',
                    'Component child executable override differs')
            calls.append(command)
        if event == 'open' and args and isinstance(args[0], (str, bytes, os.PathLike)):
            path = os.fsdecode(args[0])
            writing = isinstance(args[1], str) and any(c in args[1] for c in 'wax+') or (
                isinstance(args[2], int) and args[2] & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND))
            if writing:
                require(within(path, build_root) or key(path) in writable_reports, 'Component write escaped owned outputs')
        if event in ('os.remove','os.rmdir','os.mkdir','os.rename','os.chmod','os.link','os.symlink'):
            targets = args[:2] if event in ('os.rename','os.link','os.symlink') else args[:1]
            for target in targets:
                if isinstance(target, (str, bytes, os.PathLike)):
                    require(within(os.fsdecode(target), build_root), 'Component mutation escaped owned build root')
        if event.startswith(('ctypes.dlopen','socket.','urllib.','http.client.')) or event in ('os.system','os.startfile','os.startfile/2'):
            raise RuntimeError('Candidate loading, network or interactive execution is forbidden')

    # This is the sole shared parent creation; subsequent mutations stay in content_id.
    build_root.parent.mkdir(parents=True, exist_ok=True)
    sys.addaudithook(audit)
    build_root.mkdir()
    started = dict(schema='zerosis.retail_save.header_component_started.v1', utc=datetime.now(timezone.utc).isoformat(),
        build_root=str(build_root), inputs=inputs, compiler=compiler, protected=protected)
    with (STAGE/'build_started.json').open('x',encoding='utf-8') as stream:
        json.dump(started,stream,indent=2)
    results = []
    try:
        environment, actual_compiler = environment_for(VS, 'x64', build_root)
        require(key(actual_compiler) == key(COMPILER), 'Compiler selection differs')
        environment['VSLANG'] = '1033'
        for flavor, options in (('O2',['/O2']), ('Od',['/Od','/RTC1'])):
            directory = build_root/flavor
            directory.mkdir()
            exe, obj = directory/'RetailSaveHeaderTests.exe', directory/'retail_save_header.obj'
            response, deps = directory/'compile.rsp', directory/'dependencies.json'
            flags = ['/nologo','/std:c++17','/EHsc','/W4','/WX','/MT','/utf-8',*options,
                f'/I"{PROJECT / "Source/Host"}"',f'"{SOURCE}"',f'/Fo"{obj}"',f'/Fe"{exe}"',f'/sourceDependencies "{deps}"']
            response.write_text('\n'.join(flags)+'\n',encoding='utf-8')
            command = [str(COMPILER),'@'+str(response),'/link','/INCREMENTAL:NO','/MACHINE:X64','/Brepro','/WX','/OPT:REF','/OPT:ICF']
            allowed.add(tuple(command))
            build = run(command,cwd=directory,env=environment,timeout=120)
            output = (build.stdout+build.stderr).decode('mbcs',errors='replace')
            (STAGE/f'compile_{flavor}.log').write_text(output,encoding='utf-8')
            require(build.returncode == 0 and not re.search(r'\bwarning\s+[A-Z]+\d+', output, re.I),
                    'Component compile failed: '+flavor+'; inspect the bounded compile log')
            dependency = json.loads(deps.read_text(encoding='utf-8-sig'))['Data']
            require(key(dependency['Source']) == key(SOURCE) and any(key(x) == key(HEADER) for x in dependency['Includes']),
                    'Compiler did not consume the actual header/test')
            require(not any('sdk_bnw_x64' in key(x) for x in dependency['Includes']), 'Unexpected SDK dependency in pure component')
            imports = pe_imports(exe)
            command = [str(exe),*(str(x) for x in fixture_paths)]
            allowed.add(tuple(command))
            executed = run(command,cwd=directory,env=environment,timeout=45)
            transcript = (executed.stdout+executed.stderr).decode('utf-8',errors='replace').strip()
            (STAGE/f'test_{flavor}.log').write_text(transcript+'\n',encoding='utf-8')
            require(executed.returncode == 0, 'Actual component tests failed: '+flavor)
            test = json.loads(transcript)
            require(test['status'] == 'PASS_PUBLIC_PREFIX_COMPONENT' and test['fixtures'] == 2 and
                    test['checks'] >= 30 and test['mutations'] == 2048 and
                    test['truncations'] >= sum(path.stat().st_size for path in fixture_paths) and
                    test['accepted_mutations'] + test['rejected_mutations'] == 2048 and
                    test['gamecore_loaded'] is False and test['window_created'] is False and
                    test['input_files_unchanged'] is True,
                    'Unexpected actual component test result')
            results.append(dict(flavor=flavor,executable=artifact(exe),object=artifact(obj),pe=pe_header(exe),
                imports=imports,dependency_report=artifact(deps),compiler_input_count=1+len(dependency['Includes']),
                response=artifact(response),compile_log=artifact(STAGE/f'compile_{flavor}.log'),
                test_log=artifact(STAGE/f'test_{flavor}.log'),test=test))
        require(inputs == [artifact(r['path']) for r in inputs] and protected == [artifact(r['path']) for r in protected],
                'Inputs or ready runtime/default identity changed during component tests')
        retired = []
        for result in results:
            row = result['object'];path = Path(row['path'])
            require(artifact(path) == row and within(path,build_root), 'Unexpected object cleanup target')
            path.unlink();retired.append(row)
        require(setup.parent == build_root, 'Unexpected environment setup cleanup path')
        setup_ref = artifact(setup);setup.unlink();retired.append(setup_ref)
        result = dict(schema='zerosis.retail_save.header_component.v1',status='PASS_X64_RETAIL_HEADER_COMPONENT',
            utc=datetime.now(timezone.utc).isoformat(),inputs=inputs,compiler=compiler,build_root=str(build_root),
            results=results,protected=protected,protected_unchanged=True,child_commands=[list(x) for x in calls],
            retired_intermediates=retired,retired_logical_bytes=sum(x['bytes'] for x in retired),
            user_save_accessed=False,host_gamecore_or_hwnd_executed=False,
            metadata_prefix_only=True,compressed_framing_or_sdk_restore_verified=False,integrated_into_current_host=False,
            full_engine_goal_complete=False)
        with REPORT.open('x',encoding='utf-8') as stream:
            json.dump(result,stream,indent=2)
        print(json.dumps(dict(status=result['status'],checks=[x['test']['checks'] for x in results],
            modes=2,retired_intermediates=len(retired),report=artifact(REPORT))))
    except BaseException as error:
        failure = dict(status='FAILED_X64_RETAIL_HEADER_COMPONENT',error=type(error).__name__+': '+str(error),
            inputs=inputs,compiler=compiler,build_root=str(build_root),completed_modes=results,
            child_command_count=len(calls),protected_unchanged=protected==[artifact(r['path']) for r in protected])
        with REPORT.open('x',encoding='utf-8') as stream:
            json.dump(failure,stream,indent=2)
        raise


if __name__ == '__main__':
    main()
