"""Verbatim original DrawGraph differential goldens; no Host, SDK or window."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import random
import struct
import sys
import xml.etree.ElementTree as ET

sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[1]
sys.path[:0]=[str(PROJECT/'tools'),str(PROJECT/'Tests')]
from economic_overview_scene import execute_lua
from menu_replay_restoration import build_cxx14
from native_build import run
from prepare_ui_popup_assets import lua_value
from menu_frontend_skin import artifact,require
from retained_menu_suite_host_input import PE
from menu_replay_graph_colors import JSON_LUA

EVIDENCE=PROJECT/'evidence/game_menu/replay_scroll_graph/graph'
BUILD=EVIDENCE/'component'
GAME=Path(r"C:/Program Files (x86)/Steam/steamapps/common/Sid Meier's Civilization V")
VIEWER=GAME/'Assets/UI/InGame/Popups/ReplayViewer.lua'
FROZEN_VIEWER=PROJECT/'Source/Assets/UI/Assets/UI/InGame/Popups/ReplayViewer.lua'
XML=GAME/'Assets/DLC/Expansion2/UI/InGame/Popups/ReplayViewer.xml'
LUA_PROVIDER=PROJECT/'Build/SharedLuaRuntime/Lua/ZeroSisLua51_x64.dll'
HEADER=PROJECT/'Source/Host/MenuReplayGraphGeometry.h'
CPP=PROJECT/'Tests/menu_replay_graph_geometry.cpp'


def write(path,value):
    data=json.dumps(value,indent=2,ensure_ascii=False)+'\n'
    if path.exists():
        require(path.read_text('utf8')==data,'Refusing to replace different completed graph geometry evidence')
    else:
        path.write_text(data,encoding='utf8')


def original_blocks():
    require(artifact(VIEWER)['sha256']==artifact(FROZEN_VIEWER)['sha256'],
            'Original installed/frozen ReplayViewer.lua differs')
    source=VIEWER.read_text('utf-8-sig')
    markers=(('DrawGraph','\t\tDrawGraph = function(panel)','\t\tRefresh = function(panel)'),
             ('PadHorizontalValues','\t\tPadHorizontalValues = function(minTurn, maxTurn)',
              '\t\tCreateUpdateHandler = function(panel)'))
    blocks={};proof=[]
    for name,start,end in markers:
        require(source.count(start)==1,'Original graph source block is ambiguous: '+name)
        a=source.index(start);b=source.index(end,a);value=source[a:b]
        blocks[name]=value
        proof.append(dict(name=name,first_line=source.count('\n',0,a)+1,
            last_line=source.count('\n',0,b)+1,bytes=len(value.encode('utf8')),
            sha256=hashlib.sha256(value.encode('utf8')).hexdigest(),verbatim=True))
    draw=blocks['DrawGraph']
    for text in ('local numSegments = 100;','local numVerts = numSegments + 1;',
        'local beforeTurn = math.floor(turn);','local afterTurn = math.floor(turn);',
        'local maxScore = 0;','local newRange = range + numSegments - range % numSegments;',
        'lineSegment.LineSegment:SetStartVal(startX, startY);',
        'lineSegment.LineSegment:SetEndVal(endX, endY);'):
        require(text in draw,'Original DrawGraph algorithm shape changed')
    root=ET.parse(XML).getroot()
    canvas=[node for node in root.iter() if node.get('ID')=='GraphCanvas']
    line=root.find("Instance[@Name='GraphLineInstance']/Line")
    require(len(canvas)==1 and canvas[0].get('Size')=='720,360' and line is not None and line.get('Width')=='1',
            'Original graph canvas or line style differs')
    return blocks,dict(source=artifact(VIEWER),active_xml=artifact(XML),blocks=proof,
        canvas_attributes=dict(canvas[0].attrib),line_attributes=dict(line.attrib),
        entire_script_executed=False,source_display_policy='ORIGINAL_100_SEGMENTS_101_FLOOR_SAMPLES_NOT_ALL_RAW_POINTS')


def sparse(points):return dict(kind=0,points=[list(point) for point in points])
def dense(first,count,pattern=0,low=0,high=0,spike=0):
    return dict(kind=1,first=first,count=count,pattern=pattern,low=low,high=high,spike=spike)
def player(*histories,hidden=False):return dict(dataSets=list(histories),hidden=hidden)


def cases():
    values=[]
    def add(name,initial,final,players,dataSet=0,names=1):
        values.append(dict(name=name,initial=initial,final=final,players=players,dataSet=dataSet,names=names))
    add('empty_roster',0,100,[])
    add('empty_history',0,100,[player(sparse([]))])
    add('missing_selected_dataset',0,100,[player(sparse([(0,1000000)]))],1,2)
    for value in (0,9,-9):add('constant_'+str(value),0,100,[player(dense(0,101,low=value))])
    add('negative_only_max_starts_zero',0,100,[player(sparse([(0,-7),(30,-3),(100,-1)]))])
    add('divisible_range_still_expands',0,100,[player(dense(0,101,pattern=2,low=0,high=4))])
    add('nondivisible_range',0,100,[player(dense(0,101,pattern=2,low=1,high=6))])
    add('int32_extremes',40,140,[player(dense(40,101,pattern=2,low=-2147483648,high=2147483647))])
    add('sparse_endpoint_gaps',0,100,[player(sparse([(0,1),(1,3),(10,9),(13,4),(40,7),(99,2),(100,5)]))])
    for initial in (0,10):
        for span in range(4):add('padded_'+str(initial)+'_'+str(span),initial,initial+span,
            [player(dense(initial,span+1,pattern=1,low=5))])
    add('selected_second_dataset',0,100,[player(dense(0,101,pattern=2,low=-2147483648,high=2147483647),
        dense(0,101,pattern=2,low=5,high=6))],1,2)
    add('hidden_scale_includes_other_player',0,100,[player(dense(0,101,low=1)),
        player(dense(0,101,pattern=3,low=-1000,high=5000,spike=23),hidden=True)])
    add('all_hidden_still_has_data',0,100,[player(dense(0,101,pattern=1,low=20),hidden=True)])
    # Source floor((58/100)*100) is 57, so absent58 must not create a gap.
    add('double_floor_order_absent_58',0,100,[player(sparse([(turn,turn*9) for turn in range(101) if turn!=58]))])
    add('double_floor_order_absent_57',0,100,[player(sparse([(turn,turn*9) for turn in range(101) if turn!=57]))])
    for missing in (57,58):
        add('large_initial_offset_floor_absent_'+str(missing),9000000,9000100,
            [player(sparse([(9000000+turn,turn*9) for turn in range(101) if turn!=missing]))])
    add('large_initial_padded_domain',9000000,9000003,[player(dense(9000000,4,pattern=1,low=5))])
    add('beyond_old_1024_stride',0,1024,[player(dense(0,1025,pattern=1,low=-300))])
    add('source_maximum_6400_lines',0,1000,[player(dense(0,1001,pattern=2,low=-index,high=index+100)) for index in range(64)])
    add('million_turn_full_raw_scale_spike',0,1000000,[player(dense(0,1000001,pattern=3,low=1,high=2147483647,spike=123457))])
    add('near_aggregate_two_million_records',0,1000000,[
        player(dense(0,999000,pattern=2,low=-2147483648,high=-1)),
        player(dense(0,999000,pattern=2,low=1,high=2147483647),hidden=True)])
    rng=random.Random(0xC1F5100)
    for index in range(80):
        initial=rng.randrange(0,500);span=rng.randrange(0,320);roster=[]
        for _ in range(rng.randrange(0,7)):
            points=[(turn,rng.randrange(-50000,50001)) for turn in range(initial,initial+span+1) if rng.randrange(4)]
            roster.append(player(sparse(points),hidden=bool(rng.randrange(2))))
        add('deterministic_sparse_'+str(index),initial,initial+span,roster)
    return values


ORACLE_SETUP=r'''
local function buildScores(histories)
 local scores={}
 for dataSet,history in ipairs(histories) do
  local function point(turn,value)
   local row=scores[turn];if row==nil then row={};scores[turn]=row end
   row[dataSet-1]=value
  end
  if history.kind==0 then for _,value in ipairs(history.points) do point(value[1],value[2]) end
  else
   for index=0,history.count-1 do
    local value=history.low
    if history.pattern==1 then value=value+index
    elseif history.pattern==2 then if index%2==1 then value=history.high end
    elseif history.pattern==3 then if index==history.spike then value=history.high end
    else assert(history.pattern==0) end
    point(history.first+index,value)
   end
  end
 end
 return scores
end
local function oracle(case)
 local observed={ticks={},domain={}}
 local g_ReplayInfo={InitialTurn=case.initial,FinalTurn=case.final,PlayerInfo={}}
 for _,entry in ipairs(case.players) do g_ReplayInfo.PlayerInfo[#g_ReplayInfo.PlayerInfo+1]={Scores=buildScores(entry.dataSets)} end
 local Controls={GraphCanvas={GetSizeVal=function() return 720,360 end},
  NoGraphData={SetHide=function(_,value) observed.noDataHidden=value end}}
 local g_GraphVerticalMarkers={}
 for index=1,5 do local slot=index;g_GraphVerticalMarkers[index]={SetText=function(_,value) observed.ticks[slot]=value end} end
 local g_GraphHorizontalMarkers={1,2,3,4,5}
 local g_LineSegmentInstanceManager={ResetInstances=function() end,GetInstance=function()
  local line={}
  function line:SetStartVal(x,y) self.sx=x;self.sy=y end
  function line:SetEndVal(x,y) self.ex=x;self.ey=y end
  function line:SetColorVal(r,g,b,a) self.color={r,g,b,a} end
  function line:SetHide(value) self.hidden=value end
  return {LineSegment=line}
 end}
 local panel={CurrentGraphDataSetIndex=case.dataSet,SegmentsByPlayer={},GraphLegendsByPlayer={},PlayerGraphColors={}}
 for index,entry in ipairs(case.players) do
  local hidden=entry.hidden
  panel.GraphLegendsByPlayer[index]={ShowHide={IsChecked=function() return not hidden end}}
  panel.PlayerGraphColors[index]={Red=1,Green=1,Blue=1,Alpha=1}
 end
'''


def original_lua_goldens(blocks,inputs):
    script=JSON_LUA+'\nlocal cases='+lua_value(inputs)+'\n'+ORACLE_SETUP
    script+='\nlocal originalPad={\n'+blocks['PadHorizontalValues']+'\n}\n'
    script+=r'''
 panel.PadHorizontalValues=function(minTurn,maxTurn)
  local a,b=originalPad.PadHorizontalValues(minTurn,maxTurn);observed.domain={a,b};return a,b
 end
 local originalDraw={
'''+blocks['DrawGraph']+r'''
 }
 panel.DrawGraph=originalDraw.DrawGraph;panel:DrawGraph()
 local series={};local visible=0;local total=0
 for index=1,#case.players do
  local lines={}
  for _,instance in ipairs(panel.SegmentsByPlayer[index] or {}) do
   local line=instance.LineSegment;assert(line.sx~=nil and line.ex~=nil)
   lines[#lines+1]={line.sx,line.sy,line.ex,line.ey,line.hidden}
   total=total+1;if not line.hidden then visible=visible+1 end
  end
  series[index]=lines
 end
 return {hasData=not not observed.noDataHidden,ticks=observed.ticks,domain=observed.domain,
  series=series,totalSegments=total,visibleSegments=visible}
end
local results={}
for _,case in ipairs(cases) do results[#results+1]=oracle(case);collectgarbage('collect') end
return json(results)
'''
    require('return720' not in script,'Oracle canvas function has a malformed return statement')
    return execute_lua(script)


def history_count(history):return len(history['points']) if history['kind']==0 else history['count']


def fixture_bytes(path,inputs,goldens):
    data=bytearray(b'ZSGEO001'+struct.pack('<I',len(inputs)))
    def u32(value):data.extend(struct.pack('<I',value))
    def i32(value):data.extend(struct.pack('<i',value))
    def i64(value):data.extend(struct.pack('<q',value))
    def text(value):
        raw=value.encode('utf8');u32(len(raw));data.extend(raw)
    def history(value):
        u32(value['kind']);u32(history_count(value))
        if value['kind']==0:
            for turn,score in value['points']:i32(turn);i32(score)
        else:
            for field in ('first','pattern','low','high','spike'):i32(value[field])
    for case,expected in zip(inputs,goldens):
        text(case['name']);i32(case['initial']);i32(case['final']);u32(case['dataSet']);u32(case['names']);u32(len(case['players']))
        for entry in case['players']:
            u32(int(entry['hidden']));u32(len(entry['dataSets']))
            for value in entry['dataSets']:history(value)
        u32(int(expected['hasData']))
        if expected['hasData']:
            for value in expected['domain']:i32(value)
            i64(expected['ticks'][0]);i64(expected['ticks'][-1])
            for value in expected['ticks']:i64(value)
        for series in expected['series']:
            u32(len(series))
            for line in series:
                for value in line[:4]:i32(value)
        u32(expected['visibleSegments'])
        u32(sum(history_count(entry['dataSets'][case['dataSet']]) for entry in case['players'] if case['dataSet']<len(entry['dataSets'])))
    path.write_bytes(data)


def main():
    EVIDENCE.mkdir(parents=True,exist_ok=True);BUILD.mkdir(exist_ok=True)
    require(not (EVIDENCE/'fixture_result.json').exists(),'Completed graph geometry component must not be repeated')
    protected=[HEADER,CPP,Path(__file__),PROJECT/'Source/Host/MenuReplayData.h',PROJECT/'Source/Host/MenuReplayCalendar.h',
               VIEWER,FROZEN_VIEWER,XML,LUA_PROVIDER]
    before=[artifact(path) for path in protected]
    require(artifact(LUA_PROVIDER)['sha256']=='4873cded3ddf52366abc7964e3d3e10546f88e983d966be93bce3465ef85d944',
            'Existing pure Lua5.1 provider differs')
    blocks,source=original_blocks();inputs=cases();goldens=original_lua_goldens(blocks,inputs)
    require(len(goldens)==len(inputs),'Original DrawGraph oracle result count differs')
    by_name={case['name']:expected for case,expected in zip(inputs,goldens)}
    require(by_name['source_maximum_6400_lines']['totalSegments']==6400,'Original 64-player maximum segment bound not exercised')
    require(by_name['all_hidden_still_has_data']['hasData'] and by_name['all_hidden_still_has_data']['visibleSegments']==0,
            'Original all-hidden data availability differs')
    require(by_name['constant_9']['ticks']==[9,10,11,12,13] and by_name['constant_0']['ticks']==[0,1,2,3,4],
            'Original constant-axis expansion differs')
    require(by_name['empty_history']['ticks']==['']*5 and not by_name['empty_history']['hasData'],
            'Original no-data markers were not cleared')
    require(by_name['constant_0']['series'][0][34][2]==251 and
            by_name['constant_0']['series'][0][69][2]==503,
            'Original X floor operation order was not exercised')
    require(by_name['negative_only_max_starts_zero']['ticks']==[-7,-5,-3,-1,1],
            'Original negative-only upper bound differs')
    require(by_name['divisible_range_still_expands']['ticks']==[0,2,4,6,8],
            'Original already-divisible range did not expand')
    require(by_name['double_floor_order_absent_58']['totalSegments']==100 and
            by_name['double_floor_order_absent_57']['totalSegments']<100,
            'Original floating sample-boundary floor behavior was not exercised')
    require(by_name['large_initial_offset_floor_absent_58']['totalSegments']==100 and
            by_name['large_initial_offset_floor_absent_57']['totalSegments']<100,
            'Original relative-offset floor differs from flooring an absolute floating turn')
    require(by_name['million_turn_full_raw_scale_spike']['ticks'][-1]>=2147483647,
            'Original million-point scale ignored an unsampled spike')
    temporary=BUILD/'goldens.bin';fixture_bytes(temporary,inputs,goldens);input_pin=artifact(temporary)
    built=build_cxx14('MenuReplayGraphGeometryComponent',BUILD,EVIDENCE,CPP,[PROJECT/'Source/Host'])
    imports=PE(Path(built['path']).read_bytes()).imports()
    require({name.casefold() for name in imports}=={'kernel32.dll'},'Graph geometry component imports beyond Kernel32')
    result=run([built['path'],temporary],cwd=BUILD,timeout=60)
    require(result.returncode==0,'Original graph geometry C++14 mismatch: '+
            (result.stdout+result.stderr).decode('utf8',errors='replace'))
    actual=json.loads(result.stdout.decode('utf8'))
    require(actual['cases']==len(inputs) and actual['maximum_case_segments']==6400 and actual['largest_history']==1000001,
            'Actual graph geometry component coverage differs')
    require([artifact(path) for path in protected]==before,'Original/provider/geometry source inputs changed during fixture')
    write(EVIDENCE/'goldens.json',dict(schema='zerosis.replay_graph_geometry.verbatim_original_lua_goldens.v1',
        original_source=source,history_generators_are_test_inputs_not_expected_algorithms=True,
        cases=[dict(case,expected=golden) for case,golden in zip(inputs,goldens)],
        original_line_setters_are_record_only_fixtures=True,original_script_or_native_ui_executed=False))
    cleanup=[]
    for path in (temporary,BUILD/'MenuReplayGraphGeometryComponent.obj',BUILD/'compile.rsp',BUILD/'read_build_environment.cmd'):
        if not path.exists():continue
        require(path.absolute().parent==BUILD.absolute() and not path.is_symlink(),'Graph geometry cleanup escaped its owned component')
        row=artifact(path);path.unlink();cleanup.append(dict(**row,result='DELETED_OWNED_REGENERABLE_GRAPH_GEOMETRY_INTERMEDIATE'))
    report=dict(schema='zerosis.replay_graph_geometry.component.v1',status='PASS_VERBATIM_ORIGINAL_100_SEGMENT_GRAPH_GEOMETRY_CXX14',
        original_source=source,goldens=artifact(EVIDENCE/'goldens.json'),input_fixture_retired=input_pin,build=built,component=actual,
        imports=imports,inputs_before=before,protected_inputs_unchanged=True,cleanup=cleanup,
        full_recorded_scale_scan=True,source_sampling_preserved=True,no_authored_point_markers=True,
        hidden_series_do_not_change_scale_or_data_availability=True,no_document_copy_or_mutation_in_selector=True,
        pure_lua51_and_cpp14_console_executed=True,native_host_sdk_window_gpu_or_clr_executed=False,
        original_game_settings_saves_or_mods_written=False,retail_pixel_acceptance=False)
    write(EVIDENCE/'fixture_result.json',report)
    print(json.dumps(dict(actual,status=report['status'],imports=imports,cleaned_files=len(cleanup))))


if __name__=='__main__':main()
