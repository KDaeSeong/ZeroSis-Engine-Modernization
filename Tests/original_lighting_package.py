"""Real C++14 CPU reader, full cube mip decode and LUT reference comparison."""
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
STAGE=PROJECT/'evidence/world_terrain_original/phase5/assets/package_tests'
SHA='d0873d3915da23e45ee1b66187bb7e4174673a1e8cce1fea16b6151ff515e424'
PACKAGE=PROJECT/'Build/OriginalLightingAssets'/SHA/'lighting-assets.bin'
sys.path[0:0]=[str(PROJECT/'tools'),str(PROJECT/'Tests')]
import build_exit_confirm_host as common
import civ5_original_lighting_assets as lighting
import original_lighting_assets as fixtures
from menu_replay_restoration import build_cxx14
from menu_suite_storage import storage
from native_build import run

def write_new(path,value):
    with path.open('x',encoding='utf8')as stream:json.dump(value,stream,indent=2);stream.write('\n')

def references(build):
    parsed=lighting.validate_package(PACKAGE,SHA);raw=PACKAGE.read_bytes();rows=[];proof=[];texels=0
    for asset in parsed['assets']:
        rows.append(' '.join(str(asset[k])for k in('role','offset','bytes','blob_index','name','sha256')))
        item=dict(role=asset['role'],name=asset['name'],raw_sha256=asset['sha256'],decoded=[])
        if asset['role']<=10:
            cube=asset['cube'];rows.append(' '.join(str(v)for v in(cube['width'],cube['height'],cube['mips'],len(cube['levels']))))
            for level in cube['levels']:
                offset=level['package_offset'];data=raw[offset:offset+level['bytes']];decoded=fixtures.bc1_rgba(data,level['width'],level['height'])
                sha=hashlib.sha256(decoded).hexdigest();rows.append(' '.join(str(v)for v in(level['face'],level['mip'],level['width'],level['height'],offset,level['bytes'],level['row_pitch'],sha)))
                item['decoded'].append(dict(face=level['face'],mip=level['mip'],texels=len(decoded)//4,sha256=sha));texels+=len(decoded)//4
        else:
            data=raw[asset['offset']:asset['offset']+asset['bytes']];decoded=lighting.candidate_lut32(data);sha=hashlib.sha256(decoded).hexdigest()
            rows.append(str(len(decoded))+' '+sha);item['decoded'].append(dict(texels=32768,rgba_sha256=sha));texels+=32768
        proof.append(item)
    path=build/'references.txt';path.write_text('\n'.join(rows)+'\n',encoding='ascii');return path,proof,texels

def create_fixtures(build):
    python_result=fixtures.run();cases=fixtures.cases();table=[str(len(cases))];records=[]
    for i,case in enumerate(cases):
        raw=case['data'];name='case_'+str(i).zfill(3)+'.bin';(build/name).write_bytes(raw);sha=case.get('supplied_sha256')or hashlib.sha256(raw).hexdigest()
        table.append(str(int(case['accepted']))+' '+sha+' '+name+' '+case['label']);records.append(dict(python_result[i],filename=name))
    (build/'cases.txt').write_text('\n'.join(table)+'\n',encoding='ascii');return records

def cleanup(build,stage,protected):
    assert build.resolve()==build and build.is_relative_to(STAGE)and not build.lstat().st_file_attributes&0x400;files=[]
    for path in sorted(build.iterdir()):
        assert path.is_file()and path.suffix in('.bin','.txt','.exe','.obj','.map','.rsp','.cmd')
        row=common.artifact(path);assert row['links']==1 and not row['file_attributes']&0x401;row['allocated_bytes']=storage.allocated(path);files.append(row)
    write_new(stage/'cleanup_plan.json',dict(directory=str(build),files=files,protected=protected))
    for row in files:
        now=common.artifact(row['path']);assert all(now[k]==row[k]for k in('bytes','sha256','file_identity','mtime_ns','file_attributes','links'));Path(row['path']).unlink()
    assert not any(build.iterdir());build.rmdir();write_new(stage/'cleanup_result.json',dict(status='PASS_EXACT_OWNED_LIGHTING_CPP_INTERMEDIATES_REMOVED',
        files=files,deleted_files=len(files),released_unique_allocated_bytes=sum(row['allocated_bytes']for row in files),raw_original_copies=0))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--attempt',type=int,default=1);args=parser.parse_args();assert 1<=args.attempt<=5
    stage=STAGE/('attempt'+str(args.attempt));build=stage/'work';assert not stage.exists(),'Inspect prior lighting attempt first'
    assert not any(os.environ.get(name)for name in('CL','_CL_','LINK'));build.mkdir(parents=True)
    names=['Source/Presentation/OriginalLightingPackage.h','Source/Presentation/OriginalLightingBinding.h','Source/Presentation/OriginalTerrainSha256.h',
        'Source/Presentation/OriginalFogPackage.h','tools/civ5_original_lighting_assets.py','Tests/original_lighting_assets.py',
        'Tests/original_lighting_package.cpp','Tests/original_lighting_package.py','Source/Presentation/OriginalLightingGpuTypes.inc','Source/Presentation/OriginalLightingGpu.inc']
    inputs=[common.artifact(PROJECT/name)for name in names];original=common.artifact(PACKAGE);assert original['sha256']==SHA
    write_new(stage/'started.json',dict(inputs=inputs,package=original,native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False))
    try:
        reference,reference_meta,texels=references(build);cases=create_fixtures(build);write_new(stage/'reference_summary.json',dict(assets=reference_meta,source_texels=texels))
        write_new(stage/'fixture_cases.json',dict(cases=cases,raw_original_copies=0))
        compiled=build_cxx14('original_lighting_package',build,stage,PROJECT/'Tests/original_lighting_package.cpp',[PROJECT/'Source/Presentation'])
        imports=run([Path(compiled['compiler']).with_name('dumpbin.exe'),'/dependents',compiled['path']],cwd=build,timeout=30)
        libraries=sorted(set(re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$',imports.stdout.decode('mbcs',errors='replace'),re.M)))
        assert imports.returncode==0 and {name.lower()for name in libraries}=={'kernel32.dll'},libraries
        executable=common.artifact(compiled['path']);output=run([compiled['path'],PACKAGE,reference,build],cwd=build,timeout=60)
        stdout=output.stdout.decode('ascii');stderr=output.stderr.decode('ascii');match=re.fullmatch(
            r'PASS_ORIGINAL_LIGHTING_PACKAGE checks=(\d+) fixtures=(\d+) assets=15 blobs=9 source_texels=(\d+) rejected_api=(\d+)\s*',stdout)
        assert output.returncode==0 and not stderr and match,(output.returncode,stdout,stderr)
        assert int(match[3])==texels and int(match[2])==len(cases)
        after=[common.artifact(PROJECT/name)for name in names];assert after==inputs and common.artifact(PACKAGE)==original
        cleanup(build,stage,after+[original]);proof=dict(status='PASS_PRODUCTION_CPP14_LIGHTING_FULL_CUBE_MIPS_LUT_AND_BOUNDED_READER',
            checks=int(match[1]),fixtures=int(match[2]),api_rejections=int(match[4]),assets=15,blobs=9,source_texels=texels,cube_subresources=480,lut_texels=163840,
            source_inputs=inputs,source_inputs_after=after,package=original,build=compiled,executed_console=executable,imported_dlls=libraries,
            cleanup=common.artifact(stage/'cleanup_result.json'),native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False)
        write_new(stage/'result.json',proof);print(json.dumps({k:proof[k]for k in('status','checks','fixtures','api_rejections','source_texels','cube_subresources')}))
    except BaseException as error:
        write_new(stage/'failure.json',dict(error_type=type(error).__name__,message=str(error)[:8000],
            inputs_unchanged=[common.artifact(PROJECT/name)for name in names]==inputs,package_unchanged=common.artifact(PACKAGE)==original));raise

if __name__=='__main__':main()
