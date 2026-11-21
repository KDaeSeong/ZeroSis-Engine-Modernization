"""Compare pure pointer guides with the verbatim original Lua 5.1 closure."""
from __future__ import annotations
import argparse
import gzip
import hashlib
import inspect
import json
import math
from pathlib import Path
import random
import re
import struct
import sys
import xml.etree.ElementTree as ET

sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[1]
sys.path[:0]=[str(PROJECT/'tools'),str(PROJECT/'Tests')]
from menu_replay_restoration import build_cxx14
from native_build import run
from menu_replay_assets import artifact
from menu_suite_storage import storage
from economic_overview_scene import execute_lua
from prepare_ui_popup_assets import lua_value

GAME=Path(r"C:/Program Files (x86)/Steam/steamapps/common/Sid Meier's Civilization V")
VIEWER=PROJECT/'Source/Assets/UI/Assets/UI/InGame/Popups/ReplayViewer.lua'
XML=PROJECT/'Source/Assets/UI/Assets/DLC/Expansion2/UI/InGame/Popups/ReplayViewer.xml'
PROVIDER=PROJECT/'Build/SharedLuaRuntime/Lua/ZeroSisLua51_x64.dll'
IDS=('VerticalMouseCrosshair','HorizontalMouseCrosshair','VerticalMouseGuide','HorizontalMouseGuide')


def require(value,why):
    if not value:raise ValueError(why)


def original():
    installed_lua=GAME/'Assets/UI/InGame/Popups/ReplayViewer.lua'
    installed_xml=GAME/'Assets/DLC/Expansion2/UI/InGame/Popups/ReplayViewer.xml'
    require(VIEWER.read_bytes()==installed_lua.read_bytes(),'Installed/frozen original replay Lua differs')
    require(XML.read_bytes()==installed_xml.read_bytes(),'Installed/frozen active replay XML differs')
    require(artifact(PROVIDER)['sha256']=='4873cded3ddf52366abc7964e3d3e10546f88e983d966be93bce3465ef85d944',
        'Existing pure Lua 5.1 provider changed')
    source=VIEWER.read_text('utf-8-sig');start='\t\tCreateUpdateHandler = function(panel)';end='\t\tDrawGraph = function(panel)'
    require(source.count(start)==1 and source.count(end)==1,'Original pointer closure is ambiguous')
    a=source.index(start);b=source.index(end,a);block=source[a:b]
    for token in ('local xRelative = x - xAbsoluteOffset;','local yRelative = y - yAbsoluteOffset;',
        'xRelative > 0 and xRelative < graphDisplayWidth and','yRelative > 0 and yRelative < graphDisplayHeight',
        'local horizontalMouseGuideEnd = graphDisplayWidth + 8;','local verticalMouseGuideEnd = graphDisplayHeight + 8;',
        'if(not graphsPanel:IsHidden()) then'):
        require(token in block,'Original pointer-guide algorithm shape changed: '+token)
    root=ET.parse(XML).getroot();main=root.find(".//*[@ID='MainPanel']");graphs=root.find(".//*[@ID='GraphsPanel']")
    display=root.find(".//*[@ID='GraphDisplay']")
    require(main is not None and graphs is not None and display is not None,'Original graph XML controls missing')
    lines=[dict(node.attrib) for node in display.findall('Line') if node.get('ID') in IDS]
    require(tuple(row['ID'] for row in lines)==IDS,'Original guide XML paint order changed')
    require(all(row['Width']=='1' for row in lines),'Original pointer guide width changed')
    require([row['Color'] for row in lines]==['90,90,90,90']*2+['255,0,0,255']*2,'Original pointer guide colors changed')
    require(main.get('Size')=='920,440' and graphs.get('Offset')=='0,35' and display.get('Offset')=='160,20' and display.get('Size')=='720,360',
        'Original graph origin dimensions changed')
    proof=dict(source=artifact(VIEWER),active_xml=artifact(XML),installed_originals=[artifact(installed_lua),artifact(installed_xml)],
        closure=dict(first_line=source.count('\n',0,a)+1,last_line=source.count('\n',0,b)+1,
            bytes=len(block.encode()),sha256=hashlib.sha256(block.encode()).hexdigest(),verbatim=True),
        main=dict(main.attrib),graphs=dict(graphs.attrib),display=dict(display.attrib),ordered_line_attributes=lines,
        logical_1920x1080_origin=[660,375],original_visibility='Only GraphsPanel hidden and strict x/y internal bounds; no data/modal/capture condition.',
        output_coordinate_space='GraphDisplay-local; owner adds its origin and uses a clip including right/bottom +8.')
    return block,lines,proof


def origin(config):
    x=(config['screen'][0]*.5)-(config['main'][0]*.5)
    x=x+config['graphs'][0]+config['display'][0]
    y=(config['screen'][1]*.5)-(config['main'][1]*.5)
    y=y+config['graphs'][1]+config['display'][1]
    return x,y


def cases():
    def config(name,screen=(1920,1080),main=(920,440),graphs=(0,35),display=(160,20),size=(720,360)):
        return dict(name=name,screen=list(screen),main=list(main),graphs=list(graphs),display=list(display),size=list(size))
    configurations=[config('source_1920x1080'),config('source_1280x720',(1280,720)),
        config('source_2560x1440',(2560,1440)),config('source_8192x8192',(8192,8192)),
        config('source_960x700',(960,700)),config('fractional_origin',(1920.25,1080.125)),
        config('synthetic_negative_origin',graphs=(-2000.25,-2000.125)),
        config('synthetic_small_extent',size=(1/256,7/16)),
        config('synthetic_maximum_geometry',(600,330),size=(9999992,9999992))]
    result=[]
    def add(name,geometry,pointer,visible=True):
        result.append(dict(name=name,geometry=geometry,pointer=pointer,graphsVisible=visible))
    for geometry in configurations:
        ox,oy=origin(geometry);width,height=geometry['size'];right,bottom=ox+width,oy+height
        xs=[ox,math.nextafter(ox,-math.inf),math.nextafter(ox,math.inf),ox+width*.5,
            math.nextafter(right,-math.inf),right,math.nextafter(right,math.inf)]
        ys=[oy,math.nextafter(oy,-math.inf),math.nextafter(oy,math.inf),oy+height*.5,
            math.nextafter(bottom,-math.inf),bottom,math.nextafter(bottom,math.inf)]
        for xi,x in enumerate(xs):
            for yi,y in enumerate(ys):add(geometry['name']+'_boundary_'+str(xi)+'_'+str(yi),geometry,(x,y))
        # Adjacent cases reuse the same original factory, so both line position
        # and hide/show transitions execute through the original retained closure.
        for index,visible in enumerate((True,False,True,False,False,True)):
            add(geometry['name']+'_show_hide_'+str(index),geometry,(ox+width*.5,oy+height*.5),visible)
    rng=random.Random(0x475549444553)
    for index in range(180):
        geometry=configurations[index%len(configurations)];ox,oy=origin(geometry);width,height=geometry['size']
        add('finite_random_'+str(index),geometry,(ox+width*rng.uniform(-.3,1.3),oy+height*rng.uniform(-.3,1.3)),index%11!=0)
    geometry=configurations[0];ox,oy=origin(geometry)
    for label,value in [('nan',math.nan),('positive_inf',math.inf),('negative_inf',-math.inf),
        ('maximum_finite',sys.float_info.max),('negative_maximum_finite',-sys.float_info.max)]:
        add('pointer_x_'+label,geometry,(value,oy+180));add('pointer_y_'+label,geometry,(ox+360,value))
    return result


def safe_number(value):
    if math.isnan(value):return 'nan'
    if math.isinf(value):return 'positive_inf' if value>0 else 'negative_inf'
    return value


def original_goldens(block,inputs):
    converted=[]
    for case in inputs:
        geometry=case['geometry'];converted.append(dict(geometry=geometry,graphsVisible=case['graphsVisible'],
            pointer=[safe_number(value) for value in case['pointer']]))
    script=r'''
local cases=@@CASES@@
local block=@@BLOCK@@
local current,controls,updater,geometryKey
local rebuilt=0
local function special(value)
 if value=='nan' then return 0/0 end
 if value=='positive_inf' then return 1/0 end
 if value=='negative_inf' then return -1/0 end
 return value
end
local function geometryIdentity(g)
 local values={}
 for _,key in ipairs({'screen','main','graphs','display','size'}) do
  for _,value in ipairs(g[key]) do values[#values+1]=string.format('%.17g',value) end
 end
 return table.concat(values,',')
end
local function build(g)
 local c={MainPanel={GetSizeX=function() return g.main[1] end,GetSizeY=function() return g.main[2] end},
  GraphsPanel={GetOffsetX=function() return g.graphs[1] end,GetOffsetY=function() return g.graphs[2] end,
   IsHidden=function() return not current.graphsVisible end},
  GraphDisplay={GetOffsetX=function() return g.display[1] end,GetOffsetY=function() return g.display[2] end,
   GetSizeX=function() return g.size[1] end,GetSizeY=function() return g.size[2] end}}
 for _,name in ipairs({'VerticalMouseCrosshair','HorizontalMouseCrosshair','VerticalMouseGuide','HorizontalMouseGuide'}) do
  local line={start={0,360},finish={0,360},hidden=false,hideCalls=0,coordinateCalls=0}
  function line:SetStartVal(x,y) self.start={x,y};self.coordinateCalls=self.coordinateCalls+1 end
  function line:SetEndVal(x,y) self.finish={x,y};self.coordinateCalls=self.coordinateCalls+1 end
  function line:SetHide(value) self.hidden=value;self.hideCalls=self.hideCalls+1 end
  c[name]=line
 end
 local manager={GetScreenSizeVal=function() return g.screen[1],g.screen[2] end,
  GetMousePos=function() return special(current.pointer[1]),special(current.pointer[2]) end}
 local chunk=assert(loadstring('return {\n'..block..'\n}','@original-ReplayViewer-CreateUpdateHandler.lua'))
 setfenv(chunk,{UIManager=manager,Controls=c})
 local methods=chunk();controls=c;updater=methods.CreateUpdateHandler({});rebuilt=rebuilt+1
end
local output={}
local visibleCount,hideWrites,coordinateWrites=0,0,0
for _,case in ipairs(cases) do
 current=case
 local identity=geometryIdentity(case.geometry)
 if geometryKey~=identity then build(case.geometry);geometryKey=identity end
 local beforeHide,beforeCoordinate=0,0
 for _,name in ipairs({'VerticalMouseCrosshair','HorizontalMouseCrosshair','VerticalMouseGuide','HorizontalMouseGuide'}) do
  local line=controls[name];beforeHide=beforeHide+line.hideCalls;beforeCoordinate=beforeCoordinate+line.coordinateCalls
 end
 updater()
 local visible=not controls.VerticalMouseCrosshair.hidden
 local lines={}
 for _,name in ipairs({'VerticalMouseCrosshair','HorizontalMouseCrosshair','VerticalMouseGuide','HorizontalMouseGuide'}) do
  local line=controls[name];assert(line.hidden==not visible)
  hideWrites=hideWrites+line.hideCalls;coordinateWrites=coordinateWrites+line.coordinateCalls
  if visible then
   lines[#lines+1]='['..string.format('%.17g,%.17g,%.17g,%.17g',line.start[1],line.start[2],line.finish[1],line.finish[2])..']'
  end
 end
 hideWrites=hideWrites-beforeHide;coordinateWrites=coordinateWrites-beforeCoordinate
 if visible then visibleCount=visibleCount+1 end
 output[#output+1]='{"visible":'..tostring(visible)..',"lines":['..table.concat(lines,',')..']}'
end
return '{"cases":['..table.concat(output,',')..'],"factories":'..rebuilt..',"visible":'..visibleCount..
 ',"hide_writes":'..hideWrites..',"coordinate_writes":'..coordinateWrites..'}'
'''
    script=script.replace('@@CASES@@',lua_value(converted)).replace('@@BLOCK@@',lua_value(block))
    result=execute_lua(script)
    require(len(result['cases'])==len(inputs) and result['hide_writes']==len(inputs)*4,'Original closure did not update all four hide states')
    require(result['coordinate_writes']==result['visible']*8,'Original closure coordinate updates differ from four line endpoints')
    return result


def write_fixture(path,inputs,goldens,styles):
    data=bytearray(b'ZSGUID01'+struct.pack('<I',len(inputs)))
    for style in styles:data.extend(struct.pack('<d4B',float(style['Width']),*map(int,style['Color'].split(','))))
    for case,expected in zip(inputs,goldens):
        name=case['name'].encode('ascii');data.extend(struct.pack('<I',len(name)));data.extend(name)
        ox,oy=origin(case['geometry']);width,height=case['geometry']['size'];x,y=case['pointer']
        data.extend(struct.pack('<6dII',ox,oy,width,height,x,y,int(case['graphsVisible']),int(expected['visible'])))
        coordinates=[value for line in expected['lines'] for value in line] if expected['visible'] else [0.0]*16
        require(len(coordinates)==16,'Original pointer line count differs');data.extend(struct.pack('<16d',*coordinates))
    path.write_bytes(data)


def main():
    cli=argparse.ArgumentParser(description=__doc__);cli.add_argument('--attempt',default='attempt01');args=cli.parse_args()
    if re.fullmatch('[a-z0-9_]{1,40}',args.attempt) is None:cli.error('Use a canonical owned attempt label')
    stage=PROJECT/'evidence/game_menu/replay_hover_frame/guides'/args.attempt
    build=PROJECT/'Build/MenuReplayPointerGuides'/args.attempt
    stage.mkdir(parents=True,exist_ok=True);build.mkdir(parents=True,exist_ok=True);receipt=stage/'result.json'
    require(not receipt.exists(),'Preserve completed evidence and choose a new explicit attempt')
    sources=[PROJECT/'Source/Host/MenuReplayPointerGuides.h',PROJECT/'Tests/menu_replay_pointer_guides.cpp',Path(__file__),
        VIEWER,XML,GAME/'Assets/UI/InGame/Popups/ReplayViewer.lua',GAME/'Assets/DLC/Expansion2/UI/InGame/Popups/ReplayViewer.xml',
        PROVIDER,PROJECT/'Tests/economic_overview_scene.py',PROJECT/'tools/prepare_ui_popup_assets.py',PROJECT/'tools/native_build.py']
    before=[artifact(path) for path in sources]
    require(not any(any(value>127 for value in path.read_bytes()) for path in sources[:2]),'C++14/windows1252 component source must be ASCII')
    report=dict(schema='zerosis.replay_hover_frame.pointer_guides.v1',attempt=args.attempt,inputs_before=before,
        compile_recipe_sha256=hashlib.sha256(inspect.getsource(build_cxx14).encode()).hexdigest(),
        native_execution=False,sdk_loaded=False,host_or_sdk_or_window_executed=False,gpu_execution=False,
        actual_renderer_or_d2d_d3d_executed=False,actual_controlled_lua51=True,
        owned_intermediate_cleanup=[],limits=['Exact source closure with record-only control setters; native UI/render acceptance is not executed.',
            'Synthetic geometry exercises finite capture bounds; it does not claim those dimensions occur in the installed native UI.',
            'Owner pointer absence is an explicit host condition; original Lua differential cases always have pointer availability.',
            'Hidden line positions are not rendered or compared; the original native controls retain previous hidden coordinates.'])
    cleanup=['pointer_guide_goldens.bin','MenuReplayPointerGuides.obj','MenuReplayPointerGuides.map','compile.rsp','read_build_environment.cmd']
    try:
        block,styles,report['original_source']=original();inputs=cases();oracle=original_goldens(block,inputs)
        report['original_lua']=dict(cases=len(inputs),visible_cases=oracle['visible'],factories=oracle['factories'],
            hide_writes=oracle['hide_writes'],coordinate_writes=oracle['coordinate_writes'],verbatim_closure=True,
            only_ui_manager_and_record_only_controls_stubbed=True,no_data_modal_or_capture_visibility_condition=True)
        fixture=build/'pointer_guide_goldens.bin';write_fixture(fixture,inputs,oracle['cases'],styles);report['temporary_golden_fixture']=artifact(fixture)
        safe_inputs=[]
        for case in inputs:safe_inputs.append(dict(case,pointer=[safe_number(value) for value in case['pointer']]))
        goldens=stage/'oracle_goldens.json.gz'
        with goldens.open('xb') as stream:stream.write(gzip.compress((json.dumps(dict(
            schema='zerosis.replay_hover_frame.pointer_guides.original_lua_goldens.v1',source=report['original_source'],
            cases=[dict(case,expected=expected) for case,expected in zip(safe_inputs,oracle['cases'])]),
            indent=2,allow_nan=False)+'\n').encode(),mtime=0))
        report['compressed_original_goldens']=artifact(goldens)
        compiled=build_cxx14('MenuReplayPointerGuides',build,stage,PROJECT/'Tests/menu_replay_pointer_guides.cpp',[PROJECT/'Source/Host'])
        report['build']=compiled
        imports=run([Path(compiled['compiler']).with_name('dumpbin.exe'),'/dependents',compiled['path']],cwd=build,timeout=30)
        names=sorted(set(re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$',imports.stdout.decode('mbcs',errors='replace'),re.M)))
        require(not imports.returncode and {name.lower() for name in names}=={'kernel32.dll'},'Pure pointer guide component has an unexpected DLL import')
        report['component_imported_dlls']=names
        result=run([compiled['path'],fixture],cwd=build,timeout=30)
        require(not result.returncode,'Original pointer-guide mismatch: '+(result.stdout+result.stderr).decode('utf8',errors='replace'))
        report['component']=json.loads(result.stdout)
        require(report['component']['original_lua_cases']==len(inputs),'C++ component did not consume every original Lua case')
        report['inputs_after']=[artifact(path) for path in sources]
        require(report['inputs_after']==before,'Original/helper inputs changed during controlled component check')
        report.update(status='PASS_VERBATIM_ORIGINAL_POINTER_GUIDES_LUA51_AND_CXX14',compiler_and_linker_warnings=0)
    except Exception as error:
        report.update(status='FAIL_ORIGINAL_POINTER_GUIDES_COMPONENT',error=str(error));raise
    finally:
        for leaf in cleanup:
            path=build/leaf
            if not path.exists():continue
            info=storage.ordinary(path)
            require(path.absolute().parent==build.absolute() and info.st_nlink==1,'Unsafe pointer-guide intermediate cleanup')
            row=dict(artifact(path),file_identity=[info.st_dev,info.st_ino],allocated_bytes=storage.allocated(path))
            require(storage.metadata(info)==storage.metadata(storage.ordinary(path)),'Pointer-guide cleanup identity changed')
            path.unlink();row['result']='DELETED_EXACT_OWNED_REGENERABLE_POINTER_GUIDE_INTERMEDIATE';report['owned_intermediate_cleanup'].append(row)
        report['owned_intermediate_bytes_removed']=sum(row['bytes'] for row in report['owned_intermediate_cleanup'])
        report['owned_intermediate_allocated_bytes_removed']=sum(row['allocated_bytes'] for row in report['owned_intermediate_cleanup'])
        with receipt.open('x',encoding='utf8',newline='\n') as stream:json.dump(report,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(status=report['status'],cases=report['component']['original_lua_cases'],checks=report['component']['checks'],
        report=str(receipt),removed_intermediates=len(report['owned_intermediate_cleanup']))))


if __name__=='__main__':raise SystemExit(main())
