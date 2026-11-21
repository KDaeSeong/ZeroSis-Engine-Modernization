"""Apply one root-reviewed hash-pinned old59c retirement, never a blanket cleanup."""
from __future__ import annotations
from collections import Counter
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

PLANNER=Path(__file__).with_name('plan_superseded_59c.py')
spec=importlib.util.spec_from_file_location('exact59c_plan',PLANNER);scope=importlib.util.module_from_spec(spec);spec.loader.exec_module(scope)
from civ5_ui_assets import _unlink_font_target_without_attribute_changes as unlink
from menu_suite_storage import storage
import retained_menu_suite_host_input as menu

PLAN_SHA='2463ab4db9be99423038ba382cf141528e56acb0d8d4d78a013c98f2ac38b0a1'
SUPPLEMENT_SHA='c9340d4e0982d9e1d7340f63667081715026935eadeba91dc768a235b7f456fd'
DIRECTORY=scope.OUTPUT
PLAN=DIRECTORY/'whole_root_cleanup_plan.json'
SUPPLEMENT=DIRECTORY/'protection_supplement.json'
require=scope.require


def write_new(path,value):
    with path.open('x',encoding='utf8') as stream:json.dump(value,stream,indent=2);stream.write('\n')


def main():
    require(sys.argv[1:]==['--execute'],'Only the reviewed one-shot --execute action is supported')
    require(storage.digest(PLAN)==PLAN_SHA and storage.digest(SUPPLEMENT)==SUPPLEMENT_SHA,'Reviewed plan/protection SHA differs')
    plan,supp=scope.read(PLAN),scope.read(SUPPLEMENT)
    root=Path(plan['exact_root']);require(root==scope.OLD_ROOT and root.resolve(strict=True)==root and root.parent==scope.PROJECT/'Build/UiWindowHost','Exact old root escaped approved scope')
    require(plan['file_count']==711 and plan['directory_count']==85 and len(plan['external_hardlink_keepers'])==644,'Reviewed leaf inventory differs')
    require(plan['delete_executed'] is False and plan['protected_path_overlap']==0 and supp['protected_paths_overlap']==0,'Invalid one-shot plan state')
    require(not (DIRECTORY/'apply_started.json').exists() and not (DIRECTORY/'whole_root_cleanup_result.json').exists(),'Inspect existing action/partial receipt; never repeat an applied plan')
    scope.verify(plan['planner']);scope.verify(plan['protection_supplement'])
    for row in plan['helper_inputs']:scope.verify(row)
    scope.verify(supp['authoritative_baseline']);baseline=scope.read(supp['authoritative_baseline']['path'])['protected_artifacts']
    require(len(baseline)==4015 and supp['additional_protected_paths']==1009,'Full protected scope differs')
    protected=baseline+supp['additional_protected_artifacts'];require(len(protected)==5024 and len({menu.key(x['path']) for x in protected})==5024,'Protection rows overlap or are missing')
    protected_keys={menu.key(x['path']) for x in protected}
    require(not any(Path(x['path']).is_relative_to(root) for x in protected),'Current baseline/pair overlaps deleted root')
    expected_links={tuple(map(int,key.split(':'))):value for key,value in supp['baseline_link_counts'].items()}
    for row in supp['additional_protected_artifacts']:
        identity=tuple(row['file_identity'])
        require(identity not in expected_links or expected_links[identity]==row['links'],'Same-ID protection has inconsistent nlinks')
        expected_links[identity]=row['links']
    counts=Counter(tuple(x['file_identity']) for x in plan['files'])
    current=scope.read(plan['retained_final_report']['path'])
    request=scope.read(plan['retained_request']['path'])
    current_sources=[*current['current_source_inputs'],*menu.frozen_rows(current).values()]
    deleted=[];removed=[];archives=[];reused=[]

    def verify_protected(after=False):
        scope.DIGESTS.clear();unique=set()
        for row in protected:
            actual=scope.verify(row);identity=tuple(actual['file_identity']);unique.add(identity)
            require(actual['links']==expected_links[identity]-(counts[identity] if after else 0),'Protected alias count changed unexpectedly: '+row['path'])
        for row in current_sources:scope.verify(row)
        for row in plan['external_hardlink_keepers']:
            actual=scope.verify(row);identity=tuple(actual['file_identity'])
            require(actual['links']==row['links']-(counts[identity] if after else 0),'Outside shared donor alias count differs')
        for row in (plan['retained_final_report'],plan['retained_final_attestation'],plan['retained_final_audit'],plan['retained_prepared_verification'],plan['retained_request'],plan['retained_profile']):scope.verify(row)
        for row in plan['exact_historical_metadata_gzip_reused']:
            backup=scope.verify(row['existing_gzip']);raw=gzip.decompress(Path(backup['path']).read_bytes())
            require(len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256'],'Unique historical gzip roundtrip differs')
        return dict(protected_paths=len(protected),protected_unique_ids=len(unique),current_source_and_frozen_paths=len(current_sources),outside_donors=len(plan['external_hardlink_keepers']),
            bytes_id_mtime_attributes_unchanged=True,expected_old_alias_nlink_decrement_verified=after)

    before=verify_protected()
    actual_files,actual_dirs=scope.tree(root)
    require({x['path'] for x in actual_files}=={x['path'] for x in plan['files']} and {x['path'] for x in actual_dirs}=={x['path'] for x in plan['directories']},'Actual old root has missing/extra entries')
    rows={x['path']:x for x in actual_files};directories={x['path']:x for x in actual_dirs}
    for row in plan['files']:
        require(menu.key(row['path']) not in protected_keys,'Candidate overlaps a protected path')
        actual=rows[row['path']]
        require(all(actual[k]==row[k] for k in ('bytes','sha256','file_identity','mtime_ns','file_attributes','links','allocated_bytes')),'Candidate state differs from reviewed plan: '+row['path'])
    for row in plan['directories']:
        actual=directories[row['path']]
        require(all(actual[k]==row[k] for k in ('file_identity','mtime_ns','file_attributes','links')),'Old directory changed since plan')
    for row in plan['text_archive_candidates']:
        source=Path(row['source']['path']);target=Path(row['target']['path'])
        require(source.is_relative_to(scope.PROJECT/'evidence') and not source.is_relative_to(root) and menu.key(source) not in protected_keys,'Raw archive source outside reviewed evidence scope')
        require(target.parent==DIRECTORY/'archived_text' and not os.path.lexists(target),'Archive target escaped or already exists')
        actual=scope.verify(row['source']);require(actual['links']==1,'Raw archive source gained a hardlink')
    for row in scope.read(Path(plan['prior_exact_six_cleanup']['path']).with_name('cleanup_plan.json'))['candidates']:
        require(not os.path.lexists(row['path']),'Previously retired exact six intermediates reappeared')
    require(request['run_id']==scope.RUN_ID and request['resume_from'] is None,'Retained pair is not new-game-only')
    require(not any(scope.OLD_ID in text for text in scope.strings(request)),'New request depends on superseded build')
    write_new(DIRECTORY/'apply_started.json',dict(schema='zerosis.menu_runtime_ui.exact59c_apply_started.v1',plan_sha256=PLAN_SHA,supplement_sha256=SUPPLEMENT_SHA,
        exact_root=str(root),files=711,directories=85,text_archives=4,protected=before,readonly_attributes_will_not_change=True,native_execution=False))
    try:
        archive_directory=DIRECTORY/'archived_text';require(not archive_directory.exists(),'Archive directory already exists');archive_directory.mkdir()
        for row in plan['text_archive_candidates']:
            source=Path(row['source']['path']);target=Path(row['target']['path']);scope.verify(row['source'])
            raw=source.read_bytes();packed=gzip.compress(raw,mtime=0)
            require(len(packed)==row['target']['bytes'] and hashlib.sha256(packed).hexdigest()==row['target']['sha256'],'Exact planned gzip bytes differ')
            with target.open('xb') as stream:stream.write(packed)
            actual=scope.snapshot(target,allocated=True);restored=gzip.decompress(target.read_bytes())
            require(restored==raw and hashlib.sha256(restored).hexdigest()==row['source']['sha256'],'Archive readback/roundtrip differs')
            scope.verify(row['source']);unlink(source);require(not os.path.lexists(source),'Raw archive source still exists')
            archives.append(dict(role=row['role'],original=row['source'],archive=actual,restored_sha256=hashlib.sha256(restored).hexdigest(),raw_removed=True))
            write_new(DIRECTORY/('archive_completed_%02d.json'%len(archives)),archives[-1])
        for row in plan['exact_historical_metadata_gzip_reused']:
            scope.verify(row['existing_gzip']);reused.append(row)
        deleted_counts=Counter()
        for row in plan['files']:
            path=Path(row['path']);require(path.is_relative_to(root) and path.resolve(strict=True)==path,'Delete target escaped exact old root')
            actual=scope.verify(row);identity=tuple(row['file_identity'])
            require(actual['links']==row['links']-deleted_counts[identity],'Candidate nlinks changed after preparation')
            unlink(path);require(not os.path.lexists(path),'Old file path still exists');deleted.append(row['path']);deleted_counts[identity]+=1
        for row in sorted(plan['directories'],key=lambda x:len(Path(x['path']).parts),reverse=True):
            path=Path(row['path']);actual=os.stat(path,follow_symlinks=False)
            require(not actual.st_file_attributes&0x400 and [actual.st_dev,actual.st_ino]==row['file_identity'] and actual.st_file_attributes==row['file_attributes'],'Old directory identity/attributes changed')
            require(not any(path.iterdir()),'Old directory is not empty');path.rmdir();removed.append(str(path))
        require(not os.path.lexists(root) and len(deleted)==711 and len(removed)==85,'Exact retired root remains or counts differ')
        after=verify_protected(True)
        for row in archives:
            scope.verify(row['archive']);require(hashlib.sha256(gzip.decompress(Path(row['archive']['path']).read_bytes())).hexdigest()==row['restored_sha256'],'Retained compressed proof changed')
        raw_allocation=sum(x['original']['allocated_bytes'] for x in archives);gzip_allocation=sum(x['archive']['allocated_bytes'] for x in archives)
        result=dict(schema='zerosis.menu_runtime_ui.superseded_root_cleanup_result.v1',status='PASS_EXACT_SUPERSEDED_59C_ROOT_AND_METADATA_RETIREMENT',build_id=scope.OLD_ID,
            plan=scope.snapshot(PLAN),protection_supplement=scope.snapshot(SUPPLEMENT),exact_root=str(root),files_deleted=len(deleted),directories_removed=len(removed),all_candidates_absent=True,
            root_logical_bytes_removed=plan['logical_bytes'],root_unique_allocated_bytes_released=plan['estimated_root_allocated_bytes_released'],
            root_shared_outside_allocation_preserved=plan['shared_allocation_preserved_outside_root'],outside_donors_verified=644,
            protected_before=before,protected_after=after,all_5024_protected_bytes_id_mtime_attributes_preserved=True,protected_alias_links_only_exact_old_root_decrements=True,
            new_Host613f_frozen_source686_and_prepared_f127_sidecar114_preserved=True,old_six_remain_absent=True,
            metadata_archives=archives,existing_unique_historical_gzip_reused=reused,
            raw_metadata_bytes_removed=sum(x['original']['bytes'] for x in archives),raw_metadata_allocated_bytes_released=raw_allocation,
            gzip_bytes_retained=sum(x['archive']['bytes'] for x in archives),gzip_allocated_bytes_retained=gzip_allocation,
            net_allocated_bytes_released_before_small_receipts=plan['estimated_root_allocated_bytes_released']+raw_allocation-gzip_allocation,
            inode_allocation_method='FILE_STANDARD_INFO_DEDUP_REAL_OS_STAT_ID_LAST_CANDIDATE_LINK_REMOVED',volume_free_space_not_used=True,
            readonly_attributes_changed=False,no_retry_or_partial_replay=True,current_reports_profiles_or_protected_data_deleted=False,
            Host_SDK_CLR_HWND_GPU_game_executed=False,default_or_registered_Host_promoted=False,retail_mods_settings_saves_changed=False)
        output=DIRECTORY/'whole_root_cleanup_result.json';write_new(output,result)
        print(json.dumps(dict(status=result['status'],files_deleted=711,directories_removed=85,root_allocated_bytes_released=result['root_unique_allocated_bytes_released'],
            metadata_archives=len(archives),raw_metadata_allocated_bytes_released=raw_allocation,gzip_allocated_bytes_retained=gzip_allocation,
            net_allocated_bytes_released_before_small_receipts=result['net_allocated_bytes_released_before_small_receipts'],protected=5024,result=scope.snapshot(output))))
    except BaseException as error:
        write_new(DIRECTORY/'apply_partial_failure.json',dict(plan_sha256=PLAN_SHA,supplement_sha256=SUPPLEMENT_SHA,deleted=deleted,removed_directories=removed,
            text_archives=archives,existing_gzip_reused=reused,error_type=type(error).__name__,error=str(error),fresh_remaining_plan_required=True,native_execution=False))
        raise

if __name__=='__main__':main()
