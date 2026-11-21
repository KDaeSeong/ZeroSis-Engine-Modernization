"""Small standard-library-only CPU preview of original retained sprite packets.

Nearest-neighbor sampling is an explicit diagnostic convention, not a claim of
matching the retail sampler. No image library, window, game or GPU is loaded.
"""
from __future__ import annotations
import math
import json
from pathlib import Path
import struct
import zlib


def dds(path):
    from civ5_ui_assets import header,decode_dxt1_top_mip,decode_dxt5_top_mip
    data=Path(path).read_bytes();words=header(data);width,height=words[4],words[3]
    fourcc=words[21].to_bytes(4,'little')
    if fourcc==b'DXT1':pixels,_=decode_dxt1_top_mip(data,words)
    elif fourcc==b'DXT5':pixels,_=decode_dxt5_top_mip(data,words)
    elif words[20]==2 and words[22:27]==[8,0,0,0,255]:
        alpha=data[128:128+width*height]
        if len(alpha)!=width*height:raise ValueError('Original A8 glyph atlas is incomplete')
        pixels=bytearray(b'\xff'*(width*height*4));pixels[3::4]=alpha
    else:
        if words[22:27] not in ([32,0xff0000,0xff00,0xff,0xff000000], [32,0xff,0xff00,0xff0000,0xff000000]):
            raise ValueError('CPU proof requires a bounded BGRA/RGBA8 original DDS')
        pixels=data[128:128+width*height*4]
        if words[23]==0xff:
            bgra=bytearray(pixels);bgra[0::4]=pixels[2::4];bgra[2::4]=pixels[0::4];pixels=bytes(bgra)
    if width<=0 or height<=0 or len(pixels)!=width*height*4:raise ValueError('CPU DDS top mip is incomplete')
    return width,height,pixels


def png_bytes(width,height,bgra):
    rgba=bytearray(bgra);rgba[0::4]=bgra[2::4];rgba[2::4]=bgra[0::4]
    rows=b''.join(b'\0'+rgba[y*width*4:(y+1)*width*4] for y in range(height))
    def chunk(kind,payload):
        return struct.pack('>I',len(payload))+kind+payload+struct.pack('>I',zlib.crc32(kind+payload)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>2I5B',width,height,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(rows,9))+chunk(b'IEND',b'')


def render(packet,png,asset_root,line_records=None):
    from menu_frontend_assets import artifact
    data=Path(packet).read_bytes();root=Path(asset_root).resolve(strict=True)
    if data[:8]!=b'ZSUPIX02':raise ValueError('Component output is not the actual sprite packet')
    width,height,textures,sprites,hits,scrolls=struct.unpack_from('<6I',data,8)
    if (width,height)!=(1920,1080) or textures>64 or sprites>10000 or hits>4096 or scrolls>4096:raise ValueError('Unbounded CPU proof packet')
    pos=32;paths=[];decoded={}
    for _ in range(textures):
        length,=struct.unpack_from('<I',data,pos);pos+=4
        path=Path(data[pos:pos+length].decode('utf8'));pos+=length
        if not path.is_absolute() or not path.resolve(strict=True).is_relative_to(root):raise ValueError('CPU proof escaped the exact original asset pack')
        paths.append(path)
    canvas=bytearray(width*height*4)
    lines=[]
    if line_records is not None:
        document=json.loads(Path(line_records).read_text('utf8'))
        if document.get('schema')!='zerosis.scene_line.diagnostic.v1':raise ValueError('Unknown diagnostic line format')
        lines=document['lines']
    if len(lines)>8192:raise ValueError('Unbounded CPU diagnostic line count')
    previous=0
    for line in lines:
        anchor=line['beforeSprite'];values=[*line['start'],*line['end'],line['width'],*line['rgba'],*line['clip']]
        if type(anchor) is not int or anchor<previous or anchor>sprites or len(line['start'])!=2 or len(line['end'])!=2 or len(line['rgba'])!=4 or len(line['clip'])!=4 or not all(math.isfinite(x) for x in values):raise ValueError('Invalid CPU diagnostic line')
        if any(abs(x)>1e7 for x in [*line['start'],*line['end'],*line['clip']]):raise ValueError('CPU diagnostic line coordinates exceed the production bounds')
        if not 0<line['width']<=256 or any(not 0<=x<=1 for x in line['rgba']) or not line['clip'][2]>line['clip'][0] or not line['clip'][3]>line['clip'][1]:raise ValueError('Invalid CPU diagnostic stroke')
        previous=anchor
    pixel_budget=[20000000]
    def blend(x,y,color):
        pixel_budget[0]-=1
        if pixel_budget[0]<0:raise ValueError('CPU diagnostic line pixel budget exceeded')
        r,g,b,a=[round(x*255) for x in color]
        if not a:return
        dest=(y*width+x)*4;db,dg,dr,da=canvas[dest:dest+4];remaining=255-a;oa=a+(da*remaining+127)//255
        if oa:canvas[dest:dest+4]=bytes(((b*a+(db*da*remaining+127)//255+oa//2)//oa,(g*a+(dg*da*remaining+127)//255+oa//2)//oa,(r*a+(dr*da*remaining+127)//255+oa//2)//oa,oa))
    def draw_line(line):
        x,y=line['start'];ex,ey=line['end'];dx,dy=ex-x,ey-y;radius=line['width']/2
        if dx==0 and dy==0:return
        left=max(0,line['clip'][0]);top=max(0,line['clip'][1]);right=min(width,line['clip'][2]);bottom=min(height,line['clip'][3])
        if right<=left or bottom<=top:return
        first,last=0.,1.
        for slope,distance in [(-dx,x-left+radius),(dx,right-x+radius),(-dy,y-top+radius),(dy,bottom-y+radius)]:
            if slope==0:
                if distance<0:return
            elif slope<0:first=max(first,distance/slope)
            else:last=min(last,distance/slope)
            if first>last:return
        sx,sy=x+first*dx,y+first*dy;tx,ty=x+last*dx,y+last*dy
        steps=max(1,math.ceil(max(abs(tx-sx),abs(ty-sy))));seen=set();thickness=max(1,round(line['width']))
        for step in range(steps+1):
            center_x=math.floor(sx+(tx-sx)*step/steps);center_y=math.floor(sy+(ty-sy)*step/steps)
            for yy in range(center_y-(thickness-1)//2,center_y+thickness//2+1):
                for xx in range(center_x-(thickness-1)//2,center_x+thickness//2+1):
                    if left<=xx<right and top<=yy<bottom and (xx,yy) not in seen:seen.add((xx,yy));blend(xx,yy,line['rgba'])
    line_index=0
    for sprite_index in range(sprites):
        while line_index<len(lines) and lines[line_index]['beforeSprite']==sprite_index:draw_line(lines[line_index]);line_index+=1
        texture,key,*values=struct.unpack_from('<IQ16f',data,pos);pos+=76
        source,target,clip,tint=values[:4],values[4:8],values[8:12],values[12:]
        if not all(math.isfinite(value) for value in values) or any(value<0 or value>1 for value in tint):raise ValueError('Invalid CPU scene geometry/tint')
        left=max(0,math.ceil(target[0]),math.ceil(clip[0]));top=max(0,math.ceil(target[1]),math.ceil(clip[1]))
        right=min(width,math.ceil(target[2]),math.ceil(clip[2]));bottom=min(height,math.ceil(target[3]),math.ceil(clip[3]))
        if right<=left or bottom<=top:continue
        solid=texture==0xffffffff
        if not solid:
            if texture not in decoded:decoded[texture]=dds(paths[texture])
            tw,th,pixels=decoded[texture]
            if source[0]<0 or source[1]<0 or source[2]>tw or source[3]>th:raise ValueError('Original atlas sample escaped its dimensions')
            xscale=(source[2]-source[0])/(target[2]-target[0]);yscale=(source[3]-source[1])/(target[3]-target[1])
            xs=[min(tw-1,int(source[0]+(x+0.5-target[0])*xscale))*4 for x in range(left,right)]
        for y in range(top,bottom):
            row=(y*width+left)*4
            if not solid:
                sy=min(th-1,int(source[1]+(y+0.5-target[1])*yscale))*tw*4
            for offset in range(right-left):
                if solid:b,g,r,a=round(tint[2]*255),round(tint[1]*255),round(tint[0]*255),round(tint[3]*255)
                else:
                    pixel=sy+xs[offset];b,g,r,a=pixels[pixel:pixel+4]
                    b,g,r,a=round(b*tint[2]),round(g*tint[1]),round(r*tint[0]),round(a*tint[3])
                if a:
                    dest=row+offset*4;db,dg,dr,da=canvas[dest:dest+4];remaining=255-a
                    oa=a+(da*remaining+127)//255
                    if oa:
                        canvas[dest:dest+4]=bytes(((b*a+(db*da*remaining+127)//255+oa//2)//oa,
                            (g*a+(dg*da*remaining+127)//255+oa//2)//oa,
                            (r*a+(dr*da*remaining+127)//255+oa//2)//oa,oa))
    while line_index<len(lines):draw_line(lines[line_index]);line_index+=1
    if pos+(hits+scrolls)*24!=len(data):raise ValueError('CPU proof packet has trailing data')
    output=png_bytes(width,height,canvas);png=Path(png)
    if png.exists():
        if png.read_bytes()!=output:raise ValueError('Existing CPU proof differs; explicit changed-image review is required')
    else:png.write_bytes(output)
    return dict(image=artifact(png),sprites=sprites,lines=len(lines),texture_bank=textures,renderer='PYTHON_STANDARD_LIBRARY_CPU_ONLY',
                sampling='NEAREST_NEIGHBOR_DIAGNOSTIC_CANDIDATE',runtime_pixel_acceptance=False)
