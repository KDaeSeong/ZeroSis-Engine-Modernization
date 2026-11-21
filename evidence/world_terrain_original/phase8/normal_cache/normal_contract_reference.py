"""Independent float32 goldens from the bounded original expression DAG."""
from functools import lru_cache
import math
from pathlib import Path
import struct
from normal_contract_pe import Image
from normal_contract_bulk_dag import analyze, sum_terms, coefficients


def f32(value):return struct.unpack('<f',struct.pack('<f',value))[0]
def bits(value):return struct.unpack('<I',struct.pack('<f',value))[0]
def float_literal(value):
    text=format(value,'.9g')
    if '.' not in text and 'e' not in text:text+='.0'
    return text+'f'


class Reference:
    def __init__(self):
        self.image=Image(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V\CivilizationV_DX11.exe")
        self.graphs=analyze(self.image)
        assert [address for address,_,_ in self.graphs]==[0x7293d8,0x729495]
        self.a=[f32(value) for value in (.0228,.2293,.4948,.2293,.0228)]
        self.b=[f32(value) for value in (.0702,.3526,0,-.3526,-.0702)]
        self.reciprocal=f32(1/255)

    def compute(self,raw,metrics):
        assert len(raw)==25
        center=f32(raw[12]*self.reciprocal)
        dx=(int(raw[17])-int(raw[7]))//2
        dy=(int(raw[13])-int(raw[11]))//2
        cache={}
        def evaluate(node):
            identity=id(node)
            if identity in cache:return cache[identity]
            op=node[0]
            if op=='input':value={0:1.,1:0.,2:f32(1.03),3:f32(-10/3),4:f32(1/16384),5:.5,7:self.reciprocal}[node[1]]
            elif op=='stack':value={0x4a0:dx,0x530:dy,0xa0:0.,0xb0:self.reciprocal,0xf0:-2.,0x110:center}[node[1]]
            elif op=='memory':
                base,offset=node[1:]
                if base=='eax':offset=-0xc0+offset
                elif base=='ecx':offset=-0x80+offset
                else:assert base=='esi'
                choices=[(x,y) for x in range(-2,3) for y in range(-2,3) if (x-1)*64+y*4==offset]
                assert len(choices)==1
                x,y=choices[0];value=f32(raw[(x+2)*5+y+2]*self.reciprocal)
            elif op=='coefficient':
                offset=node[1]
                if offset<0xffcc:
                    x,y=divmod((offset-0xff68)//4,5);value=f32(self.b[x]*self.a[y])
                else:
                    x,y=divmod((offset-0xffcc)//4,5);value=f32(self.a[x]*self.b[y])
            elif op=='float':value=f32(evaluate(node[1]))
            else:
                left,right=evaluate(node[1]),evaluate(node[2])
                if op=='andps':value=abs(left)
                elif op=='addps':value=f32(left+right)
                elif op=='subps':value=f32(left-right)
                elif op=='mulps':value=f32(left*right)
                elif op=='divps':value=f32(left/right)
                else:raise ValueError(op)
            cache[identity]=value;return value
        derivative=[f32(evaluate(numerator)/evaluate(denominator)) for _,numerator,denominator in self.graphs]
        def terms(node):return terms(node[1])+terms(node[2]) if node[0]=='addps' else [node]
        self.last_terms=[[(coefficients(node),evaluate(node)) for node in terms(numerator)] for _,numerator,_ in self.graphs]
        sx,sy,hs=map(f32,metrics)
        values=[f32(sy*f32(derivative[0]*hs)),f32(sx*f32(derivative[1]*hs)),f32(sy*sx)]
        length=math.sqrt(sum(value*value for value in values))
        normal=[f32(value/length) for value in values]
        half=[struct.unpack('<H',struct.pack('<e',value))[0] for value in normal]
        return derivative,normal,half

    def fixtures(self):
        windows=[]
        for value in (0,1,15300,32768,65535):windows.append([value]*25)
        for sx,sy in ((255,0),(0,255),(-257,513),(1024,-768)):
            windows.append([max(0,min(65535,25000+x*sx+y*sy)) for x in range(-2,3) for y in range(-2,3)])
        for case in range(39):
            windows.append([((case+11)*7919+(index+3)*15427+index*index*2971)%65536 for index in range(25)])
        metrics=[(1/64,f32(.866025404)/64,f32(2.3*255/65535)),(1.,2.,1/255),(1/64,1/64,0.)]
        result=[]
        for raw in windows:
            for metric in metrics:
                derivative,normal,half=self.compute(raw,metric)
                result.append(dict(raw=raw,metrics=list(map(f32,metric)),derivative=derivative,normal=normal,half=half))
        return result

    def header(self,path):
        rows=self.fixtures()
        text='#pragma once\nstruct NormalGolden{std::array<std::uint16_t,25> raw;float sx,sy,hs,dx,dy,nx,ny,nz;std::array<std::uint16_t,3> half;};\nconstexpr NormalGolden NormalGoldens[]={\n'
        for row in rows:
            numbers=row['metrics']+row['derivative']+row['normal']
            text+='{{{'+','.join(map(str,row['raw']))+'}},'+','.join(map(float_literal,numbers))+',{{'+','.join(map(str,row['half']))+'}}},\n'
        text+='};\n'
        with Path(path).open('x',encoding='ascii',newline='\n') as stream:stream.write(text)
        return rows
