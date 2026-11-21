"""Seal exact superseded Host files and protected current pair; never deletes."""
from __future__ import annotations
from collections import defaultdict
import gzip
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

PROJECT=Path(__file__).absolute().parents[4]
STAGE=PROJECT/'evidence/game_menu/menu_runtime_ui_followup'
OLD_ID='20261103T134638Z_59c8f213b4f0'
FINAL_ID='20261103T135554Z_613f0604b928'
RUN_ID='20261103T140325Z_f127e4edebe9'
OLD_ROOT=PROJECT/'Build/UiWindowHost'/OLD_ID
FINAL_ROOT=PROJECT/'Build/UiWindowHost'/FINAL_ID
RUNTIME_ROOT=PROJECT/'Build/InteractiveGameRuntime'/RUN_ID
OUTPUT=STAGE/'retention'/OLD_ID
sys.dont_write_bytecode=True
sys.path.insert(0,str(PROJECT/'tools'))
import retained_menu_suite_host_input as menu
from menu_suite_storage import storage

DIGESTS={}
def require(value,reason):
    if not value:raise RuntimeError(reason)
def read(path):return json.loads(Path(path).read_text('utf8'))
def ordinary(path):
    path=Path(path).absolute();value=storage.ordinary(path)
    require(path.resolve(strict=True)==path,'Noncanonical ordinary file: '+str(path))
    return value
def snapshot(path,*,allocated=False):
    path=Path(path).absolute();value=ordinary(path);key=(value.st_dev,value.st_ino,value.st_size,value.st_mtime_ns)
    if key not in DIGESTS:DIGESTS[key]=storage.digest(path)
    result=dict(path=str(path),sha256=DIGESTS[key],**storage.metadata(value))
    if allocated:result['allocated_bytes']=storage.allocated(path)
    after=ordinary(path)
    require(storage.metadata(value)==storage.metadata(after),'File changed while collecting metadata: '+str(path))
    return result

def verify(expected):
    current=snapshot(expected['path'])
    fields=['bytes','sha256']+[x for x in ('file_identity','mtime_ns','file_attributes') if x in expected]
    require(all(current[x]==expected[x] for x in fields),'Pinned artifact changed: '+str(expected['path']))
    return current

def strings(value):
    if isinstance(value,str):yield value
    elif isinstance(value,dict):
        for item in value.values():yield from strings(item)
    elif isinstance(value,list):
        for item in value:yield from strings(item)

def excludes(value,paths):
    texts=[x.replace('\\','/').casefold() for x in strings(value)]
    for path in paths:
        prefix=str(path).replace('\\','/').casefold()
        require(not any(prefix in text for text in texts),'Current retained input references superseded path: '+str(path))

def tree(root):
    root=Path(root).absolute();require(root.resolve(strict=True)==root,'Tree root is not canonical')
    files=[];directories=[];pending=[root]
    while pending:
        path=pending.pop();value=os.stat(path,follow_symlinks=False)
        require(value.st_dev and value.st_ino and not value.st_file_attributes&stat.FILE_ATTRIBUTE_REPARSE_POINT,'Reparse/invalid tree directory')
        require(stat.S_ISDIR(value.st_mode) and path.resolve(strict=True)==path,'Tree entry is not an ordinary canonical directory')
        directories.append(dict(path=str(path),**storage.metadata(value)))
        for entry in sorted(os.scandir(path),key=lambda x:x.name):
            child=Path(entry.path);value=os.stat(child,follow_symlinks=False)
            require(not value.st_file_attributes&stat.FILE_ATTRIBUTE_REPARSE_POINT,'Reparse tree leaf rejected')
            require(child.is_relative_to(root),'Tree entry escaped exact root')
            if stat.S_ISDIR(value.st_mode):pending.append(child)
            else:
                require(stat.S_ISREG(value.st_mode),'Nonordinary tree leaf rejected');files.append(snapshot(child,allocated=True))
    return sorted(files,key=lambda x:x['path']),sorted(directories,key=lambda x:x['path'])

def main():
    require(OLD_ROOT.parent==PROJECT/'Build/UiWindowHost' and OLD_ROOT.resolve(strict=True)==OLD_ROOT,'Superseded root scope changed')
    require(not OUTPUT.exists(),'Inspect prior exact plan instead of regenerating it')
    old_report=PROJECT/'evidence/ui_window_host'/OLD_ID/'build_result.json'
    final_report=PROJECT/'evidence/ui_window_host'/FINAL_ID/'build_result.json'
    require(storage.digest(old_report)=='a6f219006b72559960260b1fc47672685f9e2f6bab3d450cf75ab00273bb2a54','Old report differs')
    require(storage.digest(final_report)=='1aedae12695139d7dc7a8e105fcc730b8b05a1bbfa3d12f7610fe51e7759fbbf','Final report differs')
    old,current=read(old_report),read(final_report)
    require(old['build_id']==OLD_ID and current['build_id']==FINAL_ID,'Build identity differs')
    require(all(old[name] is False and current[name] is False for name in menu.OFFLINE_FIELDS),'Host build escaped offline scope')
    baseline=STAGE/'protection_before.json';protected=read(baseline)['protected_artifacts']
    require(len(protected)==4015,'Authoritative turn protection scope changed')
    protection_snapshot=[]
    for row in protected:
        require(not Path(row['path']).is_relative_to(OLD_ROOT),'Superseded root overlaps authoritative protection')
        protection_snapshot.append(verify(row))
    prepared_path=STAGE/'prepared_runtime_verification.json'
    require(storage.digest(prepared_path)=='9dc735328d8744f56b6dd094a10574d9d004656a3412b2a2f07cbc6383a69b2c','Prepared pair verification differs')
    prepared=read(prepared_path)
    require(prepared['run_id']==RUN_ID and prepared['host_build_id']==FINAL_ID and prepared['native_attempts']==0 and
        prepared['native_host_sdk_clr_hwnd_gpu_game_executed'] is False and prepared['no_sessions'] is True,'Prepared runtime/native scope changed')
    request_path=Path(prepared['request']['path']);request=read(request_path);verify(prepared['request'])
    require(request['run_id']==RUN_ID and request['resume_from'] is None,'Runtime request is not the isolated new-game pair')
    profile_ref=request['explicit_host_input_profile'];verify(profile_ref);profile=read(profile_ref['path'])
    final_att_path=STAGE/'pair_preparation'/FINAL_ID/'independent_attestation.json'
    final_audit_path=STAGE/'pair_preparation'/FINAL_ID/'final_audit.json'
    typed_path=STAGE/'pair_preparation'/FINAL_ID/'typed_retirement.json'
    final_att,final_audit=read(final_att_path),read(final_audit_path)
    require(final_att['status']=='PASS_INDEPENDENT_CURRENT_MENU_SUITE_HOST_BYTES_AND_INPUTS' and
        final_att['build_result']['sha256']==storage.digest(final_report),'Final independent attestation differs')
    require(final_audit['status']=='PASS_CURRENT_MENU_SUITE_HOST_ATTESTED_AND_INTERMEDIATES_RETIRED_NOT_EXECUTED','Final static audit not passed')
    new_run_path=Path(current['started']['path']).with_name('run.json');new_run=read(new_run_path)
    require(new_run['status']=='PASS_CURRENT_MENU_SUITE_HOST_OFFLINE_BUILD_ONLY' and len(new_run['commands'])==12 and
        new_run['host_sdk_clr_window_gpu_or_dll_executed'] is False,'Final twelve-phase build evidence differs')
    require(current['baseline_build']['sha256']=='cd167cb92abb1dc02b53893c87123c741f8a27bbf11434dbaf2f8d20cb9e3404','Final host did not reuse preserved bc34 parent')
    documents=[current,new_run,read(current['profile']['path']),read(current['menu_suite_component']['path']),final_att,final_audit,
        read(typed_path),request,profile,prepared]
    for document in documents:excludes(document,[OLD_ROOT])
    for row in [*current['current_source_inputs'],*menu.frozen_rows(current).values()]:
        require(not Path(row['path']).is_relative_to(OLD_ROOT),'Final source closure depends on superseded root');verify(row)
    image=verify(current['executable']);old_image=verify(old['executable'])
    require(image['sha256']==old_image['sha256']=='61a2f0d040b68b5d11b0fe92c7d659a6aa2d3967fa33e2d86aa3670a2bd16925','Actual old/new host bytes differ')
    require(image['file_identity']!=old_image['file_identity'],'Old image is an alias of current retained host')
    require(not (OLD_ROOT/'final/UIFrontEnd').exists(),'Superseded host unexpectedly has a required sidecar')
    old_cleanup=STAGE/'pair_preparation'/OLD_ID/'cleanup_result.json';cleanup=read(old_cleanup)
    old_six=read(old_cleanup.with_name('cleanup_plan.json'))['candidates']
    require(cleanup['files_deleted']==6 and cleanup['all_candidates_absent'] is True and all(not os.path.lexists(x['path']) for x in old_six),'Previously retired six intermediates reappeared')
    requests=[]
    for path in sorted((PROJECT/'evidence/interactive_game').glob('*/request.json')):
        value=read(path);excludes(value,[OLD_ROOT]);require(not any(OLD_ID in text for text in strings(value)),'A runtime request selects superseded Host')
        requests.append(snapshot(path))
    fresh_files,fresh_dirs=tree(FINAL_ROOT);runtime_files,runtime_dirs=tree(RUNTIME_ROOT)
    require(len(runtime_files)==149,'Current prepared runtime file count changed')
    require(not any(Path(x['path']).suffix.lower() in ('.zssave','.civ5save') or Path(x['path']).name=='session.json' for x in runtime_files),'New prepared runtime contains a save/session')
    frozen_evidence_files,_=tree(PROJECT/'evidence/interactive_game'/RUN_ID)
    additional={menu.key(row['path']):row for row in [*fresh_files,*runtime_files,*frozen_evidence_files]}
    for path in (final_report,final_att_path,final_audit_path,typed_path,new_run_path,Path(profile_ref['path']),request_path,prepared_path,Path(current['profile']['path']),Path(current['menu_suite_component']['path'])):
        additional[menu.key(path)]=snapshot(path)
    authoritative_paths={menu.key(x['path']) for x in protected}
    require(not any(Path(x['path']).is_relative_to(OLD_ROOT) for x in additional.values()),'New protected pair overlaps old root')
    frozen=menu.frozen_rows(old);known={menu.key(row['path']):row for value in old.values() for row in menu.walk(value)}
    new_frozen={str(Path(x['path']).relative_to(FINAL_ROOT)).casefold():x for x in menu.frozen_rows(current).values()}
    before_flags_path=STAGE/'frontend/manifest_execution_flags/attestation.json';before_flags=read(before_flags_path)
    reusable_backups={x['original']['sha256']:x['backup'] for x in before_flags['backups']}
    files,directories=tree(OLD_ROOT);keepers={};groups=defaultdict(list);historical_metadata=[]
    exports={menu.key(OLD_ROOT/'final/ZeroSisHost_x64.exp'),menu.key(OLD_ROOT/'final/ZeroSisHost_x64.lib')}
    link_log=Path(old['link_log']['path']).read_text('mbcs')
    require(all(name in link_log for name in ('ZeroSisHost_x64.lib','ZeroSisHost_x64.exp')),'Old export outputs absent from actual linker log')
    for row in files:
        path=Path(row['path']);key=menu.key(path)
        require(key not in authoritative_paths and key not in additional,'Retirement candidate overlaps protected file')
        require(path.suffix.lower() not in ('.zssave','.civ5save') and path.name not in ('request.json','session.json','driver_result.json'),'Superseded root contains runtime/save data')
        if key in frozen:
            expected=frozen[key];require((row['bytes'],row['sha256'])==(expected['bytes'],expected['sha256']),'Old frozen bytes changed')
            if expected['materialization']=='attested_snapshot_hardlink':
                donor=Path(expected['reused_from_path']);require(not donor.is_relative_to(OLD_ROOT),'Old frozen alias donor inside retired root')
                kept=snapshot(donor);require((kept['bytes'],kept['sha256'],kept['file_identity'])==(row['bytes'],row['sha256'],row['file_identity']),'Outside alias donor differs')
                keepers[menu.key(donor)]=kept;row['role']='SUPERSEDED_FROZEN_ALIAS_OUTSIDE_DONOR_PRESERVED'
            else:
                require(expected['materialization'] in ('owned_changed_source_copy','owned_added_source_copy'),'Unknown private frozen source role')
                rel=str(path.relative_to(OLD_ROOT)).casefold();replacement=new_frozen.get(rel)
                if replacement and (replacement['bytes'],replacement['sha256'])==(row['bytes'],row['sha256']):
                    row['role']='SUPERSEDED_PRIVATE_COPY_IDENTICAL_CURRENT_FROZEN_INPUT';row['replacement']=dict(path=replacement['path'],sha256=replacement['sha256'])
                else:
                    require(row['sha256'] in reusable_backups,'Unique changed source/metadata has no retained exact gzip backup')
                    backup=verify(reusable_backups[row['sha256']]);raw=gzip.decompress(Path(backup['path']).read_bytes())
                    require(len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256'],'Existing gzip does not restore exact unique historical input')
                    row['role']='SUPERSEDED_UNIQUE_METADATA_EXISTING_EXACT_GZIP_PRESERVED';row['recovery_gzip']=backup
                    historical_metadata.append(dict(original=row['path'],bytes=row['bytes'],sha256=row['sha256'],existing_gzip=backup,verified_roundtrip=True))
        elif key==menu.key(old['executable']['path']):row['role']='SUPERSEDED_UNEXECUTED_HOST_IMAGE_IDENTICAL_CURRENT_IMAGE'
        elif key in exports:
            raw=path.read_bytes()
            if path.suffix=='.exp':require(len(raw)>20 and int.from_bytes(raw[:2],'little')==0x8664,'Old derived export is not x64 COFF')
            else:require(raw.startswith(b'!<arch>\n') and b'ZeroSisHost_x64.exe' in raw,'Old derived export library differs')
            row['role']='EXACT_LINKER_DECLARED_DERIVED_EXPORT_OUTPUT'
        elif key in known:row['role']='HASH_ATTESTED_SUPERSEDED_BUILD_RECIPE_OR_OUTPUT'
        else:raise RuntimeError('Unknown whole-root candidate role: '+str(path))
        if key in known:require((row['bytes'],row['sha256'])==(known[key]['bytes'],known[key]['sha256']),'Known build output bytes changed')
        groups[tuple(row['file_identity'])].append(row)
    released=shared=0;allocation_groups=[];keeper_ids={tuple(x['file_identity']) for x in keepers.values()}
    for identity,aliases in sorted(groups.items()):
        links={x['links'] for x in aliases};allocations={x['allocated_bytes'] for x in aliases}
        require(len(links)==len(allocations)==1 and aliases[0]['links']>=len(aliases),'Inconsistent same-ID alias metadata')
        outside=aliases[0]['links']-len(aliases);allocation=aliases[0]['allocated_bytes']
        if outside:
            require(identity in keeper_ids,'Shared allocation lacks exact outside retained donor');shared+=allocation
        else:released+=allocation
        allocation_groups.append(dict(file_identity=list(identity),candidate_aliases=len(aliases),observed_total_links=aliases[0]['links'],outside_links=outside,
            allocated_bytes=allocation,will_release_allocation=not outside))
    old_run_path=Path(old['started']['path']).with_name('run.json');old_run=read(old_run_path)
    archive_paths=[('old_build_report',old_report),('old_build_run',old_run_path),('old_preflight_plan',Path(old_run['reviewed_preflight']['path'])),('old_source_manifest',Path(old['menu_suite_component']['path']))]
    archives=[]
    for role,path in archive_paths:
        require(path.is_relative_to(PROJECT/'evidence') and not path.is_relative_to(OLD_ROOT),'Archive source outside allowed evidence scope')
        row=snapshot(path,allocated=True);require(row['links']==1 and menu.key(path) not in authoritative_paths and menu.key(path) not in additional,'Archive source is protected/shared')
        for document in documents:excludes(document,[path])
        raw=path.read_bytes();packed=gzip.compress(raw,mtime=0);require(gzip.decompress(packed)==raw,'Planned archive roundtrip failed')
        archives.append(dict(role=role,source=row,target=dict(path=str(OUTPUT/'archived_text'/(role+'.json.gz')),bytes=len(packed),sha256=hashlib.sha256(packed).hexdigest()),
            algorithm='PYTHON_GZIP_COMPRESS_MTIME_0',will_remove_only_source_after_exact_roundtrip=True))
    require(len(historical_metadata)==2,'Unexpected historical unique input count')
    # A complete new-pair supplement is independent from the older 4015-row
    # turn baseline and records fresh nlinks after materialization has finished.
    supplement=dict(schema='zerosis.menu_runtime_ui.retirement_protection.v1',status='PLAN_ONLY_CURRENT_PAIR_PROTECTED',
        authoritative_baseline=snapshot(baseline),authoritative_baseline_paths_verified=4015,
        authoritative_baseline_unique_ids_verified=len({tuple(x['file_identity']) for x in protection_snapshot}),
        baseline_content_identity_mtime_attributes_changed=False,baseline_link_counts={':'.join(map(str,x['file_identity'])):x['links'] for x in protection_snapshot},
        additional_protected_artifacts=list(additional.values()),additional_protected_paths=len(additional),
        new_final_report=snapshot(final_report),new_prepared_request=snapshot(request_path),new_prepared_profile=verify(profile_ref),
        new_prepared_verification=snapshot(prepared_path),outside_donors=list(keepers.values()),
        exact_backup_reuse_attestation=snapshot(before_flags_path),existing_unique_metadata_backups=historical_metadata,
        protected_paths_overlap=0,native_execution=False,default_or_registration_changed=False)
    plan=dict(schema='zerosis.menu_runtime_ui.superseded_root_retirement_plan.v1',status='SEALED_PLAN_ONLY_NOT_EXECUTED',build_id=OLD_ID,exact_root=str(OLD_ROOT),
        superseded_reason='Same compiled PE; superseded asset-manifest/producer provenance299756 was replaced by valid613f+f127; never materialized/executed',
        old_report=snapshot(old_report),retained_final_report=snapshot(final_report),retained_final_attestation=snapshot(final_att_path),retained_final_audit=snapshot(final_audit_path),
        retained_prepared_verification=snapshot(prepared_path),retained_request=snapshot(request_path),retained_profile=verify(profile_ref),
        required_preserved_bc34='20261101T091435Z_bc34fab66a03',required_preserved_Host4='20261101T074006Z_c2fd2fe9be38',required_preserved424fb='20261101T080450Z_424fb64608b2',
        prior_exact_six_cleanup=snapshot(old_cleanup),prior_six_allocated_bytes_released=cleanup['allocated_bytes_released'],prior_six_still_absent=True,
        files=files,directories=directories,file_count=len(files),directory_count=len(directories),logical_bytes=sum(x['bytes'] for x in files),
        unique_file_ids=len(groups),unique_allocated_bytes=sum(x[0]['allocated_bytes'] for x in groups.values()),
        estimated_root_allocated_bytes_released=released,shared_allocation_preserved_outside_root=shared,allocation_groups=allocation_groups,
        external_hardlink_keepers=list(keepers.values()),exact_historical_metadata_gzip_reused=historical_metadata,text_archive_candidates=archives,
        old_raw_text_allocated_bytes_released_after_archive=sum(x['source']['allocated_bytes'] for x in archives),planned_new_gzip_bytes=sum(x['target']['bytes'] for x in archives),
        new_final_source_inputs_verified=len(current['current_source_inputs']),new_final_frozen_inputs_verified=len(menu.frozen_rows(current)),
        actual_new_host_paths=len(fresh_files),actual_new_runtime_paths=len(runtime_files),runtime_requests_scanned=len(requests),runtime_request_references_to_old_root=0,
        no_old_runtime_sidecar_session_save_or_driver_results=True,new_final_does_not_reuse_old_root=True,
        reparse_entries=0,protected_path_overlap=0,readonly_attribute_changes_allowed=False,hardlink_deletion_method='EXACT_FILE_DISPOSITION_POSIX_IGNORE_READONLY_NO_CHMOD',
        require_revalidate_exact_files_directories_nlinks_and_all_protection_before_apply=True,
        nlink_change_requires_fresh_reviewed_remaining_or_link_supplement=True,delete_executed=False,Host_SDK_CLR_HWND_GPU_game_executed=False,
        helper_inputs=[snapshot(PROJECT/'tools'/name) for name in ('retained_menu_suite_host_input.py','audit_exit_host_storage.py')],
        planner=snapshot(Path(__file__)))
    OUTPUT.mkdir()
    supplement_path=OUTPUT/'protection_supplement.json';supplement_path.write_text(json.dumps(supplement,indent=2)+'\n',encoding='utf8')
    plan['protection_supplement']=snapshot(supplement_path)
    plan_path=OUTPUT/'whole_root_cleanup_plan.json';plan_path.write_text(json.dumps(plan,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(status=plan['status'],files=len(files),directories=len(directories),logical_bytes=plan['logical_bytes'],unique_file_ids=len(groups),
        estimated_root_allocated_bytes_released=released,shared_allocation_preserved=shared,external_donors=len(keepers),
        old_text_raw_bytes=sum(x['source']['bytes'] for x in archives),planned_new_gzip_bytes=plan['planned_new_gzip_bytes'],
        unique_historical_gzip_reused=len(historical_metadata),protected_baseline=4015,protected_additional=len(additional),plan=snapshot(plan_path),supplement=snapshot(supplement_path))))

if __name__=='__main__':main()
