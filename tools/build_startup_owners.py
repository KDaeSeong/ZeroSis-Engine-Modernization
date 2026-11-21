"""Build isolated exact startup ownership bodies; member/child/game services are instrumented."""
import json
import re
from pathlib import Path
from collect_baseline import PROJECT
from native_build import build_program,environment_for,checked_run
from probe_world_builder import artifact
from build_bootstrap_component import body
from define_startup_owners_patches import BASE,PLAYER,PLAYER_AI,TEAM,UTILITY,baseline_text,patches,player_owners

SIGNATURES={PLAYER:('CvPlayer::CvPlayer()','CvPlayer::~CvPlayer()'),
            PLAYER_AI:('void CvPlayerAI::initStatics()','void CvPlayerAI::freeStatics()','CvPlayerAI::CvPlayerAI()','CvPlayerAI::~CvPlayerAI()'),
            TEAM:('CvTeam::CvTeam()','CvTeam::~CvTeam()','void CvTeam::initStatics()','void CvTeam::freeStatics()'),
            UTILITY:('struct OrderIndex','bool sortHotkeyPriority(',
                     'void CvDllDatabaseUtility::orderHotkeyInfo(int** ppiSortedIndex, int* pHotkeyIndex, int iLength)',
                     'bool CvDllDatabaseUtility::SetGlobalActionInfo()')}


def projected_body(text,signature):
    value=body(text,signature)
    if signature=='CvPlayer::CvPlayer()':value=signature+'\n'+value[value.index('{'):]
    return value.replace('\r\n','\n')


def fixtures():
    original={rel:baseline_text(rel) for rel in SIGNATURES};candidate=dict(original)
    for p in patches():candidate[p['file']]=candidate[p['file']].replace(p['old'],p['new'])
    plan=json.loads((PROJECT/'Source/Porting/sdk_x64_patches.json').read_text(encoding='utf-8'))
    for patch in plan['patches']:
        if patch['id'].startswith('lua_borrowed_') and patch['file'] in candidate:
            if candidate[patch['file']].count(patch['old'])!=patch['count']:
                raise RuntimeError('Borrowed/startup fixture context changed: '+patch['id'])
            candidate[patch['file']]=candidate[patch['file']].replace(patch['old'],patch['new'])
    def functions(sources):
        result='namespace Actors {\n'
        for rel,sigs in SIGNATURES.items():
            if rel==UTILITY:continue
            result+='\n'.join(projected_body(sources[rel],sig) for sig in sigs)+'\n'
        result+='}\nnamespace Actions {\n'
        result+='\n'.join(projected_body(sources[UTILITY],sig)+(';' if sig=='struct OrderIndex' else '') for sig in SIGNATURES[UTILITY])
        return result+'\n}\n'
    fields='#define PLAYER_OWNERS(X) '+' '.join('X('+field+', '+kind+', '+str(i)+')' for i,(field,_,kind) in enumerate(player_owners()))+'\n'
    nulls=re.findall(r'\t(m_\w+) = NULL;',body(original[TEAM],'CvTeam::CvTeam()'))
    fields+='#define TEAM_NULL_FIELDS(X) '+' '.join('X('+f+')' for f in nulls)+'\n'
    defines=baseline_text('CvGameCoreDLLUtil/include/CvDLLUtilDefines.h')
    fields+='\n'.join(line for line in defines.splitlines() if re.match(r'#define\s+(?:REALLY_MAX_TEAMS|MAX_CIV_PLAYERS|MAX_PLAYERS)\s',line))+'\n'
    return {'startup_owners_fields.h':fields,'startup_owners_fixture.h':'#ifdef STARTUP_OWNERS_ORIGINAL\n'+functions(original)+'\n#else\n'+functions(candidate)+'\n#endif\n'}


def main():
    out=PROJECT/'Build/StartupOwners/x64';root=PROJECT/'evidence/startup_owners'
    out.mkdir(parents=True,exist_ok=True);root.mkdir(parents=True,exist_ok=True)
    headers=[]
    for name,text in fixtures().items():
        p=out/name;p.write_text(text,encoding='utf-8',newline='\n');headers.append(artifact(p))
    vs=Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community');builds={}
    for name,defines in (('original',('STARTUP_OWNERS_ORIGINAL',)),('candidate',())):
        directory=out/name
        built=build_program(name='startup_owners_'+name,architecture='x64',vs=vs,directory=directory,
                            evidence=root,source=PROJECT/'Tests/sdk_startup_owners.cpp',
                            includes=(out,PROJECT/'Source/LuaBorrowed',PROJECT/'Source/SDK_BNW_x64/ThirdPartyLibs/Lua51/include'),
                            defines=(*defines,'NOMINMAX'),runtime='/MD')
        env,compiler=environment_for(vs,'x64',directory)
        result=checked_run([Path(compiler).with_name('dumpbin.exe'),'/dependents',built['path']],cwd=directory,env=env)
        log=root/(name+'_imports.log');log.write_bytes(result.stdout+result.stderr)
        deps=re.findall(r'^\s+([\w.-]+\.dll)\s*$',result.stdout.decode('ascii',errors='replace'),re.M|re.I)
        allowed={'kernel32.dll','msvcp140.dll','vcruntime140.dll','vcruntime140_1.dll'}
        if not deps or any(d.lower() not in allowed and not d.lower().startswith('api-ms-win-crt-') for d in deps):raise RuntimeError('Unexpected startup owner dependency')
        builds[name]={'executable':built,'imports':{'dependencies':deps,'log':artifact(log)}}
    sources=['Tests/sdk_startup_owners.cpp','tools/define_startup_owners_patches.py','tools/build_bootstrap_component.py','tools/native_build.py',
             'Source/LuaBorrowed/ZeroSisLuaBorrowed.h']
    sources += [p.relative_to(PROJECT).as_posix() for p in sorted((PROJECT/'Source/SDK_BNW_x64/ThirdPartyLibs/Lua51/include').glob('*.h*'))]
    sources+=['Source/SDK_BNW_Original/'+name for name in (*SIGNATURES,'CvGameCoreDLLUtil/include/CvDLLUtilDefines.h')]
    report={'status':'STARTUP_OWNERS_COMPONENTS_BUILT','builds':builds,'fixtures':headers,
            'sources':[artifact(PROJECT/p) for p in sources],'baseline':artifact(BASE),'builder':artifact(Path(__file__).resolve()),
            'player_member_initializer_list_executed':False,'child_types_reset_and_hotkey_services_instrumented':True,
            'gamecore_loaded':False,'game_launched':False,
            'scope':'EXACT_PLAYER_CONSTRUCTOR_BODY_TEAM_CTORS_DTORS_STATIC_ARRAYS_AND_ACTION_BUILD_SORT_WITH_INSTRUMENTED_DEPENDENCIES'}
    (root/'build_result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(report['status'])


if __name__=='__main__':main()
