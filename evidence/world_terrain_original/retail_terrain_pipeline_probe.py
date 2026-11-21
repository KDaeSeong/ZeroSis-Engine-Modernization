"""Static, non-executing probe: which embedded DXBC belongs to which pass of the retail terrain and fog-of-war effects,
and how the retail EXE reads Resource/Common/TerrainPiecesLibrary.fxsb.

The EXE is parsed as data (pefile) and disassembled (capstone); nothing is loaded or executed.
usage: python -I retail_terrain_pipeline_probe.py CivilizationV_DX11.exe OUT.json
"""
import collections, hashlib, json, re, struct, sys
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


def u32(va):
    return struct.unpack('<I', img[va - base:va - base + 4])[0]


def cstr(va):
    return img[va - base:img.index(b'\0', va - base)].decode('latin1')


def listing(start, stop):
    return [f'{i.mnemonic} {i.op_str}'.strip() for i in md.disasm(img[start - base:stop - base], start)]


def require(condition, message):
    if not condition:
        raise SystemExit('Pinned retail evidence no longer matches: ' + message)


def blob_info(va):
    """File offset, stage and shader model of the DXBC container at a virtual address."""
    offset = pe.get_offset_from_rva(va - base)
    require(raw[offset:offset + 4] == b'DXBC', f'DXBC at {va:08x}')
    size, count = struct.unpack_from('<II', raw, offset + 24)
    blob = raw[offset:offset + size]
    for chunk_offset in struct.unpack_from('<%dI' % count, blob, 32):
        if blob[chunk_offset:chunk_offset + 4] in (b'SHDR', b'SHEX'):
            token = struct.unpack_from('<I', blob, chunk_offset + 8)[0]
            stage = {0: 'ps', 1: 'vs', 2: 'gs', 3: 'hs', 4: 'ds', 5: 'cs'}[token >> 16]
            return dict(file_offset=f'{offset:08x}', stage=stage, model=f'{stage}_{(token >> 4) & 0xf}_{token & 0xf}',
                        bytes=size, sha256=hashlib.sha256(blob).hexdigest())
    raise SystemExit('Pinned retail evidence no longer matches: shader code chunk')


report = dict(schema='zerosis.world_terrain_original.retail_terrain_pipeline_probe.v1',
              exe=dict(name='CivilizationV_DX11.exe', bytes=len(raw), sha256=sha),
              tool=dict(pefile=pefile.__version__, capstone=capstone.__version__), executed=False,
              method='PE parse and linear x86 disassembly of the pinned renderer init and loader code; no code was loaded or run.')

# 1. Effects live in an array of 0x520-byte records indexed by the registered shader id.
ARRAY, STRIDE = 0x5d1e5c0, 0x520
require(listing(0x8bd775, 0x8bd787) == ['imul esi, esi, 0x520', 'add esi, 0x5d1e5c0', 'mov eax, dword ptr [esi + 0x518]'],
        'effect record array base and stride')
names = {ident: cstr(u32(0xc9e890 + ident * 8)) for ident in range(0x5e)}

# 2. The renderer init (0x4e5c20) creates every shader with VS 0x8bbc40, PS 0x8bbbf0, HS 0x8bbcc0, DS 0x8bbd10 and
#    stores each returned 16-bit handle with the next "mov word ptr [handle], ax".
CREATORS = {'0x8bbc40': 'vs', '0x8bbbf0': 'ps', '0x8bbcc0': 'hs', '0x8bbd10': 'ds'}
INIT, INIT_END = 0x4e5c20, 0x4f5ca0
rows = list(md.disasm(img[INIT - base:INIT_END - base], INIT))
handles = collections.defaultdict(list)
pending, pushes = None, []
for ins in rows:
    if ins.mnemonic == 'push':
        pushes.append(ins.op_str)
        continue
    if ins.mnemonic == 'call' and ins.op_str in CREATORS:
        blob_va = next(int(p, 16) for p in reversed(pushes) if p.startswith('0x') and int(p, 16) > 0x1000000)
        pending = (ins.address, CREATORS[ins.op_str], blob_va)
        pushes = []
        continue
    match = re.fullmatch(r'word ptr \[(0x[0-9a-f]+)\], ax', ins.op_str)
    if ins.mnemonic == 'mov' and match and pending:
        info = blob_info(pending[2])
        require(info['stage'] == pending[1], f'creator stage at {pending[0]:08x}')
        handles[int(match.group(1), 16)].append(dict(site=f'{pending[0]:08x}', **info))
        pending = None
    if ins.mnemonic == 'call':
        pushes = []

# 3. Each effect record starts with pass records of five handles (VS, PS, GS, HS, DS); +0x500 holds the pass count.
writes = collections.defaultdict(dict)
regs = {}
for ins in rows:
    match = re.fullmatch(r'(\w+), word ptr \[(0x[0-9a-f]+)\]', ins.op_str)
    if ins.mnemonic == 'movzx' and match:
        regs[match.group(1)] = int(match.group(2), 16)
        continue
    match = re.fullmatch(r'dword ptr \[(0x[0-9a-f]+)\], (\w+)', ins.op_str)
    if ins.mnemonic == 'mov' and match:
        address = int(match.group(1), 16)
        if ARRAY <= address < ARRAY + STRIDE * 0x5e:
            ident, field = divmod(address - ARRAY, STRIDE)
            value = match.group(2)
            if value in regs:
                writes[ident][field] = ('handle', regs[value])
            elif value.startswith('0x') or value.isdigit():
                writes[ident][field] = ('imm', int(value, 0))
            else:
                writes[ident][field] = ('reg', value)
    elif ins.op_str.split(',')[0] in regs and ins.mnemonic in ('mov', 'xor', 'pop', 'lea', 'movzx'):
        regs.pop(ins.op_str.split(',')[0], None)

SLOTS = ('vs', 'ps', 'gs', 'hs', 'ds')
EFFECTS = (0x2c, 0x32, 0x33, 0x34, 0x35, 0x3a, 0x45, 0x49, 0x4a, 0x4b, 0x4c, 0x4d, 0x4e, 0x5b)


def sm5(handle):
    """The shader-model-5 (feature level 11) variant created for a handle, plus the other variants."""
    variants = handles[handle]
    best = [v for v in variants if v['model'].endswith('_5_0')]
    require(len(best) == 1, f'one shader model 5 variant for handle {handle:08x}')
    return dict(handle=f'{handle:08x}', sm5=best[0], other_models=sorted(v['model'] for v in variants if v is not best[0]))


effects = {}
for ident in EFFECTS:
    record = writes[ident]
    count = record.get(0x500)
    passes = []
    for index in range(0, 0x500 // 0x14):
        fields = [record.get(index * 0x14 + 4 * slot) for slot in range(5)]
        if not any(f and f[0] == 'handle' for f in fields):
            break
        entry = {}
        for slot, field in zip(SLOTS, fields):
            if field and field[0] == 'handle':
                entry[slot] = sm5(field[1])
        passes.append(entry)
    effects[f'{ident:#04x}'] = dict(name=names[ident], record=f'{ARRAY + ident * STRIDE:08x}', passes=passes,
                                     pass_count_field=count[1] if count and count[0] == 'imm' else None)


def ps(ident, index):
    return effects[f'{ident:#04x}']['passes'][index]['ps']['sm5']['file_offset']


def vs(ident, index):
    return effects[f'{ident:#04x}']['passes'][index]['vs']['sm5']['file_offset']


terrain = effects['0x49']['passes']
require(len(terrain) == 8 and effects['0x49']['pass_count_field'] == 8, 'TerrainShader has 8 passes')
require([vs(0x49, i) for i in range(8)] == ['00ef1e90'] * 3 + ['00ef2198'] * 3 + ['00ef3340'] * 2 and
        [ps(0x49, i) for i in range(8)] == ['00f02858', '00f04768', '00f06080'] * 2 + ['00f04768', '00f06080'],
        'TerrainShader pass VS/PS')
require([terrain[i]['hs']['sm5']['file_offset'] for i in range(3)] == ['00f152f0', '00f152f0', '00f156b8'] and
        all(terrain[i]['ds']['sm5']['file_offset'] == '00f15a80' for i in range(3)) and
        all('hs' not in terrain[i] and 'ds' not in terrain[i] for i in range(3, 8)), 'TerrainShader tessellated passes 0-2')
require(all(not terrain[i]['vs']['other_models'] for i in range(3)), 'tessellation control-point VS exists only for SM5')
require([(vs(0x4a, 0), ps(0x4a, 0))] == [('00ef4160', '00f06530')], 'NormalCalculate pass')
require([(vs(0x4b, i), ps(0x4b, i)) for i in range(2)] == [('00ef46b8', '00f07878'), ('00ef46b8', '00f08a18')], 'CacheBake passes')
require([(vs(0x4c, i), ps(0x4c, i)) for i in range(5)] == [('00ef4f50', '00f0a1f0'), ('00ef7e30', '00f0d840'),
                                                            ('00ef4f50', '00f0d840'), ('00efff90', '00f12098'),
                                                            ('00ef4160', '00f13230')], 'TerrainShaderScreen passes')
require([(vs(0x4d, i), ps(0x4d, i)) for i in range(2)] == [('00f009d8', '00f136b0'), ('00f01378', '00f13b60')], 'CompositeShader passes')
require([(vs(0x4e, i), ps(0x4e, i)) for i in range(2)] == [('00f01d60', '00f140a0'), ('00f01d60', '00f14930')], 'TerrainDecalShader passes')
require([ps(0x34, i) for i in range(5)] == ['00e99908', '00e99cf8', '00e9a0e8', '00e9a4d8', '00e9a760'], 'FOWDrawMask passes')
require([ps(0x33, 0), ps(0x35, 0)] == ['00e98eb0', '00e9ac10'], 'FOWParticleShader and FOWBaseLayer pixel shaders')
report['effect_records'] = dict(array=f'{ARRAY:08x}', stride=STRIDE, pass_record='five 16-bit shader handles widened to '
                                'dwords: VS, PS, GS, HS, DS; field +0x500 is the pass count', effects=effects)

# 4. TerrainPiecesLibrary.fxsb loader: version 20, then four counted arrays (u32, u8, u16, 0x56c-byte piece records).
loader = listing(0x4041ff, 0x404214)
require(loader[3:6] == ['call 0x82bde0', 'cmp dword ptr [esp + 0x24], 0x14', 'je 0x40423a'], 'fxsb version 20 check')
require(cstr(0xa27690) == 'Resource\\Common\\TerrainPiecesLibrary.fxsb', 'fxsb path')
body = listing(0x5fca30, 0x5fcb5f)
reads = [i for i, text in enumerate(body) if text == 'call 0x82bde0']
require(len(reads) == 4, 'four counted arrays')
scaled = []
for start, stop in zip(reads, reads[1:] + [len(body)]):
    part = body[start:stop]
    if 'imul ecx, ecx, 0x56c' in part:
        scaled.append(0x56c)
    else:
        doubles = sum(1 for t in part if t == 'add ecx, ecx')
        scaled.append(1 << doubles)
require(scaled == [4, 1, 2, 0x56c], 'array element sizes')
require('lea ebx, [edi + 0x154]' in body, 'piece array lives at +0x154')
fallback = listing(0x6a9bb0, 0x6a9bd6)
require(cstr(0xa27770) == '%s\\%s\\%s' and cstr(0xa2777c) == '%s\\*.csv', 'CSV fallback path format')
continents = [cstr(u32(0xb9960c + 4 * k)) for k in range(5)]
require(continents == ['Generic', 'America', 'Asia', 'Africa', 'Europe'], 'piece source continents')
report['pieces_library_loader'] = dict(
    path='Resource\\Common\\TerrainPiecesLibrary.fxsb', version_check=loader, reader=dict(function='005fca30', listing=body),
    layout='u32 version (must be 20); then four times: u32 count followed by count elements of 4, 1, 2 and 0x56c bytes',
    fallback='When the file is missing or the version differs, pieces are rebuilt from %s\\%s\\%s\\*.csv under the folders '
             + ', '.join(continents) + '.')
report['interpretation'] = dict(
    proven=['Each pass of each effect names its shaders by handle; the handle-to-bytecode mapping is fixed by the init code.',
            'TerrainShader passes 0-2 tessellate (quad domain HS/DS) and exist only for shader model 5; passes 3-7 use plain VS.',
            'The 8-layer material blend pixel shaders belong to TerrainShaderScreen, the cube-map lighting shaders to '
            'CacheBake, and the Sobel normal shader to NormalCalculate.',
            'TerrainPiecesLibrary.fxsb is version 20 with four counted arrays (u32, u8, u16, 0x56c-byte records).'],
    not_proven=['The order in which the cache passes run per frame (only their membership is proven here).'])
with open(out, 'w', encoding='utf8', newline='\n') as stream:
    json.dump(report, stream, indent=1)
    stream.write('\n')
print(json.dumps(dict(status='PASS_RETAIL_TERRAIN_PIPELINE_STATIC_PROBE', exe_sha256=sha, out=out,
                      handles=len(handles), effects=len(effects))))
