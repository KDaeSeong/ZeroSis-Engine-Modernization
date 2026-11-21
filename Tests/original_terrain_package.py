"""Compile the production C++14 package/SHA headers and run CPU-only byte checks."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import sys

sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[1]
STAGE=PROJECT/'evidence/world_terrain_original/phase1/package_tests'
BUILD=STAGE/'work'
PACKAGE=PROJECT/'Build/OriginalTerrainAssets/02104c582759bf0cefb58f97379699e45300eb2a9c6da6fdd3c65d1440cb84e8/terrain-assets.bin'
PACKAGE_SHA='02104c582759bf0cefb58f97379699e45300eb2a9c6da6fdd3c65d1440cb84e8'
sys.path[0:0]=[str(PROJECT/'tools'),str(PROJECT/'Tests')]
import build_exit_confirm_host as common
import civ5_original_terrain_assets as terrain
import original_terrain_assets as fixtures
from menu_replay_restoration import build_cxx14
from native_build import run
from menu_suite_storage import storage

def write_new(path,value):
    with path.open('x',encoding='utf8') as stream:json.dump(value,stream,indent=2);stream.write('\n')

def package(rows=None,textures=None,lib=None):
    rows=rows or terrain.parse_csv(fixtures.csv_text());textures=textures or [('a.dds',fixtures.dds())]
    lib=fixtures.library() if lib is None else lib
    encoded,_=terrain.encode_rows(rows,{'a.dds':0},['generic_gibraltar_h.dds'])
    blob=bytearray(terrain.MAGIC+struct.pack('<4I',2,len(rows),len(textures),len(lib))+encoded)
    for name,data in textures:
        raw=name.encode('ascii');blob.extend(struct.pack('<II',len(raw),len(data))+hashlib.sha256(data).digest()+raw+data)
    blob.extend(hashlib.sha256(lib).digest()+lib);return bytes(blob)

def create_fixtures():
    cases=[]
    def add(label,data,accepted=False,sha=None):
        name='case_'+str(len(cases)).zfill(3)+'.bin';path=BUILD/name;path.write_bytes(data)
        cases.append(dict(label=label,filename=name,accepted=accepted,bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),
            supplied_sha256=sha if sha is not None else hashlib.sha256(data).hexdigest()))
    base=package();add('valid_minimal',base,True)
    add('wrong_outer_sha',base,sha='0'*64);add('short_outer_sha',base,sha='-')
    for size in (0,8,23,40,100,len(base)-1):add('truncated_'+str(size),base[:size])
    for offset,value,label in [(0,0,'magic'),(8,1,'version'),(12,0,'empty_rows'),(12,65,'row_limit'),
        (16,0,'empty_textures'),(16,257,'texture_limit'),(20,19,'small_library'),(20,32*1024**2+1,'large_library'),
        (24,1,'row_order'),(28,5,'continent'),(32,256,'legacy_id_bound'),(36,0x7fc00000,'nan_scale'),
        (36,0x7f800000,'infinite_scale'),(36,0,'zero_scale'),(36,0xbf800000,'negative_scale'),
        (36,0x41880000,'scale_over16'),(40,2,'projection'),(44,0xffffffff,'null_diffuse'),
        (48,0xfffffffe,'unexpected_missing_height'),(48,0xfffffffd,'reference'),(52,0xfffffffe,'missing_specular')]:
        changed=bytearray(base);struct.pack_into('<I',changed,offset,value);add(label,changed)
    changed=bytearray(base);struct.pack_into('<II',changed,60,0,0x10);add('duplicate_row_identity',changed)
    changed=bytearray(base);changed[24+64+8]^=1;add('texture_digest',changed)
    changed=bytearray(base);changed[-1]^=1;add('library_digest',changed)
    add('trailing_bytes',base+b'X')
    for name in ('../a.dds','.dds','-a.dds',' a.dds','A.dds'):
        add('unsafe_name_'+repr(name),package(textures=[(name,fixtures.dds())]))
    add('duplicate_texture',package(textures=[('a.dds',fixtures.dds()),('a.dds',fixtures.dds())]))
    for offset,value,label in [(4,123,'dds_header'),(8,0,'dds_flags'),(12,0,'dds_height'),(16,4097,'dds_width'),
        (24,1,'dds_depth'),(28,14,'dds_mip_bound'),(76,31,'dds_pixel_format'),(84,0,'dds_codec'),(112,0x200,'dds_caps')]:
        data=bytearray(fixtures.dds());struct.pack_into('<I',data,offset,value)
        add(label,package(textures=[('a.dds',data)]))
    # All four 1x1 mips have matching length but exceed a 4x4 texture's three mip levels.
    data=bytearray(fixtures.dds()+bytes(48));struct.pack_into('<I',data,28,4)
    add('dds_dimension_mip_bound',package(textures=[('a.dds',data)]))
    changed=bytearray(fixtures.library());struct.pack_into('<I',changed,0,19)
    add('library_version',package(lib=changed))
    rows=terrain.parse_csv(fixtures.csv_text());rows[0]['scale']=2
    add('scale_above_one_allowed',package(rows=rows),True)
    extended=[dict(rows[0],row=index,legacy_id=index) for index in range(9)]
    extended[8]['height']='Generic_Gibraltar_H.dds'
    add('declared_missing_distinct_from_null',package(rows=extended),True)
    many=[dict(rows[0],row=index,legacy_id=index,projection=1) for index in range(22)]
    add('expanded_material_bound',package(rows=many))
    text=[str(len(cases))]+[str(int(row['accepted']))+' '+row['supplied_sha256']+' '+row['filename'] for row in cases]
    (BUILD/'cases.txt').write_text('\n'.join(text)+'\n',encoding='ascii')
    return cases

def main():
    assert not BUILD.exists() and not(STAGE/'result.json').exists(),'Inspect existing owned results instead of restarting'
    assert not any(os.environ.get(name) for name in ('CL','_CL_','LINK'))
    STAGE.mkdir(parents=True,exist_ok=True);BUILD.mkdir()
    names=['Source/Presentation/OriginalTerrainSha256.h','Source/Presentation/OriginalTerrainPackage.h',
        'Source/Presentation/OriginalTerrainBinding.h','Tests/original_terrain_package.cpp','Tests/original_terrain_package.py',
        'tools/civ5_original_terrain_assets.py','Tests/original_terrain_assets.py']
    inputs=[common.artifact(PROJECT/name) for name in names];original_package=common.artifact(PACKAGE)
    assert original_package['sha256']==PACKAGE_SHA
    write_new(STAGE/'started.json',dict(inputs=inputs,package=original_package,native_host_sdk_gpu_executed=False))
    # Independent hashlib metadata is compared with every production C++ record/blob.
    verified=terrain.validate_package(PACKAGE,PACKAGE_SHA)
    meta=['41 72 47 '+PACKAGE_SHA]
    for row in verified['rows']:
        bits=struct.unpack('<I',struct.pack('<f',row['scale']))[0]
        meta.append(' '.join(str(value) for value in (row['row'],row['continent'],row['legacy_id'],bits,row['projection'],
            row['diffuse'],row['height'],row['specular'])))
    for row in verified['textures']:
        dds=row['dds'];meta.append(' '.join(str(value) for value in (row['index'],row['offset'],row['bytes'],dds['width'],dds['height'],
            dds['mips'],row['sha256'],row['name'])))
    lib=verified['library'];meta.append(str(lib['offset'])+' '+str(lib['bytes'])+' '+lib['sha256'])
    metadata=BUILD/'python_hashes.txt';metadata.write_text('\n'.join(meta)+'\n',encoding='ascii')
    lengths=(0,1,3,55,56,63,64,65,127,128,129,1024)
    vectors=BUILD/'hash_vectors.txt'
    vectors.write_text(str(len(lengths))+'\n'+'\n'.join(str(size)+' '+hashlib.sha256(bytes((i*37+size)%256 for i in range(size))).hexdigest()
        for size in lengths)+'\n',encoding='ascii')
    cases=create_fixtures();write_new(STAGE/'fixture_cases.json',dict(cases=cases,large_package_copies=0))
    compiled=build_cxx14('original_terrain_package',BUILD,STAGE,PROJECT/'Tests/original_terrain_package.cpp',[PROJECT/'Source/Presentation'])
    imports=run([Path(compiled['compiler']).with_name('dumpbin.exe'),'/dependents',compiled['path']],cwd=BUILD,timeout=30)
    libraries=sorted(set(re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$',imports.stdout.decode('mbcs',errors='replace'),re.M)))
    assert imports.returncode==0 and {name.lower() for name in libraries}=={'kernel32.dll'},libraries
    executable=common.artifact(compiled['path'])
    output=run([compiled['path'],PACKAGE,metadata,vectors,BUILD],cwd=BUILD,timeout=60)
    stdout=output.stdout.decode('ascii');stderr=output.stderr.decode('ascii')
    match=re.fullmatch(r'PASS_ORIGINAL_TERRAIN_PACKAGE checks=(\d+) fixtures=(\d+) real_rows=41 real_textures=72 expanded=47\s*',stdout)
    assert output.returncode==0 and not stderr and match,(output.returncode,stdout,stderr)
    after=[common.artifact(PROJECT/name) for name in names]
    assert after==inputs and common.artifact(PACKAGE)==original_package
    retired=[]
    for path in sorted(BUILD.iterdir()):
        assert path.is_file() and path.suffix in ('.bin','.txt','.exe','.obj','.map','.rsp','.cmd')
        row=common.artifact(path);assert row['links']==1 and not row['file_attributes']&0x401
        row['allocated_bytes']=storage.allocated(path);retired.append(row)
    write_new(STAGE/'cleanup_plan.json',dict(directory=str(BUILD),files=retired,protected_sources=after,protected_package=original_package))
    for row in retired:
        now=common.artifact(row['path']);assert all(now[k]==row[k] for k in ('bytes','sha256','file_identity','mtime_ns','file_attributes','links'))
        Path(row['path']).unlink()
    assert not any(BUILD.iterdir());BUILD.rmdir()
    cleanup=dict(status='PASS_EXACT_OWNED_CPP_CPU_TEST_INTERMEDIATES_REMOVED',files=retired,deleted_files=len(retired),
        released_unique_allocated_bytes=sum(row['allocated_bytes'] for row in retired),large_package_copies=0)
    write_new(STAGE/'cleanup_result.json',cleanup)
    proof=dict(status='PASS_PRODUCTION_CPP14_ORIGINAL_TERRAIN_PACKAGE_SHA_AND_REJECTION_CHECKS',checks=int(match[1]),
        fixtures=int(match[2]),fixed_sha_vectors=3,python_boundary_vectors=len(lengths),real_rows=41,real_textures=72,expanded_materials=47,
        package=original_package,inputs_before=inputs,inputs_after=after,build=compiled,executed_console=executable,
        imported_dlls=libraries,cleanup=common.artifact(STAGE/'cleanup_result.json'),native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False)
    write_new(STAGE/'result.json',proof)
    print(json.dumps({key:proof[key] for key in ('status','checks','fixtures','real_rows','real_textures','expanded_materials')}))

if __name__=='__main__':main()
