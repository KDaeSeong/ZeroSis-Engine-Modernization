"""SHA-sealed original terrain rows, D/H/S DDS blobs and the untouched piece library.

This module performs file IO only. It never loads a DLL, graphics API or game.
ZSTERR02 is separate from the retained ZSTERR01 format. The absent retail
Generic_Gibraltar_H.dds is represented explicitly, never synthesized as an asset.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import stat
import struct
import sys

from civ5_ui_assets import Fpk, require

MAGIC=b'ZSTERR02'
VERSION=2
NULL_TEXTURE=0xffffffff
MISSING_TEXTURE=0xfffffffe
MAX_PACKAGE_BYTES=128*1024*1024
MAX_DDS_BYTES=32*1024*1024
MAX_LIBRARY_BYTES=32*1024*1024
MAX_ROWS=64
MAX_TEXTURES=256
CSV_RELATIVE=Path('Assets/DLC/Shared/Terrain/TerrainDef.csv')
PACK_RELATIVE=Path('Resource/DX9/TerrainTextures.fpk')
LIBRARY_RELATIVE=Path('Resource/Common/TerrainPiecesLibrary.fxsb')
CSV_SHA256='ce16f7e024672fa756fec012f6c21925461705b8ecf66bfed0940ba170ce5a4a'
PACK_SHA256='8fb5183a2fe92d8add58d7758a231caafb27a2eb87b1958284eaa7d42a49577b'
LIBRARY_SHA256='86faac1e80634b0031a9df98889682fbc17ddc72341fc68fbf5b33e7ce4c1c7a'
FIELDS=('Continent ID','Diffuse','Heightmap','Specmap','BaseDominance','Texture Scale',
        'Projection(0=horizontal 1=vertical)',' ID (unique for continent)')
ROW=struct.Struct('<IIIfIIII')
_NAME=re.compile(r'[A-Za-z0-9][A-Za-z0-9_. -]{0,120}\.dds\Z',re.ASCII|re.I)
_UINT=re.compile(r'(?:0|[1-9][0-9]*)\Z',re.ASCII)
_HEX=re.compile(r'(?:0[xX])?[0-9a-fA-F]{1,8}\Z',re.ASCII)
_SHA=re.compile(r'[0-9a-f]{64}\Z',re.ASCII)

def digest(path):
    value=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):value.update(chunk)
    return value.hexdigest()

def _regular(path):
    path=Path(path).absolute()
    require('..' not in path.parts,'Noncanonical terrain path')
    for part in (path,*path.parents):
        info=part.lstat()
        require(not stat.S_ISLNK(info.st_mode) and not getattr(info,'st_file_attributes',0)&0x400,
                'Terrain input has a reparse/symbolic path')
    info=path.stat();require(stat.S_ISREG(info.st_mode),'Terrain input is not a regular file')
    return info

def artifact(path):
    path=Path(path).absolute();before=_regular(path)
    result=dict(path=str(path),bytes=before.st_size,sha256=digest(path))
    after=path.stat()
    require((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)==
            (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns),'Terrain file changed while hashing')
    return result

def parse_csv(data):
    """Keep CSV row order; legacy ID is %x, and BaseDominance is discarded."""
    if isinstance(data,bytes):data=data.decode('utf-8-sig')
    reader=csv.DictReader(io.StringIO(data),strict=True)
    require(reader.fieldnames==list(FIELDS),'Unexpected original TerrainDef columns')
    rows=[];identities=set()
    for index,source in enumerate(reader):
        require(None not in source and all(value is not None for value in source.values()),'Malformed TerrainDef row')
        require(index<MAX_ROWS and _UINT.fullmatch(source['Continent ID']) and _HEX.fullmatch(source[FIELDS[-1]]),
                'Unbounded TerrainDef row or identity')
        continent=int(source['Continent ID']);legacy=int(source[FIELDS[-1]],16)
        require(0<=continent<=4 and legacy<=255 and (continent,legacy) not in identities,'Invalid/duplicate TerrainDef identity')
        identities.add((continent,legacy))
        try:scale=float(source['Texture Scale'])
        except ValueError as error:raise ValueError('Invalid TerrainDef scale') from error
        require(math.isfinite(scale) and 0<scale<=16,'TerrainDef scale is nonfinite or out of bounds')
        require(struct.unpack('<f',struct.pack('<f',scale))[0]>0,'TerrainDef scale underflows its original float field')
        require(source['Projection(0=horizontal 1=vertical)'] in ('0','1'),'Invalid TerrainDef projection')
        names=[]
        for field in ('Diffuse','Heightmap','Specmap'):
            name=source[field]
            require(name=='NULL' or bool(_NAME.fullmatch(name)),'Unsafe TerrainDef texture name')
            names.append(None if name=='NULL' else name)
        require(names[0] is not None,'TerrainDef diffuse may not be NULL')
        rows.append(dict(row=index,continent=continent,legacy_id=legacy,scale=scale,
            projection=int(source['Projection(0=horizontal 1=vertical)']),diffuse=names[0],height=names[1],specular=names[2]))
    require(rows and sum(3 if row['projection'] else 1 for row in rows)<=64,'TerrainDef exceeds 64 expanded materials')
    return rows

def validate_dds(data,name='DDS'):
    require(128<=len(data)<=MAX_DDS_BYTES and data[:4]==b'DDS ',name+': invalid DDS header/size')
    words=struct.unpack_from('<32I',data)
    require(words[1]==124 and words[19]==32 and words[2]&0x1007==0x1007 and words[28]==0 and words[6]==0,
            name+': unsupported DDS shape')
    width,height=words[4],words[3];mips=max(1,words[7])
    require(0<width<=4096 and 0<height<=4096 and mips<=max(width,height).bit_length(),name+': invalid DDS dimensions/mips')
    codecs={int.from_bytes(b'DXT1','little'):('BC1',8),int.from_bytes(b'DXT3','little'):('BC2',16),
            int.from_bytes(b'DXT5','little'):('BC3',16)}
    require(words[20]&4 and words[21] in codecs,name+': unsupported DDS codec')
    codec,block=codecs[words[21]]
    expected=128+sum(((max(1,width>>level)+3)//4)*((max(1,height>>level)+3)//4)*block for level in range(mips))
    require(len(data)==expected,name+': DDS payload/mip chain length differs')
    return dict(width=width,height=height,mips=mips,format=codec,block_bytes=block,full_mip_chain_validated=True)

def validate_library(data,row_count=MAX_ROWS):
    """Validate the untouched v20 container and every RLE row without expanding it."""
    require(20<=len(data)<=MAX_LIBRARY_BYTES,'Unbounded piece library')
    require(struct.unpack_from('<I',data)[0]==20,'Unexpected piece library version')
    cursor=4;sections=[]
    for element in (4,1,2,0x56c):
        require(cursor+4<=len(data),'Truncated library count');count=struct.unpack_from('<I',data,cursor)[0];cursor+=4
        require(count>0 and count<32*1024*1024 and count*element<=len(data)-cursor,'Unbounded/truncated library array')
        sections.append((cursor,count));cursor+=count*element
    require(cursor==len(data) and sections[3][1]<=299,'Unexpected piece library trailing data/count')
    a0,ac=sections[0];b0,bc=sections[1];c0,cc=sections[2];d0,dc=sections[3]
    offsets=struct.unpack_from('<'+str(ac)+'I',data,a0)
    starts=[];pieces=[]
    for index in range(dc):
        at=d0+index*0x56c
        require(struct.unpack_from('<I',data,at+0x3bc)[0]==index,'Piece index differs')
        require(struct.unpack_from('<II',data,at+0x94)==(10,10) and struct.unpack_from('<II',data,at+0x3c0)==(10,10),
                'Piece grid differs')
        level=struct.unpack_from('<I',data,at+0x3c8)[0];require(1<=level<=4,'Invalid piece level')
        names=[]
        for text_at in (0x3ea,0x42a,0x46a,0x4aa,0x4ea,0x52a):
            raw=data[at+text_at:at+text_at+64];end=raw.find(b'\0')
            require(0<end<64,'Unbounded piece name');names.append(raw[:end].decode('ascii'))
        require(names[0]==names[1],'Piece CSV names differ')
        first=struct.unpack_from('<4I',data,at+0x3d4);starts.extend(first)
        pieces.append(dict(index=index,name=names[0],level=level))
    require(starts and starts==sorted(starts) and starts[0]==0 and starts[-1]<ac,'Piece row starts differ')
    boundaries=starts+[ac];used_b=used_c=0
    for index,piece in enumerate(pieces):
        sizes=[]
        for image in range(4):
            first=boundaries[index*4+image];size=boundaries[index*4+image+1]-first
            require(size in (128,512),'Piece image must be 128 or 512 square');sizes.append(size)
            for row in range(size):
                pos=offsets[first+row];total=0
                while total<size:
                    if image==0:
                        require(pos+2<=cc,'Piece height RLE outside C');count,value=struct.unpack_from('<HH',data,c0+pos*2)
                        used_c=max(used_c,pos+2)
                    else:
                        require(pos+2<=bc,'Piece byte RLE outside B');count,value=data[b0+pos],data[b0+pos+1]
                        used_b=max(used_b,pos+2)
                        if image==1:require(value<row_count,'Piece texture row is outside TerrainDef')
                    require(count>0 and total+count<=size,'Piece RLE row width differs');total+=count;pos+=2
        require(len(set(sizes))==1,'Piece image dimensions disagree');piece['image_size']=sizes[0]
    require(used_b==bc and used_c==cc,'Piece run streams have unconsumed bytes')
    return dict(version=20,piece_count=dc,image_sizes=sorted({row['image_size'] for row in pieces}),all_rle_rows_validated=True)

def encode_rows(rows,texture_indices,missing=()):
    missing=set(missing);result=bytearray();records=[]
    for index,row in enumerate(rows):
        require(row['row']==index,'TerrainDef row order differs');references=[]
        for role in ('diffuse','height','specular'):
            name=row[role]
            references.append(NULL_TEXTURE if name is None else MISSING_TEXTURE if name.lower() in missing else texture_indices[name.lower()])
        result.extend(ROW.pack(index,row['continent'],row['legacy_id'],row['scale'],row['projection'],*references))
        records.append(dict(row,texture_indices=dict(zip(('diffuse','height','specular'),references))))
    return bytes(result),records

def validate_package(path,expected_sha256=None):
    """Parse every blob and SHA from a sealed package, without reopening retail."""
    path=Path(path).absolute();before=_regular(path)
    require(24<=before.st_size<=MAX_PACKAGE_BYTES,'Unbounded original terrain package')
    initial_sha=digest(path)
    if expected_sha256 is not None:require(_SHA.fullmatch(expected_sha256) and initial_sha==expected_sha256,'Package SHA differs')
    with path.open('rb') as stream:
        def take(count):
            require(0<=count<=MAX_PACKAGE_BYTES and count<=before.st_size-stream.tell(),'Truncated terrain package')
            value=stream.read(count);require(len(value)==count,'Truncated terrain read');return value
        require(take(8)==MAGIC,'Unexpected terrain package magic')
        version,row_count,texture_count,library_bytes=struct.unpack('<4I',take(16))
        require(version==VERSION and 0<row_count<=MAX_ROWS and 0<texture_count<=MAX_TEXTURES and
                20<=library_bytes<=MAX_LIBRARY_BYTES,'Unsupported terrain package bounds')
        rows=[];expanded=0;identities=set()
        for index in range(row_count):
            row,continent,legacy,scale,projection,diffuse,height,specular=ROW.unpack(take(ROW.size))
            require(row==index and continent<=4 and legacy<=255 and math.isfinite(scale) and 0<scale<=16 and projection in (0,1),
                    'Invalid terrain row')
            require((continent,legacy) not in identities,'Duplicate terrain row legacy identity');identities.add((continent,legacy))
            require(diffuse<texture_count and all(value<texture_count or value in (NULL_TEXTURE,MISSING_TEXTURE) for value in (height,specular)),
                    'Invalid terrain texture reference')
            require(specular!=MISSING_TEXTURE and (height!=MISSING_TEXTURE or row==8),'Undeclared missing terrain texture')
            expanded+=3 if projection else 1;rows.append(dict(row=row,continent=continent,legacy_id=legacy,scale=scale,
                projection=projection,diffuse=diffuse,height=height,specular=specular))
        require(expanded<=64,'Expanded terrain materials exceed 64')
        textures=[];previous=''
        for index in range(texture_count):
            name_bytes,data_bytes=struct.unpack('<II',take(8));expected=take(32).hex()
            require(0<name_bytes<=128 and 128<=data_bytes<=MAX_DDS_BYTES,'Unbounded terrain DDS record')
            name=take(name_bytes).decode('ascii');require(_NAME.fullmatch(name) and name==name.lower() and name>previous,
                'Unsafe/duplicate/unordered DDS name');previous=name
            offset=stream.tell();data=take(data_bytes)
            require(hashlib.sha256(data).hexdigest()==expected,'Terrain DDS SHA differs')
            textures.append(dict(index=index,name=name,bytes=data_bytes,sha256=expected,offset=offset,dds=validate_dds(data,name)))
        library_sha=take(32).hex();offset=stream.tell();data=take(library_bytes)
        require(hashlib.sha256(data).hexdigest()==library_sha,'Piece library SHA differs')
        library=dict(bytes=library_bytes,sha256=library_sha,offset=offset,**validate_library(data,row_count))
        require(stream.tell()==before.st_size,'Terrain package has trailing bytes')
    after=path.stat();require((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)==
        (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns),'Terrain package changed during validation')
    require(digest(path)==initial_sha,'Terrain package bytes changed during validation')
    return dict(version=version,row_count=row_count,expanded_material_count=expanded,texture_count=texture_count,
        rows=rows,textures=textures,library=library,bytes=before.st_size,sha256=initial_sha)

def _write_new(path,value):
    with path.open('x',encoding='utf8') as stream:json.dump(value,stream,indent=2);stream.write('\n')

def prepare(game_root,output_root):
    game=Path(game_root).resolve(strict=True);output=Path(output_root).absolute()
    require(game.is_dir() and '..' not in output.parts and not output.resolve().is_relative_to(game),'Output escaped private terrain cache')
    project=Path(__file__).absolute().parents[1]
    require(output.resolve().is_relative_to(project/'Build/OriginalTerrainAssets'),'Output must stay in the approved original terrain cache')
    require(output.resolve()==output,'Output cache must be canonical')
    for part in (output,*output.parents):
        if part.exists():require(not part.lstat().st_file_attributes&0x400,'Output cache contains a reparse directory')
    expected=(('terrain_csv',CSV_RELATIVE,CSV_SHA256),('terrain_fpk',PACK_RELATIVE,PACK_SHA256),
              ('pieces_library',LIBRARY_RELATIVE,LIBRARY_SHA256))
    inputs={}
    for name,relative,sha in expected:
        path=game/relative;row=artifact(path);require(row['sha256']==sha,'Original terrain source differs from phase-0 SHA: '+name)
        inputs[name]=row
    rows=parse_csv((game/CSV_RELATIVE).read_bytes())
    require(len(rows)==41 and sum(3 if row['projection'] else 1 for row in rows)==47,'Pinned TerrainDef row profile differs')
    output.mkdir(parents=True,exist_ok=True)
    for manifest_path in output.glob('*/terrain-assets.manifest.json'):
        require(_regular(manifest_path).st_size<=4*1024*1024,'Unbounded retained terrain manifest')
        manifest=json.loads(manifest_path.read_text('utf8'))
        if manifest.get('format')!='ZEROSIS_CIV5_ORIGINAL_TERRAIN_PACKAGE_V2' or manifest.get('inputs')!=inputs:continue
        source=manifest_path.with_name('terrain-assets.bin')
        verified=validate_package(source,manifest['package']['sha256'])
        require(verified['row_count']==41 and verified['expanded_material_count']==47 and verified['texture_count']==72 and
                verified['library']['sha256']==LIBRARY_SHA256,'Existing original terrain cache differs')
        return dict(package_path=str(source),package_sha256=verified['sha256'],manifest_path=str(manifest_path),
            package_bytes=verified['bytes'],row_count=41,expanded_material_count=47,texture_count=72,originals_unchanged=True,reused_existing=True)
    pack=Fpk(game/PACK_RELATIVE)
    names=sorted({row[role].lower() for row in rows for role in ('diffuse','height','specular') if row[role] is not None})
    absent=[name for name in names if name not in pack.entries]
    require(absent==['generic_gibraltar_h.dds'] and rows[8]['height'].lower()==absent[0],
            'Terrain has a different undeclared missing source')
    names=[name for name in names if name not in absent];indices={name:index for index,name in enumerate(names)}
    encoded,records=encode_rows(rows,indices,absent)
    library_data=(game/LIBRARY_RELATIVE).read_bytes();library_info=validate_library(library_data,len(rows))
    require(hashlib.sha256(library_data).hexdigest()==LIBRARY_SHA256,'Piece library changed during read')
    temporary=output/'assembling-current.bin';require(not temporary.exists(),'Inspect the existing incomplete original terrain package first')
    hasher=hashlib.sha256();textures=[]
    with temporary.open('xb') as stream:
        def put(data):
            require(stream.tell()+len(data)<=MAX_PACKAGE_BYTES,'Original terrain package exceeds 128MiB')
            stream.write(data);hasher.update(data)
        put(MAGIC+struct.pack('<4I',VERSION,len(rows),len(names),len(library_data)));put(encoded)
        for index,name in enumerate(names):
            data,source=pack.read(name);info=validate_dds(data,name);sha=hashlib.sha256(data).hexdigest();raw=name.encode('ascii')
            put(struct.pack('<II',len(raw),len(data))+bytes.fromhex(sha)+raw);offset=stream.tell();put(data)
            textures.append(dict(index=index,name=name,bytes=len(data),sha256=sha,offset=offset,dds=info,
                fpk_entry=source['entry'],fpk_offset=source['offset']))
        put(bytes.fromhex(LIBRARY_SHA256));library_offset=stream.tell();put(library_data)
    for name,relative,_sha in expected:require(artifact(game/relative)==inputs[name],'Original terrain input changed during packaging')
    sha=hasher.hexdigest();verified=validate_package(temporary,sha)
    target=output/sha;require(not target.exists(),'Unexpected duplicate target; inspect before retrying')
    target.mkdir();package=target/'terrain-assets.bin';temporary.rename(package)
    manifest=dict(format='ZEROSIS_CIV5_ORIGINAL_TERRAIN_PACKAGE_V2',
        package=dict(path=str(package),bytes=verified['bytes'],sha256=sha,magic=MAGIC.decode('ascii'),version=VERSION,
            row_count=len(rows),expanded_material_count=47,texture_count=len(names),library_bytes=len(library_data),
            ordering='terrain_def_row_then_casefold_texture_name'),
        inputs=inputs,originals_unchanged=True,rows=records,textures=textures,
        library=dict(bytes=len(library_data),sha256=LIBRARY_SHA256,offset=library_offset,**library_info),
        declared_missing_textures=[dict(row=8,role='height',name='Generic_Gibraltar_H.dds',sentinel=MISSING_TEXTURE)],
        null_texture_sentinel=NULL_TEXTURE,missing_texture_sentinel=MISSING_TEXTURE,
        base_dominance_stored_or_used=False,
        preparer=dict(original_path=str(Path(__file__).absolute()),**{k:v for k,v in artifact(__file__).items() if k!='path'}),
        native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False)
    manifest_path=target/'terrain-assets.manifest.json';_write_new(manifest_path,manifest)
    return dict(package_path=str(package),package_sha256=sha,manifest_path=str(manifest_path),package_bytes=verified['bytes'],
        row_count=len(rows),expanded_material_count=47,texture_count=len(names),originals_unchanged=True,reused_existing=False)

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game',type=Path,required=True);parser.add_argument('--output',type=Path,
        default=Path(__file__).absolute().parents[1]/'Build/OriginalTerrainAssets')
    args=parser.parse_args(argv);print(json.dumps(prepare(args.game,args.output)))

if __name__=='__main__':main()
