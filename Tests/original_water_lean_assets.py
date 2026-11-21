"""Bounded one-water-LEAN package/layout checks without native execution."""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path
import struct
import sys

sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[1]
sys.path.insert(0,str(PROJECT/'tools'))
import civ5_original_water_lean_assets as lean

STAGE=PROJECT/'evidence/world_terrain_original/phase4/assets'
GAME=Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V")

def texture(width=2,height=2,scale=.5,padding=b'\xcc\x55\xff'):
    mips=max(width,height).bit_length();texels=sum(max(1,width>>level)*max(1,height>>level)for level in range(mips))
    header=b'LEAN'+struct.pack('<f6I',scale,width,height,mips,2,36,36+texels*8)+b'\1'+padding
    rgba=b''.join(struct.pack('<4H',0 if i%2==0 else 65535,65535 if i%2==0 else 0,32768,16384)for i in range(texels))
    cross=b''.join(struct.pack('<H',i*7919%65536)for i in range(texels));return header+rgba+cross

def unchecked_package(data,name='waterbumps16.lean',role=1):
    raw=name.encode('ascii');return b'ZSWLEAN1'+struct.pack('<IIIII',1,1,role,len(raw),len(data))+hashlib.sha256(data).digest()+raw+data

def package(data=None):return lean.encode_package(texture()if data is None else data)

def rejection_cases():
    base=package();cases=[]
    def add(label,data,sha=None):cases.append((label,bytes(data),sha))
    for size in(0,8,15,16,59,76,len(base)-1):add('truncated_'+str(size),base[:size])
    for offset,value,label in((0,0,'magic'),(8,2,'version'),(12,0,'empty_count'),(12,2,'unexpected_count2'),(12,3,'unexpected_count3'),
        (16,0,'role0'),(16,2,'reserved_role2'),(16,3,'reserved_role3'),(20,0,'empty_name'),(20,65,'name_bound'),(24,45,'short_asset'),(24,4*1024**2+1,'asset_bound')):
        data=bytearray(base);struct.pack_into('<I',data,offset,value);add(label,data)
    data=bytearray(base);data[28]^=1;add('asset_sha',data)
    add('outer_sha',base,'0'*64);add('outer_sha_length',base,'-');add('trailing',base+b'X')
    for name in('../waterbumps16.lean','Waterbumps16.lean','waterbumps16.lean\0','riverrough16.lean'):
        add('canonical_name_'+repr(name),unchecked_package(texture(),name))
    for offset,value,label in((0,0,'lean_magic'),(4,0x7fc00000,'nan_scale'),(4,0x7f800000,'infinite_scale'),(4,0,'zero_scale'),
        (4,0xbf800000,'negative_scale'),(4,0x41880000,'scale_bound'),(8,0,'zero_width'),(8,1025,'width_bound'),(12,0,'zero_height'),
        (16,0,'zero_mips'),(16,1,'incomplete_mips'),(16,12,'mips_bound'),(20,1,'8bit_rejected'),(20,4,'channel_bytes'),
        (24,35,'first_offset'),(28,0,'second_offset')):
        raw=bytearray(texture());struct.pack_into('<I',raw,offset,value);add(label,unchecked_package(raw))
    for value in(0,2,255):
        data=bytearray(texture());data[32]=value;add('unsupported_flag_'+str(value),unchecked_package(data))
    add('raw_trailing',unchecked_package(texture()+b'X'));add('raw_truncated',unchecked_package(texture()[:-1]));return cases

def main():
    assert not(STAGE/'lean_result.json').exists(),'Inspect existing owned result before restarting';STAGE.mkdir(parents=True,exist_ok=True);checks=0
    def check(value):
        nonlocal checks
        assert value;checks+=1
    raw=package();meta=lean.validate_package_bytes(raw,hashlib.sha256(raw).hexdigest());check(meta['asset_count']==1)
    cases=rejection_cases()
    for label,data,sha in cases:
        try:lean.validate_package_bytes(data,sha or hashlib.sha256(data).hexdigest())
        except(ValueError,UnicodeError,struct.error):checks+=1
        else:raise AssertionError(label)
    for width,height in((1,1),(2,2),(5,3),(8,1)):
        t=lean.validate_texture(texture(width,height));check(t['mips']==max(width,height).bit_length())
        for plane in t['planes']:
            check(all(level['slice_pitch']==level['bytes']==level['row_pitch']*level['height']for level in plane['levels']))
    data,source,metadata=lean.source_asset(GAME);encoded=lean.encode_package(data);real=lean.validate_package_bytes(encoded)
    check(real['bytes']==3495363 and real['asset_count']==1);check(real['assets'][0]['sha256']==lean.SOURCE_SHA)
    t=real['assets'][0]['texture'];check(t['width']==t['height']==512 and t['mips']==10)
    check(t['output_scale']==struct.unpack('<f',struct.pack('<f',.33))[0])
    check(len(t['planes'])==2 and t['planes'][0]['channels']==4 and t['planes'][1]['channels']==1)
    ranges=[]
    for plane in t['planes']:
        low=65535;high=0;words=0
        for level in plane['levels']:
            values=struct.iter_unpack('<H',data[level['offset']:level['offset']+level['bytes']])
            for value, in values:low=min(low,value);high=max(high,value);words+=1
            check(level['package_offset']==real['assets'][0]['offset']+level['offset'])
        ranges.append(dict(channels=plane['channels'],minimum_word=low,maximum_word=high,normalised_minimum=low/65535,normalised_maximum=high/65535,words=words))
    lean.write_new(STAGE/'lean_format.json',dict(schema='zerosis.original_water_lean_format.v1',magic='ZSWLEAN1',version=1,
        header='magic[8],u32 version=1,u32 count=1',record='u32 role=1,u32 ASCII_name_bytes,u32 raw_size,SHA256[32],canonical name,raw LEAN',
        byte_order='little endian',max_package_bytes=lean.MAX_PACKAGE_BYTES,max_asset_bytes=lean.MAX_ASSET_BYTES,
        package_preview=real,source=source,source_metadata=metadata,normalised_ranges=ranges,
        decoder='u16LE/65535;mean=(2R-1,2G-1);second=(B,A,2crossR-1);mirrorX negates meanX/cross only',
        scale='DecodeMoments explicit S:mean/S,second/S^2;default S1 for optics;MixLayers applies runtime S once;header.scale binding remains candidate',
        excluded_river_raw_bytes=lean.EXCLUDED_RIVER_BYTES,duplicated_water_dds=0,raw_retail_bytes_written_by_test=False,
        native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False))
    proof=dict(status='PASS_WATER_LEAN_RAW_SHAPE_FULL_MIPS_BOUNDS_AND_RETAIL_PROVENANCE',checks=checks,rejection_fixtures=len(cases),
        package_bytes=real['bytes'],package_sha256=real['sha256'],asset_count=1,normalised_ranges=ranges,source=source,
        format=lean.artifact(STAGE/'lean_format.json'),native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False)
    lean.write_new(STAGE/'lean_result.json',proof);print(json.dumps({k:proof[k]for k in('status','checks','rejection_fixtures','package_bytes','package_sha256')}))

if __name__=='__main__':main()
