"""CPU-only V3/V4 page comparison: V4 may differ from V3 only inside the four WindowTrim rectangles.

Pack packets store pack-relative texture names; this check writes temporary absolute-path copies,
renders them with the project's standard-library CPU renderer, compares pixels, keeps the V4 pages and a
small side-by-side crop, and deletes its own temporaries. No Host, window, GPU or game is started.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import zlib

sys.dont_write_bytecode = True
STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[2]
sys.path.insert(0, str(PROJECT / 'tools'))
from menu_frontend_cpu import png_bytes, render

V3 = PROJECT / 'Source/Assets/UIFrontEndV3'
V4 = PROJECT / 'Source/Assets/UIFrontEndV4'
OUT = STAGE / 'frontend_v4_render'
TEMP = OUT / 'tmp'
PAGES = ('MainMenu', 'SinglePlayer')


def absolute_packet(root, name, target):
    raw = (root / (name + '.packet')).read_bytes()
    count, = struct.unpack_from('<I', raw, 16)
    cursor, out = 32, bytearray(raw[:32])
    for _ in range(count):
        size, = struct.unpack_from('<I', raw, cursor)
        cursor += 4
        path = str((root / raw[cursor:cursor + size].decode('utf8')).resolve(strict=True)).encode('utf8')
        cursor += size
        out += struct.pack('<I', len(path)) + path
    out += raw[cursor:]
    target.write_bytes(bytes(out))
    return target


def decode_png(path):
    raw = Path(path).read_bytes()
    width, height = struct.unpack('>2I', raw[16:24])
    data, cursor = b'', 8
    while cursor < len(raw):
        size, = struct.unpack('>I', raw[cursor:cursor + 4])
        kind = raw[cursor + 4:cursor + 8]
        if kind == b'IDAT':
            data += raw[cursor + 8:cursor + 8 + size]
        cursor += 12 + size
    rows = zlib.decompress(data)
    stride = width * 4 + 1
    assert all(rows[y * stride] == 0 for y in range(height))
    return width, height, b''.join(rows[y * stride + 1:(y + 1) * stride] for y in range(height))


def ref(path):
    raw = Path(path).read_bytes()
    return dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def main():
    manifest = json.loads((STAGE / 'frontend_v4/assets_v4.json').read_text('utf8'))
    rects = [tuple(row['target_bounds']) for row in manifest['original_image_size_candidates']]
    OUT.mkdir(exist_ok=False)
    TEMP.mkdir()
    pages, crops = [], []
    try:
        for name in PAGES:
            images = {}
            for label, root in (('v3', V3), ('v4', V4)):
                packet = absolute_packet(root, name, TEMP / f'{label}_{name}.packet')
                png = (OUT if label == 'v4' else TEMP) / f'{label}_{name}.png'
                render(packet, png, root)
                images[label] = decode_png(png)
            (w, h, a), (_, _, b) = images['v3'], images['v4']
            changed = [(i // 4) % w for i in range(0, len(a), 4) if a[i:i + 4] != b[i:i + 4]]
            ys = [(i // 4) // w for i in range(0, len(a), 4) if a[i:i + 4] != b[i:i + 4]]
            points = list(zip(changed, ys))
            outside = [p for p in points if not any(x <= p[0] < x + rw and y <= p[1] < y + rh for x, y, rw, rh in rects)]
            pages.append(dict(page=name, changed_pixels=len(points), changed_outside_windowtrim=len(outside),
                              bbox=[min(changed), min(ys), max(changed) + 1, max(ys) + 1] if points else None,
                              v4_image=ref(OUT / f'v4_{name}.png')))
            if name == 'SinglePlayer':
                x0, y0, cw, ch = 726, 355, 112, 416
                strip = bytearray()
                for y in range(y0, y0 + ch):
                    for source in (a, b):
                        start = (y * w + x0) * 4
                        strip += source[start:start + cw * 4]
                    strip += b'\x00\x00\x00\x00' * 0
                crop = OUT / 'singleplayer_left_trim_v3_vs_v4.png'
                # png_bytes expects BGRA rows; the strip is two RGBA crops side by side, so swap back.
                bgra = bytearray(strip)
                bgra[0::4], bgra[2::4] = strip[2::4], strip[0::4]
                crop.write_bytes(png_bytes(cw * 2, ch, bytes(bgra)))
                crops.append(ref(crop))
    finally:
        for path in sorted(TEMP.iterdir()):
            path.unlink()
        TEMP.rmdir()
    report = dict(schema='zerosis.frontend_v4.render_check.v1', pages=pages, crops=crops,
                  status='PASS_V4_DIFFERS_ONLY_INSIDE_WINDOWTRIM' if all(p['changed_pixels'] > 0 and not p['changed_outside_windowtrim'] for p in pages)
                  else 'FAIL_V4_RENDER_CHECK', renderer='PYTHON_STANDARD_LIBRARY_CPU_ONLY', temporary_files_removed=True,
                  native_execution=False, retail_pixel_acceptance=False)
    with (STAGE / 'frontend_v4_render_check.json').open('x', encoding='utf8') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
    print(json.dumps(dict(status=report['status'], pages=[{k: v for k, v in p.items() if k != 'v4_image'} for p in pages])))
    return 0 if report['status'].startswith('PASS') else 1


if __name__ == '__main__':
    raise SystemExit(main())
