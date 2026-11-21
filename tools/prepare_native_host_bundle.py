"""Prepare an isolated, pinned-input host bundle without loading GameCore."""
import argparse,json,shutil,sqlite3
from pathlib import Path
from collect_baseline import PROJECT,digest,pe_header
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts


def prepare_shared(new_game_sdk=False):
    root=PROJECT/'evidence/host';runtime_path=PROJECT/'evidence/shared_lua_runtime/build_result.json'
    build_path=root/'shared_build_result.json';runtime=json.loads(runtime_path.read_text(encoding='utf-8'))
    build=json.loads(build_path.read_text(encoding='utf-8'))
    localization_path=PROJECT/'evidence/localization/provider/build_result.json'
    corpus_path=PROJECT/'evidence/database/corpus/conformance.json'
    audio_path=root/'audio_catalog.json';scripts_path=root/'script_catalog.json'
    localization=json.loads(localization_path.read_text(encoding='utf-8'));corpus=json.loads(corpus_path.read_text(encoding='utf-8'))
    audio=json.loads(audio_path.read_text(encoding='utf-8'));scripts=json.loads(scripts_path.read_text(encoding='utf-8'))
    sdk_path=PROJECT/'evidence/new_game_sdk/build_result.json';sdk=json.loads(sdk_path.read_text(encoding='utf-8')) if new_game_sdk else None
    if build.get('profile')!=('shared-lua-new-game-sdk-v4' if sdk else 'shared-lua-v4'):
        raise RuntimeError('Shared host build profile does not match the selected bundle mode')
    if runtime.get('status')!='SHARED_LUA_RUNTIME_CANDIDATE_BUILT':raise RuntimeError('Shared Lua runtime candidate is not ready')
    core=sdk['gamecore'] if sdk else runtime['gamecore']
    if sdk:
        check_artifacts(sdk)
        if sdk.get('status')!='NEW_GAME_SDK_CANDIDATE_LINKED' or sdk.get('shared_lua_build',{}).get('sha256')!=artifact(runtime_path)['sha256']:
            raise RuntimeError('Selected SDK candidate does not match the shared Lua provider')
    db=next(row for row in build['provider_inputs'] if row['path'].endswith('ZeroSisDatabase_x64.dll'))
    language=next(row['copy'] for row in corpus['copies'] if row['copy']['path'].endswith('Localization-Merged.db'))
    rules=next(row['copy'] for row in corpus['copies'] if row['copy']['path'].endswith('Civ5DebugDatabase.db'))
    icu=next(row for row in localization['copies'] if row['path'].endswith('icudt44l.dat'))
    lua=runtime['lua_dll']
    entries={'ZeroSisHost_x64.exe':build['host']['executable'],'CvGameCoreDLL_Expansion2_x64.dll':core,
        'ZeroSisDatabase_x64.dll':db,'ZeroSisLocalization_x64.dll':localization['dll'],'ZeroSisLua51_x64.dll':lua,
        'rules.db':rules,'localization.db':language,'icudt44l.dat':icu,'audio-catalog.bin':audio['catalog'],'script-catalog.bin':scripts['catalog']}
    check_artifacts(list(entries.values()))
    languages=[]
    with sqlite3.connect(Path(language['path']).as_uri()+'?mode=ro',uri=True) as connection:
        languages=[list(row) for row in connection.execute('SELECT Type,TableName FROM Languages ORDER BY ID')]
    destination=PROJECT/'Stage/NativeHost/SharedCandidate';destination.mkdir(parents=True,exist_ok=True)
    report_path=root/'shared_bundle.json';previous=json.loads(report_path.read_text()) if report_path.exists() else {'files':[]}
    known={row['path']:row['sha256'] for row in previous['files']}
    for name,entry in entries.items():
        target=destination/name
        if target.exists() and digest(target) not in (entry['sha256'],known.get(str(target))):raise RuntimeError('Untracked shared bundle edit: '+str(target))
    files=[]
    for name,entry in entries.items():
        source=Path(entry['path']);target=destination/name;shutil.copy2(source,target)
        if digest(target)!=entry['sha256'] or digest(source)!=entry['sha256']:raise RuntimeError('Shared bundle input changed')
        row={'source':str(source),**artifact(target)}
        if target.suffix in ('.dll','.exe'):
            row['pe']=pe_header(target)
            if row['pe']['architecture']!='x64':raise RuntimeError('Non-x64 shared host module')
        files.append(row)
    manifest=destination/'bundle.manifest'
    text='ZEROSIS_HOST_BUNDLE_V4\n'+''.join(name+'|'+entry['sha256']+'\n' for name,entry in entries.items())
    if manifest.exists() and manifest.read_text()!=text and previous.get('manifest',{}).get('sha256')!=digest(manifest):raise RuntimeError('Untracked shared bundle manifest edit')
    manifest.write_text(text,encoding='ascii')
    input_paths=[build_path,runtime_path,localization_path,corpus_path,audio_path,scripts_path]
    if sdk:input_paths.append(sdk_path)
    report={'status':'SHARED_LUA_HOST_BUNDLE_PREPARED_NOT_GAME_EXECUTED','profile':build['profile'],'manifest_version':'ZEROSIS_HOST_BUNDLE_V4',
        'files':files,'manifest':artifact(manifest),'builder':artifact(Path(__file__).resolve()),'inputs':[artifact(path) for path in input_paths],
        'languages':languages,'selected_gamecore_source':'new_game_sdk' if sdk else 'shared_lua_runtime',
        'gamecore_loaded':False,'game_launched':False,'game_multicore_verified':False}
    report_path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'files':len(files),'languages':languages}))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--shared-lua',action='store_true');parser.add_argument('--new-game-sdk',action='store_true')
    args=parser.parse_args()
    if args.new_game_sdk and not args.shared_lua:parser.error('--new-game-sdk requires --shared-lua')
    if args.shared_lua:
        prepare_shared(args.new_game_sdk);return
    root=PROJECT/'evidence/host'
    paths=[root/'build_result.json',PROJECT/'evidence/sdk_x64/link_analysis.json',
           PROJECT/'evidence/localization/provider/build_result.json',PROJECT/'evidence/database/corpus/conformance.json',root/'audio_catalog.json',root/'script_catalog.json']
    build,core,localization,corpus,audio,scripts=[json.loads(p.read_text(encoding='utf-8')) for p in paths]
    check_artifacts(build)
    if core['status']!='X64_LINK_PROBE_SUCCEEDED_UNTESTED' or core['linker_unresolved_symbol_total']!=0:
        raise RuntimeError('Current GameCore link is not ready')
    database=next(r for r in build['provider_inputs'] if r['path'].endswith('ZeroSisDatabase_x64.dll'))
    rules=next(r['copy'] for r in corpus['copies'] if r['copy']['path'].endswith('Civ5DebugDatabase.db'))
    language=next(r['copy'] for r in corpus['copies'] if r['copy']['path'].endswith('Localization-Merged.db'))
    icu=next(r for r in localization['copies'] if r['path'].endswith('icudt44l.dat'))
    entries={'ZeroSisHost_x64.exe':build['host']['executable'],
             'CvGameCoreDLL_Expansion2_x64.dll':core['generated_dll'],
             'ZeroSisDatabase_x64.dll':database,'ZeroSisLocalization_x64.dll':localization['dll'],
             'rules.db':rules,'localization.db':language,'icudt44l.dat':icu,'audio-catalog.bin':audio['catalog'],'script-catalog.bin':scripts['catalog']}
    check_artifacts(list(entries.values()))
    languages=[]
    with sqlite3.connect(Path(language['path']).as_uri()+'?mode=ro',uri=True) as connection:
        languages=[list(r) for r in connection.execute('SELECT Type,TableName FROM Languages ORDER BY ID')]
    destination=PROJECT/'Stage/NativeHost';destination.mkdir(parents=True,exist_ok=True)
    report_path=root/'bundle.json'
    previous=json.loads(report_path.read_text()) if report_path.exists() else {'files':[]}
    known={r['path']:r['sha256'] for r in previous['files']}
    for name,entry in entries.items():
        target=destination/name
        if target.exists() and digest(target) not in (entry['sha256'],known.get(str(target))):
            raise RuntimeError('Untracked host bundle edit: '+str(target))
    files=[]
    for name,entry in entries.items():
        source=Path(entry['path']);target=destination/name
        shutil.copy2(source,target)
        if digest(target)!=entry['sha256'] or digest(source)!=entry['sha256']:raise RuntimeError('Host bundle input changed')
        row={'source':str(source),**artifact(target)}
        if target.suffix in ('.dll','.exe'):
            row['pe']=pe_header(target)
            if row['pe']['architecture']!='x64':raise RuntimeError('Non-x64 host module')
        files.append(row)
    manifest=destination/'bundle.manifest'
    text='ZEROSIS_HOST_BUNDLE_V3\n'+''.join(name+'|'+entry['sha256']+'\n' for name,entry in entries.items())
    if manifest.exists() and manifest.read_text()!=text and previous.get('manifest',{}).get('sha256')!=digest(manifest):
        raise RuntimeError('Untracked bundle manifest edit')
    manifest.write_text(text,encoding='ascii')
    report={'status':'NATIVE_HOST_BUNDLE_PREPARED_NOT_GAME_EXECUTED','files':files,'manifest':artifact(manifest),
            'builder':artifact(Path(__file__).resolve()),'inputs':[artifact(p) for p in paths],
            'languages':languages,'rules_source':'Previously verified BNW debug cache snapshot; not a newly assembled mod database',
            'gamecore_loaded':False,'game_launched':False,'game_multicore_verified':False}
    report_path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'files':len(files),'languages':languages}))


if __name__=='__main__':main()
