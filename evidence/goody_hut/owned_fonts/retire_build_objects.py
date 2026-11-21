"""Retire only ten attested raw COFF outputs after the linked PE was verified."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import stat
import sys

STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[2]
BUILD_ID = '20261018T024443Z_23a2e7fdb8ea'
BUILD = PROJECT / 'Build/UiWindowHost' / BUILD_ID
OUTPUT = STAGE / 'build_objects_retired.json'
ALLOWED, DENIED = set(), []


def key(path):
    return os.path.normcase(os.path.abspath(path))


def require(value, message):
    if not value:
        raise RuntimeError(message)


def guard(event, args):
    if event in ('open', 'os.listdir', 'os.scandir') and args and isinstance(args[0], (str, bytes, os.PathLike)):
        target = key(os.fsdecode(args[0]))
        require(not ('\\my games\\' in target), 'Retail user state is forbidden')
        if event == 'open':
            mode, flags = args[1:3]
            writing = isinstance(mode, str) and any(char in mode for char in 'wax+') or isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
            require(not writing or target == key(OUTPUT), 'Only the exclusive retirement receipt may be written')
    if event == 'os.remove':
        require(args[1] in (-1, None) and key(args[0]) in ALLOWED, 'Unlink escaped the exact ten raw objects')
    if event.startswith(('subprocess.', 'ctypes.', 'socket.')) or event in (
            'os.system', 'os.startfile', 'os.exec', 'os.posix_spawn', 'os.spawn', 'os.kill',
            'os.rmdir', 'os.rename', 'os.link', 'os.symlink'):
        DENIED.append(event)
        raise RuntimeError('Execution, libraries, network and other mutations are forbidden')


def ref(path):
    path = Path(path)
    require(path.is_absolute() and path.resolve(strict=True) == path, 'Non-canonical input')
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and not before.st_file_attributes & 0x400, 'Non-ordinary input')
    with path.open('rb') as stream:
        sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    after = path.lstat()
    require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), 'Input changed while hashing')
    return dict(path=str(path), bytes=after.st_size, sha256=sha)


def sealed(row):
    current = ref(row['path'])
    require(current['sha256'] == row['sha256'] and ('bytes' not in row or current['bytes'] == row['bytes']), 'Sealed identity differs')
    return current


def observe(row):
    path = Path(row['path'])
    require(path.is_relative_to(BUILD) and path.suffix == '.obj', 'Wrong raw object root')
    for member in (path, *path.parents):
        require(not member.lstat().st_file_attributes & 0x400, 'Reparse object ancestor')
        if member == PROJECT:
            break
    current = sealed(row);info = path.stat()
    require(info.st_nlink == 1, 'Raw object shares a file identity')
    with path.open('rb') as stream:
        header = stream.read(4)
    require(header[:2] == b'\x64\x86' and int.from_bytes(header[2:], 'little') > 0, 'Not an AMD64 COFF object')
    return dict(**current, device=info.st_dev, file_id=info.st_ino, mtime_ns=info.st_mtime_ns, nlink=info.st_nlink)


def collect(value, ledger, excluded):
    if isinstance(value, dict):
        if isinstance(value.get('path'), str) and isinstance(value.get('sha256'), str) and Path(value['path']).is_absolute() and key(value['path']) not in excluded:
            identity = key(value['path'])
            require(identity not in ledger or ledger[identity]['sha256'] == value['sha256'], 'Conflicting preserved identity')
            ledger[identity] = value
        for child in value.values():
            collect(child, ledger, excluded)
    elif isinstance(value, list):
        for child in value:
            collect(child, ledger, excluded)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    require(sys.dont_write_bytecode and not sys.flags.optimize and not OUTPUT.exists(), 'Single-use unoptimized retirement')
    require(STAGE == PROJECT / 'evidence/goody_hut/owned_fonts', 'Wrong retirement stage')
    sys.addaudithook(guard)
    pe_path, run_path, scope_path = STAGE / 'attestation_retry.json', STAGE / 'build_run.json', STAGE / 'build_scope.json'
    pe_ref, run_ref, scope_ref = ref(pe_path), ref(run_path), ref(scope_path)
    pe, run, scope = (json.loads(path.read_bytes()) for path in (pe_path, run_path, scope_path))
    require(pe['schema'] == 'zerosis.goody_hut.shared_font_linked_pe_attestation.v1' and
            pe['status'] == 'PASS_READONLY_LINKED_PE_67_EXACT_PAYLOADS_NATIVE_PENDING' and
            pe['build_id'] == BUILD_ID and pe['inputs_unchanged'] and not pe['forbidden_access_attempts'] and
            pe['scope'] == scope_ref and pe['actual_build_run'] == run_ref and pe['catalog']['entry_count'] == 67,
            'Actual linked PE attestation did not pass')
    sealed(pe['verifier'])
    require(run['status'] == 'PASS' and run['scope'] == scope_ref and run['new_build_ids'] == [BUILD_ID] and
            run['result'] == 0 and run['protected_unchanged'] and not run['forbidden_access_attempts'], 'Actual compiler witness did not pass')
    require(scope['retail_mod_test_hold_active'] and not scope['host_gamecore_hwnd_execution_allowed'] and
            scope_ref['sha256'] == '52820c0bbfc83a39bc4afe179099a84e69fe9588fb3c326ad5b9721fbec90bf2', 'Compile lease differs')
    objects = {key(row['object']['path']): row['object'] for row in run['actual_objects']}
    coff = {key(row['object']['path']): row['object'] for row in pe['compilation']['actual_coff_objects']}
    stems = ('HostMain', 'BitmapWindow', 'BitmapRenderer', 'WorldViewRenderer', 'WorldTerrainRenderer')
    roles = ('host_main', 'window', 'renderer', 'world_renderer', 'terrain_renderer')
    expected = {key(BUILD / phase / ('tu_%02d_%s' % (index, role)) / 'obj' / (stem + '.obj'))
                for phase in ('dependency_discovery', 'final') for index, (role, stem) in enumerate(zip(roles, stems))}
    require(len(run['actual_objects']) == len(coff) == len(objects) == 10 and objects == coff and set(objects) == expected and
            all(row['returncode'] == 0 for row in run['actual_objects']), 'Actual ten-object identities differ')
    snapshot = run['link_snapshot']
    require(snapshot['returncode'] == 0 and snapshot['objects_before'] == snapshot['objects_after'] ==
            pe['compilation']['link_objects_before'] == pe['compilation']['link_objects_after'] and
            {key(row['path']) for row in snapshot['objects_before']} == {path for path in expected if Path(path).is_relative_to(BUILD / 'final')},
            'Five actual link objects differ')
    before = [observe(objects[path]) for path in sorted(objects)]
    build = json.loads(Path(pe['build_result']['path']).read_bytes())
    preserved = json.loads(Path(scope['frozen_preservation']['path']).read_bytes())
    source = json.loads(Path(scope['source_seal']['path']).read_bytes())
    ledger = {}
    for value in (scope, source, build, pe, pe_ref, run_ref, scope_ref, preserved['artifacts'], ref(__file__), ref(scope['progress_before']['path'])):
        collect(value, ledger, expected)
    baseline = [sealed(row) for _, row in sorted(ledger.items())]
    if not args.apply:
        print(json.dumps(dict(status='PLAN_ONLY', objects=10, logical_bytes=sum(row['bytes'] for row in before), protected=len(baseline), deleted=0)))
        return
    ALLOWED.update(expected)
    receipt = dict(schema='zerosis.goody_hut.build_objects_retired.v1', status='STARTED', build_id=BUILD_ID,
                   script=ref(__file__), pe=pe_ref, actual_build_run=run_ref, build_scope=scope_ref,
                   objects_before=before, removed_count=0, retired_logical_bytes=0, removals=[],
                   protected_count=len(baseline), raw_revalidation_limit='Raw object bytes retire after actual PE/COFF attestation. Compiler-return, link pre/post hashes, map/rsp/logs, frozen inputs and executable remain.',
                   game_process_queries=0, host_gamecore_hwnd_executed=False, retail_user_state_accessed=False)
    with OUTPUT.open('x', encoding='utf-8') as stream:
        def emit():
            stream.seek(0);json.dump(receipt, stream, indent=2);stream.write('\n');stream.truncate();stream.flush();os.fsync(stream.fileno())
        emit()
        try:
            for row in before:
                require(observe(objects[key(row['path'])]) == row, 'Object changed before unlink')
                Path(row['path']).unlink();ALLOWED.remove(key(row['path']))
                require(not os.path.lexists(row['path']), 'Raw object remains')
                receipt['removals'].append(dict(before=row, exists_after=False))
                receipt['removed_count'] += 1;receipt['retired_logical_bytes'] += row['bytes'];emit()
            require(receipt['removed_count'] == 10 and not DENIED, 'Retirement did not complete')
            receipt['status'] = 'PASS_RETIRED_EXACT_TEN_OBJECTS'
        except BaseException as error:
            receipt.update(status='FAIL_PARTIAL_OR_NOT_REMOVED', error=repr(error))
            raise
        finally:
            receipt['protected_unchanged'] = [ref(row['path']) for row in baseline] == baseline
            if not receipt['protected_unchanged']:
                receipt['status'] = 'FAIL_PRESERVATION'
            receipt['forbidden_access_attempts'] = DENIED
            emit()
    require(receipt['protected_unchanged'], 'Protected input changed')
    print(json.dumps(dict(status=receipt['status'], removed=receipt['removed_count'], logical_bytes=receipt['retired_logical_bytes'], protected=len(baseline), receipt=ref(OUTPUT))))


if __name__ == '__main__':
    main()
