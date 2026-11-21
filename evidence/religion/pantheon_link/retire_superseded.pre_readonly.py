"""One scoped unlink attempt for the exact three superseded engine payload roots."""
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter
import argparse, ctypes, hashlib, json, os, stat, sys

STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[2]
SCOPE = STAGE / 'retire_superseded_scope.json'
OUTPUT = STAGE / 'superseded_retired.json'
BUILD_ID, RUN_ID = '20261017T231735Z_dfbda3dc7eb7', '20261017T233110Z_b4d9e31f65f9'
RELATIVE_ROOTS = ('Build/UiWindowHost/20261016T122615Z_1af4a5449cf1', 'Build/InteractiveGameRuntime/20261016T123256Z_fae85fb9fe79', 'Build/InteractiveGameRuntime/20261016T143731Z_bc358fc8d62a')
PINS = dict(plan='065768780ceadf9dc0226ca07d94faa28476e674ab83260f51d9cf8a05ffbcbf', pe_attestation='e12ab7f26319e6bbb5abe15ea93511d4db9791b88799d1e0bdb16f50c77b8877', runtime_identity='1d54b0bc16055a8522138a61f5243163c25363a3aa8d02d0b643345237a48bb1', runtime_request='97956933c47af867aa46fe57a51b3c65e8ea4813b7959338219ddba66ae129ae', object_retirement='2563b1b93314003588a37a9fd53eff997496d124aa41b3da6dc58fc1cd8fcf0d')
RETAIL = os.path.normcase(os.path.abspath(r"C:\Users\home\OneDrive\Documents\My Games\Sid Meier's Civilization 5"))
FILES, DIRS, DENIED, KERNEL_LOADS = set(), set(), [], []

def key(path):
    return os.path.normcase(os.path.abspath(path))

def audit(event, args):
    if event in ('open', 'os.listdir', 'os.scandir') and args and isinstance(args[0], (str, bytes, os.PathLike)):
        target = key(os.fsdecode(args[0])).removeprefix('\\\\?\\')
        if target == RETAIL or target.startswith(RETAIL + os.sep): DENIED.append(event); raise RuntimeError('Retail user-state access forbidden')
        if event == 'open' and ((isinstance(args[1], str) and any(c in args[1] for c in 'wax+')) or args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)):
            assert target == key(OUTPUT), 'Only the exclusive new journal may be written'
    if event in ('os.remove', 'os.rmdir'):
        assert args[1] in (-1, None) and key(args[0]) in (FILES if event == 'os.remove' else DIRS), 'Removal escaped the exact manifest'
    if event == 'ctypes.dlopen':
        assert str(args[0]).lower() in ('kernel32', 'kernel32.dll'), 'Only kernel32 file metadata is permitted'; KERNEL_LOADS.append(str(args[0]))
    if event in ('subprocess.Popen', 'os.system', 'os.startfile', 'os.startfile/2', 'os.exec', 'os.posix_spawn', 'os.spawn', 'os.rename', 'os.link', 'os.symlink'):
        DENIED.append(event); raise RuntimeError('Processes, moves and new links forbidden')

def ordinary(path, directory=False):
    path = Path(path); assert path.is_absolute() and path.resolve(strict=True) == path
    for member in (path, *path.parents):
        info = member.lstat(); assert not stat.S_ISLNK(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & 0x400, str(member)
        if member == PROJECT: break
    info = path.lstat(); assert (stat.S_ISDIR if directory else stat.S_ISREG)(info.st_mode), str(path)
    return info

def ref(path):
    path = Path(path); before = ordinary(path)
    with path.open('rb') as stream: sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    after = ordinary(path)
    assert (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, getattr(before, 'st_file_attributes', 0)) == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, getattr(after, 'st_file_attributes', 0)), str(path)
    return dict(path=str(path), bytes=after.st_size, sha256=sha)

def load(row):
    actual = ref(row['path']); assert actual['sha256'] == row['sha256'] and ('bytes' not in row or actual['bytes'] == row['bytes'])
    return json.loads(Path(row['path']).read_text(encoding='utf-8-sig'))

def immutable(row, directory=False, check_mtime=True):
    info = ordinary(row['path'], directory)
    assert (str(info.st_dev), format(info.st_ino, 'x'), getattr(info, 'st_file_attributes', 0)) == (row['device_id'], row['file_id'], row['attributes']), row['path']
    if check_mtime: assert str(info.st_mtime_ns) == row['mtime_ns'], row['path']
    if not directory:
        actual = ref(row['path']); assert actual['bytes'] == row['logical_bytes'] and actual['sha256'] == row['sha256'], row['path']
        assert ordinary(row['path']).st_ino == info.st_ino
    return ordinary(row['path'], directory)

def scan(roots, files, directories):
    found_files, found_dirs, stack = set(), set(), list(roots)
    sensitive = {'sessions', 'attempts', 'frames', 'screenshots', 'attempt.json', 'result.json', 'driver_result.json', 'window_result.json', 'stdout.log', 'stderr.log', 'host.stdout.log', 'host.stderr.log', 'driver.stdout.log', 'driver.stderr.log', 'native.stdout.log', 'native.stderr.log'}
    while stack:
        path = stack.pop(); ordinary(path, True); found_dirs.add(key(path))
        assert key(path) in directories, 'Unplanned directory: ' + str(path)
        with os.scandir(path) as entries: children = sorted(entries, key=lambda item: item.name.casefold())
        for entry in children:
            child = Path(entry.path); info = child.lstat(); name = entry.name.casefold()
            assert name not in sensitive and not name.startswith('checkpoint') and child.suffix.casefold() not in ('.zssave', '.civ5save', '.sav', '.save', '.dmp', '.mdmp') and not (name.startswith('result') and child.suffix.casefold() == '.json'), 'Save or native output: ' + str(child)
            assert not stat.S_ISLNK(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & 0x400, str(child)
            if stat.S_ISDIR(info.st_mode): stack.append(child)
            else: assert stat.S_ISREG(info.st_mode) and key(child) in files, 'Unplanned file: ' + str(child); found_files.add(key(child))
    assert found_files == set(files) and found_dirs == set(directories), 'Exact manifest inventory differs'

class StandardInfo(ctypes.Structure):
    _fields_ = [('AllocationSize', ctypes.c_longlong), ('EndOfFile', ctypes.c_longlong), ('NumberOfLinks', ctypes.c_uint32), ('DeletePending', ctypes.c_ubyte), ('Directory', ctypes.c_ubyte)]

def allocation_reader():
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]; kernel.CreateFileW.restype = ctypes.c_void_p
    kernel.GetFileInformationByHandleEx.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]; kernel.GetFileInformationByHandleEx.restype = ctypes.c_int
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]; kernel.CloseHandle.restype = ctypes.c_int
    def read(path):
        handle = kernel.CreateFileW('\\\\?\\' + str(path), 0x80, 7, None, 3, 0x00200000, None)
        if handle == ctypes.c_void_p(-1).value: raise OSError(ctypes.get_last_error(), 'Metadata open failed', str(path))
        try:
            value = StandardInfo()
            if not kernel.GetFileInformationByHandleEx(handle, 1, ctypes.byref(value), ctypes.sizeof(value)): raise OSError(ctypes.get_last_error(), 'FileStandardInfo failed', str(path))
            assert not value.Directory and not value.DeletePending and value.AllocationSize >= 0
            return value.AllocationSize, value.EndOfFile, value.NumberOfLinks
        finally: kernel.CloseHandle(handle)
    return read

def main():
    if sys.flags.optimize: raise RuntimeError('Python optimization must be zero')
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--apply', action='store_true', required=True); parser.parse_args()
    assert not os.path.lexists(OUTPUT), 'Inspect the existing journal; this tool is single-use'
    sys.addaudithook(audit); scope_ref = ref(SCOPE); scope = load(scope_ref)
    assert scope['schema'] == 'zerosis.pantheon_link.superseded_retirement_scope.v1' and scope['deletion_allowed'] is True and scope['retail_mod_test_hold_active'] is True
    assert all(scope[name] is False for name in ('host_gamecore_hwnd_execution_allowed', 'retail_user_state_or_game_process_access_allowed', 'default_promotion_allowed', 'full_engine_goal_complete'))
    assert scope['current_host_build_id'] == BUILD_ID and scope['current_runtime_id'] == RUN_ID
    assert ref(__file__) == scope['retirement_tool']
    documents = {}
    for name, sha in PINS.items(): assert scope[name]['sha256'] == sha; documents[name] = load(scope[name])
    plan, pe, identity, request, retired = (documents[name] for name in PINS)
    assert plan['schema'] == 'zerosis.pantheon_link.superseded_retirement_plan.v1' and not plan['blocking_findings']
    assert pe['status'] == 'PASS' and pe['build_id'] == BUILD_ID and pe['cpp_compilation']['source_to_compile_link_lineage_verified'] is True
    assert identity['schema'] == 'zerosis.pantheon_runtime_preparation.identity.v1' and identity['status'] == 'PASS_PREPARED_NOT_EXECUTED' and identity['run_id'] == RUN_ID and identity['host_build_id'] == BUILD_ID
    assert identity['runtime_inputs'] == 24 and len(identity['immutable_cache_links']) == 15 and len(identity['private_databases']) == 2 and len(identity['current_frozen_manifest_support']) == 6 and (identity['cache_hits'], identity['new_cache_objects']) == (14, 1)
    assert identity['inputs_unchanged'] is True and identity['native_execution_outputs_absent'] is True and not identity['forbidden_access_attempts'] and identity['retail_mod_test_hold_active'] is True
    assert all(identity[name] is False for name in ('host_executed', 'gamecore_loaded', 'hwnd_created', 'retail_user_state_or_game_processes_accessed', 'default_promoted', 'full_engine_goal_complete')) and identity['game_process_queries'] == 0
    assert request['run_id'] == RUN_ID and request['smoke'] is False and request['resume_from'] is None and request['ui_support_from_run'] is None and len(request['runtime_inputs']) == 24
    assert request['policy_info_options']['original_user_settings'] is None and request['policy_info_options']['original_policy_info'] is None and request['found_value_worker_policy']['requested'] == 'auto' and request['found_value_worker_policy']['resolved_workers'] == 4
    assert next(row for row in request['runtime_inputs'] if Path(row['path']).name == 'ZeroSisHost_x64.exe')['sha256'] == pe['executable']['sha256']
    assert retired['status'] == 'PASS_RETIRED_EXACT_TEN_OBJECTS' and retired['build_id'] == BUILD_ID and retired['removed_count'] == 10 and retired['preserved_unchanged'] is True
    roots = [PROJECT / relative for relative in RELATIVE_ROOTS]; assert [key(row['path']) for row in plan['candidate_roots']] == [key(path) for path in roots]
    file_rows, dir_rows, groups = plan['files'], plan['directories'], plan['file_identity_groups']
    files = {key(row['path']): i for i, row in enumerate(file_rows)}; directories = {key(row['path']): i for i, row in enumerate(dir_rows)}
    assert len(file_rows) == len(files) == 705 and len(dir_rows) == len(directories) == 74 and len(groups) == 660
    assert all(any(Path(row['path']).is_relative_to(root) for root in roots) for row in file_rows + dir_rows)
    preserved_roots = [Path(row['path'] if isinstance(row, dict) else row) for row in scope['preserved_roots']]
    for path in preserved_roots:
        ordinary(path, True); assert path.is_relative_to(PROJECT) and all(not path.is_relative_to(root) and not root.is_relative_to(path) for root in roots)
    protected = {}
    for row in [*scope['protected_artifacts'], *(scope[name] for name in PINS), scope['progress_before_retirement'], scope['retirement_tool'], scope_ref]:
        assert all(not Path(row['path']).is_relative_to(root) for root in roots)
        assert key(row['path']) not in protected or protected[key(row['path'])]['sha256'] == row['sha256']; protected[key(row['path'])] = row
    baseline = []
    for row in sorted(protected.values(), key=lambda value: key(value['path'])):
        current = ref(row['path']); assert current['sha256'] == row['sha256'] and ('bytes' not in row or current['bytes'] == row['bytes']); baseline.append(current)
    group_index = {(row['device_id'], row['file_id']): i for i, row in enumerate(groups)}
    counts = Counter((row['device_id'], row['file_id']) for row in file_rows)
    assert len(group_index) == 660 and all(counts[(row['device_id'], row['file_id'])] == row['candidate_path_count'] for row in groups)
    journal = dict(schema='zerosis.pantheon_link.superseded_retired.v1', status='VALIDATING', scope=scope_ref, plan=scope['plan'], tool=scope['retirement_tool'], utc=datetime.now(timezone.utc).isoformat(), file_result_columns=['plan_file_index', 'fresh_nlink_before_unlink', 'removed', 'last_link_allocation_estimate_bytes'], file_results=[], directory_result_columns=['plan_directory_index', 'removed'], directory_results=[], removed_files=0, removed_directories=0, removed_logical_path_bytes=0, estimated_last_link_allocation_retired_bytes=0, actual_free_space_change_measured=False, protected_count=len(baseline), preserved_ledger_sha256_before=hashlib.sha256(json.dumps(baseline, sort_keys=True).encode()).hexdigest(), retail_mod_test_hold_active=True, game_process_queries=0, host_gamecore_hwnd_executed=False, large_payload_copies=0, old_version_native_comparison_verified=False, historical_limit='Removed old payload paths cannot be rerun or directly reverified. Historical reports remain and this receipt replaces intentionally retired live-path references. Native UI/campaign/save/mod/performance acceptance is not implied.')
    FILES.update(files); DIRS.update(directories)
    with OUTPUT.open('x', encoding='utf-8') as stream:
        def emit():
            stream.seek(0); json.dump(journal, stream, indent=2); stream.write('\n'); stream.truncate(); stream.flush(); os.fsync(stream.fileno())
        emit(); error = None
        try:
            allocation = allocation_reader(); fresh = []
            for _ in range(2):
                scan(roots, files, directories)
                for row in dir_rows: immutable(row, True)
                observed = {}
                for row in file_rows:
                    info = immutable(row); observed.setdefault((row['device_id'], row['file_id']), []).append(info.st_nlink)
                fresh = []
                for i, row in enumerate(groups):
                    size, eof, links = allocation(Path(row['representative_path'])); assert size == row['allocation_bytes'] and eof == row['logical_bytes']
                    links = max([links, *observed[(row['device_id'], row['file_id'])]]); assert links >= row['candidate_path_count']
                    fresh.append([i, links, size, max(0, links - row['candidate_path_count'])])
            journal.update(fresh_group_columns=['plan_group_index', 'fresh_nlink', 'allocation_bytes', 'outside_candidate_links'], fresh_groups=fresh, fresh_unique_allocation_bytes=sum(row[2] for row in fresh), candidate_exclusive_allocation_estimate_bytes=sum(row[2] for row in fresh if row[3] == 0), shared_allocation_bytes=sum(row[2] for row in fresh if row[3] > 0), status='REMOVING'); emit()
            last_links = set()
            for i, row in enumerate(file_rows):
                info = immutable(row); group = group_index[(row['device_id'], row['file_id'])]
                estimate = fresh[group][2] if info.st_nlink == 1 and group not in last_links else 0
                Path(row['path']).unlink(); FILES.remove(key(row['path']))
                journal['file_results'].append([i, info.st_nlink, True, estimate]); journal['removed_files'] += 1; journal['removed_logical_path_bytes'] += row['logical_bytes']
                if estimate: last_links.add(group); journal['estimated_last_link_allocation_retired_bytes'] += estimate
                assert not os.path.lexists(row['path']); emit()
            for i in sorted(range(len(dir_rows)), key=lambda value: len(Path(dir_rows[value]['path']).parts), reverse=True):
                row = dir_rows[i]; immutable(row, True, False)
                with os.scandir(row['path']) as entries: assert next(entries, None) is None, 'Directory is not empty'
                Path(row['path']).rmdir(); DIRS.remove(key(row['path'])); journal['directory_results'].append([i, True]); journal['removed_directories'] += 1; emit()
            assert journal['removed_files'] == 705 and journal['removed_directories'] == 74 and not DENIED
            assert all(not os.path.lexists(row['path']) for row in file_rows + dir_rows)
            journal['status'] = 'PASS_RETIRED_EXACT_THREE_PAYLOAD_ROOTS'
        except BaseException as failure:
            error = repr(failure); journal.update(status='FAIL_PARTIAL_OR_NOT_REMOVED', error=error)
        finally:
            try:
                after = [ref(row['path']) for row in baseline]; assert after == baseline
                for path in preserved_roots: ordinary(path, True)
                journal.update(protected_unchanged=True, preserved_ledger_sha256_after=hashlib.sha256(json.dumps(after, sort_keys=True).encode()).hexdigest())
            except BaseException as preservation_failure:
                error = error or repr(preservation_failure); journal.update(status='FAIL_PRESERVATION', protected_unchanged=False, preservation_error=repr(preservation_failure))
            journal.update(candidate_roots_absent=all(not os.path.lexists(path) for path in roots), kernel32_metadata_loads=len(KERNEL_LOADS), forbidden_access_attempts=DENIED, finished_utc=datetime.now(timezone.utc).isoformat()); emit()
    assert not error and journal['protected_unchanged'] and journal['candidate_roots_absent']
    print(json.dumps(dict(status=journal['status'], removed_files=journal['removed_files'], removed_directories=journal['removed_directories'], logical_bytes=journal['removed_logical_path_bytes'], estimated_allocation=journal['estimated_last_link_allocation_retired_bytes'], receipt=ref(OUTPUT))))

if __name__ == '__main__':
    main()
