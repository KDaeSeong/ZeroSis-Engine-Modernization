"""Original stack/callback and actual V3 reward options view without a window."""
from __future__ import annotations
import argparse
import gzip
import hashlib
import inspect
import json
from pathlib import Path
import re
import sqlite3
import struct
import sys
import xml.etree.ElementTree as ET

sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[1]
sys.path[:0]=[str(PROJECT/'tools'),str(PROJECT/'Tests')]
from menu_replay_restoration import build_cxx14
from native_build import run
from menu_replay_legend_assets import artifact
from menu_suite_storage import storage
from menu_frontend_skin import FrontEndSkin
from economic_overview_scene import execute_lua
from prepare_ui_popup_assets import lua_value
from menu_resolution_preview_view import read_bank
from menu_frontend_cpu import render

ASSETS=PROJECT/'Source/Assets/UIFrontEndV4'
MANIFEST=PROJECT/'evidence/game_menu/native_offline_followup/frontend_v4/assets_v4.json'
# Same localization.db bytes and skin rows as the retired 1fba runtime; shared with the resolution preview view.
RUNTIME=PROJECT/'Build/InteractiveGameRuntime/20261105T123201Z_9a1a8fa8c1a2'
ORIGINAL=PROJECT/'Source/Assets/UI/Assets/UI/Options/OptionsMenu.xml'
LUA=PROJECT/'Source/Assets/UI/Assets/UI/Options/OptionsMenu.lua'
SCENE=PROJECT/'Source/Host/UiScene.lua'
PROVIDER=PROJECT/'Build/SharedLuaRuntime/Lua/ZeroSisLua51_x64.dll'
REWARD='NoRewardPopupsCheckbox'
BASIC='NoBasicHelpCheckbox'
LABEL='TXT_KEY_OPSCREEN_NO_REWARD_POPUPS'
TOOLTIP=LABEL+'_TT'


def require(value,why):
    if not value:raise ValueError(why)


def source_inputs():
    skin=FrontEndSkin(backend_manifest=RUNTIME/'bundle.manifest');selected=skin.resolve('UI/Options/OptionsMenu.xml')
    require(selected['source']['sha256']==artifact(ORIGINAL)['sha256']=='a8bd7dbc98544179edfd5c8dba57e6855a4b8fbc5a01a039bcd1579feb7fe7a2',
        'Snapshot is not the selected original options XML')
    selected_lua=skin.resolve('UI/Options/OptionsMenu.lua')
    require(selected_lua['source']['sha256']==artifact(LUA)['sha256']=='76247d52606e8486101e91cad3668b3a4a56257ddbd4df991ef182e9a70c5921',
        'Snapshot is not the selected original options Lua')
    styles=skin.selected_style_elements();style=styles['Button_16'];style_ref=skin._style_records['Button_16']
    require(style.get('Size')=='32,32' and style.get('Texture')=='Assets/UI/Art/Controls/Checkbox.dds','Selected checkbox candidate style changed')
    root=ET.parse(ORIGINAL).getroot();frame=root.find('Grid');panel=root.find(".//*[@ID='GamePanel']")
    require(frame is not None and panel is not None,'Original options frame/game panel missing')
    stack=next(node for node in panel.findall('Stack') if node.find("*[@ID='"+REWARD+"']") is not None)
    reward=stack.find("*[@ID='"+REWARD+"']");basic=stack.find("*[@ID='"+BASIC+"']")
    require(reward is not None and basic is not None and stack.get('Anchor')=='L,C' and stack.get('Offset')=='380,0' and stack.get('Padding')=='15',
        'Original reward/basic stack changed')
    require(reward.get('String')==LABEL and reward.get('ToolTip')==TOOLTIP and reward.get('LeadingOffset')=='-10' and
        reward.get('WrapWidth')=='350' and reward.get('Size') is None and reward.get('Style') is None,'Original reward checkbox declaration changed')
    ordered=[dict(node.attrib) for node in stack if node.tag=='CheckBox']
    require([row['ID'] for row in ordered].index(REWARD)<[row['ID'] for row in ordered].index(BASIC),'Original reward/basic order changed')
    text=SCENE.read_text('utf8');a=text.index('function methods:CalculateSize()');b=text.index('function methods:DoAutoSize()',a)
    calculate=text[a:b];a=text.index('anchor=function(handle)');b=text.index('function methods:ReprocessAnchoring()',a);anchor=text[a:b]
    original=LUA.read_text('utf-8-sig');callback=re.search(r'^function OnNoRewardPopupsCheckbox\([^\n]*\)\n.*?^end\s*$',original,re.M|re.S).group()
    registration=next(line for line in original.splitlines() if line.startswith('Controls.NoRewardPopupsCheckbox:RegisterCheckHandler'))
    cached_read=next(line.strip() for line in original.splitlines() if 'Controls.NoRewardPopupsCheckbox:SetCheck' in line)
    inputs=dict(frame=dict(frame.attrib),panel=dict(panel.attrib),stack=dict(stack.attrib),children=ordered)
    proof=dict(selected_xml=selected,selected_lua=selected_lua,checkbox_style=style_ref,
        original_context=dict(root.attrib),frame=inputs['frame'],game_panel=inputs['panel'],stack=inputs['stack'],children=ordered,
        checkbox_candidate=dict(width=32,height=32,source_style='Button_16',native_default_binding_verified=False,retail_widget_geometry_verified=False),
        original_callback=dict(source=callback,sha256=hashlib.sha256(callback.encode()).hexdigest(),registration=registration,cached_read=cached_read),
        retained_stack_function=dict(source=artifact(SCENE),bytes=len(calculate.encode()),sha256=hashlib.sha256(calculate.encode()).hexdigest(),verbatim=True),
        retained_anchor_function=dict(source=artifact(SCENE),bytes=len(anchor.encode()),sha256=hashlib.sha256(anchor.encode()).hexdigest(),verbatim=True),
        native_keyboard_order='Not authored explicitly; new supported order follows original XML sibling order through the owned model.',
        default_source='Legacy actual Host getter returnedfalse; migration_plan.json explicitly preserves that behavior. Retail factory default is not inferred from the commented Lua false line.')
    refs={selected['source']['path']:selected['source'],selected_lua['source']['path']:selected_lua['source'],style_ref['source']['path']:style_ref['source']}
    return inputs,calculate,anchor,callback,registration,cached_read,proof,[Path(path) for path in refs]


STACK_HARNESS=r'''
local input=@@INPUT@@
local methods={}
local viewport={w=1920,h=1080}
local hasRetainedPopupUi=true
local popupKind='MenuOptions'
local function state(handle) return handle end
local function finite(value) assert(type(value)=='number' and value==value and value~=math.huge and value~=-math.huge);return value end
local function pair(raw)
 local x,y=raw:match('^([^,]+),([^,]+)$');return assert(tonumber(x)),assert(tonumber(y))
end
local anchor
@@CALCULATE@@
@@ANCHOR@@
local output={}
for mask=0,3 do
 local function make(kind,attributes,parent,w,h)
  local ox,oy=pair(attributes.Offset or '0,0')
  local value={kind=kind,attributes=attributes,parent=parent,children={},w=w,h=h,x=0,y=0,
   offsetX=ox,offsetY=oy,explicitSize=attributes.Size~=nil,hidden=false}
  if parent then parent.children[#parent.children+1]=value end
  return value
 end
 local fw,fh=pair(input.frame.Size);local frame=make('Grid',input.frame,nil,fw,fh)
 local pw,ph=pair(input.panel.Size);local panel=make('Container',input.panel,frame,pw,ph)
 local attrs={} for key,value in pairs(input.stack) do attrs[key]=value end
 -- The retained original menu contract supplies Bottom when StackGrowth is
 -- omitted. This is not a claim about an unexecuted retail native default.
 attrs.StackGrowth=attrs.StackGrowth or 'Bottom'
 local stack=make('Stack',attrs,panel,0,0);local rows={}
 for _,attributes in ipairs(input.children) do
  local row=make('CheckBox',attributes,stack,32,32);rows[attributes.ID]=row
  row.hidden=not ((attributes.ID=='NoRewardPopupsCheckbox' and mask%2==1) or
    (attributes.ID=='NoBasicHelpCheckbox' and math.floor(mask/2)==1))
 end
 methods.CalculateSize(stack);anchor(frame)
 local function rect(row) return string.format('[%.17g,%.17g,%.17g,%.17g]',row.x,row.y,row.w,row.h) end
 output[#output+1]='{"mask":'..mask..',"stack":'..rect(stack)..',"reward":'..rect(rows.NoRewardPopupsCheckbox)..',"basic":'..rect(rows.NoBasicHelpCheckbox)..'}'
end
return '{"cases":['..table.concat(output,',')..']}'
'''


def oracle(data,calculate,anchor,callback,registration,cached_read):
    script=STACK_HARNESS.replace('@@INPUT@@',lua_value(data)).replace('@@CALCULATE@@',calculate).replace('@@ANCHOR@@',anchor)
    result=execute_lua(script)
    require(len(result['cases'])==4,'Retained Lua capability layout matrix differs')
    callbacks=execute_lua(r'''
local cached=false;local handler;local shown
local env={OptionsManager={SetNoRewardPopups_Cached=function(value) assert(type(value)=='boolean');cached=value end,
 IsNoRewardPopups_Cached=function() return cached end},Controls={NoRewardPopupsCheckbox={
 RegisterCheckHandler=function(_,value) assert(type(value)=='function');handler=value end,
 SetCheck=function(_,value) shown=value end}}}
local chunk=assert(loadstring(@@CALLBACK@@..'\n'..@@REGISTRATION@@,'@original-NoRewardPopupsCheckbox.lua'));setfenv(chunk,env);chunk()
local read=assert(loadstring(@@READ@@,'@original-NoRewardPopups-cached-display.lua'));setfenv(read,env)
read();assert(shown==false);handler(true);read();assert(shown==true and cached==true)
handler(false);read();assert(shown==false and cached==false)
return '{"registered_original_callback":true,"exact_cached_display_line":true,"false_true_false":true,"backend_or_persistence_called":false}'
'''.replace('@@CALLBACK@@',lua_value(callback)).replace('@@REGISTRATION@@',lua_value(registration)).replace('@@READ@@',lua_value(cached_read)))
    result['original_callback']=callbacks;return result


def metadata(path,manifest,goldens):
    fonts,textures,styles=read_bank()
    require(styles['Button_16']['width']==styles['Button_16']['height']==32 and styles['Button_16']['step']==(0,32),
        'Immutable V3 checkbox descriptor differs')
    keys={row['text'] for row in manifest['options_control_layout'] if row['text']}
    keys.update([LABEL,TOOLTIP,'TXT_KEY_MULTIPLAYER_OPTIONS','TXT_KEY_OPSCREEN_RESOLUTION','TXT_KEY_OPSCREEN_APPLY_RESOLUTION',
        'TXT_KEY_OPSCREEN_RESOLUTION_TIMER','TXT_KEY_YES_BUTTON','TXT_KEY_NO_BUTTON'])
    db=sqlite3.connect((RUNTIME/'localization.db').as_uri()+'?mode=ro&immutable=1',uri=True)
    try: labels=dict(db.execute('SELECT Tag,Text FROM Language_ko_KR WHERE Tag IN ('+','.join('?' for _ in keys)+')',sorted(keys)))
    finally: db.close()
    require(set(labels)==keys and all(value and not value.startswith('TXT_KEY_') for value in labels.values()),'Actual original localization key missing')
    coverage=[]
    for size in (18,20,22):
        glyphs=fonts[(size,'Shadow')]['glyphs'];missing=sorted({ord(ch) for key in (LABEL,TOOLTIP) for ch in labels[key] if ch not in '\r\n\t'}-glyphs.keys())
        require(not missing,'Existing V3 reward label/tooltip glyph is missing')
        coverage.append(dict(size=size,style='Shadow',label_characters=len(labels[LABEL]),tooltip_characters=len(labels[TOOLTIP]),missing_scalars=missing))
    data=bytearray(b'ZSRWDO01'+struct.pack('<I',len(labels)))
    def text(value):
        raw=value.encode('utf8');data.extend(struct.pack('<I',len(raw)));data.extend(raw)
    for key,value in sorted(labels.items()):text(key);text(value)
    data.extend(struct.pack('<I',len(goldens['cases'])))
    for case in goldens['cases']:
        data.extend(struct.pack('<I',case['mask']))
        for key in ('stack','reward','basic'):data.extend(struct.pack('<4f',*case[key]))
    path.write_bytes(data)
    return dict(actual_localization_database=artifact(RUNTIME/'localization.db'),label=labels[LABEL],tooltip=labels[TOOLTIP],coverage=coverage,
        tooltip_scope='Original source key/text and existing glyph coverage are verified; no new generic native tooltip service is invented.',
        packet_style=dict(styles['Button_16']),original_named_texture=dict(zip(('index','width','height'),textures['checkbox.dds'])))


def main():
    cli=argparse.ArgumentParser(description=__doc__);cli.add_argument('--attempt',default='attempt01');args=cli.parse_args()
    if re.fullmatch('[a-z0-9_]{1,40}',args.attempt) is None:cli.error('Use one exact owned attempt label')
    stage=PROJECT/'evidence/game_menu/options_reward_popups/view'/args.attempt;build=PROJECT/'Build/MenuRewardOptionsView'/args.attempt
    stage.mkdir(parents=True,exist_ok=True);build.mkdir(parents=True,exist_ok=True);receipt=stage/'result.json'
    require(not receipt.exists(),'Preserve completed reward view evidence and choose a new explicit attempt')
    raw_manifest=MANIFEST.read_bytes();require(hashlib.sha256(raw_manifest).hexdigest()=='dbd8c092a3ef9ca86498ef48bcdeb71b4151a97b011f1230ba35d09340fcaea7',
        'Immutable V3 asset manifest changed');manifest=json.loads(raw_manifest)
    source,calculate,anchor,callback,registration,cached_read,proof,original_refs=source_inputs()
    sources=[PROJECT/'Source/Host/MenuRewardOptionsLayout.h',PROJECT/'Source/Host/MenuFrontEndOptionsView.h',
        PROJECT/'Source/Host/MenuFrontEndOptionsModel.h',PROJECT/'Source/Host/MenuOptionsContract.h',PROJECT/'Source/Host/MenuFrontEndAssets.h',
        PROJECT/'Source/Host/MenuResolutionPreviewLayout.h',PROJECT/'Source/Host/MenuResolutionCountdown.h',
        PROJECT/'Tests/menu_reward_options_view.cpp',Path(__file__),PROJECT/'Tests/menu_frontend_scene_fixture.h',ORIGINAL,LUA,SCENE,PROVIDER,
        PROJECT/'tools/menu_frontend_cpu.py',PROJECT/'tools/menu_frontend_skin.py',PROJECT/'Tests/economic_overview_scene.py',
        PROJECT/'evidence/game_menu/options_reward_popups/requirements.json',PROJECT/'evidence/game_menu/options_reward_popups/migration_plan.json',
        RUNTIME/'localization.db',*original_refs]
    sources=list(dict.fromkeys(sources));before=[artifact(path) for path in sources]
    protected=[artifact(MANIFEST)]+[artifact(Path(row['path'])) for row in manifest['files']]
    require(len(protected)==155,'Immutable V3 physical file count differs')
    require(not any(any(value>127 for value in path.read_bytes()) for path in sources[:8] if path.suffix in ('.h','.cpp')),
        'C++14/windows1252 reward source must be ASCII')
    report=dict(schema='zerosis.options_reward_popups.view.v1',attempt=args.attempt,inputs_before=before,immutable_v3_before=protected,
        original_source=proof,compile_recipe_sha256=hashlib.sha256(inspect.getsource(build_cxx14).encode()).hexdigest(),
        native_execution=False,sdk_loaded=False,host_or_sdk_or_window_executed=False,gpu_execution=False,audio_executed=False,
        actual_controlled_lua51=True,owned_intermediate_cleanup=[],source_default_binding_and_native_geometry_verified=False,
        scope=['Exact original reward callback/registration/cached display line and retained UiScene stack/anchor function bodies execute with record-only handles.',
            'View uses existing V3 NoBasicHelp baseline and Button_16/font assets; no new asset control is looked up or asset bank modified.',
            'Pure actual controller/view exercises capability masks, original order, pending edits/cancel and existing display modal isolation.',
            'One standard-library CPU diagnostic PNG is not native sampler/AA/widget geometry acceptance.'])
    cleanup=['reward_metadata.bin','reward_game.packet','MenuRewardOptionsView.obj','MenuRewardOptionsView.map','compile.rsp','read_build_environment.cmd']
    try:
        goldens=oracle(source,calculate,anchor,callback,registration,cached_read)
        evidence=stage/'original_stack_callback_goldens.json.gz'
        with evidence.open('xb') as stream:stream.write(gzip.compress((json.dumps(dict(schema='zerosis.reward_options.source_goldens.v1',source=proof,oracle=goldens),indent=2)+'\n').encode(),mtime=0))
        report['source_oracle']=artifact(evidence)
        binary=build/'reward_metadata.bin';report['labels_and_font_coverage']=metadata(binary,manifest,goldens);report['temporary_metadata']=artifact(binary)
        compiled=build_cxx14('MenuRewardOptionsView',build,stage,PROJECT/'Tests/menu_reward_options_view.cpp',[PROJECT/'Source/Host',PROJECT/'Tests']);report['build']=compiled
        imports=run([Path(compiled['compiler']).with_name('dumpbin.exe'),'/dependents',compiled['path']],cwd=build,timeout=30)
        names=sorted(set(re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$',imports.stdout.decode('mbcs',errors='replace'),re.M)))
        require(not imports.returncode and {name.lower() for name in names}=={'kernel32.dll'},'Actual reward console imports an unexpected native provider')
        report['component_imported_dlls']=names
        packet=build/'reward_game.packet';checked=run([compiled['path'],ASSETS,binary,packet],cwd=build,timeout=30)
        require(not checked.returncode,'Actual reward view mismatch: '+(checked.stdout+checked.stderr).decode('utf8',errors='replace'));report['component']=json.loads(checked.stdout)
        png=stage/'cpu_reward_game.png';report['cpu_diagnostic']=render(packet,png,ASSETS);report['cpu_image']=artifact(png)
        report['inputs_after']=[artifact(path) for path in sources];require(report['inputs_after']==before,'Shared source changed during reward view fixture')
        after=[artifact(Path(row['path'])) for row in protected];require(after==protected,'Immutable V3 asset/manifest changed')
        report.update(status='PASS_ORIGINAL_REWARD_CALLBACK_STACK_AND_ACTUAL_V3_MODEL_VIEW_CXX14',compiler_and_linker_warnings=0,immutable_v3_preserved=True)
    except Exception as error:
        report.update(status='FAIL_ORIGINAL_REWARD_OPTIONS_VIEW',error=str(error));raise
    finally:
        for leaf in cleanup:
            path=build/leaf
            if not path.exists():continue
            info=storage.ordinary(path);require(path.absolute().parent==build.absolute() and info.st_nlink==1,'Unsafe exact reward view cleanup')
            row=dict(artifact(path),file_identity=[info.st_dev,info.st_ino],allocated_bytes=storage.allocated(path))
            require(storage.metadata(info)==storage.metadata(storage.ordinary(path)),'Reward view cleanup identity changed')
            path.unlink();row['result']='DELETED_EXACT_OWNED_REGENERABLE_REWARD_VIEW_INTERMEDIATE';report['owned_intermediate_cleanup'].append(row)
        report['owned_intermediate_bytes_removed']=sum(row['bytes'] for row in report['owned_intermediate_cleanup'])
        report['owned_intermediate_allocated_bytes_removed']=sum(row['allocated_bytes'] for row in report['owned_intermediate_cleanup'])
        with receipt.open('x',encoding='utf8',newline='\n') as stream:json.dump(report,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(status=report['status'],checks=report['component']['checks'],report=str(receipt),removed_intermediates=len(report['owned_intermediate_cleanup']))))


if __name__=='__main__':raise SystemExit(main())
