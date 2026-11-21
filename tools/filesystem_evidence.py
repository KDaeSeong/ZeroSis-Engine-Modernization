"""Revalidate native filesystem provenance, real disk tests and SDK map integration."""
import json,re
from pathlib import Path
from collect_baseline import PROJECT,digest,read_text,pe_header
from verify_world_builder_map_object import check_artifacts

def validate(build_path=None):
    bp=PROJECT/'evidence/filesystem/build_result.json';cp=bp.with_name('conformance.json')
    if build_path is not None and Path(build_path).resolve()!=bp:raise RuntimeError('Unexpected filesystem report')
    b=json.loads(bp.read_text(encoding='utf-8'));c=json.loads(cp.read_text(encoding='utf-8'));check_artifacts([b,c])
    if b['status']!='FILESYSTEM_X64_PROVIDER_BUILT' or c['status']!='FILESYSTEM_NATIVE_COMPONENT_PASS' or c['issues']:raise RuntimeError('Filesystem component did not pass')
    if b['runtime']!='/MD' or not b['production_filesystem_implemented'] or not c['windows_file_io_executed']:raise RuntimeError('Filesystem implementation missing')
    from world_builder_map_bridge_evidence import provider as map_provider
    mb,_,entry=map_provider()
    if b['map_provider']!=entry or b['map_dependencies']!=mb['dependencies']:raise RuntimeError('Map/filesystem component dependency mismatch')
    allowed={'kernel32.dll','msvcp140.dll','vcruntime140.dll','vcruntime140_1.dll'}
    for consumer in b['consumers'].values():
        if pe_header(Path(consumer['executable']['path']))['architecture']!='x64':raise RuntimeError('Non-x64 filesystem executable')
        dependencies=consumer['imports']['dependencies']
        if not dependencies or any(d.lower() not in allowed and not d.lower().startswith('api-ms-win-crt-') for d in dependencies):raise RuntimeError('Unexpected filesystem import')
        linkmap=read_text(Path(consumer['map']['path']))
        if '?GetInstance@FIFileSystem@@SAAEAV1@XZ' not in linkmap or 'ZeroSis_FileSystem_x64:SdkFileSystem.obj' not in linkmap:raise RuntimeError('Native filesystem SDK binding missing')
    for row in b['logs']:
        if re.search(r'\b(?:warning|error)\s+[A-Z]+\d+',read_text(Path(row['path'])),re.I):raise RuntimeError('Filesystem build warning/error')
    e=c['execution'];m=c['map_execution'];text=read_text(Path(e['log']['path']));mt=read_text(Path(m['log']['path']))
    if (e['exit_code'],e['checks'],e['failure_cases'],m['exit_code'],m['checks'],m['failure_cases'])!=(0,1973,21,0,113,12):raise RuntimeError('Filesystem test accounting differs')
    required=['PASS|1973','FAULTS|21|destination_preserved|no_open_handles|no_temporary_files',
              'WORKERS|4|128_independent_file_transactions','PATHS|collision_preserved|open_target_rejected|retry_after_close|long_unicode_paths|edit_source_close_failure',
              'BOUNDARIES|unsupported_flags|invalid_paths|seek_overflow|4GiB_file_rejected']
    if any(marker not in text for marker in required) or 'MAP_NATIVE_IO|12_failure_cases|file_and_object_preserved|3_byte_chunks' not in mt or 'PASS|113' not in mt:
        raise RuntimeError('Filesystem failure evidence incomplete')
    if any(Path(e['directory']).glob('.zerosis-txn-*')):raise RuntimeError('Transaction temp leaked')
    if any(b[k] or c[k] for k in ('gamecore_loaded','game_launched')) or any(c[k] for k in ('game_multicore_verified','power_loss_recovery_verified','pak_catalog_implemented','original_concrete_filesystem_oracle_available')):
        raise RuntimeError('Unsupported filesystem scope claim')
    return b,c,{'name':'FileSystem','library':b['library'],'build_report':{'path':str(bp),'sha256':digest(bp)},
                'conformance':{'path':str(cp),'sha256':digest(cp)},'runtime':'/MD',
                'scope':'NATIVE_WINDOWS_REGULAR_FILE_IO_AND_STAGED_MAP_SAVE_NOT_PAK_OR_GAME_RUNTIME'}
def validate_link():
    path=PROJECT/'evidence/filesystem/link_trial.json';r=json.loads(path.read_text(encoding='utf-8'));check_artifacts(r)
    if r['status']!='FILESYSTEM_SDK_LINK_PASS_NOT_GAME_RUNTIME' or (r['before'],r['after'],r['gamecore_objects'],r['providers'])!=(2,1,161,16):raise RuntimeError('Filesystem link evidence differs')
    if r['official_unresolved_symbols']!=0 or r['baseline_excluded_providers']!=['Logging']:raise RuntimeError('Filesystem isolated link scope differs')
    expected={'?GetInstance@FILogFileMgr@@SAAEAV1@XZ'}
    required='?GetInstance@FIFileSystem@@SAAEAV1@XZ'
    if r['resolved']!=[required] or len(r['runs'])!=2:raise RuntimeError('Wrong filesystem symbol closure')
    for trial,wanted in zip(r['runs'],(expected|{required},expected)):
        text=read_text(Path(trial['log']['path']))
        if set(trial['unresolved'])!=wanted or trial['unresolved_count']!=len(wanted) or not trial['exit_code'] or trial['generated_dll']:raise RuntimeError('Filesystem trial differs')
        if not re.search(r'LNK1120:\s*'+str(len(wanted))+r'(?!\d)',text):raise RuntimeError('Filesystem linker diagnostic missing')
    if any(r[k] for k in ('gamecore_loaded','game_launched','game_multicore_verified')):raise RuntimeError('Invalid game execution claim')
    return r

if __name__=='__main__':
    b,c,_=validate();print(json.dumps({'status':'FILESYSTEM_EVIDENCE_PASS','checks':c['execution']['checks']+c['map_execution']['checks']}))
