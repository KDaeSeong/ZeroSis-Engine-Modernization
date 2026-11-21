"""Exploration-safe water topology/geometry CPU checks; never loads the Host, SDK or a graphics device."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import struct
import sys

sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[1]
ROOT=PROJECT/'evidence/world_terrain_original/phase3/model'
sys.path.insert(0,str(PROJECT/'tools'));sys.path.insert(0,str(PROJECT/'Tests'))
import build_exit_confirm_host as common
from menu_replay_restoration import build_cxx14
from native_build import run
from menu_suite_storage import storage


def write_new(path,value):
    with path.open('x',encoding='utf8',newline='\n') as stream:
        json.dump(value,stream,indent=1,ensure_ascii=False);stream.write('\n')


def words_hash(words):
    result=14695981039346656037
    for word in words:
        for octet in struct.pack('<I',word&0xffffffff):result=((result^octet)*1099511628211)&0xffffffffffffffff
    return result


def golden(path):
    cases=[]
    # Independent axial coordinate addition, rather than production parity-offset neighbors.
    delta=((0,1),(1,0),(1,-1),(0,-1),(-1,0),(-1,1))
    for width,height in ((1,2),(2,2),(7,6),(8,6)):
        for wrapX in (False,True):
            for wrapY in (False,True):
                cells=[]
                for y in range(height):
                    for x in range(width):
                        cells.append(dict(known=(x+3*y)%7!=0,water=(x+2*y)%3==0,
                            hills=(x+y)%2!=0,mountain=(x+2*y)%11==0,terrain=(x+y)%5,
                            river=[(3*x+y+slot)%4!=0 for slot in range(3)],
                            flow=[-1 if (x+y+slot)%3==0 else slot if (x+y+slot)%3==1 else slot+3 for slot in range(3)]))
                def neighbor(x,y,direction):
                    q=x-y//2;dq,dr=delta[direction];nr=y+dr;nq=q+dq;nc=nq+nr//2
                    if wrapX:nc%=width
                    if wrapY:nr%=height
                    return (nc,nr,True) if 0<=nc<width and 0<=nr<height else (-1,-1,False)
                def style(cell):
                    if cell['mountain']:return 11
                    base={0:1,1:3,2:7,3:9,4:5}[cell['terrain']]
                    return base+int(cell['hills'])
                neighbor_words=[];waters=[];coasts=[];rivers=[]
                for y in range(height):
                    for x in range(width):
                        for direction in range(6):neighbor_words.extend(neighbor(x,y,direction))
                        owner=y*width+x;cell=cells[owner]
                        if not cell['known']:continue
                        if cell['water']:waters.append(owner)
                        for slot in range(3):
                            direction=slot+1;nc,nr,exists=neighbor(x,y,direction)
                            if not exists:continue
                            other=nr*width+nc;next_cell=cells[other]
                            if not next_cell['known']:continue
                            land_style=style(next_cell if cell['water'] else cell) if cell['water']!=next_cell['water'] else 0
                            record=[owner,other,direction,-1,int(cell['water']),int(next_cell['water']),land_style]
                            if cell['water']!=next_cell['water']:coasts.append(record)
                            if cell['river'][slot]:rivers.append(record[:3]+[cell['flow'][slot]]+record[4:])
                words=[0x77617465]+waters+[0x636f6173]+[word for record in coasts for word in record]+[0x72697672]+[word for record in rivers for word in record]
                cases.append(dict(width=width,height=height,wrapX=wrapX,wrapY=wrapY,water=len(waters),coasts=len(coasts),rivers=len(rivers),
                    hash=words_hash(words),neighbors=words_hash(neighbor_words)))
    style_names=('Default','Grass','GrassHill','Plains','PlainsHill','Snow','SnowHill','Desert','DesertHill','Tundra','TundraHill','Mountain','DefaultShallows')
    depths=[(value,1-max(0,min(1,4*value))) for value in (-1e308,-1,-0.01,0,0.0625,0.125,0.1875,0.25,0.250001,1,1e308)]
    text='#pragma once\n#include <cstdint>\n'
    text+='struct GoldenWaterCase{int width,height;bool wrapX,wrapY;unsigned water,coasts,rivers;std::uint64_t hash,neighbors;};\n'
    text+='constexpr GoldenWaterCase GoldenWaterCases[]={\n'
    for case in cases:
        text+='{'+f"{case['width']},{case['height']},{str(case['wrapX']).lower()},{str(case['wrapY']).lower()},{case['water']},{case['coasts']},{case['rivers']},{case['hash']}ull,{case['neighbors']}ull"+'},\n'
    text+='};\nconstexpr const char* GoldenStyleNames[]={'+','.join('"'+name+'"' for name in style_names)+'};\n'
    text+='struct GoldenDepth{double input,output;};\nconstexpr GoldenDepth GoldenDepths[]={\n'
    for value,expected in depths:text+='{'+format(value,'.17g')+','+format(expected,'.17g')+'},\n'
    text+='};\n';path.write_text(text,encoding='ascii')
    return dict(cases=cases,styles=style_names,depth_cases=len(depths),generated=common.artifact(path),
        method='Independent Python axial neighbor addition with floor offset conversion; SHA-pinned SDK ownership/flow contract; no production offset formulas invoked')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--attempt',type=int,default=0);args=parser.parse_args();assert 0<=args.attempt<=9
    stage=ROOT/('cpu' if args.attempt==0 else f'cpu_retry{args.attempt:02d}')
    assert not stage.exists(),'Inspect the prior attempt; use a new named retry after resolving its cause'
    assert not any(os.environ.get(name) for name in ('CL','_CL_','LINK'))
    stage.mkdir(parents=True);build=stage/'build';build.mkdir()
    inputs=[PROJECT/name for name in ('Source/Presentation/OriginalWaterModel.h','Source/Presentation/OriginalWaterState.h',
        'Source/Presentation/OriginalTerrainModel.h','Tests/original_water_model.cpp','Tests/original_water_model.py',
        'evidence/world_terrain_original/phase3/semantics/sdk_river_contract.json',
        'evidence/world_terrain_original/phase3/semantics/shader_semantics.json')]
    before=[common.artifact(path) for path in inputs]
    sdk=json.loads(inputs[-2].read_text('utf8'));assert sdk['status']=='PASS_READ_ONLY_PUBLIC_SDK_RIVER_EDGE_CONTRACT'
    source=inputs[0].read_text('ascii');state=inputs[1].read_text('ascii')
    assert not re.search(r'\b(rand|srand|CreateWindow|D3D11CreateDevice|LoadLibrary|GetProcAddress)\s*\(',source+state)
    assert '#include <windows' not in source+state and '#include <d3d' not in source+state
    assert 'WorldViewRenderer.h' not in source+state and 'OriginalWaterPackage.h' not in source+state
    reference=golden(build/'original_water_golden.h')
    write_new(stage/'started.json',dict(inputs=before,golden=reference,
        host_sdk_clr_hwnd_gpu_audio_or_game_execution=False))
    compiled=build_cxx14('original_water_model',build,stage,inputs[3],[PROJECT/'Source/Presentation',build])
    imports=run([Path(compiled['compiler']).with_name('dumpbin.exe'),'/dependents',compiled['path']],cwd=build,timeout=30)
    names=sorted(set(re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$',imports.stdout.decode('mbcs',errors='replace'),re.M)))
    assert imports.returncode==0 and {name.lower() for name in names}=={'kernel32.dll'},names
    (stage/'imports.txt').write_text(imports.stdout.decode('mbcs',errors='replace'),encoding='utf8')
    executable=common.artifact(compiled['path']);done=run([compiled['path']],cwd=build,timeout=90)
    stdout=done.stdout.decode('ascii');stderr=done.stderr.decode('ascii');(stage/'console.txt').write_text(stdout+stderr,encoding='ascii')
    match=re.fullmatch(r'PASS_ORIGINAL_WATER_MODEL checks=(\d+)\s*',stdout)
    assert done.returncode==0 and not stderr and match,(done.returncode,stdout,stderr)
    after=[common.artifact(path) for path in inputs];assert before==after
    rows=[]
    for path in sorted(build.iterdir()):
        assert path.is_file() and path.suffix in ('.exe','.obj','.map','.rsp','.cmd','.h')
        row=dict(common.artifact(path),allocated_bytes=storage.allocated(path));assert row['links']==1 and not row['file_attributes']&0x401
        rows.append(row)
    write_new(stage/'cleanup_plan.json',dict(directory=str(build),files=rows,protected_inputs=after,exact_owned_intermediates_only=True))
    for row in rows:
        path=Path(row['path']);assert path.is_relative_to(build);actual=common.artifact(path)
        assert all(actual[key]==row[key] for key in ('bytes','sha256','file_identity','mtime_ns','file_attributes','links'));path.unlink()
    assert not any(build.iterdir());build.rmdir()
    cleanup=dict(status='PASS_EXACT_OWNED_CPU_INTERMEDIATES_REMOVED',files=rows,deleted_files=len(rows),
        deleted_logical_bytes=sum(row['bytes'] for row in rows),released_unique_allocated_bytes=sum(row['allocated_bytes'] for row in rows),
        protected_inputs_unchanged=True)
    write_new(stage/'cleanup_result.json',cleanup)
    result=dict(schema='zerosis.original_water.model_cpu.v1',status='PASS_PRODUCTION_WATER_MODEL_CXX14',checks=int(match[1]),
        inputs_before=before,inputs_after=after,build=compiled,executed_console=executable,imported_dlls=names,
        golden=reference,retained_test_executable=False,cleanup=common.artifact(stage/'cleanup_result.json'),
        privacy='Capture ignores guarded unknown fields and inactive flow; topology requires both endpoints explored; height callbacks never query unknown/outside ownership',
        budgets=dict(max_axis=256,max_cells=16384,max_edges=98304,max_vertices=2097152),
        original_rules='SDK canonical E/SE/SW edge ownership, direction-specific flow pairs, offset parity, water shader UV sign patterns and 1-saturate(4h) depth-colour coordinate',
        candidates=['Atlas-following colour geometry instead of retail constant water plane; no original height buffer writes.',
            'Flat hex water fans, coast8/river4 segments with deterministic detail reduction under 2M vertices.',
            'Default widths/lift/UV scale/depth, coast style selection and band0 interpretation.',
            'Profile y as bounded lateral meander with endpoints corrected to zero, units64.',
            'Unknown vertex ownership reuses the explored range owner centre height; no unknown callback.',
            'Public SDK has no lake getter; actual capture lake=false does not establish absence of lakes.',
            'Retail river VS time-shift is represented, but confirmed PS0 ignores that coordinate and final flow speed is unverified.'],
        host_sdk_clr_hwnd_gpu_audio_or_game_executed=False,gpu_or_native_geometry_parity_verified=False)
    write_new(stage/'result.json',result)
    print(json.dumps(dict(status=result['status'],checks=result['checks'],result=str(stage/'result.json'),
        deleted_files=len(rows),released_unique_allocated_bytes=cleanup['released_unique_allocated_bytes'])))


if __name__=='__main__':main()
