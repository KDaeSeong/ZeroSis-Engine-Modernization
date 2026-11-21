"""Compare actual mod-data SDK implementations and exercise bounded/failure paths."""
import json
import difflib
from pathlib import Path
import re
import struct
from collect_baseline import PROJECT,digest,read_text
from database_evidence import artifacts
from native_build import run,checked_run
from probe_world_builder import artifact

def dense_oracle():
    strings=bytearray();schemas=[];defaults=[]
    def add(text):
        offset=len(strings);strings.extend(text.encode('utf-8')+b'\0');return offset
    fields=[];enums=[]
    for name,kind,value in [('dup',0,1),('dup',0,0),('',1,0x80000000),('empty_text',2,''),('same_text',2,'')]:
        index=add(name);value=add(value) if kind==2 else value;fields.append((kind,index,value));defaults.append(value)
    for e in range(12):
        fields.append((3+e,add('enum_'+str(e)),e%3));defaults.append(e%3)
        enums.append([add('value_'+str(e)+'_'+str(v)) for v in range(12)])
    schemas.append((fields,enums));schemas.append(([(0,add('plot'),1)],[]));defaults += [1,1]
    result=bytearray()
    def word(value):result.extend(struct.pack('<I',value))
    for fs,es in schemas:
        word(len(fs));word(len(es))
        for f in fs:
            for v in f:word(v)
        for members in es:
            word(len(members))
            for v in members:word(v)
    word(len(defaults))
    for v in defaults:word(v)
    word(len(strings));result.extend(strings);return bytes(result)

def main():
    evidence=PROJECT/'evidence/world_builder/mod_data';bp=evidence/'build_result.json';rp=PROJECT/'evidence/world_builder/mod_data_reference/observations.json'
    b=json.loads(bp.read_text(encoding='utf-8'));r=json.loads(rp.read_text(encoding='utf-8'))
    if r['status']!='WORLD_BUILDER_MOD_DATA_REFERENCE_OBSERVED':raise RuntimeError('Reference incomplete')
    sealed=list(artifacts([b,r]));
    def check():
        for item in sealed:
            if digest(Path(item['path']))!=item['sha256']:raise RuntimeError('Input changed: '+item['path'])
    check();exes={'x86':Path(r['executable']['path']),'x64':Path(b['consumers']['mod_data']['executable']['path']),'hardening':Path(b['consumers']['mod_data_hardening']['executable']['path'])}
    audits=[];inspector=Path(b['compiler']['path']).with_name('dumpbin.exe')
    allowed={'kernel32.dll','msvcr90.dll','msvcp90.dll','msvcp140.dll','vcruntime140.dll','vcruntime140_1.dll','user32.dll','advapi32.dll','dbghelp.dll','psapi.dll','ole32.dll','shell32.dll','winmm.dll'}
    for name,exe in exes.items():
        result=checked_run([inspector,'/dependents',exe],cwd=exe.parent);log=evidence/(name+'_imports.log');log.write_bytes(result.stdout+result.stderr)
        names=re.findall(r'^[ \t]+([^\\:\r\n]+\.dll)[ \t]*\r?$',result.stdout.decode('mbcs',errors='replace'),re.M|re.I)
        if not names or any(n.lower() not in allowed and not n.lower().startswith('api-ms-win-crt-') for n in names):raise RuntimeError('Unexpected dependency')
        audits.append({'binary':artifact(exe),'log':artifact(log),'dependencies':names})
    runs=[];comparisons=[];traces={}
    def execute(arch,mode,args=(),label=None):
        exe=exes[arch];result=run([exe,*(() if arch=='hardening' else (mode,)),*args],cwd=exe.parent,timeout=60)
        log=evidence/(arch+'_'+(label or mode)+'.log');log.write_bytes(result.stdout+result.stderr);trace=result.stdout.decode('utf-8').replace('\r\n','\n')
        passed=re.search(r'^PASS\|(\d+)\s*$',trace,re.M);runs.append({'architecture':arch,'mode':mode,'label':label or mode,'exit_code':result.returncode,'checks':int(passed[1]) if passed else 0,'log':artifact(log)})
        if result.returncode or not passed:raise RuntimeError('Mod-data native failure '+arch+'/'+mode+': '+read_text(log)[-5000:])
        return trace
    for mode in ('baseline','dense','defaults','bounds','fresh'):
        old=execute('x86',mode);new=execute('x64',mode);diff=evidence/(mode+'.diff');diff.write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True))),encoding='utf-8')
        adjusted=mode=='fresh' and old=='FRESH_RECREATED|99.0\nPASS|1\n' and new=='FRESH_RECREATED|17.0\nPASS|1\n'
        if old!=new and not adjusted:raise RuntimeError('Mod-data difference: '+str(diff))
        comparisons.append({'mode':mode,'exact':old==new,'intentional_fresh_default_initialization':adjusted,'diff':artifact(diff)});traces[mode]=old
    wires={arch:evidence/(arch+'_wire.bin') for arch in ('x86','x64')}
    for arch,path in wires.items():execute(arch,'write',[path])
    cross=[]
    for producer,path in wires.items():
        left=execute('x86','read',[path],'read_'+producer);right=execute('x64','read',[path],'read_'+producer)
        if left!=right:raise RuntimeError('Mod-data cross read differs')
        cross.append({'producer':producer,'wire':artifact(path),'exact':True})
    if any(p.read_bytes()!=dense_oracle() for p in wires.values()):raise RuntimeError('Independent mod-data wire oracle differs')
    hardening=execute('hardening','hardening');faults=re.search(r'^FAULTS\|(\d+)\|(\d+)$',hardening,re.M);truncated=re.search(r'^BOUNDARIES\|(\d+)_truncations',hardening,re.M)
    if not faults or int(faults[2])!=9 or not truncated or 'WORKERS|4|256' not in hardening:raise RuntimeError('Hardening incomplete')
    before=PROJECT/'evidence/world_builder/mod_data_link_before/link_unresolved_candidates.csv'
    import csv
    symbols=[x['decorated_or_c_symbol'] for x in csv.DictReader(before.open(encoding='utf-8-sig'))
             if any(k in x['decorated_or_c_symbol'] for k in ('@ModDataEntry@@','@ModType@@','@ModEnum@@','@CvWorldBuilderMapModData@@'))]
    maptext=read_text(Path(b['consumers']['mod_data']['map']['path']));original_map=read_text(Path(r['map']['path']));proof=[];original_proof=[]
    for symbol in symbols:
        matching=[line for line in maptext.splitlines() if symbol in line and 'ZeroSis_WorldBuilderModData_x64:SdkWorldBuilderModData.obj' in line]
        if not matching:raise RuntimeError('Missing mod-data implementation provenance: '+symbol)
        proof.append({'symbol':symbol,'map_line':matching[0]})
        original=[line for line in original_map.splitlines() if symbol.split('@@')[0]+'@@' in line and 'CvWorldBuilderMapWin32:CvWorldBuilderMapModData.obj' in line]
        if not original:raise RuntimeError('Original mod-data implementation provenance absent: '+symbol)
        original_proof.append(original[0])
    normal_allocator=[line for line in maptext.splitlines() if '?FireMallocAlignedNoTracking@@' in line and 'ZeroSis_Foundation_x64:SdkAlignedMemory.obj' in line]
    hard_map=read_text(Path(b['consumers']['mod_data_hardening']['map']['path']))
    fault_allocator=[line for line in hard_map.splitlines() if '?FireMallocAlignedNoTracking@@' in line and 'mod_data_hardening.obj' in line]
    if not normal_allocator or not fault_allocator:raise RuntimeError('Normal/fault allocator provenance absent')
    check();report={'status':'WORLD_BUILDER_MOD_DATA_COMPONENT_PASS' if b['sdk_access_declarations_integrated'] else 'WORLD_BUILDER_MOD_DATA_ISOLATED_COMPONENT_PASS','build':artifact(bp),'reference':artifact(rp),'verifier':artifact(Path(__file__).resolve()),
        'imports':audits,'runs':runs,'comparisons':comparisons,'cross_reads':cross,'wire_bytes':wires['x86'].stat().st_size,
        'fault_failures':int(faults[1]),'fault_successes':int(faults[2]),'truncation_rejections':int(truncated[1]),'independent_calls':256,
        'fresh_storage_initializes_defaults':True,'sdk_access_declarations_integrated':b['sdk_access_declarations_integrated'],'wire_oracle_matched':True,
        'required_symbol_baseline':artifact(before),'required_symbols':symbols,'production_proof':proof,'original_proof':original_proof,
        'allocator_proof':{'normal':normal_allocator[0],'fault_injection':fault_allocator[0]},
        'gamecore_loaded':False,'game_launched':False,'full_world_builder_verified':False,'game_multicore_verified':False}
    (evidence/'conformance.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['status','wire_bytes','fault_failures','fault_successes','truncation_rejections','independent_calls']}))

if __name__=='__main__':main()
