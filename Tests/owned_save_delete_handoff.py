"""Run exact menu-deletion production methods with SDK/Lua/OS/service fixtures.

This component never loads Host/GameCore or creates an HWND. No game-process,
retail installation, MODS, save or settings enumeration occurs. Native file
deletion is covered separately by the NativeSaveCatalog boundary harness.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import secrets
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'tools'))
from collect_baseline import pe_header
from native_build import environment_for, run
from verify_bitmap_window import run_owned_test
from load_menu_native_handoff import block

SOURCE = PROJECT / 'Source/Host/UiPopupContext.h'
CONTRACTS = [PROJECT / 'Source/Host' / name for name in ('UiSaveMenuContract.h', 'UiLoadMenuContract.h')]
TEMPLATE = Path(__file__).with_suffix('.cpp.in')
VS = Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community')


def seal(path):
    data = path.read_bytes()
    return {'path': str(path), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def generate(popup):
    markers = {
        'REQUIRE': 'void Require() const',
        'LOCAL_OWNER': 'void RequireLocalMenuPlayer(int owner,int turn){',
        'OWNED_OWNER': 'void RequireOwnedMenuPlayer(){',
        'GAME_OWNER': 'void RequireGameMenuOwner(){',
        'SAVE_OWNER': 'void RequireSaveMenuOwner(){',
        'LOAD_OWNER': 'void RequireLoadMenuOwner(){',
        'IS_DELETED': 'bool IsDeletedMenuFile(const std::string& path) const',
        'FIND_SAVE': 'const UiSaveMenuFile& FindSaveMenuFile(const char* path){',
        'FIND_LOAD': 'const UiSaveMenuFile& FindLoadMenuFile(const char* path){',
        'SUPPORTED': 'bool MenuDeletionSupported(){',
        'CAN_DELETE': 'bool CanDeleteMenuFile(const UiSaveMenuFile& file){',
        'DELETE': 'void DeleteMenuFile(const char* path){',
        'CAN_LOAD': 'bool CanLoadMenuFile(const UiSaveMenuFile& file){',
        'QUEUE_LOAD': 'void QueueLoadMenuRequest(LoadMenuRequest::Kind kind,const char* path){',
        'QUEUE_SAVE': 'void QueueSaveMenuRequest(SaveMenuRequest::Kind kind,const char* name){',
        'HAS_LOAD': 'bool HasPendingLoadMenuRequests() const',
        'TAKE_LOAD': 'std::vector<LoadMenuRequest> TakeLoadMenuRequests(){',
        'TAKE_SAVE': 'std::vector<SaveMenuRequest> TakeSaveMenuRequests(){',
        'FAULT': 'void Fault() noexcept',
    }
    fragments = {name: block(popup, marker) for name, marker in markers.items()}
    dispatch = block(popup, 'bool DispatchInput(UiInputKind kind,std::uint64_t key,double delta=0.0){')
    fragments['DISPATCH_LOAD'] = block(dispatch, 'if(kind_==UiPopupKind::LoadMenu){')
    fragments['DISPATCH_SAVE'] = block(dispatch, 'if(kind_==UiPopupKind::SaveMenu){')
    close = block(popup, 'void CloseInformationalPopup(){')
    # Preserve the exact common prologue and complete LoadMenu/SaveMenu branches.
    # Unrelated popup kinds are outside this extracted component boundary.
    boundary = '        if(IsNotificationInputPanel()){'
    if close.count(boundary) != 1:
        raise RuntimeError('The production menu-close prefix changed its boundary')
    fragments['CLOSE_MENU_PREFIX'] = close[:close.index(boundary)] + '    }'
    rendered = TEMPLATE.read_text(encoding='utf8')
    for name, value in fragments.items():
        token = '@@' + name + '@@'
        if rendered.count(token) != 1:
            raise RuntimeError('Template extraction slot differs: ' + token)
        rendered = rendered.replace(token, value)
    if '@@' in rendered:
        raise RuntimeError('Unresolved production extraction token')
    if re.search(r'\b(?:LoadLibrary[A-Za-z]*|GetProcAddress)\s*\(', rendered):
        raise RuntimeError('The headless extracted component contains a dynamic module loader')
    seals = {name: {'bytes': len(value.encode('utf8')), 'sha256': hashlib.sha256(value.encode('utf8')).hexdigest()}
             for name, value in fragments.items()}
    return rendered, seals


def main():
    before = [seal(path) for path in [SOURCE, *CONTRACTS, TEMPLATE, Path(__file__)]]
    source, fragments = generate(SOURCE.read_text(encoding='utf8'))
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '_' + secrets.token_hex(6)
    build = PROJECT / 'Build/OwnedSaveDeleteHandoff' / run_id
    evidence = PROJECT / 'evidence/save_delete/native_handoff' / run_id
    build.mkdir(parents=True, exist_ok=False)
    evidence.mkdir(parents=True, exist_ok=False)
    generated = build / 'handoff.cpp'
    generated.write_text(source, encoding='utf8')
    retained_source = evidence / 'extracted_production.cpp.txt'
    retained_source.write_bytes(generated.read_bytes())
    contracts = build / 'contracts'
    contracts.mkdir()
    report = {'schema': 'zerosis.extracted_owned_save_delete_handoff.v1', 'status': 'IN_PROGRESS',
              'run_id': run_id, 'sources': before, 'extracted_fragments': fragments,
              'generated_source': seal(generated), 'retained_extracted_source': seal(retained_source), 'runs': [],
              'contract_inputs': [], 'sdk_lua_cursor_and_delete_service_mocked': True,
              'actual_host_gamecore_or_hwnd_executed': False, 'actual_save_files_accessed': False,
              'actual_native_delete_service_executed': False, 'retail_files_accessed': False,
              'scope': 'Exact UiPopupContext delete eligibility, lookup/tombstone, owner guards, menu Dispatch branches and Save/Load Close prefix. SDK lock/player/gameplay, Lua callbacks, OS cursor, UTF-8 count for unused named-save branch, snapshot and deletion service are explicit fixtures. NativeSaveCatalog actual-file proof remains separate.'}
    destination = evidence / 'result.json'

    def checkpoint():
        destination.write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')

    checkpoint()
    try:
        for path in CONTRACTS:
            frozen = contracts / path.name
            frozen.write_bytes(path.read_bytes())
            retained = evidence / (path.name + '.txt')
            retained.write_bytes(frozen.read_bytes())
            report['contract_inputs'].append({'source': seal(path), 'frozen': seal(frozen), 'retained': seal(retained)})
        env, compiler = environment_for(VS, 'x64', build)
        env['VSLANG'] = '1033'
        report['compiler'] = seal(Path(compiler))
        for flavor, optimization in (('optimized', '/O2'), ('unoptimized', '/Od')):
            directory = build / flavor
            directory.mkdir()
            executable = directory / 'handoff.exe'
            dependencies = directory / 'dependencies.json'
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
            if [seal(path) for path in [SOURCE, *CONTRACTS, TEMPLATE, Path(__file__)]] != before:
                raise RuntimeError('A sealed menu deletion source changed during compilation')
            imported = run([str(Path(compiler).with_name('dumpbin.exe')), '/nologo', '/imports', str(executable)],
                           cwd=directory, env=env, timeout=30)
            imports = (imported.stdout + imported.stderr).decode('mbcs', errors='replace')
            imports_log = evidence / (flavor + '_imports.log')
            imports_log.write_text(imports, encoding='utf8')
            dlls = sorted(set(re.findall(r'^\s*([A-Za-z0-9_.-]+\.dll)\s*$', imports, re.M | re.I)), key=str.lower)
            if imported.returncode or not dlls or any(re.search(r'gamecore|zerosis|lua|user32|d3d|dxgi', name, re.I) for name in dlls):
                raise RuntimeError('The bounded test imports a forbidden or unverified module')
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
            markers = re.findall(r'^OWNED_SAVE_DELETE_HANDOFF_PASS cases=(\d+) checks=(\d+) GAMECORE_ACTUAL_LOADED=false HWND_CREATED=false FILESYSTEM_MUTATED=false$', runtime, re.M)
            case_names = re.findall(r'^DELETE_HANDOFF_CASE_PASS=(.+)$', runtime, re.M)
            if execution['returncode'] or execution['timed_out'] or len(markers) != 1 or \
                    runtime.splitlines().count('FAULT_UI_SUPPRESSED ERROR_MODE=32771 WER_FLAGS=32') != 1:
                raise RuntimeError(f'{flavor} extracted deletion test failed: {runtime_log}\n{runtime[-2500:]}')
            case_count, check_count = map(int, markers[0])
            if case_count != len(case_names) or len(set(case_names)) != case_count or case_count != 76 or check_count < case_count:
                raise RuntimeError('Bounded deletion case coverage changed')
            row.update(status='PASS', cases=case_count, checks=check_count, case_names=case_names,
                       compiler_and_linker_warnings=0)
            checkpoint()
        if [seal(path) for path in [SOURCE, *CONTRACTS, TEMPLATE, Path(__file__)]] != before:
            raise RuntimeError('A sealed menu deletion source changed during execution')
        if len({(row['cases'], row['checks']) for row in report['runs']}) != 1:
            raise RuntimeError('Optimization variants exercised different deletion case/check counts')
        report.update(status='PASS', total_checks=sum(row['checks'] for row in report['runs']),
                      sources_after=[seal(path) for path in [SOURCE, *CONTRACTS, TEMPLATE, Path(__file__)]])
    except Exception as error:
        report.update(status='FAIL', error=str(error))
        checkpoint()
        print(json.dumps({'status': 'FAIL', 'report': str(destination), 'error': str(error)}))
        raise SystemExit(1)
    checkpoint()
    print(json.dumps({'status': 'PASS', 'cases_per_flavor': report['runs'][0]['cases'],
                      'checks_per_flavor': report['runs'][0]['checks'], 'total_checks': report['total_checks'],
                      'report': seal(destination), 'build': str(build)}))


if __name__ == '__main__':
    main()
