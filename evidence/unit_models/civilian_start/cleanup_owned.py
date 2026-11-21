"""One-shot cleanup of this stage's exact disposable files, never a directory."""
from pathlib import Path
import ctypes
import hashlib
import json
import os
import stat

PROJECT = Path(__file__).absolute().parents[3]
STAGE = Path(__file__).absolute().parent
COMPONENT_ID = '20261016T134720Z_7a7e178dafbd'
FAILED_ID = '20261016T135209Z_7989a41f38d5'
SUCCESS_ID = '20261016T135657Z_d0a5c707425a'
PACKAGE_ID = 'fbb3b9ec4b43242cbee022b9cdf712f37ccbdf6290015ee2ee27b6547a570573'


def read(path):
    return json.loads(Path(path).read_text('utf-8'))


def artifact(path):
    path = Path(path)
    with path.open('rb') as stream:
        sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha}


def main():
    plan_path, result_path = STAGE / 'cleanup_plan.json', STAGE / 'cleanup.json'
    assert not plan_path.exists() and not result_path.exists(), 'Never replay a complete or partial cleanup plan'
    scope = read(STAGE / 'scope.json')
    failed_root = PROJECT / 'Build/CivilianUnitExports' / FAILED_ID
    failed_manifest = failed_root / 'export-manifest.json'
    assert artifact(failed_manifest)['sha256'] == 'ec26c05eab842db3521dda4b87b9897fcdeb1d29c85466f8a2827dc41395c112'
    failed = read(failed_manifest)
    success_path = PROJECT / 'Build/CivilianUnitExports' / SUCCESS_ID / 'export-manifest.json'
    package_path = PROJECT / 'Build/UnitAssets' / PACKAGE_ID / 'unit-assets.manifest.json'
    assert artifact(success_path)['sha256'] == '0319dc51f35ada30241da8c179880707fb9b32e0f0b589727db255df718420be'
    assert artifact(package_path)['sha256'] == '5fcfbdc669ffd233c4ec64118e8e938656079527028a7ac052659421c6b24e7a'
    def strings(value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, dict):
            for item in value.values():
                yield from strings(item)
        elif isinstance(value, list):
            for item in value:
                yield from strings(item)
    for path in (success_path, package_path, STAGE / 'preparation_contract.json'):
        assert not any(str(failed_root).casefold() in value.casefold() for value in strings(read(path))), 'A retained current artifact depends on the failed export'
    assert read(success_path)['status'] == 'PASS_CIVILIAN_UNIT_EXPORT'
    assert failed['status'] == 'FAILED_CIVILIAN_UNIT_EXPORT' and failed['original_inputs_unchanged']
    component = read(STAGE / COMPONENT_ID / 'result.json')
    assert component['status'] == 'PASS_HEADLESS_PRODUCTION_WORLD_UNIT_ART_SELECTION'
    targets = [(Path(row['object']['path']), row['object']['sha256'], 'completed component object') for row in component['variants']]
    targets.extend((Path(row['extracted']['path']), row['extracted']['sha256'], 'superseded failed export input') for row in failed['selected_artifacts'])
    assert len(failed['helper_calls']) == 1 and failed['helper_calls'][0]['exit_code'] == 0
    failed_json = Path(failed['helper_calls'][0]['argv'][-1])
    targets.append((failed_json, artifact(failed_json)['sha256'], 'superseded failed export JSON'))
    component_build = PROJECT / 'Build/WorldUnitArtSelection' / COMPONENT_ID
    for path in (component_build / 'environment/read_build_environment.cmd', STAGE / 'syntax/environment/read_build_environment.cmd'):
        targets.append((path, artifact(path)['sha256'], 'completed private compiler environment command'))
    assert len(targets) == 35 and len({str(p).casefold() for p, sha, why in targets}) == 35
    allowed = (failed_root, component_build, STAGE / 'syntax/environment')
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    allocated = kernel32.GetCompressedFileSizeW
    allocated.argtypes, allocated.restype = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_ulong)], ctypes.c_ulong
    def snapshot(path):
        assert path.is_absolute() and path.resolve(strict=True) == path
        assert any(path.is_relative_to(root) and path != root for root in allowed)
        for parent in (path, *path.parents):
            info = parent.lstat()
            assert not getattr(info, 'st_file_attributes', 0) & 0x400 and not stat.S_ISLNK(info.st_mode)
        info = path.stat()
        assert stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_ino
        assert not getattr(info, 'st_file_attributes', 0) & 1, 'Do not alter read-only attributes'
        high = ctypes.c_ulong()
        ctypes.set_last_error(0)
        low = allocated(str(path), ctypes.byref(high))
        assert low != 0xffffffff or not ctypes.get_last_error()
        row = {**artifact(path), 'device': info.st_dev, 'file_id': info.st_ino, 'mtime_ns': info.st_mtime_ns,
               'links': info.st_nlink, 'allocated_bytes': (high.value << 32) | low}
        after = path.stat()
        assert (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_nlink) == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_nlink)
        return row
    protected = scope['protected'] + [artifact(path) for path in (success_path, package_path, PROJECT / 'Build/UnitAssets' / PACKAGE_ID / 'unit-assets.bin', STAGE / 'preparation_contract.json', STAGE / COMPONENT_ID / 'result.json', STAGE / 'syntax/result.json')]
    for row in protected:
        assert artifact(row['path']) == row
    rows = []
    for path, expected, why in targets:
        row = snapshot(path)
        assert row['sha256'] == expected
        rows.append({**row, 'reason': why})
    plan = {'schema': 1, 'status': 'SEALED_SINGLE_USE_PLAN', 'scope': artifact(STAGE / 'scope.json'),
            'rows': rows, 'protected': protected, 'retail_user_data_or_process_accessed': False,
            'retained_failure_evidence': [artifact(failed_manifest), *[failed['helper_calls'][0][key] for key in ('stdout', 'stderr')]],
            'note': 'Deleted object and failed-input paths remain historical in their immutable original receipts.'}
    with plan_path.open('x', encoding='utf-8') as stream:
        json.dump(plan, stream, indent=2)
        stream.write('\n')
    result = {'status': 'IN_PROGRESS', 'plan': artifact(plan_path), 'removed': [], 'protected_unchanged': False}
    def checkpoint():
        result_path.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    checkpoint()
    for row in rows:
        path = Path(row['path'])
        expected = {key: value for key, value in row.items() if key != 'reason'}
        assert snapshot(path) == expected, 'Exact target identity/hash/allocation changed before unlink'
        path.unlink()
        assert not path.exists()
        result['removed'].append({'path': row['path'], 'bytes': row['bytes'], 'sha256': row['sha256'], 'allocated_bytes': row['allocated_bytes']})
        checkpoint()
    assert all(artifact(row['path']) == row for row in protected)
    result.update(status='COMPLETE', protected_unchanged=True, removed_file_count=len(rows),
                  removed_logical_bytes=sum(row['bytes'] for row in rows),
                  removed_unique_GetCompressedFileSizeW_bytes=sum(row['allocated_bytes'] for row in rows),
                  directories_removed=0, readonly_attributes_modified=0, host_gamecore_or_window_executed=False)
    checkpoint()
    print(json.dumps({key: result[key] for key in ('status', 'removed_file_count', 'removed_logical_bytes', 'removed_unique_GetCompressedFileSizeW_bytes', 'protected_unchanged')}))


if __name__ == '__main__':
    main()
