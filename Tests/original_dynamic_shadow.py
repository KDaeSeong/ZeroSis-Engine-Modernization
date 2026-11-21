"""Bounded shadow math checks; no renderer or graphics device is loaded."""
from pathlib import Path
import argparse, json, os, re, sys
sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[1]
sys.path[:0]=[str(PROJECT/'tools'),str(PROJECT/'Tests')]
import build_exit_confirm_host as common
from menu_replay_restoration import build_cxx14
from native_build import run
from menu_suite_storage import storage

def write_new(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf8')as f:json.dump(value,f,indent=2);f.write('\n')

def main():
    cli=argparse.ArgumentParser();cli.add_argument('--attempt',default='cpu01');args=cli.parse_args()
    assert re.fullmatch(r'cpu\d{2}',args.attempt)
    stage=PROJECT/'evidence/world_terrain_original/phase8/dynamic_shadow'/args.attempt
    build=PROJECT/'Build/OriginalDynamicShadow'/args.attempt
    assert not stage.exists()and not build.exists()
    assert not any(os.environ.get(k)for k in('CL','_CL_','LINK'))
    stage.mkdir(parents=True);build.mkdir(parents=True)
    names=['Source/Presentation/OriginalDynamicShadowModel.h','Tests/original_dynamic_shadow.cpp','Tests/original_dynamic_shadow.py']
    before=[common.artifact(PROJECT/name)for name in names]
    write_new(stage/'started.json',dict(inputs=before,native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False))
    compiled=build_cxx14('original_dynamic_shadow',build,stage,PROJECT/names[1],[PROJECT/'Source/Presentation'])
    imports=run([Path(compiled['compiler']).with_name('dumpbin.exe'),'/dependents',compiled['path']],cwd=build,timeout=30)
    dlls=sorted(set(re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$',imports.stdout.decode('mbcs'),re.M)))
    assert imports.returncode==0 and {d.lower()for d in dlls}=={'kernel32.dll'}
    executable=common.artifact(compiled['path']);done=run([compiled['path']],cwd=build,timeout=30)
    match=re.fullmatch(r'PASS_DYNAMIC_SHADOW checks=(\d+)\s*',done.stdout.decode('ascii'))
    assert done.returncode==0 and not done.stderr and match,(done.returncode,done.stdout,done.stderr)
    assert before==[common.artifact(PROJECT/name)for name in names]
    rows=[]
    for path in sorted(build.iterdir()):
        assert path.is_file()and path.suffix in('.exe','.obj','.map','.rsp','.cmd')
        row=common.artifact(path);row['allocated_bytes']=storage.allocated(path)
        assert row['links']==1 and not row['file_attributes']&0x401
        rows.append(row)
    write_new(stage/'cleanup_plan.json',dict(directory=str(build),files=rows,exact_owned_leaves_only=True))
    assert build.resolve().is_relative_to((PROJECT/'Build/OriginalDynamicShadow').resolve())
    for row in rows:
        now=common.artifact(row['path']);assert all(now[k]==row[k]for k in('sha256','bytes','file_identity','mtime_ns','file_attributes','links'))
        Path(row['path']).unlink()
    build.rmdir()
    write_new(stage/'cleanup_result.json',dict(status='PASS',files=rows,released_unique_allocated_bytes=sum(r['allocated_bytes']for r in rows)))
    result=dict(status='PASS_CPU_DYNAMIC_SHADOW',checks=int(match[1]),inputs=before,build=compiled,executed_console=executable,
        imported_dlls=dlls,retained_test_executable=False,cleanup=common.artifact(stage/'cleanup_result.json'),
        candidates=['2048 depth target and orthographic camera','receiver bias and four-tap bilinear PCF','opaque prepared unit silhouettes'],
        native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False,actual_gpu_acceptance=False)
    write_new(stage/'result.json',result);print(json.dumps(dict(status=result['status'],checks=result['checks'])))

if __name__=='__main__':main()
