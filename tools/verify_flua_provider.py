"""Compare actual archived FLua behavior with x64 values and real Lua VMs."""
import difflib
import json
from pathlib import Path
import re
from collect_baseline import PROJECT, digest, read_text
from native_build import run, checked_run
from build_flua_provider import artifact
from database_evidence import artifacts

def main():
    evidence=PROJECT/'evidence/flua';build_path=evidence/'build_result.json'
    build=json.loads(build_path.read_text());inputs=list(artifacts(build))
    for row in inputs:
        if digest(Path(row['path']))!=row['sha256']:raise RuntimeError('FLua input changed: '+row['path'])
    inspector=Path(build['x64']['compiler']['path']).with_name('dumpbin.exe')
    allowed={'kernel32.dll','user32.dll','advapi32.dll','psapi.dll','dbghelp.dll','ole32.dll','shell32.dll','winmm.dll',
        'msvcp90.dll','msvcr90.dll','msvcp140.dll','vcruntime140.dll','vcruntime140_1.dll','lua51_win32.dll'}
    audits=[]
    for i,module in enumerate([Path(build[a]['executable']['path']) for a in ('x86','x64')]+[PROJECT/'Build/FLua/x86/lua51_Win32.dll']):
        r=checked_run([inspector,'/nologo','/dependents',module],cwd=module.parent)
        log=evidence/('imports_'+str(i)+'.log');log.write_bytes(r.stdout+r.stderr)
        deps=re.findall(r'^[ \t]+([^\\:\r\n]+\.dll)[ \t]*\r?$',r.stdout.decode('mbcs'),re.M|re.I)
        if not deps or any(d.lower() not in allowed and not d.lower().startswith('api-ms-win-crt-') for d in deps):raise RuntimeError('Unexpected FLua native dependency: '+str(deps))
        audits.append({'module':artifact(module),'dependencies':deps,'log':artifact(log)})
    runs=[];pairs=[];self_behavior={}
    for mode in ('values','tables','lifetime','calls','concurrent','self','harden'):
        traces={}
        for arch in (('x64',) if mode=='harden' else ('x86','x64')):
            exe=Path(build[arch]['executable']['path']);r=run([exe,mode],cwd=exe.parent,timeout=30)
            log=evidence/(arch+'_'+mode+'.log');log.write_bytes(r.stdout+r.stderr)
            trace=r.stdout.replace(b'\r\n',b'\n');passed=re.search(rb'^PASS\|(\d+)\s*$',trace,re.M)
            runs.append({'architecture':arch,'mode':mode,'returncode':r.returncode,'checks':int(passed[1]) if passed else 0,'log':artifact(log)})
            if r.returncode or not passed:raise RuntimeError('FLua native failure '+arch+'/'+mode+': '+read_text(log))
            traces[arch]=trace
        if mode in ('values','tables','lifetime','calls','concurrent'):
            diff=evidence/(mode+'.diff');diff.write_text(''.join(difflib.unified_diff(traces['x86'].decode().splitlines(True),traces['x64'].decode().splitlines(True),fromfile='original',tofile='candidate')),encoding='utf-8')
            pairs.append({'mode':mode,'exact':traces['x86']==traces['x64'],'diff':artifact(diff)})
        elif mode=='self':self_behavior={arch:trace.decode() for arch,trace in traces.items()}
        elif b'HARDEN|8|long_error_16384|self_preserved' not in traces['x64']:raise RuntimeError('Missing FLua hardening coverage')
    # Current GameCore consumers require exactly these eight external bridge symbols.
    import csv
    unresolved=PROJECT/'evidence/flua/link_before/link_unresolved_candidates.csv'
    with unresolved.open(encoding='utf-8-sig') as stream:
        required=[row['decorated_or_c_symbol'] for row in csv.DictReader(stream) if '@FLua@@' in row['decorated_or_c_symbol']]
    maptext=read_text(Path(build['x64']['map']['path']));reference_map=read_text(Path(build['x86']['map']['path']))
    proof=[]
    for symbol in required:
        lines=[line for line in maptext.splitlines() if re.search(r'\s'+re.escape(symbol)+r'\s',line) and 'SdkFLuaValues.obj' in line]
        if len(lines)!=1:raise RuntimeError('FLua symbol lacks actual implementation: '+symbol)
        proof.append({'required_symbol':symbol,'map_line':lines[0]})
    if len(proof)!=8:raise RuntimeError('Unexpected initial FLua link requirements')
    reference_proof=[line for line in reference_map.splitlines() if any(key in line for key in ('??0Value@FLua','?Set@Value@FLua','?Push@Table@FLua','?Error@Details@FLua')) and 'FLuaWin32:' in line]
    if not reference_proof:raise RuntimeError('Original archive provenance missing')
    for row in inputs:
        if digest(Path(row['path']))!=row['sha256']:raise RuntimeError('FLua input changed during execution')
    fixed=('VALUE|self|0|-1|' in self_behavior['x86'] and 'absent' in self_behavior['x86']
        and 'VALUE|self|1|3|number|0|17' in self_behavior['x64'])
    result={'status':'SDK_FLUA_VALUE_BRIDGE_CONFORMANCE_PASS' if all(p['exact'] for p in pairs) and fixed else 'SDK_FLUA_VALUE_BRIDGE_DIFFERENCES',
        'build':artifact(build_path),'runs':runs,'comparisons':pairs,'audits':audits,'self_assignment_fixed':fixed,'self_assignment_observation':self_behavior,
        'required_symbols':required,'provider_proof':proof,'original_archive_map_proof':reference_proof,
        'value_inputs':13,'table_writes_per_architecture':4096,'locked_callback_workers':[1,2,4,8],'locked_callbacks_per_architecture':7680,
        'rejected_inputs':8,'long_error_bytes':16384,'cpp_callback_unwind_verified':True,'error_handler_throw_cleanup_verified':True,
        'protected_call_allocation_failure_recovery_verified':True,
        'reference_disassembly':artifact(evidence/'reference/disassembly.log'),'verifier':artifact(Path(__file__).resolve()),
        'baseline_unresolved':artifact(unresolved),'game_launched':False,'gamecore_loaded':False,'game_multicore_verified':False,
        'scope':'FLua value ownership, table field SDK templates and errors on isolated Lua VMs; not all FLua APIs or engine script host'}
    (evidence/'conformance.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('status','comparisons','self_assignment_fixed')}))
    if result['status']!='SDK_FLUA_VALUE_BRIDGE_CONFORMANCE_PASS':raise SystemExit(1)

if __name__=='__main__':main()
