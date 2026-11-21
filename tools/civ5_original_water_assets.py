"""SHA-sealed water/river DDS and coast definitions; no native or game loading.

ZSWATER1 contains only supplemental inputs. Retained terrain and fog packages
are reused. Identical coast profile bytes share one blob. Unused LEAN sources
are inspected for provenance/shape only and are never copied to the package.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import xml.etree.ElementTree as ET

from civ5_ui_assets import Fpk, require
from civ5_original_fog_assets import artifact,digest,_regular,validate_dds

MAGIC=b'ZSWATER1'
VERSION=1
MAX_PACKAGE_BYTES=16*1024*1024
MAX_ASSET_BYTES=5*1024*1024
ROLES={1:'waterdepthcolor.dds',2:'waterbumps.dds',3:'watersky.dds',4:'river_alpha.dds',5:'river_diffuse.dds',
    6:'river_rough.dds',7:'river_smooth.dds',8:'wave_coastline_01.dds',9:'riverbank_d.dds',10:'riverbank_d_endcap1.dds',
    11:'riverbank_d_endcap2.dds',12:'riverbank_h.dds',13:'generic_riverbank_d.dds',14:'generic_riverbank_s.dds',15:'coaststyles.xml',
    16:'coastcharacterspline_01_water.txt',17:'coastcharacterspline_01_surf.txt',18:'coastcharacterspline_01_beach.txt',
    19:'coastcharacterspline_02_water.txt',20:'coastcharacterspline_02_surf.txt',21:'coastcharacterspline_02_beach.txt',
    22:'coastcharacterspline_03_water.txt',23:'coastcharacterspline_03_surf.txt',24:'coastcharacterspline_03_beach.txt',25:'civ5coaststyleschema.xsd'}
SOURCE_SHA={1:'88badcaf0c632b93947a169d996f70969cde6fa55f8e50d863cd97aaf2d84533',
    2:'c23cdf47d37ddf70a2880ad5e780b7fc6290c025e9c9d637be4035448ec39878',
    3:'47fc99c3e7848e01478b693cf0e89574da59a361eac61e66f2bc3d0ce761c63d',
    4:'afc49151b0a041f55d02596d2527f7bf1903fd9ad362d0440cec2de9110f5220',
    5:'3e000b948fe91b04e2d8733eeac8af1156807544cf50f22dc427edc8e290c56b',
    6:'c6f17f95bc9dd659fdc3e92882cf2d2fdc0db59c8ee35b9d59a93394b698326b',
    7:'2109d73d6798bb4b339a74d8e7b938af91d4dbee55f7511603d3fb3addaf0705',
    8:'91111257637e38cfc1d852c14adb925c4e60dfec82c8045bef44bbda661bae2a',
    9:'3f3c2db69b5d5446eb4cd952a691603c64cc0af315b911b469d2b71e0dd1b930',
    10:'5a0960b6ec181dab9c8216438cdc8bef933cea09c120f104cf13b976745593a6',
    11:'750192601be2f9250365e0a956348bf2e66ad07d99801360306cefed25fbc11a',
    12:'bf544b8ea32e8aa663ce9d0ee1dee01482aad84748d0aba50dc8e2ecc79c7bd3',
    13:'3238bbf5ae8ab175e9cf0c16246c59cb72fa80cdf2def26e3e12c451fc974909',
    14:'ff22ea249bd2787e389c644a94862e32d8373e6f85768c9e9124b98923ee9270',
    15:'ad0b9bba44ac98c8ab2f6fdabedb0438e3f7fb6544d74ce091ceed61c203a76f',
    16:'dc7c3aebbef2089a38c9b9aff42ebcacb63ee93994adc87a04b3bcec71bc930f',
    17:'dc7c3aebbef2089a38c9b9aff42ebcacb63ee93994adc87a04b3bcec71bc930f',
    18:'65de67a45d130819f8b98720ed51c5c54f006ce0b5e67814c691defaa1e6ea2b',
    19:'9747a84dd0bd7789cfddfac93d7e6f6ea46e78a1ba5af65d16a7e60e1b5d394a',
    20:'30126bd85c5849cbc5b12c635eaedc10cd5a3aa78454626c4edb62952da2ab03',
    21:'02fd45ef4ec9c49e12d0ef8cd6365435b4b876d7b8834ed8c3538c19e93ba39c',
    22:'d9125479b68c3871522beb4f9c71988de09203d7bee55a40dff5d863339d134d',
    23:'9e95e9cf6af582d70002b51d9137c595d65fe6201455a745f93bbc8245db94f8',
    24:'b029b25d5ffacbffb8a552475ee5ca65191387e698bc6cf79dd1377bfc4b63c1',
    25:'303e905ec46516a67c823d4632a77b703bf0679190bb73341bf57b1ba3f0a7df'}
PACK_TERRAIN='Resource/DX9/TerrainTextures.fpk'
PACK_DECAL='Resource/DX9/DecalTextures.fpk'
PACK_MODELS='Resource/Common/TerrainModels.fpk'
SOURCE_PACKS={PACK_TERRAIN:'8fb5183a2fe92d8add58d7758a231caafb27a2eb87b1958284eaa7d42a49577b',
    PACK_DECAL:'4132c9f9495cf9587ea54ce8b5710ae8c69b319771adc534f0e30c881b8572d0',
    PACK_MODELS:'a44983d0e147e47068369573110942ad9f44604dd015bc8f0026c636b75fc934'}
LEAN_SHA={'waterbumps16.lean':'c7d267cb4e4fa58093e21e799783f7df5fc0535fe0f4eafae11e63d086838a14',
    'riverrough16.lean':'351e2af8a5fd8a4c153e6bbb034860ce0b6608a8662d2b3a2692f41ff3c78808',
    'riversmooth16.lean':'b23b51ba6aed5d341e5d2abd092a72833637e03cfb7ca99251110f7a7c3ed6f1'}
STYLE_NAMES=('Default','Grass','GrassHill','Plains','PlainsHill','Snow','SnowHill','Desert','DesertHill','Tundra','TundraHill','Mountain','DefaultShallows')
_DECIMAL=re.compile(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z',re.ASCII)
_UINT=re.compile(r'[0-9]{1,5}\Z',re.ASCII)
_SHA=re.compile(r'[0-9a-f]{64}\Z',re.ASCII)

def source_pack(role):return PACK_MODELS if role>=15 else PACK_DECAL if 9<=role<=12 else PACK_TERRAIN

def decimal(text,minimum,maximum):
    require(isinstance(text,str) and 0<len(text)<=64 and _DECIMAL.fullmatch(text),'Invalid coast decimal syntax')
    value=float(text);require(math.isfinite(value) and minimum<=value<=maximum,'Nonfinite/out-of-range coast value');return value

def integer(text,maximum=65535):
    require(isinstance(text,str) and _UINT.fullmatch(text),'Invalid coast unsigned integer')
    value=int(text);require(value<=maximum,'Coast integer exceeds its bound');return value

def xml_root(data,root_name):
    require(0<len(data)<=16384 and b'\0' not in data and b'<!DOCTYPE' not in data.upper() and b'<!ENTITY' not in data.upper(),
        'Unbounded coast XML or forbidden DTD/entity')
    text=data.decode('ascii');root=ET.fromstring(text);require(root.tag==root_name,'Unexpected coast XML root');return root

def _attributes(element,names):
    require(set(element.attrib)==set(names) and not list(element),'Unexpected coast attributes/children')
    require(element.text is None or not element.text.strip(),'Unexpected coast element text')

def parse_coast_styles(data):
    root=xml_root(data,'CoastRoot');require(not root.attrib and [child.tag for child in root]==['SplineCharacterList','CoastStyleList'],
        'Unexpected coast list order')
    characters,styles=root;schema_key='{http://www.w3.org/2001/XMLSchema-instance}noNamespaceSchemaLocation'
    require(characters.attrib==styles.attrib=={schema_key:'Civ5CoastStyleSchema.xsd'},'Unexpected coast schema reference')
    require(len(characters)==9,'Coast character count differs')
    for index,element in enumerate(characters,16):
        require(element.tag=='SplineCharacter','Unexpected coast character tag');_attributes(element,('Filename',))
        require(element.attrib['Filename'].lower()==ROLES[index],'Noncanonical coast character order/path')
    require(len(styles)==len(STYLE_NAMES),'Coast style count differs');result=[]
    for name,element in zip(STYLE_NAMES,styles):
        require(element.tag=='CoastStyle' and element.attrib=={'type':name} and
            [child.tag for child in element]==['SmoothingOffset','HighBeach','LowBeach','Waterline'],'Unexpected ordered coast style')
        smoothing,high,low,water=element;_attributes(smoothing,('HighSide','LowSide'))
        item=dict(name=name,high_smoothing=decimal(smoothing.attrib['HighSide'],0,128),low_smoothing=decimal(smoothing.attrib['LowSide'],0,128))
        for tag,band in (('high_beach',high),('low_beach',low),('waterline',water)):
            _attributes(band,('Height','Offset','Character') if tag=='waterline' else ('Height','Offset','Character','TerrainType'))
            character=integer(band.attrib['Character']);require(character<9 or character==65535,'Coast character reference differs')
            item[tag]=dict(height=decimal(band.attrib['Height'],0,1),offset=decimal(band.attrib['Offset'],0,128),
                character=character,terrain_type=integer(band.attrib['TerrainType']) if tag!='waterline' else 65535)
        result.append(item)
    return result

def parse_coast_profile(data):
    require(0<len(data)<=8192 and b'\0' not in data,'Unbounded coast profile');points=[]
    for line in data.decode('ascii').splitlines():
        line=line.strip()
        if not line:continue
        require(line.startswith('[') and line.endswith(']'),'Invalid coast point brackets')
        fields=line[1:-1].split(',');require(len(fields)==3,'Invalid coast point component count')
        point=[decimal(field.strip(),0,400) if i==0 else decimal(field.strip(),-64,64) for i,field in enumerate(fields)]
        require(point[2]==0 and (not points or points[-1][0]>point[0]),'Coast profile is not descending X/Z=0');points.append(point)
        require(len(points)<=100,'Coast profile exceeds100 points')
    require(len(points)==100 and points[0][0]==400 and points[-1][0]==0,'Coast profile count/endpoints differ')
    return points

def validate_lean(data):
    require(36<=len(data)<=MAX_ASSET_BYTES and data[:4]==b'LEAN','Invalid bounded LEAN container')
    scale=struct.unpack_from('<f',data,4)[0];width,height,mips,channel_bytes,first,second=struct.unpack_from('<6I',data,8)
    require(math.isfinite(scale) and 0<scale<=16 and 0<width<=2048 and 0<height<=2048 and
        0<mips<=max(width,height).bit_length() and channel_bytes in(1,2) and data[32]==1,'Unsupported LEAN shape')
    texels=sum(max(1,width>>level)*max(1,height>>level) for level in range(mips))
    require(first==36 and second==36+texels*4*channel_bytes and len(data)==second+texels*channel_bytes,'LEAN plane extents differ')
    planes=[]
    for channels,start in ((4,first),(1,second)):
        cursor=start;levels=[]
        for level in range(mips):
            x,y=max(1,width>>level),max(1,height>>level);pitch=x*channels*channel_bytes;count=pitch*y
            levels.append(dict(level=level,width=x,height=y,offset=cursor,bytes=count,row_pitch=pitch));cursor+=count
        planes.append(dict(channels=channels,levels=levels))
    return dict(width=width,height=height,mips=mips,output_scale=scale,bytes_per_channel=channel_bytes,flag_at32=data[32],
        padding_at33_35='retained opaque bytes; not interpreted',planes=planes,channel_semantics_verified=False,included_in_package=False)

def validate_asset(role,data):
    require(role in ROLES and 0<len(data)<=MAX_ASSET_BYTES,'Invalid water asset role/size')
    if role<=14:
        texture=validate_dds(data,ROLES[role]);expected='BGRA8' if role in(1,2,3,4,7) else 'BC1' if role==5 else 'BC3'
        require(texture['format']==expected,'Water role DDS codec differs');return dict(texture=texture)
    if role==15:return dict(styles=parse_coast_styles(data))
    if role<=24:
        points=parse_coast_profile(data);return dict(profile=dict(count=100,ranges=[[min(p[i]for p in points),max(p[i]for p in points)]for i in range(3)],
            samples=[dict(index=i,point=points[i])for i in(0,25,50,75,99)]))
    xml_root(data,'{http://www.w3.org/2001/XMLSchema}schema');return dict(schema_reference_only=True,external_resolution_performed=False)

def encode_package(assets):
    require(len(assets)==25,'Water package requires25 roles');descriptors=bytearray();blobs=[];indices={}
    for role,(name,data) in enumerate(assets,1):
        require(name==ROLES[role],'Noncanonical ordered water name');validate_asset(role,data)
        sha=hashlib.sha256(data).digest()
        if sha not in indices:indices[sha]=len(blobs);blobs.append((sha,data))
        else:require(blobs[indices[sha]][1]==data,'Unexpected SHA collision')
        raw=name.encode('ascii');descriptors.extend(struct.pack('<III',role,len(raw),indices[sha])+raw)
    result=bytearray(MAGIC+struct.pack('<III',VERSION,25,len(blobs))+descriptors)
    for sha,data in blobs:result.extend(struct.pack('<I',len(data))+sha+data)
    require(len(result)<=MAX_PACKAGE_BYTES,'Water package exceeds size bound');return bytes(result)

def validate_package_bytes(raw,expected_sha256=None):
    require(20<=len(raw)<=MAX_PACKAGE_BYTES,'Unbounded water package');sha=hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None:require(_SHA.fullmatch(expected_sha256) and sha==expected_sha256,'Water package SHA differs')
    cursor=0
    def take(count):
        nonlocal cursor
        require(0<=count<=len(raw)-cursor,'Truncated water package');value=raw[cursor:cursor+count];cursor+=count;return value
    require(take(8)==MAGIC,'Unknown water magic');version,count,blob_count=struct.unpack('<III',take(12))
    require(version==VERSION and count==25 and 0<blob_count<=25,'Unknown water version/count')
    descriptors=[];seen=set()
    for role in range(1,26):
        index,n,blob=struct.unpack('<III',take(12));require(index==role and 0<n<=64 and blob<blob_count,'Invalid water descriptor bounds/order')
        name=take(n).decode('ascii');require(name==ROLES[role],'Noncanonical water name')
        if blob not in seen:require(blob==len(seen),'Water blobs are not in first-reference order');seen.add(blob)
        descriptors.append(dict(role=role,name=name,blob_index=blob))
    require(len(seen)==blob_count,'Unreferenced water blob');blobs=[];hashes=set()
    for index in range(blob_count):
        size=struct.unpack('<I',take(4))[0];expected=take(32);require(0<size<=MAX_ASSET_BYTES,'Unbounded water blob')
        offset=cursor;data=take(size);require(hashlib.sha256(data).digest()==expected and expected not in hashes,'Water blob SHA/uniqueness differs')
        hashes.add(expected);blobs.append(dict(index=index,offset=offset,bytes=size,sha256=expected.hex()))
    require(cursor==len(raw),'Water package trailing data');assets=[]
    for descriptor in descriptors:
        blob=blobs[descriptor['blob_index']];meta=validate_asset(descriptor['role'],raw[blob['offset']:blob['offset']+blob['bytes']])
        if 'texture'in meta:
            for level in meta['texture']['levels']:level['package_offset']=blob['offset']+level['offset']
        assets.append(dict(descriptor,offset=blob['offset'],bytes=blob['bytes'],sha256=blob['sha256'],**meta))
    return dict(version=VERSION,asset_count=25,blob_count=blob_count,assets=assets,blobs=blobs,bytes=len(raw),sha256=sha,
        included_lean_assets=0,terrain_and_fog_package_copies=0)

def validate_package(path,expected_sha256=None):
    path=Path(path).absolute();before=_regular(path);require(before.st_size<=MAX_PACKAGE_BYTES,'Unbounded water package file')
    result=validate_package_bytes(path.read_bytes(),expected_sha256);after=path.stat()
    require((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)==
            (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns),'Water package changed during validation');return result

def source_assets(game):
    game=Path(game).resolve(strict=True);inputs={};packs={}
    for relative,sha in SOURCE_PACKS.items():
        row=artifact(game/relative);require(row['sha256']==sha,'Retail water archive SHA differs: '+relative)
        inputs[relative]=row;packs[relative]=Fpk(game/relative)
    assets=[];metadata=[]
    for role,name in ROLES.items():
        data,member=packs[source_pack(role)].read(name);sha=hashlib.sha256(data).hexdigest()
        require(sha==SOURCE_SHA[role],'Retail water member SHA differs: '+name);assets.append((name,data))
        metadata.append(dict(role=role,name=name,source=source_pack(role),member=member,bytes=len(data),sha256=sha,**validate_asset(role,data)))
    lean=[]
    for name,sha in LEAN_SHA.items():
        data,member=packs[PACK_MODELS].read(name);require(hashlib.sha256(data).hexdigest()==sha,'Retail LEAN source SHA differs')
        lean.append(dict(name=name,source=PACK_MODELS,member=member,bytes=len(data),sha256=sha,**validate_lean(data)))
    require(all(artifact(game/relative)==row for relative,row in inputs.items()),'Retail water sources changed while reading')
    return assets,inputs,metadata,lean

def write_new(path,value):
    with path.open('x',encoding='utf8')as stream:json.dump(value,stream,indent=2);stream.write('\n')

def prepare(game_root,output_root):
    game=Path(game_root).resolve(strict=True);project=Path(__file__).absolute().parents[1];output=Path(output_root).absolute()
    require('..'not in output.parts and output.resolve()==output and output.is_relative_to(project/'Build/OriginalWaterAssets')and
        not output.is_relative_to(game),'Water output must stay in approved separate cache')
    for part in(output,*output.parents):
        if part.exists():require(not getattr(part.lstat(),'st_file_attributes',0)&0x400,'Reparse water output path')
    assets,inputs,metadata,lean=source_assets(game);raw=encode_package(assets);sha=hashlib.sha256(raw).hexdigest()
    directory=output/sha;path=directory/'water-assets.bin';manifest_path=directory/'water-assets.manifest.json'
    if directory.exists():
        require(path.exists()and manifest_path.exists(),'Incomplete existing water package;inspect before retry')
        require(_regular(manifest_path).st_size<=256*1024,'Unbounded retained water manifest')
        manifest=json.loads(manifest_path.read_text('utf8'));require(manifest.get('sha256')==sha and manifest.get('inputs')==inputs,
            'Retained water provenance differs');verified=validate_package(path,sha)
        return dict(package=artifact(path),manifest=artifact(manifest_path),reused=True,verified=verified)
    output.mkdir(parents=True,exist_ok=True);directory.mkdir()
    with path.open('xb')as stream:stream.write(raw)
    verified=validate_package(path,sha)
    write_new(manifest_path,dict(schema='zerosis.original_water_assets.v1',sha256=sha,bytes=len(raw),inputs=inputs,source_assets=metadata,
        excluded_lean_sources=lean,package=verified,coast_interpretation='raw style/profile values only;rendering/units remain candidates',
        terrain_and_fog_package_copies=0,native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False))
    return dict(package=artifact(path),manifest=artifact(manifest_path),reused=False,verified=verified)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=('prepare','verify'));parser.add_argument('--game-root')
    parser.add_argument('--output-root');parser.add_argument('--package');parser.add_argument('--sha256');args=parser.parse_args()
    if args.command=='prepare':require(args.game_root and args.output_root,'Missing prepare paths');result=prepare(args.game_root,args.output_root)
    else:require(args.package and args.sha256,'Missing water package/SHA');result=validate_package(args.package,args.sha256)
    print(json.dumps({key:value for key,value in result.items()if key in('package','manifest','reused','bytes','sha256','asset_count','blob_count')}))

if __name__=='__main__':main()
