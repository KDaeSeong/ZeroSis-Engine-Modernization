"""Build only portable full-Map framing tests, using a public RAM input pipe."""
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
from verify_retail_save_header import artifact, require, key, within, pe_imports, COMPILER, COMPILER_SHA, VS
from verify_retail_save_state import public_input, OUTPUT_SHA

PROJECT = Path(__file__).absolute().parents[1]
STAGE = PROJECT/'evidence/retail_save_container/map_state'
REPORT = STAGE/'build_result.json'
SOURCE = PROJECT/'Tests/retail_save_map.cpp'
HEADERS = [PROJECT/'Source/Host'/name for name in ('RetailSaveMap.h', 'RetailSavePlot.h', 'RetailSaveMapTail.h',
    'RetailSaveState.h', 'RetailSaveStateWire.h', 'RetailSaveGameFront.h', 'RetailSaveGameTail.h')]


def validate_public(public, row):
    require(row['input_bytes'] == len(public) and row['map_offset'] == 11254 and row['plot_offset'] == 11984 and
            row['plot_count'] == 960 and row['map_bytes'] > row['plot_bytes'] > 960*1568,
            'Unexpected public Map framing scope')
    require(row['plot_offset']+row['plot_bytes'] == row['areas_offset'] and
            row['areas_offset']+row['areas_bytes'] == row['landmasses_offset'] and
            row['landmasses_offset']+row['landmasses_bytes']+4 == row['next_inflated_offset'] and
            row['map_offset']+row['map_bytes'] == row['next_inflated_offset'] <= len(public),
            'Noncontiguous full-Map boundaries')
    require(struct.unpack_from('<Ihh', public, row['plot_offset']) == (7, 0, 0), 'First public plot differs')
    start, end = row['map_offset'], row['next_inflated_offset']
    return dict(map_bytes_sha256=hashlib.sha256(public[start:end]).hexdigest(),
                unparsed_following_bytes=len(public)-end, first_plot_version=7, first_plot_xy=[0, 0],
                full_map_framing_only=True, following_stream_order_not_inferred=True)


def main():
    require(len(sys.argv) == 1 and not sys.flags.optimize, 'Unexpected map verifier invocation')
    from native_build import environment_for, run
    from collect_baseline import pe_header
    inputs = [artifact(x) for x in (*HEADERS, SOURCE, PROJECT/'Tests/retail_save_state.cpp', Path(__file__).absolute(),
        PROJECT/'tools/verify_retail_save_state.py', PROJECT/'tools/verify_retail_save_header.py',
        PROJECT/'tools/native_build.py', PROJECT/'tools/collect_baseline.py',
        PROJECT/'Tests/Fixtures/RetailSaveHeader/bnw_279.prefix', PROJECT/'Tests/Fixtures/RetailSavePregame/bnw_279.pregame')]
    compiler = artifact(COMPILER)
    require(compiler['sha256'] == COMPILER_SHA, 'Reviewed compiler changed')
    identifier = hashlib.sha256(json.dumps(dict(inputs=inputs, compiler=compiler), sort_keys=True).encode()).hexdigest()[:16]
    root = PROJECT/'Build/RetailSaveMap'/identifier
    if REPORT.exists():
        old = json.loads(REPORT.read_text(encoding='utf-8'))
        require(old['status'] == 'PASS_X64_RETAIL_MAP_COMPONENT' and old['inputs'] == inputs, 'Inspect previous Map result first')
        for row in old['results']:
            require(artifact(row['executable']['path']) == row['executable'], 'Retained Map test changed')
        print(json.dumps(dict(status=old['status'], reused=True)))
        return
    require(not root.exists(), 'Inspect partial Map build before retrying')
    public = public_input()
    protected = [artifact(PROJECT/name) for name in ('Play/EarlyAccess/release.json',
        'evidence/save_menu/20261013_original_screen/current_progress.json',
        'evidence/goody_hut/runtime_fonts/preparation_identity_audit.json',
        'evidence/goody_hut/runtime_fonts/system_freeze_hold.json',
        'evidence/retail_save_container/game_state/build_result.json')]
    for part in (root, *root.parents, STAGE):
        if part.exists():
            require(not part.lstat().st_file_attributes & 0x400, 'Reparse Map build path')
    root.parent.mkdir(parents=True, exist_ok=True)
    STAGE.mkdir(exist_ok=True)
    allowed, calls = set(), []
    setup = root/'read_build_environment.cmd'
    allowed.add(('cmd.exe', '/d', '/c', str(setup)))
    reports = {key(STAGE/name) for name in ('build_started.json', 'build_result.json', 'failed_attempt.json',
        'compile_O2.log', 'compile_Od.log', 'test_O2.log', 'test_Od.log')}

    def audit(event, args):
        if event == 'subprocess.Popen':
            command = next((x for x in allowed if subprocess.list2cmdline(x) == args[1]), None) \
                if isinstance(args[1], str) else tuple(str(x) for x in args[1])
            require(command in allowed, 'Unapproved Map-test child command')
            require(args[0] is None or key(args[0]) == key(command[0]) or
                    Path(args[0]).name.casefold() == command[0].casefold() == 'cmd.exe', 'Unexpected child executable override')
            calls.append(command)
        if event == 'open' and args and isinstance(args[0], (str, bytes, os.PathLike)):
            writing = isinstance(args[1], str) and any(c in args[1] for c in 'wax+') or \
                isinstance(args[2], int) and args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
            if writing:
                require(within(os.fsdecode(args[0]), root) or key(os.fsdecode(args[0])) in reports, 'Map-test write escaped owned outputs')
        if event in ('os.remove', 'os.rmdir', 'os.mkdir', 'os.rename', 'os.chmod', 'os.link', 'os.symlink'):
            for target in (args[:2] if event in ('os.rename', 'os.link', 'os.symlink') else args[:1]):
                if isinstance(target, (str, bytes, os.PathLike)):
                    require(within(os.fsdecode(target), root), 'Map mutation escaped owned root')
        if event.startswith(('ctypes.dlopen', 'socket.', 'urllib.', 'http.client.')) or event in ('os.system', 'os.startfile', 'os.startfile/2'):
            raise RuntimeError('Network, library loading or interactive launch forbidden during Map tests')

    sys.addaudithook(audit)
    root.mkdir()
    (STAGE/'build_started.json').write_text(json.dumps(dict(build_root=str(root), inputs=inputs,
        compiler=compiler, protected=protected), indent=2), encoding='utf-8')
    results = []
    try:
        environment, selected = environment_for(VS, 'x64', root)
        require(key(selected) == key(COMPILER), 'Compiler selection differs')
        environment['VSLANG'] = '1033'
        for flavor, options in (('O2', ['/O2']), ('Od', ['/Od', '/RTC1'])):
            directory = root/flavor
            directory.mkdir()
            exe, obj = directory/'RetailSaveMapTests.exe', directory/'retail_save_map.obj'
            response, deps = directory/'compile.rsp', directory/'dependencies.json'
            flags = ['/nologo', '/std:c++17', '/EHsc', '/W4', '/WX', '/MT', '/utf-8', *options,
                f'"{SOURCE}"', f'/Fo"{obj}"', f'/Fe"{exe}"', f'/sourceDependencies "{deps}"']
            response.write_text('\n'.join(flags)+'\n', encoding='utf-8')
            command = [str(COMPILER), '@'+str(response), '/link', '/MACHINE:X64', '/INCREMENTAL:NO', '/Brepro', '/WX', '/OPT:REF', '/OPT:ICF']
            allowed.add(tuple(command))
            compiled = run(command, cwd=directory, env=environment, timeout=120)
            output = (compiled.stdout+compiled.stderr).decode('mbcs', errors='replace')
            (STAGE/f'compile_{flavor}.log').write_text(output, encoding='utf-8')
            require(compiled.returncode == 0 and not re.search(r'\bwarning\s+[A-Z]+\d+', output, re.I), 'Compile failed; inspect '+flavor+' log')
            dependency = json.loads(deps.read_text(encoding='utf-8-sig'))['Data']
            require(key(dependency['Source']) == key(SOURCE) and all(any(key(x) == key(h) for x in dependency['Includes']) for h in HEADERS) and
                    not any('sdk_bnw_' in key(x) for x in dependency['Includes']), 'Actual Map header dependency proof differs')
            command = [str(exe), '--public']
            allowed.add(tuple(command))
            tested = subprocess.run(command, cwd=directory, env=environment, input=public, capture_output=True,
                                    timeout=60, creationflags=subprocess.CREATE_NO_WINDOW)
            output = (tested.stdout+tested.stderr).decode('utf-8', errors='replace').strip()
            (STAGE/f'test_{flavor}.log').write_text(output+'\n', encoding='utf-8')
            require(tested.returncode == 0, 'Native Map tests failed; inspect '+flavor+' log')
            test = json.loads(output)
            require(test['status'] == 'PASS_RETAIL_MAP_COMPONENT' and test['checks'] > 30 and test['truncations'] > 1000 and
                    test['mutations'] == 2048 and test['accepted_mutations']+test['rejected_mutations'] == 2048 and
                    test['gamecore_loaded'] is False and test['window_created'] is False and test['user_saves_accessed'] is False and
                    test['complete_save_validated'] is False and test['ruleset_compatibility_verified'] is False,
                    'Unexpected Map test result or approval scope')
            cross = validate_public(public, test['public'])
            results.append(dict(flavor=flavor, executable=artifact(exe), object=artifact(obj), pe=pe_header(exe), imports=pe_imports(exe),
                dependency_report=artifact(deps), response=artifact(response), compile_log=artifact(STAGE/f'compile_{flavor}.log'),
                test_log=artifact(STAGE/f'test_{flavor}.log'), test=test, public_cross_check=cross))
        require(results[0]['test']['public'] == results[1]['test']['public'], 'Native modes disagree on Map boundary')
        require(inputs == [artifact(x['path']) for x in inputs] and protected == [artifact(x['path']) for x in protected],
                'Inputs or protected current runtime changed')
        retired = []
        for path in [*(Path(x['object']['path']) for x in results), setup]:
            info = path.stat()
            require(within(path, root) and info.st_nlink == 1 and not info.st_file_attributes & 0x400, 'Unexpected Map cleanup target')
            row = dict(**artifact(path), file_identity=[info.st_dev, info.st_ino], mtime_ns=info.st_mtime_ns)
            require(artifact(path)['sha256'] == row['sha256'], 'Map intermediate changed')
            path.unlink()
            retired.append(row)
        result = dict(schema='zerosis.retail_save.map_component.v1', status='PASS_X64_RETAIL_MAP_COMPONENT',
            utc=datetime.now(timezone.utc).isoformat(), build_root=str(root), inputs=inputs, compiler=compiler, results=results,
            protected=protected, protected_unchanged=True, child_commands=[list(x) for x in calls], retired_intermediates=retired,
            retired_logical_bytes=sum(x['bytes'] for x in retired), public_inflated_sha256=OUTPUT_SHA, public_inflated_input_bytes=len(public),
            public_diagnostic_inflate_eof=False, public_save_or_body_retained=False, user_saves_accessed=False,
            host_gamecore_or_hwnd_executed=False, integrated_into_current_host=False, sdk_restore_verified=False,
            following_streams_or_original_save_write_verified=False, full_engine_goal_complete=False)
        REPORT.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
        print(json.dumps(dict(status=result['status'], checks=[x['test']['checks'] for x in results],
            public=results[0]['test']['public'], cross=results[0]['public_cross_check'], retired_bytes=result['retired_logical_bytes'], report=artifact(REPORT))))
    except BaseException as error:
        (STAGE/'failed_attempt.json').write_text(json.dumps(dict(status='FAILED_X64_RETAIL_MAP_COMPONENT',
            error=type(error).__name__+': '+str(error), build_root=str(root), inputs=inputs, compiler=compiler,
            completed_modes=results, protected_unchanged=protected == [artifact(x['path']) for x in protected]), indent=2), encoding='utf-8')
        raise


if __name__ == '__main__':
    main()
