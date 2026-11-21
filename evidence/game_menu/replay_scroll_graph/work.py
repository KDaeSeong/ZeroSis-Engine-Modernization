"""Storage/preservation startup for the source-backed replay scroll/graph wave."""
from __future__ import annotations
import argparse
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
PREVIOUS=PROJECT/'evidence/game_menu/replay_calendar_legend'
sys.path.insert(0,str(PROJECT/'tools'))
from menu_suite_storage import storage
import retained_menu_suite_host_input as menu


def read(path):return json.loads(Path(path).read_text('utf8'))
def ref(path):
    path=Path(path).absolute();info=storage.ordinary(path)
    return dict(path=str(path),sha256=storage.digest(path),**storage.metadata(info))
def write_new(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf8') as stream:json.dump(value,stream,indent=2);stream.write('\n')
def backup(relative):
    path=PROJECT/relative;row=ref(path);target=STAGE/'source_before'/(relative.replace('/','__')+'.'+row['sha256'][:16]+'.gz')
    target.parent.mkdir(parents=True,exist_ok=True)
    if not target.exists():
        with target.open('xb') as stream:stream.write(gzip.compress(path.read_bytes(),mtime=0))
    assert hashlib.sha256(gzip.decompress(target.read_bytes())).hexdigest()==row['sha256']
    return dict(**row,backup=ref(target))


def begin():
    assert not(STAGE/'startup.json').exists()
    previous=read(PREVIOUS/'current_work.json')
    assert previous['storage']['after_pending'] is False and previous['current_prepared_runtime']['native_attempts']==0
    req=dict(schema='zerosis.replay_scroll_graph.requirements.v1',
        requirements=['Restore original map floor-based turn slider selection, exact thumb grab and first-coalesced movement.',
            'Restore continuous original message viewport scrolling with bounded visible rows, raw paragraphs/order unchanged.',
            'Restore exact original100-segment/101-vertex graph projection, scale, sparse endpoint gaps and width1; no prototype point markers or1024-stride.',
            'Render all source-defined graph segments through a bounded genuine line primitive without dropping lines to a per-pixel sprite budget.',
            'Preserve data/assets/IDs/save schema/balance/default game/registration and original user files.',
            'Use C++14 controlled components and actual compile/link; do not execute Host/SDK/CLR/HWND/GPU/game or screen tools.',
            'Reuse V3 immutable assets, latest deb/4f194 and recovery inputs; remove owned intermediates and enforce10GiB disposable threshold.'],
        source_evidence='Original ReplayViewer.lua uses100segments and floor map selection; MessagesPanel is a native continuous ScrollPanel.',
        affected_modules=['Replay scroll model/row layout/presentation','Replay exact graph projection','Scene line geometry/presentation renderer and file-only fixtures'],
        save_compatibility='No game/replay bytes, persistent IDs, schema or balance changes. New UI primitives are transient.',
        deployment='Explicit prepared profile only; no default promotion or original MODS deployment.',native_execution=False,
        full_engine_goal_complete=False,previous_goal_turn_classification='progress')
    write_new(STAGE/'requirements.json',req)
    old=json.loads(gzip.decompress((PREVIOUS/'protection_before.json.gz').read_bytes()))
    refs={storage.key(row['path']):row for row in old['protected_artifacts']}
    build=read(Path(previous['current_host']['build_result']['path']))
    for row in menu.frozen_rows(build).values():refs[storage.key(row['path'])]=row
    for root in [PROJECT/'Build/UiWindowHost'/build['build_id']/'final/UIFrontEnd',
                 Path(previous['current_prepared_runtime']['runtime_directory']),PROJECT/'Source/Assets/UIFrontEndV3']:
        for directory,names,leaves in os.walk(root,followlinks=False):
            for name in names:assert not os.stat(Path(directory)/name,follow_symlinks=False).st_file_attributes&0x400
            for name in leaves:
                row=ref(Path(directory)/name);refs[storage.key(row['path'])]=row
    for path in [previous['current_host']['executable']['path'],previous['current_host']['build_result']['path'],
        previous['current_host']['prepared_profile']['path'],PREVIOUS/'legend/assets_v3.json',
        PREVIOUS/'prepared_runtime_verification.json',PREVIOUS/'current_work.json',PREVIOUS/'storage_after.json']:
        row=ref(path);refs[storage.key(row['path'])]=row
    rows=[];ids={}
    for expected in refs.values():
        path=Path(expected['path']);info=storage.ordinary(path);identity=(info.st_dev,info.st_ino)
        if identity not in ids:ids[identity]=(storage.digest(path),storage.allocated(path))
        sha,allocated=ids[identity];assert sha==expected['sha256'],str(path)
        for key in ('bytes','file_identity','mtime_ns','file_attributes'):
            if key in expected:assert storage.metadata(info)[key]==expected[key],str(path)
        rows.append(dict(path=str(path),sha256=sha,allocated_bytes=allocated,**storage.metadata(info)))
    baseline=dict(schema='zerosis.replay_scroll_graph.protection.v1',protected_artifacts=rows,protected_paths=len(rows),
        unique_file_ids=len(ids),unique_allocated_bytes=sum(v[1] for v in ids.values()),native_execution=False)
    out=STAGE/'protection_before.json.gz'
    with out.open('xb') as stream:stream.write(gzip.compress((json.dumps(baseline,indent=2)+'\n').encode(),mtime=0))
    names=['Source/Host/MenuReplayPresentation.h','Source/Host/MenuReplayText.h','Source/Host/MenuReplayLayout.h',
        'Source/Host/MenuLifecycleWindow.h','Source/Host/HostRun.h','Source/Presentation/BitmapRenderer.h',
        'Source/Presentation/BitmapRenderer.cpp','Source/Presentation/BitmapWindow.cpp','Tests/menu_replay_restored_scene.cpp',
        'Tests/menu_replay_restoration.py','tools/build_menu_suite_host.py','tools/attest_prepared_menu_host.py',
        'evidence/save_menu/20261013_original_screen/current_progress.json']
    write_new(STAGE/'source_before.json',dict(changed_file_backups=[backup(name) for name in names],full_project_copy=False))
    value=dict(status='PASS_NEW_WAVE_BASELINE_AND_PRIOR_CLEANUP_PRECHECK',protected_paths=len(rows),unique_file_ids=len(ids),
        protection=ref(out),prior_final_storage=ref(PREVIOUS/'storage_after.json'),
        prior_six_compiled_intermediates_absent=True,confirmed_disposable_bytes=0,threshold_bytes=10*1024**3,
        native_execution=False,source_changes_started=False)
    write_new(STAGE/'startup.json',value);print(json.dumps({k:value[k] for k in ['status','protected_paths','unique_file_ids']}))


def main():
    cli=argparse.ArgumentParser();cli.add_argument('action',choices=['begin','measure','verify','backup']);cli.add_argument('paths',nargs='*');cli.add_argument('--label',default='before');args=cli.parse_args()
    if args.action=='begin':begin()
    elif args.action=='backup':print(json.dumps([backup(name) for name in args.paths]))
    elif args.action=='measure':
        result=storage.measure_storage();result.update(schema='zerosis.replay_scroll_graph.storage.v1',
            utc=datetime.now(timezone.utc).isoformat(),confirmed_disposable_bytes=0,threshold_bytes=10*1024**3,
            measurement='FileStandardInfo.AllocationSize once per real os.stat identity; directories excluded.',native_execution=False)
        write_new(STAGE/('storage_'+args.label+'.json'),result)
        print(json.dumps({k:result[k] for k in ['status','file_paths','unique_allocated_bytes']}))
    else:
        before=json.loads(gzip.decompress((STAGE/'protection_before.json.gz').read_bytes()));differences=[];links=[];ids={}
        for row in before['protected_artifacts']:
            info=storage.ordinary(row['path']);now=storage.metadata(info);identity=tuple(now['file_identity'])
            if identity not in ids:ids[identity]=(storage.digest(row['path']),storage.allocated(row['path']))
            if any(now[k]!=row[k] for k in ('bytes','file_identity','mtime_ns','file_attributes')) or ids[identity]!=(row['sha256'],row['allocated_bytes']):differences.append(row['path'])
            if now['links']!=row['links']:links.append(dict(path=row['path'],before=row['links'],after=now['links']))
        value=dict(status='PASS' if not differences else 'FAIL',protected_paths=before['protected_paths'],differences=differences,alias_changes=links,native_execution=False)
        write_new(STAGE/('protection_'+args.label+'.json'),value);print(json.dumps(dict(status=value['status'],paths=before['protected_paths'],differences=len(differences),alias_changes=len(links))))
        assert not differences


if __name__=='__main__':main()
