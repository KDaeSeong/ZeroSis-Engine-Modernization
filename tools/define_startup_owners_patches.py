"""Close directly owned player/team/action allocation gaps before GC rollback integration."""
import json
import re
from pathlib import Path
from collect_baseline import PROJECT, digest
from build_bootstrap_component import body

PREFIX='startup_owners_'
BASE=PROJECT/'evidence/sdk_x64/attempts/attempt_030/sdk_x64_patches.json'
PLAYER='CvGameCoreDLL_Expansion2/CvPlayer.cpp'
PLAYER_AI='CvGameCoreDLL_Expansion2/CvPlayerAI.cpp'
TEAM='CvGameCoreDLL_Expansion2/CvTeam.cpp'
UTILITY='CvGameCoreDLL_Expansion2/CvDllDatabaseUtility.cpp'


def baseline_text(relative):
    text=(PROJECT/'Source/SDK_BNW_Original'/relative).read_bytes().decode('latin1')
    for p in json.loads(BASE.read_text(encoding='utf-8'))['patches']:
        if p['file']==relative:
            if text.count(p['old'])!=p['count']: raise RuntimeError('Startup owner baseline drift: '+p['id'])
            text=text.replace(p['old'],p['new'])
    return text


def player_owners():
    text=body(baseline_text(PLAYER),'CvPlayer::CvPlayer()')
    rows=re.findall(r'\t(m_p\w+) = (FNEW\((\w+)(?:\([^\r\n]+?\))?, c_eCiv5GameplayDLL, 0\));',text)
    if len(rows)!=26 or len({r[0] for r in rows})!=26: raise RuntimeError('Expected twenty-six direct player child owners')
    return rows


def patches():
    rows=[]
    def add(name,relative,old,new,reason):
        text=baseline_text(relative)
        if text.count(old)!=1: raise RuntimeError('Startup owner patch mismatch: '+name)
        new=new.replace('\r\n','\n')
        if '\r\n' in text:new=new.replace('\n','\r\n')
        rows.append({'id':PREFIX+name,'file':relative,'source_sha256':digest(PROJECT/'Source/SDK_BNW_Original'/relative),
                     'old':old,'new':new,'count':1,'reason':reason})
    add('player_memory',PLAYER,'#include <sstream>','#include <sstream>\n#include <memory>',
        'Use scoped local child owners without changing CvPlayer member layout.')
    old=body(baseline_text(PLAYER),'CvPlayer::CvPlayer()');new=old.replace('\r\n','\n')
    for field,allocation,kind in player_owners():
        new=new.replace(field+' = '+allocation+';', 'std::unique_ptr<'+kind+'> owned_'+field+'('+allocation+');\n\t'+field+' = owned_'+field+'.get();')
    end='\treset(NO_PLAYER, true);'
    new=new.replace(end,end+'\n\n\t// Every direct child remains scoped through constructor reset.\n'+'\n'.join('\towned_'+field+'.release();' for field,_,_ in player_owners()))
    add('player_partial_construction',PLAYER,old,new,
        'Release all successfully constructed direct children if a later child or constructor reset throws; retain normal publication order and pointers.')
    old=body(baseline_text(PLAYER),'CvPlayer::~CvPlayer()')
    add('player_culture_teardown',PLAYER,old,old[:-1]+'\tSAFE_DELETE(m_pCulture);\n}',
        'Release the twenty-sixth owned child after existing player teardown; culture had no delete in the original destructor or uninit.')
    add('team_includes',TEAM,'#include "CvGameCoreDLLPCH.h"','#include "CvGameCoreDLLPCH.h"\n#include <memory>\n#include <stdexcept>',
        'Declare scoped team child ownership and duplicate static initialization failure.')
    old=body(baseline_text(TEAM),'CvTeam::CvTeam()');new=old.replace('\r\n','\n')
    new=new.replace('m_pTeamTechs = FNEW(CvTeamTechs, c_eCiv5GameplayDLL, 0);',
        'std::unique_ptr<CvTeamTechs> ownedTeamTechs(FNEW(CvTeamTechs, c_eCiv5GameplayDLL, 0));\n\tm_pTeamTechs = ownedTeamTechs.get();')
    new=new.replace('\treset((TeamTypes)0, true);','\treset((TeamTypes)0, true);\n\townedTeamTechs.release();')
    add('team_partial_construction',TEAM,old,new,'Keep the directly owned team-tech object scoped until constructor reset succeeds.')
    add('player_statics_include',PLAYER_AI,'#include "CvGameCoreDLLPCH.h"','#include "CvGameCoreDLLPCH.h"\n#include <stdexcept>',
        'Report duplicate static initialization explicitly instead of overwriting the live array.')
    for relative,kind,field in ((PLAYER_AI,'CvPlayerAI','m_aPlayers'),(TEAM,'CvTeam','m_aTeams')):
        old=body(baseline_text(relative),'void '+kind+'::initStatics()')
        new=old.replace('{','{\n\tif('+field+' != NULL) throw std::logic_error("'+kind+' static array is already initialized");',1)
        add(kind.lower()+'_duplicate_statics',relative,old,new,
            'Reject duplicate initialization before allocation so an existing complete static array cannot be leaked or replaced.')
    old=body(baseline_text(UTILITY),'bool CvDllDatabaseUtility::SetGlobalActionInfo()');new=old.replace('\r\n','\n')
    start=new.index('\tint iEstimatedNumActionInfos =');end=new.index('\n\tint* piBuffer =',start)
    new=new[:start]+'''\tconst int counts[] = { NUM_INTERFACEMODE_TYPES, GC.getNumBuildInfos(), GC.getNumPromotionInfos(),
        GC.getNumSpecialistInfos(), NUM_CONTROL_TYPES, NUM_COMMAND_TYPES, GC.getNumAutomateInfos(), iNumMissionTypes };
    int iEstimatedNumActionInfos = 0;
    for(size_t countIndex = 0; countIndex < sizeof(counts) / sizeof(counts[0]); ++countIndex)
    {
        // The original buffer offsets and multiplier use signed int arithmetic.
        if(counts[countIndex] < 0 || counts[countIndex] > 2147483647 / 4 - iEstimatedNumActionInfos) return false;
        iEstimatedNumActionInfos += counts[countIndex];
    }
''' + new[end:]
    new=new.replace('int* piBuffer = FNEW(int[iEstimatedNumActionInfos * 4], c_eCiv5GameplayDLL, 0);',
        'std::unique_ptr<int[]> ownedBuffer(FNEW(int[iEstimatedNumActionInfos * 4], c_eCiv5GameplayDLL, 0));\n\tint* piBuffer = ownedBuffer.get();')
    new=new.replace('CvActionInfo* pActionInfo = FNEW(CvActionInfo, c_eCiv5GameplayDLL, 0);',
        'std::unique_ptr<CvActionInfo> ownedAction(FNEW(CvActionInfo, c_eCiv5GameplayDLL, 0));\n\t\tCvActionInfo* pActionInfo = ownedAction.get();')
    new=new.replace('GC.getActionInfo().push_back(pActionInfo);','GC.getActionInfo().push_back(pActionInfo);\n\t\townedAction.release();')
    new=new.replace('\tSAFE_DELETE_ARRAY(piBuffer);','\t// ownedBuffer also releases storage on every exceptional exit.')
    add('action_buffer_and_unpublished_entry',UTILITY,old,new,
        'Check signed buffer arithmetic and scope sorting storage plus the unpublished action across allocation, sorting, metadata/hotkey and publication failures.')
    return rows


def main():
    path=PROJECT/'Source/Porting/sdk_x64_patches.json'
    plan,base=(json.loads(p.read_text(encoding='utf-8')) for p in (path,BASE))
    retained=[p for p in plan['patches'] if not p['id'].startswith((PREFIX,'gc_lifecycle_', 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))]
    later=[p for p in plan['patches'] if p['id'].startswith(('gc_lifecycle_', 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))]
    if retained!=base['patches'] or len(retained)!=579:raise RuntimeError('Accepted 579 SDK patches changed')
    added=patches();plan['patches']=retained+added+later
    path.write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lp=PROJECT/'evidence/numeric_boundaries/edit_ledger.json';ledger=json.loads(lp.read_text(encoding='utf-8'))
    ledger['patch_specification_sha256']=digest(path)
    ledger['supplemental_non_numeric_patches']=[x for x in ledger['supplemental_non_numeric_patches'] if not x.startswith((PREFIX,'gc_lifecycle_', 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))]+[p['id'] for p in added+later]
    ledger['unchanged_startup_owners_baseline']={'path':str(BASE),'sha256':digest(BASE)}
    lp.write_text(json.dumps(ledger,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    root=PROJECT/'evidence/startup_owners';root.mkdir(parents=True,exist_ok=True)
    report={'status':'SDK_STARTUP_OWNERS_DECLARED','baseline':ledger['unchanged_startup_owners_baseline'],
            'recipe':{'path':str(Path(__file__).resolve()),'sha256':digest(Path(__file__).resolve())},
            'patch_specification':{'path':str(path),'sha256':digest(path)},'previous_patches':579,
            'added_patches':len(added),'total_patches':len(plan['patches']),'files':sorted({p['file'] for p in added}),
            'patches':added,'gamecore_loaded':False,'game_launched':False}
    (root/'caller_patch_plan.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('status','added_patches','total_patches')}))


if __name__=='__main__':main()
