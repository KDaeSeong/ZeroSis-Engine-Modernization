"""Add the missing owned strategy holder cleanup without changing retained patches."""
import json
from pathlib import Path
from collect_baseline import PROJECT, digest

PREFIX = 'globals_callers_'
BASE = PROJECT / 'evidence/sdk_x64/attempts/attempt_023/sdk_x64_patches.json'
TARGET = 'CvGameCoreDLL_Expansion2/CvGlobals.cpp'


def baseline_text(relative):
    text = (PROJECT / 'Source/SDK_BNW_Original' / relative).read_bytes().decode('latin1')
    for patch in json.loads(BASE.read_text(encoding='utf-8'))['patches']:
        if patch['file'] == relative:
            if text.count(patch['old']) != patch['count']:
                raise RuntimeError('Globals baseline patch drift: ' + patch['id'])
            text = text.replace(patch['old'], patch['new'])
    return text


def patches():
    text = baseline_text(TARGET)
    old = '\tSAFE_DELETE(m_pAIGrandStrategies);'
    newline = '\r\n' if '\r\n' in text else '\n'
    if text.count(old) != 1:
        raise RuntimeError('Expected one owned strategy cleanup group')
    return [{'id': PREFIX + 'city_strategy_cleanup', 'file': TARGET,
             'source_sha256': digest(PROJECT / 'Source/SDK_BNW_Original' / TARGET),
             'old': old, 'new': old + newline + '\tSAFE_DELETE(m_pAICityStrategies);', 'count': 1,
             'reason': 'Release the owned city strategy holder, its entries and flavor arrays after player/team teardown; preserve layout, rules and serialization.'}]


def main():
    path = PROJECT / 'Source/Porting/sdk_x64_patches.json'
    plan = json.loads(path.read_text(encoding='utf-8'))
    baseline = json.loads(BASE.read_text(encoding='utf-8'))
    retained = [p for p in plan['patches'] if not p['id'].startswith((PREFIX, 'construction_callers_','host_callers_','db_postprocess_', 'db_loader_', 'info_cleanup_' ,'db_cache_', 'startup_owners_', 'gc_lifecycle_', 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))]
    if retained != baseline['patches'] or len(retained) != 552:
        raise RuntimeError('Accepted 552 SDK patches changed')
    added = patches()
    later = [p for p in plan['patches'] if p['id'].startswith(('construction_callers_', 'host_callers_','db_postprocess_', 'db_loader_', 'info_cleanup_' ,'db_cache_', 'startup_owners_', 'gc_lifecycle_', 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))]
    plan['patches'] = retained + added + later
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    ledger_path = PROJECT / 'evidence/numeric_boundaries/edit_ledger.json'
    ledger = json.loads(ledger_path.read_text(encoding='utf-8'))
    ledger['patch_specification_sha256'] = digest(path)
    ledger['supplemental_non_numeric_patches'] = [
        x for x in ledger['supplemental_non_numeric_patches'] if not x.startswith((PREFIX, 'construction_callers_','host_callers_','db_postprocess_', 'db_loader_', 'info_cleanup_' ,'db_cache_', 'startup_owners_', 'gc_lifecycle_', 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))] + [p['id'] for p in added + later]
    ledger['unchanged_globals_caller_baseline'] = {'path': str(BASE), 'sha256': digest(BASE)}
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    root = PROJECT / 'evidence/globals_cleanup'
    root.mkdir(parents=True, exist_ok=True)
    report = {'status': 'SDK_GLOBALS_CLEANUP_DECLARED', 'baseline': ledger['unchanged_globals_caller_baseline'],
              'recipe': {'path': str(Path(__file__).resolve()), 'sha256': digest(Path(__file__).resolve())},
              'patch_specification': {'path': str(path), 'sha256': digest(path)},
              'previous_patches': 552, 'added_patches': 1, 'total_patches': len(plan['patches']),
              'files': [TARGET], 'patches': added, 'gamecore_loaded': False, 'game_launched': False}
    (root / 'caller_patch_plan.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('status', 'added_patches', 'total_patches')}))


if __name__ == '__main__':
    main()
