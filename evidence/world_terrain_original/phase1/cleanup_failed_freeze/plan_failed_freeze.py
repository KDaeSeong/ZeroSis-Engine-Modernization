"""Read-only inventory/guard plan for the exact resolved 0278 freeze failure.

This planner cannot delete files. Root must separately approve the sealed plan
after the successful replacement's independent attestation is verified.
"""
from __future__ import annotations
import ast
from datetime import datetime,timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

sys.dont_write_bytecode=True
STAGE=Path(__file__).absolute().parent
PHASE=STAGE.parent
PROJECT=PHASE.parents[2]
sys.path.insert(0,str(PROJECT/'tools'))
import build_exit_confirm_host as common
from menu_suite_storage import storage

FAILED='20261115T024007Z_02780d27a33b'
PARENT='20261115T005626Z_256252d8abe3'
SUCCESS='20261115T024443Z_8470b8d966f8'
SUCCESS_REPORT_SHA='c2b21c5fc5905b59c5bb5e7e0df5e8626f885bbd85b50b604bbaeeb70dc656f3'
SUCCESS_EXE_SHA='9f95a9c3fc87c865e0f07b5ec459b6f391753c23675fbde0e9815c42b2b47e38'
SUCCESS_ATTEST_SHA='b8d3e93a273c1e5dd43e0864288279c1272f6fda2437d27d4a1fcc512998cb37'
ROOTS={'failed_host':PROJECT/'Build/UiWindowHost'/FAILED,
       'failed_host_evidence':PROJECT/'evidence/ui_window_host'/FAILED}

def require(value,message):
    if not value:raise RuntimeError(message)

def key(path):return os.path.normcase(os.path.abspath(path))
def native(path):
    text=os.path.abspath(path)
    return text if text.startswith('\\\\?\\') else '\\\\?\\'+text
def snapshot(info):return info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_file_attributes
def digest(path):
    value=hashlib.sha256()
    with open(native(path),'rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):value.update(chunk)
    return value.hexdigest()

def record(path,cache):
    path=Path(path).absolute();before=os.stat(native(path),follow_symlinks=False)
    require(stat.S_ISREG(before.st_mode) and not before.st_file_attributes&0x400 and before.st_dev and before.st_ino,
            'Not an ordinary non-reparse cleanup/protection file: '+str(path))
    identity=(before.st_dev,before.st_ino)
    cached=cache.get(identity)
    if cached:
        require(snapshot(before)==cached['snapshot'],'A reused file identity changed while planning')
        sha,allocation=cached['sha256'],cached['allocated_bytes']
    else:
        sha=digest(path);allocation=storage.allocated(native(path))
        cache[identity]=dict(snapshot=snapshot(before),sha256=sha,allocated_bytes=allocation)
    after=os.stat(native(path),follow_symlinks=False)
    require(snapshot(before)==snapshot(after),'File changed while planning: '+str(path))
    return dict(path=str(path),bytes=after.st_size,sha256=sha,file_identity=[after.st_dev,after.st_ino],
        mtime_ns=after.st_mtime_ns,file_attributes=after.st_file_attributes,links=after.st_nlink,
        allocated_bytes=allocation)

def tree(root,cache):
    root=Path(root).absolute()
    require(root.resolve()==root and root.is_relative_to(PROJECT) and '.codex' not in root.parts,
            'Root escaped the exact project boundary')
    files=[];directories=[];pending=[root]
    while pending:
        directory=pending.pop();info=os.stat(native(directory),follow_symlinks=False)
        require(stat.S_ISDIR(info.st_mode) and not info.st_file_attributes&0x400,'Reparse/non-directory in planned tree')
        children=list(os.scandir(native(directory)));file_count=dir_count=0
        for item in children:
            path=directory/item.name;data=os.stat(native(path),follow_symlinks=False)
            require(not data.st_file_attributes&0x400,'Reparse entry in planned tree')
            require(path.is_relative_to(root) and '.codex' not in path.relative_to(root).parts,'Entry escaped the approved root')
            if stat.S_ISDIR(data.st_mode):pending.append(path);dir_count+=1
            else:files.append(record(path,cache));file_count+=1
        directories.append(dict(path=str(directory),file_identity=[info.st_dev,info.st_ino],mtime_ns=info.st_mtime_ns,
            file_attributes=info.st_file_attributes,files_at_plan=file_count,subdirectories_at_plan=dir_count,
            empty_at_plan=file_count+dir_count==0,win32_chars=len(str(directory))))
    return files,directories

def write_new(path,value):
    with path.open('x',encoding='utf8') as stream:json.dump(value,stream,indent=2);stream.write('\n')

def main():
    require(not(STAGE/'plan.json').exists(),'Inspect the existing sealed cleanup plan')
    STAGE.mkdir(parents=True,exist_ok=True)
    cache={};baseline_path=PHASE/'protection_before.json.gz'
    baseline=json.loads(gzip.decompress(baseline_path.read_bytes()));require(baseline['paths']==5209,'Unexpected protection baseline')
    protected={};link_changes=0
    for old in baseline['protected_artifacts']:
        now=record(old['path'],cache)
        require(all(now[name]==old[name] for name in ('bytes','sha256','file_identity','mtime_ns','file_attributes')),
                'Existing protected file changed: '+old['path'])
        link_changes+=now['links']!=old.get('links');protected[key(now['path'])]=now
    success_report=PROJECT/'evidence/ui_window_host'/SUCCESS/'build_result.json'
    require(record(success_report,cache)['sha256']==SUCCESS_REPORT_SHA,'Successful replacement report pin differs')
    success=json.loads(success_report.read_text('utf8'))
    require(success['build_id']==SUCCESS and success['executable']['sha256']==SUCCESS_EXE_SHA,
            'Successful replacement identity differs')
    attest=PHASE/'pair_preparation'/SUCCESS/'independent_attestation.json'
    require(record(attest,cache)['sha256']==SUCCESS_ATTEST_SHA,'Successful independent attestation pin differs')
    for identifier in (PARENT,SUCCESS):
        for root in (PROJECT/'Build/UiWindowHost'/identifier,PROJECT/'evidence/ui_window_host'/identifier):
            leaves,_dirs=tree(root,cache)
            for row in leaves:protected[key(row['path'])]=row
    for root in (PHASE/'pair_preparation'/SUCCESS,PROJECT/'evidence/game_menu/idle_render_cache/pair_preparation'/PARENT):
        leaves,_dirs=tree(root,cache)
        for row in leaves:protected[key(row['path'])]=row
    # Both current working Source files and retained Host/provider names are
    # outside the two exact failed roots; a shared file ID is only a safe alias.
    protected_rows=list(protected.values());protected_paths=set(protected)
    by_id={}
    for row in protected_rows:by_id.setdefault(tuple(row['file_identity']),[]).append(row['path'])
    targets=[];directories=[];summaries={}
    for role,root in ROOTS.items():
        require(root in (PROJECT/'Build/UiWindowHost'/FAILED,PROJECT/'evidence/ui_window_host'/FAILED),
                'Cleanup target differs from the explicit two roots')
        leaves,dirs=tree(root,cache)
        for row in leaves:
            path=Path(row['path']);relative=path.relative_to(root)
            require(key(path) not in protected_paths,'Protected path in deletion inventory')
            require(path.suffix.lower() not in ('.sav','.zssave','.civ5save') and
                    not any(part.lower() in ('sessions','settings','saves') for part in relative.parts),
                    'User data in failed build root')
            row.update(root_role=role,protected_external_hardlink_anchors=by_id.get(tuple(row['file_identity']),[])[:4])
        targets.extend(leaves);directories.extend(dirs)
        summaries[role]=dict(path=str(root),files=len(leaves),directories=len(dirs),logical_bytes=sum(row['bytes'] for row in leaves),
            readonly_files=sum(bool(row['file_attributes']&1) for row in leaves),
            empty_directories=sum(row['empty_at_plan'] for row in dirs),
            file_paths_over_259=sum(len(row['path'])>259 for row in leaves),directory_paths_over_259=sum(row['win32_chars']>259 for row in dirs))
    groups={}
    for row in targets:groups.setdefault(tuple(row['file_identity']),[]).append(row)
    expected_released=0;unique_allocated=0;shared=0;fully_owned=0
    for rows in groups.values():
        require(len({row['sha256'] for row in rows})==1 and len({row['allocated_bytes'] for row in rows})==1,'Alias bytes/allocation differ')
        links=rows[-1]['links'];require(links>=len(rows),'Planned aliases exceed physical link count')
        unique_allocated+=rows[0]['allocated_bytes']
        if links==len(rows):
            require(not rows[0]['protected_external_hardlink_anchors'],'A fully owned identity still has a protected external anchor')
            expected_released+=rows[0]['allocated_bytes'];fully_owned+=1
        else:shared+=1
    protected_snapshot=dict(schema='zerosis.terrain_phase1.failed_freeze.protection.v1',protected_artifacts=protected_rows,
        baseline=common.artifact(baseline_path),baseline_paths=5209,paths=len(protected_rows),baseline_content_or_identity_differences=0,
        baseline_link_count_changes=link_changes,parent=PARENT,successful_replacement=SUCCESS,native_host_or_game_executed=False)
    snapshot_path=STAGE/'protection_before.json.gz'
    with snapshot_path.open('xb') as stream:stream.write(gzip.compress((json.dumps(protected_snapshot,indent=2)+'\n').encode(),mtime=0))
    helper=PROJECT/'tools/civ5_ui_assets.py';source=helper.read_text('utf8');module=ast.parse(source)
    function=next(node for node in module.body if isinstance(node,ast.FunctionDef) and node.name=='_unlink_font_target_without_attribute_changes')
    segment=ast.get_source_segment(source,function)
    require('0x13' in segment and 'SetFileInformationByHandle(handle, 21' in segment and 'chmod' not in segment,
            'Readonly-preserving disposition helper differs')
    value=dict(schema='zerosis.terrain_phase1.failed_freeze.cleanup_plan.v1',utc=datetime.now(timezone.utc).isoformat(),
        status='PLAN_ONLY_REQUIRES_ROOT_DELETE_AUTHORIZATION',deletion_authorized=False,roots=summaries,files=targets,
        directories=sorted(directories,key=lambda row:(-len(Path(row['path']).parts),row['path'])),
        protected_snapshot=common.artifact(snapshot_path),protected_paths=len(protected_rows),protected_path_intersection=[],
        preserve_failed_attempt_diagnostics=str(PHASE/'host_build/attempts'),
        preserve_sources_originals_saves_runtime_defaults_and_codex=True,
        successful_replacement=dict(build_id=SUCCESS,report=record(success_report,cache),executable=record(success['executable']['path'],cache),
            independent_attestation=record(attest,cache)),
        initial_failure=record(PHASE/'host_build/freeze_failure.json',cache),
        allocation=dict(path_logical_bytes=sum(row['bytes'] for row in targets),unique_file_ids=len(groups),
            unique_allocated_bytes=unique_allocated,fully_owned_file_ids=fully_owned,externally_shared_file_ids=shared,
            expected_unique_allocated_bytes_released=expected_released,
            note='Allocated bytes counted once per real os.stat ID. Release estimate counts identities whose every current link is in these two roots; link counts must be refreshed before deletion.'),
        long_paths=dict(files=[row['path'] for row in targets if len(row['path'])>259],
            directories=[row for row in directories if row['win32_chars']>259]),
        deletion_method=dict(helper=common.artifact(helper),function=function.name,function_sha256=hashlib.sha256(segment.encode()).hexdigest(),
            operation='FileDispositionInfoEx class21 flags0x13 DELETE|POSIX_SEMANTICS|IGNORE_READONLY_ATTRIBUTE for one exact entry',
            attribute_changes_allowed=False,after_files='RemoveDirectory bottom-up for listed directory identities only; use extended Win32 paths',
            apply_requirements=['Root explicit delete authorization','Exact plan SHA','All protected content/ID/mtime/attrs unchanged before and after',
                'Every target path/size/SHA/ID/mtime/attrs rechecked before first deletion; current links refreshed','No unplanned entries or reparses',
                'Successful replacement report/executable/attestation remain pinned','Never clear readonly attributes or follow a shell-recursive deletion']),
        native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False,files_deleted=0)
    write_new(STAGE/'plan.json',value)
    print(json.dumps(dict(status=value['status'],plan_sha256=common.artifact(STAGE/'plan.json')['sha256'],
        files=len(targets),directories=len(directories),logical_bytes=value['allocation']['path_logical_bytes'],
        unique_allocated_bytes=unique_allocated,expected_released_bytes=expected_released,protected_paths=len(protected_rows),
        protected_path_intersection=0,long_file_paths=len(value['long_paths']['files']),long_directories=len(value['long_paths']['directories']),
        empty_directories=sum(row['empty_at_plan'] for row in directories),files_deleted=0)))

if __name__=='__main__':main()
