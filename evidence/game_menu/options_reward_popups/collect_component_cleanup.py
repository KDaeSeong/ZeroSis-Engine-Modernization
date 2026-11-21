"""Read current reward-wave cleanup receipts once; never delete or rebuild.

Run only after Root explicitly releases the final audit. Metadata copies are
references, not additional unlink events. Master Host objects are out of scope.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from datetime import datetime,timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import sys

sys.dont_write_bytecode=True
STAGE=Path(__file__).absolute().parent
PROJECT=STAGE.parents[2]
sys.path.insert(0,str(PROJECT/'tools'))
from menu_suite_storage import storage

PRIOR=PROJECT/'evidence/game_menu/options_video_preview/component_cleanup.json'
INTEGRATION=STAGE/'integration/db7b393d669f766e/result.json'
COMPONENTS={'contract','view','binding'}
SKIP_CONTEXT=('inputs_before','inputs_after','immutable_v3_before','protected','prior','previous','historical','source_before','old_auxiliary','original_source')
MASTER_ROOTS={'uiwindowhost','interactivegameruntime','runtimeinputcache'}
TEMP_SUFFIXES={'.tmp','.obj','.rsp','.cmd','.pending','.packet','.bin','.pdb','.ilk','.exp','.lib','.map','.pyc'}
SHA=re.compile('[0-9a-fA-F]{64}')
SUPERSEDED_FAILED_BINDING_ATTEMPTS={'1665d79393da716c','2d0cf9835151bddb','33dbb9ba1da0aa3d','ef407e7185a2c038'}


def read(path):
    path=Path(path)
    raw=gzip.decompress(path.read_bytes()) if path.name.endswith('.gz') else path.read_bytes()
    if len(raw)>64*1024*1024:raise ValueError('Cleanup proof exceeds the bounded JSON reader')
    return json.loads(raw)


def key(path):return os.path.normcase(os.path.abspath(os.fspath(path))).casefold()


def within(path,root):
    try:return os.path.commonpath([key(path),key(root)])==key(root)
    except ValueError:return False


def identity(row):
    value=row.get('file_identity',row.get('file_id'))
    if isinstance(value,str):value=re.findall(r'\d+',value)
    if isinstance(value,(list,tuple)) and len(value)==2:return tuple(int(part) for part in value)
    return None


def event_key(row):return (key(row['path']),row['sha256'].lower(),identity(row),row.get('mtime_ns'))


def dictionaries(value,at=()):
    if isinstance(value,dict):
        yield at,value
        for name,child in value.items():yield from dictionaries(child,at+(str(name),))
    elif isinstance(value,list):
        for index,child in enumerate(value):yield from dictionaries(child,at+(str(index),))


def skipped(at):return any(any(token in part.casefold() for token in SKIP_CONTEXT) for part in at)


def deletion(row):
    status=row.get('result','')
    return (isinstance(row.get('path'),str) and isinstance(row.get('sha256'),str) and SHA.fullmatch(row['sha256']) is not None and
        isinstance(status,str) and 'NOT_DELETED' not in status.upper() and
        (status.upper().startswith('DELETED_') or status.upper().startswith('COMPRESSED_AND_DELETED_') or status.upper().startswith('REMOVED_SOURCE_')))


def artifact(path):
    path=Path(path).absolute();info=storage.ordinary(path)
    row=dict(path=str(path),sha256=storage.digest(path),allocated_bytes=storage.allocated(path),**storage.metadata(info))
    after=storage.metadata(storage.ordinary(path))
    if any(storage.metadata(info)[name]!=after[name] for name in ('bytes','file_identity','mtime_ns','file_attributes')):
        raise ValueError('Audit input changed during its read: '+str(path))
    return row


def check_ref(row):
    current=artifact(row['path'])
    for name in ('sha256','bytes','file_identity','mtime_ns','file_attributes'):
        if name not in row or row[name] is None:continue
        same=identity(current)==identity(row) if name=='file_identity' else current[name].lower()==row[name].lower() if name=='sha256' else current.get(name)==row[name]
        if not same:raise ValueError('Retained artifact differs: '+row['path']+' '+name)
    return current


def product_ref(at,row):
    if skipped(at) or not isinstance(row.get('path'),str) or not isinstance(row.get('sha256'),str) or not SHA.fullmatch(row['sha256']):return False
    path=Path(row['path']);suffix=path.suffix.casefold()
    if suffix=='.exe':
        return within(path,PROJECT/'Build') and not any(part.casefold() in MASTER_ROOTS for part in path.parts) and any(
            token in part.casefold() for part in at for token in ('build','executable','console','retained'))
    if suffix=='.png':return within(path,PROJECT/'evidence') and any(token in part.casefold() for part in at for token in ('cpu','image','preview','proof'))
    return False


def retired_failed_binding_product(row,events):
    """Only exact, fully receipted failed fixtures may lose a product path."""
    path=Path(row['path']);root=PROJECT/'Build/MenuRewardHostBinding'
    if not within(path,root):return None
    parts=path.relative_to(root).parts
    if len(parts)!=3 or parts[0] not in SUPERSEDED_FAILED_BINDING_ATTEMPTS:return None
    if (parts[1],parts[2]) not in {('component','MenuRewardHostBinding.exe'),('legacy','MenuOptionsHostBindingRegression.exe')}:return None
    matches=[]
    for event in events.values():
        if key(event['path'])!=key(path) or event['sha256'].lower()!=row['sha256'].lower():continue
        if identity(event) is None or type(event.get('mtime_ns')) is not int or type(event.get('bytes')) is not int or type(event.get('allocated_bytes')) is not int:continue
        if identity(row) is not None and identity(row)!=identity(event):continue
        if any(name in row and row[name] is not None and row[name]!=event[name] for name in ('bytes','mtime_ns')):continue
        matches.append(event)
    if len(matches)!=1 or os.path.lexists(path):return None
    return matches[0]


def documents(deliveries,baseline_ns):
    paths={key(INTEGRATION):INTEGRATION}
    for relative in deliveries:
        path=STAGE/relative
        if not within(path,STAGE) or path.name!='delivery.json':raise ValueError('Explicit delivery must remain inside this wave')
        paths[key(path)]=path
    for name in COMPONENTS|{'integration'}:
        root=STAGE/name
        if root.exists():
            for path in root.rglob('*'):
                if path.is_file() and (path.suffix=='.json' or path.name.endswith('.json.gz')) and any(token in path.name.casefold() for token in ('result','cleanup','delivery')):
                    paths[key(path)]=path
    loaded={};pins={};pending=list(paths.values())
    while pending:
        path=pending.pop();canonical=key(path)
        if canonical in loaded:continue
        pin=artifact(path);value=read(path);loaded[canonical]=(path,value);pins[canonical]=pin
        for at,row in dictionaries(value):
            if skipped(at) or not isinstance(row.get('path'),str):continue
            target=Path(row['path'])
            if not within(target,PROJECT/'evidence') or not target.is_file() or not (target.suffix=='.json' or target.name.endswith('.json.gz')):continue
            if not any(token in part.casefold() for part in at for token in ('result','report','cleanup','delivery','proof')):continue
            if target.stat().st_mtime_ns<baseline_ns:continue
            if key(target) not in loaded:pending.append(target)
    return list(loaded.values()),pins


def run(delivery_paths):
    output=STAGE/'component_cleanup.json'
    if output.exists():raise ValueError('Final component cleanup audit is single-use; preserve the existing result')
    baseline=read(STAGE/'storage_before.json');baseline_time=datetime.fromisoformat(baseline['utc'])
    baseline_ns=int(baseline_time.timestamp())*1000000000+baseline_time.microsecond*1000
    startup=read(STAGE/'startup.json');prior=read(PRIOR)
    prior_rows=[row for _,row in dictionaries(prior) if deletion(row)]
    prior_events={event_key(row) for row in prior_rows}
    prior_without_mtime={(key(row['path']),row['sha256'].lower(),identity(row)) for row in prior_rows if row.get('mtime_ns') is None}
    docs,proof_pins=documents(delivery_paths,baseline_ns)
    by_path={key(path):value for path,value in docs}
    for relative in delivery_paths:
        value=by_path[key(STAGE/relative)]
        if not str(value.get('status','')).startswith('PASS'):raise ValueError('All three component deliveries must be complete and passing: '+relative)
    root_result=by_path[key(INTEGRATION)]
    if not str(root_result.get('status','')).startswith('PASS'):raise ValueError('Latest Root integration is not passing')
    integration_rows=root_result.get('owned_intermediate_cleanup',[])
    if len(integration_rows)!=8 or sum(row.get('allocated_bytes',0) for row in integration_rows)!=4170568:
        raise ValueError('Expected Root integration eight-event4170568-byte cleanup receipt differs')
    events={};copies=[];excluded=[];missing=[];summary_checks=[];product_candidates=defaultdict(list);old_candidates={};gzip_paths={}
    for document,value in docs:
        pin=proof_pins[key(document)];own=value.get('owned_intermediate_cleanup')
        if isinstance(own,list) and 'owned_intermediate_allocated_bytes_removed' in value:
            actual=sum(row.get('allocated_bytes',0) for row in own if deletion(row))
            summary_checks.append(dict(proof=str(document),field='owned_intermediate_allocated_bytes_removed',recorded=value['owned_intermediate_allocated_bytes_removed'],computed=actual,matches=actual==value['owned_intermediate_allocated_bytes_removed']))
        for at,row in dictionaries(value):
            location='/'.join(at);reference=dict(proof=str(document),location=location)
            if deletion(row):
                event=event_key(row);path=Path(row['path'])
                historical=(event in prior_events or (type(row.get('mtime_ns')) is int and row['mtime_ns']<baseline_ns and event[:3] in prior_without_mtime))
                if historical or skipped(at):excluded.append(dict(**reference,path=row['path'],reason='PRIOR_OR_HISTORICAL_METADATA_NOT_CURRENT_DELETION'));continue
                if any(part.casefold() in MASTER_ROOTS for part in path.parts):excluded.append(dict(**reference,path=str(path),reason='MASTER_HOST_OR_RUNTIME_OUT_OF_COMPONENT_SCOPE'));continue
                if not (within(path,PROJECT/'Build') or within(path,PROJECT/'evidence')):excluded.append(dict(**reference,path=str(path),reason='OUTSIDE_COMPONENT_BUILD_OR_EVIDENCE'));continue
                if identity(row) is None or row.get('mtime_ns') is None or type(row.get('allocated_bytes')) is not int or type(row.get('bytes')) is not int:
                    missing.append(dict(**reference,row=row));continue
                if event in events:
                    retained=events[event]
                    for field in ('bytes','allocated_bytes'):
                        if retained[field]!=row[field]:raise ValueError('Duplicate deletion receipt disagrees: '+row['path']+' '+field)
                    retained['proofs'].append(reference);copies.append(dict(**reference,event_identity=list(event)));continue
                current=dict(row);current['proofs']=[reference];events[event]=current
            if product_ref(at,row):product_candidates[key(row['path'])].append((pin['mtime_ns'],str(document),location,row))
            if 'old_auxiliary' in location.casefold() and isinstance(row.get('path'),str) and isinstance(row.get('sha256'),str):old_candidates[key(row['path'])]=row
            if not skipped(at) and isinstance(row.get('path'),str) and str(row['path']).casefold().endswith('.gz'):
                path=Path(row['path'])
                if within(path,PROJECT/'evidence') and path.is_file() and path.stat().st_mtime_ns>=baseline_ns:gzip_paths[key(path)]=path
    if missing:raise ValueError('Current deletion receipt lacks complete identity/time/allocation fields: '+str(missing[0]['row']['path']))
    if any(not row['matches'] for row in summary_checks):raise ValueError('A current cleanup summary disagrees with its actual unlink rows')
    retained=[];retired_products=[]
    for canonical,choices in product_candidates.items():
        if canonical in old_candidates:continue
        _,proof,location,row=max(choices,key=lambda choice:(choice[0],choice[1],choice[2]))
        retired=retired_failed_binding_product(row,events)
        if retired is not None:
            retired_products.append(dict(reference=row,proof=proof,location=location,deletion_event=retired,
                reason='EXACT_SUPERSEDED_FAILED_BINDING_CONSOLE_WITH_FULL_DELETION_RECEIPT_AND_ABSENT_PATH'))
            continue
        now=check_ref(row)
        now.update(proof=proof,location=location,reason='LATEST_REFERENCED_CONSOLE_OR_REQUIRED_CPU_IMAGE');retained.append(now)
    if not any(row['path'].casefold().endswith('.exe') for row in retained) or not any(row['path'].casefold().endswith('.png') for row in retained):
        raise ValueError('Required latest console/CPU image preservation proofs missing')
    old_preserved=[dict(check_ref(row),state='PRESERVED_UNCLASSIFIED_OLD_AUXILIARY_CANDIDATE_NOT_DELETED') for row in old_candidates.values()]
    if len(old_preserved)!=3:raise ValueError('Expected three preserved old auxiliary candidates')
    absent=[];path_reuse=[]
    for row in events.values():
        path=Path(row['path'])
        if not os.path.lexists(path):row['currently_absent']=True;absent.append(row['path'])
        else:
            row['currently_absent']=False;current=artifact(path);row['current_path_artifact']=current
            path_reuse.append(dict(deleted_event=row,current=current))
    if path_reuse:raise ValueError('A current deleted intermediate pathname still exists: '+path_reuse[0]['current']['path'])
    component_roots={}
    for row in [*events.values(),*retained]:
        path=Path(row['path'])
        if within(path,PROJECT/'Build'):
            relative=path.relative_to(PROJECT/'Build')
            if relative.parts and relative.parts[0].casefold() not in MASTER_ROOTS:component_roots[key(PROJECT/'Build'/relative.parts[0])]=PROJECT/'Build'/relative.parts[0]
    inventories=[];temporary=[];unclassified=[];kept_paths={key(row['path']) for row in [*retained,*old_preserved]}
    for root in sorted(component_roots.values()):
        files=[]
        if root.exists():
            for directory,names,leaves in os.walk(root,followlinks=False):
                for name in names:
                    if os.stat(Path(directory)/name,follow_symlinks=False).st_file_attributes&0x400:raise ValueError('Component inventory contains a reparse directory')
                for name in leaves:
                    path=Path(directory)/name;row=artifact(path);files.append(row)
                    if key(path) not in kept_paths:
                        if path.suffix.casefold() in TEMP_SUFFIXES or 'pending' in name.casefold():temporary.append(row)
                        else:unclassified.append(row)
        inventories.append(dict(root=str(root),files=files,file_count=len(files)))
    for name in COMPONENTS|{'integration'}:
        root=STAGE/name
        if root.exists():
            for path in root.rglob('*'):
                if path.is_file() and (path.suffix.casefold() in {'.tmp','.obj','.rsp','.cmd','.pending','.pyc'} or 'pending' in path.name.casefold()):temporary.append(artifact(path))
            for path in root.rglob('*.gz'):
                if path.stat().st_mtime_ns>=baseline_ns:gzip_paths[key(path)]=path
    if temporary:raise ValueError('Current component temporary/pending residue remains: '+temporary[0]['path'])
    gzip_retained=[];seen_gzip_ids=set()
    for path in sorted(gzip_paths.values()):
        row=artifact(path);file_id=identity(row)
        if file_id not in seen_gzip_ids:seen_gzip_ids.add(file_id);gzip_retained.append(row)
    deleted=list(events.values());gross=sum(row['allocated_bytes'] for row in deleted);logical=sum(row['bytes'] for row in deleted)
    deleted_gzip=sum(row['allocated_bytes'] for row in deleted if row['path'].casefold().endswith('.gz'))
    retained_gzip=sum(row['allocated_bytes'] for row in gzip_retained)
    proof_after=[artifact(row['path']) for row in proof_pins.values()]
    observed_link_changes=[]
    for current in proof_after:
        initial=proof_pins[key(current['path'])]
        if any(current[name]!=initial[name] for name in ('sha256','bytes','file_identity','mtime_ns','file_attributes','allocated_bytes')):
            raise ValueError('A component proof changed during final aggregation')
        if current['links']!=initial['links']:observed_link_changes.append(dict(path=current['path'],before=initial['links'],after=current['links']))
    groups=defaultdict(list)
    for row in deleted:groups[(key(row['path']),row['sha256'].lower())].append(row)
    result=dict(schema='zerosis.options_reward_popups.component_cleanup.v1',status='PASS_CURRENT_COMPONENT_EVENT_DEDUP_RETENTION_AND_RESIDUE_AUDIT',
        utc=datetime.now(timezone.utc).isoformat(),scope='Read-only receipt aggregation. No cleanup, feature execution, rebuild, source edit, master Host or runtime action is performed.',
        collector=artifact(Path(__file__)),baseline=dict(path=str(STAGE/'storage_before.json'),utc=baseline['utc']),
        required_component_deliveries=[str(STAGE/path) for path in delivery_paths],proofs_before=list(proof_pins.values()),proofs_after=proof_after,observed_proof_link_count_changes=observed_link_changes,
        prior_cleanup_boundary=dict(component_report=artifact(PRIOR),component_unique_events=len(prior_events),startup_prior_deleted_paths_verified=startup['prior_deleted_paths_verified'],
            prior_component_and_master_events_added_to_current_gross=0,master_host_objects_excluded=True),
        exact_root_integration=dict(report=str(INTEGRATION),event_count=8,allocated_bytes=4170568),summary_checks=summary_checks,
        deletion_event_identity='Case-insensitive absolute path + SHA256 + original file ID + original mtime_ns. Copies are deduplicated; regenerated same-path files with distinct identity/time remain separate events.',
        deletion_events=deleted,deletion_event_count=len(deleted),unique_deleted_paths=len(set(row['path'].casefold() for row in deleted)),
        metadata_copy_references_omitted=copies,excluded_prior_or_out_of_scope_references=excluded,
        repeated_path_sha_distinct_events=[dict(path=rows[0]['path'],sha256=rows[0]['sha256'],events=len(rows),identities=[dict(file_identity=identity(row),mtime_ns=row['mtime_ns']) for row in rows]) for rows in groups.values() if len(rows)>1],
        all_current_deleted_paths_absent=True,gross_deleted_logical_bytes=logical,gross_deleted_allocated_bytes=gross,
        gzip_accounting=dict(current_wave_new_retained_gzip=gzip_retained,new_retained_unique_allocated_bytes=retained_gzip,
            deleted_gzip_allocated_bytes=deleted_gzip,retained_gzip_allocated_change=retained_gzip-deleted_gzip,
            nongzip_deleted_allocated_bytes=gross-deleted_gzip,net_deleted_allocation_after_retained_gzip_only=gross-retained_gzip,
            interpretation='Gross deletion allocations are receipt evidence. Subtract only newly retained component gzip allocations for this scoped net; this is neither total component growth nor project/volume free-space change. EXE/PNG/report growth is not silently subtracted.'),
        latest_retained_consoles_and_required_cpu_images=retained,old_auxiliary_candidates_preserved=old_preserved,
        superseded_failed_binding_products_retired=retired_products,
        component_inventories=inventories,current_wave_temporary_residue=temporary,other_unclassified_files_preserved=unclassified,
        files_deleted_by_audit=0,source_files_changed_by_audit=False,feature_tests_or_binaries_executed=False,native_host_sdk_hwnd_gpu_audio_executed=False,
        full_project_storage_change_claimed=False,volume_free_space_delta_claimed=False)
    with output.open('x',encoding='utf8',newline='\n') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(status=result['status'],report=str(output),events=len(deleted),gross_allocated_bytes=gross,new_retained_gzip_allocated_bytes=retained_gzip,
        net_after_retained_gzip_only=gross-retained_gzip,duplicates_omitted=len(copies),retained_products=len(retained),old_candidates=len(old_preserved),temporary_residue=0,files_deleted_by_audit=0)))


def main():
    cli=argparse.ArgumentParser(description=__doc__);cli.add_argument('--final-go',action='store_true',required=True)
    cli.add_argument('--delivery',action='append',default=[]);args=cli.parse_args()
    deliveries=args.delivery or ['contract/delivery.json','view/delivery.json','binding/delivery.json']
    if len(deliveries)!=3 or len(set(deliveries))!=3:cli.error('Exactly three completed component deliveries are required')
    run(deliveries)


if __name__=='__main__':main()
