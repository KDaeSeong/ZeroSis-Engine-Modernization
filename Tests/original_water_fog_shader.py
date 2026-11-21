"""Six strict, file-only shader compilations for water FOW and marker routing."""
from __future__ import annotations
import argparse,hashlib,json,re,subprocess,sys
from pathlib import Path
sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[1]
sys.path.insert(0,str(PROJECT/'Tests'))
from original_water_shader import ref,write_new
from original_water_surface_shader import offsets,bindings

ROOT=PROJECT/'evidence/world_terrain_original/phase8/water_fog'
SOURCE=PROJECT/'Source/Presentation'
FXC=Path(r'C:/Program Files (x86)/Windows Kits/10/bin/10.0.26100.0/x64/fxc.exe')
FXC_SHA='ced7c1f95e4dffb614971826625e70da6d24aff1b4f2a3ae5952939c9547d7e6'

def literal(path,name='ShaderSource'):
    text=Path(path).read_text('utf8')
    if Path(path).suffix=='.cpp':values=re.findall(r'R"HLSL\((.*?)\)HLSL"',text,re.S);assert len(values)==1;return values[0]
    found=re.search(re.escape(name)+r'\[\]=R"HLSL\((.*?)\)HLSL"',text,re.S);assert found;return found[1]

def source_checks(shaders):
    f,s,l=shaders['fog'],shaders['surface'],shaders['legacy'];fg=f[f.index('float4 pixelMain('):];water=fg[fg.index('[branch]if(WaterFragment.Load'):fg.index('float3 terrain=')]
    surface=s[s.index('O pixelMain('):]
    return dict(fog_only_target0='SV_Target1'not in f and'SV_Target4'not in f,
        pixel_class_not_water_plot='Texture2D<uint> WaterFragment : register(t11)'in f and'plot.water'not in re.sub(r'//[^\n]*','',f),
        unknown_before_scene_marker_lut=fg.index('if(state.y==0)')<fg.index('WaterFragment.Load')<fg.index('WaterFogBase(SceneColour.Load'),
        water_once_return='return WaterFogFinish(water,transformedWater,mask,DistanceFactor(local,ndc.y));'in water,
        overlay_before_gray=f.index('waterOverlay.rgb+(1-waterOverlay.a)*colour.rgb')<f.index('lerp(float3(0.4,0.4,0.4),over,mask.r)'),
        lut_after_gray='WaterFogBase(SceneColour.Load'in water and water.index('WaterFogBase(')<water.index('FowColourKey.Sample'),
        water_lut_weight='mask.r*(1-mask.b)'in f and'colour.a'in f[f.index('float4 WaterFogFinish'):f.index('float4 pixelMain')],
        surface_trueid_and_unknown=surface.index('if(state.y==0)discard;')<surface.index('o.pick=state.x;')<surface.index('o.waterFragment=1;'),
        surface_no_watermark_for_coast=surface.index('if(p.kind>0.5)')<surface.index('o.waterFragment=1;'),
        surface_integer_target4='uint waterFragment:SV_Target4'in s,
        dynamic_shadow_only_known_surface=surface.index('if(state.y==0)discard;')<surface.index('SampleDynamicShadow(p.local)'),
        dynamic_shadow_original_coefficient='float3 shadowed=shadowAmount*lit;lit=shadowed*(-0.67)+lit;'in s,
        no_internal_fog_when_post_enabled='float fog=motion.z>0.5||state.y==2?1.0:0.30;'in s,
        unit_fragment_zero='uint waterFragment:SV_Target4'in l and'o.waterFragment=0;'in l,
        unit_exact_pick_unchanged='o.pick=p.pick;'in l,
        fog_cb224='sizeof(FogConstants)==224'in(SOURCE/'OriginalFogGpuTypes.inc').read_text('utf8'),
        water_cb320='sizeof(WaterSurfaceConstants)==320'in(SOURCE/'OriginalWaterSurfaceGpuTypes.inc').read_text('utf8'),
        fog12_srv_cleanup='PSSetShaderResources(0,12,empty)'in(SOURCE/'OriginalFogGpu.inc').read_text('utf8'),
        water12_srv_cleanup='PSSetShaderResources(0,12,empty)'in(SOURCE/'OriginalWaterSurfaceGpu.inc').read_text('utf8'))

def reflect(listing,stem,profile):
    lines=[v.strip()for v in listing.splitlines()if v.strip()and not v.startswith('//')];fields=[];resources=[]
    if stem=='fog'and profile=='ps_5_0':
        fields=[('inverseViewProjection',0,64),('viewport',64,16),('mapInfo',80,16),('camera',96,16),('distanceParameters',112,16),('fogColour',128,16),('flow',144,48),('phase',192,16),('waterOverlay',208,16)]
        resources=[('Fog','cb0')]+[(n,'t'+str(i))for i,n in enumerate(('SceneColour','SceneDepth','MaskTexture','PlotState','Cloud1','Cloud2','Cloud3','FlowField','FogDiffuse','FowColourKey','FogRamp','WaterFragment'))]+[(n,'s'+str(i))for i,n in enumerate(('ClampSampler','WrapSampler','MaskSampler'))]
    if stem=='surface':
        fields=[('inverseViewProjection',0,64)]+[(n,64+16*i,16)for i,n in enumerate(('placement','mapInfo','eye','viewport','reflectionInfo','opticsInfo','uvScales','motion','light0','light1','absorption','warp0','warp1','lightColour0','lightColour1','shadowInfo'))]
        resources=[('Surface','cb1')]
        if profile=='vs_5_0':fields+=[('viewProjection',0,64)];resources+=[('Camera','cb0')]
        else:
            fields+=[('shadowViewProjection',0,64),('shadowPlacement',64,16),('shadowMapInfo',80,16),('dynamicShadowInfo',96,16)]
            resources += [('DynamicShadow','cb5')]+[(n,'t'+str(i))for i,n in enumerate(('LeanMean','LeanCross','ReflectionCache','SceneColour','SceneDepth','SceneId','DepthColour','Sky','CoastWave','PlotState','WaterMask','DynamicShadowDepth'))]+[('WrapSampler','s0'),('ClampSampler','s1')]
    if stem=='legacy':
        if profile=='vs_5_0':fields=[('viewProjection',0,64)];resources=[('Camera','cb0')]
        else:fields=[('clipInfo',0,16)];resources=[('ReflectionClip','cb2'),('Diffuse','t0'),('GroundSampler','s0')]
    c=offsets(listing,fields);r=bindings(listing,resources);checks=dict(shader_model=profile in lines,constant_offsets=all(x['matches']for x in c),resource_bindings=all(x['matches']for x in r),no_uav_depth=not any('dcl_uav'in v or'oDepth'in v for v in lines))
    loads={}
    if profile=='ps_5_0':
        checks['target0_colour']=bool(re.search(r'^// SV_Target\s+0\s+xyzw\s+0\s+TARGET\s+float',listing,re.M))
        count=1 if stem=='fog'else 3;checks['target_count']=sum(v.startswith('dcl_output')for v in lines)==count
        if stem!='fog':
            checks['exact_uint_id_target1']=bool(re.search(r'^// SV_Target\s+1\s+x\s+1\s+TARGET\s+uint',listing,re.M))
            checks['uint_fragment_target4']=bool(re.search(r'^// SV_Target\s+4\s+x\s+4\s+TARGET\s+uint',listing,re.M))
        else:
            checks['typed_uint_marker']=any(v.startswith('dcl_resource_texture2d (uint,uint,uint,uint) t11')for v in lines)
            checks['exact_gray_literal']=any('0.400000' in v or'4.000000e-01'in v for v in lines)
            for slot in(0,3,11):loads[str(slot)]=[dict(instruction=i,text=v)for i,v in enumerate(lines)if v.startswith('ld_indexable(')and re.search(r'\bt'+str(slot)+r'(?:\.|\s|$)',v)]
            checks['plotstate_before_marker']=bool(loads['3']and loads['11']and loads['3'][0]['instruction']<loads['11'][0]['instruction'])
        if stem=='legacy':checks['zero_marker_output']=any(re.search(r'^mov o4\.x, l\(0\)',v)for v in lines)
    return dict(checks=checks,constants=c,resources=r,compiled_loads=loads,load_order_is_not_full_cfg_proof=True)

def main():
    cli=argparse.ArgumentParser();cli.add_argument('--attempt',default='water_shader01');args=cli.parse_args();assert re.fullmatch(r'water_shader\d{2}',args.attempt)
    stage=ROOT/args.attempt;assert not stage.exists();stage.mkdir(parents=True)
    fixed=[SOURCE/n for n in('OriginalFogShader.h','OriginalFogGpuTypes.inc','OriginalFogGpu.inc','OriginalWaterSurfaceShader.h','OriginalWaterSurfaceGpuTypes.inc','OriginalWaterSurfaceGpu.inc','OriginalDynamicShadowShader.h','OriginalWaterFogBinding.h')]+[Path(__file__)]
    inputs=[ref(p)for p in fixed];renderer=SOURCE/'WorldTerrainRenderer.cpp';renderer_start=ref(renderer)
    prefix='#define DYNAMIC_SHADOW_SLOT t11\n'+literal(SOURCE/'OriginalDynamicShadowShader.h','SamplingSource')
    shaders=dict(fog=literal(SOURCE/'OriginalFogShader.h'),surface=prefix+literal(SOURCE/'OriginalWaterSurfaceShader.h'),legacy=literal(renderer));hashes={k:hashlib.sha256(v.encode('ascii')).hexdigest()for k,v in shaders.items()}
    checks=source_checks(shaders);compiler=ref(FXC);assert compiler['sha256']==FXC_SHA;write_new(stage/'water_started.json',dict(inputs=inputs,legacy_embedding_initial=renderer_start,compiled_literal_sha256=hashes,source_checks=checks,compiler=compiler))
    owned=[];passes=[]
    try:
        for stem,shader in shaders.items():
            hlsl=stage/('water_'+stem+'.hlsl');hlsl.write_bytes(shader.encode('ascii'));owned.append(hlsl)
            for entry,profile in(('vertexMain','vs_5_0'),('pixelMain','ps_5_0')):
                key='water_'+stem+'_'+profile;cso=stage/(key+'.cso');asm=stage/(key+'.asm');owned.extend((cso,asm))
                command=[str(FXC),'/nologo','/Ges','/WX','/T',profile,'/E',entry,'/Fo',str(cso),'/Fc',str(asm),str(hlsl)]
                done=subprocess.run(command,cwd=stage,capture_output=True,timeout=60,creationflags=subprocess.CREATE_NO_WINDOW)
                log=stage/(key+'_compiler.txt');log.write_text((done.stdout+done.stderr).decode('mbcs',errors='replace'),encoding='utf8')
                row=dict(stem=stem,profile=profile,entry=entry,command=command,exit_code=done.returncode,log=ref(log))
                if cso.exists():row['bytecode']=ref(cso)
                if asm.exists():row['listing']=ref(asm);row['reflection']=reflect(asm.read_text('utf8'),stem,profile)
                passes.append(row)
    finally:
        assert all(ref(x['path'])==x for x in inputs);assert hashlib.sha256(literal(renderer).encode('ascii')).hexdigest()==hashes['legacy'];files=[ref(p)for p in owned if p.exists()]
        for row in files:assert Path(row['path']).is_relative_to(stage)and row['links']==1 and not row['file_attributes']&0x401
        write_new(stage/'water_cleanup_plan.json',dict(files=files,protected=inputs))
        for row in files:assert ref(row['path'])==row;Path(row['path']).unlink()
        write_new(stage/'water_cleanup_result.json',dict(status='PASS_OWNED_WATER_FOG_SHADER_INTERMEDIATES_REMOVED',files=files,deleted_files=len(files),released_unique_allocated_bytes=sum(r['allocated_bytes']for r in files)))
    passed=all(checks.values())and len(passes)==6 and all(p['exit_code']==0 and all(p.get('reflection',{}).get('checks',{}).values())for p in passes)
    result=dict(status='PASS_STRICT_WATER_FOG_SURFACE_DYNAMIC_AND_UNIT_FRAGMENT_SHADER_ABI'if passed else'FAIL_WATER_FOG_SHADER',inputs=inputs,legacy_embedding_final_seal='PENDING_ROOT_SOURCE_FREEZE',compiled_literal_sha256=hashes,
        compiler=compiler,source_checks=checks,passes=passes,cleanup=ref(stage/'water_cleanup_result.json'),retail_hardware_blend_verified=False,
        candidates=['marker-routing final opaque scene including coast overlay','neutral premultiplied overlay/current LUT sampler/shared fog calibration','root private dynamic shadow map/camera/PCF and sourceStrength1'],
        native_host_gamecore_clr_hwnd_gpu_audio_or_game_executed=False,actual_gpu_parity_verified=False)
    write_new(stage/'water_result.json',result);print(json.dumps(dict(status=result['status'],source_failed=[k for k,v in checks.items()if not v],passes=[dict(stem=p['stem'],profile=p['profile'],exit_code=p['exit_code'],failed=[k for k,v in p.get('reflection',{}).get('checks',{}).items()if not v])for p in passes])))
    if not passed:raise SystemExit(1)

if __name__=='__main__':main()
