"""Bounded Civ V FPK v6 reads and lossless FTXTInterface tile-map decoding.

Only selected entries are read. Installations are never modified or bulk unpacked.
The expansion priority is an explicit isolated candidate policy, not retail proof.
FTXT pairs are resolved from the same pack; missing or malformed data fails closed.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import errno
import os
from pathlib import Path
import re
import struct
import stat
import tempfile
import time
from typing import BinaryIO
import xml.etree.ElementTree as ET

MAX_ASSET_BYTES = 64 * 1024 * 1024
MAX_TEXELS = 16 * 1024 * 1024
FONT_CACHE_MAX_LINKS = 1000
FONT_CACHE_MAX_SHARDS = 64
PACK_POLICY = ('Expansion2UITextures.fpk', 'Expansion1UITextures.fpk', 'UITextures.fpk',
               'Upgrade1Textures.fpk')
LOOSE_UI_TEXTURES = {
    'bluebar500x3.dds': {
        'relative_path': 'Assets/UI/Art/Controls/BlueBar500x3.dds',
        'bytes': 6128,
        'sha256': '7628a4427c80afae31f3a510245502a085a9a3b16f5421cccf290621a3ccaad1',
    },
    'socialpolicies_patch64_exp2.dds': {
        'relative_path': 'Assets/DLC/Expansion2/UI/Art/Icons/SocialPolicies_Patch64_Exp2.dds',
        'bytes': 32896,
        'sha256': 'c74d13aa8e1248e6a54346246d0b3a0b6732712236525cc39b67d85a3d9fc518',
    },
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


MENU_SOURCE_GAME_ROOT = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V")
MENU_SOURCE_IDENTITIES = {
    "optionsLua": ("Assets/UI/Options/OptionsMenu.lua", 70204,
        "76247d52606e8486101e91cad3668b3a4a56257ddbd4df991ef182e9a70c5921"),
    "optionsXml": ("Assets/UI/Options/OptionsMenu.xml", 29601,
        "a8bd7dbc98544179edfd5c8dba57e6855a4b8fbc5a01a039bcd1579feb7fe7a2"),
    "touchLua": ("Assets/UI/TouchControlsMenu.lua", 838,
        "6305aeea4e6c2c538fffa5f1a30f76c3538fbdef8aedaeaf9992f8f7db72d988"),
    "touchXml": ("Assets/UI/TouchControlsMenu.xml", 6475,
        "de143c20da99754154088e29e253b9f27da1dc36785d1bec32c8d968c60a6893"),
}

MENU_SUPPORTED_ORIGINAL_HANDLERS = (
    "OnCategory", "OnNoBasicHelpCheckbox", "OnNoRewardPopupsCheckbox", "OnPolicyInfo", "OnFullscreen",
    "OnVSync", "OnUIVolumeSliderValueChanged", "OnWResolutionPull",
)

def supported_original_menu_handlers(game_root=MENU_SOURCE_GAME_ROOT) -> dict:
    """Retain exact function bytes, without executing unsupported top-level code.

    The installed source hash is pinned before extraction. Each selected stock
    function closes with an unindented ``end``; nested blocks in those functions
    are indented. Reject a changed source/shape rather than guessing Lua scopes.
    """
    source = menu_original_sources(game_root)["optionsLua"]
    raw = Path(source["path"]).read_bytes()
    text = raw.decode("utf-8-sig")
    functions = []
    for name in MENU_SUPPORTED_ORIGINAL_HANDLERS:
        matches = list(re.finditer(
            r"^function " + re.escape(name) + r"\([^\n]*\)[^\n]*\n.*?^end[ \t]*;?\r?$",
            text, re.MULTILINE | re.DOTALL))
        if len(matches) != 1:
            raise ValueError("Original options handler shape changed: " + name)
        match = matches[0]
        body = match.group(0)
        functions.append({"name": name, "firstLine": text.count("\n", 0, match.start()) + 1,
            "lastLine": text.count("\n", 0, match.end()) + 1,
            "bytes": len(body.encode("utf-8")),
            "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(), "source": body})
    return {"profile": "EXACT_ORIGINAL_OPTIONS_HANDLERS_V1", "originalLua": source,
            "completeOriginalScriptExecuted": False, "functions": functions,
            "executionScope": "selected original callbacks; private transaction lifecycle"}

def menu_slider_style(game_root=MENU_SOURCE_GAME_ROOT) -> dict:
    path = Path(game_root) / "Assets/UI/Styles.xml"
    styles = ET.parse(path).getroot()
    slider, shuttle = styles.find("Slider"), styles.find("Slider32")
    if slider is None or shuttle is None or slider.get("Size") != "66,32" or shuttle.get("Size") != "32,32":
        raise ValueError("Original horizontal slider style changed")
    children = list(slider)
    if len(children) != 1 or children[0].tag != "Shuttle" or children[0].get("Style") != "Slider32":
        raise ValueError("Original slider shuttle declaration changed")
    return {"policy": "ORIGINAL_HORIZONTAL_SLIDER_STYLE_CANDIDATE_V1", "source": menu_source_artifact(path),
        "sourceStyleAttributes": dict(slider.attrib), "sourceShuttleAttributes": dict(shuttle.attrib),
        "sourceShuttleInstanceAttributes": dict(children[0].attrib), "height": 32, "shuttleWidth": 32,
        "retailWidgetGeometryVerified": False, "retailWidgetBehaviorVerified": False,
        "valueRange": [0, 1], "activeControlWhitelist": ["EffectsVolumeSlider"]}

def menu_source_artifact(path: Path) -> dict:
    data = path.read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}

def menu_original_sources(game_root=MENU_SOURCE_GAME_ROOT) -> dict:
    result = {}
    for key, (relative, size, sha) in MENU_SOURCE_IDENTITIES.items():
        record = menu_source_artifact(Path(game_root) / relative)
        if (record["bytes"], record["sha256"]) != (size, sha):
            raise ValueError("Original options/touch source identity changed: " + relative)
        result[key] = record
    return result


def _pack_sha256(paths):
    # Each scene still reads every byte before and after compilation. Only the
    # four independent archive reads overlap; no digest survives between scenes.
    with ThreadPoolExecutor(max_workers=len(PACK_POLICY),
                            thread_name_prefix='ui-pack-hash') as workers:
        return list(workers.map(sha256, paths))


def exact(stream: BinaryIO, length: int):
    data = stream.read(length)
    require(len(data) == length, 'Truncated FPK table or asset')
    return data


def candidate_directory(destination, game_root):
    # Inspect the caller's original path before resolve(), which would hide a
    # junction or symlink in a candidate output path.
    destination = Path(os.path.abspath(os.fspath(destination)))
    _reject_reparse(destination, 'Candidate output')
    destination = destination.resolve()
    require(not destination.is_relative_to(Path(game_root).resolve()), 'Candidate output may not be inside the game installation')
    destination.mkdir(parents=True, exist_ok=True)
    return destination


def _interactive_scene_asset_cache(destination: Path) -> Path | None:
    """Select the shared Build cache only for the exact interactive scene layout."""
    destination = Path(os.path.abspath(os.fspath(destination)))
    # Inspect the lexical path before resolve(), which would hide a junction
    # inserted between the caller's destination and its actual target.
    _reject_reparse(destination, 'UI asset destination')
    if not any(parent.name == 'InteractiveGameRuntime' for parent in destination.parents):
        return None
    destination = destination.resolve()
    require(destination.name == 'textures' and
            re.fullmatch(r'play-ui-[1-9][0-9]*', destination.parent.name) is not None and
            re.fullmatch(r'[0-9a-f]{32}', destination.parents[1].name) is not None and
            destination.parents[2].name == 'sessions' and
            re.fullmatch(r'20[0-9]{6}T[0-9]{6}Z_[0-9a-f]{12}', destination.parents[3].name) is not None and
            destination.parents[4].name == 'InteractiveGameRuntime' and
            destination.parents[5].name == 'Build',
            'Interactive UI asset destination does not have the exact shared Build runtime layout')
    build_root = destination.parents[5]
    cache_root = build_root / 'RuntimeInputCache' / 'ui-source-assets'
    require(cache_root.parent == build_root / 'RuntimeInputCache' and
            cache_root.is_relative_to(build_root),
            'Interactive UI source cache escaped the common Build root')
    return cache_root


_REPARSE_POINT = getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)


def _reject_reparse(path: Path, role: str) -> None:
    absolute = Path(os.path.abspath(os.fspath(path)))
    for item in [*reversed(absolute.parents), absolute]:
        try:
            info = os.lstat(item)
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & _REPARSE_POINT:
            raise ValueError(f'{role} contains a symlink or reparse point: {item}')


def _payload_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _verify_payload_file(path: Path, expected_hash: str, expected_size: int, role: str) -> None:
    _reject_reparse(path, role)
    try:
        info = os.lstat(path)
    except FileNotFoundError as error:
        raise ValueError(f'{role} is missing: {path}') from error
    require(stat.S_ISREG(info.st_mode) and info.st_size == expected_size,
            f'{role} is not the expected regular file: {path}')
    require(sha256(path) == expected_hash, f'{role} content hash differs: {path}')


def _publish_cached_payload(data: bytes, cache_root: Path, *, shard_index: int | None = None) -> tuple[Path, str]:
    """Atomically retain exact FPK bytes once under a shared content address."""
    digest = _payload_hash(data)
    size = len(data)
    cache_root = Path(cache_root).absolute()
    _reject_reparse(cache_root, 'UI asset cache root')
    shard = cache_root / digest[:2]
    if shard_index is not None:
        require(type(shard_index) is int and 0 <= shard_index < FONT_CACHE_MAX_SHARDS,
                'Font cache shard index is outside its bound')
        shard = shard / digest
    _reject_reparse(shard, 'UI asset cache shard')
    shard.mkdir(parents=True, exist_ok=True)
    _reject_reparse(shard, 'UI asset cache shard')
    cache_file = shard / (digest + '.dds' if shard_index is None else f'shard-{shard_index:04d}.dds')
    if os.path.lexists(cache_file):
        _verify_payload_file(cache_file, digest, size, 'UI asset cache entry')
        return cache_file, 'cache-hit'

    fd, temporary_name = tempfile.mkstemp(prefix='.publish-', dir=shard)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, stat.S_IREAD)
        try:
            if os.name == 'nt':
                os.rename(temporary, cache_file)
                publish = 'cache-created-atomic-rename'
            else:
                os.link(temporary, cache_file)
                publish = 'cache-created'
        except FileExistsError:
            _verify_payload_file(cache_file, digest, size, 'UI asset cache race winner')
            publish = 'cache-race-hit'
        _verify_payload_file(cache_file, digest, size, 'published UI asset cache entry')
        return cache_file, publish
    finally:
        if os.path.lexists(temporary):
            try:
                if os.name == 'nt':
                    os.chmod(temporary, stat.S_IREAD | stat.S_IWRITE)
            except OSError:
                pass
            temporary.unlink()


def _materialize_cached_payload(cache_file: Path, target: Path, expected_hash: str,
                                expected_size: int) -> str:
    _verify_payload_file(cache_file, expected_hash, expected_size, 'UI asset cache source')
    _reject_reparse(target.parent, 'UI asset target directory')
    target.parent.mkdir(parents=True, exist_ok=True)
    _reject_reparse(target.parent, 'UI asset target directory')
    _reject_reparse(target, 'UI asset target')
    if os.path.lexists(target):
        _verify_payload_file(target, expected_hash, expected_size, 'existing UI asset target')
        return 'existing-verified'
    try:
        os.link(cache_file, target)
        method = 'hardlink'
    except FileExistsError:
        _verify_payload_file(target, expected_hash, expected_size, 'racing UI asset target')
        return 'existing-race-verified'
    except OSError as error:
        cross_volume = error.errno == errno.EXDEV or getattr(error, 'winerror', None) == 17
        link_limit = error.errno == getattr(errno, 'EMLINK', 31) or getattr(error, 'winerror', None) == 1142
        if not cross_volume and not link_limit:
            raise
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        fd = os.open(target, flags, 0o600)
        try:
            with os.fdopen(fd, 'wb') as output, cache_file.open('rb') as source:
                while True:
                    block = source.read(1024 * 1024)
                    if not block:
                        break
                    output.write(block)
                output.flush()
                os.fsync(output.fileno())
            os.chmod(target, stat.S_IREAD)
            fallback_role = 'cross-volume UI asset copy' if cross_volume else 'hardlink-limit UI asset copy'
            _verify_payload_file(target, expected_hash, expected_size, fallback_role)
            method = 'verified-copy-cross-volume' if cross_volume else 'verified-copy-hardlink-limit'
        except BaseException:
            try:
                os.chmod(target, stat.S_IREAD | stat.S_IWRITE)
                target.unlink()
            except OSError:
                pass
            raise
    try:
        os.chmod(target, stat.S_IREAD)
        _verify_payload_file(target, expected_hash, expected_size, 'materialized UI asset target')
    except BaseException:
        try:
            target.unlink()
        except OSError:
            pass
        raise
    return method


@contextmanager
def _font_cache_lock(directory: Path):
    """Bound concurrent publications; OS locks are released even after a crash."""
    _reject_reparse(directory, 'Font cache directory')
    directory.mkdir(parents=True, exist_ok=True)
    lock_path = directory / '.font-cache.lock'
    _reject_reparse(lock_path, 'Font cache lock')
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | getattr(os, 'O_BINARY', 0), 0o600)
    locked = False
    try:
        info = os.fstat(fd)
        _reject_reparse(lock_path, 'Opened font cache lock')
        current = os.lstat(lock_path)
        require(stat.S_ISREG(info.st_mode) and (info.st_dev, info.st_ino) == (current.st_dev, current.st_ino),
                'Font cache lock identity changed while opening')
        require(info.st_size in (0, 1), 'Font cache lock has unexpected contents')
        if os.name == 'nt':
            import msvcrt
        else:
            import fcntl
        deadline = time.monotonic() + 5.0
        while True:
            os.lseek(fd, 0, os.SEEK_SET)
            try:
                if os.name == 'nt':
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                else:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
                break
            except OSError as error:
                if error.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                    raise
                if time.monotonic() >= deadline:
                    raise TimeoutError('Font cache lock remained busy for five seconds') from error
                time.sleep(.02)
        _reject_reparse(lock_path, 'Locked font cache path')
        current = os.lstat(lock_path)
        require((info.st_dev, info.st_ino) == (current.st_dev, current.st_ino),
                'Font cache lock identity changed while waiting')
        if os.fstat(fd).st_size == 0:
            os.write(fd, b'\0')
        require(os.fstat(fd).st_size == 1, 'Locked font cache file has unexpected size')
        yield
    finally:
        try:
            if locked:
                os.lseek(fd, 0, os.SEEK_SET)
                if os.name == 'nt':
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _unlink_font_target_without_attribute_changes(target: Path) -> None:
    if os.name != 'nt':
        target.unlink()
        return
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                  wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.SetFileInformationByHandle.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.SetFileInformationByHandle.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    native_path = os.path.abspath(os.fspath(target))
    if not native_path.startswith('\\\\?\\'):
        native_path = ('\\\\?\\UNC\\' + native_path[2:] if native_path.startswith('\\\\')
                       else '\\\\?\\' + native_path)
    handle = kernel.CreateFileW(native_path, 0x10000, 7, None, 3, 0x00200000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        # FileDispositionInfoEx: DELETE | POSIX_SEMANTICS | IGNORE_READONLY.
        flags = wintypes.DWORD(0x13)
        if not kernel.SetFileInformationByHandle(handle, 21, ctypes.byref(flags), 4):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        kernel.CloseHandle(handle)


def _remove_created_font_link(target: Path, cache_file: Path, identity: tuple[int, int]) -> None:
    _reject_reparse(target, 'Created font link')
    _reject_reparse(cache_file, 'Created font link cache')
    require(all((os.lstat(path).st_dev, os.lstat(path).st_ino) == identity for path in (target, cache_file)),
            'Refusing to remove a font link whose identity changed')
    _unlink_font_target_without_attribute_changes(target)


def materialize_sharded_payload(data: bytes, target: Path, cache_root: Path) -> dict:
    """Retain a font payload without per-scene copy fallback at the NTFS limit."""
    require(isinstance(data, bytes) and 0 < len(data) <= MAX_ASSET_BYTES, 'Unbounded font cache payload')
    target = Path(os.path.abspath(os.fspath(target)))
    cache_root = Path(os.path.abspath(os.fspath(cache_root)))
    selected = _interactive_scene_asset_cache(target.parent)
    require(selected is not None and cache_root == selected.with_name('ui-font-atlases'),
            'Font cache or target escaped the exact shared Build runtime layout')
    _reject_reparse(cache_root, 'Font cache root')
    _reject_reparse(target, 'Font atlas target')
    target.parent.mkdir(parents=True, exist_ok=True)
    _reject_reparse(target.parent, 'Created font target directory')
    digest, size = _payload_hash(data), len(data)

    def result(method, cache_file=None, shard_index=None):
        return {'method': method, 'cache_file': str(cache_file) if cache_file else None,
                'sha256': digest, 'bytes': size, 'shard_index': shard_index}

    with _font_cache_lock(cache_root / digest[:2] / digest):
        if os.path.lexists(target):
            _verify_payload_file(target, digest, size, 'Existing font atlas target')
            return result('existing-verified')
        for index in range(FONT_CACHE_MAX_SHARDS):
            cache_file, _ = _publish_cached_payload(data, cache_root, shard_index=index)
            info = os.lstat(cache_file)
            require(info.st_nlink > 0, 'Font cache link count is unavailable')
            if info.st_nlink >= FONT_CACHE_MAX_LINKS:
                continue
            identity = info.st_dev, info.st_ino
            try:
                os.link(cache_file, target)
            except FileExistsError:
                _verify_payload_file(target, digest, size, 'Racing font atlas target')
                return result('existing-race-verified')
            except OSError as error:
                if error.errno == errno.EMLINK or getattr(error, 'winerror', None) == 1142:
                    continue
                raise
            linked = os.lstat(target)
            require((linked.st_dev, linked.st_ino) == identity, 'Created font atlas link has another identity')
            try:
                if linked.st_nlink > FONT_CACHE_MAX_LINKS:
                    _remove_created_font_link(target, cache_file, identity)
                    continue
                os.chmod(target, stat.S_IREAD)
                _verify_payload_file(target, digest, size, 'Materialized font atlas')
                _verify_payload_file(cache_file, digest, size, 'Materialized font cache')
            except BaseException:
                if os.path.lexists(target):
                    _remove_created_font_link(target, cache_file, identity)
                raise
            return result('hardlink', cache_file, index)
    raise ValueError('Font cache exhausted its bounded shards; independent scene copies are forbidden')


def materialize_font_atlas(source: Path, target: Path, expected_hash: str) -> dict:
    """Keep existing scene names and bytes; share only exact interactive layouts."""
    source, target = Path(source), Path(target)
    require(re.fullmatch(r'[0-9a-f]{64}', expected_hash) is not None, 'Malformed original font atlas hash')
    _reject_reparse(source, 'Original font atlas')
    info = os.lstat(source)
    require(stat.S_ISREG(info.st_mode) and 0 < info.st_size <= MAX_ASSET_BYTES, 'Unbounded original font atlas')
    _verify_payload_file(source, expected_hash, info.st_size, 'Original font atlas')
    data = source.read_bytes()
    require(len(data) == info.st_size and _payload_hash(data) == expected_hash, 'Original font atlas changed during read')
    selected = _interactive_scene_asset_cache(target.parent)
    if selected is not None:
        result = materialize_sharded_payload(data, target, selected.with_name('ui-font-atlases'))
    else:
        _reject_reparse(target, 'Standalone font atlas target')
        target.parent.mkdir(parents=True, exist_ok=True)
        _reject_reparse(target.parent, 'Standalone font atlas directory')
        method = 'existing-verified'
        if not os.path.lexists(target):
            try:
                with target.open('xb') as output:
                    output.write(data)
                method = 'standalone-copy'
            except FileExistsError:
                method = 'existing-race-verified'
        _verify_payload_file(target, expected_hash, len(data), 'Standalone font atlas target')
        result = {'method': method, 'cache_file': None, 'sha256': expected_hash,
                  'bytes': len(data), 'shard_index': None}
    _verify_payload_file(source, expected_hash, info.st_size, 'Retained original font atlas')
    return result


@dataclass(frozen=True)
class Entry:
    name: str
    size: int
    offset: int
    stamp: int


class Fpk:
    def __init__(self, path):
        self.path = Path(path).resolve(strict=True)
        require(self.path.is_file(), 'FPK is not a regular file')
        self.length = self.path.stat().st_size
        self.entries = {}
        with self.path.open('rb') as stream:
            header = exact(stream, 14)
            require(header[:10] == struct.pack('<I', 6) + b'FPK_\0\0', 'Unsupported FPK version/signature')
            count, = struct.unpack_from('<I', header, 10)
            require(0 < count <= 20000, 'Unbounded or empty FPK table')
            for _ in range(count):
                n, = struct.unpack('<I', exact(stream, 4))
                require(0 < n <= 1024, 'Invalid FPK filename length')
                raw = exact(stream, (n + 3) // 4 * 4)
                padding = len(raw) - n
                require(raw[n:] == (bytes([padding]) + bytes(padding - 1) if padding else b''), 'Invalid FPK name padding')
                try:
                    name = raw[:n].decode('utf-8', errors='strict')
                except UnicodeDecodeError as error:
                    raise ValueError('Invalid FPK filename UTF-8') from error
                parts = name.replace('\\', '/').split('/')
                require(all(part and part not in ('.', '..') for part in parts) and ':' not in name and '\0' not in name,
                        'Unsafe FPK entry path')
                stamp, size, offset = struct.unpack('<QII', exact(stream, 16))
                require(size > 0 and offset <= self.length and size <= self.length - offset, 'FPK asset range outside archive')
                key = name.casefold()
                require(key not in self.entries, 'Duplicate FPK entry')
                self.entries[key] = Entry(name, size, offset, stamp)
            self.table_end = stream.tell()
        ordered = sorted(self.entries.values(), key=lambda entry: entry.offset)
        require(ordered[0].offset >= self.table_end, 'FPK asset overlaps table')
        require(all(a.offset + a.size <= b.offset for a, b in zip(ordered, ordered[1:])), 'Overlapping FPK assets')

    def read(self, name):
        entry = self.entries[name.casefold()]
        require(entry.size <= MAX_ASSET_BYTES, 'Selected asset exceeds bounded size')
        with self.path.open('rb') as stream:
            stream.seek(entry.offset)
            data = exact(stream, entry.size)
        return data, {'pack_path': str(self.path), 'entry': entry.name,
                      'offset': entry.offset, 'bytes': entry.size,
                      'sha256': hashlib.sha256(data).hexdigest()}


def header(data):
    require(len(data) >= 128 and data[:4] == b'DDS ', 'Missing DDS header')
    words = list(struct.unpack_from('<32I', data))
    require(words[1] == 124 and words[19] == 32, 'Invalid DDS header sizes')
    require(words[2] & 0x1007 == 0x1007 and words[28] == 0, 'Unsupported DDS shape/caps')
    w, h = words[4], words[3]
    require(0 < w <= 8192 and 0 < h <= 8192 and w * h <= MAX_TEXELS, 'Unbounded DDS dimensions')
    require(words[6] in (0, 1), 'DDS volume not supported')
    return words


def rgba32(words):
    require(words[20:27] == [0x41, 0, 32, 0xff0000, 0xff00, 0xff, 0xff000000], 'Unsupported UI DDS pixel format')


def normalized_header(words, w, h):
    out = list(words)
    out[2] = 0x100f  # CAPS, HEIGHT, WIDTH, PITCH, PIXELFORMAT
    out[3:8] = [h, w, w * 4, 0, 1]
    out[8:19] = [0] * 11
    out[27:32] = [0x1000, 0, 0, 0, 0]
    return struct.pack('<32I', *out)


def decode_dxt5_top_mip(data, words):
    """Expand one bounded DXT5/BC3 top mip to mask-compatible BGRA8 bytes."""
    width, height = words[4], words[3]
    mips = max(words[7], 1)
    require(mips <= max(width, height).bit_length(), 'Invalid DXT5 mip count')
    mip_sizes = []
    for level in range(mips):
        level_width, level_height = max(1, width >> level), max(1, height >> level)
        mip_sizes.append(((level_width + 3) // 4) * ((level_height + 3) // 4) * 16)
    require(len(data) == 128 + sum(mip_sizes), 'Invalid or truncated DXT5 mip payload')
    block_columns = (width + 3) // 4
    block_rows = (height + 3) // 4
    pixels = bytearray(width * height * 4)

    def rgb565(value):
        red = (value >> 11) & 31
        green = (value >> 5) & 63
        blue = value & 31
        return ((red << 3) | (red >> 2), (green << 2) | (green >> 4),
                (blue << 3) | (blue >> 2))

    offset = 128
    for block_y in range(block_rows):
        for block_x in range(block_columns):
            alpha0, alpha1 = data[offset], data[offset + 1]
            alpha_indices = int.from_bytes(data[offset + 2:offset + 8], 'little')
            color0, color1 = struct.unpack_from('<HH', data, offset + 8)
            color_indices = struct.unpack_from('<I', data, offset + 12)[0]
            offset += 16
            if alpha0 > alpha1:
                alpha_table = [alpha0, alpha1] + [
                    ((7 - index) * alpha0 + index * alpha1) // 7 for index in range(1, 7)]
            else:
                alpha_table = [alpha0, alpha1] + [
                    ((5 - index) * alpha0 + index * alpha1) // 5 for index in range(1, 5)] + [0, 255]
            color_a, color_b = rgb565(color0), rgb565(color1)
            color_table = [color_a, color_b,
                           tuple((2 * a + b) // 3 for a, b in zip(color_a, color_b)),
                           tuple((a + 2 * b) // 3 for a, b in zip(color_a, color_b))]
            for local_y in range(4):
                y = block_y * 4 + local_y
                if y >= height:
                    continue
                for local_x in range(4):
                    x = block_x * 4 + local_x
                    if x >= width:
                        continue
                    texel = local_y * 4 + local_x
                    alpha_index = (alpha_indices >> (texel * 3)) & 7
                    color_index = (color_indices >> (texel * 2)) & 3
                    red, green, blue = color_table[color_index]
                    pixel = (y * width + x) * 4
                    # The normalized DDS masks below are R=0x00RRGGBB,
                    # G=0x0000GG00, B=0x000000BB, A=0xAA000000.
                    # Little-endian payload bytes must therefore be BGRA.
                    pixels[pixel:pixel + 4] = bytes((blue, green, red, alpha_table[alpha_index]))
    return bytes(pixels), {'encoding': 'DXT5_BC3_TOP_MIP_BGRA8', 'width': width, 'height': height,
                           'source_mips': mips,
                           'block_size': 4, 'bytes_per_block': 16,
                           'partial_edge_blocks_clipped_to_declared_dimensions': True,
                           'source_scalable': False}


def decode_dxt1_top_mip(data, words):
    """Expand bounded DXT1/BC1 top-mip blocks, including the transparent palette mode."""
    width, height = words[4], words[3]
    mips = max(words[7], 1)
    require(mips <= max(width, height).bit_length(), 'Invalid DXT1 mip count')
    mip_sizes = []
    for level in range(mips):
        level_width, level_height = max(1, width >> level), max(1, height >> level)
        mip_sizes.append(((level_width + 3) // 4) * ((level_height + 3) // 4) * 8)
    require(len(data) == 128 + sum(mip_sizes), 'Invalid or truncated DXT1 mip payload')
    block_columns = (width + 3) // 4
    block_rows = (height + 3) // 4
    pixels = bytearray(width * height * 4)

    def rgb565(value):
        red = (value >> 11) & 31
        green = (value >> 5) & 63
        blue = value & 31
        return ((red << 3) | (red >> 2), (green << 2) | (green >> 4),
                (blue << 3) | (blue >> 2))

    offset = 128
    for block_y in range(block_rows):
        for block_x in range(block_columns):
            color0, color1, color_bits = struct.unpack_from('<HHI', data, offset)
            offset += 8
            color_a, color_b = rgb565(color0), rgb565(color1)
            if color0 > color1:
                color_table = [color_a, color_b,
                               tuple((2 * a + b) // 3 for a, b in zip(color_a, color_b)),
                               tuple((a + 2 * b) // 3 for a, b in zip(color_a, color_b))]
            else:
                color_table = [color_a, color_b,
                               tuple((a + b) // 2 for a, b in zip(color_a, color_b)), None]
            for local_y in range(4):
                y = block_y * 4 + local_y
                if y >= height:
                    continue
                for local_x in range(4):
                    x = block_x * 4 + local_x
                    if x >= width:
                        continue
                    color_index = (color_bits >> ((local_y * 4 + local_x) * 2)) & 3
                    pixel = (y * width + x) * 4
                    color = color_table[color_index]
                    if color is None:
                        pixels[pixel:pixel + 4] = b'\0\0\0\0'
                    else:
                        red, green, blue = color
                        pixels[pixel:pixel + 4] = bytes((blue, green, red, 255))
    return bytes(pixels), {'encoding': 'DXT1_BC1_TOP_MIP_BGRA8', 'width': width, 'height': height,
                           'source_mips': mips,
                           'block_size': 4, 'bytes_per_block': 8,
                           'partial_edge_blocks_clipped_to_declared_dimensions': True,
                           'transparent_palette_mode': 'COLOR0_LE_COLOR1_INDEX3_ALPHA0',
                           'source_scalable': False}


def decode_dds(data, index_data=None):
    """Return standard top-level RGBA DDS plus precise conversion metadata.

    Pixels are copied byte-for-byte, with no color, palette, alpha or resize edits.
    FTXT BC0NN uses a hexadecimal tile size plus 8/16-bit tile indices.
    """
    words = header(data)
    w, h = words[4], words[3]
    tag = data[116:124].split(b'\0', 1)[0]
    marker = data[32:76].split(b'\0', 1)[0]
    if marker == b'FTXTInterface Compressed':
        require(index_data is None and tag == b'COLOR' and words[20] == 0x4 and
                words[21] in (int.from_bytes(b'DXT1', 'little'), int.from_bytes(b'DXT5', 'little')),
                'Only FTXTInterface Compressed DXT1/BC1 and DXT5/BC3 are supported')
        pixels, conversion = (decode_dxt1_top_mip(data, words)
                              if words[21] == int.from_bytes(b'DXT1', 'little')
                              else decode_dxt5_top_mip(data, words))
        rgba_words = list(words)
        rgba_words[2] = 0x100f
        rgba_words[3:8] = [h, w, w * 4, 0, 1]
        rgba_words[8:19] = [0] * 11
        rgba_words[19:27] = [32, 0x41, 0, 32, 0xff0000, 0xff00, 0xff, 0xff000000]
        rgba_words[27:32] = [0x1000, 0, 0, 0, 0]
        return struct.pack('<32I', *rgba_words) + pixels, conversion
    rgba32(words)
    if marker in (b'FTXTInterface', b'FTXTInterface Scalable') and tag.startswith(b'BC0') and len(tag) == 5:
        try:
            tile = int(tag[3:].decode('ascii'), 16)
        except (UnicodeDecodeError, ValueError):
            tile = 0
        require(tile in (1, 2, 4, 8, 16, 64), 'Unsupported FTXT tile size')
        require(index_data is not None, 'FTXT tile map is missing')
        require(w % tile == 0 and h % tile == 0 and len(data) == 128 + w * h * 4,
                'Invalid FTXT dictionary dimensions/length')
        iw = header(index_data)
        require(index_data[32:76].split(b'\0', 1)[0] == marker and
                index_data[116:124].split(b'\0', 1)[0] == tag, 'FTXT dictionary/map tile tag mismatch')
        require(iw[20] == 0x20000 and iw[21] == 0 and iw[22] in (8, 16) and iw[7] == 1,
                'Unsupported FTXT index encoding')
        nx, ny, bits = iw[4], iw[3], iw[22]
        require(len(index_data) == 128 + nx * ny * (bits // 8), 'Invalid FTXT map length')
        ow, oh = nx * tile, ny * tile
        require(ow <= 8192 and oh <= 8192 and ow * oh <= MAX_TEXELS, 'Unbounded decoded texture')
        indices = [value[0] for value in struct.iter_unpack('<B' if bits == 8 else '<H', index_data[128:])]
        cols, rows = w // tile, h // tile
        require(indices and max(indices) < cols * rows, 'FTXT index outside dictionary')
        pixels = bytearray(ow * oh * 4)
        for i, index in enumerate(indices):
            dx, dy = (i % nx) * tile, (i // nx) * tile
            sx, sy = (index % cols) * tile, (index // cols) * tile
            for row in range(tile):
                source = 128 + ((sy + row) * w + sx) * 4
                dest = ((dy + row) * ow + dx) * 4
                pixels[dest:dest + tile * 4] = data[source:source + tile * 4]
        out = normalized_header(words, ow, oh) + pixels
        return out, {'encoding': 'FTXT_TILE_MAP_LOSSLESS', 'tile_size': tile,
                     'index_bits': bits, 'dictionary_width': w, 'dictionary_height': h,
                     'width': ow, 'height': oh, 'pixel_byte_transform': 'COPY_ONLY',
                     'dictionary_tiles': cols * rows, 'highest_index': max(indices),
                     'source_scalable': marker == b'FTXTInterface Scalable'}
    require(index_data is None, 'Unexpected tile map for uncompressed texture')
    # Civ V's original UI animation textures use a distinct, untiled raw-RGBA
    # wrapper. The other FTXTUnnamed UI entries are BC0NN font dictionaries,
    # which are rejected here and still require their paired index DDS above.
    unnamed_rgba = marker == b'FTXTUnnamed' and tag == b'Typeless'
    require(not marker.startswith(b'FTXT') or marker in (b'FTXTInterface', b'FTXTInterface Scalable') or
            unnamed_rgba, 'Unknown FTXT encoding')
    require(not (tag.startswith(b'BC0') and len(tag) == 5),
            'Private tiled DDS cannot be used as ordinary pixels')
    mips = max(words[7], 1)
    require(mips <= max(w, h).bit_length(), 'Invalid DDS mip count')
    expected = sum(max(1, w >> i) * max(1, h >> i) * 4 for i in range(mips))
    require(len(data) == 128 + expected, 'Uncompressed DDS length mismatch')
    out = normalized_header(words, w, h) + data[128:128 + w * h * 4]
    return out, {'encoding': 'FTXT_UNNAMED_RGBA32_TOP_MIP_COPY' if unnamed_rgba else 'RGBA32_TOP_MIP_COPY', 'width': w, 'height': h,
                 'source_mips': mips, 'pixel_byte_transform': 'COPY_ONLY',
                 'source_scalable': marker == b'FTXTInterface Scalable'}


def observed_load_menu_check_defaults(style_source, control_source, assets):
    """Observe original art and declare, but do not certify, its implicit binding."""
    style_source, control_source = Path(style_source), Path(control_source)
    style_root = ET.parse(style_source).getroot()
    button = style_root.find('Button_16')
    style_attrs = {'Texture': 'Assets/UI/Art/Controls/Checkbox.dds', 'Size': '32,32'}
    if button is None or dict(button.attrib) != style_attrs or list(button):
        raise ValueError('LoadMenu checkbox candidate requires the original Button_16 source')
    original = ET.parse(control_source).getroot()
    expected = {
        'AutoCheck': {'Offset': '50,55', 'Anchor': 'R,T', 'String': 'TXT_KEY_AUTOSAVES',
                      'TextAnchor': 'L,C', 'IsChecked': '0', 'ID': 'AutoCheck'},
        'CloudCheck': {'Offset': '315,55', 'Anchor': 'R,T', 'String': 'TXT_KEY_STEAMCLOUD',
                       'TextAnchor': 'L,C', 'IsChecked': '0', 'ID': 'CloudCheck'},
    }
    for control_id, attributes in expected.items():
        matches = original.findall(".//*[@ID='" + control_id + "']")
        if len(matches) != 1 or matches[0].tag != 'CheckBox' or dict(matches[0].attrib) != attributes:
            raise ValueError('LoadMenu checkbox differs from its original implicit declaration: ' + control_id)
    selected = next((pack for pack in assets.packs if 'checkbox.dds' in pack.entries), None)
    if selected is None:
        raise ValueError('Original LoadMenu checkbox atlas is missing')
    raw, atlas_source = selected.read('checkbox.dds')
    private = (raw[32:76].split(b'\0', 1)[0] in (b'FTXTInterface', b'FTXTInterface Scalable') and
               raw[116:124].startswith(b'BC0'))
    index, index_source = selected.read('checkbox-index.dds') if private else (None, None)
    decoded, conversion = decode_dds(raw, index)
    if (conversion.get('width'), conversion.get('height')) != (32, 128):
        raise ValueError('Original LoadMenu checkbox atlas is not four vertical 32x32 cells')
    common = {
        'policy': 'LOAD_MENU_BUTTON_16_DEFAULT_CANDIDATE_V1',
        'width': 32, 'height': 32, 'frameCount': 4, 'style': 'Button_16',
        'texture': style_attrs['Texture'], 'sourceStyleAttributes': style_attrs,
        'source': {'path': str(style_source), 'sha256': sha256(style_source)},
        'controlSource': {'path': str(control_source), 'sha256': sha256(control_source)},
        'atlasSource': atlas_source, 'atlasIndexSource': index_source,
        'atlas': {'width': 32, 'height': 128, 'cellWidth': 32, 'cellHeight': 32,
                  'frameCount': 4, 'sha256': hashlib.sha256(decoded).hexdigest()},
        'defaultBindingVerified': False, 'retailGeometryVerified': False,
        'retailWidgetStateMappingVerified': False,
    }
    result = {}
    for control_id, attributes in expected.items():
        result[control_id] = deepcopy(common)
        result[control_id]['controlSourceAttributes'] = attributes
    return result


class UiAssets:
    def __init__(self, game_root):
        self.game_root = Path(game_root).resolve(strict=True)
        self.packs = [Fpk(self.game_root / 'Resource/DX9' / name) for name in PACK_POLICY]
        digests = _pack_sha256(pack.path for pack in self.packs)
        self.pack_records = [{'path': str(pack.path), 'sha256': digest,
                              'bytes': pack.length, 'entries': len(pack.entries)}
                             for pack, digest in zip(self.packs, digests)]
        self.records = []
        self.outputs = {}
        self.loose_records = []

    def resolve(self, texture_name, destination):
        basename = texture_name.replace('\\', '/').rsplit('/', 1)[-1].casefold()
        require(basename.endswith('.dds') and basename not in ('', '.dds') and ':' not in basename,
                'Expected DDS texture basename')
        if basename in self.outputs:
            return self.outputs[basename]
        matches = [pack for pack in self.packs if basename in pack.entries]
        if matches:
            selected = matches[0]
            data, source = selected.read(basename)
        else:
            loose = LOOSE_UI_TEXTURES.get(basename)
            require(type(loose) is dict, 'Missing original UI texture: ' + basename)
            relative = Path(loose['relative_path'])
            require(not relative.is_absolute() and '..' not in relative.parts,
                    'Loose original UI texture path is not installation-relative')
            source_path = self.game_root / relative
            _reject_reparse(source_path, 'Loose original UI texture')
            source_path = source_path.resolve(strict=True)
            require(source_path.is_relative_to(self.game_root) and source_path.is_file() and
                    source_path.stat().st_size == loose['bytes'],
                    'Loose original UI texture path or byte count differs from its frozen contract')
            before = sha256(source_path)
            data = source_path.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            require(len(data) == loose['bytes'] and before == digest == loose['sha256'] and
                    sha256(source_path) == before,
                    'Loose original UI texture hash differs from its frozen contract or changed during read')
            source = {'kind': 'loose-ui-texture', 'path': str(source_path),
                      'relative_path': loose['relative_path'], 'bytes': len(data), 'sha256': digest}
            if not hasattr(self, 'loose_records'):
                self.loose_records = []
            self.loose_records.append({'path': str(source_path), 'bytes': len(data), 'sha256': digest})
        index_name = basename[:-4] + '-index.dds'
        tag = data[116:124].split(b'\0', 1)[0]
        private = (data[32:76].split(b'\0', 1)[0] in (b'FTXTInterface', b'FTXTInterface Scalable') and
                   tag.startswith(b'BC0') and len(tag) == 5)
        index, index_record = selected.read(index_name) if private else (None, None)
        try:
            normalized, conversion = decode_dds(data, index)
        except ValueError as error:
            raise ValueError(f'UI texture {basename} from {selected.path.name}: {error}') from error
        source_asset_cache_root = _interactive_scene_asset_cache(destination)
        destination = candidate_directory(destination, self.game_root)
        # Keep archive names in provenance, but avoid carrying their length into
        # deep per-session Windows paths. Prefix collisions must still preserve
        # exact bytes; a candidate is never silently overwritten.
        def retain(folder, requested, payload):
            identity = hashlib.sha256(requested.encode('utf8')).hexdigest()[:8]
            payload_hash = hashlib.sha256(payload).hexdigest()
            path = folder / (identity + '-' + payload_hash[:16] + '.dds')
            if path.exists():
                require(path.is_file() and not path.is_symlink() and sha256(path) == payload_hash,
                        'Candidate texture identity collides with different retained bytes')
            else:
                require(not path.is_symlink(), 'Candidate texture destination is a symlink')
                with path.open('xb') as stream:
                    stream.write(payload)
            return path

        def retain_frozen(folder, requested, payload):
            if source_asset_cache_root is None:
                return retain(folder, requested, payload)
            identity = hashlib.sha256(requested.encode('utf8')).hexdigest()[:8]
            payload_hash = hashlib.sha256(payload).hexdigest()
            path = folder / (identity + '-' + payload_hash[:16] + '.dds')
            cache_file, _cache_publish = _publish_cached_payload(payload, source_asset_cache_root)
            _materialize_cached_payload(cache_file, path, payload_hash, len(payload))
            return path

        output = retain_frozen(destination, basename, normalized)
        retained = candidate_directory(destination.parent / 'source_assets', self.game_root)
        frozen_source = retain_frozen(retained, basename, data)
        frozen_index = None
        if index is not None:
            frozen_index = retain_frozen(retained, index_name, index)
        record = {'requested_name': texture_name, 'basename': basename, 'source': source,
                  'index_source': index_record,
                  'candidate_sources': ([str(pack.path) for pack in matches] if matches else [source['path']]),
                  'frozen_source': {'path': str(frozen_source), 'sha256': hashlib.sha256(data).hexdigest()},
                  'frozen_index': {'path': str(frozen_index), 'sha256': hashlib.sha256(index).hexdigest()} if frozen_index else None,
                  'conversion': conversion, 'output': {'path': str(output.resolve()),
                  'bytes': len(normalized), 'sha256': hashlib.sha256(normalized).hexdigest()},
                  'candidate_filename_policy': 'REQUEST_SHA8_PAYLOAD_SHA16_DDS_V1'}
        self.records.append(record)
        self.outputs[basename] = record
        return record

    def unchanged(self):
        if any(Path(row['path']).stat().st_size != row['bytes'] for row in self.pack_records):
            return False
        digests = _pack_sha256(row['path'] for row in self.pack_records)
        packs_unchanged = all(digest == row['sha256'] for row, digest in zip(self.pack_records, digests))
        loose_unchanged = all(Path(row['path']).is_file() and
                              Path(row['path']).stat().st_size == row['bytes'] and
                              sha256(row['path']) == row['sha256']
                              for row in getattr(self, 'loose_records', []))
        return packs_unchanged and loose_unchanged
