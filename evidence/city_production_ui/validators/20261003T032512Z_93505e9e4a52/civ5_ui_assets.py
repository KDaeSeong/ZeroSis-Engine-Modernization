"""Bounded Civ V FPK v6 reads and lossless FTXTInterface tile-map decoding.

Only selected entries are read. Installations are never modified or bulk unpacked.
The expansion priority is an explicit isolated candidate policy, not retail proof.
FTXT pairs are resolved from the same pack; missing or malformed data fails closed.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import struct
from typing import BinaryIO

MAX_ASSET_BYTES = 64 * 1024 * 1024
MAX_TEXELS = 16 * 1024 * 1024
PACK_POLICY = ('Expansion2UITextures.fpk', 'Expansion1UITextures.fpk', 'UITextures.fpk')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def exact(stream: BinaryIO, length: int):
    data = stream.read(length)
    require(len(data) == length, 'Truncated FPK table or asset')
    return data


def candidate_directory(destination, game_root):
    destination = Path(destination).resolve()
    require(not destination.is_relative_to(Path(game_root).resolve()), 'Candidate output may not be inside the game installation')
    destination.mkdir(parents=True, exist_ok=True)
    return destination


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


def decode_dds(data, index_data=None):
    """Return standard top-level RGBA DDS plus precise conversion metadata.

    Pixels are copied byte-for-byte, with no color, palette, alpha or resize edits.
    FTXT BC00N specifies an N x N tile dictionary plus 8/16-bit tile indices.
    """
    words = header(data)
    rgba32(words)
    w, h = words[4], words[3]
    tag = data[116:124].split(b'\0', 1)[0]
    marker = data[32:76].split(b'\0', 1)[0]
    if marker == b'FTXTInterface' and tag.startswith(b'BC00'):
        require(tag in (b'BC001', b'BC002', b'BC004', b'BC008'), 'Unsupported FTXT tile size')
        require(index_data is not None, 'FTXT tile map is missing')
        tile = int(tag[-1:])
        require(w % tile == 0 and h % tile == 0 and len(data) == 128 + w * h * 4,
                'Invalid FTXT dictionary dimensions/length')
        iw = header(index_data)
        require(index_data[32:76].split(b'\0', 1)[0] == b'FTXTInterface' and
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
                     'dictionary_tiles': cols * rows, 'highest_index': max(indices), 'source_scalable': False}
    require(index_data is None, 'Unexpected tile map for uncompressed texture')
    require(not marker.startswith(b'FTXT') or marker in (b'FTXTInterface', b'FTXTInterface Scalable'), 'Unknown FTXT encoding')
    require(not tag.startswith(b'BC00'), 'Private tiled DDS cannot be used as ordinary pixels')
    mips = max(words[7], 1)
    require(mips <= max(w, h).bit_length(), 'Invalid DDS mip count')
    expected = sum(max(1, w >> i) * max(1, h >> i) * 4 for i in range(mips))
    require(len(data) == 128 + expected, 'Uncompressed DDS length mismatch')
    out = normalized_header(words, w, h) + data[128:128 + w * h * 4]
    return out, {'encoding': 'RGBA32_TOP_MIP_COPY', 'width': w, 'height': h,
                 'source_mips': mips, 'pixel_byte_transform': 'COPY_ONLY',
                 'source_scalable': marker == b'FTXTInterface Scalable'}


class UiAssets:
    def __init__(self, game_root):
        self.game_root = Path(game_root).resolve(strict=True)
        self.packs = [Fpk(self.game_root / 'Resource/DX9' / name) for name in PACK_POLICY]
        self.pack_records = [{'path': str(pack.path), 'sha256': sha256(pack.path),
                              'bytes': pack.length, 'entries': len(pack.entries)} for pack in self.packs]
        self.records = []
        self.outputs = {}

    def resolve(self, texture_name, destination):
        basename = texture_name.replace('\\', '/').rsplit('/', 1)[-1].casefold()
        require(basename.endswith('.dds') and basename not in ('', '.dds') and ':' not in basename,
                'Expected DDS texture basename')
        if basename in self.outputs:
            return self.outputs[basename]
        matches = [pack for pack in self.packs if basename in pack.entries]
        require(matches, 'Missing original UI texture: ' + basename)
        selected = matches[0]
        data, source = selected.read(basename)
        index_name = basename[:-4] + '-index.dds'
        private = data[32:76].split(b'\0', 1)[0] == b'FTXTInterface' and data[116:124].startswith(b'BC00')
        index, index_record = selected.read(index_name) if private else (None, None)
        normalized, conversion = decode_dds(data, index)
        destination = candidate_directory(destination, self.game_root)
        output = destination / basename
        require(not output.exists() and not output.is_symlink(), 'Refusing to overwrite extracted candidate texture')
        with output.open('xb') as stream:
            stream.write(normalized)
        retained = candidate_directory(destination.parent / 'source_assets', self.game_root)
        frozen_source = retained / basename
        with frozen_source.open('xb') as stream:
            stream.write(data)
        frozen_index = None
        if index is not None:
            frozen_index = retained / index_name
            with frozen_index.open('xb') as stream:
                stream.write(index)
        record = {'requested_name': texture_name, 'basename': basename, 'source': source,
                  'index_source': index_record, 'candidate_sources': [str(pack.path) for pack in matches],
                  'frozen_source': {'path': str(frozen_source), 'sha256': hashlib.sha256(data).hexdigest()},
                  'frozen_index': {'path': str(frozen_index), 'sha256': hashlib.sha256(index).hexdigest()} if frozen_index else None,
                  'conversion': conversion, 'output': {'path': str(output.resolve()),
                  'bytes': len(normalized), 'sha256': hashlib.sha256(normalized).hexdigest()}}
        self.records.append(record)
        self.outputs[basename] = record
        return record

    def unchanged(self):
        return all(Path(row['path']).stat().st_size == row['bytes'] and sha256(row['path']) == row['sha256']
                   for row in self.pack_records)
