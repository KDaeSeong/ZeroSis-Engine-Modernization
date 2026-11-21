"""Verbatim retail resolution callback/timer evidence and pure C++14 checks."""
from __future__ import annotations
import argparse
import gzip
import hashlib
import inspect
import json
import math
from pathlib import Path
import random
import re
import struct
import sys
import xml.etree.ElementTree as ET

sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[1]
sys.path[:0]=[str(PROJECT/'tools'),str(PROJECT/'Tests')]
from menu_replay_restoration import build_cxx14
from native_build import run
from menu_replay_assets import artifact
from menu_suite_storage import storage
from economic_overview_scene import execute_lua
from prepare_ui_popup_assets import lua_value

GAME=Path(r"C:/Program Files (x86)/Steam/steamapps/common/Sid Meier's Civilization V")
LUA=PROJECT/'Source/Assets/UI/Assets/UI/Options/OptionsMenu.lua'
XML=PROJECT/'Source/Assets/UI/Assets/UI/Options/OptionsMenu.xml'
PROVIDER=PROJECT/'Build/SharedLuaRuntime/Lua/ZeroSisLua51_x64.dll'
FUNCTIONS=('SavePreviousResolutionSettings','RestorePreviousResolutionSettings','OnUpdate','ShowResolutionCountdown',
    'OnCountdownYes','OnCountdownNo','OnApplyRes','OnOK','OnCancel','OnBack')


def require(value,why):
    if not value:raise ValueError(why)


def original():
    installed_lua=GAME/'Assets/UI/Options/OptionsMenu.lua';installed_xml=GAME/'Assets/UI/Options/OptionsMenu.xml'
    require(LUA.read_bytes()==installed_lua.read_bytes() and XML.read_bytes()==installed_xml.read_bytes(),
        'Original installed/frozen options sources differ')
    require(artifact(LUA)['sha256']=='76247d52606e8486101e91cad3668b3a4a56257ddbd4df991ef182e9a70c5921',
        'Original options Lua identity changed')
    require(artifact(XML)['sha256']=='a8bd7dbc98544179edfd5c8dba57e6855a4b8fbc5a01a039bcd1579feb7fe7a2',
        'Original options XML identity changed')
    require(artifact(PROVIDER)['sha256']=='4873cded3ddf52366abc7964e3d3e10546f88e983d966be93bce3465ef85d944',
        'Existing pure Lua5.1 provider changed')
    text=LUA.read_text('utf-8-sig');blocks={};proof=[]
    for name in FUNCTIONS:
        matches=list(re.finditer(r'^function '+name+r'\([^\n]*\)\n.*?^end\s*$',text,re.M|re.S))
        require(len(matches)==1,'Original callback extraction is ambiguous: '+name)
        match=matches[0];block=match.group();blocks[name]=block
        proof.append(dict(name=name,first_line=text.count('\n',0,match.start())+1,
            last_line=text.count('\n',0,match.end())+1,bytes=len(block.encode()),
            sha256=hashlib.sha256(block.encode()).hexdigest(),verbatim=True))
    declarations=text[text.index('local fullscreenRes;'):text.index('function SavePreviousResolutionSettings()')]
    timer_declaration=text[text.index('local g_fTimer;'):text.index('function OnUpdate( fDTime )')]
    require('g_fTimer = 20;' in blocks['ShowResolutionCountdown'] and 'g_fTimer = g_fTimer - fDTime;' in blocks['OnUpdate'] and
        'string.format( "%i", g_fTimer + 1 )' in blocks['OnUpdate'],'Original20-second timer policy changed')
    require('OnApplyRes();' in blocks['OnOK'] and 'OnCountdownNo();' in blocks['OnBack'],'Original Apply/Accept/Back routes changed')
    program=declarations+timer_declaration+'\ng_bIsResolutionCountdown = true;\n'+'\n'.join(blocks.values())
    program+='\nreturn function() return g_fTimer end\n'
    tree=ET.parse(XML).getroot();ids=('ApplyResButton','Countdown','CountdownMessage','CountdownTimer','CountYes','CountNo')
    nodes={name:tree.find(".//*[@ID='"+name+"']") for name in ids}
    require(all(node is not None for node in nodes.values()),'Original countdown/apply XML control missing')
    return program,dict(lua=artifact(LUA),xml=artifact(XML),installed_sources=[artifact(installed_lua),artifact(installed_xml)],
        functions=proof,xml_controls={name:dict(node.attrib) for name,node in nodes.items()},
        source_restored_fields=['fullscreen resolution index','window width','window height','AA samples','fullscreen'],
        vsync_is_not_in_source_restore_baseline=True,source_file_persistence_semantics='Not inferred from OptionsManager API names.',
        program_bytes=len(program.encode()),program_sha256=hashlib.sha256(program.encode()).hexdigest())


def timer_cases():
    values=[]
    def add(name,*operations):values.append(dict(name=name,operations=list(operations)))
    start={'kind':'start'}
    def tick(delta):return dict(kind='tick',delta=delta)
    add('source_zero_delta21',start,tick(0),tick(0),{'kind':'yes'},tick(1))
    add('negative_zero_is_nonnegative',start,tick(-0.0),{'kind':'no'},tick(1000))
    thresholds=[0,math.ulp(0.0),sys.float_info.epsilon,math.nextafter(1,0),1,math.nextafter(1,math.inf),
        math.nextafter(19,0),19,19.5,math.nextafter(20,0),20,math.nextafter(20,math.inf),21,1000000,sys.float_info.max]
    for index,delta in enumerate(thresholds):add('threshold_'+str(index),start,tick(delta),tick(0),tick(.25))
    add('exact80quarter_second_updates',start,*[tick(.25) for _ in range(85)])
    add('fractional60hz_owner_updates',start,*[tick(1/60) for _ in range(1205)])
    add('restart_while_active',start,tick(3.5),start,tick(0),tick(19.75),tick(.25),tick(1000))
    add('yes_preserves_raw_clock',start,tick(4.75),{'kind':'yes'},tick(999),start,tick(2),{'kind':'no'},tick(999))
    add('manual_no_then_reopen',start,tick(10),{'kind':'no'},start,tick(15),{'kind':'yes'})
    add('stalled_loop_not_animation_clamped',start,tick(30),tick(30),start,tick(sys.float_info.max),tick(0))
    rng=random.Random(0x434f554e5444)
    for index in range(80):
        operations=[start]
        for step in range(36):
            choice=rng.randrange(15)
            if choice==0:operations.append(start)
            elif choice==1:operations.append({'kind':'yes'})
            elif choice==2:operations.append({'kind':'no'})
            else:operations.append(tick(rng.choice([0,.001,.25,1,3.5,20.5,60]) if step%5==0 else rng.random()*1.75))
        add('mixed_owner_sequence_'+str(index),*operations)
    return values


def flow_cases():
    baseline={'kind':'baseline'};edit={'kind':'edit','value':dict(index=2,width=1920,height=1080,msaa=4,fullscreen=True,vsync=False)}
    def case(name,*operations,graphicsChanged=False):return dict(name=name,operations=list(operations),graphicsChanged=graphicsChanged)
    return [case('separate_apply_no',baseline,edit,{'kind':'apply'},{'kind':'no'}),
        case('separate_apply_timeout',baseline,edit,{'kind':'apply'},{'kind':'tick','delta':20}),
        case('separate_apply_yes_cancel',baseline,edit,{'kind':'apply'},{'kind':'yes'},
            {'kind':'edit','value':dict(width=1600,height=900)},{'kind':'cancel'}),
        case('apply_no_change',baseline,{'kind':'apply'}),
        case('accept_changed_resolution_no',baseline,edit,{'kind':'accept'},{'kind':'no'}),
        case('accept_unchanged',baseline,{'kind':'accept'}),
        case('back_during_preview',baseline,edit,{'kind':'apply'},{'kind':'back'}),
        case('cancel_during_preview',baseline,edit,{'kind':'apply'},{'kind':'cancel'}),
        case('accept_graphics_changed',baseline,{'kind':'accept'},graphicsChanged=True),
        case('confirmed_baseline_then_second_no',baseline,edit,{'kind':'apply'},{'kind':'yes'},
            {'kind':'edit','value':dict(index=3,width=1600,height=900,fullscreen=False)}, {'kind':'apply'},{'kind':'no'})]


HARNESS=r'''
local program=@@PROGRAM@@
local timerCases=@@TIMER_CASES@@
local flowCases=@@FLOW_CASES@@
local function json(value)
 local kind=type(value)
 if kind=='nil' then return 'null' end
 if kind=='boolean' then return tostring(value) end
 if kind=='number' then assert(value==value and value~=math.huge and value~=-math.huge);return string.format('%.17g',value) end
 if kind=='string' then return '"'..value:gsub('\\','\\\\'):gsub('"','\\"'):gsub('\n','\\n'):gsub('\r','\\r')..'"' end
 assert(kind=='table')
 local result={}
 if #value>0 or next(value)==nil then
  for _,entry in ipairs(value) do result[#result+1]=json(entry) end
  return '['..table.concat(result,',')..']'
 end
 for key,entry in pairs(value) do result[#result+1]=json(key)..':'..json(entry) end
 return '{'..table.concat(result,',')..'}'
end
local function copy(value) local result={} for key,entry in pairs(value) do result[key]=entry end return result end
local function evaluate(case,keepTrace)
 local state={active=false,hidden=true,graphicsHidden=true,windowOpen=true,display=20,elapsed=0,yes=0,no=0,starts=0,
  clearCalls=0,commits=0,saves=0,restores=0,trace={}}
 local cached={index=0,width=1280,height=720,msaa=0,fullscreen=false,vsync=true}
 local committed=copy(cached)
 local function record(name) if keepTrace then state.trace[#state.trace+1]=name end end
 local resolutionKeys={'index','width','height','msaa','fullscreen'}
 local options={GetResolution_Cached=function() return cached.index end,
  GetWindowResolution_Cached=function() return cached.width,cached.height end,
  GetAASamples_Cached=function() return cached.msaa end,GetFullscreen_Cached=function() return cached.fullscreen end,
  SetResolution_Cached=function(value) cached.index=value end,
  SetWindowResolution_Cached=function(width,height) cached.width=width;cached.height=height end,
  SetAASamples_Cached=function(value) cached.msaa=value end,SetFullscreen_Cached=function(value) cached.fullscreen=value end,
  HasUserChangedResolution=function() for _,key in ipairs(resolutionKeys) do if cached[key]~=committed[key] then return true end end return false end,
  CommitResolutionOptions=function() for _,key in ipairs(resolutionKeys) do committed[key]=cached[key] end state.commits=state.commits+1;record('CommitResolutionOptions') end,
  SyncResolutionOptionsCache=function() for _,key in ipairs(resolutionKeys) do cached[key]=committed[key] end record('SyncResolutionOptionsCache') end,
  CommitGameOptions=function() record('CommitGameOptions') end,CommitGraphicsOptions=function() record('CommitGraphicsOptions') end,
  SyncGameOptionsCache=function() record('SyncGameOptionsCache') end,SyncGraphicsOptionsCache=function() record('SyncGraphicsOptionsCache') end,
  HasUserChangedGraphicsOptions=function() return not not case.graphicsChanged end}
 local context={SetUpdate=function(_,fn) state.updater=fn;state.active=true;record('SetUpdate') end,
  ClearUpdate=function() state.updater=nil;state.active=false;state.clearCalls=state.clearCalls+1;record('ClearUpdate') end,
  GetID=function() return 'OptionsMenu_FrontEnd' end}
 local function label() return {SetText=function() end} end
 local controls={Countdown={SetHide=function(_,hidden) state.hidden=hidden;record(hidden and 'CountdownHide' or 'CountdownShow') end,
   IsHidden=function() return state.hidden end},
  CountdownTimer={SetText=function(_,value) state.display=assert(tonumber(value)) end},
  CountdownMessage=label(),CountYes=label(),CountNo=label(),
  LabelStack={CalculateSize=function() end,ReprocessAnchoring=function() end},
  GraphicsChangedPopup={SetHide=function(_,hidden) state.graphicsHidden=hidden;record(hidden and 'GraphicsPopupHide' or 'GraphicsPopupShow') end,
   IsHidden=function() return state.graphicsHidden end}}
 local env={OptionsManager=options,ContextPtr=context,Controls=controls,
  Locale={ConvertTextKey=function(value) return value end},string=string,table=table,
  UIManager={DequeuePopup=function() state.windowOpen=false;record('DequeuePopup') end},
  UpdateGraphicsOptionsDisplay=function() record('UpdateGraphicsOptionsDisplay') end,
  SaveAudioOptions=function() record('SaveAudioOptions') end,CacheAudioVolumes=function() record('CacheAudioVolumes') end,
  RevertToCachedAudioVolumes=function() record('RevertToCachedAudioVolumes') end}
 local chunk=assert(loadstring(program,'@original-OptionsMenu-resolution-callbacks.lua'));setfenv(chunk,env)
 local remaining=chunk()
 for _,name in ipairs({'SavePreviousResolutionSettings','RestorePreviousResolutionSettings','ShowResolutionCountdown',
  'OnCountdownYes','OnCountdownNo','OnApplyRes','OnOK','OnCancel','OnBack','OnUpdate'}) do
  local original=assert(env[name]);local captured=name
  env[name]=function(...)
   record(captured)
   if captured=='ShowResolutionCountdown' then state.elapsed=0;state.starts=state.starts+1 end
   if captured=='OnUpdate' then state.elapsed=state.elapsed+(...) end
   if captured=='OnCountdownYes' then state.yes=state.yes+1 end
   if captured=='OnCountdownNo' then state.no=state.no+1 end
   if captured=='SavePreviousResolutionSettings' then state.saves=state.saves+1 end
   if captured=='RestorePreviousResolutionSettings' then state.restores=state.restores+1 end
   return original(...)
  end
 end
 -- Set a real source restore baseline for timer-only manual Yes/No paths.
 if not keepTrace then env.SavePreviousResolutionSettings() end
 local rows={}
 for _,operation in ipairs(case.operations) do
  local kind=operation.kind
  if kind=='start' then env.ShowResolutionCountdown()
  elseif kind=='tick' then if state.updater then state.updater(operation.delta) end
  elseif kind=='yes' then env.OnCountdownYes()
  elseif kind=='no' then env.OnCountdownNo()
  elseif kind=='baseline' then env.SavePreviousResolutionSettings()
  elseif kind=='edit' then for key,value in pairs(operation.value) do cached[key]=value end
  elseif kind=='apply' then env.OnApplyRes()
  elseif kind=='accept' then env.OnOK()
  elseif kind=='cancel' then env.OnCancel()
  elseif kind=='back' then env.OnBack()
  else error('Unknown fixture operation') end
  if not keepTrace then rows[#rows+1]={active=state.active,remaining=remaining(),elapsed=state.elapsed,
   display=state.display,yes=state.yes,no=state.no,starts=state.starts} end
 end
 return {rows=rows,trace=state.trace,active=state.active,remaining=remaining(),display=state.display,
  countdownHidden=state.hidden,windowOpen=state.windowOpen,yes=state.yes,no=state.no,starts=state.starts,
  clearCalls=state.clearCalls,resolutionCommits=state.commits,baselineSaves=state.saves,baselineRestores=state.restores,
  cached=cached,committed=committed}
end
local timers,flows={},{ }
for _,case in ipairs(timerCases) do timers[#timers+1]=evaluate(case,false) end
for _,case in ipairs(flowCases) do flows[#flows+1]=evaluate(case,true) end
return json({timers=timers,flows=flows})
'''


def source_oracle(program,timers,flows):
    script=HARNESS.replace('@@PROGRAM@@',lua_value(program)).replace('@@TIMER_CASES@@',lua_value(timers)).replace('@@FLOW_CASES@@',lua_value(flows))
    result=execute_lua(script);require(len(result['timers'])==len(timers) and len(result['flows'])==len(flows),'Original callback case count differs')
    by_name={case['name']:value for case,value in zip(flows,result['flows'])}
    rejected=by_name['separate_apply_no'];require(rejected['windowOpen'] and rejected['countdownHidden'] and rejected['cached']['width']==1280 and
        rejected['cached']['vsync'] is False and rejected['resolutionCommits']==2,'Source No did not restore only resolution baseline fields')
    accepted=by_name['separate_apply_yes_cancel'];require(not accepted['windowOpen'] and accepted['cached']['width']==1920 and accepted['resolutionCommits']==1 and
        accepted['baselineSaves']==2,'Source Yes baseline did not survive later Cancel')
    for name in ('separate_apply_timeout','back_during_preview','cancel_during_preview'):
        require(by_name[name]['windowOpen'] and by_name[name]['countdownHidden'] and by_name[name]['cached']['width']==1280,
            'Source reject path did not retain the options window: '+name)
    require(by_name['separate_apply_timeout']['no']==1 and by_name['separate_apply_timeout']['clearCalls']==2,'Original timeout No/ClearUpdate call sequence differs')
    trace=by_name['accept_changed_resolution_no']['trace'];positions=[trace.index(name) for name in
        ('CommitGameOptions','CommitGraphicsOptions','SaveAudioOptions','CacheAudioVolumes','OnApplyRes','ShowResolutionCountdown','CommitResolutionOptions')]
    require(positions==sorted(positions),'Original Accept commit-before-preview ordering differs')
    require(not by_name['accept_unchanged']['windowOpen'] and not by_name['apply_no_change']['active'],'Unchanged source Apply/Accept route differs')
    require(by_name['confirmed_baseline_then_second_no']['cached']['width']==1920,'Second reject restored pre-confirmation rather than latest confirmed source baseline')
    require(result['timers'][0]['rows'][1]['display']==21,'Original zero-delta21 label was not exercised')
    return result


def fixture_bytes(path,cases,expected):
    data=bytearray(b'ZSCNTD01'+struct.pack('<I',len(cases)));codes={'start':0,'tick':1,'yes':2,'no':3}
    for case,golden in zip(cases,expected):
        raw=case['name'].encode('ascii');data.extend(struct.pack('<I',len(raw)));data.extend(raw)
        require(len(case['operations'])==len(golden['rows']),'Original timer step count differs');data.extend(struct.pack('<I',len(case['operations'])))
        for operation,row in zip(case['operations'],golden['rows']):
            data.extend(struct.pack('<IdIddiIII',codes[operation['kind']],operation.get('delta',0),int(row['active']),row['remaining'],row['elapsed'],
                row['display'],row['yes'],row['no'],row['starts']))
    path.write_bytes(data)


def main():
    cli=argparse.ArgumentParser(description=__doc__);cli.add_argument('--attempt',default='attempt01');args=cli.parse_args()
    if re.fullmatch('[a-z0-9_]{1,40}',args.attempt) is None:cli.error('Use an exact owned attempt label')
    stage=PROJECT/'evidence/game_menu/options_video_preview/countdown'/args.attempt;build=PROJECT/'Build/MenuResolutionCountdown'/args.attempt
    stage.mkdir(parents=True,exist_ok=True);build.mkdir(parents=True,exist_ok=True);receipt=stage/'result.json'
    require(not receipt.exists(),'Preserve completed evidence and choose a new explicit attempt')
    sources=[PROJECT/'Source/Host/MenuResolutionCountdown.h',PROJECT/'Tests/menu_resolution_countdown.cpp',Path(__file__),LUA,XML,
        GAME/'Assets/UI/Options/OptionsMenu.lua',GAME/'Assets/UI/Options/OptionsMenu.xml',PROVIDER,
        PROJECT/'Tests/economic_overview_scene.py',PROJECT/'tools/prepare_ui_popup_assets.py',PROJECT/'tools/native_build.py']
    before=[artifact(path) for path in sources]
    require(not any(any(value>127 for value in path.read_bytes()) for path in sources[:2]),'C++14/windows1252 component source must be ASCII')
    report=dict(schema='zerosis.options_video_preview.countdown.v1',attempt=args.attempt,inputs_before=before,
        compile_recipe_sha256=hashlib.sha256(inspect.getsource(build_cxx14).encode()).hexdigest(),
        native_execution=False,sdk_loaded=False,host_or_sdk_or_window_executed=False,gpu_execution=False,audio_executed=False,
        actual_controlled_lua51=True,owned_intermediate_cleanup=[],settings_schema_or_keys_changed=False,
        scope=['Verbatim front-end callback bodies execute against declared OptionsManager/control/context record stubs.',
            'Pure C++ timer compares Start/OnUpdate/Yes/No state and the one-shot expiry-to-owner-No edge.',
            'OptionsManager commit/cache call ordering is observed; real engine side effects and file persistence semantics are not inferred.',
            'Production helper contains no display apply, settings values, persistence, SDK, window or audio access.',
            'Original UI/data/layout and full controller/session preview acceptance are separate Root integration checks.'])
    cleanup=['countdown_goldens.bin','MenuResolutionCountdown.obj','MenuResolutionCountdown.map','compile.rsp','read_build_environment.cmd']
    try:
        program,report['original_source']=original();timers=timer_cases();flows=flow_cases();goldens=source_oracle(program,timers,flows)
        report['original_lua']=dict(timer_cases=len(timers),timer_steps=sum(len(case['operations']) for case in timers),
            callback_flow_cases=len(flows),verbatim_function_count=len(FUNCTIONS),zero_delta_displays21=True,
            direct_apply_and_accept_routes_executed=True,yes_updates_source_restore_baseline=True,no_timeout_keeps_options_open=True,
            cancel_after_yes_keeps_confirmed_resolution=True,unrelated_vsync_cache_not_restored_by_no=True,
            timeout_no_calls_once_and_clear_update_calls_twice=True,original_multiplayer_branch_executed=False)
        evidence=stage/'original_lua_goldens.json.gz'
        value=dict(schema='zerosis.options_video_preview.countdown.original_lua_goldens.v1',source=report['original_source'],
            timer_cases=[dict(case,expected=expected) for case,expected in zip(timers,goldens['timers'])],
            callback_flow_cases=[dict(case,expected=expected) for case,expected in zip(flows,goldens['flows'])])
        with evidence.open('xb') as stream:stream.write(gzip.compress((json.dumps(value,indent=2,allow_nan=False)+'\n').encode(),mtime=0))
        report['compressed_original_goldens']=artifact(evidence)
        fixture=build/'countdown_goldens.bin';fixture_bytes(fixture,timers,goldens['timers']);report['temporary_golden_fixture']=artifact(fixture)
        compiled=build_cxx14('MenuResolutionCountdown',build,stage,PROJECT/'Tests/menu_resolution_countdown.cpp',[PROJECT/'Source/Host']);report['build']=compiled
        imports=run([Path(compiled['compiler']).with_name('dumpbin.exe'),'/dependents',compiled['path']],cwd=build,timeout=30)
        names=sorted(set(re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$',imports.stdout.decode('mbcs',errors='replace'),re.M)))
        require(not imports.returncode and {name.lower() for name in names}=={'kernel32.dll'},'Pure countdown imported an unexpected native provider')
        report['component_imported_dlls']=names
        checked=run([compiled['path'],fixture],cwd=build,timeout=30)
        require(not checked.returncode,'Original countdown mismatch: '+(checked.stdout+checked.stderr).decode('utf8',errors='replace'))
        report['component']=json.loads(checked.stdout)
        require(report['component']['original_lua_cases']==len(timers) and report['component']['original_lua_steps']==report['original_lua']['timer_steps'],
            'C++ countdown did not consume every original Lua state')
        report['inputs_after']=[artifact(path) for path in sources];require(report['inputs_after']==before,'Timer/original source changed during controlled check')
        report.update(status='PASS_ORIGINAL_RESOLUTION_CALLBACKS_LUA51_AND_PURE_COUNTDOWN_CXX14',compiler_and_linker_warnings=0)
    except Exception as error:
        report.update(status='FAIL_ORIGINAL_RESOLUTION_COUNTDOWN_COMPONENT',error=str(error));raise
    finally:
        for leaf in cleanup:
            path=build/leaf
            if not path.exists():continue
            info=storage.ordinary(path);require(path.absolute().parent==build.absolute() and info.st_nlink==1,'Unsafe exact countdown intermediate cleanup')
            row=dict(artifact(path),file_identity=[info.st_dev,info.st_ino],allocated_bytes=storage.allocated(path))
            require(storage.metadata(info)==storage.metadata(storage.ordinary(path)),'Countdown cleanup identity changed')
            path.unlink();row['result']='DELETED_EXACT_OWNED_REGENERABLE_COUNTDOWN_INTERMEDIATE';report['owned_intermediate_cleanup'].append(row)
        report['owned_intermediate_bytes_removed']=sum(row['bytes'] for row in report['owned_intermediate_cleanup'])
        report['owned_intermediate_allocated_bytes_removed']=sum(row['allocated_bytes'] for row in report['owned_intermediate_cleanup'])
        with receipt.open('x',encoding='utf8',newline='\n') as stream:json.dump(report,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(status=report['status'],cases=report['component']['original_lua_cases'],steps=report['component']['original_lua_steps'],
        checks=report['component']['checks'],report=str(receipt),removed_intermediates=len(report['owned_intermediate_cleanup']))))


if __name__=='__main__':raise SystemExit(main())
