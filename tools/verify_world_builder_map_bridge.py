"""Execute SDK Load/Save against the original archive and independent wire bits.

The one observed Load9 out-of-bounds read is an explicit safety correction;
random archived heap bytes are never an accepted equivalence target.
"""
import json,re,struct
from pathlib import Path
from collect_baseline import PROJECT,read_text
from native_build import run
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts
from verify_world_builder_map_wire import model,recovery_model


def state_regions(data):
    """Parse the sealed SDK observation format, not native object memory."""
    pos=0;regions={}
    def take(n):
        nonlocal pos
        if n<0 or n>len(data)-pos:raise ValueError('Truncated SDK state record')
        out=data[pos:pos+n];pos+=n;return out
    def numbers(n):return struct.unpack('<'+'I'*n,take(4*n))
    def string():take(numbers(1)[0])
    def save(name,start):regions[name]=data[start:pos]
    width,height,flags,players,minors,teams,year,turns=numbers(8)
    if width*height>32768 or players>32 or minors>64 or teams>96:raise ValueError('Invalid SDK state dimensions')
    for _ in range(4):string()
    save('header',0)
    for i in range(width*height):
        start=pos;values=numbers(14);city,unit=values[8:10];save(f'plot/{i}',start)
        if city!=65535:
            start=pos;string();numbers(4);take(512);save(f'city/{i}/{city}',start)
        seen=set()
        while unit!=65535:
            if unit in seen:raise ValueError('Cyclic SDK state units')
            seen.add(unit);start=pos;record=numbers(9)
            if record[0]!=unit:raise ValueError('SDK unit ordering differs')
            take(512)
            if record[2]!=65535:string()
            save(f'unit/{i}/{unit}',start);unit=record[1]
    for kind,count in (('player',players),('minor',minors)):
        for i in range(count):
            start=pos;take(256)
            for _ in range(6):string()
            numbers(6);save(f'{kind}/{i}',start)
            if kind=='player':start=pos;numbers(64);save(f'influence/{i}',start)
    visibility=[]
    for i in range(teams):
        start=pos;string();take(256);numbers(i*5);save(f'team/{i}',start)
        start=pos;bits=numbers(width*height)
        if any(v not in (0,1) for v in bits):raise ValueError('Invalid observed visibility')
        visibility.extend(bits);save(f'visibility/{i}',start)
    start=pos;take(len(data)-pos);save('mod_and_groups',start)
    return regions,visibility,{'plots':width*height,'players':players,'teams':teams}


def wire_visibility(data):
    parsed=model(data);summary=parsed['summary'].split('|');plots=int(summary[1])*int(summary[2]);teams=int(summary[5]);raw=parsed['raw_blocks']['visibility']
    return [(raw[i//8]>>(i%8))&1 for i in range(plots*teams)]


def observable_lines(text):
    return [s for s in text.splitlines() if s.startswith(('LOAD|','SUMMARY|'))]


def main():
    folder=PROJECT/'evidence/world_builder/map_bridge';bp=folder/'build_result.json';rp=PROJECT/'evidence/world_builder/map_bridge_reference/build_result.json'
    build=json.loads(bp.read_text(encoding='utf-8'));reference=json.loads(rp.read_text(encoding='utf-8'));check_artifacts([build,reference])
    source_path=PROJECT/'evidence/world_builder/map_wire/conformance.json';source=json.loads(source_path.read_text(encoding='utf-8'))
    check_artifacts(source)
    if build['status'] not in ('WORLD_BUILDER_MAP_BRIDGE_BUILT','WORLD_BUILDER_MAP_BRIDGE_BUILT_ISOLATED_HEADERS') or reference['status']!='WORLD_BUILDER_MAP_BRIDGE_REFERENCE_BUILT':raise RuntimeError('Bridge prerequisites failed')
    original=Path(reference['executable']['path']);candidate=Path(build['consumers']['map_bridge']['executable']['path']);out=PROJECT/'Build/WorldBuilder/map_bridge_verified';out.mkdir(parents=True,exist_ok=True)
    issues=[];rows=[];special=[]
    def execute(program,path,mode,label,save=False):
        state=out/(label+'.bin');saved=out/(label+'.Civ5Map');args=[program,path,mode,state]+([saved] if save else [])
        result=run(args,cwd=program.parent,timeout=30);log=folder/(label+'.log');log.write_bytes(result.stdout+result.stderr)
        text=read_text(log);ok=result.returncode==0 and re.search(r'^PASS\|\d+\s*$',text,re.M)
        if not ok:issues.append(label+': execution failed: '+text[-300:])
        return {'exit_code':result.returncode,'log':artifact(log),'state':artifact(state) if ok else None,'saved':artifact(saved) if ok and save else None}
    for i,item in enumerate(source['corpus']):
        path=Path(item['input']['path']);before=artifact(path);data=path.read_bytes();_,recovery,_=recovery_model(data);v=model(data)['version'];label=f'corpus_{i:03}'
        a=execute(original,path,'full',label+'_original');b=execute(candidate,path,'recover' if recovery else 'full',label+'_candidate',True)
        exact=False;cross=None;v9=None;extras=False
        if a['state'] and b['state']:
            ad=Path(a['state']['path']).read_bytes();bd=Path(b['state']['path']).read_bytes();exact=ad==bd
            extras=observable_lines(read_text(Path(a['log']['path'])))==observable_lines(read_text(Path(b['log']['path'])))
            if not extras:issues.append(label+': public summary/preview differ')
            if recovery and f'RECOVERED|{recovery}' not in read_text(Path(b['log']['path'])):issues.append(label+': explicit recovery mask differs')
            if v==9:
                ar,av,meta=state_regions(ad);br,bv,_=state_regions(bd);changed=[k for k in ar.keys()|br.keys() if ar.get(k)!=br.get(k)]
                expected=wire_visibility(data);offset,length=model(data)['ranges']['visibility'];shift=meta['players']*256
                prefix=max(0,length-shift)*8;prefix=min(prefix,len(expected))
                # This original fixture has zero bytes in the misread influence
                # range; its only observed differences must be visibility.
                correct=bv==expected and bool(changed) and all(k.startswith('visibility/') for k in changed)
                shifted=av[:prefix]==expected[shift*8:shift*8+prefix]
                v9={'candidate_matches_wire_bits':bv==expected,'only_visibility_differs':correct,'differing_regions':changed,
                    'wire_offset':offset,'wire_length':length,'erroneous_influence_bytes':shift,'original_shifted_prefix_bits':prefix,'original_prefix_matches_shifted_wire':shifted}
                if not correct or not shifted:issues.append(label+': Load9 safety correction not established')
                special.append((path,a,b,v9))
            elif not exact:issues.append(label+': unexpected original state difference')
            saved=Path(b['saved']['path']);parsed=model(saved.read_bytes())
            if parsed['version']!=12:issues.append(label+': output is not canonical version 12')
            cross=execute(original,saved,'full',label+'_saved_original');cross['exact']=bool(cross['state']) and Path(cross['state']['path']).read_bytes()==bd
            if not cross['exact']:issues.append(label+': original SDK reread differs')
        if artifact(path)!=before:raise RuntimeError('Installed map changed')
        rows.append({'input':before,'version':v,'recovery_bits':recovery,'reference':a,'candidate':b,'exact_observed_state':exact,'summary_preview_equal':extras,'legacy9_correction':v9,'original_reread':cross})
    modes=[]
    for fixture in ('scenario','plain'):
        path=PROJECT/'evidence/world_builder/map_reference'/(fixture+'.bin')
        for mode in ('full','plain','reverse','missing','reuse','reuse-plain'):
            label=fixture+'_'+mode;a=execute(original,path,mode,label+'_original');b=execute(candidate,path,mode,label+'_candidate')
            exact=bool(a['state'] and b['state']) and Path(a['state']['path']).read_bytes()==Path(b['state']['path']).read_bytes()
            if not exact or observable_lines(read_text(Path(a['log']['path'])))!=observable_lines(read_text(Path(b['log']['path']))):issues.append(label+': remap/reuse comparison differs')
            modes.append({'input':artifact(path),'mode':mode,'reference':a,'candidate':b,'exact_observed_state':exact})
    repeats=[]
    if len(special)!=1:issues.append('Expected exactly one installed version 9 diagnostic')
    else:
        path,first,candidate_row,diagnostic=special[0];base,_bits,_meta=state_regions(Path(first['state']['path']).read_bytes())
        for i in range(5):
            row=execute(original,path,'full',f'legacy9_repeat_{i}')
            if row['state']:
                now,_bits,_meta=state_regions(Path(row['state']['path']).read_bytes());row['non_visibility_equal']=all(now.get(k)==v for k,v in base.items() if not k.startswith('visibility/'))
                if not row['non_visibility_equal']:issues.append('Legacy9 repeated non-visibility state differs')
            repeats.append(row)
        diagnostic['distinct_original_repeated_states']=len({r['state']['sha256'] for r in repeats if r['state']})
        # Inspect the actual linked original instructions afresh, without loading it.
        dis=run([Path(build['compiler']['path']).with_name('dumpbin.exe'),'/disasm',original],cwd=out,timeout=30)
        dispath=folder/'original_disassembly.log';dispath.write_bytes(dis.stdout+dis.stderr);asm=read_text(dispath)
        instructions=['00408938: C1 E7 08','00408944: E8 F1 A3 00 00','0040895E: 8D 14 2F','00408962: E8 D9 32 00 00']
        matched=not dis.returncode and all(s in asm for s in instructions) and '00408450 f   CvWorldBuilderMapWin32:CvWorldBuilderMap.obj' in read_text(Path(reference['map']['path']))
        diagnostic['original_instruction_sequence_matches']=matched;diagnostic['disassembly']=artifact(dispath);diagnostic['original_map']=reference['map']
        if not matched:issues.append('Original Load9 instruction evidence changed')
    hard=Path(build['consumers']['map_bridge_hardening']['executable']['path']);r=run([hard,PROJECT/'evidence/world_builder/map_reference/scenario.bin'],cwd=hard.parent,timeout=60)
    log=folder/'hardening.log';log.write_bytes(r.stdout+r.stderr);text=read_text(log);passed=re.search(r'^PASS\|(\d+)\s*$',text,re.M);faults=re.search(r'FAULTS\|(\d+)\|(\d+)',text);trunc=re.search(r'TRUNCATIONS\|(\d+)',text)
    if r.returncode or not passed or not faults or not trunc:issues.append('Native bridge hardening failed')
    linktext=read_text(Path(build['consumers']['map_bridge']['map']['path']));proof=[]
    for name,owner in (('Load@CvWorldBuilderMap','SdkWorldBuilderMapFiles'),('Save@CvWorldBuilderMap','SdkWorldBuilderMapFiles'),('PreviewPlayableCivCount@CvWorldBuilderMap','SdkWorldBuilderMapFiles'),
        ('LoadMapBytes@ZeroSisWorldBuilder','SdkWorldBuilderMapBridge'),('SaveMapBytes@ZeroSisWorldBuilder','SdkWorldBuilderMapBridge'),('ReadMapDocument@ZeroSisWorldBuilder','WorldBuilderMapWire'),('WriteMapDocument@ZeroSisWorldBuilder','WorldBuilderMapWire')):
        lines=[s for s in linktext.splitlines() if re.search(r'\s\?'+re.escape(name)+r'@',s) and 'ZeroSis_WorldBuilderMapBridge_x64:'+owner+'.obj' in s]
        if len(lines)!=1:issues.append('Missing production symbol: '+name)
        proof.extend(lines)
    result={'status':'WORLD_BUILDER_MAP_BRIDGE_COMPONENT_PASS' if not issues else 'WORLD_BUILDER_MAP_BRIDGE_COMPONENT_FAILED','issues':issues,'build':artifact(bp),'reference_build':artifact(rp),'source_corpus':artifact(source_path),
        'verifier':artifact(Path(__file__).resolve()),'wire_model':artifact(PROJECT/'tools/verify_world_builder_map_wire.py'),'corpus':rows,'mode_comparisons':modes,'legacy9_repeats':repeats,'native_sdk_symbol_proof':proof,
        'hardening':{'exit_code':r.returncode,'checks':int(passed[1]) if passed else 0,'cpp_allocation_failures':int(faults[1]) if faults else 0,'successful_retries':int(faults[2]) if faults else 0,'truncation_rejections':int(trunc[1]) if trunc else 0,'log':artifact(log)},
        'sdk_map_file_object_integration':True,'sdk_access_declarations_integrated':build['sdk_access_declarations_integrated'],'production_filesystem_implemented':False,'atomic_file_replace_verified':False,
        'gamecore_linked':False,'gamecore_loaded':False,'game_launched':False,'game_multicore_verified':False,
        'scope':'SDK_FILE_OBJECT_COMPONENT_AND_OBSERVED_PUBLIC_STATE; NOT_ALL_NATIVE_HIDDEN_STATE_OR_GAME_ENGINE'}
    (folder/'conformance.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':result['status'],'inputs':len(rows),'exact_original':sum(r['exact_observed_state'] for r in rows),'original_rereads':sum(bool(r['original_reread'] and r['original_reread']['exact']) for r in rows),'hardening':result['hardening'],'issues':issues}))
    if issues:raise SystemExit(1)


if __name__=='__main__':main()
