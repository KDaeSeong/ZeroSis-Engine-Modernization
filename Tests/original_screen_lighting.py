"""Strict CPU/reference and actual integrated terrain-shader compilation only."""
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
ROOT=PROJECT/'evidence/world_terrain_original/phase8/screen_lighting'
sys.path[0:0]=[str(PROJECT/'tools'),str(PROJECT/'Tests')]
import build_exit_confirm_host as common
from menu_replay_restoration import build_cxx14
from menu_suite_storage import storage
from native_build import run


def write_new(path,value):
    with path.open('x',encoding='utf8',newline='\n') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=1);stream.write('\n')


def goldens(path):
    gamma=struct.unpack('<f',struct.pack('<I',0x400ccccd))[0]
    inverse=struct.unpack('<f',struct.pack('<I',0x3ee8ba2f))[0]
    rows=[]
    for i in range(64):
        diffuse=[((i*(j*2+1)+j)%9)/8 for j in range(3)]
        specular=[((i*(j*2+3)+2*j+1)%9)/8 for j in range(3)]
        reflection=[((i*(j*2+5)+3*j)%9)/8 for j in range(3)]
        expected=[(specular[j]**gamma*reflection[j]+diffuse[j]**gamma)**inverse for j in range(3)]
        rows.append([diffuse,specular,reflection,expected])
    def array(value):return '{'+','.join(format(x,'.17g') for x in value)+'}'
    source='struct ScreenGolden {double diffuse[3],specular[3],reflection[3],expected[3];};\n'
    source+='static const ScreenGolden ScreenGoldens[]={\n'+',\n'.join('{'+','.join(array(v) for v in row)+'}' for row in rows)+'};\n'
    source+='static const double ScreenHalfEncoded='+format(.5**inverse,'.17g')+';\n'
    source+='static const double ScreenHalfRoundtrip='+format((.5**gamma)**inverse,'.17g')+';\n'
    with path.open('x',encoding='ascii',newline='\n') as stream:stream.write(source)
    return dict(gamma_bits='0x400ccccd',inverse_gamma_bits='0x3ee8ba2f',cases=len(rows),generated=common.artifact(path))


def cleanup(stage,build):
    rows=[]
    for path in sorted(build.iterdir()):
        assert path.is_file() and path.suffix in {'.h','.exe','.obj','.map','.rsp','.cmd','.hlsl','.cso'}
        row=dict(common.artifact(path),allocated_bytes=storage.allocated(path))
        assert row['links']==1 and not row['file_attributes']&0x401;rows.append(row)
    write_new(stage/'screen_cleanup_plan.json',dict(directory=str(build),files=rows,exact_owned_leaves_only=True))
    for row in rows:
        path=Path(row['path']);assert path.is_relative_to(build) and common.artifact(path)=={k:v for k,v in row.items() if k!='allocated_bytes'}
        path.unlink()
    assert not any(build.iterdir());build.rmdir()
    write_new(stage/'screen_cleanup_result.json',dict(status='PASS_OWNED_SCREEN_LIGHTING_INTERMEDIATES_REMOVED',
        files=rows,deleted_files=len(rows),deleted_logical_bytes=sum(r['bytes'] for r in rows),
        released_unique_allocated_bytes=sum(r['allocated_bytes'] for r in rows)))


def cpu(stage):
    stage.mkdir();build=stage/'build';build.mkdir()
    names=['Source/Presentation/OriginalScreenLightingModel.h','Source/Presentation/OriginalLightingModel.h',
        'Source/Presentation/OriginalWaterOpticsModel.h','Tests/original_screen_lighting.cpp','Tests/original_screen_lighting.py']
    before=[common.artifact(PROJECT/n) for n in names];reference=goldens(build/'screen_lighting_goldens.h')
    compiled=executable=match=None;dlls=[];failure=None
    write_new(stage/'screen_started.json',dict(inputs=before,reference=reference,native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False))
    try:
        compiled=build_cxx14('original_screen_lighting',build,stage,PROJECT/names[3],[PROJECT/'Source/Presentation',build])
        imported=run([Path(compiled['compiler']).with_name('dumpbin.exe'),'/dependents',compiled['path']],cwd=build,timeout=30)
        dlls=sorted(set(re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$',imported.stdout.decode('mbcs',errors='replace'),re.M)))
        assert imported.returncode==0 and {n.lower() for n in dlls}=={'kernel32.dll'},dlls
        (stage/'screen_imports.txt').write_bytes(imported.stdout)
        executable=common.artifact(compiled['path']);done=run([compiled['path']],cwd=build,timeout=30)
        stdout=done.stdout.decode('ascii');stderr=done.stderr.decode('ascii')
        (stage/'screen_console.txt').write_text(stdout+stderr,encoding='ascii')
        match=re.fullmatch(r'PASS_ORIGINAL_SCREEN_LIGHTING checks=(\d+)\s*',stdout)
        assert done.returncode==0 and not stderr and match,(done.returncode,stdout,stderr)
    except BaseException as error:
        failure=error
        for name in [names[0],names[3]]:
            path=PROJECT/name
            with (stage/('screen_failed_'+path.name+'.gz')).open('xb') as stream:stream.write(gzip.compress(path.read_bytes(),mtime=0))
        write_new(stage/'screen_failure.json',dict(error_type=type(error).__name__,message=str(error)[:4000],build=compiled))
    finally:
        after=[common.artifact(PROJECT/n) for n in names];assert before==after
        cleanup(stage,build)
    if failure:raise failure
    result=dict(status='PASS_ORIGINAL_REFLECTION_CONSUMER_POLICY_CXX14',checks=int(match[1]),inputs_before=before,inputs_after=after,
        build=compiled,console_executable=executable,imported_dlls=dlls,reference=reference,
        cleanup=common.artifact(stage/'screen_cleanup_result.json'),retained_executable=False,
        known_only='Hidden poison inputs and malformed policy cannot call the fetch callback; disabled specular/reflection never fetch.',
        candidates='Explicit encoded-UNORM producer decode; current producer scene/camera and sampler are not original pixel equivalence.',
        native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False)
    write_new(stage/'screen_result.json',result);return common.artifact(stage/'screen_result.json')


def hlsl(name):
    text=(PROJECT/name).read_text('ascii')
    match=re.search(r'R"HLSL\((.*?)\)HLSL"',text,re.S);assert match,name
    return match[1]


def shaders(stage):
    stage.mkdir();build=stage/'build';build.mkdir()
    names=['Source/Presentation/OriginalScreenLightingShader.h','Source/Presentation/OriginalTerrainShader.h',
        'Source/Presentation/OriginalTerrainGpu.inc','Tests/original_screen_lighting.py']
    before=[common.artifact(PROJECT/n) for n in names]
    tool=json.loads((PROJECT/'evidence/world_terrain_original/terrain_shader_semantics.json').read_text('utf8'))['tool']
    compiler=common.artifact(tool['path']);assert compiler['sha256']==tool['sha256']
    source=hlsl(names[0])+hlsl(names[1])
    assert 'CombineOriginalScreenReflection' in hlsl(names[1]),'Actual terrain consumer must use the new producer'
    assert 'std::string(OSL::ShaderSource)+OT::ShaderSource' in (PROJECT/names[2]).read_text('ascii')
    shader=build/'screen_integrated_terrain.hlsl'
    with shader.open('x',encoding='ascii',newline='\n') as stream:stream.write(source)
    rows=[];failure=None
    try:
        for profile,entry in [('vs_5_0','vertexMain'),('ps_5_0','pixelMain')]:
            output=build/(profile+'.cso');listing=stage/('screen_'+profile+'.asm')
            command=[compiler['path'],'/nologo','/Ges','/WX','/O3','/Zpr','/T',profile,'/E',entry,
                '/Fo',str(output),'/Fc',str(listing),str(shader)]
            done=run(command,cwd=build,timeout=45)
            log=done.stdout.decode('mbcs',errors='replace')+done.stderr.decode('mbcs',errors='replace')
            (stage/('screen_'+profile+'_compile.txt')).write_text(log,encoding='utf8')
            assert done.returncode==0 and output.is_file() and listing.is_file(),log
            assert not re.search(r'\bwarning\b',log,re.I),log
            if profile=='ps_5_0':
                asm=listing.read_text('utf-8-sig');assert 't44' in asm and 'cb6' in asm and 's5' in asm
            rows.append(dict(profile=profile,entry=entry,command=command,compiled=common.artifact(output),listing=common.artifact(listing),warnings=0))
    except BaseException as error:
        failure=error
        with (stage/'screen_failed_source.hlsl.gz').open('xb') as stream:stream.write(gzip.compress(source.encode('ascii'),mtime=0))
        write_new(stage/'screen_failure.json',dict(error_type=type(error).__name__,message=str(error)[:4000]))
    finally:
        after=[common.artifact(PROJECT/n) for n in names];assert before==after
        cleanup(stage,build)
    if failure:raise failure
    result=dict(status='PASS_ACTUAL_INTEGRATED_TERRAIN_TWO_STRICT_SHADER_STAGES',inputs_before=before,inputs_after=after,
        compiler=compiler,stages=rows,cleanup=common.artifact(stage/'screen_cleanup_result.json'),
        hlsl_order=['OriginalScreenLighting','OriginalTerrain'],
        no_id_or_depth_target_added_by_screen_helpers=True,gpu_or_game_executed=False)
    write_new(stage/'screen_result.json',result);return common.artifact(stage/'screen_result.json')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--part',choices=['cpu','shaders','all'],default='all')
    parser.add_argument('--attempt',type=int,default=0);args=parser.parse_args()
    assert 0<=args.attempt<=9 and not any(os.environ.get(n) for n in ['CL','_CL_','LINK'])
    results={}
    for part,action in [('cpu',cpu),('shaders',shaders)]:
        if args.part not in [part,'all']:continue
        stage=ROOT/(f'screen_{part}'+(f'_retry{args.attempt:02d}' if args.attempt else ''))
        assert not stage.exists(),'Inspect retained attempt before running a fresh named retry'
        results[part]=action(stage)
    print(json.dumps(results))


if __name__=='__main__':
    main()
