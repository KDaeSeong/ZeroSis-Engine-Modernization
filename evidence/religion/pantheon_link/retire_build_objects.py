"""Retire only ten sealed raw objects after the exact retry_02 linked PE proof."""
from pathlib import Path
from datetime import datetime, timezone
import argparse, hashlib, json, os, stat, sys

STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[2]
BUILD_ID = '20261017T231735Z_dfbda3dc7eb7'
BUILD = PROJECT / 'Build/UiWindowHost' / BUILD_ID
OUTPUT = STAGE / 'build_objects_retired.json'
PE_SHA = 'e12ab7f26319e6bbb5abe15ea93511d4db9791b88799d1e0bdb16f50c77b8877'
RUN_SHA = '9f0d3e219f4c6addad59fb40775f8f18e8dc2a341badaccaedd0f96f55431452'
PARENT_SHA = '747c8710329e4b2a3a3905dc90b88ce9b9e2f106a0eed0c9ac918f35e6c0f99a'
RETAIL = os.path.normcase(os.path.abspath(r"C:\Users\home\OneDrive\Documents\My Games\Sid Meier's Civilization 5"))
ALLOWED, DENIED = set(), []

def key(path):
    return os.path.normcase(os.path.abspath(path))

def guard(event, args):
    if event in ('open', 'os.listdir', 'os.scandir') and args and isinstance(args[0], (str, bytes, os.PathLike)):
        target = key(os.fsdecode(args[0])).removeprefix('\\\\?\\')
        if target == RETAIL or target.startswith(RETAIL + os.sep):
            DENIED.append(event); raise RuntimeError('Retail test hold forbids user-state access')
        if event == 'open' and ((isinstance(args[1], str) and any(c in args[1] for c in 'wax+')) or args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)):
            assert target == key(OUTPUT), 'Only the new exclusive receipt may be written'
    if event == 'os.remove':
        assert args[1] in (-1, None) and key(args[0]) in ALLOWED, 'Unlink escaped the ten exact object paths'
    if event in ('subprocess.Popen', 'os.system', 'os.startfile', 'os.startfile/2', 'os.exec', 'os.posix_spawn', 'os.spawn', 'ctypes.dlopen', 'os.rmdir', 'os.rename', 'os.link', 'os.symlink'):
        DENIED.append(event); raise RuntimeError('Execution, libraries, moves and recursive removal are forbidden')

def ref(path):
    path = Path(path); before = path.lstat()
    assert stat.S_ISREG(before.st_mode) and not getattr(before, 'st_file_attributes', 0) & 0x400
    with path.open('rb') as stream: digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    after = path.lstat()
    assert (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    return dict(path=str(path), bytes=after.st_size, sha256=digest)

def load(row):
    actual = ref(row['path']); assert actual['sha256'] == row['sha256']
    assert 'bytes' not in row or actual['bytes'] == row['bytes']
    return json.loads(Path(row['path']).read_text(encoding='utf-8-sig'))

def observe(row):
    path = Path(row['path']); assert path.is_absolute() and path.is_relative_to(BUILD) and path.resolve(strict=True) == path
    for member in (path, *path.parents):
        info = member.lstat(); assert not stat.S_ISLNK(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & 0x400
        if member == PROJECT: break
    actual = ref(path); assert actual == row
    info = path.lstat(); assert info.st_nlink == 1
    with path.open('rb') as stream: header = stream.read(4)
    assert len(header) == 4 and int.from_bytes(header[:2], 'little') == 0x8664 and int.from_bytes(header[2:], 'little') > 0
    return dict(**actual, device_id=str(info.st_dev), file_id=format(info.st_ino, 'x'), mtime_ns=str(info.st_mtime_ns), attributes=getattr(info, 'st_file_attributes', 0), link_count=info.st_nlink)

def collect(value, ledger, excluded):
    if isinstance(value, dict):
        if isinstance(value.get('path'), str) and isinstance(value.get('sha256'), str) and key(value['path']) not in excluded:
            path = key(value['path']); assert path not in ledger or ledger[path]['sha256'] == value['sha256']; ledger[path] = value
        for child in value.values(): collect(child, ledger, excluded)
    elif isinstance(value, list):
        for child in value: collect(child, ledger, excluded)

def main():
    if sys.flags.optimize: raise RuntimeError('Python optimization must be zero')
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--apply', action='store_true'); args = parser.parse_args()
    assert not os.path.lexists(OUTPUT), 'Inspect the existing retirement receipt; never repeat this attempt'
    sys.addaudithook(guard)
    pe_ref = dict(path=str(STAGE / ('attestation_' + BUILD_ID + '.json')), sha256=PE_SHA); pe = load(pe_ref)
    assert pe['schema'] == 'zerosis.pantheon_linked_pe_attestation.v1' and pe['status'] == 'PASS' and pe['build_id'] == BUILD_ID and pe['attempt'] == 'retry_02'
    assert pe['actual_pe_inspected'] is True and pe['inputs_unchanged'] is True and not pe['forbidden_access_attempts']
    assert pe['executable']['pe']['pe_format'] == 'PE32+' and pe['executable']['pe']['machine_hex'] == '0x8664' and pe['executable']['pe']['large_address_aware'] is True
    assert all(pe[name] is False for name in ('host_executed', 'gamecore_loaded', 'dll_loaded', 'hwnd_created', 'retail_MODS_saves_settings_or_game_processes_accessed', 'default_promoted'))
    sequence, cpp = pe['actual_build_sequence'], pe['cpp_compilation']
    assert sequence['build_run']['sha256'] == RUN_SHA and sequence['guarded_preparer_then_catalog_then_compiler'] is True
    assert sequence['catalog_registered_payload_count'] == pe['pantheon']['complete_catalog_count'] == 64
    assert all(cpp[name] is True for name in ('source_to_compile_link_lineage_verified', 'exact_five_object_link_response', 'actual_compile_return_object_seals_verified', 'actual_link_before_after_object_seals_verified', 'providers_system_libraries_and_build_tools_unchanged'))
    run = load(sequence['build_run']); build = load(pe['build_report']); extension = load(sequence['catalog_preflight_scope'])
    assert pe['build_report']['sha256'] == '7cbf211c84884085bb9716dfd34b58958b8a73fc2ee01c3ddd9f3876d4e0350d'
    assert run['status'] == 'PASS' and run['state'] == dict(preparations=1, catalog_preflights=1, catalog_verified=True) and not run['forbidden_access_attempts']
    assert run['scope']['sha256'] == PARENT_SHA and run['retry_attempt'] == 'retry_02'
    scope = load(run['scope']); catalog = load(sequence['catalog_syntax'])
    assert scope['retail_mod_test_hold_active'] is True and extension['retail_mod_test_hold_active'] is True
    assert catalog['status'] == extension['expected_status'] and catalog['catalog_count'] == catalog['parsed_count'] == 64 and catalog['failed_count'] == 0 and catalog['inputs_unchanged'] is True and catalog['scripts_executed'] is False
    expected = {key(BUILD / phase / ('tu_%02d_%s' % (i, role)) / 'obj' / (stem + '.obj')) for phase in ('dependency_discovery', 'final') for i, (role, stem) in enumerate((('host_main', 'HostMain'), ('window', 'BitmapWindow'), ('renderer', 'BitmapRenderer'), ('world_renderer', 'WorldViewRenderer'), ('terrain_renderer', 'WorldTerrainRenderer')))}
    objects = {key(row['object']['path']): row['object'] for row in run['compiled_objects'].values()}
    coff = {key(row['path']): row for row in cpp['actual_ten_amd64_coff_objects'].values()}
    assert len(run['compiled_objects']) == len(objects) == len(coff) == 10 and set(objects) == set(coff) == expected and objects == coff
    assert all(row['returncode'] == 0 for row in run['compiled_objects'].values())
    link = run['actual_link_snapshot']; final = {path for path in expected if Path(path).is_relative_to(BUILD / 'final')}
    assert link['returncode'] == 0 and link['objects_before'] == link['objects_after'] and len(link['objects_before']) == 5 and {key(row['path']) for row in link['objects_before']} == final
    assert all(row == objects[key(row['path'])] for row in link['objects_before'])
    ledger = {}; collect(build, ledger, expected)
    for value in (scope['all_source_and_test_seals'], scope['protected_artifacts'], scope['original_assets'], extension['additional_protected_artifacts'], extension['new_source_snapshots_before_retry'], extension['mutable_derived_before_retry'], sequence, pe_ref, pe['build_report'], run['scope'], sequence['catalog_preflight_scope'], ref(__file__)):
        if value is sequence: value = {name: sequence[name] for name in ('build_run', 'started_marker', 'catalog_preflight_scope', 'root_build_wrapper', 'checker', 'catalog_syntax')}
        collect(value, ledger, expected)
    progress = ref(scope['progress_before']['path']); collect(progress, ledger, expected)
    baseline = []
    for row in sorted(ledger.values(), key=lambda value: key(value['path'])):
        current = ref(row['path']); assert current['sha256'] == row['sha256'] and ('bytes' not in row or current['bytes'] == row['bytes']); baseline.append(current)
    before = [observe(objects[path]) for path in sorted(objects)]
    receipt = dict(schema='zerosis.pantheon_link.build_objects_retired.v1', status='PLAN_ONLY', build_id=BUILD_ID, utc=datetime.now(timezone.utc).isoformat(), tool=ref(__file__), pe=ref(pe_ref['path']), actual_build_run=ref(sequence['build_run']['path']), build_report=ref(pe['build_report']['path']), objects_before=before, removals=[], removed_count=0, retired_logical_bytes=0, preserved_artifact_count=len(baseline), preserved_current_progress=progress, retail_mod_test_hold_active=True, game_process_queries=0, host_gamecore_hwnd_or_library_execution=False, large_payload_copies=0, physical_space_reclaimed_claimed=False, raw_revalidation_limit='Deleted raw COFF bytes cannot be re-read. Retained compiler-return seals, link pre/post seals, dependency reports, source/frozen inputs, map/rsp/logs and linked PE remain the historical proof.')
    receipt['preserved_ledger_sha256_before'] = hashlib.sha256(json.dumps(baseline, sort_keys=True).encode()).hexdigest()
    if not args.apply:
        print(json.dumps(dict(status='PLAN_ONLY', objects=len(before), logical_bytes=sum(row['bytes'] for row in before), preserved=len(baseline), deleted=0))); return
    ALLOWED.update(expected)
    with OUTPUT.open('x', encoding='utf-8') as stream:
        def emit():
            stream.seek(0); json.dump(receipt, stream, indent=2); stream.write('\n'); stream.truncate(); stream.flush(); os.fsync(stream.fileno())
        receipt['status'] = 'STARTED'; emit(); error = None
        try:
            assert [observe(objects[path]) for path in sorted(objects)] == before
            for row in before:
                assert observe(objects[key(row['path'])]) == row
                Path(row['path']).unlink(); ALLOWED.remove(key(row['path']))
                assert not os.path.lexists(row['path'])
                receipt['removals'].append(dict(before=row, after=dict(path=row['path'], exists=False)))
                receipt['removed_count'] += 1; receipt['retired_logical_bytes'] += row['bytes']; emit()
            assert receipt['removed_count'] == 10 and not DENIED
            receipt['status'] = 'PASS_RETIRED_EXACT_TEN_OBJECTS'
        except BaseException as failure:
            error = repr(failure); receipt.update(status='FAIL_PARTIAL_OR_NOT_REMOVED', error=error)
        finally:
            try:
                after = [ref(row['path']) for row in baseline]; assert after == baseline
                receipt['preserved_unchanged'] = True
                receipt['preserved_ledger_sha256_after'] = hashlib.sha256(json.dumps(after, sort_keys=True).encode()).hexdigest()
            except BaseException as preservation_failure:
                error = error or repr(preservation_failure)
                receipt.update(status='FAIL_PRESERVATION', preserved_unchanged=False, preservation_error=repr(preservation_failure))
            receipt['raw_paths_after'] = [dict(path=row['path'], exists=os.path.lexists(row['path'])) for row in before]
            receipt['forbidden_access_attempts'] = DENIED; emit()
    assert receipt['preserved_unchanged'] and not error and all(not row['exists'] for row in receipt['raw_paths_after'])
    print(json.dumps(dict(status=receipt['status'], removed=receipt['removed_count'], logical_bytes=receipt['retired_logical_bytes'], receipt=ref(OUTPUT))))

if __name__ == '__main__':
    main()
