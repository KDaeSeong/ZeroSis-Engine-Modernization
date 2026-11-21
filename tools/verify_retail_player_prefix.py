"""Run independent bounded PlayerPrefix reader fixtures without SDK or game execution."""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode = True
from verify_retail_save_header import artifact, require, key, within, pe_imports, COMPILER, COMPILER_SHA, VS
from native_build import environment_for, run
from collect_baseline import pe_header
from verify_retail_save_state import public_input, OUTPUT_SHA

PROJECT = Path(__file__).absolute().parents[1]
STAGE = PROJECT/'evidence/retail_save_container/player_prefix'
REPORT = STAGE/'build_result.json'
SOURCE = PROJECT/'Tests/retail_player_prefix.cpp'
HEADERS = [PROJECT/'Source/Host'/name for name in ('RetailSavePlayerPrefix.h', 'RetailSavePlayerFront.h', 'RetailSavePlayerAiEarly.h', 'RetailSavePlayerAiStrategy.h', 'RetailSaveStateWire.h', 'RetailSaveMap.h', 'RetailSavePlot.h', 'RetailSaveMapTail.h', 'RetailSaveState.h', 'RetailSaveGameFront.h', 'RetailSaveGameTail.h', 'RetailSaveTeam.h')]


def main():
    require(len(sys.argv) == 1 and not sys.flags.optimize, 'Unexpected PlayerPrefix verifier arguments')
    inputs = [artifact(p) for p in [SOURCE, *HEADERS, Path(__file__).absolute(),
        PROJECT/'tools/verify_retail_save_header.py', PROJECT/'tools/verify_retail_save_state.py', PROJECT/'tools/native_build.py', PROJECT/'tools/collect_baseline.py']]
    compiler = artifact(COMPILER)
    require(compiler['sha256'] == COMPILER_SHA, 'Reviewed compiler changed')
    identifier = hashlib.sha256(json.dumps(dict(inputs=inputs, compiler=compiler), sort_keys=True).encode()).hexdigest()[:16]
    root = PROJECT/'Build/RetailSavePlayerPrefix'/identifier
    if REPORT.exists():
        old = json.loads(REPORT.read_text(encoding='utf-8'))
        require(old['status'] == 'PASS_X64_RETAIL_PLAYER_PREFIX_COMPONENT' and old['inputs'] == inputs, 'Inspect previous PlayerPrefix result first')
        for row in old['results']:
            require(artifact(row['executable']['path']) == row['executable'], 'Retained PlayerPrefix test changed')
        print(json.dumps(dict(status=old['status'], reused=True)))
        return
    require(not root.exists(), 'Inspect partial PlayerPrefix build before retrying')
    public = public_input()
    protected = [artifact(PROJECT/name) for name in ('Play/EarlyAccess/release.json',
        'evidence/save_menu/20261013_original_screen/current_progress.json',
        'evidence/goody_hut/runtime_fonts/preparation_identity_audit.json',
        'evidence/goody_hut/runtime_fonts/system_freeze_hold.json',
        'evidence/serialization/type_array_count/build_result.json', 'evidence/retail_save_container/player_prefix/boundary_probe.json', 'docs/M7_RETAIL_SAVE_BOUNDARY.md')]
    for part in (root, *root.parents, STAGE):
        if part.exists(): require(not part.lstat().st_file_attributes & 0x400, 'Reparse PlayerPrefix build path')
    root.parent.mkdir(parents=True, exist_ok=True)
    STAGE.mkdir(exist_ok=True)
    allowed, calls = {('cmd.exe', '/d', '/c', str(root/'read_build_environment.cmd'))}, []
    reports = {key(STAGE/name) for name in ('build_started.json', 'build_result.json', 'failed_attempt.json',
        'compile_O2.log', 'compile_Od.log', 'test_O2.log', 'test_Od.log')}

    def audit(event, args):
        if event == 'subprocess.Popen':
            command = next((x for x in allowed if subprocess.list2cmdline(x) == args[1]), None) \
                if isinstance(args[1], str) else tuple(str(x) for x in args[1])
            require(command in allowed, 'Unapproved PlayerPrefix-test child command')
            require(args[0] is None or key(args[0]) == key(command[0]) or
                Path(args[0]).name.casefold() == command[0].casefold() == 'cmd.exe', 'Unexpected executable override')
            calls.append(command)
        if event == 'open' and args and isinstance(args[0], (str, bytes, os.PathLike)):
            writing = isinstance(args[1], str) and any(c in args[1] for c in 'wax+') or \
                isinstance(args[2], int) and args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
            if writing: require(within(os.fsdecode(args[0]), root) or key(os.fsdecode(args[0])) in reports, 'Write escaped PlayerPrefix outputs')
        if event in ('os.remove', 'os.rmdir', 'os.mkdir', 'os.rename', 'os.chmod', 'os.link', 'os.symlink'):
            for target in (args[:2] if event in ('os.rename', 'os.link', 'os.symlink') else args[:1]):
                if isinstance(target, (str, bytes, os.PathLike)):
                    require(within(os.fsdecode(target), root), 'Mutation escaped PlayerPrefix build root')
        if event.startswith(('ctypes.dlopen', 'socket.', 'urllib.', 'http.client.')) or event in ('os.system', 'os.startfile', 'os.startfile/2'):
            raise RuntimeError('Network, dynamic loading and interactive launches forbidden in PlayerPrefix tests')
    sys.addaudithook(audit)
    root.mkdir()
    (STAGE/'build_started.json').write_text(json.dumps(dict(build_root=str(root), inputs=inputs, protected=protected,
        previous_goal_turn_classification='progress'), indent=2)+'\n', encoding='utf-8')
    results = []
    try:
        environment, selected = environment_for(VS, 'x64', root)
        require(key(selected) == key(COMPILER), 'Compiler selection changed')
        environment['VSLANG'] = '1033'
        for flavor, options in (('O2', ['/O2']), ('Od', ['/Od', '/RTC1'])):
            directory = root/flavor; directory.mkdir()
            environment['TMP'] = environment['TEMP'] = str(directory)
            exe, obj = directory/'RetailSavePlayerPrefixTests.exe', directory/'retail_save_player_prefix.obj'
            response, dependencies = directory/'compile.rsp', directory/'dependencies.json'
            flags = ['/nologo', '/std:c++17', '/EHsc', '/W4', '/WX', '/MT', '/utf-8', *options,
                f'"{SOURCE}"', f'/Fo"{obj}"', f'/Fe"{exe}"', f'/sourceDependencies "{dependencies}"']
            response.write_text('\n'.join(flags)+'\n', encoding='utf-8')
            command = [str(COMPILER), '@'+str(response), '/link', '/MACHINE:X64', '/INCREMENTAL:NO', '/Brepro', '/WX', '/OPT:REF', '/OPT:ICF']
            allowed.add(tuple(command)); compiled = run(command, cwd=directory, env=environment, timeout=120)
            text = (compiled.stdout+compiled.stderr).decode('mbcs', errors='replace')
            log = STAGE/f'compile_{flavor}.log'; log.write_text(text, encoding='utf-8')
            require(compiled.returncode == 0 and not re.search(r'\bwarning\s+[A-Z]+\d+', text, re.I), 'Compile failed; inspect '+log.name)
            data = json.loads(dependencies.read_text(encoding='utf-8-sig'))['Data']
            require(key(data['Source']) == key(SOURCE) and all(any(key(h) == key(x) for x in data['Includes']) for h in HEADERS) and
                not any('sdk_bnw_' in key(x) for x in data['Includes']), 'Actual PlayerPrefix header dependency mismatch')
            command = [str(exe), '--public']; allowed.add(tuple(command))
            tested = subprocess.run(command, cwd=directory, env=environment, input=public, capture_output=True, timeout=60, creationflags=subprocess.CREATE_NO_WINDOW)
            text = (tested.stdout+tested.stderr).decode('utf-8', errors='replace').strip()
            test_log = STAGE/f'test_{flavor}.log'; test_log.write_text(text+'\n', encoding='utf-8')
            require(tested.returncode == 0, 'Native PlayerPrefix tests failed; inspect '+test_log.name)
            result = json.loads(text)
            require(result['status'] == 'PASS_RETAIL_PLAYER_PREFIX_COMPONENT' and result['checks'] > 1000 and result['truncations'] > 2000
                and result['mutations'] == 2048 and result['accepted_mutations']+result['rejected_mutations'] == 2048,
                'Unexpected PlayerPrefix checks or mutation counts')
            for field in ('gamecore_loaded', 'window_created', 'user_saves_accessed', 'complete_save_validated', 'ruleset_compatibility_verified'):
                require(result[field] is False, 'PlayerPrefix test exceeds component scope: '+field)
            row = result['public']
            require(row['input_bytes'] == len(public) and row['teams_start'] == 1695150 and row['teams_end'] == 2309550
                and row['team_count'] == 64 and row['player_id'] == 0 and row['front_offset'] == 2309550
                and row['diplomacy_version'] == 4, 'Public Player sequential boundary/profile mismatch')
            cursor = row['front_offset']
            for name in ('front', 'policies', 'economic_ai', 'city_specialization_ai', 'wonder_production_ai', 'military_ai', 'grand_strategy_ai'):
                require(row[name+'_offset'] == cursor and row[name+'_bytes'] > 0, 'Noncontiguous Player prefix span')
                cursor += row[name+'_bytes']
            require(cursor == row['next_inflated_offset'] and cursor+4 <= len(public), 'Player prefix end mismatch')
            results.append(dict(flavor=flavor, executable=artifact(exe), object=artifact(obj), pe=pe_header(exe), imports=pe_imports(exe),
                dependencies=artifact(dependencies), response=artifact(response), compile_log=artifact(log), test_log=artifact(test_log), test=result))
        require(results[0]['test'] == results[1]['test'], 'Optimized/checked PlayerPrefix observations differ')
        require(inputs == [artifact(x['path']) for x in inputs] and protected == [artifact(x['path']) for x in protected],
            'Inputs or protected runtime evidence changed')
        retired = []
        for path in [*[Path(x['object']['path']) for x in results], root/'read_build_environment.cmd']:
            info = path.stat()
            require(within(path, root) and info.st_nlink == 1 and not info.st_file_attributes & 0x400, 'Unexpected PlayerPrefix cleanup identity')
            row = dict(**artifact(path), file_identity=[info.st_dev, info.st_ino], mtime_ns=info.st_mtime_ns)
            require(artifact(path)['sha256'] == row['sha256'], 'PlayerPrefix intermediate changed before cleanup')
            path.unlink(); retired.append(row)
        report = dict(schema='zerosis.retail_save.player_prefix_component.v1', status='PASS_X64_RETAIL_PLAYER_PREFIX_COMPONENT',
            utc=datetime.now(timezone.utc).isoformat(), build_root=str(root), inputs=inputs, compiler=compiler, results=results,
            protected=protected, protected_unchanged=True, child_commands=[list(x) for x in calls], retired_intermediates=retired,
            retired_logical_bytes=sum(x['bytes'] for x in retired), previous_goal_turn_classification='progress',
            original_install_or_user_saves_accessed=False, host_gamecore_or_hwnd_executed=False, integrated_into_current_host=False,
            public_inflated_input_bytes=len(public), public_inflated_sha256=OUTPUT_SHA, public_save_or_body_retained=False,
            public_profile=dict(victory_point_awards=5, grand_strategy_count=4, building_catalog='initialized', ruleset_compatibility_verified=False),
            full_sdk_recompiled=False, sdk_restore_verified=False, full_player_framed=False, full_engine_goal_complete=False)
        REPORT.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
        print(json.dumps(dict(status=report['status'], tests=results[0]['test'], retired_bytes=report['retired_logical_bytes'], report=artifact(REPORT))))
    except BaseException as error:
        (STAGE/'failed_attempt.json').write_text(json.dumps(dict(status='FAILED_X64_RETAIL_PLAYER_PREFIX_COMPONENT',
            error=type(error).__name__+': '+str(error), build_root=str(root), inputs=inputs, completed_modes=results,
            protected_unchanged=protected == [artifact(x['path']) for x in protected]), indent=2)+'\n', encoding='utf-8')
        raise


if __name__ == '__main__':
    main()
