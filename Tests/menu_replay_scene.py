"""Actual replay viewer Scene/input component and CPU-only original-atlas previews."""
from __future__ import annotations
import json
from pathlib import Path
import re
import sqlite3
import struct
import sys

PROJECT=Path(__file__).absolute().parents[1]
sys.dont_write_bytecode=True
sys.path.insert(0,str(PROJECT/'tools'))
from native_build import build_program,run
from menu_replay_assets import artifact
from menu_suite_storage import storage
from menu_frontend_cpu import render

BUILD=PROJECT/'Build/MenuReplaySceneComponent/current'
STAGE=PROJECT/'evidence/game_menu/original_menu_followup/replay/scene'
ASSETS=PROJECT/'Source/Assets/UIFrontEnd'
RUNTIME=PROJECT/'Build/InteractiveGameRuntime/20261101T080450Z_424fb64608b2'


def metadata(path):
    db=sqlite3.connect((RUNTIME/'localization.db').as_uri()+'?mode=ro&immutable=1',uri=True)
    keys=('TXT_KEY_REPLAY_TITLE','TXT_KEY_REPLAY_VIEWER_MAP_TITLE','TXT_KEY_REPLAY_VIEWER_GRAPHS_TITLE',
          'TXT_KEY_REPLAY_VIEWER_MESSAGES_TITLE','TXT_KEY_REPLAY_PLAYPAUSE')
    values=[]
    for key in keys:
        row=db.execute('SELECT Text FROM Language_ko_KR WHERE Tag=?',(key,)).fetchone()
        if not row or not row[0] or row[0].startswith('TXT_KEY_'):raise ValueError('Original replay Korean label is unavailable: '+key)
        values.append(row[0])
    values+=['턴','기록된 그래프 데이터가 없습니다.',
        '지형은 최종 시점 참조이며 기본 표시입니다. 영토와 도시는 선택한 턴의 실제 기록입니다.',
        '이 재생 기록의 형식을 지원하지 않습니다.']
    blob=bytearray()
    def text(value):
        raw=value.encode('utf8');blob.extend(struct.pack('<I',len(raw)));blob.extend(raw)
    for value in values:text(value)
    rules=sqlite3.connect((RUNTIME/'rules.db').as_uri()+'?mode=ro&immutable=1',uri=True)
    blob.extend(struct.pack('<I',2));colors=[]
    for identifier in (0,7):
        row=rules.execute('SELECT a.Red,a.Green,a.Blue,a.Alpha,b.Red,b.Green,b.Blue,b.Alpha '
            'FROM PlayerColors p JOIN Colors a ON a.Type=p.PrimaryColor JOIN Colors b ON b.Type=p.SecondaryColor '
            'WHERE p.ID=?',(identifier,)).fetchone()
        if row is None:raise ValueError('Recorded fixture PlayerColor has no original database palette')
        colors.append(dict(recorded_player_color=identifier,rgba=list(row)));blob.extend(struct.pack('<8f',*row))
    names=('REPLAYDATASET_SCORE','REPLAYDATASET_POPULATION');blob.extend(struct.pack('<I',len(names)))
    datasets=[]
    for name in names:
        row=rules.execute('SELECT Description FROM ReplayDataSets WHERE Type=?',(name,)).fetchone()
        if row is None:raise ValueError('Actual replay dataset is missing: '+name)
        label=db.execute('SELECT Text FROM Language_ko_KR WHERE Tag=?',(row[0],)).fetchone()
        if label is None:raise ValueError('Actual replay dataset Korean label is missing')
        text(name);text(label[0]);datasets.append(dict(type=name,description=row[0],localized=label[0]))
    rules.close();db.close();path.write_bytes(blob)
    return dict(original_replay_label_keys=keys,actual_recorded_player_colors=colors,actual_data_set_labels=datasets)


def cleanup(names):
    rows=[]
    for name in names:
        path=BUILD/name
        if not path.exists():continue
        info=storage.ordinary(path)
        if path.absolute().parent!=BUILD.absolute() or info.st_nlink!=1:raise ValueError('Replay scene cleanup scope changed')
        row=dict(artifact(path),file_identity=[info.st_dev,info.st_ino],allocated_bytes=storage.allocated(path))
        path.unlink();row['result']='DELETED_EXACT_OWNED_REGENERABLE_SCENE_INTERMEDIATE';rows.append(row)
    return rows


def main():
    BUILD.mkdir(parents=True,exist_ok=True);STAGE.mkdir(parents=True,exist_ok=True)
    receipt=STAGE/'result.json'
    if receipt.exists():raise ValueError('Inspect the existing replay scene proof before rerunning')
    files=[PROJECT/'Source/Host'/name for name in ('MenuReplayData.h','MenuReplayTimeline.h','MenuReplayPresentation.h','MenuFrontEndAssets.h')]
    files+=[Path(__file__),Path(__file__).with_suffix('.cpp'),PROJECT/'Tests/menu_frontend_scene_fixture.h',
        PROJECT/'tools/menu_frontend_cpu.py',RUNTIME/'rules.db',RUNTIME/'localization.db',
        PROJECT/'evidence/interactive_game/20261101T080450Z_424fb64608b2/request.json',
        RUNTIME/'ZeroSisHost_x64.exe',RUNTIME/'CvGameCoreDLL_Expansion2_x64.dll',PROJECT/'tools/Start-Engine.ps1']
    files+=sorted(path for path in ASSETS.rglob('*') if path.is_file())
    before=[artifact(path) for path in files]
    report=dict(schema='zerosis.menu_replay.actual_asset_scene_component.v1',inputs_before=before,
        synthetic_fixture_history=True,host_or_sdk_executed=False,window_or_gpu_created=False,
        retail_pixel_acceptance=False,source_replay_layout_full_parity=False)
    try:
        report['original_labels_and_palette']=metadata(BUILD/'labels_palette.bin')
        built=build_program(name='MenuReplaySceneComponent',architecture='x64',
            vs=Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community'),directory=BUILD,evidence=STAGE,
            source=Path(__file__).with_suffix('.cpp'),includes=[PROJECT/'Source/Host',PROJECT/'Tests'])
        report['build']=built
        imported=run([Path(built['compiler']).with_name('dumpbin.exe'),'/dependents',built['path']],cwd=BUILD,timeout=30)
        names=sorted(set(re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$',imported.stdout.decode('mbcs',errors='replace'),re.M)))
        if imported.returncode or {name.lower() for name in names}!={'kernel32.dll'}:
            raise ValueError('Replay scene fixture imports unexpected modules: '+repr(names))
        report['imported_dlls']=names
        seed=PROJECT/'Build/MenuReplayComponent/current/sdk_writer_fixture.bin'
        report['actual_sdk_writer_layout_fixture']=artifact(seed)
        result=run([built['path'],ASSETS,seed,BUILD/'labels_palette.bin',BUILD],cwd=BUILD,timeout=30)
        if result.returncode:raise ValueError((result.stdout+result.stderr).decode('utf8',errors='replace'))
        report.update(json.loads(result.stdout))
        report['actual_scene_packets']=[artifact(BUILD/f'replay_{name}.packet') for name in ('map','graph','messages')]
        report['cpu_previews']=[render(BUILD/f'replay_{name}.packet',STAGE/f'cpu_replay_{name}.png',ASSETS) for name in ('map','graph')]
        after=[artifact(path) for path in files]
        if after!=before:raise ValueError('Replay/asset source, prepared pair or original database changed during fixture')
        report['inputs_after']=after
    except Exception as error:
        report.update(status='FAIL_SDK_FREE_REPLAY_SCENE',error=str(error));raise
    finally:
        report['owned_intermediate_cleanup']=cleanup(('MenuReplaySceneComponent.obj','MenuReplaySceneComponent.map',
            'compile.rsp','read_build_environment.cmd','labels_palette.bin','replay_map.packet','replay_graph.packet','replay_messages.packet'))
        receipt.write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(status=report['status'],checks=report['checks'],report=str(receipt),host_or_sdk_executed=False)))
    return 0


if __name__=='__main__':raise SystemExit(main())
