"""Strict C++14 normal producer checks against original static expression DAGs."""
from pathlib import Path
import argparse,gzip,hashlib,json,os,re,sys
sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[1]
ROOT=PROJECT/'evidence/world_terrain_original/phase8/normal_cache'
sys.path[:0]=[str(PROJECT/'tools'),str(ROOT)]
import build_exit_confirm_host as common
from menu_replay_restoration import build_cxx14
from menu_suite_storage import storage
from native_build import run
from normal_contract_reference import Reference


def write_new(path,value):
    with Path(path).open('x',encoding='utf-8',newline='\n') as stream:json.dump(value,stream,indent=2);stream.write('\n')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--attempt',type=int,default=1);args=parser.parse_args()
    assert 1<=args.attempt<=9 and not any(os.environ.get(name) for name in ('CL','_CL_','LINK'))
    stage=ROOT/('normal_contract_cpu/attempt%02d'%args.attempt)
    assert not stage.exists(),'Inspect prior CPU evidence; do not replace it'
    stage.mkdir(parents=True);build=stage/'build';build.mkdir()
    inputs=[PROJECT/'Source/Presentation/OriginalTerrainNormalModel.h',PROJECT/'Tests/original_terrain_normal.cpp',
        PROJECT/'Tests/original_terrain_normal.py',ROOT/'normal_contract_reference.py',ROOT/'normal_contract_bulk_dag.py',ROOT/'normal_contract_pe.py']
    before=[common.artifact(path) for path in inputs]
    reference=Reference();cases=reference.header(build/'normal_contract_golden.h')
    write_new(stage/'normal_contract_started.json',dict(inputs=before,root_baseline_complete=True,golden_cases=len(cases),
        reference='Static original straight-line expression DAG; no original/native shader or game code executed'))
    failure=None;compiled=None;executable=None;checks=0;imports=[]
    try:
        compiled=build_cxx14('original_terrain_normal',build,stage,PROJECT/'Tests/original_terrain_normal.cpp',
                              [PROJECT/'Source/Presentation',build])
        imported=run([Path(compiled['compiler']).with_name('dumpbin.exe'),'/dependents',compiled['path']],cwd=build,timeout=30)
        text=imported.stdout.decode('mbcs',errors='replace')
        imports=sorted(set(re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$',text,re.M)))
        assert imported.returncode==0 and {name.lower() for name in imports}=={'kernel32.dll'},imports
        with (stage/'normal_contract_imports.txt').open('x',encoding='utf-8') as stream:stream.write(text)
        executable=common.artifact(compiled['path']);done=run([compiled['path']],cwd=build,timeout=60)
        stdout,stderr=done.stdout.decode('ascii'),done.stderr.decode('ascii')
        with (stage/'normal_contract_console.txt').open('x',encoding='ascii') as stream:stream.write(stdout+stderr)
        match=re.fullmatch(r'PASS_ORIGINAL_TERRAIN_NORMAL checks=(\d+)\s*',stdout)
        assert done.returncode==0 and not stderr and match,(done.returncode,stdout,stderr)
        checks=int(match[1]);reference.image.finish()
    except BaseException as error:
        failure=error
        for path in inputs[:2]:
            with (stage/('normal_contract_failed_'+path.name+'.gz')).open('xb') as stream:stream.write(gzip.compress(path.read_bytes(),mtime=0))
        write_new(stage/'normal_contract_failure.json',dict(type=type(error).__name__,message=str(error)[:5000],compiled=compiled))
    finally:
        after=[common.artifact(path) for path in inputs];assert before==after
        rows=[]
        for path in sorted(build.iterdir()):
            assert path.is_file() and path.suffix in ('.h','.exe','.obj','.map','.rsp','.cmd')
            row=dict(common.artifact(path),allocated_bytes=storage.allocated(path))
            assert row['links']==1 and not row['file_attributes']&0x401;rows.append(row)
        write_new(stage/'normal_contract_cleanup_plan.json',dict(directory=str(build),files=rows,protected_inputs=after))
        for row in rows:
            now=common.artifact(row['path']);assert now=={k:v for k,v in row.items() if k!='allocated_bytes'}
            path=Path(row['path']);assert path.parent==build;path.unlink()
        assert not list(build.iterdir());build.rmdir()
        write_new(stage/'normal_contract_cleanup_receipt.json',dict(status='PASS_EXACT_OWNED_CPU_BUILD_TEMPORARIES_REMOVED',
            deleted_files=len(rows),deleted_allocated_bytes=sum(row['allocated_bytes'] for row in rows),files=rows,
            protected_inputs_unchanged=True,native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False))
    if failure:raise failure
    result=dict(schema='zerosis.phase8.original_terrain_normal.cpu.v1',status='PASS_STRICT_CXX14_ORIGINAL_NORMAL_PRODUCER',
        checks=checks,golden_cases=len(cases),inputs_before=before,inputs_after=after,compiled=compiled,executable=executable,
        imports=imports,half_normal_roundtrip=True,compressed_byte_pairs=65536,unknown_masks=4096,
        raw15300_flat_tilt_preserved=True,normalization_precision_policy='Double-length finite normalization is a current policy; original runtime dispatch equivalence is unverified',
        metric_and_raw_height_reconstruction='Candidate atlas/world conversion; not a recovered original runtime value',
        actual_cpu_component_executed=True,host_sdk_clr_hwnd_gpu_audio_or_game_executed=False,
        cleanup=common.artifact(stage/'normal_contract_cleanup_receipt.json'))
    write_new(stage/'normal_contract_result.json',result)
    print(json.dumps(dict(status=result['status'],checks=checks,golden_cases=len(cases),result=str(stage/'normal_contract_result.json'))))


if __name__=='__main__':main()
