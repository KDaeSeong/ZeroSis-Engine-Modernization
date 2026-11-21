"""Preserve installed scripts and compile an explicit BNW asset selection; no Lua/GameCore execution."""
import json,re,shutil,struct
from pathlib import Path
from collect_baseline import PROJECT,digest
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts

GAME=Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V")
LAYERS=(('Assets/Maps','maps'),('Assets/Gameplay/Lua','gameplay/lua'),
        ('Assets/DLC/Expansion/Gameplay/Lua','gameplay/lua'),('Assets/DLC/Expansion2/Gameplay/Lua','gameplay/lua'))


def encode(rows):
    active={};overrides=[]
    for row in rows:
        key=row['virtual_path']
        if key in active:overrides.append({'virtual_path':key,'previous':active[key]['origin'],'selected':row['origin']})
        active[key]=row
    binary=bytearray(b'ZSSCRIP1'+struct.pack('<I',len(active)));records=[]
    for key,row in sorted(active.items()):
        contents=Path(row['snapshot']['path']).read_bytes()
        for value in (key.encode('utf-8'),row['origin'].lower().encode('utf-8'),contents):binary+=struct.pack('<I',len(value))+value
        includes=re.findall(r'\binclude\s*\(\s*[\"\']([^\"\']+)',contents.decode('latin1'))
        records.append({'virtual_path':key,'origin':row['origin'].lower(),'bytes':len(contents),'sha256':row['snapshot']['sha256'],
                        'snapshot':row['snapshot'],'includes':includes})
    return bytes(binary),records,overrides


def main():
    rows=[];snapshots=PROJECT/'Source/Assets/Scripts'
    for priority,(relative,virtual) in enumerate(LAYERS):
        sources=sorted((GAME/relative).glob('*.lua'))
        if not sources:raise RuntimeError('Installed script layer is empty: '+relative)
        for source in sources:
            target=snapshots/source.relative_to(GAME);sha=digest(source)
            if target.exists() and digest(target)!=sha:raise RuntimeError('Script snapshot/source drift: '+str(target))
            target.parent.mkdir(parents=True,exist_ok=True)
            if not target.exists():shutil.copy2(source,target)
            if digest(source)!=sha or digest(target)!=sha:raise RuntimeError('Script snapshot changed while copying')
            rows.append({'priority':priority,'virtual_path':virtual+'/'+source.name.lower(),'origin':source.relative_to(GAME).as_posix(),
                         'original':artifact(source),'snapshot':artifact(target)})
    binary,records,overrides=encode(rows);catalog=PROJECT/'Build/Host/Resources/script-catalog.bin';catalog.parent.mkdir(parents=True,exist_ok=True)
    catalog.write_bytes(binary);check_artifacts(rows)
    names={Path(r['virtual_path']).name for r in records};unresolved=[]
    for row in records:
        for name in row['includes']:
            key=name.lower();key=key if key.endswith('.lua') else key+'.lua'
            if key not in names:unresolved.append({'source':row['virtual_path'],'include':name})
    report={'status':'INSTALLED_BNW_SCRIPT_CATALOG_COMPILED','builder':artifact(Path(__file__).resolve()),'layers':LAYERS,
            'inputs':rows,'records':records,'overrides':overrides,'catalog':artifact(catalog),'unresolved_literal_includes':unresolved,
            'scope':'BASE_MAPS_AND_EXPLICIT_BASE_EXPANSION_EXPANSION2_GAMEPLAY_PRIORITY; NOT_ALL_DLC_OR_MOD_VFS',
            'original_host_search_order_verified':False,'gamecore_loaded':False,'game_launched':False}
    (PROJECT/'evidence/host/script_catalog.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'originals':len(rows),'selected':len(records),'overrides':len(overrides),
                      'catalog_bytes':len(binary),'unresolved_includes':unresolved},ensure_ascii=False))


if __name__=='__main__':main()
