"""Apply only the exact root-approved f492 failed-freeze deletion plan once."""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime,timezone
import gzip
import importlib
import json
import os
from pathlib import Path
import stat
import sys

sys.dont_write_bytecode=True
STAGE=Path(__file__).absolute().parent
sys.path[0:0]=[str(STAGE),str(STAGE.parents[3]/'tools')]
import plan_failed_freeze as planner

PLAN_SHA='f49280c3a6585891eacee77b892b46062035d6299f0cd06988ec965d65f4fd27'
COMPARE=('bytes','sha256','file_identity','mtime_ns','file_attributes')

def require(value,message):
    if not value:raise RuntimeError(message)
def write_new(path,value):
    with path.open('x',encoding='utf8') as stream:json.dump(value,stream,indent=2);stream.write('\n')
def read(path):return json.loads(Path(path).read_text('utf8'))
def protected_check(rows):
    cache={};actual=[];link_changes=0
    for row in rows:
        now=planner.record(row['path'],cache)
        require(all(now[name]==row[name] for name in COMPARE),'Protected input changed: '+row['path'])
        link_changes+=now['links']!=row['links'];actual.append(now)
    return actual,link_changes

def main():
    cli=argparse.ArgumentParser();cli.add_argument('--apply',action='store_true');cli.add_argument('--plan-sha256',required=True);args=cli.parse_args()
    require(os.name=='nt' and args.apply and args.plan_sha256==PLAN_SHA,'Exact root-approved apply invocation required')
    require(not any((STAGE/name).exists() for name in ('started.json','result.json','failure.json')),
            'Inspect the existing single attempt; automatic retry is forbidden')
    deleted=[];removed_directories=[];started=False
    try:
        plan_path=STAGE/'plan.json';require(planner.digest(plan_path)==PLAN_SHA,'Approved plan SHA differs')
        plan=read(plan_path)
        require(plan['status']=='PLAN_ONLY_REQUIRES_ROOT_DELETE_AUTHORIZATION' and plan['files_deleted']==0 and
            len(plan['files'])==713 and len(plan['directories'])==97,'Approved target count/status differs')
        require({key:Path(value['path']) for key,value in plan['roots'].items()}==planner.ROOTS,'Approved roots changed')
        require(plan['successful_replacement']['build_id']==planner.SUCCESS and
            plan['successful_replacement']['report']['sha256']==planner.SUCCESS_REPORT_SHA and
            plan['successful_replacement']['executable']['sha256']==planner.SUCCESS_EXE_SHA and
            plan['successful_replacement']['independent_attestation']['sha256']==planner.SUCCESS_ATTEST_SHA,
            'Replacement pins differ from the root authorization')
        for name in ('report','executable','independent_attestation'):
            row=plan['successful_replacement'][name];actual=planner.record(row['path'],{})
            require(all(actual[key]==row[key] for key in COMPARE),'Replacement artifact differs: '+name)
        expected_snapshot=plan['protected_snapshot'];actual=planner.record(expected_snapshot['path'],{})
        require(all(actual[key]==expected_snapshot[key] for key in COMPARE),'Protected snapshot differs')
        before_snapshot=json.loads(gzip.decompress(Path(expected_snapshot['path']).read_bytes()))
        base_rows=before_snapshot['protected_artifacts'];require(len(base_rows)==6430,'Approved protection count differs')
        base_current,base_link_changes=protected_check(base_rows)
        union={planner.key(row['path']):row for row in base_current}
        success=read(plan['successful_replacement']['report']['path'])
        # Extra source checks strengthen preservation; they never add a target.
        for expected in success['current_source_inputs']:
            now=planner.record(expected['path'],{})
            require(all(now[key]==expected[key] for key in COMPARE),'Current compiled source differs: '+expected['path'])
            union[planner.key(now['path'])]=now
        assets=read(planner.PHASE/'assets/result.json')
        for name in ('package','manifest'):
            expected=assets[name];now=planner.record(expected['path'],{})
            require(all(now[key]==expected[key] for key in COMPARE),'Original terrain package input differs: '+name)
            union[planner.key(now['path'])]=now
        protected=list(union.values());protected_paths=set(union)
        cache={};seen_files=set();seen_dirs=set()
        for root in planner.ROOTS.values():
            require(root.resolve()==root and root.is_relative_to(planner.PROJECT),'Target root escaped its original boundary')
            files,dirs=planner.tree(root,cache)
            seen_files.update(planner.key(row['path']) for row in files);seen_dirs.update(planner.key(row['path']) for row in dirs)
        require(seen_files=={planner.key(row['path']) for row in plan['files']} and
                seen_dirs=={planner.key(row['path']) for row in plan['directories']},'Unplanned entry appeared or planned entry vanished')
        require(not seen_files&protected_paths,'A protected path entered the deletion set')
        group=Counter(tuple(row['file_identity']) for row in plan['files']);target_rows=[]
        for row in plan['files']:
            now=planner.record(row['path'],{})
            require(all(now[key]==row[key] for key in (*COMPARE,'links')),'Target metadata/link count changed: '+row['path'])
            require(any(Path(now['path']).is_relative_to(root) for root in planner.ROOTS.values()),'A target escaped the exact two roots')
            target_rows.append(now)
        fully_owned={tuple(row['file_identity']):row['allocated_bytes'] for row in target_rows
            if row['links']==group[tuple(row['file_identity'])]}
        released=sum(fully_owned.values());require(released==684680,'Approved reclaim estimate changed')
        helper=plan['deletion_method']['helper'];actual=planner.record(helper['path'],{})
        require(all(actual[key]==helper[key] for key in COMPARE),'Reviewed readonly-preserving helper changed')
        sys.path.insert(0,str(planner.PROJECT/'tools'))
        module=importlib.import_module('civ5_ui_assets')
        require(Path(module.__file__).absolute()==Path(helper['path']),'Readonly helper import resolved elsewhere')
        unlink=getattr(module,plan['deletion_method']['function'])
        require(callable(unlink),'Reviewed readonly unlink helper is unavailable')
        before_path=STAGE/'apply_protection_before.json.gz'
        with before_path.open('xb') as stream:stream.write(gzip.compress((json.dumps(dict(protected_artifacts=protected,
            approved_base_paths=6430,total_paths=len(protected),base_link_count_changes_since_plan=base_link_changes),indent=2)+'\n').encode(),mtime=0))
        write_new(STAGE/'started.json',dict(status='ROOT_AUTHORIZED_EXACT_FAILED_FREEZE_DELETE_STARTED',
            utc=datetime.now(timezone.utc).isoformat(),root_authorization='Explicit root-agent approval of f492 plan in this task',
            plan=planner.record(plan_path,{}),protected_snapshot=planner.record(before_path,{}),
            readonly_attribute_changes_allowed=False,native_host_sdk_gpu_game_execution_allowed=False))
        started=True;already=Counter();journal=STAGE/'progress.jsonl'
        with journal.open('x',encoding='utf8') as stream:
            def event(value):stream.write(json.dumps(value,separators=(',',':'))+'\n');stream.flush()
            for index,row in enumerate(plan['files']):
                now=planner.record(row['path'],{});identity=tuple(row['file_identity'])
                require(all(now[key]==row[key] for key in COMPARE) and now['links']==row['links']-already[identity],
                    'Target changed at disposition boundary: '+row['path'])
                event(dict(event='removing_file',index=index));unlink(Path(row['path']))
                require(not os.path.lexists(planner.native(row['path'])),'Removed directory entry still exists')
                already[identity]+=1;deleted.append(index);event(dict(event='removed_file',index=index))
            for index,row in enumerate(plan['directories']):
                path=Path(row['path']);info=os.stat(planner.native(path),follow_symlinks=False)
                require(stat.S_ISDIR(info.st_mode) and [info.st_dev,info.st_ino]==row['file_identity'] and
                    info.st_file_attributes==row['file_attributes'] and not info.st_file_attributes&0x400,'Directory identity/attributes changed')
                require(not list(os.scandir(planner.native(path))),'Directory has an unplanned surviving entry')
                event(dict(event='removing_directory',index=index));os.rmdir(planner.native(path))
                removed_directories.append(index);event(dict(event='removed_directory',index=index))
        require(all(not os.path.lexists(planner.native(root)) for root in planner.ROOTS.values()),'A failed root still exists')
        _after,link_changes=protected_check(protected)
        for name in ('report','executable','independent_attestation'):
            expected=plan['successful_replacement'][name];current=planner.record(expected['path'],{})
            require(all(current[key]==expected[key] for key in COMPARE),'Replacement changed after deletion: '+name)
        require(planner.record(helper['path'],{})['sha256']==helper['sha256'],'Readonly helper changed during cleanup')
        journal_ref=planner.record(journal,{})
        compressed=STAGE/'progress.jsonl.gz';raw=journal.read_bytes();compressed.write_bytes(gzip.compress(raw,mtime=0))
        require(gzip.decompress(compressed.read_bytes())==raw,'Progress journal compression roundtrip differs')
        require(journal_ref['links']==1 and not journal_ref['file_attributes']&0x401,'Generated progress journal is not singly owned')
        require(planner.record(journal,{})==journal_ref,'Generated progress journal changed')
        journal.unlink()
        value=dict(status='PASS_EXACT_FAILED_FREEZE_ROOTS_REMOVED_AND_CURRENT_INPUTS_PRESERVED',
            utc=datetime.now(timezone.utc).isoformat(),plan=planner.record(plan_path,{}),
            roots_removed=[str(root) for root in planner.ROOTS.values()],deleted_files=len(deleted),deleted_directories=len(removed_directories),
            deleted_file_indices=deleted,deleted_directory_indices=removed_directories,
            path_logical_bytes_removed=plan['allocation']['path_logical_bytes'],
            unique_allocated_bytes_in_deleted_names=plan['allocation']['unique_allocated_bytes'],
            unique_allocated_bytes_released=released,
            externally_shared_file_ids_preserved=plan['allocation']['externally_shared_file_ids'],
            approved_protected_paths_verified_before_after=6430,total_protected_paths_with_extra_current_sources=len(protected),
            protected_content_id_mtime_or_attribute_differences=0,protected_link_count_changes=link_changes,
            before_protection=planner.record(before_path,{}),progress_journal=planner.record(compressed,{}),
            generated_uncompressed_journal_retired=journal_ref,
            readonly_attributes_changed=False,failed_attempt_diagnostics_preserved=plan['preserve_failed_attempt_diagnostics'],
            successful_replacement=plan['successful_replacement'],native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False)
        write_new(STAGE/'result.json',value)
        print(json.dumps({key:value[key] for key in ('status','deleted_files','deleted_directories','path_logical_bytes_removed',
            'unique_allocated_bytes_released','approved_protected_paths_verified_before_after','total_protected_paths_with_extra_current_sources',
            'protected_content_id_mtime_or_attribute_differences')}))
    except BaseException as error:
        failure=dict(status='FAILED_EXACT_CLEANUP_NO_AUTOMATIC_RETRY',error=type(error).__name__+': '+str(error),
            started=started,deleted_file_indices=deleted,deleted_directory_indices=removed_directories,
            native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False)
        if not(STAGE/'failure.json').exists():write_new(STAGE/'failure.json',failure)
        raise

if __name__=='__main__':main()
