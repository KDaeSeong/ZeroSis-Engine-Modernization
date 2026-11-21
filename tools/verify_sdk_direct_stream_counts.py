"""Full PopupReturn and bounded direct-count fragments, using actual SDK streams."""
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
from verify_sdk_player_traits_count import function, imports, VC9, WIN7, CL86, CL86_SHA, LIBRARIES, MANIFEST_TOOL, MANIFEST_TOOL_SHA
from native_build import environment_for
from collect_baseline import pe_header

PROJECT = Path(__file__).absolute().parents[1]
STAGE = PROJECT/'evidence/serialization/direct_stream_counts'
REPORT = STAGE/'build_result.json'
TEST = PROJECT/'Tests/sdk_direct_stream_counts.cpp'
PLAN = STAGE/'plan.json'
PLAN_SHA = '8425da60fcdc0a9d5b86adeaf4ea0ab4167885b9ca1b1f41cb5720622e09f2de'
POPUP_HEADER_PINS = {
    'SDK_BNW_Original': '37255600aff0971be06131bcd6c5faa746e71d27e8fe0a24a58c813c3d662e60',
    'SDK_BNW_x64': '2efad09513806ca6ab98af4293f14a91677fdc60c38419a0b3e9fc9e3f8d6199',
}
AUDITS = [(PROJECT/'evidence/serialization/player_count_width'/name, sha) for name, sha in (
    ('remaining_direct_counts_a.json', '0613bacda43b7a677cdb808fddf1370c86c9d11c28efb754f4d67a1ae4be2f26'),
    ('remaining_direct_counts_b.json', '394016c31474f1ba5bb2ecee3ad458aa13b6312e5074e1a581bd9e648af724ea'))]
GROUPS = {'CvArmyAI.cpp': 'Army', 'CvCultureClasses.cpp': 'Culture', 'CvDiplomacyRequests.cpp': 'Diplomacy',
    'CvEconomicAI.cpp': 'Economic', 'CvEspionageClasses.cpp': 'Espionage', 'CvReplayInfo.cpp': 'ReplayInfo',
    'CvReplayMessage.cpp': 'ReplayMessage', 'CvPopupReturn.cpp': 'Popup'}
PATHS = dict(zip(('iNumSelectedRadioButtons', 'iNumBitFields', 'iNumEditBoxStrings', 'iNumSpinnerWidgetValues',
    'iNumPulldownIDs', 'iNumListBoxIDs', 'iNumSpinBoxIDs', 'iNumButtonIDs', 'iNumFormationEntries',
    'iNumDigCompletePlots', 'uiNumRequests', 'iNumRequestedSavings', 'iNumSpyNames', 'aiHeistLocationCounts[uiCiv]',
    'iNumSpyNotificationMessages', 'iNumIntrigueNotificationMessages', 'uiNumReplayMessages', 'iNumPlots'), range(18)))


def run_low(command, *, cwd, env=None, timeout=60):
    return subprocess.run([str(item) for item in command], cwd=cwd, env=env, capture_output=True,
        timeout=timeout, creationflags=subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS)


def cpp_path(root, filename): return PROJECT/'Source'/root/'CvGameCoreDLL_Expansion2'/filename


def exact_statement(body, expression):
    rows = list(re.finditer(rb'(?m)^[ \t]*(?:kStream|saveTo)[ \t]*<<[^;\r\n]*'+re.escape(expression)+rb'[^;\r\n]*;', body))
    require(len(rows) == 1, 'Ambiguous count statement: '+expression.decode())
    row = rows[0]
    return row.group(), dict(offset=row.start(), bytes=row.end()-row.start(), sha256=hashlib.sha256(row.group()).hexdigest())


def loop_parts(body, statement, offset):
    end = offset + len(statement)
    loop = re.search(rb'for[ \t]*\([^\r\n]*\)', body[end:])
    require(loop is not None, 'Count statement lacks a following loop header')
    begin, finish = end + loop.start(), end + loop.end()
    gap = body[end:begin]
    require(b'{' not in gap and b'}' not in gap and b'<<' not in gap, 'Unexpected code between count and loop')
    # Only Culture's original iterator is declared before the count. Current
    # iterator/counter declarations after a count are retained in the gap.
    external = re.findall(rb'(?m)^[ \t]*vector<CvPlot \*>::const_iterator[ \t]+it[^;\r\n]*;', body[:offset])
    require(len(external) <= 1, 'Ambiguous external Culture iterator declaration')
    return b'\n'.join(external), gap, loop.group(), dict(offset=begin, bytes=finish-begin,
        sha256=hashlib.sha256(loop.group()).hexdigest(), text=loop.group().decode('ascii'))


def method_counts(body, sites, stream, loops):
    result, provenance = [], []
    for site in sites:
        path = PATHS[site['local']]
        expression = site['local'].encode() if loops == 'candidate' else site['size_expression'].encode()
        statement, statement_row = exact_statement(body, expression)
        if site['array_extent']:
            preceding = list(re.finditer(rb'for[ \t]*\([^\r\n]*uiCiv[^\r\n]*MAX_MAJOR_CIVS[^\r\n]*\)', body[:statement_row['offset']]))
            require(preceding, 'Missing authenticated outer heist loop')
            outer = preceding[-1].group()
        else: outer = None
        external, gap, header, loop_row = loop_parts(body, statement, statement_row['offset'])
        # Popup's complete original/candidate body is compiled separately. Its
        # count-only method is used only to instantiate the entry preflight.
        payload = statement+b'\n'
        if loops and path >= 8:
            payload = external+b'\n'+statement+gap+header+b' { ++visits['+str(path).encode()+b']; }\n'
        if outer: payload = outer+b' {\n'+payload+b'}\n'
        result.append(payload)
        provenance.append(dict(path=path, local=site['local'], size_expression=site['size_expression'],
            reader=site['reader'], cast_range_only=site['cast_range_only'], count_statement=statement.decode('ascii'),
            count_span=statement_row, loop_header=loop_row, outer_heist_loop=outer.decode('ascii') if outer else None,
            loop_body='visit counter only, original element payload not compiled' if path >= 8 else 'full Popup body compiled separately'))
    return b'\n'.join(result), provenance


def popup_vectors(popup_header):
    declarations = re.findall(rb'(?m)^[ \t]*std::vector<[^;\r\n]+m_\w+;[^\r\n]*', popup_header)
    require(len(declarations) == 8 and sum(b'std::vector<CvString>' in x for x in declarations) == 1,
        'Actual Popup member declarations changed')
    return declarations


def prelude(popup_header):
    # The eight actual Popup vector declarations are retained; CvString comes
    # from the actual SDK header (std::string-derived, no wchar/FString shim).
    declarations = popup_vectors(popup_header)
    return b'''#pragma once
using std::vector;
// Opaque non-Popup element records: only container size/loop headers are tested.
struct DirectOpaqueElement { int unused; };
class CvPlot;
typedef std::list<DirectOpaqueElement> RequestList;
typedef std::vector<DirectOpaqueElement> ReplayMessageList;
typedef std::pair<short, short> PlotPosition;
typedef std::vector<PlotPosition> PlotPositionList;
typedef Firaxis::Array<std::vector<DirectOpaqueElement>, MAX_MAJOR_CIVS> HeistLocationList;
// Two explicit unsigned-size shims model FStaticVector's uint return only.
// No allocator, storage, element payload or capacity behavior is validated.
struct DirectUIntSizeShim {
    unsigned int value;
    DirectUIntSizeShim() : value(0) {}
    unsigned int size() const { return value; }
    void resize(unsigned int size) { value = size; }
};
struct DirectCountMembers {
'''+b'\n'.join(declarations)+b'''
    DirectUIntSizeShim m_FormationEntries;
    std::vector<CvPlot*> m_aDigCompletePlots;
    RequestList m_aRequests;
    DirectUIntSizeShim m_RequestedSavings;
    std::vector<int> m_aiSpyListNameOrder;
    HeistLocationList m_aHeistLocations;
    std::vector<DirectOpaqueElement> m_aSpyNotificationMessages;
    std::vector<DirectOpaqueElement> m_aIntrigueNotificationMessages;
    ReplayMessageList m_listReplayMessages;
    PlotPositionList m_Plots;
    mutable unsigned int visits[18];
    DirectCountMembers() { for (unsigned int i=0; i<18; ++i) visits[i]=0; }
};
'''


def generate(path, plan):
    a = json.loads(AUDITS[0][0].read_text(encoding='utf-8'))
    b = json.loads(AUDITS[1][0].read_text(encoding='utf-8'))
    pins = {**a['source_pins'], **b['source_files']}
    sources, bodies, comparisons = [], {}, []
    for row in plan['file_plans']:
        filename = row['cpp']; original, candidate = cpp_path('SDK_BNW_Original', filename), cpp_path('SDK_BNW_x64', filename)
        original_pin = pins.get('Source/SDK_BNW_Original/CvGameCoreDLL_Expansion2/'+filename) or pins.get('original:'+filename)
        require(original_pin and artifact(original)['sha256'] == original_pin['sha256'], 'Original source no longer matches finite audit')
        require(artifact(candidate)['sha256'] == row['after_sha256'], 'Candidate patch not applied/frozen: '+filename)
        old, old_info = function(original.read_bytes(), row['signature'])
        new, new_info = function(candidate.read_bytes(), row['signature'])
        first_old = re.search(rb'(?:kStream|saveTo)[ \t]*<<', old).start()
        first_new = re.search(rb'(?:kStream|saveTo)[ \t]*<<', new).start()
        old_prefix = old[old.index(b'{')+1:first_old]
        new_prefix = new[new.index(b'{')+1:first_new]
        guards = row['preflight'].encode('ascii')
        require(new_prefix.endswith(old_prefix) and new[new.index(b'{')+3:].startswith(guards),
            'Entry guards are not an exact first-write preflight insertion')
        require(sum(s['checked_type'] == 'uint' for s in row['sites']) == (1 if filename in ('CvDiplomacyRequests.cpp', 'CvReplayInfo.cpp') else 0),
            'Signed/unsigned reader policy changed')
        bodies[filename] = old, new, guards
        sources += [artifact(original), artifact(candidate), artifact(original.with_suffix('.h')), artifact(candidate.with_suffix('.h'))]
        comparisons.append(dict(cpp=filename, signature=row['signature'], original=old_info, candidate=new_info,
            preflight_sha256=hashlib.sha256(guards).hexdigest(), original_prewrite_prefix_preserved=True,
            candidate_preflight_before_first_write=True, original_source=artifact(original), candidate_source=artifact(candidate)))
    require(set(bodies) == set(GROUPS), 'Finite eight-writer set changed')
    popup_headers = {sdk: artifact(cpp_path(sdk, 'CvPopupReturn.h')) for sdk in POPUP_HEADER_PINS}
    require(all(row['sha256'] == POPUP_HEADER_PINS[sdk] for sdk, row in popup_headers.items()),
        'Reviewed original/ported Popup header identity changed')
    popup = Path(popup_headers['SDK_BNW_Original']['path']).read_bytes()
    popup_fields = popup_vectors(popup)
    # Existing port getter checks change the enclosing header. Compare the
    # eight exact storage declarations needed by the extracted writer instead.
    require(popup_fields == popup_vectors(Path(popup_headers['SDK_BNW_x64']['path']).read_bytes()),
        'Popup vector storage declarations differ')
    parts, traces = [prelude(popup)], []
    for family, branch in (('DirectOriginalCounts', 'original'), ('DirectFixedCounts', 'candidate')):
        if branch == 'candidate': parts.append(b'#ifdef _WIN64\n')
        parts.append(('struct '+family+' : DirectCountMembers {\n').encode())
        for row in plan['file_plans']:
            old, new, guards = bodies[row['cpp']]; body = new if branch == 'candidate' else old
            stream = 'saveTo' if row['cpp'] in ('CvCultureClasses.cpp', 'CvEspionageClasses.cpp') else 'kStream'
            code, provenance = method_counts(body, row['sites'], stream, branch)
            parts.append(('void '+GROUPS[row['cpp']]+'(FDataStream& '+stream+') const {\n').encode())
            if stream == 'saveTo': parts.append(('const '+family+'& readFrom = *this;\n').encode())
            if branch == 'candidate': parts.append(guards)
            parts += [code, b'}\n']
            traces.append(dict(cpp=row['cpp'], family=family, sites=provenance))
        parts.append(b'};\n')
        if branch == 'candidate': parts.append(b'#endif\n')
    for namespace, index, condition in (('DirectOriginal', 0, ''), ('DirectFixed', 1, '#ifdef _WIN64\n')):
        parts.append((condition+'namespace '+namespace+' {\nstruct PopupReturn : DirectCountMembers { void write(FDataStream& kStream) const; };\n').encode())
        parts += [bodies['CvPopupReturn.cpp'][index], b'\n}\n']
        if condition: parts.append(b'#endif\n')
    # Fake query return types match the real size() APIs. No native container
    # allocation is attempted for INT_MAX/UINT_MAX/SIZE_MAX boundary tests.
    parts.append(b'''#ifdef _WIN64
struct DirectNativeSize { std::size_t declared; DirectNativeSize():declared(0){} std::size_t size() const{return declared;} };
struct DirectUnsignedSize { unsigned int declared; DirectUnsignedSize():declared(0){} unsigned int size() const{return declared;} };
struct DirectEntryProbes {
    DirectNativeSize m_aiSelectedRadioButton, m_aiBitField, m_aszEditBoxString, m_aiSpinnerWidgetValues;
    DirectNativeSize m_aiPulldownID, m_aiListBoxID, m_aiSpinBoxID, m_aiButtonID;
    DirectUnsignedSize m_FormationEntries, m_RequestedSavings;
    DirectNativeSize m_aDigCompletePlots, m_aRequests, m_aiSpyListNameOrder;
    Firaxis::Array<DirectNativeSize, MAX_MAJOR_CIVS> m_aHeistLocations;
    DirectNativeSize m_aSpyNotificationMessages, m_aIntrigueNotificationMessages, m_listReplayMessages, m_Plots;
''')
    for row in plan['file_plans']:
        _, body, guards = bodies[row['cpp']]
        stream = 'saveTo' if row['cpp'] in ('CvCultureClasses.cpp', 'CvEspionageClasses.cpp') else 'kStream'
        code, _ = method_counts(body, row['sites'], stream, 'candidate')
        # Keep the exact count writes and outer heist loop, excluding normal
        # loop headers/payload. All checked locals are used after all guards.
        output = []
        for site in row['sites']:
            statement, span = exact_statement(body, site['local'].encode())
            if site['array_extent']:
                outer = list(re.finditer(rb'for[ \t]*\([^\r\n]*uiCiv[^\r\n]*MAX_MAJOR_CIVS[^\r\n]*\)', body[:span['offset']]))[-1].group()
                statement = outer+b' {\n'+statement+b'\n}\n'
            output.append(statement)
        parts.append(('void '+GROUPS[row['cpp']]+'(FDataStream& '+stream+') const {\n').encode())
        if stream == 'saveTo': parts.append(b'const DirectEntryProbes& readFrom = *this;\n')
        parts += [guards, b'\n'.join(output), b'\n}\n']
    parts.append(b'''};
static_assert(std::is_same<std::vector<int>::size_type,std::size_t>::value,"Native vector size type changed");
static_assert(std::is_same<std::list<DirectOpaqueElement>::size_type,std::size_t>::value,"Native list size type changed");
#endif
''')
    path.write_bytes(b'\n'.join(parts))
    return dict(generated=artifact(path), writer_bodies=comparisons, count_fragments=traces,
        popup_headers=popup_headers, popup_vector_declarations_equal=True,
        popup_vector_declarations_sha256=hashlib.sha256(b'\n'.join(popup_fields)).hexdigest(),
        full_popup_body_retained_verbatim=True, full_popup_types='Seven std::vector<int>, one std::vector<CvString>; actual SDK CvString/std::string codec',
        non_popup_scope='Exact entry guards/count statements/loop headers; loop bodies are visit counters, not record payloads',
        element_mocks='Opaque non-Popup records affect neither default-allocator size_type nor count/loop oracle; no payload/record ABI claim',
        uint_storage_shims='Army FormationEntries and Economic RequestedSavings only; explicit unsigned-int size return, no allocator/capacity claim',
        hash_resolution='Not performed; fragments omit all unrelated payloads/hash resolution',
        overflow_scope='Authenticated entry preflights with matching native-size or unsigned-int fake queries, before any stream write',
        signed_and_unsigned_policies={str(PATHS[s['local']]):s['checked_type'] for r in plan['file_plans'] for s in r['sites']},
        sources=sources)


def main():
    require(len(sys.argv) == 1 and not sys.flags.optimize, 'Unexpected direct-count verifier arguments')
    require(artifact(PLAN)['sha256'] == PLAN_SHA, 'Reviewed direct-count patch plan changed')
    tracking = STAGE/'port_patch_tracking.json'
    require(artifact(tracking)['sha256'] == '24240fb57d0758f2580468f84d61b99163596046e58caab364688eb51313aa7d',
        'Reviewed source/manifest application receipt changed')
    plan = json.loads(PLAN.read_text(encoding='utf-8'))
    require(len(plan['file_plans']) == 8 and sum(len(r['sites']) for r in plan['file_plans']) == 18, 'Finite source set changed')
    for path, sha in AUDITS: require(artifact(path)['sha256'] == sha, 'Finite read-only count inventory changed')
    source_paths = [TEST, PLAN, tracking, *[p for p, _ in AUDITS], MANIFEST_TOOL, Path(__file__).absolute(),
        PROJECT/'Source/Porting/CvCheckedNarrow.h', PROJECT/'Source/Providers/Streams/SdkStreamIncludes.h',
        PROJECT/'Tests/sdk_stream_reference_host.cpp', PROJECT/'Source/Porting/sdk_x64_patches.json',
        PROJECT/'evidence/sdk_x64/port_manifest.json', *[PROJECT/'tools'/name for name in
            ('verify_sdk_player_traits_count.py', 'verify_sdk_type_array_count.py', 'verify_retail_save_header.py',
             'verify_retail_save_state.py', 'native_build.py', 'collect_baseline.py')]]
    for row in plan['file_plans']:
        for sdk in ('SDK_BNW_Original', 'SDK_BNW_x64'):
            source_paths += [cpp_path(sdk,row['cpp']), cpp_path(sdk,row['cpp']).with_suffix('.h')]
    for sdk in ('SDK_BNW_Original', 'SDK_BNW_x64'):
        source_paths += [cpp_path(sdk, 'CvGameCoreEnums.h')]
        source_paths += [PROJECT/'Source'/sdk/'CvGameCoreDLLUtil/include'/name for name in
            ('CvEnums.h', 'CvEnumSerialization.h', 'CvDLLUtilDefines.h', 'CvString.h', 'CvAssert.h')]
        source_paths += [PROJECT/'Source'/sdk/'FirePlace/include/FireWorks'/name for name in
            ('FDataStream.h', 'FMemoryStream.h', 'FStlContainerSerialization.h', 'FArray.h', 'FFastVector.h')]
    source_paths += [p for rows in LIBRARIES.values() for p, _ in rows]
    inputs = [artifact(p) for p in source_paths]
    for rows in LIBRARIES.values():
        for path, expected in rows: require(artifact(path)['sha256'] == expected, 'Reviewed SDK stream/enum library changed')
    require(artifact(MANIFEST_TOOL)['sha256'] == MANIFEST_TOOL_SHA, 'Current Windows manifest tool changed')
    compilers = [artifact(CL86), artifact(COMPILER)]
    require(compilers[0]['sha256'] == CL86_SHA and compilers[1]['sha256'] == COMPILER_SHA, 'Reviewed compiler changed')
    manifest = json.loads((PROJECT/'evidence/sdk_x64/port_manifest.json').read_text(encoding='utf-8'))
    tracked = {key(row['port']):row['port_sha256'] for row in manifest}
    require(all(tracked.get(key(cpp_path('SDK_BNW_x64',r['cpp']))) == r['after_sha256'] for r in plan['file_plans']),
        'Port manifest does not include the frozen candidate sources')
    identifier = hashlib.sha256(json.dumps(dict(inputs=inputs, compilers=compilers), sort_keys=True).encode()).hexdigest()[:16]
    root = PROJECT/'Build/SdkDirectStreamCounts'/identifier
    if REPORT.exists():
        old = json.loads(REPORT.read_text(encoding='utf-8'))
        require(old['inputs'] == inputs and old['status'] == 'PASS_SDK_DIRECT_STREAM_COUNT_ABI_COMPONENT', 'Inspect prior direct-count proof first')
        for row in old['results']: require(artifact(row['executable']['path']) == row['executable'], 'Retained executable changed')
        for row in old['canonical_wires']: require(artifact(row['path']) == row, 'Retained canonical Popup wire changed')
        print(json.dumps(dict(status=old['status'], reused=True))); return
    require(not root.exists(), 'Inspect partial direct-count build before retrying')
    protected = [artifact(PROJECT/name) for name in ('Play/EarlyAccess/release.json',
        'evidence/save_menu/20261013_original_screen/current_progress.json',
        'evidence/goody_hut/runtime_fonts/preparation_identity_audit.json', 'evidence/goody_hut/runtime_fonts/system_freeze_hold.json',
        'evidence/serialization/player_traits_count/build_result.json', 'docs/M7_RETAIL_SAVE_BOUNDARY.md')]
    for part in (root, *root.parents, STAGE, *STAGE.parents):
        if part.exists(): require(not part.lstat().st_file_attributes & 0x400, 'Reparse output path')
    root.parent.mkdir(parents=True, exist_ok=True)
    setup = root/'read_build_environment.cmd'
    allowed, calls = {('cmd.exe', '/d', '/c', str(setup))}, []
    def audit(event, args):
        if event == 'subprocess.Popen':
            command = next((x for x in allowed if subprocess.list2cmdline(x) == args[1]), None) \
                if isinstance(args[1], str) else tuple(str(x) for x in args[1])
            require(command in allowed, 'Unapproved direct-count child command')
            require(args[0] is None or key(args[0]) == key(command[0]) or
                Path(args[0]).name.casefold() == command[0].casefold() == 'cmd.exe', 'Unexpected executable override')
            calls.append(command)
        if event == 'open' and args and isinstance(args[0], (str, bytes, os.PathLike)):
            writing = isinstance(args[1], str) and any(c in args[1] for c in 'wax+') or \
                isinstance(args[2], int) and args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
            if writing: require(within(os.fsdecode(args[0]), root) or within(os.fsdecode(args[0]), STAGE), 'Write escaped owned outputs')
        if event in ('os.remove','os.rmdir','os.mkdir','os.rename','os.chmod','os.link','os.symlink'):
            for target in (args[:2] if event in ('os.rename','os.link','os.symlink') else args[:1]):
                if isinstance(target,(str,bytes,os.PathLike)): require(within(os.fsdecode(target),root),'Mutation escaped owned build')
        if event.startswith(('ctypes.dlopen','socket.','urllib.','http.client.')) or event in ('os.system','os.startfile','os.startfile/2'):
            raise RuntimeError('Network, dynamic loading and interactive launches forbidden')
    sys.addaudithook(audit)
    root.mkdir(); results, retired, canonical, consumed = [], [], [], {}
    try:
        generated = generate(root/'SdkDirectStreamCounts.h', plan)
        (STAGE/'native_build_started.json').write_text(json.dumps(dict(build_root=str(root),inputs=inputs,protected=protected),indent=2)+'\n',encoding='utf-8')
        environment64, selected = environment_for(VS,'x64',root); require(key(selected)==key(COMPILER),'Compiler selection changed')
        for arch, flavor, optimization in (('x86','O2',['/O2']),('x64','O2',['/O2']),('x64','Od',['/Od','/RTC1'])):
            out=root/(arch+'_'+flavor);out.mkdir()
            sdk=PROJECT/('Source/SDK_BNW_Original' if arch=='x86' else 'Source/SDK_BNW_x64')
            if arch=='x86':
                env={k.upper():v for k,v in os.environ.items()};env['INCLUDE']=str(VC9/'include')+';'+str(WIN7/'Include')
                env['LIB']=str(VC9/'lib')+';'+str(WIN7/'Lib')
                env['PATH']=';'.join([str(VC9/'bin'),str(VC9.parent/'Common7/IDE'),str(WIN7/'bin'),env.get('PATH','')]);compiler=CL86
            else: env,compiler=environment64.copy(),COMPILER
            env['VSLANG']='1033';env['TMP']=env['TEMP']=str(out)
            includes=[sdk/'FirePlace/include',sdk/'CvGameCoreDLLUtil/include',sdk/'CvGameCoreDLL_Expansion2']
            own=[PROJECT/'Source/Providers/Streams',PROJECT/'Source/Porting',root]
            flags=['/nologo','/EHsc','/MD','/fp:strict','/D_CRT_SECURE_NO_WARNINGS','/DFINAL_RELEASE','/D_SECURE_SCL=0','/D_HAS_ITERATOR_DEBUGGING=0',*optimization]
            flags+=(['/W3','/wd4819']+[f'/I"{p}"' for p in includes+own]) if arch=='x86' else (
                ['/std:c++14','/W4','/WX','/D_SILENCE_STDEXT_HASH_DEPRECATION_WARNINGS','/external:W0']+
                [f'/external:I"{p}"' for p in includes]+[f'/I"{p}"' for p in own])
            sources=[TEST]+([PROJECT/'Tests/sdk_stream_reference_host.cpp'] if arch=='x86' else [])
            objects,dependencies,logs,responses=[],[],[],[]
            for source in sources:
                obj,response=out/(source.stem+'.obj'),out/(source.stem+'.rsp');dep=out/(source.stem+'.dependencies.json')
                args=[*flags,'/c',f'"{source}"',f'/Fo"{obj}"']+(['/showIncludes'] if arch=='x86' else [f'/sourceDependencies "{dep}"'])
                response.write_text('\n'.join(args)+'\n',encoding='ascii');command=[str(compiler),'@'+str(response)];allowed.add(tuple(command))
                built=run_low(command,cwd=out,env=env,timeout=120);text=(built.stdout+built.stderr).decode('mbcs',errors='replace')
                log=STAGE/(arch+'_'+flavor+'_'+source.stem+'.log');log.write_text(text,encoding='utf-8')
                require(built.returncode==0 and not re.search(r'\bwarning\s+[A-Z]+\d+',text,re.I),'Compile failed: '+log.name)
                if arch=='x64':
                    data=json.loads(dep.read_text(encoding='utf-8-sig'))['Data']
                    needed=[root/'SdkDirectStreamCounts.h',PROJECT/'Source/Porting/CvCheckedNarrow.h',
                        sdk/'CvGameCoreDLLUtil/include/CvString.h',sdk/'CvGameCoreDLL_Expansion2/CvGameCoreEnums.h']
                    require(key(data['Source'])==key(source) and all(any(key(x)==key(h) for x in data['Includes']) for h in needed),'Actual header consumption mismatch')
                    require(not any('sdk_bnw_original' in key(x) or ('cvgamecoredll_expansion2' in key(x) and
                        key(x)!=key(sdk/'CvGameCoreDLL_Expansion2/CvGameCoreEnums.h')) for x in data['Includes']),'Unexpected full GameCore include')
                    includes_seen=data['Includes'];dependencies.append(artifact(dep))
                else:
                    if source==TEST:require(str(root/'SdkDirectStreamCounts.h').casefold() in text.casefold(),'Original writer header not consumed')
                    includes_seen=[m.group(1) for line in text.splitlines() if (m:=re.search(r'([A-Za-z]:[\\/].*\.(?:h|hpp|inl|inc))\s*$',line,re.I))]
                for included in includes_seen:
                    if within(included,PROJECT):
                        row=artifact(Path(included));previous=consumed.get(key(included))
                        require(previous is None or (key(previous['path'])==key(row['path']) and
                            previous['bytes']==row['bytes'] and previous['sha256']==row['sha256']),
                            'Consumed header content changed between modes')
                        # Compiler include traces may spell the same header with
                        # a relative parent segment or different path casing.
                        consumed.setdefault(key(included),row)
                objects.append(artifact(obj));logs.append(artifact(log));responses.append(artifact(response))
            exe,linkmap=out/'SdkDirectStreamCountsTests.exe',out/'SdkDirectStreamCountsTests.map'
            link=['/nologo','/INCREMENTAL:NO','/OPT:REF','/OPT:ICF','/DYNAMICBASE','/NXCOMPAT','/MACHINE:'+arch.upper(),'/MAP:'+str(linkmap)]
            link+=['/LTCG'] if arch=='x86' else ['/Brepro','/WX']
            command=[str(compiler.with_name('link.exe')),'/OUT:'+str(exe),*[x['path'] for x in objects],*[str(p) for p,_ in LIBRARIES[arch]],*link,
                *[n+'.lib' for n in ('kernel32','user32','advapi32','psapi','dbghelp','ole32','shell32','winmm')]]
            allowed.add(tuple(command));linked=run_low(command,cwd=out,env=env,timeout=120);text=(linked.stdout+linked.stderr).decode('mbcs',errors='replace')
            log=STAGE/(arch+'_'+flavor+'_link.log');log.write_text(text,encoding='utf-8');require(linked.returncode==0 and not re.search(r'\bwarning\s+[A-Z]+\d+',text,re.I),'Link failed: '+log.name)
            manifest_file=exe.with_suffix('.exe.manifest')
            if arch=='x86' and manifest_file.exists():
                command=[str(MANIFEST_TOOL),'-nologo','-manifest',str(manifest_file),'-outputresource:'+str(exe)+';1'];allowed.add(tuple(command))
                require(run_low(command,cwd=out,env=env,timeout=30).returncode==0,'Current manifest tool embed failed')
            identity,pe,imported=artifact(exe),pe_header(exe),imports(exe)
            image=exe.read_bytes();pe_offset=struct.unpack_from('<I',image,0x3c)[0];dll_characteristics=struct.unpack_from('<H',image,pe_offset+94)[0]
            require(pe['architecture']==arch and pe['pe_format']==('PE32' if arch=='x86' else 'PE32+') and not pe['is_dll'] and
                dll_characteristics&0x140==0x140 and not any('civilization' in name or 'gamecore' in name for name in imported),'Unsafe executable PE/imports/ASLR/NX')
            mapping=linkmap.read_text(encoding='mbcs',errors='replace');require('FMemoryStream' in mapping and
                ('FireWorksWin32' if arch=='x86' else 'ZeroSis_Streams_x64') in mapping,'Actual archived/current stream provider absent')
            command=[str(exe),'--x86original' if arch=='x86' else '--x64'];allowed.add(tuple(command))
            tested=subprocess.run(command,cwd=out,env=env,capture_output=True,timeout=60,
                creationflags=subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS)
            text=(tested.stdout+tested.stderr).decode('utf-8',errors='replace').strip();log=STAGE/(arch+'_'+flavor+'_test.log');log.write_text(text+'\n',encoding='utf-8')
            require(tested.returncode==0 and artifact(exe)==identity,'Native direct-count test failed or executable changed');result=json.loads(text)
            require(result['status']=='PASS_SDK_DIRECT_STREAM_COUNTS' and result['source_count_paths']==18 and result['typed_fragment_paths']==10 and
                result['popup_full_body_cases']==3 and result['canonical_count_bytes']==4 and result['typed_fragment_loop_headers_exercised'] and
                result['legacy_size_t_count_bytes']==(0 if arch=='x86' else 8) and result['oversized_preflight_rejections']==(0 if arch=='x86' else 113) and
                result['inclusive_limit_cases']==(0 if arch=='x86' else 39) and all(result[name] is False for name in
                    ('non_popup_payloads_verified','hash_resolution_performed','gamecore_loaded','window_created','user_saves_accessed',
                     'complete_save_validated','ruleset_compatibility_verified','restore_approved')),'Native direct-count scope differs')
            wires=[artifact(out/('canonical_popup_'+str(i)+'.bin')) for i in range(3)]
            if not canonical: canonical=wires
            else:require(all(Path(a['path']).read_bytes()==Path(b['path']).read_bytes() for a,b in zip(canonical,wires)),'Original/fixed full Popup wires differ')
            results.append(dict(arch=arch,flavor=flavor,executable=identity,pe=pe,imports=imported,dll_characteristics_hex=hex(dll_characteristics),
                executable_attested_before_launch=True,objects=objects,dependencies=dependencies,responses=responses,map=artifact(linkmap),
                compile_logs=logs,test_log=artifact(log),test=result,canonical_wires=wires,
                legacy_wires=[artifact(out/('legacy64_popup_'+str(i)+'.bin')) for i in range(3)] if arch=='x64' else []))
        require(inputs==[artifact(x['path']) for x in inputs] and protected==[artifact(x['path']) for x in protected] and
            all(artifact(row['path'])==row for row in consumed.values()),'Inputs/consumed headers/protected evidence changed')
        discard=[(Path(o['path']),'completed compiler object') for r in results for o in r['objects']]+[(setup,'completed environment setup')]
        # These exact import/export byproducts belong to the newly linked test
        # executable. Retained input libraries under Build/Serialization and
        # Build/Streams_provider are never cleanup candidates.
        discard += [(Path(r['executable']['path']).with_suffix(suffix), 'owned executable export byproduct')
            for r in results for suffix in ('.exp','.lib') if Path(r['executable']['path']).with_suffix(suffix).exists()]
        discard += [(Path(w['path']),'identical canonical wire compared byte-for-byte') for r in results if r['arch']=='x64' for w in r['canonical_wires']]
        discard += [(Path(w['path']),'negative-control wire authenticated before retirement') for r in results for w in r['legacy_wires']]
        for path,reason in discard:
            info=path.stat();require(within(path,root) and info.st_nlink==1 and not info.st_file_attributes&0x400,'Unexpected cleanup identity')
            row=dict(**artifact(path),file_identity=[info.st_dev,info.st_ino],mtime_ns=info.st_mtime_ns,reason=reason)
            require(artifact(path)=={k:row[k] for k in ('path','bytes','sha256')},'Cleanup target changed');path.unlink();retired.append(row)
        report=dict(schema='zerosis.sdk.direct_stream_counts.v1',status='PASS_SDK_DIRECT_STREAM_COUNT_ABI_COMPONENT',utc=datetime.now(timezone.utc).isoformat(),
            build_root=str(root),inputs=inputs,compilers=compilers,generated_extracts=generated,results=results,canonical_wires=canonical,
            all_canonical_popup_wires_byte_identical=True,consumed_project_headers=list(consumed.values()),protected=protected,protected_unchanged=True,
            child_commands=[list(x) for x in calls],retired_intermediates=retired,retired_logical_bytes=sum(r['bytes'] for r in retired),
            full_popup_writer_exercised=True,other_ten_count_fragments_only=True,actual_eight_translation_units_built=False,
            canonical_count_bytes_by_path=[4]*18,
            legacy64_count_bytes_by_path=[4 if path in (8,11,17) else 8 for path in range(18)],
            unsigned_reader_paths=[10,16],
            original_install_or_user_saves_accessed=False,public_save_or_body_retained=False,host_gamecore_or_hwnd_executed=False,
            full_sdk_recompiled=False,integrated_into_current_host=False,sdk_restore_verified=False,full_player_framed=False,
            ruleset_compatibility_verified=False,full_engine_goal_complete=False,previous_goal_turn_classification='progress')
        REPORT.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(dict(status=report['status'],checks=[r['test']['checks'] for r in results],retired_bytes=report['retired_logical_bytes'],report=artifact(REPORT))))
    except BaseException as error:
        (STAGE/'native_failed_attempt.json').write_text(json.dumps(dict(status='FAILED_SDK_DIRECT_STREAM_COUNTS',error=type(error).__name__+': '+str(error),
            build_root=str(root),inputs=inputs,completed_modes=results,retired_intermediates=retired,
            protected_unchanged=protected==[artifact(x['path']) for x in protected]),indent=2)+'\n',encoding='utf-8');raise


if __name__ == '__main__':
    main()
