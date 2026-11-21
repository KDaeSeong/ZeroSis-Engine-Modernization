"""Preserve the current pair and measure storage before the next offline UI wave."""
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
PREVIOUS=PROJECT/'evidence/game_menu/options_video_preview'
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
def backup(name):
    path=PROJECT/name;row=ref(path)
    target=STAGE/'source_before'/(name.replace('/','__')+'.'+row['sha256'][:16]+'.gz')
    target.parent.mkdir(parents=True,exist_ok=True)
    if not target.exists():
        with target.open('xb') as stream:stream.write(gzip.compress(path.read_bytes(),mtime=0))
    assert hashlib.sha256(gzip.decompress(target.read_bytes())).hexdigest()==row['sha256']
    return dict(**row,backup=ref(target))


def begin():
    assert not(STAGE/'startup.json').exists()
    previous=read(PREVIOUS/'current_work.json')
    assert previous['storage']['after_pending'] is False and previous['current_prepared_runtime']['native_attempts']==0
    old_cleanup=read(PREVIOUS/'component_cleanup.json')
    assert old_cleanup['all_deleted_paths_currently_absent'] and not old_cleanup['current_wave_candidate_tmp_files']
    for row in old_cleanup['deletion_events']:assert not Path(row['path']).exists()
    last_cleanup=read(previous['intermediate_cleanup']['path'])
    assert last_cleanup['files_deleted']==6 and last_cleanup['all_candidates_absent']
    last_plan=read(Path(previous['intermediate_cleanup']['path']).with_name('cleanup_plan.json'))
    assert all(not Path(row['path']).exists() for row in last_plan['candidates'])
    before=json.loads(gzip.decompress((PREVIOUS/'protection_before.json.gz').read_bytes()))
    refs={storage.key(row['path']):row for row in before['protected_artifacts']}
    build=read(previous['current_host']['build_result']['path'])
    for row in menu.frozen_rows(build).values():refs[storage.key(row['path'])]=row
    for root in [PROJECT/'Build/UiWindowHost'/build['build_id']/'final/UIFrontEnd',
            Path(previous['current_prepared_runtime']['runtime_directory']),PROJECT/'Source/Assets/UIFrontEndV3']:
        for directory,names,leaves in os.walk(root,followlinks=False):
            for name in names:assert not os.stat(Path(directory)/name,follow_symlinks=False).st_file_attributes&0x400
            for name in leaves:
                row=ref(Path(directory)/name);refs[storage.key(row['path'])]=row
    for path in [previous['current_host']['executable']['path'],previous['current_host']['build_result']['path'],
            previous['current_host']['prepared_profile']['path'],PREVIOUS/'prepared_runtime_verification.json',
            PREVIOUS/'current_work.json',PREVIOUS/'storage_after.json',
            PROJECT/'evidence/game_menu/replay_calendar_legend/legend/assets_v3.json']:
        row=ref(path);refs[storage.key(row['path'])]=row
    rows=[];ids={}
    for expected in refs.values():
        path=Path(expected['path']);info=storage.ordinary(path);identity=(info.st_dev,info.st_ino)
        if identity not in ids:ids[identity]=(storage.digest(path),storage.allocated(path))
        sha,allocation=ids[identity];assert sha==expected['sha256'],str(path)
        for key in ('bytes','file_identity','mtime_ns','file_attributes'):
            if key in expected:assert storage.metadata(info)[key]==expected[key],str(path)
        rows.append(dict(path=str(path),sha256=sha,allocated_bytes=allocation,**storage.metadata(info)))
    protection=dict(schema='zerosis.options_reward_popups.protection.v1',protected_artifacts=rows,
        protected_paths=len(rows),unique_file_ids=len(ids),unique_allocated_bytes=sum(x[1] for x in ids.values()),native_execution=False)
    with (STAGE/'protection_before.json.gz').open('xb') as stream:
        stream.write(gzip.compress((json.dumps(protection,indent=2)+'\n').encode(),mtime=0))
    names=['Source/Host/MenuReplayPresentation.h','Source/Host/MenuReplayLayout.h','Source/Host/MenuLifecycleWindow.h',
        'Source/Host/HostRun.h','Source/Host/MenuFrontEndAssets.h','Source/Host/MenuOptionsContract.h',
        'Source/Host/MenuOptionsStore.h','Source/Host/MenuOptionsHostBinding.h','Source/Host/HostServices.h',
        'Source/Host/MenuFrontEndOptionsModel.h','Source/Host/MenuFrontEndOptionsView.h','Source/Presentation/BitmapWindow.cpp',
        'Source/Presentation/BitmapWindow.h','Tests/menu_replay_restored_scene.cpp','Tests/menu_replay_restoration.py',
        'tools/build_menu_suite_host.py','tools/attest_prepared_menu_host.py',
        'evidence/save_menu/20261013_original_screen/current_progress.json']
    write_new(STAGE/'source_before.json',dict(changed_file_backups=[backup(name) for name in names],full_project_copy=False))
    requirements=dict(schema='zerosis.options_reward_popups.requirements.v1',requirements=[
        'Connect original NoRewardPopupsCheckbox through the owned front-end option transaction, real Host preference snapshot and existing SDK IsOptionNoRewardPopups callback.',
        'Preserve defaultfalse and all SDK reward calculation/rule/balance code. The option selects the existing popup/notification presentation branches only.',
        'Read private V1/V2 bytes without rewriting and default the new bool tofalse. Explicit changed commits write canonical V3 with one appended noRewardPopups line.',
        'Keep all existing keys/order/control IDs, game/save/Mod schemas and video20second preview/partialcommit/rollback/owner semantics intact.',
        'Expose only committed/applied Host state via an atomic bool; cached edits, cancel and display-only preview must not leak the new draft to SDK readers.',
        'Use original checkbox/stack/source localization and existing V3 asset/font data where coverage is proven; do not clone a whole asset pack.',
        'Native Host/SDK/CLR/window/GPU/audio/game/screen execution remains held. Pure/source-extracted C++14 and file-only checks/preparation may continue.',
        'Protect current8837/1fba and original/default/recovery inputs. Remove owned intermediates and enforce10GiB confirmed-disposable threshold.'
    ],affected_modules=['Private preference V3 codec/store migration','Host binding and SDK UI preference callback','Source-backed game-options model/view'],
        save_compatibility='Only private Host preferences gain an explicitly planned V3 read/write schema. Existing V1/V2 read bytes and all GameCore/save/Mod IDs/schemas remain unchanged.',
        deployment='Explicit prepared profile only; original game/MODS/default/global registration unchanged.',
        native_execution=False,full_engine_goal_complete=False,previous_goal_turn_classification='progress')
    write_new(STAGE/'requirements.json',requirements)
    write_new(STAGE/'startup.json',dict(status='PASS_PREVIOUS_CLEANUP_AND_CURRENT_PAIR_BASELINE',protected_paths=len(rows),
        unique_file_ids=len(ids),prior_deleted_paths_verified=old_cleanup['deletion_event_count']+6,
        confirmed_disposable_bytes=0,threshold_bytes=10*1024**3,native_execution=False,source_changes_started=False))
    current=dict(schema='zerosis.options_reward_popups.current_work.v1',status='WORKING_ORIGINAL_NO_REWARD_POPUPS_OPTION_AND_V3_MIGRATION',
        previous_turn_classification='progress',native_execution=False,full_engine_goal_complete=False)
    write_new(STAGE/'current_work.json',current)
    path=PROJECT/'evidence/save_menu/20261013_original_screen/current_progress.json';progress=read(path)
    progress.update(status=current['status'],full_engine_goal_complete=False,latest_source_matches_linked_candidate=False,
        prepared_runtime_matches_latest_source=False,latest_source_matches_integrated_syntax_proof=False,
        latest_cpp_source_matches_actual_host_syntax_proof=False,latest_current_source_actual_cpp_compilation_verified=False,
        latest_host_source_matches_current_link_proof=False,
        current_source_working_stage=str(STAGE),previous_goal_turn_classification='progress')
    path.write_text(json.dumps(progress,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(status='PASS_FRESH_PROTECTION_AND_CLEANUP_BASELINE',paths=len(rows),ids=len(ids))))


def main():
    cli=argparse.ArgumentParser();cli.add_argument('action',choices=['begin','measure','verify','backup']);cli.add_argument('paths',nargs='*');cli.add_argument('--label',default='before');args=cli.parse_args()
    if args.action=='begin':begin()
    elif args.action=='backup':print(json.dumps([backup(name) for name in args.paths]))
    elif args.action=='measure':
        value=storage.measure_storage();value.update(schema='zerosis.options_reward_popups.storage.v1',utc=datetime.now(timezone.utc).isoformat(),
            confirmed_disposable_bytes=0,threshold_bytes=10*1024**3,measurement='FileStandardInfo.AllocationSize once per real os.stat identity; directories excluded.',native_execution=False)
        value['scope_note']='Includes then-existing project files exactly once per actual file identity; this scan receipt and later closing status edits are written after the scan. Project allocation is separate from volume free space.'
        value.pop('source_replacement_released_after_this_receipt',None)
        write_new(STAGE/('storage_'+args.label+'.json'),value)
        print(json.dumps({k:value[k] for k in ['status','file_paths','unique_allocated_bytes']}))
    else:
        before=json.loads(gzip.decompress((STAGE/'protection_before.json.gz').read_bytes()));differences=[];links=[];ids={}
        for row in before['protected_artifacts']:
            now=storage.metadata(storage.ordinary(row['path']));identity=tuple(now['file_identity'])
            if identity not in ids:ids[identity]=(storage.digest(row['path']),storage.allocated(row['path']))
            if any(now[k]!=row[k] for k in ('bytes','file_identity','mtime_ns','file_attributes')) or ids[identity]!=(row['sha256'],row['allocated_bytes']):differences.append(row['path'])
            if now['links']!=row['links']:links.append(dict(path=row['path'],before=row['links'],after=now['links']))
        value=dict(status='PASS' if not differences else 'FAIL',protected_paths=before['protected_paths'],differences=differences,alias_changes=links,native_execution=False)
        write_new(STAGE/('protection_'+args.label+'.json'),value);assert not differences
        print(json.dumps(dict(status=value['status'],paths=before['protected_paths'],differences=0,alias_changes=len(links))))


if __name__=='__main__':main()
