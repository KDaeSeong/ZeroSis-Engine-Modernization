"""CPU-only strict compilation and ABI/coordinate checks of private field passes."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[1]
sys.path.insert(0,str(PROJECT/'Tests'))
from original_water_shader import ref,write_new
from original_water_surface_shader import offsets,bindings

ROOT=PROJECT/'evidence/world_terrain_original/phase6/review/field_shader'
SOURCE=PROJECT/'Source/Presentation/OriginalLightingFieldShader.h'
FXC=Path(r'C:/Program Files (x86)/Windows Kits/10/bin/10.0.26100.0/x64/fxc.exe')
FXC_SHA='ced7c1f95e4dffb614971826625e70da6d24aff1b4f2a3ae5952939c9547d7e6'

def literals():
    text=SOURCE.read_text('utf8');result={}
    for kind in('Height','Normal'):
        match=re.search(kind+r'ShaderSource\[\]=R"HLSL\((.*?)\)HLSL"',text,re.S);assert match;result[kind.lower()]=match[1]
    return result

def coordinate_proof():
    taps=((-1,0),(-1,-1),(1,-1),(1,0),(-1,1),(1,1),(0,-1),(0,1));count=0;extents=[68,-1]
    for y in range(66):
        for x in range(66):
            cx,cy=x+1,y+1;assert (cx+.5-2)/64==(x-.5)/64 and (cy+.5-2)/64==(y-.5)/64
            for dx,dy in taps:
                assert 0<=cx+dx<68 and 0<=cy+dy<68;extents[0]=min(extents[0],cx+dx,cy+dy);extents[1]=max(extents[1],cx+dx,cy+dy);count+=1
    for i in range(1025):
        u=i/1024;texture=(u*64+1)/66;index=texture*66-.5;assert abs((index-.5)/64-u)<2e-15
    wrapped=0
    for width,height in((4,6),(7,8),(40,24),(256,256)):
        for flags in range(4):
            for column,row in((0,0),(width-1,0),(0,height-1),(width-1,height-1)):
                for y in range(68):
                    for x in range(68):
                        sx=column*64+x-1.5;sy=row*64+y-1.5
                        px=column+(x-1.5)/64;py=row+(y-1.5)/64
                        if flags&1:px-=math.floor(px/width)*width;sx-=math.floor(sx/(width*64))*width*64
                        if flags&2:py-=math.floor(py/height)*height;sy-=math.floor(sy/(height*64))*height*64
                        assert px*64==sx and py*64==sy;wrapped+=1
    noninteger=dict(map_width=40,scale=.014,units=64,projection=.33,unwrapped_source=-.5/64,canonical_source=40-.5/64)
    old=noninteger['unwrapped_source']*64*.014*.33;new=noninteger['canonical_source']*64*.014*.33
    assert abs((old%1)-(new%1))>.01
    noninteger.update(unwrapped_texture_u=old,canonical_texture_u=new,texture_u_difference_mod1=abs((old%1)-(new%1)))
    return dict(normal_pixels=4356,tap_addresses_checked=count,height_index_extents=extents,height_centres=[-1.5/64,65.5/64],
        normal_centres=[-.5/64,64.5/64],normal_shader_mapping='(drawUV*64+1)/66',canonical_linear_mapping_checks=1025,
        wrapflags=[0,1,2,3],canonical_halo_points_checked=wrapped,noninteger_uv_scale_regression=noninteger)

def reflection(listing,stem,profile):
    instructions=[line.strip()for line in listing.splitlines()if line.strip()and not line.startswith('//')]
    checks=dict(shader_model=profile in instructions,no_uav_depth=not any('dcl_uav'in line or'oDepth'in line for line in instructions))
    constants=[];resources=[];load_proof={}
    if profile=='ps_5_0':
        constants=offsets(listing,[('materials',0,128),('origin',128,16),('parameters',144,16),('worldAdapter',160,16)])
        resources=bindings(listing,[('Field','cb4')]+([('Known','t16'),('RawWrap','s0')]if stem=='height'else[('Height','t0'),('Known','t1')]))
        checks['constant_176']=all(v['matches']for v in constants);checks['exact_slots']=all(v['matches']for v in resources)
        checks['only_colour_target0']=sum(line.startswith('dcl_output')for line in instructions)==1 and bool(re.search(r'^// SV_Target\s+0\s+'+('x'if stem=='height'else'xyzw')+r'\s+0\s+TARGET\s+float',listing,re.M))
        mask=16 if stem=='height'else 1
        checks['typed_uint_known']=any(line.startswith('dcl_resource_texture2d (uint,uint,uint,uint) t'+str(mask))for line in instructions)
        loads=[(i,line)for i,line in enumerate(instructions)if line.startswith('ld_indexable(')and re.search(r'\bt'+str(mask)+r'(?:\.|\s|$)',line)]
        protected=[(i,line)for i,line in enumerate(instructions)if(line.startswith('sample_l_indexable(')if stem=='height'else line.startswith('ld_indexable(')and re.search(r'\bt0(?:\.|\s|$)',line))]
        checks['known_loaded_before_protected_inputs']=bool(loads and protected and loads[0][0]<protected[0][0])
        checks['conditional_control_flow_after_mask']=bool(loads and protected and any(line.startswith(('if_z','if_nz','retc'))for line in instructions[loads[0][0]+1:protected[0][0]]))
        checks['no_id_target']=not re.search(r'^// SV_Target\s+1\s',listing,re.M)
        if stem=='height':checks['explicit_mip_zero']=any(line.startswith('sample_l_indexable(')for line in instructions)and not any(line.startswith('sample_indexable(')for line in instructions)
        load_proof=dict(first_known=loads[0]if loads else None,first_protected=protected[0]if protected else None,load_order_is_not_full_cfg_privacy_proof=True)
    return dict(checks=checks,constants=constants,resources=resources,load_proof=load_proof)

def main():
    p=argparse.ArgumentParser();p.add_argument('--attempt',default='attempt01');p.add_argument('--height-only',action='store_true');a=p.parse_args();assert re.fullmatch(r'attempt\d{2}',a.attempt)
    stage=ROOT/a.attempt;assert not stage.exists(),'Inspect old field shader attempt first';stage.mkdir(parents=True)
    inputs=[ref(path)for path in(SOURCE,SOURCE.with_name('OriginalLightingFieldGpuTypes.inc'),SOURCE.with_name('OriginalLightingFieldGpu.inc'),Path(__file__))]
    compiler=ref(FXC);assert compiler['sha256']==FXC_SHA;shader=literals();hashes={k:hashlib.sha256(v.encode('ascii')).hexdigest()for k,v in shader.items()}
    h=shader['height'];n=shader['normal'];checks=dict(height_known_before_material=h.index('if(Known.Load(')<h.index('Diffuse[i].SampleLevel('),
        normal_center_known_before_height=n.index('if(Known.Load(int3(c,0))==0)')<n.index('float center=Height.Load'),
        normal_taps_guarded='if(Known.Load(int3(at,0))==0)return center;return Height.Load'in n,
        height_alpha_eight='a2=a*a,a4=a2*a2,W=a4*a4*weights[i]'in h,missing_half='material.z< -0.5?0.5:0'in h,
        no_camera_mutation='VSSetConstantBuffers(0,'not in SOURCE.with_name('OriginalLightingFieldGpu.inc').read_text('utf8'),
        cb_size='sizeof(LightingFieldConstants)==176'in SOURCE.with_name('OriginalLightingFieldGpuTypes.inc').read_text('utf8'),
        original_material_world_origin='p.height*origin.z+worldAdapter.x'in h and 'tile.y*worldAdapter.y*origin.z'in h,
        original_strength16_default='float normalStrength=16.0f'in SOURCE.with_name('OriginalLightingFieldGpu.inc').read_text('utf8'),
        canonical_wrap_before_any_material=h.index('tile.x-=floor(')<h.index('Diffuse[i].SampleLevel(')and h.index('tile.y-=floor(')<h.index('Diffuse[i].SampleLevel('),
        wrap_source_dimensions='constants.parameters[1]=static_cast<float>(surface.width);constants.parameters[2]=static_cast<float>(surface.height);'in SOURCE.with_name('OriginalLightingFieldGpu.inc').read_text('utf8'))
    coords=coordinate_proof();write_new(stage/'started.json',dict(inputs=inputs,compiler=compiler,literal_sha256=hashes,source_checks=checks,coordinate_proof=coords))
    owned=[];passes=[];reused=[]
    if a.height_only:
        prior_path=ROOT/'attempt01/result.json';prior=json.loads(prior_path.read_text('utf8'));assert prior['status']=='PASS_STRICT_PRIVATE_MATERIAL_HEIGHT_SOBEL_SHADER_ABI'
        assert prior['literal_sha256']['normal']==hashes['normal']
        reused=[dict(row,reused_from_result=ref(prior_path))for row in prior['passes']if row['stem']=='normal'];assert len(reused)==2
    try:
        for stem,text in shader.items():
            if a.height_only and stem!='height':continue
            path=stage/(stem+'.hlsl');path.write_bytes(text.encode('ascii'));owned.append(path)
            for entry,profile in(('vertexMain','vs_5_0'),('pixelMain','ps_5_0')):
                key=stem+'_'+profile;cso=stage/(key+'.cso');asm=stage/(key+'.asm');owned.extend((cso,asm))
                command=[str(FXC),'/nologo','/Ges','/WX','/T',profile,'/E',entry,'/Fo',str(cso),'/Fc',str(asm),str(path)]
                done=subprocess.run(command,cwd=stage,capture_output=True,timeout=60,creationflags=subprocess.CREATE_NO_WINDOW)
                log=stage/(key+'_compiler.txt');log.write_text((done.stdout+done.stderr).decode('mbcs',errors='replace'),encoding='utf8')
                row=dict(stem=stem,entry=entry,profile=profile,command=command,exit_code=done.returncode,log=ref(log))
                if cso.exists():row['bytecode']=ref(cso)
                if asm.exists():row['listing']=ref(asm);row['reflection']=reflection(asm.read_text('utf8'),stem,profile)
                passes.append(row)
    finally:
        assert all(ref(row['path'])==row for row in inputs)and ref(FXC)==compiler
        files=[ref(path)for path in owned if path.exists()]
        for row in files:assert Path(row['path']).is_relative_to(stage)and row['links']==1 and not row['file_attributes']&0x401
        write_new(stage/'cleanup_plan.json',dict(files=files,protected=inputs))
        for row in files:assert ref(row['path'])==row;Path(row['path']).unlink()
        write_new(stage/'cleanup_result.json',dict(status='PASS_OWNED_FIELD_SHADER_INTERMEDIATES_REMOVED',files=files,deleted_files=len(files),released_unique_allocated_bytes=sum(r['allocated_bytes']for r in files)))
    fresh=len(passes);passes.extend(reused)
    passed=all(checks.values())and len(passes)==4 and all(row['exit_code']==0 and all(row.get('reflection',{}).get('checks',{}).values())for row in passes)
    result=dict(status='PASS_STRICT_PRIVATE_MATERIAL_HEIGHT_SOBEL_SHADER_ABI'if passed else'FAIL_FIELD_SHADER',inputs=inputs,compiler=compiler,literal_sha256=hashes,
        source_checks=checks,coordinate_proof=coords,passes=passes,fresh_passes=fresh,reused_passes=len(reused),cleanup=ref(stage/'cleanup_result.json'),
        candidates=['material-height cache producer wiring,mip0,bilinear wrap,68H66N resolution,half cache,16bitnormal/shadow encoding','unknown-support tap replacement'],
        original_operations=['diffuseAlpha^8*weights/heightweightedmean','Sobel eightcardinaltaps,normalize(-16*Sx,16*Sy,4),encode*.5+.5'],
        host_gamecore_clr_hwnd_gpu_audio_or_game_executed=False,actual_gpu_parity_verified=False)
    write_new(stage/'result.json',result);print(json.dumps(dict(status=result['status'],source_checks=len(checks),passes=[dict(stem=r['stem'],profile=r['profile'],exit_code=r['exit_code'],failed=[k for k,v in r.get('reflection',{}).get('checks',{}).items()if not v])for r in passes])))
    if not passed:raise SystemExit(1)

if __name__=='__main__':main()
