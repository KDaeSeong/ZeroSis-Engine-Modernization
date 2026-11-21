"""Interpret the two VS arithmetic listings on CPU, without shader execution."""
from pathlib import Path
import hashlib,json,math,random,re,struct

ROOT=Path(__file__).absolute().parent
def f32(x):return struct.unpack('<f',struct.pack('<f',x))[0]
def operands(text):return re.split(r',\s*(?![^()]*\))',text)
def program(path):
    result=[]
    for line in path.read_text('utf8').splitlines():
        line=line.strip()
        if not line or line.startswith(('//','dcl_','vs_')):continue
        if line=='ret':break
        op,text=line.split(None,1);assert op in ('mad','mul','mov','add','div'),line;result.append((op,operands(text)))
    assert len(result)==20;return result
def evaluate(code,inputs):
    registers={k:list(v)for k,v in inputs.items()}
    def source(text):
        negative=text.startswith('-');text=text[1:]if negative else text
        if text.startswith('l('):value=[float(x)for x in text[2:-1].split(',')]
        else:
            match=re.fullmatch(r'(\w+(?:\[\d+\])?)(?:\.([xyzw]+))?',text);assert match,text
            values=registers.get(match[1],[0]*4);swizzle=match[2]or'xyzw'
            value=[values['xyzw'.index(c)]for c in swizzle]
            if len(value)==1:value*=4
        assert len(value)==4,text
        return [-x for x in value]if negative else value
    for op,args in code:
        match=re.fullmatch(r'(\w+)\.([xyzw]+)',args[0]);assert match,args[0]
        name,mask=match.groups();src=[source(x)for x in args[1:]];target=registers.setdefault(name,[0]*4)
        for lane in ('xyzw'.index(c)for c in mask):
            a=src[0][lane]
            if op=='mov':value=a
            elif op=='add':value=a+src[1][lane]
            elif op=='mul':value=a*src[1][lane]
            elif op=='mad':value=f32(a*src[1][lane])+src[2][lane]
            else:value=a/src[1][lane]
            target[lane]=f32(value)
    return registers
def main():
    old_path=ROOT/'scene_ice_0_vs.asm.txt';new_path=ROOT/'scene_ice_vs_reconstructed.asm.txt'
    old,new=program(old_path),program(new_path);rng=random.Random(0x751f30);cases=256;comparisons=0;maximum=0
    for case in range(cases):
        c=[[f32(rng.uniform(-.01,.01))for _ in range(4)]for _ in range(14)]
        c[0]=[1,0,0,.001];c[1]=[0,1,0,.001];c[2]=[0,0,1,0];c[3]=[0,0,0,1]
        c[4]=[f32(rng.uniform(-100,100)),f32(rng.uniform(-100,100)),0,0]
        c[5]=[f32(c[4][0]+rng.uniform(.1,100)),f32(c[4][1]+rng.uniform(.1,100)),0,0]
        c[6][0]=f32(rng.uniform(1,64));c[7][0]=-8
        for row in c:
            for lane in range(4):row[lane]=f32(row[lane])
        position=[f32(max(-1,rng.randint(-32768,32767)/32767))for _ in range(2)]
        attributes=[f32(rng.randrange(256)/255)for _ in range(4)]
        inputs={'v0':position+[0,0],'v1':attributes,**{'cb1[%d]'%i:row for i,row in enumerate(c)}}
        a,b=evaluate(old,inputs),evaluate(new,inputs)
        for name,mask in (('o0','xyz'),('o1','xyz'),('o2','xyz'),('o3','xyzw'),('o4','xy'),('o5','xyzw')):
            for lane in ('xyzw'.index(x)for x in mask):
                x,y=a[name][lane],b[name][lane];relative=abs(x-y)/(1+max(abs(x),abs(y)));maximum=max(maximum,relative)
                assert math.isfinite(x)and math.isfinite(y)and relative<0.000004,(case,name,lane,x,y);comparisons+=1
    report=dict(status='PASS_CPU_INTERPRETATION_OF_ORIGINAL_AND_RECONSTRUCTED_VS',cases=cases,output_lane_comparisons=comparisons,
        maximum_scaled_difference=maximum,scaled_tolerance=.000004,original_instruction_count=len(old),reconstructed_instruction_count=len(new),
        listing_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in (old_path,new_path)},
        arithmetic='float32 operations, unfused MAD; includes original/reconstructed X/Y scheduling differences',
        limitation='CPU arithmetic interpretation only; no original or reconstructed shader was executed on GPU',
        host_sdk_clr_granny_hwnd_gpu_audio_or_game_executed=False)
    out=ROOT/'scene_ice_vs_equivalence.json'
    with out.open('x',encoding='utf8')as stream:json.dump(report,stream,indent=2);stream.write('\n')
    print(json.dumps(report))
if __name__=='__main__':main()
