"""Prepare an isolated, pinned-input host bundle without loading GameCore."""
import json,shutil,sqlite3
from pathlib import Path
from collect_baseline import PROJECT,digest,pe_header
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts


def main():
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
