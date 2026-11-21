"""Execute SDK/reference checks for CRC, real OS locks/clocks, and aligned memory."""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
import random
import re
import struct
import zlib
from collect_baseline import PROJECT,digest,read_text
from native_build import run
from build_foundation_provider import build,artifact
from verify_crc import fixtures as original_crc_fixtures

POLYS=(0xedb88320,0x8005,0x1021,0x202b,0x80d,0,1,0xffffffff,0x82f63b78)

def bit_crc(data,poly,state):
    for byte in data:
        state^=byte
        for _ in range(8):state=(state>>1)^(poly if state&1 else 0)
    return state

def cases():
    for seed,data,split in original_crc_fixtures():yield POLYS[0],seed,data,split
    rng=random.Random(0xF017)
    for poly in POLYS[1:]:
        for seed in (0,0xffffffff):
            for length in range(65):
                data=bytes((i*73+length)&255 for i in range(length));yield poly,seed,data,length//2
        for byte in range(256):yield poly,(byte*0x01010101)&0xffffffff,bytes([byte]),byte%2
        for _ in range(64):
            data=bytes(rng.getrandbits(8) for _ in range(rng.randrange(1025)))
            yield poly,rng.getrandbits(32),data,rng.randrange(len(data)+1)

def validate_clock(path):
    raw=path.read_bytes()
    if len(raw)!=384*56:raise RuntimeError('Unexpected clock trace length')
    mask=(1<<64)-1
    def signed(value):
        value&=mask;return value if value<(1<<63) else value-(1<<64)
    for before,after,offset,mark,rate,freq,seconds in struct.iter_unpack('<5q2d',raw):
        if rate<=0 or after<before or mark>before or freq!=1.0/rate:raise RuntimeError('Invalid clock metadata')
        origin=offset if offset else mark
        low=signed(before-origin)*freq;high=signed(after-origin)*freq
        tolerance=max(math.ulp(low),math.ulp(high))*4+1e-12
        if not math.isfinite(seconds) or not low-tolerance<=seconds<=high+tolerance:
            raise RuntimeError(f'Clock outside counter bracket: {seconds}, [{low},{high}]')
    return len(raw)//56

def main():
    p=argparse.ArgumentParser();p.add_argument('--vs',type=Path,required=True);args=p.parse_args()
    evidence=PROJECT/'evidence/foundation';evidence.mkdir(parents=True,exist_ok=True)
    b=build(args.vs);fixture=evidence/'crc_inputs.bin';expected=bytearray();crc_cases=list(cases())
    with fixture.open('wb') as file:
        file.write(b'ZFC00001'+struct.pack('<I',len(crc_cases)))
        for i,(poly,seed,data,split) in enumerate(crc_cases):
            file.write(struct.pack('<5I',i,poly,seed,len(data),split)+data)
            standard=zlib.crc32(data,seed^0xffffffff)^0xffffffff
            checksum=standard if poly==POLYS[0] else bit_crc(data,poly,seed)
            expected+=struct.pack('<8I',i,poly,seed,len(data),checksum,checksum,checksum,standard)
    layouts=b''.join(struct.pack('<258I',*[bit_crc(bytes([i]),poly,0) for i in range(256)],poly,
        bit_crc(b'\0'*4,poly,0xffffffff)) for poly in POLYS)
    runs=[];outputs=[];failures=[];clock_checks={};allocation_results={};probe_lines={};import_audits=[]
    dumpbin=Path(b['x64']['compiler']['path']).with_name('dumpbin.exe')
    for arch in ('x86','x64'):
        exe=Path(b[arch]['executable']['path']);inspection=run([dumpbin,'/DEPENDENTS',exe],cwd=exe.parent)
        audit=evidence/(arch+'_imports.log');audit.write_bytes(inspection.stdout+inspection.stderr)
        dependencies=re.findall(r'^\s+([^\s]+\.dll)\s*$',read_text(audit),re.I|re.M)
        if inspection.returncode or not dependencies or any(any(name in dll.lower() for name in ('cvgame','lua51','steam_api','fireworks')) for dll in dependencies):
            raise RuntimeError('Unexpected game dependency in foundation harness')
        import_audits.append({'architecture':arch,'log':artifact(audit),'direct_dependencies':dependencies})
    def execute(arch,mode,*args):
        exe=Path(b[arch]['executable']['path']);r=run([exe,mode,*args],cwd=exe.parent,timeout=30)
        log=evidence/(arch+'_'+mode+'.log');log.write_bytes(r.stdout+r.stderr)
        output=(r.stdout+r.stderr).decode('utf-8',errors='replace')
        runs.append({'architecture':arch,'mode':mode,'returncode':r.returncode,'log':artifact(log)})
        if r.returncode:raise RuntimeError(f'{arch}/{mode} failed: {output}')
        if 'PASS|' not in output:raise RuntimeError('Missing native success marker')
        return output
    for arch in ('x86','x64'):
        probe=execute(arch,'probe');probe_lines[arch]=[line for line in probe.splitlines() if not line.startswith(('TIMER','PASS'))]
        crc_path=evidence/(arch+'_crc.bin');execute(arch,'crc',fixture,crc_path);outputs.append(artifact(crc_path))
        if crc_path.read_bytes()!=expected:failures.append(arch+': CRC oracle mismatch')
        layout=evidence/(arch+'_layouts.bin');execute(arch,'layout',layout);outputs.append(artifact(layout))
        if layout.read_bytes()!=layouts:failures.append(arch+': CRC object layout mismatch')
        locks=execute(arch,'locks')
        if [line for line in locks.splitlines() if line.startswith('LOCK_')]!=[
            'LOCK_WORKERS|1|20000','LOCK_WORKERS|2|40000','LOCK_WORKERS|4|80000','LOCK_LIFETIMES|512']:
            failures.append(arch+': lock trace mismatch')
        clock=evidence/(arch+'_clock.bin');timer=execute(arch,'timer',clock);outputs.append(artifact(clock))
        clock_checks[arch]=validate_clock(clock)
        if 'TIMER|8|80000|384' not in timer:failures.append(arch+': timer worker checks missing')
        allocation=execute(arch,'allocation')
        found=re.search(r'ALLOCATIONS\|(\d+)\|(\d+)\|(\d+)',allocation)
        if not found:raise RuntimeError('Allocation result missing')
        count,high,callbacks=map(int,found.groups());allocation_results[arch]={'cases':count,'above_4gb':high,'invalid_parameter_callbacks':callbacks}
        if count!=378 or (arch=='x64' and high!=378) or 'ALLOC_THREADS|4|4096' not in allocation:
            failures.append(arch+': allocation contract missing')
    invalid=execute('x64','invalid')
    if 'CRC_REJECTIONS|4' not in invalid:failures.append('Missing invalid CRC checks')
    if probe_lines['x86']!=probe_lines['x64']:failures.append('Reference probe mismatch')
    if allocation_results['x86']['invalid_parameter_callbacks']!=3 or allocation_results['x64']['invalid_parameter_callbacks']!=0:
        failures.append('Unexpected invalid-alignment behavior')
    maptext=read_text(Path(b['x86']['map']['path']))
    names={'FCrc32.obj':('??0FCRC@@','??1FCRC@@','?Calc@FCRC@@','?CalcBits@FCRC@@','?g_CRC32@@'),
        'FCriticalSection.obj':('??0FCriticalSection@@','??1FCriticalSection@@','?Enter@FCriticalSection@@','?Leave@FCriticalSection@@',
            '?Try@FCriticalSection@@','?GetLockCount@FCriticalSection@@','?GetRecursionCount@FCriticalSection@@'),
        'FTimer.obj':('?Read@FTimer@@','?m_qMark@FTimer@@','?m_qRate@FTimer@@','?m_fFreq@FTimer@@'),
        'FMemHooks.obj':('?FireMallocAlignedNoTracking@@','?FireFreeAlignedNoTracking@@')}
    proof=[]
    for member,symbols in names.items():
        for symbol in symbols:
            matches=[line.strip() for line in maptext.splitlines() if symbol in line and 'FireWorksWin32:'+member in line]
            if not matches:failures.append('SDK map proof missing: '+symbol)
            proof+=matches
    result={'status':'SDK_FOUNDATION_CONFORMANCE_PASS' if not failures else 'FAIL','failures':failures,
        'crc_cases':len(crc_cases),'crc_results_per_architecture':len(crc_cases)*4,'crc_polynomials':list(POLYS),
        'crc_layouts':9,'crc_layout_bytes':1032,'crc_invalid_input_rejections':4,
        'lock_workers':[1,2,4],'protected_increments_per_architecture':140000,'lock_lifetimes_per_architecture':512,
        'clock_bracket_checks':clock_checks,'clock_worker_reads_per_architecture':80000,'x64_concurrent_clock_first_use_workers':8,
        'clock_comparison':'Real QPC before/after brackets, signed 64-bit wrap, SDK seconds unit; four ULP plus 1e-12 tolerance, not exact cross-process timestamps',
        'allocations':allocation_results,'allocation_thread_workers':4,'threaded_allocations_per_architecture':4096,
        'native_allocation_overflow_rejections':1,'sdk_map_proof':proof,'build':artifact(evidence/'build_result.json'),
        'fixture':artifact(fixture),'outputs':outputs,'runs':runs,'direct_import_audits':import_audits,
        'dependency_inspector':artifact(dumpbin),'patch_specification':artifact(PROJECT/'Source/Porting/sdk_x64_patches.json'),
        'support_inputs':[artifact(PROJECT/'tools'/n) for n in ('verify_foundation_provider.py','build_foundation_provider.py',
            'verify_crc.py','native_build.py','collect_baseline.py')],
        'intentional_hardening':['Serialize timer first-use publication; original SDK initialized serially for reference',
            'Reject negative CRC length and null non-empty data before access',
            'Invalid alignment returns NULL/EINVAL without invoking process-wide CRT invalid-parameter handler',
            'Reject native allocation size overflow before CRT allocation'],
        'game_launched':False,'game_multicore_verified':False,'game_performance_verified':False,
        'not_verified':['CRC CalcFile','legacy host small-object allocator binding','TempHeap','copying live locks or destruction while held',
            'actual memory exhaustion','forced QPC failure','all floating-point modes','game host/DLL runtime','game turns, save/load, sync and performance']}
    (evidence/'conformance.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('status','failures','crc_cases','crc_results_per_architecture','clock_bracket_checks','allocations')}))
    if failures:raise SystemExit(1)
if __name__=='__main__':main()
