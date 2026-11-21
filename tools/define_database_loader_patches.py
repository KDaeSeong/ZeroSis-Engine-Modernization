"""Release the GameCore-owned database loader before its private heap ends."""
import json
from pathlib import Path
from collect_baseline import PROJECT, digest
from build_bootstrap_component import body

PREFIX = 'db_loader_'
BASE = PROJECT / 'evidence/sdk_x64/attempts/attempt_027/sdk_x64_patches.json'
GLOBALS = 'CvGameCoreDLL_Expansion2/CvGlobals.cpp'
HEADER = 'CvGameCoreDLL_Expansion2/CvGlobals.h'
CONTEXT = 'CvGameCoreDLL_Expansion2/CvDllContext.cpp'
UTILITY = 'CvGameCoreDLL_Expansion2/CvDllDatabaseUtility.cpp'


def baseline_text(relative):
    text = (PROJECT / 'Source/SDK_BNW_Original' / relative).read_bytes().decode('latin1')
    for patch in json.loads(BASE.read_text(encoding='utf-8'))['patches']:
        if patch['file'] == relative:
            if text.count(patch['old']) != patch['count']:
                raise RuntimeError('Database loader baseline drift: ' + patch['id'])
            text = text.replace(patch['old'], patch['new'])
    return text


def patches():
    result = []
    def add(name, relative, old, new, reason):
        text = baseline_text(relative)
        new = new.replace('\r\n', '\n')
        if '\r\n' in text:
            new = new.replace('\n', '\r\n')
        if text.count(old) != 1:
            raise RuntimeError('Database loader patch mismatch: ' + name)
        result.append({'id': PREFIX + name, 'file': relative,
                       'source_sha256': digest(PROJECT / 'Source/SDK_BNW_Original' / relative),
                       'old': old, 'new': new, 'count': 1, 'reason': reason})
    add('include', GLOBALS, '#include "CvCheckedNarrow.h"',
        '#include "CvCheckedNarrow.h"\n#include "ZeroSisHostBinding.h"',
        'Use the live ICvUnknown Destroy dispatcher without nonvirtual-base deletion.')
    add('declare_release', HEADER, '\tICvDLLDatabaseUtility1* getDatabaseLoadUtility();',
        '\tICvDLLDatabaseUtility1* getDatabaseLoadUtility();\n'
        '\t// Serialized lifecycle owner; external references must finish before heap shutdown.\n'
        '\tvoid releaseDatabaseLoadUtility();',
        'Expose a nonvirtual lifecycle helper without changing object layout or public interface slots.')
    factory = body(baseline_text(GLOBALS), 'ICvDLLDatabaseUtility1* CvGlobals::getDatabaseLoadUtility()')
    add('release_owner', GLOBALS, factory, factory + '''

void CvGlobals::releaseDatabaseLoadUtility()
{
    // Detach the cached owner first. QueryInterface callers own separate references.
    // A later factory request gets a new loader with an uncached database state.
    ICvDLLDatabaseUtility1* owner = m_pkDatabaseLoadUtility;
    m_pkDatabaseLoadUtility = NULL;
    ZeroSisHostBinding::Release(owner);
}''', 'Release exactly the retained reference, clear the factory cache, and preserve caller-owned references.')
    old = body(baseline_text(GLOBALS), 'void CvGlobals::uninit()')
    add('uninit_release', GLOBALS, old,
        old.replace('\tm_kGlobalDefinesLookup.Release();',
                    '\tm_kGlobalDefinesLookup.Release();\n\treleaseDatabaseLoadUtility();'),
        'Finish internal DB queries and release the loader before host UninitGlobals.')
    old = body(baseline_text(CONTEXT), 'bool CvDllGameContext::ShutdownSingleton()')
    add('shutdown_release', CONTEXT, old,
        old.replace('    SAFE_DELETE(s_pSingleton);',
                    '    SAFE_DELETE(s_pSingleton);\n    GC.releaseDatabaseLoadUtility();'),
        'Also drain a loader requested before GC.init, before releasing the host and destroying the context heap.')
    return result


def main():
    path = PROJECT / 'Source/Porting/sdk_x64_patches.json'
    plan, base = (json.loads(p.read_text(encoding='utf-8')) for p in (path, BASE))
    retained = [p for p in plan['patches'] if not p['id'].startswith((PREFIX, 'info_cleanup_' ,'db_cache_', 'startup_owners_', 'gc_lifecycle_', 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))]
    if retained != base['patches'] or len(retained) != 563:
        raise RuntimeError('Accepted 563 SDK patches changed')
    added = patches()
    later = [p for p in plan['patches'] if p['id'].startswith(('info_cleanup_', 'db_cache_', 'startup_owners_', 'gc_lifecycle_', 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))]
    plan['patches'] = retained + added + later
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    lp = PROJECT / 'evidence/numeric_boundaries/edit_ledger.json'
    ledger = json.loads(lp.read_text(encoding='utf-8'))
    ledger['patch_specification_sha256'] = digest(path)
    ledger['supplemental_non_numeric_patches'] = [x for x in ledger['supplemental_non_numeric_patches']
        if not x.startswith((PREFIX, 'info_cleanup_' ,'db_cache_', 'startup_owners_', 'gc_lifecycle_', 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))] + [p['id'] for p in added + later]
    ledger['unchanged_database_loader_baseline'] = {'path': str(BASE), 'sha256': digest(BASE)}
    lp.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    root = PROJECT / 'evidence/database_loader'
    root.mkdir(parents=True, exist_ok=True)
    report = {'status': 'SDK_DATABASE_LOADER_CALLERS_DECLARED', 'baseline': ledger['unchanged_database_loader_baseline'],
              'recipe': {'path': str(Path(__file__).resolve()), 'sha256': digest(Path(__file__).resolve())},
              'patch_specification': {'path': str(path), 'sha256': digest(path)}, 'previous_patches': 563,
              'added_patches': len(added), 'total_patches': len(plan['patches']),
              'files': sorted({p['file'] for p in added}), 'patches': added,
              'gamecore_loaded': False, 'game_launched': False}
    (root / 'caller_patch_plan.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('status', 'added_patches', 'total_patches')}))


if __name__ == '__main__':
    main()
