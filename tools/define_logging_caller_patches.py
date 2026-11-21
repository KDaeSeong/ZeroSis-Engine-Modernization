"""Preserve 495 accepted SDK patches and make prepared log text a literal argument."""
import json,re
from collections import defaultdict
from collect_baseline import PROJECT,digest

PREFIX='logging_callers_'
BASE=PROJECT/'evidence/sdk_x64/attempts/attempt_020/sdk_x64_patches.json'
PATTERN=re.compile(r'->(Msg|DebugMsg|WarningMsg|ErrorMsg)\(([^\r\n]*)\);')
ARGUMENTS={'strOutBuf','strLog','strBaseString','strHeader','strLine','strMsg','rngLogMessage.c_str()',
           'buf','strOutput','szMessage','strTemp','szOut','stackTrace.c_str()','msg'}

def patches():
    baseline=json.loads(BASE.read_text(encoding='utf-8'))
    if len(baseline['patches'])!=495:raise RuntimeError('Expected accepted 495-patch baseline')
    result=[];calls=[];files=[]
    sdk=PROJECT/'Source/SDK_BNW_Original'
    for source in sorted((sdk/'CvGameCoreDLL_Expansion2').rglob('*')):
        if source.suffix not in ('.cpp','.h'):continue
        relative=source.relative_to(sdk).as_posix();text=source.read_bytes().decode('latin1')
        for patch in baseline['patches']:
            if patch['file']==relative:
                if text.count(patch['old'])!=patch['count']:raise RuntimeError('SDK baseline patch drift')
                text=text.replace(patch['old'],patch['new'])
        groups=defaultdict(list)
        for match in PATTERN.finditer(text):
            argument=match[2]
            if argument.startswith('"'):continue
            if argument not in ARGUMENTS:raise RuntimeError('Review new logger expression: '+argument)
            method=match[1];new=f'->{method}("%s", static_cast<const char*>({argument}));'
            groups[(match[0],new)].append(text.count('\n',0,match.start())+1)
            calls.append({'file':relative,'line':text.count('\n',0,match.start())+1,'method':method,'argument':argument,'old':match[0],'new':new})
        for index,((old,new),lines) in enumerate(sorted(groups.items())):
            result.append({'id':PREFIX+source.stem.lower()+'_'+str(index),'file':relative,'source_sha256':digest(source),
                'old':old,'new':new,'count':len(lines),
                'reason':'Treat completed log text as data, never as a second printf format; explicit const-char pointer avoids class objects in varargs.'})
        if groups:files.append(relative)
    if len(calls)!=155 or len(files)!=38:raise RuntimeError('Reviewed logging call inventory drift')
    relative='CvGameCoreDLL_Expansion2/CvDllDatabaseUtility.cpp';source=sdk/relative
    result.append({'id':PREFIX+'database_local_buffer','file':relative,'source_sha256':digest(source),
        'old':'\tstatic char buf[kBuffSize];','new':'\tchar buf[kBuffSize] = {0};','count':1,
        'reason':'Make database diagnostic formatting use each call stack instead of a shared writable static buffer.'})
    return result,calls

def main():
    path=PROJECT/'Source/Porting/sdk_x64_patches.json';plan=json.loads(path.read_text(encoding='utf-8'))
    baseline=json.loads(BASE.read_text(encoding='utf-8'));retained=[p for p in plan['patches'] if not p['id'].startswith((PREFIX,'bootstrap_callers_','debug_callers_','globals_callers_','construction_callers_','host_callers_','db_postprocess_', 'db_loader_', 'info_cleanup_' ,'db_cache_', 'startup_owners_', 'gc_lifecycle_', 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))]
    if retained!=baseline['patches']:raise RuntimeError('The accepted 495 SDK patches changed')
    added,calls=patches();later=[p for p in plan['patches'] if p['id'].startswith(('bootstrap_callers_','debug_callers_','globals_callers_','construction_callers_','host_callers_','db_postprocess_', 'db_loader_', 'info_cleanup_' ,'db_cache_', 'startup_owners_', 'gc_lifecycle_', 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))];plan['patches']=retained+added+later
    path.write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    ledger_path=PROJECT/'evidence/numeric_boundaries/edit_ledger.json';ledger=json.loads(ledger_path.read_text(encoding='utf-8'))
    ledger['patch_specification_sha256']=digest(path)
    prefixes=('serialization_','temp_callers_','auto_callers_','db_callers_','localization_callers_','world_mod_access_','world_map_access_','world_map_bridge_access_',PREFIX,'bootstrap_callers_','debug_callers_','globals_callers_','construction_callers_','host_callers_','db_postprocess_', 'db_loader_', 'info_cleanup_' ,'db_cache_', 'startup_owners_', 'gc_lifecycle_', 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_')
    ledger['supplemental_non_numeric_patches']=[p['id'] for p in plan['patches'] if p['id'].startswith(prefixes)]
    ledger['unchanged_logging_caller_baseline']={'path':str(BASE),'sha256':digest(BASE)}
    ledger_path.write_text(json.dumps(ledger,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    out=PROJECT/'evidence/logging/caller_patch_plan.json'
    report={'status':'SDK_LOGGING_LITERAL_CALLERS_DECLARED','baseline':ledger['unchanged_logging_caller_baseline'],
        'recipe':{'path':str(PROJECT/'tools/define_logging_caller_patches.py'),'sha256':digest(PROJECT/'tools/define_logging_caller_patches.py')},
        'patch_specification':{'path':str(path),'sha256':digest(path)},'previous_patches':495,'added_patches':len(added),
        'total_patches':len(plan['patches']),'later_patches':len(later),'text_calls':len(calls),'files':38,'calls':calls,'gamecore_loaded':False,'game_launched':False}
    out.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('status','added_patches','total_patches','text_calls','files')}))
if __name__=='__main__':main()

