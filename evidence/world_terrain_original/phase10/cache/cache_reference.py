"""Independent matrix expression checks and constants from the original PE data."""
from pathlib import Path
import hashlib
import json
import re
import struct
import sys

sys.dont_write_bytecode = True
ROOT=Path(__file__).absolute().parent
PROJECT=ROOT.parents[3]
sys.path.insert(0,str(PROJECT/'evidence/world_terrain_original/phase8/normal_cache'))
from normal_contract_pe import Image


def terms(expression):
    return terms(expression[1])+terms(expression[2]) if expression[0]=='+' else [expression]


def product_proof(image):
    # Symbolic register expressions only; original instructions are not executed.
    registers={}
    stack={}
    for instruction in image.instructions(0x6ea039,0x6ea0a8):
        text=instruction.op_str
        source=re.fullmatch(r'(e[a-z]{2}), dword ptr \[eax(?: \+ (0x[0-9a-f]+|[0-9]+))?\]',text)
        store=re.fullmatch(r'dword ptr \[esp \+ (0x[0-9a-f]+|[0-9]+)\], (e[a-z]{2})',text)
        assert instruction.mnemonic=='mov'
        if source:
            offset=int(source[2] or '0',0)//4
            registers[source[1]]=('B',offset//4,offset%4)
        elif store:stack[int(store[1],0)-12]=registers[store[2]]
        else:raise AssertionError(text)
    registers={}
    output={}
    def value(text):
        if text in registers:return registers[text]
        match=re.fullmatch(r'dword ptr \[esp \+ (0x[0-9a-f]+|[0-9]+)\]',text)
        if match:return stack[int(match[1],0)]
        match=re.fullmatch(r'dword ptr \[ecx(?: ([+-]) (0x[0-9a-f]+|[0-9]+))?\]',text)
        if match:
            offset=int(match[2] or '0',0)*(-1 if match[1]=='-' else 1)
            return ('A',(offset+8)//4)
        raise AssertionError(text)
    for instruction in image.instructions(0x6ea0c0,0x6ea164):
        target,source=instruction.op_str.split(', ',1)
        if instruction.mnemonic=='mov':
            match=re.fullmatch(r'dword ptr \[edx(?: ([+-]) (0x[0-9a-f]+|[0-9]+))?\]',target)
            if match:
                offset=int(match[2] or '0',0)*(-1 if match[1]=='-' else 1)
                output[(offset+4)//4]=value(source)
            else:registers[target]=value(source)
        elif instruction.mnemonic in ('imul','add'):
            registers[target]=('*' if instruction.mnemonic=='imul' else '+',registers[target],value(source))
        else:raise AssertionError(instruction.mnemonic+' '+instruction.op_str)
    result=[]
    for column in range(4):
        pairs=[]
        for term in terms(output[column]):
            assert term[0]=='*'
            a,b=term[1:]
            if a[0]=='B':a,b=b,a
            assert a[0]=='A' and b==('B',a[1],column)
            pairs.append([a[1],b[1],b[2]])
        assert sorted(pair[0] for pair in pairs)==[0,1,2,3]
        result.append(dict(output_column=column,ordered_terms=pairs))
    tail={x.address:x.mnemonic+' '+x.op_str for x in image.instructions(0x6ea164,0x6ea1a5)}
    assert tail[0x6ea164]=='add ecx, 0x10' and tail[0x6ea167]=='add edx, 0x10'
    assert tail[0x6ea189]=='rep movsd dword ptr es:[edi], dword ptr [esi]'
    assert tail[0x6ea196]=='rep movsd dword ptr es:[edi], dword ptr [esi]'
    return result


def multiply(a,b):
    return [[sum(a[row][k]*b[k][column] for k in range(4)) for column in range(4)] for row in range(4)]


class Reference:
    def __init__(self):
        self.image=Image(Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V\CivilizationV_DX11.exe"))
        self.product=product_proof(self.image)
        self.rotation_coefficients=list(struct.unpack('<6i',self.image.read(0xa3eb0c,24)))
        assert self.rotation_coefficients==[0,1,1,0,-1,-1]
        rotation=[[0]*4 for _ in range(4)]
        i,j=self.rotation_coefficients[2],self.rotation_coefficients[4]
        rotation[0][1]=rotation[1][2]=rotation[2][0]=-i
        rotation[0][2]=rotation[1][0]=rotation[2][1]=j
        rotation[3][3]=1
        self.matrices=[]
        self.tables={}
        for translation,index in [([0,0,0],0),([1,-3,2],2),([-4,0,4],6),([-2,-3,5],9)]:
            table=list(struct.unpack('<16i',self.image.read(0xc90150+index*64,64)))
            self.tables[index]=table
            mirror=[table[row*4:row*4+4] for row in range(4)]
            shift=[[int(row==column) for column in range(4)] for row in range(4)]
            shift[3][:3]=translation
            self.matrices.append(multiply(multiply(shift,rotation),mirror))
        assert [self.matrices[i][3][:3] for i in range(4)]==[[0,0,0],[-2,3,-1],[4,0,-4],[2,3,-5]]
        self.image.finish()

    def header(self,path):
        rows=['#pragma once','static const int OriginalOrientationGolden[4][16]={']
        rows += ['{'+','.join(str(x) for row in matrix for x in row)+'},' for matrix in self.matrices]
        rows += ['};']
        with Path(path).open('x',encoding='ascii',newline='\n') as stream:stream.write('\n'.join(rows)+'\n')

    def report(self):
        return dict(original_sha256=self.image.sha,matrix_product_symbolic_terms=self.product,
                    rotation_table=self.rotation_coefficients,mirror_tables=self.tables,
                    orientation_matrices=self.matrices,
                    row_vector_cell_consumer='0x648cfc..0x648d46',
                    constructor_order='0x75f2a0: translation, turn0, mirror; helper mutates left and copies output',
                    orientation_zero_descriptor='Zero-filled global descriptor is used for direction0; actual game-state comparison is pending.',
                    original_binary_executed=False)


if __name__=='__main__':
    reference=Reference()
    output=ROOT/'cache_matrix_reference.json'
    with output.open('x',encoding='utf8',newline='\n') as stream:json.dump(reference.report(),stream,indent=2);stream.write('\n')
    print(json.dumps(dict(status='PASS_ORIGINAL_INTEGER_MATRIX_EXPRESSION_DAGS',bytes=output.stat().st_size,
        sha256=hashlib.sha256(output.read_bytes()).hexdigest())))
