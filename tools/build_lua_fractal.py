"""Build exact Fractal Lua bodies with instrumented lifetime and real calculation variants."""
import argparse,json,re
from pathlib import Path
from collect_baseline import PROJECT,read_text,pe_header
from native_build import environment_for,run,checked_run
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts
from build_bootstrap_component import body
from define_lua_fractal_patches import BASE,SOURCE,baseline_text,candidate_text

SIGNATURES=('bool HasFlag(', 'int GetFractalFlags(', 'void CvLuaFractal::Register(',
    'int CvLuaFractal::pRegister(', 'int CvLuaFractal::lBuildRidges(', 'CvFractal* CvLuaFractal::CreateFractal(',
    'int CvLuaFractal::lCreate(', 'int CvLuaFractal::lCreateRifts(', 'int CvLuaFractal::lDestroy(', 'int CvLuaFractal::lGetHeight(')


def fixture_texts():
    root=PROJECT/'Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2'
    original,candidate=baseline_text(),candidate_text()
    header=(root/'CvFractal.h').read_bytes().decode('latin1')
    lua_header=(root/'Lua/CvLuaFractal.h').read_bytes().decode('latin1')
    code=(root/'CvFractal.cpp').read_bytes().decode('latin1')
    utils_h=(root/'CvGameCoreUtils.h').read_bytes().decode('latin1')
    utils_c=(root/'CvGameCoreUtils.cpp').read_bytes().decode('latin1')
    helpers='\n'.join(body(utils_h,s) for s in ('inline int xToHexspaceX(', 'inline int hexDistance('))+'\n'+body(utils_c,'DirectionTypes estimateDirection(')
    calculation=re.sub(r'^#include[^\r\n]*','',code,flags=re.M)
    lua=lua_header.replace('protected:','public:')+'\n#ifdef LUA_FRACTAL_ORIGINAL\n'+'\n'.join(body(original,s) for s in SIGNATURES)+'\n#else\n'+'\n'.join(body(candidate,s) for s in SIGNATURES)+'\n#endif\n'
    texts={'fractal_lua_fixture.h':lua,'fractal_calculation_fixture.h':helpers+'\n'+calculation,
        'fractal_class_fixture.h':header,'fractal_enum_fixture.h':body(header,'enum FracVals')+';\n'}
    sources=[root/n for n in ('CvFractal.h','CvFractal.cpp','CvGameCoreUtils.h','CvGameCoreUtils.cpp','Lua/CvLuaFractal.h')]
    return {k:v.replace('\r\n','\n') for k,v in texts.items()},sources


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--production',action='store_true');args=parser.parse_args()
    root=PROJECT/'evidence/lua_fractal';root.mkdir(parents=True,exist_ok=True)
    out=PROJECT/'Build/LuaFractal/x64';out.mkdir(parents=True,exist_ok=True);sdk=PROJECT/'Source/SDK_BNW_x64'
    if args.production and (sdk/SOURCE).read_bytes().decode('latin1')!=candidate_text():raise RuntimeError('Compiled SDK differs from Fractal candidate')
    texts,sources=fixture_texts()
    for name,text in texts.items():(out/name).write_text(text,encoding='utf-8',newline='\n')
    reports={name:json.loads((PROJECT/('evidence/'+name+'/build_result.json')).read_text(encoding='utf-8-sig')) for name in ('lua_provider','flua')}
    inputs=[reports['lua_provider']['library'],reports['flua']['library'],reports['flua']['foundation_provider']['library']];check_artifacts(inputs)
    builds={};audits=[]
    for variant in ('original','candidate','original_od','candidate_od','original_math','candidate_math'):
        directory=out/variant;env,compiler=environment_for(Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community'),'x64',directory)
        compiler=Path(compiler);env['VSLANG']='1033'
        exe=directory/('lua_fractal_'+variant+'.exe');mapfile=directory/'fractal.map';deps=directory/'dependencies.json'
        optimization='/Od' if variant.endswith('_od') else '/O2'
        flags=['/nologo','/std:c++14','/EHsc','/W4','/WX',optimization,'/MD','/utf-8','/external:W0',
            '/DWIN32','/DFINAL_RELEASE','/D_CRT_SECURE_NO_WARNINGS','/D_SILENCE_STDEXT_HASH_DEPRECATION_WARNINGS','/D_SILENCE_TR1_NAMESPACE_DEPRECATION_WARNING']
        if variant.startswith('original'):flags+=['/DLUA_FRACTAL_ORIGINAL']
        if not variant.endswith('_math'):flags+=['/DFRACTAL_LIFETIME_FIXTURE']
        flags += [f'/I"{p}"' for p in (out,PROJECT/'Source/Porting',PROJECT/'Source/Providers/FLua')]
        flags += [f'/external:I"{sdk/p}"' for p in ('ThirdPartyLibs/Lua51/include','FirePlace/include','FirePlace/include/FireWorks/Flua/include')]
        flags += [f'"{PROJECT/"Tests/sdk_lua_fractal.cpp"}"',*[f'"{r["path"]}"' for r in inputs],f'/Fo"{directory/"fractal.obj"}"',f'/Fe"{exe}"',f'/sourceDependencies "{deps}"']
        rsp=directory/'compile.rsp';rsp.write_text('\n'.join(flags)+'\n',encoding='utf-8')
        result=run([compiler,'@'+str(rsp),'/link','/INCREMENTAL:NO','/MACHINE:X64','/Brepro','/WX','/OPT:REF','/OPT:ICF','/MAP:'+str(mapfile),'kernel32.lib'],cwd=directory,env=env,timeout=180)
        log=root/(variant+'_build.log');log.write_bytes(result.stdout+result.stderr)
        if result.returncode or re.search(r'\bwarning\s+[A-Z]+\d+',read_text(log)):raise RuntimeError(read_text(log)[-6500:])
        result=checked_run([compiler.with_name('dumpbin.exe'),'/dependents',exe],cwd=directory,env=env)
        ilog=root/(variant+'_imports.log');ilog.write_bytes(result.stdout+result.stderr)
        imports=re.findall(r'^\s+([\w.-]+\.dll)\s*$',result.stdout.decode('ascii',errors='replace'),re.M|re.I)
        allowed={'kernel32.dll','msvcp140.dll','vcruntime140.dll','vcruntime140_1.dll'}
        if not imports or any(s.lower() not in allowed and not s.lower().startswith('api-ms-win-crt-') for s in imports):raise RuntimeError('Unexpected Fractal dependency: '+str(imports))
        audits.append({'module':artifact(exe),'dependencies':imports,'log':artifact(ilog)})
        consumed=json.loads(deps.read_text(encoding='utf-8-sig'))['Data']
        builds[variant]={'executable':{**artifact(exe),'pe':pe_header(exe)},'optimization':optimization,'compiler':artifact(compiler),
            'response':artifact(rsp),'log':artifact(log),'map':artifact(mapfile),'dependencies':artifact(deps),
            'compiler_inputs':[artifact(Path(p)) for p in [consumed['Source'],*consumed['Includes']]]}
    report={'status':'SDK_LUA_FRACTAL_COMPONENTS_BUILT','builds':builds,'audits':audits,'providers':inputs,
        'baseline':artifact(BASE),'fixtures':[artifact(out/n) for n in texts],'builder':artifact(Path(__file__).resolve()),
        'sources':[artifact(p) for p in [*sources,PROJECT/'Source/SDK_BNW_Original'/SOURCE,PROJECT/'Source/Porting/ZeroSisLuaFractal.h',
            PROJECT/'Tests/sdk_lua_fractal.cpp',PROJECT/'tools/define_lua_fractal_patches.py']],
        'exact_lua_function_bodies':list(SIGNATURES),'candidate_matches_generated_sdk':args.production,
        'gamecore_loaded':False,'game_launched':False,
        'scope':'EXACT_LUA_BINDINGS_REAL_LUA_FLUA; LIFETIME_SPY_AND_SEPARATE_CURRENT_CV_FRACTAL_CALCULATION_WITH_NUMERIC_RNG_STD_VECTOR_OWNER_ADAPTERS; NOT_WHOLE_GAMECORE'}
    if args.production:report['generated_sdk_source']=artifact(sdk/SOURCE)
    (root/'build_result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(report['status'])


if __name__=='__main__':main()
