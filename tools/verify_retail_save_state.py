"""Execute only owned portable BNW-state tests; keep public payloads in RAM."""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import struct
import subprocess
import sys
from urllib.request import Request, urlopen
import zlib

sys.dont_write_bytecode = True
from verify_retail_save_header import artifact, require, key, within, pe_imports, COMPILER, COMPILER_SHA, VS

PROJECT = Path(__file__).absolute().parents[1]
STAGE = PROJECT/'evidence/retail_save_container/game_state'
REPORT = STAGE/'build_result.json'
SOURCE = PROJECT/'Tests/retail_save_state.cpp'
HEADERS = [PROJECT/'Source/Host'/name for name in
           ('RetailSaveState.h', 'RetailSaveStateWire.h', 'RetailSaveGameFront.h', 'RetailSaveGameTail.h')]
URL = 'https://raw.githubusercontent.com/bmaupin/js-civ5save/858ce8532725f634e64fa8acaf355aa8e50829bf/src/__tests__/resources/1.0.3.279.Civ5Save'
OUTPUT_SHA = '1fdc3cf2c0d1fa5859f6be202cc7654ff97835ffc67abe91301d1fbceb9a93db'


def public_input():
    with urlopen(Request(URL, headers={'User-Agent': 'ZeroSis-Native-State-Public-Pipe'}), timeout=20) as stream:
        require(stream.geturl() == URL, 'Unexpected public fixture redirect')
        full = stream.read(1024*1024+1)
    require(len(full) == 418069 and hashlib.sha1(b'blob 418069\0'+full).hexdigest() ==
            '186fb9a84f4e47192e11b8cd98b436a48ccbee16', 'Immutable public fixture changed')
    prefix = (PROJECT/'Tests/Fixtures/RetailSaveHeader/bnw_279.prefix').read_bytes() + \
             (PROJECT/'Tests/Fixtures/RetailSavePregame/bnw_279.pregame').read_bytes()
    require(full[:10991] == prefix, 'Public uncompressed prefix differs')
    decoder = zlib.decompressobj()
    inflated = decoder.decompress(full[10991:], 64*1024*1024+1)
    require(len(inflated) == 9762327 and hashlib.sha256(inflated).hexdigest() == OUTPUT_SHA and
            not decoder.unconsumed_tail and not decoder.unused_data and not decoder.eof,
            'Unexpected public diagnostic-inflate identity or termination')
    return inflated


def inspect_database(public, row):
    # Inspect only the exact declared span returned by ordered framing; never
    # search for SQLite magic or a candidate map boundary in the public payload.
    start, count = row['database_offset'], row['database_bytes']
    require(0 <= start <= len(public) and 0 <= count <= len(public)-start, 'Invalid database span')
    require(row['game_offset'] == 0 and start+count == row['game_bytes'] == row['map_offset'] and
            row['map_offset']+row['map_bytes'] == row['next_inflated_offset'] <= len(public),
            'Noncontiguous native boundaries')
    require(struct.unpack_from('<I', public, row['map_offset'])[0] == 1 and
            struct.unpack_from('<ii', public, row['map_offset']+4) == (row['map_width'], row['map_height']),
            'Map scalar cross-check differs')
    require(struct.unpack_from('<I', public, start-4)[0] == count, 'Database length word differs')
    if not count:
        return dict(bytes=0, present=False, ruleset_width_verified=False)
    payload = public[start:start+count]
    require(count >= 100 and payload[:16] == b'SQLite format 3\0', 'Declared database is not SQLite')
    pagesize = struct.unpack_from('>H', payload, 16)[0]
    if pagesize == 1:
        pagesize = 65536
    pages = struct.unpack_from('>I', payload, 28)[0]
    require(512 <= pagesize <= 65536 and pagesize & (pagesize-1) == 0 and
            pages*pagesize == count, 'SQLite page framing differs')
    with sqlite3.connect(':memory:') as connection:
        connection.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 64*1024*1024)
        connection.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, 4096)
        connection.deserialize(payload)
        connection.execute('PRAGMA query_only=ON')
        names = {value[0] for value in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        values = []
        if 'Defines' in names:
            values = connection.execute('SELECT Value FROM Defines WHERE Name=?',
                                        ('NUM_VICTORY_POINT_AWARDS',)).fetchall()
        require(not values or len(values) == 1 and int(values[0][0]) == 5,
                'Explicit native profile disagrees with embedded database')
    return dict(bytes=count, present=True, sha256=hashlib.sha256(payload).hexdigest(),
                page_size=pagesize, pages=pages, sqlite_version=sqlite3.sqlite_version,
                database_opened_in_memory_only=True, victory_point_awards_values=values,
                ruleset_width_verified=bool(values), all_ruleset_types_verified=False)


def main():
    require(len(sys.argv) == 1 and not sys.flags.optimize, 'Unexpected state verifier invocation')
    from native_build import environment_for, run
    from collect_baseline import pe_header
    inputs = [artifact(path) for path in (*HEADERS, SOURCE, Path(__file__).absolute(),
              PROJECT/'tools/verify_retail_save_header.py', PROJECT/'tools/native_build.py',
              PROJECT/'tools/collect_baseline.py', PROJECT/'Tests/Fixtures/RetailSaveHeader/bnw_279.prefix',
              PROJECT/'Tests/Fixtures/RetailSavePregame/bnw_279.pregame')]
    compiler = artifact(COMPILER)
    require(compiler['sha256'] == COMPILER_SHA, 'Reviewed compiler changed')
    content_id = hashlib.sha256(json.dumps(dict(inputs=inputs, compiler=compiler), sort_keys=True).encode()).hexdigest()[:16]
    root = PROJECT/'Build/RetailSaveState'/content_id
    if REPORT.exists():
        old = json.loads(REPORT.read_text(encoding='utf-8'))
        require(old['status'] == 'PASS_X64_RETAIL_STATE_COMPONENT' and old['inputs'] == inputs,
                'Inspect prior state result before replacing it')
        for row in old['results']:
            require(artifact(row['executable']['path']) == row['executable'], 'Retained state executable changed')
        print(json.dumps(dict(status=old['status'], reused=True)))
        return
    require(not root.exists(), 'Inspect partial state build before retrying')
    public = public_input()
    protected = [artifact(PROJECT/name) for name in ('Play/EarlyAccess/release.json',
        'evidence/save_menu/20261013_original_screen/current_progress.json',
        'evidence/goody_hut/runtime_fonts/preparation_identity_audit.json',
        'evidence/goody_hut/runtime_fonts/system_freeze_hold.json')]
    for part in (root, *root.parents, STAGE):
        if part.exists():
            require(not part.lstat().st_file_attributes & 0x400, 'Reparse state build path')
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
            require(command in allowed, 'Unapproved state-test child command')
            require(args[0] is None or key(args[0]) == key(command[0]) or
                    Path(args[0]).name.casefold() == command[0].casefold() == 'cmd.exe',
                    'Unexpected native executable override')
            calls.append(command)
        if event == 'open' and args and isinstance(args[0], (str, bytes, os.PathLike)):
            writing = isinstance(args[1], str) and any(c in args[1] for c in 'wax+') or \
                      isinstance(args[2], int) and args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
            if writing:
                require(within(os.fsdecode(args[0]), root) or key(os.fsdecode(args[0])) in reports,
                        'State-test write escaped owned outputs')
        if event in ('os.remove', 'os.rmdir', 'os.mkdir', 'os.rename', 'os.chmod', 'os.link', 'os.symlink'):
            for target in (args[:2] if event in ('os.rename', 'os.link', 'os.symlink') else args[:1]):
                if isinstance(target, (str, bytes, os.PathLike)):
                    require(within(os.fsdecode(target), root), 'State mutation escaped owned root')
        if event.startswith(('ctypes.dlopen', 'socket.', 'urllib.', 'http.client.')) or event in ('os.system', 'os.startfile', 'os.startfile/2'):
            raise RuntimeError('Network, candidate loading or interactive launch forbidden during native tests')

    sys.addaudithook(audit)
    root.mkdir()
    with (STAGE/'build_started.json').open('w', encoding='utf-8') as stream:
        json.dump(dict(build_root=str(root), inputs=inputs, compiler=compiler, protected=protected), stream, indent=2)
    results = []
    try:
        environment, selected = environment_for(VS, 'x64', root)
        require(key(selected) == key(COMPILER), 'Compiler selection differs')
        environment['VSLANG'] = '1033'
        for flavor, options in (('O2', ['/O2']), ('Od', ['/Od', '/RTC1'])):
            directory = root/flavor
            directory.mkdir()
            exe, obj = directory/'RetailSaveStateTests.exe', directory/'retail_save_state.obj'
            response, deps = directory/'compile.rsp', directory/'dependencies.json'
            flags = ['/nologo', '/std:c++17', '/EHsc', '/W4', '/WX', '/MT', '/utf-8', *options,
                     f'"{SOURCE}"', f'/Fo"{obj}"', f'/Fe"{exe}"', f'/sourceDependencies "{deps}"']
            response.write_text('\n'.join(flags)+'\n', encoding='utf-8')
            command = [str(COMPILER), '@'+str(response), '/link', '/MACHINE:X64', '/INCREMENTAL:NO', '/Brepro', '/WX', '/OPT:REF', '/OPT:ICF']
            allowed.add(tuple(command))
            build = run(command, cwd=directory, env=environment, timeout=120)
            output = (build.stdout+build.stderr).decode('mbcs', errors='replace')
            (STAGE/f'compile_{flavor}.log').write_text(output, encoding='utf-8')
            require(build.returncode == 0 and not re.search(r'\bwarning\s+[A-Z]+\d+', output, re.I), 'Compile failed; inspect '+flavor+' log')
            dependency = json.loads(deps.read_text(encoding='utf-8-sig'))['Data']
            require(key(dependency['Source']) == key(SOURCE) and all(any(key(x) == key(h) for x in dependency['Includes'])
                    for h in HEADERS) and not any('sdk_bnw_' in key(x) for x in dependency['Includes']),
                    'Actual production-header dependency proof differs')
            command = [str(exe), '--public']
            allowed.add(tuple(command))
            tested = subprocess.run(command, cwd=directory, env=environment, input=public,
                                    capture_output=True, timeout=60, creationflags=subprocess.CREATE_NO_WINDOW)
            output = (tested.stdout+tested.stderr).decode('utf-8', errors='replace').strip()
            (STAGE/f'test_{flavor}.log').write_text(output+'\n', encoding='utf-8')
            require(tested.returncode == 0, 'Native state tests failed; inspect '+flavor+' log')
            test = json.loads(output)
            require(test['status'] == 'PASS_RETAIL_STATE_COMPONENT' and test['checks'] > 30 and
                    test['mutations'] == 2048 and test['truncations'] > 1000 and
                    test['accepted_mutations']+test['rejected_mutations'] == 2048 and
                    test['input_files_unchanged'] is True and test['gamecore_loaded'] is False and
                    test['window_created'] is False and test['complete_save_validated'] is False and
                    test['ruleset_compatibility_verified'] is False and test['public']['input_bytes'] == len(public),
                    'Unexpected native state result or scope')
            database = inspect_database(public, test['public'])
            results.append(dict(flavor=flavor, executable=artifact(exe), object=artifact(obj), pe=pe_header(exe),
                                imports=pe_imports(exe), dependency_report=artifact(deps), response=artifact(response),
                                compile_log=artifact(STAGE/f'compile_{flavor}.log'), test_log=artifact(STAGE/f'test_{flavor}.log'),
                                test=test, independent_database_check=database))
        require(results[0]['test']['public'] == results[1]['test']['public'], 'Build-mode boundary results differ')
        require(inputs == [artifact(x['path']) for x in inputs] and protected == [artifact(x['path']) for x in protected],
                'Inputs or protected runtime/default state changed')
        retired = []
        for path in [*(Path(x['object']['path']) for x in results), setup]:
            info = path.stat()
            require(within(path, root) and info.st_nlink == 1 and not info.st_file_attributes & 0x400, 'Unexpected cleanup target')
            row = dict(**artifact(path), file_identity=[info.st_dev, info.st_ino], mtime_ns=info.st_mtime_ns)
            require(artifact(path)['sha256'] == row['sha256'], 'Intermediate changed before removal')
            path.unlink()
            retired.append(row)
        result = dict(schema='zerosis.retail_save.state_component.v1', status='PASS_X64_RETAIL_STATE_COMPONENT',
                      utc=datetime.now(timezone.utc).isoformat(), build_root=str(root), inputs=inputs, compiler=compiler,
                      results=results, protected=protected, protected_unchanged=True, child_commands=[list(x) for x in calls],
                      retired_intermediates=retired, retired_logical_bytes=sum(x['bytes'] for x in retired),
                      public_source_url=URL, public_input_bytes=len(public), public_inflated_sha256=OUTPUT_SHA,
                      public_diagnostic_inflate_eof=False, public_complete_container_verified=False,
                      public_save_or_body_retained=False, user_saves_accessed=False,
                      host_gamecore_or_hwnd_executed=False, integrated_into_current_host=False,
                      sdk_restore_verified=False, full_map_or_original_save_write_verified=False, full_engine_goal_complete=False)
        with REPORT.open('x', encoding='utf-8') as stream:
            json.dump(result, stream, indent=2)
        print(json.dumps(dict(status=result['status'], checks=[x['test']['checks'] for x in results],
                              public=results[0]['test']['public'], database=results[0]['independent_database_check'],
                              retired_bytes=result['retired_logical_bytes'], report=artifact(REPORT))))
    except BaseException as error:
        with (STAGE/'failed_attempt.json').open('w', encoding='utf-8') as stream:
            json.dump(dict(status='FAILED_X64_RETAIL_STATE_COMPONENT', error=type(error).__name__+': '+str(error),
                           build_root=str(root), inputs=inputs, compiler=compiler, completed_modes=results,
                           child_command_count=len(calls), protected_unchanged=protected == [artifact(x['path']) for x in protected]), stream, indent=2)
        raise


if __name__ == '__main__':
    main()
