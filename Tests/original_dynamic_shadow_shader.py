"""Strict compile-only validation of private shadow producers and sampling ABI."""
from pathlib import Path
import argparse, hashlib, json, re, subprocess, sys
sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[1]
sys.path.insert(0,str(PROJECT/'Tests'))
from original_water_shader import ref,write_new
FXC=Path(r'C:/Program Files (x86)/Windows Kits/10/bin/10.0.26100.0/x64/fxc.exe')
FXC_SHA='ced7c1f95e4dffb614971826625e70da6d24aff1b4f2a3ae5952939c9547d7e6'
SOURCE=PROJECT/'Source/Presentation/OriginalDynamicShadowShader.h'

def main():
    cli=argparse.ArgumentParser();cli.add_argument('--attempt',default='shader01');a=cli.parse_args()
    assert re.fullmatch(r'shader\d{2}',a.attempt)
    stage=PROJECT/'evidence/world_terrain_original/phase8/dynamic_shadow'/a.attempt
    assert not stage.exists();stage.mkdir(parents=True)
    inputs=[ref(SOURCE),ref(SOURCE.with_name('OriginalDynamicShadowGpuTypes.inc')),ref(SOURCE.with_name('OriginalDynamicShadowGpu.inc')),ref(Path(__file__))]
    compiler=ref(FXC);assert compiler['sha256']==FXC_SHA
    text=SOURCE.read_text('utf8');literals={key:re.search(key+r'Source\[\]=R"HLSL\((.*?)\)HLSL"',text,re.S)[1]for key in('Producer','Sampling')}
    receiver='#define DYNAMIC_SHADOW_SLOT t11\n'+literals['Sampling']+'\nfloat4 receiver(float3 p:TEXCOORD0):SV_Target0{return SampleDynamicShadow(p).xxxx;}'
    passes=[('ground','groundVertex','vs_5_0',literals['Producer']),('unit','unitVertex','vs_5_0',literals['Producer']),
        ('ground','groundPixel','ps_5_0',literals['Producer']),('receiver','receiver','ps_5_0',receiver)]
    rows=[];owned=[]
    write_new(stage/'started.json',dict(inputs=inputs,compiler=compiler,literal_sha256={k:hashlib.sha256(v.encode('ascii')).hexdigest()for k,v in literals.items()}))
    try:
        for name,entry,profile,source in passes:
            stem=name+'_'+profile;hlsl=stage/(stem+'.hlsl');hlsl.write_text(source,encoding='ascii');cso=stage/(stem+'.cso');asm=stage/(stem+'.asm');owned.extend((hlsl,cso,asm))
            command=[str(FXC),'/nologo','/Ges','/WX','/T',profile,'/E',entry,'/Fo',str(cso),'/Fc',str(asm),str(hlsl)]
            done=subprocess.run(command,cwd=stage,capture_output=True,timeout=60,creationflags=subprocess.CREATE_NO_WINDOW)
            log=stage/(stem+'_compiler.txt');log.write_text((done.stdout+done.stderr).decode('mbcs',errors='replace'),encoding='utf8')
            row=dict(stem=stem,entry=entry,exit_code=done.returncode,log=ref(log));checks={}
            if asm.exists():
                listing=asm.read_text('utf8');row['listing']=ref(asm)
                checks['b5']=bool(re.search(r'^// DynamicShadow\s+cbuffer.*cb5\s+1',listing,re.M))
                checks['constant_112']=bool(re.search(r'^//\s*float4 dynamicShadowInfo;.*Offset:\s*96 Size:\s*16',listing,re.M))if name=='receiver'else True
                checks['no_integer_id_target']=not re.search(r'^// SV_Target\s+[14]\s',listing,re.M)
                if entry=='groundPixel':checks['exact_known_guard_and_no_colour_output']='t0' in listing and not re.search(r'^// SV_Target',listing,re.M)and 'discard'in listing
                if name=='receiver':checks['projected_depth_t11']='t11' in listing and 'ld_indexable(texture2d)'in listing and 'if_'in listing
                row['checks']=checks
            if cso.exists():row['bytecode']=ref(cso)
            rows.append(row)
    finally:
        assert all(ref(r['path'])==r for r in inputs)and ref(FXC)==compiler
        leaves=[ref(p)for p in owned if p.exists()]
        for row in leaves:assert Path(row['path']).is_relative_to(stage)and row['links']==1 and not row['file_attributes']&0x401
        write_new(stage/'cleanup_plan.json',dict(files=leaves,exact_owned_leaves_only=True))
        for row in leaves:assert ref(row['path'])==row;Path(row['path']).unlink()
        write_new(stage/'cleanup_result.json',dict(status='PASS',files=leaves,released_unique_allocated_bytes=sum(row['allocated_bytes']for row in leaves)))
    passed=len(rows)==4 and all(row['exit_code']==0 and row.get('checks')and all(row['checks'].values())for row in rows)
    result=dict(status='PASS_STRICT_DYNAMIC_SHADOW_SHADERS'if passed else'FAIL',passes=rows,inputs=inputs,compiler=compiler,
        native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False,actual_gpu_acceptance=False,cleanup=ref(stage/'cleanup_result.json'))
    write_new(stage/'result.json',result)
    print(json.dumps(dict(status=result['status'],passes=[dict(stem=r['stem'],exit_code=r['exit_code'],checks=r.get('checks'))for r in rows])))
    if not passed:raise SystemExit(1)

if __name__=='__main__':main()
