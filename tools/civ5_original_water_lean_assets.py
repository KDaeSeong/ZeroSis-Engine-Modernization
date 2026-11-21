"""One SHA-sealed water LEAN source, with no DDS/terrain/fog duplication.

Only waterbumps16.lean is used by this stage. River LEAN files stay in the
retail archive. The raw output-scale field is not silently bound to shader S.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct

from civ5_ui_assets import Fpk,require
from civ5_original_fog_assets import artifact,digest,_regular
from civ5_original_water_assets import validate_lean,write_new

MAGIC=b'ZSWLEAN1'
VERSION=1
MAX_PACKAGE_BYTES=8*1024*1024
MAX_ASSET_BYTES=4*1024*1024
NAME='waterbumps16.lean'
SOURCE_RELATIVE='Resource/Common/TerrainModels.fpk'
SOURCE_PACK_SHA='a44983d0e147e47068369573110942ad9f44604dd015bc8f0026c636b75fc934'
SOURCE_SHA='c7d267cb4e4fa58093e21e799783f7df5fc0535fe0f4eafae11e63d086838a14'
EXCLUDED_RIVER_BYTES=437012
_SHA=re.compile(r'[0-9a-f]{64}\Z',re.ASCII)

def validate_texture(data):
    require(46<=len(data)<=MAX_ASSET_BYTES,'Unbounded water LEAN asset');meta=validate_lean(data)
    require(meta['width']<=1024 and meta['height']<=1024 and meta['mips']==max(meta['width'],meta['height']).bit_length()and
        meta['bytes_per_channel']==2,'Water LEAN must be complete16-bit mip chains')
    meta['included_in_package']=True;meta['full_mip_chain_validated']=True
    meta['planes'][0]['format']='R16G16B16A16_UNORM';meta['planes'][1]['format']='R16_UNORM'
    for plane in meta['planes']:
        for level in plane['levels']:level['slice_pitch']=level['bytes']
    meta['shader_scale_binding']='header outputScale to runtime shader S remains a candidate'
    return meta

def encode_package(data):
    validate_texture(data);name=NAME.encode('ascii')
    return MAGIC+struct.pack('<IIIII',1,1,1,len(name),len(data))+hashlib.sha256(data).digest()+name+data

def validate_package_bytes(raw,expected_sha256=None):
    require(16<=len(raw)<=MAX_PACKAGE_BYTES,'Unbounded water LEAN package');sha=hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None:require(_SHA.fullmatch(expected_sha256)and sha==expected_sha256,'Water LEAN package SHA differs')
    cursor=0
    def take(count):
        nonlocal cursor
        require(0<=count<=len(raw)-cursor,'Truncated water LEAN package');data=raw[cursor:cursor+count];cursor+=count;return data
    require(take(8)==MAGIC and struct.unpack('<II',take(8))==(1,1),'Unknown water LEAN format/count')
    role,n,count=struct.unpack('<III',take(12));expected=take(32)
    require(role==1 and 0<n<=64 and 46<=count<=MAX_ASSET_BYTES,'Invalid water LEAN record bounds/role')
    name=take(n).decode('ascii');require(name==NAME,'Noncanonical water LEAN asset name');offset=cursor;data=take(count)
    require(hashlib.sha256(data).digest()==expected,'Water LEAN asset SHA differs');texture=validate_texture(data)
    for plane in texture['planes']:
        for level in plane['levels']:level['package_offset']=offset+level['offset']
    require(cursor==len(raw),'Water LEAN package trailing data')
    return dict(version=VERSION,asset_count=1,bytes=len(raw),sha256=sha,assets=[dict(role=1,name=name,offset=offset,bytes=count,
        sha256=expected.hex(),texture=texture)],duplicated_water_dds=0,included_river_lean_assets=0)

def validate_package(path,expected_sha256=None):
    path=Path(path).absolute();before=_regular(path);require(before.st_size<=MAX_PACKAGE_BYTES,'Unbounded water LEAN package file')
    result=validate_package_bytes(path.read_bytes(),expected_sha256);after=path.stat()
    require((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)==
        (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns),'Water LEAN package changed during validation');return result

def source_asset(game):
    game=Path(game).resolve(strict=True);path=game/SOURCE_RELATIVE;before=artifact(path)
    require(before['sha256']==SOURCE_PACK_SHA,'Retail LEAN archive SHA differs');pack=Fpk(path);raw,member=pack.read(NAME)
    require(hashlib.sha256(raw).hexdigest()==SOURCE_SHA,'Retail water LEAN SHA differs');texture=validate_texture(raw)
    commands=[]
    for name in('run_water.bat','make_river_lean.bat'):
        data,meta=pack.read(name);commands.append(dict(name=name,bytes=len(data),sha256=meta['sha256'],text=data.decode('ascii'),executed=False))
    require(artifact(path)==before,'Retail LEAN archive changed while reading')
    return raw,before,dict(member=member,texture=texture,commands=commands)

def prepare(game_root,output_root):
    game=Path(game_root).resolve(strict=True);project=Path(__file__).absolute().parents[1];output=Path(output_root).absolute()
    require('..'not in output.parts and output.resolve()==output and output.is_relative_to(project/'Build/OriginalWaterLeanAssets')and
        not output.is_relative_to(game),'Water LEAN output must stay in approved private cache')
    for part in(output,*output.parents):
        if part.exists():require(not getattr(part.lstat(),'st_file_attributes',0)&0x400,'Reparse water LEAN output path')
    data,source,metadata=source_asset(game);raw=encode_package(data);sha=hashlib.sha256(raw).hexdigest()
    directory=output/sha;path=directory/'water-lean-assets.bin';manifest_path=directory/'water-lean-assets.manifest.json'
    if directory.exists():
        require(path.exists()and manifest_path.exists(),'Incomplete retained water LEAN package;inspect before retry')
        require(_regular(manifest_path).st_size<=128*1024,'Unbounded retained water LEAN manifest')
        manifest=json.loads(manifest_path.read_text('utf8'));require(manifest.get('sha256')==sha and manifest.get('source')==source,
            'Retained water LEAN provenance differs');verified=validate_package(path,sha)
        return dict(package=artifact(path),manifest=artifact(manifest_path),verified=verified,reused=True)
    output.mkdir(parents=True,exist_ok=True);directory.mkdir()
    with path.open('xb')as stream:stream.write(raw)
    verified=validate_package(path,sha)
    write_new(manifest_path,dict(schema='zerosis.original_water_lean_assets.v1',sha256=sha,bytes=len(raw),source=source,metadata=metadata,
        package=verified,river_lean_bytes_not_copied=EXCLUDED_RIVER_BYTES,duplicated_water_dds=0,
        shader_scale_binding_verified=False,native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False))
    return dict(package=artifact(path),manifest=artifact(manifest_path),verified=verified,reused=False)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=('prepare','verify'));parser.add_argument('--game-root');parser.add_argument('--output-root')
    parser.add_argument('--package');parser.add_argument('--sha256');args=parser.parse_args()
    if args.command=='prepare':require(args.game_root and args.output_root,'Missing water LEAN prepare paths');result=prepare(args.game_root,args.output_root)
    else:require(args.package and args.sha256,'Missing water LEAN package/SHA');result=validate_package(args.package,args.sha256)
    print(json.dumps({k:v for k,v in result.items()if k in('package','manifest','reused','bytes','sha256','asset_count')}))

if __name__=='__main__':main()
