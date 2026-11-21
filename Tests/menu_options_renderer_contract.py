"""Pure source/geometry/packet checks; no images, Host, SDK, HWND or GPU run."""
from __future__ import annotations
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile

PROJECT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(PROJECT/'tools'),str(PROJECT/'Tests')]
from economic_overview_scene import execute_lua
from menu_options_scene import fixture_script as option_fixture
from menu_options_map_scene import fixture_script as map_fixture
from ui_pixel_scene import (Compiler, private_menu_contract, PRIVATE_MENU_CONTEXTS,
                            intersect, rect, validate_hit_regions)
from interactive_ui_driver import validate_private_menu_scene_proof, parse_scene_request
from render_ui_popup import retained_bounds
from prepare_ui_popup_assets import GAME


def visible_geometry(snapshot):
    rows=[]
    def walk(node,visible=True):
        visible=visible and not node['hidden']
        if not visible:return
        rows.append(dict(key=node['key'],id=node.get('id',''),kind=node['kind'],
            bounds=tuple(node[field] for field in ('x','y','width','height')),style_decoration=False))
        if node['kind']=='ShowOnMouseOver' and not node['hovered']:return
        for child in node['children']:walk(child,visible)
    walk(snapshot['tree']);return rows


def nodes(snapshot):
    result=[]
    def walk(node):
        result.append(node)
        for child in node['children']:walk(child)
    walk(snapshot['tree']);return result


def manifest(snapshot,proof,geometry,hits,scrolls):
    context=proof['context'];name,kind,_=PRIVATE_MENU_CONTEXTS[context]
    return dict(status='PRIVATE_HOST_MENU_COMPONENT_SCENE_COMPILED',context=context,
        context_name=name,popup_kind=kind,packet_version='ZSUPIX02',private_menu_scene=proof,
        closed_context_not_drawn=not snapshot['active'],retained_input_targets=snapshot['inputTargets'],
        original_context_sources=[proof[field] for field in ('originalLua','originalXml','originalStyles')],
        hit_regions=[list(hit) for hit in hits],scroll_regions=[list(hit) for hit in scrolls],
        input_target_count=len(snapshot['inputTargets']),scroll_region_count=len(snapshot['scrollTargets']),
        geometry=geometry,labels=[],sprite_count=0,texture_count=0)


def main():
    checks=0
    def check(value,message):
        nonlocal checks
        checks+=1
        if not value:raise AssertionError(message)
    def reject(fn,message):
        caught=False
        try:fn()
        except (ValueError,RuntimeError,KeyError,TypeError,IndexError):caught=True
        check(caught,message)
    script,_=option_fixture()
    captured=execute_lua('_RETURN_MENU_SNAPSHOTS=true\n'+script)
    script,_,_,_=map_fixture()
    captured.update(execute_lua('_RETURN_MENU_SNAPSHOTS=true\n'+script))
    scenes=[]
    destination=Path(tempfile.mkdtemp(prefix='menu-options-contract-',dir=PROJECT/'Build'))
    try:
        for name,snapshot in captured.items():
            context='menu-options' if name in ('options','video','audio','optionsClosed') else 'touch-help' if name.startswith('touch') else 'map-menu'
            closed=not snapshot['active'];before=deepcopy(snapshot)
            proof=private_menu_contract(snapshot,context=context,closed=closed)
            check(proof['native_acceptance_verified'] is False and proof['retail_options_api_complete'] is False,
                  'Source-only checks promoted a native or complete retail API claim')
            for field in ('originalLua','originalXml','originalStyles'):
                check(Path(proof[field]['path']).is_file(), 'Missing source binding')
            compiler=Compiler(GAME,destination/name,context=context,snapshot_clock=snapshot.get('presentationClock',0))
            if closed:
                packet=compiler.compile(snapshot,closed=True)
                check(packet==b'ZSUPIX02'+struct.pack('<6I',1920,1080,0,0,0,0),'Closed packet retained paint/input')
                geometry=[];hits=[];scrolls=[]
            else:
                geometry=visible_geometry(snapshot)
                compiler.geometry=geometry;compiler.private_menu_scene=proof
                compiler.production_input_targets=snapshot['inputTargets'];compiler.hits=[]
                compiler.game_menu_hits();hits=compiler.hits
                compiler.production_scroll_targets=snapshot['scrollTargets'];compiler.scroll_regions=[]
                compiler.production_scrolls(snapshot['tree']);scrolls=compiler.scroll_regions
                retained_bounds(snapshot,geometry,context=context)
                check(len(hits)==len(snapshot['inputTargets']),'Private menu hit order lost a target')
                check(all(len(hit)==5 and all(type(v) in (int,float) for v in hit) for hit in hits),'Packet hit layout is not scalar')
            value=manifest(snapshot,proof,geometry,hits,scrolls)
            validate_private_menu_scene_proof(snapshot,value,context=context,closed=closed)
            check(snapshot==before,'Source or packet validation changed retained UI state')
            bad=deepcopy(value);bad['private_menu_scene']['retail_options_api_complete']=True
            reject(lambda:validate_private_menu_scene_proof(snapshot,bad,context=context,closed=closed),'Overstated retail API proof accepted')
            bad=deepcopy(snapshot);bad['popupKind']='GameMenu'
            reject(lambda:private_menu_contract(bad,context=context,closed=closed),'Wrong owner context accepted')
            bad=deepcopy(snapshot);bad['mapMenu' if context=='map-menu' else 'menuOptions']['owner']=True
            reject(lambda:private_menu_contract(bad,context=context,closed=closed),'Boolean player identity accepted')
            line=f'INTERACTIVE_UI_SCENE_REQUEST=1|{context}|C:\\owned\\snapshot.json|C:\\owned\\packet\n'
            check(parse_scene_request(line)[1]==context,'Host handshake rejects a new source-bound child context')
            scenes.append(dict(name=name,context=context,closed=closed,hit_count=len(hits),scroll_count=len(scrolls)))
        bad=deepcopy(captured['options']);bad['menuOptions']['source']['originalXml']['sha256']='0'*64
        reject(lambda:private_menu_contract(bad,context='menu-options'),'Changed original menu XML hash accepted')
        bad=deepcopy(captured['audio']);bad['menuOptions']['derivedControls']=[]
        reject(lambda:private_menu_contract(bad,context='menu-options'),'Missing derived control inventory accepted')
        bad=deepcopy(captured['audio']);bad['menuOptions']['supportedCapabilities']['uiCueVolumePercent']=False
        reject(lambda:private_menu_contract(bad,context='menu-options'),'Unsupported volume control exposed as active')
        bad=deepcopy(captured['options']);bad['tree']['children'].pop(0)
        reject(lambda:private_menu_contract(bad,context='menu-options'),'Removed original XML child accepted')
        bad=deepcopy(captured['mapConfirm']);background=next(target for target in captured['map']['inputTargets'] if target.get('id')=='Button')
        # Use a current background row identity, not the old row from before its
        # original selection rebuilt the list, to isolate the modal barrier.
        current=next(node for node in nodes(bad) if node.get('id')=='Button')
        background=deepcopy(background);background['key']=current['key']
        background['bounds']={key:current[field] for key,field in (('x','x'),('y','y'),('width','width'),('height','height'))}
        background['clippedBounds']=dict(background['bounds']);bad['inputTargets'].append(background)
        reject(lambda:private_menu_contract(bad,context='map-menu'),'Map confirmation allowed a background row hit')
        nested=deepcopy(captured['map']);nested['mapMenu']['parentContext']='SaveMenu'
        check(private_menu_contract(nested,context='map-menu')['parent_context']=='SaveMenu','Original nested SaveMenu owner rejected')
        check(all(not list(path.iterdir()) for path in destination.iterdir()),'Source-only check created image/texture outputs')
    finally:
        if destination.parent!=PROJECT/'Build' or not destination.name.startswith('menu-options-contract-'):
            raise RuntimeError('Owned empty test cleanup escaped Build')
        for path in destination.iterdir():
            if path.is_symlink() or getattr(path.lstat(),'st_file_attributes',0)&0x400:raise RuntimeError('Reparse point in owned cleanup')
            path.rmdir()
        destination.rmdir()
    evidence=PROJECT/'evidence/game_menu/offline_menu_suite/options_touch'
    report=dict(schema='zerosis.private_menu.renderer_source_contract.v1',status='PASS',checks=checks,scenes=scenes,
        source_only=True,images_rendered=False,host_executed=False,sdk_executed=False,hwnd_created=False,gpu_executed=False,
        source_sha256={name:hashlib.sha256((PROJECT/'tools'/name).read_bytes()).hexdigest() for name in
            ('ui_pixel_scene.py','interactive_ui_driver.py','render_ui_popup.py')})
    (evidence/'renderer_contract_tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status='PASS',checks=checks,scenes=len(scenes),images_rendered=False)))


if __name__=='__main__':main()
