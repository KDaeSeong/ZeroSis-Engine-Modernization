"""Compile exact SDK registration bodies with real Lua/FLua and instrumented owners."""
import argparse
import json
import re
from pathlib import Path
from collect_baseline import PROJECT, read_text, pe_header
from native_build import environment_for, run, checked_run
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts
from build_bootstrap_component import body
from define_lua_registration_patches import BASE, LUA, STATIC, FILES, baseline_text, candidate_text


def fixture_text():
    sources = {}; extracted = []; rosters = {}; pieces = []
    def get(source, signature, template=False, changed=False):
        original = baseline_text(source)
        candidate = candidate_text(source)
        sources[source] = candidate
        old, new = body(original, signature), body(candidate, signature)
        extracted.append({'file': source, 'signature': signature, 'original_body': old, 'candidate_body': new})
        prefix = 'template<class Derived, class InstanceType>\n' if template else ''
        if changed:
            return '#ifdef LUA_REGISTRATION_ORIGINAL\n' + prefix + old + '\n#else\n' + prefix + new + '\n#endif\n'
        if old != new:
            raise RuntimeError('Unexpected registration-body change: ' + signature)
        return prefix + new + '\n'
    pieces += ['''// Declarations and owners are instrumentation; function bodies below are exact SDK extracts.
template<class Derived, class InstanceType> class CvLuaStaticInstance {
public: static void Register(lua_State*);
protected: static int pRegister(lua_State*);
static void RegisterMethod(lua_State*, lua_CFunction, const char*);
};
''']
    for signature, changed in (
        ('void CvLuaStaticInstance<Derived, InstanceType>::Register(lua_State* L)', True),
        ('int CvLuaStaticInstance<Derived, InstanceType>::pRegister(lua_State* L)', False),
        ('void CvLuaStaticInstance<Derived, InstanceType>::RegisterMethod(', False)):
        pieces.append(get(STATIC, signature, template=True, changed=changed))
    scoped=LUA+'CvLuaScopedInstance.h'
    get(scoped, 'void CvLuaScopedInstance<Derived, InstanceType>::Push(lua_State* L, InstanceType* pkType)', template=True, changed=True)
    pieces.append('template<class Derived, class InstanceType> class CvLuaMethodWrapper {};\ntemplate<class T> class FObjectHandle;\n')
    pieces.append('#ifdef LUA_REGISTRATION_ORIGINAL\n'+baseline_text(scoped).replace('#include "CvLuaMethodWrapper.h"','')+
        '\n#else\n'+candidate_text(scoped).replace('#include "CvLuaMethodWrapper.h"','')+'\n#endif\n')
    definitions = []
    for c in ('Fractal','GameInfo','Map','Game','Player','Team'):
        cls = 'CvLua'+c; source = LUA+cls+'.cpp'; original = baseline_text(source)
        if c == 'GameInfo':
            pieces.append('class CvLuaGameInfo { public: static void Register(lua_State*); static int pRegisterActions(lua_State*); static int pRegisterTypesInfo(lua_State*); };\n')
            for signature in ('void CvLuaGameInfo::Register(lua_State* L)','int CvLuaGameInfo::pRegisterActions(', 'int CvLuaGameInfo::pRegisterTypesInfo('):
                definitions.append(get(source, signature, changed='::Register(' in signature))
            continue
        inherited = ' : public CvLuaStaticInstance<'+cls+', Cv'+c+'>' if c in ('Map','Game') else (
            ' : public CvLuaScopedInstance<'+cls+', Cv'+('PlayerAI' if c=='Player' else 'Team')+'>' if c in ('Player','Team') else '')
        signatures = []
        if c in ('Map','Game'):
            signature = 'void '+cls+'::RegisterMembers('
            declaration = 'static const char* GetInstanceName(); static void RegisterMembers(lua_State*);'
            signatures.append('const char* '+cls+'::GetInstanceName(')
        elif c in ('Player','Team'):
            signature = 'void '+cls+'::PushMethods('
            declaration = 'static void Register(lua_State*); static int pRegister(lua_State*); static const char* GetTypeName(); static void PushMethods(lua_State*, int);'
            signatures += ['void '+cls+'::Register(lua_State* L)','int '+cls+'::pRegister(', 'const char* '+cls+'::GetTypeName(']
        else:
            signature = 'int '+cls+'::pRegister('
            declaration = 'static void Register(lua_State*); static int pRegister(lua_State*);'
            signatures.append('void '+cls+'::Register(lua_State* L)')
        raw = body(original, signature)
        clean = re.sub(r'/\*.*?\*/|//[^\r\n]*','',raw,flags=re.S)
        names = ['Create','CreateRifts'] if c=='Fractal' else re.findall(r'\bMethod\s*\(\s*(\w+)\s*\)', clean)
        if not names or len(set(names)) != len(names):
            raise RuntimeError('Empty or duplicate SDK method metadata: '+c)
        rosters[c] = names
        stubs = '\n'.join('static int l'+n+'(lua_State* L) { ++gameplayFixtureCalls; lua_pushinteger(L,'+str(i+1)+'); return 1; }' for i,n in enumerate(names))
        pieces.append('class '+cls+inherited+' { public: '+declaration+'\n'+stubs+'\n};\n')
        for s in signatures: definitions.append(get(source,s,changed='::Register(' in s))
        macro = '#define Method(Name) RegisterMethod(L,l##Name,#Name);\n' if c in ('Map','Game') else (
            '#define Method(Name) lua_pushcclosure(L,l##Name,0); lua_setfield(L,t,#Name);\n')
        definitions.append(macro+get(source,signature,changed=c=='Fractal')+'\n#undef Method\n')
        metadata=''.join('{"'+n+'",'+cls+'::l'+n+'},\n' for n in names)
        if c=='Fractal':
            protected=''.join('{"'+n+'",ZeroSisLuaFractalNumeric::Protected<'+cls+'::l'+n+'>},\n' for n in names)
            metadata='#ifdef LUA_REGISTRATION_ORIGINAL\n'+metadata+'#else\n'+protected+'#endif\n'
        definitions.append('static const MethodSpec '+c+'Methods[] = {\n'+metadata+'};\n')
    pieces += definitions
    pieces.append(get(LUA+'CvLuaSupport.cpp','void LuaSupport::RegisterScriptData('))
    source='CvGameCoreDLLUtil/include/CvDLLUtilDefines.h'
    original=baseline_text(source); sources[source]=original
    defines='\n'.join(re.search(r'^#define\s+'+name+r'\s+[^\r\n]+',original,re.M)[0] for name in ('MAX_CIV_PLAYERS','MAX_PLAYERS','MAX_TEAMS'))
    text=defines+'\n'+''.join(pieces)
    return text.replace('\r\n','\n'), sources, extracted, rosters


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--production',action='store_true')
    args=parser.parse_args()
    root=PROJECT/'evidence/lua_registration';root.mkdir(parents=True,exist_ok=True)
    out=PROJECT/'Build/LuaRegistration/x64';out.mkdir(parents=True,exist_ok=True)
    sdk=PROJECT/'Source/SDK_BNW_x64'
    text,sources,extracted,rosters=fixture_text()
    if args.production:
        for source,expected in sources.items():
            if (sdk/source).read_bytes().decode('latin1')!=expected:
                raise RuntimeError('Generated SDK differs from registration candidate: '+source)
    fixture=out/'lua_registration_fixture.h';fixture.write_text(text,encoding='utf-8',newline='\n')
    report_inputs={name:json.loads((PROJECT/('evidence/'+name+'/build_result.json')).read_text(encoding='utf-8-sig')) for name in ('lua_provider','flua')}
    inputs=[report_inputs['lua_provider']['library'],report_inputs['flua']['library'],report_inputs['flua']['foundation_provider']['library']]
    check_artifacts(inputs)
    builds={};audits=[]
    for variant in ('original','candidate','original_od','candidate_od'):
        directory=out/variant;env,compiler=environment_for(Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community'),'x64',directory)
        compiler=Path(compiler);env['VSLANG']='1033'
        exe=directory/('lua_registration_'+variant+'.exe');mapfile=directory/'registration.map';deps=directory/'dependencies.json'
        optimization='/Od' if variant.endswith('_od') else '/O2'
        flags=['/nologo','/std:c++14','/EHsc','/W4','/WX',optimization,'/MD','/utf-8','/external:W0',
            '/DWIN32','/DFINAL_RELEASE','/D_CRT_SECURE_NO_WARNINGS','/D_SILENCE_STDEXT_HASH_DEPRECATION_WARNINGS','/D_SILENCE_TR1_NAMESPACE_DEPRECATION_WARNING']
        if variant.startswith('original'):flags+=['/DLUA_REGISTRATION_ORIGINAL']
        flags += [f'/I"{p}"' for p in (out,PROJECT/'Source/Porting',PROJECT/'Source/LuaBorrowed',PROJECT/'Source/Providers/FLua')]
        flags += [f'/external:I"{sdk/p}"' for p in ('ThirdPartyLibs/Lua51/include','FirePlace/include','FirePlace/include/FireWorks/Flua/include')]
        flags += [f'"{PROJECT/"Tests/sdk_lua_registration.cpp"}"',*[f'"{r["path"]}"' for r in inputs],f'/Fo"{directory/"registration.obj"}"',f'/Fe"{exe}"',f'/sourceDependencies "{deps}"']
        rsp=directory/'compile.rsp';rsp.write_text('\n'.join(flags)+'\n',encoding='utf-8')
        result=run([compiler,'@'+str(rsp),'/link','/INCREMENTAL:NO','/MACHINE:X64','/Brepro','/WX','/OPT:REF','/OPT:ICF','/MAP:'+str(mapfile),'kernel32.lib'],cwd=directory,env=env,timeout=180)
        log=root/(variant+'_build.log');log.write_bytes(result.stdout+result.stderr)
        if result.returncode or re.search(r'\bwarning\s+[A-Z]+\d+',read_text(log)):
            raise RuntimeError(read_text(log)[-6500:])
        result=checked_run([compiler.with_name('dumpbin.exe'),'/dependents',exe],cwd=directory,env=env)
        ilog=root/(variant+'_imports.log');ilog.write_bytes(result.stdout+result.stderr)
        imports=re.findall(r'^\s+([\w.-]+\.dll)\s*$',result.stdout.decode('ascii',errors='replace'),re.M|re.I)
        allowed={'kernel32.dll','msvcp140.dll','vcruntime140.dll','vcruntime140_1.dll'}
        if not imports or any(s.lower() not in allowed and not s.lower().startswith('api-ms-win-crt-') for s in imports):
            raise RuntimeError('Unexpected registration component dependency: '+str(imports))
        audits.append({'module':artifact(exe),'dependencies':imports,'log':artifact(ilog)})
        consumed=json.loads(deps.read_text(encoding='utf-8-sig'))['Data']
        builds[variant]={'executable':{**artifact(exe),'pe':pe_header(exe)},'optimization':optimization,'compiler':artifact(compiler),
            'response':artifact(rsp),'log':artifact(log),'map':artifact(mapfile),'dependencies':artifact(deps),
            'compiler_inputs':[artifact(Path(p)) for p in [consumed['Source'],*consumed['Includes']]]}
    report={'status':'SDK_LUA_REGISTRATION_COMPONENTS_BUILT','builds':builds,'audits':audits,'providers':inputs,
        'baseline':artifact(BASE),'fixture':artifact(fixture),'builder':artifact(Path(__file__).resolve()),
        'sources':[artifact(PROJECT/'Tests/sdk_lua_registration.cpp'),artifact(PROJECT/'tools/define_lua_registration_patches.py'),
            artifact(PROJECT/'Source/LuaBorrowed/ZeroSisLuaBorrowed.h'),
            *[artifact(PROJECT/'Source/SDK_BNW_Original'/s) for s in sources]],
        'extracted_bodies':extracted,'method_rosters':rosters,
        'entire_scoped_template_included':True,
        'candidate_matches_generated_sdk':args.production,'gamecore_loaded':False,'game_launched':False,
        'scope':'EXACT_SIX_REGISTRAR_BODIES_METHOD_LISTS_STATIC_AND_SCOPED_TEMPLATES_SEQUENCE_REAL_LUA_FLUA; INSTRUMENTED_GAME_OWNERS_AND_GAMEPLAY_METHODS_ENUM_SEQUENCE_STUB'}
    if args.production:report['generated_sdk_sources']=[artifact(sdk/s) for s in sources]
    (root/'build_result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'exact_bodies':len(extracted),'methods':{k:len(v) for k,v in rosters.items()}}))


if __name__=='__main__':main()
