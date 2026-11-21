"""Independently verify original TechAward UI delivery, HWND input, and native-save restore.

This checks normal SDK research completion followed by the installed stock popup,
then a new Host process restoring the saved acquired-technology state. It does not
claim retail renderer, complete 3D, human-input, or retail-save equivalence.
"""
from __future__ import annotations
import argparse, hashlib, json, re, shutil, sys, uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from collect_baseline import PROJECT, digest
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts
import verify_interactive_game as interactive
import verify_city_capture_restore as save_restore

EVIDENCE = PROJECT / 'evidence/interactive_game'
RUNTIME = PROJECT / 'Build/InteractiveGameRuntime'
RUN_ID = re.compile(r'\d{8}T\d{6}Z_[0-9a-f]{12}\Z')
GAME = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V")
LUA = GAME / 'Assets/UI/InGame/Popups/TechAwardPopup.lua'
XML = GAME / 'Assets/DLC/Expansion2/UI/InGame/Popups/TechAwardPopup.xml'
HOST_FILES = ('InteractiveGameLoop.h', 'InteractiveGameSession.h', 'UiPopupContext.h',
              'InteractiveUiSession.h', 'HostServices.h')

def fail(message: str) -> None: raise RuntimeError(message)
def checked(ref: Any, expected: Path | None = None) -> Path:
    if type(ref) is not dict: fail('Missing immutable artifact reference')
    check_artifacts(ref); p = Path(ref['path']).resolve(strict=True)
    if expected is not None and p != expected.resolve(strict=True): fail('Artifact differs from its required exact path')
    return p
def read_json(path: Path) -> dict:
    x=json.loads(path.read_text(encoding='utf-8'))
    if type(x) is not dict: fail(f'Expected JSON object: {path.name}')
    return x
def rows(text: str, marker: str, pattern: str) -> list[tuple[str,...]]:
    out=[]
    for line in text.splitlines():
        if line.startswith(marker+'='):
            m=re.fullmatch(pattern,line)
            if not m: fail(f'Malformed {marker} marker')
            out.append(tuple(m.groups()))
    return out
def exactly(items, message):
    if len(items)!=1: fail(f'{message}: expected exactly one, got {len(items)}')
    return items[0]
def run(run_id: str):
    if not RUN_ID.fullmatch(run_id): fail('Invalid actual run identity')
    root=EVIDENCE/run_id; reqp=root/'request.json'; resp=root/'result.json'
    req,res=read_json(reqp),read_json(resp)
    if req.get('run_id')!=run_id or res.get('run_id')!=run_id: fail('Run identity differs from evidence directory')
    check_artifacts(req); check_artifacts(res)
    checked(res.get('request'),reqp); attempt=read_json(checked(res.get('attempt'),root/'attempt.json'))
    out=checked(res.get('stdout'),root/'stdout.log').read_text(encoding='utf-8').replace('\r\n','\n').replace('\r','\n')
    err=checked(res.get('stderr'),root/'stderr.log').read_text(encoding='utf-8',errors='replace')
    if res.get('returncode')!=0 or res.get('timed_out') is not False or res.get('runtime_inputs_unchanged') is not True or \
       attempt.get('status')!='FINISHED' or attempt.get('returncode')!=0 or attempt.get('timed_out') is not False or \
       attempt.get('host_pid')!=res.get('pid') or attempt.get('pid')!=res.get('driver_pid'):
        fail('Runner/attempt do not prove a clean completed pair of distinct processes')
    if re.search(r'HOST_FAILURE|HOST_NATIVE_EXCEPTION|HOST_CLEANUP_PENDING|SCRIPT_FAILURE|INTERACTIVE_INPUT_REJECTED',out+'\n'+err):
        fail('Run output contains host, script, cleanup, or rejected-input failure')
    if req.get('smoke') is not True or req.get('stage_or_mods_changed') is not False:
        fail('Run was not an isolated no-stage/no-MODS smoke')
    runtime=Path(req.get('cwd','')).resolve(strict=True)
    if runtime != (RUNTIME/run_id).resolve(strict=True): fail('Run did not use its exact private runtime')
    driverp=checked(res.get('interactive_ui_driver'),root/'driver_result.json'); driver=read_json(driverp)
    if driver.get('status')!='INTERACTIVE_UI_DRIVER_PASS' or driver.get('returncode')!=0 or driver.get('pid')!=res.get('pid') or driver.get('error') is not None:
        fail('Actual UI driver result is failed or belongs to another host')
    provenance=interactive.verify_provenance(req,res,runtime,expected_input_profile=req.get('input_profile'))
    return root,req,res,attempt,out,err,runtime,driver,provenance

def state_rows(path: Path):
    records=path.read_text(encoding='utf-8').splitlines()
    players=[r.split('|') for r in records if r.startswith('P|')]
    teams=[r.split('|') for r in records if r.startswith('T|')]
    return players,teams

def generated(result: dict,runtime: Path):
    files=result.get('generated_files')
    if not isinstance(files,list): fail('Run result lacks generated inventory')
    names={}
    base=(runtime/'sessions').resolve(strict=True)
    for row in files:
        p=checked(row)
        if not p.is_relative_to(base): fail('Generated artifact escaped private session tree')
        names.setdefault(p.name,[]).append(p)
    actual=sorted(p.resolve() for p in base.rglob('*') if p.is_file())
    listed=sorted(checked(x) for x in files)
    if actual!=listed or len(set(listed))!=len(listed): fail('Generated inventory incomplete or duplicated')
    return names

def one_file(files,name,runtime):
    p=exactly(files.get(name,[]),f'Missing/ambiguous generated {name}')
    if not p.is_relative_to((runtime/'sessions').resolve(strict=True)): fail('Snapshot escaped run')
    return p

def verify_host_assets(req, frozen_dir):
    frozen_dir.mkdir(parents=True, exist_ok=True)
    ref=req.get('provenance',{}).get('host_build'); buildp=checked(ref); build=read_json(buildp)
    if build.get('status')!='UI_WINDOW_HOST_CANDIDATE_BUILT' or build.get('source_inputs_unchanged') is not True:
        fail('TechAward run lacks sealed successful Host build')
    srcs={Path(x.get('path','')).name:x for x in build.get('sources',[]) if type(x) is dict}
    if not set(HOST_FILES)<=srcs.keys(): fail('Host build source closure lacks TechAward producers')
    for name in HOST_FILES:
        r=srcs[name]; p=checked(r)
        current=PROJECT/'Source/Host'/name
        if Path(r.get('original_source','')).resolve(strict=True)!=current.resolve(strict=True) or digest(p)!=digest(current):
            fail(f'Frozen Host source differs from current source: {name}')
        shutil.copy2(current,frozen_dir/name)
    loop=(PROJECT/'Source/Host/InteractiveGameLoop.h').read_text(encoding='utf-8')
    session=(PROJECT/'Source/Host/InteractiveGameSession.h').read_text(encoding='utf-8')
    popup=(PROJECT/'Source/Host/UiPopupContext.h').read_text(encoding='utf-8')
    service=(PROJECT/'Source/Host/HostServices.h').read_text(encoding='utf-8')
    for token,txt in [('INTERACTIVE_TECH_AWARD_TARGET=',loop),('INTERACTIVE_TECH_AWARD_SHOWN=',popup),
                      ('INTERACTIVE_TECH_AWARD_CLOSED=',popup),('PrepareResearchCompletionSmoke',session),
                      ('length<-1',service),('UI_GAME_MESSAGE_RETAINED=',service)]:
        if token not in txt: fail(f'Current Host source lacks required TechAward/message contract: {token}')
    if 'length<0' in service: fail('HostServices still rejects the original SDK length=-1 notification sentinel')
    prepared_path=checked(build.get('ui_assets')); prepared=read_json(prepared_path)
    if prepared.get('status')!='INSTALLED_UI_POPUP_ASSETS_PREPARED_NOT_RUNTIME_VERIFIED': fail('Host build lacks sealed retained UI preparation')
    inputs=prepared.get('inputs',[])
    def input_named(name):
        return exactly([r for r in inputs if type(r) is dict and r.get('name')==name],f'Prepared UI catalog {name}')
    lua_row=input_named('TechAwardPopup'); installed=checked(lua_row.get('installed'),LUA)
    lua_snapshot=checked(lua_row.get('snapshot'))
    if digest(installed)!=digest(lua_snapshot): fail('Prepared TechAward Lua snapshot differs from exact installed original bytes')
    layout=input_named('TechAwardLayout')
    xml_installed=checked(layout.get('installed'),XML); xml_snapshot=checked(layout.get('snapshot'))
    if digest(xml_installed)!=digest(xml_snapshot): fail('Prepared TechAward XML snapshot differs from installed original')
    # Verify generated header and build dependency reference the prepared exact source bytes.
    header_ref=prepared.get('compiled_assets'); header=checked(header_ref)
    compiler=[r for r in build.get('compiler_inputs',[]) if type(r) is dict and str(r.get('relative_path','')).replace('\\','/').casefold()=='source/host/uipopupassets.generated.h']
    comp=exactly(compiler,'Compiled generated UI header input')
    comp_path=checked(comp)
    if Path(comp.get('original_path','')).resolve(strict=True)!=header.resolve(strict=True) or digest(comp_path)!=digest(header):
        fail('Compiled Host did not consume the prepared exact UI header')
    hb=header.read_bytes(); raw=lua_snapshot.read_bytes()
    # The generated serializer uses bounded hex escapes in adjacent C++ string literals.
    from prepare_ui_popup_assets import cpp_literal, lua_value, control_tree
    if b'static const char TechAwardPopup[]=\n'+cpp_literal(raw).encode('ascii')+b';' not in hb:
        fail('Generated header does not embed exact original TechAwardPopup.lua bytes')
    tree=control_tree(__import__('xml.etree.ElementTree',fromlist=['ElementTree']).parse(xml_snapshot).getroot())
    prepared_tree=prepared.get('xml_control_trees',{}).get('TechAwardLayout')
    if type(prepared_tree) is not dict or any(prepared_tree.get(k)!=v for k,v in tree.items()) or \
       prepared_tree.get('contextName')!='TechAwardPopup' or prepared_tree.get('popupKind')!='TechAward':
        fail('Prepared TechAward control tree differs from original XML snapshot')
    # JSON object keys stringify integer glyph-codepoint keys; restore their
    # producer types before replaying lua_value's deterministic serialization.
    def restore_numeric_keys(value):
        if isinstance(value,dict):
            return {(int(key) if isinstance(key,str) and re.fullmatch(r'-?\d+',key) else key):restore_numeric_keys(child)
                    for key,child in value.items()}
        if isinstance(value,list): return [restore_numeric_keys(child) for child in value]
        return value
    serialized=('ZeroSisUiLayout='+lua_value(restore_numeric_keys(prepared_tree))+'\n').encode('ascii')
    if b'static const char TechAwardLayout[]=\n'+cpp_literal(serialized).encode('ascii')+b';' not in hb:
        fail('Generated header does not embed exact XML-derived TechAward layout tree')
    lua=lua_snapshot.read_bytes()
    for token in (b'BUTTONPOPUP_TECH_AWARD',b'popupInfo.Data3',b'storedPopupInfo',b'OnContinueButtonClicked'):
        if token not in lua: fail(f'Original TechAward Lua lifecycle lacks {token}')
    if not re.search(rb'Controls\.ContinueButton\s*:\s*RegisterCallback\s*\(\s*Mouse\.eLClick\s*,\s*OnContinueButtonClicked\s*\)',lua) or \
       not re.search(rb'UIManager\s*:\s*DequeuePopup\s*\(\s*ContextPtr\s*\)',lua):
        fail('Original TechAward Continue callback does not call the stock close lifecycle')
    return {'build_report':artifact(buildp),'prepared_assets':artifact(prepared_path),'generated_header':artifact(header),
            'compiler_header':comp,'lua':artifact(lua_snapshot),'xml':artifact(xml_snapshot),
            'exact_original_lua_embedded':True,'xml_tree_embedded':True,'original_callback_tokens_verified':True}

def award_source(out,res,runtime,driver,files):
    if res.get('tech_award_requested') is not True or res.get('tech_award_verified') is not True:
        fail('Source result does not report a requested verified TechAward run')
    if res.get('status')!='CONTINUOUS_INTERACTIVE_SDK_TECH_AWARD_SMOKE_PASS':
        fail('Source status is not the normal research TechAward smoke')
    fixture=exactly(rows(out,'INTERACTIVE_RESEARCH_COMPLETION_FIXTURE',r'^INTERACTIVE_RESEARCH_COMPLETION_FIXTURE=(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)\|([01])$'),'completion fixture')
    shown=exactly(rows(out,'INTERACTIVE_TECH_AWARD_SHOWN',r'^INTERACTIVE_TECH_AWARD_SHOWN=(\d+)\|(\d+)\|(\d+)\|(\d+)\|([01])$'),'TechAward shown')
    target=exactly(rows(out,'INTERACTIVE_TECH_AWARD_TARGET',r'^INTERACTIVE_TECH_AWARD_TARGET=(\d+)\|(\d+)\|(\d+)\|(\d+)$'),'TechAward target')
    closed=exactly(rows(out,'INTERACTIVE_TECH_AWARD_CLOSED',r'^INTERACTIVE_TECH_AWARD_CLOSED=(\d+)\|(\d+)\|0\|STATE_UNCHANGED$'),'TechAward close')
    verified=exactly(rows(out,'INTERACTIVE_RESEARCH_COMPLETION_VERIFIED',r'^INTERACTIVE_RESEARCH_COMPLETION_VERIFIED=(-?\d+)\|(\d+)\|(-?\d+)\|([01])\|(\d+)$'),'completion observation')
    f=list(map(int,fixture)); s=list(map(int,shown)); tech,key,gen,turn=map(int,target); closekey,closeturn=map(int,closed); v=list(map(int,verified))
    if res.get('tech_award_fixtures')!=[f] or res.get('tech_award_shown')!=[s] or \
       res.get('tech_award_targets')!=[[tech,key,gen,turn]] or res.get('tech_award_closed')!=[[key,turn]] or \
       res.get('tech_award_observations')!=[v]:
        fail('Runner TechAward arrays differ from independently parsed stdout markers')
    if f[5]!=f[6]-1 or f[6]<=1 or f[7]<100 or f[8]!=0 or s!=[f[1],0,f[3],f[0]+1,1] or \
       tech!=f[3] or key<=0 or gen<=0 or turn!=f[0]+1 or (closekey,closeturn)!=(key,turn) or \
       v[0]!=tech or v[1]!=turn or v[2]==tech or v[3]!=1 or v[4]!=1:
        fail('Fixture does not prove cost-minus-one, normal completion, exact popup payload, and settled award state')
    # Fixture team research remaining can be zero despite player cost; only the live technology state is authoritative.
    queued=rows(out,'INTERACTIVE_UI_QUEUED',r'^INTERACTIVE_UI_QUEUED=(-?\d+)\|(-?\d+)\|(-?\d+)\|(-?\d+)$')
    if queued.count(('68',str(f[1]),'0',str(tech)))!=1: fail('Actual SDK queue lacks exactly one Technology Award payload')
    if out.index('INTERACTIVE_RESEARCH_COMPLETION_FIXTURE=')>out.index('INTERACTIVE_END_TURN_ACCEPTED=') or not (
       out.index('INTERACTIVE_END_TURN_ACCEPTED=')<out.index('INTERACTIVE_TECH_AWARD_SHOWN=')<out.index('INTERACTIVE_TECH_AWARD_CLOSED=')<out.index('INTERACTIVE_RESEARCH_COMPLETION_VERIFIED=')<out.index('INTERACTIVE_NATIVE_SAVE=') ):
        fail('Fixture, normal turn, award lifecycle, settled state, and save are out of order')
    next_turn=exactly(rows(out,'INTERACTIVE_NEXT_HUMAN_TURN',r'^INTERACTIVE_NEXT_HUMAN_TURN=(\d+)\|(\d+)$'),
                      'normal SDK next-human-turn result')
    accepted=exactly(rows(out,'INTERACTIVE_END_TURN_ACCEPTED',r'^INTERACTIVE_END_TURN_ACCEPTED=(\d+)$'),
                     'accepted normal EndTurn command')
    if int(next_turn[0])!=turn or int(next_turn[1])<=0 or \
       int(accepted[0])!=f[0] or \
       not out.index('INTERACTIVE_END_TURN_ACCEPTED=')<out.index('INTERACTIVE_NEXT_HUMAN_TURN=')<out.index('INTERACTIVE_TECH_AWARD_SHOWN='):
        fail('Technology award was not delivered during the next normal active-player turn')
    # Original SDK emits AddMessage(...,-1,...); Host must retain that system message rather than reject it.
    messages=rows(out,'UI_GAME_MESSAGE_RETAINED',r'^UI_GAME_MESSAGE_RETAINED=(\d+)\|(\d+)\|(-?\d+)\|(\d+)\|(\d+)$')
    negatives=[r for r in messages if r[1]==fixture[1] and r[2]=='-1']
    sdk_team=PROJECT/'Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvTeam.cpp'
    sdk_text=sdk_team.read_bytes()
    if b'void CvTeam::announceTechToPlayers' not in sdk_text or \
       b'DLLUI->AddMessage(0, ePlayer, false, (bSound ? GC.getEVENT_MESSAGE_TIME() : -1)' not in sdk_text or \
       not any(r[0]=='0' and r[2]=='-1' and r[3]=='0' and int(r[4])>0 for r in negatives):
        fail('Original announceTechToPlayers -1 message contract was not retained by HostServices')
    lines=out.splitlines()
    msg_line=exactly([i for i,line in enumerate(lines) if re.fullmatch(rf'UI_GAME_MESSAGE_RETAINED=0\|{re.escape(fixture[1])}\|-1\|0\|\d+',line)],
                     'original length=-1 research notification log position')
    queued_line=exactly([i for i,line in enumerate(lines) if line==f'INTERACTIVE_UI_QUEUED=68|{fixture[1]}|0|{fixture[3]}'],
                        'Technology Award queue log position')
    accepted_line=exactly([i for i,line in enumerate(lines) if line.startswith('INTERACTIVE_END_TURN_ACCEPTED=')],
                          'accepted EndTurn log position')
    shown_line=exactly([i for i,line in enumerate(lines) if line.startswith('INTERACTIVE_TECH_AWARD_SHOWN=')],
                       'TechAward shown log position')
    if not accepted_line<msg_line<queued_line<shown_line:
        fail('Original research notification and popup queue are not ordered within the normal turn')
    owner=int(f[1]); team=int(f[2]); tech=int(f[3]); before=one_file(files,'play-initial-state.txt',runtime)
    after=one_file(files,'play-final-state.txt',runtime); selected=one_file(files,'play-decisions-selected-state.txt',runtime)
    decision=one_file(files,'play-decisions-next-turn-state.txt',runtime)
    p0,t0=state_rows(before); ps,ts=state_rows(selected); p1,t1=state_rows(after); pd,td=state_rows(decision)
    def player(rows_,pid): return exactly([r for r in rows_ if len(r)>10 and r[0]=='P' and int(r[1])==pid],f'Player {pid} state')
    def techrow(ts,tm,th): return exactly([r for r in ts if len(r)==4 and r[0]=='T' and int(r[1])==tm and int(r[2])==th],f'Team {tm} technology {th}')
    if int(player(p0,owner)[5])!=team or int(player(ps,owner)[5])!=team or int(player(p1,owner)[5])!=team or int(player(pd,owner)[5])!=team or \
       int(player(ps,owner)[10])!=tech or techrow(t0,team,tech)[3]!='0' or techrow(ts,team,tech)[3]!='0' or \
       techrow(td,team,tech)[3]!='1' or techrow(t1,team,tech)[3]!='1' or \
       int(player(pd,owner)[10])==tech or int(player(p1,owner)[10])==tech:
        fail('Actual SDK snapshot does not prove team technology false→true and selected research settling')
    decision_target=exactly(rows(out,'INTERACTIVE_DECISION_RESEARCH_TARGET',r'^INTERACTIVE_DECISION_RESEARCH_TARGET=(\d+)\|(\d+)$'),
                            'original TechTree technology selection')
    if tuple(map(int,decision_target))[0]!=tech or 'INTERACTIVE_DECISION_TREE_SELECTION_REMAINS_OPEN=true' not in out:
        fail('Original TechTree did not select this technology and retain its callback context')
    ui_frames=rows(out,'INTERACTIVE_UI_FRAME',r'^INTERACTIVE_UI_FRAME=(\d+)\|(\d+)\|(-?\d+)\|([^|]+)\|(\d+)\|(\d+)\|([^|]+)\|([^|]+)$')
    tree_key=int(decision_target[1])
    tree_posts=rows(out,'INTERACTIVE_SMOKE_POSTED',r'^INTERACTIVE_SMOKE_POSTED=(\d+)\|(\d+)\|(-?\d+)\|(-?\d+)$')
    tree_inputs=rows(out,'INTERACTIVE_UI_NATIVE_INPUT',r'^INTERACTIVE_UI_NATIVE_INPUT=(\d+)\|(\d+)\|(\d+)\|([01])$')
    target_posts=[r for r in tree_posts if r[1]==str(tree_key)]
    tree_gen=int(exactly(sorted({r[0] for r in target_posts}),'research-tree target generation'))
    if len(target_posts)!=1:
        fail('Selected technology target was not posted exactly once')
    target_native=[r for r in tree_inputs if r[0]==str(tree_gen) and r[1]=='1' and r[3]=='1']
    native_target=exactly(target_native,'consumed same-generation research-tree left click')
    tree_dispatch_inputs=rows(out,'UI_WINDOW_INPUT',r'^UI_WINDOW_INPUT=(\d+)\|(\d+)\|(\d+)\|([01])\|(\d+)\|(\d+)\|([01])\|([01])\|(-?\d+)\|\d+$')
    tree_dispatch=exactly([r for r in tree_dispatch_inputs if r[1]=='2' and r[2]==native_target[2] and
                           r[3]=='1' and r[4]==r[5] and r[6]=='1' and r[7]=='1'],
                          'original TechTree callback dispatch record')
    tree_scenes=[r for r in driver.get('scene_requests',[]) if type(r) is dict and r.get('context')=='research-tree']
    tree_frames=[r for r in ui_frames if r[3]=='research-tree' and int(r[1])==tree_gen]
    tree_frame=exactly(tree_frames,'research-tree frame matching the posted target generation')
    tree_folder=Path(tree_frame[7]).resolve(strict=True)
    tree_scene=exactly([r for r in tree_scenes if Path(r.get('folder','')).resolve()==tree_folder],
                       'original TechTree scene bound to posted target frame')
    tree_manifest=read_json(checked(tree_scene.get('manifest'))); tree_snap=read_json(checked(tree_manifest.get('snapshot')))
    tech_targets=[r for r in tree_manifest.get('retained_input_targets',[]) if type(r) is dict and r.get('key')==tree_key and r.get('event')=='LeftClick']
    tech_target=exactly(tech_targets,'original TechButton handoff target')
    if tech_target.get('id')!='TechButton' or tech_target.get('void1')!=tech or tech_target.get('void2')!=0 or \
       tech_target.get('visible') is not True or tech_target.get('disabled') is not False:
        fail('Research choice is not the live visible enabled original TechButton payload')
    if not any(type(r) is dict and r.get('key')==tree_key and r.get('id')=='TechButton' and r.get('void1')==tech
               for r in tree_snap.get('inputTargets',[])):
        fail('Frozen TechTree snapshot does not contain the exact selected original TechButton')
    # The window hit-test can resolve the posted hotspot to its generated child
    # control key (for example B2); validate that actual callback target too.
    dispatch_targets=[r for r in tree_manifest.get('retained_input_targets',[]) if type(r) is dict and
                      r.get('key')==int(native_target[2]) and r.get('event')=='LeftClick']
    dispatch=exactly(dispatch_targets,'actual TechTree child callback target')
    if dispatch.get('void1')!=tech or dispatch.get('void2')!=0 or dispatch.get('visible') is not True or \
       dispatch.get('disabled') is not False or type(dispatch.get('bounds')) is not dict or \
       dispatch.get('bounds')!=dispatch.get('clippedBounds') or dispatch['bounds'].get('width',0)<=0 or dispatch['bounds'].get('height',0)<=0:
        fail('Resolved TechTree child callback differs from the selected technology or is not fully visible/enabled')
    if not any(type(r) is dict and r.get('key')==dispatch.get('key') and r.get('void1')==tech and r.get('void2')==0
               for r in tree_snap.get('inputTargets',[])):
        fail('TechTree frame snapshot omits the actual resolved technology callback')
    target_frame=[r for r in ui_frames if r[3]=='tech-award' and int(r[1])==gen]
    fr=exactly(target_frame,'TechAward HWND frame matching the posted generation'); framegen=int(fr[1])
    if framegen!=gen: fail('TechAward target generation differs from actual presented HWND frame')
    posts=tree_posts
    inputs=rows(out,'UI_WINDOW_INPUT',r'^UI_WINDOW_INPUT=(\d+)\|(\d+)\|(\d+)\|([01])\|(\d+)\|(\d+)\|([01])\|([01])\|(-?\d+)\|\d+$')
    uiinputs=tree_inputs
    pp=[r for r in posts if r[:2]==(str(gen),str(key))]
    # Popup-local input confirms RNG invariance and timer 1→0. HWND generation
    # and posted-key identity are independently tied by the two native records.
    ii=[r for r in inputs if r[1]=='2' and r[2]==str(key) and r[3]=='1' and r[4]==r[5] and
        r[6]=='1' and r[7]=='0' and int(r[8])==turn]
    uu=[r for r in uiinputs if r[0]==str(gen) and r[2]==str(key) and r[3]=='1']
    if len(pp)!=1 or len(ii)!=1 or len(uu)!=1:
        fail('Continue HWND posted click was not consumed exactly once by same-generation original UI')
    scenes=[x for x in driver.get('scene_requests',[]) if type(x) is dict and x.get('context')=='tech-award']
    award_folder=Path(fr[7]).resolve(strict=True)
    scene=exactly([x for x in scenes if Path(x.get('folder','')).resolve()==award_folder],
                  'TechAward scene request bound to target HWND generation and frame folder')
    manifest=read_json(checked(scene.get('manifest'))); snap=read_json(checked(manifest.get('snapshot')))
    targets=[x for x in manifest.get('retained_input_targets',[]) if type(x) is dict and x.get('key')==key and x.get('event')=='LeftClick']
    stargets=[x for x in snap.get('inputTargets',[]) if type(x) is dict and x.get('key')==key and x.get('event')=='LeftClick']
    control=exactly(targets,'retained ContinueButton target'); sc=exactly(stargets,'snapshot ContinueButton target')
    b=control.get('bounds')
    if control.get('id')!='ContinueButton' or control.get('visible') is not True or control.get('disabled') is not False or \
       type(b) is not dict or b!=control.get('clippedBounds') or b.get('width',0)<=0 or b.get('height',0)<=0 or \
       sc.get('visible') is not True or sc.get('disabled') is not False or sc.get('bounds')!=b or sc.get('clippedBounds')!=b:
        fail('ContinueButton is not the fully visible, enabled, positive-area original retained control')
    opened_rows=rows(out,'INTERACTIVE_UI_OPENED',r'^INTERACTIVE_UI_OPENED=(\d+)\|([^|]+)$')
    opened=exactly([r for r in opened_rows if r[1]=='tech-award'],'TechAward context open')
    # Context snapshots are listed by exact session path and must pair to this opened context sequence.
    all_context=[p for ps in files.values() for p in ps if p.parent.name==f'play-context-{opened[0]}']
    shownfile=exactly([p for p in all_context if p.name=='ui-popup-1-shown.json'],'TechAward shown lifecycle snapshot')
    closedfile=exactly([p for p in all_context if p.name=='ui-popup-1-closed.json'],'TechAward closed lifecycle snapshot')
    a=read_json(shownfile); z=read_json(closedfile)
    if a.get('active') is not True or a.get('timerSemaphore')!=1 or z.get('active') is not False or z.get('timerSemaphore')!=0 or z.get('inputTargets')!=[] or \
       a.get('contextName')!='TechAwardPopup' or a.get('popupKind')!='TechAward' or \
       z.get('contextName')!='TechAwardPopup' or z.get('popupKind')!='TechAward' or \
       a.get('lifecycle')!=['queued','shown:68'] or \
       z.get('lifecycle')!=['queued','shown:68','processed:68','closed']:
        fail('TechAward native timer/lifecycle snapshots do not show held→released close')
    shown_sizes=rows(out,'UI_POPUP_shown',r'^UI_POPUP_shown=(\d+),(\d+),(\d+)$')
    closed_sizes=rows(out,'UI_POPUP_closed',r'^UI_POPUP_closed=(\d+),(\d+),(\d+)$')
    if len([r for r in shown_sizes if r[1]==str(turn) and int(r[2])==shownfile.stat().st_size])!=1 or \
       len([r for r in closed_sizes if r[1]==str(turn) and int(r[2])==closedfile.stat().st_size])!=1:
        fail('Shown/closed popup lifecycle logs do not match exact TechAward snapshot byte sizes')
    return {'technology':tech,'owner':owner,'team':team,'turn':turn,'fixture_cost_minus_one':True,
      'actual_initial_team_technology':0,'actual_next_turn_team_technology':1,'actual_final_team_technology':1,
      'original_sdk_negative_length_message':negatives,'queue_payload':list(queued),'target':control,
      'posted_click':list(pp[0]),'native_consumption':list(ii[0]),'original_ui_consumption':list(uu[0]),
      'shown_snapshot':artifact(shownfile),'closed_snapshot':artifact(closedfile),'timer_held_then_released':True}

def restore_proof(out,res,source_final:bytes,restore_initial:bytes,runtime,files,team:int,technology:int):
    if res.get('status')!='CONTINUOUS_INTERACTIVE_SDK_TREE_DECISION_UI_RESTORE_SMOKE_PASS' or \
       res.get('tech_award_requested') is not False or res.get('tech_award_verified') is not False or \
       res.get('fresh_process_restore_verified') is not True or res.get('semantic_restore_equal') is not True or \
       res.get('checkpoint_input_unchanged') is not True: fail('Restore is not a clean fresh-process existing tree-decision restore')
    for field in ('tech_award_fixtures','tech_award_shown','tech_award_targets','tech_award_closed','tech_award_observations'):
        if res.get(field)!=[]: fail(f'Restore result unexpectedly contains source award evidence: {field}')
    if source_final!=restore_initial: fail('Restore initial SDK state is not byte-identical to source final state')
    queue_rows=rows(out,'INTERACTIVE_UI_QUEUED',r'^INTERACTIVE_UI_QUEUED=(-?\d+)\|(-?\d+)\|(-?\d+)\|(-?\d+)$')
    if rows(out,'INTERACTIVE_TECH_AWARD_SHOWN',r'^INTERACTIVE_TECH_AWARD_SHOWN=.*$') or \
       rows(out,'INTERACTIVE_TECH_AWARD_TARGET',r'^INTERACTIVE_TECH_AWARD_TARGET=.*$') or \
       any(r[0]=='68' for r in queue_rows) or \
       'UI_POPUP_CONTEXT=OFFICIAL_BNW_TECH_AWARD' in out:
        fail('Restore unexpectedly replayed TechAward after the technology was acquired')
    initial=one_file(files,'play-initial-state.txt',runtime); final=one_file(files,'play-final-state.txt',runtime)
    _,ti=state_rows(initial); _,tf=state_rows(final)
    # Compare all initially known technology rows to restore final; their exact save bytes and semantic restore were also checked above.
    if not ti or not tf: fail('Restore snapshots omit team technology rows')
    ini={tuple(r[1:3]):r[3] for r in ti if len(r)==4 and r[0]=='T'}
    fin={tuple(r[1:3]):r[3] for r in tf if len(r)==4 and r[0]=='T'}
    if not ini or any(fin.get(k)!='1' for k,v in ini.items() if v=='1') or \
       ini.get((str(team),str(technology)))!='1' or fin.get((str(team),str(technology)))!='1':
        fail('Restore lost the awarded technology or another technology already acquired at checkpoint')
    return {'award_replayed':False,'source_final_equals_restore_initial':True,'restore_technology_rows_preserved':True}

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source-run',required=True); ap.add_argument('--restore-run',required=True); a=ap.parse_args()
    proof=EVIDENCE/'validators'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_')+uuid.uuid4().hex[:12]); proof.mkdir(parents=True,exist_ok=False)
    try:
        sr=run(a.source_run); rr=run(a.restore_run)
        sroot,sq,sres,sa,so,se,sruntime,sdriver,sprov=sr
        rroot,rq,rres,ra,ro,re,rruntime,rdriver,rprov=rr
        if a.source_run==a.restore_run or len({sres.get('pid'),sres.get('driver_pid'),rres.get('pid'),rres.get('driver_pid')})!=4:
            fail('Source and restore must be four distinct Host and driver processes')
        if sres.get('status')!='CONTINUOUS_INTERACTIVE_SDK_TECH_AWARD_SMOKE_PASS' or \
           sq.get('tech_award') is not True or sres.get('tech_award_requested') is not True or \
           sq.get('input_profile')!='POSTED_HWND_NORMAL_RESEARCH_TECH_AWARD_SMOKE' or \
           sq.get('decisions') is not True or sq.get('research_tree') is not True:
            fail('Source request/result is not the award fixture run')
        if rq.get('tech_award') is not False or rq.get('input_profile')!=save_restore.RESTORE_INPUT_PROFILE or \
           rq.get('decisions') is not True or rq.get('research_tree') is not True or \
           rres.get('decision_ui_sequence_verified') is not True or rres.get('research_tree_sequence_verified') is not True:
            fail('Restore must continue the saved decision/tree run without replaying the award fixture')
        if (rres.get('pid')==sres.get('pid') or rres.get('driver_pid')==sres.get('driver_pid')): fail('Restore reused source process')
        same=save_restore.same_provenance(sq,rq,sruntime,rruntime)
        if sprov.get('gamecore_sha256')!=rprov.get('gamecore_sha256') or sprov.get('host_executable_sha256')!=rprov.get('host_executable_sha256'):
            fail('Source and restore use different Host/Core provenance')
        resume=rq.get('resume_from')
        if type(resume) is not dict or resume.get('run_id')!=a.source_run: fail('Restore request does not bind this source save')
        frozen_result=checked(resume.get('run_result'),rroot/'resume-source-result.json')
        if frozen_result.read_bytes()!=(sroot/'result.json').read_bytes(): fail('Restore froze another source result')
        sfiles=generated(sres,sruntime); rfiles=generated(rres,rruntime)
        sf=one_file(sfiles,'play-final-state.txt',sruntime).read_bytes(); ri=one_file(rfiles,'play-initial-state.txt',rruntime).read_bytes()
        saves=rows(so,'INTERACTIVE_NATIVE_SAVE',r'^INTERACTIVE_NATIVE_SAVE=(\d+)\|(.+)$')
        if not saves or int(saves[-1][0])!=1: fail('Source has no final native save at the newly acquired turn')
        source_save=Path(saves[-1][1]).resolve(strict=True)
        if source_save.name!='play-save-2-turn-1.zssave' or source_save not in [p for group in sfiles.values() for p in group]:
            fail('Source final checkpoint is not its exact generated turn-one SDK save')
        checkpoint_source=checked(resume.get('checkpoint_source'),source_save)
        checkpoint_input=checked(resume.get('checkpoint_input'))
        if checkpoint_input!= (rruntime/'checkpoint-input.zssave').resolve(strict=True) or \
           checkpoint_input.read_bytes()!=source_save.read_bytes() or digest(checkpoint_input)!=resume['checkpoint_input'].get('sha256') or \
           digest(checkpoint_source)!=resume['checkpoint_source'].get('sha256'):
            fail('Restore checkpoint is not an exact immutable copy of the source native save')
        restore_marker=exactly(rows(ro,'INTERACTIVE_RESTORE_CHECKPOINT',r'^INTERACTIVE_RESTORE_CHECKPOINT=(.+)$'),
                               'loaded native restore checkpoint')
        if Path(restore_marker[0]).resolve(strict=True)!=checkpoint_input or \
           rres.get('resume_from_run')!=a.source_run:
            fail('Restore Host did not load the exact copied source checkpoint')
        assets=verify_host_assets(sq,proof/'frozen'); src=award_source(so,sres,sruntime,sdriver,sfiles)
        rst=restore_proof(ro,rres,sf,ri,rruntime,rfiles,src['team'],src['technology'])
        report={'status':'TECH_AWARD_ORIGINAL_UI_AND_FRESH_NATIVE_RESTORE_PASS','source_run':a.source_run,'restore_run':a.restore_run,
          'same_frozen_host_core_runtime':same,'source_host_assets':assets,'source_award':src,'restore':rst,
          'source_restore_four_distinct_processes':True,'retail_renderer_equivalence_verified':False,
          'full_3d_popup_equivalence_verified':False,'human_input_verified':False,'retail_save_compatibility_verified':False,
          'limitations':['This is normal SDK research completion and original retained popup input in the isolated Host.',
            'It does not establish retail 3D rendering, complete UI equivalence, or human-play behavior.']}
        p=proof/'conformance.json'; p.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8'); check_artifacts(report)
        print(json.dumps({'status':report['status'],'proof':artifact(p),'source_run':a.source_run,'restore_run':a.restore_run},ensure_ascii=False))
    except Exception as e:
        (proof/'validation_failure.json').write_text(json.dumps({'status':'TECH_AWARD_VALIDATION_FAILED','source_run':a.source_run,'restore_run':a.restore_run,'error':str(e)},indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
        raise
if __name__=='__main__':
    try: main()
    except Exception as exc: print(f'TECH_AWARD_UI_VERIFY_FAILED: {exc}',file=sys.stderr); raise SystemExit(1) from exc

