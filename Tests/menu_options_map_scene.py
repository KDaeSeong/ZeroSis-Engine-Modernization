"""Execute installed SaveMapMenu Lua with retained production input in pure Lua."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/'tools'))
from prepare_ui_popup_assets import (GAME, control_tree, production_style_defaults,
    production_font_metrics, lua_value)
from economic_overview_scene import execute_lua

HARNESS=r'''
local sources,layout=@@SOURCES@@,@@LAYOUT@@
local checks=0
local function check(value,message) checks=checks+1;assert(value,message) end
local arrayTypes={}
local function json(value)
 local t=type(value)
 if t=='nil' then return 'null' end
 if t=='boolean' or t=='number' then return tostring(value) end
 if t=='string' then return '"'..value:gsub('[%z\1-\31\\"]',function(ch)
  if ch=='"' then return '\\"' elseif ch=='\\' then return '\\\\' end
  return string.format('\\u%04x',string.byte(ch)) end)..'"' end
 local parts={}
 if arrayTypes[getmetatable(value)] or #value>0 then for _,v in ipairs(value) do parts[#parts+1]=json(v) end;return '['..table.concat(parts,',')..']' end
 local keys={};for k in pairs(value) do keys[#keys+1]=k end;table.sort(keys)
 for _,k in ipairs(keys) do parts[#parts+1]=json(k)..':'..json(value[k]) end
 return '{'..table.concat(parts,',')..'}'
end
local maps={{File='C:\\owned-fixture\\Existing.Civ5Map',Name='Existing',Description='Original fixture map',
 worldType='WORLDSIZE_STANDARD',width=80,height=52,ModificationTime='fixture-time'}}
local requests={}
local env=setmetatable({ZeroSisUiLayout=layout,Game={Rand=function() return 0 end,
 IsNetworkMultiPlayer=function() return false end,GetActivePlayer=function() return 0 end,GetGameTurn=function() return 1 end},GameInfo={
 MapScripts=function() return function() return nil end end,
 Worlds={WORLDSIZE_STANDARD={ID=3}}}}, {__index=_G});env._G=env
local function run(text,name) local fn=assert(loadstring(text,'@'..name));setfenv(fn,env);return fn() end
env.include=function(name) return run(assert(sources[name],'Missing original include '..name),name) end
env.print=function() end
env.ZeroSisUiNative=function(op,...)
 if op=='uiFrameTime' then return 0 end
 if op=='screenSize' then return 1920,1080 end
 if op=='randomSeed' then return 17 end
 if op=='locale' then return (...) end
 if op=='localeLength' then return #(...) end
 if op=='localeSubstring' then local s,a,n=...;return s:sub(a,a+n-1) end
 if op=='snapshotJson' then local value,marker=...;arrayTypes[marker]=true;return value end
 if op=='mapMenuList' then return maps end
 if op=='mapMenuCurrent' then return 'Assets/Maps/Continents.lua',3,_FIXTURE_MAP_PARENT or 'GameMenu' end
 if op=='mapMenuNameAvailable' then
  local name=...
  if name=='CON' or name:sub(-1)=='.' or name:sub(1,1)==' ' or #name>100 then return false end
  for _,m in ipairs(maps) do if m.Name:lower()==name:lower() then return false end end
  return true
 end
 if op=='mapMenuSave' then local name,path=...;requests[#requests+1]={kind='save',name=name,path=path};return end
 if op=='mapMenuDelete' then requests[#requests+1]={kind='delete',path=(...)};return end
 error('Unmodeled native operation '..op)
end
run(sources.scene,'UiScene+input+map');run(sources.original,'original-SaveMapMenu')
local function click(id)
 for _,target in ipairs(env.ZeroSisUi.GetInputTargets()) do if target.id==id and target.event=='LeftClick' then
  check(env.ZeroSisUi.DispatchLeftClick(target.key),'Retained map click failed '..id);return target.key
 end end
 error('Missing retained map click target '..id)
end
env.ZeroSisUi.OpenMapMenu()
check(env.ZeroSisUi.IsActive() and env.ZeroSisUi.IsTextInputEnabled(),'Original map show/focus failed')
local snap=env.ZeroSisUi.Snapshot()
check(snap.timerSemaphore==0 and snap.mapMenu.privateCatalogOnly and not snap.mapMenu.campaignSave,'Map scope/timer changed')
local row=click('Button')
check(env.Controls.NameBox:GetText()=='Existing','Original map row selection failed')
click('SaveButton')
check(not env.Controls.DeleteConfirm:IsHidden() and #requests==0,'Overwrite did not ask before mutation')
check(env.ZeroSisUi.DispatchLeftClick(row)==false,'Confirmation allowed stale background row input')
click('No');check(env.Controls.DeleteConfirm:IsHidden(),'Original overwrite No did not dismiss')
click('SaveButton');click('Yes')
check(#requests==1 and requests[1].kind=='save' and requests[1].path==maps[1].File and not env.ZeroSisUi.IsActive(),
 'Confirmed overwrite did not publish exact private map path')
env.ZeroSisUi.OpenMapMenu();click('NameBox')
for _,scalar in ipairs({78,101,119,77,97,112}) do check(env.ZeroSisUi.DispatchTextInput(scalar),'Map text insert failed') end
check(env.Controls.NameBox:GetText()=='NewMap','Map text editor changed entered name')
check(env.ZeroSisUi.DispatchKeyDown(13),'Map Enter was rejected')
check(#requests==2 and requests[2].name=='NewMap' and requests[2].path=='' and not env.ZeroSisUi.IsActive(),
 'New map Enter did not defer a name-only create and close')
env.ZeroSisUi.OpenMapMenu();click('Button');click('Delete')
check(not env.Controls.DeleteConfirm:IsHidden(),'Map Delete did not confirm')
click('Yes');check(#requests==3 and requests[3].kind=='delete' and env.ZeroSisUi.IsActive(),'Map Delete did not publish owned request')
maps={};env.ZeroSisUi.RefreshMapMenu()
check(env.Controls.NameBox:GetText()=='' and env.Controls.SaveButton:IsDisabled(),'Post-delete refresh retained obsolete name')
check(env.ZeroSisUi.DispatchLeftClick(row)==false,'Deleted map retained an input identity')
check(env.ZeroSisUi.DispatchKeyDown(27),'Map Escape did not close')
check(not env.ZeroSisUi.IsActive() and not env.ZeroSisUi.IsTextInputEnabled(),'Map close retained focus/modal state')
maps={{File='C:\\owned-fixture\\Existing.Civ5Map',Name='Existing',Description='Original fixture map',
 worldType='WORLDSIZE_STANDARD',width=80,height=52,ModificationTime='fixture-time'}}
env.ZeroSisUi.OpenMapMenu()
for _,bad in ipairs({'CON','trailing.','existing',' leading'}) do
 local count=#requests
 env.Controls.NameBox:SetText(bad);env.OnEditBoxChange()
 check(env.Controls.SaveButton:IsDisabled(),'Unavailable private map name kept Save enabled')
 check(env.ZeroSisUi.DispatchKeyDown(13),'Invalid map Enter was not consumed')
 check(env.OnSave()==false and env.ZeroSisUi.IsActive() and #requests==count,'Invalid map name closed or queued a mutation')
end
check(not env.ValidateText(string.rep('x',101)),'Native overlong name rejection was bypassed by the wrapped validator')
env.ZeroSisUi.CloseMapMenu()
if _RETURN_MENU_SNAPSHOTS then
 maps={{File='C:\\owned-fixture\\Existing.Civ5Map',Name='Existing',Description='Original fixture map',
  worldType='WORLDSIZE_STANDARD',width=80,height=52,ModificationTime='fixture-time'}}
 env.ZeroSisUi.OpenMapMenu();local shown=env.ZeroSisUi.Snapshot()
 click('Button');click('Delete');local confirming=env.ZeroSisUi.Snapshot()
 env.ZeroSisUi.DispatchKeyDown(27);env.ZeroSisUi.CloseMapMenu()
 maps={}
 for index=1,30 do maps[index]={File='C:\\owned-fixture\\Map'..index..'.Civ5Map',Name='Map'..index,Description='',
  worldType='WORLDSIZE_STANDARD',width=80,height=52,ModificationTime='fixture-time'} end
 env.ZeroSisUi.OpenMapMenu();local overflow=env.ZeroSisUi.Snapshot()
 click('Button');click('Delete');local overflowConfirm=env.ZeroSisUi.Snapshot()
 env.ZeroSisUi.DispatchKeyDown(27);env.ZeroSisUi.CloseMapMenu();local closed=env.ZeroSisUi.Snapshot()
 return json({map=shown,mapConfirm=confirming,mapOverflow=overflow,mapOverflowConfirm=overflowConfirm,mapClosed=closed})
end
return json({status='PASS',checks=checks,requests=#requests,classification='RETAINED_MAP_LUA_FIXTURE_ONLY',
 originalMapLuaExecuted=true,hostExecuted=false,sdkExecuted=false,hwndCreated=false,filesWritten=0})
'''


def fixture_script(*,scene_override=None,layout_override=None):
    relatives={'original':'Assets/UI/InGame/Menus/SaveMapMenu.lua','xml':'Assets/UI/InGame/Menus/SaveMapMenu.xml',
        'InstanceManager':'Assets/UI/InstanceManager.lua','IconSupport':'Assets/UI/IconSupport.lua',
        'SupportFunctions':'Assets/UI/SupportFunctions.lua','FLuaVector':'Assets/Gameplay/Lua/FLuaVector.lua'}
    before={name:hashlib.sha256((GAME/path).read_bytes()).hexdigest() for name,path in relatives.items()}
    tree=control_tree(ET.parse(GAME/relatives['xml']).getroot())
    tree.update(popupKind='MapMenu',contextName='SaveMapMenu')
    from menu_options_assets import artifact
    tree['mapMenu']=dict(profile='ORIGINAL_PRIVATE_MAP_MENU_V1',originalLua=artifact(GAME/relatives['original']),
        originalXml=artifact(GAME/relatives['xml']),completeOriginalXmlRetained=True,
        retailWidgetGeometryVerified=False,nativeDisplayVerified=False,privateCatalogOnly=True,
        retailOrUserSaveDirectoriesUsed=False,saveContractChanged=False)
    styles=production_style_defaults(PROJECT/'Source/Assets/UI',tree)
    tree.update(styleDefaults=styles['controls'],styleDefaultsSource=styles['source'],styleDefaultsPolicy=styles['policy'])
    tree['fontMetrics']=production_font_metrics(tree,{})
    sources={name:(GAME/path).read_text(encoding='utf-8-sig') for name,path in relatives.items() if name!='xml'}
    sources['scene']='\n'.join((PROJECT/path).read_text(encoding='utf-8-sig') for path in
        ('Source/Host/UiScene.lua','Source/Presentation/UiPresentationInput.lua','Source/Presentation/UiMapMenu.lua'))
    if scene_override is not None:sources['scene']=scene_override
    if layout_override is not None:tree=layout_override
    return HARNESS.replace('@@SOURCES@@',lua_value(sources)).replace('@@LAYOUT@@',lua_value(tree)),sources,before,relatives


def main():
    script,sources,before,relatives=fixture_script()
    report=execute_lua(script)
    after={name:hashlib.sha256((GAME/path).read_bytes()).hexdigest() for name,path in relatives.items()}
    if before!=after:raise RuntimeError('Installed map source changed during read-only fixture')
    report.update(schema='zerosis.menu_map.scene_fixture.v1',original_source_sha256=before,
        source_sha256={key:hashlib.sha256(value.encode('utf-8')).hexdigest() for key,value in sources.items()})
    evidence=PROJECT/'evidence/game_menu/offline_menu_suite/options_touch';evidence.mkdir(parents=True,exist_ok=True)
    (evidence/'map_lua_tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({key:report[key] for key in ('status','checks','classification')}))


if __name__=='__main__':main()
