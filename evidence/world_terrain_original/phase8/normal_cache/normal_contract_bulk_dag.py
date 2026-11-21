"""Static reaching-expression analysis of a bounded straight-line SIMD block."""
from pathlib import Path
import sys
import capstone
from normal_contract_pe import Image


def analyze(image):
    image.decoder.detail=True
    regs={f'xmm{i}':('input',i) for i in range(8)}
    stack={}
    results=[]
    def load(ins, operand):
        if operand.type==capstone.x86.X86_OP_REG:return regs.get(ins.reg_name(operand.reg),('reg',ins.reg_name(operand.reg)))
        if operand.type==capstone.x86.X86_OP_MEM:
            mem=operand.mem;base=ins.reg_name(mem.base)
            if base=='esp' and mem.index==0:return stack.get(mem.disp,('stack',mem.disp))
            if base=='edi':return ('coefficient',mem.disp)
            return ('memory',base,mem.disp)
        return ('immediate',operand.imm)
    for ins in image.instructions(0x728679,0x7294a8):
        op=ins.operands
        if not op:continue
        if ins.mnemonic in ('movaps','movups','movdqa','movss') and len(op)==2:
            value=load(ins,op[1])
            if op[0].type==capstone.x86.X86_OP_REG:regs[ins.reg_name(op[0].reg)]=value
            elif op[0].type==capstone.x86.X86_OP_MEM and ins.reg_name(op[0].mem.base)=='esp':stack[op[0].mem.disp]=value
        elif ins.mnemonic in ('addps','subps','mulps','divps','andps'):
            name=ins.reg_name(op[0].reg);left=regs[name];right=load(ins,op[1])
            if ins.mnemonic=='divps':results.append((ins.address,left,right))
            regs[name]=(ins.mnemonic,left,right)
        elif ins.mnemonic=='cvtdq2ps':
            regs[ins.reg_name(op[0].reg)]=('float',load(ins,op[1]))
    return results


def coefficients(node):
    if node[0]=='coefficient':return [node[1]]
    result=[]
    for child in node[1:]:
        if isinstance(child,tuple):result.extend(coefficients(child))
    return sorted(set(result))


def sum_terms(node):
    if node[0]=='addps':return sum_terms(node[1])+sum_terms(node[2])
    return [coefficients(node)]


if __name__=='__main__':
    image=Image(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V\CivilizationV_DX11.exe")
    for address,numerator,denominator in analyze(image):
        print(hex(address),[[hex(v) for v in term] for term in sum_terms(numerator)])
        print('denominator',[[hex(v) for v in term] for term in sum_terms(denominator)])
