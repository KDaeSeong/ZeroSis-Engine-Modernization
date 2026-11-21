"""Build the actual x64 host against the frozen SDK ABI; do not load GameCore."""
import json,re,shutil
from pathlib import Path
from collect_baseline import PROJECT,read_text,pe_header
from native_build import environment_for,run,checked_run
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts


def compile_program(name,source,extra_sources=(),libraries=(),optimization='/O2',definitions=(),additional_imports=()):
    directory=PROJECT/'Build/Host/x64'/name;root=PROJECT/'evidence/host';root.mkdir(parents=True,exist_ok=True)
    vs=Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community');env,compiler=environment_for(vs,'x64',directory);compiler=Path(compiler);env['VSLANG']='1033'
    sdk=PROJECT/'Source/SDK_BNW_x64';exe=directory/(name+'.exe');mapfile=directory/(name+'.map')
    includes=[sdk/r for r in ('CvGameCoreDLL_Expansion2','CvGameCoreDLLUtil/include','CvGameDatabase/include','CvLocalization/include','CvWorldBuilderMap/include','FirePlace/include','FirePlace/include/FireWorks','ThirdPartyLibs/Lua51/include')]
    if optimization not in ('/O2','/Od'):raise ValueError('Unexpected host compiler optimization')
    flags=['/nologo','/std:c++14','/EHsc','/W4','/WX',optimization,'/MD','/fp:strict','/source-charset:windows-1252','/external:W0',
           '/DWIN32','/DNDEBUG','/DFINAL_RELEASE','/D_CRT_SECURE_NO_WARNINGS','/D_SILENCE_STDEXT_HASH_DEPRECATION_WARNINGS','/D_SILENCE_TR1_NAMESPACE_DEPRECATION_WARNING']
    flags += [f'/external:I"{p}"' for p in includes]
    flags += [f'/I"{PROJECT/p}"' for p in ('Source/Host','Source/Porting','Tests')]
    flags += ['/D'+definition for definition in definitions]
    flags += [f'"{p}"' for p in (source,*extra_sources,*libraries)]
    dependencies=directory/'dependencies.json'
    flags += [f'/Fo"{directory.as_posix()}/"',f'/Fe"{exe}"',f'/sourceDependencies "{dependencies}"']
    rsp=directory/'compile.rsp';rsp.write_text('\n'.join(flags)+'\n',encoding='utf-8')
    result=run([compiler,'@'+str(rsp),'/link','/INCREMENTAL:NO','/MACHINE:X64','/Brepro','/WX','/OPT:REF','/OPT:ICF','/MAP:'+str(mapfile)],cwd=directory,env=env,timeout=180)
    log=root/(name+'_build.log');log.write_bytes(result.stdout+result.stderr)
    if result.returncode or re.search(r'\bwarning\s+[A-Z]+\d+',read_text(log)):raise RuntimeError(read_text(log)[-6500:])
    result=checked_run([compiler.with_name('dumpbin.exe'),'/dependents',exe],cwd=directory,env=env)
    dep_log=root/(name+'_imports.log');dep_log.write_bytes(result.stdout+result.stderr)
    deps=re.findall(r'^\s+([\w.-]+\.dll)\s*$',result.stdout.decode('ascii',errors='replace'),re.M|re.I)
    allowed={'kernel32.dll','msvcp140.dll','vcruntime140.dll','vcruntime140_1.dll','zerosisdatabase_x64.dll','zerosislocalization_x64.dll','bcrypt.dll'}
    allowed.update(name.lower() for name in additional_imports)
    if not deps or any(d.lower() not in allowed and not d.lower().startswith('api-ms-win-crt-') for d in deps):raise RuntimeError('Unexpected native host import')
    dep_inputs=json.loads(dependencies.read_text(encoding='utf-8-sig'))['Data']
    consumed=[Path(dep_inputs['Source']),*[Path(p) for p in dep_inputs['Includes']]]
    return {'executable':{**artifact(exe),'pe':pe_header(exe)},'compiler':artifact(compiler),'response':artifact(rsp),'map':artifact(mapfile),
            'dependency_report':artifact(dependencies),'compiler_inputs':[artifact(p) for p in consumed],
            'log':artifact(log),'imports':{'dependencies':deps,'log':artifact(dep_log)}}


def build_shared_host(new_game_sdk=False):
    root=PROJECT/'evidence/host';root.mkdir(parents=True,exist_ok=True)
    reports={key:json.loads((PROJECT/path).read_text(encoding='utf-8')) for key,path in {
        'database':'evidence/database/candidate/build_result.json',
        'localization':'evidence/localization/provider/build_result.json',
        'lua':'evidence/shared_lua_runtime/build_result.json',
        'streams':'evidence/streams/provider/build_result.json',
        'temp_heap':'evidence/temp_heap/build_result.json'}.items()}
    sdk_path=PROJECT/'evidence/new_game_sdk/build_result.json'
    sdk=json.loads(sdk_path.read_text(encoding='utf-8')) if new_game_sdk else None
    provider=reports['lua']
    if provider.get('status')!='SHARED_LUA_RUNTIME_CANDIDATE_BUILT':raise RuntimeError('Shared Lua runtime is not a verified candidate input')
    libs=[reports['database']['library'],reports['localization']['library'],provider['lua_library'],reports['streams']['library'],*reports['temp_heap']['x64']['libraries']]
    dlls=[reports['database']['dll'],reports['localization']['dll'],provider['lua_dll']]
    check_artifacts(libs+dlls)
    if sdk is not None:
        check_artifacts(sdk)
        if sdk.get('status')!='NEW_GAME_SDK_CANDIDATE_LINKED' or sdk.get('sdk_objects_recompiled')!=2 or sdk.get('accepted_objects_reused')!=159:
            raise RuntimeError('New-game SDK candidate does not match the selected two-TU contract')
        if sdk.get('shared_lua_build',{}).get('sha256')!=artifact(PROJECT/'evidence/shared_lua_runtime/build_result.json')['sha256']:
            raise RuntimeError('New-game SDK candidate references a different shared Lua provider')
        if 'ZeroSisLua51_x64.dll' not in sdk.get('imports',[]) or 'dummynode_' in Path(sdk['map']['path']).read_text(errors='replace'):
            raise RuntimeError('New-game GameCore does not import the shared Lua provider cleanly')
    lua_library=Path(provider['lua_library']['path'])
    definitions=('ZEROSIS_SHARED_LUA_RUNTIME=1','LUA_BUILD_AS_DLL')
    imports=('ZeroSisLua51_x64.dll',)
    host_libs=[Path(item['path']) for item in libs]
    shared_host=compile_program('ZeroSisHostShared_x64',PROJECT/'Source/Host/HostMain.cpp',libraries=host_libs,
            definitions=definitions,additional_imports=imports)
    deployed=Path(shared_host['executable']['path']).parent/'Runtime'/'ZeroSisHost_x64.exe'
    deployed.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(shared_host['executable']['path'],deployed)
    if artifact(deployed)['sha256']!=shared_host['executable']['sha256']:raise RuntimeError('Shared host deployment copy differs')
    shared_host['executable']={**artifact(deployed),'pe':shared_host['executable']['pe']}
    built={'host':shared_host}
    tests=(('tests','sdk_native_host','Tests/sdk_native_host.cpp',[reports['database']['library'],lua_library]),
           ('map_audio_tests','sdk_host_map_audio','Tests/sdk_host_map_audio.cpp',[lua_library]),
           ('script_tests','sdk_host_script','Tests/sdk_host_script.cpp',[lua_library]),
           ('script_asset_tests','sdk_host_script_assets','Tests/sdk_host_script_assets.cpp',[lua_library]))
    for key,name,relative,libraries in tests:
        source=PROJECT/relative
        if source.exists():built[key]=compile_program(name+'_shared',source,libraries=[Path(p['path']) if isinstance(p,dict) else p for p in libraries],
                definitions=definitions,additional_imports=imports)
    copies=[]
    for build in built.values():
        directory=Path(build['executable']['path']).parent
        for provider_row in dlls:
            source=Path(provider_row['path']);target=directory/source.name
            shutil.copy2(source,target);copies.append(artifact(target))
    all_inputs=[*libs,*dlls]
    check_artifacts(all_inputs)
    selected_gamecore=Path((sdk['gamecore'] if sdk else provider['gamecore'])['path'])
    selected_map=Path(sdk['map']['path']) if sdk else Path(provider['gamecore_map']['path'])
    if 'dummynode_' in selected_map.read_text(errors='replace'):raise RuntimeError('Selected GameCore contains private Lua symbols')
    report={'status':'SHARED_LUA_NATIVE_HOST_COMPILED_NOT_GAME_EXECUTED','profile':'shared-lua-new-game-sdk-v4' if sdk else 'shared-lua-v4',
        'host':built['host'],'builder':artifact(Path(__file__).resolve()),'provider_inputs':all_inputs,'runtime_copies':copies,'builds':built,
        'shared_lua_build':artifact(PROJECT/'evidence/shared_lua_runtime/build_result.json'),
        'new_game_sdk_build':artifact(sdk_path) if sdk else None,'gamecore':artifact(selected_gamecore),
        'provider_reports':[artifact(PROJECT/path) for path in ('evidence/database/candidate/build_result.json',
            'evidence/localization/provider/build_result.json','evidence/shared_lua_runtime/build_result.json',
            'evidence/streams/provider/build_result.json','evidence/temp_heap/build_result.json')],
        'sources':[artifact(p) for p in sorted((PROJECT/'Source/Host').glob('*')) if p.is_file()],
        'gamecore_loaded':False,'game_launched':False}
    for key,_,relative,_ in tests:
        source=PROJECT/relative
        if source.exists():report.setdefault('test_sources',[]).append(artifact(source))
    (root/'shared_build_result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(report['status'])


def main():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--shared-lua',action='store_true');parser.add_argument('--new-game-sdk',action='store_true')
    args=parser.parse_args()
    if args.new_game_sdk and not args.shared_lua:parser.error('--new-game-sdk requires --shared-lua')
    if args.shared_lua:
        build_shared_host(args.new_game_sdk);return
    from build_host_script_access import main as build_script_access
    build_script_access()
    from host_game_info_evidence import build as build_game_info
    build_game_info()
    providers=[json.loads((PROJECT/p).read_text(encoding='utf-8')) for p in
               ('evidence/database/candidate/build_result.json','evidence/localization/provider/build_result.json')]
    inputs=[row[k] for row in providers for k in ('dll','library')]
    lua=json.loads((PROJECT/'evidence/lua_provider/build_result.json').read_text())
    inputs.append(lua['library']);lua_library=Path(lua['library']['path'])
    check_artifacts(inputs)
    result=compile_program('ZeroSisHost_x64',PROJECT/'Source/Host/HostMain.cpp',libraries=[*[Path(row['library']['path']) for row in providers],lua_library])
    builds={'host':result}
    test=PROJECT/'Tests/sdk_native_host.cpp'
    if test.exists():builds['tests']=compile_program('sdk_native_host',test,libraries=[Path(providers[0]['library']['path']),lua_library])
    map_audio_test=PROJECT/'Tests/sdk_host_map_audio.cpp'
    if map_audio_test.exists():builds['map_audio_tests']=compile_program('sdk_host_map_audio',map_audio_test,libraries=[lua_library])
    script_test=PROJECT/'Tests/sdk_host_script.cpp'
    if script_test.exists():builds['script_tests']=compile_program('sdk_host_script',script_test,libraries=[lua_library])
    assets_test=PROJECT/'Tests/sdk_host_script_assets.cpp'
    if assets_test.exists():builds['script_asset_tests']=compile_program('sdk_host_script_assets',assets_test,libraries=[lua_library])
    copies=[]
    for build in builds.values():
        directory=Path(build['executable']['path']).parent
        for provider in providers:
            source=Path(provider['dll']['path']);target=directory/source.name
            shutil.copy2(source,target);copies.append(artifact(target))
    check_artifacts(inputs)
    report={'status':'NATIVE_HOST_COMPILED_NOT_GAME_EXECUTED','host':result,'builder':artifact(Path(__file__).resolve()),
            'script_access_build':artifact(PROJECT/'evidence/host_script_access/build_result.json'),
            'game_info_build':artifact(PROJECT/'evidence/host_game_info/build_result.json'),
            'sources':[artifact(p) for p in sorted((PROJECT/'Source/Host').glob('*')) if p.is_file()],
            'provider_inputs':inputs,'runtime_copies':copies,'builds':builds,
            'gamecore_loaded':False,'game_launched':False}
    if test.exists():report['test_sources']=[artifact(test),artifact(PROJECT/'Tests/host_context_fixture.h')]
    if map_audio_test.exists():report['test_sources'].append(artifact(map_audio_test))
    if script_test.exists():report['test_sources'].append(artifact(script_test))
    report['test_sources'].append(artifact(PROJECT/'Tests/host_script_utility_fixture.h'))
    if assets_test.exists():report['test_sources'].append(artifact(assets_test))
    (PROJECT/'evidence/host/build_result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(report['status'])


if __name__=='__main__':main()
