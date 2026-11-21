"""Owned baseline, changed-file backups and allocation accounting for idle rendering."""
from __future__ import annotations
import argparse
import copy
from datetime import datetime,timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode=True
STAGE=Path(__file__).absolute().parent
PROJECT=STAGE.parents[2]
sys.path.insert(0,str(PROJECT/'tools'))
import build_exit_confirm_host as common
import build_menu_suite_host as builder
import retained_menu_suite_host_input as menu
from menu_suite_storage import storage

def write_new(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf8') as f:json.dump(value,f,indent=2);f.write('\n')

def backup(name):
    path=PROJECT/name;row=common.artifact(path)
    target=STAGE/'source_before'/(name.replace('/','__')+'.'+row['sha256'][:16]+'.gz')
    target.parent.mkdir(parents=True,exist_ok=True)
    if not target.exists():
        with target.open('xb') as f:f.write(gzip.compress(path.read_bytes(),mtime=0))
    assert hashlib.sha256(gzip.decompress(target.read_bytes())).hexdigest()==row['sha256']
    return dict(source=row,backup=common.artifact(target))

def begin():
    assert not(STAGE/'startup.json').exists()
    previous=PROJECT/'evidence/game_menu/native_slider_hover/current_work.json'
    current=json.loads(previous.read_text('utf8'))
    assert current['working_source_matches_current_frozen_and_prepared_profile']
    report=Path(current['current_host']['build_result']['path'])
    parent=json.loads(report.read_text('utf8'))
    # The OS tool changed before this work. Capture its current protection
    # baseline, without changing the historical report or selecting a compiler.
    baseline_parent=copy.deepcopy(parent);tool_changes=[]
    system_cmd=Path(os.environ['SystemRoot'])/'System32/cmd.exe'
    for index,row in enumerate(baseline_parent['protected_artifacts']):
        if common.key(row['path'])==common.key(system_cmd):
            actual=common.artifact(system_cmd)
            if actual['sha256']!=row['sha256']:
                tool_changes.append(dict(historical=row,current=actual))
                baseline_parent['protected_artifacts'][index]=actual
    refs={common.key(row['path']):row for row in builder.protected_inventory(baseline_parent)}
    for row in menu.frozen_rows(parent).values():refs[common.key(row['path'])]=row
    runtime=Path(current['current_prepared_runtime']['runtime_directory'])
    for root in (runtime,PROJECT/'Source/Assets/UIFrontEndV4'):
        for directory,names,leaves in os.walk(root,followlinks=False):
            for name in names:assert not os.stat(Path(directory)/name,follow_symlinks=False).st_file_attributes&0x400
            for name in leaves:
                row=common.artifact(Path(directory)/name);refs[common.key(row['path'])]=row
    for path in (report,previous,Path(current['current_host']['executable']['path']),
                 Path(current['current_host']['prepared_profile']['path']),
                 PROJECT/'evidence/game_menu/native_slider_hover/prepared_runtime_verification.json'):
        row=common.artifact(path);refs[common.key(path)]=row
    rows=[]
    for row in refs.values():
        current_ref=common.artifact(row['path']);assert current_ref['sha256']==row['sha256']
        current_ref['allocated_bytes']=storage.allocated(row['path']);rows.append(current_ref)
    protection=dict(protected_artifacts=rows,paths=len(rows),native_execution=False)
    with (STAGE/'protection_before.json.gz').open('xb') as f:
        f.write(gzip.compress((json.dumps(protection,indent=2)+'\n').encode(),mtime=0))
    names=['Source/Presentation/WorldTerrainRenderer.cpp','Source/Presentation/WorldViewRenderer.cpp',
        'Source/Presentation/WorldViewRenderer.h','Source/Host/InteractiveGameLoop.h',
        'tools/build_menu_suite_host.py','tools/attest_prepared_menu_host.py',
        'docs/CLAUDE_HANDOFF.md','docs/ORIGINAL_MENUS_OFFLINE.md',
        'evidence/save_menu/20261013_original_screen/current_progress.json']
    write_new(STAGE/'source_before.json',dict(backups=[backup(n) for n in names],full_project_copy=False))
    write_new(STAGE/'startup.json',dict(status='PASS_CURRENT_INPUT_AND_USER_SESSION_PROTECTION_BASELINE',
        utc=datetime.now(timezone.utc).isoformat(),protected_paths=len(rows),previous_host=parent['build_id'],
        current_runtime=str(runtime),user_session_preserved='sessions/350dd3b9ceb408a391b5a8aa63b48301',
        cleanup_before_new_work='Existing component temporary cleanup is closed; only current-owned new intermediates will be retired.',
        preexisting_system_tool_changes=tool_changes,compiler_provider_refresh_approved_by_this_baseline=False,
        confirmed_disposable_bytes=0,threshold_bytes=10*1024**3,native_execution=False))
    target=PROJECT/'evidence/save_menu/20261013_original_screen/current_progress.json'
    value=json.loads(target.read_text('utf8'));value.update(status='WORKING_IDLE_RENDER_CACHE',
        current_source_working_stage=str(STAGE),latest_source_matches_linked_candidate=False,
        prepared_runtime_matches_latest_source=False,full_engine_goal_complete=False)
    target.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(status='PASS_BASELINE_AND_CHANGED_FILE_BACKUPS',protected=len(rows))))

def main():
    cli=argparse.ArgumentParser();cli.add_argument('action',choices=['begin','measure','verify','backup']);cli.add_argument('values',nargs='*');args=cli.parse_args()
    if args.action=='begin':begin()
    elif args.action=='backup':print(json.dumps([backup(n) for n in args.values]))
    elif args.action=='measure':
        label=args.values[0];assert label in ('before','precompile','after')
        value=storage.measure_storage();value.update(utc=datetime.now(timezone.utc).isoformat(),
            scope_note='Project file allocation counted once per real os.stat identity; this receipt is written after its scan.',
            native_execution=False,confirmed_disposable_bytes=0,threshold_bytes=10*1024**3)
        value.pop('source_replacement_released_after_this_receipt',None)
        write_new(STAGE/('storage_'+label+'.json'),value)
        print(json.dumps({k:value[k] for k in ('status','file_paths','unique_allocated_bytes')}))
    else:
        label=args.values[0];assert label in ('precompile','after')
        original=json.loads(gzip.decompress((STAGE/'protection_before.json.gz').read_bytes()));bad=[];aliases=0
        for row in original['protected_artifacts']:
            now=common.artifact(row['path'])
            if any(now[k]!=row[k] for k in ('bytes','sha256','file_identity','mtime_ns','file_attributes')):bad.append(row['path'])
            aliases+=now.get('links')!=row.get('links')
        value=dict(status='FAIL' if bad else 'PASS',paths=original['paths'],differences=bad,alias_changes=aliases,native_execution=False)
        write_new(STAGE/('protection_'+label+'.json'),value);assert not bad
        print(json.dumps(dict(status='PASS',protected=original['paths'],differences=0,alias_changes=aliases)))

if __name__=='__main__':main()
