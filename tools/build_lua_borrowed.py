"""Build exact original/candidate Lua binding templates with instrumented owners."""
import argparse
import json
import re
from pathlib import Path
from collect_baseline import PROJECT, read_text, pe_header
from native_build import environment_for, run, checked_run
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts
from build_bootstrap_component import body
from define_lua_borrowed_patches import BASE, LUA, ROOT, SCOPED, IS_NONE, baseline_text, candidate_text


TYPES = ('Area', 'City', 'Deal', 'League', 'Plot', 'Unit', 'Player', 'Team', 'TeamTech')


def fixture_text():
    old = baseline_text(SCOPED)
    new = candidate_text(SCOPED)
    sections = ['template<class Derived, class T> class CvLuaMethodWrapper {};\n',
                'template<class T> class FObjectHandle;\n',
                '#ifdef LUA_BORROWED_ORIGINAL\n'+old.replace('#include "CvLuaMethodWrapper.h"', '')+
                '\n#else\n'+new.replace('#include "CvLuaMethodWrapper.h"', '')+'\n#endif\n']
    extracted = [dict(file=SCOPED, original_body=old, candidate_body=new)]
    sources = {SCOPED: new}
    for name in TYPES:
        native = 'Cv'+dict(Player='PlayerAI', TeamTech='TeamTechs').get(name, name)
        cls = 'CvLua'+name
        source = LUA+cls+'.cpp'
        old, new = baseline_text(source), candidate_text(source)
        sources[source] = new
        members = 'int marker = 0; int GetID() const { return marker; } int getOwner() const { return marker; } int GetFromPlayer() const { return marker; }'
        if name == 'Unit':
            members += '''
    ~CvUnit(); void uninit(); void uninitInfos() { UnitUninitObserved(this); }
    struct ThisHandle { void ignoreDestruction(bool) {} } m_thisHandle;
    struct Promotions { void Uninit() {} } m_Promotions;
    std::vector<int> m_missionQueue, m_kLastPath;
    int* m_pReligion = NULL;
    int m_iMapLayer = 0, m_iX = 0, m_iY = 0;
    int GetIDInfo() { return marker; }
'''
        if name in ('Deal', 'League', 'TeamTech'):
            members += ' ~'+native+'();'
        if name == 'Deal':
            members += '''
    CvDeal& operator=(const CvDeal&);
    int m_eFromPlayer = 0, m_eToPlayer = 0, m_iDuration = 0, m_iFinalTurn = 0, m_iStartTurn = 0;
    int m_ePeaceTreatyType = 0, m_eSurrenderingPlayer = 0, m_eDemandingPlayer = 0, m_eRequestingPlayer = 0;
    bool m_bConsideringForRenewal = false, m_bCheckedForRenewal = false, m_bDealCancelled = false;
    TradedItemList m_TradedItems;
'''
        sections.append('struct '+native+' { '+members+' };\n')
        declaration = 'static int lIsNone(lua_State*);' if name in IS_NONE else ''
        sections.append('class '+cls+' : public CvLuaScopedInstance<'+cls+', '+native+'> {\npublic:\n'
            'static const char* GetTypeName();\n'
            'static void PushMethods(lua_State* L, int table) { Methods(L, table); }\n'
            'static void HandleMissingInstance(lua_State* L) { luaL_error(L, "Missing instrumented native owner"); }\n'+declaration+'\n};\n')
        signatures = ['const char* '+cls+'::GetTypeName(']
        if name in IS_NONE: signatures.append('int '+cls+'::lIsNone(')
        for sig in signatures:
            before, after = body(old, sig), body(new, sig)
            extracted.append(dict(file=source, signature=sig, original_body=before, candidate_body=after))
            sections.append('#ifdef LUA_BORROWED_ORIGINAL\n'+before+'\n#else\n'+after+'\n#endif\n')
    # Actual interface field declarations and method bodies; other interfaces are instruments.
    getters = dict(City=('int CvDllCity::GetID() const', 'int GetID() const;'),
        Unit=('int CvDllUnit::GetID() const', 'int GetID() const;'),
        Plot=('PlayerTypes CvDllPlot::GetOwner() const', 'PlayerTypes GetOwner() const;'),
        Deal=('PlayerTypes CvDllDeal::GetFromPlayer()', 'PlayerTypes GetFromPlayer();'))
    definitions = []
    utility_declarations = []
    for name in ('City', 'Unit', 'Plot', 'Deal'):
        header_source = ROOT+'CvDll'+name+'.h'
        header_old, header_new = baseline_text(header_source), candidate_text(header_source)
        sources[header_source] = header_new
        old_field = re.search(r'[^\r\n]*\bm_p'+name+r';', header_old)[0].strip()
        new_field = re.search(r'[^\r\n]*\bm_p'+name+r';', header_new)[0].strip()
        extracted.append(dict(file=header_source, original_body=old_field, candidate_body=new_field))
        sections.append('struct ICv'+name+'1 { virtual ~ICv'+name+'1() {} };\n')
        sections.append('class CvDll'+name+' : public ICv'+name+'1 { public:\n'
            'CvDll'+name+'(Cv'+name+'*); ~CvDll'+name+'(); Cv'+name+'* GetInstance(); '+getters[name][1]+
            (' void CopyFrom(ICvDeal1*);' if name == 'Deal' else '')+
            '\nprivate: unsigned int m_uiRefCount;\n#ifdef LUA_BORROWED_ORIGINAL\n'+old_field+'\n#else\n'+new_field+'\n#endif\n};\n')
        source = ROOT+'CvDll'+name+'.cpp'
        old, new = baseline_text(source), candidate_text(source)
        sources[source] = new
        for sig in ('CvDll'+name+'::CvDll'+name+'(', 'CvDll'+name+'::~CvDll'+name+'()', 'Cv'+name+'* CvDll'+name+'::GetInstance()', getters[name][0])+(
                ('void CvDllDeal::CopyFrom(',) if name == 'Deal' else ()):
            before, after = body(old, sig), body(new, sig)
            assert before == after
            extracted.append(dict(file=source, signature=sig, original_body=before, candidate_body=after))
            definitions.append(after+'\n')
        for operation in ('Push', 'Get'):
            result = 'void' if operation == 'Push' else 'ICv'+name+'1*'
            arguments = 'lua_State* L, ICv'+name+'1* p' if operation == 'Push' else 'lua_State* L, int index, bool bErrorOnFail'
            utility_declarations.append(result+' '+operation+'Cv'+name+'Instance('+arguments+');')
            source = ROOT+'CvDllScriptSystemUtility.cpp'
            old, new = baseline_text(source), candidate_text(source)
            sources[source] = new
            sig = result+' CvDllScriptSystemUtility::'+operation+'Cv'+name+'Instance('
            before, after = body(old, sig), body(new, sig)
            extracted.append(dict(file=source, signature=sig, original_body=before, candidate_body=after))
            definitions.append('#ifdef LUA_BORROWED_ORIGINAL\n'+before+'\n#else\n'+after+'\n#endif\n')
    sections.append('class CvDllScriptSystemUtility { public:\n'+'\n'.join(utility_declarations)+'\n};\n')
    for file, sig in [('CvUnit.cpp','CvUnit::~CvUnit()'), ('CvUnit.cpp','void CvUnit::uninit()'),
                      ('CvDealClasses.cpp','CvDeal::~CvDeal()'), ('CvVotingClasses.cpp','CvLeague::~CvLeague('),
                      ('CvTechClasses.cpp','CvTeamTechs::~CvTeamTechs('), ('CvDealClasses.cpp','CvDeal& CvDeal::operator=(')]:
        source = ROOT+file
        old, new = baseline_text(source), candidate_text(source)
        sources[source] = new
        before, after = body(old, sig), body(new, sig)
        extracted.append(dict(file=source, signature=sig, original_body=before, candidate_body=after))
        definitions.append('#ifdef LUA_BORROWED_ORIGINAL\n'+before+'\n#else\n'+after+'\n#endif\n')
    sections += definitions
    return ''.join(sections).replace('\r\n', '\n'), sources, extracted


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--production',action='store_true')
    args=parser.parse_args()
    root = PROJECT/'evidence/lua_borrowed'
    root.mkdir(parents=True, exist_ok=True)
    out = PROJECT/'Build/LuaBorrowed/x64'
    out.mkdir(parents=True, exist_ok=True)
    fixture, sources, extracted = fixture_text()
    if args.production:
        for source, expected in sources.items():
            if (PROJECT/'Source/SDK_BNW_x64'/source).read_bytes().decode('latin1') != expected:
                raise RuntimeError('Generated SDK differs from borrowed candidate: '+source)
    header = out/'lua_borrowed_fixture.h'
    header.write_text(fixture, encoding='utf-8', newline='\n')
    provider = json.loads((PROJECT/'evidence/lua_provider/build_result.json').read_text(encoding='utf-8'))['library']
    check_artifacts([provider])
    sdk = PROJECT/'Source/SDK_BNW_x64'
    builds = {}
    for variant in ('original', 'candidate', 'original_od', 'candidate_od'):
        directory = out/variant
        env, compiler = environment_for(Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community'), 'x64', directory)
        compiler = Path(compiler)
        env['VSLANG'] = '1033'
        exe, deps = directory/('lua_borrowed_'+variant+'.exe'), directory/'dependencies.json'
        optimization = '/Od' if variant.endswith('_od') else '/O2'
        flags = ['/nologo', '/std:c++14', '/EHsc', '/W4', '/WX', optimization, '/MD', '/utf-8', '/external:W0',
            '/DWIN32', '/DNOMINMAX', '/DFINAL_RELEASE', '/D_CRT_SECURE_NO_WARNINGS',
            '/D_SILENCE_STDEXT_HASH_DEPRECATION_WARNINGS', '/D_SILENCE_TR1_NAMESPACE_DEPRECATION_WARNING']
        if variant.startswith('original'): flags += ['/DLUA_BORROWED_ORIGINAL']
        flags += [f'/I"{p}"' for p in (out, PROJECT/'Source/LuaBorrowed', PROJECT/'Source/Porting')]
        flags += [f'/external:I"{sdk/p}"' for p in ('ThirdPartyLibs/Lua51/include', 'FirePlace/include/FireWorks')]
        peer_deps = directory/'peer_dependencies.json'
        peer_response = directory/'peer_compile.rsp'
        peer_response.write_text('\n'.join(flags+['/c', f'"{PROJECT/"Tests/sdk_lua_borrowed_peer.cpp"}"',
            f'/Fo"{directory/"peer.obj"}"', f'/sourceDependencies "{peer_deps}"'])+'\n', encoding='utf-8')
        peer_result = run([compiler, '@'+str(peer_response)], cwd=directory, env=env, timeout=180)
        peer_log = root/(variant+'_peer_build.log')
        peer_log.write_bytes(peer_result.stdout+peer_result.stderr)
        if peer_result.returncode or re.search(r'\bwarning\s+[A-Z]+\d+', read_text(peer_log)):
            raise RuntimeError(read_text(peer_log)[-6500:])
        flags += [
            f'"{PROJECT/"Tests/sdk_lua_borrowed.cpp"}"', f'"{provider["path"]}"',
            f'"{directory/"peer.obj"}"',
            f'/Fo"{directory/"borrowed.obj"}"', f'/Fe"{exe}"', f'/sourceDependencies "{deps}"']
        response = directory/'compile.rsp'
        response.write_text('\n'.join(flags)+'\n', encoding='utf-8')
        result = run([compiler, '@'+str(response), '/link', '/INCREMENTAL:NO', '/MACHINE:X64', '/Brepro', '/WX',
            '/OPT:REF', '/OPT:ICF', '/MAP:'+str(directory/'borrowed.map'), 'kernel32.lib'], cwd=directory, env=env, timeout=180)
        log = root/(variant+'_build.log')
        log.write_bytes(result.stdout+result.stderr)
        if result.returncode or re.search(r'\bwarning\s+[A-Z]+\d+', read_text(log)):
            raise RuntimeError(read_text(log)[-6500:])
        imports = checked_run([compiler.with_name('dumpbin.exe'), '/dependents', exe], cwd=directory, env=env)
        ilog = root/(variant+'_imports.log')
        ilog.write_bytes(imports.stdout+imports.stderr)
        dlls = re.findall(r'^\s+([\w.-]+\.dll)\s*$', imports.stdout.decode('ascii', errors='replace'), re.M|re.I)
        allowed = {'kernel32.dll', 'msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll'}
        if not dlls or any(s.lower() not in allowed and not s.lower().startswith('api-ms-win-crt-') for s in dlls):
            raise RuntimeError('Unexpected borrowed component dependency: '+str(dlls))
        consumed = json.loads(deps.read_text(encoding='utf-8-sig'))['Data']
        peer_consumed = json.loads(peer_deps.read_text(encoding='utf-8-sig'))['Data']
        builds[variant] = dict(executable={**artifact(exe), 'pe':pe_header(exe)}, optimization=optimization,
            compiler=artifact(compiler), response=artifact(response), log=artifact(log), map=artifact(directory/'borrowed.map'),
            dependencies=artifact(deps), imports=dlls, import_log=artifact(ilog),
            compiler_inputs=[artifact(Path(p)) for p in [consumed['Source'], *consumed['Includes']]],
            peer_response=artifact(peer_response), peer_log=artifact(peer_log), peer_object=artifact(directory/'peer.obj'),
            peer_dependencies=artifact(peer_deps),
            peer_compiler_inputs=[artifact(Path(p)) for p in [peer_consumed['Source'], *peer_consumed['Includes']]])
    report = dict(status='SDK_LUA_BORROWED_COMPONENTS_BUILT' if args.production else 'SDK_LUA_BORROWED_CANDIDATES_BUILT_NOT_INTEGRATED', builds=builds,
        fixture=artifact(header), baseline=artifact(BASE), providers=[provider], builder=artifact(Path(__file__).resolve()),
        sources=[artifact(PROJECT/'Tests/sdk_lua_borrowed.cpp'), artifact(PROJECT/'Tests/sdk_lua_borrowed_peer.cpp'), artifact(PROJECT/'Source/LuaBorrowed/ZeroSisLuaBorrowed.h'),
                 artifact(PROJECT/'tools/define_lua_borrowed_patches.py'),
                 *[artifact(PROJECT/'Source/SDK_BNW_Original'/s) for s in sources]],
        extracted_bodies=extracted, scoped_types=list(TYPES), candidate_matches_generated_sdk=args.production,
        native_gameplay_owner_lifecycle_executed=False, gamecore_loaded=False, game_launched=False,
        native_proxy_bodies_compiled=True, unit_destructor_body_with_instrumented_services_compiled=True,
        actual_sdk_container_header_compiled=True,
        scope='EXACT_SCOPED_TEMPLATE_SIX_IS_NONE_FOUR_PROXY_FIELDS_17_PROXY_BODIES_EIGHT_SCRIPT_GATEWAYS_FIVE_NATIVE_LIFECYCLE_BODIES_DEAL_ASSIGNMENT_REAL_LUA_AND_SDK_STATIC_VECTOR; INSTRUMENTED_GAMEPLAY_OWNERS_SERVICES_AND_TRADE_ITEM_LIST')
    if args.production: report['generated_sdk_sources']=[artifact(PROJECT/'Source/SDK_BNW_x64'/s) for s in sources]
    (root/'build_result.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'status':report['status'], 'variants':list(builds), 'extracted_units':len(extracted)}))


if __name__ == '__main__':
    main()
