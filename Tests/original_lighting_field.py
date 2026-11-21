"""Bounded H68->N66 and raw/guarded40-step shadow references; pure C++14 CPU only."""
from __future__ import annotations
import argparse
import gzip
import json
import math
import os
from pathlib import Path
import re
import struct
import sys

sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[1]
ROOT=PROJECT/'evidence/world_terrain_original/phase6/field_cpu'
sys.path[0:0]=[str(PROJECT/'tools'),str(PROJECT/'Tests')]
import build_exit_confirm_host as common
from menu_replay_restoration import build_cxx14
from native_build import run
from menu_suite_storage import storage
import original_lighting_model as prior_lighting


def write_new(path,value):
    with path.open('x',encoding='utf8',newline='\n') as stream:json.dump(value,stream,indent=1,ensure_ascii=False);stream.write('\n')


def f32(value):return struct.unpack('<f',struct.pack('<f',value))[0]
def unit(value):return max(0,min(1,value))
RISE=struct.unpack('<f',bytes.fromhex('3d04a13e'))[0]
INVERSE96=struct.unpack('<f',bytes.fromhex('abaa2a3c'))[0]
OFFSET=f32(f32(15300)/f32(65535));SCALE=f32(2.3)/255;ROW=f32(0.866025404)


def raw_reference(initial,alpha,length,scale,bias):
    origin=initial*scale*255+bias;rise=length*RISE
    # Closed ray-height positions and a reduction over independent witnesses,
    # rather than the production iterative ray loop.
    occluders=[1-unit((value*255-64)*INVERSE96) for index,value in enumerate(alpha)
               if value*255*scale>origin+(index+2)*rise]
    lit=min([1.0]+occluders);return (1-lit)*bias,lit


def atlas_alpha(x,y):
    ix,iy=math.floor(x),math.floor(y);fx,fy=x-ix,y-iy;value=0.0
    for dy,wy in ((0,1-fy),(1,fy)):
        for dx,wx in ((0,1-fx),(1,fx)):
            cx,cy=(ix+dx)%128,(iy+dy)%128
            raw=0.2+0.35*(cx%16)/15+0.1*(cy%8)/7
            encoded=f32(raw-OFFSET);value+=unit(encoded+OFFSET)*wx*wy
    return value


def golden(path):
    raw=[];traces=[]
    for case in range(36):
        initial=(0.1,0.25,0.5)[case%3];scale=(SCALE,1/255,0.02)[case%3];bias=(0.05,0.125,0.25)[(case//3)%3]
        length=(1/64,math.hypot(1/64,ROW/64),0.04)[(case//9)%3]
        alpha=[0.15+0.45*((case+index)%23)/22 for index in range(40)]
        value,lit=raw_reference(initial,alpha,length,scale,bias);raw.append((initial,length,scale,bias,alpha,value,lit))
    starts=((0.5,0.5),(-0.5,-0.5),(64.5,16.5),(128*512+0.5,-128*512+1.5))
    for x,y in starts:
        for dx,dy in ((-1,1),(1,0.25),(0,-1),(0.5,1)):
            span=max(abs(dx),abs(dy));sx,sy=dx/span,dy/span;length=math.hypot(sx/64,sy*ROW/64)
            initial=atlas_alpha(x,y);alpha=[atlas_alpha(x+(i+2)*sx,y+(i+2)*sy) for i in range(40)]
            value,lit=raw_reference(initial,alpha,length,SCALE,0.125);traces.append((x,y,dx,dy,value,lit))
    quant=[]
    for value in (-100,-0.01,0,0.5/65535,1.5/65535,0.125,0.5,0.99999,1,2,100):
        quant.append((value,math.floor(unit(value)*65535+0.5)))
    text='#pragma once\nstruct GoldenRawShadow{double initial,length,scale,bias;std::array<double,40> alpha;double value,lit;};\nconstexpr GoldenRawShadow GoldenRawShadows[]={\n'
    for initial,length,scale,bias,alpha,value,lit in raw:
        text+='{'+','.join(format(v,'.17g') for v in (initial,length,scale,bias))+',{{'+','.join(format(v,'.17g') for v in alpha)+'}},'+format(value,'.17g')+','+format(lit,'.17g')+'},\n'
    text+='};\nstruct GoldenAtlasShadow{double x,y,dx,dy,value,lit;};\nconstexpr GoldenAtlasShadow GoldenAtlasShadows[]={\n'
    for row in traces:text+='{'+','.join(format(v,'.17g') for v in row)+'},\n'
    text+='};\nstruct GoldenQuantCase{double input;unsigned output;};\nconstexpr GoldenQuantCase GoldenQuant[]={\n'
    for value,expected in quant:text+='{'+format(value,'.17g')+','+str(expected)+'},\n'
    text+='};\n';path.write_text(text,encoding='ascii')
    return dict(raw_cases=len(raw),atlas_cases=len(traces),quant_boundary_cases=len(quant),
        constants=dict(ray_rise=RISE,inverse96=INVERSE96,offset=OFFSET,height_scale=SCALE,row_spacing=ROW,normal_strength=16),
        method='Independent closed ray heights at2..41 and min reduction; periodic four-weight UNORM alpha interpolation from float32 fixture heights; dyadic analytic Sobel derivative and all65536UNORM words',
        generated=common.artifact(path))


def lighting_api_regression():
    root=ROOT/'lighting_api';success=root/'cpu/result.json'
    inputs=[common.artifact(PROJECT/name) for name in ('Source/Presentation/OriginalLightingModel.h','Tests/original_lighting_model.cpp','Tests/original_lighting_model.py')]
    if success.exists():
        old=json.loads(success.read_text('utf8'));current={row['path']:row for row in old['inputs_after']}
        assert all(current[row['path']]==row for row in inputs);return common.artifact(success)
    assert not root.exists(),'Inspect the existing renamed lighting API attempt before continuing'
    prior_lighting.ROOT=root
    arguments=sys.argv
    try:
        sys.argv=[arguments[0]];prior_lighting.main()
    finally:sys.argv=arguments
    proof=json.loads(success.read_text('utf8'));assert proof['status']=='PASS_PRODUCTION_LIGHTING_CXX14' and proof['checks']==3689
    return common.artifact(success)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--attempt',type=int,default=0);args=parser.parse_args();assert 0<=args.attempt<=9
    assert not any(os.environ.get(name) for name in ('CL','_CL_','LINK'))
    regression=lighting_api_regression()
    stage=ROOT/('cpu' if args.attempt==0 else f'cpu_retry{args.attempt:02d}');assert not stage.exists(),'Inspect prior field attempt before creating a retry'
    stage.mkdir(parents=True);build=stage/'build';build.mkdir()
    names=['Source/Presentation/OriginalLightingFieldModel.h','Source/Presentation/OriginalLightingModel.h',
        'Source/Presentation/OriginalWaterOpticsModel.h','Source/Presentation/OriginalTerrainModel.h','Source/Presentation/OriginalTerrainBinding.h',
        'Tests/original_lighting_field.cpp','Tests/original_lighting_field.py',
        'evidence/world_terrain_original/phase5/semantics/shadow/TerrainShaderScreen_3_ps.asm']
    before=[common.artifact(PROJECT/name) for name in names]
    source=(PROJECT/names[0]).read_text('ascii');assert not re.search(r'\b(rand|srand|CreateWindow|LoadLibrary|D3D11CreateDevice)\s*\(',source)
    assert 'WorldView' not in source and 'Package.h' not in source and '<Windows' not in source
    assert 'specularCache' in (PROJECT/names[1]).read_text('ascii')
    reference=golden(build/'original_lighting_field_golden.h')
    write_new(stage/'started.json',dict(inputs=before,reference=reference,renamed_lighting_api_regression=regression,
        root_baseline_complete=True,host_sdk_clr_hwnd_gpu_audio_or_game_executed=False))
    compiled=None;executable=None;dlls=[];failure=None;match=None
    try:
        compiled=build_cxx14('original_lighting_field',build,stage,PROJECT/names[5],[PROJECT/'Source/Presentation',build])
        imports=run([Path(compiled['compiler']).with_name('dumpbin.exe'),'/dependents',compiled['path']],cwd=build,timeout=30)
        dlls=sorted(set(re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$',imports.stdout.decode('mbcs',errors='replace'),re.M)))
        assert imports.returncode==0 and {name.lower() for name in dlls}=={'kernel32.dll'},dlls
        (stage/'imports.txt').write_text(imports.stdout.decode('mbcs',errors='replace'),encoding='utf8')
        executable=common.artifact(compiled['path']);done=run([compiled['path']],cwd=build,timeout=90)
        stdout=done.stdout.decode('ascii');stderr=done.stderr.decode('ascii');(stage/'console.txt').write_text(stdout+stderr,encoding='ascii')
        match=re.fullmatch(r'PASS_ORIGINAL_LIGHTING_FIELD checks=(\d+)\s*',stdout)
        assert done.returncode==0 and not stderr and match,(done.returncode,stdout,stderr)
    except BaseException as error:
        failure=error
        for name in names[:1]+names[5:7]:
            path=PROJECT/name
            with (stage/('failed_'+path.name+'.gz')).open('xb') as stream:stream.write(gzip.compress(path.read_bytes(),mtime=0))
        write_new(stage/'failure.json',dict(error_type=type(error).__name__,message=str(error)[:7000],build=compiled))
    finally:
        after=[common.artifact(PROJECT/name) for name in names];assert before==after;rows=[]
        for path in sorted(build.iterdir()):
            assert path.is_file() and path.suffix in ('.h','.exe','.obj','.map','.rsp','.cmd')
            row=dict(common.artifact(path),allocated_bytes=storage.allocated(path));assert row['links']==1 and not row['file_attributes']&0x401;rows.append(row)
        write_new(stage/'cleanup_plan.json',dict(directory=str(build),files=rows,protected_inputs=after))
        for row in rows:
            path=Path(row['path']);assert path.is_relative_to(build);now=common.artifact(path)
            assert all(now[key]==row[key] for key in ('bytes','sha256','file_identity','mtime_ns','file_attributes','links'));path.unlink()
        assert not any(build.iterdir());build.rmdir()
        write_new(stage/'cleanup_result.json',dict(status='PASS_EXACT_OWNED_FIELD_INTERMEDIATES_REMOVED',files=rows,deleted_files=len(rows),
            deleted_logical_bytes=sum(row['bytes'] for row in rows),released_unique_allocated_bytes=sum(row['allocated_bytes'] for row in rows),protected_inputs_unchanged=True))
    if failure is not None:raise failure
    result=dict(schema='zerosis.original_lighting.phase6.field_cpu.v1',status='PASS_BOUNDED_KNOWN_ONLY_NORMAL_SHADOW_FIELDS_CXX14',checks=int(match[1]),
        inputs_before=before,inputs_after=after,build=compiled,executed_console=executable,imported_dlls=dlls,reference=reference,
        renamed_lighting_api_regression=regression,cleanup=common.artifact(stage/'cleanup_result.json'),retained_executable=False,
        source_contract='Atlas index coordinates are worldX*64 and-worldZ/RowSpacing*64; validate origin(-32,0), never add it to sample indices',
        geometry_contract='64source texels per hex; H68 two-halo centres-1.5..65.5 -> N66 one-halo centres-.5..64.5; no geometry/depth/picking IDs in field output',
        original_operations='Source material-height input and strength16 now traced; Sobel8 and raw40ray algebra, step2..41 and samebias/start+finalamplitude verified',
        safety_policies=['Sparse missing plots remain unknown, duplicates and invalid coordinates rejected.',
            'All four source supports and SDK ownership known before callbacks/heights; unknown normal tap uses known centre.',
            'Unknown or outside shadow ray becomes entirely zero/incomplete; no hidden raw sample callback executes.',
            'Zero direction returns incomplete zero rather than original0/0.',
            'Atlas-relative physical height plus configured offset is clamped to UNORM alpha before bilinear sampling.',
            'UNORM16 conversion is finite-clamped round-half-up candidate, not original GPU tie-mode proof.'],
        candidates=['H68/N66 resolution and RTformat; CPUfloat32cache versus GPUR16F precision.',
            'Current-chunk top8 palette caps and projected material sampler inputs; model seam equality assumes a globally consistent supplier.',
            'Physical atlas-to-original alpha/scale, sun direction/world texel scale and bias-amplitude binding.'],
        bounds=dict(domain_cells=16384,atlas_texels=67108864,max_material_samples_per_tile=4624,normal_owned_payload_bytes=79748,
            normal_plus_shadow_result_payload_bytes=78408,perchunk_budget_bytes=112640,large_atlas_copies=0),
        host_sdk_clr_hwnd_gpu_audio_or_game_executed=False,gpu_pixels_native_screen_or_performance_verified=False)
    write_new(stage/'result.json',result)
    print(json.dumps(dict(status=result['status'],checks=result['checks'],result=str(stage/'result.json'),
        deleted_files=len(rows),released_unique_allocated_bytes=sum(row['allocated_bytes'] for row in rows))))


if __name__=='__main__':main()
