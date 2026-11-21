"""Strict isolated CPU checks for original cache coordinates and height conversion."""
from pathlib import Path
import argparse,gzip,hashlib,json,os,re,sys
sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[1]
ROOT=PROJECT/'evidence/world_terrain_original/phase12/cache'
sys.path[:0]=[str(PROJECT/'tools'),str(ROOT)]
import build_exit_confirm_host as common
from menu_replay_restoration import build_cxx14
from menu_suite_storage import storage
from native_build import run
from cache_reference import Reference


def write_new(path,value):
    with Path(path).open('x',encoding='utf8',newline='\n') as stream:json.dump(value,stream,indent=2);stream.write('\n')


def main():
    cli=argparse.ArgumentParser();cli.add_argument('--attempt',type=int,default=1);args=cli.parse_args()
    assert 1<=args.attempt<=9 and not any(os.environ.get(name) for name in ('CL','_CL_','LINK'))
    startup=json.loads((ROOT.parent/'startup.json').read_text(encoding='utf8'))
    assert startup.get('status','').startswith('PASS'),startup.get('status')
    stage=ROOT/('cache_sampling_cpu/attempt%02d'%args.attempt)
    assert not stage.exists(),'Inspect existing evidence; use a separately reviewed fresh attempt'
    stage.mkdir(parents=True);build=stage/'build';build.mkdir()
    inputs=[PROJECT/'Source/Presentation/OriginalTerrainCacheSamplingModel.h',
            PROJECT/'Source/Presentation/OriginalTerrainCacheModel.h',PROJECT/'Tests/original_terrain_cache_sampling.cpp',
            PROJECT/'Tests/original_terrain_cache_sampling.py',ROOT/'cache_reference.py',
            PROJECT/'evidence/world_terrain_original/phase8/normal_cache/normal_contract_pe.py']
    before=[common.artifact(path) for path in inputs]
    reference=Reference();reference.header(build/'cache_sampling_golden.h')
    write_new(stage/'cache_started.json',dict(inputs=before,root_baseline_complete=True,
        reference=reference.report(),original_binary_loaded_or_executed=False))
    failure=None;compiled=None;executable=None;checks=0;imports=[]
    try:
        compiled=build_cxx14('original_terrain_cache_sampling',build,stage,PROJECT/'Tests/original_terrain_cache_sampling.cpp',
                            [PROJECT/'Source/Presentation',build])
        result=run([Path(compiled['compiler']).with_name('dumpbin.exe'),'/dependents',compiled['path']],cwd=build,timeout=30)
        text=result.stdout.decode('mbcs',errors='replace')
        imports=sorted(set(re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$',text,re.M)))
        assert result.returncode==0 and {name.lower() for name in imports}=={'kernel32.dll'},imports
        with (stage/'cache_imports.txt').open('x',encoding='utf8') as stream:stream.write(text)
        executable=common.artifact(compiled['path']);done=run([compiled['path']],cwd=build,timeout=60)
        stdout,stderr=done.stdout.decode('ascii'),done.stderr.decode('ascii')
        with (stage/'cache_console.txt').open('x',encoding='ascii') as stream:stream.write(stdout+stderr)
        match=re.fullmatch(r'PASS_ORIGINAL_TERRAIN_CACHE_SAMPLING checks=(\d+)\s*',stdout)
        assert done.returncode==0 and not stderr and match,(done.returncode,stdout,stderr)
        checks=int(match[1]);reference.image.finish()
    except BaseException as error:
        failure=error
        for path in inputs[:1]+inputs[2:3]:
            with (stage/('cache_failed_'+path.name+'.gz')).open('xb') as stream:stream.write(gzip.compress(path.read_bytes(),mtime=0))
        write_new(stage/'cache_failure.json',dict(type=type(error).__name__,message=str(error)[:5000],compiled=compiled))
    finally:
        after=[common.artifact(path) for path in inputs];assert before==after
        rows=[]
        for path in sorted(build.iterdir()):
            assert path.is_file() and path.suffix in ('.h','.exe','.obj','.map','.rsp','.cmd')
            row=dict(common.artifact(path),allocated_bytes=storage.allocated(path))
            assert row['links']==1 and not row['file_attributes']&0x401;rows.append(row)
        write_new(stage/'cache_cleanup_plan.json',dict(directory=str(build),files=rows,protected_inputs=after))
        for row in rows:
            assert common.artifact(row['path'])=={k:v for k,v in row.items() if k!='allocated_bytes'}
            path=Path(row['path']);assert path.parent==build;path.unlink()
        assert not list(build.iterdir());build.rmdir()
        write_new(stage/'cache_cleanup_receipt.json',dict(status='PASS_EXACT_OWNED_CPU_TEMPORARIES_REMOVED',
            files=rows,deleted_files=len(rows),deleted_allocated_bytes=sum(row['allocated_bytes'] for row in rows),
            protected_inputs_unchanged=True,host_sdk_clr_hwnd_gpu_audio_or_game_executed=False))
    if failure:raise failure
    report=dict(schema='zerosis.phase12.original_terrain_cache_sampling.cpu.v1',status='PASS_STRICT_CXX14_CACHE_SAMPLING',
        checks=checks,reference=reference.report(),inputs_before=before,inputs_after=after,compiled=compiled,
        executable=executable,imports=imports,actual_cpu_component_executed=True,
        host_sdk_clr_hwnd_gpu_audio_or_game_executed=False,
        cleanup=common.artifact(stage/'cache_cleanup_receipt.json'))
    write_new(stage/'cache_result.json',report)
    print(json.dumps(dict(status=report['status'],checks=checks,result=str(stage/'cache_result.json'))))


if __name__=='__main__':main()
