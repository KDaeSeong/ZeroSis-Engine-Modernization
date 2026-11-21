"""Validate SDK logger provenance, real file observations and literal caller patches."""
import json,re
from pathlib import Path
from collect_baseline import PROJECT,digest,read_text,pe_header
from verify_world_builder_map_object import check_artifacts
from define_logging_caller_patches import patches,BASE,PREFIX,PATTERN

def validate_callers():
    declared=json.loads((PROJECT/'evidence/logging/caller_patch_plan.json').read_text(encoding='utf-8'));check_artifacts(declared)
    plan=json.loads((PROJECT/'Source/Porting/sdk_x64_patches.json').read_text(encoding='utf-8'))
    baseline=json.loads(BASE.read_text(encoding='utf-8'));added,calls=patches()
    if [p for p in plan['patches'] if not p['id'].startswith((PREFIX,'bootstrap_callers_','debug_callers_','globals_callers_','construction_callers_','host_callers_','db_postprocess_', 'db_loader_', 'info_cleanup_' ,'db_cache_', 'startup_owners_', 'gc_lifecycle_', 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))]!=baseline['patches'] or [p for p in plan['patches'] if p['id'].startswith(PREFIX)]!=added:
        raise RuntimeError('Logger caller baseline/recipe differs')
    if (len(plan['patches']),len(added),len(calls))!=(693,48,155) or declared['calls']!=calls:raise RuntimeError('Logger caller inventory differs')
    for relative in {c['file'] for c in calls}:
        source=PROJECT/'Source/SDK_BNW_x64'/relative;text=source.read_bytes().decode('latin1')
        expected=[p for p in added if p['file']==relative]
        if any(text.count(p['new'])!=p['count'] or p['old'] in text for p in expected):raise RuntimeError('Actual SDK logger patch missing: '+relative)
        if any(not m[2].startswith('"') for m in PATTERN.finditer(text)):raise RuntimeError('Nonliteral logging format remains: '+relative)
    build=json.loads((PROJECT/'evidence/sdk_x64/build_result.json').read_text(encoding='utf-8'))
    if build['status']!='SDK_X64_ALL_OBJECTS_COMPILED' or len(build['objects'])!=161 or build['patch_specification']['sha256']!=digest(PROJECT/'Source/Porting/sdk_x64_patches.json'):
        raise RuntimeError('Patched logging callers were not compiled into all GameCore objects')
    return declared

def validate(build_path=None):
    bp=PROJECT/'evidence/logging/build_result.json';cp=bp.with_name('conformance.json')
    if build_path is not None and Path(build_path).resolve()!=bp:raise RuntimeError('Unexpected logger report')
    b=json.loads(bp.read_text(encoding='utf-8'));c=json.loads(cp.read_text(encoding='utf-8'));check_artifacts([b,c])
    validate_callers()
    from filesystem_evidence import validate as filesystem
    _,_,fs=filesystem()
    if b['filesystem_provider']!=fs or b['status']!='LOGGING_X64_PROVIDER_BUILT' or b['runtime']!='/MD':raise RuntimeError('Logger dependency/build mismatch')
    if c['status']!='LOGGING_NATIVE_COMPONENT_PASS' or c['issues']:raise RuntimeError('Logger component did not pass')
    consumer=b['consumer']
    if pe_header(Path(consumer['executable']['path']))['architecture']!='x64':raise RuntimeError('Non-x64 logger')
    deps=consumer['imports']['dependencies'];allowed={'kernel32.dll','msvcp140.dll','vcruntime140.dll','vcruntime140_1.dll'}
    if not deps or any(d.lower() not in allowed and not d.lower().startswith('api-ms-win-crt-') for d in deps):raise RuntimeError('Unexpected logger import')
    linkmap=read_text(Path(consumer['map']['path']))
    if '?GetInstance@FILogFileMgr@@SAAEAV1@XZ' not in linkmap or 'ZeroSis_Logging_x64:SdkLogFile.obj' not in linkmap:raise RuntimeError('Actual SDK logger symbol missing')
    for row in b['logs']:
        if re.search(r'\b(?:warning|error)\s+[A-Z]+\d+',read_text(Path(row['path'])),re.I):raise RuntimeError('Logger build diagnostic')
    e=c['execution'];text=read_text(Path(e['log']['path']))
    if (e['exit_code'],e['checks'],e['fault_cases'],c['shared_records'],c['shared_unique'],c['sdk_caller_records'])!=(0,2169,19,1600,1600,155):
        raise RuntimeError('Logger execution accounting differs')
    required=['PASS|2169','FAULTS|19|prior_records_preserved|partial_append_rollback|explicit_recovery',
              'WORKERS|8|1600_shared_log_records','SDK_CALLERS|155|literal_percent_strings|actual_CvString_and_pointer_arguments']
    if any(s not in text for s in required):raise RuntimeError('Logger execution proof missing')
    regression=json.loads(Path(c['missing_error_code_regression']['path']).read_text(encoding='utf-8'));check_artifacts(regression)
    if regression['status']!='LOG_WRITE_FALSE_WITH_ZERO_ERROR_REPRODUCED' or regression['exit_code']!=2 or regression['expected_bytes_hex']!='736565640d0a' or regression['actual_bytes_hex']!='736565640d0a616263646566':raise RuntimeError('Logger zero-error-code defect evidence differs')
    directory=Path(e['directory'])
    records=(directory/'concurrent.log').read_text(encoding='utf-8').splitlines()
    if len(records)!=1600 or set(records)!={f'{w},{i},payload' for w in range(8) for i in range(200)}:raise RuntimeError('Logger records interleaved/duplicated/missing')
    _,calls=patches();severity={'Msg':'','DebugMsg':'[DEBUG] ','WarningMsg':'[WARNING] ','ErrorMsg':'[ERROR] '}
    if (directory/'sdk_callers.log').read_text(encoding='utf-8').splitlines()!=[severity[r['method']]+'City 100% %s %n literal payload' for r in calls]:
        raise RuntimeError('Prepared SDK text was reinterpreted')
    if not c['windows_log_io_executed'] or not c['shared_exact_set'] or not c['sdk_caller_exact']:raise RuntimeError('Logger observation claim mismatch')
    if any(b[k] or c[k] for k in ('gamecore_loaded','game_launched')) or any(c[k] for k in ('original_concrete_logger_oracle_available','game_multicore_verified','power_loss_recovery_verified')):
        raise RuntimeError('Unsupported full logger/game execution claim')
    return b,c,{'name':'Logging','library':b['library'],'build_report':{'path':str(bp),'sha256':digest(bp)},
                'conformance':{'path':str(cp),'sha256':digest(cp)},'runtime':'/MD',
                'scope':'NATIVE_SDK_LOGGER_AND_LITERAL_CALLERS_NOT_GAME_INITIALIZATION_OR_RUNTIME'}

def validate_link():
    path=PROJECT/'evidence/logging/link_trial.json';r=json.loads(path.read_text(encoding='utf-8'));check_artifacts(r)
    if r['status']!='LOGGING_SDK_LINK_PASS_NOT_GAME_RUNTIME' or (r['before'],r['after'],r['gamecore_objects'],r['providers'])!=(1,0,161,16):raise RuntimeError('Logger link evidence differs')
    expected=set()
    required='?GetInstance@FILogFileMgr@@SAAEAV1@XZ'
    if r['resolved']!=[required] or len(r['runs'])!=2:raise RuntimeError('Wrong logger symbol closure')
    for trial,wanted in zip(r['runs'],(expected|{required},expected)):
        text=read_text(Path(trial['log']['path']))
        if set(trial['unresolved'])!=wanted or trial['unresolved_count']!=len(wanted):raise RuntimeError('Logger trial differs')
        if wanted:
            if not trial['exit_code'] or trial['generated_dll'] or not re.search(r'LNK1120:\s*1(?!\d)',text):raise RuntimeError('Logger linker diagnostic missing')
        elif trial['exit_code'] or not trial['generated_dll'] or pe_header(Path(trial['dll']['path']))['architecture']!='x64':
            raise RuntimeError('Logger complete link artifact missing')
    if any(r[k] for k in ('gamecore_loaded','game_launched','game_multicore_verified')):raise RuntimeError('Invalid game execution claim')
    return r

if __name__=='__main__':
    _,c,_=validate();print(json.dumps({'status':'LOGGING_EVIDENCE_PASS','checks':c['execution']['checks'],'literal_callers':c['sdk_caller_records']}))
