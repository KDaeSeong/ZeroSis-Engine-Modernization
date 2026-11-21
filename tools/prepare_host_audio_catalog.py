"""Compile the installed soundscape definitions into an immutable host catalog."""
import copy,json,re,shutil,sqlite3,struct
import xml.etree.ElementTree as ET
from pathlib import Path
from collect_baseline import PROJECT,digest
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts

SOUND_ROOT=Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V\Assets\Sounds\XML")
NAMES=('AudioSoundscapeScripts.xml','Audio2DScripts.xml','AudioDefines.xml')


def encode(snapshots):
    roots=[ET.parse(path).getroot() for path in snapshots]
    scapes=roots[0].findall('./ScriptSoundscapes/ScriptSoundscape')
    def index(nodes,key):
        output={}
        for node in nodes:
            name=node.findtext(key)
            if not name or name in output:raise RuntimeError('Empty/duplicate audio definition: '+str(name))
            output[name]=node
        return output
    index(scapes,'ScriptID')
    scripts=index(roots[1].findall('./Script2DSounds/Script2DSound'),'ScriptID')
    sounds=index(roots[2].findall('./SoundDatas/SoundData'),'SoundID')
    records=[];binary=bytearray(b'ZSAUDIO1'+struct.pack('<I',len(scapes)))
    for number,node in enumerate(scapes):
        tag=node.findtext('ScriptID')
        if not re.fullmatch(r'[A-Za-z0-9_]{1,256}',tag):raise RuntimeError('Unsupported audio tag syntax')
        refs=[]
        for element in node.findall('SoundscapeElement'):
            if element.findtext('ScriptType')!='2D':raise RuntimeError('Soundscape uses an unimplemented script kind')
            refs.extend(child.text for child in element.findall('ScriptID'))
        refs=sorted(set(refs));sound_refs=[]
        document=ET.Element('HostSoundscape');document.append(copy.deepcopy(node))
        linked_scripts=ET.SubElement(document,'Referenced2DScripts');linked_sounds=ET.SubElement(document,'ReferencedSounds')
        for reference in refs:
            if reference not in scripts:raise RuntimeError('Unresolved 2D script '+str(reference))
            linked_scripts.append(copy.deepcopy(scripts[reference]))
            sound_refs.extend(child.text for child in scripts[reference].findall('SoundID'))
        sound_refs=sorted(set(sound_refs))
        for reference in sound_refs:
            if reference not in sounds:raise RuntimeError('Unresolved sound definition '+str(reference))
            linked_sounds.append(copy.deepcopy(sounds[reference]))
        xml=ET.tostring(document,encoding='utf-8');name=tag.encode('ascii')
        for data in (name,xml):binary.extend(struct.pack('<I',len(data))+data)
        records.append({'index':number,'tag':tag,'xml':xml.decode('utf-8'),'scripts':refs,'sounds':sound_refs})
    return bytes(binary),records


def main():
    root=PROJECT/'evidence/host';snapshot_root=PROJECT/'Source/Assets/Audio';snapshot_root.mkdir(parents=True,exist_ok=True)
    inputs=[artifact(SOUND_ROOT/name) for name in NAMES];snapshots=[]
    for row in inputs:
        source=Path(row['path']);target=snapshot_root/source.name
        if target.exists() and digest(target)!=row['sha256']:raise RuntimeError('Local audio snapshot differs from installed source')
        shutil.copy2(source,target);snapshots.append(target)
    binary,records=encode(snapshots)
    out=PROJECT/'Build/Host/Resources/audio-catalog.bin';out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(binary)
    corpus=json.loads((PROJECT/'evidence/database/corpus/conformance.json').read_text())
    rules=next(r['copy'] for r in corpus['copies'] if r['copy']['path'].endswith('Civ5DebugDatabase.db'));check_artifacts(rules)
    with sqlite3.connect(Path(rules['path']).as_uri()+'?mode=ro',uri=True) as db:
        needed=sorted({row[0] for table in ('Improvements','Features','Terrains') for row in db.execute(
            'SELECT WorldSoundscapeAudioScript FROM '+table+" WHERE WorldSoundscapeAudioScript IS NOT NULL AND WorldSoundscapeAudioScript != ''")})
    missing=sorted(set(needed)-{r['tag'] for r in records})
    check_artifacts(inputs)
    report={'status':'HOST_AUDIO_CATALOG_COMPILED_FROM_INSTALLED_XML','generator':artifact(Path(__file__).resolve()),
            'originals':inputs,'snapshots':[artifact(p) for p in snapshots],'catalog':artifact(out),'records':records,
            'rules':rules,'required_rule_tags':needed,'missing_rule_tags':missing,
            'distinct_2d_scripts':len({s for r in records for s in r['scripts']}),
            'distinct_sound_definitions':len({s for r in records for s in r['sounds']}),
            'originals_unchanged':True,'original_numeric_audio_ids_verified':False,'playback_verified':False,'gamecore_loaded':False,
            'scope':'SOUNDSCAPE_NAME_AND_DEFINITION_REGISTRY; LOCAL_IDS_NOT_LEGACY_EXE_ID_EQUIVALENCE_OR_PLAYBACK'}
    (root/'audio_catalog.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'records':len(records),'scripts':report['distinct_2d_scripts'],
                      'sounds':report['distinct_sound_definitions'],'missing_rule_tags':missing}))


if __name__=='__main__':main()
