"""Independent scalar/matrix references for original lighting operations, pure C++14 CPU only."""
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
ROOT=PROJECT/'evidence/world_terrain_original/phase5/lighting_cpu'
sys.path[0:0]=[str(PROJECT/'tools'),str(PROJECT/'Tests')]
import build_exit_confirm_host as common
from menu_replay_restoration import build_cxx14
from native_build import run
from menu_suite_storage import storage


def write_new(path,value):
    with path.open('x',encoding='utf8',newline='\n') as stream:
        json.dump(value,stream,indent=1,ensure_ascii=False);stream.write('\n')


def f32(value):return struct.unpack('<f',struct.pack('<f',value))[0]
def unit(value):return max(0,min(1,value))
def dot(a,b):return sum(x*y for x,y in zip(a,b))
def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def normalize(value):return tuple(x/math.sqrt(dot(value,value)) for x in value)
def blend(a,b,t):return tuple((1-t)*x+t*y for x,y in zip(a,b))
def power(value,exponent):return tuple(math.pow(x,exponent) for x in value)
def world_lut(c):return (0.05+0.8*c[0],0.1+0.6*c[1],0.2+0.5*c[2])
def fow_lut(c):return (0.01+0.9*c[2],0.02+0.8*c[1],0.03+0.7*c[0])
def normal(base,sample):
    columns=(normalize(cross(base,(0,1,0))),normalize(cross(base,(1,0,0))),base)
    decoded=tuple(2*x-1 for x in sample)
    return tuple(sum(columns[column][row]*decoded[column] for column in range(3)) for row in range(3))
def literal(value):
    if isinstance(value,bool):return str(value).lower()
    if isinstance(value,(tuple,list)):return '{'+','.join(literal(item) for item in value)+'}'
    return format(value,'.17g')


def golden(path):
    gamma=f32(2.2);inverse=struct.unpack('<f',bytes.fromhex('2fbae83e'))[0]
    irradiance=f32(1.7);floor=f32(0.001);shadow_coefficient=f32(-0.67);fog_base=f32(0.4)
    sobels=[];bases=[];bakes=[];waters=[];finals=[]
    sx_weights=(2,1,-1,-2,1,-1,0,0);sy_weights=(0,1,1,0,-1,-1,2,-2)
    for i in range(64):
        height=tuple(0.5+0.25*math.sin((i+1)*(tap+1)*0.17) for tap in range(8));strength=(i%9-3)*0.4
        sx,sy=dot(height,sx_weights),dot(height,sy_weights);n=normalize((-strength*sx,strength*sy,4))
        sobels.append((height,strength,sx,sy,n,tuple(0.5+0.5*x for x in n)+(0,)))
    for i in range(48):
        base=(0.2+0.01*i,0.1-0.003*i,0.8+0.002*i);sample=(0.2+0.005*i,0.7-0.002*i,0.6+0.004*i)
        bases.append((base,sample,normal(base,sample)))
    for i in range(32):
        base=(0.1,0.15,0.9);sample=(0.45+0.001*i,0.55-0.001*i,0.95);n=normal(base,sample)
        albedo=(0.2+0.005*i,0.3,0.4);a=(0.2,0.3,0.4);b=(0.4,0.35,0.3);light=(0.2,0.3,0.9)
        spec=(0.12,0.16,0.2,0.2+0.02*(i%6));shadow=(-0.25,0.25,0.8,1.25)[i%4]
        # Scalar radiance interpolation independent of the shader's mad grouping.
        linear=tuple(albedo[j]*irradiance*((1-shadow)*a[j]+shadow*b[j])+floor for j in range(3))
        exponent=64*spec[3]+1;spec_factor=math.pow(unit(dot(n,light)),exponent)*exponent*unit(1-shadow)
        specular_linear=tuple(component*spec_factor for component in spec[:3]);specular_alpha=spec[3]*spec_factor
        bakes.append((base,sample,albedo,a,b,light,spec,shadow,n,linear,power(linear,inverse),specular_linear,power(specular_linear,inverse),specular_alpha))
    for q in (-0.25,0,0.5,2,16,17):
        for fresnel in (-0.2,0.35,1.2):
            depth=(0.4,0.35,0.3,0.6);height=0.1875;lambert=0.7;g0=0.02;g1=0 if q>=16 else 0.015;wide=0.003
            light0=(1,0.95,0.85);light1=(0.8,0.9,1);reflection=(0.12,0.2,0.32);reflection_alpha=0.45;reflection_strength=0.4
            shadow=1.2 if len(waters)%2 else 0.35;shadow_strength=0.6;depth_term=unit(4*height)*math.pow(q,3)
            pre=tuple(lambert*(depth[j]+fresnel*(g0*light0[j]+g1*light1[j]))+
                wide*depth[j]*light0[j]+reflection_strength*reflection[j]+depth_term*depth[j] for j in range(3))
            shadowed=tuple(value*(1+shadow_coefficient*unit(shadow)*shadow_strength) for value in pre)
            encoded=power(shadowed,inverse);alpha=unit(depth[3]*(1+reflection_alpha))
            waters.append((depth,height,lambert,fresnel,g0,g1,wide,q,light0,light1,reflection,reflection_alpha,
                reflection_strength,shadow,shadow_strength,pre,shadowed,encoded,alpha,depth_term))
    for i in range(12):
        lit=(0.2+0.01*i,0.3,0.4);albedo=(0.3,0.4,0.5);screen=(0.8,0.7,0.6);use_lit=i%3!=0;use_screen=i%2==0
        active=lit if use_lit else (0,0,0)
        cached=power(tuple(math.pow(albedo[j],gamma)*screen[j]+math.pow(active[j],gamma) for j in range(3)),inverse) if use_screen else active
        world_mask=(-0.2,0.4,1.25)[i%3];world_strength=0.75;replacement=(0.2,0.3,0.4);overlay=(0.02,0.03,0.04,0.25)
        r=(0.25,0.75,1)[i%3];b=(0,0.25,1)[i%3];fog=0.35;fog_colour=(146/255,182/255,243/255)
        world=blend(cached,world_lut(cached),unit(world_mask)*world_strength)
        over=tuple(world[j]*(1-overlay[3])+overlay[j] for j in range(3));before_fow=blend(replacement,over,r)
        transformed=blend(before_fow,fow_lut(before_fow),r*(1-b));result=blend(transformed,fog_colour,fog)+(1,)
        finals.append((lit,albedo,screen,use_lit,use_screen,world_mask,world_strength,replacement,overlay,r,b,fog,fog_colour,cached,before_fow,result))
    row=waters[2];encoded=row[17];overlay=(0.02,0.03,0.04,0.25);r=0.6;b=0.25
    over=tuple(encoded[j]*(1-overlay[3])+overlay[j] for j in range(3));base=blend((fog_base,)*3,over,r)
    water_post=blend(blend(base,fow_lut(base),r*(1-b)),(146/255,182/255,243/255),0.35)+(row[18],)
    header='#pragma once\nnamespace GL=ZeroSisPresentation::OriginalLighting;\n'
    header+='struct GoldenSobelCase{std::array<double,8> height;double strength,sx,sy;GL::Rgb normal;GL::Rgba encoded;};\nconstexpr GoldenSobelCase GoldenSobel[]={\n'
    for row in sobels:header+='{'+literal(row[0])+','+','.join(literal(value) for value in row[1:])+'},\n'
    header+='};\nstruct GoldenBasisCase{GL::Rgb base,sample,expected;};\nconstexpr GoldenBasisCase GoldenBasis[]={\n'
    for row in bases:header+=literal(row)+',\n'
    header+='};\nstruct GoldenBakeCase{GL::Rgb base,normal,albedo,cubeA,cubeB,light;GL::Rgba specular;double shadow;GL::Rgb decoded,diffuseLinear,diffuseEncoded,specularLinear,specularEncoded;double specularAlpha;};\nconstexpr GoldenBakeCase GoldenBake[]={\n'
    for row in bakes:header+=literal(row)+',\n'
    header+='};\nstruct GoldenWater{GL::Rgba depth;double height,lambert,fresnel,g0,g1,wide,q2;GL::Rgb light0,light1,reflection;double reflectionAlpha,reflectionStrength,shadow,shadowStrength;GL::Rgb preShadow,shadowed,encoded;double alpha,depthTerm;};\nconstexpr GoldenWater GoldenWaters[]={\n'
    for row in waters:header+=literal(row)+',\n'
    header+='};\nstruct GoldenFinal{GL::Rgb lit,albedo,screen;bool useLit,useScreen;double worldMask,worldStrength;GL::Rgb replacement;GL::Rgba overlay;double r,b,fog;GL::Rgb fogColour,cached,beforeFow;GL::Rgba result;};\nconstexpr GoldenFinal GoldenFinals[]={\n'
    for row in finals:header+=literal(row)+',\n'
    header+='};\nconstexpr GL::Rgba GoldenWaterPost='+literal(water_post)+';\n';path.write_text(header,encoding='ascii')
    return dict(sobel_cases=len(sobels),basis_cases=len(bases),cache_cases=len(bakes),water_cases=len(waters),final_cases=len(finals),
        generated=common.artifact(path),float_constants=dict(irradiance=irradiance,floor=floor,shadow=shadow_coefficient,water_fow_base=fog_base,gamma=gamma,inverse_gamma=inverse),
        method='Independent Python Sobel matrix, cross-product basis, scalar interpolated radiance, pow specular, rejected-q live cubic term and colour-affine post references; production header not imported')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--attempt',type=int,default=0);args=parser.parse_args();assert 0<=args.attempt<=9
    stage=ROOT/('cpu' if args.attempt==0 else f'cpu_retry{args.attempt:02d}');assert not stage.exists(),'Inspect prior owned attempt before a named retry'
    assert not any(os.environ.get(name) for name in ('CL','_CL_','LINK'))
    stage.mkdir(parents=True);build=stage/'build';build.mkdir()
    names=['Source/Presentation/OriginalLightingModel.h','Source/Presentation/OriginalWaterOpticsModel.h',
        'Tests/original_lighting_model.cpp','Tests/original_lighting_model.py',
        'evidence/world_terrain_original/phase5/semantics/bytecode/CacheBake_0_ps.asm',
        'evidence/world_terrain_original/phase5/semantics/bytecode/CacheBake_1_ps.asm',
        'evidence/world_terrain_original/phase5/semantics/bytecode/NormalCalculate_0_ps.asm',
        'evidence/world_terrain_original/phase5/semantics/bytecode/TerrainShader_0_ps.asm',
        'evidence/world_terrain_original/phase3/semantics/bytecode/WaterShader_2_ps.asm']
    before=[common.artifact(PROJECT/name) for name in names];assert before[1]['sha256']=='7cdb4b6f35271e071d878b31bcdb019cbbf8c1b6384e6fc8ed2201db7d2d68ea'
    source=(PROJECT/names[0]).read_text('ascii');assert not re.search(r'\b(rand|srand|CreateWindow|LoadLibrary|D3D11CreateDevice)\s*\(',source)
    assert 'WorldView' not in source and 'Package.h' not in source and '<Windows' not in source
    reference=golden(build/'original_lighting_golden.h')
    write_new(stage/'started.json',dict(inputs=before,reference=reference,baseline='Root confirmed phase5 baseline complete before this compile',
        host_sdk_clr_hwnd_gpu_audio_or_game_executed=False))
    compiled=None;executable=None;dlls=[];failure=None;match=None
    try:
        compiled=build_cxx14('original_lighting_model',build,stage,PROJECT/names[2],[PROJECT/'Source/Presentation',build])
        imports=run([Path(compiled['compiler']).with_name('dumpbin.exe'),'/dependents',compiled['path']],cwd=build,timeout=30)
        dlls=sorted(set(re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$',imports.stdout.decode('mbcs',errors='replace'),re.M)))
        assert imports.returncode==0 and {name.lower() for name in dlls}=={'kernel32.dll'},dlls
        (stage/'imports.txt').write_text(imports.stdout.decode('mbcs',errors='replace'),encoding='utf8')
        executable=common.artifact(compiled['path']);done=run([compiled['path']],cwd=build,timeout=60)
        stdout=done.stdout.decode('ascii');stderr=done.stderr.decode('ascii');(stage/'console.txt').write_text(stdout+stderr,encoding='ascii')
        match=re.fullmatch(r'PASS_ORIGINAL_LIGHTING_MODEL checks=(\d+)\s*',stdout)
        assert done.returncode==0 and not stderr and match,(done.returncode,stdout,stderr)
    except BaseException as error:
        failure=error
        for name in names[:1]+names[2:4]:
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
        write_new(stage/'cleanup_result.json',dict(status='PASS_EXACT_OWNED_LIGHTING_INTERMEDIATES_REMOVED',files=rows,deleted_files=len(rows),
            deleted_logical_bytes=sum(row['bytes'] for row in rows),released_unique_allocated_bytes=sum(row['allocated_bytes'] for row in rows),protected_inputs_unchanged=True))
    if failure is not None:raise failure
    result=dict(schema='zerosis.original_lighting.phase5.cpu_model.v1',status='PASS_PRODUCTION_LIGHTING_CXX14',checks=int(match[1]),
        inputs_before=before,inputs_after=after,build=compiled,executed_console=executable,imported_dlls=dlls,reference=reference,
        cleanup=common.artifact(stage/'cleanup_result.json'),retained_executable=False,original_sources_modified=False,
        operations=['Original 8-tap Sobel signs and encoded normal; runtime texel offsets remain caller inputs.',
            'Nonorthogonal tangent basis with no base/final renormalization; sampled irradiance direction preserved.',
            'CacheBake1.7 irradiance, unclamped diffuse shadow interpolation, .001 floor, exact inverse gamma, same LUT.',
            'Separate specular target, saturated dot/1-shadow, 64*gloss+1, RGB gamma/LUT with unencoded alpha.',
            'Water raw depth RGB, original Lambert/Fresnel/Gaussian/tint/reflection/q2^3 sum, shadow/gamma/alpha.',
            'Conditional terrain linear cache sum, world LUT, premultiplied overlay, replacement/FOW LUT and fog order.'],
        privacy='Unrevealed guarded wrappers do not call input, cube, LUT or Sobel sample suppliers; zero-R water discards before material input',
        safety_policies=['Degenerate tangent denominator rejects instead of original NaN.',
            'Negative/nonfinite RGB log domains and arithmetic overflow reject rather than clamp.',
            'Guarded Sobel missing taps use explored centre height; original cache source/offset/strength are not inferred.',
            'Unknown terrain returns a separately supplied safe replacement; exact raw functions remain distinct.',
            'Gaussian determinant rejection policies belong to the preserved OpticsModel; its surviving finite secondary q is not erased.'],
        host_sdk_clr_hwnd_gpu_audio_or_game_executed=False,original_gpu_or_screen_parity_verified=False)
    write_new(stage/'result.json',result)
    print(json.dumps(dict(status=result['status'],checks=result['checks'],result=str(stage/'result.json'),
        deleted_files=len(rows),released_unique_allocated_bytes=sum(row['allocated_bytes'] for row in rows))))


if __name__=='__main__':main()
