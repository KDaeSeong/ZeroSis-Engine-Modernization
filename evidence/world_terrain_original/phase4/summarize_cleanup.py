"""Combine distinct owned cleanup receipts without counting aliases or volume drift."""
import json,sys
from pathlib import Path
sys.dont_write_bytecode=True
STAGE=Path(__file__).absolute().parent;PROJECT=STAGE.parents[2]
sys.path.insert(0,str(PROJECT/'tools'))
import build_exit_confirm_host as common
names=['cache_cpu/cleanup_result.json','model/cpu/cleanup_result.json','model/cpu_retry01/cleanup_result.json',
    'optics/cpu/cleanup_result.json','optics/cpu_retry01/cleanup_result.json','package_tests/attempt1/cleanup_result.json',
    'pipeline/cpu/cleanup_result.json','shader/attempt01/cleanup_result.json',
    'pair_preparation/20261115T055523Z_51738aa69964/cleanup_result.json']
rows=[]
for name in names:
    path=STAGE/name;value=json.loads(path.read_text('utf8'));assert value['status'].startswith('PASS')
    count=next((value[k] for k in ('deleted_files','files_deleted','retired_files') if k in value),None)
    allocation=next((value[k] for k in ('released_unique_allocated_bytes','allocated_bytes_released') if k in value),None)
    assert type(count) is int and type(allocation) is int
    rows.append(dict(receipt=common.artifact(path),files=count,predelete_unique_allocated_bytes=allocation))
result=dict(status='PASS_OWNED_SURFACE_INTERMEDIATES_SUMMARIZED',nonoverlapping_receipts=rows,
    deleted_files=sum(row['files'] for row in rows),known_unique_allocated_bytes_removed=sum(row['predelete_unique_allocated_bytes'] for row in rows),
    volume_delta_attributed=False,unknown_allocation_inferred=False,source_originals_settings_mods_default_or_user_saves_deleted=False,native_execution=False)
with (STAGE/'cleanup_summary.json').open('x',encoding='utf8') as f:json.dump(result,f,indent=2);f.write('\n')
print(json.dumps({k:v for k,v in result.items() if k!='nonoverlapping_receipts'}))
