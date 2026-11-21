"""Build native/Lua numeric Fractal candidates and isolated sanitizer probes."""
import argparse,json,re,shutil
from pathlib import Path
from collect_baseline import PROJECT,read_text,pe_header
from native_build import environment_for,run,checked_run
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts
from build_bootstrap_component import body
from build_lua_fractal import SIGNATURES
from define_fractal_numeric_patches import BASE,NATIVE,HEADER,LUA,baseline_text,candidate_text


def fixture_texts():
    root=PROJECT/'Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2'
    def select(old,new):return '#ifdef FRACTAL_NUMERIC_ORIGINAL\n'+old+'\n#else\n'+new+'\n#endif\n'
    helpers='\n'.join(body((root/'CvGameCoreUtils.h').read_bytes().decode('latin1'),s) for s in ('inline int xToHexspaceX(','inline int hexDistance('))
    helpers+='\n'+body((root/'CvGameCoreUtils.cpp').read_bytes().decode('latin1'),'DirectionTypes estimateDirection(')
    def calculation(text):return re.sub(r'^#include[^\r\n]*','',text,flags=re.M)
    header=(root/'Lua/CvLuaFractal.h').read_bytes().decode('latin1').replace('protected:','public:')
    old,new=baseline_text(LUA),candidate_text(LUA)
    lua=header+'\n'+select('\n'.join(body(old,s) for s in SIGNATURES),'\n'.join(body(new,s) for s in SIGNATURES))
    suite=(PROJECT/'Tests/sdk_lua_fractal.cpp').read_text(encoding='utf-8')
    anchor='        ++calls; seed=seed*UINT32_C(1103515245)+UINT32_C(12345);'
    if suite.count(anchor)!=1:raise RuntimeError('Numeric RNG adapter anchor changed')
    suite=suite.replace(anchor,'        if (calls>=observationLimit) throw std::runtime_error("numeric observation budget");\n'+anchor)
    texts={'fractal_lua_fixture.h':lua,
        'fractal_calculation_fixture.h':helpers+'\n'+select(calculation(baseline_text(NATIVE)),calculation(candidate_text(NATIVE))),
        'fractal_class_fixture.h':select(baseline_text(HEADER),candidate_text(HEADER)),
        'fractal_enum_fixture.h':body(baseline_text(HEADER),'enum FracVals')+';\n',
        'fractal_numeric_existing_suite.h':suite}
    sources=[root/n for n in ('CvGameCoreUtils.h','CvGameCoreUtils.cpp','Lua/CvLuaFractal.h')]
    return {k:v.replace('\r\n','\n') for k,v in texts.items()},sources


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--production',action='store_true');args=parser.parse_args()
    root=PROJECT/'evidence/fractal_numeric';root.mkdir(parents=True,exist_ok=True)
    out=PROJECT/'Build/FractalNumeric/x64';out.mkdir(parents=True,exist_ok=True);sdk=PROJECT/'Source/SDK_BNW_x64'
    if args.production:
        for name in (NATIVE,HEADER,LUA):
            if (sdk/name).read_bytes().decode('latin1')!=candidate_text(name):raise RuntimeError('Compiled SDK differs from numeric candidate: '+name)
    texts,sources=fixture_texts()
    for name,text in texts.items():(out/name).write_text(text,encoding='utf-8',newline='\n')
    reports={name:json.loads((PROJECT/('evidence/'+name+'/build_result.json')).read_text(encoding='utf-8-sig')) for name in ('lua_provider','flua')}
    inputs=[reports['lua_provider']['library'],reports['flua']['library'],reports['flua']['foundation_provider']['library']];check_artifacts(inputs)
    builds={};audits=[]
    for variant in ('original','candidate','original_od','candidate_od','original_asan','candidate_asan'):
        directory=out/variant;env,compiler=environment_for(Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community'),'x64',directory)
        compiler=Path(compiler);env['VSLANG']='1033'
        exe=directory/('fractal_numeric_'+variant+'.exe');mapfile=directory/'fractal.map';deps=directory/'dependencies.json'
        optimization='/Od' if variant.endswith('_od') else '/O2';sanitized=variant.endswith('_asan')
        flags=['/nologo','/std:c++14','/EHsc','/W4','/WX',optimization,'/MD','/utf-8','/external:W0',
            '/DWIN32','/DFINAL_RELEASE','/D_CRT_SECURE_NO_WARNINGS','/D_SILENCE_STDEXT_HASH_DEPRECATION_WARNINGS','/D_SILENCE_TR1_NAMESPACE_DEPRECATION_WARNING']
        if variant.startswith('original'):flags+=['/DFRACTAL_NUMERIC_ORIGINAL','/DLUA_FRACTAL_ORIGINAL']
        runtime=None
        if sanitized:
            # Existing FLua/Foundation providers use ordinary STL ABI settings.
            # Keep those annotations consistent; instrument actual native array accesses.
            flags+=['/fsanitize=address','/D_DISABLE_STRING_ANNOTATION','/D_DISABLE_VECTOR_ANNOTATION',
                '/Zi',f'/Fd"{directory/"fractal_numeric.pdb"}"']
            source=compiler.with_name('clang_rt.asan_dynamic-x86_64.dll');target=directory/source.name
            if not source.is_file():raise RuntimeError('MSVC AddressSanitizer runtime unavailable')
            shutil.copy2(source,target);runtime={'source':artifact(source),'copy':artifact(target)}
        flags += [f'/I"{p}"' for p in (out,PROJECT/'Source/Porting',PROJECT/'Source/Providers/FLua')]
        flags += [f'/external:I"{sdk/p}"' for p in ('ThirdPartyLibs/Lua51/include','FirePlace/include','FirePlace/include/FireWorks/Flua/include')]
        flags += [f'"{PROJECT/"Tests/sdk_fractal_numeric.cpp"}"',*[f'"{r["path"]}"' for r in inputs],f'/Fo"{directory/"fractal.obj"}"',f'/Fe"{exe}"',f'/sourceDependencies "{deps}"']
        rsp=directory/'compile.rsp';rsp.write_text('\n'.join(flags)+'\n',encoding='utf-8')
        result=run([compiler,'@'+str(rsp),'/link','/INCREMENTAL:NO','/MACHINE:X64','/Brepro','/WX','/OPT:REF','/OPT:ICF','/MAP:'+str(mapfile),'kernel32.lib'],cwd=directory,env=env,timeout=180)
        log=root/(variant+'_build.log');log.write_bytes(result.stdout+result.stderr)
        if result.returncode or re.search(r'\bwarning\s+[A-Z]+\d+',read_text(log)):raise RuntimeError(read_text(log)[-6500:])
        result=checked_run([compiler.with_name('dumpbin.exe'),'/dependents',exe],cwd=directory,env=env)
        ilog=root/(variant+'_imports.log');ilog.write_bytes(result.stdout+result.stderr)
        imports=re.findall(r'^\s+([\w.-]+\.dll)\s*$',result.stdout.decode('ascii',errors='replace'),re.M|re.I)
        allowed={'kernel32.dll','msvcp140.dll','vcruntime140.dll','vcruntime140_1.dll'}
        if sanitized:allowed.add('clang_rt.asan_dynamic-x86_64.dll')
        if not imports or any(s.lower() not in allowed and not s.lower().startswith('api-ms-win-crt-') for s in imports):raise RuntimeError('Unexpected numeric Fractal dependency: '+str(imports))
        audits.append({'module':artifact(exe),'dependencies':imports,'log':artifact(ilog)})
        consumed=json.loads(deps.read_text(encoding='utf-8-sig'))['Data']
        builds[variant]={'executable':{**artifact(exe),'pe':pe_header(exe)},'optimization':optimization,'compiler':artifact(compiler),
            'response':artifact(rsp),'log':artifact(log),'map':artifact(mapfile),'dependencies':artifact(deps),'sanitizer_runtime':runtime,
            'compiler_inputs':[artifact(Path(p)) for p in [consumed['Source'],*consumed['Includes']]]}
        print('BUILT '+variant,flush=True)
    report={'status':'SDK_FRACTAL_NUMERIC_COMPONENTS_BUILT','builds':builds,'audits':audits,'providers':inputs,
        'baseline':artifact(BASE),'fixtures':[artifact(out/n) for n in texts],'builder':artifact(Path(__file__).resolve()),
        'sources':[artifact(p) for p in [*sources,*[PROJECT/'Source/SDK_BNW_Original'/n for n in (NATIVE,HEADER,LUA)],
            PROJECT/'Source/Porting/ZeroSisLuaFractal.h',PROJECT/'Source/Porting/ZeroSisLuaFractalNumeric.h',
            PROJECT/'Tests/sdk_lua_fractal.cpp',PROJECT/'Tests/sdk_fractal_numeric.cpp',PROJECT/'tools/define_fractal_numeric_patches.py']],
        'candidate_matches_generated_sdk':args.production,'gamecore_loaded':False,'game_launched':False,
        'scope':'EXACT_NATIVE_AND_LUA_FRACTAL_BODIES; REAL_LUA_FLUA; NUMERIC_RNG_AND_STD_VECTOR_OWNER_ADAPTERS; NO_GAMECORE_LOADING'}
    if args.production:report['generated_sdk_sources']=[artifact(sdk/n) for n in (NATIVE,HEADER,LUA)]
    (root/'build_result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(report['status'])


if __name__=='__main__':main()
