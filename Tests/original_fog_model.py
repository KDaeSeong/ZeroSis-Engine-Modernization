"""Strict C++14 CPU-only fog reference checks and owned-intermediate receipts."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import struct
import sys

sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[1]
ROOT=PROJECT/'evidence/world_terrain_original/phase2/model'
sys.path.insert(0,str(PROJECT/'tools'));sys.path.insert(0,str(PROJECT/'Tests'))
import build_exit_confirm_host as common
from menu_replay_restoration import build_cxx14
from native_build import run
from menu_suite_storage import storage


def write_new(path,value):
    with path.open('x',encoding='utf8',newline='\n') as stream:
        json.dump(value,stream,indent=1,ensure_ascii=False);stream.write('\n')


def golden(path):
    # Independent Euclidean nearest-centre raster, without axial cube rounding.
    w,h,tph=8,4,16;tw,th=w*tph,h*tph;spacing=0.866025404
    raw=[]
    for y in range(th):
        for x in range(tw):
            px,py=(x+0.5)/tph,(y+0.5)/tph*spacing
            best=None
            for row in range(h):
                for col in range(w):
                    dx=abs(px-col-(row%2)*0.5);dx=min(dx,w-dx)
                    dy=abs(py-row*spacing);dy=min(dy,h*spacing-dy)
                    value=dx*dx+dy*dy
                    if best is None or value<best[0]:best=value,col,row
            _,col,row=best
            raw.append((1 if col<4 else 0,1 if col==3 and row==2 else 0))
    values=raw
    taps=(1,4,6,4,1)
    for vertical in (False,True):
        filtered=[]
        for y in range(th):
            for x in range(tw):
                value=[0.0,0.0]
                for index,weight in enumerate(taps):
                    dx,dy=(0,index-2) if vertical else (index-2,0)
                    sample=values[((y+dy)%th)*tw+(x+dx)%tw]
                    for channel in range(2):value[channel]+=sample[channel]*weight/16
                filtered.append(tuple(value))
        values=filtered
    points=[(x,y) for y in (0,1,7,15,16,23,31,32,39,47,55,63)
            for x in (0,1,3,47,48,55,56,61,62,63,64,65,66,71,72,79,80,95,111,127)]
    distances=[]
    for z in (-50.0,-10.0,-0.125,-1e-9,0.0,1e-9,0.125,10.0,50.0):
        for k,density,ramp in ((0.02,0.0002,1.0),(0.003,0.02,0.25),(0.1,0.1,0.7)):
            x,y=12.5,-3.75;c=struct.unpack('<f',struct.pack('<f',1.442695))[0];scale=c*math.log(2)
            integral=-k*scale if z==0 else -math.expm1(z*k*scale)/z
            exponent=integral*(x*x+y*y+z*z)*density*scale
            expected=-math.expm1(min(0.0,exponent))*ramp
            distances.append((x,y,z,k,density,ramp,expected))
    text='#pragma once\n'
    text+='struct GoldenMaskTexel{unsigned x,y;double r,b;};\nconstexpr GoldenMaskTexel GoldenMaskTexels[]={\n'
    for x,y in points:text+='{'+f'{x},{y},{values[y*tw+x][0]:.17g},{values[y*tw+x][1]:.17g}'+'},\n'
    text+='};\n'
    totalR=sum(value[0] for value in values);totalB=sum(value[1] for value in values)
    text+=f'constexpr double GoldenMaskTotalR={totalR:.17g},GoldenMaskTotalB={totalB:.17g};\n'
    text+='struct GoldenDistance{double x,y,z,k,density,ramp,expected;};\nconstexpr GoldenDistance GoldenDistances[]={\n'
    for row in distances:text+='{'+','.join(format(value,'.17g') for value in row)+'},\n'
    text+='};\n';path.write_text(text,encoding='ascii')
    return dict(mask=dict(width=tw,height=th,texels=len(values),checked_texels=len(points),
        total_explored=totalR,total_visible=totalB,kernel=taps,
        method='Euclidean nearest wrapped hex centre, then independent separable scalar convolution; no cube rounding'),
        distance_cases=len(distances),distance_method='Python double expm1 with the two retail float32 1.442695 multipliers',
        generated=common.artifact(path))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--attempt',type=int,default=0);args=parser.parse_args()
    assert 0<=args.attempt<=9
    stage=ROOT/('cpu' if args.attempt==0 else f'cpu_retry{args.attempt:02d}')
    assert not stage.exists(),'Inspect the prior attempt; use an explicitly named retry after resolving its cause'
    assert not any(os.environ.get(name) for name in ('CL','_CL_','LINK'))
    stage.mkdir(parents=True);build=stage/'build';build.mkdir()
    inputs=[PROJECT/name for name in ('Source/Presentation/OriginalFogModel.h','Tests/original_fog_model.cpp',
        'Tests/original_fog_model.py','evidence/world_terrain_original/phase2/model/bytecode/result.json')]
    before=[common.artifact(path) for path in inputs]
    source=inputs[0].read_text('ascii')
    assert not re.search(r'\b(rand|srand|random_device|CreateWindow|D3D11CreateDevice|LoadLibrary)\s*\(',source)
    assert '#include <windows' not in source and '#include <d3d' not in source
    assert not any(token in source for token in ('terrainId','continent','PlotInput','WorldView.h','OriginalTerrainGeometry.h'))
    reference=golden(build/'original_fog_golden.h')
    write_new(stage/'started.json',dict(inputs=before,golden=reference,
        approved_execution='Compiler/linker, dumpbin and KERNEL32-only CPU console',
        host_sdk_clr_hwnd_gpu_audio_or_game_execution=False))
    compiled=build_cxx14('original_fog_model',build,stage,inputs[1],[PROJECT/'Source/Presentation',build])
    imported=run([Path(compiled['compiler']).with_name('dumpbin.exe'),'/dependents',compiled['path']],cwd=build,timeout=30)
    names=sorted(set(re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$',imported.stdout.decode('mbcs',errors='replace'),re.M)))
    assert imported.returncode==0 and {name.lower() for name in names}=={'kernel32.dll'},names
    (stage/'imports.txt').write_text(imported.stdout.decode('mbcs',errors='replace'),encoding='utf8')
    executed=common.artifact(compiled['path'])
    done=run([compiled['path']],cwd=build,timeout=60)
    stdout=done.stdout.decode('ascii');stderr=done.stderr.decode('ascii')
    (stage/'console.txt').write_text(stdout+stderr,encoding='ascii')
    match=re.fullmatch(r'PASS_ORIGINAL_FOG_MODEL checks=(\d+)\s*',stdout)
    assert done.returncode==0 and not stderr and match,(done.returncode,stdout,stderr)
    after=[common.artifact(path) for path in inputs];assert before==after
    rows=[]
    for path in sorted(build.iterdir()):
        assert path.is_file() and path.suffix in ('.exe','.obj','.map','.rsp','.cmd','.h')
        row=dict(common.artifact(path),allocated_bytes=storage.allocated(path))
        assert row['links']==1 and not row['file_attributes']&0x401
        rows.append(row)
    write_new(stage/'cleanup_plan.json',dict(schema='zerosis.original_fog.cpu_cleanup.v1',directory=str(build),
        files=rows,protected_inputs=after,exact_owned_intermediates_only=True))
    for row in rows:
        path=Path(row['path']);assert path.is_relative_to(build)
        current=common.artifact(path)
        assert all(current[key]==row[key] for key in ('bytes','sha256','file_identity','mtime_ns','file_attributes','links'))
        path.unlink()
    assert not any(build.iterdir());build.rmdir()
    cleanup=dict(status='PASS_EXACT_OWNED_CPU_INTERMEDIATES_REMOVED',files=rows,deleted_files=len(rows),
        deleted_logical_bytes=sum(row['bytes'] for row in rows),
        released_unique_allocated_bytes=sum(row['allocated_bytes'] for row in rows),protected_inputs_unchanged=True)
    write_new(stage/'cleanup_result.json',cleanup)
    proof=dict(schema='zerosis.original_fog.cpu_model.v1',status='PASS_PRODUCTION_FOG_MODEL_CXX14',
        checks=int(match[1]),inputs_before=before,inputs_after=after,build=compiled,executed_console=executed,
        imported_dlls=names,golden=reference,source_has_no_game_rng_or_device_calls=True,
        mask_inputs='Only revealed/visible booleans; exact unknown ownership discards terrain and LUT colour inputs',
        independent_tile_picking_not_modified=True,host_sdk_clr_hwnd_gpu_audio_or_game_executed=False,
        gpu_parity_verified=False,retained_test_executable=False,cleanup=common.artifact(stage/'cleanup_result.json'),
        candidate_policies=['R=explored/B=visible/G=1-R channel interpretation and 16 texels per hex mask.',
            'State-only nearest-hex raster at texel centres, separable 1,4,6,4,1 / 16 smoothing.',
            'Linear texel-centre normalized sampling with clamp LUT and caller-selected clamp/wrap 2D.',
            'Distance heightK/density restricted to finite nonnegative controlled inputs; delta.z=0 uses its continuous limit.',
            'Fixed three cloud UV scales, speeds and phases; no retail flow-field equation claim.'])
    write_new(stage/'result.json',proof)
    print(json.dumps(dict(status=proof['status'],checks=proof['checks'],result=str(stage/'result.json'),
        cleanup_files=len(rows),released_unique_allocated_bytes=cleanup['released_unique_allocated_bytes'],
        host_sdk_gpu_executed=False)))


if __name__=='__main__':main()
