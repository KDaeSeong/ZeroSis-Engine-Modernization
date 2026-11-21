"""Propagate the six remaining Lua registrar failures; preserve attempt_033."""
import argparse
import json
from pathlib import Path
from collect_baseline import PROJECT, digest
from build_bootstrap_component import body

PREFIX = 'lua_registration_'
BASE = PROJECT / 'evidence/sdk_x64/attempts/attempt_033/sdk_x64_patches.json'
LUA = 'CvGameCoreDLL_Expansion2/Lua/'
STATIC = 'CvGameCoreDLLUtil/include/CvLuaStaticInstance.h'
FILES = tuple(LUA + 'CvLua' + c + '.cpp' for c in ('Fractal', 'GameInfo', 'Player', 'Team')) + (STATIC,)


def baseline_text(source):
    text = (PROJECT / 'Source/SDK_BNW_Original' / source).read_bytes().decode('latin1')
    for patch in json.loads(BASE.read_text(encoding='utf-8'))['patches']:
        if patch['file'] == source:
            if text.count(patch['old']) != patch['count']:
                raise RuntimeError('Registrar baseline changed: ' + patch['id'])
            text = text.replace(patch['old'], patch['new'])
    return text


def patches():
    result = []
    for source in FILES:
        original = baseline_text(source)
        def add(name, old, new, reason):
            new = new.replace('\r\n', '\n').replace('\n', '\r\n' if '\r\n' in original else '\n')
            if original.count(old) != 1:
                raise RuntimeError('Registrar patch context changed: ' + name)
            result.append({'id': PREFIX + name, 'file': source,
                'source_sha256': digest(PROJECT / 'Source/SDK_BNW_Original' / source),
                'old': old, 'new': new, 'count': 1, 'reason': reason})
        cls = Path(source).stem
        include = '#include "CvLuaMethodWrapper.h"' if source == STATIC else '#include "' + cls + '.h"'
        add(cls + '_stdexcept', include, include + '\n#include <stdexcept>',
            'Declare registration failure exceptions explicitly without changing SDK ABI or save layout.')
        owner = 'CvLuaStaticInstance<Derived, InstanceType>' if source == STATIC else cls
        signature = 'void ' + owner + '::Register(lua_State* L)'
        if cls == 'CvLuaGameInfo':
            calls = '''    if (!Lua::CCallWithErrorHandling(L, pRegisterActions))
        throw std::runtime_error("GameCore action library registration failed");
    if (!Lua::CCallWithErrorHandling(L, pRegisterTypesInfo))
        throw std::runtime_error("GameCore type library registration failed");'''
        else:
            label = 'static' if source == STATIC else cls.removeprefix('CvLua')
            calls = '    if (!FLua::Details::CCallWithErrorHandling(L, pRegister))\n' + (
                '        throw std::runtime_error("GameCore ' + label + ' library registration failed");')
        add(cls + '_propagate', body(original, signature), signature + '\n{\n' + calls + '\n}',
            'Stop on protected-call failure so the owner discards the incomplete VM and later registrars do not run.')
    return result


def candidate_text(source):
    text = baseline_text(source)
    for patch in patches():
        if patch['file'] == source:
            if text.count(patch['old']) != patch['count']:
                raise RuntimeError('Registrar candidate patch order changed')
            text = text.replace(patch['old'], patch['new'])
    current = json.loads((PROJECT / 'Source/Porting/sdk_x64_patches.json').read_text(encoding='utf-8'))
    for patch in current['patches']:
        if patch['id'].startswith(('lua_fractal_','fractal_numeric_', 'lua_borrowed_')) and patch['file'] == source:
            if text.count(patch['old']) != patch['count']:
                raise RuntimeError('Later Fractal source context changed')
            text = text.replace(patch['old'], patch['new'])
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    target = PROJECT / 'Source/Porting/sdk_x64_patches.json'
    plan, base = (json.loads(p.read_text(encoding='utf-8')) for p in (target, BASE))
    retained = [p for p in plan['patches'] if not p['id'].startswith((PREFIX, 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))]
    if retained != base['patches'] or len(retained) != 603:
        raise RuntimeError('Accepted 603 SDK patches changed')
    added = patches()
    later = [p for p in plan['patches'] if p['id'].startswith(('lua_fractal_','fractal_numeric_', 'lua_borrowed_'))]
    if args.apply:
        plan['patches'] = retained + added + later
        target.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        lp = PROJECT / 'evidence/numeric_boundaries/edit_ledger.json'
        ledger = json.loads(lp.read_text(encoding='utf-8'))
        ledger['patch_specification_sha256'] = digest(target)
        ledger['supplemental_non_numeric_patches'] = [p for p in ledger['supplemental_non_numeric_patches']
            if not p.startswith((PREFIX, 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))] + [p['id'] for p in added + later]
        ledger['unchanged_lua_registration_baseline'] = {'path': str(BASE), 'sha256': digest(BASE)}
        lp.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    root = PROJECT / 'evidence/lua_registration'
    root.mkdir(parents=True, exist_ok=True)
    report = {'status': 'SDK_LUA_REGISTRATION_PATCHES_APPLIED' if args.apply else 'SDK_LUA_REGISTRATION_PATCHES_PROPOSED',
        'baseline': {'path': str(BASE), 'sha256': digest(BASE)},
        'recipe': {'path': str(Path(__file__).resolve()), 'sha256': digest(Path(__file__).resolve())},
        'previous_patches': 603, 'added_patches': len(added), 'total_patches': 603 + len(added) + len(later),
        'patches': added, 'files': list(FILES), 'gamecore_loaded': False, 'game_launched': False}
    if args.apply:
        report['patch_specification'] = {'path': str(target), 'sha256': digest(target)}
    (root / 'caller_patch_plan.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(report['status'])


if __name__ == '__main__':
    main()
