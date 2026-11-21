"""V2 selected retail front-end assets; immutable V1 payloads are hardlinked.

The existing V1/source/bc34 aliases are never written or chmodded. Only the new
bank, extension packet, original options chrome and necessary font/icon/style
payloads are generated. Layout is measured by the actual retained Lua adapter
in the shared SDK-free fixture; it is not native retail geometry acceptance.
"""
from __future__ import annotations
from copy import deepcopy
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import struct
import sys

PROJECT=Path(__file__).resolve().parents[1]
V1=PROJECT/'Source/Assets/UIFrontEnd'
V2=PROJECT/'Source/Assets/UIFrontEndV2'
STAGE=PROJECT/'evidence/game_menu/menu_runtime_ui_followup/frontend'
CONTROL_IDS={'GameButton':1,'IFaceButton':2,'VideoButton':3,'AudioButton':4,
 'NoBasicHelpCheckbox':10,'PolicyInfo':11,'WResolutionPull':12,'FullscreenCheck':13,
 'VSyncCheck':14,'EffectsVolumeSlider':15,'DefaultButton':20,'CancelButton':21,'AcceptButton':22}


def artifact(path):
    path=Path(path);info=os.stat(path,follow_symlinks=False)
    if info.st_file_attributes&0x400:raise ValueError('Front-end asset is a reparse point')
    return dict(path=str(path.absolute()),bytes=info.st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                file_identity=[info.st_dev,info.st_ino],mtime_ns=info.st_mtime_ns,file_attributes=info.st_file_attributes,links=info.st_nlink)


def write_generated(path,data):
    path=Path(path)
    if path.exists():
        if path.read_bytes()==data:return
        info=os.stat(path,follow_symlinks=False)
        if info.st_nlink!=1 or info.st_file_attributes&(0x400|1) or not path.is_relative_to(V2):
            raise ValueError('Refusing to mutate a shared/sealed front-end generated asset')
    path.write_bytes(data)


def hardlink(source,target):
    if target.exists():
        if not os.path.samefile(source,target):raise ValueError('Existing V2 payload is not the exact V1 hardlink')
        return
    target.parent.mkdir(parents=True,exist_ok=True)
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateHardLinkW.argtypes=[wintypes.LPCWSTR,wintypes.LPCWSTR,wintypes.LPVOID]
    kernel.CreateHardLinkW.restype=wintypes.BOOL
    if not kernel.CreateHardLinkW(str(target),str(source),None):raise ctypes.WinError(ctypes.get_last_error())
    if not os.path.samefile(source,target):raise ValueError('V2 hardlink identity differs after creation')


def read_packet_textures(path):
    data=Path(path).read_bytes();count,=struct.unpack_from('<I',data,16);cursor=32;result=[]
    for _ in range(count):
        length,=struct.unpack_from('<I',data,cursor);cursor+=4
        result.append(data[cursor:cursor+length].decode('utf8'));cursor+=length
    return result


def text(blob,value):
    raw=value.encode('utf8');blob+=struct.pack('<I',len(raw))+raw


def walk(node):
    yield node
    for child in node.get('children',[]):yield from walk(child)


def prepare_v2():
    from menu_frontend_assets import GAME,packet
    from ui_pixel_scene import Compiler,pair
    from ui_font_profile import profile_input_root,load_font_profile
    import civ5_ui_assets
    # This tiny loose official atlas is not present in the FPK search set.
    # Extend only this preparer's in-process exact-source allowlist.
    loose_icon=dict(relative_path='Assets/DLC/Shared/UI/Art/Fonts/Font Icons/FontIcons_DLC_07.dds',
        bytes=4000,sha256='ac3acd71484003d674ee85f1a95cfdb9c80e125c4307ae323d6e3d9bd28f53a9')
    if 'fonticons_dlc_07.dds' in civ5_ui_assets.LOOSE_UI_TEXTURES and civ5_ui_assets.LOOSE_UI_TEXTURES['fonticons_dlc_07.dds']!=loose_icon:
        raise ValueError('Loose icon source pin collision')
    civ5_ui_assets.LOOSE_UI_TEXTURES['fonticons_dlc_07.dds']=loose_icon
    sys.path.insert(0,str(PROJECT/'Tests'))
    from menu_options_original_followup import run_lua
    STAGE.mkdir(parents=True,exist_ok=True);V2.mkdir(parents=True,exist_ok=True)
    previous=json.loads((PROJECT/'evidence/game_menu/original_menu_followup/frontend/assets.json').read_text('utf8'))
    original_before={str(path):artifact(path) for path in V1.rglob('*') if path.is_file()}
    if len(original_before)!=62:raise ValueError('V1 must remain the exact sealed 62-file pack')
    links=[]
    for path in sorted(V1.rglob('*')):
        if not path.is_file() or path.name=='frontend.bin':continue
        target=V2/path.relative_to(V1);hardlink(path,target);links.append(dict(source=artifact(path),target=artifact(target)))
    profile,_=load_font_profile();compiler=Compiler(GAME,V2,context='menu-options')
    compiler.font_root=profile_input_root()
    compiler.font_input_refs={path:artifact(path) for path in compiler.font_root.rglob('*') if path.is_file()}
    names=read_packet_textures(V1/'background.packet')
    compiler.textures=[str((V2/name).absolute()) for name in names]
    compiler.texture_ids={name:index for index,name in enumerate(compiler.textures)}
    old_records=deepcopy(previous['original_texture_sources'])
    for record in old_records:
        for key in ('output','frozen_source','frozen_index'):
            if record.get(key):record[key]['path']=str(V2/Path(record[key]['path']).relative_to(V1))
        compiler.assets.outputs[record['basename']]=record
    captures=run_lua()['captures'];snapshot=deepcopy(captures['interface']);tree=snapshot['tree']
    layout=[]
    for node in walk(tree):
        name=node.get('id','')
        if name in CONTROL_IDS:
            caption=node.get('attributes',{}).get('String','')
            if not caption:
                caption=next((child.get('attributes',{}).get('String','') for child in node.get('children',[]) if child.get('kind')=='Label'),'')
            layout.append(dict(name=name,key=CONTROL_IDS[name],bounds=[node[k] for k in ('x','y','width','height')],
                text=caption,attributes=node.get('sourceAttributes',node.get('attributes',{}))))
        if name in ('GamePanel','IFacePanel','VideoPanel','AudioPanel','MultiplayerPanel'):
            node['hidden']=True
        if node.get('kind') in ('Label','ShowOnMouseOver','GridButton','Button','CheckBox','Slider','PullDown') or name.endswith('Highlight'):
            node['hidden']=True
        node['text']=''
    compiler.node(tree,(0,0,1920,1080),{},(0,0,1920,1080))
    chrome=list(compiler.sprites)
    style_names=('Grid9DetailFive140','Grid9FrameTurns','Grid9FrameTurnsHL','Grid9Frame27SquareBlack',
        'SmallButton','BaseButton','ZoomButton','SquareButton','GenericPullDown','Button_16',
        'Slider','Slider32','VertSlider','VertShuttle','ScrollBarUp','ScrollBarDown')
    styles=[]
    for name in style_names:
        node=compiler.styles[name]
        if name=='GenericPullDown':node=compiler.styles[node.find('ButtonData/GridButton').get('Style')]
        grid=node.find('GridData')
        if grid is not None:node=compiler.styles[grid.get('Style')]
        attrs=node.attrib
        if 'ULSize' in attrs:kind=0;parts=[(x,y,key) for y,row in enumerate((('UL','UC','UR'),('L','C','R'),('LL','LC','LR'))) for x,key in enumerate(row)]
        elif 'LSize' in attrs and 'RSize' in attrs:kind=1;parts=[(x,1,key) for x,key in enumerate(('L','C','R'))]
        elif 'UCSize' in attrs and 'LCSize' in attrs:kind=2;parts=[(1,y,key) for y,key in enumerate(('UC','C','LC'))]
        else:kind=3;parts=[]
        texture,tw,th=compiler.texture(attrs['Texture']);width,height=pair(attrs.get('Size','32,32'))
        step=pair(attrs.get('StateOffsetIncrement','0,0'))
        if name=='Button_16':step=(0,32)
        pieces=[]
        for x,y,key in parts:
            w,h=pair(attrs[key+'Size']);u,v=pair(attrs.get(key+'TexStart','0,0'))
            if w and h:pieces.append((x,y,u,v,u+w,v+h))
        if kind==3:pieces=[(1,1,0,0,width,height)]
        styles.append(dict(name=name,kind=kind,texture=texture,width=width,height=height,step=step,pieces=pieces))
    for name in ('topframe.dds','bottomframe_Thinner.dds','HorizontalTrim.dds','BlueBar500x3.dds','Assets/UI/Art/Controls/9 Grids/Corner16.dds'):
        compiler.texture(name)
    prepared=json.loads((PROJECT/'Build/UiWindowHost/20261101T091435Z_bc34fab66a03/frozen/ui_assets/prepared.json').read_text('utf8'))
    icon_pin=prepared['inline_icon_catalog'];icon_path=Path(icon_pin['path'])
    if hashlib.sha256(icon_path.read_bytes()).hexdigest()!=icon_pin['sha256']:raise ValueError('Frozen original icon catalog differs')
    icon_catalog=json.loads(icon_path.read_text('utf8'))['icons'];icons=[]
    for name,row in sorted(icon_catalog.items()):
        texture,_,_=compiler.texture(row['texture']);glyph=row['glyph']
        icons.append(dict(name=name,texture=texture,**glyph))
    faces=[]
    for size,style in ((18,'Base'),(18,'Shadow'),(20,'Shadow'),(20,'SoftShadow'),(22,'Shadow'),(24,'Shadow')):
        faces.append((size,style,compiler.font('TwCenMT%d'%size,style)))
    # Reuse V1 control records verbatim. The V2 font variants and exact named
    # style/icon/retained-layout tables follow this existing source contract.
    old=(V1/'frontend.bin').read_bytes();cursor=12;controls,=struct.unpack_from('<I',old,8)
    for _ in range(controls):
        cursor+=36
        for _ in range(2):length,=struct.unpack_from('<I',old,cursor);cursor+=4+length
    bank=bytearray(b'ZSMFE002'+old[8:cursor]);bank+=struct.pack('<I',len(faces))
    for size,style,font in faces:
        bank+=struct.pack('<I',size);text(bank,style)
        bank+=struct.pack('<ii fII',font.line_advance,font.baseline_offset,font.spacing/2,len(font.layers),len(font.glyphs))
        colors=font.color_sets['Beige_Black_Alpha'].layer_colors
        for layer in font.layers:
            index,_,_=compiler.register_texture(V2/'textures'/layer.sheet.path.name,layer.sheet.width,layer.sheet.height)
            color=colors[min(layer.order,len(colors)-1)].rgba
            bank+=struct.pack('<I4f',index,*(v/255 for v in color))
        for cp,glyph in sorted(font.glyphs.items()):
            drawn=bool(glyph.width and glyph.height)
            bank+=struct.pack('<I9i',cp,glyph.a,glyph.b,glyph.c,glyph.origin_x,glyph.origin_y,glyph.u,glyph.v,
                glyph.width+font.spacing if drawn else 0,glyph.height+font.spacing if drawn else 0)
    registry={}
    for row in [*old_records,*compiler.assets.records]:
        path=str(Path(row['output']['path']).absolute())
        if path in compiler.texture_ids:
            registry[row['basename']]=(compiler.texture_ids[path],row['conversion']['width'],row['conversion']['height'])
    bank+=struct.pack('<I',len(registry))
    for name,(index,width,height) in sorted(registry.items()):text(bank,name);bank+=struct.pack('<3I',index,width,height)
    bank+=struct.pack('<I',len(styles))
    for row in styles:
        text(bank,row['name']);bank+=struct.pack('<II4fI',row['kind'],row['texture'],row['width'],row['height'],*row['step'],len(row['pieces']))
        for piece in row['pieces']:bank+=struct.pack('<II4f',*piece)
    bank+=struct.pack('<I',len(icons))
    for row in icons:
        text(bank,row['name']);bank+=struct.pack('<I7i',row['texture'],*(row[k] for k in ('u','v','width','height','advance','originx','originy')))
    bank+=struct.pack('<I',len(layout))
    for row in layout:text(bank,row['name']);bank+=struct.pack('<I4f',row['key'],*row['bounds']);text(bank,row['text'])
    colors=faces[0][2].color_sets;bank+=struct.pack('<I',len(colors))
    for name,row in sorted(colors.items()):text(bank,name);bank+=struct.pack('<I',len(row.layer_colors));bank+=b''.join(struct.pack('<4f',*(v/255 for v in color.rgba)) for color in row.layer_colors)
    write_generated(V2/'frontend.bin',bytes(bank))
    write_generated(V2/'extension.packet',packet(compiler,[]))
    write_generated(V2/'options_chrome.packet',packet(compiler,chrome))
    # Font parsing can expose original layers that contribute no sprite or
    # selected face. Remove only this new pack's unreferenced generated links.
    cleanup=[];used={Path(path) for path in compiler.textures}
    retained={V2/path.relative_to(V1) for path in V1.rglob('*') if path.is_file() and path.name!='frontend.bin'}
    for row in compiler.font_records:
        for sheet in row['sheets']:
            path=Path(sheet['path'])
            if path in used or path in retained or not path.exists():continue
            before=artifact(path);source=Path(sheet['source_path']);origin=artifact(source)
            if path.parent!=V2/'textures' or before['sha256']!=sheet['sha256'] or origin['sha256']!=before['sha256']:
                raise ValueError('Unreferenced V2 font link differs from its observed source')
            civ5_ui_assets._unlink_font_target_without_attribute_changes(path)
            after=artifact(source)
            if any(after[k]!=origin[k] for k in ('bytes','sha256','file_identity','mtime_ns','file_attributes')):
                raise ValueError('Protected original font changed during V2 link retirement')
            cleanup.append(dict(**before,result='DELETED_ONLY_UNREFERENCED_NEW_V2_FONT_ALIAS',protected_source=after))
    if cleanup:
        cleanup_path=STAGE/'unused_font_cleanup.json'
        history=json.loads(cleanup_path.read_text('utf8')) if cleanup_path.exists() else []
        cleanup_path.write_text(json.dumps(history+cleanup,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
    if not compiler.unchanged():raise ValueError('Original UI/font sources changed during V2 preparation')
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.SetFileAttributesW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD]
    kernel.SetFileAttributesW.restype=wintypes.BOOL
    for path in V2.rglob('*'):
        if not path.is_file():continue
        info=os.stat(path,follow_symlinks=False)
        if info.st_file_attributes&0x400:raise ValueError('Refusing to seal a reparse asset')
        if info.st_file_attributes&1:continue
        # Never change attributes through a shared alias. Immutable shared
        # font/cache/V1 inputs must already be read-only before reuse.
        if info.st_nlink!=1:raise ValueError('Shared V2 input is not immutable at its source')
        if not kernel.SetFileAttributesW(str(path),info.st_file_attributes|1):raise ctypes.WinError(ctypes.get_last_error())
    for name,before in original_before.items():
        after=artifact(name)
        for key in ('bytes','sha256','file_identity','mtime_ns','file_attributes'):
            if after[key]!=before[key]:raise ValueError('Immutable V1/bc34 payload changed: '+name)
    output=dict(schema='zerosis.original_frontend.assets.v2',source_root=str(V2),runtime_root='UIFrontEnd',
        original_v1_preserved=True,immutable_v1_manifest=artifact(PROJECT/'evidence/game_menu/original_menu_followup/frontend/assets.json'),
        unchanged_v1_hardlinks=links,unchanged_v1_hardlink_count=len(links),options_control_layout=layout,
        layout_source='ACTUAL_SHARED_LUA_ORIGINAL_OPTIONS_ADAPTER_RETAINED_XML',native_geometry_verified=False,
        fonts=[dict(size=size,style=style,glyphs=len(font.glyphs),ggxml=artifact(font.ggxml_path)) for size,style,font in faces],
        original_options=artifact(PROJECT/'Source/Assets/UI/Assets/UI/Options/OptionsMenu.xml'),
        original_styles=artifact(GAME/'Assets/UI/Styles.xml'),inline_icon_catalog=artifact(icon_path),
        original_texture_sources=[*old_records,*compiler.assets.records],
        files=[artifact(path) for path in sorted(V2.rglob('*')) if path.is_file()],native_execution=False,sdk_loaded=False,
        host_or_sdk_or_window_executed=False,gpu_execution=False)
    (STAGE/'assets_v2.json').write_text(json.dumps(output,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
    return output


if __name__=='__main__':
    result=prepare_v2();print(json.dumps(dict(status='PASS_ORIGINAL_FRONTEND_V2_ASSETS_PREPARED_NOT_EXECUTED',
        files=len(result['files']),reused_hardlinks=result['unchanged_v1_hardlink_count'],fonts=len(result['fonts']))))
