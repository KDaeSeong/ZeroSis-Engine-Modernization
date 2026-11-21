"""Pure synthetic regressions for the retained FoundValue CPU-capture gate."""
from __future__ import annotations
import copy, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from verify_found_value_cpu_capture import validate_etl, validate_reader_component_reference

def fixture():
    topology={'schema':'zerosisfoundvalue.topology.v1','boot_time_100ns':100000000,'qpc_frequency':10000000,'os_version':{'major':10,'minor':0,'build':1},'processor_count':4,'topology':[{'group':0,'logical_processor':i,'physical_core':i} for i in range(4)]}
    parsed={'schema':'zerosisfoundvaluecpu.v1','provider_name':'ZeroSis.FoundValueCpuTrace','provider_guid':'{49a604e1-6c99-4e01-b41d-73694f2290a6}','etl_opened':True,'clock_is_qpc':True,'qpc_frequency':10000000,'physical_multicore_proven':True,'status':'ETW_DISTINCT_CORE_OVERLAP_PROVEN','topology_binding':{'same_current_boot':True,'etl_boot_time_100ns':100000000,'etl_perf_frequency':10000000,'etl_clock_type_reserved_flags':1,'etl_processor_count':4,'captured_sidecar_boot_time_100ns':100000000,'topology_source':'captured_sidecar'},'loss':{'events_lost':0,'buffers_lost':0,'reader_events_lost':0,'buffers_read':2},'cswitch_counts':{'all':100,'worker_related':2,'worker_related_unmapped_cpu':0},'kernel_event_decode':{'tdh_error_not_found_fallback':True,'process_provider_guid':'{3d6fa8d0-fe05-11d0-9dda-00c04fd7ba7c}','process_lifecycle_versions':[{'version':4,'count':2}],'process_lifecycle_records_observed':2,'process_events_emitted_worker_pid_only':2,'process_payload_strings_read':False,'thread_provider_guid':'{3d6fa8d1-fe05-11d0-9dda-00c04fd7ba7c}','thread_lifecycle_versions':[{'version':3,'count':4}],'thread_lifecycle_records_observed':4,'thread_worker_lifecycle_rows_emitted':4,'cswitch_versions':[{'version':5,'count':100}],'cswitch_records_observed':100,'identity_prefix_contract':'ProcessId after pointer-sized UniqueProcessKey; thread ProcessId,TThreadId; CSwitch NewThreadId,OldThreadId'},'topology':topology['topology'],'batch_scopes':[{'process_id':44,'batch_id':1,'owner_tid':5,'begin_qpc':99,'end_qpc':115,'job_count':2}],'markers':[],'process_events':[{'event_id':3,'process_id':44,'timestamp':80},{'event_id':4,'process_id':44,'timestamp':140}],'thread_events':[],'worker_cpu_slices':[],'proof':None}
    for tid,idx,lo,hi in ((21,0,102,110),(22,1,103,111)):
        for phase,qpc in (('begin',lo),('end',hi)):
            parsed['markers'].append({'phase':phase,'batch_id':1,'job_index':idx,'process_id':44,'worker_tid':tid,'fact_count':960,'qpc':qpc})
        parsed['thread_events'] += [{'event_id':3,'process_id':44,'thread_id':tid,'timestamp':90},{'event_id':4,'process_id':44,'thread_id':tid,'timestamp':130}]
    parsed['worker_cpu_slices']=[{'process_id':44,'worker_tid':21,'processor_index':0,'group':0,'group_processor':0,'physical_core':0,'begin_qpc':102,'end_qpc':110},{'process_id':44,'worker_tid':22,'processor_index':1,'group':0,'group_processor':1,'physical_core':1,'begin_qpc':103,'end_qpc':111}]
    parsed['proof']={'batch_id':1,'first_job':0,'first_tid':21,'first_core':0,'second_job':1,'second_tid':22,'second_core':1,'begin_qpc':103,'end_qpc':110}
    return parsed,topology

def rejects(mutator):
    p,t=fixture(); mutator(p,t)
    try: validate_etl(p,t)
    except (ValueError,KeyError,TypeError): return
    raise AssertionError('Invalid capture fixture was accepted')

def main():
    p,t=fixture(); result=validate_etl(p,t); assert result['physical_multicore_verified'] and result['conservative_overlap']['begin_qpc']==104 and result['conservative_overlap']['end_qpc']==109
    for ticks in (1,2,3):
        short,topo=fixture()
        for marker in short['markers']:
            marker['qpc']=102 if marker['phase']=='begin' else 102+ticks
        for row in short['worker_cpu_slices']:
            row['begin_qpc']=102; row['end_qpc']=102+ticks
        short['proof']['begin_qpc']=102; short['proof']['end_qpc']=102+ticks
        short_result=validate_etl(short,topo)
        assert short_result['raw_overlap'] and short_result['raw_overlap']['raw_end_qpc']-short_result['raw_overlap']['raw_begin_qpc']==ticks
        assert short_result['physical_multicore_verified'] is (ticks==3)
        assert (short_result['conservative_overlap'] is None) is (ticks<3)
    checks=[lambda p,t:p['loss'].__setitem__('buffers_lost',1),lambda p,t:p['topology_binding'].__setitem__('etl_perf_frequency',1),lambda p,t:p['markers'][0].__setitem__('extra',0),lambda p,t:p['thread_events'].append(copy.deepcopy(p['thread_events'][0])),lambda p,t:p['worker_cpu_slices'][0].__setitem__('physical_core',2),lambda p,t:p['batch_scopes'][0].__setitem__('job_count',3),lambda p,t:p.__setitem__('physical_multicore_proven',False),lambda p,t:p['worker_cpu_slices'][1].__setitem__('processor_index',0)]
    for test in checks: rejects(test)
    version_mutations=[lambda p,t:p['kernel_event_decode']['cswitch_versions'][0].__setitem__('version',6),
                       lambda p,t:p['kernel_event_decode']['cswitch_versions'][0].__setitem__('count',99),
                       lambda p,t:p['kernel_event_decode']['thread_lifecycle_versions'].append({'version':3,'count':1}),
                       lambda p,t:p['kernel_event_decode'].__setitem__('process_lifecycle_versions',{'4':2})]
    for test in version_mutations: rejects(test)
    sdk_path=Path('synthetic_sdk/unique/build_result.json').resolve()
    reader_path=Path('synthetic_reader/conformance.json').resolve(); reader_hash='a'*64
    component_path=sdk_path.parent/'frozen/018/conformance.json'
    sdk={'cpu_trace_component':{'path':str(component_path),'sha256':reader_hash},
         'frozen_inputs':[{'original_path':str(reader_path),'path':str(component_path),'sha256':reader_hash}]}
    validate_reader_component_reference(sdk,sdk_path,reader_path,reader_hash)
    mutations=[lambda s:s['cpu_trace_component'].__setitem__('path',str(reader_path)),
               lambda s:s['cpu_trace_component'].__setitem__('sha256','b'*64),
               lambda s:s.__setitem__('frozen_inputs',[]),
               lambda s:s['frozen_inputs'].append(copy.deepcopy(s['frozen_inputs'][0])),
               lambda s:s['frozen_inputs'][0].__setitem__('path',str(sdk_path.parent/'frozen/019/conformance.json'))]
    for mutate in mutations:
        bad=copy.deepcopy(sdk); mutate(bad)
        try: validate_reader_component_reference(bad,sdk_path,reader_path,reader_hash)
        except (ValueError,KeyError,TypeError): continue
        raise AssertionError('Invalid frozen reader provenance was accepted')
    print('PASS|20|physical overlap, two-tick margin rejection, exact kernel-version schema, capture and frozen-reader provenance cases')
if __name__=='__main__': main()
