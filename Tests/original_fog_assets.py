"""Bounded file/parser checks and retail metadata; never starts native code."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import struct
import sys

sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[1]
sys.path.insert(0,str(PROJECT/'tools'))
import civ5_original_fog_assets as fog

STAGE=PROJECT/'evidence/world_terrain_original/phase2/assets'
GAME=Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V")

def dds(codec='BC3',width=4,height=4,mips=1,blocks=None):
    words=[0]*32;words[:8]=[int.from_bytes(b'DDS ','little'),124,0x21007,height,width,0,0,mips]
    words[19]=32;words[27]=0x1000
    if codec=='BGRA8':words[20:27]=[0x41,0,32,0xff0000,0xff00,0xff,0xff000000];block=0
    else:words[20:22]=[4,int.from_bytes(b'DXT1' if codec=='BC1' else b'DXT5','little')];block=8 if codec=='BC1' else 16
    size=sum(((max(1,width>>level)+3)//4)*((max(1,height>>level)+3)//4)*block if block else
        max(1,width>>level)*max(1,height>>level)*4 for level in range(mips))
    return struct.pack('<32I',*words)+(bytes(size) if blocks is None else blocks)

def tga(origin=8,footer=True):
    width,height=32,1024;pixels=bytearray(width*height*4)
    for index in range(width*height):
        x,y=index%width,index//width
        logical_x=width-1-x if origin&16 else x;logical_y=y if origin&32 else height-1-y
        logical=logical_y*width+logical_x
        r,g,b=logical%32,(logical//32)%32,logical//1024
        pixels[index*4:index*4+4]=bytes((3+8*b,3+8*g,3+8*r,255))
    header=struct.pack('<BBBHHBHHHHBB',0,0,2,0,0,0,0,0,width,height,32,origin)
    return header+pixels+(bytes(8)+b'TRUEVISION-XFILE.\0' if footer else b'')

def assets():
    return [(name,dds('BC1' if role==2 else 'BGRA8' if role in (4,6) else 'BC3') if role<=6 else
        tga() if role==7 else b'146,182,243\r\n' if role==8 else b'<?xml?><FluidFOWSettings></FluidFOWSettings>')
        for role,name in fog.ROLES.items()]

def package(asset_values=None):return fog.encode_package(assets() if asset_values is None else asset_values)

def rejection_cases():
    base=package();cases=[]
    def add(label,data,sha=None):cases.append((label,bytes(data),sha))
    for size in (0,8,15,16,45,len(base)-1):add('truncated_'+str(size),base[:size])
    for offset,value,label in ((0,0,'magic'),(8,2,'version'),(12,8,'missing_role'),(12,10,'extra_role'),
        (16,2,'role_order'),(20,0,'empty_name'),(20,65,'name_bound'),(24,0,'empty_asset'),(24,5*1024**2+1,'asset_bound')):
        value_bytes=bytearray(base);struct.pack_into('<I',value_bytes,offset,value);add(label,value_bytes)
    changed=bytearray(base);changed[28]^=1;add('asset_sha',changed)
    changed=bytearray(base);changed[60]=ord('/');add('noncanonical_name',changed)
    add('outer_sha',base,'0'*64);add('outer_sha_length',base,'-');add('trailing',base+b'X')
    for offset,value,label in ((4,123,'dds_header'),(8,0,'dds_flags'),(12,0,'zero_height'),(16,2049,'width_bound'),
        (24,1,'volume_rejected'),(28,4,'mips_bound'),(76,31,'pixel_format'),(80,0,'pixel_flags'),(84,0,'codec'),(112,0x200,'cube_rejected')):
        values=assets();raw=bytearray(values[0][1]);struct.pack_into('<I',raw,offset,value);values[0]=(values[0][0],raw)
        add(label,unchecked_package(values))
    for label,role,data in (
        ('codec_role',2,dds('BC3')),('rgba_masks',4,dds('BGRA8')[:92]+bytes(4)+dds('BGRA8')[96:]),
        ('dds_trailing',1,dds()+b'X'),('tga_short',7,b'TGA'),('tga_rle',7,tga()[:2]+b'\x0a'+tga()[3:]),
        ('tga_descriptor',7,tga()[:17]+b'\x00'+tga()[18:]),('tga_trailing',7,tga()+b'X'),
        ('csv_alpha',8,b'1,x,3'),('csv_range',8,b'1,2,256'),('csv_negative',8,b'-1,2,3'),
        ('csv_extra',8,b'1,2,3,4'),('xml_root',9,b'<?xml?><wrong/>')):
        values=assets();values[role-1]=(values[role-1][0],data);add(label,unchecked_package(values))
    return cases

def unchecked_package(values):
    output=bytearray(fog.MAGIC+struct.pack('<II',1,9))
    for role,(name,data) in enumerate(values,1):
        raw=name.encode('ascii');output.extend(struct.pack('<III',role,len(raw),len(data))+hashlib.sha256(data).digest()+raw+data)
    return bytes(output)

def write_new(path,value):
    with path.open('x',encoding='utf8') as stream:json.dump(value,stream,indent=2);stream.write('\n')

def main():
    assert not (STAGE/'result.json').exists(),'Inspect existing owned results before restarting'
    STAGE.mkdir(parents=True,exist_ok=True);checks=0
    def check(value):
        nonlocal checks
        assert value;checks+=1
    raw=package();parsed=fog.validate_package_bytes(raw,hashlib.sha256(raw).hexdigest())
    check(parsed['asset_count']==9 and parsed['fog_colour_bytes']==[146,182,243])
    cases=rejection_cases()
    for label,raw,supplied in cases:
        try:fog.validate_package_bytes(raw,supplied if supplied is not None else hashlib.sha256(raw).hexdigest())
        except (ValueError,UnicodeError,struct.error):checks+=1
        else:raise AssertionError(label)
    for descriptor in (8,24,40,56):check(fog.validate_tga(tga(descriptor))['origin_top']==bool(descriptor&32))
    check(fog.validate_tga(tga(8,False))['candidate_lut_edge']==32)
    check(fog.parse_fog_colour(b' 0 , 255 , 001\t\r\n')==[0,255,1])
    for codec in ('BC1','BC3','BGRA8'):
        meta=fog.validate_dds(dds(codec,5,3,3));check(meta['levels'][-1]['width']==1 and meta['levels'][-1]['height']==1)
    source,inputs,meta=fog.source_assets(GAME);encoded=fog.encode_package(source);real=fog.validate_package_bytes(encoded)
    check(real['fog_colour_bytes']==[146,182,243] and real['asset_count']==9)
    check(sum(row['bytes'] for row in meta)==sum(len(data) for _,data in source))
    identity=GAME/'Assets/colorkeys/Terrain_Generic_ColorKey.tga';identity_before=fog.artifact(identity)
    identity_raw=identity.read_bytes();identity_meta=fog.validate_tga(identity_raw)
    width,height=identity_meta['width'],identity_meta['height'];check(not identity_meta['origin_top'] and not identity_meta['origin_right'])
    for index in range(32768):
        at=18+((height-1-index//width)*width+index%width)*4
        check(identity_raw[at:at+4]==bytes((3+8*(index//1024),3+8*((index//32)%32),3+8*(index%32),255)))
    check(fog.artifact(identity)==identity_before)
    same_keys=[]
    for file in sorted((GAME/'Assets/colorkeys').glob('Terrain[Ff][Oo][Ww]_*_ColorKey.tga')):
        row=fog.artifact(file);check(row['sha256']==fog.SOURCE_SHA[7]);same_keys.append(row)
    check(len(same_keys)==5)
    write_new(STAGE/'format.json',dict(schema='zerosis.original_fog_format.v1',magic='ZSFOG001',version=1,
        header='magic[8],u32 version,u32 record_count(9)',record='u32 role,u32 name_bytes,u32 raw_bytes,sha256[32],ASCII canonical name,raw bytes',
        byte_order='little endian',max_package_bytes=fog.MAX_PACKAGE_BYTES,package_bytes=real['bytes'],package_sha256=real['sha256'],
        roles=real['assets'],source_assets=meta,inputs=inputs,fow_colour_key_aliases=same_keys,
        fog_colour_csv='exactly three unsigned 1..3 digit decimal bytes, comma separated; ASCII space/tab/CR/LF allowed; each <=255; output RGB /255',
        lut_candidate=dict(input='one identical original TerrainFOW key',method='standard TGA origin to top-left; first32768 BGRA pixels converted to RGBA;32x32x32,R/x fastest',
            identity_evidence=identity_before,identity_pixels_compared=32768,identity_formula='B=3+8*z,G=3+8*y,R=3+8*x,A=255',
            retail_loader_and_sampler_equivalence_verified=False),
        fow_base_layer='generated mask/cloud render layer; no independent retail file found',
        raw_retail_bytes_written=False,native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False))
    proof=dict(status='PASS_FOG_ASSET_BOUNDS_SHA_LAYOUT_AND_RETAIL_METADATA',checks=checks,rejection_fixtures=len(cases),
        package_bytes=real['bytes'],package_sha256=real['sha256'],assets=9,raw_retail_bytes_written=False,
        source_inputs=inputs,format=fog.artifact(STAGE/'format.json'),native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False)
    write_new(STAGE/'result.json',proof)
    print(json.dumps({key:proof[key] for key in ('status','checks','rejection_fixtures','package_bytes','package_sha256')}))

if __name__=='__main__':main()
