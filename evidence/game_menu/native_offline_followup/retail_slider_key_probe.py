"""Static, non-executing probe of the retail Civ V DX11 ForgeUI Slider keyboard path.

Question: which window messages and keys move a retail <Slider>, by how much, and in which direction?
The front-end options volume slider (OptionsMenu.xml EffectsVolumeSlider, WheelSteps="1") is compared with it.

The EXE is parsed as data (pefile) and disassembled (capstone); nothing is loaded or executed.
usage: python -I retail_slider_key_probe.py CivilizationV_DX11.exe OUT.json
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


def listing(start, stop):
    return [dict(va=f'{i.address:08x}', text=f'{i.mnemonic} {i.op_str}'.strip())
            for i in md.disasm(img[start - base:stop - base], start)]


def texts(rows):
    return [row['text'] for row in rows]


def require(condition, message):
    if not condition:
        raise SystemExit('Pinned retail evidence no longer matches: ' + message)


report = dict(schema='zerosis.retail_slider_key_probe.v1', exe=dict(name='CivilizationV_DX11.exe', bytes=len(raw), sha256=sha),
              tool=dict(pefile=pefile.__version__, capstone=capstone.__version__), executed=False,
              method='PE parse plus linear x86 disassembly of the pinned slider message handler; no code was loaded or run.')

VTABLE = 0xa52110
require(u32(VTABLE + 5 * 4) == 0x5e03e0, 'slider vtable slot 5 is the slider message handler')
require(f32(0x9e7230) == 100.0 and f32(0x9f72f4) == 1.0, 'step constants 100.0 and 1.0')

# 1. Message routing: only WM_KEYUP (0x101) enters the key branch; WM_KEYDOWN (0x100) and every other message
#    below WM_MOUSEMOVE leave through the generic exit at 0x5e0616.
route = listing(0x5e047a, 0x5e04bf)
rt = texts(route)
require(rt[2:7] == ['cmp ebp, 0x200', 'ja 0x5e053d', 'je 0x5e055a', 'cmp ebp, 0x101', 'jne 0x5e0616'],
        'messages up to WM_MOUSEMOVE: only WM_KEYUP reaches the key branch')
require(rt[7:9] == ['test eax, 0x10000', 'je 0x5e0616'], 'key branch requires the same control state bit 0x10000 as the wheel')
require(rt[9:14] == ['mov eax, dword ptr [esp + 0x20]', 'add eax, -0x25', 'cmp eax, 3', 'ja 0x5e0616',
                     'jmp dword ptr [eax*4 + 0x5e08a8]'], 'only virtual keys 0x25..0x28 are dispatched')
table = [u32(0x5e08a8 + 4 * i) for i in range(4)]
require(table == [0x5e04bf, 0x5e04bf, 0x5e0500, 0x5e0500], 'VK_LEFT/VK_UP share one target, VK_RIGHT/VK_DOWN the other')

# 2. Subtract and add targets: one float32 step of 1/(100/WheelSteps), stored through the clamp-and-notify setter.
minus = listing(0x5e04bf, 0x5e0500)
plus = listing(0x5e0500, 0x5e053d)
mt, pt = texts(minus), texts(plus)
for rows in (mt, pt):
    require(rows[0:2] == ['movss xmm0, dword ptr [0x9e7230]', 'divss xmm0, dword ptr [esi + 0x628]'], 'divisor 100/WheelSteps')
    require('movss xmm1, dword ptr [0x9f72f4]' in rows and ('divss xmm1, xmm0' in rows), 'step = 1/(100/WheelSteps)')
    require('call 0x481330' in rows and 'mov al, 1' in rows, 'clamp-and-notify setter then handled=true')
require('subss xmm0, xmm1' in mt and 'movss xmm0, dword ptr [esi + 0x128]' in mt, 'VK_LEFT/VK_UP: value - step')
require('addss xmm1, dword ptr [esi + 0x128]' in pt, 'VK_RIGHT/VK_DOWN: value + step')
require(not any('GetKeyState' in t or 'GetAsyncKeyState' in t for t in mt + pt) and
        not any(t.startswith('cmp') for t in mt + pt), 'no modifier query or further key test inside either step target')

report['slider_key_path'] = dict(
    handler=dict(vtable=f'{VTABLE:08x}', slot=5, function='005e03e0'),
    routing=dict(listing=route), jump_table=dict(address='005e08a8', targets=[f'{va:08x}' for va in table]),
    subtract=dict(listing=minus), add=dict(listing=plus),
    semantics=dict(
        message='WM_KEYUP (0x101) only; WM_KEYDOWN and its auto-repeat do not move a retail slider.',
        keys='VK_LEFT (0x25) and VK_UP (0x26) subtract one step; VK_RIGHT (0x27) and VK_DOWN (0x28) add one step; '
             'no other virtual key (Home, End, Page Up/Down) is handled and no modifier changes the step.',
        step='float32 1.0f / (100.0f / WheelSteps), the same step as one wheel message.',
        clamp='The shared setter 0x481330 clamps to [0,1] and notifies the registered callback.',
        gate='Control state bit 0x10000 is required for keys exactly as for the wheel; its meaning is not established here.'))
report['options_volume_application'] = dict(
    source='Assets/UI/Options/OptionsMenu.xml EffectsVolumeSlider WheelSteps="1"',
    step='0.01 of the normalized value per key release, i.e. one percent of uiCueVolumePercent',
    direction='Left and Up lower the volume; Right and Down raise it.')
with open(out, 'w', encoding='utf8', newline='\n') as stream:
    json.dump(report, stream, indent=1)
    stream.write('\n')
print(json.dumps(dict(status='PASS_RETAIL_SLIDER_KEY_STATIC_PROBE', exe_sha256=sha, out=out)))
