"""Exercise original SaveMenu overwrite callbacks with an in-memory queue.

The approved headless Lua provider is the only native code loaded. No Host,
GameCore, window, user archive or retail configuration is accessed.
"""
from __future__ import annotations

from contextlib import closing, contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import uuid
import xml.etree.ElementTree as ET

import owned_save_delete_scene as base

PROJECT = base.PROJECT
_digest = base._digest
SCRATCH_RECEIPTS = []


@contextmanager
def recorded_style_directory():
    """Inventory own temporary styles even when a negative Lua case raises."""
    folder = PROJECT / 'evidence/save_overwrite/source_contract/lua_scratch'
    folder.mkdir(parents=True, exist_ok=True)
    receipt = folder / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_') + uuid.uuid4().hex[:12] + '.json')
    record = {'schema': 'zerosis.owned_save_overwrite_style_cleanup.v1', 'status': 'NOT_ALLOCATED', 'files': []}
    temporary = None
    try:
        with base.small_source_directory() as temporary:
            record['directory'] = str(temporary)
            try:
                yield temporary, record['files']
            finally:
                for path in sorted(temporary.rglob('*')):
                    if path.is_file():
                        info = path.stat()
                        record['files'].append({'path': str(path), 'bytes': info.st_size, 'sha256': _digest(path),
                                                'file_identity': [info.st_dev, info.st_ino]})
                record['status'] = 'INVENTORIED_BEFORE_GUARDED_REMOVAL'
                with receipt.open('x', encoding='utf8') as stream:
                    json.dump(record, stream, ensure_ascii=False, indent=2)
                    stream.write('\n')
    finally:
        if temporary is not None:
            record['directory_absent'] = not temporary.exists()
            for row in record['files']:
                row['result'] = 'REMOVED_ABSENT' if not Path(row['path']).exists() else 'PRESENT'
            record['status'] = ('COMPLETE' if record['directory_absent'] and
                                all(row['result']=='REMOVED_ABSENT' for row in record['files']) else 'PARTIAL')
            record['logical_bytes_removed'] = sum(row['bytes'] for row in record['files'] if row['result']=='REMOVED_ABSENT')
            receipt.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
            SCRATCH_RECEIPTS.append({'path': str(receipt), 'bytes': receipt.stat().st_size, 'sha256': _digest(receipt)})

# Reuse the existing original-Lua bootstrap, independent catalog and input
# helpers. Insert the new queue contract before the current scene is loaded.
_prefix = base.HARNESS[:base.HARNESS.index("phase='open-original-menu'")]
_bootstrap, _helpers = _prefix.split("run(source.scene..", 1)
HARNESS = _bootstrap + r'''
local overwriteCalls,requests={},{}
local overwriteCapabilityQueries=0
local oldNative=env.ZeroSisUiNative
env.ZeroSisUiNative=function(op,...)
 if op=='saveMenuDeleteSupported' then
  check(select('#',...)==0,'Delete capability arity changed');return data.supported
 end
 if op=='saveMenuOverwriteSupported' then
  check(select('#',...)==0,'Overwrite capability arity changed')
  overwriteCapabilityQueries=overwriteCapabilityQueries+1
  if data.case=='invalid-capability' then return 1 end
  return data.overwriteSupported
 end
 if op=='saveMenuNameAvailable' then
  local name=...
  for _,row in ipairs(data.files) do
   if not deleted[row.path] and string.upper(row.path:match('([^\\]+)%.zssave$'))==string.upper(name) then return false end
  end
  return #unicodeChars(name)>0 and #unicodeChars(name)<=32
 end
 if op=='saveMenuOverwrite' then
  check(select('#',...)==2,'Overwrite queue arity changed')
  local name,path=...
  local row=rowFor(path)
  check(data.overwriteSupported and row.known and allowed(path) and selectedPath()==path,
   'Overwrite queue received an unknown, stale, unlisted or different selection')
  check(env.Controls.DeleteConfirm:IsHidden(),'Stock OnYes did not hide before overwrite')
  check(name==env.Controls.NameBox:GetText() and
   string.upper(name)==string.upper(path:match('([^\\]+)%.zssave$')),
   'Overwrite queue lost the exact requested name/path binding')
  overwriteCalls[#overwriteCalls+1]={name=name,path=path}
  if data.case=='native-fault' then error('Mock overwrite queue failed before admission') end
  check(#requests==0,'Overwrite queue admitted a duplicate request')
  requests[#requests+1]={kind='Overwrite',name=name,path=path,observation=captured(row)}
  -- Production saveMenuOverwrite returns zero Lua results.
  return
 end
 if op=='saveMenuSave' then
  local name=...
  check(select('#',...)==1 and oldNative('saveMenuNameAvailable',name),'New save path lost its availability gate')
  check(#requests==0,'New save queue admitted a duplicate request')
  requests[#requests+1]={kind='Save',name=name};return
 end
 if op=='saveMenuClose' then
  oldNative(op,...);requests[#requests+1]={kind='Close'};return
 end
 return oldNative(op,...)
end
''' + "run(source.scene.." + _helpers + r'''
local function meta() return metadata(snapshot()) end
local function observeOverwrite(stage)
 local value=snapshot();if data.capture then captures[stage]=value end;return value
end
local function showOverwrite(stage)
 click('SaveButton')
 check(not env.Controls.DeleteConfirm:IsHidden(),'Original OnSave did not open its confirmation')
 check(env.Controls.Message:GetText()==localized('TXT_KEY_OVERWRITE_TXT'),'Original overwrite message changed')
 local value=observeOverwrite(stage or 'confirmation');local m=metadata(value)
 check(m.confirmationOp=='overwrite' and m.overwriteConfirmationArmed and not m.deleteConfirmationArmed,
  'Shared confirmation did not arm overwrite exclusively')
 check(not env.Controls.Yes:IsDisabled(),'Eligible overwrite has no original Yes target')
 check(not ui.DispatchLeftClick(key(env.Controls.Yes),env.Mouse.eRClick),'Right click acquired overwrite approval')
 check(not ui.DispatchLeftClick(key(env.Controls.NameBox)),'Overwrite confirmation leaked editor input')
 check(not ui.DispatchLeftClick(key(env.Controls.SaveButton)),'Overwrite confirmation leaked SaveButton input')
 local before=#overwriteCalls
 check(ui.DispatchKeyDown(env.Keys.VK_RETURN) and #overwriteCalls==before,'Enter approved an overwrite confirmation')
 return value
end
local function typeName(name)
 click('NameBox');ui.DispatchKeyDown(35)
 for _=1,#unicodeChars(env.Controls.NameBox:GetText()) do check(ui.DispatchKeyDown(8),'NameBox backspace failed') end
 for _,ch in ipairs(unicodeChars(name)) do
  local bytes={ch:byte(1,-1)};local scalar=bytes[1]
  if #bytes==2 then scalar=(bytes[1]-192)*64+bytes[2]-128
  elseif #bytes==3 then scalar=(bytes[1]-224)*4096+(bytes[2]-128)*64+bytes[3]-128
  elseif #bytes==4 then scalar=(bytes[1]-240)*262144+(bytes[2]-128)*4096+(bytes[3]-128)*64+bytes[4]-128 end
  check(ui.DispatchTextInput(scalar),'NameBox text input failed')
 end
end
local function finishOverwrite()
 if snapshot().active then ui.CloseSaveMenu() end
 local closed=observeOverwrite('closed')
 check(not closed.active and closed.timerSemaphore==0 and #ui.GetInputTargets()==0,'Closed overwrite retained input/timer')
 return json({status='PASS_ORIGINAL_SAVE_OVERWRITE_LUA_FIXTURE',case=data.case,checks=checks,
  overwriteCalls=overwriteCalls,requests=requests,deleteCalls=deleteCalls,
  capabilityQueries=overwriteCapabilityQueries,timerChanges=timerChanges,
  snapshots=data.capture and captures or nil,originalLuaExecuted=true,
  realArchiveWrites=0,realArchiveDeletes=0,nativeHostOrGameCoreExecuted=false,
  fixtureFaultRecoveryIsNativeAcceptance=false})
end
phase='open-original-save-menu'
ui.OpenSaveMenu()
local opened=metadata(observeOverwrite('opened'))
check(overwriteCapabilityQueries==1,'Overwrite capability was not bound exactly once')
check(opened.localOverwriteImplemented and opened.localOverwriteBackendBound==data.overwriteSupported,
 'Overwrite snapshot capability differs from its binding')
check(opened.confirmationOp=='none' and not opened.overwriteConfirmationArmed,'Open acquired an overwrite grant')
local first,second,unknown=data.files[1].path,data.files[2].path,data.files[3].path
phase='select-original-row'
selectPath(first)
local selected=metadata(observeOverwrite('selected'))
check(not selected.nameAvailable,'Existing row incorrectly became a new available name')
if data.case=='unsupported' then
 check(not selected.overwriteEligible and not selected.saveActionAvailable and env.Controls.SaveButton:IsDisabled(),
  'Unsupported overwrite enabled SaveButton')
 check(not ui.DispatchLeftClick(key(env.Controls.SaveButton)),'Unsupported overwrite accepted SaveButton')
 rejects(function() env.UI.SaveGame('Alpha') end,'unsupported direct existing-name save')
 check(#overwriteCalls==0,'Unsupported overwrite reached its queue')
 return finishOverwrite()
end
check(selected.overwriteEligible and selected.saveActionAvailable and not env.Controls.SaveButton:IsDisabled(),
 'Known existing row did not acquire save admission')
if data.case=='unknown-header' then
 selectPath(unknown)
 check(not meta().overwriteEligible and env.Controls.SaveButton:IsDisabled(),'Unknown header enabled overwrite')
 check(not ui.DispatchLeftClick(key(env.Controls.SaveButton)),'Unknown header accepted SaveButton')
 check(#overwriteCalls==0,'Unknown header reached overwrite queue')
 observeOverwrite('unknown');return finishOverwrite()
end
if data.case=='unlisted' then
 local _,_,entry=findEntry(first)
 entry.FileName=data.foreign
 check(not meta().overwriteEligible and not meta().overwriteConfirmationArmed,'Unlisted path retained overwrite eligibility')
 rejects(function() env.UI.SaveGame('Alpha') end,'unlisted direct existing-name save')
 check(#overwriteCalls==0,'Unlisted path reached overwrite queue')
 entry.FileName=first;return finishOverwrite()
end
if data.case=='entered' then
 typeName('alpha')
 check(env.g_SelectedEntry==nil and meta().overwriteEligible and not meta().nameAvailable,
  'Typed case-insensitive existing name lost its original matching rule')
 check(ui.DispatchKeyDown(env.Keys.VK_RETURN),'NameBox Enter did not call original OnEditBoxChange')
 local m=metadata(observeOverwrite('entered-confirmation'))
 check(m.confirmationOp=='overwrite' and m.overwriteConfirmationArmed and not m.deleteConfirmationArmed,
  'NameBox Enter bypassed original overwrite confirmation')
 check(#overwriteCalls==0,'NameBox Enter executed overwrite without Yes')
 check(ui.DispatchKeyDown(env.Keys.VK_RETURN) and #overwriteCalls==0,'Second Enter approved overwrite')
 click('Yes')
 check(#overwriteCalls==1 and overwriteCalls[1].name=='alpha' and overwriteCalls[1].path==first,
  'Original Yes did not queue the exact typed name and selected path')
 return finishOverwrite()
end
if data.case=='native-fault' then
 showOverwrite('fault-confirmation')
 rejects(function() click('Yes') end,'native overwrite queue fault')
 local m=metadata(observeOverwrite('faulted'))
 check(m.confirmationOp=='none' and not m.overwriteConfirmationArmed and not m.deleteConfirmationArmed,
  'Native fault retained a confirmation grant')
 rejects(function() env.UI.SaveGame('Alpha') end,'retry without fresh confirmation')
 check(#overwriteCalls==1 and #requests==0,'Native fault reused or admitted the failed queue grant')
 return finishOverwrite()
end
phase='cancel-original-overwrite'
showOverwrite('confirmation')
click('No');check(env.Controls.DeleteConfirm:IsHidden() and #overwriteCalls==0,'No did not only cancel overwrite')
observeOverwrite('cancelled')
showOverwrite('escape-confirmation');check(ui.DispatchKeyDown(env.Keys.VK_ESCAPE),'Escape was rejected')
check(snapshot().active and env.Controls.DeleteConfirm:IsHidden() and meta().confirmationOp=='none' and #overwriteCalls==0,
 'Escape did not cancel only the original confirmation')
phase='revoke-name-and-selection-and-list-changes'
showOverwrite('name-confirmation')
env.Controls.NameBox:SetText('OtherNewName');env.Controls.NameBox:SetText('Alpha')
check(not meta().overwriteConfirmationArmed and env.Controls.Yes:IsDisabled(),'Name round trip reused a confirmation grant')
click('No');selectPath(first)
showOverwrite('selection-confirmation')
local _,_,other=findEntry(second);env.SetSelected(other)
check(not meta().overwriteConfirmationArmed and env.Controls.Yes:IsDisabled(),'Selection change retained overwrite approval')
click('No');selectPath(first)
showOverwrite('list-confirmation');env.SetupFileButtonList()
check(not meta().overwriteConfirmationArmed and env.Controls.Yes:IsDisabled(),'Catalog refresh retained overwrite approval')
click('No');selectPath(first)
phase='deny-direct-callback-and-cross-operation'
env.OnSave();check(not meta().overwriteConfirmationArmed and env.Controls.Yes:IsDisabled(),
 'Direct original OnSave acquired overwrite admission')
rejects(env.OnYes,'direct original OnYes')
selectPath(first);showOverwrite('unconfirmed-direct-yes')
rejects(env.OnYes,'direct Yes without owned mouse admission')
selectPath(first)
showOverwrite('cross-operation-confirmation')
env.OnDelete()
check(meta().confirmationOp=='none' and env.Controls.Yes:IsDisabled(),'Direct delete borrowed an overwrite grant')
rejects(function() env.UI.DeleteSavedGame(first) end,'cross-operation delete without own approval')
click('No');selectPath(first);showDelete()
env.OnSave()
check(meta().confirmationOp=='none' and env.Controls.Yes:IsDisabled(),'Direct save borrowed a delete grant')
rejects(env.OnYes,'cross-operation overwrite without own approval')
selectPath(first)
phase='commit-original-overwrite-once'
showOverwrite('commit-confirmation')
click('Yes')
check(#overwriteCalls==1 and overwriteCalls[1].name=='Alpha' and overwriteCalls[1].path==first,
 'Original Yes did not queue exact existing selection once')
check(#deleteCalls==0,'Overwrite used the delete service')
check(#requests==2 and requests[1].kind=='Overwrite' and requests[2].kind=='Close',
 'Original overwrite did not retain Overwrite then Close handoff order')
check(not ui.DispatchLeftClick(key(env.Controls.Yes)),'Closed context accepted duplicate Yes')
rejects(function() env.UI.SaveGame('Alpha') end,'duplicate direct existing-name save')
check(#overwriteCalls==1,'Duplicate approval reached overwrite queue')
return finishOverwrite()
end
local ok,result=xpcall(exercise,function(message)
 return 'Owned-overwrite case='..data.case..' phase='..phase..': '..tostring(message)
end)
assert(ok,result)
return result
'''


def verify_component(*, cases=('selected', 'entered', 'unsupported', 'unknown-header', 'unlisted', 'native-fault'),
                     include_snapshot=False):
    valid = {'selected', 'entered', 'unsupported', 'unknown-header', 'unlisted', 'native-fault', 'invalid-capability'}
    if any(case not in valid for case in cases):
        raise ValueError('Unknown original overwrite fixture')
    includes = {'InstanceManager': 'Assets/UI/InstanceManager.lua', 'IconSupport': 'Assets/UI/IconSupport.lua',
                'SupportFunctions': 'Assets/UI/SupportFunctions.lua', 'UniqueBonuses': base.UNIQUE_BONUSES_LUA,
                'InfoTooltipInclude': 'Assets/DLC/Expansion2/UI/InGame/InfoTooltipInclude.lua',
                'FLuaVector': 'Assets/Gameplay/Lua/FLuaVector.lua', 'MapUtilities': 'Assets/Gameplay/Lua/MapUtilities.lua'}
    paths = {name: base.GAME / relative for name, relative in includes.items()}
    paths.update(scene=PROJECT / 'Source/Host/UiScene.lua', input=PROJECT / 'Source/Presentation/UiPresentationInput.lua',
                 stock=base.GAME / base.SAVE_MENU_LUA, xml=base.GAME / base.SAVE_MENU_XML,
                 lua=PROJECT / 'Build/SharedLuaRuntime/Lua/ZeroSisLua51_x64.dll')
    before = {name: _digest(path) for name, path in paths.items()}
    if before['lua'] != base.LUA_SHA256:
        raise AssertionError('Approved headless Lua provider changed')
    source = {name: paths[name].read_text(encoding='utf-8-sig') for name in (*includes, 'scene', 'input', 'stock')}
    release = json.loads((PROJECT / 'Play/EarlyAccess/release.json').read_text(encoding='utf-8-sig'))
    database = PROJECT / 'Build/InteractiveGameRuntime' / release['runtime_id'] / 'rules.db'
    names = ('Leaders', 'Civilization_Leaders', 'Civilizations', 'PlayerColors', 'Colors', 'IconTextureAtlases',
             'Worlds', 'HandicapInfos', 'GameSpeeds', 'Eras', 'MapScripts', 'Map_Sizes', 'Maps', 'GameOptions')
    with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        tables = {name: [{key: value for key, value in dict(row).items() if value is not None}
                         for row in connection.execute('SELECT * FROM "' + name + '"')] for name in names}
    civ = next(row for row in tables['Civilizations'] if row['Type'] == 'CIVILIZATION_ROME')
    current = dict(PlayerCivilization=civ['ID'], GameSpeed=2, StartEra=0, TurnNumber=7, Difficulty=3, WorldSize=3,
                   MapScript='Assets/Maps/Continents.lua', LeaderName='저장된 지도자', CivilizationName='저장된 문명',
                   CurrentEra=0, GameType=base.sdk_game_types()['GAME_SINGLE_PLAYER'])
    tags = sorted(set(re.findall(r'TXT_KEY_[A-Za-z0-9_]+', '\n'.join(source.values()) + json.dumps(tables) +
                                 paths['xml'].read_text(encoding='utf-8-sig'))))
    locale = {}
    with closing(sqlite3.connect(database.with_name('localization.db').as_uri() + '?mode=ro', uri=True)) as connection:
        for language in ('en_US', 'ko_KR'):
            for offset in range(0, len(tags), 500):
                batch = tags[offset:offset + 500]
                locale.update(connection.execute('SELECT Tag,Text FROM LocalizedText WHERE Language=? AND Tag IN (' +
                                                  ','.join('?' for _ in batch) + ')', [language, *batch]))
    inline = json.loads((PROJECT / 'evidence/ui_popup/assets/inline_icons.json').read_text(encoding='utf8'))['icons']
    files = [dict(path=r'C:\owned\session\Alpha.zssave', known=True, high=2097152, low=0, display='2026-10-16 01:00'),
             dict(path=r'C:\owned\session\Beta.zssave', known=True, high=2097152, low=1, display='2026-10-16 01:01'),
             dict(path=r'C:\owned\session\Unknown.zssave', known=False, high=2097151, low=0, display='2026-10-16 00:59')]
    results, temporary_files, snapshots = [], [], {}
    temporary = None
    try:
        with recorded_style_directory() as (temporary, temporary_files):
            tree = base.save_menu_control_tree(ET.parse(paths['xml']).getroot())
            tree.update(contextName='SaveMenu', popupKind='SaveMenu')
            styles = base.production_style_defaults(temporary, tree)
            tree.update(styleDefaults=styles['controls'], styleDefaultsSource=styles['source'], styleDefaultsPolicy=styles['policy'])
            tree['fontMetrics'] = base.production_font_metrics(tree, inline)
            for case in cases:
                data = dict(tables=tables, locale=locale, current=current, gameTypes=base.sdk_game_types(),
                            lockMods=next(row['ID'] for row in tables['GameOptions'] if row['Type']=='GAMEOPTION_LOCK_MODS'),
                            menu='SaveMenu', case=case, supported=case != 'unlisted', overwriteSupported=case != 'unsupported', files=files,
                            capture=True, foreign=r'C:\foreign\not-owned.zssave')
                assembled = HARNESS.replace('@@SOURCES@@', base.lua_value(source)).replace('@@LAYOUT@@', base.lua_value(tree)).replace('@@DATA@@', base.lua_value(data))
                observed = base.execute_lua(assembled)
                states = observed.pop('snapshots', {})
                for stage, snapshot in states.items():
                    try:
                        base.save_menu_contract(snapshot, closed=stage == 'closed')
                    except Exception as error:
                        raise AssertionError(f'Overwrite compositor contract {case}/{stage}: {error}') from error
                observed['compositorContractStages'] = sorted(states)
                if include_snapshot:
                    snapshots[case] = states
                results.append(observed)
    finally:
        changed = [name for name, path in paths.items() if _digest(path) != before[name]]
        if changed:
            raise AssertionError('Overwrite fixture changed protected inputs: ' + ', '.join(changed))
    if temporary is None or temporary.exists():
        raise AssertionError('Overwrite fixture did not remove temporary styles')
    coverage = {
        'selected': ['original SaveButton to OnSave to OnYes mouse approval', 'No and Escape cancellation',
                     'unapproved modal Enter', 'name round trip revocation', 'selection change revocation',
                     'catalog refresh revocation', 'direct callbacks rejected', 'delete/overwrite cross-operation rejection',
                     'duplicate approval rejected', 'Overwrite then Close ordering'],
        'entered': ['original NameBox Enter to OnEditBoxChange(true) to OnSave', 'case-folded existing-name match',
                    'second Enter cannot approve', 'exact typed name/path queued only by original mouse Yes'],
        'unsupported': ['separate false overwrite capability', 'existing name remains unavailable for new save'],
        'unknown-header': ['unknown-header target cannot overwrite'],
        'unlisted': ['private listed-path observation rejects mutated unlisted selection', 'overwrite independent of deletion capability'],
        'native-fault': ['native queue exception before admission', 'single-use dispatch consumed', 'no retry without fresh confirmation'],
    }
    result = {'status': 'PASS_ORIGINAL_OWNED_SAVE_OVERWRITE_LUA_FIXTURES', 'checks': sum(row['checks'] for row in results),
              'cases': results, 'source_sha256': before, 'original_sources_unchanged': True, 'temporary_styles_removed': True,
              'coverage_mapping': {case: coverage.get(case, ['invalid typed capability rejected']) for case in cases},
              'scratch_cleanup_receipt': SCRATCH_RECEIPTS[-1],
              'temporary_cleanup': [{**row, 'result': 'REMOVED_ABSENT' if not Path(row['path']).exists() else 'PRESENT'} for row in temporary_files],
              'native_host_or_gamecore_executed': False, 'retail_user_state_accessed': False,
              'real_archive_writes': 0, 'real_archive_deletes': 0}
    if include_snapshot:
        result['snapshots'] = snapshots
    return result
