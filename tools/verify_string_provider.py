"""Run actual x86 SDK and x64 string implementations, with bounded failure tests."""
import csv
import difflib
import json
from pathlib import Path
import re
import struct
from build_string_provider import artifact
from collect_baseline import PROJECT,digest,read_text
from database_evidence import artifacts
from native_build import checked_run,run

def corpus_oracle(seed,mask):
    def next_value():
        nonlocal seed
        seed=(seed*1664525+1013904223)&0xffffffff
        return seed
    expected=[];checksum=2166136261
    for step in range(4096):
        action=next_value()%7;size=next_value()%97
        external=[next_value()&mask for _ in range(size+4)]
        if action==0 or len(expected)>2048:expected=external[2:2+size]
        elif action==1:
            index=next_value()%(len(expected)+1)
            if size:expected[index:index+size]=external[1:1+size]
        elif action==2:expected=[external[1] if c==external[0] else c for c in expected]
        elif action==4:expected=[]
        elif action==6:expected+=external[3:3+size]
        for value in [len(expected),*expected]:checksum=((checksum^value)*16777619)&0xffffffff
    return f'{checksum:08x}'

def main():
    evidence=PROJECT/'evidence/strings';build_path=evidence/'build_result.json'
    build=json.loads(build_path.read_text(encoding='utf-8'));inputs=list(artifacts(build))
    def check_inputs():
        for row in inputs:
            if digest(Path(row['path']))!=row['sha256']:raise RuntimeError('String input changed: '+row['path'])
    check_inputs();inspector=Path(build['x64']['compiler']['path']).with_name('dumpbin.exe')
    allowed={'kernel32.dll','msvcr90.dll','msvcp90.dll','msvcp140.dll','vcruntime140.dll','vcruntime140_1.dll'}
    audits=[]
    for name,module in [(arch,Path(build[arch]['executable']['path'])) for arch in ('x86','x64')]+[
            ('hardening',Path(build['x64']['hardening']['executable']['path']))]:
        inspected=checked_run([inspector,'/nologo','/dependents',module],cwd=module.parent)
        log=evidence/(name+'_imports.log');log.write_bytes(inspected.stdout+inspected.stderr)
        deps=re.findall(r'^[ \t]+([^\\:\r\n]+\.dll)[ \t]*\r?$',inspected.stdout.decode('mbcs'),re.M|re.I)
        if not deps or any(d.lower() not in allowed and not d.lower().startswith('api-ms-win-crt-') for d in deps):
            raise RuntimeError('Unexpected string harness dependency: '+str(deps))
        audits.append({'module':artifact(module),'dependencies':deps,'log':artifact(log)})
    runs=[];comparisons=[];observed={};hardening=None
    def execute(arch,mode,args=(),hard=False):
        exe=Path((build[arch]['hardening']['executable'] if hard else build[arch]['executable'])['path'])
        result=run([exe,*(() if hard else (mode,)),*args],cwd=exe.parent,timeout=30)
        label=mode if mode!='read' else 'read_'+Path(args[0]).stem
        log=evidence/('run_'+arch+'_'+label+'.log');log.write_bytes(result.stdout+result.stderr)
        trace=result.stdout.replace(b'\r\n',b'\n');passed=re.search(rb'^PASS\|(\d+)\s*$',trace,re.M)
        runs.append({'architecture':arch,'mode':label,'returncode':result.returncode,'checks':int(passed[1]) if passed else 0,'log':artifact(log)})
        if result.returncode or not passed:raise RuntimeError('String native failure '+arch+'/'+label+': '+read_text(log))
        return trace
    for mode in ('values','fixed','paths','encoding','stream','corpus','overlap','boundary'):
        traces={arch:execute(arch,mode,[evidence/(arch+'_stream.bin')] if mode=='stream' else ()) for arch in ('x86','x64')}
        diff=evidence/(mode+'.diff');diff.write_text(''.join(difflib.unified_diff(traces['x86'].decode().splitlines(True),traces['x64'].decode().splitlines(True),fromfile='original',tofile='candidate')),encoding='utf-8')
        if mode in ('overlap','boundary'):observed[mode]={arch:value.decode() for arch,value in traces.items()}
        else:comparisons.append({'mode':mode,'exact':traces['x86']==traces['x64'],'diff':artifact(diff)})
    hardening=execute('x64','hardening',hard=True).decode()
    cross_reads=[]
    for producer in ('x86','x64'):
        wire=evidence/(producer+'_stream.bin')
        traces=[execute(consumer,'read',[wire]) for consumer in ('x86','x64')]
        cross_reads.append({'producer':producer,'wire':artifact(wire),'exact':traces[0]==traces[1]})
    lengths=list(range(130))+[256,4096,65535,65536]
    payloads=[b'a\0bc',b'',bytes.fromhex('ed959ceab880')]+[bytes((i*73+n)&255 for i in range(n)) for n in lengths]
    wire_expected=b''.join(struct.pack(order+'I',len(value))+value for order in ('>','<','>') for value in payloads)
    wire_oracle=all((evidence/(arch+'_stream.bin')).read_bytes()==wire_expected for arch in ('x86','x64'))
    oracle={name:corpus_oracle(seed,mask) for name,seed,mask in [('A',0x12345678,255),('W',0x89abcdef,65535)]}
    oracle_matched=all(f'CORPUS|{name}|4096|{value}' in read_text(evidence/('run_'+arch+'_corpus.log')) for arch in ('x86','x64') for name,value in oracle.items())
    changed=observed['overlap'];guard=observed['boundary']
    fixes={
        'interior_copy':all(old in changed['x86'] and new in changed['x64'] for old,new in [
            ('A|interior_copy|3|626300','A|interior_copy|3|626364'),('W|interior_copy|3|006200630000','W|interior_copy|3|006200630064')]),
        'short_reserve':all(old in changed['x86'] and new in changed['x64'] for old,new in [
            ('A|short_reserve|6|616200646566','A|short_reserve|6|616263646566'),('W|short_reserve|6|006100620000006400650066','W|short_reserve|6|006100620063006400650066')]),
        'fixed_buffer_terminator':'CANARY|0|0|0' in guard['x86'] and 'CANARY|123|123|123' in guard['x64']}
    baseline=evidence/'link_before/link_unresolved_candidates.csv'
    with baseline.open(encoding='utf-8-sig') as file:
        required=[row['decorated_or_c_symbol'] for row in csv.DictReader(file) if any(key in row['decorated_or_c_symbol'] for key in ('FStringA','FStringW','@CvStringUtils@@'))]
    maptext=read_text(Path(build['x64']['map']['path']));proof=[]
    for symbol in required:
        lines=[line for line in maptext.splitlines() if re.search(r'\s'+re.escape(symbol)+r'\s',line) and any(obj in line for obj in ('SdkStrings.obj','SdkStringStream.obj'))]
        if len(lines)!=1:raise RuntimeError('String implementation map proof missing: '+symbol)
        proof.append({'required_symbol':symbol,'map_line':lines[0]})
    reference=read_text(Path(build['x86']['map']['path']))
    reference_proof=[line for line in reference.splitlines() if any(name in line for name in ('?Copy@FStringA','?Copy@FStringW','?FromUTF8ToUTF16','?Write@FDataStream@@IAEXABVFStringA')) and any(lib in line for lib in ('FireWorksWin32:','CvGameCoreDLLUtilWin32:'))]
    if len(proof)!=12 or len(reference_proof)<4:raise RuntimeError('String native provenance incomplete')
    fault=re.search(r'FAULTS\|(\d+)\|(\d+)\|15_operations',hardening);stream_reject=re.search(r'STREAM_REJECTIONS\|(\d+)',hardening)
    boundary=re.search(r'BOUNDARIES\|(\d+)_rejections',hardening)
    if not fault or not stream_reject or not boundary:raise RuntimeError('String hardening accounting absent')
    check_inputs()
    passed=all(p['exact'] for p in comparisons) and all(p['exact'] for p in cross_reads) and all(fixes.values()) and wire_oracle and oracle_matched
    result={'status':'SDK_STRINGS_COMPONENT_CONFORMANCE_PASS' if passed else 'SDK_STRINGS_DIFFERENCES',
        'build':artifact(build_path),'runs':runs,'comparisons':comparisons,'audits':audits,'cross_reads':cross_reads,
        'wire_oracle_matched':wire_oracle,'wire_bytes':len(wire_expected),'wire_fields':len(payloads)*3,'endians':[0,1,2],
        'mutation_operations_per_architecture':8192,'corpus_oracle':oracle,'corpus_oracle_matched':oracle_matched,
        'intentional_defect_fixes':fixes,'defect_observations':observed,
        'fault_cases':int(fault[1]),'fault_success_cases':int(fault[2]),'boundary_rejections':int(boundary[1]),'stream_rejections':int(stream_reject[1]),
        'hardening_checks':next(r['checks'] for r in runs if r['mode']=='hardening'),
        'required_symbols':required,'provider_proof':proof,'original_archive_map_proof':reference_proof,
        'baseline_unresolved':artifact(baseline),'verifier':artifact(Path(__file__).resolve()),
        'game_launched':False,'gamecore_loaded':False,'game_multicore_verified':False,'full_game_save_compatibility_verified':False,
        'scope':'SDK FString required consumers, UTF conversion, owned-string failure behavior and exact field wire format; not full FString API or game host'}
    (evidence/'conformance.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({key:result[key] for key in ('status','wire_bytes','wire_fields','mutation_operations_per_architecture','intentional_defect_fixes','fault_cases','hardening_checks')}))
    if not passed:raise SystemExit(1)

if __name__=='__main__':main()
