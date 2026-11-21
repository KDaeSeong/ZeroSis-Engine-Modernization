"""Actual production ground-cache policy, C++14 CPU console; never executes graphics or the Host."""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
import sys

sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[1]
STAGE=PROJECT/'evidence/game_menu/idle_render_cache/tests'
BUILD=PROJECT/'Build/WorldTerrainReuse/current'
sys.path.insert(0,str(PROJECT/'tools'));sys.path.insert(0,str(PROJECT/'Tests'))
import build_exit_confirm_host as common
from menu_replay_restoration import build_cxx14
from native_build import run
from menu_suite_storage import storage

def write_new(path,value):
    with path.open('x',encoding='utf8') as f:json.dump(value,f,indent=2);f.write('\n')

def main():
    assert not BUILD.exists() and not(STAGE/'result.json').exists(),'Inspect the existing owned attempt instead of restarting it'
    assert not any(os.environ.get(name) for name in ('CL','_CL_','LINK'))
    STAGE.mkdir(parents=True,exist_ok=True);BUILD.mkdir(parents=True)
    inputs=[PROJECT/name for name in ('Source/Presentation/WorldTerrainReuse.h','Source/Presentation/WorldViewRenderer.h',
        'Source/Presentation/WorldTerrainRenderer.h','Source/Presentation/WorldCameraControls.h','Source/Presentation/BitmapRenderer.h',
        'Tests/world_terrain_reuse.cpp','Tests/world_terrain_reuse.py')]
    before=[common.artifact(path) for path in inputs]
    write_new(STAGE/'started.json',dict(inputs=before,build_directory=str(BUILD),native_host_sdk_gpu_window_or_game=False))
    compiled=build_cxx14('world_terrain_reuse',BUILD,STAGE,PROJECT/'Tests/world_terrain_reuse.cpp',[PROJECT/'Source/Presentation'])
    imports=run([Path(compiled['compiler']).with_name('dumpbin.exe'),'/dependents',compiled['path']],cwd=BUILD,timeout=30)
    names=sorted(set(re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$',imports.stdout.decode('mbcs',errors='replace'),re.M)))
    assert imports.returncode==0 and {name.lower() for name in names}=={'kernel32.dll'},names
    executable=common.artifact(compiled['path'])
    result=run([compiled['path']],cwd=BUILD,timeout=30)
    stdout=result.stdout.decode('ascii');stderr=result.stderr.decode('ascii')
    match=re.fullmatch(r'PASS_WORLD_TERRAIN_REUSE checks=(\d+)\s*',stdout)
    assert result.returncode==0 and not stderr and match,(result.returncode,stdout,stderr)
    after=[common.artifact(path) for path in inputs];assert before==after
    rows=[]
    for path in sorted(BUILD.iterdir()):
        assert path.is_file() and path.suffix in ('.exe','.obj','.map','.rsp','.cmd')
        row=common.artifact(path);row['allocated_bytes']=storage.allocated(path)
        assert row['links']==1 and not row['file_attributes']&0x401
        rows.append(row)
    plan=dict(schema='zerosis.idle_cache.cpu_intermediate_cleanup.v1',directory=str(BUILD),files=rows,
        exact_owned_leaves_only=True,protected_source_inputs=after)
    write_new(STAGE/'cleanup_plan.json',plan)
    for row in rows:
        path=Path(row['path']);now=common.artifact(path)
        assert all(now[k]==row[k] for k in ('bytes','sha256','file_identity','mtime_ns','file_attributes','links'))
        path.unlink()
    assert not any(BUILD.iterdir());BUILD.rmdir()
    cleanup=dict(status='PASS_EXACT_OWNED_CPU_INTERMEDIATES_REMOVED',files=rows,
        retired_files=len(rows),released_unique_allocated_bytes=sum(row['allocated_bytes'] for row in rows),
        original_sources_unchanged=True)
    write_new(STAGE/'cleanup_result.json',cleanup)
    proof=dict(schema='zerosis.world_terrain_reuse.cpu_tests.v1',status='PASS_ACTUAL_PRODUCTION_HEADER_CPU_CACHE_TESTS',
        checks=int(match[1]),production_header=before[0],inputs_before=before,inputs_after=after,
        build=compiled,executed_console=executable,imported_dlls=names,
        cases=['All used plot/camera/viewport/device/context inputs invalidate including order',
            'Unit/UI/time/turn and unused improvement/route fields keep exact ground reuse',
            'Owned key snapshot survives input mutation; returned real metadata can move without emptying cache',
            'Invalid dimensions/nonfinite zoom rejected; upper viewport bound accepted',
            'Null publication and injected Entry allocation failure preserve old entry and release candidate',
            'Successful replacement/clear release previous owned payload; one bounded entry'],
        cleanup=common.artifact(STAGE/'cleanup_result.json'),retained_test_executable=False,
        native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False,measured_live_cpu_reduction=False)
    write_new(STAGE/'result.json',proof)
    print(json.dumps(dict(status=proof['status'],checks=proof['checks'],retired_files=len(rows),
        released_unique_allocated_bytes=cleanup['released_unique_allocated_bytes'],native_host_sdk_gpu_executed=False)))

if __name__=='__main__':main()
