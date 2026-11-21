"""Strict C++14 CPU and FXC-only water blend/fog resource-contract checks."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[4]
STAGE=Path(__file__).absolute().parent
sys.path[:0]=[str(PROJECT/'tools'),str(PROJECT/'Tests'),str(STAGE)]
from menu_replay_restoration import build_cxx14
from original_screen_lighting import goldens
from menu_suite_storage import storage
from native_build import run
from water_pe_view import ref


def write_new(path,value):
    assert path.is_relative_to(STAGE) and not path.exists()
    with path.open('x',encoding='utf8') as f:json.dump(value,f,indent=2);f.write('\n')


def literal(path):
    found=re.findall(r'R"HLSL\((.*?)\)HLSL"',path.read_text('utf8'),re.S)
    assert len(found)==1,str(path)
    return found[0]


def imports(executable):
    raw=executable.read_bytes();import struct
    pe=struct.unpack_from('<I',raw,60)[0];assert raw[pe:pe+4]==b'PE\0\0' and struct.unpack_from('<H',raw,pe+4)[0]==0x8664
    opt=pe+24;assert struct.unpack_from('<H',raw,opt)[0]==0x20b
    rva,size=struct.unpack_from('<II',raw,opt+120)
    sections=[]
    for i in range(struct.unpack_from('<H',raw,pe+6)[0]):
        at=opt+struct.unpack_from('<H',raw,pe+20)[0]+i*40
        sections.append(struct.unpack_from('<IIII',raw,at+8))
    def offset(va):
        for virtual,r,n,rawat in sections:
            if r<=va<r+n:return rawat+va-r
        raise AssertionError(va)
    rows=[]
    while True:
        at=offset(rva);fields=struct.unpack_from('<IIIII',raw,at)
        if not any(fields):break
        stringat=offset(fields[3]);rows.append(raw[stringat:raw.index(0,stringat)].decode('ascii'));rva+=20
    assert {r.lower() for r in rows}=={'kernel32.dll'},rows
    return rows


def main():
    cli=argparse.ArgumentParser();cli.add_argument('--attempt',default='water_components01');args=cli.parse_args()
    assert re.fullmatch('water_components[0-9]{2}',args.attempt)
    stage=STAGE/args.attempt;work=stage/'work';assert not stage.exists()
    assert not any(os.environ.get(k) for k in ('CL','_CL_','LINK'))
    work.mkdir(parents=True)
    names=['OriginalWaterBlendModel.h','OriginalWaterBlendState.h','OriginalReflectionContract.h','OriginalWaterSurfaceShader.h',
           'OriginalFogShader.h','OriginalScreenLightingModel.h','OriginalScreenLightingShader.h','OriginalDynamicShadowShader.h',
           'OriginalWaterFogModel.h','OriginalWaterFogBinding.h','OriginalLightingModel.h','OriginalWaterOpticsModel.h']
    paths=[PROJECT/'Source/Presentation'/n for n in names]+[PROJECT/'Tests/original_water_blend.cpp',PROJECT/'Tests/original_screen_lighting.cpp',Path(__file__)]
    inputs=[ref(p) for p in paths];results=[];shader_results=[];error=None
    write_new(stage/'water_started.json',dict(scope='NoNative0',inputs=inputs))
    try:
        for name in ['original_water_blend','original_screen_lighting']:
            build=work/name;build.mkdir()
            if name=='original_screen_lighting':goldens(build/'screen_lighting_goldens.h')
            compiled=build_cxx14(name,build,stage,PROJECT/'Tests'/(name+'.cpp'),[PROJECT/'Source/Presentation',build])
            exe=Path(compiled['path']);dlls=imports(exe);before=ref(exe)
            done=run([str(exe)],cwd=build,timeout=45)
            stdout,stderr=done.stdout.decode('ascii'),done.stderr.decode('ascii')
            assert done.returncode==0 and not stderr,(stdout,stderr)
            match=re.fullmatch(r'PASS_ORIGINAL_WATER_BLEND checks=(\d+) plans=256 native_graphics_calls=0\s*' if name=='original_water_blend' else r'PASS_ORIGINAL_SCREEN_LIGHTING checks=(\d+)\s*',stdout)
            assert match,stdout
            results.append(dict(name=name,checks=int(match[1]),build=compiled,executed_console=before,imports=dlls,stdout=stdout.strip(),native_graphics_calls=0))
        compiler=json.loads((PROJECT/'evidence/world_terrain_original/terrain_shader_semantics.json').read_text('utf8'))['tool']
        assert ref(compiler['path'])['sha256']==compiler['sha256']
        surface=literal(PROJECT/'Source/Presentation/OriginalWaterSurfaceShader.h')
        fog=literal(PROJECT/'Source/Presentation/OriginalFogShader.h')
        shadow_source=(PROJECT/'Source/Presentation/OriginalDynamicShadowShader.h').read_text('utf8')
        shadow=re.search(r'SamplingSource\[\]=R"HLSL\((.*?)\)HLSL"',shadow_source,re.S)[1]
        assert not any(token in surface for token in ['SceneColour','SceneDepth','SceneId','Refraction(','Sky.Sample'])
        assert 'o.colour=FogBeforeBlend(float4(Encoded(lit),opacity),p)' in surface and 'o.waterFragment=motion.z>0.5?2u:0u' in surface
        assert 'if(fragment==2)output=SceneColour.Load' in fog
        screen=literal(PROJECT/'Source/Presentation/OriginalScreenLightingShader.h')
        assert 'screenReflectionFlags.w>' not in screen
        variants=[('water_surface','vertexMain','vs_5_0','#define DYNAMIC_SHADOW_SLOT t11\n'+shadow+surface),
                  ('water_surface','pixelMain','ps_5_0','#define DYNAMIC_SHADOW_SLOT t11\n'+shadow+surface),
                  ('water_fog','vertexMain','vs_5_0',fog),('water_fog','pixelMain','ps_5_0',fog),('water_fog','underlayMain','ps_5_0',fog),
                  ('water_screen','pixelMain','ps_5_0',screen+'\nfloat4 pixelMain(float4 p:SV_POSITION):SV_Target0{return float4(CombineOriginalScreenReflection(float3(.2,.4,.6),float3(.5,.25,.75),p.xy,true),1);}\n')]
        for label,entry,profile,source in variants:
            stem=label+'_'+entry+'_'+profile
            sourcepath=work/(stem+'.hlsl');bytecode=work/(stem+'.cso');listing=work/(stem+'.asm')
            sourcepath.write_text(source,encoding='ascii')
            command=[compiler['path'],'/nologo','/Ges','/WX','/O3','/T',profile,'/E',entry,'/Fo',str(bytecode),'/Fc',str(listing),str(sourcepath)]
            done=run(command,cwd=work,timeout=90)
            output=(done.stdout+done.stderr).decode('mbcs',errors='replace')
            (stage/(stem+'_compiler.txt')).write_text(output,encoding='utf8')
            assert done.returncode==0 and not re.search(r'\bwarning\b',output,re.I),(stem,output[:3000])
            asm=listing.read_text('utf-8-sig')
            checks=dict(compiled=True,no_uav='dcl_uav' not in asm)
            if label=='water_surface' and profile=='ps_5_0':
                checks['fog_bindings']=all(re.search(r'^//\s*'+name+r'\s+.*\b'+slot+r'\s+1\s*$',asm,re.M) for name,slot in [('FogMask','t12'),('FowColourKey','t13'),('FogRamp','t14'),('MaskSampler','s2')])
                checks['cb368']=all(re.search(r'\b'+name+r';\s*//\s*Offset:\s*'+str(offset)+r'\s+Size:\s*16',asm) for name,offset in [('fogDistance',320),('fogColour',336),('waterOverlay',352)])
                checks['old_fullframe_copies_unused']=not any(re.search(r'^//\s*'+name+r'\s+',asm,re.M) for name in ['SceneColour','SceneDepth','SceneId'])
            if entry=='underlayMain':
                checks['no_fragment_feedback']='WaterFragment' not in asm
                checks['integer_marker_output']=re.search(r'^// SV_Target\s+1\s+x\s+1\s+TARGET\s+uint\s+x\s*$',asm,re.M) is not None
            if label=='water_screen':checks['raw_sampler_no_consumer_decode']='screenReflectionFlags.w' not in source
            assert all(checks.values()),(stem,checks)
            shader_results.append(dict(name=stem,compiler=compiler,bytecode=ref(bytecode),listing=ref(listing),source_sha256=hashlib.sha256(source.encode()).hexdigest(),checks=checks,graphics_device_created=False))
        assert [ref(p) for p in paths]==inputs,'Owned source changed during verification'
    except BaseException as e:
        error=e
        write_new(stage/'water_failure.json',dict(scope='NoNative0',error_type=type(e).__name__,message=str(e)[:5000],inputs_unchanged=[ref(p) for p in paths]==inputs))
    finally:
        rows=[]
        for path in sorted(work.rglob('*')):
            if not path.is_file():continue
            assert path.resolve()==path and not path.lstat().st_file_attributes&0x401
            row=ref(path);assert path.stat().st_nlink==1
            row['allocated_bytes']=storage.allocated(path);rows.append(row)
        write_new(stage/'water_cleanup_plan.json',dict(root=str(work),files=rows,exact_owned_intermediates=True))
        for row in rows:
            path=Path(row['path']);assert path.is_relative_to(work) and ref(path)=={k:v for k,v in row.items() if k!='allocated_bytes'};path.unlink()
        for directory in sorted((p for p in work.rglob('*') if p.is_dir()),key=lambda p:len(p.parts),reverse=True):directory.rmdir()
        work.rmdir()
        write_new(stage/'water_cleanup_result.json',dict(status='PASS_EXACT_WATER_COMPONENT_INTERMEDIATES_REMOVED',files=len(rows),logical_bytes_removed=sum(r['bytes'] for r in rows),allocated_bytes_removed=sum(r['allocated_bytes'] for r in rows)))
    if error:raise error
    result=dict(schema='zerosis.phase10.water_blend_component_checks.v1',status='PASS_WATER_BLEND_FOG_ORDER_AND_RAW_REFLECTION_CXX14_FXC',scope='NoNative0',inputs=inputs,
                retail_evidence=ref(STAGE/'water_retail_state_contract.json'),cpu=results,shaders=shader_results,checks=sum(row['checks'] for row in results),
                shader_entries=len(shader_results),native_host_gamecore_clr_hwnd_gpu_audio_or_game_executed=False,
                limitations='CPU reference, PE import closure and shader compilation only; no native rendering, original camera/plane parity or full-scene acceptance.',
                cleanup=ref(stage/'water_cleanup_result.json'))
    write_new(stage/'water_result.json',result)
    print(json.dumps(dict(status=result['status'],checks=result['checks'],shader_entries=result['shader_entries'],output=ref(stage/'water_result.json'))))


if __name__=='__main__':main()
