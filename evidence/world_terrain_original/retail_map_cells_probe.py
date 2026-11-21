"""Static, non-executing probe: how the retail Civ V DX11 EXE fills the map pattern grid that the terrain piece
matcher reads (terrain mask and continent per plot), and how the matcher's rand() is seeded.

The EXE is parsed as data (pefile) and disassembled (capstone); nothing is loaded or executed.
Interface method names come from the public SDK header CvDllInterfaces.h when it is given (slot = 4 * position, after
the two ICvUnknown methods); without it only the slot offsets are recorded.
usage: python -I retail_map_cells_probe.py CivilizationV_DX11.exe OUT.json [CvDllInterfaces.h]
"""
import hashlib, json, re, struct, sys
import capstone, pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

EXPECTED_SHA256 = 'b7c8977ebab33ba6c1abf65d63fa310f8d096341465e0fc419f1b4da0fcd8818'
HEADER_SHA256 = 'c3bc7fc1377c8466e67974b779d0e8a582e728e5a41e3b47f77dc38089209486'
exe, out = sys.argv[1], sys.argv[2]
header = sys.argv[3] if len(sys.argv) > 3 else None
raw = open(exe, 'rb').read()
sha = hashlib.sha256(raw).hexdigest()
if sha != EXPECTED_SHA256:
    raise SystemExit('Retail EXE differs from the analysed build: ' + sha)
pe = pefile.PE(data=raw)
base = pe.OPTIONAL_HEADER.ImageBase
img = pe.get_memory_mapped_image()
md = Cs(CS_ARCH_X86, CS_MODE_32)
imports = {imp.address: (imp.name or b'').decode() for entry in pe.DIRECTORY_ENTRY_IMPORT for imp in entry.imports}


def cstr(va):
    return img[va - base:img.index(b'\0', va - base)].decode('latin1')


def rows(start, stop):
    return list(md.disasm(img[start - base:stop - base], start))


def texts(start, stop):
    return [f'{i.mnemonic} {i.op_str}'.strip() for i in rows(start, stop)]


def has(listing, needle):
    return any(listing[k:k + len(needle)] == needle for k in range(len(listing) - len(needle) + 1))


def require(condition, message):
    if not condition:
        raise SystemExit('Pinned retail evidence no longer matches: ' + message)


report = dict(schema='zerosis.world_terrain_original.retail_map_cells_probe.v1',
              exe=dict(name='CivilizationV_DX11.exe', bytes=len(raw), sha256=sha),
              tool=dict(pefile=pefile.__version__, capstone=capstone.__version__), executed=False,
              method='PE parse and linear x86 disassembly of pinned functions; no code was loaded or run.')

# 1. Seed: TerrainSystem::CreateTerrain (0x709b50) calls srand(third argument) first; its only caller passes the value
#    returned by slot 0x118 of the object that slot 0x1c of the game context returns.
require(imports[0x9d6848] == 'srand' and imports[0x9d6894] == 'rand', 'C runtime imports')
head = texts(0x709b50, 0x709b75)
require(head[4] == 'mov eax, dword ptr [ebp + 0x10]' and head[-4:-1] == ['push eax', 'mov dword ptr [esp + 0x80], ebx',
                                                                      'call dword ptr [0x9d6848]'], 'srand(arg3) at entry')
call = texts(0x60bba7, 0x60bbd6)
require(call == ['lea ecx, [esp + 0x40]', 'push ecx', 'call 0x4455d0', 'mov eax, dword ptr [eax]', 'mov edx, dword ptr [eax]',
                 'add esp, 4', 'push eax', 'mov eax, dword ptr [edx + 0x118]', 'call eax', 'push eax', 'push 1',
                 'lea ecx, [esp + 0xb8]', 'push ecx', 'mov ecx, 0xd165e0', 'call 0x709b50'], 'seed argument')
getter = texts(0x4455d0, 0x4455e7)
require(getter[-3:] == ['mov ecx, dword ptr [eax + 0x1c]', 'push esi', 'call ecx'], 'context slot 0x1c')
report['seed'] = dict(create_terrain='00709b50', caller='0060abb0', listing=call,
                      rule='srand(context.slot[0x1c]().slot[0x118]()) at the start of CreateTerrain; the matcher shuffles '
                           'then use MSVCR90 rand().',
                      caveat='Other rand() calls inside CreateTerrain before the matcher were not enumerated.')

# 2. Per plot: terrain mask and continent byte (first plot loop of 0x60abb0).
loop = texts(0x60afd0, 0x60b110)
require(has(loop, ['mov esi, 0x4000', 'mov byte ptr [esp + 0x44], 0']) and
        has(loop, ['mov eax, dword ptr [edx + 0xd8]', 'push ebp', 'call eax', 'mov ecx, dword ptr [ebp]',
                   'mov edx, dword ptr [ecx + 0x70]', 'mov bl, al', 'push ebp', 'mov byte ptr [esp + 0x48], bl', 'call edx',
                   'mov esi, eax', 'cmp esi, 5', 'jne 0x60b019', 'mov esi, 0x2000', 'mov byte ptr [esp + 0x44], 0']) and
        has(loop, ['cmp esi, 6', 'jne 0x60b050']) and has(loop, ['mov esi, 0x4000', 'mov byte ptr [esp + 0x48], 0']) and
        has(loop, ['mov edx, dword ptr [ecx + 0x6c]', 'push ebp', 'call edx', 'test al, al', 'je 0x60b087', 'mov esi, 0x400']) and
        has(loop, ['mov eax, dword ptr [edx + 0x64]', 'push ebp', 'call eax', 'test al, al', 'je 0x60b0cc', 'test esi, esi',
                   'jne 0x60b09f', 'mov esi, 0x20', 'jmp 0x60b0fc', 'cmp esi, 2', 'jne 0x60b0ab', 'mov esi, 0x80', 'jmp 0x60b0fc',
                   'cmp esi, 3', 'jne 0x60b0b7', 'mov esi, 0x100', 'jmp 0x60b0fc', 'sub esi, 4', 'neg esi', 'sbb esi, esi',
                   'and esi, 0xfffffe40', 'add esi, 0x200', 'jmp 0x60b0fc', 'test esi, esi', 'jne 0x60b0d7', 'mov esi, 1',
                   'jmp 0x60b0fc', 'cmp esi, 2', 'jne 0x60b0e3', 'mov esi, 4', 'jmp 0x60b0fc', 'cmp esi, 3', 'jne 0x60b0ef',
                   'mov esi, 8', 'jmp 0x60b0fc', 'sub esi, 4', 'neg esi', 'sbb esi, esi', 'and esi, 0xfffffff2', 'add esi, 0x10',
                   'mov ecx, dword ptr [ebp]', 'mov edx, dword ptr [ecx + 0x74]', 'push ebp', 'call edx', 'mov edi, eax',
                   'cmp edi, -1', 'je 0x60b57f']), 'terrain and hill/mountain mapping')
store = texts(0x60b57f, 0x60b5ab)
require(store[-3:] == ['mov dword ptr [ecx + eax*8], esi', 'mov ecx, dword ptr [esp + 0x14c]',
                       'mov dword ptr [ecx + eax*8 + 4], edx'] and 'mov edx, dword ptr [esp + 0x44]' in store, 'cell store')

# 3. Natural wonders: feature info slot 0x24 must be true; the type name picks the bit.
names = {}
listing = rows(0x60b14a, 0x60b573)
pending = None
for k, ins in enumerate(listing):
    m = re.fullmatch(r'(edx|ecx), (0xa20[0-9a-f]{3})', ins.op_str)
    if ins.mnemonic == 'mov' and m and cstr(int(m.group(2), 16)).startswith('FEATURE_'):
        pending = cstr(int(m.group(2), 16))
        names[pending] = None
    m = re.fullmatch(r'esi, (0x[0-9a-f]+)', ins.op_str)
    if ins.mnemonic == 'mov' and m and pending and names[pending] is None:
        names[pending] = int(m.group(1), 16)
        pending = None
flat = [f'{i.mnemonic} {i.op_str}'.strip() for i in listing]
require(has(flat, ['mov edx, dword ptr [ecx + 0x24]', 'push eax', 'call edx', 'test al, al', 'je 0x60b573']), 'slot 0x24 gate')
require(has(flat, ['jne 0x60b50e', 'lea esi, [eax + 4]', 'jmp 0x60b573']) and has(flat, ['je 0x60b56e']) and
        flat[-1] == 'mov esi, 0x40000', 'Solomon -> 4, Fuji and unlisted wonders -> 0x40000')
expected = {'FEATURE_GEYSER': 0x8000, 'FEATURE_CRATER': 0x10000, 'FEATURE_GIBRALTAR': 0x4000000, 'FEATURE_MESA': 0x80000,
            'FEATURE_REEF': 0x100000, 'FEATURE_VOLCANO': 0x200000, 'FEATURE_POTOSI': 0x20000, 'FEATURE_ULURU': 0x400000,
            'FEATURE_MT_SINAI': 0x800000, 'FEATURE_MT_KAILASH': 0x1000000, 'FEATURE_SRI_PADA': 0x2000000,
            'FEATURE_KILIMANJARO': 0x800, 'FEATURE_LAKE_VICTORIA': 0x1000}
require({k: v for k, v in names.items() if k in expected} == expected and
        set(names) - set(expected) == {'FEATURE_FUJI', 'FEATURE_SOLOMONS_MINES', 'FEATURE_FOUNTAIN_YOUTH', 'FEATURE_EL_DORADO'},
        'natural wonder bits')
wonders = {k: f'{v:#x}' for k, v in expected.items()}
wonders.update({'FEATURE_FUJI': '0x40000', 'FEATURE_SOLOMONS_MINES': '0x4 (flat desert)',
                'FEATURE_FOUNTAIN_YOUTH': 'unchanged (base terrain)', 'FEATURE_EL_DORADO': 'unchanged (base terrain)',
                'any other natural wonder': '0x40000'})
report['plot_to_cell'] = dict(
    function='0060abb0',
    slots={'map 0x3c': 'plot at (x, y)', 'plot 0xd8': 'continent byte', 'plot 0x70': 'terrain', 'plot 0x6c': 'mountain test',
           'plot 0x64': 'hills test', 'plot 0x74': 'feature', 'context 0xbc': 'feature info', 'feature info 0x24': 'gate',
           'feature info 0x8': 'type name'},
    terrain_rule=['no plot: mask 0x4000, continent 0', 'terrain 5: 0x2000, continent 0', 'terrain 6: 0x4000, continent 0',
                  'mountain: 0x400',
                  'hills: terrain 0 -> 0x20, 2 -> 0x80, 3 -> 0x100, 4 -> 0x200, other -> 0x40',
                  'flat: terrain 0 -> 0x1, 2 -> 0x4, 3 -> 0x8, 4 -> 0x10, other -> 0x2',
                  'continent byte = plot slot 0xd8 for everything except terrain 5 and 6'],
    natural_wonders=wonders,
    note='Features that fail the slot 0x24 gate (forest, jungle, marsh, ice, ...) leave the terrain mask unchanged.')
if header:
    text = open(header, encoding='latin1').read()
    require(hashlib.sha256(text.encode('latin1')).hexdigest() == HEADER_SHA256, 'SDK header')

    def method(interface, slot):
        body = re.search(r'class\s+' + interface + r'\s*:\s*public\s+\w+\s*\{(.*?)\n\};', text, re.S).group(1)
        lines = [line.strip() for line in body.splitlines() if 'virtual' in line]
        return re.search(r'(\w+)\s*\(', lines[slot // 4 - 2].split('DLLCALL')[-1]).group(1)

    named = {'ICvGameContext1 0x1c': method('ICvGameContext1', 0x1c), 'ICvPreGame1 0x118': method('ICvPreGame1', 0x118),
             'ICvGameContext1 0xbc': method('ICvGameContext1', 0xbc), 'ICvMap1 0x3c': method('ICvMap1', 0x3c),
             'ICvPlot1 0xd8': method('ICvPlot1', 0xd8), 'ICvPlot1 0x70': method('ICvPlot1', 0x70),
             'ICvPlot1 0x6c': method('ICvPlot1', 0x6c), 'ICvPlot1 0x64': method('ICvPlot1', 0x64),
             'ICvPlot1 0x74': method('ICvPlot1', 0x74), 'ICvFeatureInfo1 0x24': method('ICvFeatureInfo1', 0x24),
             'ICvFeatureInfo1 0x8': method('ICvFeatureInfo1', 0x8)}
    require(named == {'ICvGameContext1 0x1c': 'GetPreGame', 'ICvPreGame1 0x118': 'mapRandomSeed',
                      'ICvGameContext1 0xbc': 'GetFeatureInfo', 'ICvMap1 0x3c': 'GetPlot', 'ICvPlot1 0xd8': 'GetContinentType',
                      'ICvPlot1 0x70': 'GetTerrainType', 'ICvPlot1 0x6c': 'IsMountain', 'ICvPlot1 0x64': 'IsHills',
                      'ICvPlot1 0x74': 'GetFeatureType', 'ICvFeatureInfo1 0x24': 'IsNaturalWonder',
                      'ICvFeatureInfo1 0x8': 'GetType'}, 'SDK interface slots')
    report['sdk_names'] = dict(header_sha256=HEADER_SHA256, slots=named,
                               basis='Slot = 4 * (2 ICvUnknown methods + position in the public SDK header). The interface '
                                     'of each object is inferred from use, not proven from the EXE.',
                               reading='seed = GetPreGame()->mapRandomSeed(); terrain 0-6 = grass, plains, desert, tundra, '
                                       'snow, coast, ocean (SDK TerrainTypes order).')
report['interpretation'] = dict(
    proven=['CreateTerrain seeds rand() from one value supplied by its caller.',
            'A plot becomes one terrain bit plus a continent byte; water has continent 0.',
            'Only natural wonders change the bit; other features do not.'],
    not_proven=['That no other rand() call runs between srand and the matcher.',
                'Interface identities (they match the public SDK header slot for slot).'])
with open(out, 'w', encoding='utf8', newline='\n') as stream:
    json.dump(report, stream, indent=1)
    stream.write('\n')
print(json.dumps(dict(status='PASS_RETAIL_MAP_CELLS_STATIC_PROBE', exe_sha256=sha, out=out, sdk=bool(header))))
