"""Combine nonoverlapping owned cleanup receipts; never infer unknown allocation."""
import json,sys
from pathlib import Path
sys.dont_write_bytecode=True
STAGE=Path(__file__).absolute().parent;PROJECT=STAGE.parents[2]
sys.path.insert(0,str(PROJECT/'tools'))
import build_exit_confirm_host as common
def read(name):return json.loads((STAGE/name).read_text('utf8'))
model=read('model/current_model.json')['cleanup_totals']
rows=[dict(role='model_cpu_and_bytecode',receipt=common.artifact(STAGE/'model/current_model.json'),
    files=model['deleted_files'],known_allocated_bytes=model['released_unique_allocated_bytes'])]
for name in ('state/cpu/cleanup_result.json','package_tests/attempt1/cleanup_result.json','cache_cpu/cleanup_result.json'):
    value=read(name);assert value['status'].startswith('PASS')
    rows.append(dict(role=name,receipt=common.artifact(STAGE/name),
        files=value.get('deleted_files',value.get('retired_files')),known_allocated_bytes=value['released_unique_allocated_bytes']))
name='pair_preparation/20261115T034310Z_77ed882144d1/cleanup_result.json';value=read(name)
rows.append(dict(role='successful_host_objects_and_environment',receipt=common.artifact(STAGE/name),
    files=value['files_deleted'],known_allocated_bytes=value['allocated_bytes_released']))
name='cleanup_failed_discovery/result.json';value=read(name)
rows.append(dict(role='failed_discovery',receipt=common.artifact(STAGE/name),files=value['files_deleted'],
    known_allocated_bytes=value['summed_predelete_unique_allocation_bytes']))
for name in ('shader/attempt01/cleanup_result.json','shader/attempt02/cleanup_result.json','shader/attempt03/cleanup_result.json','shader/harness_retry_cleanup.json'):
    value=read(name);assert value['status'].startswith('PASS')
    rows.append(dict(role=name,receipt=common.artifact(STAGE/name),files=value['deleted_files'],
        known_allocated_bytes=None,logical_bytes=value['deleted_logical_bytes']))
result=dict(status='PASS_OWNED_INTERMEDIATE_CLEANUP_RECEIPTS_SUMMARIZED',nonoverlapping_receipts=rows,
    deleted_files=sum(row['files'] for row in rows),known_unique_allocated_bytes_removed=sum(row['known_allocated_bytes'] or 0 for row in rows),
    additional_shader_files_without_allocation_receipt=sum(row['files'] for row in rows if row['known_allocated_bytes'] is None),
    additional_shader_logical_bytes=sum(row.get('logical_bytes',0) for row in rows if row['known_allocated_bytes'] is None),
    unknown_allocation_inferred=False,volume_free_delta_attributed=False,
    current_host_sources_originals_mods_settings_or_user_saves_deleted=False,native_execution=False)
with (STAGE/'cleanup_summary.json').open('x',encoding='utf8') as f:json.dump(result,f,indent=2);f.write('\n')
print(json.dumps({k:v for k,v in result.items() if k!='nonoverlapping_receipts'}))
