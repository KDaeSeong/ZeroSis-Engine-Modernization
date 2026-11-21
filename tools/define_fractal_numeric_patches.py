"""Propose native Fractal numeric boundaries on the accepted attempt_035."""
import argparse,json
from pathlib import Path
from collect_baseline import PROJECT,digest
from build_bootstrap_component import body

PREFIX='fractal_numeric_'
BASE=PROJECT/'evidence/sdk_x64/attempts/attempt_035/sdk_x64_patches.json'
NATIVE='CvGameCoreDLL_Expansion2/CvFractal.cpp'
HEADER='CvGameCoreDLL_Expansion2/CvFractal.h'
LUA='CvGameCoreDLL_Expansion2/Lua/CvLuaFractal.cpp'


def baseline_text(source):
    text=(PROJECT/'Source/SDK_BNW_Original'/source).read_bytes().decode('latin1')
    for p in json.loads(BASE.read_text(encoding='utf-8'))['patches']:
        if p['file']==source:
            if text.count(p['old'])!=p['count']:raise RuntimeError('Numeric baseline changed: '+p['id'])
            text=text.replace(p['old'],p['new'])
    return text


def patches():
    result=[]
    def add(source,name,old,new,reason):
        original=baseline_text(source)
        if original.count(old)!=1:raise RuntimeError('Numeric patch context changed: '+name)
        new=new.replace('\r\n','\n').replace('\n','\r\n' if '\r\n' in original else '\n')
        result.append({'id':PREFIX+name,'file':source,'source_sha256':digest(PROJECT/'Source/SDK_BNW_Original'/source),
            'old':old,'new':new,'count':1,'reason':reason})
    def change(source,name,signature,transform,reason):
        old=body(baseline_text(source),signature)
        new=transform(old.replace('\r\n','\n'))
        if new==old.replace('\r\n','\n'):raise RuntimeError('Empty numeric patch: '+name)
        add(source,name,old,new,reason)
    def replace(text,old,new):
        if text.count(old)!=1:raise RuntimeError('Numeric body anchor changed: '+old[:90])
        return text.replace(old,new)
    add(NATIVE,'includes','#include "CvFractal.h"','#include "CvFractal.h"\n#include <stdexcept>\n#include <cstdint>',
        'Provide typed failures and wide intermediate arithmetic without changing object layout.')
    def initialize(text):
        prefix='''    if (iNewXs <= 0 || iNewYs <= 0)
        throw std::invalid_argument("Fractal output dimensions must be positive");
    if (iFracXExp < 0) iFracXExp = DEFAULT_FRAC_X_EXP;
    if (iFracYExp < 0) iFracYExp = DEFAULT_FRAC_Y_EXP;
    if (iFracXExp > 7 || iFracYExp > 7)
        throw std::invalid_argument("Fractal exponents exceed fixed storage including endpoints");
    const int fracX = 1 << iFracXExp;
    const int fracY = 1 << iFracYExp;
    const int minExp = std::min(iFracXExp, iFracYExp);
    const int iSmooth = iGrain <= 0 ? minExp : iGrain >= minExp ? 0 : minExp - iGrain;
    const int iHintsWidth = (1 << (iFracXExp - iSmooth)) + ((iFlags & FRAC_WRAP_X) ? 0 : 1);
    const int iHintsHeight = (1 << (iFracYExp - iSmooth)) + ((iFlags & FRAC_WRAP_Y) ? 0 : 1);
    if (pbyHints && iHintsLength != iHintsWidth * iHintsHeight)
        throw std::invalid_argument("Fractal hint buffer length does not match the input grid");
    if (pRifts && (pRifts == this || pRifts->m_iXs <= 0 || pRifts->m_iYs <= 0 ||
        pRifts->m_iFracX < ((fracX / 4) * 3) || pRifts->m_iFracY < fracY))
        throw std::invalid_argument("Fractal rifts do not cover the initialized input grid");
'''
        text=replace(text,'\tFAssert(iNewXs < FRACTAL_MAX_DIMS);\n\tFAssert(iNewYs < FRACTAL_MAX_DIMS);\n\n\tint iSmooth;',prefix)
        defaults='''\tif(iFracXExp < 0)
\t{
\t\tiFracXExp = DEFAULT_FRAC_X_EXP;
\t}
\tif(iFracYExp < 0)
\t{
\t\tiFracYExp = DEFAULT_FRAC_Y_EXP;
\t}

'''
        text=replace(text,defaults,'')
        start=text.index('\tint iMinExp = std::min(m_iFracXExp, m_iFracYExp);')
        end=text.index('\tfor(iPass = iSmooth;',start)
        text=text[:start]+text[end:]
        return text
    change(NATIVE,'validate_before_initialization','void CvFractal::fracInitInternal(',initialize,
        'Validate dimensions, shifts, hints and rift coverage before reset/RNG; preserve saturated grain without overflowing subtraction.')
    change(NATIVE,'require_percent_state','int CvFractal::getHeightFromPercent(',
        lambda t:replace(t,'{\n\tint iEstimate;','{\n    if (m_iXs <= 0 || m_iYs <= 0 || m_iFracX <= 0 || m_iFracY <= 0)\n        throw std::logic_error("Fractal is not initialized");\n\tint iEstimate;'),
        'Reject percentile reads of uninitialized state before denominator or array access.')
    add(NATIVE,'wrap_small_grids',body(baseline_text(NATIVE),'int CvFractal::yieldX('),'''int CvFractal::yieldX(int iBadX)
{
    if (m_iFracX <= 0) throw std::logic_error("Fractal is not initialized");
    const int wrapped = iBadX % m_iFracX;
    return wrapped < 0 ? wrapped + m_iFracX : wrapped;
}''','Normalize repeated wrapping for small grids without reading outside the fixed array.')
    def ridges(text):
        anchor='\tiNumVoronoiSeeds = std::max(iNumVoronoiSeeds,3); // make sure that we have at least 3'
        prefix='''    if (m_iXs <= 0 || m_iYs <= 0 || m_iFracX <= 0 || m_iFracY <= 0)
        throw std::logic_error("Fractal is not initialized");
    if (iBlendRidge < 0 || iBlendFract < 0)
        throw std::invalid_argument("Fractal ridge blend weights must be nonnegative");
    iNumVoronoiSeeds = std::max(iNumVoronoiSeeds, 3);
    // Initial hex-space and retry coordinates occupy this conservative rectangle.
    if (iNumVoronoiSeeds > (m_iFracX + m_iFracY / 2) * m_iFracY)
        throw std::invalid_argument("Fractal ridge seed count exceeds the coordinate domain");
    const int retryLimit = m_iFracX * m_iFracY * 64 + 1024;
    int retries = 0;'''
        text=replace(text,anchor,prefix)
        anchor='\t\t\t\t\tthisVoronoiSeed.m_iHexspaceX = random.get(m_iFracX, "Ridge Gen 6");'
        text=replace(text,anchor,'\t\t\t\t\tif (++retries > retryLimit)\n\t\t\t\t\t\tthrow std::runtime_error("Fractal ridge placement retry budget exhausted");\n'+anchor)
        text=replace(text,'\t\t\tm_aaiFrac[iX][iY] = (iRidgeHeight * iBlendRidge + m_aaiFrac[iX][iY] * iBlendFract) / std::max(iBlendRidge + iBlendFract, 1);',
            '''            const std::int64_t numerator = static_cast<std::int64_t>(iRidgeHeight) * iBlendRidge
                + static_cast<std::int64_t>(m_aaiFrac[iX][iY]) * iBlendFract;
            const std::int64_t denominator = std::max<std::int64_t>(static_cast<std::int64_t>(iBlendRidge) + iBlendFract, 1);
            m_aaiFrac[iX][iY] = static_cast<int>(numerator / denominator);''')
        return text
    change(NATIVE,'bounded_ridges_and_wide_blend','void CvFractal::ridgeBuilder(',ridges,
        'Reject impossible/negative inputs, bound retries before height writes and preserve valid blend arithmetic using 64-bit intermediates.')
    add(HEADER,'exponent_contract','// iFracXExp should be 8 or less','// Internal exponents are 0..7; fixed storage also holds the endpoint. Negative values select defaults.',
        'Correct the existing exponent comment without changing fields or ABI.')
    add(LUA,'error_boundary_include','#include "ZeroSisLuaFractal.h"','#include "ZeroSisLuaFractal.h"\n#include "ZeroSisLuaFractalNumeric.h"',
        'Translate native numeric/allocation exceptions at the actual Lua callback boundary.')
    def register(text):
        for name in ('lCreate','lCreateRifts'):
            text=replace(text,'lua_pushcclosure(L, '+name+', 0);','lua_pushcclosure(L, ZeroSisLuaFractalNumeric::Protected<'+name+'>, 0);')
        return text
    change(LUA,'protect_create_callbacks','int CvLuaFractal::pRegister(',register,
        'Leave C++ catch scopes before raising Lua errors from native initialization failures.')
    change(LUA,'protect_method_callbacks','CvFractal* CvLuaFractal::CreateFractal(',
        lambda t:replace(t,'(L, lGetHeight, lBuildRidges, lDestroy);',
            '(L, ZeroSisLuaFractalNumeric::Protected<lGetHeight>, ZeroSisLuaFractalNumeric::Protected<lBuildRidges>, lDestroy);'),
        'Make native ridge and percentile errors catchable by Lua pcall without crossing an active C++ catch.')
    return result


def candidate_text(source):
    text=baseline_text(source)
    for p in patches():
        if p['file']==source:
            if text.count(p['old'])!=p['count']:raise RuntimeError('Numeric candidate patch order changed')
            text=text.replace(p['old'],p['new'])
    return text


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    target=PROJECT/'Source/Porting/sdk_x64_patches.json'
    plan,base=(json.loads(p.read_text(encoding='utf-8')) for p in (target,BASE))
    retained=[p for p in plan['patches'] if not p['id'].startswith((PREFIX,'lua_borrowed_'))]
    if retained!=base['patches'] or len(retained)!=620:raise RuntimeError('Accepted 620 SDK patches changed')
    added=patches()
    later=[p for p in plan['patches'] if p['id'].startswith('lua_borrowed_')]
    if args.apply:
        plan['patches']=retained+added+later;target.write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        lp=PROJECT/'evidence/numeric_boundaries/edit_ledger.json';ledger=json.loads(lp.read_text(encoding='utf-8'))
        ledger['patch_specification_sha256']=digest(target)
        ledger['supplemental_non_numeric_patches']=[p for p in ledger['supplemental_non_numeric_patches'] if not p.startswith((PREFIX,'lua_borrowed_'))]+[p['id'] for p in added+later]
        ledger['unchanged_fractal_numeric_baseline']={'path':str(BASE),'sha256':digest(BASE)}
        lp.write_text(json.dumps(ledger,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    root=PROJECT/'evidence/fractal_numeric';root.mkdir(parents=True,exist_ok=True)
    report={'status':'SDK_FRACTAL_NUMERIC_PATCHES_APPLIED' if args.apply else 'SDK_FRACTAL_NUMERIC_PATCHES_PROPOSED',
        'baseline':{'path':str(BASE),'sha256':digest(BASE)},'recipe':{'path':str(Path(__file__).resolve()),'sha256':digest(Path(__file__).resolve())},
        'previous_patches':620,'added_patches':len(added),'total_patches':620+len(added)+len(later),'patches':added,
        'gamecore_loaded':False,'game_launched':False}
    if args.apply:report['patch_specification']={'path':str(target),'sha256':digest(target)}
    (root/'caller_patch_plan.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(report['status'])


if __name__=='__main__':main()
