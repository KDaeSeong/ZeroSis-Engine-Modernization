"""Build one Lua runtime DLL and relink a private GameCore candidate against it."""
import json,re
from pathlib import Path
from collect_baseline import PROJECT,read_text,pe_header
from native_build import environment_for,run,checked_run
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts

ROOT=PROJECT/'evidence/shared_lua_runtime'

def main():
    ROOT.mkdir(parents=True,exist_ok=True)
    prior=json.loads((PROJECT/'evidence/lua_provider/build_result.json').read_text());check_artifacts(prior)
    manifest=json.loads(Path(prior['source_manifest']['path']).read_text());check_artifacts(manifest)
    source=PROJECT/'Source/Lua51_x64/src';directory=PROJECT/'Build/SharedLuaRuntime/Lua'
    env,compiler=environment_for(Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community'),'x64',directory);compiler=Path(compiler)
    sources=sorted(p for p in source.glob('*.c') if p.name not in {'lua.c','luac.c','print.c'})
    original_ldo=source/'ldo.c';ldo_text=original_ldo.read_text(encoding='ascii')
    call='n = (*curr_func(L)->c.f)(L);  /* do the actual call */'
    include='#include "lzio.h"'
    if ldo_text.count(call)!=1 or ldo_text.count(include)!=1:raise RuntimeError('Lua C-function call boundary differs')
    ldo_text=ldo_text.replace(include,include+'\n\nextern int ZeroSisLuaInvoke(lua_State*, lua_CFunction);')
    ldo_text=ldo_text.replace(call,'n = ZeroSisLuaInvoke(L, curr_func(L)->c.f);  /* catch native exceptions before leaving Lua frames */')
    generated=PROJECT/'Source/SharedLua/ldo.c';generated.parent.mkdir(parents=True,exist_ok=True)
    if generated.exists() and generated.read_text(encoding='ascii')!=ldo_text:raise RuntimeError('Untracked shared Lua call-boundary edit')
    generated.write_text(ldo_text,encoding='ascii');sources=[generated if p==original_ldo else p for p in sources]
    response=directory/'compile.rsp';response.write_text('\n'.join([
        '/nologo','/c','/TC','/O2','/MD','/fp:strict','/W3','/WX','/D_CRT_SECURE_NO_WARNINGS','/DLUA_BUILD_AS_DLL',
        f'/I"{source}"',f'/Fo"{directory.as_posix()}/"',*[f'"{p}"' for p in sources]])+'\n')
    result=run([compiler,'@'+str(response)],cwd=directory,env=env,timeout=180)
    log=ROOT/'lua_compile.log';log.write_bytes(result.stdout+result.stderr)
    if result.returncode or re.search(r'\bwarning\s+[A-Z]+\d+',read_text(log)):raise RuntimeError(read_text(log)[-5000:])
    objects=[directory/(p.stem+'.obj') for p in sources]
    bridge=PROJECT/'Source/SharedLua/ZeroSisLuaCallback.cpp';bridge_object=directory/'ZeroSisLuaCallback.obj'
    bridge_response=directory/'callback.rsp';bridge_response.write_text('\n'.join([
        '/nologo','/c','/EHsc','/std:c++14','/O2','/MD','/W4','/WX','/DLUA_BUILD_AS_DLL','/DLUA_CORE',
        f'/I"{source}"',f'/Fo"{bridge_object}"',f'"{bridge}"'])+'\n')
    result=run([compiler,'@'+str(bridge_response)],cwd=directory,env=env,timeout=60)
    bridge_log=ROOT/'callback_compile.log';bridge_log.write_bytes(result.stdout+result.stderr)
    if result.returncode:raise RuntimeError(read_text(bridge_log)[-5000:])
    objects.append(bridge_object)
    dll=directory/'ZeroSisLua51_x64.dll';library=dll.with_suffix('.lib');mapfile=dll.with_suffix('.map')
    lua_response=directory/'link.rsp';lua_response.write_text('\n'.join([
        '/NOLOGO','/DLL','/MACHINE:X64','/INCREMENTAL:NO','/WX','/Brepro','/OPT:REF','/OPT:ICF',
        f'/OUT:"{dll}"',f'/IMPLIB:"{library}"',f'/MAP:"{mapfile}"',*[f'"{p}"' for p in objects]])+'\n')
    result=run([compiler.with_name('link.exe'),'@'+str(lua_response)],cwd=directory,env=env,timeout=120)
    linklog=ROOT/'lua_link.log';linklog.write_bytes(result.stdout+result.stderr)
    if result.returncode:raise RuntimeError(read_text(linklog)[-5000:])
    link=json.loads((PROJECT/'evidence/sdk_x64/link_analysis.json').read_text());check_artifacts(link)
    game_directory=PROJECT/'Build/SharedLuaRuntime/GameCore';game_directory.mkdir(parents=True,exist_ok=True)
    game_dll=game_directory/'CvGameCoreDLL_Expansion2_x64.dll';game_map=game_dll.with_suffix('.map')
    original_response=Path(link['link_response']['path']).read_text(encoding='utf-8')
    static_library=prior['library']['path']
    if original_response.count('"'+static_library+'"')!=1:raise RuntimeError('GameCore Lua archive reference differs')
    modified=original_response.replace('"'+static_library+'"','"'+str(library)+'"')
    for option,target in (('OUT',game_dll),('IMPLIB',game_dll.with_suffix('.lib')),('MAP',game_map)):
        modified,count=re.subn(r'^/'+option+r':[^\r\n]+',lambda _:f'/{option}:"{target}"',modified,flags=re.M)
        if count!=1:raise RuntimeError('GameCore output option differs: '+option)
    game_response=game_directory/'link.rsp';game_response.write_text(modified,encoding='utf-8')
    result=run([compiler.with_name('link.exe'),'@'+str(game_response)],cwd=game_directory,env=env,timeout=180)
    game_log=ROOT/'gamecore_link.log';game_log.write_bytes(result.stdout+result.stderr)
    if result.returncode:raise RuntimeError(read_text(game_log)[-5000:])
    imports={}
    for name,binary in (('lua',dll),('gamecore',game_dll)):
        inspected=checked_run([compiler.with_name('dumpbin.exe'),'/dependents',binary],cwd=directory,env=env)
        report=ROOT/(name+'_imports.log');report.write_bytes(inspected.stdout+inspected.stderr)
        imports[name]={'log':artifact(report),'dependencies':re.findall(r'^\s+([\w.-]+\.dll)\s*$',inspected.stdout.decode('ascii',errors='replace'),re.M|re.I)}
    if 'ZeroSisLua51_x64.dll' not in imports['gamecore']['dependencies'] or 'dummynode_' in read_text(game_map):
        raise RuntimeError('GameCore still contains a private Lua implementation')
    exports=checked_run([compiler.with_name('dumpbin.exe'),'/exports',dll],cwd=directory,env=env)
    export_log=ROOT/'lua_exports.log';export_log.write_bytes(exports.stdout+exports.stderr)
    names=re.findall(r'^\s+\d+\s+[0-9A-F]+\s+[0-9A-F]+\s+(\S+)\s*$',exports.stdout.decode('ascii',errors='replace'),re.M)
    for required in ('lua_newstate','lua_newthread','lua_close','lua_gc','lua_cpcall','lua_pcall','luaL_newstate','luaL_openlibs'):
        if required not in names:raise RuntimeError('Shared Lua API export missing: '+required)
    report={'status':'SHARED_LUA_RUNTIME_CANDIDATE_BUILT','builder':artifact(Path(__file__).resolve()),
        'source_manifest':prior['source_manifest'],'sources':manifest,'static_provider_reference':artifact(PROJECT/'evidence/lua_provider/build_result.json'),
        'native_callback_boundary':{'original_ldo':artifact(original_ldo),'patched_ldo':artifact(generated),
            'bridge':artifact(bridge),'response':artifact(bridge_response),'log':artifact(bridge_log)},
        'compiler':artifact(compiler),'objects':[artifact(p) for p in objects],'compile_response':artifact(response),'compile_log':artifact(log),
        'lua_dll':{**artifact(dll),'pe':pe_header(dll)},'lua_library':artifact(library),'lua_map':artifact(mapfile),
        'lua_link_response':artifact(lua_response),'lua_link_log':artifact(linklog),'exports':names,'export_log':artifact(export_log),
        'gamecore':{**artifact(game_dll),'pe':pe_header(game_dll)},'gamecore_map':artifact(game_map),'gamecore_link_response':artifact(game_response),
        'gamecore_link_log':artifact(game_log),'original_gamecore_link':artifact(PROJECT/'evidence/sdk_x64/link_analysis.json'),
        'imports':imports,'gamecore_executed':False,'static_provider_replaced':False,'accepted_bundle_replaced':False}
    (ROOT/'build_result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'exports':len(names),'gamecore_imports_shared_lua':True}),flush=True)

if __name__=='__main__':main()
