"""Build exact SDK enum wrappers with real DB, Lua and FLua; never load GameCore."""
import argparse
import json
import re
import shutil
from pathlib import Path
from collect_baseline import PROJECT, read_text, pe_header
from native_build import environment_for, run, checked_run
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts
from build_bootstrap_component import body
from define_lua_enum_patches import BASE, SOURCE, SIGNATURES, baseline_text, candidate_text


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--production',action='store_true')
    args=parser.parse_args()
    root=PROJECT/'evidence/lua_enums'; root.mkdir(parents=True,exist_ok=True)
    out=PROJECT/'Build/LuaEnums/x64'; out.mkdir(parents=True,exist_ok=True)
    sdk=PROJECT/'Source/SDK_BNW_x64'
    candidate=candidate_text()
    if args.production and (sdk/SOURCE).read_bytes().decode('latin1')!=candidate:
        raise RuntimeError('Generated SDK enum source does not match the tested candidate')
    fixture=out/'lua_enum_fixture.h'
    fixture.write_text(('#ifdef LUA_ENUM_ORIGINAL\n'+ '\n'.join(body(baseline_text(),s) for s in SIGNATURES)
        +'\n#else\n'+'\n'.join(body(candidate,s) for s in SIGNATURES)+'\n#endif\n').replace('\r\n','\n'),encoding='utf-8',newline='\n')
    reports={name:json.loads((PROJECT/path).read_text(encoding='utf-8-sig')) for name,path in {
        'database':'evidence/database/candidate/build_result.json', 'lua':'evidence/lua_provider/build_result.json',
        'flua':'evidence/flua/build_result.json', 'foundation':'evidence/foundation/build_result.json'}.items()}
    inputs=[reports[name]['library'] for name in ('database','lua','flua')]+[reports['flua']['foundation_provider']['library']]
    inputs.append(reports['database']['dll']);check_artifacts(inputs)
    builds={};audits=[]
    for variant in ('original','candidate','original_od','candidate_od'):
        directory=out/variant;env,compiler=environment_for(Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community'),'x64',directory)
        compiler=Path(compiler);env['VSLANG']='1033'
        exe=directory/('lua_enums_'+variant+'.exe');mapfile=directory/'enum.map';deps=directory/'dependencies.json'
        optimization='/Od' if variant.endswith('_od') else '/O2'
        flags=['/nologo','/std:c++14','/EHsc','/W4','/WX',optimization,'/MD','/utf-8','/external:W0',
               '/DWIN32','/DFINAL_RELEASE','/D_CRT_SECURE_NO_WARNINGS','/D_SILENCE_STDEXT_HASH_DEPRECATION_WARNINGS','/D_SILENCE_TR1_NAMESPACE_DEPRECATION_WARNING']
        if variant.startswith('original'):flags+=['/DLUA_ENUM_ORIGINAL']
        flags += [f'/I"{p}"' for p in (out,PROJECT/'Source/Porting',PROJECT/'Source/Providers/Database',PROJECT/'Source/Providers/FLua')]
        flags += [f'/external:I"{sdk/p}"' for p in ('CvGameDatabase/include','ThirdPartyLibs/Lua51/include','FirePlace/include','FirePlace/include/FireWorks/Flua/include')]
        flags += [f'"{PROJECT/"Tests/sdk_lua_enums.cpp"}"',*[f'"{r["path"]}"' for r in inputs[:-1]],f'/Fo"{directory/"enum.obj"}"',f'/Fe"{exe}"',f'/sourceDependencies "{deps}"']
        rsp=directory/'compile.rsp';rsp.write_text('\n'.join(flags)+'\n',encoding='utf-8')
        result=run([compiler,'@'+str(rsp),'/link','/INCREMENTAL:NO','/MACHINE:X64','/Brepro','/WX','/OPT:REF','/OPT:ICF','/MAP:'+str(mapfile),'kernel32.lib'],cwd=directory,env=env,timeout=180)
        log=root/(variant+'_build.log');log.write_bytes(result.stdout+result.stderr)
        if result.returncode or re.search(r'\bwarning\s+[A-Z]+\d+',read_text(log)):
            raise RuntimeError(read_text(log)[-6500:])
        dll=directory/Path(inputs[-1]['path']).name;shutil.copy2(inputs[-1]['path'],dll)
        for module in (exe,dll):
            result=checked_run([compiler.with_name('dumpbin.exe'),'/dependents',module],cwd=directory,env=env)
            ilog=root/(variant+'_'+module.stem+'_imports.log');ilog.write_bytes(result.stdout+result.stderr)
            imports=re.findall(r'^\s+([\w.-]+\.dll)\s*$',result.stdout.decode('ascii',errors='replace'),re.M|re.I)
            allowed={'zerosisdatabase_x64.dll','kernel32.dll','msvcp140.dll','vcruntime140.dll','vcruntime140_1.dll'}
            if not imports or any(s.lower() not in allowed and not s.lower().startswith('api-ms-win-crt-') for s in imports):
                raise RuntimeError('Unexpected enum component dependency: '+str(imports))
            audits.append({'module':artifact(module),'dependencies':imports,'log':artifact(ilog)})
        consumed=json.loads(deps.read_text(encoding='utf-8-sig'))['Data']
        builds[variant]={'executable':{**artifact(exe),'pe':pe_header(exe)},'optimization':optimization,'dll':artifact(dll),'compiler':artifact(compiler),
                         'response':artifact(rsp),'log':artifact(log),'map':artifact(mapfile),'dependencies':artifact(deps),
                         'compiler_inputs':[artifact(Path(p)) for p in [consumed['Source'],*consumed['Includes']]]}
    report={'status':'SDK_LUA_ENUM_COMPONENTS_BUILT','builds':builds,'audits':audits,'providers':inputs,
            'baseline':artifact(BASE),'fixture':artifact(fixture),'builder':artifact(Path(__file__).resolve()),
            'sources':[artifact(PROJECT/'Tests/sdk_lua_enums.cpp'),artifact(PROJECT/'Source/Porting/ZeroSisLuaEnums.h'),
                       artifact(PROJECT/'tools/define_lua_enum_patches.py'),artifact(PROJECT/'Source/SDK_BNW_Original'/SOURCE)],
            'candidate_matches_generated_sdk':args.production,'gamecore_loaded':False,'game_launched':False,
            'scope':'EXACT_DYNAMIC_ENUM_AND_REGISTER_WRAPPERS_WITH_REAL_DB_LUA_FLUA; REPRESENTATIVE_pRegister_AND_GC_ACCESSOR; NOT_ALL_GAME_LIBRARIES'}
    if args.production:report['generated_sdk_source']=artifact(sdk/SOURCE)
    (root/'build_result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(report['status'])


if __name__=='__main__':main()
