"""Water asset bounds and XML/profile checks; no native execution."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import struct
import sys

sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[1]
sys.path[0:0]=[str(PROJECT/'tools'),str(PROJECT/'Tests')]
import civ5_original_water_assets as water
from original_fog_assets import dds

STAGE=PROJECT/'evidence/world_terrain_original/phase3/assets'
GAME=Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V")

def styles():
    schema=' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="Civ5CoastStyleSchema.xsd"'
    text='<?xml version="1.0"?><CoastRoot><SplineCharacterList'+schema+'>'
    text+=''.join('<SplineCharacter Filename="'+water.ROLES[role]+'"/>'for role in range(16,25))
    text+='</SplineCharacterList><CoastStyleList'+schema+'>'
    for name in water.STYLE_NAMES:
        text+='<CoastStyle type="'+name+'"><SmoothingOffset HighSide="20" LowSide="20"/>'
        text+='<HighBeach Height=".2044" Offset="1.5" Character="2" TerrainType="5"/>'
        text+='<LowBeach Height=".19226" Offset="1.5" Character="1" TerrainType="5"/>'
        text+='<Waterline Height=".19836" Offset="0" Character="0"/></CoastStyle>'
    return (text+'</CoastStyleList></CoastRoot>').encode('ascii')

def profile():
    return ''.join('['+format(400*(99-index)/99,'.9g')+','+str((index%11-5)/10)+',0]\r\n'for index in range(100)).encode('ascii')

def assets():
    schema=b'<?xml version="1.0"?><xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"></xs:schema>'
    return [(name,dds('BGRA8'if role in(1,2,3,4,7)else'BC1'if role==5 else'BC3')if role<=14 else
        styles()if role==15 else profile()if role<=24 else schema)for role,name in water.ROLES.items()]

def unchecked_package(values,deduplicate=True):
    blobs=[];refs=[]
    for name,data in values:
        match=next((i for i,b in enumerate(blobs)if b==data),None)if deduplicate else None
        if match is None:match=len(blobs);blobs.append(data)
        refs.append(match)
    out=bytearray(b'ZSWATER1'+struct.pack('<III',1,25,len(blobs)))
    for index,((name,data),blob)in enumerate(zip(values,refs),1):
        raw=name.encode('ascii');out.extend(struct.pack('<III',index,len(raw),blob)+raw)
    for data in blobs:out.extend(struct.pack('<I',len(data))+hashlib.sha256(data).digest()+data)
    return bytes(out)

def package(values=None):return water.encode_package(assets()if values is None else values)

def rejection_cases():
    base=package();cases=[]
    def add(label,data,sha=None):cases.append((label,bytes(data),sha))
    for size in(0,8,19,20,40,len(base)-1):add('truncated_'+str(size),base[:size])
    for offset,value,label in((0,0,'magic'),(8,2,'version'),(12,24,'role_count'),(16,0,'empty_blobs'),(16,26,'blob_bound'),
        (20,2,'role_order'),(24,0,'empty_name'),(24,65,'name_bound'),(28,1,'first_reference_order'),(28,25,'blob_reference_bound')):
        data=bytearray(base);struct.pack_into('<I',data,offset,value);add(label,data)
    data=bytearray(base);data[32]=ord('/');add('canonical_name',data)
    parsed=water.validate_package_bytes(base);first=parsed['blobs'][0]['offset']
    data=bytearray(base);data[first-32]^=1;add('blob_digest',data)
    data=bytearray(base);struct.pack_into('<I',data,first-36,5*1024*1024+1);add('blob_size_bound',data)
    add('outer_sha',base,'0'*64);add('outer_sha_length',base,'-');add('trailing',base+b'X')
    add('duplicate_unique_blob',unchecked_package(assets(),False))
    for offset,value,label in((4,123,'dds_header'),(8,0,'dds_flags'),(12,0,'dds_height'),(16,2049,'dds_width'),
        (24,1,'dds_volume'),(28,4,'dds_mip_bound'),(76,31,'dds_pixel_format'),(92,0,'dds_rgba_masks'),(112,0x200,'dds_cubemap')):
        values=assets();data=bytearray(values[0][1]);struct.pack_into('<I',data,offset,value);values[0]=(values[0][0],data)
        add(label,unchecked_package(values))
    def replace(role,data,label):
        values=assets();values[role-1]=(values[role-1][0],data);add(label,unchecked_package(values))
    replace(1,dds('BC1'),'dds_role_codec');replace(1,dds('BGRA8')+b'X','dds_trailing')
    xml=styles()
    for old,new,label in((b'Height=".2044"',b'Height="NaN"','xml_nan'),(b'Height=".2044"',b'Height="1e999"','xml_infinite'),
        (b'Height=".2044"',b'Height="1.1"','xml_height_bound'),(b'Offset="1.5"',b'Offset="-1"','xml_negative_offset'),
        (b'Character="2"',b'Character="9"','xml_character_bound'),(b'TerrainType="5"',b'TerrainType="65536"','xml_terrain_bound'),
        (b'HighSide="20"',b'HighSide="129"','xml_smoothing_bound'),(b'type="Default"',b'type="wrong"','xml_style_name'),
        (b'type="Default"',b'type="Default" type="Default"','xml_duplicate_attribute'),(b'Height=".2044" ',b'','xml_missing_attribute'),
        (b'coastcharacterspline_01_water.txt',b'../coastcharacterspline_01_water.txt','xml_character_path'),
        (b'<CoastRoot>',b'<!DOCTYPE CoastRoot><CoastRoot>','xml_dtd'),(b'<CoastRoot>',b'<!ENTITY evil "x"><CoastRoot>','xml_entity'),
        (b'Offset="1.5"',b'Offset="&evil;"','xml_entity_reference'),(b'<LowBeach',b'<Unknown','xml_tag')):
        replace(15,xml.replace(old,new,1),label)
    lines=profile().splitlines()
    for label,index,value in(('profile_nan',1,b'[395,NaN,0]'),('profile_infinite',1,b'[395,1e999,0]'),
        ('profile_y_bound',1,b'[395,65,0]'),('profile_z_nonzero',1,b'[395,0,1]'),('profile_duplicate_x',1,b'[400,0,0]'),
        ('profile_first_endpoint',0,b'[399,0,0]'),('profile_last_endpoint',99,b'[1,0,0]'),('profile_bracket',1,b'395,0,0]')):
        changed=list(lines);changed[index]=value;replace(16,b'\r\n'.join(changed),label)
    replace(16,b'\r\n'.join(lines[:-1]),'profile_99_points');replace(16,b'\r\n'.join(lines+[b'[0,0,0]']),'profile_101_points')
    replace(16,profile()+b'\0','profile_nul');replace(25,b'<!DOCTYPE xs:schema><xs:schema></xs:schema>','schema_dtd')
    return cases

def main():
    assert not(STAGE/'result.json').exists(),'Inspect existing owned results before restarting';STAGE.mkdir(parents=True,exist_ok=True)
    checks=0
    def check(value):
        nonlocal checks
        assert value;checks+=1
    raw=package();p=water.validate_package_bytes(raw,hashlib.sha256(raw).hexdigest());check(p['asset_count']==25)
    cases=rejection_cases()
    for label,data,sha in cases:
        try:water.validate_package_bytes(data,sha or hashlib.sha256(data).hexdigest())
        except(ValueError,UnicodeError,struct.error,water.ET.ParseError):checks+=1
        else:raise AssertionError(label)
    a,inputs,meta,lean=water.source_assets(GAME);real=water.validate_package_bytes(water.encode_package(a))
    check(real['asset_count']==25 and real['blob_count']==24 and real['assets'][15]['offset']==real['assets'][16]['offset'])
    check(real['included_lean_assets']==0 and sum(r['bytes']for r in lean)==3932298)
    for row in real['assets']:
        if'texture'in row:
            texture=row['texture'];check(texture['levels'][-1]['offset']+texture['levels'][-1]['bytes']==row['bytes'])
        if'profile'in row:check(row['profile']['count']==100 and row['profile']['ranges'][0]==[0,400]and row['profile']['ranges'][2]==[0,0])
    style=real['assets'][14]['styles'];check(len(style)==13 and style[11]['high_beach']['character']==6 and
        style[12]['waterline']['character']==65535 and style[0]['high_beach']['height']==.2244)
    pack=water.Fpk(GAME/water.PACK_MODELS);lean_cases=0
    for name in water.LEAN_SHA:
        data=pack.read(name)[0];check(water.validate_lean(data)['bytes_per_channel']==2)
        for offset,value in((4,0x7fc00000),(8,0),(20,3),(24,35),(28,0)):
            changed=bytearray(data);struct.pack_into('<I',changed,offset,value)
            try:water.validate_lean(changed)
            except ValueError:checks+=1;lean_cases+=1
            else:raise AssertionError('LEAN bound')
    water.write_new(STAGE/'format.json',dict(schema='zerosis.original_water_format.v1',magic='ZSWATER1',version=1,
        header='magic[8],u32 version(1),u32 roles(25),u32 unique_blob_count(1..25)',
        descriptor='u32 canonical_role,u32 ASCII_name_bytes,u32 blob_index,ASCII_name;25 records;blobs ordered by first reference',
        blob='u32 raw_size,SHA256[32],raw bytes;unique hashes;all blobs referenced',byte_order='little endian',
        max_package_bytes=water.MAX_PACKAGE_BYTES,package_bytes=real['bytes'],package_sha256=real['sha256'],blob_count=24,
        dds_parser='shared OriginalFog::DecodeTexture;BC1/BC3/BGRA8;full mip extent;absolute package offset and rowPitch',
        coast_parser='13 canonical styles;finite decimals;heights0..1,offset/smoothing0..128;character0..8/65535;terrain0..65535;DTD/entities rejected',
        profile_parser='9x100 ASCII triples;x400 descending to0,z0,y[-64,64];raw units preserved;geometry scale remains a candidate',
        lean_included=False,lean_excluded_bytes=3932298,original_discovery=water.artifact(STAGE/'discovery.json'),
        original_asset_metadata=meta,excluded_lean_metadata=lean,raw_retail_bytes_written_by_test=False,
        native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False))
    proof=dict(status='PASS_WATER_DDS_BLOB_SHA_XML_PROFILE_AND_EXCLUDED_LEAN_CHECKS',checks=checks,rejection_fixtures=len(cases),lean_rejections=lean_cases,
        package_bytes=real['bytes'],package_sha256=real['sha256'],roles=25,unique_blobs=24,source_inputs=inputs,
        format=water.artifact(STAGE/'format.json'),native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False)
    water.write_new(STAGE/'result.json',proof);print(json.dumps({k:proof[k]for k in('status','checks','rejection_fixtures','lean_rejections','package_bytes')}))

if __name__=='__main__':main()
