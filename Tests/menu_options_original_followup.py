"""Stock options callbacks/control transport with pure Lua and CPU-only paint.

No Host, GameCore, window, GPU, retail INI, MODS or user saves are run/written.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

PROJECT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(PROJECT / 'tools'), str(PROJECT / 'Tests')]
from menu_options_scene import fixture_script, execute_lua
from menu_options_assets import GAME, supported_original_handlers, menu_slider_style
from ui_pixel_scene import Compiler, private_menu_contract
from menu_options_renderer_contract import visible_geometry, nodes

STAGE = PROJECT / 'evidence/game_menu/original_menu_followup/options'

EXTENSION = r'''
local captures={}
env.ZeroSisUi.OpenMenuOptions()
click(env,'IFaceButton');captures.interface=env.ZeroSisUi.Snapshot()
local beforePolicy=committed.policyInfo
click(env,'PolicyInfo')
check(cached.policyInfo~=beforePolicy and committed.policyInfo==beforePolicy,'Original policy handler applied before Save')
click(env,'CancelButton')
check(committed.policyInfo==beforePolicy,'Original policy handler Cancel persisted its edit')
env.ZeroSisUi.OpenMenuOptions();click(env,'IFaceButton');click(env,'PolicyInfo')
fail=true;click(env,'AcceptButton')
check(env.ZeroSisUi.IsActive() and committed.policyInfo==beforePolicy,'Failed policy commit closed or changed actual readback')
fail=false;click(env,'AcceptButton')
check(committed.policyInfo~=beforePolicy and not env.ZeroSisUi.IsActive(),'Policy commit did not apply then close')
env.ZeroSisUi.OpenMenuOptions();click(env,'IFaceButton')
check(env.Controls.PolicyInfo:IsChecked()==(committed.policyInfo~=0),'Original policy option did not read back after reopen')
click(env,'VideoButton')
local widget=env.ZeroSisUi.Snapshot().pullDowns[1]
check(env.ZeroSisUi.DispatchLeftClick(widget.buttonKey),'Original resolution PullDown toggle rejected')
local opened=env.ZeroSisUi.Snapshot()
check(opened.pullDowns[1].opened and #opened.pullDowns[1].entryKeys==6,'Original resolution PullDown did not expose owned entries')
captures.resolutionOpen=opened
local covered=0
for _,target in ipairs(opened.inputTargets) do if target.id=='AcceptButton' then covered=covered+1 end end
check(covered==0,'Resolution popup exposed a background Apply callback')
local backgroundKey
for _,node in ipairs(opened.tree.children) do if node.id=='AcceptButton' then backgroundKey=node.key end end
check(env.ZeroSisUi.DispatchLeftClick(0)==false,'Resolution popup accepted absent key zero')
local picked=opened.pullDowns[1].entryKeys[3]
check(env.ZeroSisUi.DispatchLeftClick(picked),'Original resolution selection callback rejected')
check(cached.windowWidth==1280 and cached.windowHeight==800 and not env.ZeroSisUi.Snapshot().pullDowns[1].opened,
 'Original resolution selection did not cache dimensions then close its popup')
check(env.ZeroSisUi.DispatchLeftClick(picked)==false,'Hidden resolution entry accepted a stale click')
check(env.ZeroSisUi.DispatchLeftClick(widget.buttonKey),'Original resolution popup failed to reopen')
check(env.ZeroSisUi.DispatchKeyDown(27) and env.ZeroSisUi.IsActive() and open and
 not env.ZeroSisUi.Snapshot().pullDowns[1].opened,'Escape did not close resolution list before cancelling options')
check(env.ZeroSisUi.DispatchLeftClick(widget.buttonKey),'Resolution popup failed to reopen for dismissal')
local dismiss
for _,target in ipairs(env.ZeroSisUi.GetInputTargets()) do if target.inputRole=='PullDownDismiss' then dismiss=target.key end end
check(dismiss and env.ZeroSisUi.DispatchLeftClick(dismiss),'Resolution popup root dismissal failed')
check(env.ZeroSisUi.IsActive() and open,'Resolution dismissal cancelled its parent option transaction')
click(env,'AudioButton')
local slider=env.ZeroSisUi.GetInputTargets('SliderValue')[1]
check(slider and slider.void1==1 and slider.minimum==0 and slider.maximum==1,'Original effects slider has wrong identity/range/knob')
local volumeBefore=cached.uiCueVolumePercent
for _,bad in ipairs({-0.01,1.01,math.huge,-math.huge,'0.5'}) do
 check(env.ZeroSisUi.DispatchSliderValue(slider.key,bad)==false,'Malformed slider amount was accepted')
end
check(env.ZeroSisUi.DispatchSliderValue(slider.key,0/0)==false,'NaN slider amount was accepted')
check(env.ZeroSisUi.DispatchSliderValue(slider.key,0.5,true)==false,'Slider accepted extra arguments')
check(env.ZeroSisUi.DispatchSliderValue(slider.key+100000,0.5)==false,'Slider accepted stale identity')
check(env.ZeroSisUi.DispatchLeftClick(slider.key)==false,'Slider accepted fake button input')
check(cached.uiCueVolumePercent==volumeBefore,'Rejected slider input changed its cached preference')
check(env.ZeroSisUi.DispatchSliderValue(slider.key,0),'Slider zero endpoint rejected')
check(cached.uiCueVolumePercent==0,'Slider zero endpoint failed actual option cache')
captures.audioZero=env.ZeroSisUi.Snapshot()
check(env.ZeroSisUi.DispatchSliderValue(slider.key,0.373),'Fractional slider input rejected')
check(cached.uiCueVolumePercent==37 and env.Controls.EffectsVolumeSlider:GetValue()==0.37,'Slider percent quantization/readback changed')
captures.audioFraction=env.ZeroSisUi.Snapshot()
check(env.ZeroSisUi.DispatchSliderValue(slider.key,1),'Slider full endpoint rejected')
check(cached.uiCueVolumePercent==100,'Slider full endpoint failed actual option cache')
captures.audioFull=env.ZeroSisUi.Snapshot()
click(env,'GameButton')
check(env.ZeroSisUi.DispatchSliderValue(slider.key,0.5)==false,'Hidden slider accepted a drag')
local observations=env.ZeroSisUi.Snapshot().menuOptions.originalHandlerInvocations
for _,name in ipairs({'OnCategory','OnNoBasicHelpCheckbox','OnPolicyInfo','OnFullscreen','OnVSync',
 'OnUIVolumeSliderValueChanged','OnWResolutionPull'}) do
 check(type(observations[name])=='number' and observations[name]>0,'Supported original function did not execute: '..name)
end
env.ZeroSisUi.CloseMenuOptions()
check(env.ZeroSisUi.DispatchSliderValue(slider.key,0.5)==false,'Closed options accepted stale slider input')
captures.closed=env.ZeroSisUi.Snapshot()
check(env.OptionsManager.SetMusicVolume==nil and env.OptionsManager.SetLeaderQuality_Cached==nil,
 'Unsupported retail music/renderer APIs became success stubs')
if _RETURN_OPTIONS_FOLLOWUP then return json({status='PASS',checks=checks,captures=captures,
 originalHandlerInvocations=observations,retailOptionsLuaExecuted=false,hostExecuted=false,sdkExecuted=false,
 hwndCreated=false,gpuExecuted=false}) end
'''


def followup_script():
    script, sources = fixture_script()
    marker = 'if _RETURN_MENU_SNAPSHOTS then'
    assert script.count(marker) == 1
    return '_RETURN_OPTIONS_FOLLOWUP=true\n' + script.replace(marker, EXTENSION + '\n' + marker), sources


def run_lua():
    script, sources = followup_script()
    result = execute_lua(script)
    result['source_sha256'] = {name: hashlib.sha256(text.encode()).hexdigest() for name,text in sources.items()}
    return result


def main():
    STAGE.mkdir(parents=True,exist_ok=True)
    report = run_lua()
    captures = report.pop('captures')
    report['source_controls'] = {}
    for name,snapshot in captures.items():
        proof = private_menu_contract(snapshot,context='menu-options',closed=not snapshot['active'])
        report['source_controls'][name] = {'controls':proof['retained_control_count'],
            'input_targets':len(proof['input_order_keys']), 'slider_keys':proof['slider_input_keys'],
            'original_xml_preserved':proof['full_original_tree_matched']}
    (STAGE / 'original_options_lua_tests.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'checks':report['checks'],'captured_scenes':len(captures),
        'original_callbacks':len(report['originalHandlerInvocations']),'native_execution':False}))


if __name__ == '__main__':
    main()
