"""Strictly validate a retained FoundValue ETW capture; never starts capture/GameCore."""
from __future__ import annotations

import argparse
import ast
from bisect import bisect_left
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import sys
import uuid

from collect_baseline import PROJECT, digest
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts

PROVIDER = '{49a604e1-6c99-4e01-b41d-73694f2290a6}'
READER_RUN = '20261002T151042Z_0d8765878529'
MARGIN = 1


def require(ok, message):
    if not ok:
        raise ValueError(message)


def uint(x, bits=64):
    return type(x) is int and 0 <= x < (1 << bits)


def validate_reader_component_reference(sdk, sdk_path, reader_path, reader_hash):
    component = sdk.get('cpu_trace_component', {})
    frozen_root = sdk_path.resolve().parent / 'frozen'
    component_path = Path(component.get('path', '')).resolve()
    require(component_path.is_relative_to(frozen_root) and component_path.name == 'conformance.json'
            and component.get('sha256') == reader_hash,
            'SDK reader component is not a byte-identical frozen proof')
    matches = [row for row in sdk.get('frozen_inputs', [])
               if row.get('original_path') == str(reader_path.resolve())]
    require(len(matches) == 1 and Path(matches[0].get('path', '')).resolve() == component_path
            and matches[0].get('sha256') == reader_hash,
            'SDK frozen reader component lacks its unique original-source mapping')


def validate_topology(t):
    require(type(t) is dict and set(t) == {'schema','boot_time_100ns','qpc_frequency','os_version','processor_count','topology'}, 'Topology root schema mismatch')
    require(t['schema'] == 'zerosisfoundvalue.topology.v1' and uint(t['boot_time_100ns']) and t['boot_time_100ns'] > 0 and uint(t['qpc_frequency']) and t['qpc_frequency'] > 0, 'Invalid topology boot/QPC binding')
    n=t['processor_count']; rows=t['topology']
    require(uint(n,32) and n > 1 and isinstance(rows,list) and len(rows)==n, 'Incomplete processor topology')
    seen=set(); cores=set()
    for r in rows:
        require(type(r) is dict and set(r)=={'group','logical_processor','physical_core'} and all(uint(r[k],32) for k in r), 'Malformed topology row')
        key=(r['group'],r['logical_processor']); require(key not in seen,'Duplicate logical processor'); seen.add(key); cores.add(r['physical_core'])
    require(seen=={(0,i) for i in range(n)} and cores==set(range(len(cores))) and len(cores)>1, 'Topology is not a complete canonical single group')
    return {(r['group'],r['logical_processor']):r['physical_core'] for r in rows}


def validate_etl(parsed, captured):
    mapping=validate_topology(captured)
    require(parsed.get('schema')=='zerosisfoundvaluecpu.v1' and parsed.get('provider_name')=='ZeroSis.FoundValueCpuTrace' and parsed.get('provider_guid','').casefold()==PROVIDER, 'Unknown FoundValue ETL schema/provider')
    require(parsed.get('etl_opened') is True and parsed.get('clock_is_qpc') is True and parsed.get('qpc_frequency')==captured['qpc_frequency'], 'ETL did not retain raw QPC timestamps')
    require(parsed.get('status')==('ETW_DISTINCT_CORE_OVERLAP_PROVEN' if parsed.get('physical_multicore_proven') is True else 'ETW_TRACE_READ_NO_PROOF') and type(parsed.get('physical_multicore_proven')) is bool, 'Reader status/exit conclusion is inconsistent')
    require(parsed.get('topology')==captured['topology'],'Reader logical-to-physical topology differs from the capture-time sidecar')
    b=parsed.get('topology_binding',{})
    require(type(b) is dict and set(b)=={'same_current_boot','etl_boot_time_100ns','etl_perf_frequency','etl_clock_type_reserved_flags','etl_processor_count','captured_sidecar_boot_time_100ns','topology_source'} and b['same_current_boot'] is True and b['topology_source']=='captured_sidecar' and uint(b['etl_boot_time_100ns']) and abs(b['etl_boot_time_100ns']-captured['boot_time_100ns'])<=20_000_000 and b['captured_sidecar_boot_time_100ns']==captured['boot_time_100ns'] and b['etl_perf_frequency']==captured['qpc_frequency'] and b['etl_clock_type_reserved_flags']==1 and b['etl_processor_count']==captured['processor_count'], 'ETL header does not bind to captured QPC/topology')
    loss=parsed.get('loss',{})
    require(set(loss)=={'events_lost','buffers_lost','reader_events_lost','buffers_read'} and all(type(loss[k]) is int and loss[k]==0 for k in ('events_lost','buffers_lost','reader_events_lost')) and uint(loss.get('buffers_read')) and loss['buffers_read']>0, 'ETL has loss or no read buffers')
    counts=parsed.get('cswitch_counts',{})
    require(set(counts)=={'all','worker_related','worker_related_unmapped_cpu'} and uint(counts['all']) and counts['all']>0 and uint(counts['worker_related']) and counts['worker_related']>0 and counts['worker_related']<=counts['all'] and counts['worker_related_unmapped_cpu']==0, 'CSwitch accounting is incomplete')
    kd=parsed.get('kernel_event_decode',{})
    kdkeys={'tdh_error_not_found_fallback','process_provider_guid','process_lifecycle_versions','process_lifecycle_records_observed','process_events_emitted_worker_pid_only','process_payload_strings_read','thread_provider_guid','thread_lifecycle_versions','thread_lifecycle_records_observed','thread_worker_lifecycle_rows_emitted','cswitch_versions','cswitch_records_observed','identity_prefix_contract'}
    require(type(kd) is dict and set(kd)==kdkeys and kd['tdh_error_not_found_fallback'] is True and kd['process_payload_strings_read'] is False and kd['process_provider_guid'].casefold()=='{3d6fa8d0-fe05-11d0-9dda-00c04fd7ba7c}' and kd['thread_provider_guid'].casefold()=='{3d6fa8d1-fe05-11d0-9dda-00c04fd7ba7c}' and kd['identity_prefix_contract']=='ProcessId after pointer-sized UniqueProcessKey; thread ProcessId,TThreadId; CSwitch NewThreadId,OldThreadId', 'Classic kernel schema/lifecycle diagnostic fields differ')
    version_counts={}
    for name in ('process_lifecycle_versions','thread_lifecycle_versions','cswitch_versions'):
        rows=kd[name]; require(type(rows) is list and rows,'Missing typed kernel event version array')
        require(all(type(row) is dict and set(row)=={'version','count'} and uint(row['version'],32) and uint(row['count']) and row['count']>0 for row in rows),'Malformed kernel event version/count row')
        versions=[row['version'] for row in rows]
        require(versions==sorted(set(versions)),'Duplicate or unordered kernel event version')
        version_counts[name]={row['version']:row['count'] for row in rows}
    require(all(uint(kd[k]) for k in ('process_lifecycle_records_observed','process_events_emitted_worker_pid_only','thread_lifecycle_records_observed','thread_worker_lifecycle_rows_emitted','cswitch_records_observed')) and kd['process_lifecycle_records_observed']==sum(version_counts['process_lifecycle_versions'].values()) and kd['thread_lifecycle_records_observed']==sum(version_counts['thread_lifecycle_versions'].values()) and kd['cswitch_records_observed']==sum(version_counts['cswitch_versions'].values())==counts['all'], 'Kernel lifecycle/CSwitch version counts disagree')
    require(set(version_counts['process_lifecycle_versions']).issubset({4,5}) and set(version_counts['thread_lifecycle_versions'])=={3} and set(version_counts['cswitch_versions'])=={5},'Unknown classic Process/Thread/CSwitch event version observed')
    scopes=parsed.get('batch_scopes'); markers=parsed.get('markers'); require(isinstance(scopes,list) and scopes and isinstance(markers,list) and markers, 'Missing batch/job markers')
    jobs=[]; scope_by_key={}
    for s in scopes:
        require(type(s) is dict and set(s)=={'process_id','batch_id','owner_tid','begin_qpc','end_qpc','job_count'} and all(uint(v) for v in s.values()) and s['process_id']>0 and s['owner_tid']>0 and s['begin_qpc']<s['end_qpc'] and s['job_count']>0, 'Malformed batch scope')
        key=(s['process_id'],s['batch_id']); require(key not in scope_by_key,'Duplicate batch scope'); scope_by_key[key]=s
    grouped={}
    for m in markers:
        require(type(m) is dict and set(m)=={'phase','batch_id','job_index','process_id','worker_tid','fact_count','qpc'} and m['phase'] in ('begin','end') and all(uint(v) for k,v in m.items() if k!='phase') and m['process_id']>0 and m['worker_tid']>0 and m['fact_count']>0 and m['qpc']>0, 'Malformed FoundValue job marker')
        key=(m['process_id'],m['batch_id']); require(key in scope_by_key and scope_by_key[key]['begin_qpc']<=m['qpc']<=scope_by_key[key]['end_qpc'], 'Marker outside its batch scope')
        pair=grouped.setdefault((m['process_id'],m['batch_id'],m['job_index']),{}); require(m['phase'] not in pair,'Duplicate job marker phase'); pair[m['phase']]=m
    for key,s in scope_by_key.items():
        indexes=sorted(k[2] for k in grouped if k[:2]==key)
        require(indexes==list(range(s['job_count'])), 'Missing/extra candidate job index in batch')
        for idx in indexes:
            pair=grouped[(key[0],key[1],idx)]; require(set(pair)=={'begin','end'}, 'Unpaired or duplicate job marker')
            a,z=pair['begin'],pair['end']; require(a['worker_tid']==z['worker_tid'] and a['fact_count']==z['fact_count'] and a['qpc']<z['qpc'], 'Job identity/fact count/interval mismatch')
            jobs.append({'process_id':key[0],'batch_id':key[1],'job_index':idx,'worker_tid':a['worker_tid'],'fact_count':a['fact_count'],'begin_qpc':a['qpc'],'end_qpc':z['qpc']})
    pidset={s['process_id'] for s in scopes}; require(len(pidset)==1,'Capture must contain one SDK process identity')
    pid=next(iter(pidset)); workers={j['worker_tid'] for j in jobs}
    lives={tid:[] for tid in workers}; active={}; pe=parsed.get('process_events'); te=parsed.get('thread_events')
    require(isinstance(pe,list) and isinstance(te,list) and pe and te,'Missing process/thread lifecycle rows')
    proc=[]
    for e in pe:
        require(type(e) is dict and set(e)=={'event_id','process_id','timestamp'} and all(uint(v) for v in e.values()) and e['process_id']==pid and e['event_id'] in (1,2,3,4), 'Malformed process lifetime event')
        proc.append(e)
    require(kd['process_events_emitted_worker_pid_only']==len(pe) and kd['thread_worker_lifecycle_rows_emitted']==len(te) and kd['process_lifecycle_records_observed']>=len(pe) and kd['thread_lifecycle_records_observed']>=len(te),'Lifecycle emission/count totals disagree with retained rows')
    starts=[e['timestamp'] for e in proc if e['event_id'] in (1,3)]; ends=[e['timestamp'] for e in proc if e['event_id'] in (2,4)]
    require(len(starts)==1 and len(ends)==1 and starts[0]<=min(j['begin_qpc'] for j in jobs) and ends[0]>=max(j['end_qpc'] for j in jobs), 'Process lifetime does not uniquely enclose all jobs')
    for e in sorted(te,key=lambda x:x.get('timestamp',-1)):
        require(type(e) is dict and set(e)=={'event_id','process_id','thread_id','timestamp'} and all(uint(v) for v in e.values()) and e['process_id']==pid and e['thread_id'] in workers and e['event_id'] in (1,2,3,4), 'Malformed/foreign thread lifetime event')
        tid,ts=e['thread_id'],e['timestamp']
        if e['event_id'] in (1,3):
            require(tid not in active,'Ambiguous duplicate worker start'); active[tid]=ts
        else:
            require(tid in active and active[tid]<ts,'Worker ended without a unique start'); lives[tid].append((active.pop(tid),ts))
    require(not active and all(lives.values()),'Incomplete worker lifetime')
    for j in jobs: require(sum(a<=j['begin_qpc'] and j['end_qpc']<=z for a,z in lives[j['worker_tid']])==1,'Job escapes worker lifetime')
    slices=parsed.get('worker_cpu_slices'); require(isinstance(slices,list) and slices,'No worker scheduling slices')
    for r in slices:
        keys={'process_id','worker_tid','processor_index','group','group_processor','physical_core','begin_qpc','end_qpc'}
        require(type(r) is dict and set(r)==keys and all(uint(v) for v in r.values()) and r['process_id']==pid and r['worker_tid'] in workers and r['begin_qpc']<r['end_qpc'], 'Malformed/foreign worker CSwitch slice')
        logical=(r['group'],r['group_processor']); require(logical in mapping and mapping[logical]==r['physical_core'] and r['processor_index']==r['group_processor'],'CSwitch CPU identity disagrees with captured topology')
        require(sum(a<=r['begin_qpc']<r['end_qpc']<=z for a,z in lives[r['worker_tid']])==1,'CSwitch slice escapes worker lifetime')
    def reject_group_overlap(rows, message):
        for group in rows.values():
            ordered=sorted(group,key=lambda row:(row['begin_qpc'],row['end_qpc']))
            furthest_end=None
            for row in ordered:
                require(furthest_end is None or furthest_end<=row['begin_qpc'],message)
                furthest_end=row['end_qpc'] if furthest_end is None else max(furthest_end,row['end_qpc'])
    by_cpu={}; by_tid={}
    for row in slices:
        by_cpu.setdefault(row['processor_index'],[]).append(row)
        by_tid.setdefault(row['worker_tid'],[]).append(row)
    reject_group_overlap(by_cpu,'Impossible overlapping worker scheduling slices on one logical processor')
    reject_group_overlap(by_tid,'Impossible overlapping worker scheduling slices for one TID')
    slices_by_tid={tid:sorted(rows,key=lambda row:(row['begin_qpc'],row['end_qpc'])) for tid,rows in by_tid.items()}
    starts_by_tid={tid:[row['begin_qpc'] for row in rows] for tid,rows in slices_by_tid.items()}
    scored=[]
    for j in jobs:
        rows=slices_by_tid[j['worker_tid']]; starts=starts_by_tid[j['worker_tid']]
        pos=bisect_left(starts,j['begin_qpc'])
        if pos and rows[pos-1]['end_qpc']>j['begin_qpc']:
            pos-=1
        while pos<len(rows) and rows[pos]['begin_qpc']<j['end_qpc']:
            r=rows[pos]
            lo=max(j['begin_qpc'],r['begin_qpc']); hi=min(j['end_qpc'],r['end_qpc'])
            if lo<hi: scored.append({**j,'begin_qpc':lo,'end_qpc':hi,'physical_core':r['physical_core'],'processor_index':r['processor_index']})
            pos+=1
    witness=None; longest=0
    scored_by_batch={}
    for row in scored: scored_by_batch.setdefault(row['batch_id'],[]).append(row)
    for batch_rows in scored_by_batch.values():
        for i,a in enumerate(batch_rows):
            for z in batch_rows[i+1:]:
                lo=max(a['begin_qpc'],z['begin_qpc']); hi=min(a['end_qpc'],z['end_qpc'])
                if a['job_index']!=z['job_index'] and a['worker_tid']!=z['worker_tid'] and a['physical_core']!=z['physical_core'] and hi-lo>longest:
                    witness={'batch_id':a['batch_id'],'first_job':a['job_index'],'first_tid':a['worker_tid'],'first_core':a['physical_core'],'second_job':z['job_index'],'second_tid':z['worker_tid'],'second_core':z['physical_core'],'raw_begin_qpc':lo,'raw_end_qpc':hi}; longest=hi-lo
    require(parsed.get('physical_multicore_proven') is (witness is not None), 'Reader multicore claim disagrees with independent schedule calculation')
    raw_proof=parsed.get('proof')
    if witness:
        fields={'batch_id','first_job','first_tid','first_core','second_job','second_tid','second_core','begin_qpc','end_qpc'}
        require(type(raw_proof) is dict and set(raw_proof)==fields and all(uint(v) for v in raw_proof.values()) and raw_proof['first_job']!=raw_proof['second_job'] and raw_proof['first_tid']!=raw_proof['second_tid'] and raw_proof['first_core']!=raw_proof['second_core'] and raw_proof['begin_qpc']<raw_proof['end_qpc'], 'Malformed reader overlap witness')
        for side in ('first','second'):
            matches=[r for r in scored if r['batch_id']==raw_proof['batch_id'] and r['job_index']==raw_proof[side+'_job'] and r['worker_tid']==raw_proof[side+'_tid'] and r['physical_core']==raw_proof[side+'_core'] and r['begin_qpc']<=raw_proof['begin_qpc']<raw_proof['end_qpc']<=r['end_qpc']]
            require(matches,'Reader witness does not fit validated job and CSwitch intervals')
    else: require(raw_proof is None, 'Reader emitted witness without independent overlap')
    conservative=None
    if witness and witness['raw_end_qpc']-witness['raw_begin_qpc']>2*MARGIN:
        conservative={**witness,'begin_qpc':witness['raw_begin_qpc']+MARGIN,'end_qpc':witness['raw_end_qpc']-MARGIN,'margin_ticks_each_boundary':MARGIN}
    return {'pid':pid,'jobs':jobs,'worker_tids':sorted(workers),'score_cpu_slices':scored,'raw_overlap':witness,'conservative_overlap':conservative,'physical_multicore_verified':bool(conservative),'performance_improvement_verified':False}


def local_python_closure():
    tools_dir = PROJECT / 'tools'
    pending = [Path(__file__).resolve()]
    found = {}
    while pending:
        source = pending.pop().resolve()
        if source in found:
            continue
        found[source] = True
        tree = ast.parse(source.read_text(encoding='utf8'), filename=str(source))
        modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.update(alias.name.split('.')[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                modules.add(node.module.split('.')[0])
        for module in modules:
            candidate = tools_dir / (module + '.py')
            if candidate.is_file():
                pending.append(candidate.resolve())
    sources = sorted(found, key=lambda path: str(path).casefold())
    names = [path.name.casefold() for path in sources]
    require(len(names) == len(set(names)), 'Validator AST closure has colliding basenames')
    return sources


def freeze_validation_sources():
    sources = local_python_closure()
    before = {str(path): digest(path) for path in sources}
    validation_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_') + uuid.uuid4().hex[:12]
    directory = PROJECT / 'evidence/found_value_cpu_capture' / 'validators' / validation_id
    frozen_dir = directory / 'inputs'
    frozen_dir.mkdir(parents=True, exist_ok=False)
    records = []
    for source in sources:
        target = frozen_dir / source.name
        shutil.copy2(source, target)
        require(digest(target) == before[str(source)], 'Frozen validator source hash differs: ' + source.name)
        records.append({'original_source_path': str(source), 'original_source_sha256': before[str(source)], 'frozen': artifact(target)})
    after = {str(path): digest(path) for path in sources}
    require(before == after, 'Validator source closure changed during freeze')
    return {'validation_id': validation_id, 'directory': directory, 'sources': sources,
            'validators': records, 'source_hashes_before': before, 'source_hashes_after': after,
            'inputs_unchanged': True}


def refresh_source_hashes(context):
    after = {str(path): digest(path) for path in context['sources']}
    context['source_hashes_after'] = after
    context['inputs_unchanged'] = context['source_hashes_before'] == after


def validate_existing_capture(context):
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--capture',required=True); p.add_argument('--reader-proof',type=Path,required=True); p.add_argument('--sdk-proof',type=Path,required=True); p.add_argument('--found-value-runtime-report',dest='runtime_proof',type=Path,required=True); a=p.parse_args()
    require(re.fullmatch(r'\d{8}T\d{6}Z_[0-9a-f]{12}',a.capture) is not None,'Invalid immutable capture ID')
    cap_path=PROJECT/'evidence/found_value_cpu_capture'/a.capture/'result.json'; cap=json.loads(cap_path.read_text(encoding='utf8')); check_artifacts(cap)
    require(cap.get('status')=='ACTUAL_FOUND_VALUE_CPU_TRACE_RETAINED_PENDING_STRICT_VALIDATION' and cap.get('capture_started') is True and cap.get('gamecore_loaded') is True and cap.get('inputs_unchanged') is True,'Capture provenance incomplete')
    before=cap.get('input_hashes_before'); after=cap.get('input_hashes_after')
    require(isinstance(before,dict) and len(before)==5 and before==after and all(isinstance(k,str) and re.fullmatch(r'[0-9a-f]{64}',v) for k,v in before.items()),'Capture frozen input hash closure differs')
    frozen_rows=cap.get('inputs'); require(isinstance(frozen_rows,list) and len(frozen_rows)==6,'Capture did not retain five source inputs and its generated WPR profile')
    for index,(source,expected_hash) in enumerate(before.items()):
        row=frozen_rows[index]; expected_path=PROJECT/'evidence/found_value_cpu_capture'/a.capture/'inputs'/f'{index:02d}_{Path(source).name}'
        require(Path(row.get('path','')).resolve()==expected_path.resolve() and row.get('sha256')==expected_hash,'Frozen capture input path/hash differs')
    profile_row=frozen_rows[5]; require(Path(profile_row.get('path','')).resolve()==(PROJECT/'evidence/found_value_cpu_capture'/a.capture/'inputs'/'found_value_cpu.wprp').resolve(),'Generated WPR profile was not retained as the last frozen input')
    require(cap.get('capture_id')==a.capture and cap.get('input_layout')=='SHARED_FACTS' and cap.get('reader_component_proof',{}).get('path')==str(a.reader_proof.resolve()) and cap.get('shared_sdk_proof',{}).get('path')==str(a.sdk_proof.resolve()) and cap.get('shared_sdk_proof',{}).get('sha256')==digest(a.sdk_proof.resolve()) and cap.get('runtime_prerequisite',{}).get('path')==str(a.runtime_proof.resolve()),'Capture typed proof references differ from validator inputs')
    expected_profile=PROJECT/'evidence/found_value_cpu_capture'/a.capture/'inputs'/'found_value_cpu.wprp'; require(Path(cap.get('wpr_profile',{}).get('path','')).resolve()==expected_profile.resolve(),'WPR profile is not the frozen capture profile')
    profile=expected_profile.read_text(encoding='utf8'); require(PROVIDER.strip('{}').casefold() in profile.casefold() and 'ProcessThread' in profile and 'CSwitch' in profile and 'CpuConfig' in profile,'Frozen WPR profile omits the exact provider or kernel scheduling sources')
    commands={row['name']:row for row in cap.get('commands',[])}; require(len(commands)==len(cap.get('commands',[])),'Duplicate capture lifecycle command')
    for name in ('global_status_before','owned_status_before','profile_details','start','sdk_run','stop','topology_before','topology_after','reader','owned_status_after','global_status_after'):
        require(name in commands and commands[name]['exit_code']==0 or name=='reader' and name in commands and commands[name]['exit_code']==3,'Capture lifecycle command failed: '+name)
    for name in ('global_status_before','owned_status_before','owned_status_after','global_status_after'):
        require(b'WPR is not recording' in Path(commands[name]['log']['path']).read_bytes(),'WPR was not idle outside the owned capture')
    require(commands['start']['command'][-2:]==['-instancename','ZeroSisFoundValue_'+a.capture] and commands['stop']['command'][-2:]==['-instancename','ZeroSisFoundValue_'+a.capture],'WPR start/stop escaped the uniquely owned instance')
    etl_path=PROJECT/'Build/FoundValueCpuCapture'/a.capture/'found_value_cpu.etl'; require(Path(cap.get('etl',{}).get('path','')).resolve()==etl_path.resolve(),'Retained ETL escaped its unique build directory')
    reader=json.loads(a.reader_proof.read_text(encoding='utf8')); sdk=json.loads(a.sdk_proof.read_text(encoding='utf8')); runtime_proof=json.loads(a.runtime_proof.read_text(encoding='utf8'))
    for doc in (reader,sdk,runtime_proof): check_artifacts(doc)
    require(a.reader_proof.resolve()==(PROJECT/'evidence/found_value_cpu_trace'/READER_RUN/'conformance.json').resolve(),'Reader proof differs from the pinned capture contract')
    sdk_path=a.sdk_proof.resolve(); sdk_root=(PROJECT/'evidence/found_value_shared_sdk').resolve()
    require(sdk_path.is_relative_to(sdk_root) and sdk_path.name=='build_result.json' and re.fullmatch(r'\d{8}T\d{6}Z_[0-9a-f]{12}',sdk_path.parent.name) is not None,'SDK prerequisite is not an immutable unique shared-SDK build report')
    runtime_root=(PROJECT/'evidence/found_value_shared_sdk_runtime').resolve(); runtime_path=a.runtime_proof.resolve()
    require(runtime_path.is_relative_to(runtime_root) and runtime_path.name=='conformance.json' and re.fullmatch(r'\d{8}T\d{6}Z_[0-9a-f]{12}',runtime_path.parent.name) is not None,'Runtime prerequisite is not one immutable shared-SDK runtime proof')
    require(reader.get('status')=='FOUND_VALUE_CPU_TRACE_OFFLINE_PASS' and reader.get('run_id')==READER_RUN and reader.get('schema')=='zerosisfoundvalue.cpu_trace_conformance.v1','Unexpected frozen reader proof')
    require(bool(reader.get('source_hashes_before')) and reader['source_hashes_before']==reader.get('source_hashes_after') and bool(reader.get('dependency_closure_hashes_before')) and reader['dependency_closure_hashes_before']==reader.get('dependency_closure_hashes_after'),'Reader component source/dependency hashes changed')
    require(all(type(reader.get('builds',{}).get(mode,{}).get('checks')) is int and reader['builds'][mode]['checks']>=14 and reader['builds'][mode].get('capture_started') is False and reader['builds'][mode].get('gamecore_loaded') is False for mode in ('O2','Od')),'Reader O2/Od frozen component checks did not pass offline')
    reader_path=Path(reader.get('reader_artifact',{}).get('path','')).resolve(); reader_build=(PROJECT/'Build/FoundValueCpuTrace'/READER_RUN).resolve()
    require(reader_path==reader_build/'reader_o2'/'found_value_cpu_trace_reader.exe' and reader.get('builds',{}).get('reader_help',{}).get('exe_sha256')==reader.get('reader_artifact',{}).get('sha256') and 'PROCESS_TRACE_MODE_EVENT_RECORD | PROCESS_TRACE_MODE_RAW_TIMESTAMP' in Path(reader.get('frozen_inputs',{}).get('reader',{}).get('path','')).read_text(encoding='utf8'),'Reader executable/source is not the pinned raw-QPC reader artifact')
    require(sdk.get('status')=='FOUND_VALUE_SHARED_SDK_CANDIDATE_LINKED' and sdk.get('input_layout')=='SHARED_FACTS' and sdk.get('cpu_trace_provider_guid','').casefold()==PROVIDER.casefold() and sdk.get('cpu_trace_provider_name')=='ZeroSis.FoundValueCpuTrace' and sdk.get('cpu_trace_header',{}).get('sha256')==reader.get('frozen_inputs',{}).get('header',{}).get('sha256') and sdk.get('input_hashes_before')==sdk.get('input_hashes_after') and sdk.get('inputs_unchanged') is True and sdk.get('active_sdk_updated') is False and sdk.get('stage_updated') is False,'Shared SDK input/provider/header/component proof mismatch')
    validate_reader_component_reference(sdk, sdk_path, a.reader_proof.resolve(), digest(a.reader_proof.resolve()))
    require(runtime_proof.get('status')=='ACTUAL_SDK_FOUND_VALUE_ORDERED_RESULTS_AND_RESTORE_PASS' and runtime_proof.get('input_layout')=='SHARED_FACTS' and runtime_proof.get('gamecore_loaded') is True and runtime_proof.get('physical_multicore_verified') is False,'Missing passing shared-layout FoundValue runtime matrix prerequisite')
    proof_runs=runtime_proof.get('runs',[]); require(isinstance(proof_runs,list) and runtime_proof.get('shared_layout_records_verified') is True and 4 in runtime_proof.get('found_value_worker_settings',[]) and all(any(r.get('found_value_workers')==4 and r.get('language')==lang and r.get('found_value_input_layout')=='SHARED_FACTS' and r.get('shared_input_layouts') for r in proof_runs) for lang in ('en_US','ko_KR')),'Runtime proof does not cover shared worker-four EN/KO layouts')
    require(cap.get('reader',{}).get('path')==reader.get('reader_artifact',{}).get('path') and cap.get('reader',{}).get('sha256')==reader.get('reader_artifact',{}).get('sha256'),'Capture topology/ETL reader differs from frozen component artifact')
    rp=json.loads(Path(cap['reader_result']['path']).read_text(encoding='utf8')); topo=json.loads(Path(cap['topology_before']['path']).read_text(encoding='utf8')); topo_after=json.loads(Path(cap['topology_after']['path']).read_text(encoding='utf8')); analysis=validate_etl(rp,topo)
    validate_topology(topo_after); require({k:v for k,v in topo.items() if k!='boot_time_100ns'}=={k:v for k,v in topo_after.items() if k!='boot_time_100ns'} and abs(topo['boot_time_100ns']-topo_after['boot_time_100ns'])<=20_000_000,'Captured machine topology changed during ETW recording')
    runtime=json.loads(Path(cap['sdk_run']['path']).read_text(encoding='utf8')); check_artifacts(runtime)
    require(runtime.get('status')=='ISOLATED_NATIVE_SAVE_RESTORE_EXTENDED_PASS' and runtime.get('exit_code')==0 and runtime.get('timed_out') is False and runtime.get('extra_restored_turns')==48 and runtime.get('extended_turns_verified') is True and runtime.get('candidate_inputs_unchanged') is True and runtime.get('accepted_bundle_unchanged') is True and runtime.get('cleanup_completed') is True and runtime.get('module_unloaded') is True,'Captured SDK execution did not complete the unchanged 50-turn workload')
    pid=cap.get('process_id'); sdkid=cap.get('sdk_run_id'); require(uint(pid,32) and pid>0 and runtime.get('process_id')==pid and sdkid and runtime.get('found_value_cpu_trace_enabled') is True,'Actual captured process/trace flag does not bind')
    request=json.loads(Path(runtime['request']['path']).read_text(encoding='utf8')); check_artifacts(request)
    sdk_copy=request.get('found_value_sdk_build',{}); require(request.get('run_id')==sdkid and request.get('found_value_cpu_trace_enabled') is True and request.get('found_value_input_layout')=='SHARED_FACTS' and request.get('found_value_workers')==4 and request.get('found_value_cpu_trace_environment_overrides')=={'ZEROSIS_FOUND_VALUE_CPU_TRACE':'1'} and request.get('inherited_found_value_cpu_trace_environment_removed') is True and request.get('city_site_cpu_trace_enabled') is False and request.get('city_site_workers')==0 and sdk_copy.get('sha256')==digest(sdk_path) and Path(sdk_copy.get('path','')).resolve()==(PROJECT/'evidence/save_restore'/sdkid/'found_value_sdk_build.json').resolve(),'Launch request did not bind the immutable shared SDK and Found-only trace opt-in')
    matches=[r for r in proof_runs if r.get('language')==cap.get('language') and r.get('found_value_workers')==4 and r.get('found_value_input_layout')=='SHARED_FACTS']; require(len(matches)==1,'Runtime prerequisite lacks one same-language shared worker-four row')
    matrix_run=matches[0]; captured_input_hashes={Path(item['path']).name:item['sha256'] for item in request.get('inputs',[])}
    require(captured_input_hashes==matrix_run.get('inputs') and request.get('environment_overrides',{}).get('ZEROSIS_EXPLORE_WORKERS')=='0' and matrix_run.get('workers')==0 and matrix_run.get('final_turn')==50,'Captured host/SDK/workload identity differs from its verified shared runtime matrix row')
    stdout=Path(runtime['stdout']['path']).read_text(encoding='utf8'); all_lines=stdout.splitlines(); traces=[]; layout_calls=[]; layout_call_set=set()
    positions=[i for i,line in enumerate(all_lines) if line.startswith('ZEROSIS_FOUND_VALUE_LAYOUT ')]; last_batch=0
    restore_boundaries=[i for i,line in enumerate(all_lines) if line=='NATIVE_RESTORE_FRESH_SESSION=true']
    require(len(restore_boundaries)==1,'Captured runtime lacks its unique fresh-session restore boundary')
    require(positions,'No typed shared-layout rows bind the ETW batch IDs')
    for i in positions:
        require(i>=3 and all_lines[i-3].startswith('ZEROSIS_FOUND_VALUE_VALUES ') and all_lines[i-2].startswith('ZEROSIS_FOUND_VALUE_AREAS ') and all_lines[i-1].startswith('ZEROSIS_FOUND_VALUE_TRACE '),'FoundValue LAYOUT/results/trace records are not adjacent and ordered')
        def fields(line):
            out={}
            for atom in line.split()[1:]:
                k,sep,v=atom.partition('='); require(sep and k not in out,'Malformed or duplicate runtime metric'); out[k]=v
            return out
        layout=fields(all_lines[i]); values=fields(all_lines[i-3]); areas=fields(all_lines[i-2]); row=fields(all_lines[i-1])
        layout_keys={'version','call_id','input_layout','cpu_batch_id','common_bytes','plot_bytes','candidate_bytes','input_payload_bytes','dense_equivalent_bytes','jobs_total'}
        trace_order=['version','call_id','turn','player','starting_loc','mode','requested_workers','map_plots','revealed','helper_unique_plots','snapshot_us','worker_us','shadow_us','reduction_us','total_us','jobs_total','jobs_started','jobs_completed','workers_started','used_threads','max_overlap','worker_tids_job_counts']
        require(set(layout)==layout_keys and list(layout)==['version','call_id','input_layout','cpu_batch_id','common_bytes','plot_bytes','candidate_bytes','input_payload_bytes','dense_equivalent_bytes','jobs_total'] and set(values)=={'call_id','records'} and list(values)==['call_id','records'] and set(areas)=={'call_id','records'} and list(areas)==['call_id','records'] and list(row)==trace_order and layout['version']=='1' and layout['input_layout']=='SHARED_FACTS' and layout['call_id']==values['call_id']==areas['call_id']==row.get('call_id'),'Runtime layout schema/order/call linkage differs')
        require(all(re.fullmatch(r'\d+',layout[k]) for k in layout_keys-{'input_layout'}) and int(layout['call_id'])>0,'Shared layout contains invalid typed sizes or call ID')
        require(row.get('mode')=='owned-worker' and row.get('requested_workers')=='4','Captured trace contains a non-shared call')
        require(int(layout['jobs_total'])==int(row.get('jobs_completed','-1'))==int(row.get('jobs_total','-2')),'Layout and FoundValue metrics disagree on job count')
        count=int(layout['jobs_total']); batch=int(layout['cpu_batch_id']); plots=int(row['map_plots'])
        session=sum(boundary<i for boundary in restore_boundaries); identity=(session,int(layout['call_id']))
        require(identity not in layout_call_set,'Duplicate session-local shared layout call'); layout_call_set.add(identity); layout_calls.append(identity)
        require(count==int(row['revealed']) and 0<=count<=plots and all(re.fullmatch(r'\d+',row[k]) and uint(int(row[k])) for k in trace_order if k not in ('mode','worker_tids_job_counts')),'FoundValue runtime counts/timings are invalid')
        require(int(layout['common_bytes'])==240 and int(layout['plot_bytes'])==plots*116 and int(layout['candidate_bytes'])==count*1848 and int(layout['input_payload_bytes'])==int(layout['common_bytes'])+int(layout['plot_bytes'])+int(layout['candidate_bytes']) and int(layout['dense_equivalent_bytes'])==count*19140,'Runtime shared-payload byte accounting differs from the frozen layout contract')
        if count==0: require(batch==0 and row['worker_tids_job_counts']=='-','Empty FoundValue call has a CPU batch or worker IDs')
        else: require(batch>last_batch,'Nonempty FoundValue CPU batch IDs are not unique monotonic QPC identities'); last_batch=batch
        tids={} if row['worker_tids_job_counts']=='-' else {int(t):int(n) for t,n in (x.split(':') for x in row['worker_tids_job_counts'].split(','))}
        if count: require(tids and len(tids)==int(row['used_threads']) and sum(tids.values())==count and int(row['workers_started'])==4 and 1<=int(row['max_overlap'])<=int(row['used_threads'])<=4,'FoundValue worker/TID metrics do not account for the completed jobs')
        else: require(not tids and int(row['used_threads'])==int(row['workers_started'])==int(row['max_overlap'])==0,'Empty FoundValue call reports worker jobs')
        if count: traces.append({'session':session,'batch_id':batch,'call_id':int(layout['call_id']),'job_count':count,'fact_count':plots,'tids':tids})
    worker_trace_calls=[]; worker_trace_call_set=set()
    trace_order=['version','call_id','turn','player','starting_loc','mode','requested_workers','map_plots','revealed','helper_unique_plots','snapshot_us','worker_us','shadow_us','reduction_us','total_us','jobs_total','jobs_started','jobs_completed','workers_started','used_threads','max_overlap','worker_tids_job_counts']
    for index,line in enumerate(all_lines):
        if not line.startswith('ZEROSIS_FOUND_VALUE_TRACE '): continue
        row={}
        for atom in line.split()[1:]:
            key,sep,value=atom.partition('='); require(sep and key not in row,'Malformed captured FoundValue trace'); row[key]=value
        require(list(row)==trace_order,'Captured FoundValue trace schema/order differs')
        if row['mode']=='owned-worker':
            identity=(sum(boundary<index for boundary in restore_boundaries),int(row['call_id']))
            require(identity not in worker_trace_call_set,'Duplicate session-local FoundValue worker trace'); worker_trace_call_set.add(identity); worker_trace_calls.append(identity)
    require(layout_calls==worker_trace_calls,'Shared LAYOUT rows do not cover all owned-worker trace calls in order')
    require(traces,'No actual nonempty FoundValue worker trace rows in captured run')
    scopes={(s['process_id'],s['batch_id']):s for s in rp['batch_scopes']}; require(all(k[0]==pid for k in scopes),'ETL contains foreign process batches')
    require(len({(t['session'],t['call_id']) for t in traces})==len(traces) and len({t['batch_id'] for t in traces})==len(traces),'Duplicate session-local runtime call or CPU batch identifier')
    for tr in traces:
        s=scopes.get((pid,tr['batch_id'])); require(s is not None and s['job_count']==tr['job_count'],'ETL batch/job count does not match runtime metrics')
        jobs=[j for j in analysis['jobs'] if j['process_id']==pid and j['batch_id']==tr['batch_id']]
        require(len(jobs)==tr['job_count'] and all(j['fact_count']==tr['fact_count'] for j in jobs),'ETL job fact count/index set differs from captured runtime metrics')
        counts=Counter(j['worker_tid'] for j in jobs); require(dict(counts)==tr['tids'],'ETL worker TIDs/job distribution differs from runtime metrics')
    require(set((pid,t['batch_id']) for t in traces)==set(scopes),'ETL has unmatched or unreported batch')
    refresh_source_hashes(context)
    require(context['inputs_unchanged'], 'Validator source closure changed while validating capture')
    output={'status':'ACTUAL_FOUND_VALUE_SCHEDULED_DISTINCT_CORE_OVERLAP_PASS' if analysis['physical_multicore_verified'] else 'ACTUAL_FOUND_VALUE_CPU_TRACE_VALID_NO_CONSERVATIVE_OVERLAP','capture':artifact(cap_path),'reader_proof':artifact(a.reader_proof.resolve()),'shared_sdk_proof':artifact(a.sdk_proof.resolve()),'runtime_proof':artifact(a.runtime_proof.resolve()),'reader_result':cap['reader_result'],'sdk_run':cap['sdk_run'],'topology_before':cap['topology_before'],'validated_pid':pid,'matched_batch_count':len(traces),'matched_job_count':len(analysis['jobs']),'validated_worker_tids':analysis['worker_tids'],'raw_overlap':analysis['raw_overlap'],'conservative_overlap':analysis['conservative_overlap'],'qpc_margin_ticks_each_boundary':MARGIN,'physical_multicore_verified':analysis['physical_multicore_verified'],'performance_improvement_verified':False,'gamecore_loaded_during_capture':True,'new_capture_started_by_validator':False,'new_gamecore_execution_started_by_validator':False,'proof_scope':'FOUND_VALUE_PURE_KERNEL_JOB_CPU_SCHEDULE_OVERLAP_ONLY','validators':context['validators'],'validator_ast_closure_files':[Path(path).name for path in context['source_hashes_before']],'validator_source_hashes_before':context['source_hashes_before'],'validator_source_hashes_after':context['source_hashes_after'],'validator_inputs_unchanged':context['inputs_unchanged']}
    target=context['directory']/'conformance.json'; target.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf8'); check_artifacts(output); print(json.dumps({'status':output['status'],'validation_id':context['validation_id'],'proof':artifact(target)},ensure_ascii=False))


def main():
    context = None
    try:
        context = freeze_validation_sources()
        validate_existing_capture(context)
        return 0
    except Exception as error:
        if context is None:
            failure_id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_')+uuid.uuid4().hex[:12]
            target_dir=PROJECT/'evidence/found_value_cpu_capture'/'validators'/failure_id
            target_dir.mkdir(parents=True,exist_ok=False)
            target=target_dir/'conformance.json'
            context={'validation_id':failure_id,'validators':[],'source_hashes_before':{},'source_hashes_after':{},'inputs_unchanged':False}
        else:
            refresh_source_hashes(context)
            target_dir=context['directory']
        report={'status':'ACTUAL_FOUND_VALUE_CPU_TRACE_VALIDATION_FAILED','error':str(error),
                'capture_started_by_validator':False,'new_gamecore_execution_started_by_validator':False,
                'physical_multicore_verified':False,'performance_improvement_verified':False,
                'accepted_stage_promoted':False,'proof_scope':'FOUND_VALUE_PURE_KERNEL_JOB_CPU_SCHEDULE_OVERLAP_ONLY',
                'validators':context['validators'],'validator_source_hashes_before':context['source_hashes_before'],
                'validator_source_hashes_after':context['source_hashes_after'],'validator_inputs_unchanged':context['inputs_unchanged']}
        target=target_dir/'conformance.json'; target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        print(json.dumps({'status':report['status'],'validation_id':context['validation_id'],'proof':artifact(target),'error':str(error)},ensure_ascii=False),file=sys.stderr)
        return 1


if __name__=='__main__': raise SystemExit(main())
