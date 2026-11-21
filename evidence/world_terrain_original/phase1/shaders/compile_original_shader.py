"""Compile only the production HLSL raw literal with the pinned SDK FXC; no device is created."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode=True
STAGE=Path(__file__).absolute().parent
PROJECT=STAGE.parents[3]
SOURCE=PROJECT/'Source/Presentation/OriginalTerrainShader.h'
TEMP=STAGE/'tmp.hlsl'

def ref(path):
    raw=path.read_bytes();info=os.stat(path,follow_symlinks=False)
    return dict(path=str(path),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),
                file_identity=[info.st_dev,info.st_ino],mtime_ns=info.st_mtime_ns,
                file_attributes=info.st_file_attributes,links=info.st_nlink)

def write_new(path,value):
    with path.open('x',encoding='utf8') as stream:json.dump(value,stream,indent=2);stream.write('\n')

def main():
    assert not (STAGE/'result.json').exists() and not TEMP.exists(),'Inspect the existing owned shader attempt'
    source=ref(SOURCE);raw=SOURCE.read_text('utf8')
    literals=re.findall(r'R"HLSL\((.*?)\)HLSL"',raw,re.S);assert len(literals)==1
    shader=literals[0].encode('ascii')
    tool_json=PROJECT/'evidence/world_terrain_original/terrain_shader_semantics.json'
    pin=json.loads(tool_json.read_text('utf8'))['tool'];tool=ref(Path(pin['path']))
    assert tool['sha256']==pin['sha256']=='ced7c1f95e4dffb614971826625e70da6d24aff1b4f2a3ae5952939c9547d7e6'
    TEMP.write_bytes(shader);passes=[];owned=[TEMP]
    for entry,profile,stem in [('vertexMain','vs_5_0','vertex'),('pixelMain','ps_5_0','pixel')]:
        bytecode=STAGE/(stem+'.cso');assert not bytecode.exists();owned.append(bytecode)
        command=[tool['path'],'/nologo','/Ges','/WX','/T',profile,'/E',entry,'/Fo',str(bytecode),str(TEMP)]
        result=subprocess.run(command,cwd=STAGE,capture_output=True,timeout=90,creationflags=subprocess.CREATE_NO_WINDOW)
        log=(result.stdout+result.stderr).decode('mbcs',errors='replace')
        log_path=STAGE/(stem+'_compiler.txt');assert not log_path.exists();log_path.write_text(log,encoding='utf8')
        row=dict(entry=entry,profile=profile,command=command,exit_code=result.returncode,log=ref(log_path))
        if bytecode.exists():
            data=bytecode.read_bytes();assert data[:4]==b'DXBC';row['dxbc']=ref(bytecode)
        passes.append(row)
        if result.returncode:
            print(json.dumps(dict(status='FAIL_SHADER_COMPILE',source=source,entry=entry,profile=profile,compiler_output=log)))
            break
    assert ref(SOURCE)==source and ref(Path(pin['path']))==tool,'Production source or compiler changed during check'
    cleanup=[]
    for path in owned:
        if not path.exists():continue
        row=ref(path);assert row['links']==1 and not row['file_attributes']&0x401 and path.is_relative_to(STAGE)
        assert ref(path)==row;path.unlink();row['result']='DELETED_EXACT_OWNED_SHADER_INTERMEDIATE';cleanup.append(row)
    write_new(STAGE/'cleanup_result.json',dict(status='PASS_EXACT_SHADER_INTERMEDIATES_REMOVED',files=cleanup,deleted_files=len(cleanup),deleted_logical_bytes=sum(row['bytes'] for row in cleanup),existing_sources_or_evidence_changed=False))
    ok=len(passes)==2 and all(row['exit_code']==0 for row in passes)
    proof=dict(schema='zerosis.terrain.phase1.original_hlsl_compile.v1',status='PASS_STRICT_VS_PS_5_0_COMPILE_ONLY' if ok else 'FAIL_SHADER_COMPILE',
        source=source,literal_bytes=len(shader),literal_sha256=hashlib.sha256(shader).hexdigest(),
        compiler=tool,original_compiler_pin=ref(tool_json),passes=passes,
        cleanup=ref(STAGE/'cleanup_result.json'),shader_compiler_processes=len(passes),
        host_gamecore_clr_hwnd_gpu_audio_or_game_executed=False,graphics_device_created=False,
        runtime_gpu_shader_equivalence_verified=False)
    write_new(STAGE/'result.json',proof)
    print(json.dumps(dict(status=proof['status'],passes=len(passes),deleted_intermediates=len(cleanup),graphics_device_created=False)))
    if not ok:raise SystemExit(1)

if __name__=='__main__':main()
