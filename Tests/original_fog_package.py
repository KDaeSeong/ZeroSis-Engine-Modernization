"""Compile production C++14 parser and run Kernel32-only CPU byte checks."""
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
STAGE=PROJECT/'evidence/world_terrain_original/phase2/package_tests'
PACKAGE_SHA='42ae12554e1514dd48a9a5df25f47b4280d22d180dff29d169c602334e879bcc'
PACKAGE=PROJECT/'Build/OriginalFogAssets'/PACKAGE_SHA/'fog-assets.bin'
sys.path[0:0]=[str(PROJECT/'tools'),str(PROJECT/'Tests')]
import build_exit_confirm_host as common
import civ5_original_fog_assets as fog
import civ5_ui_assets as ui
import original_fog_assets as fixtures
from menu_replay_restoration import build_cxx14
from menu_suite_storage import storage
from native_build import run

def write_new(path,value):
    with path.open('x',encoding='utf8') as stream:json.dump(value,stream,indent=2);stream.write('\n')

def reference_top_rgba(data,texture):
    """Use the pre-existing Python UI decoder as an independent language path."""
    words=list(struct.unpack_from('<32I',data))
    if texture['format']=='BC1':bgra,_=ui.decode_dxt1_top_mip(data,words)
    elif texture['format']=='BC3':bgra,_=ui.decode_dxt5_top_mip(data,words)
    else:bgra=data[128:128+texture['width']*texture['height']*4]
    result=bytearray(len(bgra));result[0::4]=bgra[2::4];result[1::4]=bgra[1::4];result[2::4]=bgra[0::4];result[3::4]=bgra[3::4]
    return result

def reference_lut_rgba(data):
    width,height=struct.unpack_from('<HH',data,12);origin=data[17];result=bytearray()
    for z in range(32):
        for y in range(32):
            for x in range(32):
                linear=x+32*y+1024*z;column,row=linear%width,linear//width
                if origin&16:column=width-1-column
                if not origin&32:row=height-1-row
                blue,green,red,alpha=struct.unpack_from('4B',data,18+4*(column+width*row));result.extend((red,green,blue,alpha))
    return result

def create_fixtures(build):
    cases=[dict(label='valid_base',data=fixtures.package(),accepted=True,identity=True)]
    for label,data,sha in fixtures.rejection_cases():cases.append(dict(label=label,data=data,supplied_sha256=sha,accepted=False,identity=False))
    for origin in (8,24,40,56):
        values=fixtures.assets();values[6]=(values[6][0],fixtures.tga(origin));cases.append(dict(label='valid_tga_origin_'+str(origin),
            data=fixtures.package(values),accepted=True,identity=True))
    values=fixtures.assets();values[7]=(values[7][0],b' 0 ,255,001\t\n')
    cases.append(dict(label='valid_csv_whitespace_and_zeroes',data=fixtures.package(values),accepted=True,identity=False))
    result=[];table=[str(len(cases))]
    for index,case in enumerate(cases):
        data=case.pop('data');sha=hashlib.sha256(data).hexdigest();name='case_'+str(index).zfill(3)+'.bin';(build/name).write_bytes(data)
        row=dict(case,filename=name,bytes=len(data),sha256=sha);row['supplied_sha256']=row.get('supplied_sha256') or sha
        result.append(row);table.append(str(int(row['accepted']))+' '+str(int(row['identity']))+' '+row['supplied_sha256']+' '+name)
    (build/'cases.txt').write_text('\n'.join(table)+'\n',encoding='ascii');return result

def metadata(build):
    parsed=fog.validate_package(PACKAGE,PACKAGE_SHA);raw=PACKAGE.read_bytes();rows=['9 '+str(len(raw))+' '+PACKAGE_SHA]
    format_ids={'BC1':1,'BC3':2,'BGRA8':3};decoded=[]
    for asset in parsed['assets']:
        texture=asset.get('texture');role=asset['role']
        row=[role,asset['offset'],asset['bytes'],format_ids[texture['format']] if texture else 0,
            texture['width'] if texture else 0,texture['height'] if texture else 0,texture['mips'] if texture else 0,asset['sha256'],asset['name']]
        rows.append(' '.join(str(value) for value in row));data=raw[asset['offset']:asset['offset']+asset['bytes']]
        if texture:
            for level in texture['levels']:
                rows.append(' '.join(str(level[key]) for key in ('package_offset','bytes','row_pitch','width','height')))
            rgba=reference_top_rgba(data,texture);sha=hashlib.sha256(rgba).hexdigest();rows.append(sha)
            decoded.append(dict(role=role,rgba_bytes=len(rgba),rgba_sha256=sha,reference='retained Python UI decoder / exact BGRA masks'))
        if role==7:lut=reference_lut_rgba(data)
    lut_sha=hashlib.sha256(lut).hexdigest();rows.append(lut_sha)
    path=build/'python_metadata.txt';path.write_text('\n'.join(rows)+'\n',encoding='ascii')
    return path,decoded,dict(bytes=len(lut),sha256=lut_sha,candidate=True,retail_loader_equivalence_verified=False)

def cleanup(build,stage,protected):
    retired=[]
    assert build.resolve()==build and build.is_relative_to(STAGE) and not build.lstat().st_file_attributes&0x400
    for path in sorted(build.iterdir()):
        assert path.is_file() and path.suffix in ('.bin','.txt','.exe','.obj','.map','.rsp','.cmd')
        row=common.artifact(path);assert row['links']==1 and not row['file_attributes']&0x401
        row['allocated_bytes']=storage.allocated(path);retired.append(row)
    write_new(stage/'cleanup_plan.json',dict(directory=str(build),files=retired,protected=protected))
    for row in retired:
        now=common.artifact(row['path']);assert all(now[key]==row[key] for key in ('bytes','sha256','file_identity','mtime_ns','file_attributes','links'))
        Path(row['path']).unlink()
    assert not any(build.iterdir());build.rmdir()
    write_new(stage/'cleanup_result.json',dict(status='PASS_EXACT_OWNED_FOG_CPP_CPU_INTERMEDIATES_REMOVED',files=retired,
        deleted_files=len(retired),released_unique_allocated_bytes=sum(row['allocated_bytes'] for row in retired),original_asset_copies=0))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--attempt',type=int,default=1);args=parser.parse_args()
    assert 1<=args.attempt<=5
    stage=STAGE/('attempt'+str(args.attempt));build=stage/'work'
    assert not stage.exists(),'Inspect and preserve existing attempt before restarting'
    assert not any(os.environ.get(name) for name in ('CL','_CL_','LINK'))
    build.mkdir(parents=True)
    names=['Source/Presentation/OriginalTerrainSha256.h','Source/Presentation/OriginalFogPackage.h','tools/civ5_original_fog_assets.py',
           'Tests/original_fog_assets.py','Tests/original_fog_package.cpp','Tests/original_fog_package.py','tools/civ5_ui_assets.py']
    inputs=[common.artifact(PROJECT/name) for name in names];original=common.artifact(PACKAGE);assert original['sha256']==PACKAGE_SHA
    write_new(stage/'started.json',dict(inputs=inputs,package=original,native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False))
    try:
        reference,decoded,lut=metadata(build);cases=create_fixtures(build);write_new(stage/'fixture_cases.json',dict(cases=cases,original_asset_copies=0))
        compiled=build_cxx14('original_fog_package',build,stage,PROJECT/'Tests/original_fog_package.cpp',[PROJECT/'Source/Presentation'])
        imports=run([Path(compiled['compiler']).with_name('dumpbin.exe'),'/dependents',compiled['path']],cwd=build,timeout=30)
        libraries=sorted(set(re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$',imports.stdout.decode('mbcs',errors='replace'),re.M)))
        assert imports.returncode==0 and {name.lower() for name in libraries}=={'kernel32.dll'},libraries
        executable=common.artifact(compiled['path']);output=run([compiled['path'],PACKAGE,reference,build],cwd=build,timeout=60)
        stdout=output.stdout.decode('ascii');stderr=output.stderr.decode('ascii');match=re.fullmatch(
            r'PASS_ORIGINAL_FOG_PACKAGE checks=(\d+) fixtures=(\d+) real_assets=9 textures=6 candidate_lut=32\s*',stdout)
        assert output.returncode==0 and not stderr and match,(output.returncode,stdout,stderr)
        after=[common.artifact(PROJECT/name) for name in names];assert after==inputs and common.artifact(PACKAGE)==original
        protected=after+[original];cleanup(build,stage,protected)
        proof=dict(status='PASS_PRODUCTION_CPP14_FOG_PACKAGE_AND_RGBA_LUT_DECODING',checks=int(match[1]),fixtures=int(match[2]),
            assets=9,textures=6,decoded_top_mips=decoded,candidate_lut=lut,package=original,inputs_before=inputs,inputs_after=after,
            build=compiled,executed_console=executable,imported_dlls=libraries,cleanup=common.artifact(stage/'cleanup_result.json'),
            native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False)
        write_new(stage/'result.json',proof)
        print(json.dumps({key:proof[key] for key in ('status','checks','fixtures','assets','textures')}))
    except BaseException as error:
        write_new(stage/'failure.json',dict(error_type=type(error).__name__,message=str(error)[:8000],
            inputs_unchanged=[common.artifact(PROJECT/name) for name in names]==inputs,package_unchanged=common.artifact(PACKAGE)==original))
        raise

if __name__=='__main__':main()
