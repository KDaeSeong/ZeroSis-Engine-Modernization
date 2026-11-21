"""Compile production LEAN reader and compare every mip/texel to Python."""
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
STAGE=PROJECT/'evidence/world_terrain_original/phase4/package_tests'
PACKAGE_SHA='69c6780dbeb5f8605d8231cef944d0ec9392109b6ccc81a9d3b76ae83cfd0ef7'
PACKAGE=PROJECT/'Build/OriginalWaterLeanAssets'/PACKAGE_SHA/'water-lean-assets.bin'
sys.path[0:0]=[str(PROJECT/'tools'),str(PROJECT/'Tests')]
import build_exit_confirm_host as common
import civ5_original_water_lean_assets as lean
import original_water_lean_assets as fixtures
from menu_replay_restoration import build_cxx14
from menu_suite_storage import storage
from native_build import run

def write_new(path,value):
    with path.open('x',encoding='utf8')as stream:json.dump(value,stream,indent=2);stream.write('\n')

def references(build):
    parsed=lean.validate_package(PACKAGE,PACKAGE_SHA);raw=PACKAGE.read_bytes();asset=parsed['assets'][0];t=asset['texture'];start=asset['offset']
    scale=t['output_scale'];scale_bits=struct.unpack_from('<I',raw,start+4)[0];padding=list(raw[start+33:start+36])
    rows=[str(len(raw))+' '+PACKAGE_SHA,' '.join(str(v)for v in(asset['offset'],asset['bytes'],t['width'],t['height'],t['mips'],scale_bits,t['flag_at32'],*padding,asset['name'],asset['sha256']))]
    proof=[]
    for mip in range(t['mips']):
        payload=[];levels=[]
        for plane in t['planes']:
            level=plane['levels'][mip];offset=level['package_offset'];data=raw[offset:offset+level['bytes']];sha=hashlib.sha256(data).hexdigest();payload.append(data)
            rows.append(' '.join(str(v)for v in(offset,level['bytes'],level['row_pitch'],level['slice_pitch'],level['width'],level['height'],sha)))
            levels.append(dict(offset=offset,bytes=len(data),sha256=sha,channels=plane['channels']))
        hashes=[hashlib.sha256()for _ in range(4)];square=scale*scale;texels=0
        for (r,g,b,a),(cross,)in zip(struct.iter_unpack('<4H',payload[0]),struct.iter_unpack('<H',payload[1])):
            rgba=(r/65535,g/65535,b/65535,a/65535);c=cross/65535
            hashes[0].update(struct.pack('<4d',*rgba));hashes[1].update(struct.pack('<d',c))
            # Independent scalar WaterPS2 channel/sign reference. Scale is an
            # explicit test parameter, not an automatic header-to-runtime link.
            values=((2*rgba[0]-1)/scale,(2*rgba[1]-1)/scale,rgba[2]/square,rgba[3]/square,(2*c-1)/square)
            hashes[2].update(struct.pack('<5d',*values));hashes[3].update(struct.pack('<5d',-values[0],values[1],values[2],values[3],-values[4]));texels+=1
        sha=[h.hexdigest()for h in hashes];rows.append(' '.join(sha));proof.append(dict(mip=mip,texels=texels,raw_planes=levels,
            normalised_rgba64_sha256=sha[0],normalised_cross64_sha256=sha[1],moments64_sha256=sha[2],mirror_moments64_sha256=sha[3],explicit_shader_scale=scale))
    path=build/'python_references.txt';path.write_text('\n'.join(rows)+'\n',encoding='ascii');return path,proof

def create_fixtures(build):
    cases=[dict(label='valid_base',data=fixtures.package(),accepted=True)]
    for label,data,sha in fixtures.rejection_cases():cases.append(dict(label='reject_'+str(len(cases)),description=label,data=data,supplied_sha256=sha,accepted=False))
    for width,height,padding in((1,1,b'\0\0\0'),(5,3,b'\xff\xcc\x11'),(8,1,b'\xcc\xcc\xcc')):
        cases.append(dict(label='valid_'+str(width)+'x'+str(height),data=fixtures.package(fixtures.texture(width,height,padding=padding)),accepted=True))
    table=[str(len(cases))];records=[]
    for index,case in enumerate(cases):
        data=case.pop('data');name='case_'+str(index).zfill(3)+'.bin';(build/name).write_bytes(data);sha=hashlib.sha256(data).hexdigest()
        row=dict(case,filename=name,bytes=len(data),sha256=sha);row['supplied_sha256']=row.get('supplied_sha256')or sha;records.append(row)
        table.append(str(int(row['accepted']))+' '+row['supplied_sha256']+' '+name+' '+row['label'])
    (build/'cases.txt').write_text('\n'.join(table)+'\n',encoding='ascii');return records

def cleanup(build,stage,protected):
    assert build.resolve()==build and build.is_relative_to(STAGE)and not build.lstat().st_file_attributes&0x400;files=[]
    for path in sorted(build.iterdir()):
        assert path.is_file()and path.suffix in('.bin','.txt','.exe','.obj','.map','.rsp','.cmd')
        row=common.artifact(path);assert row['links']==1 and not row['file_attributes']&0x401;row['allocated_bytes']=storage.allocated(path);files.append(row)
    write_new(stage/'cleanup_plan.json',dict(directory=str(build),files=files,protected=protected))
    for row in files:
        now=common.artifact(row['path']);assert all(now[k]==row[k]for k in('bytes','sha256','file_identity','mtime_ns','file_attributes','links'));Path(row['path']).unlink()
    assert not any(build.iterdir());build.rmdir();write_new(stage/'cleanup_result.json',dict(status='PASS_EXACT_OWNED_WATER_LEAN_CPP_INTERMEDIATES_REMOVED',
        files=files,deleted_files=len(files),released_unique_allocated_bytes=sum(row['allocated_bytes']for row in files),raw_original_copies=0))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--attempt',type=int,default=1);args=parser.parse_args();assert 1<=args.attempt<=5
    stage=STAGE/('attempt'+str(args.attempt));build=stage/'work';assert not stage.exists(),'Inspect prior LEAN attempt first'
    assert not any(os.environ.get(name)for name in('CL','_CL_','LINK'));build.mkdir(parents=True)
    names=['Source/Presentation/OriginalWaterLeanPackage.h','Source/Presentation/OriginalTerrainSha256.h',
        'tools/civ5_original_water_lean_assets.py','tools/civ5_original_water_assets.py','tools/civ5_original_fog_assets.py','tools/civ5_ui_assets.py',
        'Tests/original_water_lean_assets.py','Tests/original_water_lean_package.cpp','Tests/original_water_lean_package.py']
    inputs=[common.artifact(PROJECT/name)for name in names];original=common.artifact(PACKAGE);assert original['sha256']==PACKAGE_SHA
    write_new(stage/'started.json',dict(inputs=inputs,package=original,native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False))
    try:
        reference,reference_meta=references(build);cases=create_fixtures(build);write_new(stage/'reference_summary.json',dict(mips=reference_meta,source_texels=sum(m['texels']for m in reference_meta)))
        write_new(stage/'fixture_cases.json',dict(cases=cases,raw_original_copies=0))
        compiled=build_cxx14('original_water_lean_package',build,stage,PROJECT/'Tests/original_water_lean_package.cpp',[PROJECT/'Source/Presentation'])
        imports=run([Path(compiled['compiler']).with_name('dumpbin.exe'),'/dependents',compiled['path']],cwd=build,timeout=30)
        libraries=sorted(set(re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$',imports.stdout.decode('mbcs',errors='replace'),re.M)))
        assert imports.returncode==0 and{name.lower()for name in libraries}=={'kernel32.dll'},libraries
        executable=common.artifact(compiled['path']);output=run([compiled['path'],PACKAGE,reference,build],cwd=build,timeout=60)
        stdout=output.stdout.decode('ascii');stderr=output.stderr.decode('ascii');match=re.fullmatch(
            r'PASS_ORIGINAL_WATER_LEAN_PACKAGE checks=(\d+) fixtures=(\d+) assets=1 mips=10 planes=2 source_texels=349525 rejected_api=(\d+)\s*',stdout)
        assert output.returncode==0 and not stderr and match,(output.returncode,stdout,stderr)
        after=[common.artifact(PROJECT/name)for name in names];assert after==inputs and common.artifact(PACKAGE)==original
        cleanup(build,stage,after+[original]);proof=dict(status='PASS_PRODUCTION_CPP14_WATER_LEAN_FULL_MIPS_UNORM_SIGN_SCALE_DECODING',
            checks=int(match[1]),fixtures=int(match[2]),api_rejections=int(match[3]),assets=1,mips=10,planes=2,source_texels=349525,normalised_words=1747625,
            mip_references=reference_meta,source_inputs=inputs,source_inputs_after=after,package=original,build=compiled,executed_console=executable,
            imported_dlls=libraries,cleanup=common.artifact(stage/'cleanup_result.json'),duplicated_water_dds=0,excluded_river_lean_bytes=437012,
            scale_contract='default DecodeMoments S1 yields unscaled signed moments;Optics MixLayers applies S once;header-to-runtime binding candidate',
            native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False)
        write_new(stage/'result.json',proof);print(json.dumps({k:proof[k]for k in('status','checks','fixtures','api_rejections','source_texels','normalised_words')}))
    except BaseException as error:
        write_new(stage/'failure.json',dict(error_type=type(error).__name__,message=str(error)[:8000],
            inputs_unchanged=[common.artifact(PROJECT/name)for name in names]==inputs,package_unchanged=common.artifact(PACKAGE)==original));raise

if __name__=='__main__':main()
