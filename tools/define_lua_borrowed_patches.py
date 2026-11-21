"""Reviewable borrowed-reference candidate on frozen attempt_036 (not applied)."""
import argparse
import json
from functools import lru_cache
from pathlib import Path
from collect_baseline import PROJECT, digest
from build_bootstrap_component import body

PREFIX = 'lua_borrowed_'
BASE = PROJECT/'evidence/sdk_x64/attempts/attempt_036/sdk_x64_patches.json'
LUA = 'CvGameCoreDLL_Expansion2/Lua/'
SCOPED = LUA+'CvLuaScopedInstance.h'
IS_NONE = ('Area', 'City', 'League', 'Plot', 'Unit', 'Team')
ROOT = 'CvGameCoreDLL_Expansion2/'
LIFECYCLE = {
    'CvArea.cpp': ['CvArea::~CvArea()', 'void CvArea::uninit()', 'void CvArea::reset(', 'void CvArea::read('],
    'CvCity.cpp': ['CvCity::~CvCity()', 'void CvCity::uninit()', 'void CvCity::reset(', 'void CvCity::read('],
    'CvUnit.cpp': ['CvUnit::~CvUnit()', 'void CvUnit::uninit()', 'void CvUnit::reset(', 'void CvUnit::read('],
    'CvPlot.cpp': ['CvPlot::~CvPlot()', 'void CvPlot::uninit()', 'void CvPlot::reset(', 'void CvPlot::read('],
    'CvPlayer.cpp': ['CvPlayer::~CvPlayer()', 'void CvPlayer::uninit()', 'void CvPlayer::reset(', 'void CvPlayer::Read('],
    'CvPlayerAI.cpp': ['CvPlayerAI::~CvPlayerAI()'],
    'CvTeam.cpp': ['CvTeam::~CvTeam()', 'void CvTeam::uninit()', 'void CvTeam::reset(', 'void CvTeam::Read('],
    'CvTechClasses.cpp': ['CvTeamTechs::~CvTeamTechs(', 'void CvTeamTechs::Init(', 'void CvTeamTechs::Uninit()', 'void CvTeamTechs::Reset()', 'void CvTeamTechs::Read('],
    'CvDealClasses.cpp': ['CvDeal::~CvDeal()', 'FDataStream& operator>>(FDataStream& loadFrom, CvDeal& writeTo)'],
    'CvVotingClasses.cpp': ['CvLeague::~CvLeague(', 'FDataStream& operator>>(FDataStream& loadFrom, CvLeague& writeTo)'],
}


@lru_cache(maxsize=None)
def baseline_text(source):
    text = (PROJECT/'Source/SDK_BNW_Original'/source).read_bytes().decode('latin1')
    for patch in json.loads(BASE.read_text(encoding='utf-8'))['patches']:
        if patch['file'] == source:
            if text.count(patch['old']) != patch['count']:
                raise RuntimeError('Borrowed baseline mismatch: '+patch['id'])
            text = text.replace(patch['old'], patch['new'])
    return text


@lru_cache(maxsize=None)
def patches():
    result = []

    def add(source, name, old, new, reason):
        original = baseline_text(source)
        if original.count(old) != 1:
            raise RuntimeError('Borrowed context mismatch: '+name)
        new = new.replace('\r\n', '\n').replace('\n', '\r\n' if '\r\n' in original else '\n')
        result.append(dict(id=PREFIX+name, file=source,
            source_sha256=digest(PROJECT/'Source/SDK_BNW_Original'/source),
            old=old, new=new, count=1, reason=reason))

    original = baseline_text(SCOPED)
    changed = original.replace('\r\n', '\n')
    changed = changed.replace('#ifndef CVLUASCOPEDNSTANCE_H', '#ifndef CVLUASCOPEDNSTANCE_H\n#define CVLUASCOPEDNSTANCE_H')
    changed = changed.replace('#include "CvLuaMethodWrapper.h"', '#include "CvLuaMethodWrapper.h"\n#include "ZeroSisLuaBorrowed.h"')
    changed = changed.replace('protected:\n', 'protected:\n\tstatic int pPush(lua_State* L);\n', 1)
    signature = 'void CvLuaScopedInstance<Derived, InstanceType>::Push(lua_State* L, InstanceType* pkType)'
    old_push = body(changed, signature)
    inner = old_push.replace(signature,
        'int CvLuaScopedInstance<Derived, InstanceType>::pPush(lua_State* L)', 1)
    inner = inner.replace('{\n', '''{
    ZeroSisLuaBorrowed::Request<InstanceType>* request =
        static_cast<ZeroSisLuaBorrowed::Request<InstanceType>*>(lua_touserdata(L, 1));
    InstanceType* pkType = request->pointer;
''', 1)
    publish = '\t\t\tlua_pushvalue(L, -1);\n\t\t\tlua_setglobal(L, Derived::GetTypeName());\n\n\t\t\tDerived::PushMethods(L, lua_gettop(L));'
    assert inner.count(publish) == 1
    inner = inner.replace(publish, '\t\t\tDerived::PushMethods(L, lua_gettop(L));\n\t\t\tlua_pushvalue(L, -1);\n\t\t\tlua_setglobal(L, Derived::GetTypeName());')
    anchor = '\t\tconst int type_index = lua_gettop(L);'
    inner = inner.replace(anchor, '\t\tif (!lua_istable(L, -1)) luaL_error(L, "Object type table is invalid");\n'+anchor)
    anchor = '\t\tconst int instances_index = lua_gettop(L);'
    inner = inner.replace(anchor, '\t\tif (!lua_istable(L, -1)) luaL_error(L, "Object instance cache is invalid");\n'+anchor)
    anchor = '\t\tif(lua_isnil(L, -1))\n\t\t{\n\t\t\tlua_pop(L, 1);\n\n\t\t\t//Push new instance'
    assert inner.count(anchor) == 1
    inner = inner.replace(anchor, anchor.replace('lua_isnil(L, -1)', 'ZeroSisLuaBorrowed::Find<InstanceType>(L, -1) != pkType'))
    anchor = '\t\t\t//Assign it in instances'
    inner = inner.replace(anchor, '\t\t\tZeroSisLuaBorrowed::Attach<InstanceType>(L, -1, request);\n\n'+anchor)
    inner = inner[:-1]+'    ZeroSisLuaBorrowed::StoreResult(L, request);\n    return 0;\n}'
    outer = signature+'''\n{
    ZeroSisLuaBorrowed::Push(L, pkType, &CvLuaScopedInstance<Derived, InstanceType>::pPush);
}'''
    changed = changed.replace(old_push, outer+'\n\ntemplate<class Derived, class InstanceType>\n'+inner)
    signature = 'InstanceType* CvLuaScopedInstance<Derived, InstanceType>::GetInstance('
    old_get = body(changed, signature)
    new_get = '''InstanceType* CvLuaScopedInstance<Derived, InstanceType>::GetInstance(lua_State* L, int idx, bool bErrorOnFail)
{
    InstanceType* pkInstance = ZeroSisLuaBorrowed::Find<InstanceType>(L, idx);
    if (!pkInstance && bErrorOnFail)
    {
        if (idx == 1)
            luaL_error(L, "Not a valid instance.  Either the instance is NULL or you used '.' instead of ':'.");
        Derived::HandleMissingInstance(L);
    }
    return pkInstance;
}'''
    changed = changed.replace(old_get, new_get)
    add(SCOPED, 'scoped_reference_provenance', original, changed,
        'Authenticate typed VM-issued tables, track invalidation through protected Push, reject stale cache entries, publish complete methods only.')
    for name in IS_NONE:
        source = LUA+'CvLua'+name+'.cpp'
        old = body(baseline_text(source), 'int CvLua'+name+'::lIsNone(')
        new = old.replace('GetInstance(L, false)', 'GetInstance(L, 1, false)')
        if name == 'Area':
            new = new.replace('const bool bExists =', 'const bool bDoesNotExist =').replace('!= NULL', '== NULL').replace('lua_pushboolean(L, bExists)', 'lua_pushboolean(L, bDoesNotExist)')
        add(source, 'is_none_'+name.lower(), old, new,
            'Use stack argument 1 and suppress lookup errors explicitly; IsNone reports missing references.')
    for name in ('City', 'Unit', 'Plot', 'Deal'):
        source = ROOT+'CvDll'+name+'.h'
        old = baseline_text(source)
        new = old.replace('#include "CvDllInterfaces.h"', '#include "CvDllInterfaces.h"\n#include "ZeroSisLuaBorrowed.h"')
        member = 'Cv'+name+'* m_p'+name+';'
        assert old.count(member) == 1
        new = new.replace(member, 'ZeroSisLuaBorrowed::NativeReference<Cv'+name+'> m_p'+name+';')
        add(source, 'native_reference_'+name.lower(), old, new,
            'Replace the DLL-private raw pointer with an invalidatable reference; public ICv method declarations and gameplay layout stay unchanged.')
    for file, signatures in LIFECYCLE.items():
        source = ROOT+file
        add(source, 'native_include_'+file[:-4].lower(), '#include "CvGameCoreDLLPCH.h"',
            '#include "CvGameCoreDLLPCH.h"\n#include "ZeroSisLuaBorrowed.h"', 'Connect native lifetime boundaries to the shared nonowning reference registry.')
        for index, signature in enumerate(signatures):
            old = body(baseline_text(source), signature)
            new = old.replace('\r\n', '\n')
            if signature == 'CvUnit::~CvUnit()':
                new = new.replace('{\n', '{\n    ZeroSisLuaBorrowed::RetireOnExit borrowedExit(this);\n', 1)
                assert new.count('\tuninit();') == 1
                new = new.replace('\tuninit();', '    ZeroSisLuaBorrowed::InvalidationScope borrowedEnd(this);\n\tuninit();')
                reason = 'Keep GameplayUnitDestroyed and map removal callbacks live, then revoke before uninit; invalidate again on destructor exit.'
            else:
                kind = 'InvalidationScope' if '::~' in signature else 'SuspensionScope'
                target = '&writeTo' if signature.startswith('FDataStream& operator>>') else 'this'
                new = new.replace('{\n', '{\n    ZeroSisLuaBorrowed::'+kind+' borrowedState('+target+');\n', 1)
                reason = 'Revoke at physical destruction; preserve existing identity across state reset/read while rejecting reentrant access during mutation.'
            add(source, 'native_lifecycle_'+file[:-4].lower()+'_'+str(index), old, new, reason)
    source = ROOT+'CvDealClasses.cpp'
    old = body(baseline_text(source), 'CvDeal& CvDeal::operator=(')
    new = old.replace('\r\n', '\n').replace('{\n', '{\n    if (this == &source) return *this;\n', 1)
    add(source, 'deal_self_assignment', old, new,
        'Preserve trade items when CopyFrom aliases the same scratch deal; keep ordinary copy and reference identity unchanged.')
    source = ROOT+'CvDllScriptSystemUtility.cpp'
    for name in ('City', 'Unit', 'Plot', 'Deal'):
        for operation in ('Push', 'Get'):
            signature = ('void ' if operation == 'Push' else 'ICv'+name+'1* ')+ 'CvDllScriptSystemUtility::'+operation+'Cv'+name+'Instance('
            old = body(baseline_text(source), signature)
            guard = '    if (L == NULL) return'+(';' if operation == 'Push' else ' NULL;')
            new = old.replace('\r\n', '\n').replace('{\n', '{\n'+guard+'\n', 1)
            add(source, 'script_utility_'+operation.lower()+'_'+name.lower(), old, new,
                'Avoid calling the Lua C API with a null VM; expired native references otherwise flow through the existing nil result.')
    return result


def candidate_text(source):
    text = baseline_text(source)
    for patch in patches():
        if patch['file'] == source:
            if text.count(patch['old']) != patch['count']:
                raise RuntimeError('Candidate patch ordering mismatch')
            text = text.replace(patch['old'], patch['new'])
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    baseline = json.loads(BASE.read_text(encoding='utf-8'))
    if len(baseline['patches']) != 629:
        raise RuntimeError('Accepted attempt_036 baseline changed')
    proposed = patches()
    target = PROJECT/'Source/Porting/sdk_x64_patches.json'
    current = json.loads(target.read_text(encoding='utf-8'))
    retained = [p for p in current['patches'] if not p['id'].startswith(PREFIX)]
    if retained != baseline['patches']:
        raise RuntimeError('Borrowed integration would change the accepted 629-patch baseline')
    if args.apply:
        current['patches'] = retained+proposed
        target.write_text(json.dumps(current, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        ledger_path = PROJECT/'evidence/numeric_boundaries/edit_ledger.json'
        ledger = json.loads(ledger_path.read_text(encoding='utf-8'))
        ledger['patch_specification_sha256'] = digest(target)
        ledger['supplemental_non_numeric_patches'] = [p for p in ledger['supplemental_non_numeric_patches']
            if not p.startswith(PREFIX)]+[p['id'] for p in proposed]
        ledger['unchanged_lua_borrowed_baseline'] = dict(path=str(BASE), sha256=digest(BASE))
        ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    root = PROJECT/'evidence/lua_borrowed'
    root.mkdir(parents=True, exist_ok=True)
    report = dict(status='SDK_LUA_BORROWED_PATCHES_APPLIED' if args.apply else 'SDK_LUA_BORROWED_PATCHES_PROPOSED_NOT_APPLIED',
        baseline=dict(path=str(BASE), sha256=digest(BASE)),
        recipe=dict(path=str(Path(__file__).resolve()), sha256=digest(Path(__file__).resolve())),
        previous_patches=629, added_patches=len(proposed), patches=proposed,
        lifecycle_hooks_proposed=True, lifecycle_hooks_integrated=args.apply,
        native_lifecycle_boundaries=sum(map(len, LIFECYCLE.values())), gamecore_loaded=False, game_launched=False)
    if args.apply: report['patch_specification'] = dict(path=str(target), sha256=digest(target))
    (root/'caller_patch_plan.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(report['status'])


if __name__ == '__main__':
    main()
