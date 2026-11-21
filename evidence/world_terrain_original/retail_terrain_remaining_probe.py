"""Static, non-executing probe of three remaining questions about the retail Civ V DX11 terrain path:
1. which TerrainDef.csv copy the file system returns, 2. when the terrain spec cache flag is on,
3. what the second plot loop of the map-cell builder does.

The EXE is parsed as data (pefile) and disassembled (capstone); nothing is loaded or executed.
usage: python -I retail_terrain_remaining_probe.py CivilizationV_DX11.exe OUT.json [Upgrade1.Civ5Pkg]
"""
import hashlib, json, re, struct, sys
import capstone, pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

EXPECTED_SHA256 = 'b7c8977ebab33ba6c1abf65d63fa310f8d096341465e0fc419f1b4da0fcd8818'
PACKAGE_SHA256 = '1a817a8946eb0226167410562c0dbeb246d2bb193b555cb2d81ce3b767593486'
exe, out = sys.argv[1], sys.argv[2]
package = sys.argv[3] if len(sys.argv) > 3 else None
raw = open(exe, 'rb').read()
sha = hashlib.sha256(raw).hexdigest()
if sha != EXPECTED_SHA256:
    raise SystemExit('Retail EXE differs from the analysed build: ' + sha)
pe = pefile.PE(data=raw)
base = pe.OPTIONAL_HEADER.ImageBase
img = pe.get_memory_mapped_image()
md = Cs(CS_ARCH_X86, CS_MODE_32)
text = next(s for s in pe.sections if s.Name.rstrip(b'\0') == b'.text')
T0, T1 = text.VirtualAddress, text.VirtualAddress + text.Misc_VirtualSize


def cstr(va):
    return img[va - base:img.index(b'\0', va - base)].decode('latin1')


def texts(start, stop):
    return [f'{i.mnemonic} {i.op_str}'.strip() for i in md.disasm(img[start - base:stop - base], start)]


def has(listing, needle):
    return any(listing[k:k + len(needle)] == needle for k in range(len(listing) - len(needle) + 1))


def require(condition, message):
    if not condition:
        raise SystemExit('Pinned retail evidence no longer matches: ' + message)


def byte_writes(displacement):
    """Every 'mov byte ptr [reg + displacement], ...' in .text (register-relative, not stack)."""
    found = []
    needle = struct.pack('<I', displacement)
    k = img.find(needle, T0, T1)
    while k != -1:
        for back in (2, 3):
            ins = next(md.disasm(img[k - back:k + 12], base + k - back), None)
            if ins and ins.mnemonic == 'mov' and re.fullmatch(r'byte ptr \[e(ax|bx|cx|dx|si|di) \+ %s\], \w+' % hex(displacement),
                                                              ins.op_str):
                found.append((ins.address, ins.op_str))
                break
        k = img.find(needle, k + 1, T1)
    return found


report = dict(schema='zerosis.world_terrain_original.retail_terrain_remaining_probe.v1',
              exe=dict(name='CivilizationV_DX11.exe', bytes=len(raw), sha256=sha),
              tool=dict(pefile=pefile.__version__, capstone=capstone.__version__), executed=False,
              method='PE parse and linear x86 disassembly of pinned functions; no code was loaded or run.')

# 1. File lookup.
# 1a. Start-up (0x6d26a0): one "Base" index gets the FPKs, Resource\Overrides and Assets without *\DLC\*; then the
#     package {8871E748-29A4-4910-8C57-8C99E32D0167} is requested.
start = texts(0x6d26c2, 0x6d2945)
require(cstr(0xb68394) == 'Base' and 'call 0x8186f0' in start and cstr(0xa0e4b4) == 'Resource\\Common\\TerrainModels.fpk' and
        has(start, ['push 0xa0e4b4', 'mov ecx, esi', 'call 0x821840']) and cstr(0xa0e51c) == 'Resource\\Overrides' and
        cstr(0xa0e530) == '*\\DLC\\*' and has(start, ['push 0xa0e530', 'push -1', 'push 0xa0e538', 'mov ecx, edi', 'call 0x78fc00']) and
        has(start, ['mov dword ptr [esp + 0x18], 0x8871e748', 'mov eax, 0x29a4']) and start[-1] == 'call 0x4c94f0',
        'start-up file index order')
# 1b. Lookup (0x8181e0): extra indexes are searched from the last to the first; a hit there returns at once when the
#     index flag +0x88 is set and the hit has no source object or its source flag +0x280 is set; otherwise the Base
#     index is asked and wins over the remembered hit.
look = texts(0x8181e0, 0x81835a)
require(has(look, ['mov ebp, dword ptr [eax + 8]', 'sub ebp, dword ptr [eax + 4]', 'sar ebp, 2', 'dec ebp']) and
        has(look, ['call 0x822300', 'mov edi, eax', 'cmp edi, ebx', 'je 0x8182cd', 'mov eax, dword ptr [esp + 0x14]',
                   'cmp byte ptr [esi + 0x88], bl', 'je 0x8182bf', 'cmp eax, ebx', 'je 0x8182a9',
                   'cmp byte ptr [eax + 0x280], bl', 'je 0x8182bf']) and
        has(look, ['dec ebp', 'cmp edi, ebx', 'je 0x818240', 'mov eax, edi']) and
        has(look, ['mov ecx, dword ptr [0x6196a40]', 'mov edx, dword ptr [esp + 0x28]', 'mov eax, dword ptr [esp + 0x30]',
                   'mov esi, dword ptr [esp + 0x2c]', 'push eax', 'push esi', 'push edx', 'call 0x822300']), 'lookup order')
ctor = texts(0x8215b5, 0x8215e3)
require(ctor[0] == 'mov eax, 1' and 'mov byte ptr [esi + 0x88], al' in ctor, 'index flag +0x88 starts as 1')
writes280 = dict(byte_writes(0x280))
# 0x63f5fb is a byte pattern inside another instruction, not a real write.
require(sorted(writes280) == [0x63f5fb, 0x6b51e0, 0x6b528c, 0x834f8a] and writes280[0x834f8a] == 'byte ptr [esi + 0x280], 1',
        'writers of source flag +0x280')
pak_flag = texts(0x6b51c9, 0x6b51e6)
require(pak_flag == ['push eax', 'mov ecx, esi', 'call 0x8223d0', 'cmp eax, ebx', 'je 0x6b52f8',
                     'mov cl, byte ptr [esp + 0x244]', 'mov byte ptr [eax + 0x280], cl'], 'package pak flag from a parameter')
entry = texts(0x82231f, 0x822369)
require(has(entry, ['xor eax, eax', 'test esi, esi', 'je 0x822360', 'cmp dword ptr [esi + 8], eax', 'je 0x822360']) and
        has(entry, ['mov dword ptr [ebx], eax']), 'a hit without a source object reports a null source')
flag88 = [(a, op) for a, op in byte_writes(0x88) if 0x810000 <= a < 0x845000]
require([a for a, _ in flag88] == [0x8215d7, 0x8215ec] and all(op.endswith(', al') for _, op in flag88),
        'no file-system code clears index flag +0x88')
# 1c. The key is the file name only (0x832bd0): '/' -> '\', then the part after the last '\'.
key = texts(0x832c38, 0x832cb5)
require(key[:3] == ['cmp byte ptr [ecx], 0x2f', 'jne 0x832c40', 'mov byte ptr [ecx], 0x5c'] and
        has(key, ['push 0x5c', 'lea edx, [esp + 0x14]', 'push edx', 'lea ecx, [esp + 0x1c]', 'call 0x814890']) and
        key[-1] == 'call 0x8332e0', 'lookup key is the base name')
# 1d. Content packages register their indexes as extra indexes (0x47d440 -> 0x819be0); packages come from *.civ5pkg.
reg = texts(0x47d45e, 0x47d483)
require(reg[-2:] == ['push esi', 'call 0x819be0'] and cstr(0xa39e44) == '*.civ5pkg' and
        cstr(0xa39e5c) == '.\\App\\Engine\\cvContentPackageManager.cpp', 'content package indexes')
lookup = dict(
    startup='Base index: Resource FPKs (TerrainModels.fpk among them), Resource\\Overrides, Assets except *\\DLC\\*; then '
            'package {8871E748-29A4-4910-8C57-8C99E32D0167} is requested (0x4c94f0).',
    rule='Extra indexes (content packages, mods) are searched newest first and a hit returns immediately; the Base index '
         'is asked only when none of them has the file. This holds for hits without a source object (entry field +8 '
         'is 0, read here as loose files) and for pak hits whose flag +0x280 is set. That flag starts as 1; the package '
         'loader (0x6b51e0, 0x6b528c) overwrites it per pak from a parameter. Index flag +0x88 is always 1.',
    key='file name without directories, so assets\\terrain\\TerrainTextures\\TerrainDef.csv matches any TerrainDef.csv',
    consequence='When the Assets\\DLC\\Shared package is active its Terrain\\TerrainDef.csv is returned instead of the '
                'terraindef.csv inside TerrainModels.fpk.',
    not_proven=['That 0x4c94f0 activates the package and that its index contains Terrain\\TerrainDef.csv (expected '
                'from the package manifest and folder, not traced).',
                'That entry field +8 == 0 means a loose file.',
                'The direct disk open tried before the index lookup fails here because no such loose path exists.'])
if package:
    data = open(package, 'rb').read()
    require(hashlib.sha256(data).hexdigest() == PACKAGE_SHA256, 'Upgrade1.Civ5Pkg')
    require(b'<GUID>{8871E748-29A4-4910-8C57-8C99E32D0167}</GUID>' in data and b'<Ownership>FREE</Ownership>' in data,
            'package GUID and ownership')
    lookup['package'] = dict(file='Assets/DLC/Shared/Upgrade1.Civ5Pkg', sha256=PACKAGE_SHA256,
                             guid='{8871E748-29A4-4910-8C57-8C99E32D0167}', ownership='FREE',
                             note='The GUID requested at start-up is the package in Assets/DLC/Shared.')
report['file_lookup'] = lookup

# 2. Spec cache flag 0xd90f28 (settings apply function 0x453f80).
tier = texts(0x8bb6ce, 0x8bb70e)
require(tier == ['cmp eax, 0xa100', 'jg 0x8bb6fd', 'je 0x8bb6f1', 'cmp eax, 0x9300', 'je 0x8bb668', 'cmp eax, 0xa000', 'jne 0x8bb686',
                 'mov dword ptr [0x2e49edc], 7', 'jmp 0x8bb70e', 'mov dword ptr [0x2e49edc], 9', 'jmp 0x8bb70e',
                 'cmp eax, 0xb000', 'jne 0x8bb686', 'mov dword ptr [0x2e49edc], 0xa'], 'device tier from the feature level')
apply = texts(0x453f80, 0x454226)
require(cstr(0xa1b6b4) == 'TerrainDetailLevel' and cstr(0xa1b6fc) == 'TerrainTessLevel' and
        has(texts(0x5d8e0c, 0x5d8e16), ['push 0xd90f74', 'push 0xa1b6b4']) and
        has(texts(0x5d8e37, 0x5d8e41), ['push 0xd90f70', 'push 0xa1b6fc']), 'option variables')
require(has(apply, ['cmp edx, ecx', 'jge 0x4540b2', 'mov dword ptr [0xd90f4c], edi', 'mov ecx, dword ptr [0xd90f74]',
                    'mov dword ptr [0xd90f28], edi']) and
        has(apply, ['cmp dword ptr [0xd90f4c], edi', 'je 0x454082', 'mov ecx, dword ptr [0xd90f74]', 'sub ecx, eax',
                    'je 0x4541de', 'sub ecx, eax', 'je 0x45419e', 'sub ecx, eax', 'je 0x45415e', 'mov dword ptr [0xd90f28], edi']) and
        has(apply, ['mov dword ptr [0xd90f2c], 0x200', 'mov dword ptr [0xd90f28], eax']) and
        has(apply, ['mov dword ptr [0xd90f2c], esi', 'mov dword ptr [0xd90f28], edi']) and
        has(apply, ['cmp ebx, edi', 'jne 0x454155', 'mov dword ptr [0xd90f28], edi']) and
        has(apply, ['mov eax, 1', 'xor edi, edi']) and has(apply, ['mov ecx, 8']), 'spec flag rule')
report['spec_cache_flag'] = dict(
    function='00453f80', flag='0xd90f28',
    device_tier='0x2e49edc: 6 = feature level 9.3, 7 = 10.0, 9 = 10.1, 10 = 11.0 (8 comes from another path)',
    rule='flag = 1 only when device tier >= 8, internal flag 0xd90f4c != 0, TerrainDetailLevel is 2 or 3, and '
         'TerrainTessLevel != 0; otherwise 0.',
    effect='flag 0 -> TerrainShaderScreen pass 0 (no spec target); flag 1 -> pass 1 or 2 (see '
           'retail_terrain_blend_cpu_probe.json).',
    not_proven=['What sets 0xd90f4c to 0 besides this function, and where device tier 8 comes from.'])

# 3. Second plot loop of the map-cell builder (0x60b5f1..0x60bb94): feature and river lists; it never writes cells.
second = texts(0x60b610, 0x60bb94)
require(not any(re.search(r'\[e\w\w \+ e\w\w\*8', t) for t in second), 'second loop does not touch the cell array')
require(has(second, ['mov edx, dword ptr [ecx + 0x74]', 'push ebx', 'call edx', 'test eax, eax', 'jne 0x60b6be',
                     'lea eax, [esp + 0x50]', 'push eax', 'mov ecx, 0xd68f9c', 'call 0x639850']) and
        has(second, ['cmp eax, 4', 'jne 0x60b703']) and has(second, ['mov ecx, 0xd3ddf8']) and
        has(second, ['mov edx, dword ptr [ecx + 0x18]', 'push ebx', 'call edx', 'test al, al', 'je 0x60bb79']) and
        all(has(second, [f'mov {r}, dword ptr [{b} + {slot}]']) for r, b, slot in
            (('ecx', 'eax', '0x44'), ('eax', 'edx', '0x4c'), ('edx', 'ecx', '0x48'), ('ecx', 'eax', '0x50'),
             ('eax', 'edx', '0x40'), ('edx', 'ecx', '0x54'))), 'second loop calls')
first = texts(0x60af78, 0x60afd0)
require(has(first, ['cmp eax, 2', 'jne 0x60afd0']) and 'mov ecx, 0xd3dcb8' in first, 'first loop feature 2 list')
report['second_plot_loop'] = dict(
    range='0060b5f1-0060bb94',
    rule=['feature 0: position appended to the list at 0xd68f9c', 'feature 4: record appended to the list at 0xd3ddf8',
          'plot slot 0x18 false: nothing more',
          'plot slots 0x44/0x4c, 0x48/0x50, 0x40/0x54: river edge records for three hex sides'],
    first_loop_extra='feature 2: a record with terrain and continent goes to the list at 0xd3dcb8',
    sdk_reading='slot 0x18 IsRiver, 0x44 IsWOfRiver / 0x4c GetRiverEFlowDirection, 0x48 IsNWOfRiver / 0x50 '
                'GetRiverSEFlowDirection, 0x40 IsNEOfRiver / 0x54 GetRiverSWFlowDirection (names by SDK header slot order). '
                'Feature numbers 0, 2, 4 are ice, marsh and flood plains in the stock FeatureTypes order (not checked here).',
    consequence='The pattern cells used by the piece matcher are final after the first loop.')
with open(out, 'w', encoding='utf8', newline='\n') as stream:
    json.dump(report, stream, indent=1)
    stream.write('\n')
print(json.dumps(dict(status='PASS_RETAIL_TERRAIN_REMAINING_STATIC_PROBE', exe_sha256=sha, out=out, package=bool(package))))
