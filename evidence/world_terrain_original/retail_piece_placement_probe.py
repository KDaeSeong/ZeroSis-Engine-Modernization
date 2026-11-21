"""Static, non-executing probe: how the retail Civ V DX11 EXE chooses and places terrain pieces (HexPatternMatcher)
and how a placement becomes a texel rectangle.

The EXE is parsed as data (pefile) and disassembled (capstone); nothing is loaded or executed.
usage: python -I retail_piece_placement_probe.py CivilizationV_DX11.exe OUT.json
"""
import hashlib, json, math, struct, sys
import capstone, pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

EXPECTED_SHA256 = 'b7c8977ebab33ba6c1abf65d63fa310f8d096341465e0fc419f1b4da0fcd8818'
exe, out = sys.argv[1], sys.argv[2]
raw = open(exe, 'rb').read()
sha = hashlib.sha256(raw).hexdigest()
if sha != EXPECTED_SHA256:
    raise SystemExit('Retail EXE differs from the analysed build: ' + sha)
pe = pefile.PE(data=raw)
base = pe.OPTIONAL_HEADER.ImageBase
img = pe.get_memory_mapped_image()
md = Cs(CS_ARCH_X86, CS_MODE_32)
imports = {imp.address: (imp.name or b'').decode() for entry in pe.DIRECTORY_ENTRY_IMPORT for imp in entry.imports}
text = next(s for s in pe.sections if s.Name.rstrip(b'\0') == b'.text')
T0, T1 = text.VirtualAddress, text.VirtualAddress + text.Misc_VirtualSize


def s32(va):
    return struct.unpack('<i', img[va - base:va - base + 4])[0]


def f32(va):
    return struct.unpack('<f', img[va - base:va - base + 4])[0]


def f64(va):
    return struct.unpack('<d', img[va - base:va - base + 8])[0]


def texts(start, stop):
    return [f'{i.mnemonic} {i.op_str}'.strip() for i in md.disasm(img[start - base:stop - base], start)]


def has(listing, needle):
    return any(listing[k:k + len(needle)] == needle for k in range(len(listing) - len(needle) + 1))


def require(condition, message):
    if not condition:
        raise SystemExit('Pinned retail evidence no longer matches: ' + message)


def direct_callers(target):
    found = []
    for offset in range(T0, T1 - 5):
        if img[offset] in (0xe8, 0xe9) and offset + 5 + struct.unpack('<i', img[offset + 1:offset + 5])[0] == target - base:
            found.append(base + offset)
    return found


report = dict(schema='zerosis.world_terrain_original.retail_piece_placement_probe.v1',
              exe=dict(name='CivilizationV_DX11.exe', bytes=len(raw), sha256=sha),
              tool=dict(pefile=pefile.__version__, capstone=capstone.__version__), executed=False,
              method='PE parse and linear x86 disassembly of pinned functions; no code was loaded or run.')

# 1. Adding a piece to the matcher (0x526520): 0x49c-byte entries; a cell is "significant" when its mask is not
#    0xffffffff or its owned byte is set; the matcher keeps the highest level (record +0x3c8).
add = texts(0x526520, 0x5266a8)
require('imul esi, esi, 0x49c' in add and has(add, ['mov esi, dword ptr [eax + edx*8 + 0x9c]', 'mov edi, dword ptr [eax + edx*8 + 0xa0]',
                                                      'cmp esi, -1', 'jne 0x5265d2', 'mov edx, edi', 'shr edx, 8', 'test dl, dl',
                                                      'je 0x52661c']) and
        has(add, ['mov byte ptr [eax + edx*2 + 0x3d0], bl']) and has(add, ['mov byte ptr [eax + edx*2 + 0x3d1], cl']) and
        'inc byte ptr [eax + 0x498]' in add and has(add, ['mov eax, dword ptr [eax + 0x3c8]']) and
        'mov dword ptr [edx + 0x19c], eax' in add, 'matcher entry and significant cell list')
report['matcher_entry'] = dict(function='00526520', entry_bytes=0x49c,
                               rule='cell (x, y) is stored at x + 10*y; it is significant when mask != 0xffffffff or owned != 0; '
                                    'matcher +0x19c = highest level of any piece')

# 2. ComputePatternPositions (0x769960): levels from the highest down to 0. It is reached only through a thunk that
#    asks a protection routine for the address (no direct call or jump exists).
levels = texts(0x769960, 0x7699a7)
require(has(levels, ['mov esi, dword ptr [edi + 0x19c]']) and
        has(levels, ['lea ebx, [edi + 0x1a0]', 'push ebx', 'push esi', 'push ebp', 'mov ecx, edi', 'call 0x648a00',
                     'sub esi, 1', 'jns 0x769990']), 'level loop')
require(direct_callers(0x769960) == [] and direct_callers(0x648a00) == [0x769995], 'matcher reached only via the thunk')
require(texts(0x574c00, 0x574c0b) == ['push ecx', 'mov eax, 0x675d80', 'call eax', 'pop ecx', 'jmp eax'], 'address thunk')
report['level_loop'] = dict(function='00769960', thunk='00574c00 -> 00675d80 (address computed at run time)',
                            rule='for level = highest .. 0: match(grid, level, placements)')

# 3. The matcher pass (0x648a00).
m = texts(0x648a00, 0x648f5c)
require(imports[0x9d6894] == 'rand' and 'call dword ptr [0x9d6894]' in texts(0x907a00, 0x907a7f) and
        'call dword ptr [0x9d6894]' in texts(0x693a00, 0x693aa0), 'shuffles use the C runtime rand()')
require(has(m, ['mov eax, 0xfffffffe', 'add ecx, 2']) and has(m, ['call 0x693a00']) and m.count('call 0x907a00') == 2,
        'positions from -2 to size+2, shuffled; piece and orientation order shuffled per position')
require(has(m, ['imul ebx, ebx, 0x49c', 'add ebx, dword ptr [eax]', 'mov edx, dword ptr [ebx + 0x3c8]', 'mov dword ptr [ebp + 0x50], ebx',
                'cmp edx, dword ptr [ebp + 0x78]', 'jne 0x648eb6']), 'only pieces of the current level')
require(has(m, ['mov edx, eax', 'shr edx, 1', 'sub ecx, edx', 'mov esi, ecx']) and has(m, ['lea edx, [esi + eax]', 'neg edx']) and
        has(m, ['mov edi, esi', 'sar edi, 1', 'add edi, ecx', 'js 0x648e16']), 'offset <-> cube coordinates')
require(has(m, ['mov eax, dword ptr [edx]', 'test eax, eax', 'je 0x648d9c', 'cmp dword ptr [ebx], 0',
                'mov dword ptr [ebp + 0x2c], 1', 'jne 0x648da3', 'mov dword ptr [ebp + 0x2c], 0', 'mov ecx, dword ptr [ebx]',
                'and ecx, eax', 'mov al, byte ptr [edx + 4]', 'test al, al', 'je 0x648dbd', 'mov dl, byte ptr [ebx + 4]',
                'test dl, dl', 'je 0x648dbd', 'cmp al, dl', 'je 0x648dbd', 'xor eax, eax', 'jmp 0x648dc2', 'mov eax, 1',
                'test ecx, ecx', 'je 0x648dca', 'test eax, eax', 'jne 0x648dd4', 'cmp dword ptr [ebp + 0x2c], 0',
                'jne 0x648eb6']), 'mask and continent test')
require(has(m, ['cmp byte ptr [edx + 5], 0', 'je 0x648e16', 'cmp byte ptr [ebx + 5], 0', 'jne 0x648eb6']) and
        has(m, ['mov byte ptr [edx + eax*8 + 5], 1']) and has(m, ['cmp dword ptr [ebp + 0x3c], 0', 'jbe 0x648eb6']) and
        has(m, ['call 0x578780']), 'owned cells must be unclaimed; a match claims them and is recorded')
report['matcher_pass'] = dict(
    function='00648a00',
    rule=['positions: every (column, row) with column in [-2, width+2) and row in [-2, height+2), as cube coordinates, '
          'in random order (std::random_shuffle over rand())',
          'at each position the piece order and the orientation order are shuffled again',
          'only pieces whose level (record +0x3c8) equals the current level are tried',
          'each significant piece cell (x, y) -> cube (x - (y >> 1), y, -(sum)) -> orientation and position matrix -> '
          'map column = X + (Y >> 1), row = Y; cells outside the map are ignored',
          'reject when piece mask != 0 and map mask != 0 and ((piece mask & map mask) == 0 or both continent bytes are '
          'non-zero and differ)',
          'reject when the piece cell is owned and the map cell is already claimed',
          'accept when at least one owned cell lies on the map: record (piece, orientation, position) and claim the cells'],
    cell_layout='8 bytes: u32 terrain mask, u8 continent, u8 owned/claimed, u8, u8')

# 4. Orientations (matcher constructor 0x578b00): four, built from (translation, turn 0, table index).
ctor = texts(0x578b00, 0x578d15)
require(ctor.count('call 0x75f2a0') == 4 and 'push 0x2dd1cd8' in ctor and
        has(ctor, ['mov edi, 1']) and has(ctor, ['mov eax, 2']) and
        has(ctor, ['mov dword ptr [esp + 0x18], eax', 'mov dword ptr [esp + 0x20], eax']) and
        has(ctor, ['mov dword ptr [esp + 0x18], edi', 'mov dword ptr [esp + 0x1c], 0xfffffffd', 'mov dword ptr [esp + 0x24], esi']) and
        has(ctor, ['mov dword ptr [esp + 0x18], 0xfffffffc', 'mov dword ptr [esp + 0x1c], esi', 'mov dword ptr [esp + 0x20], 4',
                   'mov dword ptr [esp + 0x24], esi', 'mov dword ptr [esp + 0x28], 6']) and
        has(ctor, ['mov dword ptr [esp + 0x18], 0xfffffffe', 'mov dword ptr [esp + 0x1c], 0xfffffffd',
                   'mov dword ptr [esp + 0x20], 5', 'mov dword ptr [esp + 0x24], esi', 'mov dword ptr [esp + 0x28], 9']),
        'four orientation descriptors')
table = {k: [s32(0xc90150 + k * 0x40 + 4 * j) for j in range(16)] for k in (0, 2, 6, 9)}
require(table[0] == [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1] and table[9] == [-1, 0, 0, 0, 0, -1, 0, 0, 0, 0, -1, 0, 0, 0, 0, 1] and
        table[2] == [0, 0, -1, 0, 0, -1, 0, 0, -1, 0, 0, 0, 0, 0, 0, 1] and table[6] == [0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 0, 0, 0, 0, 1],
        'orientation table rows')
require([s32(0xa3eb0c + 4 * k) for k in range(6)] == [0, 1, 1, 0, -1, -1], 'turn table')
report['orientations'] = [dict(translation=[0, 0, 0], table_index=0, meaning='identity'),
                          dict(translation=[1, -3, 2], table_index=2, meaning='(x, y, z) -> (-z, -y, -x): mirror'),
                          dict(translation=[-4, 0, 4], table_index=6, meaning='(x, y, z) -> (z, y, x): mirror'),
                          dict(translation=[-2, -3, 5], table_index=9, meaning='(x, y, z) -> (-x, -y, -z): half turn')]

# 5. Texel geometry: the global texel -> hex matrix (0x561da0) and the piece corner points (0x46da70).
build = texts(0x561db3, 0x561f4d)
require(abs(f32(0xa01e28) - 0.866) < 1e-6 and abs(f32(0x9e98f0) - math.pi / 6) < 1e-6 and f32(0x9f23e0) == 1 / 64 and
        abs(f32(0xa04dcc) - 1 / (64 * 0.866)) < 1e-7 and abs(f64(0x9f1958) - math.pi / 3) < 1e-12, 'matrix constants')
require(has(build, ['fld dword ptr [0xa01e28]']) and has(build, ['fld dword ptr [0x9e98f0]']) and
        has(build, ['fld dword ptr [0x9f23e0]']) and has(build, ['fld dword ptr [0xa04dcc]']) and
        has(build, ['push 0xd91030', 'call 0x8a86b6']), 'hex -> texel matrix is the inverse of the built matrix')
corners = texts(0x46dc98, 0x46de30)
require(f32(0x9ff880) == 128.0 and f32(0x9dc2c0) == 512.0 and 'movss xmm0, dword ptr [0x9ff880]' in corners and
        'movss xmm0, dword ptr [0x9dc2c0]' in corners and 'mov dword ptr [0xd91100], eax' in corners and
        'mov dword ptr [0xd91120], eax' in corners, 'piece corner points for 128 and 512 pixel images')


def matmul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def ident():
    return [[float(i == j) for j in range(4)] for i in range(4)]


def scale(x, y):
    value = ident(); value[0][0] = x; value[1][1] = y
    return value


rot = ident()
angle = f32(0x9e98f0)
rot[0][0], rot[0][1], rot[1][0], rot[1][1] = math.cos(angle), math.sin(angle), -math.sin(angle), math.cos(angle)
shear = ident(); shear[0][1] = -math.cos(f64(0x9f1958))
move = ident(); move[3][0], move[3][2] = 0.5, -0.5
cube = ident(); cube[2][2] = 0.0; cube[0][2] = cube[1][2] = -1.0
t2h = matmul(matmul(matmul(matmul(matmul(scale(1.0, f32(0xa01e28)), rot), scale(f32(0xa04dcc), f32(0x9f23e0))), shear), move), cube)


def texel_to_hex(px, py):
    return [round(px * t2h[0][j] + py * t2h[1][j] + t2h[3][j], 3) for j in range(3)]


require(texel_to_hex(0, 0) == [0.5, 0.0, -0.5] and texel_to_hex(64, 64) == [1.0, 1.0, -2.0] and
        texel_to_hex(64, 0) == [1.5, 0.0, -1.5] and texel_to_hex(512, 512) == [4.5, 8.0, -12.5], 'texel -> hex values')
report['texel_geometry'] = dict(
    builder='00561da0 (hex -> texel at 0xd91030 is its inverse); piece corners at 0046da70',
    texel_to_hex='cube x = px/64 - py/128 + 0.5, cube y (row) = py/64',
    consequence='One hex is 64 texels wide and rows are 64 texels apart (odd rows shifted by 32). A 128-pixel piece image '
                'covers 2 x 2 hexes and a 512-pixel image 8 x 8; images are stamped 1:1 into the texel map.',
    examples={'(0,0)': texel_to_hex(0, 0), '(64,64)': texel_to_hex(64, 64), '(128,128)': texel_to_hex(128, 128)})

# 6. Placement -> stamp record (in 0x425060) and the stamp flips (0x463b10).
record = texts(0x425fb6, 0x42610d)
require(has(record, ['imul eax, eax, 0x49c']) and has(record, ['mov eax, dword ptr [eax + 0x3bc]']) and
        has(record, ['imul eax, eax, 0x56c']) and has(record, ['push 0xd91030']) and
        has(record, ['mov ecx, dword ptr [eax + 0x3d0]', 'and ecx, 1', 'mov dword ptr [esi], ecx']), 'stamp record')
stamp = texts(0x463b56, 0x463b86)
require(has(stamp, ['mov eax, dword ptr [esi + 0x1c]', 'cmp eax, dword ptr [esi + 0x14]']) and 'setg cl' in stamp and
        'lea ecx, [ecx + ecx - 1]' in stamp, 'stamp direction +1/-1 from the rectangle corners')
report['stamp_record'] = dict(rule='texel origin = round(position * hexToTexel); rectangle = origin + the orientation\'s '
                                   'transformed corner pair ((0,0)-(128,128) when record flag +0x3d0 bit 0 is set, else '
                                   '(0,0)-(512,512)); a reversed corner order makes the stamp walk that axis backwards.')

# 7. Texel defaults before stamping (0x512b20) and the water/land class of a map cell (0x5a8640).
defaults = texts(0x512b20, 0x512bc0)
require(abs(f32(0x9e4948) - 1e-6) < 1e-12 and has(defaults, ['mov byte ptr [esp + 0x14], 4', 'mov byte ptr [esp + 0x15], 3',
                                                            'mov byte ptr [esp + 0x16], 0']), 'texel defaults')
classes = texts(0x5a86e1, 0x5a8705)
require(classes == ['mov eax, dword ptr [ecx + eax*8]', 'mov bl, 2', 'test eax, 0xf3ef9fff', 'je 0x5a86f1', 'xor bl, bl',
                    'jmp 0x5a8705', 'test eax, 0xc102000', 'je 0x5a86fc', 'mov bl, 1', 'jmp 0x5a8705', 'test eax, 0x4000',
                    'je 0x5a8705', 'mov bl, 2'], 'cell class from the terrain mask')
report['texel_defaults'] = dict(height_sum=0.0, weight_sum=1e-6, class_byte=4, id=3, best_blend=0,
                                note='id 3 is TerrainDef row 3 (Euro_Coast in both copies)')
report['cell_class'] = dict(rule='0 when any bit outside 0x0c106000 is set; else 1 for bits 0x0c102000; else 2',
                            used_for='seeding the coast flood fill of the texel class byte')
report['interpretation'] = dict(
    proven=['Placement is a greedy first-fit over shuffled positions, pieces and four orientations, level by level.',
            'The order depends on the C runtime rand(), so the layout is not a pure function of the map.',
            'A piece cell constrains the map by a terrain bit mask and an optional continent number.',
            'The texel map has 64 x 64 texels per hex; piece images are stamped 1:1 with optional mirroring.'],
    not_proven=['Where rand() is seeded before the matcher runs.',
                'How the game fills the map pattern grid (terrain mask and continent per plot); bit meanings are taken '
                'from the piece names in piece_cells.json.',
                'The exact matrix multiplication order inside the orientation builder (0x75f2a0).'])
with open(out, 'w', encoding='utf8', newline='\n') as stream:
    json.dump(report, stream, indent=1)
    stream.write('\n')
print(json.dumps(dict(status='PASS_RETAIL_PIECE_PLACEMENT_STATIC_PROBE', exe_sha256=sha, out=out)))
