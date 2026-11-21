"""Read-only independent checks of the final 74 generated Lua payloads."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys

PROJECT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(PROJECT/'tools'),str(PROJECT/'Tests')]
import prepare_ui_popup_assets as preparer
import refresh_exit_confirm_ui_assets as reuse
from menu_options_scene import fixture_script as option_fixture
from menu_options_map_scene import fixture_script as map_fixture
from economic_overview_scene import execute_lua
from ui_pixel_scene import private_menu_contract


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    root=PROJECT/'evidence/game_menu/original_menu_followup/ui_assets'
    publication=json.loads((root/'ui_embedding_result.json').read_text(encoding='utf-8'))
    manifest=json.loads((root/'source_manifest.json').read_text(encoding='utf-8'))
    header=PROJECT/'Source/Host/UiPopupAssets.generated.h'
    prepared_path=PROJECT/'evidence/ui_popup/assets/prepared.json'
    checks=0
    def check(value,message):
        nonlocal checks
        checks+=1
        if not value:raise AssertionError(message)
    for name,path in (('header',header),('prepared',prepared_path)):
        expected=publication['outputs_expected'][name]
        check(path.stat().st_size==expected['bytes'] and digest(path)==expected['sha256'],'Published artifact hash differs: '+name)
    for row in manifest['sources']:
        path=Path(row['path']);info=path.stat()
        check(info.st_size==row['bytes'] and digest(path)==row['sha256'] and
              [info.st_dev,info.st_ino]==row['file_identity'] and info.st_mtime_ns==row['mtime_ns'],
              'Final source manifest drifted: '+str(path))
    prepared=json.loads(prepared_path.read_text(encoding='utf-8'))
    arrays,audio=reuse.parse_text_arrays(header.read_bytes(),preparer)
    payloads=dict(arrays)
    check(len(arrays)==len(payloads)==74,'Final header is not a unique 74-payload catalog')
    check(len(prepared['xml_control_trees'])==30,'Final prepared catalog lost a layout')
    expected_rows=publication['catalog_payloads']
    check([(name,len(data),hashlib.sha256(data).hexdigest()) for name,data in arrays]==
          [(row['name'],row['bytes'],row['sha256']) for row in expected_rows], 'Payload bytes/order differ from publication')
    sources={key:(PROJECT/relative).read_bytes() for key,relative,_ in reuse.HOST_LUA}
    expected_scene=(reuse.scene_bytes(sources)+b'\n'+(PROJECT/'Source/Presentation/UiMenuOptions.lua').read_bytes()+
                    b'\n'+(PROJECT/'Source/Presentation/UiMapMenu.lua').read_bytes())
    check(payloads['ZeroSisUiScene']==expected_scene,'Published scene is not the exact final shared source composition')
    for name,relative in (('TouchControlsMenu','Assets/UI/TouchControlsMenu.lua'),
                          ('SaveMapMenu','Assets/UI/InGame/Menus/SaveMapMenu.lua')):
        check(payloads[name]==(preparer.GAME/relative).read_bytes(),'Published original Lua bytes differ: '+name)
    for name in ('MenuOptionsLayout','TouchHelpLayout','MapMenuLayout'):
        check(payloads[name]==('ZeroSisUiLayout='+preparer.lua_value(prepared['xml_control_trees'][name])+'\n').encode('ascii'),
              'Generated layout does not bind the exact prepared tree: '+name)
    shared=payloads['SharedFontMetrics'].decode('ascii')+'\n'
    scene=payloads['ZeroSisUiScene'].decode('utf-8-sig')
    script,_=option_fixture(scene_override=scene,layouts_override={
        'options':prepared['xml_control_trees']['MenuOptionsLayout'],
        'touch':prepared['xml_control_trees']['TouchHelpLayout']})
    captures=execute_lua(shared+'_RETURN_MENU_SNAPSHOTS=true\n'+script)
    script,_,_,_=map_fixture(scene_override=scene,layout_override=prepared['xml_control_trees']['MapMenuLayout'])
    captures.update(execute_lua(shared+"_RETURN_MENU_SNAPSHOTS=true;_FIXTURE_MAP_PARENT='SaveMenu'\n"+script))
    proofs=[]
    for name,snapshot in captures.items():
        context='menu-options' if name in ('options','video','audio','optionsClosed') else 'touch-help' if name.startswith('touch') else 'map-menu'
        proof=private_menu_contract(snapshot,context=context,closed=not snapshot['active'])
        check(proof['full_original_tree_matched'] and not proof['native_acceptance_verified'],
              'Published source/layout composition failed its source-only renderer contract')
        proofs.append(dict(name=name,context=context,input_count=len(snapshot['inputTargets']),
                           parent=proof['parent_context'],closed=proof['closed']))
    report=dict(schema='zerosis.menu_suite.final_embedding_crosscheck.v1',status='PASS',checks=checks,
        generated_payloads=len(arrays),prepared_layouts=len(prepared['xml_control_trees']),manifest_sources=len(manifest['sources']),
        scenes=proofs,header_sha256=digest(header),prepared_sha256=digest(prepared_path),
        final_source_manifest_sha256=digest(root/'source_manifest.json'),
        publication_sha256=digest(root/'ui_embedding_result.json'),
        shared_lua_fixture_executed=True,host_executed=False,sdk_executed=False,hwnd_created=False,gpu_executed=False,images_rendered=False)
    target=PROJECT/'evidence/game_menu/original_menu_followup/options/embedding_cross_tests.json'
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({key:report[key] for key in ('status','checks','generated_payloads','manifest_sources')}))


if __name__=='__main__':main()
