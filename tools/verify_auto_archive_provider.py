"""Actual SDK archive oracle, cross-architecture reads and candidate failure injection."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import random
import re
import struct
import sys
from build_auto_archive_provider import build,artifact
from collect_baseline import PROJECT,read_text
from native_build import run

SLOTS=[6,0,4,2,5,1,3]
REAL_VALUES=[0.0,-0.0,0.5,-0.5,0.0000005,-0.0000005,1.2345675,1.2345685,
    0.0078125,-0.0078125,1.0078125,1.0000005,1e-20,-1e-20,1e20,-1e20,123456.1234567]

def fixture():
    rng=random.Random(0xAA64)
    records=[(4,0,0),(0,0,10),(1,0,0),(1,0,0),(3,0,0),(2,0,0),(4,0,0),(7,0,0)]
    records += [(0,i,-i-1) for i in range(7)]+[(4,0,0)]
    for _ in range(4096):
        value=rng.getrandbits(32);value=value if value<0x80000000 else value-0x100000000
        records.append((rng.randrange(9),rng.randrange(7),value))
    records.extend([(7,0,0),(4,0,0)])
    return records

def trace_oracle(records,endian):
    def words(values):return b''.join(struct.pack('<I' if endian==1 else '>I',v&0xffffffff) for v in values)
    values=[10+i*101 for i in range(7)];dirty=set();clears=[0]*7;resets=[0]*7;result=bytearray()
    for op,index,value in records:
        side=b''
        if op==0:
            if values[index]!=value:dirty.add(index);values[index]=value
        elif op==1:dirty.add(index)
        elif op==2:side=words(values)
        elif op==3:values=[0]*7;resets=[n+1 for n in resets]
        elif op==4:
            indices=sorted(dirty,key=lambda i:SLOTS[i]);side=words([len(indices)]+[n for i in indices for n in (i,values[i])]);dirty.clear()
        elif op==5:values[index]=value;values[(index+1)%7]=value^0x1234
        elif op==6:side=words([1,index])
        elif op==7:
            for i in dirty:clears[i]+=1
            dirty.clear()
        elif op==8:values=[value^(i*17) for i in range(7)]
        result+=words([op,int(bool(dirty)),len(side)])+side+words(values+clears+resets)
    return bytes(result)

def hex_rows(raw):
    result=[]
    for line in raw.decode('ascii').splitlines():
        parts=line.split('|')
        if len(parts)==3 and parts[0] in ('SHORT','USHORT','CHAR','UCHAR','INT','UINT','FLOAT','DOUBLE','SPECIAL','EXTREME'):
            data=bytes.fromhex(parts[2]);assert len(data)==int(parts[1]);result.append((parts[0],data.decode('ascii')))
    return result

def expected_formatting():
    rows=[]
    for i in range(-32768,32768):rows += [('SHORT',''),('USHORT',str(i&65535)+'h')]
    for i in range(-128,128):rows += [('CHAR',''),('UCHAR',str(i&255)+'hh')]
    for i in (0,1,0xffffffff,0x80000000,0x7fffffff,0x12345678):
        rows += [('INT',str(i if i<0x80000000 else i-0x100000000)),('UINT',str(i)+'d')]
    for value in REAL_VALUES:
        rows += [('DOUBLE',format(value,'.6f')),('FLOAT',format(struct.unpack('<f',struct.pack('<f',value))[0],'.6f'))]
    rows += [('SPECIAL',value) for value in ('inf','-inf','nan','nan')]
    return rows

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--vs',type=Path,required=True);args=parser.parse_args()
    b=build(args.vs);e=PROJECT/'evidence/auto_archive';runs=[];outputs=[];failures=[];audits=[]
    dumpbin=Path(b['x64']['compiler']['path']).with_name('dumpbin.exe')
    for arch,entry in [('x86',b['x86']),('x64',b['x64']),('x64_callers',b['x64']['callers'])]:
        exe=Path(entry['executable']['path']);r=run([dumpbin,'/dependents',exe],cwd=exe.parent)
        log=e/(arch+'_direct_imports.log');log.write_bytes(r.stdout+r.stderr)
        dlls=re.findall(r'^\s+([\w.-]+\.dll)\s*$',read_text(log),re.M|re.I)
        if r.returncode or not dlls or any(any(x in d.lower() for x in ('cvgame','steam_api','lua51','fireworks')) for d in dlls):
            raise RuntimeError('Unsafe or unknown standalone executable dependencies: '+str(log))
        audits.append({'architecture':arch,'direct_dependencies':dlls,'log':artifact(log)})
    def execute(arch,mode,*arguments,label=None):
        exe=Path(b[arch]['executable']['path']);label=label or arch+'_'+mode
        r=run([exe,mode,*map(str,arguments)],cwd=exe.parent,timeout=40)
        log=e/(label+'.log');log.write_bytes(r.stdout+r.stderr)
        matches=re.findall(rb'^PASS\|(\d+)\r?$',r.stdout,re.M)
        runs.append({'architecture':arch,'mode':mode,'returncode':r.returncode,'checks':int(matches[-1]) if matches else 0,'log':artifact(log)})
        if r.returncode or len(matches)!=1:raise RuntimeError('Archive execution failed: '+str(log)+'\n'+read_text(log)[-1800:])
        return r.stdout
    reference_probe=execute('x86','probe');candidate_probe=execute('x64','probe')
    if reference_probe.replace(b'DESTROY|0|1',b'DESTROY|0|0')!=candidate_probe:failures.append('Unexpected probe difference')
    reference_strings=execute('x86','strings');candidate_strings=execute('x64','strings')
    if reference_strings!=candidate_strings:failures.append('Ordinary diagnostic string difference')
    reference_format=hex_rows(execute('x86','formatting'));candidate_format=hex_rows(execute('x64','formatting'))
    expected=expected_formatting()
    if candidate_format!=expected:failures.append('Candidate formatting differs from independent C-locale oracle')
    if len(reference_format)!=len(expected):failures.append('Reference formatting count differs')
    differences=[];integer_matches=0
    for i,(old,new) in enumerate(zip(reference_format,candidate_format)):
        if old==new:
            if old[0] not in ('FLOAT','DOUBLE','SPECIAL'):integer_matches+=1
        else:
            differences.append({'case':i,'type':old[0],'sdk':old[1],'candidate':new[1]})
            if old[0] not in ('FLOAT','DOUBLE','SPECIAL') or old[0]!=new[0]:failures.append('Nonnumeric-diagnostic formatting difference')
    records=fixture();fixture_path=e/'operations.bin';fixture_path.write_bytes(b''.join(struct.pack('<IIi',*r) for r in records))
    trace_sizes=[];wire_matches=0;cross_reads=0
    for endian in (0,1,2):
        oracle=trace_oracle(records,endian);oracle_path=e/f'trace_oracle_e{endian}.bin';oracle_path.write_bytes(oracle);outputs.append(artifact(oracle_path));trace_sizes.append(len(oracle))
        directories={}
        for arch in ('x86','x64'):
            result=e/f'trace_{arch}_e{endian}.bin';execute(arch,'trace',endian,fixture_path,result,label=f'trace_{arch}_e{endian}');outputs.append(artifact(result))
            data=result.read_bytes()
            if data!=oracle:
                first=next((i for i,(a,bv) in enumerate(zip(data,oracle)) if a!=bv),min(len(data),len(oracle)))
                failures.append(f'{arch}/{endian}: trace mismatch at {first}; {len(data)} vs {len(oracle)} bytes')
            directory=e/f'exchange_{arch}_e{endian}';directory.mkdir(exist_ok=True);directories[arch]=directory
            for mode in ('exchange','templates'):execute(arch,mode,endian,directory,'write',label=f'{mode}_{arch}_write_e{endian}')
            outputs.extend(artifact(directory/name) for name in ('full.bin','delta.bin','templates_full.bin','templates_delta.bin'))
        for name in ('full.bin','delta.bin','templates_full.bin','templates_delta.bin'):
            if (directories['x86']/name).read_bytes()!=(directories['x64']/name).read_bytes():failures.append(f'Exchange wire mismatch {endian}/{name}')
            else:wire_matches+=1
        for arch,other in (('x86','x64'),('x64','x86')):
            for mode in ('exchange','templates'):
                execute(arch,mode,endian,directories[other],'read',label=f'{mode}_{arch}_from_{other}_e{endian}');cross_reads+=2
    hardening=execute('x64','hardening');hardening_summary=re.search(rb'HARDENING\|(\d+)\|(\d+)',hardening)
    if not hardening_summary or tuple(map(int,hardening_summary.groups()))!=(156,120):failures.append('Hardening coverage differs')
    extremes=[sys.float_info.max,-sys.float_info.max,sys.float_info.min,float.fromhex('0x0.0000000000001p-1022'),struct.unpack('<f',bytes.fromhex('ffff7f7f'))[0]]
    if hex_rows(hardening)!=[('EXTREME',format(v,'.6f')) for v in extremes]:failures.append('Large finite diagnostic format mismatch')
    caller_runs=[];caller_results={}
    for mode in ('lifecycle','mutations','concurrency'):
        exe=Path(b['x64']['callers']['executable']['path']);r=run([exe,mode],cwd=exe.parent,timeout=45)
        log=e/('callers_'+mode+'.log');log.write_bytes(r.stdout+r.stderr)
        if r.returncode:raise RuntimeError('Actual SDK caller regression failed: '+read_text(log))
        result=json.loads(r.stdout.decode('utf-8'));caller_results[mode]=result
        caller_runs.append({'mode':mode,'returncode':r.returncode,'log':artifact(log)})
    life=caller_results['lifecycle'];mutation=caller_results['mutations'];concurrency=caller_results['concurrency']
    if {k:v for k,v in life.items() if k not in ('mode','checks')}!={'constructor_and_name_faults':15,
        'registration_allocation_failures':3,'lifetime_cleanups':21,'bounds_rejections':16,'protected_owner_pages':1,
        'base_bytes':24,'scalar_bytes':40,'vector_bytes':80}:failures.append('Caller lifetime coverage differs')
    if {k:v for k,v in mutation.items() if k not in ('mode','checks')}!={'operation_kinds':15,'pending_variants':3,
        'integer_allocation_failures':119,'bool_allocation_failures':96,'custom_allocation_failures':167,'custom_value_failures':531,
        'successful_mutations':180,'truncated_vector_reads':216,'growth_pushes':4096,'growth_allocations':41}:failures.append('Caller mutation coverage differs')
    if {k:v for k,v in concurrency.items() if k not in ('mode','checks')}!={'workers':8,'owner_lifetimes':4096,
        'named_variable_lifetimes':8192,'first_pool_use_concurrent':True,'shared_name_pointer_equal':True}:failures.append('Caller independent-owner concurrency differs')
    caller_map=read_text(Path(b['x64']['callers']['map']['path']))
    new_proof=[line.strip() for line in caller_map.splitlines() if re.search(r'\s\?\?2@YAPEAX_K@Z\s',line) and 'sdk_auto_archive_callers.obj' in line]
    if len(new_proof)!=1:failures.append('Allocation-fault hook linkage not proven')
    # Link-map evidence is taken from real SDK archive members, never a mock archive.
    maptext=read_text(Path(b['x86']['map']['path']));proof=[]
    patterns=['??0FAutoArchive@@','??1FAutoArchive@@','?add@FAutoArchive@@','?remove@FAutoArchive@@','?load@FAutoArchive@@',
        '?save@FAutoArchive@@','?saveDelta@FAutoArchive@@','?loadDelta@FAutoArchive@@','?clearDelta@FAutoArchive@@','?reset@FAutoArchive@@',
        '?findMismatchedVariables@FAutoArchive@@','?findVariable@FAutoArchive@@','?hasDeltas@FAutoArchive@@','?EnableCallStacks@FAutoArchive@@',
        '?AreCallStacksEnabled@FAutoArchive@@','??0FAutoVariableBase@@','??1FAutoVariableBase@@','?debugDump@FAutoVariableBase@@',
        '?getStackTrace@FAutoVariableBase@@','?getStackTraceRemark@FAutoVariableBase@@','?toString@FSerialization@@']
    for pattern in patterns:
        lines=[line.strip() for line in maptext.splitlines() if re.search(r'\s'+re.escape(pattern),line) and
            ('FireWorksWin32:FAuto' in line or 'CvGameCoreDLLUtilWin32:CvEnumSerialization.obj' in line)]
        if not lines:failures.append('Missing SDK map proof: '+pattern)
        proof.extend(lines)
    # Record relevant machine-code ranges and malformed legacy printf literals.
    disassembly=[]
    for line in proof:
        if any(token in line for token in ('?saveDelta@','?remove@','?loadDelta@','?toString@')):
            match=re.search(r'\s([0-9A-Fa-f]{8})\s+f',line)
            if match:
                start=int(match[1],16);r=run([dumpbin,'/disasm',f'/range:0x{start:x},0x{start+160:x}',b['x86']['executable']['path']],cwd=e)
                if r.returncode:raise RuntimeError('Reference disassembly failed')
                disassembly.append(line.encode()+b'\n'+r.stdout+r.stderr)
    asm_path=e/'sdk_archive_disassembly.txt';asm_path.write_bytes(b'\n'.join(disassembly))
    pe=Path(b['x86']['executable']['path']).read_bytes();literals={value:pe.count(value.encode()+b'\0') for value in ('%uhh','%hh','%uh','%h','%ud','%d','%f')}
    if not all(literals.values()):failures.append('SDK printf-format literal evidence incomplete')
    result={'status':'SDK_AUTO_ARCHIVE_CONFORMANCE_PASS' if not failures else 'FAIL','failures':failures,
        'operations_per_architecture_per_endian':len(records),'endian_modes':[0,1,2],'trace_bytes_per_endian':trace_sizes,
        'trace_model_matches':6-len([f for f in failures if 'trace mismatch' in f]),'exchange_wire_matches':wire_matches,
        'cross_architecture_payload_reads':cross_reads,'integer_diagnostic_matches':integer_matches,'diagnostic_cases':len(expected),
        'diagnostic_float_differences':differences,'removal_difference':{'sdk':'dirty removed pointer remains','candidate':'registration and dirty pointer erased'},
        'rejected_inputs_and_injected_failures':156,'successful_write_retries':120,'extreme_finite_formats':len(extremes),
        'partial_load_behavior':'Earlier variables can be changed before a later malformed entry is rejected; no composite rollback',
        'sdk_map_proof':proof,'sdk_printf_literals':literals,'sdk_disassembly':artifact(asm_path),'dependency_inspector':artifact(dumpbin),
        'build':artifact(e/'build_result.json'),'fixture':artifact(fixture_path),'outputs':outputs,'runs':runs,'direct_import_audits':audits,
        'caller_results':caller_results,'caller_runs':caller_runs,'caller_allocator_map_proof':new_proof,
        'caller_patch_plan':artifact(PROJECT/'Source/Porting/sdk_x64_patches.json'),
        'support_inputs':[artifact(PROJECT/'tools'/name) for name in ('verify_auto_archive_provider.py','build_auto_archive_provider.py',
            'auto_archive_evidence.py','native_build.py','collect_baseline.py','stream_evidence.py','serialization_evidence.py')],
        'game_launched':False,'full_save_compatibility_verified':False,'game_multicore_verified':False,
        'scope':'FINAL_RELEASE_ACTUAL_SDK_ARCHIVE_AND_TEMPLATE_COMPONENTS_NOT_GAME_SYNCHRONIZATION',
        'not_verified':['GameCore or game host execution','whole-save compatibility','same-archive concurrent/reentrant access',
            'arbitrary scalar assignment failure rollback','name pointer use after module unload',
            'unordered container wire order or game determinism','cross-machine pointer-order wire equality',
            'non-FINAL_RELEASE ABI or real call-stack capture','game performance']}
    (e/'conformance.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('status','failures','operations_per_architecture_per_endian','trace_model_matches',
        'exchange_wire_matches','cross_architecture_payload_reads','integer_diagnostic_matches','diagnostic_float_differences')}))
    if failures:raise SystemExit(1)
if __name__=='__main__':main()
