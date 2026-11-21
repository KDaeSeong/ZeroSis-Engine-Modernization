"""SHA-sealed retail fog inputs; file IO only, with no native/GPU/game loading.

ZSFOG001 retains the raw DDS, TGA, CSV and settings XML once. The 32-cube
interpretation of the FOW TGA is an explicit asset-backed candidate, not proof
of the retail loader's coordinate or sampler conventions.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import sys

from civ5_ui_assets import Fpk, require

MAGIC=b'ZSFOG001'
VERSION=1
MAX_PACKAGE_BYTES=16*1024*1024
MAX_ASSET_BYTES=5*1024*1024
ROLES={1:'fogcloudtile_dif_01.dds',2:'fogcloudtile_dif_02.dds',3:'fogcloudtile_dif_03.dds',
       4:'flowfield.dds',5:'fx_fog_dif.dds',6:'fogramp.dds',7:'terrainfow_generic_colorkey.tga',
       8:'fogcolor.csv',9:'fluidfowsettings.xml'}
SOURCE_PACKS={
    'Resource/DX9/EffectTextures.fpk':'db76b3df7d1c3c94369afffbc81a9de7edcd7e581e223643094b0181a880e7d8',
    'Resource/DX9/MiscTextures.fpk':'01fdbb60a8098c5e12f1ecf4d53f5ff2b064a7fddd002e06ee53c298f9a60183',
    'Resource/Common/MiscData.fpk':'d19e1a29c456f0a16c31bb4460c281691ffc96d66cb7733bca1752fca59817ce',
    'Resource/Common/EffectData.fpk':'c6164bbdfe7047d064e2e2aaa8caadde41d5ea1f3310e07ce93f8102ffadcd75'}
SOURCE_SHA={
    1:'4d337bbff22ace327d96c896c622225a48aef24f200ce9cadb322c95c5adb939',
    2:'d7fbc347ee7c3c2be139358e3d804ecb40a020b37f7ebb4d1548c86cc167bff0',
    3:'1de17c6a39a54506e008bf4326c74216878433c1121b5d75ae4fe6f143915ec1',
    4:'d91bdac326ff1f891b758b24d9e91ae74ff336863e736f9193785f6c3b1c5514',
    5:'1bbc6c09b2f61033c0f25d11f99055aca055649a0c9c3e7c7bfa0b9d45a9d3e3',
    6:'948e51cf9d409918fc42006234e117374c84df8a31dcce19a9781af225bb9d3d',
    7:'fc9b869406264f62f1d228dff8bf94d77f7ae6937d1b04dd7931ab9ccf5f72e8',
    8:'efc94e89ed0a4263c4a5477bf26e1720b03a9aee2a39b9c093e826ba2c3aa1f8',
    9:'cc31bded506a206663fcc752401e5c80a1df85102e718a3258aa89814f0c5e0b'}
SOURCE_RELATIVE={**{i:'Resource/DX9/EffectTextures.fpk' for i in range(1,6)},
    6:'Resource/DX9/MiscTextures.fpk',7:'Assets/colorkeys/TerrainFOW_Generic_ColorKey.tga',
    8:'Resource/Common/MiscData.fpk',9:'Resource/Common/EffectData.fpk'}
_SHA=re.compile(r'[0-9a-f]{64}\Z',re.ASCII)

def digest(path):
    result=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):result.update(chunk)
    return result.hexdigest()

def _regular(path):
    path=Path(path).absolute();require('..' not in path.parts,'Noncanonical fog path')
    for part in (path,*path.parents):
        row=part.lstat()
        require(not stat.S_ISLNK(row.st_mode) and not getattr(row,'st_file_attributes',0)&0x400,'Reparse fog path')
    row=path.stat();require(stat.S_ISREG(row.st_mode),'Fog input is not a regular file');return row

def artifact(path):
    path=Path(path).absolute();before=_regular(path)
    result=dict(path=str(path),bytes=before.st_size,sha256=digest(path),file_identity=[before.st_dev,before.st_ino],
                mtime_ns=before.st_mtime_ns,file_attributes=getattr(before,'st_file_attributes',0),links=before.st_nlink)
    after=path.stat()
    require((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)==
            (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns),'Fog input changed while hashing')
    return result

def validate_dds(data,name='DDS'):
    require(128<=len(data)<=MAX_ASSET_BYTES and data[:4]==b'DDS ',name+': invalid DDS header/size')
    w=struct.unpack_from('<32I',data)
    require(w[1]==124 and w[19]==32 and w[2]&0x1007==0x1007 and w[28]==0 and w[6]==0,
            name+': unsupported DDS shape')
    width,height=w[4],w[3];mips=max(1,w[7]);require(0<width<=2048 and 0<height<=2048 and
        mips<=max(width,height).bit_length(),name+': unbounded DDS dimensions/mips')
    if w[20]==4 and w[21] in (int.from_bytes(b'DXT1','little'),int.from_bytes(b'DXT5','little')):
        codec,block=('BC1',8) if w[21]==int.from_bytes(b'DXT1','little') else ('BC3',16)
    else:
        require(list(w[20:27])==[0x41,0,32,0xff0000,0xff00,0xff,0xff000000],name+': unsupported DDS codec/masks')
        codec,block='BGRA8',0
    levels=[];offset=128
    for level in range(mips):
        x,y=max(1,width>>level),max(1,height>>level)
        pitch=((x+3)//4)*block if block else x*4
        count=pitch*((y+3)//4) if block else pitch*y
        levels.append(dict(level=level,width=x,height=y,offset=offset,bytes=count,row_pitch=pitch));offset+=count
    require(offset==len(data),name+': DDS full mip extent differs')
    return dict(format=codec,width=width,height=height,mips=mips,levels=levels,raw_channels='BGRA' if not block else 'RGBA decoded from BC blocks')

def validate_tga(data):
    require(18<=len(data)<=300000,'Unbounded FOW TGA')
    ident,cmap,image,first,clen,cbits,x,y,width,height,bits,desc=struct.unpack_from('<BBBHHBHHHHBB',data)
    require(ident==cmap==first==clen==cbits==x==y==0 and image==2 and bits==32 and desc in (8,24,40,56),
            'Unsupported FOW TGA encoding/origin')
    require(0<width<=4096 and 0<height<=2048 and 32768<=width*height<=65536,'Unbounded FOW TGA dimensions')
    end=18+width*height*4
    require(len(data)==end or (len(data)==end+26 and data[end:end+8]==bytes(8) and
        data[end+8:]==b'TRUEVISION-XFILE.\0'),'FOW TGA extent/footer differs')
    return dict(width=width,height=height,pixel_offset=18,format='BGRA8',origin_top=bool(desc&32),origin_right=bool(desc&16),
                candidate_lut_edge=32,candidate_lut_order='top-left logical row-major first 32768 pixels; R/x fastest, G/y, B/z',
                retail_loader_equivalence_verified=False)

def parse_fog_colour(data):
    require(0<len(data)<=128,'Unbounded fog colour CSV')
    match=re.fullmatch(rb'[ \t\r\n]*(\d{1,3})[ \t\r\n]*,[ \t\r\n]*(\d{1,3})[ \t\r\n]*,[ \t\r\n]*(\d{1,3})[ \t\r\n]*',data)
    require(match is not None,'Invalid fog colour CSV')
    colour=[int(value) for value in match.groups()];require(all(value<=255 for value in colour),'Fog colour exceeds byte range')
    return colour

def validate_asset(role,data):
    require(role in ROLES and 0<len(data)<=MAX_ASSET_BYTES,'Invalid fog asset role/size')
    if role<=6:
        meta=validate_dds(data,ROLES[role]);expected={1:'BC3',2:'BC1',3:'BC3',4:'BGRA8',5:'BC3',6:'BGRA8'}[role]
        require(meta['format']==expected,'Fog role DDS codec differs');return dict(texture=meta)
    if role==7:return dict(tga=validate_tga(data))
    if role==8:return dict(fog_colour_bytes=parse_fog_colour(data))
    require(len(data)<=4096 and data.startswith(b'<?xml') and b'<FluidFOWSettings>' in data and b'</FluidFOWSettings>' in data,
            'Invalid bounded FluidFOW settings');return dict(text_encoding='utf-8',used_as_raw_reference=True)

def encode_package(assets):
    require(len(assets)==len(ROLES),'Fog package requires all nine roles')
    output=bytearray(MAGIC+struct.pack('<II',VERSION,len(assets)))
    for role,(name,data) in enumerate(assets,1):
        require(name==ROLES[role],'Noncanonical fog role/name');validate_asset(role,data)
        raw=name.encode('ascii');output.extend(struct.pack('<III',role,len(raw),len(data))+hashlib.sha256(data).digest()+raw+data)
    require(len(output)<=MAX_PACKAGE_BYTES,'Fog package exceeds size bound');return bytes(output)

def validate_package_bytes(raw,expected_sha256=None):
    require(16<=len(raw)<=MAX_PACKAGE_BYTES,'Unbounded fog package')
    sha=hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None:require(_SHA.fullmatch(expected_sha256) and sha==expected_sha256,'Fog package SHA differs')
    cursor=0
    def take(count):
        nonlocal cursor
        require(0<=count<=len(raw)-cursor,'Truncated fog package');value=raw[cursor:cursor+count];cursor+=count;return value
    require(take(8)==MAGIC and struct.unpack('<II',take(8))==(VERSION,len(ROLES)),'Unknown fog package format/count')
    result=[]
    for index in range(1,len(ROLES)+1):
        role,n,count=struct.unpack('<III',take(12));sha_raw=take(32)
        require(role==index and 0<n<=64 and 0<count<=MAX_ASSET_BYTES,'Invalid ordered fog record bounds')
        name=take(n).decode('ascii');require(name==ROLES[index],'Noncanonical fog record name')
        offset=cursor;data=take(count);require(hashlib.sha256(data).digest()==sha_raw,'Fog asset SHA differs')
        meta=validate_asset(role,data)
        if 'texture' in meta:
            for level in meta['texture']['levels']:level['package_offset']=offset+level['offset']
        result.append(dict(role=role,name=name,offset=offset,bytes=count,sha256=sha_raw.hex(),**meta))
    require(cursor==len(raw),'Fog package trailing bytes')
    return dict(version=VERSION,asset_count=len(result),assets=result,bytes=len(raw),sha256=sha,
                fog_colour_bytes=result[7]['fog_colour_bytes'])

def validate_package(path,expected_sha256=None):
    path=Path(path).absolute();before=_regular(path);require(before.st_size<=MAX_PACKAGE_BYTES,'Unbounded fog package file')
    raw=path.read_bytes();result=validate_package_bytes(raw,expected_sha256);after=path.stat()
    require((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)==
            (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns),'Fog package changed during validation')
    return result

def source_assets(game):
    game=Path(game).resolve(strict=True);inputs={}
    for relative,sha in SOURCE_PACKS.items():
        row=artifact(game/relative);require(row['sha256']==sha,'Retail fog archive SHA differs: '+relative);inputs[relative]=row
    loose=SOURCE_RELATIVE[7];inputs[loose]=artifact(game/loose)
    require(inputs[loose]['sha256']==SOURCE_SHA[7],'Retail FOW key SHA differs')
    packs={relative:Fpk(game/relative) for relative in SOURCE_PACKS};assets=[];metadata=[]
    for role,name in ROLES.items():
        relative=SOURCE_RELATIVE[role]
        if role==7:data=(game/relative).read_bytes();member=None
        else:data,member=packs[relative].read(name)
        sha=hashlib.sha256(data).hexdigest();require(sha==SOURCE_SHA[role],'Retail fog member SHA differs: '+name)
        assets.append((name,data));metadata.append(dict(role=role,name=name,source=relative,member=member,bytes=len(data),sha256=sha,**validate_asset(role,data)))
    require(all(artifact(game/relative)==row for relative,row in inputs.items()),'Retail fog sources changed while reading')
    return assets,inputs,metadata

def _write_new(path,value):
    with path.open('x',encoding='utf8') as stream:json.dump(value,stream,indent=2);stream.write('\n')

def prepare(game_root,output_root):
    game=Path(game_root).resolve(strict=True);project=Path(__file__).absolute().parents[1];output=Path(output_root).absolute()
    require('..' not in output.parts and output.resolve()==output and output.is_relative_to(project/'Build/OriginalFogAssets') and
            not output.is_relative_to(game),'Output must stay in approved separate fog cache')
    for part in (output,*output.parents):
        if part.exists():require(not getattr(part.lstat(),'st_file_attributes',0)&0x400,'Reparse fog output path')
    assets,inputs,metadata=source_assets(game)
    raw=encode_package(assets);sha=hashlib.sha256(raw).hexdigest();directory=output/sha;path=directory/'fog-assets.bin'
    manifest_path=directory/'fog-assets.manifest.json'
    if directory.exists():
        require(path.exists() and manifest_path.exists(),'Incomplete existing fog package; inspect before retrying')
        manifest=json.loads(manifest_path.read_text('utf8'))
        require(manifest.get('sha256')==sha and manifest.get('inputs')==inputs,'Retained fog package provenance differs')
        verified=validate_package(path,sha);return dict(package=artifact(path),manifest=artifact(manifest_path),reused=True,verified=verified)
    output.mkdir(parents=True,exist_ok=True);directory.mkdir()
    with path.open('xb') as stream:stream.write(raw)
    verified=validate_package(path,sha)
    _write_new(manifest_path,dict(schema='zerosis.original_fog_assets.v1',sha256=sha,bytes=len(raw),inputs=inputs,source_assets=metadata,
        package=verified,lut_interpretation='CANDIDATE_TGA_STANDARD_ORIGIN_FIRST_32_CUBED_R_FASTEST',
        original_lut_loader_equivalence_verified=False,native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False))
    return dict(package=artifact(path),manifest=artifact(manifest_path),reused=False,verified=verified)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=('prepare','verify'))
    parser.add_argument('--game-root');parser.add_argument('--output-root');parser.add_argument('--package');parser.add_argument('--sha256')
    args=parser.parse_args()
    if args.command=='prepare':require(args.game_root and args.output_root,'Missing prepare paths');result=prepare(args.game_root,args.output_root)
    else:require(args.package and args.sha256,'Missing verify package/SHA');result=validate_package(args.package,args.sha256)
    print(json.dumps({key:value for key,value in result.items() if key in ('package','manifest','reused','bytes','sha256','asset_count')}))

if __name__=='__main__':main()
