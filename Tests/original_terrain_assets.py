"""Pure Python byte/format/component checks for ZSTERR02. No native execution."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[1]
STAGE=PROJECT/'evidence/world_terrain_original/phase1/assets'
sys.path.insert(0,str(PROJECT/'tools'))
import civ5_original_terrain_assets as terrain
import build_exit_confirm_host as common
from menu_suite_storage import storage

checks=0
def check(value):
    global checks
    checks+=1
    if not value:raise AssertionError('Original terrain asset regression')

def reject(action):
    global checks
    checks+=1
    try:action()
    except (ValueError,UnicodeError,KeyError,struct.error):return
    raise AssertionError('Malformed original terrain data was accepted')

def dds(codec=b'DXT5',width=4,height=4):
    words=[0]*32;words[0]=int.from_bytes(b'DDS ','little');words[1]=124;words[2]=0x1007
    words[3]=height;words[4]=width;words[7]=1;words[19]=32;words[20]=4;words[21]=int.from_bytes(codec,'little')
    block=8 if codec==b'DXT1' else 16
    return struct.pack('<32I',*words)+bytes(((width+3)//4)*((height+3)//4)*block)

def library():
    offsets=list(range(0,256,2))+list(range(0,768,2))
    b=bytes([128,1]*128+[128,255]*128+[128,255]*128)
    c=struct.pack('<256H',*([128,32768]*128))
    record=bytearray(0x56c)
    for at in (0x94,0x3c0):struct.pack_into('<II',record,at,10,10)
    struct.pack_into('<I',record,0x3c8,1);struct.pack_into('<4I',record,0x3d4,0,128,256,384)
    for at,text in zip((0x3ea,0x42a,0x46a,0x4aa,0x4ea,0x52a),
        (b'Fixture.csv',b'Fixture.csv',b'Fixture_H.dds',b'Fixture_T1.dds',b'Fixture_H_BLEND.dds',b'Fixture_T_BLEND.dds')):
        record[at:at+len(text)]=text
    return (struct.pack('<II',20,len(offsets))+struct.pack('<512I',*offsets)+
        struct.pack('<I',len(b))+b+struct.pack('<I',len(c)//2)+c+struct.pack('<I',1)+record)

def csv_text(dominance='0'):
    return ','.join(terrain.FIELDS)+'\n0,A.dds,A.dds,NULL,'+dominance+',0.014,0,10\n1,A.dds,A.dds,NULL,0,0.1,0,20\n'

def package(rows=None,textures=None,lib=None):
    rows=rows or terrain.parse_csv(csv_text());textures=textures or [('a.dds',dds())];lib=library() if lib is None else lib
    encoded,_=terrain.encode_rows(rows,{name:index for index,(name,_data) in enumerate(textures)},['generic_gibraltar_h.dds'])
    blob=bytearray(terrain.MAGIC+struct.pack('<4I',2,len(rows),len(textures),len(lib))+encoded)
    for name,data in textures:
        raw=name.encode('ascii');blob.extend(struct.pack('<II',len(raw),len(data))+hashlib.sha256(data).digest()+raw+data)
    blob.extend(hashlib.sha256(lib).digest()+lib);return bytes(blob)

def unit():
    rows=terrain.parse_csv(csv_text());check([row['row'] for row in rows]==[0,1]);check(rows[0]['legacy_id']==0x10)
    a=terrain.encode_rows(rows,{'a.dds':0})[0]
    b=terrain.encode_rows(terrain.parse_csv(csv_text('1')),{'a.dds':0})[0]
    check(a==b);check(all('dominance' not in key.lower() for row in rows for key in row))
    for change in [lambda t:t.replace('Texture Scale','Other Scale'),lambda t:t.replace('0.014','nan'),
                   lambda t:t.replace('0.014','-1'),lambda t:t.replace('0.014','inf'),lambda t:t.replace('0.014','5e-324'),
                   lambda t:t.replace('0.014,0','0.014,2'),lambda t:t.replace('A.dds','../A.dds'),
                   lambda t:t.replace('A.dds','C:/A.dds'),lambda t:t.replace(',10\n',',GZ\n'),
                   lambda t:t.replace('\n1,A.dds','\n0,A.dds').replace(',20\n',',10\n'),
                   lambda t:t.replace('0,A.dds','5,A.dds')]:reject(lambda change=change:terrain.parse_csv(change(csv_text())))
    for codec,expected in [(b'DXT1','BC1'),(b'DXT3','BC2'),(b'DXT5','BC3')]:check(terrain.validate_dds(dds(codec))['format']==expected)
    reject(lambda:terrain.validate_dds(dds()[:-1]));reject(lambda:terrain.validate_dds(dds()+b'X'))
    reject(lambda:terrain.validate_dds(dds(b'DX10')));reject(lambda:terrain.validate_dds(dds(width=4097)))
    for offset,value in [(4,123),(76,31),(112,0x200),(24,1),(28,20)]:
        bad=bytearray(dds());struct.pack_into('<I',bad,offset,value);reject(lambda bad=bad:terrain.validate_dds(bad))
    lib=library();check(terrain.validate_library(lib,2)['all_rle_rows_validated'])
    reject(lambda:terrain.validate_library(lib,1));reject(lambda:terrain.validate_library(lib[:-1],2))
    bad=bytearray(lib);struct.pack_into('<I',bad,0,19);reject(lambda:terrain.validate_library(bad,2))
    bad=bytearray(lib);struct.pack_into('<I',bad,4,0xffffffff);reject(lambda:terrain.validate_library(bad,2))
    bad=bytearray(lib);struct.pack_into('<I',bad,8,0xffffffff);reject(lambda:terrain.validate_library(bad,2))
    temp=STAGE/'component-fixture.bin';check(not temp.exists());blob=package()
    temp.write_bytes(blob)
    proof=terrain.validate_package(temp,hashlib.sha256(blob).hexdigest())
    check(proof['row_count']==2 and proof['expanded_material_count']==2 and proof['texture_count']==1)
    check(proof['rows'][0]['specular']==terrain.NULL_TEXTURE and proof['textures'][0]['dds']['format']=='BC3')
    reject(lambda:terrain.validate_package(temp,'0'*64))
    for cut in (0,8,23,40,100,len(blob)-1):
        temp.write_bytes(blob[:cut]);reject(lambda:terrain.validate_package(temp))
    for offset,value in [(8,1),(12,65),(16,257),(20,terrain.MAX_LIBRARY_BYTES+1),(24,1),(24+16,2),
                         (24+12,0x7fc00000),(24+20,terrain.MISSING_TEXTURE),(24+24,0xfffffffd),(24+28,terrain.MISSING_TEXTURE)]:
        bad=bytearray(blob);struct.pack_into('<I',bad,offset,value);temp.write_bytes(bad);reject(lambda:terrain.validate_package(temp))
    temp.write_bytes(blob+b'X');reject(lambda:terrain.validate_package(temp))
    bad=bytearray(blob);bad[24+len(a)+8]^=1;temp.write_bytes(bad);reject(lambda:terrain.validate_package(temp))
    bad=bytearray(blob);bad[-1]^=1;temp.write_bytes(bad);reject(lambda:terrain.validate_package(temp))
    temp.write_bytes(package(textures=[('a.dds',dds()),('a.dds',dds())]));reject(lambda:terrain.validate_package(temp))
    bad=bytearray(blob);struct.pack_into('<II',bad,24+32+4,0,0x10);temp.write_bytes(bad);reject(lambda:terrain.validate_package(temp))
    extended=[dict(rows[0],row=index,legacy_id=index) for index in range(9)]
    extended[8]['height']='Generic_Gibraltar_H.dds';temp.write_bytes(package(rows=extended))
    check(terrain.validate_package(temp)['rows'][8]['height']==terrain.MISSING_TEXTURE)
    temp.write_bytes(blob);row=common.artifact(temp);row['allocated_bytes']=storage.allocated(temp)
    assert row['links']==1 and not row['file_attributes']&0x401
    temp.unlink()
    return dict(status='PASS_ORIGINAL_TERRAIN_ASSET_COMPONENT_CHECKS',checks=checks,
        inputs=[common.artifact(PROJECT/'tools/civ5_original_terrain_assets.py'),common.artifact(__file__)],
        cleanup=dict(deleted_files=[row],released_unique_allocated_bytes=row['allocated_bytes']),
        native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--package',type=Path);parser.add_argument('--sha256')
    parser.add_argument('--result-name',default='unit_result.json');args=parser.parse_args()
    STAGE.mkdir(parents=True,exist_ok=True)
    if args.package:
        result=terrain.validate_package(args.package,args.sha256)
        proof=dict(status='PASS_FULL_ORIGINAL_TERRAIN_PACKAGE_BYTES',package=common.artifact(args.package),
            row_count=result['row_count'],expanded_material_count=result['expanded_material_count'],texture_count=result['texture_count'],
            library=result['library'],dds_formats=sorted({row['dds']['format'] for row in result['textures']}),
            native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False)
        output=STAGE/'package_validation.json'
    else:
        check(re.fullmatch(r'[A-Za-z0-9_]+\.json',args.result_name) is not None)
        proof=unit();output=STAGE/args.result_name
    with output.open('x',encoding='utf8') as stream:json.dump(proof,stream,indent=2);stream.write('\n')
    print(json.dumps({key:proof[key] for key in ('status','checks','row_count','expanded_material_count','texture_count') if key in proof}))

if __name__=='__main__':main()
