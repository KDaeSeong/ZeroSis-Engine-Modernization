"""Build/run the actual patched SDK wrappers and cache I/O, with separate injected failures."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import struct
import uuid
from collect_baseline import PROJECT,digest,read_text,pe_header
from native_build import environment_for,run

def artifact(path):return {'path':str(path),'sha256':digest(path)}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--vs',type=Path,required=True);args=parser.parse_args()
    from temp_heap_evidence import validate as validate_temp
    from stream_evidence import validate as validate_stream
    from foundation_evidence import validate as validate_foundation
    _,_,temp=validate_temp(PROJECT/'evidence/temp_heap/build_result.json')
    _,_,stream=validate_stream(PROJECT/'evidence/streams/provider/build_result.json')
    _,_,foundation=validate_foundation(PROJECT/'evidence/foundation/build_result.json')
    providers=[temp,stream,foundation]
    directory=PROJECT/'Build/TempHeapCallers/x64';directory.mkdir(parents=True,exist_ok=True)
    evidence=PROJECT/'evidence/temp_heap_callers';evidence.mkdir(parents=True,exist_ok=True)
    env,compiler=environment_for(args.vs,'x64',directory);compiler=Path(compiler);dumpbin=compiler.with_name('dumpbin.exe')
    sdk=PROJECT/'Source/SDK_BNW_x64'
    flags=['/nologo','/EHsc','/std:c++14','/W4','/WX','/O2','/MD','/fp:strict','/DWIN32','/DFXS_IS_DLL','/DFINAL_RELEASE',
        '/D_CRT_SECURE_NO_WARNINGS','/D_SECURE_SCL=0','/D_HAS_ITERATOR_DEBUGGING=0','/external:W0',
        f'/external:I"{sdk/"FirePlace/include"}"']
    flags += [f'/I"{PROJECT/relative}"' for relative in ('Source/Providers/TempHeap','Source/Providers/Foundation','Source/Providers/Streams','Source/Porting')]
    source=PROJECT/'Tests/sdk_temp_callers.cpp';host=PROJECT/'Tests/sdk_temp_heap_host.cpp'
    inputs=[source,host,PROJECT/'Source/Porting/CvEmbeddedDatabaseIO.h',PROJECT/'Source/Porting/sdk_x64_patches.json',
        PROJECT/'tools/define_temp_heap_caller_patches.py',Path(__file__).resolve(),PROJECT/'tools/native_build.py',PROJECT/'tools/collect_baseline.py',
        sdk/'FirePlace/include/FireWorks/FTempHeap.h',sdk/'FirePlace/include/FireWorks/FDefNew.h',sdk/'FirePlace/include/FireWorks/FMemHooks.h',
        sdk/'CvGameCoreDLL_Expansion2/CvGame.cpp',PROJECT/'evidence/sdk_x64/port_manifest.json']
    sealed=[artifact(p) for p in inputs];builds=[];runs=[];outputs=[];audits=[];failures=[];counts={}
    expected=bytearray()
    sizes=(0,1,15,16,17,255,256,8191,8192,8193,65537)
    for endian in range(3):
        for size in sizes:
            payload=bytes((i*73+29)&255 for i in range(size))
            field=struct.pack('<I' if endian==1 else '>I',size)+payload
            expected+=struct.pack('<3I',endian,size,len(field))+field
    oracle=evidence/'expected_wire.bin';oracle.write_bytes(expected);outputs.append(artifact(oracle))
    for variant in ('production','allocation_faults'):
        out=directory/variant;out.mkdir(parents=True,exist_ok=True)
        exe=out/'temp_callers.exe';linkmap=out/'temp_callers.map';response=out/'compile.rsp'
        variant_flags=flags+(['/DTEMP_CALLER_ALLOCATION_FAULTS'] if variant=='allocation_faults' else [])
        command=variant_flags+[f'"{source}"',f'"{host}"',f'/Fo"{out}\\\\"',f'/Fe"{exe}"']+[f'"{p["library"]["path"]}"' for p in providers]
        response.write_text('\n'.join(command)+'\n',encoding='utf-8')
        result=run([compiler,f'@{response}','/link','/INCREMENTAL:NO','/MACHINE:X64','/WX',f'/MAP:{linkmap}'],cwd=out,env=env,timeout=120)
        log=evidence/(variant+'_build.log');log.write_bytes(result.stdout+result.stderr)
        if result.returncode or re.search(r'\bwarning\s+[A-Z]+\d+',read_text(log)):raise RuntimeError(read_text(log)[:7000])
        builds.append({'variant':variant,'executable':{**artifact(exe),'pe':pe_header(exe)},'map':artifact(linkmap),
            'log':artifact(log),'response':artifact(response),'flags':variant_flags,'compiler_warnings':0})
        inspected=run([dumpbin,'/DEPENDENTS',exe],cwd=out)
        audit=evidence/(variant+'_imports.log');audit.write_bytes(inspected.stdout+inspected.stderr)
        imports=re.findall(r'^\s+([^\s]+\.dll)\s*$',read_text(audit),re.I|re.M)
        if inspected.returncode or not imports or any(any(name in dll.lower() for name in ('cvgame','lua51','steam_api','fireworks')) for dll in imports):
            raise RuntimeError('Unexpected game dependency in caller component executable')
        audits.append({'variant':variant,'log':artifact(audit),'direct_dependencies':imports})
        # Unique files created only in the isolated build directory. Existing or
        # failed-run files are never reused or silently removed by the runner.
        cache=out/('cache_한글_'+uuid.uuid4().hex+'.db');trace=evidence/(variant+'_wire.bin')
        result=run([exe,cache,trace],cwd=out,timeout=45)
        log=evidence/(variant+'_execution.log');log.write_bytes(result.stdout+result.stderr)
        text=(result.stdout+result.stderr).decode('utf-8',errors='replace').replace('\r\n','\n')
        runs.append({'variant':variant,'returncode':result.returncode,'log':artifact(log),'isolated_cache':str(cache)})
        if result.returncode or 'PASS|' not in text:raise RuntimeError(text)
        counts[variant]=int(re.search(r'PASS\|(\d+)',text).group(1));outputs.append(artifact(trace))
        if trace.read_bytes()!=expected:failures.append(variant+' saved field differs from independent uint32/raw-byte model')
        for required in ('WRAPPERS|ZERO|POOLED|FALLBACK|ALIGN64|OWNER|UNWIND|OVERFLOW','DATABASE_ROUNDTRIPS|33|MISSING_FILE_ZERO',
            'IO_FAILURES|26|CACHE_PRESERVED|HANDLES_CLOSED|TEMPORARIES_REMOVED','PARTIAL_IO|2|COLLISION_PRESERVED'):
            if required not in text:failures.append(variant+' missing coverage: '+required)
        if variant=='allocation_faults' and 'ALLOCATION_FAILURES|5|WIDE_REQUEST|8589934590|NO_LEAK' not in text:failures.append('Allocation fault and native-width boundary checks missing')
        if cache.exists() or list(out.glob(cache.name+'.zerosis-tmp-*')):failures.append(variant+' left owned cache/temporary files behind')
        maptext=read_text(linkmap)
        allocation_symbol='?FireMallocAlignedNoTracking@@'
        matching=[line.strip() for line in maptext.splitlines() if re.search(r'\s'+re.escape(allocation_symbol),line)]
        expected_provider='ZeroSis_Foundation_x64:SdkAlignedMemory.obj' if variant=='production' else 'sdk_temp_callers.obj'
        if len(matching)!=1 or expected_provider not in matching[0]:raise RuntimeError('Allocation fault/production provider separation unproven: '+repr(matching))
        builds[-1]['allocation_provider_map_proof']=matching
    if any(digest(Path(a['path']))!=a['sha256'] for a in sealed):raise RuntimeError('Caller test inputs changed during verification')
    source_text=read_text(sdk/'CvGameCoreDLL_Expansion2/CvGame.cpp')
    if (source_text.count('CvEmbeddedDatabase::Read(kStream, wstrDatabasePath, lSize);')!=1
        or source_text.count('CvEmbeddedDatabase::Write(kStream, wstrDatabasePath);')!=1
        or 'GetTempHeap()->Allocate' in source_text):raise RuntimeError('Actual BNW call sites are not bound to the tested helpers')
    result={'status':'SDK_TEMP_HEAP_CALLERS_PASS' if not failures else 'FAIL','failures':failures,'input_artifacts':sealed,
        'providers':providers,'builds':builds,'runs':runs,'outputs':outputs,'direct_import_audits':audits,
        'compiler':artifact(compiler),'dependency_inspector':artifact(dumpbin),'native_checks':counts,
        'database_cases_per_executable':33,'endian_modes':3,'database_sizes':list(sizes),'wire_bytes_per_executable':len(expected),
        'io_failure_cases_per_executable':26,'injected_allocation_failures':5,'tested_native_request_bytes':8589934590,
        'checked_bnwsdk_call_sites':2,'save_field_count_bytes':4,'existing_cache_preserved_on_tested_precommit_failure':True,
        'temporary_files_cleaned':True,'handles_and_temporary_buffers_released':True,
        'game_launched':False,'full_save_compatibility_verified':False,'game_multicore_verified':False,
        'not_verified':['Complete game load/save and host exception handling','Power loss, process termination and storage failure during replacement',
            'Coherent SQLite snapshot while another writer changes same-size bytes','Cleanup when OS repeatedly refuses Close/Delete',
            'Real physical memory exhaustion','Actual 8 GiB allocation (request width tested with deliberate refusal)',
            'Vanilla and Expansion1 GameCore callers','Windows long-path manifest/policy behavior']}
    (evidence/'conformance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({key:result[key] for key in ('status','failures','native_checks','wire_bytes_per_executable','io_failure_cases_per_executable','injected_allocation_failures')}))
    if failures:raise SystemExit(1)
if __name__=='__main__':main()
