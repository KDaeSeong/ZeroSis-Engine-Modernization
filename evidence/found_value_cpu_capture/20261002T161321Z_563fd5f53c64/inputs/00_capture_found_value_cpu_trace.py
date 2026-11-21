"""Capture one explicitly opted-in shared FoundValue workload into a retained ETL."""
from __future__ import annotations
import argparse, json, re, shutil, subprocess, sys, uuid
from datetime import datetime, timezone
from pathlib import Path
from collect_baseline import PROJECT, digest
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts

WPR=Path(r'C:\Windows\System32\wpr.exe')
RUNNER=PROJECT/'tools/run_new_game_probe.py'
ROOT=PROJECT/'evidence/found_value_cpu_capture'
READER_PROOF=PROJECT/'evidence/found_value_cpu_trace/20261002T151042Z_0d8765878529/conformance.json'
READER_ID='20261002T151042Z_0d8765878529'
PROVIDER='{49a604e1-6c99-4e01-b41d-73694f2290a6}'

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--language',choices=('en_US','ko_KR'),default='en_US'); p.add_argument('--timeout',type=int,default=150); p.add_argument('--sdk-proof',type=Path,required=True); p.add_argument('--found-value-runtime-report',dest='runtime_proof',type=Path,required=True); a=p.parse_args()
    if not 30<=a.timeout<=180: p.error('Bounded diagnostic timeout must be 30..180 seconds')
    rp=json.loads(READER_PROOF.read_text(encoding='utf8')); check_artifacts(rp)
    if rp.get('status')!='FOUND_VALUE_CPU_TRACE_OFFLINE_PASS' or rp.get('run_id')!=READER_ID: raise RuntimeError('Pinned FoundValue reader component proof is not passing')
    reader=Path(rp['reader_artifact']['path']); sdk_path=a.sdk_proof.resolve(); sdk=json.loads(sdk_path.read_text(encoding='utf8')); check_artifacts(sdk)
    sdk_root=(PROJECT/'evidence/found_value_shared_sdk').resolve()
    if not sdk_path.is_relative_to(sdk_root) or sdk_path.name!='build_result.json' or not re.fullmatch(r'\d{8}T\d{6}Z_[0-9a-f]{12}',sdk_path.parent.name): raise RuntimeError('SDK proof must be one immutable shared-SDK build report')
    if sdk.get('status')!='FOUND_VALUE_SHARED_SDK_CANDIDATE_LINKED' or sdk.get('input_layout')!='SHARED_FACTS' or sdk.get('cpu_trace_provider_guid','').casefold()!=PROVIDER.casefold() or sdk.get('cpu_trace_provider_name')!='ZeroSis.FoundValueCpuTrace' or sdk.get('cpu_trace_header',{}).get('sha256')!=rp.get('frozen_inputs',{}).get('header',{}).get('sha256') or sdk.get('cpu_trace_component',{}).get('sha256')!=digest(READER_PROOF): raise RuntimeError('Shared FoundValue SDK proof/provider/header/component contract mismatch')
    runtime_proof=json.loads(a.runtime_proof.resolve().read_text(encoding='utf8')); check_artifacts(runtime_proof)
    runtime_root=(PROJECT/'evidence/found_value_shared_sdk_runtime').resolve(); runtime_path=a.runtime_proof.resolve()
    if not runtime_path.is_relative_to(runtime_root) or runtime_path.name!='conformance.json' or not re.fullmatch(r'\d{8}T\d{6}Z_[0-9a-f]{12}',runtime_path.parent.name): raise RuntimeError('Runtime prerequisite must be one immutable shared-SDK proof')
    runtime_rows=runtime_proof.get('runs',[])
    if runtime_proof.get('status')!='ACTUAL_SDK_FOUND_VALUE_ORDERED_RESULTS_AND_RESTORE_PASS' or runtime_proof.get('input_layout')!='SHARED_FACTS' or runtime_proof.get('shared_layout_records_verified') is not True or 4 not in runtime_proof.get('found_value_worker_settings',[]) or not all(any(r.get('language')==lang and r.get('found_value_workers')==4 and r.get('found_value_input_layout')=='SHARED_FACTS' and r.get('shared_input_layouts') for r in runtime_rows) for lang in ('en_US','ko_KR')) or not any(r.get('language')==a.language and r.get('found_value_workers')==4 and r.get('found_value_input_layout')=='SHARED_FACTS' and r.get('shared_input_layouts') for r in runtime_rows): raise RuntimeError('Shared FoundValue runtime matrix proof is not passing for both languages and requested capture language')
    run_id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_')+uuid.uuid4().hex[:12]; ev=ROOT/run_id; build=PROJECT/'Build/FoundValueCpuCapture'/run_id
    ev.mkdir(parents=True,exist_ok=False); build.mkdir(parents=True,exist_ok=False); temp=build/'wpr_temporary'; temp.mkdir()
    instance='ZeroSisFoundValue_'+run_id; etl=build/'found_value_cpu.etl'
    inputs=[Path(__file__).resolve(),RUNNER,READER_PROOF,sdk_path,a.runtime_proof.resolve()]; before={str(x):digest(x) for x in inputs}
    frozen=ev/'inputs'; frozen.mkdir(); frozen_rows=[]
    for i,src in enumerate(inputs):
        dest=frozen/f'{i:02d}_{src.name}'; shutil.copy2(src,dest)
        if digest(dest)!=before[str(src)]: raise RuntimeError('Capture input changed while freezing')
        frozen_rows.append(artifact(dest))
    profile_text='''<?xml version="1.0" encoding="utf-8"?>\n<WindowsPerformanceRecorder Version="1.0" Author="ZeroSis"><Profiles><SystemCollector Id="FoundValueSystemCollector" Name="ZeroSisFoundValueSystem"><BufferSize Value="1024"/><Buffers Value="32"/></SystemCollector><EventCollector Id="FoundValueMarkerCollector" Name="ZeroSisFoundValueMarkers"><BufferSize Value="128"/><Buffers Value="64"/></EventCollector><SystemProvider Id="FoundValueSystemProvider"><Keywords><Keyword Value="ProcessThread"/><Keyword Value="CSwitch"/><Keyword Value="CpuConfig"/></Keywords></SystemProvider><EventProvider Id="FoundValueMarkerProvider" Name="49a604e1-6c99-4e01-b41d-73694f2290a6" Level="5"/><Profile Id="ZeroSisFoundValue.Verbose.File" Name="ZeroSisFoundValue" Description="FoundValue job markers and physical CPU scheduling" DetailLevel="Verbose" LoggingMode="File"><Collectors><SystemCollectorId Value="FoundValueSystemCollector"><SystemProviderId Value="FoundValueSystemProvider"/></SystemCollectorId><EventCollectorId Value="FoundValueMarkerCollector"><EventProviders><EventProviderId Value="FoundValueMarkerProvider"/></EventProviders></EventCollectorId></Collectors></Profile></Profiles></WindowsPerformanceRecorder>\n'''
    profile=frozen/'found_value_cpu.wprp'; profile.write_text(profile_text,encoding='utf8'); frozen_rows.append(artifact(profile))
    report={'capture_id':run_id,'status':'FOUND_VALUE_CPU_CAPTURE_NOT_STARTED','instance_name':instance,'language':a.language,'input_layout':'SHARED_FACTS','inputs':frozen_rows,'reader_component_proof':artifact(READER_PROOF),'shared_sdk_proof':artifact(sdk_path),'runtime_prerequisite':artifact(a.runtime_proof.resolve()),'reader':artifact(reader),'wpr_profile':artifact(profile),'wpr':artifact(WPR),'capture_started':False,'gamecore_loaded':False,'physical_multicore_verified':False,'performance_improvement_verified':False,'accepted_stage_promoted':False,'commands':[]}
    def execute(name,cmd,timeout=30,env=None):
        cmd=[str(x) for x in cmd]; r=subprocess.run(cmd,cwd=PROJECT,env=env,capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW,timeout=timeout)
        log=ev/(name+'.log'); log.write_bytes(r.stdout+r.stderr); report['commands'].append({'name':name,'command':cmd,'exit_code':r.returncode,'log':artifact(log)}); return r
    started=False
    try:
        idle=execute('global_status_before',[WPR,'-status'])
        if idle.returncode or b'WPR is not recording' not in idle.stdout+idle.stderr: raise RuntimeError('Existing WPR session prevents isolated capture')
        prof=execute('profile_details',[WPR,'-profiledetails',str(profile)+'!ZeroSisFoundValue','-filemode'])
        profile_output=(prof.stdout+prof.stderr).decode('mbcs',errors='replace')
        if prof.returncode or not all(x in profile_output for x in ('CSwitch','ProcessThread')) or PROVIDER.strip('{}').casefold() not in profile_output.casefold(): raise RuntimeError('WPR rejected FoundValue/kernel profile')
        topo=ev/'topology_before.json'; snap=execute('topology_before',[reader,'--write-topology',topo])
        if snap.returncode or not topo.is_file(): raise RuntimeError('Capture-time topology snapshot failed')
        report['topology_before']=artifact(topo)
        own=execute('owned_status_before',[WPR,'-status','-instancename',instance])
        if own.returncode or b'WPR is not recording' not in own.stdout+own.stderr: raise RuntimeError('Owned WPR instance is not idle')
        start=execute('start',[WPR,'-start',str(profile)+'!ZeroSisFoundValue','-filemode','-recordtempto',temp,'-instancename',instance])
        if start.returncode: raise RuntimeError('Owned WPR start failed')
        started=report['capture_started']=True
        env=dict(__import__('os').environ); env.pop('ZEROSIS_FOUND_VALUE_CPU_TRACE',None)
        args=[sys.executable,'-B','-X','utf8',RUNNER,'--shared-lua','--sdk-new-game','--sdk-save-restore','--sdk-explore','--workers','0','--sdk-city-sites','--city-site-workers','0','--sdk-found-values','--found-value-layout','shared','--found-value-workers','4','--found-value-cpu-trace','--save-restore','--ui-popups','--fixture-promotions','--fixture-unit-actions','--extra-turns','48','--language',a.language,'--timeout',str(a.timeout)]
        run=execute('sdk_run',args,a.timeout+30,env); ids=re.findall(rb'^RUN_NEW_GAME (\d{8}T\d{6}Z_[0-9a-f]{12})\r?$',run.stdout,re.M)
        if len(ids)!=1: raise RuntimeError('SDK run did not emit exactly one retained run ID')
        sdkid=ids[0].decode('ascii'); result=PROJECT/'evidence/save_restore'/sdkid/'result.json'; runtime=json.loads(result.read_text(encoding='utf8')); check_artifacts(runtime)
        request=json.loads(Path(runtime['request']['path']).read_text(encoding='utf8')); check_artifacts(request)
        report.update(sdk_run=artifact(result),sdk_run_id=sdkid,process_id=runtime.get('process_id'),gamecore_loaded=True)
        if run.returncode or runtime.get('status')!='ISOLATED_NATIVE_SAVE_RESTORE_EXTENDED_PASS' or runtime.get('found_value_cpu_trace_enabled') is not True or request.get('found_value_cpu_trace_enabled') is not True or request.get('found_value_cpu_trace_environment_overrides')!={'ZEROSIS_FOUND_VALUE_CPU_TRACE':'1'} or request.get('inherited_found_value_cpu_trace_environment_removed') is not True or request.get('city_site_cpu_trace_enabled') is not False or request.get('city_site_workers')!=0 or request.get('found_value_sdk_build',{}).get('sha256')!=digest(sdk_path): raise RuntimeError('Actual SDK run does not match the frozen Found-only trace opt-in/shared SDK identity')
        report['runtime_prerequisite']=artifact(a.runtime_proof.resolve())
        stop=execute('stop',[WPR,'-stop',etl,'-instancename',instance],60)
        if stop.returncode or not etl.is_file(): raise RuntimeError('Could not stop owned WPR and retain ETL')
        started=False; report['etl']=artifact(etl)
        aftertop=ev/'topology_after.json'; snap=execute('topology_after',[reader,'--write-topology',aftertop])
        if snap.returncode: raise RuntimeError('Post-capture topology snapshot failed')
        report['topology_after']=artifact(aftertop)
        decoded=execute('reader',[reader,etl,'--topology',topo],120)
        if decoded.returncode not in (0,3): raise RuntimeError('Reader failed to decode ETL')
        payload=json.loads(decoded.stdout.decode('utf8','strict')); parsed=ev/'reader.json'; parsed.write_text(json.dumps(payload,indent=2)+'\n',encoding='utf8'); report['reader_result']=artifact(parsed)
        report['status']='ACTUAL_FOUND_VALUE_CPU_TRACE_RETAINED_PENDING_STRICT_VALIDATION'; return 0
    except Exception as e:
        report.update(status='FOUND_VALUE_CPU_CAPTURE_FAILED',error=str(e)); return 2
    finally:
        if started: execute('cancel_owned_after_failure',[WPR,'-cancel','-instancename',instance])
        execute('owned_status_after',[WPR,'-status','-instancename',instance]); execute('global_status_after',[WPR,'-status'])
        after={str(x):digest(x) for x in inputs}; report['input_hashes_before']=before; report['input_hashes_after']=after; report['inputs_unchanged']=before==after
        if before!=after: report['status']='FOUND_VALUE_CPU_CAPTURE_INPUT_CHANGED'
        target=ev/'result.json'; target.write_text(json.dumps(report,indent=2)+'\n',encoding='utf8'); print(json.dumps({'status':report['status'],'result':artifact(target)},ensure_ascii=False),flush=True)
if __name__=='__main__': raise SystemExit(main())
