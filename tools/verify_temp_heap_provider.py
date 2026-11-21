"""Compare real SDK arena traces with a separate model and exercise the x64 arena."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import random
import re
import struct
from collect_baseline import PROJECT,read_text
from native_build import run
from build_temp_heap_provider import build,artifact

CAPACITIES=(0,1,15,16,31,32,255,256,1023,4096,65536)

def fixtures():
    rng=random.Random(0x7E4F2026);operations=[];expected=bytearray()
    capacity=offset=flags=0;active={};started=False;next_id=0
    successful=failed=released=zero=0
    def emit(op,a=0,b=0):
        nonlocal capacity,offset,flags,started,successful,failed,released,zero
        result=0
        if op in (0,1):
            assert not started and not active
            started=True;capacity=a;offset=0;flags=int(op==0);result=a
        elif op==2:
            assert started and a not in active
            rounded=((b+15)//16)*16
            if rounded<=capacity-offset:
                result=offset;offset+=rounded;active[a]=(result,b);successful+=1;zero+=int(b==0)
            else:result=0xffffffff;failed+=1
        elif op==3:
            del active[a];released+=1
            if not active:offset=0
        elif op==4:
            assert not active
            capacity=offset=flags=0;started=False
        else:raise AssertionError(op)
        expected.extend(struct.pack('<10I',len(operations),op,a,b,result,capacity,capacity-offset,len(active),offset,flags))
        operations.append((op,a,b))
    for borrowed in (False,True):
        for cap in CAPACITIES:
            emit(int(borrowed),cap)
            # Explicit boundary sequences, including zero-byte leases at the end.
            for size in (cap//16*16,0,1,15,16,17,cap,max(0,cap-1),cap+1):
                emit(2,next_id,size);next_id+=1
            for identifier in list(active)[::-1]:emit(3,identifier)
            for _ in range(600):
                if active and rng.random()<0.44:emit(3,rng.choice(tuple(active)))
                else:
                    size=rng.choice((0,1,15,16,17,31,32,cap,cap+1,rng.randrange(cap+17)))
                    emit(2,next_id,size);next_id+=1
            for identifier in rng.sample(list(active),len(active)):emit(3,identifier)
            emit(4)
    assert successful==released and not active and not started
    return operations,bytes(expected),dict(operations=len(operations),arena_lifetimes=22,allocations=successful,
        capacity_rejections=failed,releases=released,zero_byte_leases=zero)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--vs',type=Path,required=True);args=parser.parse_args()
    evidence=PROJECT/'evidence/temp_heap';evidence.mkdir(parents=True,exist_ok=True)
    b=build(args.vs);operations,expected,counts=fixtures()
    fixture=evidence/'operations.txt';fixture.write_text(''.join(f'{op} {a} {n}\n' for op,a,n in operations),encoding='ascii')
    oracle=evidence/'model_trace.bin';oracle.write_bytes(expected)
    dumpbin=Path(b['x64']['compiler']['path']).with_name('dumpbin.exe')
    audits=[];runs=[];outputs=[artifact(oracle)];failures=[];probes={};pressure_counts={}
    programs=[('x86',b['x86']['executable']),('x64',b['x64']['executable']),('missing_host',b['x64']['missing_host']['executable'])]
    for name,entry in programs:
        exe=Path(entry['path']);r=run([dumpbin,'/DEPENDENTS',exe],cwd=exe.parent)
        log=evidence/(name+'_imports.log');log.write_bytes(r.stdout+r.stderr)
        imports=re.findall(r'^\s+([^\s]+\.dll)\s*$',read_text(log),re.I|re.M)
        if r.returncode or not imports or any(any(s in dll.lower() for s in ('cvgame','lua51','steam_api','fireworks')) for dll in imports):
            raise RuntimeError('Unexpected dependency in isolated temporary heap executable')
        audits.append({'name':name,'log':artifact(log),'direct_dependencies':imports})
    def execute(arch,mode,*args,missing=False):
        exe=Path((b[arch]['missing_host'] if missing else b[arch])['executable']['path'])
        r=run([exe,*([] if missing else [mode]),*args],cwd=exe.parent,timeout=40)
        log=evidence/(arch+'_'+mode+'.log');log.write_bytes(r.stdout+r.stderr)
        text=(r.stdout+r.stderr).decode('utf-8',errors='replace').replace('\r\n','\n')
        runs.append({'architecture':arch,'mode':mode,'returncode':r.returncode,'log':artifact(log)})
        if r.returncode or 'PASS|' not in text:raise RuntimeError(f'{arch}/{mode} failed: {text}')
        return text
    for arch in ('x86','x64'):
        probes[arch]=execute(arch,'probe')
        output=evidence/(arch+'_trace.bin');result=execute(arch,'trace',fixture,output);outputs.append(artifact(output))
        if f"TRACE|{counts['operations']}\n" not in result or output.read_bytes()!=expected:failures.append(arch+' model trace mismatch')
    if probes['x86']!=probes['x64']:failures.append('Original SDK probe mismatch')
    if 'BOUNDARIES|15|65535|6\n' not in execute('x64','boundaries'):failures.append('Missing integer/lease/lifecycle boundaries')
    if 'LARGE_OFFSETS|4294967296|8192|2147483648|4294967280\n' not in execute('x64','large'):failures.append('Missing native high-pointer/unsigned-offset checks')
    batches=execute('x64','batches')
    if [line for line in batches.splitlines() if line.startswith('BATCHES|')]!=[f'BATCHES|{w}|128|{w*64*128}' for w in (1,2,4,8)]:
        failures.append('Concurrent batch count mismatch')
    pressure=execute('x64','pressure');match=re.search(r'PRESSURE\|8\|400000\|(\d+)\|(\d+)',pressure)
    if not match or not all(map(int,match.groups())) or sum(map(int,match.groups()))!=400000:failures.append('Pressure run missing success/failure paths')
    else:pressure_counts=dict(zip(('successful','capacity_rejections'),map(int,match.groups())))
    host=execute('x64','host')
    if 'HOST_THREADS|8|8192\n' not in host or 'NULL_HOST|2|RECOVERED\n' not in host:failures.append('Missing concurrent host binding/null recovery')
    if 'MISSING_HOST|2\n' not in execute('x64','missing_host',missing=True):failures.append('Missing engine export rejection')
    maptext=read_text(Path(b['x86']['map']['path']));proof=[];addresses=[]
    for name in ('??0TempHeap@@','??1TempHeap@@','?Startup@TempHeap@@','?Shutdown@TempHeap@@','?Allocate@TempHeap@@',
                 '?DeAllocate@TempHeap@@','?OwnsAllocation@TempHeap@@','?GetTempHeap@@'):
        lines=[line.strip() for line in maptext.splitlines() if name in line and 'FireWorksWin32:FTempHeap.obj' in line]
        if len(lines)!=1:raise RuntimeError('Actual SDK temporary heap linkage missing: '+name)
        proof+=lines;addresses.append(int(re.search(r'\s([0-9a-fA-F]{8})\s+f\s',lines[0]).group(1),16))
    exe=Path(b['x86']['executable']['path'])
    disassembly=run([dumpbin,'/DISASM:NOBYTES',f'/RANGE:0x{min(addresses):x},0x{max(addresses)+80:x}',exe],cwd=exe.parent)
    if disassembly.returncode:raise RuntimeError('SDK binary inspection failed')
    assembly=evidence/'sdk_x86_temp_heap_disassembly.txt';assembly.write_bytes(disassembly.stdout+disassembly.stderr)
    result={'status':'SDK_TEMP_HEAP_CONFORMANCE_PASS' if not failures else 'FAIL','failures':failures,
        'sequential_model':counts,'trace_bytes_per_architecture':len(expected),'matching_reference_probe':probes['x86']==probes['x64'],
        'workers':[1,2,4,8],'batches_per_worker_configuration':128,'concurrent_successful_allocations':122880,
        'concurrent_forced_capacity_rejections':15360,'pressure_workers':8,'pressure_attempts':400000,'pressure_results':pressure_counts,
        'rounding_overflow_rejections':15,'maximum_simultaneous_leases':65535,'lifecycle_or_release_rejections':6,
        'native_address_space_reserved':4294967296,'committed_page_bytes':8192,'tested_unsigned_offsets':[2147483648,4294967280],
        'host_first_use_workers':8,'host_binding_calls':8192,'missing_host_rejections':2,'null_host_rejections_and_recovery':2,
        'sdk_map_proof':proof,'sdk_disassembly':artifact(assembly),'build':artifact(evidence/'build_result.json'),
        'fixture':artifact(fixture),'outputs':outputs,'runs':runs,'direct_import_audits':audits,'dependency_inspector':artifact(dumpbin),
        'support_inputs':[artifact(PROJECT/'tools'/name) for name in ('verify_temp_heap_provider.py','build_temp_heap_provider.py',
            'foundation_evidence.py','native_build.py','collect_baseline.py')],
        'intentional_hardening':['Reject 16-byte rounding overflow and the 65536th simultaneous lease',
            'Final successful or failed lease transfers directly to exclusive reset ownership',
            'Uninitialized allocation returns null without leaking a lease',
            'Reject restart before shutdown, misaligned borrowed memory and detectable invalid returns',
            'Thread-safe host export binding; missing or null host callback result raises instead of calling null'],
        'game_launched':False,'game_multicore_verified':False,'game_performance_verified':False,
        'not_verified':['Full GameCore link or runtime','Game turns, save/load, synchronization and performance',
            'Legacy host allocator domain/capacity','Actual physical memory exhaustion','Shutdown while new allocations continue',
            'Arbitrary double return or stale pointer detection while other leases exist','Legacy nested HeapLock helper constructors',
            'GameCore direct allocation failure handling and zero-size FTempArray/FFastVector wrapper ownership']}
    (evidence/'conformance.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({key:result[key] for key in ('status','failures','sequential_model','concurrent_successful_allocations','pressure_results')}))
    if failures:raise SystemExit(1)
if __name__=='__main__':main()
