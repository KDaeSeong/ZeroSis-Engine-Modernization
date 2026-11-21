"""Refresh three existing text payloads only, without extraction or native code."""
from __future__ import annotations
import argparse
from copy import deepcopy
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

sys.dont_write_bytecode=True
STAGE=Path(__file__).absolute().parent
PROJECT=STAGE.parents[2]
sys.path.insert(0,str(PROJECT/'tools'))
import build_exit_confirm_host as common
import refresh_exit_confirm_ui_assets as reuse
import prepare_ui_popup_assets as preparer
import menu_options_assets as options

HEADER=PROJECT/'Source/Host/UiPopupAssets.generated.h'
PREPARED=PROJECT/'evidence/ui_popup/assets/prepared.json'
EXTRA=(('host_ui_menu_options_addendum','Source/Presentation/UiMenuOptions.lua'),
       ('host_ui_map_menu_addendum','Source/Presentation/UiMapMenu.lua'))


def digest(raw):return hashlib.sha256(raw).hexdigest()
def encoded(value):return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode('utf8')
def write_new(path,raw):
    with path.open('xb') as stream:stream.write(raw)
def baseline(path):
    relative=path.relative_to(PROJECT).as_posix().replace('/','__')
    matches=[item for item in (STAGE/'source_before').glob(relative+'.*.gz')
        if gzip.decompress(item.read_bytes())==path.read_bytes()]
    assert len(matches)==1,str(path)
    return common.artifact(matches[0])


def prepare(revision):
    assert HEADER.stat().st_nlink==PREPARED.stat().st_nlink==1
    old_header,old_prepared=HEADER.read_bytes(),PREPARED.read_bytes()
    backups=[baseline(path) for path in (HEADER,PREPARED)]
    old=json.loads(old_prepared)
    assert old['renderer_verified'] is False and len(old['xml_control_trees'])==30
    arrays,tail=reuse.parse_text_arrays(old_header,preparer)
    assert len(arrays)==74 and len(dict(arrays))==74
    old_by_name=dict(arrays)
    sources,host_refs={},{}
    paths=[Path(__file__).absolute(),HEADER,PREPARED,PROJECT/'tools/menu_options_assets.py',
        PROJECT/'tools/civ5_ui_assets.py',PROJECT/'tools/refresh_exit_confirm_ui_assets.py',
        PROJECT/'tools/prepare_ui_popup_assets.py']
    assert common.artifact(PROJECT/'tools/refresh_exit_confirm_ui_assets.py')['sha256']=='4a2ed7b2282642f948cc9c3042d46d526548e033db94a25fd88cdcef390e8618'
    for key,relative in [(key,relative) for key,relative,_ in reuse.HOST_LUA]+list(EXTRA):
        path=PROJECT/relative;record=common.artifact(path);paths.append(path)
        if key!='host_ui_menu_options_addendum':assert old[key]['sha256']==record['sha256'],key
        sources[key]=path.read_bytes();host_refs[key]=record
    scene=reuse.scene_bytes(sources)+b'\n'+sources[EXTRA[0][0]]+b'\n'+sources[EXTRA[1][0]]
    assert sources['production_command_guard']==old_by_name['ProductionCommandGuard']
    assert sources['research_command_guard']==old_by_name['ResearchCommandGuard']
    updated=deepcopy(old);changes={'ZeroSisUiScene':scene}
    for name,relative,kind in [('MenuOptionsLayout','Assets/UI/Options/OptionsMenu.xml','MenuOptions'),
                               ('TouchHelpLayout','Assets/UI/TouchControlsMenu.xml','TouchHelp')]:
        path=PROJECT/'Source/Assets/UI'/relative;paths.append(path)
        generated=options.menu_options_control_tree(ET.fromstring(path.read_bytes()),kind)
        existing=updated['xml_control_trees'][name]
        for field in ('kind','attributes','children','contextName','popupKind'):assert generated[field]==existing[field],(name,field)
        for field in ('originalLua','originalXml'):
            source=Path(generated['menuOptions'][field]['path']);paths.append(source)
            assert common.artifact(source)['sha256']==generated['menuOptions'][field]['sha256']
        existing['menuOptions']=generated['menuOptions']
        assert generated['menuOptions']['privateSettingsSchema']=='ZEROSIS_PRIVATE_MENU_OPTIONS_V3'
        assert generated['menuOptions']['privateKeys'][-1]=='noRewardPopups'
        changes[name]=('ZeroSisUiLayout='+preparer.lua_value(existing)+'\n').encode('ascii')
        policy='menu_options' if kind=='MenuOptions' else 'touch_help'
        updated[policy]['metadata']=deepcopy(existing['menuOptions'])
    handlers=updated['xml_control_trees']['MenuOptionsLayout']['menuOptions']['originalSupportedHandlers']['functions']
    assert sum(row['name']=='OnNoRewardPopupsCheckbox' for row in handlers)==1
    texts=[(name,changes.get(name,raw)) for name,raw in arrays]
    changed=[name for (name,before),(_,after) in zip(arrays,texts) if before!=after]
    assert set(changed)==({'ZeroSisUiScene','MenuOptionsLayout','TouchHelpLayout'} if revision==1 else {'ZeroSisUiScene'})
    new_header=(reuse.PREFIX+''.join('static const char '+name+'[]=\n'+preparer.cpp_literal(raw)+';\n' for name,raw in texts)+tail).encode('ascii')
    roundtrip,new_tail=reuse.parse_text_arrays(new_header,preparer)
    assert roundtrip==texts and new_tail==tail
    for key,row in host_refs.items():updated[key]={field:row[field] for field in ('path','sha256')}
    updated['base_builder']=deepcopy(old['builder'])
    updated['builder']={field:common.artifact(Path(__file__).absolute())[field] for field in ('path','sha256')}
    updated['compiled_assets']=dict(path=str(HEADER),sha256=digest(new_header))
    cumulative_changed=changed
    if revision==2:
        prior_path=STAGE/'embedded_options.result.json';prior=json.loads(prior_path.read_bytes());paths.append(prior_path)
        assert digest(old_header)==prior['generated_header']['sha256'] and digest(old_prepared)==prior['prepared_report']['sha256']
        original_raw=gzip.decompress(Path(prior['header_recovery']['path']).read_bytes())
        original_arrays,original_tail=reuse.parse_text_arrays(original_raw,preparer)
        assert original_tail==tail and [name for name,_ in original_arrays]==[name for name,_ in texts]
        cumulative_changed=[name for (name,before),(_,after) in zip(original_arrays,texts) if before!=after]
        assert set(cumulative_changed)=={'ZeroSisUiScene','MenuOptionsLayout','TouchHelpLayout'}
    updated['reward_options_text_refresh']=dict(schema='zerosis.reward_options.text_refresh.v1',revision=revision,
        changed_payloads=changed,cumulative_changed_payloads=cumulative_changed,catalog_payload_count=74,layout_count=30,
        no_font_texture_or_audio_extraction=True,no_asset_pack_copy=True,
        native_execution=False,full_asset_preparer_main_executed=False)
    new_prepared=encoded(updated)
    unique={str(path.absolute()).casefold():path.absolute() for path in paths}
    before=[common.artifact(path) for path in unique.values()]
    report=dict(schema='zerosis.reward_options.embedding_preflight.v1',
        status='PASS_THREE_EXISTING_TEXT_PAYLOADS_REBUILT_FILE_ONLY',inputs=before,
        revision=revision,changed_payloads=changed,cumulative_changed_payloads=cumulative_changed,
        unchanged_payload_count=74-len(changed),cumulative_unchanged_payload_count=74-len(cumulative_changed),catalog_entries=74,original_layouts=30,
        original_reward_callback=next(row for row in handlers if row['name']=='OnNoRewardPopupsCheckbox'),
        header_recovery=backups[0],prepared_recovery=backups[1],
        expected_header=dict(path=str(HEADER),bytes=len(new_header),sha256=digest(new_header)),
        expected_prepared=dict(path=str(PREPARED),bytes=len(new_prepared),sha256=digest(new_prepared)),
        audio_registry_tail_byte_identical=True,audio_registry_tail_sha256=digest(tail.encode('ascii')),
        shared_font_bank_unchanged=True,texture_or_font_extraction=False,
        host_or_sdk_executed=False,native_execution=False,full_asset_preparer_main_executed=False)
    for row in before:assert common.artifact(row['path'])==row
    return new_header,new_prepared,report,old_header


def main():
    cli=argparse.ArgumentParser();cli.add_argument('action',choices=['plan','apply']);cli.add_argument('--plan-sha')
    cli.add_argument('--revision',type=int,choices=[1,2],default=1);args=cli.parse_args()
    stem='embedded_options' if args.revision==1 else 'embedded_options_revision2'
    plan=STAGE/(stem+'.plan.json');result=STAGE/(stem+'.result.json')
    assert not result.exists()
    header,prepared,report,old_header=prepare(args.revision)
    if args.action=='plan':
        assert args.plan_sha is None;write_new(plan,encoded(report));print(json.dumps(dict(status=report['status'],plan=common.artifact(plan),changed=report['changed_payloads'])));return
    assert args.plan_sha and digest(plan.read_bytes())==args.plan_sha and json.loads(plan.read_bytes())==report
    pending=[STAGE/'reward_header.pending',STAGE/'reward_prepared.pending']
    assert all(not path.exists() for path in pending)
    write_new(pending[0],header);write_new(pending[1],prepared)
    os.replace(pending[0],HEADER)
    try:os.replace(pending[1],PREPARED)
    except OSError:
        write_new(pending[0],old_header);os.replace(pending[0],HEADER);raise
    for path,want in ((HEADER,report['expected_header']),(PREPARED,report['expected_prepared'])):
        actual=common.artifact(path);assert all(actual[key]==want[key] for key in ('path','bytes','sha256'))
    for row in report['inputs']:
        if row['path'] not in (str(HEADER),str(PREPARED)):assert common.artifact(row['path'])==row
    report.update(status='PASS_REWARD_OPTIONS_V3_EMBEDDED_FILE_ONLY_NOT_HOST_EXECUTED',
        reviewed_plan=common.artifact(plan),generated_header=common.artifact(HEADER),prepared_report=common.artifact(PREPARED),
        current_host_lua_sources=[row for row in report['inputs'] if row['path'].endswith('.lua')],
        pending_files_remaining=False)
    write_new(result,encoded(report));print(json.dumps(dict(status=report['status'],header_sha=report['generated_header']['sha256'],changed=report['changed_payloads'])))


if __name__=='__main__':main()
