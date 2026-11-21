"""Retire the exact observed interrupted candidate; preserve all accepted inputs."""
from pathlib import Path
import ctypes
import gzip
import hashlib
import json
import os
import sys
import zipfile

STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[2]
OBSERVATION = STAGE.parent / 'shared_fonts/build_interrupted.json'
BUILD_ID = '20261018T021154Z_af998ee0b81f'


def require(value, message):
    if not value:
        raise RuntimeError(message)


def ordinary(path):
    require(path.is_absolute() and path.resolve(strict=True) == path, 'Non-canonical target')
    for node in (path, *path.parents):
        require(not node.lstat().st_file_attributes & 0x400, 'Reparse target')
    return path.stat()


def ref(path):
    path = Path(path)
    before = ordinary(path)
    require(path.is_file(), 'Target is not a file')
    with path.open('rb') as stream:
        sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    after = ordinary(path)
    require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), 'File changed during validation')
    return dict(path=str(path), bytes=after.st_size, sha256=sha)


def write(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n'); stream.flush(); os.fsync(stream.fileno())


def main():
    require(sys.dont_write_bytecode and not sys.flags.optimize, 'Use unoptimized Python -B')
    output, started = STAGE / 'interrupted_cleanup.json', STAGE / 'interrupted_cleanup_started.json'
    require(not output.exists() and not started.exists(), 'Single-use cleanup; inspect any partial receipt')
    require(ref(OBSERVATION)['sha256'] == '2881f6a904829868d60e390c78470f8acca1e8cabc948aeb0e6a6ef8ad055e3b', 'Observation changed')
    observed = json.loads(OBSERVATION.read_bytes())
    require(observed['build_id'] == BUILD_ID and observed['selected_process_query_matches'] == 0 and
            observed['object_or_executable_count'] == 0, 'Interrupted candidate boundary differs')
    proof = json.loads((STAGE / 'catalog_preflight_retry.json').read_bytes())
    require(proof['status'] == 'PASS_SHARED_FONT_CATALOG_67_LUA51_PARSE_ONLY_NATIVE_PENDING' and
            proof['catalog_count'] == proof['parsed_count'] == 67 and proof['inputs_unchanged'], 'Replacement generation did not pass')
    roots = [PROJECT / 'Build/UiWindowHost' / BUILD_ID, PROJECT / 'evidence/ui_window_host' / BUILD_ID]
    for root in roots:
        ordinary(root)
        require(root.parent in (PROJECT / 'Build/UiWindowHost', PROJECT / 'evidence/ui_window_host'), 'Wrong cleanup parent')
    rows = observed['partial_artifacts']
    require(len(rows) == 76, 'Unexpected interrupted inventory')
    paths = {Path(row['path']) for row in rows}
    current = {path for root in roots for path in root.rglob('*') if path.is_file()}
    require(paths == current and len(paths) == len(rows), 'Interrupted candidate gained or lost files')
    for row in rows:
        path = Path(row['path']);info = ordinary(path)
        require(any(path.is_relative_to(root) for root in roots) and path.suffix.lower() not in ('.obj', '.exe', '.pdb', '.ilk'), 'Unapproved target')
        require(ref(path) == {key: row[key] for key in ('path', 'bytes', 'sha256')} and
                (info.st_dev, info.st_ino, info.st_mtime_ns, info.st_nlink) ==
                (row['device'], row['file_id'], row['mtime_ns'], row['nlink']), 'Observed target changed')
    preservation = json.loads((PROJECT / 'evidence/goody_hut/source/frozen_candidate_preservation.json').read_bytes())
    seal = json.loads((STAGE / 'source_seal.json').read_bytes())
    capture = json.loads((STAGE / 'capture_result.json').read_bytes())
    protected = [*preservation['artifacts'], *seal['production_sources'].values(),
                 *seal['new_assets_and_tests'].values(), *capture['owned_inputs'],
                 ref(PROJECT / 'Source/Host/UiPopupAssets.generated.h'),
                 ref(PROJECT / 'evidence/ui_popup/assets/prepared.json')]
    for row in protected:
        require(Path(row['path']).is_relative_to(PROJECT) and Path(row['path']) not in paths and ref(row['path']) == row,
                'Preserved current/default/rollback/cache input differs')
    small = [(path, path.relative_to(PROJECT).as_posix()) for path in sorted(paths)
             if path.suffix in ('.rsp', '.cmd', '.log') or path.name == 'build_result.json']
    require(all(path.stat().st_size <= 16384 for path, _ in small), 'Unexpected large diagnostic')
    with zipfile.ZipFile(STAGE / 'interrupted_small_diagnostics.zip', 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for path, name in small:
            archive.writestr(name, path.read_bytes())
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    size = kernel.GetCompressedFileSizeW
    size.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_uint32)]
    size.restype = ctypes.c_uint32
    released = 0
    seen = set()
    for row in rows:
        info = Path(row['path']).stat();identity = (info.st_dev, info.st_ino)
        if info.st_nlink == 1 and identity not in seen:
            high = ctypes.c_uint32();ctypes.set_last_error(0);low = size(row['path'], ctypes.byref(high))
            require(low != 0xffffffff or ctypes.get_last_error() == 0, 'Cannot measure selected allocation')
            released += (high.value << 32) | low;seen.add(identity)
    write(started, dict(schema='zerosis.goody_hut.interrupted_cleanup_started.v1',
                        observation=ref(OBSERVATION), script=ref(__file__), target_roots=[str(root) for root in roots]))
    for row in rows:
        path = Path(row['path']);info = ordinary(path)
        require((info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns) ==
                (row['device'], row['file_id'], row['bytes'], row['mtime_ns']), 'Target changed immediately before deletion')
        path.unlink()
    directories = [path for root in roots for path in root.rglob('*') if path.is_dir()]
    for path in sorted(directories, key=lambda value: len(value.parts), reverse=True):
        ordinary(path);path.rmdir()
    for root in roots:
        root.rmdir()
    require(all(not path.exists() for path in roots), 'Interrupted roots remain')
    require(all(ref(row['path']) == row for row in protected), 'Protected input changed during cleanup')
    result = dict(schema='zerosis.goody_hut.interrupted_cleanup.v1', status='PASS', observation=ref(OBSERVATION),
                  script=ref(__file__), deleted_files=len(rows), deleted_directories=len(directories) + 2,
                  deleted_logical_bytes=sum(row['bytes'] for row in rows), last_link_GetCompressedFileSizeW_bytes=released,
                  protected_count=len(protected), protected_unchanged=True, removed_roots=[str(root) for root in roots],
                  small_diagnostics=ref(STAGE / 'interrupted_small_diagnostics.zip'),
                  game_process_queries=0, host_gamecore_hwnd_executed=False, retail_user_state_accessed=False)
    write(output, result)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
