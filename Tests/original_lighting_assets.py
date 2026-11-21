"""Independent bounded lighting-package fixtures and BC1 reference decoder."""
from __future__ import annotations
import hashlib
from pathlib import Path
import struct
import sys

PROJECT=Path(__file__).absolute().parents[1]
sys.path.insert(0,str(PROJECT/'tools'))
import civ5_original_lighting_assets as lighting

def cube(width=8):
    words=[0]*32;words[0]=int.from_bytes(b'DDS ','little');words[1]=124;words[2]=0x21007;words[3]=words[4]=width
    words[7]=width.bit_length();words[19]=32;words[20]=4;words[21]=0x31545844;words[27]=0x401008;words[28]=0xfe00
    data=bytearray(struct.pack('<32I',*words))
    for face in range(6):
        for mip in range(width.bit_length()):
            size=max(1,width>>mip)
            for block in range(((size+3)//4)**2):
                data.extend(struct.pack('<HHI',0xf800 if (face+mip+block)%2 else 0x001f,0x07e0,0xe4e4e4e4))
    return bytes(data)

def tga(desc=8):
    width,height=256,128;raw=bytearray(struct.pack('<BBBHHBHHHHBB',0,0,2,0,0,0,0,0,width,height,32,desc))
    for i in range(width*height):raw.extend(bytes((i&255,(i>>8)&255,(i*13)&255,255)))
    return bytes(raw)

def wire(assets):
    blobs=[];indices={};descriptors=bytearray()
    for role in range(1,16):
        data=assets[role];sha=hashlib.sha256(data).digest();name=lighting.ROLES[role].encode('ascii')
        if sha not in indices:indices[sha]=len(blobs);blobs.append((sha,data))
        descriptors.extend(struct.pack('<III',role,len(name),indices[sha])+name)
    raw=bytearray(lighting.MAGIC+struct.pack('<III',1,15,len(blobs))+descriptors)
    for sha,data in blobs:raw.extend(struct.pack('<I',len(data))+sha+data)
    return bytes(raw)

def assets(c=None,t=None):
    c=cube()if c is None else c;t=tga()if t is None else t
    return {**{i:c for i in range(1,11)},**{i:t for i in range(11,16)}}

def mutate(data,offset,value,fmt='<I'):
    raw=bytearray(data);struct.pack_into(fmt,raw,offset,value);return bytes(raw)

def cases():
    base=wire(assets());parsed=lighting.validate_package_bytes(base);blob=parsed['blobs'][0];data=cube();t=tga()
    result=[dict(label='valid_shared',data=base,accepted=True)]
    def add(label,raw,accepted=False,sha=None):result.append(dict(label=label,data=raw,accepted=accepted,supplied_sha256=sha))
    add('outer_sha',base,sha='0'*64)
    for length in(0,4,8,12,16,19,20,43,100,512,len(base)-1):add('truncated_'+str(length),base[:length])
    for label,offset,value in(('version',8,2),('count',12,14),('blobs_zero',16,0),('blobs_many',16,16),('role_zero',20,0),('role_order',20,2),
        ('name_zero',24,0),('name_long',24,65),('blob_range',28,2),('blob_first_reference',28,1),('unreferenced_blob',16,3)):
        add(label,mutate(base,offset,value))
    add('magic',b'BADMAGIC'+base[8:]);add('name',base[:32]+b'X'+base[33:]);add('trailing',base+b'X')
    add('blob_sha',mutate(base,blob['offset']-1,0,'<B'));add('blob_empty',mutate(base,blob['offset']-36,0))
    add('blob_big',mutate(base,blob['offset']-36,300001));add('oversized',b'\0'*(lighting.MAX_PACKAGE_BYTES+1))
    for offset,value in((4,123),(8,0),(12,7),(16,129),(24,1),(28,3),(76,31),(80,0),(84,0x35545844),(88,32),(108,0),(112,0x200)):
        add('cube_header_'+str(offset),wire(assets(c=mutate(data,offset,value))))
    add('cube_truncated',wire(assets(c=data[:-1])));add('cube_trailing',wire(assets(c=data+b'X')))
    for offset,value in((0,1),(1,1),(2,10),(16,24),(17,0)):
        bad=bytearray(t);bad[offset]=value;add('tga_header_'+str(offset),wire(assets(t=bytes(bad))))
    for offset,value in((12,0),(14,0),(12,1)):
        add('tga_dimension_'+str(offset)+'_'+str(value),wire(assets(t=mutate(t,offset,value,'<H'))))
    add('tga_truncated',wire(assets(t=t[:-1])));add('tga_trailing',wire(assets(t=t+b'X')))
    add('tga_invalid_footer',wire(assets(t=t+b'\0'*26)))
    for desc in(8,24,40,56):add('valid_origin_'+str(desc),wire(assets(t=tga(desc))),True)
    for width in(1,4,16):add('valid_cube_'+str(width),wire(assets(c=cube(width))),True)
    return result

def bc1_rgba(raw,width,height):
    def rgb(value):
        r=(value>>11)&31;g=(value>>5)&63;b=value&31
        return(r*8+r//4,g*4+g//16,b*8+b//4,255)
    result=bytearray(width*height*4);blocks=(width+3)//4
    for by in range((height+3)//4):
        for bx in range(blocks):
            c0,c1,indices=struct.unpack_from('<HHI',raw,(by*blocks+bx)*8);a,b=rgb(c0),rgb(c1)
            if c0>c1:palette=(a,b,tuple((2*a[i]+b[i])//3 for i in range(3))+(255,),tuple((a[i]+2*b[i])//3 for i in range(3))+(255,))
            else:palette=(a,b,tuple((a[i]+b[i])//2 for i in range(3))+(255,),(0,0,0,0))
            for y in range(min(4,height-by*4)):
                for x in range(min(4,width-bx*4)):
                    i=((by*4+y)*width+bx*4+x)*4;result[i:i+4]=bytes(palette[(indices>>(2*(y*4+x)))&3])
    return bytes(result)

def run():
    rows=[]
    for case in cases():
        raw=case['data'];sha=case.get('supplied_sha256')or hashlib.sha256(raw).hexdigest();accepted=True
        try:lighting.validate_package_bytes(raw,sha)
        except(ValueError,UnicodeError,struct.error):accepted=False
        assert accepted==case['accepted'],case['label']
        rows.append(dict(label=case['label'],accepted=accepted,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),supplied_sha256=sha))
    return rows

if __name__=='__main__':print('PASS_LIGHTING_PYTHON_FIXTURES cases='+str(len(run())))
