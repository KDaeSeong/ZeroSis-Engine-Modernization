"""One immutable active-skin front-end pack with the actual current 14px font.

V1/V2 inputs and installed sources remain untouched. The six V2 face records
are copied byte for byte; 14:Shadow is appended under the existing bank002
contract. Exact immutable payload donors are hardlinked without chmod.
"""
from __future__ import annotations
from copy import deepcopy
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import struct
import sys
import xml.etree.ElementTree as ET

PROJECT=Path(__file__).resolve().parents[1]
GAME=Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V")
V2=PROJECT/'Source/Assets/UIFrontEndV2'
V3=PROJECT/'Source/Assets/UIFrontEndV3'
STAGE=PROJECT/'evidence/game_menu/replay_calendar_legend/legend'
MANIFEST=STAGE/'assets_v3.json'
V2_MANIFEST=PROJECT/'evidence/game_menu/menu_runtime_ui_followup/frontend/assets_v2.json'
BACKEND=PROJECT/'Build/InteractiveGameRuntime/20261103T140325Z_f127e4edebe9/bundle.manifest'
CURRENT_FONT={
 'Assets/UI/Fonts/Tw Cent MT/TwCenMT14.ggxml':(1837551,'cb57452311af11e795bacad3e1bd8c73b465f2339f4d3b794a5fc13a78c656f9'),
 'kTwCenMT14.dds':(6414464,'5fbfcb1f7fedc26203c46af73392b528e9c1a8c13372441750754dfd02e2d6d0'),
 'kTwCenMT14Shadow.dds':(6414464,'588d885a352f63369cbd1b7ba37fb32899cb1300d319dc2d1b4225e4bcd1e38b'),
 'Assets/UI/ColorAtlas.xml':(2133,'f5796603d1d904a711765c48750ea5e10380b36bd17f36cb5cb3658017ae8561')}
OLD_FACES=((18,'Base'),(18,'Shadow'),(20,'Shadow'),(20,'SoftShadow'),(22,'Shadow'),(24,'Shadow'))
OFFLINE=dict(native_execution=False,sdk_loaded=False,host_or_sdk_or_window_executed=False,
             gpu_execution=False,retail_pixel_acceptance=False,native_geometry_verified=False)


def require(value,message):
    if not value:raise ValueError(message)


def artifact(path):
    from menu_frontend_options_assets import artifact as inspect
    return inspect(path)


def seal_private(path):
    info=os.stat(path,follow_symlinks=False)
    if info.st_file_attributes&1:return
    require(info.st_nlink==1 and not info.st_file_attributes&0x400,'Refusing to chmod a shared or reparse input')
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.SetFileAttributesW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD]
    kernel.SetFileAttributesW.restype=wintypes.BOOL
    if not kernel.SetFileAttributesW(str(path),info.st_file_attributes|1):raise ctypes.WinError(ctypes.get_last_error())


def same_protected(before):
    for row in before:
        now=artifact(row['path'])
        require(all(row[key]==now[key] for key in ('bytes','sha256','file_identity','mtime_ns','file_attributes')),
                'Protected source changed: '+row['path'])


def bank_sections(data):
    require(data[:8]==b'ZSMFE002','V3 requires the immutable V2 bank')
    cursor=8
    def u32():
        nonlocal cursor
        require(cursor+4<=len(data),'Truncated V2 bank')
        value,=struct.unpack_from('<I',data,cursor);cursor+=4;return value
    def text():
        nonlocal cursor
        size=u32();require(cursor+size<=len(data),'Truncated V2 bank string')
        raw=data[cursor:cursor+size];cursor+=size;return raw.decode('utf8')
    controls=u32()
    for _ in range(controls):cursor+=36;text();text()
    font_count_at=cursor;count=u32();require(count==6,'Sealed V2 face count differs')
    faces=[]
    for _ in range(count):
        start=cursor;size=u32();style=text();cursor+=12;layers=u32();glyphs=u32();cursor+=20*layers+40*glyphs
        require(cursor<=len(data),'Truncated V2 font record');faces.append((size,style,data[start:cursor]))
    require(tuple((size,style) for size,style,_ in faces)==OLD_FACES,'V2 face key order changed')
    textures={}
    for _ in range(u32()):
        name=text();textures[name]=struct.unpack_from('<3I',data,cursor);cursor+=12
    for _ in range(u32()):text();cursor+=24;pieces=u32();cursor+=24*pieces
    tail=cursor
    for _ in range(u32()):text();cursor+=32
    icon_end=cursor
    for _ in range(u32()):text();cursor+=20;text()
    options_end=cursor
    for _ in range(u32()):
        text();layers=u32();cursor+=16*layers
    require(cursor==len(data),'V2 bank tail differs')
    return dict(font_count_at=font_count_at,faces=faces,textures=textures,icons=data[tail:icon_end],
                options=data[icon_end:options_end],colors=data[options_end:])


def make_bank(old,controls,styles,registry,font,font_textures):
    from menu_frontend_options_assets import text
    bank=bytearray(b'ZSMFE002'+struct.pack('<I',len(controls)))
    for row in controls:
        bank+=struct.pack('<IQQ4f',row['page'],row['key'],row['spriteKey'],*row['bounds'])
        text(bank,row['name']);text(bank,row['text'])
    bank+=struct.pack('<I',7)
    for _,_,raw in old['faces']:bank+=raw
    bank+=struct.pack('<I',14);text(bank,'Shadow')
    bank+=struct.pack('<ii fII',font.line_advance,font.baseline_offset,font.spacing/2,len(font.layers),len(font.glyphs))
    colors=font.color_sets['Beige_Black_Alpha'].layer_colors
    for layer in font.layers:
        bank+=struct.pack('<I4f',font_textures[layer.sheet.path.name],*(value/255 for value in colors[layer.order].rgba))
    for cp,glyph in sorted(font.glyphs.items()):
        drawn=bool(glyph.width and glyph.height)
        bank+=struct.pack('<I9i',cp,glyph.a,glyph.b,glyph.c,glyph.origin_x,glyph.origin_y,glyph.u,glyph.v,
                          glyph.width+font.spacing if drawn else 0,glyph.height+font.spacing if drawn else 0)
    bank+=struct.pack('<I',len(registry))
    for name,values in sorted(registry.items()):text(bank,name);bank+=struct.pack('<3I',*values)
    bank+=struct.pack('<I',len(styles))
    for row in styles:
        text(bank,row['name']);bank+=struct.pack('<II4fI',row['kind'],row['texture'],row['width'],row['height'],*row['step'],len(row['pieces']))
        for piece in row['pieces']:bank+=struct.pack('<II4f',*piece)
    bank+=old['icons']+old['options']+old['colors']
    return bytes(bank)


class Payloads:
    def __init__(self,old_files):
        self.by_hash={};self.materialized=[]
        for path in old_files:
            row=artifact(path)
            if row['file_attributes']&1:self.by_hash.setdefault(row['sha256'],Path(path))

    def retain(self,path,data,*,private=False):
        from menu_frontend_options_assets import hardlink
        path=Path(path);require(path.is_relative_to(V3),'Payload escaped the new pack')
        digest=hashlib.sha256(data).hexdigest();path.parent.mkdir(parents=True,exist_ok=True)
        if path.exists():
            row=artifact(path);require((row['bytes'],row['sha256'])==(len(data),digest),'Immutable V3 payload differs')
            require(row['file_attributes']&1 and (not private or row['links']==1),'Resumed required payload is unexpectedly shared or mutable')
            self.materialized.append(dict(relative_path=path.relative_to(V3).as_posix(),
                method='RESUMED_REQUIRED_PRIVATE_COPY' if row['links']==1 else 'RESUMED_EXACT_IMMUTABLE_ALIAS',
                bytes=row['bytes'],sha256=digest,file_identity=row['file_identity'],donor=None))
            self.by_hash.setdefault(digest,path);return path
        donor=None if private else self.by_hash.get(digest)
        cache=PROJECT/'Build/RuntimeInputCache/ui-source-assets'/digest[:2]/(digest+'.dds')
        if donor is None and not private and cache.exists():
            row=artifact(cache)
            if row['bytes']==len(data) and row['sha256']==digest and row['file_attributes']&1 and row['links']<990:donor=cache
        if donor is not None:
            before=artifact(donor);require(before['file_attributes']&1,'Payload donor is mutable')
            hardlink(donor,path);same_protected([before]);method='HARDLINK_EXACT_IMMUTABLE_DONOR'
        else:
            with path.open('xb') as stream:stream.write(data)
            seal_private(path);method='NEW_REQUIRED_PRIVATE_COPY'
        row=artifact(path);require((row['bytes'],row['sha256'])==(len(data),digest),'New payload readback differs')
        if private:require(row['links']==1,'Current font copy unexpectedly aliases another file')
        self.materialized.append(dict(relative_path=path.relative_to(V3).as_posix(),method=method,
            bytes=row['bytes'],sha256=digest,file_identity=row['file_identity'],donor=str(donor) if donor else None))
        self.by_hash.setdefault(digest,path);return path


def install_resolver(compiler,skin,payloads):
    from civ5_ui_assets import Fpk,decode_dds
    packs={}
    def resolve(texture_name,destination):
        selected=skin.texture(texture_name);basename=selected['basename']
        if basename in compiler.assets.outputs:
            row=compiler.assets.outputs[basename];skin.verify_texture_records([row]);return row
        source=selected['source'];index_source=selected.get('index_source')
        if selected['kind']=='fpk-entry':
            key=source['pack_path'];pack=packs.setdefault(key,Fpk(key));data,read_source=pack.read(source['entry'])
            require(read_source==source,'Original texture source changed after selection')
            index=None
            if index_source:
                index,read_index=pack.read(index_source['entry']);require(read_index==index_source,'Original tile index changed after selection')
        else:
            data=Path(source['path']).read_bytes();index=None
            require((len(data),hashlib.sha256(data).hexdigest())==(source['bytes'],source['sha256']),'Loose original texture changed')
        normalized,conversion=decode_dds(data,index)
        def retain(folder,name,raw):
            identity=hashlib.sha256(name.encode('utf8')).hexdigest()[:8];digest=hashlib.sha256(raw).hexdigest()
            return payloads.retain(Path(folder)/(identity+'-'+digest[:16]+'.dds'),raw)
        output=retain(destination,basename,normalized);raw=retain(V3/'source_assets',basename,data)
        index_path=retain(V3/'source_assets',basename[:-4]+'-index.dds',index) if index is not None else None
        record=dict(requested_name=texture_name,basename=basename,source=source,index_source=index_source,
            candidate_sources=[row.get('pack',{}).get('path',row.get('source',{}).get('path')) for row in selected['candidates']],
            frozen_source=dict(path=str(raw),sha256=hashlib.sha256(data).hexdigest()),
            frozen_index=dict(path=str(index_path),sha256=hashlib.sha256(index).hexdigest()) if index_path else None,
            conversion=conversion,output=dict(path=str(output),bytes=len(normalized),sha256=hashlib.sha256(normalized).hexdigest()),
            candidate_filename_policy='REQUEST_SHA8_PAYLOAD_SHA16_DDS_V1')
        compiler.assets.records.append(record);compiler.assets.outputs[basename]=record
        skin.verify_texture_records([record]);return record
    compiler.assets.resolve=resolve


def preflight():
    from retained_host_runtime_input import _Files
    from retained_menu_suite_host_input import sidecar_source_inventory
    files=_Files(check_metadata=True)
    report=sidecar_source_inventory(PROJECT,V3,artifact(MANIFEST),'zerosis.original_frontend.assets.v2',files)
    files.finish();return report


def prepare_v3():
    from menu_frontend_assets import packet,write_same_or_new
    from menu_frontend_options_assets import hardlink,read_packet_textures
    from menu_frontend_skin import FrontEndSkin
    from menu_frontend_skin_pages import compile_skin_pages
    from ui_bitmap_fonts import load_font
    from ui_font_profile import load_font_profile,profile_input_root
    from ui_pixel_scene import Compiler
    import civ5_ui_assets
    if MANIFEST.exists():preflight();return json.loads(MANIFEST.read_text('utf8'))
    STAGE.mkdir(parents=True,exist_ok=True)
    original=[artifact(GAME/relative) for relative in CURRENT_FONT]
    for relative,row in zip(CURRENT_FONT,original):require((row['bytes'],row['sha256'])==CURRENT_FONT[relative],'Actual current 14px input differs: '+relative)
    font=load_font(GAME,'TwCenMT14','Shadow')
    require(len(font.glyphs)==17320 and all(cp in font.glyphs for cp in range(0xac00,0xd7a4)) and
        (font.texture_width,font.texture_height,font.line_advance,font.baseline_offset,font.spacing)==(2048,3132,17,17,1),'Current full-coverage 14px profile differs')
    previous=json.loads(V2_MANIFEST.read_text('utf8'));require(artifact(V2_MANIFEST)['sha256']=='e01f8775c526ee3b9e408bad263c81a88ac1c64acd578367cfa5424adb0a245a','Immutable V2 manifest changed')
    from retained_host_runtime_input import _Files
    from retained_menu_suite_host_input import sidecar_source_inventory
    old_gate_files=_Files(check_metadata=True)
    old_gate=sidecar_source_inventory(PROJECT,V2,artifact(V2_MANIFEST),'zerosis.original_frontend.assets.v2',old_gate_files)
    old_gate_files.finish();require(old_gate['file_count']==114,'Protected V2 source gate differs')
    old_files=sorted(path for path in V2.rglob('*') if path.is_file());require(len(old_files)==114,'Immutable V2 inventory changed')
    protected=original+[artifact(path) for path in old_files]+[artifact(V2_MANIFEST)]
    V3.mkdir(parents=True,exist_ok=True);payloads=Payloads(old_files);unchanged=[]
    for path in old_files:
        if path.suffix=='.packet' or path.name=='frontend.bin':continue
        target=V3/path.relative_to(V2);hardlink(path,target);unchanged.append(target.relative_to(V3).as_posix())
    civ5_ui_assets.LOOSE_UI_TEXTURES['fonticons_dlc_07.dds']=dict(
        relative_path='Assets/DLC/Shared/UI/Art/Fonts/Font Icons/FontIcons_DLC_07.dds',bytes=4000,
        sha256='ac3acd71484003d674ee85f1a95cfdb9c80e125c4307ae323d6e3d9bd28f53a9')
    skin=FrontEndSkin(GAME,BACKEND);compiler=Compiler(GAME,V3,context='menu-options')
    load_font_profile();compiler.font_root=profile_input_root()
    compiler.font_input_refs={path:artifact(path) for path in compiler.font_root.rglob('*') if path.is_file()}
    for size,style in OLD_FACES:compiler.fonts[('TwCenMT%d'%size,style)]=load_font(compiler.font_root,'TwCenMT%d'%size,style)
    names=read_packet_textures(V2/'extension.packet');compiler.textures=[str(V3/name) for name in names]
    compiler.texture_ids={name:index for index,name in enumerate(compiler.textures)}
    old_records=deepcopy(previous['original_texture_sources'])
    for row in old_records:
        for key in ('output','frozen_source','frozen_index'):
            if row.get(key):row[key]['path']=str(V3/Path(row[key]['path']).relative_to(V2))
        compiler.assets.outputs[row['basename']]=row
    install_resolver(compiler,skin,payloads)
    font_textures={}
    for layer in font.layers:
        path=payloads.retain(V3/'textures'/layer.sheet.path.name,layer.sheet.path.read_bytes(),private=True)
        font_textures[layer.sheet.path.name]=compiler.register_texture(path,font.texture_width,font.texture_height)[0]
    sys.path.insert(0,str(PROJECT/'Tests'))
    from menu_options_original_followup import run_lua
    options_tree=run_lua()['captures']['interface']['tree']
    selected=compile_skin_pages(compiler,skin,options_tree=options_tree)
    # The front-end package directory resolver is not an in-game skin loader.
    # Retain the separately pinned Expansion2 replay source profile unchanged.
    legend_xml=dict(profile='EXPLICIT_EXISTING_EXPANSION2_REPLAY_SOURCE_BINDING',
        source=artifact(GAME/'Assets/DLC/Expansion2/UI/InGame/Popups/ReplayViewer.xml'))
    legend_lua=dict(profile='EXPLICIT_EXISTING_BASE_REPLAY_LUA_SOURCE_BINDING',
        source=artifact(GAME/'Assets/UI/InGame/Popups/ReplayViewer.lua'))
    require(legend_xml['source']['sha256']=='c10c832cc827dc8fcf3db0c69bf71a27f0cb21c4c140c18d794d1f90af442f6d' and
        legend_lua['source']['sha256']=='64141da32e031d89dbcada820c0eccd30bd0cf50bf66322a4e4955847b927379','Selected original replay legend sources differ')
    protected.extend((legend_xml['source'],legend_lua['source']))
    replay=ET.parse(legend_xml['source']['path']).getroot()
    legend_source=dict(xml=legend_xml,lua=legend_lua,row_pitch=32,inspected={})
    for name in ('GraphLegend','LegendIcon','LegendLine','LegendName','ShowHide','GraphLegendStack','GraphLegendScrollPanel'):
        nodes=replay.findall(".//*[@ID='"+name+"']");require(len(nodes)==1,'Original replay legend control differs: '+name)
        legend_source['inspected'][name]=dict(nodes[0].attrib)
    legend_source['separator']=dict(replay.find(".//*[@ID='GraphLegend']/Grid").attrib)
    rules=Path(skin.backend['rules']['path'])
    with sqlite3.connect(rules.as_uri()+'?mode=ro&immutable=1',uri=True) as database:
        atlases=database.execute('SELECT DISTINCT a.Filename FROM Civilizations c JOIN IconTextureAtlases a ON c.IconAtlas=a.Atlas WHERE a.IconSize=32 ORDER BY a.Filename').fetchall()
        civs=database.execute('SELECT c.Type,c.PortraitIndex,a.Filename,a.IconsPerRow,a.IconsPerColumn FROM Civilizations c JOIN IconTextureAtlases a ON c.IconAtlas=a.Atlas WHERE a.IconSize=32 ORDER BY c.Type').fetchall()
    require(len(atlases)==10 and len(civs)==45,'Actual civilization icon inventory changed')
    legend=[]
    for name, in atlases:
        index,width,height=compiler.texture(name);legend.append(dict(name=name,index=index,width=width,height=height,source=skin.texture(name)))
    require(len(compiler.textures)<=64,'Actual active skin and complete legend exceed the renderer texture bank')
    lookup={row['name'].casefold():row for row in legend};crops=[]
    for civilization,portrait,name,raw_columns,raw_rows in civs:
        columns,rows=int(raw_columns),int(raw_rows);require(columns>0 and rows>0 and type(portrait) is int and 0<=portrait<columns*rows,'Malformed actual civilization atlas row')
        u,v=portrait%columns*32,portrait//columns*32;sheet=lookup[name.casefold()]
        require(u+32<=sheet['width'] and v+32<=sheet['height'],'Actual civilization crop escapes original DDS: '+civilization)
        crops.append(dict(civilization=civilization,portrait_index=portrait,filename=name,columns=columns,rows=rows,source_rect=[u,v,u+32,v+32]))
    old=bank_sections((V2/'frontend.bin').read_bytes());registry=dict(old['textures'])
    for record in [*old_records,*compiler.assets.records]:
        path=str(Path(record['output']['path']).absolute())
        if path in compiler.texture_ids:registry[record['basename']]=(compiler.texture_ids[path],record['conversion']['width'],record['conversion']['height'])
    require(len(registry)<=64,'Named texture registry exceeds its bound')
    outputs={name+'.packet':packet(compiler,sprites) for name,sprites in selected['scenes'].items()}
    outputs.update({'extension.packet':packet(compiler,[]),'options_chrome.packet':packet(compiler,selected['options_chrome']),
                    'frontend.bin':make_bank(old,selected['controls'],selected['styles'],registry,font,font_textures)})
    for name,data in outputs.items():
        path=V3/name
        if (V2/name).read_bytes()==data:hardlink(V2/name,path);unchanged.append(name)
        else:write_same_or_new(path,data);seal_private(path)
    require(skin.unchanged() and compiler.unchanged(),'Original selected inputs changed during V3 preparation')
    same_protected(protected)
    files=[artifact(path) for path in sorted(V3.rglob('*')) if path.is_file()]
    require(all(row['file_attributes']&1 for row in files),'New front-end pack is not immutable')
    provenance=skin.provenance(texture_names=sorted(compiler.assets.outputs))
    output=dict(schema='zerosis.original_frontend.assets.v2',**OFFLINE,source_root=str(V3),runtime_root='UIFrontEnd',
        pack_revision='ACTIVE_EXPANSION2_COMMON_SKIN_AND_CURRENT_14PX_LEGEND_V3',
        immutable_v2_manifest=artifact(V2_MANIFEST),original_v2_preserved=True,
        unchanged_v2_hardlink_count=len(unchanged),unchanged_v2_relative_paths=unchanged,
        current_14px_original_inputs=original,current_14px_profile=dict(glyphs=17320,modern_hangul=11172,texture_size=[2048,3132],
            line_advance=17,baseline=17,spacing=1,border=0.5,layer_texture_indices=font_textures,
            source='ACTUAL_CURRENT_INSTALLED_GGXML_AND_ATLASES_HASH_PINNED',
            historical_2529_glyph_regression_profile='PRESERVED_FOR_SIX_EXISTING_FACES_NOT_USED_FOR_14PX'),
        fonts=[*previous['fonts'],dict(size=14,style='Shadow',glyphs=17320,ggxml=original[0])],
        active_skin=provenance,active_controls=selected['controls'],active_styles=selected['styles'],
        original_image_size_candidates=selected.get('original_image_size_candidates',[]),
        options_control_layout=previous['options_control_layout'],options_geometry=selected['options_geometry'],
        original_options=previous['original_options'],inline_icon_catalog=previous['inline_icon_catalog'],
        original_texture_sources=[*old_records,*compiler.assets.records],legend_atlases=legend,actual_civilization_crops=crops,
        original_graph_legend=legend_source,
        unchanged_six_face_bytes=True,unchanged_inline_icon_count=148,legend_checkbox=dict(texture='checkbox.dds',size=[32,32],
            source_cell_height=32,unchecked_cell=0,checked_cell=1,retail_widget_state_mapping_verified=False),
        materialization=payloads.materialized,protected_source_count=len(protected),protected_sources_unchanged=True,
        files=files)
    raw=(json.dumps(output,indent=2,ensure_ascii=False)+'\n').encode('utf8')
    with MANIFEST.open('xb') as stream:stream.write(raw)
    seal_private(MANIFEST);gate=preflight()
    proof=STAGE/'asset_preflight.json'
    with proof.open('x',encoding='utf8') as stream:
        json.dump(dict(schema='zerosis.replay_legend.asset_preflight.v1',**OFFLINE,manifest=artifact(MANIFEST),
            file_count=gate['file_count'],texture_count=len(compiler.textures),protected_source_count=len(protected),
            protected_sources_unchanged=True,new_payload_bytes=sum(row['bytes'] for row in payloads.materialized if row['method'] in ('NEW_REQUIRED_PRIVATE_COPY','RESUMED_REQUIRED_PRIVATE_COPY')),
            source_root=str(V3)),stream,indent=2);stream.write('\n')
    return output


if __name__=='__main__':
    result=prepare_v3()
    print(json.dumps(dict(status='PASS_ORIGINAL_ACTIVE_SKIN_AND_FULL_LEGEND_ASSETS_PREPARED_NOT_EXECUTED',
        manifest=str(MANIFEST),files=len(result['files']),reused_v2_hardlinks=result['unchanged_v2_hardlink_count'],
        fonts=len(result['fonts']),legend_atlases=len(result['legend_atlases']),**OFFLINE)))
