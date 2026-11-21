"""Run real host services/data and injected lifecycle tests, never --initialize."""
import argparse,json,re,shutil,sqlite3,uuid
from pathlib import Path
from collect_baseline import PROJECT,digest,read_text
from probe_world_builder import artifact
from native_build import run
from verify_world_builder_map_object import check_artifacts

MARKER='STARTUP_FAILURES=16 CLEANUP_RETRY_CASES=12 BUSY_CALLS=512 REENTRY=28 RESTARTS=64 SERVICE_WORK=1024 GAMECORE_LOADED=false'
SHARED_MARKER='BUNDLE_VERIFIED files=10 architecture=x64 GAMECORE_LOADED=false'


def verify_shared(new_game_sdk=False):
    root=PROJECT/'evidence/host';build_path=root/'shared_build_result.json';bundle_path=root/'shared_bundle.json'
    build=json.loads(build_path.read_text(encoding='utf-8'));bundle=json.loads(bundle_path.read_text(encoding='utf-8'))
    stage=PROJECT/'Stage/NativeHost/SharedCandidate';check_artifacts([build,bundle])
    expected_profile='shared-lua-new-game-sdk-v4' if new_game_sdk else 'shared-lua-v4'
    if build.get('profile')!=expected_profile or bundle.get('profile')!=expected_profile or bundle.get('manifest_version')!='ZEROSIS_HOST_BUNDLE_V4':
        raise RuntimeError('Shared candidate profile or manifest version differs')
    if len(bundle.get('files',[]))!=10:raise RuntimeError('V4 shared candidate must contain exactly ten files')
    by_name={Path(row['path']).name:row for row in bundle['files']}
    required={'ZeroSisHost_x64.exe','CvGameCoreDLL_Expansion2_x64.dll','ZeroSisDatabase_x64.dll','ZeroSisLocalization_x64.dll',
        'ZeroSisLua51_x64.dll','rules.db','localization.db','icudt44l.dat','audio-catalog.bin','script-catalog.bin'}
    if set(by_name)!=required:raise RuntimeError('Shared bundle file set differs from V4 contract')
    if not all((stage/name).is_file() and digest(stage/name)==row['sha256'] for name,row in by_name.items()):raise RuntimeError('Shared staged files differ from pinned bundle')
    imports=build['builds']['host']['imports']['dependencies']
    if 'ZeroSisLua51_x64.dll' not in imports:raise RuntimeError('Host does not import the shared Lua DLL')
    if 'dummynode_' in Path(build['builds']['host']['map']['path']).read_text(errors='replace'):
        raise RuntimeError('Host contains private Lua symbols')
    selected=build.get('new_game_sdk_build') if new_game_sdk else build['shared_lua_build']
    if not selected or (new_game_sdk and bundle.get('selected_gamecore_source')!='new_game_sdk'):
        raise RuntimeError('New-game SDK GameCore selection is absent')
    sdk_path=PROJECT/'evidence/new_game_sdk/build_result.json'
    runtime_path=PROJECT/'evidence/shared_lua_runtime/build_result.json'
    expected_core=json.loads(sdk_path.read_text(encoding='utf-8'))['gamecore'] if new_game_sdk else json.loads(runtime_path.read_text(encoding='utf-8'))['gamecore']
    if by_name['CvGameCoreDLL_Expansion2_x64.dll']['sha256']!=expected_core['sha256']:
        raise RuntimeError('V4 bundle contains a different GameCore than the selected source report')
    core_map=(json.loads(sdk_path.read_text(encoding='utf-8'))['map'] if new_game_sdk else json.loads(runtime_path.read_text(encoding='utf-8'))['gamecore_map'])
    if 'dummynode_' in Path(core_map['path']).read_text(errors='replace'):
        raise RuntimeError('Selected GameCore contains private Lua symbols')
    exe=stage/'ZeroSisHost_x64.exe';runs=[]
    def execute(name,command,expected,marker):
        result=run(command,cwd=command[0].parent,timeout=45);log=root/('shared_'+name+'_execution.log');log.write_bytes(result.stdout+result.stderr)
        output=read_text(log).replace('\r\n','\n')
        if result.returncode!=expected or marker not in output:raise RuntimeError(name+': '+output[-3500:])
        runs.append({'name':name,'executable':artifact(command[0]),'exit_code':result.returncode,'log':artifact(log),'required_marker':marker})
    execute('capabilities',[exe,'--capabilities'],0,'GAMECORE_LOADED=false')
    execute('bundle',[exe,'--verify-bundle'],0,SHARED_MARKER)
    check_dir=PROJECT/'Build/Host/shared-validation'/uuid.uuid4().hex;check_dir.mkdir(parents=True)
    for row in bundle['files']:shutil.copy2(row['path'],check_dir/Path(row['path']).name)
    manifest=check_dir/'bundle.manifest';original=manifest.read_text(encoding='ascii');lines=original.splitlines()
    cases={
        'v3_rejected':('ZEROSIS_HOST_BUNDLE_V3\n'+'\n'.join(lines[1:])+'\n','Invalid bundle manifest version'),
        'missing_lua':('\n'.join(line for line in lines if not line.startswith('ZeroSisLua51_x64.dll|'))+'\n','Bundle manifest is incomplete'),
        'missing_gamecore':('\n'.join(line for line in lines if not line.startswith('CvGameCoreDLL_Expansion2_x64.dll|'))+'\n','Bundle manifest is incomplete'),
        'bad_lua_hash':(original.replace('ZeroSisLua51_x64.dll|'+by_name['ZeroSisLua51_x64.dll']['sha256'],'ZeroSisLua51_x64.dll|'+'0'*64),'Bundle hash differs: ZeroSisLua51_x64.dll'),
        'bad_hash_syntax':(original.replace('rules.db|'+by_name['rules.db']['sha256'],'rules.db|INVALID'),'Unexpected, duplicate or invalid')}
    for name,(text,marker) in cases.items():
        manifest.write_text(text,encoding='ascii');execute(name,[check_dir/exe.name,'--verify-bundle'],1,marker)
    manifest.write_text(original,encoding='ascii')
    report={'status':'SHARED_LUA_BUNDLE_V4_PASS','build':artifact(build_path),'bundle':artifact(bundle_path),
        'verifier':artifact(Path(__file__).resolve()),'profile':expected_profile,'bundle_files':10,'malformed_bundle_cases':len(cases),
        'runs':runs,'selected_new_game_sdk':new_game_sdk,'shared_lua_import_verified':True,'private_lua_symbols_absent':True,
        'gamecore_loaded':False,'game_launched':False,'first_turn_verified':False,'game_multicore_verified':False,
        'scope':'SHARED_LUA_V4_HOST_AND_BUNDLE_CONTRACT; NEW_GAME_AND_TURN_RUNTIME_EVIDENCE_REMAINS_SEPARATE'}
    report_path=root/'shared_conformance.json';report_path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'bundle_files':10,'malformed_bundle_cases':len(cases)}))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--shared-lua',action='store_true');parser.add_argument('--new-game-sdk',action='store_true')
    args=parser.parse_args()
    if args.new_game_sdk and not args.shared_lua:parser.error('--new-game-sdk requires --shared-lua')
    if args.shared_lua:
        verify_shared(args.new_game_sdk);return
    from verify_host_script_access import main as verify_script_access
    script_access=verify_script_access()
    from host_game_info_evidence import verify as verify_game_info,validate as validate_game_info
    verify_game_info();game_info,_=validate_game_info()
    root=PROJECT/'evidence/host';bp=root/'build_result.json';bundle_path=root/'bundle.json'
    build=json.loads(bp.read_text());bundle=json.loads(bundle_path.read_text())
    audio=json.loads((root/'audio_catalog.json').read_text());scripts=json.loads((root/'script_catalog.json').read_text())
    check_artifacts([build,bundle,audio,scripts]);stage=PROJECT/'Stage/NativeHost'
    before={r['path']:digest(Path(r['path'])) for r in bundle['files']}
    runs=[]
    def execute(name,exe,args,expected,marker):
        if args and args[0] not in ('--capabilities','--verify-bundle','--check-data','--unknown-option') and not (
                (name=='map_audio' and exe==Path(build['builds']['map_audio_tests']['executable']['path']) and args==[audio['catalog']['path']]) or
                (name=='script_assets' and exe==Path(build['builds']['script_asset_tests']['executable']['path']) and args==[scripts['catalog']['path']])):
            raise RuntimeError('Refusing a GameCore-loading command')
        result=run([exe,*args],cwd=exe.parent,timeout=45)
        log=root/(name+'_execution.log');log.write_bytes(result.stdout+result.stderr)
        output=read_text(log).replace('\r\n','\n')
        if result.returncode!=expected or marker not in output:raise RuntimeError(name+': '+output[-4000:])
        runs.append({'name':name,'executable':artifact(exe),'arguments':args,'exit_code':result.returncode,'log':artifact(log),'required_marker':marker})
        return output
    test=Path(build['builds']['tests']['executable']['path'])
    output=execute('tests',test,[],0,MARKER)
    found=re.search(r'NATIVE_HOST_TEST_PASS checks=(\d+)',output)
    if not found:raise RuntimeError('Missing host native assertions')
    assertions=int(found[1])
    script_lifecycle='SCRIPT_LIFECYCLE_PASS ACTIVE_SHUTDOWN_REJECTED=true FINALIZER_BEFORE_MODULE_RELEASE=true' in output
    if not script_lifecycle or 'SCRIPT_LIBRARY_BIND_FAILURES=3' not in output:raise RuntimeError('Script/GameCore lifecycle/binding failures were not tested')
    output=execute('map_audio',Path(build['builds']['map_audio_tests']['executable']['path']),[audio['catalog']['path']],0,'HOST_MAP_AUDIO_PASS')
    m=re.search(r'HOST_MAP_AUDIO_PASS checks=(\d+) MAP_ALLOCATION_FAILURES=2 CATALOG_ALLOCATION_FAILURES=(\d+) MALFORMED_CASES=(\d+) MAP_RESIZES=128 READ_OPERATIONS=4096 AUDIO_LOOKUPS=8192 GAMECORE_LOADED=false',output)
    if not m:raise RuntimeError('Missing map/audio service observations')
    map_audio_checks,allocation_failures,malformed_catalog_cases=map(int,m.groups())
    expected=[]
    for row in audio['records']:
        raw=row['xml'].encode('utf-8');fingerprint=14695981039346656037
        for byte in raw:fingerprint=((fingerprint^byte)*1099511628211)&((1<<64)-1)
        expected.append((str(row['index']),row['tag'],str(len(raw)),f'{fingerprint:016x}'))
    if re.findall(r'AUDIO_DEFINITION index=(\d+) tag=(\w+) xml_bytes=(\d+) xml_fnv=([0-9a-f]+)',output)!=expected:
        raise RuntimeError('Native audio definitions differ from installed XML compilation')
    output=execute('scripts',Path(build['builds']['script_tests']['executable']['path']),[],0,'HOST_SCRIPT_PASS')
    m=re.search(r'HOST_SCRIPT_PASS checks=(\d+) CPP_FAILURES=(\d+) LUA_CREATE_FAILURES=(\d+) LUA_EXECUTE_FAILURES=(\d+) LUA_EVENT_FAILURES=(\d+) FOREIGN_REJECTIONS=160 RESTARTS=32 GAMECORE_LOADED=false',output)
    if not m:raise RuntimeError('Missing actual Lua service/failure observations')
    script_checks,cpp_failures,lua_create_failures,lua_execute_failures,lua_event_failures=map(int,m.groups())
    output=execute('script_assets',Path(build['builds']['script_asset_tests']['executable']['path']),[scripts['catalog']['path']],0,'HOST_SCRIPT_ASSETS_PASS')
    m=re.search(r'HOST_SCRIPT_ASSETS_PASS checks=(\d+) files=(\d+) maps=(\d+) MALFORMED_CASES=(\d+) GAMECORE_LOADED=false',output)
    if not m:raise RuntimeError('Missing native script catalog/map metadata evidence')
    asset_checks,script_files,map_scripts,malformed_scripts=map(int,m.groups())
    asset_failures={name:int(re.search(marker+r'=(\d+)',output)[1]) for name,marker in
                    [('catalog_cpp','SCRIPT_CATALOG_ALLOCATION_FAILURES'),('include_cpp','SCRIPT_INCLUDE_CPP_FAILURES'),('include_lua','SCRIPT_INCLUDE_LUA_FAILURES')]}
    if 'SCRIPT_LIBRARY_BINDING_PASS FAILED_REGISTRATION_VM_PUBLISHED=false BORROWED_UTILITY_DESTROYED=false' not in output:
        raise RuntimeError('Borrowed script utility registration/lifetime evidence missing')
    definitions=[];expected_metadata=[]
    for row in scripts['records']:
        raw=Path(row['snapshot']['path']).read_bytes();fingerprint=14695981039346656037
        for byte in raw:fingerprint=((fingerprint^byte)*1099511628211)&((1<<64)-1)
        definitions.append((row['virtual_path'],str(len(raw)),f'{fingerprint:016x}'))
        if row['virtual_path'].startswith('maps/'):
            source=raw.decode('latin1')
            body=re.search(r'function\s+GetMapScriptInfo\s*\(\s*\)(.*?)\nend\b',source,re.S)
            table=re.search(r'\breturn\s*\{(.*)',body[1],re.S)
            name=re.search(r'\bName\s*=\s*[\"\']([^\"\']+)',table[1])[1]
            description=re.search(r'\bDescription\s*=\s*[\"\']([^\"\']+)',table[1])[1]
            expected_metadata.append((row['virtual_path'],name,description))
    if re.findall(r'SCRIPT_FILE path=(\S+) bytes=(\d+) fnv=([0-9a-f]+)',output)!=definitions:
        raise RuntimeError('Native script catalog differs from original bytes')
    map_metadata=re.findall(r'MAP_METADATA path=(\S+) name=(\S+) description=(\S+) options=(\d+)',output)
    if [row[:3] for row in map_metadata]!=expected_metadata or script_files!=len(scripts['records']) or map_scripts!=len(expected_metadata):
        raise RuntimeError('Map script metadata differs from its original source literals')
    exe=stage/'ZeroSisHost_x64.exe'
    prior_sessions=set((stage/'sessions').iterdir()) if (stage/'sessions').exists() else set()
    execute('capabilities',exe,['--capabilities'],0,'GAMECORE_LOADED=false')
    execute('bundle',exe,['--verify-bundle'],0,'BUNDLE_VERIFIED files=9 architecture=x64 GAMECORE_LOADED=false')
    execute('usage',exe,['--unknown-option'],2,'Usage:')
    after_sessions=set((stage/'sessions').iterdir()) if (stage/'sessions').exists() else set()
    if after_sessions!=prior_sessions:raise RuntimeError('Read-only modes created session state')
    with sqlite3.connect((stage/'rules.db').as_uri()+'?mode=ro',uri=True) as db:
        expected_counts=[db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for table in ('Civilizations','Units','Buildings')]
    data_runs=[]
    for language,table in bundle['languages']:
        output=execute('data_'+language,exe,['--check-data',language],0,'HOST_DATA_CHECK_PASS GAMECORE_LOADED=false')
        counts=[int(n) for n in re.search(r'RULE_COUNTS=(\d+,\d+,\d+)',output)[1].split(',')]
        with sqlite3.connect((stage/'localization.db').as_uri()+'?mode=ro',uri=True) as db:
            # Table names are verified against the frozen language metadata, not external input.
            if not re.fullmatch(r'Language_[A-Za-z_]+',table):raise RuntimeError('Unexpected language table')
            expected_text=db.execute('SELECT Text FROM '+table+' WHERE Tag=?',('TXT_KEY_SINGLE_PLAYER',)).fetchone()[0]
        if counts!=expected_counts or '\nLANGUAGE='+language+'\n' not in output or '\nSAMPLE_TEXT='+expected_text+'\n' not in output:
            raise RuntimeError('Native host data differs from independent SQLite query')
        audio_counts=[int(n) for n in re.search(r'AUDIO_TAG_COUNTS=(\d+,\d+,\d+)',output)[1].split(',')]
        missing_tags=re.findall(r'^MISSING_AUDIO_TAG=(.+)$',output,re.M)
        if audio_counts!=[len(audio['records']),len(audio['required_rule_tags'])-len(audio['missing_rule_tags']),len(audio['missing_rule_tags'])] or missing_tags!=audio['missing_rule_tags']:
            raise RuntimeError('Native host soundscape lookup differs from installed XML/rules evidence')
        script_observation=[int(n) for n in re.search(r'SCRIPT_OBSERVATION=(\d+,\d+,\d+)',output)[1].split(',')]
        expected_bytes=len(expected_text.encode('utf-8'))
        if script_observation!=[expected_counts[0],expected_bytes,expected_counts[0]+expected_bytes]:
            raise RuntimeError('Lua SDK argument/event result differs from independent DB/text inputs')
        if '\nMAP_SCRIPT_METADATA=TXT_KEY_MAP_CONTINENTS,TXT_KEY_MAP_CONTINENTS_HELP,5\n' not in output or '\nSCRIPT_CATALOG_COUNT=36\n' not in output:
            raise RuntimeError('Host did not load actual Continents and its nested script dependencies')
        session=Path(re.search(r'^SESSION_DIRECTORY=(.+)$',output,re.M)[1].strip())
        if session.parent!=stage/'sessions' or not session.is_dir():raise RuntimeError('Host cache is not isolated')
        if digest(session/'rules.db')!=before[str(stage/'rules.db')]:raise RuntimeError('Data check mutated rules')
        if (session/'Civ5SavedGameDatabase.db').exists():raise RuntimeError('Unexpected GameCore startup cache')
        data_runs.append({'language':language,'rule_counts':counts,'sample_text':expected_text,'audio_counts':audio_counts,'missing_audio_tags':missing_tags,
                          'script_observation':script_observation,'session_rules':artifact(session/'rules.db')})
    execute('invalid_language',exe,['--check-data','no_such_language'],1,'HOST_CLEANUP_PASS')
    # All malformed bundles are separate copies. No loaded code file is modified.
    invalid=PROJECT/'Build/Host/validation'/uuid.uuid4().hex;invalid.mkdir(parents=True)
    for row in bundle['files']:shutil.copy2(row['path'],invalid/Path(row['path']).name)
    manifest=invalid/'bundle.manifest';original=(stage/'bundle.manifest').read_text();lines=original.splitlines()
    cases={
        'manifest_version':('ZEROSIS_HOST_BUNDLE_V1\n'+'\n'.join(lines[1:])+'\n','Invalid bundle manifest version'),
        'manifest_v2':('ZEROSIS_HOST_BUNDLE_V2\n'+'\n'.join(lines[1:])+'\n','Invalid bundle manifest version'),
        'manifest_duplicate':(original+lines[1]+'\n','Unexpected, duplicate or invalid'),
        'manifest_path':(original+'../rules.db|'+'0'*64+'\n','Unexpected, duplicate or invalid'),
        'manifest_missing':('\n'.join(l for l in lines if not l.startswith('rules.db|'))+'\n','Bundle manifest is incomplete'),
        'manifest_missing_script':('\n'.join(l for l in lines if not l.startswith('script-catalog.bin|'))+'\n','Bundle manifest is incomplete'),
        'manifest_hash':(original.replace('rules.db|'+before[str(stage/'rules.db')],'rules.db|'+'0'*64),'Bundle hash differs: rules.db'),
        'manifest_bad_hash':(original.replace('rules.db|'+before[str(stage/'rules.db')],'rules.db|INVALID'),'Unexpected, duplicate or invalid'),
        'manifest_format':(original+'invalid-line\n','Invalid bundle manifest entry'),
        'manifest_size':('A'*16385,'Bundle manifest is too large')}
    for name,(text,marker) in cases.items():
        manifest.write_text(text,encoding='ascii')
        execute(name,invalid/exe.name,['--verify-bundle'],1,marker)
    core=invalid/'CvGameCoreDLL_Expansion2_x64.dll';raw=core.read_bytes();offset=int.from_bytes(raw[60:64],'little')
    for name,index,value,marker in [('pe_architecture',offset+4,b'\x4c\x01','not AMD64 PE32+'),
                                   ('pe_kind',offset+23,bytes([raw[offset+23]&~0x20]),'EXE/DLL kind differs')]:
        data=bytearray(raw);data[index:index+len(value)]=value;core.write_bytes(data)
        text=original.replace(before[str(stage/core.name)],digest(core));manifest.write_text(text,encoding='ascii')
        execute(name,invalid/exe.name,['--verify-bundle'],1,marker)
    core.write_bytes(raw);manifest.write_text(original,encoding='ascii')
    catalog=invalid/'audio-catalog.bin';catalog_raw=catalog.read_bytes();catalog.write_bytes(b'X'+catalog_raw[1:])
    manifest.write_text(original.replace(before[str(stage/catalog.name)],digest(catalog)),encoding='ascii')
    output=execute('invalid_catalog_data',invalid/exe.name,['--check-data','en_US'],1,'HOST_CLEANUP_PASS')
    if 'Invalid audio catalog version' not in output:raise RuntimeError('Catalog failure did not reach the data lifecycle')
    catalog.write_bytes(catalog_raw);manifest.write_text(original,encoding='ascii')
    catalog=invalid/'script-catalog.bin';catalog_raw=catalog.read_bytes();catalog.write_bytes(b'X'+catalog_raw[1:])
    manifest.write_text(original.replace(before[str(stage/catalog.name)],digest(catalog)),encoding='ascii')
    output=execute('invalid_script_catalog_data',invalid/exe.name,['--check-data','en_US'],1,'HOST_CLEANUP_PASS')
    if 'Invalid script catalog version' not in output:raise RuntimeError('Script catalog failure did not reach the data lifecycle')
    catalog.write_bytes(catalog_raw);manifest.write_text(original,encoding='ascii')
    if any(digest(Path(path))!=sha for path,sha in before.items()):raise RuntimeError('Staged inputs changed during host verification')
    check_artifacts(build)
    report={'status':'NATIVE_HOST_COMPONENT_AND_DATA_PASS','build':artifact(bp),'bundle':artifact(bundle_path),
            'verifier':artifact(Path(__file__).resolve()),'native_checks':assertions+map_audio_checks+script_checks+asset_checks,'lifecycle_native_checks':assertions,
            'map_audio_native_checks':map_audio_checks,'runs':runs,'data_observations':data_runs,'audio_catalog':artifact(root/'audio_catalog.json'),
            'script_native_checks':script_checks,'script_lifecycle_with_instrumented_core':script_lifecycle,
            'script_allocation_failures':{'cpp':cpp_failures,'lua_create':lua_create_failures,'lua_execute':lua_execute_failures,'lua_event':lua_event_failures},
            'script_foreign_thread_rejections':160,'script_restart_cycles':32,
            'real_lua_provider_executed':True,'game_script_libraries_registered':False,'original_event_semantics_verified':False,
            'script_asset_native_checks':asset_checks,'script_asset_failures':asset_failures,'script_catalog_files':script_files,
            'map_script_metadata':map_metadata,'script_catalog':artifact(root/'script_catalog.json'),'script_catalog_malformed_cases':malformed_scripts,
            'script_utility_binding_compiled':True,'script_utility_registration_with_fixture':True,'script_utility_binding_failure_cases':3,
            'startup_failure_boundaries':16,'cleanup_retry_cases':12,'concurrent_busy_calls':512,'reentrant_boundaries':28,
            'restart_cycles':64,'concurrent_service_operations':1024,'malformed_bundle_cases':14,
            'map_allocation_failures':2,'catalog_allocation_failures':allocation_failures,'malformed_catalog_cases':malformed_catalog_cases,
            'map_resizes':128,'concurrent_map_reads':4096,'concurrent_audio_lookups':8192,
            'bundle_inputs_unchanged':True,'read_only_modes_created_no_sessions':True,'real_database_localization_executed':True,
            'gamecore_lifecycle_instrumented':True,'gamecore_loaded':False,'game_launched':False,'game_multicore_verified':False,
            'scope':'REAL_HOST_ADAPTERS_SESSION_DATA_AND_MANIFEST_WITH_FAKE_GAMECORE; REAL_GAMECORE_INITIALIZATION_NOT_RUN'}
    report['script_access_conformance']=artifact(PROJECT/'evidence/host_script_access/conformance.json')
    report['script_access_native_checks']=script_access['native_checks']
    report['script_access_process_runs']=len(script_access['runs'])
    report['game_info_conformance']=artifact(PROJECT/'evidence/host_game_info/conformance.json')
    report['game_info_native_checks']=game_info['native_checks']
    (root/'conformance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'native_checks':report['native_checks'],'process_runs':len(runs),
                      'audio_counts':data_runs[0]['audio_counts'],'missing_audio_tags':data_runs[0]['missing_audio_tags']},ensure_ascii=False))


if __name__=='__main__':main()
