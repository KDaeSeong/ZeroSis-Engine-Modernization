"""Six strict offline HLSL compilations with ABI and disclosure-boundary checks.

Only the pinned FXC compiler executes. Renderer edits outside its embedded
HLSL are allowed until --seal records the completed root integration.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys

sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[1]
sys.path.insert(0,str(PROJECT/'Tests'))
from original_water_shader import ref,write_new
from original_fog_shader import terrain_reflected_contract

ROOT=PROJECT/'evidence/world_terrain_original/phase4/shader'
PRESENTATION=PROJECT/'Source/Presentation'
RENDERER=PRESENTATION/'WorldTerrainRenderer.cpp'
FXC_SHA='ced7c1f95e4dffb614971826625e70da6d24aff1b4f2a3ae5952939c9547d7e6'
SURFACE=PRESENTATION/'OriginalWaterSurfaceShader.h'
TERRAIN=PRESENTATION/'OriginalTerrainShader.h'
TYPES=PRESENTATION/'OriginalWaterSurfaceGpuTypes.inc'
TERRAIN_TYPES=PRESENTATION/'OriginalTerrainGpuTypes.inc'

def literal(path):
    values=re.findall(r'R"HLSL\((.*?)\)HLSL"',Path(path).read_text('utf8'),re.S)
    assert len(values)==1,(str(path),len(values));return values[0]

def digest(text):return hashlib.sha256(text.encode('ascii')).hexdigest()
def clean(text):return re.sub(r'//[^\n]*','',text)

def source_contracts(shaders):
    s,t,l=(clean(shaders[name])for name in('surface','terrain','legacy'));pixel=s[s.index('O pixelMain('):]
    refract=s[s.index('float3 Refraction('):s.index('struct O{')]
    gate=pixel.index('if(state.y==0)discard;')
    return dict(
        surface_integer_target='uint pick:SV_Target1' in s,
        surface_integer_state='Texture2D<uint2> PlotState:register(t9);'in s,
        surface_integer_water_mask='Texture2D<uint> WaterMask:register(t10);'in s,
        surface_state_before_mask=pixel.index('PlotState.Load(')<gate<pixel.index('WaterMask.Load('),
        surface_water_kind_exact_mask='if(p.kind<0.5&&WaterMask.Load(int3(cell,0))==0)discard;'in pixel,
        surface_exact_pick_after_guards=pixel.index('o.pick=state.x;')>pixel.index('WaterMask.Load('),
        surface_no_material_sample_before_guards=not re.search(r'\.Sample(?:Level)?\(',pixel[:gate]),
        refraction_positive_id='if(pick==0)return fallback;'in refract,
        refraction_id_depth_world_colour_order=refract.index('SceneId.Load(')<refract.index('if(id!=pick)return fallback;')<
            refract.index('SceneDepth.Load(')<refract.index('source.y>=reflectionInfo.z')<refract.index('SceneColour.Load('),
        refraction_underwater_and_finite='!all(isfinite(source.xyz))||source.y>=reflectionInfo.z'in refract,
        refraction_depth_gate='depth>=1||depth<=p.p.z+0.0000001'in refract,
        signed_moments='mean=a.rg*2-1;second=float3(a.b,a.a,cross*2-1);'in s,
        mirror_only_mean_x_cross='if(mirrorX){mean.x=-mean.x;second.z=-second.z;}'in s,
        scale_once='float2 weights=float2(0.5,0.5)/opticsInfo.x;'in s and s.count('/opticsInfo.x')==1,
        independent_layer_second='s0*weights.x*weights.x+s1*weights.y*weights.y+'in s,
        covariance='covariance=second-float3(mean.x*mean.x,mean.y*mean.y,mean.x*mean.y);'in s,
        gaussian_regularisers='(wide?16.0:1.0)/k'in s,
        gaussian_det_guard='determinant=a*d-b*b;if(determinant<=0)return 0;'in s,
        gaussian_cutoff='if(!isfinite(q)||q>=16)return 0;'in s,
        gaussian_exp='exp2(-q*1.442695)/sqrt(determinant)*(wide?0.005:1.0)'in s,
        reflection_four_equal_taps=s.count('ReflectionCache.Sample(')==4 and s.count('*0.25')==4,
        reflection_source_offsets=all(v in s for v in('float2(2,2)','float2(2,-2)','float2(-2,6)','float2(-2,-2)','screen-1+6*covariance.xy')),
        exact_gamma_source='0.4545454680919647216796875'in s and struct.unpack('<I',struct.pack('<f',0.4545454680919647216796875))[0]==0x3ee8ba2f,
        retail_depth_lookup='DepthColour.SampleLevel(ClampSampler,float2(1-saturate(4*p.rawHeight),0),0)'in s,
        unbounded_raw_fresnel_before_composite='return base*fourth;'in s and 'saturate(RetailFresnel(mean,view))'in s,
        no_uav_or_depth_write=not re.search(r'SV_Depth|RWTexture|RWBuffer|Interlocked',s+t+l),
        terrain_clip_plane='if(clipInfo.y>0.5 && p.height<clipInfo.x)discard;'in t,
        terrain_unknown_reflection_discard='if(state.y==0){if(clipInfo.y>0.5)discard;return o;}'in t,
        terrain_unknown_before_material=t.index('if(state.y==0)')<t.index('Diffuse[i].Sample('),
        terrain_original_mrt='uint pick:SV_Target1;'in t and 'specularSquared:SV_Target2'in t and 'materialHeight:SV_Target3'in t,
        legacy_clip_unknown='if(clipInfo.y>0.5 && (p.height<clipInfo.x||p.fog<0))discard;'in l,
        legacy_unknown_main_unchanged='if(p.fog<0) {o.color=float4(0.002,0.003,0.004,1);return o;}'in l,
        cpu_surface_abi='sizeof(WaterSurfaceConstants)==272'in TYPES.read_text('utf8'),
        cpu_terrain_abi='sizeof(OriginalConstants)==192'in TERRAIN_TYPES.read_text('utf8'))

def offsets(listing,fields):
    result=[]
    for name,offset,size in fields:
        found=re.search(r'\b'+re.escape(name)+r'(?:\[\d+\])?;\s*//\s*Offset:\s*(\d+)\s+Size:\s*(\d+)',listing)
        result.append(dict(name=name,offset=offset,size=size,actual_offset=int(found[1])if found else None,actual_size=int(found[2])if found else None,
            matches=bool(found and int(found[1])==offset and int(found[2])==size)))
    return result

def bindings(listing,expected):
    return [dict(name=name,slot=slot,matches=sum(bool(re.match(r'//\s*'+re.escape(name)+r'\s+',line)and
        re.search(r'\b'+slot+r'\s+1\s*$',line))for line in listing.splitlines())==1)for name,slot in expected]

def gamma_count(data):
    assert data[:4]==b'DXBC'and len(data)==struct.unpack_from('<I',data,24)[0];count=struct.unpack_from('<I',data,28)[0]
    assert count<=64 and 32+4*count<=len(data);found=0
    for at in struct.unpack_from('<'+str(count)+'I',data,32):
        assert at+8<=len(data);size=struct.unpack_from('<I',data,at+4)[0];assert at+8+size<=len(data)
        if data[at:at+4]in(b'SHEX',b'SHDR'):
            assert size%4==0;found+=sum(word==0x3ee8ba2f for word, in struct.iter_unpack('<I',data[at+8:at+8+size]))
    return found

def reflection(listing,stem,profile,data):
    fields=[];resources=[]
    if profile=='vs_5_0':fields=[('viewProjection',0,64)];resources=[('Camera','cb0')]
    if stem=='surface':
        fields += [('inverseViewProjection',0,64)]+[(name,64+16*i,16)for i,name in enumerate(('placement','mapInfo','eye','viewport','reflectionInfo','opticsInfo','uvScales','motion','light0','light1','absorption','warp0','warp1'))]
        resources += [('Surface','cb1')]
        if profile=='ps_5_0':resources += [(n,'t'+str(i))for i,n in enumerate(('LeanMean','LeanCross','ReflectionCache','SceneColour','SceneDepth','SceneId','DepthColour','Sky','CoastWave','PlotState','WaterMask'))]+[('WrapSampler','s0'),('ClampSampler','s1')]
    elif stem=='terrain':
        fields += [('materials',0,128),('placement',128,16),('mapInfo',144,16),('textureOrigin',160,16),('fogInfo',176,16)]
        resources += [('Chunk','cb1')]
        if profile=='ps_5_0':fields += [('clipInfo',0,16)];resources += [('ReflectionClip','cb2')]
    elif profile=='ps_5_0':fields=[('clipInfo',0,16)];resources=[('ReflectionClip','cb2'),('Diffuse','t0'),('GroundSampler','s0')]
    constant_rows=offsets(listing,fields);resource_rows=bindings(listing,resources)
    lines=[line.strip()for line in listing.splitlines()if line.strip()and not line.startswith('//')]
    checks=dict(shader_model=profile in lines,constant_layout=all(r['matches']for r in constant_rows),
        resource_slots=all(r['matches']for r in resource_rows),no_uav_or_depth=not any('dcl_uav'in line or'oDepth'in line for line in lines))
    detail={}
    if profile=='ps_5_0':
        checks['target_zero_float']=bool(re.search(r'^// SV_Target\s+0\s+xyzw\s+0\s+TARGET\s+float\s+xyzw\s*$',listing,re.M))
        checks['target_one_uint']=bool(re.search(r'^// SV_Target\s+1\s+x\s+1\s+TARGET\s+uint\s+x\s*$',listing,re.M))
        checks['expected_output_count']=sum(line.startswith('dcl_output')for line in lines)==(4 if stem=='terrain'else 2)
        if stem=='terrain':
            detail['original_terrain_contract']=terrain_reflected_contract(listing);checks['original_terrain_contract']=all(detail['original_terrain_contract']['checks'].values())
        if stem=='surface':
            checks['typed_integer_inputs']=all(any(line.startswith('dcl_resource_texture2d (uint,uint,uint,uint) t'+str(slot))for line in lines)for slot in(5,9,10))
            checks['exact_gamma_bytecode']=gamma_count(data)>0;detail['exact_gamma_immediate_count']=gamma_count(data)
            loads={}
            for slot in(3,4,5,9,10):
                matches=[dict(instruction=i,text=line)for i,line in enumerate(lines)if line.startswith('ld_indexable(')and re.search(r'\bt'+str(slot)+r'(?:\.|\s|$)',line)]
                loads[str(slot)]=matches
            checks['compiled_refraction_load_order']=all(loads[str(slot)]for slot in(3,4,5))and loads['5'][0]['instruction']<loads['4'][0]['instruction']<loads['3'][0]['instruction']
            detail['compiled_restricted_loads']=loads
    return dict(checks=checks,constants=constant_rows,resources=resource_rows,detail=detail,instruction_count=len(lines))

def seal(stage,review_path):
    path=stage/'result.json';result=json.loads(path.read_text('utf8'));assert result['status']=='PASS_STRICT_WATER_SURFACE_TERRAIN_LEGACY_SHADER_ABI'
    assert all(ref(row['path'])==row for row in result['fixed_inputs'])
    assert digest(literal(RENDERER))==result['literal_sha256']['legacy'],'Embedded legacy HLSL changed;recompile before sealing'
    review_path=Path(review_path).absolute();review=json.loads(review_path.read_text('utf8'))
    assert review['status']=='PASS_FINAL_WATER_SURFACE_SHADER_INTEGRATION_SOURCE_REVIEW'
    required=('unorm_surface_target','clip_main_zero','clip_reflection_one','clip_slot2_binding','no_reflection_recursion')
    assert all(review['checks'].get(name)is True for name in required)
    assert all(ref(row['path'])==row for row in review['source_files'])
    assert any(row['path']==str(RENDERER)for row in review['source_files'])
    proof=dict(status='PASS_ROOT_SHADER_SOURCE_SEAL',compiled_result=ref(path),renderer=ref(RENDERER),integration_review=ref(review_path),checks=review['checks'],
        fixed_inputs=result['fixed_inputs'],literal_sha256=result['literal_sha256'],host_gamecore_clr_hwnd_gpu_audio_or_game_executed=False)
    write_new(stage/'source_seal.json',proof);print(json.dumps(dict(status=proof['status'],seal=ref(stage/'source_seal.json'))))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--attempt',default='attempt01');parser.add_argument('--seal',action='store_true')
    parser.add_argument('--integration-review',default=str(ROOT/'integration_review.json'));args=parser.parse_args()
    assert re.fullmatch(r'attempt\d{2}',args.attempt);stage=ROOT/args.attempt
    if args.seal:seal(stage,args.integration_review);return
    assert not stage.exists(),'Inspect previous owned attempt before restart'
    fixed=[ref(p)for p in(SURFACE,TYPES,TERRAIN,TERRAIN_TYPES,Path(__file__))]
    shaders=dict(surface=literal(SURFACE),terrain=literal(TERRAIN),legacy=literal(RENDERER));hashes={k:digest(v)for k,v in shaders.items()}
    checks=source_contracts(shaders);pin=PROJECT/'evidence/world_terrain_original/terrain_shader_semantics.json'
    compiler=ref(json.loads(pin.read_text('utf8'))['tool']['path']);assert compiler['sha256']==FXC_SHA
    stage.mkdir(parents=True);write_new(stage/'started.json',dict(fixed_inputs=fixed,legacy_embedding_initial=ref(RENDERER),literal_sha256=hashes,source_checks=checks,compiler=compiler))
    owned=[];passes=[]
    try:
        for stem,shader in shaders.items():
            source=stage/(stem+'.hlsl');source.write_bytes(shader.encode('ascii'));owned.append(source)
            for entry,profile in(('vertexMain','vs_5_0'),('pixelMain','ps_5_0')):
                key=stem+'_'+profile;bytecode=stage/(key+'.cso');listing=stage/(key+'.asm');owned.extend((bytecode,listing))
                command=[compiler['path'],'/nologo','/Ges','/WX','/T',profile,'/E',entry,'/Fo',str(bytecode),'/Fc',str(listing),str(source)]
                done=subprocess.run(command,cwd=stage,capture_output=True,timeout=90,creationflags=subprocess.CREATE_NO_WINDOW)
                log=(done.stdout+done.stderr).decode('mbcs',errors='replace');log_path=stage/(key+'_compiler.txt');log_path.write_text(log,encoding='utf8')
                row=dict(stem=stem,entry=entry,profile=profile,command=command,exit_code=done.returncode,log=ref(log_path))
                if bytecode.exists():row['bytecode']=ref(bytecode)
                if listing.exists():row['listing']=ref(listing);row['reflection']=reflection(listing.read_text('utf8'),stem,profile,bytecode.read_bytes())
                passes.append(row)
    finally:
        assert all(ref(row['path'])==row for row in fixed);assert ref(compiler['path'])==compiler
        assert digest(literal(RENDERER))==hashes['legacy'],'Root edited embedded HLSL during compilation'
        files=[ref(path)for path in owned if path.exists()]
        for row in files:assert Path(row['path']).is_relative_to(stage)and row['links']==1 and not row['file_attributes']&0x401 and ref(row['path'])==row
        write_new(stage/'cleanup_plan.json',dict(files=files,protected_inputs=fixed,embedded_literal_sha256=hashes['legacy']))
        for row in files:assert ref(row['path'])==row;Path(row['path']).unlink()
        write_new(stage/'cleanup_result.json',dict(status='PASS_EXACT_HLSL_CSO_ASM_INTERMEDIATES_REMOVED',files=files,deleted_files=len(files),
            released_unique_allocated_bytes=sum(row['allocated_bytes']for row in files),raw_original_asset_copies=0))
    passed=all(checks.values())and len(passes)==6 and all(row['exit_code']==0 and row.get('reflection')and all(row['reflection']['checks'].values())for row in passes)
    result=dict(schema='zerosis.water_phase4.strict_surface_terrain_legacy_shader.v1',status='PASS_STRICT_WATER_SURFACE_TERRAIN_LEGACY_SHADER_ABI'if passed else'FAIL_WATER_SURFACE_SHADER',
        fixed_inputs=fixed,legacy_embedding_final_seal='PENDING_ROOT_SOURCE_FREEZE',literal_sha256=hashes,compiler=compiler,passes=passes,source_checks=checks,
        original_operations=['PS2 signed moments,covariance/Gaussian,regularisers/cutoff,reflection offsets and exact gamma bits','u=1-saturate4h lookup'],
        candidates=['fixed plane/contour geometry and current mirror-camera reflection cache','same-positive-ID/depth/underwater scene refraction','equal layer weights,header scale binding,lighting and finite guards'],
        cleanup=ref(stage/'cleanup_result.json'),host_gamecore_clr_hwnd_gpu_audio_or_game_executed=False,actual_gpu_parity_verified=False)
    write_new(stage/'result.json',result);print(json.dumps(dict(status=result['status'],source_checks=len(checks),source_failed=[k for k,v in checks.items()if not v],
        passes=[dict(stem=r['stem'],profile=r['profile'],exit_code=r['exit_code'],failed=[k for k,v in r.get('reflection',{}).get('checks',{}).items()if not v])for r in passes])))
    if not passed:raise SystemExit(1)

if __name__=='__main__':main()
