"""Production C++14 water reader; Kernel32-only console and exact cleanup."""
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
STAGE=PROJECT/'evidence/world_terrain_original/phase3/package_tests'
PACKAGE_SHA='2ff227dae9d16398e038e8ea33624940a9581e0eb2d37c3891121fae22c25afc'
PACKAGE=PROJECT/'Build/OriginalWaterAssets'/PACKAGE_SHA/'water-assets.bin'
sys.path[0:0]=[str(PROJECT/'tools'),str(PROJECT/'Tests')]
import build_exit_confirm_host as common
import civ5_original_water_assets as water
import original_water_assets as fixtures
from original_fog_package import reference_top_rgba
from menu_replay_restoration import build_cxx14
from menu_suite_storage import storage
from native_build import run

def write_new(path,value):
    with path.open('x',encoding='utf8')as stream:json.dump(value,stream,indent=2);stream.write('\n')

def create_fixtures(build):
    cases=[dict(label='valid_base',data=fixtures.package(),accepted=True)]
    for label,data,sha in fixtures.rejection_cases():cases.append(dict(label=label,data=data,supplied_sha256=sha,accepted=False))
    for label,role,data in [('valid_xml_comment',15,fixtures.styles().replace(b'<SplineCharacterList',b'<!-- reference --><SplineCharacterList',1)),
        ('valid_xml_scientific',15,fixtures.styles().replace(b'Height=".2044"',b'Height="2.044e-1"',1)),
        ('valid_profile_lf_whitespace',16,fixtures.profile().replace(b'\r\n',b'\n').replace(b',',b' ,\t'))]:
        values=fixtures.assets();values[role-1]=(values[role-1][0],data);cases.append(dict(label=label,data=fixtures.package(values),accepted=True))
    result=[];table=[str(len(cases))]
    for index,case in enumerate(cases):
        data=case.pop('data');sha=hashlib.sha256(data).hexdigest();name='case_'+str(index).zfill(3)+'.bin';(build/name).write_bytes(data)
        row=dict(case,filename=name,bytes=len(data),sha256=sha);row['supplied_sha256']=row.get('supplied_sha256')or sha
        result.append(row);table.append(str(int(row['accepted']))+' '+row['supplied_sha256']+' '+name+' '+row['label'])
    (build/'cases.txt').write_text('\n'.join(table)+'\n',encoding='ascii');return result

def metadata(build):
    parsed=water.validate_package(PACKAGE,PACKAGE_SHA);raw=PACKAGE.read_bytes()
    rows=['25 24 '+str(len(raw))+' '+PACKAGE_SHA];decoded=[];formats={'BC1':1,'BC3':2,'BGRA8':3}
    for asset in parsed['assets']:
        texture=asset.get('texture');row=[asset['role'],asset['blob_index'],asset['offset'],asset['bytes'],formats[texture['format']]if texture else 0,
            texture['width']if texture else 0,texture['height']if texture else 0,texture['mips']if texture else 0,asset['sha256'],asset['name']]
        rows.append(' '.join(str(value)for value in row));data=raw[asset['offset']:asset['offset']+asset['bytes']]
        if texture:
            for level in texture['levels']:rows.append(' '.join(str(level[key])for key in('package_offset','bytes','row_pitch','width','height')))
            rgba=reference_top_rgba(data,texture);sha=hashlib.sha256(rgba).hexdigest();rows.append(sha)
            decoded.append(dict(role=asset['role'],rgba_bytes=len(rgba),rgba_sha256=sha,reference='retained independent Python UI decoder/exact BGRA masks'))
    for style in parsed['assets'][14]['styles']:
        row=[style['name'],style['high_smoothing'],style['low_smoothing']]
        for band in('high_beach','low_beach','waterline'):row.extend(style[band][key]for key in('height','offset','character','terrain_type'))
        rows.append(' '.join(str(value)for value in row))
    for asset in parsed['assets'][15:24]:
        data=raw[asset['offset']:asset['offset']+asset['bytes']];points=water.parse_coast_profile(data)
        rows.append(str(asset['role'])+' 100 '+asset['name'])
        rows.extend(' '.join(format(value,'.17g')for value in point)for point in points)
    path=build/'python_metadata.txt';path.write_text('\n'.join(rows)+'\n',encoding='ascii');return path,decoded

def cleanup(build,stage,protected):
    assert build.resolve()==build and build.is_relative_to(STAGE)and not build.lstat().st_file_attributes&0x400;retired=[]
    for path in sorted(build.iterdir()):
        assert path.is_file()and path.suffix in('.bin','.txt','.exe','.obj','.map','.rsp','.cmd')
        row=common.artifact(path);assert row['links']==1 and not row['file_attributes']&0x401
        row['allocated_bytes']=storage.allocated(path);retired.append(row)
    write_new(stage/'cleanup_plan.json',dict(directory=str(build),files=retired,protected=protected))
    for row in retired:
        now=common.artifact(row['path']);assert all(now[key]==row[key]for key in('bytes','sha256','file_identity','mtime_ns','file_attributes','links'))
        Path(row['path']).unlink()
    assert not any(build.iterdir());build.rmdir()
    write_new(stage/'cleanup_result.json',dict(status='PASS_EXACT_OWNED_WATER_CPP_CPU_INTERMEDIATES_REMOVED',files=retired,
        deleted_files=len(retired),released_unique_allocated_bytes=sum(row['allocated_bytes']for row in retired),original_asset_copies=0))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--attempt',type=int,default=1);args=parser.parse_args();assert 1<=args.attempt<=5
    stage=STAGE/('attempt'+str(args.attempt));build=stage/'work';assert not stage.exists(),'Inspect existing owned attempt before restart'
    assert not any(os.environ.get(name)for name in('CL','_CL_','LINK'));build.mkdir(parents=True)
    names=['Source/Presentation/OriginalWaterPackage.h','Source/Presentation/OriginalFogPackage.h','Source/Presentation/OriginalTerrainSha256.h',
        'tools/civ5_original_water_assets.py','tools/civ5_original_fog_assets.py','tools/civ5_ui_assets.py','Tests/original_water_assets.py',
        'Tests/original_water_package.cpp','Tests/original_water_package.py','Tests/original_fog_package.py']
    inputs=[common.artifact(PROJECT/name)for name in names];original=common.artifact(PACKAGE);assert original['sha256']==PACKAGE_SHA
    write_new(stage/'started.json',dict(inputs=inputs,package=original,native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False))
    try:
        reference,decoded=metadata(build);cases=create_fixtures(build);write_new(stage/'fixture_cases.json',dict(cases=cases,original_asset_copies=0))
        compiled=build_cxx14('original_water_package',build,stage,PROJECT/'Tests/original_water_package.cpp',[PROJECT/'Source/Presentation'])
        imports=run([Path(compiled['compiler']).with_name('dumpbin.exe'),'/dependents',compiled['path']],cwd=build,timeout=30)
        libraries=sorted(set(re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$',imports.stdout.decode('mbcs',errors='replace'),re.M)))
        assert imports.returncode==0 and {name.lower()for name in libraries}=={'kernel32.dll'},libraries
        executable=common.artifact(compiled['path']);output=run([compiled['path'],PACKAGE,reference,build],cwd=build,timeout=60)
        stdout=output.stdout.decode('ascii');stderr=output.stderr.decode('ascii');match=re.fullmatch(
            r'PASS_ORIGINAL_WATER_PACKAGE checks=(\d+) fixtures=(\d+) assets=25 textures=14 styles=13 profiles=9 points=900\s*',stdout)
        assert output.returncode==0 and not stderr and match,(output.returncode,stdout,stderr)
        after=[common.artifact(PROJECT/name)for name in names];assert after==inputs and common.artifact(PACKAGE)==original
        cleanup(build,stage,after+[original]);proof=dict(status='PASS_PRODUCTION_CPP14_WATER_PACKAGE_SHARED_DDS_XML_PROFILE_PARSERS',
            checks=int(match[1]),fixtures=int(match[2]),assets=25,textures=14,styles=13,profiles=9,points=900,decoded_top_mips=decoded,
            package=original,inputs_before=inputs,inputs_after=after,build=compiled,executed_console=executable,imported_dlls=libraries,
            cleanup=common.artifact(stage/'cleanup_result.json'),included_lean_raw_assets=0,terrain_and_fog_package_copies=0,
            native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False)
        write_new(stage/'result.json',proof);print(json.dumps({key:proof[key]for key in('status','checks','fixtures','assets','textures','profiles','points')}))
    except BaseException as error:
        write_new(stage/'failure.json',dict(error_type=type(error).__name__,message=str(error)[:8000],
            inputs_unchanged=[common.artifact(PROJECT/name)for name in names]==inputs,package_unchanged=common.artifact(PACKAGE)==original));raise

if __name__=='__main__':main()
