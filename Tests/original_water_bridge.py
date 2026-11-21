"""Actual sealed coast library to production bridge; CPU-only integration."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys

sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[1]
STAGE=PROJECT/'evidence/world_terrain_original/phase3/bridge'
PACKAGE_SHA='2ff227dae9d16398e038e8ea33624940a9581e0eb2d37c3891121fae22c25afc'
PACKAGE=PROJECT/'Build/OriginalWaterAssets'/PACKAGE_SHA/'water-assets.bin'
sys.path[0:0]=[str(PROJECT/'tools'),str(PROJECT/'Tests')]
import build_exit_confirm_host as common
import civ5_original_water_assets as water
from menu_replay_restoration import build_cxx14
from menu_suite_storage import storage
from native_build import run

def write_new(path,value):
    with path.open('x',encoding='utf8')as stream:json.dump(value,stream,indent=2);stream.write('\n')

def reference_profiles(build):
    raw=PACKAGE.read_bytes();parsed=water.validate_package_bytes(raw,PACKAGE_SHA);profiles=[]
    for asset in parsed['assets'][15:24]:profiles.append(water.parse_coast_profile(raw[asset['offset']:asset['offset']+asset['bytes']]))
    rows=[]
    def points(mode,index,band,profile):
        # Knot ordinates and adjacent means are direct independent source
        # facts, not a reimplementation of the production binary search.
        for x,y,z in profile:rows.append((mode,index,band,1-x/400,y))
        for a,b in zip(profile,profile[1:]):rows.append((mode,index,band,1-(a[0]+b[0])/800,(a[1]+b[1])/2))
    for index,profile in enumerate(profiles):points(0,index,0,profile)
    for index,style in enumerate(parsed['assets'][14]['styles']):
        for band,name in enumerate(('waterline','low_beach','high_beach')):
            character=style[name]['character']
            if character==65535:rows.extend((1,index,band,t,0)for t in(0,.125,.5,.875,1))
            else:points(1,index,band,profiles[character])
    path=build/'profile_reference.txt';path.write_text(str(len(rows))+'\n'+'\n'.join(' '.join(format(v,'.17g')if isinstance(v,float)else str(v)for v in row)for row in rows)+'\n',encoding='ascii')
    return path,dict(rows=len(rows),source_profiles=9,source_styles=13,all_original_knots=900,all_profile_midpoints=891,
        reference='Python XML/ASCII parser;source knot Y and adjacent arithmetic means;all style bands including65535 sentinel')

def reference_maps(build):
    cases=[(4,4,False,False,0),(4,4,True,False,0),(4,4,True,True,0),(5,6,False,True,1),
        (6,4,True,False,1),(40,24,True,True,1),(4,4,True,True,2),(4,4,True,True,3),(4,4,False,False,4),(4,4,True,True,5)]
    records=[]
    for width,height,wx,wy,pattern in cases:
        cells=[]
        for y in range(height):
            for x in range(width):cells.append(dict(revealed=pattern!=2 and(pattern!=1 or(3*x+y)%5!=0),
                water=pattern==3 or(pattern in(0,1,2)and(x+2*y)%3==0),
                river=[pattern in(0,1,5)and(x+2*y+slot)%4==0 for slot in range(3)]))
        coast=river=0;water_count=sum(c['revealed']and c['water']for c in cells)
        # Independent axial E/SE/SW vectors, converted back to odd-row offset.
        for y in range(height):
            for x in range(width):
                cell=cells[y*width+x]
                if not cell['revealed']:continue
                q=x-y//2
                for slot,(dq,dr)in enumerate(((1,0),(1,-1),(0,-1))):
                    nr=y+dr;nx=q+dq+nr//2
                    if wx:nx%=width
                    if wy:nr%=height
                    if not(0<=nx<width and 0<=nr<height):continue
                    other=cells[nr*width+nx]
                    if not other['revealed']:continue
                    coast+=cell['water']!=other['water'];river+=cell['river'][slot]
        count=18*water_count+6*(8*coast+4*river)
        records.append(dict(width=width,height=height,wrap_x=wx,wrap_y=wy,pattern=pattern,water=water_count,coasts=coast,rivers=river,vertices=count))
    path=build/'map_reference.txt';rows=[str(len(records))]
    for c in records:rows.append(' '.join(str(int(c[k]))for k in('width','height','wrap_x','wrap_y','pattern','water','coasts','rivers','vertices')))
    path.write_text('\n'.join(rows)+'\n',encoding='ascii');return path,records

def cleanup(build,stage,protected):
    assert build.resolve()==build and build.is_relative_to(STAGE)and not build.lstat().st_file_attributes&0x400;files=[]
    for path in sorted(build.iterdir()):
        assert path.is_file()and path.suffix in('.txt','.exe','.obj','.map','.rsp','.cmd')
        row=common.artifact(path);assert row['links']==1 and not row['file_attributes']&0x401;row['allocated_bytes']=storage.allocated(path);files.append(row)
    write_new(stage/'cleanup_plan.json',dict(directory=str(build),files=files,protected=protected))
    for row in files:
        now=common.artifact(row['path']);assert all(now[k]==row[k]for k in('bytes','sha256','file_identity','mtime_ns','file_attributes','links'));Path(row['path']).unlink()
    assert not any(build.iterdir());build.rmdir();write_new(stage/'cleanup_result.json',dict(status='PASS_EXACT_OWNED_WATER_BRIDGE_INTERMEDIATES_REMOVED',
        files=files,deleted_files=len(files),released_unique_allocated_bytes=sum(row['allocated_bytes']for row in files),raw_original_copies=0))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--attempt',type=int,default=1);args=parser.parse_args();assert 1<=args.attempt<=5
    stage=STAGE/('attempt'+str(args.attempt));build=stage/'work';assert not stage.exists(),'Inspect prior bridge attempt first'
    assert not any(os.environ.get(name)for name in('CL','_CL_','LINK'));build.mkdir(parents=True)
    names=['Source/Presentation/OriginalWaterBridge.h','Source/Presentation/OriginalWaterModel.h','Source/Presentation/OriginalWaterState.h',
        'Source/Presentation/OriginalWaterPackage.h','Source/Presentation/OriginalFogPackage.h','Source/Presentation/OriginalTerrainSha256.h',
        'Source/Presentation/OriginalTerrainGeometry.h','Source/Presentation/OriginalTerrainBinding.h','Source/Presentation/OriginalTerrainModel.h',
        'Source/Presentation/WorldViewRenderer.h','Tests/original_water_bridge.cpp','Tests/original_water_bridge.py','tools/civ5_original_water_assets.py']
    inputs=[common.artifact(PROJECT/name)for name in names];original=common.artifact(PACKAGE);assert original['sha256']==PACKAGE_SHA
    write_new(stage/'started.json',dict(inputs=inputs,package=original,native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False))
    try:
        profiles,profile_meta=reference_profiles(build);maps,map_meta=reference_maps(build)
        write_new(stage/'reference_summary.json',dict(profile_reference=profile_meta,maps=map_meta,atlas_fixture='40x24 CPU-only;no file texture or game data copied'))
        compiled=build_cxx14('original_water_bridge',build,stage,PROJECT/'Tests/original_water_bridge.cpp',[PROJECT/'Source/Presentation'])
        imports=run([Path(compiled['compiler']).with_name('dumpbin.exe'),'/dependents',compiled['path']],cwd=build,timeout=30)
        libraries=sorted(set(re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$',imports.stdout.decode('mbcs',errors='replace'),re.M)))
        assert imports.returncode==0 and{name.lower()for name in libraries}=={'kernel32.dll'},libraries
        executable=common.artifact(compiled['path']);output=run([compiled['path'],PACKAGE,profiles,maps],cwd=build,timeout=60)
        stdout=output.stdout.decode('ascii');stderr=output.stderr.decode('ascii');match=re.fullmatch(
            r'PASS_ORIGINAL_WATER_BRIDGE checks=(\d+) profile_samples=(\d+) maps=(\d+) height_samples=(\d+) rejections=(\d+)\s*',stdout)
        assert output.returncode==0 and not stderr and match,(output.returncode,stdout,stderr)
        after=[common.artifact(PROJECT/name)for name in names];assert after==inputs and common.artifact(PACKAGE)==original
        cleanup(build,stage,after+[original]);proof=dict(status='PASS_PRODUCTION_CPP14_WATER_PACKAGE_PROFILE_ATLAS_MESH_BRIDGE',
            checks=int(match[1]),profile_samples=int(match[2]),maps=int(match[3]),height_samples=int(match[4]),rejections=int(match[5]),
            profile_reference=profile_meta,map_reference=map_meta,source_inputs=inputs,source_inputs_after=after,package=original,
            build=compiled,executed_console=executable,imported_dlls=libraries,cleanup=common.artifact(stage/'cleanup_result.json'),
            preconditions='CoastProfileY standalone consumes parser-validated canonical profiles;BuildAtlasMesh malformed-profile validation tested.',
            raw_height_calibration='candidate atlas lift/scale/offset reconstruction,not retail cache equivalence',
            native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False)
        write_new(stage/'result.json',proof);print(json.dumps({k:proof[k]for k in('status','checks','profile_samples','maps','height_samples','rejections')}))
    except BaseException as error:
        write_new(stage/'failure.json',dict(error_type=type(error).__name__,message=str(error)[:8000],
            inputs_unchanged=[common.artifact(PROJECT/name)for name in names]==inputs,package_unchanged=common.artifact(PACKAGE)==original));raise

if __name__=='__main__':main()
