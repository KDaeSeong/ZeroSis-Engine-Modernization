"""Build the original/current host Lua execution boundary with a real Lua provider."""
import argparse,json
from pathlib import Path
from collect_baseline import PROJECT
from build_native_host import compile_program
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts

def main(variant='all'):
    root=PROJECT/'evidence/host_script_access';root.mkdir(parents=True,exist_ok=True)
    lua=json.loads((PROJECT/'evidence/lua_provider/build_result.json').read_text())['library'];check_artifacts(lua)
    builds={}
    for kind in ('original','candidate'):
        if variant not in ('all',kind):continue
        for suffix,optimization in (('o2','/O2'),('od','/Od')):
            name=kind+'_'+suffix
            builds[name]={**compile_program('script_access_'+name,PROJECT/'Tests/sdk_host_script_access.cpp',
                libraries=[Path(lua['path'])],optimization=optimization,definitions=['SCRIPT_ACCESS_ORIGINAL='+str(int(kind=='original'))]),
                'optimization':optimization,'variant':kind}
    report={'status':'HOST_SCRIPT_ACCESS_COMPILED','builder':artifact(Path(__file__).resolve()),
        'compiler_helper':artifact(PROJECT/'tools/build_native_host.py'),'builds':builds,'lua_provider':lua,
        'gamecore_loaded':False,'game_launched':False}
    target='build_result.json' if variant=='all' else variant+'_build.json'
    (root/target).write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'variant':variant,'programs':len(builds)}))
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--variant',choices=('all','original','candidate'),default='all')
    main(parser.parse_args().variant)
