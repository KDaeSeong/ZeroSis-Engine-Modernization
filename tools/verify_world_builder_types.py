"""Execute both real implementations and compare type/group behavior and wire data."""
import difflib
import json
from pathlib import Path
import re
import struct
from collect_baseline import PROJECT,digest,read_text
from database_evidence import artifacts
from native_build import run,checked_run
from probe_world_builder import artifact

MODES=('groups','types','palette','length_254','length_255','length_256','length_257','corpus')

def oracle():
    palette={};group=[];types=[];state=0x71b183;hash_value=2166136261
    for step in range(2048):
        state=(state*1664525+1013904223)&0xffffffff
        name=(('TYPE' if state&1 else 'type')+'_'+str((state>>8)%73)).encode()
        if state%3==0:
            if name in group:group.remove(name)
        elif name not in group:group.append(name)
        value=None if step%11==0 else b'' if step%17==0 else name
        types.append(None if value is None else palette.setdefault(value.lower(),value))
        encoded=b''.join(bytes([len(v)])+v+b'\0' for v in group)+b''.join((v or b'')+b'\0' for v in types)
        for byte in encoded:hash_value=((hash_value^byte)*16777619)&0xffffffff
    return f'{hash_value:08x}'

def main():
    evidence=PROJECT/'evidence/world_builder/types';bpath=evidence/'build_result.json';rpath=PROJECT/'evidence/world_builder/reference/observations.json'
    b=json.loads(bpath.read_text(encoding='utf-8'));reference=json.loads(rpath.read_text(encoding='utf-8'))
    if b['status']!='WORLD_BUILDER_TYPES_BUILT' or reference['status']!='WORLD_BUILDER_REFERENCE_OBSERVED':raise RuntimeError('Build/reference incomplete')
    inputs=list(artifacts([b,reference]));
    def seal():
        for row in inputs:
            if digest(Path(row['path']))!=row['sha256']:raise RuntimeError('Input changed: '+row['path'])
    seal();inspector=Path(b['compiler']['path']).with_name('dumpbin.exe');audits=[]
    exe_by_arch={'x86':Path(reference['executable']['path']),'x64':Path(b['consumers']['trace']['executable']['path'])}
    hard_exe=Path(b['consumers']['hardening']['executable']['path'])
    for name,exe in [*exe_by_arch.items(),('hardening',hard_exe)]:
        result=checked_run([inspector,'/dependents',exe],cwd=exe.parent);log=evidence/(name+'_imports.log');log.write_bytes(result.stdout+result.stderr)
        names=re.findall(r'^[ \t]+([^\\:\r\n]+\.dll)[ \t]*\r?$',result.stdout.decode('mbcs',errors='replace'),re.M|re.I)
        allowed={'kernel32.dll','msvcr90.dll','msvcp90.dll','msvcp140.dll','vcruntime140.dll','vcruntime140_1.dll','user32.dll','advapi32.dll','dbghelp.dll','psapi.dll','ole32.dll','shell32.dll','winmm.dll'}
        if not names or any(n.lower() not in allowed and not n.lower().startswith('api-ms-win-crt-') for n in names):raise RuntimeError('Unexpected native dependency')
        audits.append({'binary':artifact(exe),'dependencies':names,'log':artifact(log)})
    runs=[];comparisons=[];traces={}
    def execute(arch,mode,args=(),label=None):
        exe=hard_exe if mode=='hardening' else exe_by_arch[arch]
        result=run([exe,*(() if mode=='hardening' else (mode,)),*args],cwd=exe.parent,timeout=30)
        log=evidence/('run_'+arch+'_'+(label or mode)+'.log');log.write_bytes(result.stdout+result.stderr)
        trace=result.stdout.decode('utf-8').replace('\r\n','\n');passed=re.search(r'^PASS\|(\d+)\s*$',trace,re.M)
        runs.append({'architecture':arch,'mode':mode,'label':label or mode,'exit_code':result.returncode,'checks':int(passed[1]) if passed else 0,'log':artifact(log)})
        if result.returncode or not passed:raise RuntimeError('WorldBuilder component failed '+arch+'/'+mode+': '+read_text(log))
        return trace
    for mode in MODES+('self',):
        old=execute('x86',mode);new=execute('x64',mode);traces[mode]=(old,new)
        diff=evidence/(mode+'.diff');diff.write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='original',tofile='candidate')),encoding='utf-8')
        exact=old==new
        fixed=mode=='self' and 'BYTES|self_after|0|\n' in old and new==old.replace('BYTES|self_after|0|\n','BYTES|self_after|10|036f6e65000374776f00\n')
        if not exact and not fixed:raise RuntimeError('Unexpected difference: '+str(diff))
        comparisons.append({'mode':mode,'exact':exact,'intentional_self_assignment_fix':fixed,'diff':artifact(diff)})
    wires={arch:evidence/(arch+'_wire.bin') for arch in ('x86','x64')}
    for arch in wires:execute(arch,'write',[wires[arch]])
    cross=[]
    for producer,wire in wires.items():
        left=execute('x86','read',[wire],'read_'+producer);right=execute('x64','read',[wire],'read_'+producer)
        if left!=right:raise RuntimeError('Cross-read differs')
        cross.append({'producer':producer,'wire':artifact(wire),'exact':True})
    names=[b'TERRAIN_GRASS',b'terrain_grass','한글'.encode(),b'',None,b'RESOURCE_IRON']
    group=b''.join(bytes([len(s)])+s+b'\0' for s in names if s)
    palette={};types=b''.join((palette.setdefault(s.lower(),s) if s is not None else b'')+b'\0' for s in names)
    expected_wire=struct.pack('<II',len(group),len(types))+group+types
    if any(w.read_bytes()!=expected_wire for w in wires.values()):raise RuntimeError('Independent wire oracle differs')
    expected_hash=oracle()
    if any('CORPUS|2048|'+expected_hash not in trace for trace in traces['corpus']):raise RuntimeError('Independent operation oracle differs')
    hardening=execute('x64','hardening');faults=re.search(r'^FAULTS\|(\d+)\|(\d+)$',hardening,re.M)
    if not faults or int(faults[2])!=6 or 'WORKERS|4|4096' not in hardening:raise RuntimeError('Missing failure/concurrency evidence')
    maps={'original':read_text(Path(reference['map']['path'])),'candidate':read_text(Path(b['consumers']['trace']['map']['path']))}
    proof={}
    for kind in maps:
        tokens=(('?Add@TypeMap@CvWorldBuilderMapTypeDesc@@QAEIPBD@Z','?Contains@CvWorldBuilderMapTypeGroup@@QBE_NPBD@Z','??0CvWorldBuilderMapTypeDesc@@QAE@XZ')
                if kind=='original' else ('?Add@TypeMap@CvWorldBuilderMapTypeDesc@@QEAAIPEBD@Z','?Contains@CvWorldBuilderMapTypeGroup@@QEBA_NPEBD@Z','??0CvWorldBuilderMapTypeDesc@@QEAA@XZ'))
        rows=[]
        for token in tokens:
            matches=[line for line in maps[kind].splitlines() if token in line and ('CvWorldBuilderMapWin32:' in line if kind=='original' else 'ZeroSis_WorldBuilderTypes_x64:' in line)]
            if not matches:raise RuntimeError('Missing real implementation map provenance: '+kind+'/'+token)
            rows.append(matches[0])
        proof[kind]=rows
    seal()
    report={'status':'WORLD_BUILDER_TYPES_COMPONENT_PASS','build':artifact(bpath),'reference':artifact(rpath),'verifier':artifact(Path(__file__).resolve()),
        'imports':audits,'runs':runs,'comparisons':comparisons,'cross_reads':cross,'wire_bytes':len(expected_wire),'wire_oracle_matched':True,
        'operations_per_architecture':2048,'operation_oracle':expected_hash,'operation_oracle_matched':True,'production_proof':proof,
        'fault_failures':int(faults[1]),'fault_successes':int(faults[2]),'independent_calls':4096,
        'game_launched':False,'gamecore_loaded':False,'full_world_builder_verified':False,'game_multicore_verified':False}
    (evidence/'conformance.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['status','wire_bytes','operation_oracle','fault_failures','fault_successes','independent_calls']}))

if __name__=='__main__':main()
