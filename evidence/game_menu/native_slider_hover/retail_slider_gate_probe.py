"""Static, non-executing probe: what is the retail ForgeUI control state bit 0x10000 that gates Slider keys and wheel?
Also pins Locale.ToPercent, which formats the options volume labels.

The EXE is parsed as data (pefile) and disassembled (capstone); nothing is loaded or executed.
usage: python -I retail_slider_gate_probe.py CivilizationV_DX11.exe OUT.json
"""
import hashlib, json, re, struct, sys
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
text = next(s for s in pe.sections if s.Name.rstrip(b'\0') == b'.text')
t0, t1 = text.VirtualAddress, text.VirtualAddress + text.Misc_VirtualSize


def u32(va):
    return struct.unpack('<I', img[va - base:va - base + 4])[0]


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


def immediate_sites(pattern, mnemonic, operand):
    """Every exact instruction in .text that applies `operand` to [reg + 0x40]."""
    sites = set()
    for match in re.finditer(re.escape(pattern), img[t0:t1]):
        end = t0 + match.end()
        for length in range(6, 11):
            start = end - length
            try:
                ins = next(md.disasm(img[start:end], base + start))
            except StopIteration:
                continue
            if ins.size == length and ins.mnemonic == mnemonic and operand in ins.op_str and '+ 0x40]' in ins.op_str:
                sites.add(ins.address)
    return sorted(sites)


report = dict(schema='zerosis.retail_slider_gate_probe.v1', exe=dict(name='CivilizationV_DX11.exe', bytes=len(raw), sha256=sha),
              tool=dict(pefile=pefile.__version__, capstone=capstone.__version__), executed=False,
              method='PE parse, byte-pattern search of .text and linear x86 disassembly of pinned functions; no code was loaded or run.')

# 1. Exactly one instruction in .text sets the control state bit 0x10000 in memory and exactly one clears it.
set_sites = immediate_sites(b'\x00\x00\x01\x00', 'or', '0x10000')
clear_sites = immediate_sites(b'\xff\xff\xfe\xff', 'and', '0xfffeffff')
require(set_sites == [0x5f2550] and clear_sites == [0x6d3680], 'single set/clear instruction for state bit 0x10000')
setter, clearer = listing(0x5f2550, 0x5f2568), listing(0x6d3680, 0x6d3698)
require(texts(setter) == ['or dword ptr [ecx + 0x40], 0x10000', 'test dword ptr [ecx + 0x40], 0x20000', 'jne 0x5f2567',
                          'push 1', 'call 0x409420', 'ret'], 'bit setter body')
require(texts(clearer) == ['and dword ptr [ecx + 0x40], 0xfffeffff', 'test dword ptr [ecx + 0x40], 0x20000', 'jne 0x6d3697',
                           'push 0', 'call 0x409420', 'ret'], 'bit clearer body')

# 2. They are the base implementations of virtual slots 35/36 (pointer enter/exit). Image (0xa4e658) uses them as is;
#    Slider (0xa52110) overrides both with the button-style routines 0x7641d0/0x6359b0, which end in the base routines.
require(u32(0xa4e658 + 35 * 4) == 0x5f2550 and u32(0xa4e658 + 36 * 4) == 0x6d3680, 'Image vtable slots 35/36 are the base routines')
require(u32(0xa52110 + 35 * 4) == 0x7641d0 and u32(0xa52110 + 36 * 4) == 0x6359b0, 'Slider vtable slots 35/36 are the overrides')
slider_enter = listing(0x7641d0, 0x76427c)
require(texts(slider_enter)[:3] == ['push esi', 'mov esi, ecx', 'mov eax, dword ptr [esi + 0x40]'] and
        texts(slider_enter)[-1] == 'jmp 0x5f2550', 'Slider enter override starts at 0x7641d0 and tail-calls the base setter')

# 3. The only direct transfers into them are the tails of the mouse-enter and mouse-exit routines, which first fire the
#    registered Lua mouse callbacks 5 and 6 through the callback dispatcher 0x6e3030.
def transfers(target):
    found = []
    for offset in range(t0, t1 - 5):
        if img[offset] in (0xe8, 0xe9) and offset + 5 + struct.unpack('<i', img[offset + 1:offset + 5])[0] == target - base:
            found.append(base + offset)
    return found


require(transfers(0x5f2550) == [0x764277] and transfers(0x6d3680) == [0x6359d4, 0x6359e9], 'only mouse enter/exit tails reach the slots')
enter, leave = listing(0x76426b, 0x76427c), listing(0x6359b0, 0x6359ee)
require(texts(enter) == ['push 5', 'mov ecx, esi', 'call 0x6e3030', 'mov ecx, esi', 'pop esi', 'jmp 0x5f2550'],
        'mouse enter fires callback 5 then sets the bit')
lt = texts(leave)
require(lt.count('push 6') == 2 and lt.count('call 0x6e3030') == 2 and lt.count('jmp 0x6d3680') == 2,
        'mouse exit fires callback 6 then clears the bit on both visual-state paths')
dispatch = listing(0x6e3030, 0x6e3077)
require(texts(dispatch)[5:9] == ['cmp edi, 7', 'jbe 0x6e3045', 'mov edi, 7', 'cmp dword ptr [esi + edi*8 + 0xbc], 0'],
        'callback dispatcher indexes the registered mouse callbacks')

# 4. The Lua Mouse table names those callback indices: eMouseEnter=5, eMouseExit=6.
names = {}
for name_va in (0xa71658, 0xa71664):
    site = img.find(b'\x68' + struct.pack('<I', name_va), t0, t1)
    require(site != -1, 'Mouse enum name is pushed')
    rows = texts(listing(base + site - 8, base + site + 5))
    require(len(rows) == 4 and rows[0].startswith('push ') and rows[1:] == ['push esi', 'call 0x923940', f'push 0x{name_va:x}'],
            'value pushed with lua_pushinteger before the Mouse enum name')
    names[cstr(name_va)] = int(rows[0].split()[-1], 0)
require(names == {'eMouseEnter': 5, 'eMouseExit': 6}, 'Mouse.eMouseEnter/eMouseExit values')

# 5. Locale.ToPercent: String("{1: percent}") with PushArgument(double) of the Lua number.
percent = listing(0x5f7640, 0x5f76b7)
pt = texts(percent)
require(cstr(0xa697c0) == 'ToPercent' and img.find(b'\x68' + struct.pack('<I', 0xa697c0), t0, t1) == 0x731af7 - base,
        'ToPercent registration')
require(texts(listing(0x731ae9, 0x731aee)) == ['push 0x5f7640'], 'ToPercent binds 0x5f7640')
require(cstr(0xa699f0) == '{1: percent}' and pt[0] == 'mov eax, 0xa699f0' and 'call dword ptr [0x9d6168]' in pt and
        'fstp qword ptr [esp]' in pt, 'ToPercent formats one double with the percent style')

report['state_bit_0x10000'] = dict(
    setter=dict(function='005f2550', vtable_slot=35, listing=setter),
    clearer=dict(function='006d3680', vtable_slot=36, listing=clearer),
    only_transfers=dict(setter=['00764277'], clearer=['006359d4', '006359e9']),
    slider_overrides=dict(vtable='00a52110', enter='007641d0', exit='006359b0', enter_listing=slider_enter),
    mouse_enter_tail=dict(listing=enter), mouse_exit=dict(function='006359b0', listing=leave),
    callback_dispatcher=dict(function='006e3030', listing=dispatch), lua_mouse_enum=names,
    meaning='Pointer-over (hover): set after Mouse.eMouseEnter (5) fires and cleared after Mouse.eMouseExit (6) fires.',
    consequence='Retail Slider keys (WM_KEYUP arrows) and wheel move a slider only while the pointer is over it. '
                'Keyboard focus is not part of the gate.',
    not_traced='The UI manager path that delivers WM_KEYUP to controls is not traced; hover is proven necessary, not sufficient.')
report['locale_to_percent'] = dict(
    function='005f7640', listing=percent, template='{1: percent}', argument='PushArgument(double)',
    consequence='Options volume labels format the stored normalized float with the ICU percent style of the current language.')
with open(out, 'w', encoding='utf8', newline='\n') as stream:
    json.dump(report, stream, indent=1)
    stream.write('\n')
print(json.dumps(dict(status='PASS_RETAIL_SLIDER_GATE_STATIC_PROBE', exe_sha256=sha, out=out, mouse=names)))
