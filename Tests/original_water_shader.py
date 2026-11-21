"""Compile the water overlay with strict FXC and check ABI/colour-only boundaries."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode = True
PROJECT = Path(__file__).absolute().parents[1]
STAGE_ROOT = PROJECT/'evidence/world_terrain_original/phase3/shader'
SOURCE = PROJECT/'Source/Presentation/OriginalWaterShader.h'
TYPES = PROJECT/'Source/Presentation/OriginalWaterGpuTypes.inc'
FXC_SHA = 'ced7c1f95e4dffb614971826625e70da6d24aff1b4f2a3ae5952939c9547d7e6'
spec = importlib.util.spec_from_file_location('water_shader_storage', PROJECT/'tools/audit_exit_host_storage.py')
storage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(storage)


def ref(path):
    path = Path(path).absolute()
    before = storage.ordinary(path)
    sha, allocation = storage.digest(path),storage.allocated(path)
    after = storage.ordinary(path)
    assert storage.metadata(before)==storage.metadata(after)
    return dict(path=str(path),**storage.metadata(after),sha256=sha,allocated_bytes=allocation)


def write_new(path,value):
    with path.open('x',encoding='utf8') as stream:
        json.dump(value,stream,indent=2)
        stream.write('\n')


def source_checks(shader):
    clean = re.sub(r'//[^\n]*','',shader)
    pixel = clean[clean.index('float4 pixelMain('):]
    gate = pixel.index('if(state.y==0)discard;')
    return dict(
        one_float_colour_output=':SV_Target0' in pixel and not re.search(r'SV_Target[1-9]|SV_Depth|RWTexture|RWBuffer|Interlocked',clean),
        exact_plot_state_type='Texture2D<uint2> PlotState:register(t14);' in clean,
        exact_state_load_before_unknown_gate=pixel.index('PlotState.Load(')<gate,
        all_material_reads_after_exact_unknown_gate=all(match.start()>gate for match in re.finditer(r'\.Sample(?:Level)?\(',pixel)),
        no_integer_id_or_depth_store=not re.search(r'\.Store\(|SV_Target1|SV_Depth',clean),
        mirrored_uv_zero='float2 a=retail*uvScales.x+translation;' in pixel,
        mirrored_uv_one='float2 b=retail*float2(-1,1)*uvScales.y+translation;' in pixel,
        mirrored_uv_two='float2 c=-retail*uvScales.z+translation;' in pixel,
        mirrored_uv_three='float2 d=retail*float2(1,-1)*uvScales.w+translation;' in pixel,
        original_depth_lookup_coordinate='float u=1-saturate(4*p.depth);' in pixel,
        original_lookup_row_and_lod='WaterDepth.SampleLevel(ClampSampler,float2(u,0),0)' in pixel,
        current_world_to_original_xy='p.canonical*float2(1,-1)*eye.w' in pixel,
        presentation_clock_only='float translation=shade.x*motion.x;' in pixel and not re.search(r'\b(?:rand|srand|noise)\s*\(',clean),
        fog_postpass_disables_old_hidden_dim='shade.w>0.5||state.y==2?1.0:0.30' in pixel,
        no_second_fow_or_distance_pass=not any(name in clean for name in ('FowColourKey','FogRamp','DistanceFactor','FogMask')),
        coast_uses_explicit_owner_independent_water_weight='colour=lerp(bank.rgb,foam.rgb,saturate(p.depth));' in pixel,
    )


def reflection(listing,profile):
    if profile=='vs_5_0':
        constants=[('viewProjection',0,64)]
        bindings=[('Camera','cb0')]
    else:
        constants=[('placement',0,16),('mapInfo',16,16),('shade',32,16),
                   ('uvScales',48,16),('eye',64,16),('motion',80,16)]
        names=['WaterDepth','WaterBumps','WaterSky','RiverAlpha','RiverDiffuse','RiverRough','RiverSmooth',
               'CoastWave','BankDiffuse','BankEnd1','BankEnd2','BankHeight','GenericBankDiffuse','GenericBankSpecular','PlotState']
        bindings=[(name,'t'+str(index)) for index,name in enumerate(names)]
        bindings += [('WrapSampler','s0'),('ClampSampler','s1'),('Draw','cb1')]
    offsets=[]
    for name,offset,size in constants:
        match=re.search(r'\b'+name+r';\s*//\s*Offset:\s*(\d+)\s+Size:\s*(\d+)',listing)
        offsets.append(dict(name=name,expected_offset=offset,expected_size=size,
            reflected_offset=int(match[1]) if match else None,reflected_size=int(match[2]) if match else None,
            matches=bool(match and int(match[1])==offset and int(match[2])==size)))
    resources=[]
    for name,slot in bindings:
        rows=[line for line in listing.splitlines() if re.match(r'//\s*'+name+r'\s+',line)
              and re.search(r'\b'+slot+r'\s+1\s*$',line)]
        resources.append(dict(name=name,slot=slot,matches=len(rows)==1))
    lines=[line.strip() for line in listing.splitlines() if line.strip() and not line.startswith('//')]
    checks=dict(expected_shader_model=profile in lines,
                constant_offsets_and_sizes=all(row['matches'] for row in offsets),
                expected_resource_slots=all(row['matches'] for row in resources),
                no_uav_or_depth_output=not any('dcl_uav' in line or 'oDepth' in line for line in lines))
    if profile=='ps_5_0':
        checks['one_float_target_zero']=sum(line.startswith('dcl_output') for line in lines)==1 and 'dcl_output o0.xyzw' in lines
        checks['target_zero_signature']=re.search(r'^// SV_Target\s+0\s+xyzw\s+0\s+TARGET\s+float\s+xyzw\s*$',listing,re.M) is not None
        checks['integer_plot_state_resource']=any(line.startswith('dcl_resource_texture2d (uint,uint,uint,uint) t14') for line in lines)
        # The guard is tracked from the compiled integer load, not a colour-mask approximation.
        load=[(i,re.match(r'ld_indexable\(texture2d\)\(uint,uint,uint,uint\) (r\d+)\.([xyzw]), [^,]+, t14\.([xyzw]{4})',line))
              for i,line in enumerate(lines)]
        load=[(i,m) for i,m in load if m]
        boundary=False
        if len(load)==1:
            start,match=load[0]
            register=match[1]+'.'+match[2]
            source_y=match[3]['xyzw'.index(match[2])]=='y'
            window=lines[start+1:min(start+10,len(lines))]
            if source_y:
                direct=[i for i,line in enumerate(window) if line=='discard_z '+register]
                if direct:boundary=not any(line.startswith('sample') for line in lines[:start+1+direct[0]])
                for index,line in enumerate(window):
                    compare=re.fullmatch(r'ieq (r\d+\.[xyzw]), '+re.escape(register)+r', l\(0\)',line)
                    if compare and index+1<len(window) and window[index+1]=='discard_nz '+compare[1]:
                        boundary=not any(item.startswith('sample') for item in lines[:start+index+2])
            guards=[i for i in range(start+1,min(start+8,len(lines))) if lines[i]=='if_z '+register]
            if guards:
                guard=guards[0]
                end=next((i for i in range(guard+1,min(guard+8,len(lines))) if lines[i]=='endif'),None)
                boundary=source_y and end is not None and any('discard' in line or line.startswith('ret') for line in lines[guard+1:end])
                boundary=boundary and not any(line.startswith('sample') for line in lines[:guard])
        checks['compiled_unknown_discard_before_material_samples']=boundary
    return dict(checks=checks,constants=offsets,resources=resources)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--attempt',default='attempt01')
    args=parser.parse_args()
    assert re.fullmatch(r'attempt\d{2}',args.attempt)
    stage=STAGE_ROOT/args.attempt
    assert not stage.exists(),'Inspect the owned attempt before retrying'
    assert not any(path.exists() and os.stat(path,follow_symlinks=False).st_file_attributes&0x400 for path in (stage,*stage.parents))
    inputs=[ref(path) for path in (SOURCE,Path(__file__))]
    cpu_types=ref(TYPES) if TYPES.exists() else None
    if cpu_types:inputs.append(cpu_types)
    literals=re.findall(r'R"HLSL\((.*?)\)HLSL"',SOURCE.read_text('utf8'),re.S)
    assert len(literals)==1
    shader=literals[0]
    checks=source_checks(shader)
    assert all(checks.values()),checks
    pin_path=PROJECT/'evidence/world_terrain_original/terrain_shader_semantics.json'
    compiler=ref(json.loads(pin_path.read_text('utf8'))['tool']['path'])
    assert compiler['sha256']==FXC_SHA
    stage.mkdir(parents=True)
    write_new(stage/'started.json',dict(inputs=inputs,compiler=compiler,source_checks=checks,cpu_types_available=bool(cpu_types)))
    temporary=stage/'water.hlsl'
    temporary.write_bytes(shader.encode('ascii'))
    owned=[temporary]
    passes=[]
    try:
        for entry,profile,stem in [('vertexMain','vs_5_0','vertex'),('pixelMain','ps_5_0','pixel')]:
            bytecode,listing=stage/(stem+'.cso'),stage/(stem+'.asm')
            owned.append(bytecode)
            command=[compiler['path'],'/nologo','/Ges','/WX','/T',profile,'/E',entry,
                     '/Fo',str(bytecode),'/Fc',str(listing),str(temporary)]
            done=subprocess.run(command,cwd=stage,capture_output=True,timeout=90,creationflags=subprocess.CREATE_NO_WINDOW)
            log=(done.stdout+done.stderr).decode('mbcs',errors='replace')
            log_path=stage/(stem+'_compiler.txt')
            log_path.write_text(log,encoding='utf8')
            row=dict(entry=entry,profile=profile,command=command,exit_code=done.returncode,log=ref(log_path),compiler_output=log)
            if bytecode.exists():
                assert bytecode.read_bytes()[:4]==b'DXBC'
                row['bytecode']=ref(bytecode)
            if listing.exists():
                row['listing']=ref(listing)
                row['reflection']=reflection(listing.read_text('utf8'),profile)
            passes.append(row)
            if done.returncode:break
    finally:
        assert [ref(row['path']) for row in inputs]==inputs
        assert ref(compiler['path'])==compiler
        files=[ref(path) for path in owned if path.exists()]
        for row in files:
            assert Path(row['path']).is_relative_to(stage) and row['links']==1 and not row['file_attributes']&0x401
            assert ref(row['path'])==row
        write_new(stage/'cleanup_plan.json',dict(files=files,protected_inputs=inputs))
        for row in files:
            assert ref(row['path'])==row
            Path(row['path']).unlink()
        write_new(stage/'cleanup_result.json',dict(status='PASS_EXACT_SHADER_INTERMEDIATES_REMOVED',files=files,
            deleted_files=len(files),deleted_logical_bytes=sum(row['bytes'] for row in files),
            summed_predelete_unique_allocation_bytes=sum(row['allocated_bytes'] for row in files),source_and_original_assets_changed=False))
    passed=len(passes)==2 and all(row['exit_code']==0 and row.get('reflection') and
        row['reflection']['checks'] and all(row['reflection']['checks'].values()) for row in passes)
    result=dict(schema='zerosis.original_water.phase3.strict_shader.v1',
        status='PASS_STRICT_WATER_OVERLAY_COLOUR_ONLY_ABI' if passed else 'FAIL_WATER_SHADER',
        inputs=inputs,compiler=compiler,compiler_pin=ref(pin_path),passes=passes,source_checks=checks,
        literal_sha256=hashlib.sha256(shader.encode('ascii')).hexdigest(),cpu_types_available=bool(cpu_types),
        candidate_operations=['Fresnel/reflection/normal/alpha/bank/cap mixing','Atlas raw-depth calibration','UV scales and independent presentation-time translations'],
        original_operations=['four mirrored UV forms','Depth lookup u=1-saturate(4h), row0, LOD0'],
        cleanup=ref(stage/'cleanup_result.json'),graphics_device_created=False,
        host_gamecore_clr_hwnd_gpu_audio_or_game_executed=False,original_gpu_or_image_parity_verified=False)
    write_new(stage/'result.json',result)
    print(json.dumps(dict(status=result['status'],source_checks=len(checks),
        passes=[dict(profile=row['profile'],exit_code=row['exit_code'],reflection_checks=row.get('reflection',{}).get('checks'),compiler_output=row['compiler_output'] if row['exit_code'] else '') for row in passes],
        cpu_types_available=bool(cpu_types),graphics_device_created=False)))
    if not passed:raise SystemExit(1)


if __name__=='__main__':
    main()
