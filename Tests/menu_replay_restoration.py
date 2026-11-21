"""SDK-free source/text/Scene restoration checks. Never launches the Host or SDK."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import struct
import sys

PROJECT=Path(__file__).absolute().parents[1]
sys.dont_write_bytecode=True
sys.path.insert(0,str(PROJECT/'tools'));sys.path.insert(0,str(PROJECT/'Tests'))
from native_build import environment_for,run
from collect_baseline import digest,pe_header
from menu_replay_assets import artifact,original_replay_layout
from menu_suite_storage import storage
import menu_replay_offline as writer

ROOT=PROJECT/'evidence/game_menu/replay_hover_frame/integration'
ASSETS=PROJECT/'Source/Assets/UIFrontEndV4'
RUNTIME=PROJECT/'Build/InteractiveGameRuntime/20261105T114739Z_01dfa4cf86d8'


def build_cxx14(name,directory,evidence,source,includes):
    """Match the production Host C++14 dialect without changing shared tools."""
    environment,compiler=environment_for(Path(r'C:/Program Files/Microsoft Visual Studio/2022/Community'),'x64',directory)
    executable=directory/(name+'.exe');map_file=directory/(name+'.map')
    flags=['/nologo','/std:c++14','/source-charset:windows-1252','/EHsc','/W4','/WX','/O2','/fp:strict','/MT']
    flags += [f'/I"{path}"' for path in includes]
    flags += [f'"{source}"',f'/Fo"{directory/(name+".obj")}"',f'/Fe"{executable}"']
    link=['/INCREMENTAL:NO','/Brepro','/WX','/OPT:REF','/OPT:ICF','/MACHINE:X64',f'/MAP:{map_file}']
    response=directory/'compile.rsp';response.write_text('\n'.join(flags)+'\n',encoding='utf8')
    result=run([compiler,'@'+str(response),'/link',*link],cwd=directory,env=environment,timeout=180)
    output=(result.stdout+result.stderr).decode('mbcs',errors='replace')
    log=evidence/('compile_'+name+'_x64_cxx14.txt');log.write_text(output,encoding='utf8')
    if result.returncode or re.search(r'\bwarning\s+[A-Z]+\d+|경고\s+[A-Z]+\d+',output,re.I):
        raise RuntimeError('C++14 component build failed or emitted warnings: '+str(log)+'\n'+output[:6000])
    pe=pe_header(executable)
    if pe['architecture']!='x64':raise RuntimeError('Wrong C++14 component architecture')
    return dict(path=str(executable),sha256=digest(executable),pe=pe,compiler=compiler,compiler_sha256=digest(Path(compiler)),
        flags=flags+['/link']+link,actual_compile_response=artifact(response),cpp_dialect='c++14',
        compiler_and_linker_warnings=0,log=str(log),log_sha256=digest(log),map=str(map_file))


def metadata(path):
    loc=sqlite3.connect((RUNTIME/'localization.db').as_uri()+'?mode=ro&immutable=1',uri=True)
    rules=sqlite3.connect((RUNTIME/'rules.db').as_uri()+'?mode=ro&immutable=1',uri=True)
    keys=('TXT_KEY_REPLAY_TITLE','TXT_KEY_REPLAY_VIEWER_MAP_TITLE','TXT_KEY_REPLAY_VIEWER_GRAPHS_TITLE',
          'TXT_KEY_REPLAY_VIEWER_MESSAGES_TITLE','TXT_KEY_REPLAY_PLAYPAUSE')
    def label(key):
        row=loc.execute('SELECT Text FROM Language_ko_KR WHERE Tag=?',(key,)).fetchone()
        if row is None or not row[0] or row[0].startswith('TXT_KEY_'):raise ValueError('Missing actual Korean label '+key)
        return row[0]
    labels=[label(key) for key in keys]+['턴',label('TXT_KEY_REPLAY_NOGRAPHDATA'),
        '지형은 최종 시점 참조입니다. 영토와 도시는 선택한 턴의 실제 기록입니다.',
        '이 재생 형식은 지원하지 않습니다.',label('TXT_KEY_BACK_BUTTON')]
    blob=bytearray()
    def text(value):
        raw=value.encode('utf8');blob.extend(struct.pack('<I',len(raw)));blob.extend(raw)
    for value in labels:text(value)
    colors=[];blob.extend(struct.pack('<I',2))
    for identifier in (0,7):
        row=rules.execute('SELECT p.PrimaryColor,p.SecondaryColor,a.Red,a.Green,a.Blue,a.Alpha,b.Red,b.Green,b.Blue,b.Alpha FROM PlayerColors p JOIN Colors a ON a.Type=p.PrimaryColor JOIN Colors b ON b.Type=p.SecondaryColor WHERE p.ID=?',(identifier,)).fetchone()
        if row is None:raise ValueError('Actual recorded player color missing')
        blob.extend(struct.pack('<8f',*row[2:]));colors.append(dict(id=identifier,primary=row[0],secondary=row[1],rgba=row[2:]))
    names=('REPLAYDATASET_SCORE','REPLAYDATASET_POPULATION');blob.extend(struct.pack('<I',len(names)))
    for name in names:
        row=rules.execute('SELECT Description FROM ReplayDataSets WHERE Type=?',(name,)).fetchone()
        if row is None:raise ValueError('Actual dataset name missing')
        text(name);text(label(row[0]))
    rich=list(rules.execute('SELECT Type,Red,Green,Blue,Alpha FROM Colors ORDER BY ID'))
    blob.extend(struct.pack('<I',len(rich)))
    for row in rich:text(row[0]);blob.extend(struct.pack('<4f',*row[1:]))
    def optional_label(key):
        row=loc.execute('SELECT Text FROM Language_ko_KR WHERE Tag=?',(key,)).fetchone()
        return row[0] if row and row[0] and not row[0].startswith('TXT_KEY_') else ''
    calendars=list(rules.execute('SELECT ID,Type FROM Calendars ORDER BY ID'))
    speeds=list(rules.execute('SELECT ID,Type FROM GameSpeeds ORDER BY ID'))
    blob.extend(struct.pack('<I',len(calendars)))
    for identifier,name in calendars:blob.extend(struct.pack('<I',identifier));text(name)
    blob.extend(struct.pack('<I',len(speeds)))
    increment_count=0
    for identifier,name in speeds:
        blob.extend(struct.pack('<I',identifier));text(name)
        rows=list(rules.execute('SELECT MonthIncrement,TurnsPerIncrement FROM GameSpeed_Turns WHERE GameSpeedType=? ORDER BY rowid',(name,)))
        increment_count+=len(rows);blob.extend(struct.pack('<I',len(rows)))
        for row in rows:blob.extend(struct.pack('<2I',*row))
    missing=[]
    def calendar_name(key):
        # Stock ReplayViewer Locale.Lookup(Description): a missing key is shown as the key itself.
        row=loc.execute('SELECT Text FROM Language_ko_KR WHERE Tag=?',(key,)).fetchone()
        return row[0] if row else key
    for table in ('Months','Seasons'):
        rows=list(rules.execute('SELECT ID,Description FROM '+table+' ORDER BY ID'))
        if [row[0] for row in rows]!=list(range(len(rows))):raise ValueError('Calendar names are not contiguous original IDs')
        blob.extend(struct.pack('<I',len(rows)))
        for _,key in rows:
            value=calendar_name(key);text(value)
            if value==key:missing.append(key)
    definitions=dict(rules.execute("SELECT Name,Value FROM Defines WHERE Name IN ('WEEKS_PER_MONTHS','HIDDEN_START_TURN_OFFSET')"))
    blob.extend(struct.pack('<2i',definitions['WEEKS_PER_MONTHS'],definitions['HIDDEN_START_TURN_OFFSET']))
    number_keys=('TXT_KEY_TIME_AD','TXT_KEY_TIME_BC','TXT_KEY_TIME_TURN','TXT_KEY_TIME_WEEK','TXT_KEY_TP_TURN_COUNTER')
    blob.extend(struct.pack('<I',len(number_keys)))
    for key in number_keys:
        value=label(key)
        if len(re.findall(r'\{1_[^{}]+\}',value))!=1 or re.sub(r'\{1_[^{}]+\}','',value).count('{'):
            raise ValueError('Actual calendar number template no longer matches this bounded file-only fixture')
        text(key);text(value)
    portraits=list(rules.execute('SELECT c.ID,c.PortraitIndex,c.ShortDescription,a.Filename,a.IconsPerRow,a.IconsPerColumn FROM Civilizations c JOIN IconTextureAtlases a ON a.Atlas=c.IconAtlas AND a.IconSize=32 ORDER BY c.ID'))
    blob.extend(struct.pack('<I',len(portraits)))
    for identifier,portrait,caption,filename,columns,rows in portraits:
        blob.extend(struct.pack('<4I',identifier,portrait,int(columns),int(rows)));text(filename);text(optional_label(caption))
    civilization_ids=[rules.execute('SELECT ID FROM Civilizations WHERE Type=?',(kind,)).fetchone()[0] for kind in ('CIVILIZATION_AMERICA','CIVILIZATION_ROME')]
    blob.extend(struct.pack('<2I',*civilization_ids))
    first_caption=optional_label(next(row[2] for row in portraits if row[0]==civilization_ids[0]))
    caption_match=re.fullmatch(r'\[COLOR:(\d+):(\d+):(\d+):(\d+)\]([^\[\]]+)\[ENDCOLOR\]',first_caption)
    if not caption_match or any(int(value)>255 for value in caption_match.groups()[:4]):
        raise ValueError('Actual first civilization caption no longer uses this exact numeric color fixture')
    caption_rgba=[int(value)/255 for value in caption_match.groups()[:4]]
    blob.extend(struct.pack('<4f',*caption_rgba));text(caption_match.group(5))
    blob.extend(struct.pack('<I',len(rich)))
    for row in rich:text(row[0]);blob.extend(struct.pack('<4d',*row[1:]))
    blob.extend(struct.pack('<I',len(colors)))
    for row in colors:text(row['primary']);text(row['secondary'])
    loc.close();rules.close();path.write_bytes(blob)
    return dict(original_label_keys=keys+('TXT_KEY_BACK_BUTTON',),actual_player_colors=colors,actual_rich_colors=len(rich),
        actual_calendars=calendars,actual_game_speeds=speeds,ordered_increment_rows=increment_count,
        number_template_keys=number_keys,missing_original_calendar_localization=missing,
        actual_definitions=definitions,civilization_portrait_rows=len(portraits),fixture_civilization_ids=civilization_ids,
        actual_first_civilization_caption_rgba=caption_rgba,
        localization_fixture_scope='Only the five exact original single-integer templates; the native Localization library is not loaded.')


def reuse_cpu_previews(current_packets,current_inputs,current_lines):
    """Same actual packet bytes and DDS inputs reuse already reviewed images."""
    fingerprints=[(row['bytes'],row['sha256']) for row in current_packets]
    current={row['path']:row for row in current_inputs}
    for receipt in sorted((ROOT/'scene').glob('*/result.json'),key=lambda x:x.stat().st_mtime_ns,reverse=True):
        old=json.loads(receipt.read_text('utf8'))
        if not str(old.get('status','')).startswith('PASS_'):continue
        if [(row['bytes'],row['sha256']) for row in old.get('actual_scene_packets',[])]!=fingerprints:continue
        if [(row['bytes'],row['sha256']) for row in old.get('actual_scene_line_packets',[])]!=[(row['bytes'],row['sha256']) for row in current_lines]:continue
        old_assets=[row for row in old.get('inputs_after',[]) if Path(row['path']).is_relative_to(ASSETS)]
        if not old_assets or any(current.get(row['path'])!=row for row in old_assets):continue
        images=old.get('cpu_previews',[])
        if len(images)!=3 or any(artifact(Path(row['image']['path']))!=row['image'] for row in images):continue
        return images,artifact(receipt)
    return None,None


def deduplicate_cpu_images(images,stage):
    """Keep one exact PNG after actual byte comparison; preserve proof references."""
    prior={}
    for receipt in ROOT.glob('scene/*/result.json'):
        old=json.loads(receipt.read_text('utf8'))
        if not str(old.get('status','')).startswith('PASS_'):continue
        for item in old.get('cpu_previews',[]):
            row=item['image'];path=Path(row['path'])
            if path.is_file() and artifact(path)==row:prior[(row['bytes'],row['sha256'])]=row
    retired=[]
    for item in images:
        row=item['image'];path=Path(row['path']);old=prior.get((row['bytes'],row['sha256']))
        if not old or path==Path(old['path']) or not path.is_relative_to(stage):continue
        info=storage.ordinary(path)
        if info.st_nlink!=1 or info.st_file_attributes&1 or artifact(path)!=row:raise ValueError('Owned duplicate PNG identity changed')
        candidate=dict(row,file_identity=[info.st_dev,info.st_ino],allocated_bytes=storage.allocated(path),retained_exact_image=old)
        path.unlink();candidate['result']='DELETED_EXACT_OWNED_DUPLICATE_CPU_PNG_AFTER_BYTE_HASH_COMPARISON';retired.append(candidate);item['image']=old
    return retired


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--text-only',action='store_true');options=parser.parse_args()
    group='text' if options.text_only else 'scene'
    inputs=[PROJECT/name for name in ('Source/Host/MenuReplayData.h','Source/Host/MenuReplayTimeline.h',
        'Source/Host/MenuReplayText.h','Source/Host/MenuReplayLayout.h','Source/Host/MenuReplayCalendar.h','Source/Host/MenuFrontEndAssets.h',
        'Source/Host/MenuReplayGraphColors.h',
        'Source/Host/MenuReplayGraphGeometry.h','Source/Host/MenuReplayScrollModel.h','Source/Host/MenuReplayMessageViewport.h',
        'Source/Host/MenuReplayPointerGuides.h','Source/Host/MenuFrontEndGridLayout.h',
        'tools/menu_replay_assets.py','Tests/menu_replay_rich_text.cpp','Tests/menu_replay_restoration.py')]
    if not options.text_only:
        inputs+=[PROJECT/'Source/Host/MenuReplayPresentation.h',PROJECT/'Tests/menu_replay_restored_scene.cpp',
                 PROJECT/'Source/Presentation/BitmapWindow.h',PROJECT/'Source/Presentation/BitmapWindow.cpp',
                 PROJECT/'Source/Presentation/BitmapPointerPress.h',
                 PROJECT/'Source/Presentation/BitmapRenderer.h',PROJECT/'Source/Presentation/BitmapRenderer.cpp',
                 PROJECT/'Source/Presentation/SceneLineContract.h',PROJECT/'Source/Presentation/WorldViewRenderer.cpp',
                 PROJECT/'tools/menu_frontend_cpu.py',
                 RUNTIME/'rules.db',RUNTIME/'localization.db']
        inputs+=sorted(x for x in ASSETS.rglob('*') if x.is_file())
    before=[artifact(x) for x in inputs]
    signature=hashlib.sha256(json.dumps(before,sort_keys=True).encode()).hexdigest()[:16]
    stage=ROOT/group/signature;stage.mkdir(parents=True,exist_ok=True);receipt=stage/'result.json'
    if receipt.exists():raise ValueError('Inspect existing restoration proof instead of repeating it')
    build=PROJECT/('Build/MenuReplayRichText/current' if options.text_only else 'Build/MenuReplayRestoredScene/current');build.mkdir(parents=True,exist_ok=True)
    name='MenuReplayRichText' if options.text_only else 'MenuReplayRestoredScene'
    report=dict(schema='zerosis.menu_replay.restoration_component.v1',inputs_before=before,source_layout=original_replay_layout(),
        synthetic_fixture_history=True,native_host_sdk_window_gpu_executed=False,retail_pixel_acceptance=False)
    cleanup_names=[name+'.obj',name+'.map','compile.rsp','read_build_environment.cmd']
    try:
        if not options.text_only:
            writer.BUILD=build;report['actual_sdk_writer_extraction']=writer.extract_writer();cleanup_names+=['sdk_replay_writer.inc','labels_palette.bin']
            cleanup_names += [leaf for name in ('messages','map','graph') for leaf in ('restored_'+name+'.packet','restored_'+name+'.packet.lines.json')]
            report['actual_labels_palette']=metadata(build/'labels_palette.bin')
        compiled=build_cxx14(name=name,directory=build,evidence=stage,
            source=PROJECT/('Tests/menu_replay_rich_text.cpp' if options.text_only else 'Tests/menu_replay_restored_scene.cpp'),
            includes=[PROJECT/'Source/Host',PROJECT/'Tests',build])
        report['build']=compiled
        imported=run([Path(compiled['compiler']).with_name('dumpbin.exe'),'/dependents',compiled['path']],cwd=build,timeout=30)
        names=sorted(set(re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$',imported.stdout.decode('mbcs',errors='replace'),re.M)))
        if imported.returncode or {name.lower() for name in names}!={'kernel32.dll'}:raise ValueError('Unexpected component DLL dependency: '+repr(names))
        report['imported_dlls']=names
        command=[compiled['path']] if options.text_only else [compiled['path'],ASSETS,build/'labels_palette.bin',build]
        result=run(command,cwd=build,timeout=60)
        if result.returncode:raise ValueError((result.stdout+result.stderr).decode('utf8',errors='replace'))
        report.update(json.loads(result.stdout))
        if not options.text_only:
            from menu_frontend_cpu import render
            packets=[build/('restored_'+name+'.packet') for name in ('messages','map','graph')]
            line_packets=[path.with_name(path.name+'.lines.json') for path in packets]
            report['actual_scene_packets']=[artifact(x) for x in packets]
            report['actual_scene_line_packets']=[artifact(x) for x in line_packets]
            images,reused=reuse_cpu_previews(report['actual_scene_packets'],before,report['actual_scene_line_packets'])
            report['cpu_previews']=images or [render(x,stage/(x.stem+'.png'),ASSETS,lines) for x,lines in zip(packets,line_packets)]
            if reused:report['cpu_previews_reused_from_identical_packet_bytes_and_atlas_inputs']=reused
            report['duplicate_cpu_png_cleanup']=deduplicate_cpu_images(report['cpu_previews'],stage)
        report['inputs_after']=[artifact(x) for x in inputs]
        if report['inputs_after']!=before:raise ValueError('Production or actual immutable assets changed during fixture')
    except Exception as error:
        report.update(status='FAIL_SDK_FREE_REPLAY_RESTORATION',error=str(error));raise
    finally:
        removed=[]
        for leaf in cleanup_names:
            path=build/leaf
            if not path.exists():continue
            info=storage.ordinary(path)
            if path.absolute().parent!=build.absolute() or info.st_nlink!=1:raise ValueError('Replay cleanup target is not an exact owned single-link intermediate')
            row=dict(artifact(path),file_identity=[info.st_dev,info.st_ino],allocated_bytes=storage.allocated(path))
            path.unlink();row['result']='DELETED_EXACT_OWNED_REGENERABLE_REPLAY_INTERMEDIATE';removed.append(row)
        report['owned_intermediate_cleanup']=removed;receipt.write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(status=report['status'],checks=report['checks'],report=str(receipt))))
    return 0


if __name__=='__main__':raise SystemExit(main())
