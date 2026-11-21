"""Seal bounded original/candidate native SQL, file exchange, lifetime and concurrency evidence."""
from __future__ import annotations
import csv
import json
from pathlib import Path
import re
import shutil
from collect_baseline import PROJECT,digest,read_text
from native_build import checked_run
from compare_database_provider import main as compare

def artifact(path):return {'path':str(path),'sha256':digest(path)}
def main():
    compare();e=PROJECT/'evidence/database';comparison=e/'probe_comparison.json';c=json.loads(comparison.read_text())
    if not c['all_regular_exact'] or not c['all_candidate_runs_pass'] or not all(r['exact_read_trace'] and r['unchanged_by_readers'] for r in c['exchange']):raise RuntimeError('Database component conformance failed')
    candidate=e/'candidate/build_result.json';reference=e/'reference/build_result.json';b=json.loads(candidate.read_text());original=json.loads(reference.read_text())
    for row in c['runs']:
        log=Path(row['log']['path']);found=re.search(r'^PASS\|(\d+)',read_text(log),re.M)
        if not found:raise RuntimeError('Missing checks in '+str(log))
        row['checks']=int(found[1])
    baseline=e/'link_before/link_unresolved_candidates.csv';baseline.parent.mkdir(parents=True,exist_ok=True)
    if not baseline.is_file():shutil.copyfile(PROJECT/'evidence/sdk_x64/link_unresolved_candidates.csv',baseline)
    with baseline.open(encoding='utf-8-sig') as f:all_missing=[r['decorated_or_c_symbol'] for r in csv.DictReader(f)]
    required=sorted(s for s in all_missing if s.startswith('__imp_') and '@Database@@' in s)
    if len(required)!=41 or len(all_missing)!=113:raise RuntimeError('Unexpected database baseline')
    dumpbin=Path(b['compiler']['path']).with_name('dumpbin.exe');exports=e/'candidate/exports.log';members=e/'candidate/import_members.log'
    for option,target,path in (('/exports',exports,Path(b['dll']['path'])),('/linkermember:1',members,Path(b['library']['path']))):
        r=checked_run([dumpbin,'/nologo',option,path],cwd=path.parent);target.write_bytes(r.stdout+r.stderr)
    exported={m[1] for line in read_text(exports).splitlines() if (m:=re.match(r'^\s*\d+\s+[0-9A-F]+\s+[0-9A-F]+\s+(\S+)',line))}
    member_text=read_text(members);map_text=read_text(Path(b['map']['path']));proof=[]
    for symbol in required:
        name=symbol[len('__imp_'):]
        lines=[line for line in map_text.splitlines() if re.search(r'\s'+re.escape(name)+r'\s',line)]
        if name not in exported or not re.search(r'\s'+re.escape(symbol)+r'\s*$',member_text,re.M) or len(lines)!=1 or not any(x in lines[0] for x in ('SdkDatabase.obj','SdkDatabaseResults.obj')):
            raise RuntimeError('Database export/import/body binding absent: '+symbol)
        proof.append({'required_import':symbol,'export':name,'map_line':lines[0]})
    result={'status':'SDK_DATABASE_COMPONENT_CONFORMANCE_PASS','scope':'SDK_CONNECTION_RESULTS_CACHE_AND_SQLITE317_COMPONENT_ONLY',
        'candidate_build':artifact(candidate),'reference_build':artifact(reference),'comparison':artifact(comparison),'reference_probes':artifact(e/'reference/probe_result.json'),
        'assignment_conformance':artifact(e/'assignment/conformance.json'),'sdk_patch_plan':artifact(PROJECT/'Source/Porting/sdk_x64_patches.json'),
        'runs':c['runs'],'differential_modes':['probe','semantics','types','contracts','bulk'],'exact_trace_pairs':5,
        'bulk_rows':1024,'bulk_columns':6,'read_only_file_exchange':c['exchange'],'file_rows_per_writer':257,
        'hardening_checks':next(r['checks'] for r in c['runs'] if r['mode']=='hardening'),
        'concurrency_checks':next(r['checks'] for r in c['runs'] if r['mode']=='concurrency'),'workers':8,'independent_connection_lifetimes':64,'concurrent_inserted_rows':32768,
        'required_import_count':41,'export_count':len(exported),'provider_proof':proof,'baseline':artifact(baseline),'exports':artifact(exports),'import_members':artifact(members),
        'original_disassembly':artifact(e/'reference/wrapper_disassembly.log'),'original_exports':artifact(e/'reference/exports.log'),'dependency_inspector':artifact(dumpbin),
        'support_inputs':[artifact(PROJECT/'tools'/name) for name in ('build_database_reference.py','run_database_reference.py','compare_database_provider.py','verify_database_provider.py','database_evidence.py','native_build.py','collect_baseline.py','prepare_sqlite_compat.py','define_database_caller_patches.py','build_database_fault_tests.py')],
        'documented_differences':['Original double SelectAt crashes; candidate binds the double safely.','Candidate detaches live Results on Connection Close/destruction.','Candidate quotes table/column/savepoint identifiers and bounds error logging by SQL length.','Candidate validates composite foreign keys as complete tuples.','Memory statistics report actual candidate allocations with a new diagnostic format.'],
        'pending_gates':['SQL corpus beyond these fixtures','Allocation failures beyond the tested Results copy/assignment paths','BinaryIO/XMLSerializer/Lua/host APIs not provided','Shared Connection/Results require external serialization','Maintained SQLite upgrade not implemented','Full game/save/performance gates'],
        'game_launched':False,'gamecore_loaded':False,'full_game_save_compatibility_verified':False,'game_multicore_verified':False}
    (e/'conformance.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    from database_evidence import validate
    validate(candidate)
    print(json.dumps({k:result[k] for k in ('status','exact_trace_pairs','required_import_count','export_count','hardening_checks','concurrency_checks')}))
if __name__=='__main__':main()
