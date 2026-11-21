"""Compile the production state adapter and run an isolated, KERNEL32-only CPU console."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import sys

sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[1]
ROOT=PROJECT/'evidence/world_terrain_original/phase2/state'
sys.path.insert(0,str(PROJECT/'tools'));sys.path.insert(0,str(PROJECT/'Tests'))
import build_exit_confirm_host as common
from menu_replay_restoration import build_cxx14
from native_build import run
from menu_suite_storage import storage


def write_new(path,value):
    with path.open('x',encoding='utf8',newline='\n') as stream:
        json.dump(value,stream,indent=1,ensure_ascii=False);stream.write('\n')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--attempt',type=int,default=0);args=parser.parse_args()
    assert 0<=args.attempt<=9
    stage=ROOT/('cpu' if args.attempt==0 else f'cpu_retry{args.attempt:02d}')
    assert not stage.exists(),'Inspect the prior attempt before creating a named retry'
    assert not any(os.environ.get(name) for name in ('CL','_CL_','LINK'))
    stage.mkdir(parents=True);build=stage/'build';build.mkdir()
    inputs=[PROJECT/name for name in ('Source/Presentation/OriginalFogState.h','Source/Presentation/OriginalFogModel.h',
        'Tests/original_fog_state.cpp','Tests/original_fog_state.py')]
    before=[common.artifact(path) for path in inputs]
    assert before[1]['sha256']=='e4c8fa8ac04bb9a4ef08b6135071b596db551ee5e2a9c5db822cd15a8a80b8f9'
    header=inputs[0].read_text('ascii')
    accessed=sorted(set(re.findall(r'\b(?:view|plot)\.([A-Za-z_]\w*)',header)))
    assert accessed==['gridHeight','gridWidth','plots','revealed','visible','wrapX','wrapY','x','y'],accessed
    assert header.count('#include')==1 and '#include "OriginalFogModel.h"' in header
    assert not re.search(r'\b(rand|srand|CreateWindow|D3D11CreateDevice|LoadLibrary)\s*\(',header)
    write_new(stage/'started.json',dict(inputs=before,structural_view_fields=accessed,
        host_sdk_clr_hwnd_gpu_audio_or_game_execution=False))
    compiled=build_cxx14('original_fog_state',build,stage,inputs[2],[PROJECT/'Source/Presentation'])
    imported=run([Path(compiled['compiler']).with_name('dumpbin.exe'),'/dependents',compiled['path']],cwd=build,timeout=30)
    names=sorted(set(re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$',imported.stdout.decode('mbcs',errors='replace'),re.M)))
    assert imported.returncode==0 and {name.lower() for name in names}=={'kernel32.dll'},names
    (stage/'imports.txt').write_text(imported.stdout.decode('mbcs',errors='replace'),encoding='utf8')
    executed=common.artifact(compiled['path']);done=run([compiled['path']],cwd=build,timeout=60)
    stdout=done.stdout.decode('ascii');stderr=done.stderr.decode('ascii')
    (stage/'console.txt').write_text(stdout+stderr,encoding='ascii')
    match=re.fullmatch(r'PASS_ORIGINAL_FOG_STATE checks=(\d+)\s*',stdout)
    assert done.returncode==0 and not stderr and match,(done.returncode,stdout,stderr)
    after=[common.artifact(path) for path in inputs];assert before==after
    rows=[]
    for path in sorted(build.iterdir()):
        assert path.is_file() and path.suffix in ('.exe','.obj','.map','.rsp','.cmd')
        row=dict(common.artifact(path),allocated_bytes=storage.allocated(path))
        assert row['links']==1 and not row['file_attributes']&0x401;rows.append(row)
    write_new(stage/'cleanup_plan.json',dict(directory=str(build),files=rows,protected_inputs=after))
    for row in rows:
        path=Path(row['path']);assert path.is_relative_to(build)
        actual=common.artifact(path)
        assert all(actual[key]==row[key] for key in ('bytes','sha256','file_identity','mtime_ns','file_attributes','links'))
        path.unlink()
    assert not any(build.iterdir());build.rmdir()
    cleanup=dict(status='PASS_EXACT_OWNED_CPU_INTERMEDIATES_REMOVED',files=rows,deleted_files=len(rows),
        deleted_logical_bytes=sum(row['bytes'] for row in rows),
        released_unique_allocated_bytes=sum(row['allocated_bytes'] for row in rows),protected_inputs_unchanged=True)
    write_new(stage/'cleanup_result.json',cleanup)
    result=dict(schema='zerosis.original_fog.state_cpu.v1',status='PASS_PRODUCTION_STATE_ADAPTER_CXX14',
        checks=int(match[1]),inputs_before=before,inputs_after=after,build=compiled,executed_console=executed,
        imported_dlls=names,structural_view_fields=accessed,compiler_and_linker_warnings=0,
        key_fields='Grid dimensions/wrapping plus canonical row-major revealed/visible booleans only',
        ignored_metamorphic_inputs='Camera, animation time, zoom, seed, unit count, selection, terrain IDs, heights, continent, feature, plot index',
        maximum_cells=16384,maximum_axis=256,exact_coverage_required=True,odd_height_vertical_wrap_rejected=True,
        invalid_grid_equality_policy='SameFogGrid returns false for invalid grid shape or visible-but-unrevealed states',
        retained_test_executable=False,cleanup=common.artifact(stage/'cleanup_result.json'),
        host_sdk_clr_hwnd_gpu_audio_or_game_executed=False,gpu_mask_or_cache_acceptance_verified=False)
    write_new(stage/'result.json',result)
    print(json.dumps(dict(status=result['status'],checks=result['checks'],result=str(stage/'result.json'),
        cleanup_files=len(rows),released_unique_allocated_bytes=cleanup['released_unique_allocated_bytes'])))


if __name__=='__main__':main()
