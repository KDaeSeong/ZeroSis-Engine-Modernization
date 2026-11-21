"""Actual original DDS slider paint and exact source/input contracts on the CPU."""
from __future__ import annotations
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import struct
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(PROJECT/'tools'),str(PROJECT/'Tests')]
from menu_options_assets import GAME
from menu_options_original_followup import run_lua
from menu_options_renderer_contract import nodes, visible_geometry, manifest
from ui_pixel_scene import Compiler, private_menu_contract
from interactive_ui_driver import validate_private_menu_scene_proof
from render_ui_popup import retained_bounds
from menu_frontend_cpu import dds, png_bytes

STAGE = PROJECT/'evidence/game_menu/original_menu_followup/options'
WORK = PROJECT/'Build/MenuOptionsFollowup/renderer'


def main():
    checks = 0
    def check(value,message):
        nonlocal checks
        checks += 1
        if not value:raise AssertionError(message)
    def reject(fn,message):
        caught = False
        try:fn()
        except (ValueError,RuntimeError,KeyError,TypeError,IndexError):caught = True
        check(caught,message)
    data = run_lua();captures = data['captures']
    source_files = ['Source/Host/UiScene.lua','Source/Presentation/UiPresentationInput.lua',
        'Source/Presentation/UiMenuOptions.lua','tools/menu_options_assets.py','tools/ui_pixel_scene.py','tools/menu_frontend_cpu.py']
    source_before = {str(PROJECT/name):hashlib.sha256((PROJECT/name).read_bytes()).hexdigest() for name in source_files}
    WORK.mkdir(parents=True,exist_ok=True);STAGE.mkdir(parents=True,exist_ok=True)
    rows = []
    for name,snapshot in captures.items():
        closed = not snapshot['active']
        before = deepcopy(snapshot)
        proof = private_menu_contract(snapshot,context='menu-options',closed=closed)
        compiler = Compiler(GAME,WORK,context='menu-options')
        if name in ('audioFraction','resolutionOpen','interface') or closed:
            packet = compiler.compile(snapshot,closed=closed)
            fields = struct.unpack('<6I',packet[8:32])
            check(fields[:2] == (1920,1080),'Actual packet viewport changed')
            check(fields[4:] == (len(snapshot['inputTargets']),len(snapshot['scrollTargets'])),
                'Actual packet hit/scroll inventories differ from original source controls')
            if closed:check(packet == b'ZSUPIX02'+struct.pack('<6I',1920,1080,0,0,0,0),'Closed packet retained paint/input')
            packet_proof = dict(bytes=len(packet),sha256=hashlib.sha256(packet).hexdigest(),
                textures=fields[2],sprites=fields[3],hits=fields[4],scrolls=fields[5])
        else:
            compiler.geometry=visible_geometry(snapshot);compiler.private_menu_scene=proof
            compiler.production_input_targets=snapshot['inputTargets'];compiler.hits=[]
            compiler.game_menu_hits();compiler.production_scroll_targets=snapshot['scrollTargets']
            compiler.scroll_regions=[];compiler.production_scrolls(snapshot['tree'])
            packet_proof = None
        geometry,hits,scrolls = compiler.geometry,compiler.hits,compiler.scroll_regions
        if not closed:retained_bounds(snapshot,geometry,context='menu-options')
        payload = manifest(snapshot,proof,geometry,hits,scrolls)
        validate_private_menu_scene_proof(snapshot,payload,context='menu-options',closed=closed)
        check(snapshot == before,'Renderer/source verifier changed the options snapshot')
        rows.append(dict(scene=name,closed=closed,packet=packet_proof,
            hit_count=len(hits),scroll_count=len(scrolls),exact_source_contract=True))
    sample = captures['audioFraction']
    for key,value in (('value',0.5),('minimum',False),('maximum',True),('event','LeftClick')):
        bad=deepcopy(sample)
        target=next(t for t in bad['inputTargets'] if t['event']=='SliderValue');target[key]=value
        reject(lambda:private_menu_contract(bad,context='menu-options'),'Forged slider '+key+' was accepted')
    bad=deepcopy(sample);bad['menuOptions']['source']['originalSupportedHandlers']['functions'][0]['source']+='\nerror("forged")'
    reject(lambda:private_menu_contract(bad,context='menu-options'),'Forged original function source was accepted')
    bad=deepcopy(captures['interface']);bad['menuOptions']['supportedCapabilities']['policyInfo']=False
    reject(lambda:private_menu_contract(bad,context='menu-options'),'Unsupported policy backend acquired source controls')
    bad=deepcopy(captures['resolutionOpen'])
    next(n for n in nodes(bad) if n.get('styleChildSource'))['styleChildSource']['ownerPullDownKey']+=1
    reject(lambda:private_menu_contract(bad,context='menu-options'),'Forged resolution widget owner was accepted')
    bad=deepcopy(captures['resolutionOpen']);bad['inputTargets'].append(deepcopy(
        next(t for t in captures['interface']['inputTargets'] if t['id']=='AcceptButton')))
    reject(lambda:private_menu_contract(bad,context='menu-options'),'Resolution popup exposed a covered Apply callback')
    compiler = Compiler(GAME,WORK,context='menu-options')
    preview = bytearray(bytes((22,26,30,255))*(500*112));paint_rows=[]
    for index,name in enumerate(('audioZero','audioFraction','audioFull')):
        snapshot = captures[name]
        compiler.private_menu_scene=private_menu_contract(snapshot,context='menu-options')
        node=next(n for n in nodes(snapshot) if n['id']=='EffectsVolumeSlider')
        bounds=tuple(node[k] for k in ('x','y','width','height'))
        compiler.geometry=[dict(key=node['key'],bounds=bounds)];compiler.sprites=[]
        compiler.original_effects_slider(node,bounds,(0,0,1920,1080))
        check(len(compiler.sprites)==4,'Original slider did not use its three source track pieces and one source shuttle')
        expected=bounds[0]+(bounds[2]-32)*node['sliderValue']
        thumb=compiler.geometry[-1]['slider_shuttle_bounds']
        check(abs(thumb[0]-expected)<1e-9 and thumb[1:]==(bounds[1],32,32),'Slider shuttle did not reflect actual value')
        layer=bytearray(bytes((22,26,30,255))*(500*32))
        for sprite in compiler.sprites:
            texture=sprite[0];src=sprite[2:6];dst=sprite[6:10]
            tw,th,pixels=dds(compiler.textures[texture])
            check(tuple(sprite[-4:])==(1,1,1,1),'Diagnostic slider unexpectedly changed the original texture tint')
            left=max(0,math.ceil(dst[0]-bounds[0]));right=min(500,math.ceil(dst[2]-bounds[0]))
            top=max(0,math.ceil(dst[1]-bounds[1]));bottom=min(32,math.ceil(dst[3]-bounds[1]))
            for y in range(top,bottom):
                sy=min(th-1,int(src[1]+(y+0.5+bounds[1]-dst[1])*(src[3]-src[1])/(dst[3]-dst[1])))
                for x in range(left,right):
                    sx=min(tw-1,int(src[0]+(x+0.5+bounds[0]-dst[0])*(src[2]-src[0])/(dst[2]-dst[0])))
                    at=(sy*tw+sx)*4;b,g,r,a=pixels[at:at+4];out=(y*500+x)*4
                    if a:
                        old=layer[out:out+4];inv=255-a
                        layer[out:out+4]=bytes(((b*a+old[0]*inv+127)//255,
                            (g*a+old[1]*inv+127)//255,(r*a+old[2]*inv+127)//255,255))
            for y in range(32):
                out=((index*36+4+y)*500)*4;preview[out:out+500*4]=layer[y*500*4:(y+1)*500*4]
        paint_rows.append(dict(scene=name,value=node['sliderValue'],shuttle_bounds=thumb,
            bgra_sha256=hashlib.sha256(layer).hexdigest(),sprite_count=len(compiler.sprites)))
    check(len({r['bgra_sha256'] for r in paint_rows})==3,'Actual original DDS slider pixels did not change with value')
    check(len(compiler.textures)==2,'Slider paint expanded beyond its exact stock track and shuttle textures')
    preview_path=STAGE/'slider_cpu_preview.png';preview_path.write_bytes(png_bytes(500,112,preview))
    textures=[dict(path=p,bytes=Path(p).stat().st_size,sha256=hashlib.sha256(Path(p).read_bytes()).hexdigest()) for p in compiler.textures]
    source_after={path:hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in source_before}
    check(source_before==source_after,'Production sources changed during the renderer fixture')
    report=dict(schema='zerosis.original_options.renderer_cpu.v1',status='PASS',checks=checks,
        scenes=rows,slider_paint=paint_rows,original_normalized_textures=textures,
        source_sha256=source_before,preview=dict(path=str(preview_path),bytes=preview_path.stat().st_size,
            sha256=hashlib.sha256(preview_path.read_bytes()).hexdigest()),
        host_executed=False,sdk_executed=False,hwnd_created=False,gpu_executed=False,
        retail_pixels_verified=False,classification='EXACT_SOURCE_PACKET_CONTRACT_AND_CPU_SLIDER_CANDIDATE_ONLY')
    report['cpu_sampling']='NEAREST_NEIGHBOR_DIAGNOSTIC_CANDIDATE'
    (STAGE/'renderer_tests.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status='PASS',checks=checks,scenes=len(rows),
        actual_full_packets=sum(r['packet'] is not None for r in rows),cpu_preview_bytes=preview_path.stat().st_size)))


if __name__=='__main__':main()
