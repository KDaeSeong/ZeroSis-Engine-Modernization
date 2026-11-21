"""Identify concrete startup service gaps without loading the GameCore DLL."""
import json,re,sqlite3
from collections import Counter
from pathlib import Path
from collect_baseline import PROJECT
from probe_world_builder import artifact
from build_bootstrap_component import body
from native_host_evidence import validate


def main():
    _,_,bundle,services=validate();sdk=PROJECT/'Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2'
    implemented={m['name'] for m in services[0]['methods'] if m['implemented']}
    signatures={'CvGlobals.cpp':['void CvGlobals::init()','void CvGlobals::uninit()'],
                'CvGame.cpp':['void CvGame::reset(','void CvGame::uninit()'],
                'CvMap.cpp':['CvMap::CvMap()','void CvMap::reset(','void CvMap::uninit()'],
                'CvPlayer.cpp':['void CvPlayer::reset(','void CvPlayer::uninit()'],
                'CvTeam.cpp':['void CvTeam::reset(','void CvTeam::uninit()'],
                'CvImprovementClasses.cpp':['bool CvImprovementEntry::CacheResults('],
                'CvInfos.cpp':['bool CvFeatureInfo::CacheResults(','bool CvTerrainInfo::CacheResults(']}
    functions=[]
    for name,wanted in signatures.items():
        path=sdk/name;text=path.read_bytes().decode('latin1')
        for signature in wanted:
            code=body(text,signature)
            calls=sorted(set(re.findall(r'\bgDLL\s*->\s*(\w+)\s*\(',code)))
            functions.append({'source':artifact(path),'signature':signature,'line':text.count('\n',0,text.index(signature))+1,
                              'engine_calls':[{'method':m,'implemented':m in implemented} for m in calls],
                              'body':code.replace('\r\n','\n')})
    rules=next(r for r in bundle['files'] if Path(r['path']).name=='rules.db')
    audio=[]
    with sqlite3.connect(Path(rules['path']).as_uri()+'?mode=ro',uri=True) as db:
        for table in ('Improvements','Features','Terrains'):
            for name,script in db.execute('SELECT Type,WorldSoundscapeAudioScript FROM '+table+' WHERE WorldSoundscapeAudioScript IS NOT NULL'):
                audio.append({'table':table,'type':name,'soundscape':script})
    sites=[]
    for path in sorted(sdk.glob('*.cpp')):
        text=path.read_bytes().decode('latin1')
        # Preserve line offsets while excluding comments. This is still lexical, not reachability analysis.
        text=re.sub(r'/\*.*?\*/|//[^\r\n]*',lambda m:'\n'*m[0].count('\n'),text,flags=re.S)
        for line_number,line in enumerate(text.split('\n'),1):
            for method in re.findall(r'\bgDLL\s*->\s*(\w+)\s*\(',line):
                if method not in implemented:sites.append({'file':str(path),'line':line_number,'method':method,'text':line.strip()})
    counts=Counter(row['method'] for row in sites)
    report={'status':'NATIVE_HOST_STARTUP_GAPS_IDENTIFIED_STATIC_ONLY','auditor':artifact(Path(__file__).resolve()),
            'services':artifact(PROJECT/'evidence/host/services.json'),'rules':rules,'functions':functions,
            'findings':[
                {'id':'HOST-SCRIPT-SYSTEM','method':'GetScriptSystem','implemented':True,
                 'evidence':'The host returns a real Lua 5.1 x64 service implementing the 13 frozen SDK methods; actual Lua calls, argument/event propagation, allocation failures and finalizer ordering are executed without loading GameCore.',
                 'impact':'Script service lookup, the production utility binding and the selected installed map/gameplay asset catalog are connected. Eighteen actual map metadata scripts execute without GameCore; actual game library registration is untested.',
                 'next_action':'Resolve the SDK enum registration error boundaries, execute actual registration after authorization, extend selected assets to active mods/UI and compare legacy event/VM semantics.'},
                {'id':'HOST-MAP-SETUP','method':'DoMapSetup','implemented':True,'evidence':'CvMap constructor calls reset; reset unconditionally calls DoMapSetup(numPlots()). The host now allocates and publishes a generation-tagged map presentation snapshot.',
                 'impact':'The callback now prepares real host state; allocation failure preserves the prior snapshot and owner/lifecycle violations are rejected.',
                 'next_action':'Verify the real GameCore call after loading authorization; integrate map presentation consumers and later rendering.'},
                {'id':'HOST-AUDIO-REGISTRY','method':'GetAudioTagIndex','evidence':'Concrete feature/terrain CacheResults paths request non-null soundscape tags present in the verified rules snapshot.',
                 'implemented':True,'impact':'The host now resolves local catalog IDs to ten installed soundscape definitions and their 33 script/sound dependencies. Unsupported kinds remain explicit.',
                 'next_action':'Connect actual audio playback and verify lifecycle/runtime semantics; do not claim equality with legacy numeric audio IDs.'},
                {'id':'HOST-AUDIO-MISSING-TUNDRA','method':'GetAudioTagIndex','implemented':True,
                 'evidence':'ASSS_AMBIENCE_TUNDRA is referenced by the rules but absent from installed soundscape definitions.',
                 'impact':'The host returns -1 and records the missing name; seven of eight distinct rules tags resolve.',
                 'next_action':'Compare the original host missing-tag behavior when authorized; preserve the absence rather than inventing an audio alias.'}],
            'host_map_audio_conformance':artifact(PROJECT/'evidence/host/conformance.json'),
            'audio_rows':audio,'distinct_soundscapes':sorted({r['soundscape'] for r in audio}),
            'unimplemented_direct_call_counts':dict(sorted(counts.items())), 'unimplemented_direct_call_sites':sites,
            'scope':'SELECTED_EXACT_STARTUP_BODIES_RULES_ROWS_AND_LEXICAL_DIRECT_CALLS_NOT_COMPLETE_REACHABILITY_OR_RUNTIME',
            'gamecore_loaded':False,'game_launched':False}
    (PROJECT/'evidence/host/startup_services.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'functions':len(functions),'distinct_soundscapes':len(report['distinct_soundscapes']),
                      'unimplemented_methods_with_direct_call_sites':len(counts),'direct_call_sites':len(sites)}))


if __name__=='__main__':main()
