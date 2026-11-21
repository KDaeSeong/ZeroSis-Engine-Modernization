"""Content-addressed, read-only materialization for immutable runtime inputs."""
import errno
import hashlib
import os
import shutil
import stat
import tempfile
from pathlib import Path


_CHUNK = 1024 * 1024
_REPARSE_POINT = getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)


def _reject_reparse(path: Path, role: str) -> None:
    """Reject symlinks/reparse points anywhere along the existing path."""
    absolute = Path(os.path.abspath(os.fspath(path)))
    for item in [*reversed(absolute.parents), absolute]:
        try:
            info = os.lstat(item)
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & _REPARSE_POINT:
            raise RuntimeError(f'{role} contains a symlink or reparse point: {item}')


def _regular_file(path: Path, role: str):
    _reject_reparse(path, role)
    try:
        info = os.lstat(path)
    except FileNotFoundError as exc:
        raise RuntimeError(f'{role} does not exist: {path}') from exc
    if not stat.S_ISREG(info.st_mode):
        raise RuntimeError(f'{role} is not a regular file: {path}')
    return info


def _hash_handle(stream) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    while True:
        block = stream.read(_CHUNK)
        if not block:
            break
        digest.update(block)
        size += len(block)
    return digest.hexdigest(), size


def _hash_path(path: Path, role: str) -> tuple[str, int]:
    _regular_file(path, role)
    with path.open('rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or getattr(info, 'st_file_attributes', 0) & _REPARSE_POINT:
            raise RuntimeError(f'{role} changed to a non-regular file: {path}')
        return _hash_handle(stream)


def _readonly(path: Path) -> None:
    mode = stat.S_IMODE(os.lstat(path).st_mode)
    os.chmod(path, mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))


def _copy_to_temp(source: Path, temp_fd: int) -> tuple[str, int]:
    """Copy from one open source snapshot and compare repeated reads for mutation."""
    dst = os.fdopen(temp_fd, 'wb')
    try:
        before = _regular_file(source, 'source')
        with dst, source.open('rb') as src:
            opened = os.fstat(src.fileno())
            if not stat.S_ISREG(opened.st_mode) or getattr(opened, 'st_file_attributes', 0) & _REPARSE_POINT:
                raise RuntimeError('Source changed to a non-regular file while opening')
            first_hash, first_size = _hash_handle(src)
            src.seek(0)
            copied = hashlib.sha256()
            copied_size = 0
            while True:
                block = src.read(_CHUNK)
                if not block:
                    break
                dst.write(block)
                copied.update(block)
                copied_size += len(block)
            dst.flush()
            os.fsync(dst.fileno())
            src.seek(0)
            final_hash, final_size = _hash_handle(src)
    except BaseException:
        if not dst.closed:
            dst.close()
        raise
    after = _regular_file(source, 'source')
    copied_hash = copied.hexdigest()
    if (first_hash, first_size) != (copied_hash, copied_size) or (first_hash, first_size) != (final_hash, final_size):
        raise RuntimeError('Source mutated while creating its immutable snapshot')
    if (before.st_dev, before.st_ino, before.st_size) != (after.st_dev, after.st_ino, after.st_size):
        raise RuntimeError('Source path changed while creating its immutable snapshot')
    return first_hash, first_size


def _verify_cache(path: Path, expected_hash: str, expected_size: int) -> None:
    observed_hash, observed_size = _hash_path(path, 'cache entry')
    if (observed_hash, observed_size) != (expected_hash, expected_size):
        raise RuntimeError(f'Content-addressed cache entry is corrupt: {path}')


def _materialize_cache(source: Path, cache_file: Path, expected_hash: str, expected_size: int) -> str:
    if os.path.lexists(cache_file):
        _verify_cache(cache_file, expected_hash, expected_size)
        return 'cache-hit'

    fd, temp_name = tempfile.mkstemp(prefix='.publish-', dir=cache_file.parent)
    temp = Path(temp_name)
    try:
        copied_hash, copied_size = _copy_to_temp(source, fd)
        if (copied_hash, copied_size) != (expected_hash, expected_size):
            raise RuntimeError('Source hash changed before snapshot publication')
        _readonly(temp)
        try:
            # Windows rename is atomic on the same volume and fails if the name exists.
            # POSIX hard-link publication supplies the equivalent no-replace operation.
            if os.name == 'nt':
                os.rename(temp, cache_file)
            else:
                os.link(temp, cache_file)
        except FileExistsError:
            _verify_cache(cache_file, expected_hash, expected_size)
            return 'cache-race-hit'
        _verify_cache(cache_file, expected_hash, expected_size)
        return 'cache-created-atomic-rename' if os.name == 'nt' else 'cache-created'
    finally:
        if os.name == 'nt' and os.path.lexists(temp):
            # Read-only attributes can prevent unlinking a failed/unpublished temp.
            os.chmod(temp, stat.S_IREAD | stat.S_IWRITE)
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


def _cross_device(error: OSError) -> bool:
    return error.errno == errno.EXDEV or getattr(error, 'winerror', None) == 17


def _copy_fallback(cache_file: Path, target: Path, expected_hash: str, expected_size: int) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(target, flags, 0o600)
    try:
        with os.fdopen(fd, 'wb') as dst, cache_file.open('rb') as src:
            shutil.copyfileobj(src, dst, _CHUNK)
            dst.flush()
            os.fsync(dst.fileno())
        _readonly(target)
        if _hash_path(target, 'materialized target') != (expected_hash, expected_size):
            raise RuntimeError('Cross-volume copy differs from immutable cache entry')
        _verify_cache(cache_file, expected_hash, expected_size)
    except BaseException as exc:
        _cleanup_created_target(target, shared_with_cache=False, original_error=exc)
        raise


def _cleanup_created_target(target: Path, shared_with_cache: bool, original_error: BaseException) -> None:
    """Clean only this call's output; never change attributes on a cache hardlink."""
    try:
        if not shared_with_cache and os.path.lexists(target):
            mode = stat.S_IMODE(os.lstat(target).st_mode)
            os.chmod(target, mode | stat.S_IWRITE)
        target.unlink()
    except FileNotFoundError:
        return
    except BaseException as cleanup_error:
        original_error.add_note(f'Could not remove failed materialized target {target}: {cleanup_error!r}')


def materialize_immutable(source: Path, target: Path, cache_root: Path) -> dict:
    """Snapshot source into a SHA-256 cache, then materialize it read-only at target.

    The source is never hard-linked. A target is created only when absent; existing
    targets, symlinks/reparse points, mutable source races, and corrupt cache objects
    fail closed. Cross-volume hard-link failures use a verified read-only copy.
    """
    source, target, cache_root = Path(source), Path(target), Path(cache_root)
    source_info = _regular_file(source, 'source')
    with source.open('rb') as stream:
        opened = os.fstat(stream.fileno())
        if not stat.S_ISREG(opened.st_mode) or getattr(opened, 'st_file_attributes', 0) & _REPARSE_POINT:
            raise RuntimeError('Source changed to a non-regular file while opening')
        source_hash, source_size = _hash_handle(stream)
    if (source_info.st_dev, source_info.st_ino, source_info.st_size) != (opened.st_dev, opened.st_ino, opened.st_size):
        raise RuntimeError('Source path changed while hashing')

    _reject_reparse(cache_root, 'cache root')
    cache_root.mkdir(parents=True, exist_ok=True)
    _reject_reparse(cache_root, 'cache root')
    shard = cache_root / source_hash[:2]
    _reject_reparse(shard, 'cache shard')
    shard.mkdir(exist_ok=True)
    _reject_reparse(shard, 'cache shard')
    cache_file = shard / source_hash
    cache_method = _materialize_cache(source, cache_file, source_hash, source_size)

    _reject_reparse(target.parent, 'target directory')
    target.parent.mkdir(parents=True, exist_ok=True)
    _reject_reparse(target.parent, 'target directory')
    _reject_reparse(target, 'target')
    if os.path.lexists(target):
        raise RuntimeError(f'Target already exists: {target}')
    try:
        os.link(cache_file, target)
        method = 'hardlink'
    except FileExistsError as exc:
        raise RuntimeError(f'Target already exists: {target}') from exc
    except OSError as exc:
        if not _cross_device(exc):
            raise
        _copy_fallback(cache_file, target, source_hash, source_size)
        method = 'verified-copy-cross-volume'

    try:
        _readonly(target)
        target_hash, target_size = _hash_path(target, 'materialized target')
        if (target_hash, target_size) != (source_hash, source_size):
            raise RuntimeError('Materialized target differs from source snapshot')
        _verify_cache(cache_file, source_hash, source_size)
    except BaseException as exc:
        _cleanup_created_target(target, shared_with_cache=(method == 'hardlink'), original_error=exc)
        raise
    return {'sha256': source_hash, 'size': source_size, 'cache': str(cache_file), 'target': str(target),
            'cache_method': cache_method, 'materialization_method': method, 'read_only': True}
