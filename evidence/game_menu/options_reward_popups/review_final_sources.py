"""Read-only byte/source review of the final reward-option embedding."""
from __future__ import annotations
import ast
from datetime import datetime,timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import sys

sys.dont_write_bytecode=True
STAGE=Path(__file__).absolute().parent
PROJECT=STAGE.parents[2]
def sha(raw):return hashlib.sha256(raw).hexdigest()
def read(path):return json.loads(Path(path).read_bytes())
def artifact(path):
    path=Path(path).absolute();before=os.stat(path,follow_symlinks=False)
    assert not before.st_file_attributes&0x400,str(path)
    raw=path.read_bytes();after=os.stat(path,follow_symlinks=False)
    assert (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_file_attributes)==(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_file_attributes)
    return dict(path=str(path),bytes=len(raw),sha256=sha(raw),file_identity=[after.st_dev,after.st_ino],mtime_ns=after.st_mtime_ns,file_attributes=after.st_file_attributes,links=after.st_nlink)
def checked(row):
    now=artifact(row['path']);assert now['sha256']==row['sha256'],row['path']
    for key in ('bytes','file_identity','mtime_ns','file_attributes'):
        if key in row:assert now[key]==row[key],(row['path'],key)
    return now
def arrays(raw):
    text=raw.decode('ascii');token='static const char '
    at=text.index(token);prefix=text[:at];values=[]
    grammar=re.compile(r'static const char ([A-Za-z][A-Za-z0-9_]*)\[\]=\n((?:"(?:\\x[0-9a-f]{2})*"\n?)+);\n')
    while text.startswith(token,at):
        match=grammar.match(text,at);assert match is not None
        name,literals=match.groups();values.append((name,bytes.fromhex(''.join(re.findall(r'\\x([0-9a-f]{2})',literals)))));at=match.end()
    assert len(values)==len(dict(values))==74
    return prefix,values,text[at:]
def assignments(source,name):
    tree=ast.parse(source)
    values=[ast.literal_eval(node.value) for node in tree.body if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in node.targets)]
    assert len(values)==1;return values[0]


def main():
    target=STAGE/'independent_source_review_final.json';assert not target.exists()
    embed=read(STAGE/'embedded_options_revision2.result.json');original=read(STAGE/'embedded_options.result.json')
    binding=read(STAGE/'binding/4d2aac9a11814351/result.json');contract_delivery=read(STAGE/'contract/delivery.json')
    assert binding['status']=='PASS_COMMITTED_REWARD_HOST_BINDING_LEGACY_REGRESSION_AND_RETAINED_LUA'
    assert binding['compiler_and_linker_warnings']==0 and binding['sdk_rules_and_dll_unchanged'] and binding['strict_committed_only_publication_verified']
    binding_rows=[checked(row) for row in binding['inputs_before']]
    checked(embed['generated_header']);checked(embed['prepared_report'])
    assert embed['generated_header']['sha256']=='561af68d28ab76236c68f34b8605d0cd9bac83d89fc1f032cae523bfe8172e16'
    old_header_ref=checked(original['header_recovery']);old_prepared_ref=checked(original['prepared_recovery'])
    old_header=gzip.decompress(Path(old_header_ref['path']).read_bytes());new_header=Path(embed['generated_header']['path']).read_bytes()
    op,ov,ot=arrays(old_header);np,nv,nt=arrays(new_header)
    assert op==np and ot==nt and [name for name,_ in ov]==[name for name,_ in nv]
    old_by,new_by=dict(ov),dict(nv);changed=[name for name,before in ov if new_by[name]!=before]
    assert set(changed)=={'MenuOptionsLayout','TouchHelpLayout','ZeroSisUiScene'}
    assert old_by['SharedFontMetrics']==new_by['SharedFontMetrics']
    mapping=[('host_ui_runtime','Source/Host/UiScene.lua',None),('host_ui_input_addendum','Source/Presentation/UiPresentationInput.lua',None),
        ('host_ui_city_view_addendum','Source/Presentation/UiCityView.lua','hasRetainedCityUi'),
        ('host_ui_unit_panel_addendum','Source/Presentation/UiUnitPanel.lua','hasRetainedUnitUi'),
        ('host_ui_social_policy_addendum','Source/Presentation/UiSocialPolicy.lua','hasRetainedSocialPolicyUi'),
        ('host_ui_economic_overview_addendum','Source/Presentation/UiEconomicOverview.lua','hasRetainedEconomicUi'),
        ('host_ui_action_info_addendum','Source/Presentation/UiActionInfoPanel.lua','hasRetainedActionInfoUi'),
        ('host_ui_notification_addendum','Source/Presentation/UiNotificationPanel.lua','hasRetainedNotificationUi'),
        ('production_command_guard','Source/Host/ProductionCommandGuard.lua',None),('research_command_guard','Source/Host/ResearchCommandGuard.lua',None),
        ('host_ui_menu_options_addendum','Source/Presentation/UiMenuOptions.lua',None),('host_ui_map_menu_addendum','Source/Presentation/UiMapMenu.lua',None)]
    lua_refs=[artifact(PROJECT/relative) for _,relative,_ in mapping]
    sources={key:(PROJECT/relative).read_bytes() for key,relative,_ in mapping}
    scene=sources['host_ui_runtime']+b'\n'+sources['host_ui_input_addendum']
    for key,_,guard in mapping[2:8]:scene+=b'\nif '+guard.encode()+b' then\n'+sources[key]+b'\nend\n'
    scene+=b'\n'+sources['host_ui_menu_options_addendum']+b'\n'+sources['host_ui_map_menu_addendum']
    assert scene==new_by['ZeroSisUiScene']
    assert sources['production_command_guard']==new_by['ProductionCommandGuard'] and sources['research_command_guard']==new_by['ResearchCommandGuard']
    assert sha(sources['host_ui_menu_options_addendum'])=='b75f00e5476cb7f9545187215d5b777414bb05dd66ba5bc02ae2b74dde684f19'
    old_prepared=json.loads(gzip.decompress(Path(old_prepared_ref['path']).read_bytes()));prepared=read(embed['prepared_report']['path'])
    old_trees,new_trees=old_prepared['xml_control_trees'],prepared['xml_control_trees'];assert set(old_trees)==set(new_trees) and len(new_trees)==30
    for name,tree in new_trees.items():
        before=dict(old_trees[name]);after=dict(tree)
        if name in ('MenuOptionsLayout','TouchHelpLayout'):before.pop('menuOptions');after.pop('menuOptions')
        assert before==after,name
    keys=['noBasicHelp','hideTouchHelp','uiCueVolumePercent','windowWidth','windowHeight','fullscreen','vsync','policyInfo','noRewardPopups']
    caps=['noBasicHelp','noRewardPopups','uiCueVolumePercent','windowWidth','windowHeight','fullscreen','vsync','policyInfo']
    options=(PROJECT/'tools/menu_options_assets.py').read_text('utf8');reader=(PROJECT/'tools/ui_pixel_scene.py').read_text('utf8')
    lua=sources['host_ui_menu_options_addendum'].decode('utf8');cpp=(PROJECT/'Source/Host/MenuOptionsContract.h').read_text('utf8')
    assert list(assignments(options,'PRIVATE_KEYS'))==keys
    for name in ('MenuOptionsLayout','TouchHelpLayout'):
        metadata=new_trees[name]['menuOptions'];assert metadata['privateKeys']==keys
        assert metadata['privateSettingsSchema']=='ZEROSIS_PRIVATE_MENU_OPTIONS_V3'
        assert metadata['readablePrivateSettingsSchemas']==['ZEROSIS_PRIVATE_MENU_OPTIONS_V1','ZEROSIS_PRIVATE_MENU_OPTIONS_V2','ZEROSIS_PRIVATE_MENU_OPTIONS_V3']
    match=re.search(r"for _,key in ipairs\(\{([^}]+)\}\) do\s+supported\[key\]",lua);assert match and re.findall("'([^']+)'",match.group(1))==caps
    fn=next(node for node in ast.parse(reader).body if isinstance(node,ast.FunctionDef) and node.name=='private_menu_contract')
    cap_comparisons=[node for node in ast.walk(fn) if isinstance(node,ast.Compare) and isinstance(node.left,ast.Call) and isinstance(node.left.func,ast.Name) and node.left.func.id=='set' and any(isinstance(arg,ast.Name) and arg.id=='caps' for arg in node.left.args)]
    assert len(cap_comparisons)==1 and set(ast.literal_eval(cap_comparisons[0].comparators[0]))==set(caps)
    assert "local gameSupported=supported.noBasicHelp or supported.noRewardPopups" in lua
    assert "any(caps[key] for key in ('noBasicHelp','noRewardPopups'))" in reader
    model=(PROJECT/'Source/Host/MenuFrontEndOptionsModel.h').read_text('utf8')
    assert 'if(page==Page::Game)return Supports("noBasicHelp") || Supports("noRewardPopups");' in model
    popup="if id:find('Popup',1,true) and not (id=='NoRewardPopupsCheckbox' and\n          state(handle).kind=='CheckBox' and supported.noRewardPopups) then handle:SetHide(true) end"
    assert popup in lua and lua.count("id=='NoRewardPopupsCheckbox'")==1
    assert "{'GraphicsChangedPopup','Countdown','CountdownPopup','ResolutionConfirmPopup'}" in lua
    assert 'if(version>=2)v.policyInfo=boolean("policyInfo");' in cpp and 'if(version>=3)v.noRewardPopups=boolean("noRewardPopups");' in cpp
    assert 'Canonical(v,version)!=bytes' in cpp and 'Encode(const MenuOptionsValues& v) {return Canonical(v,3);}' in cpp
    assert 'committed_=candidate;PublishNoRewardPopups();' in cpp and 'committed_=resolutionCandidate_;PublishNoRewardPopups();ClearPreview();' in cpp
    reviewed=[artifact(PROJECT/name) for name in ['Source/Host/MenuOptionsContract.h','Source/Host/MenuOptionsStore.h','Source/Host/MenuOptionsHostBinding.h','Source/Host/HostServices.h','Source/Host/MenuFrontEndOptionsModel.h','Source/Host/MenuFrontEndOptionsView.h','Source/Host/MenuRewardOptionsLayout.h','tools/civ5_ui_assets.py','tools/menu_options_assets.py','tools/ui_pixel_scene.py','evidence/game_menu/options_reward_popups/refresh_embedded_options.py']]
    for row in binding_rows+lua_refs+reviewed:checked(row)
    result=dict(schema='zerosis.reward_options.final_independent_source_review.v1',status='PASS_FINAL_SOURCE_EMBEDDING_AND_STRICT_PREFERENCE_READER_REVIEW',utc=datetime.now(timezone.utc).isoformat(),
        reviewed_sources=reviewed,actual_current_host_lua_sources=lua_refs,binding_success=artifact(STAGE/'binding/4d2aac9a11814351/result.json'),binding_input_rows_reverified=len(binding_rows),
        embedding_success=artifact(STAGE/'embedded_options_revision2.result.json'),current_header=artifact(embed['generated_header']['path']),current_prepared=artifact(embed['prepared_report']['path']),
        baseline_header_backup=old_header_ref,baseline_prepared_backup=old_prepared_ref,catalog_entries=74,original_layouts=30,changed_payloads=changed,unchanged_payloads=71,
        exact_current_scene_byte_combination=True,scene_source_files=10,separate_original_guard_payloads=2,host_lua_source_inventory=12,
        unchanged_audio_registry_tail_sha256=sha(nt.encode('ascii')),shared_font_payload_unchanged=True,original_declarations_and_other_layout_metadata_unchanged=True,
        private_keys=keys,capabilities=caps,difference='hideTouchHelp is a separate original TouchHelp preference, not a missing options capability',
        popup_exception='Only original ID NoRewardPopupsCheckbox with CheckBox kind and supported.noRewardPopups true is exempt; unsupported popup hiding remains.',
        legacy_read='Current canonical V1/V2 decoding code and successful controlled evidence match current inputs; new field defaults false and V3 writing is explicit changed commit only.',
        committed_publication='Session release-store follows successful persistence and committed assignment; SDK uses confirmed atomic acquire load; cache/staging/preview do not publish the draft.',
        findings=[],hardlink_limit='A legacy hardlink-creation probe was not executed past Win32 error5; this review does not convert that branch to PASS.',
        source_modified=False,source_generator_executed=False,lua_or_feature_tests_executed=False,host_sdk_clr_hwnd_gpu_audio_or_game_executed=False,
        limitations=['Actual five-translation-unit Host compilation/link, PE attestation and new frozen runtime/Python binding audit remain separate root-agent gates.','Source review and prior controlled Lua evidence do not prove native UI/gameplay/save/mod/multicore acceptance.'])
    with target.open('x',encoding='utf8') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(status=result['status'],artifact=artifact(target),binding_rows=len(binding_rows),changed=changed)))


if __name__=='__main__':main()
