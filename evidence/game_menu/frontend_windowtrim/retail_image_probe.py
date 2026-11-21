"""Static, non-executing probe of the retail Civ V DX11 ForgeUI Image control texture mapping.

Question: how does an <Image Size="W,H" Texture="..."/> with no StretchMode map its texture when
Size differs from the texture (WindowTrimLeft/Right: Size 82,396 against the active 98x394 image)?

The EXE is parsed as data (pefile) and disassembled (capstone); nothing is loaded or executed.
usage: python -I retail_image_probe.py CivilizationV_DX11.exe OUT.json
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


def u32(va):
    return struct.unpack('<I', img[va - base:va - base + 4])[0]


def f32(va):
    return struct.unpack('<f', img[va - base:va - base + 4])[0]


def cstr(va):
    return img[va - base:img.index(b'\0', va - base)].decode('ascii')


def listing(start, stop):
    return [dict(va=f'{i.address:08x}', text=f'{i.mnemonic} {i.op_str}'.strip())
            for i in md.disasm(img[start - base:stop - base], start)]


def texts(rows):
    return [row['text'] for row in rows]


def require(condition, message):
    if not condition:
        raise SystemExit('Pinned retail evidence no longer matches: ' + message)


report = dict(schema='zerosis.retail_image_probe.v1', exe=dict(name='CivilizationV_DX11.exe', bytes=len(raw), sha256=sha),
              tool=dict(pefile=pefile.__version__, capstone=capstone.__version__), executed=False,
              method='PE parse plus linear x86 disassembly of pinned functions; no code was loaded or run.')

# 0. The XML tag "Image" creates this class: tag dispatch -> factory 0x72eb80 -> constructor 0x503430.
VTABLE = 0xa4e658
dispatch = listing(0x6cf02c, 0x6cf046)
require(cstr(0xa4249c) == 'Image' and texts(dispatch)[:5] == ['push 0xa4249c', 'mov ecx, esi', 'call 0x76b1c0', 'test al, al',
        'je 0x6cf046'] and texts(dispatch)[5] == 'call 0x72eb80', 'XML tag "Image" dispatches to factory 0x72eb80')
factory = listing(0x72eb80, 0x72ebcb)
require('push 0xf0' in texts(factory) and 'jmp 0x503430' in texts(factory), 'factory allocates 0xf0 bytes and runs the Image constructor')

# 1. Image XML attribute reader (vtable slot 17 of the Image control class).
require(u32(VTABLE + 17 * 4) == 0x58b190, 'Image vtable slot 17 is the XML attribute reader')
reader = listing(0x58b190, 0x58b37f)
rt = texts(reader)
for name, va in (('Texture', 0xa4de0c), ('TextureOffset', 0xa4de14), ('MaskTexture', 0xa4dcbc), ('StretchMode', 0xa4de24),
                 ('None', 0xa4de30), ('Uniform', 0xa4de38), ('Fill', 0xa4de40), ('UniformToFill', 0xa4de48),
                 ('Sampler', 0xa4de58), ('Linear', 0xa4de60)):
    require(cstr(va) == name and f'push 0x{va:x}' in rt, 'reader references ' + name)
require('mov dword ptr [esi + 0xc8], eax' in rt and 'lea edx, [esi + 0xb8]' in rt, 'Texture -> +0xc8, TextureOffset -> +0xb8')
for value in (1, 2, 3, 4):
    require(f'mov dword ptr [esi + 0xe4], {value}' in rt, 'StretchMode enum value %d' % value)
require('or dword ptr [esi + 0x40], 0x400000' in rt, 'Sampler="Linear" sets control flag 0x400000')
require('fild dword ptr [eax + 0x118]' in rt and 'fstp dword ptr [esi + 0xe8]' in rt and
        'fild dword ptr [eax + 0x114]' in rt and 'fstp dword ptr [esi + 0xec]' in rt, 'texture width/height cached as floats')
require(rt[-1] == 'call 0x6fcea0', 'reader then runs the base control reader')

# 2. Base control reader: Size -> +0x30/+0x34.
base_reader = listing(0x6fcefd, 0x6fcf22)
bt = texts(base_reader)
require(cstr(0xa49a98) == 'Size' and bt[0] == 'push 0xa49a98' and 'lea eax, [esi + 0x30]' in bt and 'call 0x41ec30' in bt,
        'Size is parsed into the base control +0x30/+0x34 pair')

# 3. Constructors: StretchMode default and sampler default.
ctor = listing(0x503430, 0x503457)
ct = texts(ctor)
require('mov dword ptr [esi], 0xa4e658' in ct and 'mov dword ptr [esi + 0xe4], 0' in ct and 'call 0x502a20' in ct,
        'Image constructor sets StretchMode=0 and builds the quad member at +0x84')
quad_ctor = listing(0x502a20, 0x502a8f)
qt = texts(quad_ctor)
require('mov dword ptr [eax], 0x9e0c48' in qt and 'mov dword ptr [eax + 0x3c], 0xa' in qt, 'quad default sampler index 10')

# 4. Layout (vtable slot 4): StretchMode 0 copies the control Size into the quad draw and texture-region sizes.
require(u32(VTABLE + 4 * 4) == 0x41bf50, 'Image vtable slot 4 is the layout update')
layout = listing(0x41bf50, 0x41bfc0)
lt = texts(layout)
require(lt[3:6] == ['test dword ptr [esi + 0x40], 0x400000', 'je 0x41bf6b', 'mov dword ptr [esi + 0xc0], 5'],
        'Linear sampler flag selects sampler index 5')
require(lt[6:8] == ['cmp dword ptr [esi + 0xe4], 0', 'jne 0x41bf98'], 'StretchMode 0 branch')
for line in ('mov eax, dword ptr [esi + 0x30]', 'mov ecx, dword ptr [esi + 0x34]', 'mov dword ptr [esi + 0xa8], eax',
             'mov dword ptr [esi + 0xac], ecx', 'mov dword ptr [esi + 0xb0], edx', 'mov dword ptr [esi + 0xb4], eax'):
    require(line in lt, 'StretchMode 0 copies Size: ' + line)
require('call 0x666030' in lt, 'other StretchMode values use the fit routine')

# 5. Quad UV update (quad vtable slot 0 -> 0x562900).
require(u32(0x9e0c48) == 0x736990 and texts(listing(0x736990, 0x736995)) == ['jmp 0x562900'], 'quad slot 0 forwards to UV update')
uv = listing(0x562900, 0x56297f)
ut = texts(uv)
expected = ['fild dword ptr [eax + 0x114]', 'fdivr dword ptr [ecx + 0x38]', 'fild dword ptr [esp]', 'fdivr dword ptr [ecx + 0x34]',
            'fstp dword ptr [ecx + 0x58]', 'fstp dword ptr [ecx + 0x5c]', 'fdivr dword ptr [ecx + 0x30]', 'fdivr dword ptr [ecx + 0x2c]',
            'fstp dword ptr [ecx + 0x50]', 'fstp dword ptr [ecx + 0x54]', 'mov eax, dword ptr [eax + 0x118]']
for line in expected:
    require(line in ut, 'UV update instruction ' + line)

# 6. Quad submit (slot 1) passes the UV constants and sampler index to the batch.
submit = listing(0x6ffb70, 0x6ffe83)
st = texts(submit)
for line in ('fld dword ptr [edi + 0x50]', 'movss xmm0, dword ptr [edi + 0x54]', 'movss xmm1, dword ptr [edi + 0x58]',
             'movss xmm2, dword ptr [edi + 0x5c]', 'mov edx, dword ptr [edi + 0x3c]', 'call 0x631780'):
    require(line in st, 'submit uses ' + line)

report['image_control'] = dict(
    vtable=f'{VTABLE:08x}', xml_tag_dispatch=dict(listing=dispatch), factory=dict(function='0072eb80', listing=factory),
    xml_reader=dict(function='0058b190', listing=reader),
    base_size_reader=dict(listing=base_reader),
    constructor=dict(function='00503430', listing=ctor), quad_constructor=dict(function='00502a20', listing=quad_ctor),
    layout=dict(function='0041bf50', listing=layout), uv_update=dict(function='00562900', listing=uv),
    submit=dict(function='006ffb70', key_lines=[l for l in submit if l['text'] in (
        'fld dword ptr [edi + 0x50]', 'movss xmm0, dword ptr [edi + 0x54]', 'movss xmm1, dword ptr [edi + 0x58]',
        'movss xmm2, dword ptr [edi + 0x5c]', 'mov edx, dword ptr [edi + 0x3c]', 'call 0x631780')]),
    fields={'+0x30/+0x34': 'control Size (w,h)', '+0xb8/+0xbc': 'TextureOffset (x,y)', '+0xc8': 'Texture',
            '+0xe4': 'StretchMode (0 default, None=1, Uniform=2, Fill=3, UniformToFill=4)',
            '+0xe8/+0xec': 'texture width/height (texture object +0x118/+0x114)', '+0xc0': 'sampler index (default 10, Linear 5)',
            'quad +0x24/+0x28 (+0xa8/+0xac)': 'drawn size', 'quad +0x2c/+0x30 (+0xb0/+0xb4)': 'texture region size'},
    semantics=dict(
        default_stretch_mode='No StretchMode attribute leaves 0, which copies Size into both the drawn size and the sampled texture region.',
        uv='u0 = TextureOffset.x / texture width, v0 = TextureOffset.y / texture height, du = Size.w / texture width, dv = Size.h / texture height.',
        consequence='A default Image samples Size pixels from TextureOffset at 1:1. It never rescales the whole texture into Size.',
        sampler='Without Sampler="Linear" the quad keeps sampler index 10; "Linear" selects index 5.',
        unresolved='The runtime sampler address mode for texture coordinates beyond 1.0, and the FTXT tile-index shader path for them, are not established by this probe.'))
report['windowtrim'] = dict(
    xml='Assets/DLC/Expansion/UI/FrontEnd SinglePlayer/OtherMenu/MultiplayerSelect/Mods*: <Image Size="82,396" Texture=".../WindowTrimLeft|Right.dds"/>, no TextureOffset/StretchMode/Sampler.',
    applied='With the active 98x394 image: u spans 0..82/98 and v spans 0..396/394. Columns 0..81 and rows 0..393 map 1:1; texture columns 82..97 are not drawn; the bottom 2 drawn rows read beyond the image.')
with open(out, 'w', encoding='utf8', newline='\n') as stream:
    json.dump(report, stream, indent=1)
    stream.write('\n')
print(json.dumps(dict(status='PASS_RETAIL_IMAGE_STATIC_PROBE', exe_sha256=sha, out=out)))
