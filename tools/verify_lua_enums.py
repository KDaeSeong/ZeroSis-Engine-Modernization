"""Run import-audited enum components and compare real DB rows and original output."""
import json
import re
import sqlite3
from pathlib import Path
from collect_baseline import PROJECT, digest, pe_header
from native_build import run
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts


def oracle(rows, count=True):
    values={'s:'+b'NO_MISSION'.hex():'n:-1','n:-1':'s:'+b'NO_MISSION'.hex(),
            's:'+b'KeepExisting'.hex():'n:919'}
    for value,name in rows:
        text='s:'+name.encode('utf-8').hex()
        values[text]='n:'+str(value)
        values['n:'+str(value)]=text
    if count:values['s:'+b'NUM_MISSION_TYPES'.hex()]='n:'+str(len(rows))
    return values


def main():
    root=PROJECT/'evidence/lua_enums';bp=root/'build_result.json'
    build=json.loads(bp.read_text(encoding='utf-8'));check_artifacts(build)
    if build['status']!='SDK_LUA_ENUM_COMPONENTS_BUILT' or len(build['audits'])!=8:
        raise RuntimeError('Enum build/import evidence missing')
    for audit in build['audits']:
        allowed={'zerosisdatabase_x64.dll','kernel32.dll','msvcp140.dll','vcruntime140.dll','vcruntime140_1.dll'}
        if not audit['dependencies'] or any(s.lower() not in allowed and not s.lower().startswith('api-ms-win-crt-') for s in audit['dependencies']):
            raise RuntimeError('Enum component has an unexpected dependency')
    corpus=PROJECT/'Stage/NativeHost/rules.db';corpus_before=artifact(corpus)
    with sqlite3.connect(corpus.resolve().as_uri()+'?mode=ro&immutable=1',uri=True) as db:
        corpus_rows=db.execute('select ID,Type from Missions').fetchall()
    fixture_rows=[(0,'MISSION_ZERO'),(7,'MISSION_GAP'),(7,'MISSION_REPLACEMENT'),(8,'MISSION_ZERO'),
                  (2147483647,'MAX_ID'),(-2147483648,'MIN_ID'),(11,''),(12,'한글'),(13,'NUM_MISSION_TYPES')]
    expected={'normal':oracle(fixture_rows),'empty':oracle([]),'no-count':oracle(fixture_rows,False),
              'corpus':oracle(corpus_rows)}
    rows=[];observations={};issues=[]
    for variant in ('original','candidate','original_od','candidate_od'):
        exe=Path(build['builds'][variant]['executable']['path'])
        if pe_header(exe)['architecture']!='x64':raise RuntimeError('Enum test is not x64')
        modes=['unwind-lua','unwind-null','sql-failures','wrapper','normal','corpus']
        modes+=['faults'] if variant.startswith('candidate') else ['original-lua-faults']
        for mode in modes:
            result=run([exe,mode,*([corpus] if mode=='corpus' else [])],cwd=exe.parent,timeout=30)
            log=root/(variant+'_'+mode+'.log');log.write_bytes(result.stdout+result.stderr)
            text=(result.stdout+result.stderr).decode('utf-8',errors='replace')
            match=re.search(r'^PASS\|(\d+)\s*$',text,re.M)
            count=int(match[1]) if match else 0
            rows.append({'variant':variant,'mode':mode,'executable':artifact(exe),'exit_code':result.returncode,
                         'checks':count,'log':artifact(log)})
            if result.returncode or not count:
                issues.append(variant+'/'+mode+' failed')
                print(text,flush=True)
                break
            observations[variant,mode]=text
            print(f'{variant}/{mode}: {count} checks',flush=True)
        if issues:break
    if not issues:
        for variant in ('original','candidate','original_od','candidate_od'):
            for mode in ('normal','corpus'):
                actual={}
                for label,key,value in re.findall(r'^MAP\|([^|]+)\|([^|]+)\|([^\r\n]+)',observations[variant,mode],re.M):
                    actual.setdefault(label,{})[key]=value
                labels={'normal','empty','no-count'} if mode=='normal' else {'corpus'}
                if set(actual)!=labels or any(actual[label]!=expected[label] for label in labels):
                    issues.append(variant+'/'+mode+' differs from independent SQLite/key mapping')
        for suffix in ('','_od'):
            for mode in ('unwind-lua','unwind-null'):
                if 'ORIGINAL_X64_UNWIND|'+mode+'|statements=0' not in observations['original'+suffix,mode]:
                    issues.append('Original x64 unwind observation changed: '+mode+suffix)
                if 'CANDIDATE_QUERY_CLEANED|'+mode+'|statements=0' not in observations['candidate'+suffix,mode]:
                    issues.append('Candidate Results cleanup missing: '+mode+suffix)
            if len(re.findall(r'^ORIGINAL_SQL_FAILURE_IGNORED\|',observations['original'+suffix,'sql-failures'],re.M))!=4:
                issues.append('Original SQL failure observations incomplete'+suffix)
            if len(re.findall(r'^CANDIDATE_SQL_FAILURE_PROPAGATED\|',observations['candidate'+suffix,'sql-failures'],re.M))!=4:
                issues.append('Candidate SQL query/step/count failures incomplete'+suffix)
            if 'ORIGINAL_REGISTER_IGNORED|query_and_lua_failure' not in observations['original'+suffix,'wrapper']:
                issues.append('Original Register suppression not reproduced'+suffix)
            if 'CANDIDATE_REGISTER_PROPAGATED|query_and_lua_failure|retry_passed' not in observations['candidate'+suffix,'wrapper']:
                issues.append('Candidate Register propagation/retry missing'+suffix)
    faults={k:int(v) for k,v in re.findall(r'^ALLOCATION_FAILURES\|(lua|cpp)\|(\d+)',observations.get(('candidate','faults'),''),re.M)}
    if set(faults)!={'lua','cpp'} or any(v<=10 for v in faults.values()):issues.append('Incomplete allocation-failure sweep')
    od_faults={k:int(v) for k,v in re.findall(r'^ALLOCATION_FAILURES\|(lua|cpp)\|(\d+)',observations.get(('candidate_od','faults'),''),re.M)}
    original_faults={suffix or 'O2':int(m[1]) if (m:=re.search(r'^ORIGINAL_X64_LUA_FAILURES\|(\d+)\|statements_restored_and_retry_passed',observations.get(('original'+suffix,'original-lua-faults'),''),re.M)) else 0 for suffix in ('','_od')}
    if od_faults!=faults or any(v<=10 for v in original_faults.values()):issues.append('Optimization configuration fault coverage differs')
    check_artifacts(build)
    if digest(corpus)!=corpus_before['sha256']:issues.append('Read-only corpus changed')
    report={'status':'SDK_LUA_ENUM_NATIVE_PASS' if not issues else 'SDK_LUA_ENUM_NATIVE_FAIL',
            'build':artifact(bp),'verifier':artifact(Path(__file__).resolve()),'runs':rows,'issues':issues,
            'native_checks':sum(r['checks'] for r in rows),'corpus':corpus_before,'corpus_rows':len(corpus_rows),
            'independent_oracle_fields':{name:len(table) for name,table in expected.items()},
            'candidate_allocation_failures_per_optimization':faults,'original_lua_failures_without_leak':original_faults,
            'tested_optimizations':['/O2','/Od'],'sql_failures_per_variant':4,
            'original_query_leaks_reproduced':False,'original_x64_unwind_verified':not issues,
            'original_register_failure_suppression_reproduced':not issues,
            'candidate_db_failures_before_table_mutation':not issues,'candidate_statement_stack_heap_recovery':not issues,
            'candidate_table_identity_and_normal_values_preserved':not issues,'real_flua_wrapper_executed':True,
            'candidate_matches_generated_sdk':build['candidate_matches_generated_sdk'],
            'all_static_enum_families_registered':False,'gamecore_loaded':False,'game_launched':False,
            'whole_game_library_registration_verified':False,'game_multicore_verified':False,
            'scope':'EXACT_SDK_FUNCTION_BODIES_WITH_REAL_DB_LUA_FLUA_AND_REPRESENTATIVE_REGISTRATION_ENTRYPOINT; MSVC_X64_EHSC_OD_AND_O2; NOT_ALL_GAME_LIBRARIES'}
    (root/'conformance.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('status','native_checks','corpus_rows','candidate_allocation_failures_per_optimization','original_lua_failures_without_leak','issues')}))
    if issues:raise SystemExit(1)


if __name__=='__main__':main()
