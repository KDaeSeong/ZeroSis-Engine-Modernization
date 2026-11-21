"""Compile two map-startup units and relink a private candidate with shared Lua."""
import json,re
from pathlib import Path
from collect_baseline import PROJECT,read_text,pe_header,digest
from native_build import environment_for,run,checked_run
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts
from define_new_game_patches import BASE,patches,baseline_text


def main():
    root=PROJECT/'evidence/new_game_sdk';root.mkdir(parents=True,exist_ok=True)
    directory=PROJECT/'Build/NewGameSDK';directory.mkdir(parents=True,exist_ok=True)
    accepted_path=PROJECT/'evidence/sdk_x64/attempts/attempt_037/build_result.json'
    accepted=json.loads(accepted_path.read_text());check_artifacts(accepted)
    runtime_path=PROJECT/'evidence/shared_lua_runtime/build_result.json'
    runtime=json.loads(runtime_path.read_text());check_artifacts(runtime)
    plan=patches();files=sorted({p['file'] for p in plan})
    expected=['CvGameCoreDLL_Expansion2/CvGame.cpp','CvGameCoreDLL_Expansion2/CvMapGenerator.cpp']
    if files!=expected:raise RuntimeError('Unexpected new-game SDK patch scope')
    plan_path=root/'patches.json';plan_path.write_text(json.dumps(plan,indent=2)+'\n')
    old_path=root/'build_result.json'
    previous=json.loads(old_path.read_text()) if old_path.exists() else {}
    tracked={r['path']:r['sha256'] for r in previous.get('sources',[])}
    generated=[]
    for name in files:
        original=PROJECT/'Source/SDK_BNW_x64'/name
        text=baseline_text(name)
        if original.read_bytes()!=text.encode('latin1'):raise RuntimeError('Accepted source differs: '+name)
        for patch in (p for p in plan if p['file']==name):
            if text.count(patch['old'])!=patch['count']:raise RuntimeError('Patch context differs: '+patch['id'])
            text=text.replace(patch['old'],patch['new'])
        target=directory/'Source'/name;content=text.encode('latin1')
        if target.exists() and target.read_bytes()!=content and digest(target)!=tracked.get(str(target)):
            raise RuntimeError('Untracked new-game candidate source edit: '+str(target))
        target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(content);generated.append(target)
    env,compiler=environment_for(Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community'),'x64',directory)
    compiler=Path(compiler);env['VSLANG']='1033'
    original_response=Path(accepted['executions'][1]['response'])
    flags=[line for line in original_response.read_text().splitlines()
        if not line.startswith('"') and not line.startswith('/Fo') and line!='/MP4']
    pch=PROJECT/'Build/SDK_x64/attempt_037/GameCore_x64.pch'
    units=[]
    for source in generated:
        obj=directory/(source.stem+'.obj');response=directory/(source.stem+'.rsp')
        dependencies=directory/(source.stem+'_dependencies.json')
        response.write_text('\n'.join(flags+[f'/Fo"{obj}"',f'/sourceDependencies "{dependencies}"',f'"{source}"'])+'\n')
        result=run([compiler,'@'+str(response)],cwd=source.parent,env=env,timeout=180)
        log=root/(source.stem+'.log');log.write_bytes(result.stdout+result.stderr);output=read_text(log)
        if result.returncode or re.search(r'warning\s+C(?:4244|4267|4838)\b',output):raise RuntimeError(output[-7000:])
        consumed=json.loads(dependencies.read_text(encoding='utf-8-sig'))['Data']
        units.append({'source':artifact(source),'object':artifact(obj),'response':artifact(response),'log':artifact(log),
            'dependencies':artifact(dependencies),'compiler_inputs':[artifact(Path(p)) for p in [consumed['Source'],*consumed['Includes']]]})
    dll=directory/'CvGameCoreDLL_Expansion2_x64.dll';mapfile=dll.with_suffix('.map')
    response=directory/'link.rsp';link_text=Path(runtime['gamecore_link_response']['path']).read_text()
    for unit in units:
        name=Path(unit['source']['path']).stem
        original=next(Path(r['path']) for r in accepted['objects'] if Path(r['path']).stem==name)
        if link_text.count('"'+str(original)+'"')!=1:raise RuntimeError('Candidate object replacement differs: '+name)
        link_text=link_text.replace('"'+str(original)+'"','"'+unit['object']['path']+'"')
    for option,target in (('OUT',dll),('IMPLIB',dll.with_suffix('.lib')),('MAP',mapfile)):
        link_text,count=re.subn(r'^/'+option+r':[^\r\n]+',lambda _:f'/{option}:"{target}"',link_text,flags=re.M)
        if count!=1:raise RuntimeError('Link output option differs')
    response.write_text(link_text)
    result=run([compiler.with_name('link.exe'),'@'+str(response)],cwd=directory,env=env,timeout=180)
    log=root/'link.log';log.write_bytes(result.stdout+result.stderr)
    if result.returncode:raise RuntimeError(read_text(log)[-5000:])
    inspected=checked_run([compiler.with_name('dumpbin.exe'),'/dependents',dll],cwd=directory,env=env)
    imports=root/'imports.log';imports.write_bytes(inspected.stdout+inspected.stderr)
    names=re.findall(r'^\s+([\w.-]+\.dll)\s*$',read_text(imports),re.M|re.I)
    if 'ZeroSisLua51_x64.dll' not in names or 'dummynode_' in read_text(mapfile):raise RuntimeError('Private Lua reintroduced')
    check_artifacts([accepted,runtime])
    report={'status':'NEW_GAME_SDK_CANDIDATE_LINKED','builder':artifact(Path(__file__).resolve()),
        'patch_builder':artifact(PROJECT/'tools/define_new_game_patches.py'),'patch_baseline':artifact(BASE),'patches':artifact(plan_path),
        'accepted_build':artifact(accepted_path),'shared_lua_build':artifact(runtime_path),'sources':[artifact(p) for p in generated],
        'compiler':artifact(compiler),'pch':artifact(pch),'original_compile_response':artifact(original_response),'units':units,
        'gamecore':{**artifact(dll),'pe':pe_header(dll)},'map':artifact(mapfile),'link_response':artifact(response),'link_log':artifact(log),
        'imports':names,'imports_log':artifact(imports),'sdk_objects_recompiled':2,'accepted_objects_reused':159,
        'gamecore_loaded':False,'active_sdk_updated':False,'accepted_bundle_replaced':False}
    old_path.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'sdk_objects_recompiled':2,'accepted_objects_reused':159}),flush=True)


if __name__=='__main__':main()
