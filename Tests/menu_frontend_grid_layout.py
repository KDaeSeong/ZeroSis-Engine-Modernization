"""Per-cap original grid geometry and immutable V3 asset-reader integration.

Only the compiler, linker and SDK-free Kernel32 console fixture execute. There
is no Host, game SDK, window, native renderer, GPU or image output.
"""
from __future__ import annotations
import ast
import gzip
import hashlib
import inspect
import json
from pathlib import Path
import random
import re
import struct
import sys
import xml.etree.ElementTree as ET

sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[1]
sys.path.insert(0,str(PROJECT/'tools'));sys.path.insert(0,str(PROJECT/'Tests'))
from menu_replay_restoration import build_cxx14
from menu_frontend_assets import artifact
from menu_suite_storage import storage
from native_build import run

STAGE=PROJECT/'evidence/game_menu/replay_hover_frame/frame'
BUILD=PROJECT/'Build/MenuFrontEndGridLayout/current'
HEADER=PROJECT/'Source/Host/MenuFrontEndGridLayout.h'
READER=PROJECT/'Source/Host/MenuFrontEndAssets.h'
CPP=PROJECT/'Tests/menu_frontend_grid_layout.cpp'
ASSETS=PROJECT/'Source/Assets/UIFrontEndV4'
MANIFEST=PROJECT/'evidence/game_menu/native_offline_followup/frontend_v4/assets_v4.json'
MANIFEST_SHA='dbd8c092a3ef9ca86498ef48bcdeb71b4151a97b011f1230ba35d09340fcaea7'
ORACLE=PROJECT/'tools/ui_pixel_scene.py'
BACKUP=PROJECT/'evidence/game_menu/replay_hover_frame/source_before/Source__Host__MenuFrontEndAssets.h.20ba3346398b5486.gz'
GAME=Path(r"C:/Program Files (x86)/Steam/steamapps/common/Sid Meier's Civilization V")
ACTIVE_STYLE=GAME/'Assets/DLC/Expansion/UI/Styles_Expansion1.xml'
ACTIVE_REPLAY=PROJECT/'Source/Assets/UI/Assets/DLC/Expansion2/UI/InGame/Popups/ReplayViewer.xml'


def require(ok,message):
    if not ok:raise ValueError(message)


def source_scope():
    before=gzip.decompress(BACKUP.read_bytes());require(hashlib.sha256(before).hexdigest()=='20ba3346398b5486e4e96378b0324f8b6e0194bea2d8074224d3533fb2c00bdb','Changed-file reader backup differs')
    before=before.decode('utf8').replace('\r\n','\n');current=READER.read_text('utf8').replace('\r\n','\n')
    start='    void Grid(';end='    void StyleButton('
    def split(text):
        a=text.index(start);b=text.index(end,a);return text[:a],text[a:b],text[b:]
    old_prefix,old_grid,old_suffix=split(before);prefix,grid,suffix=split(current)
    require(prefix.replace('#include "MenuFrontEndGridLayout.h"\n','')==old_prefix and suffix==old_suffix,'Reader changed beyond Grid and its required include')
    tree=ast.parse(ORACLE.read_text('utf8'));node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='grid_targets')
    source=ast.get_source_segment(ORACLE.read_text('utf8'),node);environment={'require':require}
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(ORACLE),'exec'),environment)
    active=ET.parse(ACTIVE_STYLE).getroot().find('Grid9DetailFive140')
    require(active is not None and active.attrib['LLSize']=='74,50' and active.attrib['LCSize']=='1,70' and active.attrib['LRSize']=='74,50','Installed original asymmetric cap declarations differ')
    replay=ET.parse(ACTIVE_REPLAY).getroot();frame=replay.find(".//*[@ID='FrontEndReplayViewer']")
    require(frame is not None and frame.attrib['Size']=='960,628' and frame.attrib['Offset']=='0,36','Original replay frame declaration differs')
    images=[dict(node.attrib) for node in frame.findall('Image')]
    return dict(backup=artifact(BACKUP),reader_only_grid_and_include_changed=True,previous_grid_source_sha256=hashlib.sha256(old_grid.encode()).hexdigest(),
        original_grid_target_oracle=artifact(ORACLE),oracle_function_sha256=hashlib.sha256(source.encode()).hexdigest(),
        installed_active_style=artifact(ACTIVE_STYLE),installed_active_style_attributes=dict(active.attrib),
        original_replay_xml=artifact(ACTIVE_REPLAY),frame_attributes=dict(frame.attrib),decorative_images_unchanged=images,
        native_control_geometry_executed=False),environment['grid_targets']


def synthetic(name,kind,sizes):
    return dict(name=name,actual=False,kind=kind,texture=0,width=32,height=32,step=[0,0],
        pieces=[[column,row,0,0,width,height] for column,row,width,height in sizes])


def minimum(row):
    parts={(p[0],p[1]):(p[4]-p[2],p[5]-p[3]) for p in row['pieces']}
    if row['kind']==0:
        wh=lambda c,r:parts.get((c,r),(0,0))
        return max(wh(0,r)[0]+wh(2,r)[0] for r in range(3)),max(wh(c,0)[1]+wh(c,2)[1] for c in range(3))
    left=max((w for (c,r),(w,h) in parts.items() if c==0),default=0);right=max((w for (c,r),(w,h) in parts.items() if c==2),default=0)
    top=max((h for (c,r),(w,h) in parts.items() if r==0),default=0);bottom=max((h for (c,r),(w,h) in parts.items() if r==2),default=0)
    return (left+right,0) if row['kind']==1 else (0,top+bottom) if row['kind']==2 else (0,0)


def legacy_equal(row):
    if row['kind']!=0:return True
    parts={(p[0],p[1]):(p[4]-p[2],p[5]-p[3]) for p in row['pieces']}
    if len(parts)!=9:return False
    return len({parts[(0,r)][0] for r in range(3)})==1 and len({parts[(2,r)][0] for r in range(3)})==1 and len({parts[(c,0)][1] for c in range(3)})==1 and len({parts[(c,2)][1] for c in range(3)})==1


def golden_matrix(grid_targets):
    manifest=json.loads(MANIFEST.read_text('utf8'));require(artifact(MANIFEST)['sha256']==MANIFEST_SHA,'Immutable V4 asset manifest differs')
    rows=[dict(row,actual=True) for row in manifest['active_styles']];require(len(rows)==16,'Expected all sixteen current V3 styles')
    nine=[(0,0,10,7),(1,0,1,9),(2,0,13,11),(0,1,8,1),(1,1,1,1),(2,1,6,1),(0,2,14,15),(1,2,1,17),(2,2,12,19)]
    rows.extend([synthetic('__all_nine_caps_independent',0,nine),synthetic('__omitted_empty_center',0,[p for p in nine if p[:2]!=(1,1)]),
        synthetic('__horizontal_preserved',1,[(0,1,9,5),(1,1,3,7),(2,1,13,11)]),synthetic('__vertical_preserved',2,[(1,0,5,7),(1,1,9,1),(1,2,13,11)]),synthetic('__stretch_preserved',3,[(1,1,3,7)])])
    payload=bytearray(b'ZSGRID01'+struct.pack('<I',len(rows)))
    def text(value):
        raw=value.encode();payload.extend(struct.pack('<I',len(raw))+raw)
    for row in rows:
        text(row['name']);payload.extend(struct.pack('<III4fI',int(row['actual']),row['kind'],row['texture'],row['width'],row['height'],*row['step'],len(row['pieces'])))
        for c,r,u,v,right,bottom in row['pieces']:payload.extend(struct.pack('<II4f',c,r,u,v,right,bottom))
    cases=[];randomizer=random.Random(0x9ca950)
    for index,row in enumerate(rows):
        min_w,min_h=minimum(row);min_w=max(min_w,1);min_h=max(min_h,1)
        dimensions=[(480,262,960,628),(1.25,9.5,min_w,min_h),(-14.5,26.25,min_w+31.5,min_h+23.75),(1024.125,-64.25,2000.5,1000.25)]
        dimensions.extend((randomizer.randrange(-512,512)/8,randomizer.randrange(-512,512)/8,min_w+randomizer.randrange(0,2048)/4,min_h+randomizer.randrange(0,2048)/4) for _ in range(25))
        for bounds in dimensions:
            x,y,w,h=bounds
            if row['kind']==0:
                parts={(p[0],p[1]):(p[4]-p[2],p[5]-p[3]) for p in row['pieces']}
                sizes={name:parts.get((c,r),(0,0)) for r,names in enumerate((('UL','UC','UR'),('L','C','R'),('LL','LC','LR'))) for c,name in enumerate(names)}
                all_targets=grid_targets(sizes,bounds);targets=[all_targets[p[1]*3+p[0]] for p in row['pieces']]
            else:
                left=max((p[4]-p[2] for p in row['pieces'] if p[0]==0),default=0);right=max((p[4]-p[2] for p in row['pieces'] if p[0]==2),default=0)
                top=max((p[5]-p[3] for p in row['pieces'] if p[1]==0),default=0);bottom=max((p[5]-p[3] for p in row['pieces'] if p[1]==2),default=0)
                if row['kind']==1:top=bottom=0
                if row['kind']==2:left=right=0
                if row['kind']==3:left=right=top=bottom=0
                xs=[x,x+left,x+w-right,x+w];ys=[y,y+top,y+h-bottom,y+h];targets=[]
                for p in row['pieces']:
                    c=1 if row['kind'] in (2,3) else p[0];r=1 if row['kind'] in (1,3) else p[1];targets.append((xs[c],ys[r],xs[c+1],ys[r+1]))
            for state in range(4):cases.append((index,state,bounds,legacy_equal(row),targets))
    payload.extend(struct.pack('<I',len(cases)))
    for index,state,bounds,equal,targets in cases:
        payload.extend(struct.pack('<II4fII',index,state,*bounds,int(equal),len(targets)))
        for target in targets:payload.extend(struct.pack('<4f',*target))
    return bytes(payload),dict(current_styles=len(manifest['active_styles']),synthetic_styles=len(rows)-len(manifest['active_styles']),states=4,cases=len(cases),
        current_style_names=[r['name'] for r in rows if r['actual']],unchanged_legacy_style_names=[r['name'] for r in rows if r['actual'] and legacy_equal(r)],
        intentionally_repaired_style='Grid9DetailFive140',source_per_cap_geometry_oracle='Existing ui_pixel_scene.grid_targets, extracted verbatim as an isolated pure function.',
        source_14px_font_or_colors_changed=False,asset_pack_or_manifest_changed=False)


def main():
    STAGE.mkdir(parents=True,exist_ok=True);BUILD.mkdir(parents=True,exist_ok=True)
    scope,oracle=source_scope();matrix,catalog=golden_matrix(oracle)
    inputs=[HEADER,READER,CPP,Path(__file__),MANIFEST,ORACLE,BACKUP,ACTIVE_STYLE,ACTIVE_REPLAY,PROJECT/'Tests/menu_frontend_scene_fixture.h',PROJECT/'Source/Presentation/BitmapRenderer.h',PROJECT/'tools/native_build.py',PROJECT/'Tests/menu_replay_restoration.py']
    inputs.extend(sorted(path for path in ASSETS.rglob('*') if path.is_file()))
    before=[artifact(path) for path in inputs];recipe=inspect.getsource(build_cxx14);signature=hashlib.sha256(json.dumps(before,sort_keys=True).encode()+recipe.encode()+matrix).hexdigest()[:20]
    evidence=STAGE/('attempt_'+signature);receipt=evidence/'result.json'
    if receipt.exists():
        old=json.loads(receipt.read_text('utf8'))
        if old.get('status')=='PASS_ORIGINAL_PER_CAP_GRID_AND_ACTUAL_V3_SCENE' and old.get('inputs_before')==before and artifact(Path(old['build']['path']))['sha256']==old['build']['sha256']:
            print(json.dumps(dict(status=old['status'],report=str(receipt),reused_identical_inputs=True)));return 0
        raise ValueError('Existing grid fixture proof cannot be overwritten')
    evidence.mkdir();golden=BUILD/'grid_layout_goldens.bin'
    if golden.exists():raise ValueError('Unresolved prior grid fixture golden exists')
    golden.write_bytes(matrix)
    report=dict(schema='zerosis.original_grid_layout.v1',input_signature=signature,inputs_before=before,source_scope=scope,oracle_catalog=catalog,
        immutable_asset_manifest=artifact(MANIFEST),compile_recipe_sha256=hashlib.sha256(recipe.encode()).hexdigest(),
        cpp_dialect='c++14',native_host_sdk_window_gpu_executed=False,retail_pixel_acceptance=False,image_output_created=False,
        limitations=['Per-cap targets preserve original style declarations and the existing source-derived grid layout policy; native Grid implementation/sampler equivalence is not asserted.',
                    'The actual asset reader emits real Scene sprites in this SDK-free fixture; no native painting path is invoked.'])
    cleanup=['grid_layout_goldens.bin','MenuFrontEndGridLayout.obj','MenuFrontEndGridLayout.map','compile.rsp','read_build_environment.cmd']
    try:
        if any(any(value>127 for value in path.read_bytes()) for path in (HEADER,CPP)):raise ValueError('Grid C++14 sources must be ASCII')
        report['golden_input']=artifact(golden);report['build']=build_cxx14('MenuFrontEndGridLayout',BUILD,evidence,CPP,[PROJECT/'Source/Host'])
        compiled=report['build'];dependencies=run([Path(compiled['compiler']).with_name('dumpbin.exe'),'/dependents',compiled['path']],cwd=BUILD,timeout=30)
        names=sorted(set(re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$',dependencies.stdout.decode('mbcs',errors='replace'),re.M)))
        if dependencies.returncode or {name.lower() for name in names}!={'kernel32.dll'}:raise ValueError('Unexpected SDK-free grid fixture imports '+repr(names))
        report['component_imported_dlls']=names;result=run([compiled['path'],str(ASSETS),str(golden)],cwd=BUILD,timeout=60)
        if result.returncode:raise ValueError((result.stdout+result.stderr).decode('utf8',errors='replace'))
        report.update(json.loads(result.stdout));report['inputs_after']=[artifact(path) for path in inputs]
        if before!=report['inputs_after']:raise ValueError('Grid source or immutable asset inputs changed during fixture')
    except Exception as error:
        report.update(status='FAIL_ORIGINAL_PER_CAP_GRID_AND_ACTUAL_V3_SCENE',error=str(error));raise
    finally:
        removed=[]
        for name in cleanup:
            path=BUILD/name
            if not path.exists():continue
            info=storage.ordinary(path)
            if path.absolute().parent!=BUILD.absolute() or info.st_nlink!=1:raise ValueError('Unsafe grid intermediate cleanup')
            row=dict(artifact(path),file_identity=[info.st_dev,info.st_ino],allocated_bytes=storage.allocated(path))
            if storage.metadata(info)!=storage.metadata(storage.ordinary(path)):raise ValueError('Grid cleanup identity changed')
            path.unlink();row['result']='DELETED_EXACT_OWNED_REGENERABLE_GRID_LAYOUT_INTERMEDIATE';removed.append(row)
        report['owned_intermediate_cleanup']=removed;report['owned_intermediate_bytes_removed']=sum(row['bytes'] for row in removed);report['owned_intermediate_allocated_bytes_removed']=sum(row['allocated_bytes'] for row in removed)
        receipt.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(status=report['status'],checks=report['checks'],report=str(receipt),cleaned_allocated_bytes=report['owned_intermediate_allocated_bytes_removed'])));return 0


if __name__=='__main__':raise SystemExit(main())
