"""Independent tile/pixel examples and corrupt FPK boundaries, no game required."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import errno
import hashlib
import json
import os
import stat
import struct
import sys
import tempfile
import threading
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import civ5_ui_assets as asset_module
import interactive_ui_driver as ui_driver
from civ5_ui_assets import (Fpk, UiAssets, decode_dds, candidate_directory, sha256, header, rgba32,
                            _interactive_scene_asset_cache, _materialize_cached_payload,
                            _publish_cached_payload, materialize_font_atlas, materialize_sharded_payload)

checks = 0


def check(ok):
    global checks
    assert ok
    checks += 1


def reject(call):
    try:
        call()
    except (ValueError, KeyError, RuntimeError):
        check(True)
    else:
        raise AssertionError('Malformed input was accepted')


def dds(w, h, pixels, *, tile=0, bits=32):
    values = [0] * 32
    values[0:5] = [0x20534444, 124, 0x100f, h, w]
    values[5] = w * (bits // 8)
    values[7] = 1
    values[19:27] = [32, 0x41, 0, 32, 0xff0000, 0xff00, 0xff, 0xff000000]
    if bits != 32:
        values[20:27] = [0x20000, 0, bits, 0, 0, 0, 0]
    values[27] = 0x1000
    raw = bytearray(struct.pack('<32I', *values))
    if tile:
        raw[32:45] = b'FTXTInterface'
        raw[116:121] = f'BC0{tile:02X}'.encode()
    return bytes(raw) + pixels


def dxt5_dds(w, h, blocks, *, mips=0, fourcc=b'DXT5', marker=b'FTXTInterface Compressed'):
    values = [0] * 32
    values[0:5] = [0x20534444, 124, 0x1007, h, w]
    values[7] = mips
    values[19:27] = [32, 0x4, int.from_bytes(fourcc, 'little'), 0, 0, 0, 0, 0]
    values[27] = 0x1000
    raw = bytearray(struct.pack('<32I', *values))
    raw[32:32 + len(marker)] = marker
    raw[116:121] = b'COLOR'
    return bytes(raw) + blocks


def as_scalable(data):
    result = bytearray(data)
    marker = b'FTXTInterface Scalable'
    result[32:76] = marker + bytes(44 - len(marker))
    return bytes(result)


def dxt5_block(alpha0, alpha1, alpha_indices, color0, color1, color_indices):
    alpha_bits = sum((index & 7) << (3 * position)
                     for position, index in enumerate(alpha_indices))
    color_bits = sum((index & 3) << (2 * position)
                     for position, index in enumerate(color_indices))
    return bytes((alpha0, alpha1)) + alpha_bits.to_bytes(6, 'little') + \
           struct.pack('<HHI', color0, color1, color_bits)


def dxt1_dds(w, h, blocks, *, mips=0, fourcc=b'DXT1', marker=b'FTXTInterface Compressed'):
    values = [0] * 32
    values[0:5] = [0x20534444, 124, 0x1007, h, w]
    values[7] = mips
    values[19:27] = [32, 0x4, int.from_bytes(fourcc, 'little'), 0, 0, 0, 0, 0]
    values[27] = 0x1000
    raw = bytearray(struct.pack('<32I', *values))
    raw[32:32 + len(marker)] = marker
    raw[116:121] = b'COLOR'
    return bytes(raw) + blocks


def dxt1_block(color0, color1, color_indices):
    bits = sum((index & 3) << (2 * position)
               for position, index in enumerate(color_indices))
    return struct.pack('<HHI', color0, color1, bits)


def make_fpk(rows):
    header = struct.pack('<I', 6) + b'FPK_\0\0' + struct.pack('<I', len(rows))
    names = [name.encode() for name, _ in rows]
    cursor = 14 + sum(4 + (len(name) + 3) // 4 * 4 + 16 for name in names)
    records, body = [], []
    for raw, (_, payload) in zip(names, rows):
        pad = (-len(raw)) % 4
        padding = bytes([pad]) + bytes(pad - 1) if pad else b''
        records.append(struct.pack('<I', len(raw)) + raw + padding + struct.pack('<QII', 0, len(payload), cursor))
        body.append(payload)
        cursor += len(payload)
    return header + b''.join(records) + b''.join(body)


def main():
    # Four independently colored 2x2 tiles in a 4x4 dictionary. Shuffle them so
    # transposition, row-stride and mistaken pixel-index implementations fail.
    a, b, c, d = [bytes((v, v + 1, v + 2, v + 3)) for v in (0, 20, 40, 60)]
    dictionary_pixels = (a * 2 + b * 2) * 2 + (c * 2 + d * 2) * 2
    dictionary = dds(4, 4, dictionary_pixels, tile=2)
    expected = (d * 2 + b * 2 + c * 2) * 2 + (a * 2 + c * 2 + b * 2) * 2
    for bits in (8, 16):
        idx = struct.pack('<6B' if bits == 8 else '<6H', 3, 1, 2, 0, 2, 1)
        mapping = dds(3, 2, idx, tile=2, bits=bits)
        actual, meta = decode_dds(dictionary, mapping)
        check(actual[128:] == expected)
        check(struct.unpack_from('<II', actual, 12) == (4, 6))
        check(meta['index_bits'] == bits and meta['pixel_byte_transform'] == 'COPY_ONLY')
        check(actual[32:76] == bytes(44) and actual[116:128] == bytes(12))
        # The great-person meter uses the same tile encoding with a scalable
        # marker. Its shuffled pixels and dimensions must remain exact.
        scaled, scaled_meta = decode_dds(as_scalable(dictionary), as_scalable(mapping))
        check(scaled == actual and scaled_meta['source_scalable'] is True)
        reject(lambda: decode_dds(as_scalable(dictionary), mapping))
        reject(lambda: decode_dds(dictionary, as_scalable(mapping)))
        reject(lambda: decode_dds(as_scalable(dictionary)))
        reject(lambda: decode_dds(dictionary, mapping[:-1]))
        malformed = bytearray(mapping)
        malformed[128:128 + bits // 8] = (4).to_bytes(bits // 8, 'little')
        reject(lambda: decode_dds(dictionary, malformed))
    for tile in (1, 4, 8):
        pixels = a * (tile * tile) + b * (tile * tile) if tile == 1 else ((a * tile + b * tile) * tile)
        source = dds(tile * 2, tile, pixels, tile=tile)
        actual, meta = decode_dds(source, dds(1, 1, b'\x01', tile=tile, bits=8))
        check(actual[128:] == b * tile * tile and meta['width'] == tile)
    tile16_pixels = b''.join(a * 16 + b * 16 for _ in range(16))
    tile16_source = dds(32, 16, tile16_pixels, tile=16)
    tile16_map = dds(1, 1, b'\x01', tile=16, bits=8)
    tile16_actual, tile16_meta = decode_dds(tile16_source, tile16_map)
    check(tile16_actual[128:] == b * (16 * 16) and
          tile16_meta['tile_size'] == 16 and tile16_meta['width'] == 16 and
          tile16_meta['height'] == 16)
    tile64_pixels = bytes((index % 256 for index in range(64 * 64 * 4)))
    tile64_source = dds(64, 64, tile64_pixels, tile=64)
    tile64_map = dds(1, 1, b'\x00', tile=64, bits=8)
    tile64_actual, tile64_meta = decode_dds(tile64_source, tile64_map)
    check(tile64_actual[128:] == tile64_pixels and tile64_meta['tile_size'] == 64 and
          tile64_meta['width'] == 64 and tile64_meta['height'] == 64)
    reject(lambda: decode_dds(dds(32, 32, bytes(32 * 32 * 4), tile=32),
                              dds(1, 1, b'\x00', tile=32, bits=8)))
    reject(lambda: decode_dds(dictionary))
    wrong_tag = dds(3, 2, bytes(6), tile=4, bits=8)
    reject(lambda: decode_dds(dictionary, wrong_tag))
    reject(lambda: decode_dds(dictionary[:-1], dds(1, 1, b'\0', tile=2, bits=8)))
    reject(lambda: decode_dds(dds(3, 4, bytes(48), tile=2), dds(1, 1, b'\0', tile=2, bits=8)))
    normal = dds(2, 2, a + b + c + d)
    check(decode_dds(normal)[0][128:] == a + b + c + d)
    scalable = bytearray(normal)
    marker = b'FTXTInterface Scalable'
    scalable[32:32 + len(marker)] = marker
    scalable[116:121] = b'COLOR'
    scaled, meta = decode_dds(scalable)
    check(scaled[128:] == a + b + c + d and meta['source_scalable'] is True)
    unnamed_rgba = bytearray(normal)
    unnamed_rgba[2 * 4:3 * 4] = struct.pack('<I', 0x21007)
    unnamed_rgba[32:76] = b'FTXTUnnamed' + bytes(33)
    unnamed_rgba[116:124] = b'Typeless'
    unnamed_rgba[27 * 4:32 * 4] = struct.pack('<5I', 0x401008, 0, 0x65707954, 0x7373656c, 0)
    copied, copied_meta = decode_dds(unnamed_rgba)
    unnamed_header = header(unnamed_rgba)
    copied_header = header(copied)
    rgba32(unnamed_header)
    rgba32(copied_header)
    expected_raw_size = 128 + unnamed_header[4] * unnamed_header[3] * 4
    check(unnamed_header[7] == 1 and len(unnamed_rgba) == expected_raw_size and
          copied_header[7] == 1 and len(copied) == expected_raw_size and
          copied[128:] == unnamed_rgba[128:] == a + b + c + d and
          copied_meta['encoding'] == 'FTXT_UNNAMED_RGBA32_TOP_MIP_COPY' and
          copied_meta['pixel_byte_transform'] == 'COPY_ONLY')
    unnamed_dictionary = bytearray(dictionary)
    unnamed_dictionary[32:76] = b'FTXTUnnamed' + bytes(33)
    reject(lambda: decode_dds(unnamed_dictionary))
    reject(lambda: decode_dds(normal + b'\0'))
    reject(lambda: decode_dds(normal[:127]))
    huge = bytearray(normal)
    struct.pack_into('<I', huge, 16, 0xffffffff)
    reject(lambda: decode_dds(huge))
    unknown = bytearray(dictionary)
    unknown[116:121] = b'BC003'
    reject(lambda: decode_dds(unknown))

    # BC3/DXT5 uses a four-color RGB565 block and the two alpha endpoint
    # branches. A 6x3 image also exercises right/bottom partial-block clipping.
    alpha_indices = [index % 8 for index in range(16)]
    color_indices = [index % 4 for index in range(16)]
    block_a = dxt5_block(250, 10, alpha_indices, 0xf800, 0x001f, color_indices)
    block_b = dxt5_block(10, 250, [6, 7] * 8, 0x07e0, 0xf800, [3] * 16)
    decoded, meta = decode_dds(dxt5_dds(6, 3, block_a + block_b))
    pixel = lambda x, y: decoded[128 + (y * 6 + x) * 4:128 + (y * 6 + x + 1) * 4]
    def masked_rgba(x, y):
        packed = int.from_bytes(pixel(x, y), 'little')
        masks = decoded_header[23:27]
        shifts = [next((bit for bit in range(32) if mask & (1 << bit)), 0) for mask in masks]
        return tuple(((packed & mask) >> shift) if mask else 255
                     for mask, shift in zip(masks, shifts))
    decoded_header = header(decoded)
    rgba32(decoded_header)
    check(len(decoded) == 128 + 6 * 3 * 4 and pixel(0, 0) == bytes((0, 0, 255, 250)) and
          masked_rgba(0, 0) == (255, 0, 0, 250))
    check(decoded_header[4] == 6 and decoded_header[3] == 3 and decoded_header[5] == 24 and
          decoded_header[21] == 0 and decoded_header[22:27] ==
          [32, 0xff0000, 0xff00, 0xff, 0xff000000])
    check(pixel(2, 0) == bytes((85, 0, 170, 215)) and
          masked_rgba(2, 0) == (170, 0, 85, 215) and
          pixel(1, 0) == bytes((255, 0, 0, 10)) and masked_rgba(1, 0) == (0, 0, 255, 10))
    check(pixel(4, 0) == bytes((0, 85, 170, 0)) and masked_rgba(4, 0) == (170, 85, 0, 0) and
          pixel(5, 0) == bytes((0, 85, 170, 255)) and masked_rgba(5, 0) == (170, 85, 0, 255) and
          meta['encoding'] == 'DXT5_BC3_TOP_MIP_BGRA8' and
          meta['partial_edge_blocks_clipped_to_declared_dimensions'] is True)
    reject(lambda: decode_dds(dxt5_dds(6, 3, block_a + block_b)[:-1]))
    reject(lambda: decode_dds(dxt5_dds(6, 3, block_a + block_b + b'\0')))
    reject(lambda: decode_dds(dxt5_dds(4, 4, block_a, fourcc=b'DXT1')))
    reject(lambda: decode_dds(dxt5_dds(4, 4, block_a, marker=b'FTXTInterface CompressedX')))

    # DXT1/BC1 SocialPolicy icons use eight-byte blocks. Cover opaque four-color
    # mode, transparent three-color mode, and partial right/bottom blocks.
    opaque_indices = [index % 4 for index in range(16)]
    transparent_indices = [0, 1, 2, 3, 3, 1, 2, 3, 0, 1, 2, 3, 0, 1, 2, 3]
    bc1 = dxt1_dds(5, 3,
                   dxt1_block(0xf800, 0x001f, opaque_indices) +
                   dxt1_block(0x001f, 0x07e0, transparent_indices))
    decoded_bc1, bc1_meta = decode_dds(bc1)
    bc1_pixel = lambda x, y: decoded_bc1[128 + (y * 5 + x) * 4:128 + (y * 5 + x + 1) * 4]
    bc1_header = header(decoded_bc1)
    rgba32(bc1_header)
    check(len(decoded_bc1) == 128 + 5 * 3 * 4 and
          bc1_pixel(0, 0) == bytes((0, 0, 255, 255)) and
          bc1_pixel(2, 0) == bytes((85, 0, 170, 255)) and
          bc1_pixel(3, 0) == bytes((170, 0, 85, 255)) and
          bc1_pixel(4, 0) == bytes((255, 0, 0, 255)) and
          bc1_pixel(4, 1) == bytes(4) and
          bc1_meta['encoding'] == 'DXT1_BC1_TOP_MIP_BGRA8' and
          bc1_meta['partial_edge_blocks_clipped_to_declared_dimensions'] is True)
    reject(lambda: decode_dds(bc1[:-1]))
    reject(lambda: decode_dds(dxt1_dds(4, 4, dxt1_block(0xf800, 0x001f, opaque_indices),
                                      fourcc=b'DXT3')))
    with tempfile.TemporaryDirectory() as temp:
        game = Path(temp) / 'game'
        game.mkdir()
        reject(lambda: candidate_directory(game, game))
        reject(lambda: candidate_directory(game / 'Assets', game))
        output = candidate_directory(Path(temp) / 'candidate', game)
        check(output == (Path(temp) / 'candidate').resolve())
        lexical_session = Path(temp) / 'runtime' / 'sessions' / ('a' * 32)
        lexical_session.mkdir(parents=True)
        check(ui_driver._validate_scene_output_path(str(lexical_session / 'play-ui-7'),
                                                    lexical_session, 7) == lexical_session / 'play-ui-7')
        reject(lambda: ui_driver._validate_scene_output_path(str(lexical_session / 'play-ui-8'),
                                                             lexical_session, 7))
        scene_target = Path(temp) / 'scene-target'
        scene_target.mkdir()
        scene_link = lexical_session / 'play-ui-7'
        try:
            os.symlink(scene_target, scene_link, target_is_directory=True)
        except (OSError, NotImplementedError):
            pass
        else:
            reject(lambda: ui_driver._validate_scene_output_path(str(scene_link), lexical_session, 7))
            scene_link.unlink()
            candidate_link = Path(temp) / 'candidate-link'
            os.symlink(scene_target, candidate_link, target_is_directory=True)
            reject(lambda: candidate_directory(candidate_link, game))
        path = Path(temp) / 'fixture.fpk'
        good = make_fpk([('abc.dds', b'one'), ('longer.dds', b'two')])
        path.write_bytes(good)
        pack = Fpk(path)
        check(pack.read('ABC.DDS')[0] == b'one')
        check(pack.read('longer.dds')[0] == b'two')
        # A packed tile-map name can exceed MAX_PATH when appended to a deep
        # session directory. Both original dictionary/index and normalized pixels
        # must remain readable there without changing the archive's identity.
        long_name = 'portrait_' + 'ancient_medieval_' * 8 + '360.dds'
        mapping = dds(1, 1, b'\x03', tile=2, bits=8)
        archive = Path(temp) / 'path-regression.fpk'
        archive.write_bytes(make_fpk([(long_name, dictionary), (long_name[:-4]+'-index.dds', mapping),
            ('scalable.dds', as_scalable(dictionary)), ('scalable-index.dds', as_scalable(mapping))]))
        archive_hash = sha256(archive)
        deep = Path(temp) / ('session_' + 'x' * max(1, 200-len(str(Path(temp)))))
        resolver = UiAssets.__new__(UiAssets)
        resolver.game_root, resolver.packs = game.resolve(), [Fpk(archive)]
        resolver.records, resolver.outputs = [], {}
        record = resolver.resolve(long_name, deep / 'textures')
        output_dds = Path(record['output']['path'])
        check(len(str(deep/'source_assets'/(long_name[:-4]+'-index.dds'))) > 259)
        check(output_dds.read_bytes()[128:] == d * 4)
        check(Path(record['frozen_source']['path']).read_bytes() == dictionary)
        check(Path(record['frozen_index']['path']).read_bytes() == mapping)
        check(all(len(row['path']) < 260 for row in (record['output'],record['frozen_source'],record['frozen_index'])))
        check(record['basename'] == long_name and record['source']['entry'] == long_name)
        check(resolver.resolve(long_name.upper(),deep/'textures') is record and len(resolver.records)==1)
        scaled_record = resolver.resolve('scalable.dds', deep / 'textures')
        check(Path(scaled_record['output']['path']).read_bytes()[128:] == d * 4)
        check(scaled_record['conversion']['source_scalable'] is True)
        check(Path(scaled_record['frozen_index']['path']).read_bytes() == as_scalable(mapping))
        check(sha256(archive) == archive_hash)

        # One exact loose Civ V UI texture is allowed when it is absent from
        # every FPK; both the preparation and runtime resolver use this same
        # path/hash/byte contract and recheck it after the scene is prepared.
        loose_root = Path(temp) / 'loose-game'
        loose_path = loose_root / 'Assets/UI/Art/Controls/BlueBar500x3.dds'
        loose_path.parent.mkdir(parents=True)
        loose_payload = dds(500, 3, bytes((i % 256 for i in range(500 * 3 * 4))))
        loose_path.write_bytes(loose_payload)
        loose_contract = {'relative_path': 'Assets/UI/Art/Controls/BlueBar500x3.dds',
                          'bytes': len(loose_payload), 'sha256': hashlib.sha256(loose_payload).hexdigest()}
        with mock.patch.dict(asset_module.LOOSE_UI_TEXTURES,
                             {'bluebar500x3.dds': loose_contract}, clear=True):
            loose_resolver = UiAssets.__new__(UiAssets)
            loose_resolver.game_root, loose_resolver.packs = loose_root.resolve(), []
            loose_resolver.pack_records = []
            loose_resolver.records, loose_resolver.outputs, loose_resolver.loose_records = [], {}, []
            loose_record = loose_resolver.resolve('Assets/UI/Art/Controls/BlueBar500x3.dds',
                                                   Path(temp) / 'loose-runtime' / 'textures')
            check(loose_record['source'] == {'kind': 'loose-ui-texture',
                  'path': str(loose_path.resolve()),
                  'relative_path': loose_contract['relative_path'],
                  'bytes': len(loose_payload), 'sha256': loose_contract['sha256']})
            check(loose_record['candidate_sources'] == [str(loose_path.resolve())] and
                  loose_record['index_source'] is None and
                  Path(loose_record['output']['path']).read_bytes()[128:] == loose_payload[128:] and
                  Path(loose_record['frozen_source']['path']).read_bytes() == loose_payload and
                  loose_resolver.unchanged())
            loose_path.write_bytes(bytes([loose_payload[0] ^ 1]) + loose_payload[1:])
            check(not loose_resolver.unchanged())
            loose_path.write_bytes(loose_payload + b'changed')
            check(not loose_resolver.unchanged())
            bad_contract = dict(loose_contract, sha256='0' * 64)
            with mock.patch.dict(asset_module.LOOSE_UI_TEXTURES,
                                 {'bluebar500x3.dds': bad_contract}, clear=True):
                bad_resolver = UiAssets.__new__(UiAssets)
                bad_resolver.game_root, bad_resolver.packs = loose_root.resolve(), []
                bad_resolver.pack_records = []
                bad_resolver.records, bad_resolver.outputs, bad_resolver.loose_records = [], {}, []
                reject(lambda: bad_resolver.resolve('BlueBar500x3.dds',
                                                    Path(temp) / 'loose-bad' / 'textures'))
        for malformed in (good[:13], b'\x05' + good[1:], make_fpk([('../a.dds', b'x')]),
                          make_fpk([('a.dds', b'x'), ('A.DDS', b'y')]), good[:-1]):
            path.write_bytes(malformed)
            reject(lambda: Fpk(path))
        badpad = bytearray(good)
        badpad[14 + 4 + 7] = 0
        path.write_bytes(badpad)
        reject(lambda: Fpk(path))
        badrange = bytearray(good)
        struct.pack_into('<I', badrange, 14 + 4 + 8 + 12, 1)
        path.write_bytes(badrange)
        reject(lambda: Fpk(path))

        # Both original and normalized texture payloads share the Build cache,
        # while each scene keeps its established filename and provenance row.
        build = Path(temp) / 'shared-cache-test' / 'Build'
        cache_root = build / 'RuntimeInputCache' / 'ui-source-assets'
        scene_records = []
        for run_id in ('a' * 12, 'b' * 12):
            resolver = UiAssets.__new__(UiAssets)
            resolver.game_root, resolver.packs = game.resolve(), [Fpk(archive)]
            resolver.records, resolver.outputs = [], {}
            destination = (build / 'InteractiveGameRuntime' / ('20261005T123456Z_' + run_id) /
                           'sessions' / ('c' * 32) / 'play-ui-1' / 'textures')
            check(_interactive_scene_asset_cache(destination) == cache_root)
            row = resolver.resolve(long_name, destination)
            scene_records.append(row)
            check(Path(row['output']['path']).read_bytes()[128:] == d * 4)
            check(Path(row['frozen_source']['path']).read_bytes() == dictionary)
            check(Path(row['frozen_index']['path']).read_bytes() == mapping)
            check(set(row['output']) == {'path', 'bytes', 'sha256'})
        first, second = scene_records
        check(first['source'] == second['source'] and first['index_source'] == second['index_source'])
        check(first['conversion'] == second['conversion'] and
              Path(first['output']['path']).name == Path(second['output']['path']).name and
              first['output']['bytes'] == second['output']['bytes'] and
              first['output']['sha256'] == second['output']['sha256'])
        check(os.path.samefile(first['output']['path'], second['output']['path']))
        check(os.path.samefile(first['frozen_source']['path'], second['frozen_source']['path']))
        check(os.path.samefile(first['frozen_index']['path'], second['frozen_index']['path']))
        check(first['output']['sha256'] == hashlib.sha256(Path(first['output']['path']).read_bytes()).hexdigest())
        check(_interactive_scene_asset_cache(deep / 'textures') is None)

        limited_payload = b'link-limit fixture DDS payload'
        limited_hash = hashlib.sha256(limited_payload).hexdigest()
        limited_cache, _ = _publish_cached_payload(limited_payload, cache_root)
        limited_target = build / 'InteractiveGameRuntime' / ('20261005T123456Z_' + 'd' * 12) / 'limited.dds'
        with mock.patch.object(asset_module.os, 'link', side_effect=OSError(errno.EMLINK, 'simulated NTFS link limit')):
            method = _materialize_cached_payload(limited_cache, limited_target, limited_hash, len(limited_payload))
        check(method == 'verified-copy-hardlink-limit')
        check(limited_target.read_bytes() == limited_payload and not os.path.samefile(limited_cache, limited_target))
        check(not os.stat(limited_target).st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
        windows_limit = OSError(errno.EACCES, 'simulated ERROR_TOO_MANY_LINKS')
        windows_limit.winerror = 1142
        windows_limit_target = limited_target.with_name('limited-winerror.dds')
        with mock.patch.object(asset_module.os, 'link', side_effect=windows_limit):
            windows_method = _materialize_cached_payload(limited_cache, windows_limit_target,
                                                         limited_hash, len(limited_payload))
        check(windows_method == 'verified-copy-hardlink-limit')
        check(windows_limit_target.read_bytes() == limited_payload and
              not os.path.samefile(limited_cache, windows_limit_target))

        reparse_target = Path(temp) / 'reparse-target'
        reparse_target.mkdir()
        reparse_link = Path(temp) / 'reparse-link'
        try:
            os.symlink(reparse_target, reparse_link, target_is_directory=True)
        except (OSError, NotImplementedError):
            pass
        else:
            reject(lambda: _interactive_scene_asset_cache(reparse_link / 'textures'))

        corrupt_payload = b'cache corruption fixture'
        corrupt_hash = hashlib.sha256(corrupt_payload).hexdigest()
        corrupt_cache, _ = _publish_cached_payload(corrupt_payload, cache_root)
        corrupt_cache.chmod(stat.S_IREAD | stat.S_IWRITE)
        corrupt_cache.write_bytes(b'corrupted')
        reject(lambda: _publish_cached_payload(corrupt_payload, cache_root))
        mismatched_target = build / 'mismatched' / 'existing.dds'
        mismatched_target.parent.mkdir(parents=True)
        mismatched_target.write_bytes(b'not the cached payload')
        reject(lambda: _materialize_cached_payload(limited_cache, mismatched_target,
                                                    limited_hash, len(limited_payload)))

        font_cache = build / 'RuntimeInputCache' / 'ui-font-atlases'
        font_scene = (build / 'InteractiveGameRuntime' / ('20261010T120000Z_' + 'e' * 12) /
                      'sessions' / ('f' * 32) / 'play-ui-1' / 'textures')
        font_source = Path(temp) / 'original-font.dds'
        font_payload = dds(2, 2, bytes([3, 7, 13, 255]) * 4)
        font_source.write_bytes(font_payload)
        font_hash = hashlib.sha256(font_payload).hexdigest()
        original_stat = font_source.stat()
        first = materialize_font_atlas(font_source, font_scene / 'font.dds', font_hash)
        second = materialize_font_atlas(font_source, font_scene / 'font-other-name.dds', font_hash)
        check(first['method'] == second['method'] == 'hardlink')
        check(first['cache_file'] == second['cache_file'] and first['shard_index'] == 0)
        check(Path(first['cache_file']) == font_cache / font_hash[:2] / font_hash / 'shard-0000.dds')
        check(os.path.samefile(first['cache_file'], font_scene / 'font.dds'))
        check(os.path.samefile(font_scene / 'font.dds', font_scene / 'font-other-name.dds'))
        check(not os.path.samefile(font_source, font_scene / 'font.dds'))
        check(font_source.read_bytes() == (font_scene / 'font.dds').read_bytes() == font_payload)
        check(font_source.stat().st_mtime_ns == original_stat.st_mtime_ns and
              font_source.stat().st_nlink == original_stat.st_nlink and font_source.stat().st_mode == original_stat.st_mode)
        check(not (font_scene / 'font.dds').stat().st_mode & stat.S_IWUSR)
        check(materialize_font_atlas(font_source, font_scene / 'font.dds', font_hash)['method'] == 'existing-verified')
        rollback_target = font_scene / 'rollback.dds'
        materialize_sharded_payload(font_payload, rollback_target, font_cache)
        cache_identity = (rollback_target.stat().st_dev, rollback_target.stat().st_ino)
        cache_mode = Path(first['cache_file']).stat().st_mode
        with mock.patch.object(asset_module, '_unlink_font_target_without_attribute_changes',
                               side_effect=PermissionError('injected unlink rejection')):
            try:
                asset_module._remove_created_font_link(rollback_target, Path(first['cache_file']), cache_identity)
            except PermissionError:
                check(True)
            else:
                raise AssertionError('Unlink rejection was ignored')
        check(rollback_target.is_file() and Path(first['cache_file']).stat().st_mode == cache_mode)
        check((font_scene / 'font.dds').read_bytes() == font_payload and
              (font_scene / 'font.dds').stat().st_mode == cache_mode)
        asset_module._remove_created_font_link(rollback_target, Path(first['cache_file']), cache_identity)
        check(not rollback_target.exists() and Path(first['cache_file']).stat().st_mode == cache_mode)
        if os.name == 'nt':
            long_target = font_scene / ('long-' + 'x' * 120 + '.dds')
            materialize_sharded_payload(font_payload, long_target, font_cache)
            ordinary_path = str(long_target)
            if ordinary_path.startswith('\\\\?\\'):
                ordinary_path = ordinary_path[4:]
            check(len(ordinary_path) > 260)
            asset_module._unlink_font_target_without_attribute_changes(Path(ordinary_path))
            check(not long_target.exists() and Path(first['cache_file']).stat().st_mode == cache_mode)
        different = materialize_sharded_payload(font_payload + b'different', font_scene / 'different.dds', font_cache)
        check(different['cache_file'] != first['cache_file'] and
              not os.path.samefile(different['cache_file'], first['cache_file']))
        standalone = Path(temp) / 'standalone-font' / 'atlas.dds'
        check(materialize_font_atlas(font_source, standalone, font_hash)['method'] == 'standalone-copy')
        check(standalone.read_bytes() == font_payload and not os.path.samefile(standalone, font_source))
        reject(lambda: materialize_font_atlas(font_source, font_scene / 'different.dds', font_hash))
        reject(lambda: materialize_font_atlas(font_source, font_scene / 'bad-source.dds', '0' * 64))
        reject(lambda: materialize_sharded_payload(font_payload, font_scene / 'escaped.dds', font_cache.parent / 'wrong-cache'))
        reject(lambda: materialize_sharded_payload(font_payload, build / 'InteractiveGameRuntime' / 'bad-layout' / 'font.dds', font_cache))
        check(not (font_scene / 'escaped.dds').exists() and not (font_scene / 'bad-source.dds').exists())

        # A real small link cap exercises rollover without creating 1024 files.
        rollover_payload = b'font rollover bytes'
        with mock.patch.object(asset_module, 'FONT_CACHE_MAX_LINKS', 3):
            rollover = [materialize_sharded_payload(rollover_payload, font_scene / f'rollover-{i}.dds', font_cache)
                        for i in range(5)]
        check([row['shard_index'] for row in rollover] == [0, 0, 1, 1, 2])
        check(all(Path(row['cache_file']).stat().st_nlink <= 3 for row in rollover))
        check(all((font_scene / f'rollover-{i}.dds').read_bytes() == rollover_payload for i in range(5)))
        real_link = os.link
        for suffix, failure in (('errno', OSError(errno.EMLINK, 'simulated link limit')),
                                ('winerror', windows_limit)):
            def limited_link(source, target, *, _failure=failure):
                if Path(source).name == 'shard-0000.dds':
                    raise _failure
                return real_link(source, target)
            with mock.patch.object(asset_module.os, 'link', side_effect=limited_link):
                row = materialize_sharded_payload(('font OS limit ' + suffix).encode(),
                                                 font_scene / f'os-limit-{suffix}.dds', font_cache)
            check(row['method'] == 'hardlink' and row['shard_index'] == 1)
            check(os.path.samefile(row['cache_file'], font_scene / f'os-limit-{suffix}.dds'))
        with mock.patch.object(asset_module, 'FONT_CACHE_MAX_LINKS', 2), mock.patch.object(asset_module, 'FONT_CACHE_MAX_SHARDS', 2):
            for i in range(2):
                materialize_sharded_payload(b'bounded shards', font_scene / f'bounded-{i}.dds', font_cache)
            reject(lambda: materialize_sharded_payload(b'bounded shards', font_scene / 'bounded-2.dds', font_cache))
        check(not (font_scene / 'bounded-2.dds').exists())

        # Concurrent callers share the same identity and cannot overfill a shard.
        with mock.patch.object(asset_module, 'FONT_CACHE_MAX_LINKS', 3):
            with ThreadPoolExecutor(max_workers=8) as workers:
                concurrent = list(workers.map(lambda i: materialize_sharded_payload(
                    b'concurrent font', font_scene / f'concurrent-{i}.dds', font_cache), range(8)))
        check(len({row['cache_file'] for row in concurrent}) == 4)
        check(all(Path(row['cache_file']).stat().st_nlink == 3 for row in concurrent))
        with ThreadPoolExecutor(max_workers=4) as workers:
            same_target = list(workers.map(lambda _: materialize_sharded_payload(
                b'same target race', font_scene / 'same-target.dds', font_cache), range(4)))
        check(sum(row['method'] == 'hardlink' for row in same_target) == 1)
        check(sum(row['method'] == 'existing-verified' for row in same_target) == 3)
        barrier = threading.Barrier(2)
        contested = font_scene / 'contested.dds'
        def competing_link(source, target):
            if Path(target) == contested:
                barrier.wait(timeout=5)
            return real_link(source, target)
        def competing_payload(payload):
            try:
                return materialize_sharded_payload(payload, contested, font_cache)
            except ValueError:
                return None
        with mock.patch.object(asset_module.os, 'link', side_effect=competing_link):
            with ThreadPoolExecutor(max_workers=2) as workers:
                competing = list(workers.map(competing_payload, (b'font A', b'font B')))
        check(sum(row is not None for row in competing) == 1)
        winner = next(row for row in competing if row is not None)
        check(contested.read_bytes() in (b'font A', b'font B') and os.path.samefile(contested, winner['cache_file']))
        corrupt = materialize_sharded_payload(b'font cache corruption', font_scene / 'corrupt-1.dds', font_cache)
        corrupt_path = Path(corrupt['cache_file'])
        corrupt_path.chmod(stat.S_IREAD | stat.S_IWRITE)
        corrupt_path.write_bytes(b'altered cached font')
        reject(lambda: materialize_sharded_payload(b'font cache corruption', font_scene / 'corrupt-2.dds', font_cache))
        check(corrupt_path.read_bytes() == b'altered cached font' and not (font_scene / 'corrupt-2.dds').exists())
        font_reparse_exercised = reparse_link.is_symlink()
        if font_reparse_exercised:
            reject(lambda: materialize_font_atlas(font_source, reparse_link / 'font.dds', font_hash))
            linked_source = reparse_link / 'original-font.dds'
            reject(lambda: materialize_font_atlas(linked_source, font_scene / 'reparse-source.dds', font_hash))
    print(json.dumps({'status': 'BOUNDED_FPK_AND_LOSSLESS_FTXT_COMPONENT_PASS', 'checks': checks,
                      'font_cache_reparse_symlink_exercised': font_reparse_exercised,
                      'game_install_modified': False, 'retail_rendering_proven': False}))


if __name__ == '__main__':
    main()
