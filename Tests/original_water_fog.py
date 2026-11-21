"""Pure C++14 post-water FOW/alpha/fragment routing reference console."""
from __future__ import annotations
import argparse,json,os,re,sys
from pathlib import Path
sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[1]
sys.path[0:0]=[str(PROJECT/'tools'),str(PROJECT/'Tests')]
import build_exit_confirm_host as common
from menu_replay_restoration import build_cxx14
from menu_suite_storage import storage
from native_build import run
ROOT=PROJECT/'evidence/world_terrain_original/phase8/water_fog'

def write_new(path,value):
    with path.open('x',encoding='utf8')as f:json.dump(value,f,indent=2);f.write('\n')

def main():
    cli=argparse.ArgumentParser();cli.add_argument('--attempt',default='water_cpu01');args=cli.parse_args();assert re.fullmatch(r'water_cpu\d{2}',args.attempt)
    stage=ROOT/args.attempt;build=stage/'work';assert not stage.exists();assert not any(os.environ.get(k)for k in('CL','_CL_','LINK'));build.mkdir(parents=True)
    paths=[PROJECT/'Source/Presentation'/n for n in('OriginalWaterFogBinding.h','OriginalWaterFogModel.h','OriginalLightingModel.h','OriginalWaterOpticsModel.h')]+[Path(__file__),PROJECT/'Tests/original_water_fog.cpp']
    inputs=[common.artifact(p)for p in paths];write_new(stage/'water_started.json',dict(inputs=inputs,native_host_gamecore_clr_hwnd_gpu_audio_or_game_executed=False))
    try:
        compiled=build_cxx14('original_water_fog',build,stage,PROJECT/'Tests/original_water_fog.cpp',[PROJECT/'Source/Presentation'])
        deps=run([Path(compiled['compiler']).with_name('dumpbin.exe'),'/dependents',compiled['path']],cwd=build,timeout=30)
        libs=sorted(set(re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$',deps.stdout.decode('mbcs',errors='replace'),re.M)));assert deps.returncode==0 and {k.lower()for k in libs}=={'kernel32.dll'}
        exe=common.artifact(compiled['path']);done=run([compiled['path']],cwd=build,timeout=60);stdout=done.stdout.decode('ascii');stderr=done.stderr.decode('ascii')
        match=re.fullmatch(r'PASS_WATER_FOG_ALPHA_ORDER_MARKER_GUARDS checks=(\d+) rejected=(\d+) cases=768 water_pixels=48 unit_pixels=16\s*',stdout)
        assert done.returncode==0 and not stderr and match,(done.returncode,stdout,stderr);assert [common.artifact(p)for p in paths]==inputs
        files=[]
        for path in sorted(build.iterdir()):
            assert path.is_file()and path.suffix in('.txt','.exe','.obj','.map','.rsp','.cmd');row=common.artifact(path);assert row['links']==1 and not row['file_attributes']&0x401;row['allocated_bytes']=storage.allocated(path);files.append(row)
        write_new(stage/'water_cleanup_plan.json',dict(files=files,protected=inputs))
        for row in files:assert common.artifact(row['path'])=={k:v for k,v in row.items()if k!='allocated_bytes'};Path(row['path']).unlink()
        assert not any(build.iterdir());build.rmdir();write_new(stage/'water_cleanup_result.json',dict(status='PASS_WATER_FOG_CPU_INTERMEDIATES_REMOVED',files=files,deleted_files=len(files),released_unique_allocated_bytes=sum(r['allocated_bytes']for r in files)))
        result=dict(status='PASS_CPP14_WATER_FOG_ORDER_ALPHA_MARKERS_UNKNOWN_AND_SINGLE_FOG',checks=int(match[1]),rejected=int(match[2]),cases=768,
            original_effects='encodedRGB->premultipliedOverlay->gray.4/R->LUTR(1-B)->distance;alphaexactinput',water_pixels=48,unit_pixels=16,inputs=inputs,build=compiled,executed_console=exe,imported_dlls=libs,
            cleanup=common.artifact(stage/'water_cleanup_result.json'),native_host_gamecore_clr_hwnd_gpu_audio_or_game_executed=False)
        write_new(stage/'water_result.json',result);print(json.dumps({k:result[k]for k in('status','checks','rejected','cases')}))
    except BaseException as e:
        write_new(stage/'water_failure.json',dict(error_type=type(e).__name__,message=str(e)[:8000],inputs_unchanged=[common.artifact(p)for p in paths]==inputs));raise

if __name__=='__main__':main()
