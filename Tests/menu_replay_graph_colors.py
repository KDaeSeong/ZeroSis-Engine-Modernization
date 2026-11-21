"""Exact original Lua 5.1 graph-color goldens and an SDK-free C++14 selector."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import struct
import sys

sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[1]
sys.path[:0]=[str(PROJECT/'tools'),str(PROJECT/'Tests')]
from economic_overview_scene import execute_lua
from menu_replay_restoration import build_cxx14
from native_build import run
from prepare_ui_popup_assets import lua_value
from menu_frontend_skin import artifact,require
from menu_suite_storage import storage
from retained_menu_suite_host_input import PE

EVIDENCE=PROJECT/'evidence/game_menu/replay_calendar_legend/graph_colors'
BUILD=EVIDENCE/'component'
RUNTIME=PROJECT/'Build/InteractiveGameRuntime/20261103T140325Z_f127e4edebe9'
LUA_PROVIDER=PROJECT/'Build/SharedLuaRuntime/Lua/ZeroSisLua51_x64.dll'
VIEWER=Path(r"C:/Program Files (x86)/Steam/steamapps/common/Sid Meier's Civilization V/Assets/UI/InGame/Popups/ReplayViewer.lua")
FROZEN_VIEWER=PROJECT/'Source/Assets/UI/Assets/UI/InGame/Popups/ReplayViewer.lua'
CPP=PROJECT/'Tests/menu_replay_graph_colors.cpp'
HEADER=PROJECT/'Source/Host/MenuReplayGraphColors.h'


def write(path,value):
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf8')


def catalog():
    with sqlite3.connect((RUNTIME/'rules.db').as_uri()+'?mode=ro&immutable=1',uri=True) as database:
        colors=[dict(zip(('Type','Red','Green','Blue','Alpha'),row)) for row in database.execute(
            'SELECT Type,Red,Green,Blue,Alpha FROM Colors ORDER BY rowid')]
        players=[dict(zip(('rowid','ID','Type','PrimaryColor','SecondaryColor'),row)) for row in database.execute(
            'SELECT rowid,ID,Type,PrimaryColor,SecondaryColor FROM PlayerColors ORDER BY rowid')]
        colors_order=[row[0] for row in database.execute('SELECT Type FROM Colors ORDER BY ID')]
        schema={name:sql for name,sql in database.execute("SELECT name,sql FROM sqlite_master WHERE name IN ('Colors','PlayerColors')")}
    require(len(colors)==221 and len(players)==106,'Exact current original graph color catalogs differ')
    require(colors_order==[row['Type'] for row in colors] and all(row['rowid']==row['ID'] for row in players),
            'Current INTEGER PRIMARY KEY order is not the original rowid order')
    require(all(type(row[key]) in (int,float) for row in colors for key in ('Red','Green','Blue','Alpha')),
            'Original color channels are not numeric double values')
    return colors,players,schema


def original_block():
    require(artifact(VIEWER)['sha256']==artifact(FROZEN_VIEWER)['sha256'],
            'Installed and frozen original ReplayViewer.lua differ')
    text=VIEWER.read_text('utf-8-sig')
    start='local colorDistances = {};'
    end='panel.PlayerGraphColors = {};'
    require(text.count(start)==1,'Original graph color distance block is ambiguous')
    a=text.index(start);b=text.index(end,a);body=text[a:b]
    for exact in ('local blackThreshold = 5000;','local differenceThreshold = 3000;',
        'distanceAgainstBlack > blackThreshold','distanceAgainstOtherPlayer < differenceThreshold',
        'return GameInfo.Colors[playerColor.PrimaryColor];','for color in GameInfo.Colors() do'):
        require(exact in body,'Original graph color algorithm shape differs')
    return body,dict(source=artifact(VIEWER),first_line=text.count('\n',0,a)+1,
        last_line=text.count('\n',0,b)+1,extracted_bytes=len(body.encode('utf8')),
        extracted_sha256=hashlib.sha256(body.encode('utf8')).hexdigest(),
        extraction='VERBATIM_COLOR_DISTANCE_UNIQUENESS_AND_DETERMINE_GRAPH_COLOR_ONLY',
        entire_replay_viewer_or_ui_executed=False)


def color(name,r,g,b,a=1):
    return dict(Type=name,Red=r,Green=g,Blue=b,Alpha=a)


def cases_for(colors,players):
    catalogs={'actual':colors};cases=[]
    def add(name,roster,key='actual',probes=()):
        cases.append(dict(name=name,catalog=key,roster=[dict(PrimaryColor=p,SecondaryColor=s) for p,s in roster],probes=list(probes)))
    actual_by_id={row['ID']:row for row in players}
    add('actual_recorded_0_7',[(actual_by_id[i]['PrimaryColor'],actual_by_id[i]['SecondaryColor']) for i in (0,7)])
    for row in players:
        add('actual_player_color_'+str(row['ID']),[(row['PrimaryColor'],row['SecondaryColor'])])
    for at in range(0,len(players),64):
        add('actual_player_catalog_chunk_'+str(at),[(row['PrimaryColor'],row['SecondaryColor']) for row in players[at:at+64]])
    for row in colors:
        add('actual_color_primary_'+row['Type'],[(row['Type'],row['Type'])])
    for identifier in (0,7):
        row=actual_by_id[identifier]
        add('actual_repeated_64_player_color_'+str(identifier),[(row['PrimaryColor'],row['SecondaryColor'])]*64)
    add('actual_64_ordered_roster',[(players[(i*17)%len(players)]['PrimaryColor'],players[(i*17)%len(players)]['SecondaryColor']) for i in range(64)])
    add('actual_empty_roster',[])

    # Synthetic inputs exercise source comparison boundaries, never replace
    # original game colors or generate production palette entries.
    pairings=[]
    for name,base,threshold_kind in [('black',math.sqrt(5000)/255,'black'),
                                     ('difference',1-math.sqrt(3000)/255,'difference')]:
        values=[base]
        low=high=base
        for _ in range(5):
            low=math.nextafter(low,0.0);high=math.nextafter(high,1.0)
            values.extend((low,high))
        for index,value in enumerate(values):
            key=name+'_near_'+str(index)
            if threshold_kind=='black':
                entries=[color('COLOR_EDGE',value,0,0),color('COLOR_SAFE',1,1,1)]
                roster=[('COLOR_EDGE','COLOR_SAFE')];probes=[dict(left='COLOR_EDGE',right='#BLACK')]
            else:
                entries=[color('COLOR_FIRST',1,1,1),color('COLOR_EDGE',value,1,1),color('COLOR_SAFE',0,1,0)]
                roster=[('COLOR_FIRST','COLOR_SAFE'),('COLOR_EDGE','COLOR_SAFE')]
                probes=[dict(left='COLOR_EDGE',right='COLOR_FIRST')]
            catalogs[key]=entries;add(key,roster,key,probes)
            quantized=key+'_float32'
            catalogs[quantized]=[dict(row,**{field:struct.unpack('<f',struct.pack('<f',row[field]))[0]
                for field in ('Red','Green','Blue','Alpha')}) for row in entries]
            add(quantized,roster,quantized,probes);pairings.append((key,quantized))
    catalogs['black_exact']= [color('COLOR_EDGE',50/255,50/255,0),color('COLOR_SAFE',1,1,1)]
    add('black_distance_exact_5000',[('COLOR_EDGE','COLOR_SAFE')],'black_exact',[dict(left='COLOR_EDGE',right='#BLACK')])
    catalogs['type_cache']=[color('COLOR_BLACK',1,1,1),color('COLOR_SAFE',1,0,0)]
    add('virtual_black_type_self_distance',[('COLOR_BLACK','COLOR_SAFE')],'type_cache',
        [dict(left='COLOR_BLACK',right='#BLACK')])
    catalogs['exhausted']=[color('PRIMARY',0,0,0),color('SECONDARY',0,0,0)]
    add('exhausted_returns_original_primary',[('PRIMARY','SECONDARY')]*64,'exhausted')
    catalogs['alpha']=[color('ZERO_ALPHA_BRIGHT',1,0,0,0),color('SAME_RGB_OTHER_TYPE',1,0,0,1),color('BLUE',0,0,1)]
    add('alpha_ignored_distance_preserved_output',[('ZERO_ALPHA_BRIGHT','BLUE'),('SAME_RGB_OTHER_TYPE','BLUE')],'alpha')
    catalogs['ordered']=[color('FIRST_CATALOG_FALLBACK',1,0,0),color('SECOND_CATALOG_FALLBACK',0,1,0),color('PRIMARY',0,0,0),color('SECONDARY',0,0,0)]
    add('fallback_uses_catalog_order',[('PRIMARY','SECONDARY')]*3,'ordered')
    catalogs['ordered_reverse']=[catalogs['ordered'][1],catalogs['ordered'][0],*catalogs['ordered'][2:]]
    add('fallback_follows_reversed_catalog_order',[('PRIMARY','SECONDARY')]*3,'ordered_reverse')
    return catalogs,cases,pairings


JSON_LUA=r'''
local function json(value)
 local kind=type(value)
 if kind=='number' then return string.format('%.17g',value) end
 if kind=='boolean' then return tostring(value) end
 if kind=='string' then return '"'..value:gsub('[%z\1-\31\\"]',function(ch)
  if ch=='"' then return '\\"' elseif ch=='\\' then return '\\\\' end
  return string.format('\\u%04x',string.byte(ch)) end)..'"' end
 assert(kind=='table')
 local parts={}
 if #value>0 or next(value)==nil then for _,item in ipairs(value) do parts[#parts+1]=json(item) end;return '['..table.concat(parts,',')..']' end
 local keys={};for key in pairs(value) do keys[#keys+1]=key end;table.sort(keys)
 for _,key in ipairs(keys) do parts[#parts+1]=json(key)..':'..json(value[key]) end
 return '{'..table.concat(parts,',')..'}'
end
'''


def goldens(body,catalogs,cases):
    script=JSON_LUA+'\nlocal catalogs='+lua_value(catalogs)+'\nlocal cases='+lua_value(cases)+r'''
local function oracle(catalog,roster,probes)
 local lookup={};for _,entry in ipairs(catalog) do lookup[entry.Type]=entry end
 local GameInfo={Colors=setmetatable(lookup,{__call=function()
  local at=0;return function() at=at+1;return catalog[at] end end})}
 local panel={PlayerGraphColors={}}
'''+body+r'''
 local selected={}
 for index,playerColor in ipairs(roster) do
  local chosen=DetermineGraphColor(playerColor);panel.PlayerGraphColors[index]=chosen
  selected[#selected+1]={type=chosen.Type,r=chosen.Red,g=chosen.Green,b=chosen.Blue,a=chosen.Alpha}
 end
 local distances={}
 for _,probe in ipairs(probes) do distances[#distances+1]=ColorDistance(lookup[probe.left],probe.right=='#BLACK' and colorBlack or lookup[probe.right]) end
 return {selected=selected,distances=distances}
end
local results={}
for _,case in ipairs(cases) do results[#results+1]=oracle(catalogs[case.catalog],case.roster,case.probes) end
return json(results)
'''
    return execute_lua(script)


def fixture_bytes(path,catalogs,cases,expected):
    data=bytearray(b'ZSGRC001'+struct.pack('<I',len(cases)))
    def text(value):
        raw=value.encode('utf8');data.extend(struct.pack('<I',len(raw)));data.extend(raw)
    def rgba(entry,fields):
        text(entry[fields[0]]);data.extend(struct.pack('<4d',*(entry[field] for field in fields[1:])))
    for case,golden in zip(cases,expected):
        text(case['name']);entries=catalogs[case['catalog']];data.extend(struct.pack('<I',len(entries)))
        for entry in entries:rgba(entry,('Type','Red','Green','Blue','Alpha'))
        data.extend(struct.pack('<I',len(case['roster'])))
        for player in case['roster']:text(player['PrimaryColor']);text(player['SecondaryColor'])
        data.extend(struct.pack('<I',len(golden['selected'])))
        for entry in golden['selected']:rgba(entry,('type','r','g','b','a'))
    path.write_bytes(data)


def main():
    EVIDENCE.mkdir(parents=True,exist_ok=True);BUILD.mkdir(exist_ok=True)
    result_path=EVIDENCE/'fixture_result.json'
    require(not result_path.exists(),'A completed graph color receipt already exists; do not repeat it')
    protected=[HEADER,CPP,Path(__file__),VIEWER,FROZEN_VIEWER,RUNTIME/'rules.db',LUA_PROVIDER]
    before=[artifact(path) for path in protected]
    require(artifact(LUA_PROVIDER)['sha256']=='4873cded3ddf52366abc7964e3d3e10546f88e983d966be93bce3465ef85d944',
            'Shared pure Lua5.1 provider differs from the reviewed immutable input')
    original,source=original_block();colors,players,schema=catalog();catalogs,cases,pairings=cases_for(colors,players)
    expected=goldens(original,catalogs,cases)
    require(len(expected)==len(cases),'Original Lua golden result count differs')
    by_name={case['name']:golden for case,golden in zip(cases,expected)}
    require([row['type'] for row in by_name['actual_recorded_0_7']['selected']]==['COLOR_PLAYER_WHITE','COLOR_PLAYER_DARK_PINK'],
            'Actual recorded roster no longer selects original graph colors')
    require(by_name['black_distance_exact_5000']['distances']==[5000] and
            by_name['black_distance_exact_5000']['selected'][0]['type']=='COLOR_SAFE','Original strict black boundary differs')
    require(by_name['virtual_black_type_self_distance']['distances']==[0] and
            by_name['virtual_black_type_self_distance']['selected'][0]['type']=='COLOR_SAFE','Original Type-keyed self-distance differs')
    require(all(row['type']=='PRIMARY' for row in by_name['exhausted_returns_original_primary']['selected']),
            'Original exhausted-catalog fallback differs')
    require(by_name['fallback_uses_catalog_order']['selected'][0]['type']=='FIRST_CATALOG_FALLBACK' and
            by_name['fallback_follows_reversed_catalog_order']['selected'][0]['type']=='SECOND_CATALOG_FALLBACK',
            'Original catalog fallback order was not exercised')
    float_sensitive=[dict(double_case=a,float32_case=b,double_selected=[x['type'] for x in by_name[a]['selected']],
        float32_selected=[x['type'] for x in by_name[b]['selected']],double_distances=by_name[a]['distances'],
        float32_distances=by_name[b]['distances']) for a,b in pairings
        if [x['type'] for x in by_name[a]['selected']] != [x['type'] for x in by_name[b]['selected']]]
    require(float_sensitive,'Near-threshold fixture did not detect premature float conversion')
    input_path=BUILD/'goldens.bin';fixture_bytes(input_path,catalogs,cases,expected);input_pin=artifact(input_path)
    built=build_cxx14('MenuReplayGraphColorsComponent',BUILD,EVIDENCE,CPP,[PROJECT/'Source/Host'])
    imports=PE(Path(built['path']).read_bytes()).imports()
    require({name.casefold() for name in imports}=={'kernel32.dll'},'Graph color component imports beyond Kernel32')
    result=run([built['path'],input_path],cwd=BUILD,timeout=60)
    require(result.returncode==0,'Graph color component failed: '+(result.stdout+result.stderr).decode('utf8',errors='replace'))
    component=json.loads(result.stdout.decode('utf8'))
    require(component['cases']==len(cases),'Actual C++14 golden case count differs')
    after=[artifact(path) for path in protected]
    require(before==after,'Original/provider/selector source changed during graph color fixture')
    write(EVIDENCE/'goldens.json',dict(schema='zerosis.replay_graph_colors.original_lua_goldens.v1',
        source=source,catalogs=catalogs,cases=[dict(case,expected=golden) for case,golden in zip(cases,expected)],
        premature_float_conversion_regressions=float_sensitive,synthetic_colors_are_test_inputs_only=True,
        actual_catalog_count=len(colors),actual_player_color_count=len(players),original_sqlite_schema=schema))
    cleanup=[]
    # Only exact files generated by this component run are disposable. Keep the
    # current executable/map/environment receipt and small compiler log.
    for path in (input_path,BUILD/'MenuReplayGraphColorsComponent.obj',BUILD/'compile.rsp',BUILD/'vcvarsall_env_x64.bat'):
        if not path.exists():continue
        require(path.absolute().parent==BUILD.absolute() and not path.is_symlink(),'Graph color cleanup escaped its owned component')
        row=artifact(path);path.unlink();cleanup.append(dict(**row,result='DELETED_OWNED_REGENERABLE_GRAPH_COLOR_INTERMEDIATE'))
    report=dict(schema='zerosis.replay_graph_colors.component.v1',status='PASS_EXACT_ORIGINAL_LUA_GRAPH_COLOR_SELECTION_CXX14',
        original_algorithm=source,actual_colors=len(colors),actual_player_colors=len(players),ordered_database_policy='ORDER_BY_ROWID_INTEGER_PRIMARY_KEY_EQUALS_ID',
        goldens=artifact(EVIDENCE/'goldens.json'),golden_input_retired=input_pin,component=component,build=built,imports=imports,
        near_threshold_float_conversion_regressions=len(float_sensitive),actual_recorded_roster_0_7=by_name['actual_recorded_0_7'],
        cleanup=cleanup,inputs_before=before,protected_inputs_unchanged=True,native_host_or_sdk_or_window_executed=False,
        pure_lua51_provider_executed=True,pure_cpp14_console_executed=True,clr_or_gpu_executed=False,
        user_original_settings_saves_or_mods_written=False,retail_pixel_acceptance=False)
    write(result_path,report)
    print(json.dumps(dict(status=report['status'],cases=component['cases'],selected=component['matched_selected_colors'],
        invalid_and_bounds=component['invalid_and_bounds_checks'],float_sensitive=len(float_sensitive),imports=imports,
        cleaned_files=len(cleanup),native_host_or_sdk_or_window_executed=False)))


if __name__=='__main__':main()
