"""Specify Lua-owned Fractal type/lifetime boundaries on the accepted attempt_034."""
import argparse
import json
from pathlib import Path
from collect_baseline import PROJECT, digest
from build_bootstrap_component import body

PREFIX='lua_fractal_'
BASE=PROJECT/'evidence/sdk_x64/attempts/attempt_034/sdk_x64_patches.json'
SOURCE='CvGameCoreDLL_Expansion2/Lua/CvLuaFractal.cpp'
SIGNATURES=('CvFractal* CvLuaFractal::CreateFractal(', 'int CvLuaFractal::lDestroy(',
    'int CvLuaFractal::lGetHeight(', 'int CvLuaFractal::lBuildRidges(', 'int CvLuaFractal::lCreateRifts(')


def baseline_text():
    text=(PROJECT/'Source/SDK_BNW_Original'/SOURCE).read_bytes().decode('latin1')
    for p in json.loads(BASE.read_text(encoding='utf-8'))['patches']:
        if p['file']==SOURCE:
            if text.count(p['old'])!=p['count']:raise RuntimeError('Fractal baseline changed: '+p['id'])
            text=text.replace(p['old'],p['new'])
    return text


def patches():
    original=baseline_text();result=[]
    def add(name,old,new,reason):
        new=new.replace('\r\n','\n').replace('\n','\r\n' if '\r\n' in original else '\n')
        if original.count(old)!=1:raise RuntimeError('Fractal patch context changed: '+name)
        result.append({'id':PREFIX+name,'file':SOURCE,'source_sha256':digest(PROJECT/'Source/SDK_BNW_Original'/SOURCE),
            'old':old,'new':new,'count':1,'reason':reason})
    include='#include "..\\CvFractal.h"'
    add('ownership_include',include,include+'\n#include "ZeroSisLuaFractal.h"',
        'Declare private VM provenance and constructed state without changing CvFractal ABI or save data.')
    add('prepare_lua_before_native',body(original,SIGNATURES[0]),'''CvFractal* CvLuaFractal::CreateFractal(lua_State* L)
{
    return ZeroSisLuaFractal::Create<CvFractal>(L, lGetHeight, lBuildRidges, lDestroy);
}''','Complete allocating Lua registration/finalizer setup before native construction; keep VM-local weak ownership.')
    add('idempotent_destroy',body(original,SIGNATURES[1]),'''int CvLuaFractal::lDestroy(lua_State* L)
{
    return ZeroSisLuaFractal::Destroy<CvFractal>(L, 1);
}''','Destroy only objects created by this VM, mark dead before destruction, and allow repeated finalization safely.')
    old='\tluaL_checktype(L, 1, LUA_TUSERDATA);\n\tCvFractal* pFractal = static_cast<CvFractal*>(lua_touserdata(L, 1));'
    for name,signature in [('check_height_self',SIGNATURES[2]),('check_ridges_self',SIGNATURES[3])]:
        before=body(original,signature);normalized=before.replace('\r\n','\n')
        if normalized.count(old)!=1:raise RuntimeError('Fractal self boundary changed')
        add(name,before,normalized.replace(old,'\tCvFractal* pFractal = ZeroSisLuaFractal::Check<CvFractal>(L, 1);'),
            'Reject foreign, borrowed and destroyed userdata before invoking native Fractal methods.')
    add('parse_create_before_userdata',body(original,'int CvLuaFractal::lCreate('),'''int CvLuaFractal::lCreate(lua_State* L)
{
    const int iNewXs = CvLuaChecked::ToInt(L, 1);
    const int iNewYs = CvLuaChecked::ToInt(L, 2);
    const int iGrain = CvLuaChecked::ToInt(L, 3);
    const int flags = GetFractalFlags(L, 4);
    const int iFracXExp = CvLuaChecked::OptInt(L, 5, CvFractal::DEFAULT_FRAC_X_EXP);
    const int iFracYExp = CvLuaChecked::OptInt(L, 6, CvFractal::DEFAULT_FRAC_Y_EXP);
    CvRandom& rand = GC.getGame().getMapRand();
    CvFractal* pFractal = CreateFractal(L);
    pFractal->fracInit(iNewXs, iNewYs, iGrain, rand, flags, NULL, iFracXExp, iFracYExp);
    return 1;
}''','Read optional arguments before pushing output userdata so missing options are not mistaken for that new object.')
    add('parse_rifts_before_userdata',body(original,SIGNATURES[4]),'''int CvLuaFractal::lCreateRifts(lua_State* L)
{
    const int iNewXs = CvLuaChecked::ToInt(L, 1);
    const int iNewYs = CvLuaChecked::ToInt(L, 2);
    const int iGrain = CvLuaChecked::ToInt(L, 3);
    const int flags = GetFractalFlags(L, 4);
    CvFractal* pRidgeFrac = ZeroSisLuaFractal::Optional<CvFractal>(L, 5);
    const int iFracXExp = CvLuaChecked::OptInt(L, 6, CvFractal::DEFAULT_FRAC_X_EXP);
    const int iFracYExp = CvLuaChecked::OptInt(L, 7, CvFractal::DEFAULT_FRAC_Y_EXP);
    CvRandom& rand = GC.getGame().getMapRand();
    CvFractal* pFractal = CreateFractal(L);
    pFractal->fracInit(iNewXs, iNewYs, iGrain, rand, flags, pRidgeFrac, iFracXExp, iFracYExp);
    return 1;
}''','Allow nil or live VM-owned rifts and parse before output allocation; never mistake the new object for a missing rifts argument.')
    return result


def candidate_text():
    text=baseline_text()
    for p in patches():
        if text.count(p['old'])!=p['count']:raise RuntimeError('Fractal candidate order changed')
        text=text.replace(p['old'],p['new'])
    current=json.loads((PROJECT/'Source/Porting/sdk_x64_patches.json').read_text(encoding='utf-8'))
    for p in current['patches']:
        if p['id'].startswith(('fractal_numeric_', 'lua_borrowed_')) and p['file']==SOURCE:
            if text.count(p['old'])!=p['count']:raise RuntimeError('Later Fractal numeric context changed')
            text=text.replace(p['old'],p['new'])
    return text


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    target=PROJECT/'Source/Porting/sdk_x64_patches.json'
    plan,base=(json.loads(p.read_text(encoding='utf-8')) for p in (target,BASE))
    retained=[p for p in plan['patches'] if not p['id'].startswith((PREFIX,'fractal_numeric_', 'lua_borrowed_'))]
    if retained!=base['patches'] or len(retained)!=613:raise RuntimeError('Accepted 613 SDK patches changed')
    added=patches()
    later=[p for p in plan['patches'] if p['id'].startswith(('fractal_numeric_', 'lua_borrowed_'))]
    if args.apply:
        plan['patches']=retained+added+later;target.write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        lp=PROJECT/'evidence/numeric_boundaries/edit_ledger.json';ledger=json.loads(lp.read_text(encoding='utf-8'))
        ledger['patch_specification_sha256']=digest(target)
        ledger['supplemental_non_numeric_patches']=[p for p in ledger['supplemental_non_numeric_patches'] if not p.startswith((PREFIX,'fractal_numeric_', 'lua_borrowed_'))]+[p['id'] for p in added+later]
        ledger['unchanged_lua_fractal_baseline']={'path':str(BASE),'sha256':digest(BASE)}
        lp.write_text(json.dumps(ledger,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    root=PROJECT/'evidence/lua_fractal';root.mkdir(parents=True,exist_ok=True)
    report={'status':'SDK_LUA_FRACTAL_PATCHES_APPLIED' if args.apply else 'SDK_LUA_FRACTAL_PATCHES_PROPOSED',
        'baseline':{'path':str(BASE),'sha256':digest(BASE)},'recipe':{'path':str(Path(__file__).resolve()),'sha256':digest(Path(__file__).resolve())},
        'previous_patches':613,'added_patches':len(added),'total_patches':613+len(added)+len(later),'patches':added,'files':[SOURCE],
        'gamecore_loaded':False,'game_launched':False}
    if args.apply:report['patch_specification']={'path':str(target),'sha256':digest(target)}
    (root/'caller_patch_plan.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(report['status'])


if __name__=='__main__':main()
