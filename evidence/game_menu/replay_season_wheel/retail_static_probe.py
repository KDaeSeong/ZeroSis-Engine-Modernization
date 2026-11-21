"""Static, non-executing probe of the retail Civ V DX11 EXE for two replay-viewer fidelity questions.

1. Lua Locale.Lookup / Locale.ConvertTextKey: what reaches the caller for a missing text key?
2. Slider WheelSteps: fraction and direction of one WM_MOUSEWHEEL message.

The EXE is parsed as data (pefile) and disassembled (capstone); nothing is loaded or executed.
Every address below is pinned to the EXE SHA-256 and re-verified from the bytes on each run.

usage: python -I retail_static_probe.py CivilizationV_DX11.exe OUT.json
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
imports = {}
for entry in pe.DIRECTORY_ENTRY_IMPORT:
    # pefile reports names with spaces (CvLocalizationWin32Final Release.dll) as *invalid*; read the raw name.
    dll = pe.get_string_at_rva(entry.struct.Name).decode('ascii')
    for imp in entry.imports:
        imports[imp.address] = (dll, (imp.name or b'').decode())


def u32(va):
    return struct.unpack('<I', img[va - base:va - base + 4])[0]


def f32(va):
    return struct.unpack('<f', img[va - base:va - base + 4])[0]


def cstr(va):
    return img[va - base:img.index(b'\0', va - base)].decode('ascii')


def thunk(va):
    ins = next(md.disasm(img[va - base:va - base + 8], va))
    if ins.mnemonic == 'jmp' and ins.op_str.startswith('dword ptr [0x'):
        return imports.get(int(ins.op_str[13:-1], 16))
    return None


def listing(start, stop):
    rows = []
    for ins in md.disasm(img[start - base:stop - base], start):
        note = None
        if ins.op_str.startswith('dword ptr [0x') and ins.mnemonic in ('call', 'mov'):
            note = imports.get(int(ins.op_str.split('[0x')[1].rstrip(']'), 16))
        elif ins.mnemonic == 'call' and ins.op_str.startswith('0x'):
            note = thunk(int(ins.op_str, 16))
        rows.append(dict(va=f'{ins.address:08x}', text=f'{ins.mnemonic} {ins.op_str}'.strip(),
                         **({'import': '!'.join(note)} if note else {})))
    return rows


def require(condition, message):
    if not condition:
        raise SystemExit('Pinned retail evidence no longer matches: ' + message)


def registration(name_va):
    """The Locale table is filled by lua_pushcclosure(L, fn, 0); lua_setfield(L, -2, name)."""
    code = b'\x68' + struct.pack('<I', name_va) + b'\x6a\xfe\x56\xe8'
    at = img.find(code)
    require(at > 0 and img.find(code, at + 1) < 0, 'unique Locale field registration')
    va = base + at
    prev = list(md.disasm(img[va - 13 - base:va - base], va - 13))
    require([i.mnemonic for i in prev] == ['push', 'push', 'push', 'call'] and prev[0].op_str == '0',
            'pushcclosure(L, fn, 0) precedes setfield')
    require(thunk(int(prev[3].op_str, 16)) == ('lua51_Win32.dll', 'lua_pushcclosure'), 'pushcclosure import')
    require(thunk(int(next(md.disasm(img[va + 8 - base:va + 13 - base], va + 8)).op_str, 16)) ==
            ('lua51_Win32.dll', 'lua_setfield'), 'setfield import')
    return int(prev[1].op_str, 16), f'{va:08x}'


report = dict(schema='zerosis.retail_static_probe.v1', exe=dict(name='CivilizationV_DX11.exe', bytes=len(raw), sha256=sha),
              tool=dict(pefile=pefile.__version__, capstone=capstone.__version__),
              executed=False, method='PE parse plus linear x86 disassembly of pinned functions; no code was loaded or run.')

# --- 1. Locale ---------------------------------------------------------------------------------------------------
locale = {}
for name, va in (('Lookup', 0xa6973c), ('ConvertTextKey', 0xa69714), ('HasTextKey', 0xa69614)):
    require(cstr(va) == name, 'Locale name string ' + name)
    fn, at = registration(va)
    locale[name] = dict(name_va=f'{va:08x}', setfield_site=at, function=f'{fn:08x}')
for name in ('Lookup', 'ConvertTextKey'):
    fn = int(locale[name]['function'], 16)
    body = listing(fn, fn + 0x102)
    end = next(i for i, row in enumerate(body) if row['text'] == 'ret')
    body = body[:end + 1]
    called = [row.get('import', '') for row in body]
    require(any(c.endswith('?Lookup@Localization@@YA?AVString@1@PBD@Z') for c in called), name + ' calls Localization::Lookup')
    require(not any('HasKey' in c or 'TryLookup' in c for c in called), name + ' has no presence test')
    require(any(c.endswith('lua_pushlstring') for c in called), name + ' pushes the composed string')
    require(any('toUTF8' in c for c in called), name + ' returns String::toUTF8')
    locale[name]['listing'] = body
    locale[name]['finding'] = ('luaL_checklstring(1) -> Localization::Lookup(key); pushes later arguments '
                               '(boolean->PushArgument(int), number->PushArgument(double), string->PushArgument(const char*)); '
                               'returns String::toUTF8 via lua_pushlstring. No HasKey/TryLookup and no substitute text.')
loc_imports = sorted(n for d, n in imports.values() if d.startswith('CvLocalization'))
require('?Lookup@Localization@@YA?AVString@1@PBD@Z' in loc_imports and
        not any('TryLookup' in n for n in loc_imports), 'EXE localization import set')
report['locale'] = dict(functions=locale, localization_imports_with_lookup_or_key=[n for n in loc_imports if 'Lookup' in n or 'HasKey' in n],
    conclusion='A missing key yields exactly what Localization::Lookup returns. The project reference trace of the original '
               'localization component (evidence/localization/reference/basic.log line 11) returns the key text itself '
               '(TXT_MISSING) for a missing key, so stock ReplayViewer/GameCalendarUtilities show the raw Description key.')

# --- 2. Slider WheelSteps ----------------------------------------------------------------------------------------
require(cstr(0xa51b5c) == 'WheelSteps', 'WheelSteps attribute name')
parse = listing(0x732dcd, 0x732de2)
require(parse[0]['text'] == 'push 0xa' and parse[1]['text'] == 'push 0xa51b5c' and
        parse[2]['text'] == 'lea ecx, [esi + 0x628]', 'WheelSteps parsed into slider field +0x628')
vtable = 0xa52110
require(u32(vtable + 17 * 4) == 0x732d90, 'slider vtable slot 17 is the XML attribute reader')
require(u32(vtable + 5 * 4) == 0x5e03e0, 'slider vtable slot 5 is the slider message handler')
require(f32(0x9e7230) == 100.0 and f32(0x9f72f4) == 1.0, 'step constants 100.0 and 1.0')
dispatch_index = img[0x5e08cc - base + (0x20a - 0x201)]
require(dispatch_index == 2 and u32(0x5e08b8 + 4 * dispatch_index) == 0x5e0832, 'WM_MOUSEWHEEL -> 0x5e0832')
wheel = listing(0x5e0832, 0x5e08a8)
texts = [row['text'] for row in wheel]
require(texts[:2] == ['test eax, 0x10000', 'je 0x5e0616'], 'wheel requires control state bit 0x10000')
require('shr ecx, 0x10' in texts and 'test cx, cx' in texts and 'jle 0x5e088a' in texts, 'HIWORD sign test')
require('divss xmm0, dword ptr [esi + 0x628]' in texts and 'divss xmm1, xmm0' in texts, 'step = 1/(100/WheelSteps)')
require('subss xmm0, xmm1' in texts and 'addss xmm1, dword ptr [esi + 0x128]' in texts, 'positive delta subtracts')
store = listing(0x7af7c0, 0x7af7f9)
store_text = [row['text'] for row in store]
require('xorps xmm0, xmm0' in store_text and 'movss xmm0, dword ptr [0x9f72f4]' in store_text and
        'movss dword ptr [esi + 0x128], xmm0' in store_text, 'value store clamps to [0,1]')
setter = listing(0x481330, 0x4813c2)
require(setter[7]['text'] == 'call 0x7af7c0' and any(r['text'] == 'call edx' for r in setter), 'setter stores then notifies')
keys = [u32(0x5e08a8 + 4 * i) for i in range(4)]
require(keys == [0x5e04bf, 0x5e04bf, 0x5e0500, 0x5e0500], 'VK_LEFT/UP subtract, VK_RIGHT/DOWN add on WM_KEYUP')
text_section = next(s for s in pe.sections if s.Name.rstrip(b'\0') == b'.text')
t0, t1 = text_section.VirtualAddress, text_section.VirtualAddress + text_section.Misc_VirtualSize
notify_calls = [base + o for o in range(t0, t1 - 4) if img[o] == 0xe8 and
                o + 5 + struct.unpack('<i', img[o + 1:o + 5])[0] == 0x481330 - base]
notify_absolute = [base + o for o in range(len(img) - 3) if img[o:o + 4] == struct.pack('<I', 0x481330)]
require(len(notify_calls) == 7 and all(0x5e03e0 <= va < 0x5e08a8 for va in notify_calls) and notify_absolute == [0x48980b],
        'store-and-notify routine is reached only from the slider handler and one Lua method binding')


def lua_method(name_va, push_site, function):
    """Lua method tables bind 'push "Class::Method"; push fn; call 0x87c130'."""
    rows = list(md.disasm(img[push_site - base:push_site + 15 - base], push_site))[:3]
    require([r.mnemonic for r in rows] == ['push', 'push', 'call'] and int(rows[0].op_str, 16) == name_va and
            int(rows[1].op_str, 16) == function and rows[2].op_str == '0x87c130', 'Lua method binding ' + cstr(name_va))
    return dict(method=cstr(name_va), binding_site=f'{push_site:08x}', function=f'{function:08x}')


methods = [lua_method(0xa51d78, 0x48e925, 0x7af7c0), lua_method(0xa51da8, 0x489805, 0x481330)]
require([m['method'] for m in methods] == ['SliderControl::SetValue', 'SliderControl::SetAndCall'], 'slider Lua method names')
report['slider_wheel'] = dict(
    attribute=dict(name='WheelSteps', field='+0x628 (float)', parse_listing=parse),
    handler=dict(vtable=f'{vtable:08x}', slot=5, function='005e03e0', wm_mousewheel_case='005e0832', listing=wheel),
    value_store=dict(function='007af7c0', listing=store,
                     clamp='if (0.0f > v) v = +0.0f; else if (v > 1.0f) v = 1.0f (comiss; NaN passes unchanged)'),
    setter_and_callback=dict(function='00481330', listing=setter,
                             direct_call_sites=[f'{va:08x}' for va in notify_calls], absolute_references=['0048980b'],
                             finding='The store-and-notify routine is reached from the slider message handler and '
                                     'from the Lua method SliderControl::SetAndCall only.'),
    lua_methods=dict(rows=methods,
                     finding='Lua SliderControl::SetValue binds the clamp-and-store routine without callback notification; '
                             'ReplayViewer.lua re-seeds TurnSlider with SetValue, so a redraw does not re-enter '
                             'OnTurnSliderValueChanged.'),
    keyboard=dict(message='WM_KEYUP (0x101)', vk_left_up='subtract step', vk_right_down='add step'),
    semantics=dict(
        step='float32 1.0f / (100.0f / WheelSteps), i.e. WheelSteps percent of the normalized 0..1 value per WM_MOUSEWHEEL message',
        direction='HIWORD(wParam) > 0 (wheel away/up): value -= step; HIWORD(wParam) <= 0: value += step',
        magnitude='ignored: one step per message regardless of 120-unit multiples',
        clamp='stored value clamped to [0, 1] in float32 before notification',
        notification='registered slider callbacks receive the stored float even when clamping left it unchanged',
        gate='control state bit 0x10000 must be set; its meaning (pointer-over versus enabled) is not established by this probe'),
    original_turn_slider='ReplayViewer.xml TurnSlider WheelSteps="10" -> step 0.1f; ReplayViewer.lua re-seeds the slider '
                         'with (turn-initial)/(final-initial) on every redraw, so each wheel step starts from the current turn.')
report['open_items_not_resolved'] = ['WindowTrim UV/sampling and the slider gate bit meaning were not resolved here.']
with open(out, 'w', encoding='utf8', newline='\n') as stream:
    json.dump(report, stream, indent=1)
    stream.write('\n')
print(json.dumps(dict(status='PASS_RETAIL_STATIC_PROBE', exe_sha256=sha, locale=list(locale), out=out)))
