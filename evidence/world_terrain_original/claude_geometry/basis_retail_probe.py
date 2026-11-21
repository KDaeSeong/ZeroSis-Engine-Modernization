"""File-only probe of the retail TerrainShader bicubic patch inputs (CivilizationV_DX11.exe).

It follows the cb1[10..13] basis from its float literals through the stack image built by the
CPU writer (0x6add60), the constant-block copy and the DS/HS/VS consumers, and it re-derives the
16-control index order from the patch index generator (0x6c9c00).

Only the standard library is used.  The executable is read as bytes; nothing is loaded or run.
usage: python -B -X utf8 basis_retail_probe.py [--exe PATH] [--out basis_retail_probe.json]
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).absolute().parent
EVIDENCE = HERE.parent
DEFAULT_EXE = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V\CivilizationV_DX11.exe")
EXE_SHA256 = 'b7c8977ebab33ba6c1abf65d63fa310f8d096341465e0fc419f1b4da0fcd8818'
IMAGE_BASE = 0x400000

# Byte ranges that carry the claims.  sha256 values were taken from the pinned executable.
REGIONS = {
    'cb1_writer_stack_fill': (0x6add60, 0x6ade3f),
    'cb1_writer_copy': (0x6ade3f, 0x6adfcd),
    'cb1_writer_tess_factor': (0x6adfcd, 0x6ae015),
    'cb1_writer_texel_scales': (0x6ae12a, 0x6ae1a1),
    'cb1_block_getter_0x250': (0x6be670, 0x6be682),
    'cb0_block_getter_0x70': (0x6bbe60, 0x6bbe6f),
    'patch_index_generator': (0x6c9c00, 0x6c9d8a),
    'patch_draw_cb0_writer': (0x5c37e0, 0x5c3a8f),
    'lod_draw_item_builder': (0x768160, 0x7683aa),
    'config_bicubic_enable': (0x5d932a, 0x5d9355),
    'config_bicubic_subdiv': (0x5d9380, 0x5d93ab),
    'subdiv_debug_step': (0x502ab0, 0x502af0),
}
REGION_SHA256 = {
    'cb1_writer_stack_fill': 'ff7052687a1333e1bd6478533a94e1a8d24981d53f191b0d85d502bd7bc839aa',
    'cb1_writer_copy': '268e4b5f3836cc2947406ca9ca76758db4bf200d1e74890e3d21fd74aedaba30',
    'cb1_writer_tess_factor': 'b0194e5d76bb80952d9ac487616c935051cec8d5484b527e83594beb009485e0',
    'cb1_writer_texel_scales': 'd25ce3107cb04c5aa440ad009b1bd37a1a1921752f57a0d2e6e00ed73fd93bca',
    'cb1_block_getter_0x250': 'ead8474fc8410e000f497f3c1a8cc1d000339db53df584c3195a14b91ccf054d',
    'cb0_block_getter_0x70': '89044b53d16101f37c35f5d7d7af9c119b1b58c672e753bdb01b0f0c80cd62aa',
    'patch_index_generator': '57ea1bef986c336eff92065677dee74a029f69dc63e29e36e5d4a3f6b1f5ebf6',
    'patch_draw_cb0_writer': '9209d61e8a3519a7e91be88fb0b27d703c167799d0c2d3df508d6155da022a2c',
    'lod_draw_item_builder': '775be5d4548a960a76f67487a1eec7438d04c9807207ebd31ed26bb7b50592a9',
    'config_bicubic_enable': 'ca00e407d60f46f5d14e64951c25e1d0fd9cf21fccbeab85f3b90b3a651ccbdc',
    'config_bicubic_subdiv': 'ebceee3414b1275a73efbc7833d366a18ca6a1c7e2148def79e411fcd04e0a9b',
    'subdiv_debug_step': '605597de9d24a6417096c5aa910cc7e41cd47499fd6fd45e19a7639b09644411',
}


class Fail(SystemExit):
    pass


def require(condition, message):
    if not condition:
        raise Fail('Pinned retail evidence no longer matches: ' + message)


class Image:
    def __init__(self, raw):
        self.raw = raw
        pe = struct.unpack_from('<I', raw, 0x3c)[0]
        require(raw[pe:pe + 4] == b'PE\0\0', 'PE signature')
        count = struct.unpack_from('<H', raw, pe + 6)[0]
        optional = struct.unpack_from('<H', raw, pe + 20)[0]
        require(struct.unpack_from('<I', raw, pe + 24 + 28)[0] == IMAGE_BASE, 'image base')
        table = pe + 24 + optional
        self.sections = []
        for index in range(count):
            name, vsize, rva, rsize, offset = struct.unpack_from('<8sIIII', raw, table + index * 40)
            self.sections.append((rva, vsize, rsize, offset, name.rstrip(b'\0').decode('ascii')))

    def offset(self, va):
        rva = va - IMAGE_BASE
        for start, vsize, rsize, offset, _ in self.sections:
            if start <= rva < start + max(vsize, rsize):
                require(rva - start < rsize, 'address %#x has file bytes' % va)
                return offset + rva - start
        raise Fail('address outside the image: %#x' % va)

    def read(self, va, size):
        start = self.offset(va)
        return self.raw[start:start + size]

    def u32(self, va):
        return struct.unpack('<I', self.read(va, 4))[0]

    def f32(self, va):
        return struct.unpack('<f', self.read(va, 4))[0]

    def text(self, va):
        data = self.read(va, 96)
        return data[:data.index(b'\0')].decode('ascii')


XMM_LOAD = {0x05: 0, 0x0d: 1, 0x15: 2, 0x1d: 3}
XMM_STORE = {0x44: 0, 0x4c: 1, 0x54: 2, 0x5c: 3}
REG_LOAD = {0x44: 'eax', 0x4c: 'ecx', 0x54: 'edx'}
REG_STORE = {0x83: 'eax', 0x8b: 'ecx', 0x93: 'edx'}


def decode_stack_fill(image):
    """Decode 0x6add87..0x6ade3a.  Returns {slot offset relative to the pre-push esp: literal address or 0}."""
    code = image.read(0x6add87, 0x6ade3a - 0x6add87)
    position, push_bias, xmm, slots, steps = 0, 0, {}, {}, []
    while position < len(code):
        at = 0x6add87 + position
        window = code[position:position + 8]
        if window[:3] == b'\xf3\x0f\x10' and window[3] in XMM_LOAD:          # movss xmmN, [abs]
            xmm[XMM_LOAD[window[3]]] = struct.unpack_from('<I', window, 4)[0]
            position += 8
        elif window[:3] == b'\xf3\x0f\x11' and window[3] in XMM_STORE and window[4] == 0x24:  # movss [esp+d8], xmmN
            slot = window[5] - push_bias
            slots[slot] = xmm[XMM_STORE[window[3]]]
            steps.append(dict(at='%#x' % at, slot='%#x' % slot, source='%#x' % slots[slot] if slots[slot] else 'zero'))
            position += 6
        elif window[:3] == b'\x0f\x57\xc0':                                   # xorps xmm0, xmm0
            xmm[0] = 0
            position += 3
        elif window[:2] == b'\x6a\x00':                                       # push 0 (argument of the block getter)
            push_bias += 4
            position += 2
        elif window[:2] == b'\x8b\xc8':                                       # mov ecx, eax
            position += 2
        elif window[:4] == b'\x89\x44\x24\x24':                               # mov [esp+0x24], eax
            position += 4
        else:
            raise Fail('unexpected instruction bytes in the stack fill at %#x: %s' % (at, window.hex()))
    require(push_bias == 4, 'exactly one pushed argument before the block getter call')
    return slots, steps


def decode_copy(image):
    """Decode 0x6adf21..0x6adfcd: mov r32,[esp+d8] / mov [ebx+d32],r32 pairs.  Returns {block offset: slot}."""
    code = image.read(0x6adf21, 0x6adfcd - 0x6adf21)
    position, registers, block = 0, {}, {}
    while position < len(code):
        at = 0x6adf21 + position
        window = code[position:position + 6]
        if window[0] == 0x8b and window[1] in REG_LOAD and window[2] == 0x24:
            registers[REG_LOAD[window[1]]] = window[3]
            position += 4
        elif window[0] == 0x89 and window[1] in REG_STORE:
            offset = struct.unpack_from('<I', window, 2)[0]
            block[offset] = registers.get(REG_STORE[window[1]])                 # None: loaded before this range
            position += 6
        else:
            raise Fail('unexpected instruction bytes in the block copy at %#x: %s' % (at, window.hex()))
    return block


def generator_indices(width, height):
    """Python reading of 0x6c9cb0..0x6c9d67: five levels, 16 words per patch."""
    out = []
    for _ in range(5):
        level = []
        for row in range(1, height):               # ebp, compared with the second argument
            for column in range(1, width):         # eax, compared with the first argument
                patch = []
                for r in range(4):                 # esi
                    high = (r + row + 1) << 8      # lea ecx,[esi+ebp+1]; shl ecx,8
                    patch += [high | (column + 1 + c) for c in range(4)]
                level.append(patch)
        out.append(level)
        width, height = (width >> 1) + 1, (height >> 1) + 1
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--exe', type=Path, default=DEFAULT_EXE)
    parser.add_argument('--out', type=Path, default=HERE / 'basis_retail_probe.json')
    parser.add_argument('--print-region-hashes', action='store_true')
    arguments = parser.parse_args()
    raw = arguments.exe.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    require(sha == EXE_SHA256, 'executable SHA-256 ' + sha)
    image = Image(raw)

    regions = {}
    for name, (start, stop) in REGIONS.items():
        data = image.read(start, stop - start)
        regions[name] = dict(start='%#x' % start, stop='%#x' % stop, bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    if arguments.print_region_hashes:
        print(json.dumps({name: value['sha256'] for name, value in regions.items()}, indent=1))
        return
    for name, value in regions.items():
        require(value['sha256'] == REGION_SHA256[name], 'region ' + name)

    # --- basis: literals -> stack image -> constant block -------------------------------------------------
    slots, steps = decode_stack_fill(image)
    block = decode_copy(image)
    require(image.read(0x6ade3a, 1) == b'\xe8' and
            0x6ade3f + struct.unpack('<i', image.read(0x6ade3b, 4))[0] == 0x6be670, 'call of the 0x250 block getter')
    getter = image.read(0x6be670, 18)
    require(getter[:10] == bytes.fromhex('8b442404506850020000') and getter[10] == 0xe8 and getter[15:18] == b'\xc2\x04\x00',
            'block getter pushes size 0x250 and returns with ret 4 (stack restored for the copy)')
    require(image.read(0x8a868c, 2) == b'\xff\x25', 'D3DX import thunk between the getter and the copy (stdcall, three arguments)')
    require(image.read(0x6ade4d, 1) == b'\x51' and image.read(0x6ade50, 1) == b'\x52' and image.read(0x6ade55, 1) == b'\x50',
            'three pushes before the stdcall thunk')
    basis, literal_rows = [], []
    for row in range(4):
        values, sources = [], []
        for column in range(4):
            offset = 0xa0 + 16 * row + 4 * column
            require(offset in block and block[offset] is not None, 'block offset %#x is copied from the stack image' % offset)
            slot = block[offset]
            require(slot in slots, 'stack slot %#x is written before the call' % slot)
            literal = slots[slot]
            values.append(image.f32(literal) if literal else 0.0)
            sources.append(dict(block_offset='%#x' % offset, stack_slot='%#x' % slot,
                                literal='%#x' % literal if literal else 'xorps zero',
                                u32='%#010x' % (image.u32(literal) if literal else 0)))
        basis.append(values)
        literal_rows.append(sources)
    eighths = [[value * 8 for value in row] for row in basis]
    expected = [[-1, 7, -7, 1], [3, -12, 9, 0], [-3, 0, 3, 0], [1, 6, 1, 0]]
    require(eighths == expected, 'basis rows times eight ' + repr(eighths))

    # Mitchell-Netravali family: B/6 = 1/8 and C = 0 reproduce every entry.
    B, C = 0.75, 0.0
    family = [[-B / 6 - C, (12 - 9 * B - 6 * C) / 6, -(12 - 9 * B - 6 * C) / 6, B / 6 + C],
              [B / 2 + 2 * C, (-18 + 12 * B + 6 * C) / 6, (18 - 15 * B - 12 * C) / 6, -C],
              [-B / 2 - C, 0.0, B / 2 + C, 0.0],
              [B / 6, 1 - B / 3, B / 6, 0.0]]
    require(all(abs(family[r][c] - basis[r][c]) < 1e-12 for r in range(4) for c in range(4)), 'B=3/4, C=0 family identity')

    # --- other entries written by the same function -------------------------------------------------------
    copy = image.read(0x6ade79, 0x6adee5 - 0x6ade79)
    pairs = []
    for index in range(9):
        load, store = copy[index * 12:index * 12 + 6], copy[index * 12 + 6:index * 12 + 12]
        require(load[0] == 0x8b and load[1] in (0x85, 0x8d, 0x95) and store[0] == 0x89 and store[1] in REG_STORE, 'ebp field copy %d' % index)
        pairs.append((struct.unpack_from('<I', load, 2)[0], struct.unpack_from('<I', store, 2)[0]))
    require(pairs == [(0x1acc, 0x100), (0x1ad0, 0x104), (0x1ad4, 0x108), (0x400, 0x110), (0x404, 0x114), (0x408, 0x118),
                      (0x40c, 0x120), (0x410, 0x124), (0x414, 0x128)], 'cb1[16..18] come from object fields')
    require(image.read(0x67837e, 0x2e) == bytes.fromhex(
        'a1d4a6b9008983cc1a00008b0dd8a6b9008b450c898bd01a00008b15dca6b9008983140b000033c08993d41a0000'),
        'initialiser copies .data 0xb9a6d4/d8/dc to object+0x1acc/0x1ad0/0x1ad4')
    unit_scale = [image.f32(0xb9a6d4), image.f32(0xb9a6d8), image.f32(0xb9a6dc)]
    require([image.u32(0xb9a6d4), image.u32(0xb9a6d8), image.u32(0xb9a6dc)] == [0x3f800000, 0x3f5db22d, 0x3e4ccccd], 'unit scale literals')
    text = [s for s in image.sections if s[4] == '.text'][0]
    code = raw[text[3]:text[3] + text[2]]
    direct_stores = {}
    for global_address in (0xb9a6d4, 0xb9a6d8, 0xb9a6dc):
        needle, found, at = struct.pack('<I', global_address), [], 0
        while True:
            at = code.find(needle, at)
            if at < 0:
                break
            before = code[max(0, at - 4):at]
            # mov [abs],eax (a3) / mov [abs],r32 (89 /r disp32) / movss [abs],xmm (f3 0f 11 /r) / fstp [abs] (d9 1d) / mov [abs],imm (c7 05)
            if before[-1:] == b'\xa3' or (before[-2:-1] == b'\x89' and before[-1] & 0xc7 == 0x05) or \
                    (before[-4:-1] == b'\xf3\x0f\x11' and before[-1] & 0xc7 == 0x05) or before[-2:] in (b'\xd9\x1d', b'\xd9\x15', b'\xc7\x05'):
                found.append('%#x' % (IMAGE_BASE + text[0] + at))
            at += 1
        direct_stores['%#x' % global_address] = found
    require(all(not value for value in direct_stores.values()), 'no direct store to the unit scale globals ' + repr(direct_stores))

    tess = image.read(0x6adfcd, 0x6ae015 - 0x6adfcd)
    require(tess[:6] == bytes.fromhex('8b8528240000') and bytes.fromhex('d99be0000000') in tess and
            bytes.fromhex('f30f1183f0000000') in tess, 'cb1[14].x = float(uint field 0x2428), cb1[15].x = 1.0')
    require(image.read(0x678c53, 12) == bytes.fromhex('8b0d140fd900898b28240000'), 'field 0x2428 is initialised from global 0xd90f14')
    require(image.text(0xa1bfb8) == 'BicubicTerrainTessSubdiv' and image.read(0x5d9395, 10) == bytes.fromhex('68140fd90068b8bfa100'),
            'config value BicubicTerrainTessSubdiv is bound to 0xd90f14')
    require(image.text(0xa1bf00) == 'BicubicTerrainTessellation' and image.read(0x5d933f, 10) == bytes.fromhex('681c0fd9006800bfa100'),
            'config value BicubicTerrainTessellation is bound to 0xd90f1c')
    scales = image.read(0x6ae12a, 0x6ae1a1 - 0x6ae12a)
    require(bytes.fromhex('f30f118360010000') in scales and bytes.fromhex('f30f118364010000') in scales and
            bytes.fromhex('f30f118370010000') in scales and bytes.fromhex('f30f118374010000') in scales, 'cb1[22].xy and cb1[23].xy stores')
    require([image.u32(0x9de4f0), image.u32(0x9eae88), image.u32(0x9ecfb8)] == [0x3a800000, 0xba800000, 0x3b000000], '1/1024, -1/1024, 1/512')

    # --- control point order ------------------------------------------------------------------------------
    generator = image.read(0x6c9cb0, 0x6c9d6d - 0x6c9cb0)
    for needle, meaning in ((bytes.fromhex('8d4c2e01c1e108'), 'high byte = (r + row + 1) << 8'),
                            (bytes.fromhex('0fb7c88d79018d59028d410383c104'), 'low bytes = column + 1..4'),
                            (bytes.fromhex('66896afc'), 'word 0'), (bytes.fromhex('66896afe'), 'word 1'),
                            (bytes.fromhex('66892a'), 'word 2'), (bytes.fromhex('66894a02'), 'word 3'),
                            (bytes.fromhex('4683c20883fe047ccd'), 'four rows of four words'),
                            (bytes.fromhex('d1efd1eb4743836c241c01'), 'next level: n = (n >> 1) + 1, five levels')):
        require(needle in generator, 'index generator: ' + meaning)
    require(image.read(0x6c9c03, 7) == bytes.fromhex('833ddc9ee4020a'), 'generator is skipped below device tier 10')
    sample = generator_indices(5, 4)
    first = sample[0][0]
    control = lambda word: ((word & 255) - 3, (word >> 8) - 3)      # TerrainShader VS: (id & 255) - 3, (id >> 8) - 3
    require([control(word) for word in first] == [(c - 1, r - 1) for r in range(4) for c in range(4)],
            'patch 0 controls are (c-1, r-1), c fastest')
    require(all(control(patch[5]) == (index % 4, index // 4) for index, patch in enumerate(sample[0])),
            'control 5 is the patch origin; patches advance along x first')
    require([len(level) for level in sample] == [12, 4, 1, 1, 1], 'level sizes for a 5 x 4 cell')

    # --- per-draw cb0 -------------------------------------------------------------------------------------
    draw = image.read(0x5c37e0, 0x5c3a8f - 0x5c37e0)
    for needle, meaning in ((bytes.fromhex('f30f2a83dc000000'), 'cb0[4].x = float(int cell+0xdc)'),
                            (bytes.fromhex('f30f2a83e0000000'), 'cb0[4].y = float(int cell+0xe0)'),
                            (bytes.fromhex('f30f2a83e4000000'), 'cb0[4].z = float(int cell+0xe4)'),
                            (bytes.fromhex('f30f2a83e8000000'), 'cb0[4].w = float(int cell+0xe8)'),
                            (bytes.fromhex('d1f9d1fa414283ee0175f5'), 'level size: n = (n >> 1) + 1 repeated cell+0x1c4 times'),
                            (bytes.fromhex('f30f108124240000'), 'cb0[6].z = float object+0x2424 (height mip level)'),
                            (bytes.fromhex('833ddc9ee4020a'), 'tier >= 10 gate before the level update'),
                            (bytes.fromhex('833d1c0fd90000'), 'pass choice reads BicubicTerrainTessellation'),
                            (bytes.fromhex('833d700fd90000'), 'pass choice reads TerrainTessLevel')):
        require(needle in draw, 'patch draw: ' + meaning)

    # --- shader consumers (text listings written earlier by the project, read-only) ----------------------
    shader_checks = {}
    for name, lines in (('phase10/geometry/TerrainShader_0_ds.asm.txt',
                         ['mul r2.xyzw, r0.xxxx, cb1[11].xyzw', 'mad r2.xyzw, cb1[10].xyzw, r3.xxxx, r2.xyzw',
                          'mad r2.xyzw, cb1[12].xyzw, vDomain.xxxx, r2.xyzw', 'add r2.xyzw, r2.xyzw, cb1[13].xyzw',
                          'dp4 r1.x, r2.xyzw, r1.xyzw', 'dp4 r2.x, cb1[10].xyzw, r1.xyzw', 'dp4 r2.w, cb1[13].xyzw, r1.xyzw',
                          'dp4 r0.x, r2.xyzw, r0.xyzw', 'mad r0.yz, vDomain.xxyx, cb0[6].xxyx, vpc0.yyzy',
                          'mul r0.yz, r1.xxyx, cb1[16].xxyx']),
                        ('phase10/geometry/TerrainShader_0_hs.asm.txt',
                         ['mov o[r0.x + 0].x, cb1[14].x', 'mov o[r0.x + 4].x, cb1[14].x', 'mov o0.y, vicp[5][0].y',
                          'mov o0.z, vicp[5][0].z', 'dcl_tessellator_partitioning partitioning_integer'])):
        path = EVIDENCE / name
        if path.is_file():
            body = path.read_text('utf8')
            missing = [line for line in lines if line not in body]
            require(not missing, name + ' lacks ' + repr(missing))
            shader_checks[name] = dict(sha256=hashlib.sha256(path.read_bytes()).hexdigest(), lines=lines, status='PASS')
        else:
            shader_checks[name] = dict(status='LISTING_NOT_PRESENT')

    report = dict(
        schema='zerosis.world_terrain_original.claude_geometry.basis_retail_probe.v1',
        status='PASS_FILE_ONLY', executable=dict(path=str(arguments.exe), bytes=len(raw), sha256=sha),
        native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False, regions=regions,
        basis=dict(
            status='confirmed',
            cb1_10_13=basis, times_eight=eighths, literal_sources=literal_rows, stack_fill_steps=steps,
            row_meaning='cb1[10] multiplies t^3, cb1[11] t^2, cb1[12] t, cb1[13] 1 (DS instructions); the column is the control index 0..3',
            family='Mitchell-Netravali cubic with B = 3/4, C = 0 (identity checked on all 16 entries). Not B-spline (B=1), '
                   'Catmull-Rom (B=0, C=1/2) or Bezier.',
            properties=dict(partition_of_unity=True, interpolates_controls=False, weights_at_t0=[0.125, 0.75, 0.125, 0.0],
                            linear_precision=False,
                            ramp_response='controls (-1,0,1,2) give -0.5 t^3 + 0.75 t^2 + 0.75 t, not t')),
        other_cb1_entries=dict(
            status='confirmed',
            cb1_14_x='float(uint object+0x2428); initialised from config BicubicTerrainTessSubdiv (0xd90f14); debug step doubles/halves within 1..16',
            cb1_15_x=1.0,
            cb1_16_xyz=dict(values=unit_scale, source='object+0x1acc/0x1ad0/0x1ad4 copied from .data 0xb9a6d4/d8/dc; no direct store found',
                            direct_stores=direct_stores),
            cb1_17_xyz='object+0x400..0x408', cb1_18_xyz='object+0x40c..0x414',
            cb1_22_xy=[image.f32(0x9de4f0), image.f32(0x9eae88)], cb1_23_xy=[image.f32(0x9ecfb8)] * 2),
        controls=dict(
            status='confirmed',
            index_word='low byte = px + c + 2, high byte = py + r + 2 for patch (px, py), c fastest; 16 words per patch',
            vertex_shader='x = ((id & 255) - 3) * cb0[6].x, y = ((id >> 8) - 3) * cb0[6].y, so control (c, r) sits at (px + c - 1, py + r - 1) * spacing',
            patch_origin='control 5 (c = 1, r = 1); HS forwards its yz to the DS',
            domain='u runs along c (x), v along r (y); the patch spans one control spacing between controls 1 and 2',
            patch_order='rows outer (py = 0..H-2), columns inner (px = 0..W-2); arguments are the cell fields +0xd4 (W) and +0xd8 (H)',
            levels='five levels, each (n >> 1) + 1; generator returns 0 below device tier 10',
            sample_5x4_first_patch=first),
        per_draw_cb0=dict(
            status='confirmed_layout_candidate_values',
            cb0_0_3='D3DXMatrixTranslation result (world row vectors) from the negated object+0x1ab0/0x1ab4/0x1ab8 bit patterns',
            cb0_4='float of int cell fields +0xdc, +0xe0, +0xe4, +0xe8 (texel origin xy and extra offset zw); values not traced',
            cb0_5_xy='1 / (W + 1), 1 / (H + 1)',
            cb0_6_xy='(W - 1) / (W_level - 1), (H - 1) / (H_level - 1): control spacing in height texels',
            cb0_6_z='float object+0x2424: height texture mip level; floor() of it selects the index level when tier >= 10'),
        units=dict(
            status='confirmed_operations',
            height='control height = height texture alpha * cb1[16].z * 255 = alpha * 0.2 * 255 (VS instructions and literal)',
            horizontal='world xy = (domain * cb0[6].xy + origin + cb0[4].xy) * cb1[16].xy = texel * (1.0, 0.866)',
            sample_uv='((id - 3) * cb0[6].xy + cb0[4].xy + cb0[4].zw + 0.5) * (1/1024, -1/1024), LOD cb0[6].z',
            not_established='cell size W, H and the cb0[4] integers for a real map; the 0x1ab0 translation fields'),
        shader_listings=shader_checks,
        limits=['Static bytes only: no shader, GPU, Host or game was executed.',
                'The stack image is decoded by a small fixed-form decoder; any other instruction form stops the probe.',
                'The values prove what the CPU uploads, not that the current renderer draws the same picture.'])
    out = arguments.out
    if out.exists():
        out.unlink()
    with out.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(report, stream, indent=1, ensure_ascii=False)
        stream.write('\n')
    print(json.dumps(dict(status=report['status'], basis_times_eight=eighths, cb1_16=unit_scale, out=str(out))))


if __name__ == '__main__':
    main()
