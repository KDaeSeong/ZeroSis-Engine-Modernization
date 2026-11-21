"""Borrowed mip0 BC3 reference against fixed original compressed textures."""
from __future__ import annotations
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import struct
import sys

sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[1];ROOT=PROJECT/'evidence/world_terrain_original/phase6/review/material_sampler'
sys.path[0:0]=[str(PROJECT/'tools'),str(PROJECT/'Tests')]
import build_exit_confirm_host as common
from menu_replay_restoration import build_cxx14
from menu_suite_storage import storage
from native_build import run

SHA='02104c582759bf0cefb58f97379699e45300eb2a9c6da6fdd3c65d1440cb84e8';DIRECTORY=PROJECT/'Build/OriginalTerrainAssets'/SHA;PACKAGE=DIRECTORY/'terrain-assets.bin'

def write_new(path,value):
    with path.open('x',encoding='utf8')as f:json.dump(value,f,indent=2);f.write('\n')

def texel(raw,width,x,y,alpha):
    at=((y//4)*((width+3)//4)+x//4)*16;pixel=(y%4)*4+x%4
    if alpha:
        a,b=raw[at:at+2]
        palette=[a,b]+[((7-i)*a+i*b)//7 for i in range(1,7)]if a>b else[a,b]+[((5-i)*a+i*b)//5 for i in range(1,5)]+[0,255]
        index=(int.from_bytes(raw[at+2:at+8],'little')>>(3*pixel))&7;return palette[index]/255
    a,b,bits=struct.unpack_from('<HHI',raw,at+8);a=(a>>11)&31;b=(b>>11)&31;a=a*8+a//4;b=b*8+b//4
    return[a,b,(2*a+b)//3,(a+2*b)//3][(bits>>(2*pixel))&3]/255

def bilinear(raw,width,height,u,v,mode,alpha):
    if mode:u=max(0,min(1,u));v=max(0,min(1,v))
    else:u%=1;v%=1
    x=u*width-.5;y=v*height-.5;ix=math.floor(x);iy=math.floor(y);fx=x-ix;fy=y-iy;result=0
    for dy in range(2):
        for dx in range(2):
            px=max(0,min(width-1,ix+dx))if mode else(ix+dx)%width;py=max(0,min(height-1,iy+dy))if mode else(iy+dy)%height
            result+=(fx if dx else 1-fx)*(fy if dy else 1-fy)*texel(raw,width,px,py,alpha)
    return result

def references(build):
    manifest=json.loads((DIRECTORY/'terrain-assets.manifest.json').read_text('utf8'));ids={role:{r['texture_indices'][role]for r in manifest['rows']}for role in('diffuse','height')}
    ids={k:{i for i in v if i<len(manifest['textures'])}for k,v in ids.items()};indices=sorted(ids['diffuse']|ids['height']);rows=[str(len(indices))];rng=random.Random(1706);samples=0;proof=[]
    with PACKAGE.open('rb')as stream:
        for index in indices:
            t=manifest['textures'][index];w=t['dds']['width'];h=t['dds']['height'];size=((w+3)//4)*((h+3)//4)*16
            stream.seek(t['offset']+128);raw=stream.read(size);assert len(raw)==size;queries=[]
            points=[(0,0),(1,1),(-1,-1),(-.25,1.25),(.5/w,.5/h),(1-.5/w,1-.5/h),(.5,.5),(-.5/w,-.5/h)]+[(rng.uniform(-2,2),rng.uniform(-2,2))for _ in range(56)]
            alpha=index in ids['diffuse']
            for mode in(0,1):
                for u,v in points:queries.append((int(alpha),mode,u,v,bilinear(raw,w,h,u,v,mode,alpha)))
            rows.append(' '.join(str(v)for v in(index,w,h,len(queries))));rows.extend(' '.join(format(v,'.17g')if isinstance(v,float)else str(v)for v in q)for q in queries);samples+=len(queries)
            proof.append(dict(index=index,name=t['name'],width=w,height=h,channel='alpha'if alpha else'red',raw_sha256=t['sha256'],borrowed_top_bytes=size,queries=len(queries)))
    path=build/'references.txt';path.write_text('\n'.join(rows)+'\n',encoding='ascii');return path,proof,samples

def main():
    stage=ROOT/'attempt01';build=stage/'work';assert not stage.exists();assert not any(os.environ.get(k)for k in('CL','_CL_','LINK'));build.mkdir(parents=True)
    paths=[PROJECT/'Source/Presentation/OriginalTerrainMaterialSampler.h',PROJECT/'Source/Presentation/OriginalTerrainPackage.h',PROJECT/'Source/Presentation/OriginalTerrainBinding.h',PROJECT/'Source/Presentation/OriginalTerrainSha256.h',Path(__file__),PROJECT/'Tests/original_terrain_material_sampler.cpp']
    inputs=[common.artifact(p)for p in paths];original=common.artifact(PACKAGE);assert original['sha256']==SHA
    write_new(stage/'started.json',dict(inputs=inputs,package=original,host_gamecore_clr_hwnd_gpu_audio_or_game_executed=False))
    try:
        reference,proof,samples=references(build);write_new(stage/'references.json',dict(textures=proof,actual_samples=samples,production_cpu_raw_retention_bytes=0))
        compiled=build_cxx14('original_terrain_material_sampler',build,stage,PROJECT/'Tests/original_terrain_material_sampler.cpp',[PROJECT/'Source/Presentation'])
        deps=run([Path(compiled['compiler']).with_name('dumpbin.exe'),'/dependents',compiled['path']],cwd=build,timeout=30)
        libs=sorted(set(re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$',deps.stdout.decode('mbcs',errors='replace'),re.M)));assert deps.returncode==0 and {k.lower()for k in libs}=={'kernel32.dll'}
        exe=common.artifact(compiled['path']);done=run([compiled['path'],PACKAGE,reference],cwd=build,timeout=60);stdout=done.stdout.decode('ascii');stderr=done.stderr.decode('ascii')
        match=re.fullmatch(r'PASS_MATERIAL_BORROWED_BC3_SAMPLER checks=(\d+) actual_samples=(\d+) textures=59 rejected=(\d+)\s*',stdout)
        assert done.returncode==0 and not stderr and match and int(match[2])==samples,(done.returncode,stdout,stderr)
        assert [common.artifact(p)for p in paths]==inputs and common.artifact(PACKAGE)==original
        files=[]
        for path in sorted(build.iterdir()):
            assert path.is_file()and path.suffix in('.txt','.exe','.obj','.map','.rsp','.cmd');row=common.artifact(path);assert row['links']==1 and not row['file_attributes']&0x401;row['allocated_bytes']=storage.allocated(path);files.append(row)
        write_new(stage/'cleanup_plan.json',dict(files=files,protected=inputs+[original]))
        for row in files:assert common.artifact(row['path'])=={k:v for k,v in row.items()if k!='allocated_bytes'};Path(row['path']).unlink()
        assert not any(build.iterdir());build.rmdir();write_new(stage/'cleanup_result.json',dict(status='PASS_OWNED_BORROWED_MATERIAL_TEST_INTERMEDIATES_REMOVED',files=files,deleted_files=len(files),released_unique_allocated_bytes=sum(r['allocated_bytes']for r in files)))
        result=dict(status='PASS_CPP14_BORROWED_BC3_RED_ALPHA_MIP0_BILINEAR',checks=int(match[1]),actual_samples=samples,textures=59,rejected=int(match[3]),inputs=inputs,package=original,
            imported_dlls=libs,build=compiled,executed_console=exe,cleanup=common.artifact(stage/'cleanup_result.json'),new_raw_asset_copies=0,production_cpu_raw_retention_bytes=0,
            limitations=['CPU byte palette uses integer interpolation;hardware BC decode rounding and field half quantisation await actual GPU comparison','Reference console temporarily owns sealed112MBTerrainPackage;no production catalogue source retention'],host_gamecore_clr_hwnd_gpu_audio_or_game_executed=False)
        write_new(stage/'result.json',result);print(json.dumps({k:result[k]for k in('status','checks','actual_samples','textures','rejected')}))
    except BaseException as e:
        write_new(stage/'failure.json',dict(error_type=type(e).__name__,message=str(e)[:8000],inputs_unchanged=[common.artifact(p)for p in paths]==inputs,package_unchanged=common.artifact(PACKAGE)==original));raise

if __name__=='__main__':main()
