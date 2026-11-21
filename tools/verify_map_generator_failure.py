"""Exercise extracted SDK map startup methods with the actual host and shared Lua."""
import json,re,shutil
from pathlib import Path
from collect_baseline import PROJECT,read_text
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts
from build_bootstrap_component import body
from build_native_host import compile_program
from native_build import run


def main():
    root=PROJECT/'evidence/new_game_sdk';root.mkdir(parents=True,exist_ok=True)
    sdk_path=root/'build_result.json';sdk=json.loads(sdk_path.read_text());check_artifacts(sdk)
    runtime_path=PROJECT/'evidence/shared_lua_runtime/build_result.json'
    runtime=json.loads(runtime_path.read_text());check_artifacts(runtime)
    source=next(Path(r['path']) for r in sdk['sources'] if Path(r['path']).name=='CvMapGenerator.cpp')
    text=source.read_bytes().decode('latin1')
    signatures=['CvMapGenerator::CvMapGenerator(', 'CvMapGenerator::~CvMapGenerator()',
        'void CvMapGenerator::GenerateRandomMap()', 'int CvMapGenerator::pGenerateRandomMap(']
    extracted='\n\n'.join(body(text,signature) for signature in signatures)
    directory=PROJECT/'Build/NewGameSDK/FailureComponent';directory.mkdir(parents=True,exist_ok=True)
    include=directory/'map_generator_failure_methods.inc';include.write_bytes(extracted.encode('latin1'))
    original=PROJECT/'Tests/sdk_map_generator_failure.cpp';test=directory/original.name
    shutil.copy2(original,test)
    rows=[]
    for optimization in ('O2','Od'):
        built=compile_program('sdk_map_generator_failure_'+optimization,test,
            libraries=[Path(runtime['lua_library']['path'])],optimization='/'+optimization,
            definitions=('LUA_BUILD_AS_DLL',),additional_imports=('ZeroSisLua51_x64.dll',))
        exe=Path(built['executable']['path']);copy=exe.parent/Path(runtime['lua_dll']['path']).name
        shutil.copy2(runtime['lua_dll']['path'],copy)
        result=run([exe],cwd=exe.parent,timeout=60)
        log=root/('failure_'+optimization+'.log');log.write_bytes(result.stdout+result.stderr);output=read_text(log)
        marker=re.search(r'MAP_GENERATOR_FAILURE_PASS checks=(\d+) GAMECORE_LOADED=false',output)
        if result.returncode or not marker:raise RuntimeError(f'exit=0x{result.returncode&0xffffffff:08X}: '+output[-4000:])
        rows.append({'optimization':optimization,'build':built,'runtime_copy':artifact(copy),
            'log':artifact(log),'exit_code':result.returncode,'checks':int(marker[1])})
    check_artifacts([sdk,runtime])
    report={'status':'SDK_MAP_GENERATOR_FAILURE_COMPONENT_PASS','validator':artifact(Path(__file__).resolve()),
        'sdk_candidate':artifact(sdk_path),'shared_lua_build':artifact(runtime_path),'source':artifact(source),
        'signatures':signatures,'extracted_methods':artifact(include),'test_source':artifact(original),'test_copy':artifact(test),
        'runs':rows,'native_checks':sum(row['checks'] for row in rows),'gamecore_loaded':False,
        'scope':'EXTRACTED_SDK_MAP_SCRIPT_LOAD_GENERATE_FAILURE_RAII_AND_REAL_HOST_VM_REUSE'}
    (root/'failure_conformance.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'checks':report['native_checks'],'runs':len(rows)}),flush=True)


if __name__=='__main__':main()
