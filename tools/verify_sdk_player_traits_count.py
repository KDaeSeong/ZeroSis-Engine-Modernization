"""Exact PlayerTraits writers with archived/current SDK streams; no GameCore."""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys

sys.dont_write_bytecode = True
from verify_retail_save_header import artifact, require, key, within, COMPILER, COMPILER_SHA, VS
from verify_sdk_type_array_count import imports, VC9, WIN7, CL86, CL86_SHA, LIBRARIES as STREAM_LIBRARIES
from native_build import environment_for, run
from collect_baseline import pe_header

PROJECT = Path(__file__).absolute().parents[1]
STAGE = PROJECT/'evidence/serialization/player_traits_count'
REPORT = STAGE/'build_result.json'
TEST = PROJECT/'Tests/sdk_player_traits_count.cpp'
ORIGINAL = PROJECT/'Source/SDK_BNW_Original/CvGameCoreDLL_Expansion2/CvTraitClasses.cpp'
CANDIDATE = PROJECT/'Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvTraitClasses.cpp'
ORIGINAL_SHA = '8e5c3fe9ad40e44e2ad9a16e9ea590ff13ced2b51925f96b280495d82fec8edc'
CANDIDATE_SHA = 'f9b66e589e47abd0bad339a08187c4124f572961575a983da79f91348598eaf6'
DECLARATIONS_SHA = '1750f445c977cec4ecd587a1cd0642f3edb1df1186ce23000b591c2f32254d81'
HELPER_SHA = 'b33060722669f0374d6307a79364c065d84739ae0c958bbe41eb8e1b8a4acb9f'
HEADERS = [PROJECT/'Source/Host'/name for name in ('RetailSaveStateWire.h', 'RetailSavePlayerTraits.h')]
LIBRARIES = {arch: list(rows) for arch, rows in STREAM_LIBRARIES.items()}
LIBRARIES['x64'].insert(0, (PROJECT/'Build/Serialization/candidate/x64/ZeroSis_Serialization_x64.lib',
    'ee917f38ae102932d757625f5abc48839e5ff1d934a747244b3e216eb16fcf91'))
PREFLIGHTS = (('iNumMayaBonusChoices', 'm_aMayaBonusChoices'),
              ('iNumNoTrain', 'm_abNoTrain'), ('iNumUniqueLuxuryAreas', 'm_aUniqueLuxuryAreas'))
MANIFEST_TOOL = Path(r'C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\mt.exe')
MANIFEST_TOOL_SHA = '5370fbc9234c7d8ab88688f5a98c218b686f37096a4c88dac8498823a6154069'


def function(data, signature, template=False):
    token = signature.encode('ascii')
    require(data.count(token) == 1, 'Ambiguous retained function: '+signature)
    start = data.index(token)
    if template:
        start = data.rfind(b'template<', 0, start)
        require(start >= 0, 'Missing template prefix')
    opening = data.index(b'{', data.index(token))
    end, depth = opening + 1, 1
    while depth:
        require(end < len(data), 'Unterminated retained function')
        if data[end] == ord('{'): depth += 1
        elif data[end] == ord('}'): depth -= 1
        end += 1
    body = data[start:end]
    body.decode('ascii')
    return body, dict(signature=signature, offset=start, bytes=len(body), sha256=hashlib.sha256(body).hexdigest())


def record_struct(data, name):
    start = data.index(('struct '+name+'\r\n').encode())
    end = data.index(b'\r\n};', start) + len(b'\r\n};')
    return data[start:end]


def generate(path):
    original, fixed = ORIGINAL.read_bytes(), CANDIDATE.read_bytes()
    require(hashlib.sha256(original).hexdigest() == ORIGINAL_SHA and
        hashlib.sha256(fixed).hexdigest() == CANDIDATE_SHA, 'Reviewed Traits source changed')
    original_h, candidate_h = ORIGINAL.with_suffix('.h'), CANDIDATE.with_suffix('.h')
    declarations = original_h.read_bytes()
    require(artifact(original_h)['sha256'] == DECLARATIONS_SHA and declarations == candidate_h.read_bytes(),
        'Traits member declarations differ from retained source')
    signature = 'void CvPlayerTraits::Write(FDataStream& kStream)'
    original_body, original_row = function(original, signature)
    fixed_body, fixed_row = function(fixed, signature)
    original_read, read_row = function(original, 'void CvPlayerTraits::Read(FDataStream& kStream)')
    candidate_read, _ = function(fixed, 'void CvPlayerTraits::Read(FDataStream& kStream)')
    require(original_read == candidate_read and b'int iNumEntries;' in original_read,
        'The retained int32 count reader changed')
    guards = []
    for local, member in PREFLIGHTS:
        statement = f'const int {local} = CvChecked::Integer<int>({member}.size());'.encode()
        require(fixed_body.count(statement) == 1 and fixed_body.index(statement) < fixed_body.index(b'kStream <<'),
            'All signed count guards must precede every stream write')
        require(fixed_body.count(f'kStream << {local};'.encode()) == 1, 'Count write does not use its checked local')
        guards.append(statement)
    require(b'for(int iI = 0; iI < iNumMayaBonusChoices; iI++)' in fixed_body and
        b'for (int ui = 0; ui < iNumNoTrain; ui++)' in fixed_body and
        b'for (int iI = 0; iI < iNumUniqueLuxuryAreas; iI++)' in fixed_body,
        'Loop bounds no longer use the three checked locals')
    require(b'kStream << m_aMayaBonusChoices.size();' in original_body and
        b'kStream << m_abNoTrain.size();' in original_body and
        b'kStream << (int)m_aUniqueLuxuryAreas.size();' in original_body,
        'Original negative-control count expressions changed')
    free_block = lambda body: body[body.index(b'kStream << m_aFreeTraitUnits.size();'):
        body.index(b'int iNumUnitCombatClassInfos')]
    require(free_block(original_body) == free_block(fixed_body), 'The existing uint-size free-unit block changed')

    section = declarations[declarations.index(b'// Cached data about this player'):]
    used = set(re.findall(rb'\bm_\w+', original_body))
    lines = [line for line in section.splitlines() if b';' in line and
        any(re.search(rb'\b'+name+rb'\b', line) for name in used)]
    # Record fields from nested structs are outside this class section. Every
    # selected declaration must name exactly one serialized member.
    selected = []
    for line in lines:
        names = [name for name in used if re.search(rb'\b'+name+rb'\b', line)]
        require(len(names) == 1 and (line.strip().endswith(b';') or b'// Saved' in line or b'DEPRECATED' in line),
            'Unexpected Traits declaration shape')
        selected.append((names[0], line))
    names = [name for name, _ in selected]
    require(len(names) == len(set(names)) == 105, 'Serialized member declaration set differs')
    scalars = [name for name, line in selected if re.fullmatch(rb'\s*int\s+m_\w+;\s*(?://.*)?', line)
        and name != b'm_iBaktunPreviousTurn']
    bools = [name for name, line in selected if re.fullmatch(rb'\s*bool\s+m_\w+;\s*(?://.*)?', line)]
    require(len(scalars) == 65 and len(bools) == 19, 'Traits scalar int/bool counts differ')
    require(all(b'std::vector<' in line for name, line in selected if name in
        (b'm_aMayaBonusChoices', b'm_abNoTrain', b'm_aUniqueLuxuryAreas')), 'Real vector declarations were replaced')
    def macro(name, fields):
        return ('#define '+name+'(X) \\\n'+ ' \\\n'.join('    X('+field.decode()+')' for field in fields)+'\n').encode()
    parts = [b'#pragma once\n', macro('SDK_TRAITS_INT_MEMBERS', scalars), macro('SDK_TRAITS_BOOL_MEMBERS', bools),
        record_struct(declarations, 'MayaBonusChoice'), record_struct(declarations, 'FreeTraitUnit'),
        b'''// Scoped shim: FStaticVector<FreeTraitUnit,...> has unsigned-int size().
// Its allocator/capacity behavior is not under test; all std::vectors stay real.
struct TraitsFreeUnitsShim {
    std::vector<FreeTraitUnit> values;
    unsigned int size() const { return static_cast<unsigned int>(values.size()); }
    FreeTraitUnit& operator[](unsigned int i) { return values[i]; }
    void clear() { values.clear(); }
    void push_back(const FreeTraitUnit& value) { values.push_back(value); }
};
struct TraitsFixtureMembers {
''']
    for name, line in selected:
        parts.append(b'    TraitsFreeUnitsShim m_aFreeTraitUnits;\n' if name == b'm_aFreeTraitUnits' else line+b'\n')
    parts.append(b'''};
struct TraitsTestGlobals {
    int terrains, combat;
    TraitsTestGlobals() : terrains(0), combat(0) {}
    int getNumTerrainInfos() const { return terrains; }
    int getNumUnitCombatClassInfos() const { return combat; }
} GC;
namespace CvInfosSerializationHelper {
using TestHooks::WriteHashed;
''')
    helpers = [ORIGINAL.with_name('CvInfosSerializationHelper.h'), CANDIDATE.with_name('CvInfosSerializationHelper.h')]
    require(artifact(helpers[1])['sha256'] == HELPER_SHA, 'Previously verified hashed-vector count helper changed')
    pointer_sig = 'void WriteHashedDataArray(FDataStream& kStream, TData* paArray, uint uiArraySize)'
    vector_sig = 'void WriteHashedDataArray(FDataStream& kStream, const std::vector<TData>& aArray)'
    pointer, pointer_row = function(helpers[0].read_bytes(), pointer_sig, template=True)
    other_pointer, _ = function(helpers[1].read_bytes(), pointer_sig, template=True)
    require(pointer == other_pointer, 'Pointer hash-array writer changed')
    vector_original, vector_original_row = function(helpers[0].read_bytes(), vector_sig, template=True)
    vector_fixed, vector_fixed_row = function(helpers[1].read_bytes(), vector_sig, template=True)
    parts += [pointer+b'\n', b'#ifdef _WIN64\n', vector_fixed+b'\n', b'#else\n', vector_original+b'\n', b'#endif\n}\n']
    families = []
    for name, body, row, condition in (
        ('OriginalWriter', original_body, original_row, '#ifndef _WIN64'),
        ('Legacy64Writer', original_body, original_row, '#ifdef _WIN64'),
        ('CandidateWriter', fixed_body, fixed_row, '#ifdef _WIN64')):
        parts += [(condition+'\nnamespace '+name+' {\nstruct CvPlayerTraits : TraitsFixtureMembers { void Write(FDataStream& kStream); };\n').encode(),
            body+b'\n}\n#endif\n']
        families.append(dict(namespace=name, source_sha256=CANDIDATE_SHA if name == 'CandidateWriter' else ORIGINAL_SHA,
            function=row, body_retained_verbatim=True))
    parts += [b'''#ifdef _WIN64
// Only the actual three preflight statements are instantiated with fake size
// returns. Normal full-writer tests above retain actual std::vector members.
struct TraitsFakeSize {
    std::size_t declared;
    TraitsFakeSize() : declared(0) {}
    std::size_t size() const { return declared; }
};
struct TraitsPreflightProbe {
    TraitsFakeSize m_aMayaBonusChoices, m_abNoTrain, m_aUniqueLuxuryAreas;
    void Write(FDataStream& kStream) {
''', b'\n'.join(b'        '+statement for statement in guards), b'''
        kStream << iNumMayaBonusChoices << iNumNoTrain << iNumUniqueLuxuryAreas;
    }
};
static_assert(std::is_same<std::vector<MayaBonusChoice>::size_type, std::size_t>::value, "Maya size_type changed");
static_assert(std::is_same<std::vector<bool>::size_type, std::size_t>::value, "NoTrain size_type changed");
static_assert(std::is_same<std::vector<int>::size_type, std::size_t>::value, "Luxury size_type changed");
#endif
''']
    path.write_bytes(b'\n'.join(parts))
    return dict(generated=artifact(path), families=families, original_read=read_row,
        preflights=[dict(statement=s.decode(), body_offset=fixed_body.index(s),
            source_file_offset=fixed_row['offset']+fixed_body.index(s)) for s in guards],
        first_scalar_ints=65, scalar_bools=19, serialized_member_count=len(names), fixed_yields=6,
        free_trait_shim='Only FStaticVector<FreeTraitUnit> storage replaced; size() remains unsigned int; allocator/capacity untested',
        normal_vectors='Actual SDK-declared std::vector<MayaBonusChoice>, std::vector<bool>, std::vector<int>',
        hash_resolution='TestHooks only, not actual database hashes or ruleset IDs',
        hash_helpers=dict(pointer=pointer_row, original_vector=vector_original_row, current_vector=vector_fixed_row,
            legacy64_nested_helpers='Canonical current uint32 hashed/STL counts; only the two Traits direct size_t writes are negative controls'),
        overflow_scope='Exact authenticated three preflight statements with allocation-free size_t-return objects; full normal Write bodies also compiled')


def main():
    require(len(sys.argv) == 1 and not sys.flags.optimize, 'Unexpected Traits count verifier arguments')
    enums = PROJECT/'evidence/serialization/candidate/conformance.json'
    syntax = PROJECT/'evidence/serialization/player_count_syntax/build_result.json'
    require(artifact(enums)['sha256'] == '24d80941049f5fa4fa050bc138742806bfaeb7e249195dd330dd5b1959f15e22', 'Original enum proof changed')
    require(artifact(syntax)['sha256'] == 'c7c67e2065af9c5a81e986b8487a84d7de4337b3330d41abaa27dec30080800a', 'Actual Traits syntax proof changed')
    source_paths = [TEST, ORIGINAL, CANDIDATE, ORIGINAL.with_suffix('.h'), CANDIDATE.with_suffix('.h'), *HEADERS,
        *[p.with_name('CvInfosSerializationHelper.h') for p in (ORIGINAL, CANDIDATE)],
        PROJECT/'Source/Porting/CvCheckedNarrow.h', PROJECT/'Source/Providers/Streams/SdkStreamIncludes.h',
        PROJECT/'Tests/sdk_stream_reference_host.cpp', Path(__file__).absolute(), enums, syntax, MANIFEST_TOOL,
        *[PROJECT/'tools'/name for name in ('verify_sdk_type_array_count.py', 'verify_retail_save_header.py',
            'verify_retail_save_state.py', 'native_build.py', 'collect_baseline.py')]]
    for sdk in ('SDK_BNW_Original', 'SDK_BNW_x64'):
        source_paths.append(PROJECT/'Source'/sdk/'CvGameCoreDLL_Expansion2/CvGameCoreEnums.h')
        source_paths += [PROJECT/'Source'/sdk/'FirePlace/include/FireWorks'/name for name in
            ('FDataStream.h', 'FMemoryStream.h', 'FStlContainerSerialization.h', 'FFastVector.h', 'FArray.h')]
        source_paths += [PROJECT/'Source'/sdk/'CvGameCoreDLLUtil/include'/name for name in ('CvEnums.h', 'CvEnumSerialization.h')]
    source_paths += [p for rows in LIBRARIES.values() for p, _ in rows]
    inputs = [artifact(p) for p in source_paths]
    require(artifact(MANIFEST_TOOL)['sha256'] == MANIFEST_TOOL_SHA, 'Reviewed current Windows SDK manifest tool changed')
    for rows in LIBRARIES.values():
        for path, expected in rows: require(artifact(path)['sha256'] == expected, 'Reviewed SDK library changed')
    compilers = [artifact(CL86), artifact(COMPILER)]
    require(compilers[0]['sha256'] == CL86_SHA and compilers[1]['sha256'] == COMPILER_SHA, 'Reviewed compiler changed')
    identifier = hashlib.sha256(json.dumps(dict(inputs=inputs, compilers=compilers), sort_keys=True).encode()).hexdigest()[:16]
    root = PROJECT/'Build/SdkPlayerTraitsCount'/identifier
    if REPORT.exists():
        old = json.loads(REPORT.read_text(encoding='utf-8'))
        require(old['inputs'] == inputs and old['status'] == 'PASS_SDK_PLAYER_TRAITS_COUNT_ABI_COMPONENT', 'Inspect previous Traits count proof first')
        for row in old['results']: require(artifact(row['executable']['path']) == row['executable'], 'Retained Traits test changed')
        for row in old['canonical_wires']: require(artifact(row['path']) == row, 'Retained canonical wire changed')
        print(json.dumps(dict(status=old['status'], reused=True)))
        return
    require(not root.exists(), 'Inspect and retire partial Traits build before retrying')
    protected = [artifact(PROJECT/name) for name in ('Play/EarlyAccess/release.json',
        'evidence/save_menu/20261013_original_screen/current_progress.json',
        'evidence/goody_hut/runtime_fonts/preparation_identity_audit.json',
        'evidence/goody_hut/runtime_fonts/system_freeze_hold.json',
        'evidence/retail_save_container/player_ai_mid/build_result.json', 'docs/M7_RETAIL_SAVE_BOUNDARY.md')]
    for part in (root, *root.parents, STAGE, *STAGE.parents):
        if part.exists(): require(not part.lstat().st_file_attributes & 0x400, 'Reparse Traits output path')
    root.parent.mkdir(parents=True, exist_ok=True); STAGE.mkdir(exist_ok=True)
    setup = root/'read_build_environment.cmd'
    allowed, calls = {('cmd.exe', '/d', '/c', str(setup))}, []

    def audit(event, args):
        if event == 'subprocess.Popen':
            command = next((x for x in allowed if subprocess.list2cmdline(x) == args[1]), None) \
                if isinstance(args[1], str) else tuple(str(x) for x in args[1])
            require(command in allowed, 'Unapproved Traits-test child command')
            require(args[0] is None or key(args[0]) == key(command[0]) or
                Path(args[0]).name.casefold() == command[0].casefold() == 'cmd.exe', 'Unexpected executable override')
            calls.append(command)
        if event == 'open' and args and isinstance(args[0], (str, bytes, os.PathLike)):
            writing = isinstance(args[1], str) and any(c in args[1] for c in 'wax+') or \
                isinstance(args[2], int) and args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
            if writing: require(within(os.fsdecode(args[0]), root) or within(os.fsdecode(args[0]), STAGE), 'Write escaped Traits outputs')
        if event in ('os.remove', 'os.rmdir', 'os.mkdir', 'os.rename', 'os.chmod', 'os.link', 'os.symlink'):
            for target in (args[:2] if event in ('os.rename', 'os.link', 'os.symlink') else args[:1]):
                if isinstance(target, (str, bytes, os.PathLike)): require(within(os.fsdecode(target), root), 'Mutation escaped owned Traits root')
        if event.startswith(('ctypes.dlopen', 'socket.', 'urllib.', 'http.client.')) or event in ('os.system', 'os.startfile', 'os.startfile/2'):
            raise RuntimeError('Network, dynamic loading and interactive launches forbidden during Traits tests')
    sys.addaudithook(audit)
    results, retired, canonical, consumed = [], [], [], {}
    root.mkdir()
    try:
        generated = generate(root/'SdkPlayerTraitsWriters.h')
        (STAGE/'build_started.json').write_text(json.dumps(dict(build_root=str(root), inputs=inputs, protected=protected,
            execution_scope='Owned SDK stream component tests only; no public/user save input'), indent=2)+'\n', encoding='utf-8')
        environment64, selected = environment_for(VS, 'x64', root)
        require(key(selected) == key(COMPILER), 'Compiler selection changed')
        for arch, flavor, optimization in (('x86', 'O2', ['/O2']), ('x64', 'O2', ['/O2']), ('x64', 'Od', ['/Od', '/RTC1'])):
            out = root/(arch+'_'+flavor); out.mkdir()
            sdk = PROJECT/('Source/SDK_BNW_Original' if arch == 'x86' else 'Source/SDK_BNW_x64')
            if arch == 'x86':
                env = {k.upper(): v for k, v in os.environ.items()}
                env['INCLUDE'] = str(VC9/'include')+';'+str(WIN7/'Include')
                env['LIB'] = str(VC9/'lib')+';'+str(WIN7/'Lib')
                env['PATH'] = ';'.join([str(VC9/'bin'), str(VC9.parent/'Common7/IDE'), str(WIN7/'bin'), env.get('PATH', '')])
                compiler = CL86
            else: env, compiler = environment64.copy(), COMPILER
            env['VSLANG'] = '1033'; env['TMP'] = env['TEMP'] = str(out)
            includes = [sdk/'FirePlace/include', sdk/'CvGameCoreDLLUtil/include', sdk/'CvGameCoreDLL_Expansion2']
            own = [PROJECT/'Source/Providers/Streams', PROJECT/'Source/Porting', root]
            flags = ['/nologo', '/EHsc', '/MD', '/fp:strict', '/D_CRT_SECURE_NO_WARNINGS', '/DFINAL_RELEASE',
                '/D_SECURE_SCL=0', '/D_HAS_ITERATOR_DEBUGGING=0', *optimization]
            flags += (['/W3', '/wd4819']+[f'/I"{p}"' for p in includes+own]) if arch == 'x86' else (
                ['/std:c++14', '/W4', '/WX', '/D_SILENCE_STDEXT_HASH_DEPRECATION_WARNINGS', '/external:W0']+
                [f'/external:I"{p}"' for p in includes]+[f'/I"{p}"' for p in own])
            sources = [TEST]+([PROJECT/'Tests/sdk_stream_reference_host.cpp'] if arch == 'x86' else [])
            objects, dependencies, logs, responses = [], [], [], []
            for source in sources:
                obj, response = out/(source.stem+'.obj'), out/(source.stem+'.rsp')
                dep = out/(source.stem+'.dependencies.json')
                args = [*flags, '/c', f'"{source}"', f'/Fo"{obj}"']
                args += ['/showIncludes'] if arch == 'x86' else [f'/sourceDependencies "{dep}"']
                response.write_text('\n'.join(args)+'\n', encoding='ascii')
                command = [str(compiler), '@'+str(response)]; allowed.add(tuple(command))
                built = run(command, cwd=out, env=env, timeout=120)
                text = (built.stdout+built.stderr).decode('mbcs', errors='replace')
                log = STAGE/(arch+'_'+flavor+'_'+source.stem+'.log'); log.write_text(text, encoding='utf-8')
                require(built.returncode == 0 and not re.search(r'\bwarning\s+[A-Z]+\d+', text, re.I), 'Compile failed: '+log.name)
                if arch == 'x64':
                    data = json.loads(dep.read_text(encoding='utf-8-sig'))['Data']
                    needed = [root/'SdkPlayerTraitsWriters.h', *HEADERS, PROJECT/'Source/Porting/CvCheckedNarrow.h',
                        sdk/'CvGameCoreDLL_Expansion2/CvGameCoreEnums.h',
                        sdk/'FirePlace/include/FireWorks/FStlContainerSerialization.h', sdk/'CvGameCoreDLLUtil/include/CvEnumSerialization.h']
                    require(key(data['Source']) == key(source) and all(any(key(x) == key(h) for x in data['Includes']) for h in needed),
                        'Actual Traits source/header dependency mismatch')
                    require(not any('cvgamecoredll_expansion2' in key(x) and
                        key(x) != key(sdk/'CvGameCoreDLL_Expansion2/CvGameCoreEnums.h') for x in data['Includes']),
                        'Full GameCore header entered component TU; only the pure BNW enum declaration is permitted')
                    require(not any('sdk_bnw_original' in key(x) for x in data['Includes']), 'Original headers entered x64 component TU')
                    for included in data['Includes']:
                        if within(included, PROJECT): consumed[key(included)] = artifact(Path(included))
                    dependencies.append(artifact(dep))
                else:
                    if source == TEST: require(str(root/'SdkPlayerTraitsWriters.h').casefold() in text.casefold(), 'Original exact writer header not consumed')
                    for line in text.splitlines():
                        match = re.search(r'([A-Za-z]:[\\/].*\.(?:h|hpp|inl|inc))\s*$', line, re.I)
                        if match and within(match.group(1), PROJECT):
                            require('sdk_bnw_x64' not in key(match.group(1)), 'Port headers entered original x86 component TU')
                            consumed[key(match.group(1))] = artifact(Path(match.group(1)))
                objects.append(artifact(obj)); logs.append(artifact(log)); responses.append(artifact(response))
            exe, linkmap = out/'SdkPlayerTraitsCountTests.exe', out/'SdkPlayerTraitsCountTests.map'
            link = ['/nologo', '/INCREMENTAL:NO', '/OPT:REF', '/OPT:ICF', '/DYNAMICBASE', '/NXCOMPAT',
                '/MACHINE:'+arch.upper(), '/MAP:'+str(linkmap)]
            link += ['/LTCG'] if arch == 'x86' else ['/Brepro', '/WX']
            command = [str(compiler.with_name('link.exe')), '/OUT:'+str(exe), *[x['path'] for x in objects],
                *[str(p) for p, _ in LIBRARIES[arch]], *link,
                *[n+'.lib' for n in ('kernel32', 'user32', 'advapi32', 'psapi', 'dbghelp', 'ole32', 'shell32', 'winmm')]]
            allowed.add(tuple(command)); linked = run(command, cwd=out, env=env, timeout=120)
            text = (linked.stdout+linked.stderr).decode('mbcs', errors='replace')
            log = STAGE/(arch+'_'+flavor+'_link.log'); log.write_text(text, encoding='utf-8')
            require(linked.returncode == 0 and not re.search(r'\bwarning\s+[A-Z]+\d+', text, re.I), 'Link failed: '+log.name)
            manifest = exe.with_suffix('.exe.manifest')
            if arch == 'x86' and manifest.exists():
                command = [str(MANIFEST_TOOL), '-nologo', '-manifest', str(manifest), '-outputresource:'+str(exe)+';1']
                allowed.add(tuple(command)); embedded = run(command, cwd=out, env=env, timeout=30)
                require(embedded.returncode == 0, 'Original CRT manifest embed failed')
            # Attest every newly generated executable BEFORE it can be launched.
            identity, pe, imported = artifact(exe), pe_header(exe), imports(exe)
            image = exe.read_bytes(); pe_offset = struct.unpack_from('<I', image, 0x3c)[0]
            dll_characteristics = struct.unpack_from('<H', image, pe_offset+94)[0]
            require(pe['architecture'] == arch and pe['pe_format'] == ('PE32' if arch == 'x86' else 'PE32+') and
                not pe['is_dll'] and dll_characteristics & 0x140 == 0x140 and
                not any('civilization' in name or 'gamecore' in name for name in imported), 'Unexpected generated test PE/imports/relocation flags')
            mapping = linkmap.read_text(encoding='mbcs', errors='replace')
            require('FMemoryStream' in mapping and ('FireWorksWin32' if arch == 'x86' else 'ZeroSis_Streams_x64') in mapping,
                'Actual SDK stream library not present in link map')
            for enum in ('UnitTypes', 'TechTypes', 'ImprovementTypes'):
                for operation in ('??5@', '??6@'):
                    require(any('W4'+enum+'@@' in line and operation in line and
                        ('CvEnumSerialization.obj' if arch == 'x86' else 'SdkEnumSerialization.obj') in line for line in mapping.splitlines()),
                        'Actual enum codec provider not present in map: '+enum+' '+operation)
            command = [str(exe), '--x86original' if arch == 'x86' else '--x64']; allowed.add(tuple(command))
            tested = subprocess.run(command, cwd=out, env=env, capture_output=True, timeout=60,
                creationflags=subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS)
            text = (tested.stdout+tested.stderr).decode('utf-8', errors='replace').strip()
            log = STAGE/(arch+'_'+flavor+'_test.log'); log.write_text(text+'\n', encoding='utf-8')
            require(tested.returncode == 0 and artifact(exe) == identity, 'Native Traits test failed or executable changed')
            result = json.loads(text)
            require(result['status'] == 'PASS_SDK_PLAYER_TRAITS_COUNT' and result['canonical_direct_count_bytes'] == 4 and
                result['legacy64_direct_count_bytes'] == (0 if arch == 'x86' else 8) and
                result['oversized_preflight_rejections'] == (0 if arch == 'x86' else 9) and
                result['production_reader_cases'] == (0 if arch == 'x86' else 3) and
                result['legacy_exact_boundaries_rejected'] == (0 if arch == 'x86' else 3) and
                all(result[name] is False for name in ('gamecore_loaded', 'window_created', 'user_saves_accessed',
                    'complete_save_validated', 'ruleset_compatibility_verified', 'restore_approved')), 'Native Traits result scope differs')
            wires = [artifact(out/('canonical_case_'+str(i)+'.bin')) for i in range(3)]
            if not canonical: canonical = wires
            else:
                require(all(Path(a['path']).read_bytes() == Path(b['path']).read_bytes() for a, b in zip(canonical, wires)),
                    'Actual x86 and fixed x64 full writer/canary wires differ')
            results.append(dict(arch=arch, flavor=flavor, executable=identity, pe=pe, imports=imported,
                dll_characteristics_hex=hex(dll_characteristics),
                executable_attested_before_launch=True, objects=objects, dependencies=dependencies, responses=responses,
                map=artifact(linkmap), compile_logs=logs, test_log=artifact(log), test=result, canonical_wires=wires,
                legacy_wires=[artifact(out/('legacy64_case_'+str(i)+'.bin')) for i in range(3)] if arch == 'x64' else []))
        require(inputs == [artifact(x['path']) for x in inputs] and protected == [artifact(x['path']) for x in protected],
            'Inputs or protected runtime evidence changed')
        require(all(artifact(row['path']) == row for row in consumed.values()), 'Consumed project header changed')
        discard = [(Path(o['path']), 'completed compiler object') for r in results for o in r['objects']]
        discard += [(setup, 'completed environment setup')]
        discard += [(Path(w['path']), 'duplicate canonical wire compared byte-for-byte') for r in results if r['arch'] == 'x64' for w in r['canonical_wires']]
        discard += [(Path(w['path']), 'negative-control wire authenticated before retirement') for r in results for w in r['legacy_wires']]
        for path, reason in discard:
            info = path.stat()
            require(within(path, root) and info.st_nlink == 1 and not info.st_file_attributes & 0x400, 'Unexpected Traits cleanup identity')
            row = dict(**artifact(path), file_identity=[info.st_dev, info.st_ino], mtime_ns=info.st_mtime_ns, reason=reason)
            require(artifact(path) == {k: row[k] for k in ('path', 'bytes', 'sha256')}, 'Intermediate changed before cleanup')
            path.unlink(); retired.append(row)
        report = dict(schema='zerosis.sdk.player_traits.count_abi.v1', status='PASS_SDK_PLAYER_TRAITS_COUNT_ABI_COMPONENT',
            utc=datetime.now(timezone.utc).isoformat(), build_root=str(root), inputs=inputs, compilers=compilers,
            generated_extracts=generated, results=results, consumed_project_headers=list(consumed.values()),
            canonical_wires=canonical, all_canonical_wires_byte_identical=True,
            protected=protected, protected_unchanged=True, child_commands=[list(x) for x in calls],
            retired_intermediates=retired, retired_logical_bytes=sum(x['bytes'] for x in retired),
            actual_traits_translation_unit_syntax_proof=artifact(syntax), previous_goal_turn_classification='progress',
            original_install_or_user_saves_accessed=False, public_save_or_body_retained=False,
            host_gamecore_or_hwnd_executed=False, full_sdk_recompiled=False, integrated_into_current_host=False,
            sdk_restore_verified=False, full_player_framed=False, ruleset_compatibility_verified=False, full_engine_goal_complete=False)
        REPORT.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
        print(json.dumps(dict(status=report['status'], checks=[r['test']['checks'] for r in results],
            retired_bytes=report['retired_logical_bytes'], report=artifact(REPORT))))
    except BaseException as error:
        (STAGE/'failed_attempt.json').write_text(json.dumps(dict(status='FAILED_SDK_PLAYER_TRAITS_COUNT_TEST',
            error=type(error).__name__+': '+str(error), build_root=str(root), inputs=inputs, completed_modes=results,
            retired_intermediates=retired,
            protected_unchanged=protected == [artifact(x['path']) for x in protected]), indent=2)+'\n', encoding='utf-8')
        raise


if __name__ == '__main__':
    main()
