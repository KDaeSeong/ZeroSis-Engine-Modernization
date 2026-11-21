"""Exercise exact overwrite queue/handoff methods with SDK/Lua/storage mocks.

This is a bounded no-GameCore native component. It never opens a real save,
creates a window, launches a Host, or reads retail MODS/settings/processes.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'tools'))
from collect_baseline import pe_header
from native_build import environment_for, run
from verify_bitmap_window import run_owned_test
from load_menu_native_handoff import block

POPUP = PROJECT / 'Source/Host/UiPopupContext.h'
SESSION = PROJECT / 'Source/Host/InteractiveGameSession.h'
CONTRACTS = [PROJECT / 'Source/Host' / name for name in ('UiSaveMenuContract.h', 'UiLoadMenuContract.h')]
TEMPLATE = Path(__file__).with_suffix('.cpp.in')
SOURCES = [POPUP, SESSION, *CONTRACTS, TEMPLATE, Path(__file__)]
VS = Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community')
BUILD_ROOT = PROJECT / 'Build/OwnedSaveOverwriteHandoff'


def seal(path):
    data = path.read_bytes()
    return {'path': str(path), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def generate():
    popup = POPUP.read_text(encoding='utf8')
    session = SESSION.read_text(encoding='utf8')
    markers = {
        'REQUIRE': 'void Require() const',
        'LOCAL_OWNER': 'void RequireLocalMenuPlayer(int owner,int turn){',
        'OWNED_OWNER': 'void RequireOwnedMenuPlayer(){',
        'SAVE_OWNER': 'void RequireSaveMenuOwner(){',
        'IS_DELETED': 'bool IsDeletedMenuFile(const std::string& path) const',
        'FIND_SAVE': 'const UiSaveMenuFile& FindSaveMenuFile(const char* path){',
        'QUEUE_SAVE': 'void QueueSaveMenuRequest(SaveMenuRequest::Kind kind,const char* name){',
        'QUEUE_OVERWRITE': 'void QueueSaveMenuOverwrite(const char* name,const char* listedPath){',
        'TAKE_SAVE': 'std::vector<SaveMenuRequest> TakeSaveMenuRequests(){',
        'FAULT': 'void Fault() noexcept',
        'UTF8_NEXT': 'static std::size_t Utf8Next(const char* text,std::size_t bytes,std::size_t offset){',
        'UTF8_LENGTH': 'static std::size_t Utf8Length(const char* text){',
        'TEXT': 'static const char* Text(lua_State* state,int index){',
    }
    fragments = {name: block(popup, marker) for name, marker in markers.items()}
    native = block(popup, 'static int Native(lua_State* state){')
    fragments['NATIVE_SUPPORTED'] = block(native, 'if(std::strcmp(operation,"saveMenuOverwriteSupported")==0){')
    fragments['NATIVE_OVERWRITE'] = block(native, 'if(std::strcmp(operation,"saveMenuOverwrite")==0){')
    dispatch = block(popup, 'bool DispatchInput(UiInputKind kind,std::uint64_t key,double delta=0.0){')
    fragments['DISPATCH_SAVE'] = block(dispatch, 'if(kind_==UiPopupKind::SaveMenu){')
    for name, marker in {
        'OWNER': 'void Owner() const',
        'HUMAN_RAW': 'bool HumanTurnRaw(){',
        'HUMAN': 'bool HumanTurn(){',
        'SAVE_ORDINARY': 'std::wstring Save(){',
        'SAVE_NAMED': 'std::wstring SaveNamed(const std::string& name){',
        'SAVE_OVERWRITE': 'NativeSaveCatalog::ReplacementResult SaveNamedOverwrite(const SaveMenuRequest& request){',
        'APPLY_SAVE': 'void ApplySaveMenuRequests(const std::vector<SaveMenuRequest>& requests){',
    }.items():
        fragments[name] = block(session, marker)
    fragments['AUTOSAVE_BIND'] = block(session, 'host_.autoSave=[this,nativeAutoSave](bool initial,bool postTurn){')
    rendered = TEMPLATE.read_text(encoding='utf8')
    for name, value in fragments.items():
        token = '@@' + name + '@@'
        if rendered.count(token) != 1:
            raise RuntimeError('Template extraction slot differs: ' + token)
        rendered = rendered.replace(token, value)
    if '@@' in rendered or re.search(r'\b(?:LoadLibrary[A-Za-z]*|GetProcAddress)\s*\(', rendered):
        raise RuntimeError('Unresolved slot or dynamic loader in bounded extracted component')
    return rendered, {name: {'bytes': len(value.encode('utf8')),
                            'sha256': hashlib.sha256(value.encode('utf8')).hexdigest()}
                      for name, value in fragments.items()}


def cleanup_generated(build, destination):
    if build.parent.resolve(strict=True) != BUILD_ROOT.resolve(strict=True) or \
            not re.fullmatch(r'\d{8}T\d{6}Z_[0-9a-f]{12}', build.name):
        raise RuntimeError('Cleanup target escaped the exact owned component Build root')
    if destination.exists():
        raise RuntimeError('Refusing to overwrite an existing component cleanup receipt')
    rows, directories = [], []
    for parent, child_dirs, children in os.walk(build, topdown=True, followlinks=False):
        for path in [Path(parent), *(Path(parent) / name for name in child_dirs)]:
            info = path.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_file_attributes & 0x400:
                raise RuntimeError('Cleanup encountered an unexpected directory or reparse point')
        directories.append(Path(parent))
        for name in children:
            path = Path(parent) / name
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_file_attributes & 0x400 or info.st_nlink != 1:
                raise RuntimeError('Cleanup encountered a nonordinary or multiply-linked generated file')
            rows.append({**seal(path), 'device': info.st_dev, 'file_id': info.st_ino,
                         'mtime_ns': info.st_mtime_ns, 'attributes': info.st_file_attributes})
    report = {'schema': 'zerosis.owned_save_overwrite_handoff_cleanup.v1', 'status': 'PLANNED',
              'root': str(build), 'files': rows, 'file_count': len(rows), 'removed': 0,
              'logical_bytes_removed': 0, 'physical_allocation_measured': False}

    def checkpoint():
        destination.write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')

    checkpoint()
    for row in rows:
        path = Path(row['path'])
        info = path.lstat()
        if (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_file_attributes, info.st_nlink) != \
                (row['device'], row['file_id'], row['bytes'], row['mtime_ns'], row['attributes'], 1) or \
                seal(path)['sha256'] != row['sha256']:
            report['status'] = 'PARTIAL_INPUT_CHANGED'
            checkpoint()
            raise RuntimeError('Generated cleanup input changed after attestation')
        path.unlink()
        report['removed'] += 1
        report['logical_bytes_removed'] += row['bytes']
    for path in reversed(directories):
        path.rmdir()
    report['status'] = 'COMPLETE'
    checkpoint()
    return report


def retire_references(value, retired):
    if isinstance(value, dict):
        if value.get('path') in retired:
            value['original_path'] = value.pop('path')
            value['generated_artifact_retired'] = True
        for child in list(value.values()):
            retire_references(child, retired)
    elif isinstance(value, list):
        for child in value:
            retire_references(child, retired)


def main():
    before = [seal(path) for path in SOURCES]
    source, fragments = generate()
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '_' + secrets.token_hex(6)
    build = BUILD_ROOT / run_id
    evidence = PROJECT / 'evidence/save_overwrite/native_handoff' / run_id
    build.mkdir(parents=True, exist_ok=False)
    evidence.mkdir(parents=True, exist_ok=False)
    generated = build / 'handoff.cpp'
    generated.write_text(source, encoding='utf8')
    retained = evidence / 'extracted_production.cpp.txt'
    retained.write_bytes(generated.read_bytes())
    contracts = build / 'contracts'
    contracts.mkdir()
    report = {'schema': 'zerosis.extracted_owned_save_overwrite_handoff.v1', 'status': 'IN_PROGRESS',
              'run_id': run_id, 'sources': before, 'extracted_fragments': fragments,
              'generated_source': seal(generated), 'retained_extracted_source': seal(retained),
              'runs': [], 'contract_inputs': [],
              'sdk_lua_modal_archive_capture_and_storage_mocked': True,
              'actual_host_gamecore_or_hwnd_executed': False, 'actual_save_files_accessed': False,
              'actual_native_replacement_service_executed': False, 'retail_files_accessed': False,
              'scope': 'Exact production SaveMenu queue, native arity/text dispatch, callback handoff, owner/turn/UTF-8 guards, independent observation lifetime, and Session Apply/SaveNamedOverwrite result handling. SDK, Lua execution, original parent/child modal calls, archive capture and NativeSaveCatalog replacement are explicit mocks. This is not real-file, game, UI or runtime acceptance.'}
    destination = evidence / 'result.json'

    def checkpoint():
        destination.write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')

    checkpoint()
    try:
        for path in CONTRACTS:
            frozen = contracts / path.name
            frozen.write_bytes(path.read_bytes())
            retained_contract = evidence / (path.name + '.txt')
            retained_contract.write_bytes(frozen.read_bytes())
            report['contract_inputs'].append({'source': seal(path), 'frozen': seal(frozen), 'retained': seal(retained_contract)})
        env, compiler = environment_for(VS, 'x64', build)
        env['VSLANG'] = '1033'
        report['compiler'] = seal(Path(compiler))
        for flavor, optimization in (('optimized', '/O2'), ('unoptimized', '/Od')):
            directory = build / flavor
            directory.mkdir()
            executable, dependencies = directory / 'handoff.exe', directory / 'dependencies.json'
            arguments = [compiler, '/nologo', '/std:c++14', '/EHsc', '/W4', '/WX', '/MT', optimization,
                         '/source-charset:utf-8', '/D_CRT_SECURE_NO_WARNINGS', '/I' + str(contracts), str(generated),
                         '/Fo' + str(directory) + '\\', '/Fe' + str(executable), '/sourceDependencies', str(dependencies),
                         '/link', '/INCREMENTAL:NO', '/MACHINE:X64', '/Brepro', '/WX', 'wer.lib']
            row = {'flavor': flavor, 'optimization': optimization, 'status': 'COMPILING'}
            report['runs'].append(row)
            checkpoint()
            compiled = run(arguments, cwd=directory, env=env, timeout=180)
            transcript = (compiled.stdout + compiled.stderr).decode('mbcs', errors='replace')
            compile_log = evidence / (flavor + '_compile.log')
            compile_log.write_text(transcript, encoding='utf8')
            row.update(compiler_exit_code=compiled.returncode, compile_log=seal(compile_log))
            checkpoint()
            if compiled.returncode or re.search(r'\bwarning\s+[A-Z]+\d+', transcript, re.I):
                raise RuntimeError(f'{flavor} compile failed or warned: {compile_log}\n{transcript[-2500:]}')
            if [seal(path) for path in SOURCES] != before:
                raise RuntimeError('A sealed overwrite source changed during compilation')
            imported = run([str(Path(compiler).with_name('dumpbin.exe')), '/nologo', '/imports', str(executable)],
                           cwd=directory, env=env, timeout=30)
            imports = (imported.stdout + imported.stderr).decode('mbcs', errors='replace')
            imports_log = evidence / (flavor + '_imports.log')
            imports_log.write_text(imports, encoding='utf8')
            dlls = sorted(set(re.findall(r'^\s*([A-Za-z0-9_.-]+\.dll)\s*$', imports, re.M | re.I)), key=str.lower)
            if imported.returncode or not dlls or any(re.search(r'gamecore|zerosis|lua|user32|d3d|dxgi', name, re.I) for name in dlls):
                raise RuntimeError('Bounded fixture imports a forbidden or unverified module')
            pe = pe_header(executable)
            if pe['architecture'] != 'x64':
                raise RuntimeError('Unexpected native fixture PE architecture')
            row.update(status='RUNNING', executable=seal(executable), dependencies=seal(dependencies),
                       imports=dlls, imports_log=seal(imports_log), pe=pe)
            checkpoint()
            execution = run_owned_test([str(executable)], cwd=directory, env=env, timeout=30)
            runtime = (execution.pop('stdout') + execution.pop('stderr')).replace('\r\n', '\n')
            runtime_log = evidence / (flavor + '_execution.log')
            runtime_log.write_text(runtime, encoding='utf8')
            row.update(execution=execution, execution_log=seal(runtime_log))
            checkpoint()
            markers = re.findall(r'^OWNED_SAVE_OVERWRITE_HANDOFF_PASS cases=(\d+) checks=(\d+) GAMECORE_ACTUAL_LOADED=false HWND_CREATED=false FILESYSTEM_MUTATED=false$', runtime, re.M)
            case_names = re.findall(r'^OVERWRITE_HANDOFF_CASE_PASS=(.+)$', runtime, re.M)
            if execution['returncode'] or execution['timed_out'] or len(markers) != 1 or \
                    runtime.splitlines().count('FAULT_UI_SUPPRESSED ERROR_MODE=32771 WER_FLAGS=32') != 1:
                raise RuntimeError(f'{flavor} extracted overwrite test failed: {runtime_log}\n{runtime[-2500:]}')
            case_count, check_count = map(int, markers[0])
            if case_count != 54 or len(set(case_names)) != case_count or len(case_names) != case_count or check_count < case_count:
                raise RuntimeError('Bounded overwrite case coverage changed')
            row.update(status='PASS', cases=case_count, checks=check_count, case_names=case_names,
                       compiler_and_linker_warnings=0)
            checkpoint()
        if [seal(path) for path in SOURCES] != before:
            raise RuntimeError('A sealed overwrite source changed during execution')
        if len({(row['cases'], row['checks']) for row in report['runs']}) != 1:
            raise RuntimeError('Optimization variants exercised different cases/checks')
        report.update(status='PASS', total_checks=sum(row['checks'] for row in report['runs']),
                      sources_after=[seal(path) for path in SOURCES])
    except Exception as error:
        report.update(status='FAIL', error=str(error))
    finally:
        try:
            cleanup = cleanup_generated(build, evidence / 'cleanup.json')
            report['cleanup'] = seal(evidence / 'cleanup.json')
            report['generated_files_removed'] = cleanup['removed']
            report['generated_logical_bytes_removed'] = cleanup['logical_bytes_removed']
            retire_references(report, {row['path'] for row in cleanup['files']})
        except Exception as error:
            report.update(status='FAIL', cleanup_error=str(error))
        checkpoint()
    print(json.dumps({'status': report['status'], 'cases_per_flavor': report['runs'][0].get('cases') if report['runs'] else None,
                      'checks_per_flavor': report['runs'][0].get('checks') if report['runs'] else None,
                      'total_checks': report.get('total_checks'), 'report': seal(destination),
                      'generated_files_removed': report.get('generated_files_removed'),
                      'generated_logical_bytes_removed': report.get('generated_logical_bytes_removed'),
                      'error': report.get('error'), 'cleanup_error': report.get('cleanup_error')}))
    if report['status'] != 'PASS':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
