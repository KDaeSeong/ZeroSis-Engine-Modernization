"""Compare native file sections with independent bytes and the original SDK reader."""
import json,re,struct
from pathlib import Path
from collect_baseline import PROJECT,digest,read_text
from native_build import run,checked_run
from probe_world_builder import artifact

def fnv(data):
    h=2166136261
    for v in data:h=((h^v)*16777619)&0xffffffff
    return f'{h:08x}'

def model(data):
    pos=0;blocks={};ranges={}
    def take(n):
        nonlocal pos
        if n>len(data)-pos:raise ValueError('model truncated')
        out=data[pos:pos+n];pos+=n;return out
    def u32():return struct.unpack('<I',take(4))[0]
    def section(name,n):ranges[name]=(pos,n);blocks[name]=take(n)
    tag=take(1)[0];version=tag&127;width=u32();height=u32();count=width*height;playable=take(1)[0];flags=u32()
    base_names=['terrain','feature','wonder','resource','mod']+(['name'] if version>=7 else [])+['description']
    lengths=[u32() for _ in base_names]
    for name,n in zip(base_names,lengths):section(name,n)
    if version>=11:section('world',u32())
    section('plots',count*8)
    scenario=bool(tag&128);players=city_states=teams=0;start=maximum=0;year=0xfffff060
    if scenario:
        take(64);start=u32();maximum=u32();u32();year=u32();players,city_states,teams,pad=take(4)
        names=['improvement','unit','tech','policy','building']+(['promotion'] if version>=9 else [])+['units']+(['unit_names'] if version>=9 else [])+['cities','victories','options']
        lengths=[u32() for _ in names]
        for name,n in zip(names,lengths):section(name,n)
        for i in range(5):section('relationship_'+str(i),(teams*(teams-1)//2+7)//8)
        if version>=10:section('influence',players*64*4)
        section('visibility',(count*teams+7)//8);section('teams',teams*64)
        section('players',players*(436 if version>=9 else 304));section('city_states',city_states*(436 if version>=9 else 304));section('plot_scenario',count*8)
    if pos!=len(data):raise ValueError('model trailing')
    all_names=['terrain','feature','wonder','resource','improvement','unit','tech','policy','building','promotion','mod','name','description','world','plots','units','unit_names','cities','victories','options']+['relationship_'+str(i) for i in range(5)]+['influence','visibility','teams','players','city_states','plot_scenario']
    return {'summary':f'SUMMARY|{width}|{height}|{players}|{city_states}|{teams}',
        'header':f'HEADER|{version}|{int(bool(tag&128))}|{playable}|{flags}|{int(scenario)}|{start}|{maximum}|{year}',
        'blocks':{name:f'BLOCK|{name}|{len(blocks.get(name,b""))}|{fnv(blocks.get(name,b""))}' for name in all_names},'raw_blocks':blocks,'ranges':ranges,'version':version,'scenario':scenario}

def recovery_model(data):
    d=model(data);blocks=d['raw_blocks'];v=d['version'];pools=['units','unit_names','cities'];strides=[84 if v>=12 else 48 if v>=9 else 12,64,136 if v>=12 else 104 if v>=9 else 100]
    used=[set(),set(),set()];bad=[];counts=[]
    for k,(name,stride) in enumerate(zip(pools,strides)):
        b=blocks.get(name,b'');n=(len(b)-4)//stride if b else 0;counts.append(n);seen=set();head=struct.unpack_from('<i',b)[0] if b else -1
        while 0<=head<n and head not in seen:seen.add(head);head=struct.unpack_from('<i',b,4+head*stride)[0]
        if head!=-1:bad.append(k)
    plot=blocks.get('plot_scenario',b'');units=blocks.get('units',b'')
    for off in range(0,len(plot),8):
        city,unit=struct.unpack_from('<HH',plot,off)
        if city!=65535:assert city<counts[2];used[2].add(city)
        chain=set()
        while unit!=65535:
            assert unit<counts[0] and unit not in chain;chain.add(unit);used[0].add(unit);at=4+unit*strides[0]
            if v>=9:
                name=struct.unpack_from('<H',units,at+2)[0]
                if name!=65535:assert name<counts[1];used[1].add(name)
            unit=struct.unpack_from('<H',units,at)[0]
    repaired=bytearray(data);changes=[]
    for k in bad:
        start,length=d['ranges'][pools[k]];free=sorted(set(range(counts[k]))-used[k]);struct.pack_into('<i',repaired,start,free[0] if free else -1)
        for i,slot in enumerate(free):struct.pack_into('<i',repaired,start+4+slot*strides[k],free[i+1] if i+1<len(free) else -1)
        changes.append({'pool':pools[k],'reachable_records':len(used[k]),'reconstructed_free_slots':len(free)})
    return bytes(repaired),sum(1<<k for k in bad),changes

def main():
    e=PROJECT/'evidence/world_builder/map_wire';b=json.loads((e/'build_result.json').read_text(encoding='utf-8'))
    refpath=PROJECT/'evidence/world_builder/map_reference/observations.json';ref=json.loads(refpath.read_text(encoding='utf-8'))
    for row in b['sources']+[b['builder'],b['library']]+[r['executable'] for r in b['consumers'].values()]+ref['sources']+[ref['executable'],ref['builder']]:
        if digest(Path(row['path']))!=row['sha256']:raise RuntimeError('Stale input: '+row['path'])
    exe=Path(b['consumers']['world_builder_map_wire']['executable']['path']);original=Path(ref['executable']['path']);root=exe.parent
    imports=[];allowed={'kernel32.dll','msvcp140.dll','vcruntime140.dll','vcruntime140_1.dll','msvcr90.dll','msvcp90.dll','user32.dll','advapi32.dll','dbghelp.dll','psapi.dll','ole32.dll','shell32.dll','winmm.dll'}
    allowed.update('api-ms-win-crt-'+s+'-l1-1-0.dll' for s in ('runtime','stdio','heap','string','filesystem','math','locale','time','utility','convert','environment'))
    for name,program in [('reference',original)]+[(name,Path(c['executable']['path'])) for name,c in b['consumers'].items()]:
        r=checked_run([Path(b['compiler']['path']).with_name('dumpbin.exe'),'/dependents',program],cwd=root)
        log=e/(name+'_imports.log');log.write_bytes(r.stdout+r.stderr);deps=re.findall(r'^\s+([\w.-]+\.dll)\s*$',r.stdout.decode('ascii',errors='replace'),re.M|re.I)
        if not deps or any(d.lower() not in allowed for d in deps):raise RuntimeError('Unexpected native imports: '+str(deps))
        imports.append({'binary':artifact(program),'log':artifact(log),'dependencies':deps})
    inputs=[Path(row['path']) for row in ref['installed_inventory']]+[PROJECT/'evidence/world_builder/map_reference'/n for n in ('scenario.bin','plain.bin')]
    rows=[];issues=[]
    for i,source in enumerate(inputs):
        before=artifact(source);data=source.read_bytes();expected_wire,recovery_bits,repairs=recovery_model(data);expected=model(expected_wire);local=root/('input_%03d.bin'%i);local.write_bytes(data);out=root/('output_%03d.bin'%i)
        r=run([exe,local,out,'recover'],cwd=root,timeout=30);log=e/('corpus_%03d.log'%i);log.write_bytes(r.stdout+r.stderr);text=read_text(log)
        compared=r.returncode==0 and expected['summary'] in text and expected['header'] in text and all(line in text for line in expected['blocks'].values())
        exact=r.returncode==0 and out.read_bytes()==data;wire_matched=r.returncode==0 and out.read_bytes()==expected_wire and f'RECOVERY|{recovery_bits}' in text
        if not compared or not wire_matched:issues.append({'index':i,'source':str(source),'reason':text[-500:]});print('FAILED',i,source.name,text[-180:],flush=True)
        # The original DLL-free map reader must accept candidate output and agree
        # on public dimensions and participant counts for every installed file.
        original_row=None
        if r.returncode==0:
            args=[original,'inspect',out,'full' if expected['scenario'] else 'plain']
            normalized_state=root/('normalized_state_%03d.bin'%i);raw_state=root/('original_state_%03d.bin'%i)
            if recovery_bits:args.append(normalized_state)
            rr=run(args,cwd=root,timeout=30);original_log=e/('original_%03d.log'%i);original_log.write_bytes(rr.stdout+rr.stderr)
            original_ok=rr.returncode==0 and expected['summary'] in read_text(original_log)
            if not original_ok:issues.append({'index':i,'reason':'Original map reader disagrees'})
            original_row={'exit_code':rr.returncode,'public_summary_matches':original_ok,'log':artifact(original_log)}
            if recovery_bits:
                src_run=run([original,'inspect',local,'full',raw_state],cwd=root,timeout=30);source_log=e/('unrepaired_original_%03d.log'%i);source_log.write_bytes(src_run.stdout+src_run.stderr)
                source_state=re.findall(r'^SEMANTIC\|([0-9a-f]+)',read_text(source_log),re.M);output_state=re.findall(r'^SEMANTIC\|([0-9a-f]+)',read_text(original_log),re.M)
                state_equal=src_run.returncode==0 and len(source_state)==1 and source_state==output_state and raw_state.read_bytes()==normalized_state.read_bytes()
                if not state_equal:issues.append({'index':i,'reason':'Recovery changed original SDK public state'})
                strict=run([exe,local,root/'strict_reject.bin'],cwd=root,timeout=30);strict_log=e/('strict_%03d.log'%i);strict_log.write_bytes(strict.stdout+strict.stderr)
                if strict.returncode!=3:issues.append({'index':i,'reason':'Strict mode unexpectedly accepted corrupt allocator'})
                original_row.update(source_log=artifact(source_log),semantic_state_preserved=state_equal,semantic_hash=source_state,
                    semantic_source=artifact(raw_state),semantic_output=artifact(normalized_state),semantic_bytes=raw_state.stat().st_size,strict_rejection=artifact(strict_log))
        if artifact(source)!=before:raise RuntimeError('Original input changed: '+str(source))
        rows.append({'input':before,'version':expected['version'],'scenario':expected['scenario'],'exit_code':r.returncode,'log':artifact(log),
            'model_sections_compared':len(expected['blocks']),'model_matched':compared,'exact_roundtrip':exact,'recovery_bits':recovery_bits,'repairs':repairs,
            'wire_model_matched':wire_matched,'changed_bytes':sum(x!=y for x,y in zip(data,expected_wire)),'output':artifact(out) if r.returncode==0 else None,'original_read':original_row})
    fixture=PROJECT/'evidence/world_builder/map_reference/scenario.bin';mutated=root/'mutated.bin'
    r=run([exe,fixture,mutated,'mutate'],cwd=root,timeout=30);log=e/'mutate.log';log.write_bytes(r.stdout+r.stderr)
    rr=run([original,'read',mutated],cwd=root,timeout=30) if r.returncode==0 else r;original_log=e/'mutate_original.log';original_log.write_bytes(rr.stdout+rr.stderr)
    expected_map='MAP|4|3|3|2|5|18|-3000|407|WORLDSIZE_SMALL|GAMESPEED_QUICK|Changed map name longer than original|World builder x64 fixture'
    expected_plot='PLOT|0|0|0|0|0|0|1|255|23|65535|65535|255|255|255|255'
    text=read_text(original_log);mutation_ok=r.returncode==rr.returncode==0 and expected_map in text and expected_plot in text
    if not mutation_ok:issues.append({'reason':'Original reader rejected or misread changed document'})
    hard=Path(b['consumers']['world_builder_map_wire_hardening']['executable']['path']);r=run([hard,fixture],cwd=root,timeout=60)
    log=e/'hardening.log';log.write_bytes(r.stdout+r.stderr);text=read_text(log);passed=re.search(r'^PASS\|(\d+)\s*$',text,re.M)
    fault=re.search(r'FAULTS\|(\d+)\|(\d+)',text);trunc=re.search(r'TRUNCATIONS\|(\d+)',text)
    if r.returncode or not passed:issues.append({'reason':'Hardening failed','details':text[-500:]})
    maptext=Path(b['consumers']['world_builder_map_wire']['map']['path']).read_text(errors='replace');proof=[]
    for symbol in ('ReadMapDocument','WriteMapDocument','ValidateMapDocument'):
        lines=[line for line in maptext.splitlines() if re.search(r'\s\?'+symbol+r'@ZeroSisWorldBuilder',line) and 'ZeroSis_WorldBuilderMapWire_x64:WorldBuilderMapWire.obj' in line]
        if len(lines)!=1:issues.append({'reason':'Missing actual production object proof','symbol':symbol})
        proof.extend(lines)
    result={'status':'WORLD_BUILDER_MAP_WIRE_COMPONENT_PASS' if not issues else 'WORLD_BUILDER_MAP_WIRE_COMPONENT_FAILED','issues':issues,
        'build':artifact(e/'build_result.json'),'reference':artifact(refpath),'verifier':artifact(Path(__file__).resolve()),'imports':imports,'corpus':rows,
        'installed_inputs':len(ref['installed_inventory']),'model_sections_per_file':31,'production_proof':proof,
        'mutation':{'original_read_matches':mutation_ok,'wire':artifact(mutated),'original_log':artifact(original_log)},
        'hardening':{'exit_code':r.returncode,'checks':int(passed[1]) if passed else 0,'fault_failures':int(fault[1]) if fault else 0,
            'fault_successes':int(fault[2]) if fault else 0,'truncation_rejections':int(trunc[1]) if trunc else 0,'log':artifact(log)},
        'sdk_map_object_integration':False,'gamecore_loaded':False,'game_launched':False,'game_multicore_verified':False,
        'scope':'NAMED_FILE_SECTIONS_AND_BOUNDED_RECORD_REFERENCES_NOT_ALL_GAME_FIELD_SEMANTICS_OR_SDK_MAP_CLASS_IMPLEMENTATION'}
    (e/'conformance.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':result['status'],'files':len(rows),'native_checks':result['hardening']['checks'],'issues':issues},ensure_ascii=True))
    if issues:raise SystemExit(1)

if __name__=='__main__':main()
