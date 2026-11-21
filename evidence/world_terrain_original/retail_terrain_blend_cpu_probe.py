"""Static, non-executing probe of the CPU side of the retail Civ V DX11 terrain material blend.

Question: how does the retail EXE turn the placed terrain pieces into the per-vertex material slots and weights that
the TerrainShaderScreen blend shaders consume, and what does it do with the TerrainDef.csv columns?
The EXE is parsed as data (pefile) and disassembled (capstone); nothing is loaded or executed.
usage: python -I retail_terrain_blend_cpu_probe.py CivilizationV_DX11.exe OUT.json
"""
import hashlib, json, struct, sys
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
imports = {imp.address: (entry.dll.decode() + '!' + (imp.name or b'').decode())
           for entry in pe.DIRECTORY_ENTRY_IMPORT for imp in entry.imports}


def u32(va):
    return struct.unpack('<I', img[va - base:va - base + 4])[0]


def f32(va):
    return struct.unpack('<f', img[va - base:va - base + 4])[0]


def f64(va):
    return struct.unpack('<d', img[va - base:va - base + 8])[0]


def cstr(va):
    return img[va - base:img.index(b'\0', va - base)].decode('latin1')


def texts(start, stop):
    return [f'{i.mnemonic} {i.op_str}'.strip() for i in md.disasm(img[start - base:stop - base], start)]


def rows(start, stop):
    return [dict(va=f'{i.address:08x}', text=f'{i.mnemonic} {i.op_str}'.strip())
            for i in md.disasm(img[start - base:stop - base], start)]


def contains(haystack, needle):
    return any(haystack[k:k + len(needle)] == needle for k in range(len(haystack) - len(needle) + 1))


def require(condition, message):
    if not condition:
        raise SystemExit('Pinned retail evidence no longer matches: ' + message)


report = dict(schema='zerosis.world_terrain_original.retail_terrain_blend_cpu_probe.v1',
              exe=dict(name='CivilizationV_DX11.exe', bytes=len(raw), sha256=sha),
              tool=dict(pefile=pefile.__version__, capstone=capstone.__version__), executed=False,
              method='PE parse and linear x86 disassembly of pinned functions; no code was loaded or run.')

# 1. TerrainDef.csv loader (0x61bae0): commas become spaces, then sscanf_s "%i %s %s %s %f %f %i %x".
loader = texts(0x61bc00, 0x61bc5a)
require(cstr(0xa26c6c) == '%i %s %s %s %f %f %i %x' and loader[-2:] == ['push edx', 'call dword ptr [0x9d6850]'] and
        imports[0x9d6850] == 'MSVCR90.dll!sscanf_s', 'TerrainDef row format')
require(loader[:4] == ['push 0x20', 'push 0x2c', 'lea ecx, [esp + 0x18]', 'call 0x814fb0'], 'comma to space before scanning')
# sscanf_s destinations relative to the loop's stack frame: continent +0x28, diffuse +0x58, height +0x258, spec +0x158,
# BaseDominance (%f) +0x54, Texture Scale (%f) +0x34, Projection (%i) +0x30, ID (%x, hexadecimal) +0x38.
require(loader[4:16] == ['lea eax, [esp + 0x38]', 'push eax', 'lea ecx, [esp + 0x34]', 'push ecx', 'lea edx, [esp + 0x3c]',
                         'push edx', 'lea eax, [esp + 0x60]', 'push eax', 'push 0x100', 'lea ecx, [esp + 0x16c]', 'push ecx',
                         'push 0x100'], 'sscanf_s destination order')
store = texts(0x61c100, 0x61c153)
require(store == ['mov eax, dword ptr [ebx]', 'mov ecx, dword ptr [esp + 0x30]', 'xorps xmm0, xmm0',
                  'mov dword ptr [ebx + eax*4 + 0x508], ecx', 'mov edx, dword ptr [ebx]',
                  'movss dword ptr [ebx + edx*4 + 0x308], xmm0', 'mov eax, dword ptr [ebx]',
                  'movss xmm0, dword ptr [esp + 0x34]', 'movss dword ptr [ebx + eax*4 + 0x408], xmm0',
                  'mov ecx, dword ptr [esp + 0x28]', 'mov edx, dword ptr [ecx*4 + 0xb99658]', 'or edx, dword ptr [esp + 0x38]',
                  'mov eax, dword ptr [ebx]', 'mov dword ptr [ebx + eax*4 + 0x608], edx', 'mov ecx, dword ptr [ebx]',
                  'mov edx, dword ptr [esp + 0x28]', 'mov dword ptr [ebx + ecx*4 + 0x708], edx', 'inc dword ptr [ebx]'],
        'row store: projection, a zeroed float, scale, continent key | ID, continent')
whole = texts(0x61bae0, 0x61c498)
require(not any('esp + 0x54]' in t and not t.startswith('lea') for t in whole[whole.index('call dword ptr [0x9d6850]'):]),
        'the BaseDominance stack slot is not read after scanning')
continent_keys = [u32(0xb99658 + 4 * k) for k in range(5)]
require(continent_keys == [0x100000, 0x110000, 0x120000, 0x130000, 0x140000], 'continent key table')
require(abs(f32(0xa01020) - 0.01) < 1e-9 and cstr(0xa26cb4) == 'Checkerboard.dds', 'checkerboard fallback row')
report['terraindef_loader'] = dict(
    function='0061bae0', format=cstr(0xa26c6c), scan=rows(0x61bc00, 0x61bc5a), row_store=rows(0x61c100, 0x61c153),
    continent_keys=[f'{k:#x}' for k in continent_keys],
    consequence='Rows are kept in file order. Stored per row: diffuse/spec/height textures, Texture Scale, Projection, '
                'key = 0x100000 + continent*0x10000 | ID (ID is parsed as hexadecimal) and the continent. A float column '
                'at +0x308 is always written as 0.0. BaseDominance is scanned but never stored or read again. After the '
                'file a Checkerboard.dds row is appended (scale 0.01, projection 0, key -1).')

# 2. Blend kernel (0x6bb2b0): separable 5x5, 1-D weights 0.125, 0.636056, 1, 0.636056, 0.125, normalised to sum 1.
kernel = texts(0x6bb2b0, 0x6bb437)
require(abs(f32(0xa02860) - 0.125) < 1e-9 and abs(f32(0x9dbb20) - 0.636056) < 1e-6, 'kernel constants')
require('mov edx, 0xfffffffe' in kernel and 'mov dword ptr [edx + 0x3d4], 0x19' in kernel and 'divss xmm7, xmm1' in kernel,
        'offsets from -2, 25 taps, normalisation')
one_d = [0.125, f32(0x9dbb20), 1.0, f32(0x9dbb20), 0.125]
total = sum(a * b for a in one_d for b in one_d)
weights = [[round(a * b / total, 6) for b in one_d] for a in one_d]
require(weights[2][2] == 0.157207 and weights[0][0] == 0.002456 and weights[1][2] == 0.099992, 'normalised taps')
report['blend_kernel'] = dict(function='006bb2b0', one_dimensional=one_d, normalised_5x5=weights,
                              note='Same taps as the TerrainShaderScreen pass-1 vertex shader (centre 0.157207).')

# 3. Material table (0x4a8454..): each TerrainDef row becomes one material, or three (projection modes 0, 1, 2) when its
#    Projection column is 1; the row's first material index is stored next to the projection flag; at most 64 materials.
materials = texts(0x4a8463, 0x4a8512)
require(materials[:3] == ['mov ecx, dword ptr [esi + 0x1118]', 'mov dword ptr [edi + 0x100], ecx',
                          'mov ecx, dword ptr [esi + 0x1118]'] and 'cmp dword ptr [edi], edx' in materials and
        materials.count('cmp ecx, 0x40') == 4 and 'mov dword ptr [esi + ecx*4 + 0x1018], 2' in materials and
        materials.count('mov dword ptr [esi + ecx*4 + 0xf18], eax') == 4, 'row -> material expansion')
report['material_table'] = dict(listing=rows(0x4a8463, 0x4a8512),
                                rule='material -> (row, projection mode). Projection 0 rows: one material, mode 0. '
                                     'Projection 1 rows: three materials, modes 0, 1, 2. Row -> first material is kept.')

# 4. Per-chunk material choice (0x568430): histogram of texel materials over the chunk plus a 2-texel border, with the
#    projection variant picked from the terrain normal; keep the 8 most frequent.
chunk = texts(0x568430, 0x5687b0)
require(contains(chunk, ['mov edx, dword ptr [esi + ebx*4 + 0xc10]']) and 'comiss xmm0, dword ptr [0x9fcec8]' in chunk and
        abs(f32(0x9fcec8) - 0.9) < 1e-6 and contains(chunk, ['mov ebp, 8', 'cmp dword ptr [edi + 0x1f8], ebp']) and
        'mov dword ptr [edi + 0x1f8], ebp' in chunk and 'sub ebx, 2' in chunk and 'sub ebp, 2' in chunk,
        'chunk material histogram, 0.9 normal threshold, top 8')
report['chunk_materials'] = dict(function='00568430', rule='count materials over the chunk and a 2-texel border; sort by '
                                 'count (descending); keep at most 8 per chunk.')

# 5. Per-vertex weights (0x527720): convolve the one-hot material of the 25 neighbouring texels (wrapping) with the kernel.
weights_fn = texts(0x527720, 0x527953)
require(contains(weights_fn, ['mov ecx, dword ptr [esi + 0x13c]', 'movss xmm0, dword ptr [edi + ecx]', 'movzx edx, al',
                              'mov eax, dword ptr [ecx + edx*4 + 0xc10]', 'addss xmm0, dword ptr [ebp + eax*4]',
                              'movss dword ptr [ebp + eax*4], xmm0']) and
        contains(weights_fn, ['cmp dword ptr [ecx + eax*4 + 0xb10], 1', 'mov edx, dword ptr [ecx + eax*4 + 0xc10]']) and
        'div dword ptr [ecx + 0x1aa8]' in weights_fn and 'divss xmm1, xmm0' in weights_fn and
        weights_fn.count('call 0x517bf0') == 2, 'kernel convolution over the texel id map, normalised')
report['vertex_weights'] = dict(function='00527720', listing=rows(0x527720, 0x527953),
                                rule='w[m] = sum over 25 taps of K(dx,dy) * [material(id(x+dx, y+dy)) == m]; the id map '
                                     'holds TerrainDef row numbers; rows with Projection 1 use their mode-0/1/2 material '
                                     'chosen by the vertex; w is normalised to sum 1.')

# 6. Blend-mesh vertex writer (0x5ce920): one 48-byte vertex per texel of the chunk plus a 1-texel border.
writer = texts(0x5ce920, 0x5cf197)
require(contains(writer, ['comiss xmm0, dword ptr [0x9fcec8]', 'mov dword ptr [esp + 0x40], edx',
                          'mov dword ptr [esp + 0x3c], ecx', 'jbe 0x5ceb59', 'mov dword ptr [esp + 0x18], 0']) and 'mov dword ptr [esp + 0x18], 2' in writer and
        'cmp dword ptr [0xd90f24], 0' in writer and 'mov byte ptr [esi + 0x28], dl' in writer and
        abs(f64(0x9f9268) - 0.001) < 1e-12 and 'movss xmm0, dword ptr [0x9d9f84]' in writer and f32(0x9d9f84) == 255.0 and
        all(f'mov byte ptr [esi + {hex(0x20 + k)}], ' in ' '.join(writer) for k in range(16)),
        'projection from normal, weights x255 to bytes +0x20..0x27, material bytes +0x28..0x2f')
report['blend_mesh_vertex'] = dict(
    function='005ce920', stride_bytes=48,
    layout={'0x00': 'cache clip x, y and 0.5', '0x0c': 'texel x, y', '0x14': 'world x, y, height/255*scale',
            '0x20': '8 weights, byte = w*255 (TEXCOORD2/3)', '0x28': '8 material numbers (BLENDINDICES0/1)'},
    projection='normal.z > 0.9 -> 0; else |normal.y| > |normal.x| -> 1; else 2',
    fallback='if the chunk materials hold less than 0.001 of the weight, the first slot gets 1',
    advanced_gpu='With TerrainUseAdvancedGPU only byte +0x28 (the projection mode) is written; the vertex shader then '
                 'runs the same kernel on an id texture.')

# 7. Pass choice in the cache render (0x694a60): spec cache flag 0xd90f28 picks pass 0 (two targets) or pass 1/2;
#    TerrainUseAdvancedGPU (0xd90f24) picks pass 1 (GPU kernel) over pass 2 (CPU weights).
render = texts(0x6954d8, 0x695836)
require(contains(render, ['cmp dword ptr [0xd90f28], 0', 'push 0x4c', 'je 0x6956fe']) and
        contains(render, ['mov eax, dword ptr [edx + 0x59c]', 'je 0x6956e9', 'push 1']) and
        contains(render, ['push 2', 'push eax', 'push ecx', 'mov ecx, esi', 'call 0x8ccd80']) and
        contains(render, ['mov ecx, dword ptr [eax + 0x59c]', 'mov edx, dword ptr [esp + 0x28]', 'push 0']),
        'TerrainShaderScreen pass selection')
config = texts(0x5d8ef9, 0x5d8f1d)
require(config[-3:] == ['push 0xd90f24', 'push 0xa1b890', 'push 0xa1b8a8'] and cstr(0xa1b890) == 'TerrainUseAdvancedGPU' and
        cstr(0xa1b8a8) == 'GraphicsDetailSettings' and cstr(0xa1b848).startswith('Use more advanced GPU features'),
        'TerrainUseAdvancedGPU option')
require(cstr(0xa19a10) == 'HW/driver workaround: Disabling GPU terrain weight blending', 'driver workaround text')
report['pass_choice'] = dict(listing=rows(0x6954d8, 0x695836), option='GraphicsDetailSettings.TerrainUseAdvancedGPU',
                             rule='0xd90f28 == 0 -> pass 0; else TerrainUseAdvancedGPU -> pass 1, otherwise pass 2. '
                                  '0xd90f28 is set from TerrainDetailLevel in the settings apply function 0x453f80.')

# 8. Piece stamping into the texel map (0x463b10): id = T1 of the piece with the highest blend value; height is the
#    H_BLEND-weighted sum of the piece heights (16-bit / 65535 minus an offset).
stamp = texts(0x463d53, 0x463e61)
require(abs(f32(0x9f5c2c) - 1 / 65535) < 1e-11 and abs(f32(0x9f9e34) - 1 / 255) < 1e-9, 'stamp constants')
require(contains(stamp, ['mov dl, byte ptr [esp + ecx + 0x2060]', 'cmp dl, byte ptr [eax + 0xa]', 'jbe 0x463e1f',
                         'mov byte ptr [eax + 0xa], dl', 'mov dl, byte ptr [esp + ecx + 0x60]', 'mov byte ptr [eax + 9], dl']) and
        contains(stamp, ['movzx edx, byte ptr [esp + ecx + 0x1060]', 'movzx ecx, word ptr [esp + ecx*2 + 0x3060]',
                         'cvtsi2ss xmm3, ecx', 'mulss xmm3, xmm2', 'subss xmm3, dword ptr [edi + 0x7ec]', 'cvtsi2ss xmm0, edx',
                         'mulss xmm0, xmm1', 'mulss xmm3, xmm0', 'addss xmm3, dword ptr [eax]', 'movss dword ptr [eax], xmm3']),
        'id by maximum blend value, height accumulated by blend weight')
decode = texts(0x463cc5, 0x463d45)
require([t for t in decode if t.startswith('call')] == ['call 0x42e3a0', 'call 0x7940a0', 'call 0x7940a0', 'call 0x4bcd60'],
        'one 8-bit id image, two 8-bit blend images and one 16-bit height image per placed piece')
require(texts(0x42e420, 0x42e43b)[:2] == ['movzx edi, byte ptr [eax]', 'xor esi, esi'] and
        'mov ecx, dword ptr [esi + 0x80178]' in texts(0x42e404, 0x42e40d), 'u8 run-length row decoder over the library')
report['piece_stamping'] = dict(function='00463b10', listing=rows(0x463d53, 0x463e61),
                                rule='per texel: if blend8_a(p) > best: best = blend8_a(p), id = id8(p); '
                                     'heightSum += (h16(p)/65535 - offset) * blend8_b(p)/255; weightSum += blend8_b(p)/255.',
                                image_names='By role and by the record name order (_H, _T1, _H_BLEND, _T_BLEND): id8 = _T1, '
                                            'blend8_a = _T_BLEND, blend8_b = _H_BLEND, h16 = _H (inferred from use).')

# 9. Other textures named in the plan.
layout_ref = texts(0x663fc0, 0x663fd6)
require(cstr(0xa3898c) == 'assets\\LayoutSystem\\TF_BLEND.dds' and any('0xa3898c' in t for t in layout_ref) and
        cstr(0xa389b0) == 'DF_flat' and cstr(0xa389bc) == '_A1.dds', 'TF_BLEND belongs to the LayoutSystem')
require(img.lower().find(b'hexgridid') == -1 and img.lower().find('hexgridid'.encode('utf-16-le')) == -1,
        'hexgridid is not named in the EXE')
report['other_textures'] = dict(tf_blend='Loaded by the LayoutSystem (0x663fc0) next to DF_flat and _A1.._A8 decals; '
                                          'not part of the terrain material blend.',
                                hexgridid='Not named anywhere in the EXE (ASCII or UTF-16).')
report['interpretation'] = dict(
    proven=['BaseDominance is read from TerrainDef.csv and discarded.',
            'The texel id map holds TerrainDef row numbers; materials are rows, tripled for Projection 1 rows.',
            'Per-vertex weights are a normalised 5x5 kernel (0.125, 0.636056, 1, ...) over the one-hot texel materials.',
            'Each 64-texel chunk keeps its 8 most frequent materials; vertices store 8 weight bytes and 8 material bytes.',
            'Placed pieces write the id of the piece with the highest blend value and a blend-weighted height.'],
    not_proven=['How HexPatternMatcher chooses and places pieces (the 10 x 10 cell patterns).',
                'Which TerrainDef.csv copy the virtual file system returns for assets\\terrain\\TerrainTextures\\TerrainDef.csv.',
                'The TerrainDetailLevel values that turn the spec cache (0xd90f28) on.'])
with open(out, 'w', encoding='utf8', newline='\n') as stream:
    json.dump(report, stream, indent=1)
    stream.write('\n')
print(json.dumps(dict(status='PASS_RETAIL_TERRAIN_BLEND_CPU_STATIC_PROBE', exe_sha256=sha, out=out)))
