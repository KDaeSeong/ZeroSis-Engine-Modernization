"""Source-derived confirmation layout and real model/view, without a window.

The immutable V3 bank, original XML/active styles and actual Korean strings are
read only. The console uses a value-only display backend. No image, new asset
pack, font, Host, SDK, HWND, GPU, native display or audio path is produced/run.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import struct
import sys
import xml.etree.ElementTree as ET

sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[1]
sys.path[:0]=[str(PROJECT/'tools'),str(PROJECT/'Tests')]
from menu_replay_restoration import build_cxx14
from menu_replay_legend_assets import artifact
from menu_frontend_skin import FrontEndSkin
from menu_suite_storage import storage
from native_build import run

BASE=PROJECT/'evidence/game_menu/options_video_preview/view'
ASSETS=PROJECT/'Source/Assets/UIFrontEndV4'
MANIFEST=PROJECT/'evidence/game_menu/native_offline_followup/frontend_v4/assets_v4.json'
RUNTIME=PROJECT/'Build/InteractiveGameRuntime/20261105T123201Z_9a1a8fa8c1a2'
ORIGINAL=PROJECT/'Source/Assets/UI/Assets/UI/Options/OptionsMenu.xml'


def read_bank():
    raw=(ASSETS/'frontend.bin').read_bytes();at=8
    if raw[:8]!=b'ZSMFE002':raise ValueError('Expected unchanged V3 bank contract')
    def take(fmt):
        nonlocal at
        values=struct.unpack_from(fmt,raw,at);at+=struct.calcsize(fmt);return values
    def word():return take('<I')[0]
    def text():
        nonlocal at
        count=word();value=raw[at:at+count].decode('utf8');at+=count;return value
    for _ in range(word()):take('<IQQ4f');text();text()
    fonts={}
    for _ in range(word()):
        size=word();style=text();line,baseline,border,layers,glyphs=take('<ii fII')
        for _ in range(layers):take('<I4f')
        entries={}
        for _ in range(glyphs):
            codepoint=word();entries[codepoint]=take('<9i')
        fonts[(size,style)]=dict(line=line,baseline=baseline,border=border,glyphs=entries)
    textures={}
    for _ in range(word()):name=text();textures[name]=take('<III')
    styles={}
    for _ in range(word()):
        name=text();kind,index,width,height,stepx,stepy,pieces=take('<II4fI')
        styles[name]=dict(kind=kind,index=index,width=width,height=height,step=(stepx,stepy),pieces=[take('<II4f') for _ in range(pieces)])
    return fonts,textures,styles


def pair(value):
    parts=value.split(',') if ',' in value else value.split('.')
    if len(parts)!=2:raise ValueError('Expected one original coordinate pair')
    return tuple(float(x) for x in parts)


def anchored(parent,size,attrs):
    px,py,pw,ph=parent;w,h=size;ox,oy=pair(attrs.get('Offset','0,0'))
    ax,ay=attrs.get('Anchor','L,T').replace('.',',').upper().split(',')
    sx,sy=attrs.get('AnchorSide','I,I').replace('.',',').upper().split(',')
    def axis(span,length,offset,anchor,side,near,far):
        if anchor=='C':return (span-length)/2+offset
        if anchor==far:return span+offset if side=='O' else span-length-offset
        if anchor==near:return -length-offset if side=='O' else offset
        raise ValueError('Unexpected original anchor')
    return (px+axis(pw,w,ox,ax,sx,'L','R'),py+axis(ph,h,oy,ay,sy,'T','B'),w,h)


def measured(text,font,width):
    lines=1;advance=0;nonempty=False;maximum=0;at=0
    while at<len(text):
        ch=text[at];at+=1
        if ch in '\r\n':
            if ch=='\r' and at<len(text) and text[at]=='\n':at+=1
            maximum=max(maximum,advance);advance=0;nonempty=False;lines+=1;continue
        glyph=font['glyphs'].get(ord(ch),font['glyphs'].get(ord('?')))
        if glyph is None:raise ValueError('Missing existing glyph fallback')
        next_width=sum(glyph[:3])
        if nonempty and advance+next_width>width:maximum=max(maximum,advance);advance=0;nonempty=False;lines+=1
        advance+=next_width;nonempty=True
    return dict(lines=lines,width=max(maximum,advance),height=lines*font['line'])


def source_inputs():
    skin=FrontEndSkin(backend_manifest=RUNTIME/'bundle.manifest');styles=skin.selected_style_elements()
    selected=skin.resolve('UI/Options/OptionsMenu.xml')
    if selected['source']['sha256']!=artifact(ORIGINAL)['sha256']:raise ValueError('Snapshot is not the active original options XML')
    references={selected['source']['path']:selected['source']}
    for name in ['Grid9FrameButtons','Grid9DetailFive140','SmallButton','BaseButton','PopupLeftSideTreatment','PopupRightSideTreatment','PopupNotificationTopTreatment']:
        row=skin._style_records[name]['source'];references[row['path']]=row
    return skin,styles,list(references.values())


def metadata(path,manifest,styles):
    root=ET.parse(ORIGINAL).getroot();parents={id(child):node for node in root.iter() for child in node}
    by_id={node.get('ID'):node for node in root.iter() if node.get('ID')}
    keys={row['text'] for row in manifest['options_control_layout'] if row['text']}
    keys.update(['TXT_KEY_MULTIPLAYER_OPTIONS','TXT_KEY_OPSCREEN_RESOLUTION','TXT_KEY_OPSCREEN_APPLY_RESOLUTION',
        'TXT_KEY_OPSCREEN_RESOLUTION_TIMER','TXT_KEY_YES_BUTTON','TXT_KEY_NO_BUTTON'])
    database=sqlite3.connect((RUNTIME/'localization.db').as_uri()+'?mode=ro&immutable=1',uri=True)
    labels={}
    try:
        for key in sorted(keys):
            lookup=key.strip('{}').split(':')[0];row=database.execute('SELECT Text FROM Language_ko_KR WHERE Tag=?',(lookup,)).fetchone()
            if not row or not row[0] or row[0].startswith('TXT_KEY_'):raise ValueError('Missing actual localized label: '+key)
            labels[key]=row[0]
    finally:database.close()
    fonts,textures,bank_styles=read_bank()
    coverage={}
    for key,size in [('TXT_KEY_OPSCREEN_APPLY_RESOLUTION',18),('TXT_KEY_OPSCREEN_RESOLUTION_TIMER',20),('TXT_KEY_YES_BUTTON',20),('TXT_KEY_NO_BUTTON',20)]:
        missing=sorted({char for char in labels[key] if ord(char) not in fonts[(size,'Shadow')]['glyphs']})
        if missing:raise ValueError('Existing source face lacks requested label characters: '+repr(missing))
        coverage[key]=dict(size=size,style='Shadow',missing=missing)
    if any(ord(ch) not in fonts[(24,'Shadow')]['glyphs'] for ch in '0123456789'):raise ValueError('Existing24px timer digits missing')
    message_node=by_id['CountdownMessage'];timer_node=by_id['CountdownTimer'];label_node=by_id['LabelStack'];button_node=by_id['ButtonStack']
    message=measured(labels['TXT_KEY_OPSCREEN_RESOLUTION_TIMER'],fonts[(20,'Shadow')],float(message_node.get('WrapWidth')))
    timer=measured('20',fonts[(24,'Shadow')],float(timer_node.get('WrapWidth')))
    countdown=by_id['Countdown'];frame_node=next(node for node in countdown if node.tag=='Grid')
    viewport=(0,0,1920,1080);frame=anchored(viewport,pair(frame_node.get('Size')),frame_node.attrib)
    button_sizes=[pair(node.get('Size')) for node in button_node if node.tag=='GridButton' and node.get('Hidden')!='1']
    gap=float(button_node.get('Padding'));button_size=(max(size[0] for size in button_sizes),sum(size[1] for size in button_sizes)+gap*(len(button_sizes)-1))
    label_size=(max(float(message_node.get('WrapWidth')),float(timer_node.get('WrapWidth'))),message['height']+float(label_node.get('Padding'))+timer['height'])
    bounds={'frame':frame,'labelStack':anchored(frame,label_size,label_node.attrib),'buttonStack':anchored(frame,button_size,button_node.attrib)}
    bounds['message']=anchored(bounds['labelStack'],(float(message_node.get('WrapWidth')),message['height']),message_node.attrib)
    timer_attrs=dict(timer_node.attrib);timer_attrs['Offset']='0,'+str(message['height']+float(label_node.get('Padding')))
    bounds['timer']=anchored(bounds['labelStack'],(float(timer_node.get('WrapWidth')),timer['height']),timer_attrs)
    bounds['yes']=anchored(bounds['buttonStack'],button_sizes[0],by_id['CountYes'].attrib)
    no_attrs=dict(by_id['CountNo'].attrib);no_attrs['Offset']='0,'+str(button_sizes[0][1]+gap)
    bounds['no']=anchored(bounds['buttonStack'],button_sizes[1],no_attrs)
    for source_style,target in [('PopupLeftSideTreatment','leftDecoration'),('PopupRightSideTreatment','rightDecoration')]:
        style=styles[source_style];box=anchored(frame,(0,0),style.attrib);image=next(iter(style));bounds[target]=anchored(box,pair(image.get('Size')),image.attrib)
    top_style=styles['PopupNotificationTopTreatment'];top_box=anchored(frame,(0,0),top_style.attrib);image=next(iter(top_style))
    bounds['topDecoration']=anchored(top_box,pair(image.get('Size')),image.attrib);image_frame=next(iter(image))
    bounds['notificationFrame']=anchored(bounds['topDecoration'],pair(image_frame.get('Size')),image_frame.attrib)
    glow=next(iter(image_frame));bounds['glow']=anchored(bounds['notificationFrame'],pair(glow.get('Size')),glow.attrib)
    apply=by_id['ApplyResButton'];resolution=parents[id(apply)];video=parents[id(resolution)];outer=parents[id(video)]
    outer_bounds=anchored(viewport,pair(outer.get('Size')),outer.attrib);video_bounds=anchored(outer_bounds,pair(video.get('Size')),video.attrib)
    resolution_bounds=anchored(video_bounds,pair(resolution.get('Size')),resolution.attrib);bounds['apply']=anchored(resolution_bounds,pair(apply.get('Size')),apply.attrib)
    def source_style(name,target,state=0):
        node=styles[name]
        if node.find('GridData') is not None:node=styles[node.find('GridData').get('Style')]
        attrs=node.attrib;tx=textures[attrs['Texture'].lower()][0];pieces={}
        for row,names in enumerate([['UL','UC','UR'],['L','C','R'],['LL','LC','LR']]):
            for column,part in enumerate(names):
                w,h=pair(attrs[part+'Size']);u,v=pair(attrs.get(part+'TexStart','0,0'));pieces[(column,row)]=(u,v,w,h)
        x,y,width,height=target;step=pair(attrs.get('StateOffsetIncrement','0,0'));output=[]
        for row in range(3):
            for column in range(3):
                u,v,w,h=pieces[(column,row)]
                left=x if column==0 else x+width-w if column==2 else x+pieces[(0,row)][2]
                right=left+w if column!=1 else x+width-pieces[(2,row)][2]
                top=y if row==0 else y+height-h if row==2 else y+pieces[(column,0)][3]
                bottom=top+h if row!=1 else y+height-pieces[(column,2)][3]
                output.append((tx,[u+state*step[0],v+state*step[1],u+w+state*step[0],v+h+state*step[1]],[left,top,right,bottom]))
        if bank_styles[name]['index']!=tx:raise ValueError('Active source style is not the immutable bank style')
        return output
    groups={'frame':source_style('Grid9DetailFive140',frame),'apply_active':source_style('SmallButton',bounds['apply']),
        'apply_disabled':source_style('SmallButton',bounds['apply'],3),'yes':source_style('BaseButton',bounds['yes']),
        'yes_hover':source_style('BaseButton',bounds['yes'],1),'no':source_style('BaseButton',bounds['no'])}
    blob=bytearray()
    def word(value):blob.extend(struct.pack('<I',value))
    def text(value):raw=value.encode('utf8');word(len(raw));blob.extend(raw)
    word(len(labels))
    for key,value in sorted(labels.items()):text(key);text(value)
    word(len(bounds))
    for key,value in sorted(bounds.items()):text(key);blob.extend(struct.pack('<4f',*value))
    word(len(groups))
    for key,values in sorted(groups.items()):
        text(key);word(len(values))
        for index,source,target in values:word(index);blob.extend(struct.pack('<8f',*source,*target))
    word(message['lines']);word(timer['lines']);path.write_bytes(blob)
    names=['dec32x64left.dds','dec32x64right.dds','top512icontrim.dds','notificationframebase.dds','notificationgenericglow.dds']
    return dict(original_xml=artifact(ORIGINAL),source_bounds=bounds,localized_confirmation_labels={key:labels[key] for key in coverage},
        original_glyph_coverage=coverage,message_metrics=message,timer_metrics=timer,source_style_groups=list(groups),
        reused_decorations={name:list(textures[name]) for name in names},missing_decorations=0,
        source_alpha_animation=dict(glow.attrib),animation_policy='EXISTING_UISCENE_EXPLICIT_SPEED_BOUNCE_SOURCE_DERIVED_NOT_NATIVE_VERIFIED',
        native_animation_uv_or_label_equivalence_verified=False,metadata=artifact(path))


def stable(row):return tuple(row[key] for key in ('path','bytes','sha256','file_identity','mtime_ns','file_attributes'))


def main():
    if hashlib.sha256(MANIFEST.read_bytes()).hexdigest()!='dbd8c092a3ef9ca86498ef48bcdeb71b4151a97b011f1230ba35d09340fcaea7':raise ValueError('Immutable V3 manifest differs')
    manifest=json.loads(MANIFEST.read_bytes());skin,styles,original_refs=source_inputs()
    inputs=[Path(__file__),Path(__file__).with_suffix('.cpp'),PROJECT/'Source/Host/MenuResolutionPreviewLayout.h',
        PROJECT/'Source/Host/MenuFrontEndOptionsView.h',PROJECT/'Source/Host/MenuFrontEndOptionsModel.h',PROJECT/'Source/Host/MenuOptionsContract.h',
        PROJECT/'Source/Host/MenuResolutionCountdown.h',PROJECT/'Source/Host/MenuFrontEndAssets.h',PROJECT/'Source/Host/MenuFrontEndGridLayout.h',
        PROJECT/'Source/Host/UiScene.lua',PROJECT/'Tests/menu_frontend_scene_fixture.h',ORIGINAL,ORIGINAL.with_suffix('.lua'),MANIFEST,
        RUNTIME/'localization.db',*[Path(row['path']) for row in original_refs]]
    inputs+=list(ASSETS.rglob('*'));inputs=sorted({str(path.absolute()):path for path in inputs if path.is_file()}.values(),key=lambda p:str(p).casefold())
    before=[artifact(path) for path in inputs];signature=hashlib.sha256(json.dumps(before,sort_keys=True).encode()).hexdigest()[:16]
    stage=BASE/signature;build=PROJECT/'Build/MenuResolutionPreviewView'/signature;receipt=stage/'result.json'
    if receipt.exists() or build.exists():raise ValueError('Inspect the existing exact-input result instead of replaying it')
    stage.mkdir(parents=True,exist_ok=True);build.mkdir(parents=True,exist_ok=False)
    report=dict(schema='zerosis.options.resolution_preview.view.v1',input_signature=signature,inputs_before=before,
        host_sdk_hwnd_gpu_native_display_or_audio_executed=False,actual_model_included=True,
        new_asset_pack_or_font_or_texture_created=False,new_png_created=False,owned_intermediate_cleanup=[])
    cleanup=['fixture.bin','MenuResolutionPreviewView.obj','MenuResolutionPreviewView.map','compile.rsp','read_build_environment.cmd']
    try:
        report['source_layout_and_actual_labels']=metadata(build/'fixture.bin',manifest,styles)
        compiled=build_cxx14('MenuResolutionPreviewView',build,stage,PROJECT/'Tests/menu_resolution_preview_view.cpp',[PROJECT/'Source/Host',PROJECT/'Tests'])
        report['build']=compiled
        imported=run([Path(compiled['compiler']).with_name('dumpbin.exe'),'/dependents',compiled['path']],cwd=build,timeout=30)
        names=sorted(set(re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$',imported.stdout.decode('mbcs',errors='replace'),re.M)))
        if imported.returncode or {name.lower() for name in names}!={'kernel32.dll'}:raise ValueError('Unexpected controlled view import '+repr(names))
        report['component_imported_dlls']=names
        result=run([compiled['path'],str(ASSETS),str(build/'fixture.bin')],cwd=build,timeout=30)
        if result.returncode:raise ValueError((result.stdout+result.stderr).decode('utf8',errors='replace'))
        report.update(json.loads(result.stdout));report['inputs_after']=[artifact(row['path']) for row in before]
        if [stable(row) for row in report['inputs_after']]!=[stable(row) for row in before]:raise ValueError('Source or protected V3/labels changed during controlled view check')
        if not all(artifact(ASSETS/Path(row['path']).relative_to(ASSETS))['file_attributes']&1 for row in manifest['files']):raise ValueError('Immutable V3 member is mutable')
        skin.unchanged();report['immutable_v3_and_originals_preserved']=True
    except Exception as error:
        report.update(status='FAIL_ACTUAL_OPTIONS_MODEL_RESOLUTION_PREVIEW_VIEW',error=str(error));raise
    finally:
        for name in cleanup:
            path=build/name
            if not path.exists():continue
            info=storage.ordinary(path)
            if path.parent.absolute()!=build.absolute() or info.st_nlink!=1:raise ValueError('View cleanup escaped its exact private intermediate')
            row=dict(artifact(path),allocated_bytes=storage.allocated(path));path.unlink()
            row['result']='DELETED_EXACT_OWNED_REGENERABLE_RESOLUTION_VIEW_INTERMEDIATE';report['owned_intermediate_cleanup'].append(row)
        report['intermediate_allocated_bytes_removed']=sum(row['allocated_bytes'] for row in report['owned_intermediate_cleanup'])
        receipt.write_text(json.dumps(report,ensure_ascii=True,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(status=report['status'],checks=report['checks'],report=str(receipt),
        reused_decorations=5,new_assets=0,new_png=0,removed_intermediates=len(report['owned_intermediate_cleanup']),
        intermediate_allocated_bytes_removed=report['intermediate_allocated_bytes_removed'])))
    return 0


if __name__=='__main__':raise SystemExit(main())
