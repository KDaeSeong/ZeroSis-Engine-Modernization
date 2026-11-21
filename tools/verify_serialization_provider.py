"""Actual enum/STL component execution and bidirectional serialized-data compatibility."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import random
import struct
from collect_baseline import PROJECT,digest,read_text
from native_build import run
from build_serialization_provider import build,artifact
from stream_evidence import validate as validate_streams

NAMES=('vector_int','vector_empty','deque_string','list_enum','map_string','set_int','nested_vector',
       'string_binary','string_empty','hash_map','unordered_set','replay_turn_data','replay_empty','vote_selection','vote_empty')
UNORDERED={'hash_map','unordered_set'}

def decode(name,data,endian):
    offset=0; fmt='<I' if endian==1 else '>I'
    def u32():
        nonlocal offset
        n=struct.unpack_from(fmt,data,offset)[0];offset+=4;return n
    def i32():
        n=u32();return n if n<0x80000000 else n-0x100000000
    def string():
        nonlocal offset
        n=u32();raw=data[offset:offset+n];offset+=n
        if len(raw)!=n: raise ValueError('Short string')
        return raw
    def ints(): return [i32() for _ in range(u32())]
    if name in ('vector_int','vector_empty','list_enum','set_int','unordered_set'): value=ints()
    elif name=='deque_string':value=[string() for _ in range(u32())]
    elif name=='map_string':value=[(i32(),string()) for _ in range(u32())]
    elif name=='hash_map':value=sorted((i32(),i32()) for _ in range(u32()))
    elif name=='nested_vector':value=[ints() for _ in range(u32())]
    elif name in ('replay_turn_data','replay_empty'):value=[(u32(),i32()) for _ in range(u32())]
    elif name in ('vote_selection','vote_empty'):
        value=(u32(),i32(),i32(),[(i32(),i32(),i32(),i32(),string()) for _ in range(u32())])
    else:value=string()
    if offset!=len(data): raise ValueError('Unexpected trailing bytes')
    if name=='unordered_set':value=sorted(value)
    return value

def expectations():
    ints=[-1,0,-2147483648,2147483647,0x12345678]
    return {'vector_int':ints,'vector_empty':[],'deque_string':[b'',b'abc',b'x\0y'],'list_enum':[-1,42],
        'map_string':[(-3,b'A'),(4,b'x\0y'),(17,'한'.encode())],'set_int':[-1,0,42],
        'nested_vector':[[],ints,[7,7,7]],'string_binary':bytes(range(256)),'string_empty':b'',
        'hash_map':sorted(((i*17)%53,i-7) for i in range(20)),
        'unordered_set':sorted({(i*17)%53 for i in range(20)}),
        'replay_turn_data':[(0,-2147483648),(42,-1),(4294967295,2147483647)],'replay_empty':[],
        'vote_selection':(1,-7,42,[(-1,-1,-1,-1,b''),(2147483647,63,-2147483648,17,b'x\0'+ '한'.encode())]),
        'vote_empty':(1,0,-1,[])}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--vs',type=Path,required=True);args=parser.parse_args()
    validate_streams(PROJECT/'evidence/streams/provider/build_result.json')
    evidence=PROJECT/'evidence/serialization/candidate';evidence.mkdir(parents=True,exist_ok=True)
    reference=build(args.vs)
    numeric=json.loads((PROJECT/'evidence/numeric_boundaries/conformance.json').read_text())
    notification_path=Path(numeric['notification_trace']['path'])
    if digest(notification_path)!=numeric['notification_trace']['sha256']:raise RuntimeError('Notification fixture changed')
    rng=random.Random(0xE6C5)
    values=list(dict.fromkeys(list(range(512))+[0xffffffff,0xfffffffe,0x7fffffff,0x80000000,0x80000001,0xaaaaaaaa,0x55555555]
        +list(struct.unpack('<142I',notification_path.read_bytes()))+[rng.getrandbits(32) for _ in range(1024)]))
    raw=struct.pack('<'+'I'*len(values),*values);input_path=evidence/'enum_inputs.bin';input_path.write_bytes(raw)
    runs=[];data_files=[];failures=[];ordering_differences=[];same_ordered=0;crossloads=0
    def execute(arch,mode,endian,input_arg,output_arg,label):
        exe=reference[arch]['executable']['path']
        r=run([exe,mode,str(endian),input_arg,output_arg],cwd=Path(exe).parent,timeout=20)
        log=evidence/(label+'.log');log.write_bytes(r.stdout+r.stderr)
        runs.append({'architecture':arch,'mode':mode,'endian':endian,'returncode':r.returncode,'log':artifact(log)})
        if r.returncode:failures.append(label+': nonzero exit')
        if mode=='containers' and (r.stdout+r.stderr).count(b'EXISTING_VALUES|')!=4:
            failures.append(label+': pre-existing replay/vote values were not checked')
    maptext=read_text(Path(reference['x86']['map']['path']))
    proof=[]
    for type_name in reference['enum_types']:
        lines=[line.strip() for line in maptext.splitlines() if line.lstrip().startswith('0001:') and
               ('??5@' in line or '??6@' in line) and f'W4{type_name}@@' in line and 'CvGameCoreDLLUtilWin32:CvEnumSerialization.obj' in line]
        if len(lines)!=2:failures.append('Missing actual SDK enum provider map: '+type_name)
        proof+=lines
    string_proof=[line.strip() for line in maptext.splitlines() if ('??5@' in line or '??6@' in line)
        and 'basic_string@D' in line and 'FireWorksWin32:FStlContainerSerialization.obj' in line]
    if len(string_proof)!=2:failures.append('Missing actual SDK string operators')
    expected=expectations()
    for endian in (0,1,2):
        endian_payload=b''.join((bytes(v&255 for v in values) if name=='GameTypes' else
            b''.join(struct.pack('<I' if endian==1 else '>I',v) for v in values)) for name in reference['enum_types'])
        directories={}
        for arch in ('x86','x64'):
            enum_path=evidence/f'enums_{arch}_e{endian}.bin'
            execute(arch,'enums',endian,input_path,enum_path,f'enums_{arch}_e{endian}')
            if enum_path.read_bytes()!=endian_payload:failures.append(f'{arch}/{endian}: enum byte oracle mismatch')
            data_files.append(artifact(enum_path))
            d=evidence/f'containers_{arch}_e{endian}';d.mkdir(exist_ok=True);directories[arch]=d
            execute(arch,'containers',endian,d,'write',f'containers_{arch}_e{endian}')
            for name in NAMES:
                f=d/(name+'.bin');data_files.append(artifact(f))
                if decode(name,f.read_bytes(),endian)!=expected[name]:failures.append(f'{arch}/{endian}/{name}: logical oracle mismatch')
        for name in NAMES:
            if (directories['x86']/(name+'.bin')).read_bytes()==(directories['x64']/(name+'.bin')).read_bytes():
                if name not in UNORDERED:same_ordered+=1
            elif name in UNORDERED:ordering_differences.append({'container':name,'endian':endian})
            else:failures.append(f'{endian}/{name}: ordered wire mismatch')
        for arch,other in [('x86','x64'),('x64','x86')]:
            execute(arch,'containers',endian,directories[other],'read',f'cross_read_{arch}_from_{other}_e{endian}')
            crossloads+=len(NAMES)
    execute('x64','boundaries',1,'unused','unused','count_boundaries')
    boundary=(evidence/'count_boundaries.log').read_text()
    if 'COUNT_BOUNDARIES|2|4' not in boundary:failures.append('Count boundary rejection not proven')
    result={'status':'SDK_SERIALIZATION_CONFORMANCE_PASS' if not failures else 'FAIL','failures':failures,
        'enum_types':reference['enum_types'],'enum_type_count':len(reference['enum_types']),
        'values_per_enum':len(values),'endian_modes':3,'enum_write_read_pairs':len(values)*len(reference['enum_types'])*3,
        'enum_bytes_per_architecture':len(values)*(80*4+1)*3,
        'enum_wire_bytes':{name:1 if name=='GameTypes' else 4 for name in reference['enum_types']},
        'ordered_container_wire_matches':same_ordered,'cross_architecture_container_reads':crossloads,
        'container_case_names':list(NAMES),'extracted_gamecore_cases':['replay_turn_data','replay_empty','vote_selection','vote_empty'],
        'gamecore_scope':'Exact extracted SDK function bodies and declarations; minimal owning class; GameCore not loaded',
        'existing_value_merge_append_checks':48,
        'unordered_logical_values_match':not any('logical oracle' in f for f in failures),
        'unordered_wire_order_differences':ordering_differences,'native_count_overflow_rejections':2,
        'sdk_enum_map_proof':proof,'sdk_string_map_proof':string_proof,'build':artifact(evidence/'build_result.json'),
        'input':artifact(input_path),'notification_fixture':artifact(notification_path),'outputs':data_files,'runs':runs,
        'support_inputs':[artifact(PROJECT/'tools'/n) for n in ('verify_serialization_provider.py','build_serialization_provider.py',
             'native_build.py','collect_baseline.py','stream_evidence.py')],
        'patch_specification':artifact(PROJECT/'Source/Porting/sdk_x64_patches.json'),
        'stream_conformance':artifact(PROJECT/'evidence/streams/conformance.json'),
        'game_launched':False,'full_save_compatibility_verified':False,'game_determinism_verified':False,
        'not_verified':['host/GameCore runtime','all game serialization paths','FAutoArchive','FString',
            'unordered iteration equality and game-level determinism','corrupt composite save rollback','rendering or game multicore performance']}
    (evidence/'conformance.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('status','failures','enum_type_count','values_per_enum','enum_write_read_pairs',
        'ordered_container_wire_matches','cross_architecture_container_reads','unordered_wire_order_differences')}))
    if failures:raise SystemExit(1)
if __name__=='__main__':main()
