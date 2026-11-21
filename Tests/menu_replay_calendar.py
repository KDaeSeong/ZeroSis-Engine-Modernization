"""Read-only stock-calendar oracles and a bounded SDK-free C++14 component."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys

sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[1]
sys.path.insert(0,str(PROJECT/'tools'));sys.path.insert(0,str(PROJECT/'Tests'))
from menu_replay_restoration import build_cxx14
from menu_replay_assets import artifact
from menu_suite_storage import storage
from native_build import run
from economic_overview_scene import execute_lua
from prepare_ui_popup_assets import lua_value

BUILD=PROJECT/'Build/MenuReplayCalendar/current'
EVIDENCE=PROJECT/'evidence/game_menu/replay_calendar_legend/calendar'
RUNTIME=PROJECT/'Build/InteractiveGameRuntime/20261103T140325Z_f127e4edebe9'
LUA=PROJECT/'Source/Assets/Scripts/Assets/Gameplay/Lua/GameCalendarUtilities.lua'
VIEWER=PROJECT/'Source/Assets/UI/Assets/UI/InGame/Popups/ReplayViewer.lua'
SDK=PROJECT/'Source/SDK_BNW_Original'
UTILS=SDK/'CvGameCoreDLL_Expansion2/CvGameCoreUtils.cpp'
TEXT=SDK/'CvGameCoreDLL_Expansion2/CvGameTextMgr.cpp'
ENUMS=SDK/'CvGameCoreDLLUtil/include/CvEnums.h'
GAME=Path(r"C:/Program Files (x86)/Steam/steamapps/common/Sid Meier's Civilization V")
ORIGINAL_LUA=GAME/'Assets/Gameplay/Lua/GameCalendarUtilities.lua'
ORIGINAL_SEASONS=GAME/'Assets/Gameplay/XML/BasicInfos/CIV5Seasons.xml'
CPP=PROJECT/'Tests/menu_replay_calendar.cpp'
HEADER=PROJECT/'Source/Host/MenuReplayCalendar.h'
RETAIL_PROBE=PROJECT/'evidence/game_menu/replay_season_wheel/retail_static_probe.json'
LOCALIZATION_TRACE=PROJECT/'evidence/localization/reference/basic.log'
FUNCTIONS=('getTurnYearForGame','getTurnMonthForGame','CvGameTextMgr::setYearStr','CvGameTextMgr::setDateStr')


def block(text,signature):
    """Extract this small original C++ block verbatim; reject nested unmatched text."""
    start=text.index(signature);opening=text.index('{',start);depth=0
    # These exact functions contain no braces in strings or comments.
    for end in range(opening,len(text)):
        if text[end]=='{':depth+=1
        elif text[end]=='}':
            depth-=1
            if depth==0:return text[start:end+1]
    raise ValueError('Unterminated stock source block '+signature)


def extract_sdk():
    utils=UTILS.read_text('cp1252');text=TEXT.read_text('cp1252');enums=ENUMS.read_text('cp1252')
    extracted=[block(enums,'enum CalendarTypes')+';']
    extracted += [block(utils,'int '+name+'(') for name in FUNCTIONS[:2]]
    extracted += [block(text,'void '+name+'(') for name in FUNCTIONS[2:]]
    declaration='''
int getTurnMonthForGame(int,int,CalendarTypes,GameSpeedTypes);
class CvGameTextMgr final { public:
 void setYearStr(CvString&,int,bool,CalendarTypes,int,GameSpeedTypes);
 void setDateStr(CvString&,int,bool,CalendarTypes,int,GameSpeedTypes);
};
'''
    # Declaration follows the verbatim enum and precedes all original bodies.
    body=extracted[0]+'\n'+declaration+'\n'+'\n\n'.join(extracted[1:])+'\n'
    (BUILD/'sdk_calendar_oracle.inc').write_text(body,encoding='cp1252',newline='\n')
    return dict(exact_original_blocks=[dict(name=name,sha256=hashlib.sha256(value.encode('cp1252')).hexdigest())
        for name,value in zip(('CalendarTypes',)+FUNCTIONS,extracted)],
        database_and_localization_are_fixture_stubs=True,original_sdk_dll_executed=False)


def read_actual_catalog():
    con=sqlite3.connect((RUNTIME/'rules.db').as_uri()+'?mode=ro&immutable=1',uri=True)
    try:
        calendars=list(con.execute('SELECT ID,Type FROM Calendars ORDER BY ID'))
        speeds=list(con.execute('SELECT ID,Type FROM GameSpeeds ORDER BY ID'))
        months=list(con.execute('SELECT ID,Description FROM Months ORDER BY ID'))
        seasons=list(con.execute('SELECT ID,Description FROM Seasons ORDER BY ID'))
        turns={kind:list(con.execute('SELECT MonthIncrement,TurnsPerIncrement FROM GameSpeed_Turns WHERE GameSpeedType=? ORDER BY rowid ASC',(kind,))) for _,kind in speeds}
        defines={name:con.execute('SELECT Value FROM Defines WHERE Name=?',(name,)).fetchone()[0]
                 for name in ('WEEKS_PER_MONTHS','HIDDEN_START_TURN_OFFSET')}
    finally:con.close()
    assert [row[0] for row in calendars]==list(range(7))
    assert [row[0] for row in speeds]==list(range(4))
    for rows in (months,seasons):assert [row[0] for row in rows]==list(range(len(rows)))
    assert [kind for _,kind in calendars]==['CALENDAR_DEFAULT','CALENDAR_BI_YEARLY','CALENDAR_YEARS',
        'CALENDAR_TURNS','CALENDAR_SEASONS','CALENDAR_MONTHS','CALENDAR_WEEKS']
    assert len(months)==12 and len(seasons)==4 and defines=={'WEEKS_PER_MONTHS':4,'HIDDEN_START_TURN_OFFSET':0}
    assert all(isinstance(value,int) for rows in turns.values() for row in rows for value in row)
    return dict(calendars=calendars,speeds=speeds,months=months,seasons=seasons,turns=turns,defines=defines)


def actual_localization(data):
    keys=['TXT_KEY_TIME_AD','TXT_KEY_TIME_BC','TXT_KEY_TIME_TURN','TXT_KEY_TIME_WEEK','TXT_KEY_TP_TURN_COUNTER']
    keys += [key for _,key in data['months']+data['seasons']]
    con=sqlite3.connect((RUNTIME/'localization.db').as_uri()+'?mode=ro&immutable=1',uri=True)
    try:
        values={};availability={}
        for key in keys:
            row=con.execute('SELECT Text FROM Language_KO_KR WHERE Tag=?',(key,)).fetchone()
            values[key]=row[0] if row else None
            availability[key]=dict(korean=values[key],all_localized_text_rows=con.execute('SELECT COUNT(*) FROM LocalizedText WHERE Tag=?',(key,)).fetchone()[0])
    finally:con.close()
    for key in keys[:5]+[key for _,key in data['months']]:assert values[key]
    for _,key in data['seasons']:assert values[key] is None and availability[key]['all_localized_text_rows']==0
    scan=run(['rg','-n','-g','*.xml','-g','*.sql','-g','*.lua','-g','*.csv','-g','*.txt',
        'TXT_KEY_SEASON_(WINTER|SPRING|SUMMER|FALL)',str(GAME/'Assets')],cwd=PROJECT,timeout=60)
    if scan.returncode not in (0,1):raise RuntimeError('Original season text scan failed')
    matches=scan.stdout.decode('utf8').splitlines()
    assert len(matches)==4 and all('CIV5Seasons.xml:' in line and '<Description>' in line for line in matches)
    assert artifact(LUA)['sha256']==artifact(ORIGINAL_LUA)['sha256']
    overrides=[]
    for root in (PROJECT/'Source/Assets',GAME/'Assets'):
        overrides.extend(str(path) for path in root.rglob('GameCalendarUtilities_Overrides_*.lua'))
    if overrides:raise ValueError('Calendar overrides require a separately validated formatter: '+repr(overrides))
    probe=json.loads(RETAIL_PROBE.read_text('utf8'))
    assert probe['exe']['sha256']=='b7c8977ebab33ba6c1abf65d63fa310f8d096341465e0fc419f1b4da0fcd8818' and probe['executed'] is False
    assert probe['locale']['functions']['Lookup']['function']=='005cc8d0'
    assert 'No HasKey/TryLookup and no substitute text.' in probe['locale']['functions']['Lookup']['finding']
    traced=[line for line in LOCALIZATION_TRACE.read_text('utf8').splitlines() if line.startswith('TEXT|missing|')]
    assert len(traced)==1 and bytes.fromhex(traced[0].rsplit('|',1)[1])==b'TXT_MISSING'
    return values,dict(actual_key_availability=availability,original_text_scan_matches=matches,
        original_text_scan_scope='Installed Assets recursively: XML, SQL, Lua, CSV, TXT only; no packed/binary archive claims.',
        source_snapshot_matches_installed_helper=True,stock_calendar_overrides=overrides,
        actual_korean_seasons_supported=False,
        missing_key_lookup=dict(retail_probe=artifact(RETAIL_PROBE),localization_trace=artifact(LOCALIZATION_TRACE),trace_line=traced[0],
            result='Retail Locale.Lookup calls Localization::Lookup without a presence test; the original component returns the missing key itself.'),
        missing_seasons_behavior='CALENDAR_SEASONS shows the raw Description key (for example TXT_KEY_SEASON_WINTER) before the localized year, '
                                 'exactly as stock ReplayViewer Locale.Lookup does. No replacement translation is generated.',
        formatter_limit='Korean samples statically evaluate the actual single-integer templates; ICU/SDK localization runtime is not executed.')


def actual_cases(data):
    result=[];sdk=[]
    years=(-2147483648,-4000,-2,-1,0,1,2024,2147483647)
    for speed,kind in data['speeds']:
        points={0,1,2,3,4,5,6,7,8,11,12,23,24,47,48,49,99,100,123,125,250,375,500,10000000}
        cumulative=0
        for _,turns in data['turns'][kind]:
            cumulative+=turns;points.update((cumulative-1,cumulative,cumulative+1))
        for year in years:
            for turn in sorted(points):
                for calendar,_ in data['calendars'][:-1]:result.append((calendar,speed,year,turn))
                if abs(year)<100000000:sdk.append((speed,year,turn))
    return result,sdk


def original_lua(data,cases):
    source=LUA.read_text('utf-8-sig');viewer=VIEWER.read_text('utf-8-sig')
    pad=re.search(r'PadHorizontalValues\s*=\s*(function\(minTurn, maxTurn\).*?\n\s*end),',viewer,re.S).group(1)
    horizontal=re.search(r'(function RefreshHorizontalScales\(\).*?)\n\s*function RefreshCivilizations',viewer,re.S).group(1).rstrip()
    assert horizontal.endswith('end') and '#g_GraphHorizontalMarkers - 1' in horizontal
    graph_cases=[(initial,initial+span) for initial in (0,1,3,50,9999990) for span in range(10)]
    graph_cases += [(0,1000000),(9000000,10000000),(51,58),(0,500),(9999999,10000000)]
    script=r'''
local input=@@INPUT@@
local cases=@@CASES@@
local graphCases=@@GRAPHS@@
local function token(key,number)
 if number==nil then return '{'..key..'}' end
 return '{'..key..':'..string.format('%.0f',number)..'}'
end
local function indexed(rows)
 local proxy=newproxy(true);local mt=getmetatable(proxy)
 mt.__len=function() return #rows end
 mt.__index=function(_,index) return rows[index+1] and {Description=rows[index+1][2]} end
 return proxy
end
local environment={math={floor=math.floor},include=function(name,wildcard)
 assert(name=='GameCalendarUtilities_Overrides_%w+.lua' and wildcard==true)
end,Locale={Lookup=token},GameDefines=input.defines,
 GameInfo={Months=indexed(input.months),Seasons=indexed(input.seasons)},DB={}}
environment.DB.Query=function(sql,kind)
 assert(sql=='SELECT MonthIncrement, TurnsPerIncrement FROM GameSpeed_Turns WHERE GameSpeedType = ? ORDER BY rowid ASC')
 local rows=assert(input.turns[kind]);local cursor=0
 return function() cursor=cursor+1;local row=rows[cursor]
  if row then return {MonthIncrement=row[1],TurnsPerIncrement=row[2]} end
 end
end
local function run(source,env,name)
 local fn=assert(loadstring(source,'@'..name));setfenv(fn,env);return fn()
end
run(@@SOURCE@@,environment,'original-GameCalendarUtilities.lua')
local outputs={}
for _,case in ipairs(cases) do
 local calendar,speed,year,turn=case[1],case[2],case[3],case[4]
 outputs[#outputs+1]=environment.GetShortDateString(turn,input.calendars[calendar+1][2],input.speeds[speed+1][2],year)
end
local weeksWorks,weeksError=pcall(environment.GetShortDateString,1,'CALENDAR_WEEKS',input.speeds[1][2],-4000)
assert(not weeksWorks and weeksError:find('GC'))
local graphOutputs={}
for _,case in ipairs(graphCases) do
 local marks={};for i=1,5 do marks[i]={SetText=function(self,text) self.value=text end} end
 local env={math={floor=math.floor},ipairs=ipairs,g_GraphHorizontalMarkers=marks,
  initialTurn=case[1],finalTurn=case[2],startYear=-4000,calendarType='CALENDAR_DEFAULT',gameSpeedType='GAMESPEED_STANDARD',
  GetShortDateString=function(turn) return turn end}
 local padFunction=run('return '..@@PAD@@,env,'original-PadHorizontalValues.lua')
 env.panel={PadHorizontalValues=padFunction};run(@@HORIZONTAL@@,env,'original-RefreshHorizontalScales.lua')
 env.RefreshHorizontalScales()
 local minimum,maximum=padFunction(case[1],case[2]);local values={}
 for i=1,5 do values[i]=marks[i].value=='' and -1 or marks[i].value end
 graphOutputs[#graphOutputs+1]={case[1],case[2],minimum,maximum,values}
end
local function quote(value)
 return '"'..value:gsub('[%z\1-\31\\"]',function(ch) return string.format('\\u%04x',string.byte(ch)) end)..'"'
end
local function json(value)
 if type(value)=='string' then return quote(value) end
 if type(value)=='number' then return string.format('%.17g',value) end
 local parts={};for _,item in ipairs(value) do parts[#parts+1]=json(item) end
 return '['..table.concat(parts,',')..']'
end
return '{"outputs":'..json(outputs)..',"graphs":'..json(graphOutputs)..',"stock_weeks_error":'..quote(weeksError)..'}'
'''
    replacements={'@@INPUT@@':lua_value(json.loads(json.dumps(data))),'@@CASES@@':lua_value([list(x) for x in cases]),
        '@@GRAPHS@@':lua_value([list(x) for x in graph_cases]),'@@SOURCE@@':lua_value(source),
        '@@PAD@@':lua_value(pad),'@@HORIZONTAL@@':lua_value(horizontal)}
    for key,value in replacements.items():script=script.replace(key,value)
    result=execute_lua(script)
    assert len(result['outputs'])==len(cases) and len(result['graphs'])==len(graph_cases)
    return result,dict(stock_helper=LUA.name,stock_weeks_error=result['stock_weeks_error'],
        sandbox='Original helper is setfenv-bound to fixture GameInfo/DB/Locale/math.floor/include only; no game services.',
        calendar_types=6,speeds=4,golden_cases=len(cases),graph_domains=len(graph_cases),
        original_pad_sha256=hashlib.sha256(pad.encode()).hexdigest(),
        original_horizontal_scales_sha256=hashlib.sha256(horizontal.encode()).hexdigest(),
        source_overrides_present=False,localized_strings_are_argument_tokens=True)


def cpp_string(value):return json.dumps(value,ensure_ascii=True)
def cpp_int(value):return '(-2147483647-1)' if value==-2147483648 else str(value)


def integer_template(text):
    pieces=re.split(r'\{1_[A-Za-z0-9_]+(?:: number #)?\}',text)
    if len(pieces)!=2:raise ValueError('Actual numeric template requires a new verified adapter: '+text)
    return pieces


def actual_samples(data,cases,lua,labels):
    goldens=dict(zip(cases,lua['outputs']))
    def format_token(match):
        key,number=match.groups();value=labels[key]
        # Original Locale.Lookup returns a missing key itself (season names).
        if value is None and number is None:return key
        if value is None:raise LookupError(key)
        if number is None:return value
        prefix,suffix=integer_template(value);return prefix+number+suffix
    selected=[(identifier,2,-4000,4) for identifier,_ in data['calendars'][:-1]]
    selected += [(0,speed,-4000,turn) for speed,_ in data['speeds'] for turn in (0,1,4,125,250,375,500)]
    result=[]
    for case in sorted(set(selected)):
        try:text=re.sub(r'\{([A-Z0-9_]+)(?::([0-9]+))?\}',format_token,goldens[case]);supported=True
        except LookupError:text='';supported=False
        result.append(dict(calendar=case[0],speed=case[1],start_year=case[2],turn=case[3],expected=text,available=supported))
    week_prefix,week_suffix=integer_template(labels['TXT_KEY_TIME_WEEK'])
    bc_prefix,bc_suffix=integer_template(labels['TXT_KEY_TIME_BC'])
    weeks=week_prefix+'1'+week_suffix+', '+labels['TXT_KEY_MONTH2']+', '+bc_prefix+'3999'+bc_suffix
    return result,weeks


def write_goldens(data,cases,sdk,lua,labels,samples,weeks_sample):
    lines=['static MenuReplayCalendarCatalog ActualCatalog(){MenuReplayCalendarCatalog c;']
    for identifier,name in data['calendars']:lines.append(f'c.calendars[{identifier}]={cpp_string(name)};')
    for identifier,name in data['speeds']:lines.append(f'c.gameSpeeds[{identifier}]={cpp_string(name)};')
    for name,rows in data['turns'].items():
        lines.append('c.speedTurns['+cpp_string(name)+']={'+','.join('{'+str(a)+','+str(b)+'}' for a,b in rows)+'};')
    for key,rows in (('monthNames',data['months']),('seasonNames',data['seasons'])):
        lines.append('c.'+key+'={'+','.join('L'+cpp_string('{'+name+'}') for _,name in rows)+'};')
    lines.append(f'c.weeksPerMonth={data["defines"]["WEEKS_PER_MONTHS"]};c.hiddenStartTurnOffset={data["defines"]["HIDDEN_START_TURN_OFFSET"]};')
    lines.append('c.localizeNumber=[](const char* key,std::int64_t n){return Wide(Token(key,n));};return c;}')
    lines.append('static void ConfigureSdk(const MenuReplayCalendarCatalog& c){')
    for key,rows in (('months',data['months']),('seasons',data['seasons'])):
        lines.append('StockSdkOracle::DB.'+key+'={'+','.join(cpp_string(name) for _,name in rows)+'};')
    lines.append('for(const auto& speed:c.gameSpeeds){StockSdkOracle::CvGameSpeedInfo info;')
    lines.append('for(const auto& row:c.speedTurns.at(speed.second))info.increments.push_back({static_cast<int>(row.monthIncrement),static_cast<int>(row.turns)});')
    lines.append('StockSdkOracle::GC.speeds[speed.first]=std::move(info);}}')
    lines.append('static const LuaCase LuaGoldens[]={')
    for case,expected in zip(cases,lua['outputs']):lines.append('{'+','.join(map(cpp_int,case))+','+cpp_string(expected)+'},')
    lines.append('};\nstatic const SdkCase SdkGoldens[]={')
    for case in sdk:lines.append('{'+','.join(map(str,case))+'},')
    lines.append('};\nstatic const GraphCase GraphGoldens[]={')
    for initial,final,minimum,maximum,graph_labels in lua['graphs']:
        lines.append('{'+','.join(map(str,(initial,final,minimum,maximum)))+',{{'+','.join(map(str,graph_labels))+'}}},')
    lines.append('};\n')
    lines.append('static MenuReplayCalendarCatalog ActualLocaleCatalog(){auto c=ActualCatalog();')
    for key,rows in (('monthNames',data['months']),('seasonNames',data['seasons'])):
        lines.append('c.'+key+'={'+','.join('L'+cpp_string(labels[name] or name) for _,name in rows)+'};')
    lines.append('c.localizeNumber=[](const char* key,std::int64_t number)->std::wstring{')
    for key in ('TXT_KEY_TIME_AD','TXT_KEY_TIME_BC','TXT_KEY_TIME_TURN','TXT_KEY_TIME_WEEK'):
        prefix,suffix=integer_template(labels[key])
        lines.append('if(std::string(key)=='+cpp_string(key)+')return L'+cpp_string(prefix)+'+std::to_wstring(number)+L'+cpp_string(suffix)+';')
    lines.append('return {};};return c;}\nstatic const LocaleCase ActualLocaleSamples[]={')
    for sample in samples:
        case=[sample[key] for key in ('calendar','speed','start_year','turn')]
        lines.append('{'+','.join(map(cpp_int,case))+',L'+cpp_string(sample['expected'])+'},')
    lines.append('};\nstatic std::wstring ActualWeeksSample(){return L'+cpp_string(weeks_sample)+';}\n')
    (BUILD/'calendar_actual_goldens.inc').write_text('\n'.join(lines),encoding='ascii',newline='\n')


def main():
    EVIDENCE.mkdir(parents=True,exist_ok=True);BUILD.mkdir(parents=True,exist_ok=True)
    inputs=[HEADER,CPP,Path(__file__),LUA,ORIGINAL_LUA,ORIGINAL_SEASONS,VIEWER,UTILS,TEXT,ENUMS,
        SDK/'CvGameCoreDLL_Expansion2/CvInfos.cpp',
        PROJECT/'Source/Assets/UI/Assets/DLC/Expansion2/UI/InGame/Popups/ReplayViewer.xml',
        RUNTIME/'rules.db',RUNTIME/'localization.db',
        PROJECT/'Build/SharedLuaRuntime/Lua/ZeroSisLua51_x64.dll',
        PROJECT/'Tests/menu_replay_restoration.py',PROJECT/'Tests/economic_overview_scene.py',
        PROJECT/'tools/native_build.py',PROJECT/'tools/prepare_ui_popup_assets.py',RETAIL_PROBE,LOCALIZATION_TRACE]
    before=[artifact(path) for path in inputs]
    if any(any(value>127 for value in path.read_bytes()) for path in (HEADER,CPP)):
        raise ValueError('C++14/windows-1252 production and fixture sources must remain ASCII')
    signature=hashlib.sha256(json.dumps(before,sort_keys=True).encode()).hexdigest()[:16]
    receipt=EVIDENCE/'result.json'
    if receipt.exists():
        previous=json.loads(receipt.read_text('utf8'))
        retained=Path(previous.get('build',{}).get('path','NO_RETAINED_FIXTURE'))
        retained_matches=retained.is_file() and artifact(retained)['sha256']==previous.get('build',{}).get('sha256')
        if previous.get('input_signature')==signature and previous.get('status')=='PASS_SDK_FREE_CALENDAR' and retained_matches:
            print(json.dumps(dict(status=previous['status'],reused_existing_identical_inputs=True,report=str(receipt))));return 0
    report=dict(schema='zerosis.menu_replay.calendar.v1',input_signature=signature,inputs_before=before,
        source_encoding='ASCII / windows-1252',cpp_dialect='c++14',
        native_host_sdk_window_gpu_executed=False,retail_pixel_acceptance=False,
        acceptance='Controlled pure Lua 5.1 and SDK-free C++14 component only.',
        stock_weeks_repair=dict(reason='Stock short WEEKS references missing GC and weekString, and uses a fractional month row.',
            behavior='Only WEEKS uses exact CvGameTextMgr::setDateStr/getTurnMonthForGame source, including hidden start offset and signed BC truncation.',
            unchanged='Other six calendar formats preserve stock ReplayViewer Lua results, including floor(turn/2) BI_YEARLY. Recorded metadata and saves unchanged.'))
    intermediates=['sdk_calendar_oracle.inc','calendar_actual_goldens.inc','MenuReplayCalendar.obj',
        'MenuReplayCalendar.map','compile.rsp','read_build_environment.cmd']
    try:
        report['actual_sdk_oracle']=extract_sdk()
        data=read_actual_catalog();labels,report['actual_localization']=actual_localization(data);cases,sdk=actual_cases(data)
        lua,lua_report=original_lua(data,cases);report['original_lua']=lua_report
        samples,weeks_sample=actual_samples(data,cases,lua,labels)
        report['actual_korean_static_samples']=samples
        report['actual_sdk_weeks_korean_static_sample']=dict(calendar=6,speed=2,start_year=-4000,turn=4,expected=weeks_sample)
        write_goldens(data,cases,sdk,lua,labels,samples,weeks_sample)
        report['actual_catalog']=dict(calendars=data['calendars'],game_speeds=data['speeds'],
            month_rows=len(data['months']),season_rows=len(data['seasons']),
            speed_turn_rows={key:len(value) for key,value in data['turns'].items()},defines=data['defines'])
        compiled=build_cxx14('MenuReplayCalendar',BUILD,EVIDENCE,CPP,[PROJECT/'Source/Host',BUILD])
        report['build']=compiled
        dependents=run([Path(compiled['compiler']).with_name('dumpbin.exe'),'/dependents',compiled['path']],cwd=BUILD,timeout=30)
        names=sorted(set(re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$',dependents.stdout.decode('mbcs',errors='replace'),re.M)))
        if dependents.returncode or {name.lower() for name in names}!={'kernel32.dll'}:
            raise ValueError('Unexpected SDK-free fixture DLL dependency '+repr(names))
        report['component_imported_dlls']=names
        result=run([compiled['path']],cwd=BUILD,timeout=60)
        if result.returncode:raise ValueError((result.stdout+result.stderr).decode('utf8',errors='replace'))
        report.update(json.loads(result.stdout))
        report['inputs_after']=[artifact(path) for path in inputs]
        if report['inputs_after']!=before:raise ValueError('Calendar source or immutable inputs changed during fixture')
    except Exception as error:
        report.update(status='FAIL_SDK_FREE_CALENDAR',error=str(error));raise
    finally:
        removed=[]
        for name in intermediates:
            path=BUILD/name
            if not path.exists():continue
            if path.absolute().parent!=BUILD.absolute():raise ValueError('Owned cleanup escaped component build directory')
            info=storage.ordinary(path)
            if info.st_nlink!=1:raise ValueError('Owned intermediate is shared or linked: '+str(path))
            row=dict(artifact(path),file_identity=[info.st_dev,info.st_ino],allocated_bytes=storage.allocated(path))
            if storage.metadata(info)!=storage.metadata(storage.ordinary(path)):raise ValueError('Cleanup identity changed')
            path.unlink();row['result']='DELETED_EXACT_OWNED_REGENERABLE_CALENDAR_INTERMEDIATE';removed.append(row)
        report['owned_intermediate_cleanup']=removed
        report['owned_intermediate_bytes_removed']=sum(row['bytes'] for row in removed)
        report['owned_intermediate_allocated_bytes_removed']=sum(row['allocated_bytes'] for row in removed)
        receipt.write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(status=report['status'],checks=report['checks'],
        original_lua_goldens=report['original_lua_goldens'],sdk_weeks_goldens=report['actual_sdk_weeks_goldens'],
        report=str(receipt))))
    return 0


if __name__=='__main__':raise SystemExit(main())
