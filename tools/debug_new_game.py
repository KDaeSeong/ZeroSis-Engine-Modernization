"""Capture exception stacks from a fresh isolated candidate using a local debugger."""
import argparse,json,re,shutil,uuid
from pathlib import Path
from collect_baseline import PROJECT,digest
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts
from native_build import run

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--shared-lua',action='store_true');args=parser.parse_args()
    root=PROJECT/'evidence/new_game_debugger';root.mkdir(parents=True,exist_ok=True)
    candidate_path=PROJECT/'evidence/new_game'/('candidate_build_shared.json' if args.shared_lua else 'candidate_build.json')
    candidate=json.loads(candidate_path.read_text());check_artifacts(candidate)
    runtime=json.loads((PROJECT/'evidence/shared_lua_runtime/build_result.json').read_text()) if args.shared_lua else None
    if runtime:check_artifacts(runtime)
    bundle=json.loads((PROJECT/'evidence/host/bundle.json').read_text());check_artifacts(bundle)
    debugger=json.loads((root/'build.json').read_text());check_artifacts({'path':debugger['path'],'sha256':debugger['sha256']})
    key='debug_'+uuid.uuid4().hex[:12];directory=PROJECT/'Build/NewGameRuntime'/key;directory.mkdir(parents=True)
    evidence=root/key;evidence.mkdir();rows=[]
    for row in bundle['files']:
        name=Path(row['path']).name;source=Path(candidate['executable']['path']) if name=='ZeroSisHost_x64.exe' else Path(row['path'])
        if runtime and name=='CvGameCoreDLL_Expansion2_x64.dll':source=Path(runtime['gamecore']['path'])
        target=directory/name;shutil.copy2(source,target);rows.append(artifact(target))
    if runtime:
        source=Path(runtime['lua_dll']['path']);target=directory/source.name;shutil.copy2(source,target);rows.append(artifact(target))
    (directory/'bundle.manifest').write_text(('ZEROSIS_HOST_BUNDLE_V4\n' if runtime else 'ZEROSIS_HOST_BUNDLE_V3\n')+''.join(Path(r['path']).name+'|'+r['sha256']+'\n' for r in rows),encoding='ascii')
    command=[debugger['path'],str(directory/'ZeroSisHost_x64.exe')]
    request={'command':command,'cwd':str(directory),'inputs':rows,'candidate_build':artifact(candidate_path),
        'debugger_source':artifact(PROJECT/'Tests/new_game_debugger.cpp'),'debugger':artifact(Path(debugger['path'])),'runner':artifact(Path(__file__).resolve())}
    (evidence/'request.json').write_text(json.dumps(request,indent=2)+'\n')
    result=run(command,cwd=directory,timeout=105);output=(result.stdout+result.stderr).decode('utf8',errors='replace')
    (evidence/'debug.log').write_bytes(result.stdout+result.stderr)
    core_base=re.search(r'DEBUG_MODULE base=([0-9A-F]+) path=.*CvGameCoreDLL_Expansion2_x64.dll',output)
    link=json.loads((PROJECT/'evidence/sdk_x64/link_analysis.json').read_text())
    functions=[]
    for line in Path((runtime['gamecore_map'] if runtime else link['link_map'])['path']).read_text(errors='replace').splitlines():
        match=re.match(r'\s*0001:[0-9A-Fa-f]+\s+(\S+)\s+([0-9A-Fa-f]{16})\s+.*',line)
        if match:functions.append((int(match[2],16)-0x180000000,match[1]))
    functions.sort();frames=[]
    if core_base:
        base=int(core_base[1],16)
        for pc,module in re.findall(r'DEBUG_STACK index=\d+ pc=([0-9A-F]+) module=([0-9A-F]+)',output):
            if int(module,16)!=base:continue
            offset=int(pc,16)-base;preceding=[row for row in functions if row[0]<=offset]
            if preceding:
                address,name=preceding[-1];frames.append({'rva':hex(offset),'nearest_symbol':name,'displacement':hex(offset-address)})
    report={'debugger_exit':result.returncode,'request':artifact(evidence/'request.json'),'log':artifact(evidence/'debug.log'),
        'exceptions':re.findall(r'DEBUG_EXCEPTION code=([0-9A-F]+) first=(\d+)',output),
        'gamecore_frames':frames,'inputs_unchanged':all(digest(Path(r['path']))==r['sha256'] for r in rows),
        'debugged_candidate_only':True,'new_game_success_verified':False}
    (evidence/'result.json').write_text(json.dumps(report,indent=2)+'\n');(root/'latest.json').write_text(json.dumps(artifact(evidence/'result.json'),indent=2)+'\n')
    print(json.dumps({'run':key,**report},indent=2));print(output[-14000:])

if __name__=='__main__':main()
