"""Minimal immutable original lighting input cache; no native/GPU execution.

Ten cube roles and five terrain LUT roles share nine original byte blobs.
Cube axis binding, LUT selection/origin and sampler calibration are candidates.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct

from civ5_ui_assets import Fpk, require
from civ5_original_fog_assets import artifact, _regular, validate_tga
from civ5_original_water_assets import write_new

MAGIC=b'ZSLIGHT1'
VERSION=1
MAX_PACKAGE_BYTES=2*1024*1024
MAX_ASSET_BYTES=300000
REGIONS=('generic','america','asia','africa','europe')
ROLES={**{i+1:'sunlight_'+s+'_terrain.dds' for i,s in enumerate(REGIONS)},
       **{i+6:'shadowlight_'+s+'_terrain.dds' for i,s in enumerate(REGIONS)},
       **{i+11:'terrain_'+s+'_colorkey.tga' for i,s in enumerate(REGIONS)}}
PACK_RELATIVE='Resource/DX9/TerrainTextures.fpk'
PACK_SHA='8fb5183a2fe92d8add58d7758a231caafb27a2eb87b1958284eaa7d42a49577b'
SUN='769b8b557c825e0b88057a7fdb1a41b8c151251e4d4c9759af2fefdbe296bd10'
LUT0='baf5e23ad8d860096c589c0cccc6179991877fb1af132caf854c154223cdfe5b'
LUT1='6fb58875c1e9d4389c3ab1434ecdb9af6366cc87406390675d9c3604f1ef633f'
SOURCE_SHA={1:SUN,2:SUN,3:SUN,4:'2122e4ef633cf1fe118b79772f0c53da0bb60df30b8e3f8411b2e7a3a8388c2d',5:SUN,
    6:'8854bcddc1a4a58b5f7fb3daafdbd6e5c2c9312edff4eb580ef8cedbccd1d88f',
    7:'4b3ae4dd5dc5a7dda0dea38ae03227e56d52cc89229a9b0b5cf9140f4358437b',
    8:'cb0981ec1062617953506b77f3bd6a6d8b2bf69feccd55af31557b5fb2ec3d21',
    9:'6ec47ce2389f14c6dd80aaf19e0117bfa25424629598515f843cb9007ace5ed1',
    10:'1c15a4c8321d87be7f8bac2094e5aa59ea510c1906cb494998f97d5ac9d722e7',
    11:LUT0,12:LUT0,13:LUT0,14:LUT1,15:LUT1}
_SHA=re.compile(r'[0-9a-f]{64}\Z',re.ASCII)

def validate_cube(data):
    require(128<=len(data)<=MAX_ASSET_BYTES and data[:4]==b'DDS ','Unbounded lighting cube DDS')
    w=struct.unpack_from('<32I',data)
    require(w[1]==124 and w[2]==0x21007 and w[6]==0 and w[19]==32 and w[20]==4 and w[21]==0x31545844 and
        not any(w[22:27]) and w[27]==0x401008 and w[28]==0xfe00,'Unsupported lighting cube DDS header/caps')
    width,height,mips=w[4],w[3],w[7]
    require(0<width<=128 and width==height and width&(width-1)==0 and mips==width.bit_length(),'Lighting cube requires complete square mip chain')
    cursor=128;levels=[]
    for face in range(6):
        for mip in range(mips):
            size=max(1,width>>mip);pitch=((size+3)//4)*8;count=pitch*((size+3)//4)
            require(count<=len(data)-cursor,'Truncated lighting cube face/mip')
            levels.append(dict(face=face,mip=mip,width=size,height=size,offset=cursor,bytes=count,row_pitch=pitch,slice_pitch=count));cursor+=count
    require(cursor==len(data),'Lighting cube extent/trailing bytes differ')
    return dict(format='BC1_UNORM',width=width,height=height,mips=mips,faces=6,face_order=['+X','-X','+Y','-Y','+Z','-Z'],levels=levels,
        srgb_decode=False,cube_axes_retail_binding_verified=False,opaque_caps3_caps4_reserved_hex=data[116:128].hex())

def validate_asset(role,data):
    if role<=10:return dict(cube=validate_cube(data))
    meta=validate_tga(data);return dict(lut=meta)

def candidate_lut32(data):
    validate_tga(data);width,height=struct.unpack_from('<HH',data,12);desc=data[17];result=bytearray(32768*4)
    for i in range(32768):
        x,y=i%width,i//width
        if desc&16:x=width-1-x
        if not desc&32:y=height-1-y
        p=18+(y*width+x)*4;b,g,r,a=data[p:p+4];result[i*4:i*4+4]=bytes((r,g,b,a))
    return bytes(result)

def encode_package(assets):
    require(len(assets)==15,'Lighting requires15 canonical roles');descriptors=bytearray();blobs=[];indices={}
    for role in range(1,16):
        data=assets[role];validate_asset(role,data);sha=hashlib.sha256(data).digest();name=ROLES[role].encode('ascii')
        if sha not in indices:indices[sha]=len(blobs);blobs.append((sha,data))
        else:require(blobs[indices[sha]][1]==data,'Unexpected lighting SHA collision')
        descriptors.extend(struct.pack('<III',role,len(name),indices[sha])+name)
    raw=bytearray(MAGIC+struct.pack('<III',VERSION,15,len(blobs))+descriptors)
    for sha,data in blobs:raw.extend(struct.pack('<I',len(data))+sha+data)
    require(len(raw)<=MAX_PACKAGE_BYTES,'Lighting package exceeds bound');return bytes(raw)

def validate_package_bytes(raw,expected_sha256=None):
    require(20<=len(raw)<=MAX_PACKAGE_BYTES,'Unbounded lighting package');sha=hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None:require(_SHA.fullmatch(expected_sha256) and sha==expected_sha256,'Lighting outer SHA differs')
    cursor=0
    def take(count):
        nonlocal cursor
        require(0<=count<=len(raw)-cursor,'Truncated lighting package');data=raw[cursor:cursor+count];cursor+=count;return data
    require(take(8)==MAGIC,'Unknown lighting magic');version,count,blob_count=struct.unpack('<III',take(12))
    require(version==VERSION and count==15 and 0<blob_count<=15,'Unknown lighting format/count')
    roles=[];seen=set()
    for role in range(1,16):
        index,n,blob=struct.unpack('<III',take(12));require(index==role and 0<n<=64 and blob<blob_count,'Invalid ordered lighting descriptor')
        name=take(n).decode('ascii');require(name==ROLES[role],'Noncanonical lighting name')
        if blob not in seen:require(blob==len(seen),'Lighting blobs not in first-reference order');seen.add(blob)
        roles.append(dict(role=role,name=name,blob_index=blob))
    require(len(seen)==blob_count,'Unreferenced lighting blob');blobs=[];hashes=set()
    for index in range(blob_count):
        size=struct.unpack('<I',take(4))[0];expected=take(32);require(0<size<=MAX_ASSET_BYTES,'Unbounded lighting blob')
        offset=cursor;data=take(size);require(hashlib.sha256(data).digest()==expected and expected not in hashes,'Lighting blob SHA/uniqueness differs')
        hashes.add(expected);blobs.append(dict(index=index,offset=offset,bytes=size,sha256=expected.hex()))
    require(cursor==len(raw),'Lighting trailing bytes');assets=[]
    for descriptor in roles:
        blob=blobs[descriptor['blob_index']];meta=validate_asset(descriptor['role'],raw[blob['offset']:blob['offset']+blob['bytes']])
        if 'cube'in meta:
            for level in meta['cube']['levels']:level['package_offset']=blob['offset']+level['offset']
        assets.append(dict(descriptor,offset=blob['offset'],bytes=blob['bytes'],sha256=blob['sha256'],**meta))
    return dict(version=VERSION,asset_count=15,blob_count=blob_count,assets=assets,blobs=blobs,bytes=len(raw),sha256=sha)

def validate_package(path,expected_sha256=None):
    path=Path(path).absolute();before=_regular(path);require(before.st_size<=MAX_PACKAGE_BYTES,'Unbounded lighting package file')
    result=validate_package_bytes(path.read_bytes(),expected_sha256);after=path.stat()
    require((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)==(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns),'Lighting input changed');return result

def source_assets(game_root):
    game=Path(game_root).resolve(strict=True);packpath=game/PACK_RELATIVE;before=artifact(packpath);require(before['sha256']==PACK_SHA,'Retail terrain texture archive SHA differs')
    pack=Fpk(packpath);assets={};sources=[]
    for role in range(1,16):
        if role<=10:data,source=pack.read(ROLES[role])
        else:
            relative='Assets/colorkeys/Terrain_'+REGIONS[role-11].title()+'_ColorKey.tga';path=game/relative;source=artifact(path);data=path.read_bytes()
            require(artifact(path)==source,'Retail terrain LUT changed while reading');source['relative_path']=relative
        require(hashlib.sha256(data).hexdigest()==SOURCE_SHA[role],'Retail lighting raw SHA differs');validate_asset(role,data)
        sources.append(dict(role=role,name=ROLES[role],source=source));assets[role]=data
    require(artifact(packpath)==before,'Retail archive changed while reading');return assets,before,sources

def prepare(game_root,output_root):
    project=Path(__file__).absolute().parents[1];output=Path(output_root).absolute();game=Path(game_root).resolve(strict=True)
    require('..'not in output.parts and output.resolve()==output and output.is_relative_to(project/'Build/OriginalLightingAssets') and not output.is_relative_to(game),'Lighting output outside private cache')
    for part in(output,*output.parents):
        if part.exists():require(not getattr(part.lstat(),'st_file_attributes',0)&0x400,'Reparse lighting output')
    assets,source,sources=source_assets(game);raw=encode_package(assets);sha=hashlib.sha256(raw).hexdigest();directory=output/sha
    path=directory/'lighting-assets.bin';manifest_path=directory/'lighting-assets.manifest.json'
    if directory.exists():
        require(path.exists() and manifest_path.exists(),'Incomplete retained lighting package;inspect before retry');require(_regular(manifest_path).st_size<=512*1024,'Unbounded lighting manifest')
        manifest=json.loads(manifest_path.read_text('utf8'));require(manifest.get('sha256')==sha and manifest.get('source')==source and manifest.get('sources')==sources,'Retained lighting provenance differs')
        return dict(package=artifact(path),manifest=artifact(manifest_path),verified=validate_package(path,sha),reused=True)
    directory.mkdir(parents=True)
    with path.open('xb')as stream:stream.write(raw)
    verified=validate_package(path,sha)
    write_new(manifest_path,dict(schema='zerosis.original_lighting_assets.v1',sha256=sha,bytes=len(raw),source=source,sources=sources,package=verified,
        raw_unique_bytes=sum(b['bytes']for b in verified['blobs']),duplicate_raw_bytes_avoided=sum(len(b)for b in assets.values())-sum(b['bytes']for b in verified['blobs']),
        runtime_upload_binding_verified=False,lut_candidate='standard TGA origin;first32768 pixels;R/x-fastest32^3;UNORM8 without linearisation',
        native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False))
    return dict(package=artifact(path),manifest=artifact(manifest_path),verified=verified,reused=False)

def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=('prepare','verify'));p.add_argument('--game-root');p.add_argument('--output-root');p.add_argument('--package');p.add_argument('--sha256');a=p.parse_args()
    if a.command=='prepare':require(a.game_root and a.output_root,'Missing lighting prepare paths');result=prepare(a.game_root,a.output_root)
    else:require(a.package and a.sha256,'Missing lighting verify paths');result=validate_package(a.package,a.sha256)
    print(json.dumps({k:v for k,v in result.items()if k in('package','manifest','reused','bytes','sha256','asset_count','blob_count')}))

if __name__=='__main__':main()
