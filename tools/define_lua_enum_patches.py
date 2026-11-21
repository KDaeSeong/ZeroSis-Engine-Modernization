"""Specify SDK dynamic enum error boundaries against the accepted attempt_032."""
import argparse
import json
from pathlib import Path
from collect_baseline import PROJECT, digest
from build_bootstrap_component import body

PREFIX = 'lua_enum_'
BASE = PROJECT / 'evidence/sdk_x64/attempts/attempt_032/sdk_x64_patches.json'
SOURCE = 'CvGameCoreDLL_Expansion2/Lua/CvLuaEnums.cpp'
SIGNATURES = ('void CvLuaEnums::Register(lua_State* L)', 'void CvLuaEnums::RegisterDynamicEnums(')


def baseline_text():
    text = (PROJECT / 'Source/SDK_BNW_Original' / SOURCE).read_bytes().decode('latin1')
    for patch in json.loads(BASE.read_text(encoding='utf-8'))['patches']:
        if patch['file'] == SOURCE:
            if text.count(patch['old']) != patch['count']:
                raise RuntimeError('Lua enum baseline changed: ' + patch['id'])
            text = text.replace(patch['old'], patch['new'])
    return text


def patches():
    original = baseline_text()
    result = []
    def add(name, old, new, reason):
        new = new.replace('\r\n', '\n').replace('\n', '\r\n' if '\r\n' in original else '\n')
        if original.count(old) != 1:
            raise RuntimeError('Lua enum patch context changed: ' + name)
        result.append({'id': PREFIX + name, 'file': SOURCE,
                       'source_sha256': digest(PROJECT / 'Source/SDK_BNW_Original' / SOURCE),
                       'old': old, 'new': new, 'count': 1, 'reason': reason})
    add('protected_helper_include', '#include "CvLuaEnums.h"',
        '#include "CvLuaEnums.h"\n#include "ZeroSisLuaEnums.h"',
        'Declare the DB snapshot/protected Lua publication helper without changing SDK ABI or save fields.')
    add('propagate_registration_failure', body(original, SIGNATURES[0]),
        '''void CvLuaEnums::Register(lua_State* L)
{
    if (!FLua::Details::CCallWithErrorHandling(L, pRegister))
        throw std::runtime_error("GameCore enum library registration failed");
}''', 'Do not report a failed protected enum registration as success to the script VM owner.')
    add('snapshot_and_protected_publication', body(original, SIGNATURES[1]),
        '''void CvLuaEnums::RegisterDynamicEnums(lua_State* L, const char* szTableName, const char* szIdField, const char* szNameField, const char* szCountName)
{
    ZeroSisLuaEnums::RegisterDynamic(L, GC.GetGameDatabase(), szTableName, szIdField, szNameField, szCountName);
}''', 'Complete DB reads/count before Lua writes, check query/iteration/count failures and unwind C++ storage after protected Lua errors.')
    return result


def candidate_text():
    text = baseline_text()
    for patch in patches():
        if text.count(patch['old']) != patch['count']:
            raise RuntimeError('Lua enum candidate patch order changed')
        text = text.replace(patch['old'], patch['new'])
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    target = PROJECT / 'Source/Porting/sdk_x64_patches.json'
    plan, base = (json.loads(p.read_text(encoding='utf-8')) for p in (target, BASE))
    retained = [p for p in plan['patches'] if not p['id'].startswith((PREFIX, 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))]
    if retained != base['patches'] or len(retained) != 600:
        raise RuntimeError('Accepted 600 SDK patches changed')
    added = patches()
    later = [p for p in plan['patches'] if p['id'].startswith(('lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))]
    if args.apply:
        plan['patches'] = retained + added + later
        target.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        lp = PROJECT / 'evidence/numeric_boundaries/edit_ledger.json'
        ledger = json.loads(lp.read_text(encoding='utf-8'))
        ledger['patch_specification_sha256'] = digest(target)
        ledger['supplemental_non_numeric_patches'] = [p for p in ledger['supplemental_non_numeric_patches']
            if not p.startswith((PREFIX, 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))] + [p['id'] for p in added + later]
        ledger['unchanged_lua_enum_baseline'] = {'path': str(BASE), 'sha256': digest(BASE)}
        lp.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    root = PROJECT / 'evidence/lua_enums'
    root.mkdir(parents=True, exist_ok=True)
    report = {'status': 'SDK_LUA_ENUM_PATCHES_APPLIED' if args.apply else 'SDK_LUA_ENUM_PATCHES_PROPOSED',
              'baseline': {'path': str(BASE), 'sha256': digest(BASE)},
              'recipe': {'path': str(Path(__file__).resolve()), 'sha256': digest(Path(__file__).resolve())},
              'previous_patches': 600, 'added_patches': len(added), 'total_patches': 600 + len(added) + len(later),
              'patches': added, 'files': [SOURCE], 'gamecore_loaded': False, 'game_launched': False}
    if args.apply:
        report['patch_specification'] = {'path': str(target), 'sha256': digest(target)}
    (root / 'caller_patch_plan.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(report['status'])


if __name__ == '__main__':
    main()
