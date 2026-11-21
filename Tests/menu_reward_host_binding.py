"""Real Host binding/commit snapshots, legacy regression and retained Lua only.

SDK sources/DLL are hashed, never loaded. The current C++ getter body is
compiled with a fake owner and real atomic cell. File stores are isolated in
the exact new fixture directories. Lua runs only in the existing shared5.1
provider with explicit fake menu operations and already retained font metrics.
"""
from __future__ import annotations
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[1]
sys.path[:0]=[str(PROJECT/'tools'),str(PROJECT/'Tests')]
from menu_replay_legend_assets import artifact
from menu_replay_restoration import build_cxx14
from native_build import build_program,run
from menu_suite_storage import storage
from retained_menu_suite_host_input import parse_catalog
from civ5_ui_assets import supported_original_menu_handlers
from ui_font_profile import resolve_prepared_font_metrics
from prepare_ui_popup_assets import lua_value
from economic_overview_scene import execute_lua
from ui_pixel_scene import private_menu_contract
import menu_options_scene

STAGE=PROJECT/'evidence/game_menu/options_reward_popups/binding'
HEADER=PROJECT/'Source/Host/UiPopupAssets.generated.h'
PREPARED=PROJECT/'evidence/ui_popup/assets/prepared.json'
SDK_REPORT=PROJECT/'evidence/serialization/unit_great_work_save/sdk_2bdcdf80a1695780f864/result.json'
SDK=PROJECT/'Build/UnitGreatWorkSaveSDK/2bdcdf80a1695780f864/CvGameCoreDLL_Expansion2_x64.dll'
SDK_DIRECTORY=PROJECT/'Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2'
RULE_FILES=('CvBuildingClasses.cpp','CvPlayer.cpp','CvPlot.cpp','CvTeam.cpp','CvUnit.cpp')


def read(path):return json.loads(Path(path).read_bytes())


def checked(row):
    actual=artifact(row['path'])
    if actual['sha256']!=row['sha256'] or ('bytes' in row and actual['bytes']!=row['bytes']):raise ValueError('Pinned source/provenance changed: '+row['path'])
    return actual


def stable(row):return tuple(row[key] for key in ('path','bytes','sha256','file_identity','mtime_ns','file_attributes'))


def sdk_provenance():
    report=checked(dict(path=str(SDK_REPORT),sha256='4b6310ce04dc6d1b155c406ac470b855682c2934eb03f6742ab1f065a6ef12ec'))
    current=read(SDK_REPORT);parent_ref=checked(current['parent']);parent=read(parent_ref['path'])
    sdk=checked(dict(path=str(SDK),sha256='430f3122d0b555d6daae14aa7c011ef43ce8f978270477c8af596ca4b0493ab9'))
    rows={Path(row['path']).name:row for row in parent['inputs'] if 'path' in row and Path(row['path']).parent==SDK_DIRECTORY and Path(row['path']).name in RULE_FILES}
    rows[Path(current['source']['path']).name]=current['source']
    if set(rows)!=set(RULE_FILES):raise ValueError('SDK430 inherited/new source records do not cover the five consumers')
    consumers=[]
    for name in RULE_FILES:
        source=checked(rows[name]);text=(SDK_DIRECTORY/name).read_bytes().decode('utf8',errors='replace')
        matches=list(re.finditer(r'IsOptionNoRewardPopups\(\)',text))
        if len(matches)!=1:raise ValueError('Expected exactly one known reward option consumer: '+name)
        match=matches[0];line=text.count('\n',0,match.start())+1
        consumers.append(dict(source=source,compiled_source_record=rows[name],record_owner=report if name=='CvUnit.cpp' else parent_ref,
            line=line,source_branch_sha256=hashlib.sha256(text[match.start():match.start()+1100].encode()).hexdigest(),
            scope='EXACT_SDK430_NEW_CVUNIT_OR_INHERITED_COMPILED_SOURCE_HASH_MATCH_NOT_RUNTIME_EXECUTION'))
    return dict(report=report,parent_build_report=parent_ref,dll=sdk,known_consumers=consumers,
        all_five_live_sources_match_effective_sdk430_input_records=True,sdk_loaded_or_executed=False,gameplay_balance_modified=False)


def getter_source():
    text=(PROJECT/'Source/Host/HostServices.h').read_text('utf8')
    token='bool IsOptionNoRewardPopups() override'
    if text.count(token)!=1:raise ValueError('Actual SDK getter is missing or ambiguous')
    start=text.index(token);brace=text.index('{',start);end=text.index('}',brace)+1;body=text[start:end]
    if 'noRewardPopupsCommitted->load(std::memory_order_acquire)' not in body or any(word in body for word in ['RequireUiOwner','menuOptions','noRewardPopupsApplied']):raise ValueError('SDK getter does not read only the confirmed atomic snapshot')
    if 'const std::shared_ptr<std::atomic<bool>> noRewardPopupsCommitted=' not in text:raise ValueError('Host publication cell is replaceable')
    return body


def embedded_proof():
    arrays,order=parse_catalog(HEADER.read_bytes(),74,('ZeroSisUiScene','MenuOptionsLayout','TouchHelpLayout'))
    menu=(PROJECT/'Source/Presentation/UiMenuOptions.lua').read_bytes();map_menu=(PROJECT/'Source/Presentation/UiMapMenu.lua').read_bytes()
    if not arrays['ZeroSisUiScene'].endswith(b'\n'+menu+b'\n'+map_menu):raise ValueError('Host still embeds an older menu adapter')
    handlers=supported_original_menu_handlers();reward=[row for row in handlers['functions'] if row['name']=='OnNoRewardPopupsCheckbox']
    if len(reward)!=1:raise ValueError('Original callback provenance is missing')
    expected=reward[0]
    if expected['sha256'].encode() not in arrays['MenuOptionsLayout'] or b'SetNoRewardPopups_Cached' not in arrays['MenuOptionsLayout']:raise ValueError('Embedded layout lacks exact original reward callback bytes/provenance')
    prepared=read(PREPARED);tree=prepared['xml_control_trees']['MenuOptionsLayout']
    if tree['menuOptions']['originalSupportedHandlers']!=handlers or 'noRewardPopups' not in tree['menuOptions']['privateKeys']:raise ValueError('Prepared menu metadata is stale')
    return dict(header=artifact(HEADER),prepared=artifact(PREPARED),catalog_entries=len(order),layouts=len(prepared['xml_control_trees']),
        scene_sha256=hashlib.sha256(arrays['ZeroSisUiScene']).hexdigest(),menu_layout_sha256=hashlib.sha256(arrays['MenuOptionsLayout']).hexdigest(),
        exact_current_menu_adapter_embedded=True,exact_original_reward_handler=expected,complete_original_options_script_executed=False),arrays,prepared


ONLY_REWARD=r'''
capabilityOverrides={noBasicHelp=false,uiCueVolumePercent=false,windowWidth=false,windowHeight=false,
 fullscreen=false,vsync=false,policyInfo=false,noRewardPopups=true}
local env=initialize('options');env.ZeroSisUi.OpenMenuOptions()
local metadata=env.ZeroSisUi.MenuOptionsMetadata()
check(metadata.page=='game' and metadata.supportedCapabilities.noRewardPopups and not metadata.supportedCapabilities.noBasicHelp,
 'Reward-only backend did not select the actual Game page')
local key=click(env,'NoRewardPopupsCheckbox')
check(cached.noRewardPopups==1 and committed.noRewardPopups==0,'Original reward handler bypassed its draft')
check(env.ZeroSisUi.MenuOptionsMetadata().originalHandlerInvocations.OnNoRewardPopupsCheckbox==1,'Original reward callback was replaced')
click(env,'CancelButton');check(committed.noRewardPopups==0 and persistence==0,'Cancelled reward draft persisted')
check(not env.ZeroSisUi.DispatchLeftClick(key),'Closed reward callback remained actionable')
env.ZeroSisUi.OpenMenuOptions();click(env,'NoRewardPopupsCheckbox');click(env,'AcceptButton')
check(committed.noRewardPopups==1 and persistence==1 and not open,'Reward apply did not commit once')
env.ZeroSisUi.OpenMenuOptions();click(env,'NoRewardPopupsCheckbox');fail=true;click(env,'AcceptButton')
check(committed.noRewardPopups==1 and env.ZeroSisUi.IsActive(),'Failed reward apply changed confirmed state or closed the editor')
fail=false;click(env,'CancelButton')
env.ZeroSisUi.OpenMenuOptions();click(env,'DefaultButton');click(env,'CancelButton')
check(committed.noRewardPopups==1 and persistence==1,'Cancelled defaults changed the confirmed reward flag')
env.ZeroSisUi.OpenMenuOptions();local snapshot=env.ZeroSisUi.Snapshot();env.ZeroSisUi.CloseMenuOptions()
return json({status='PASS_REWARD_ONLY_ACTUAL_RETAINED_LUA_CALLBACK',checks=checks,applies=applies,persistence=persistence,
 originalRewardHandlerInvocations=env.ZeroSisUi.MenuOptionsMetadata().originalHandlerInvocations.OnNoRewardPopupsCheckbox,
 nativeHostOrSdkExecuted=false,completeOriginalOptionsScriptExecuted=false,snapshot=snapshot})
'''


POPUP_VISIBILITY=r'''
local observed={}
for _,rewardSupported in ipairs({true,false}) do
 capabilityOverrides={noRewardPopups=rewardSupported}
 local env=initialize('options');env.ZeroSisUi.OpenMenuOptions()
 check(env.Controls.NoRewardPopupsCheckbox:IsHidden()==not rewardSupported,
  'Reward capability and checkbox visibility diverged')
 local hidden={}
 for id,control in pairs(env.Controls) do
  if type(id)=='string' and id:find('Popup',1,true) then
   if id~='NoRewardPopupsCheckbox' or not rewardSupported then
    check(control:IsHidden(),'Unsupported source popup became visible: '..id);hidden[#hidden+1]=id
   end
  end
 end
 for _,id in ipairs({'Countdown','GraphicsChangedPopup','VideoPanelBlock'}) do
  if env.Controls[id] then check(env.Controls[id]:IsHidden(),'Unsupported source window became visible: '..id) end
 end
 for _,target in ipairs(env.ZeroSisUi.GetInputTargets()) do
  check(target.id~='Countdown' and target.id~='GraphicsChangedPopup' and target.id~='VideoPanelBlock',
   'Unsupported source popup/window acquired input')
  if not rewardSupported then check(target.id~='NoRewardPopupsCheckbox','Unsupported reward callback acquired input') end
 end
 table.sort(hidden);observed[#observed+1]={rewardSupported=rewardSupported,hiddenPopupIds=hidden}
 env.ZeroSisUi.CloseMenuOptions()
end
capabilityOverrides={noRewardPopups=false,noBasicHelp=false}
local noGame=initialize('options');noGame.ZeroSisUi.OpenMenuOptions()
check(noGame.Controls.GameButton:IsHidden(),'Game tab remained visible without either backend')
for _,target in ipairs(noGame.ZeroSisUi.GetInputTargets()) do
 check(target.id~='GameButton' and target.id~='NoRewardPopupsCheckbox','Backend-free Game tab acquired input')
end
noGame.ZeroSisUi.CloseMenuOptions()
return json({status='PASS_SUPPORTED_CHECKBOX_EXCEPTION_AND_UNSUPPORTED_POPUP_WINDOW_MASK',checks=checks,cases=observed,
 nativeHostOrSdkExecuted=false})
'''


def lua_probes(arrays,prepared):
    layouts={}
    for key,symbol in [('options','MenuOptionsLayout'),('touch','TouchHelpLayout')]:
        tree=deepcopy(prepared['xml_control_trees'][symbol]);tree['fontMetrics']=resolve_prepared_font_metrics(prepared,tree['fontMetrics']);layouts[key]=tree
    scene=arrays['ZeroSisUiScene'].decode('utf-8-sig')
    full,sources=menu_options_scene.fixture_script(scene_override=scene,layouts_override=layouts)
    full_result=execute_lua(full)
    if full_result['status']!='PASS':raise ValueError('Existing full retained menu harness failed')
    marker="local env=initialize('options')"
    if menu_options_scene.HARNESS.count(marker)!=1:raise ValueError('Menu harness initialization boundary changed')
    prefix=menu_options_scene.HARNESS.split(marker)[0]
    visibility=(prefix+POPUP_VISIBILITY).replace('@@SOURCES@@',lua_value(sources)).replace('@@LAYOUTS@@',lua_value(layouts))
    visibility_result=execute_lua(visibility)
    if visibility_result['status']!='PASS_SUPPORTED_CHECKBOX_EXCEPTION_AND_UNSUPPORTED_POPUP_WINDOW_MASK':raise ValueError('Popup visibility probe failed')
    isolated=(prefix+ONLY_REWARD).replace('@@SOURCES@@',lua_value(sources)).replace('@@LAYOUTS@@',lua_value(layouts))
    reward_result=execute_lua(isolated)
    if reward_result['status']!='PASS_REWARD_ONLY_ACTUAL_RETAINED_LUA_CALLBACK':raise ValueError('Reward-only retained menu probe failed')
    snapshots=execute_lua('_RETURN_MENU_SNAPSHOTS=true\n'+full)
    contracts={}
    for name,context,closed in [('options','menu-options',False),('video','menu-options',False),('audio','menu-options',False),
                               ('optionsClosed','menu-options',True),('touch','touch-help',False),('touchClosed','touch-help',True)]:
        contracts[name]=private_menu_contract(snapshots[name],context=context,closed=closed)
    reward_snapshot=reward_result.pop('snapshot')
    contracts['rewardOnly']=private_menu_contract(reward_snapshot,context='menu-options')
    rejected=[]
    bad=deepcopy(snapshots['options']);bad['menuOptions']['source']['privateSettingsSchema']='ZEROSIS_PRIVATE_MENU_OPTIONS_V2'
    missing=deepcopy(snapshots['options']);missing['menuOptions']['supportedCapabilities'].pop('noRewardPopups')
    wrong=deepcopy(snapshots['options']);wrong['menuOptions']['supportedCapabilities']['noRewardPopups']='true'
    for name,snapshot in [('wrongVersion',bad),('missingRewardCapability',missing),('nonBooleanCapability',wrong)]:
        try:private_menu_contract(snapshot,context='menu-options')
        except (ValueError,AssertionError):rejected.append(name)
        else:raise ValueError('Private source/input contract accepted '+name)
    return dict(shared_lua_provider=artifact(PROJECT/'Build/SharedLuaRuntime/Lua/ZeroSisLua51_x64.dll'),
        full_existing_harness=full_result,reward_only_probe=reward_result,popup_visibility_probe=visibility_result,
        popup_visibility_script_sha256=hashlib.sha256(visibility.encode()).hexdigest(),full_script_sha256=hashlib.sha256(full.encode()).hexdigest(),
        reward_script_sha256=hashlib.sha256(isolated.encode()).hexdigest(),font_metrics_reused_from=artifact(PREPARED),
        actual_snapshot_contracts=contracts,rejected_invalid_snapshot_contracts=rejected,
        font_or_asset_extraction_run=False,actual_embedded_scene_executed_in_controlled_lua_only=True,gamecore_or_host_loaded=False)


def imported(compiled,directory):
    result=run([Path(compiled['compiler']).with_name('dumpbin.exe'),'/dependents',compiled['path']],cwd=directory,timeout=30)
    names=sorted(set(re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$',result.stdout.decode('mbcs',errors='replace'),re.M)))
    if result.returncode or {name.lower() for name in names}!={'kernel32.dll'}:raise ValueError('Controlled binding console imports a UI/SDK/audio DLL: '+repr(names))
    return names


def cleanup_intermediates(root,stage,report):
    candidates=[]
    for path in root.rglob('*'):
        if not path.is_file() or path.suffix=='.exe':continue
        if path.resolve()!=path.absolute() or not path.is_relative_to(root):raise ValueError('Cleanup candidate escaped private binding fixture')
        info=storage.ordinary(path)
        if info.st_nlink!=1:raise ValueError('Binding fixture intermediate unexpectedly shared')
        row=dict(artifact(path),allocated_bytes=storage.allocated(path));candidates.append(row)
    plan=stage/'cleanup_plan.json'
    with plan.open('x',encoding='utf8') as f:json.dump(dict(schema='zerosis.reward_binding.exact_cleanup.v1',root=str(root),candidates=candidates,source_or_game_or_runtime_deleted=False),f,indent=2);f.write('\n')
    report['cleanup_plan']=artifact(plan);deleted=[]
    for row in candidates:
        path=Path(row['path']);current=artifact(path)
        if stable(current)!=stable(row):raise ValueError('Binding cleanup file identity/content changed')
        path.unlink();row['result']='DELETED_EXACT_OWNED_BINDING_FIXTURE_INTERMEDIATE';deleted.append(row)
    empty=[]
    for path in sorted((path for path in root.rglob('*') if path.is_dir()),key=lambda x:len(x.parts),reverse=True):
        if path.resolve()!=path.absolute() or not path.is_relative_to(root):raise ValueError('Empty cleanup directory escaped fixture')
        if not list(path.iterdir()):path.rmdir();empty.append(str(path))
    report['owned_intermediate_cleanup']=deleted;report['empty_fixture_directories_removed']=empty
    report['intermediate_allocated_bytes_removed']=sum(row['allocated_bytes'] for row in deleted)


def main():
    sdk=sdk_provenance();embedding,arrays,prepared=embedded_proof();body=getter_source()
    inputs=[Path(__file__),Path(__file__).with_suffix('.cpp'),PROJECT/'Tests/menu_options_host_binding.cpp',PROJECT/'Tests/menu_options_scene.py',
        PROJECT/'Source/Host/HostServices.h',PROJECT/'Source/Host/MenuOptionsHostBinding.h',PROJECT/'Source/Host/MenuOptionsContract.h',PROJECT/'Source/Host/MenuOptionsStore.h',
        PROJECT/'Source/Presentation/UiMenuOptions.lua',PROJECT/'Source/Presentation/UiMapMenu.lua',PROJECT/'tools/civ5_ui_assets.py',PROJECT/'tools/menu_options_assets.py',
        PROJECT/'tools/ui_font_profile.py',PROJECT/'tools/ui_pixel_scene.py',PROJECT/'Source/Host/UiScene.lua',PROJECT/'Source/Presentation/UiPresentationInput.lua',HEADER,PREPARED,
        PROJECT/'Build/SharedLuaRuntime/Lua/ZeroSisLua51_x64.dll',SDK_REPORT,Path(sdk['parent_build_report']['path']),SDK,
        PROJECT/'evidence/game_menu/options_reward_popups/migration_plan.json',*[SDK_DIRECTORY/name for name in RULE_FILES]]
    inputs=sorted({str(path.absolute()):path for path in inputs}.values(),key=lambda path:str(path).casefold());before=[artifact(path) for path in inputs]
    signature=hashlib.sha256(json.dumps(before,sort_keys=True).encode()).hexdigest()[:16];stage=STAGE/signature;root=PROJECT/'Build/MenuRewardHostBinding'/signature
    if stage.exists() or root.exists():raise ValueError('Inspect the existing exact-input binding attempt instead of replaying it')
    stage.mkdir(parents=True,exist_ok=False);root.mkdir(parents=True,exist_ok=False)
    component=root/'component';legacy=root/'legacy';data=root/'component_data';legacy_data=root/'legacy_data'
    for path in (component,legacy,data,legacy_data):path.mkdir()
    report=dict(schema='zerosis.reward_popups.host_binding.v1',inputs_before=before,input_signature=signature,known_sdk_sources=sdk,
        embedded_payload_verification=embedding,actual_sdk_getter_body_sha256=hashlib.sha256(body.encode()).hexdigest(),
        sdk_Host_HWND_GPU_or_audio_executed=False,gamecore_loaded=False,retail_settings_or_user_save_opened=False,
        shared_lua_provider_only_allowed=True,owned_intermediate_cleanup=[])
    try:
        getter=component/'reward_popup_sdk_getter.inc';getter.write_text(body+'\n',encoding='ascii');report['extracted_getter']=artifact(getter)
        built=build_cxx14('MenuRewardHostBinding',component,stage,PROJECT/'Tests/menu_reward_host_binding.cpp',[PROJECT/'Source/Host',component]);report['component_build']=built
        report['component_imported_dlls']=imported(built,component)
        result=run([built['path'],str(data)],cwd=component,timeout=30)
        if result.returncode:raise ValueError((result.stdout+result.stderr).decode('utf8',errors='replace'))
        report['binding_fixture']=json.loads(result.stdout)
        old=build_program(name='MenuOptionsHostBindingRegression',architecture='x64',vs=Path(r'C:/Program Files/Microsoft Visual Studio/2022/Community'),directory=legacy,evidence=stage,
            source=PROJECT/'Tests/menu_options_host_binding.cpp',includes=[PROJECT/'Source/Host'],defines=['_CRT_SECURE_NO_WARNINGS']);report['legacy_regression_build']=old
        report['legacy_regression_imported_dlls']=imported(old,legacy)
        result=run([old['path'],str(legacy_data)],cwd=legacy,timeout=30)
        if result.returncode:raise ValueError((result.stdout+result.stderr).decode('utf8',errors='replace'))
        report['legacy_regression']=json.loads(result.stdout)
        report['lua']=lua_probes(arrays,prepared)
        report['inputs_after']=[artifact(row['path']) for row in before]
        if [stable(row) for row in report['inputs_after']]!=[stable(row) for row in before]:raise ValueError('Frozen binding/provenance inputs changed during verification')
        report.update(status='PASS_COMMITTED_REWARD_HOST_BINDING_LEGACY_REGRESSION_AND_RETAINED_LUA',compiler_and_linker_warnings=0,
            sdk_rules_and_dll_unchanged=True,strict_committed_only_publication_verified=True)
    except Exception as error:
        report.update(status='FAIL_REWARD_HOST_BINDING_COMPONENT',error=str(error));raise
    finally:
        cleanup_intermediates(root,stage,report)
        with (stage/'result.json').open('x',encoding='utf8') as f:json.dump(report,f,indent=2);f.write('\n')
    print(json.dumps(dict(status=report['status'],cpp_checks=report['binding_fixture']['checks'],legacy_checks=report['legacy_regression']['checks'],
        lua_checks=sum(report['lua'][key]['checks'] for key in ['full_existing_harness','reward_only_probe','popup_visibility_probe']),sdk_consumers=5,report=str(stage/'result.json'),
        removed_intermediates=len(report['owned_intermediate_cleanup']),intermediate_allocated_bytes_removed=report['intermediate_allocated_bytes_removed'])))
    return 0


if __name__=='__main__':raise SystemExit(main())
