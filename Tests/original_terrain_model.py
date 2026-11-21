"""C++14 production CPU terrain model checks; no Host, SDK, CLR, window or GPU execution."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import sys

sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[1]
ROOT=PROJECT/'evidence/world_terrain_original/phase1/model'
sys.path.insert(0,str(PROJECT/'tools'));sys.path.insert(0,str(PROJECT/'Tests'))
import build_exit_confirm_host as common
from menu_replay_restoration import build_cxx14
from native_build import run
from menu_suite_storage import storage

def write_new(path,value):
    with path.open('x',encoding='utf8') as stream:json.dump(value,stream,indent=2);stream.write('\n')

def reference_shuffle(count):
    state=12345;values=list(range(count));calls=0
    def rand():
        nonlocal state,calls
        state=(state*214013+2531011)&0xffffffff;calls+=1
        return (state>>16)&32767
    for current in range(1,count):
        bound=current+1;mask=32767;value=rand()&mask
        while bound>mask and mask!=0xffffffff:
            mask=((mask<<15)|32767)&0xffffffff
            value=((value<<15)|(rand()&32767))&0xffffffff
        selected=value%bound;values[current],values[selected]=values[selected],values[current]
    digest=14695981039346656037
    for value in values:
        for octet in struct.pack('<I',value):digest=((digest^octet)*1099511628211)&0xffffffffffffffff
    return digest,calls,state

def make_golden(path):
    counts=(1,4,64,33000)
    values={count:reference_shuffle(count) for count in counts}
    state=1;value=0
    for _ in range(3):
        state=(state*214013+2531011)&0xffffffff
        value=((value<<15)|((state>>16)&32767))&0xffffffff
    taps=(0.125,0.6360560059547424,1.0,0.6360560059547424,0.125)
    center=1/sum(taps)**2
    histogram=[0]*12
    for y in range(-2,66):
        for x in range(-2,66):histogram[((y%64)+(x%64)//8)%12]+=1
    slots=sorted(range(12),key=lambda index:(-histogram[index],index))[:8]
    text='#pragma once\n#include <cstdint>\n'
    text+='\n'.join(f'constexpr std::uint64_t GoldenHash{count}={values[count][0]}ull;' for count in counts)+'\n'
    text+=f'constexpr std::uint32_t GoldenFullRandom={value}u;\n'
    text+=f'constexpr float GoldenKernelCenter={center:.12f}f;\n'
    text+='constexpr unsigned GoldenChunkSlots[]={'+','.join(str(item) for item in slots)+'};\n'
    path.write_text(text,encoding='ascii')
    return dict(shuffles={str(k):dict(fnv64=f'{v[0]:016x}',calls=v[1],state=v[2]) for k,v in values.items()},
        full_range=value,kernel_center=center,chunk_histogram=histogram,chunk_top8=slots,
        method='Independent Python transliteration of bounded x86 shuffle instructions and scalar mathematical kernel/chunk references.')

def main():
    cli=argparse.ArgumentParser();cli.add_argument('--attempt',type=int,default=0);args=cli.parse_args()
    assert 0<=args.attempt<=9
    stage=ROOT/('cpu' if args.attempt==0 else f'cpu_retry{args.attempt:02d}')
    build=stage/'build';assert not stage.exists(),'Inspect the existing owned CPU attempt before retrying it'
    assert not any(os.environ.get(name) for name in ('CL','_CL_','LINK'))
    stage.mkdir(parents=True);build.mkdir()
    inventory=json.loads((PROJECT/'evidence/world_terrain_original/asset_inventory.json').read_text('utf8'))
    library=Path(inventory['game_root'])/'Resource/Common/TerrainPiecesLibrary.fxsb'
    inputs=[PROJECT/name for name in ('Source/Presentation/OriginalTerrainModel.h','Tests/original_terrain_model.cpp','Tests/original_terrain_model.py')]+[library]
    before=[common.artifact(path) for path in inputs]
    assert before[-1]['sha256']=='86faac1e80634b0031a9df98889682fbc17ddc72341fc68fbf5b33e7ce4c1c7a'
    golden=make_golden(build/'original_terrain_golden.h')
    write_new(stage/'started.json',dict(inputs=before,golden=golden,host_sdk_clr_hwnd_gpu_audio_or_game_execution=False))
    compiled=build_cxx14('original_terrain_model',build,stage,PROJECT/'Tests/original_terrain_model.cpp',
        [PROJECT/'Source/Presentation',build])
    imported=run([Path(compiled['compiler']).with_name('dumpbin.exe'),'/dependents',compiled['path']],cwd=build,timeout=30)
    names=sorted(set(re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$',imported.stdout.decode('mbcs',errors='replace'),re.M)))
    assert imported.returncode==0 and {name.lower() for name in names}=={'kernel32.dll'},names
    executable=common.artifact(compiled['path'])
    result=run([compiled['path'],library],cwd=build,timeout=180)
    stdout=result.stdout.decode('ascii');stderr=result.stderr.decode('ascii')
    match=re.fullmatch(r'PASS_ORIGINAL_TERRAIN_MODEL checks=(\d+)\s*',stdout)
    (stage/'console.txt').write_text(stdout+stderr,encoding='ascii')
    assert result.returncode==0 and not stderr and match,(result.returncode,stdout,stderr)
    after=[common.artifact(path) for path in inputs];assert before==after
    rows=[]
    for path in sorted(build.iterdir()):
        assert path.is_file() and path.suffix in ('.exe','.obj','.map','.rsp','.cmd','.h')
        row=common.artifact(path);row['allocated_bytes']=storage.allocated(path)
        assert row['links']==1 and not row['file_attributes']&0x401
        rows.append(row)
    write_new(stage/'cleanup_plan.json',dict(schema='zerosis.original_terrain_model.cpu_cleanup.v1',directory=str(build),
        files=rows,protected_inputs=after,exact_owned_intermediates_only=True))
    for row in rows:
        path=Path(row['path']);current=common.artifact(path)
        assert all(current[key]==row[key] for key in ('bytes','sha256','file_identity','mtime_ns','file_attributes','links'))
        path.unlink()
    assert not any(build.iterdir());build.rmdir()
    cleanup=dict(status='PASS_EXACT_OWNED_CPU_INTERMEDIATES_REMOVED',files=rows,deleted_files=len(rows),
        released_unique_allocated_bytes=sum(row['allocated_bytes'] for row in rows),originals_unchanged=True)
    write_new(stage/'cleanup_result.json',cleanup)
    proof=dict(schema='zerosis.original_terrain_model.cpu_reference.v1',status='PASS_PRODUCTION_CPU_MODEL_CXX14',
        checks=int(match[1]),inputs_before=before,inputs_after=after,build=compiled,executed_console=executable,
        imported_dlls=names,golden=golden,real_piece_count=299,real_decoded_pixels=42008576,
        original_fxsb_unchanged=True,independent_tile_picking_not_modified_by_model=True,
        report_label='규칙 동등, 배치 동등은 미검증',host_sdk_clr_hwnd_gpu_audio_or_game_executed=False,
        gpu_parity_verified=False,retained_test_executable=False,cleanup=common.artifact(stage/'cleanup_result.json'),
        candidate_policies=['Orientation component order then placement translation; original multiplication order remains open.',
            'Cube rounding and fixed source/atlas origin (-32,0) are explicit; runtime alignment remains unverified.',
            'Equal histogram ties use material index order; caller supplies unconfirmed height offset/world scale.',
            'Zero total shader alpha returns zero instead of nonfinite values.'])
    write_new(stage/'result.json',proof)
    print(json.dumps(dict(status=proof['status'],checks=proof['checks'],result=str(stage/'result.json'),
        cleanup_files=len(rows),released_unique_allocated_bytes=cleanup['released_unique_allocated_bytes'],
        host_sdk_gpu_executed=False)))

if __name__=='__main__':main()
