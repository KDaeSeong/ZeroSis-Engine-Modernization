"""Complete owned rule collection cleanup and scoped unpublished cache entries."""
import json
import re
from pathlib import Path
from collect_baseline import PROJECT, digest
from build_bootstrap_component import body

PREFIX = 'info_cleanup_'
BASE = PROJECT / 'evidence/sdk_x64/attempts/attempt_028/sdk_x64_patches.json'
GLOBALS = 'CvGameCoreDLL_Expansion2/CvGlobals.cpp'
HEADER = 'CvGameCoreDLL_Expansion2/CvGlobals.h'
LOADER = 'CvGameCoreDLL_Expansion2/CvDllDatabaseUtility.h'


def baseline_text(relative):
    text = (PROJECT / 'Source/SDK_BNW_Original' / relative).read_bytes().decode('latin1')
    for p in json.loads(BASE.read_text(encoding='utf-8'))['patches']:
        if p['file'] == relative:
            if text.count(p['old']) != p['count']:
                raise RuntimeError('Info cleanup baseline changed: ' + p['id'])
            text = text.replace(p['old'], p['new'])
    return text


def collections():
    found = re.findall(r'std::vector<\s*(\w+)\s*\*\s*>\s+(m_\w+)', baseline_text(HEADER))
    if len(found) != 40 or len({name for _, name in found}) != 40:
        raise RuntimeError('Expected forty direct rule pointer collections')
    return found


def patches():
    result = []
    def add(name, relative, old, new, reason):
        text = baseline_text(relative)
        new = new.replace('\r\n', '\n')
        if '\r\n' in text:
            new = new.replace('\n', '\r\n')
        if text.count(old) != 1:
            raise RuntimeError('Info cleanup patch mismatch: ' + name)
        result.append({'id': PREFIX + name, 'file': relative,
                       'source_sha256': digest(PROJECT / 'Source/SDK_BNW_Original' / relative),
                       'old': old, 'new': new, 'count': 1, 'reason': reason})
    text = baseline_text(GLOBALS)
    old = body(text, 'void CvGlobals::deleteInfoArrays()')
    missing = {name for _, name in collections()} - set(re.findall(r'deleteInfoArray\((m_\w+)\)', old))
    if missing != {'m_paMultiUnitFormationInfo'}:
        raise RuntimeError('Original missing rule collection changed')
    new = old.replace('\tSAFE_DELETE_ARRAY(GC.getFootstepAudioTags());', '''\t// This instance owns both arrays; do not address the global singleton here.
\tSAFE_DELETE_ARRAY(m_paszFootstepAudioTags);
\tm_iNumFootstepAudioTags = 0;
\tSAFE_DELETE_ARRAY(m_paszFlavorTypes);
\tm_iNumFlavorTypes = 0;''')
    new = new.replace('\tdeleteInfoArray(m_paEntityEventInfo);', '''\tdeleteInfoArray(m_paEntityEventInfo);
\tdeleteInfoArray(m_paMultiUnitFormationInfo);
\tm_iNumPlayableCivilizationInfos = 0;
\tm_iNumAIPlayableCivilizationInfos = 0;
\tinfoTypeFromStringReset();''')
    add('owned_collections_and_metadata', GLOBALS, old, new,
        'Release all forty directly owned rule collections and both string arrays; clear lookup items and related counts on this instance.')
    old = body(text, 'void CvGlobals::uninit()')
    new = old[:-1] + '''\t// All game/host/pathfinder borrowers above have finished using rule info.
\tdeleteInfoArrays();
}'''
    add('after_borrower_shutdown', GLOBALS, old, new,
        'Keep rule information available through existing borrower teardown, then release direct rule storage at the end of uninit.')
    add('scoped_entry_include', LOADER, '#include "CvInfos.h"', '#include "CvInfos.h"\n#include <memory>',
        'Declare local scoped ownership without changing SDK class layout.')
    text = baseline_text(LOADER)
    old = body(text, 'template<class T>\r\nbool CvDllDatabaseUtility::PrefetchCollection(')
    new = old.replace('T* pkItem = FNEW(T, c_eCiv5GameplayDLL, 0);',
                      'std::unique_ptr<T> pkItem(FNEW(T, c_eCiv5GameplayDLL, 0));')
    new = new.replace('kCollection.push_back(pkItem);',
                      'kCollection.push_back(pkItem.get());\n\t\t\tpkItem.release();')
    add('unpublished_entry_owner', LOADER, old, new,
        'Destroy a constructed but unpublished entry if CacheResults or vector growth throws; retain existing successful order and return-value semantics.')
    return result


def main():
    path = PROJECT / 'Source/Porting/sdk_x64_patches.json'
    plan, base = (json.loads(p.read_text(encoding='utf-8')) for p in (path, BASE))
    retained = [p for p in plan['patches'] if not p['id'].startswith((PREFIX, 'db_cache_', 'startup_owners_', 'gc_lifecycle_', 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))]
    if retained != base['patches'] or len(retained) != 568:
        raise RuntimeError('Accepted 568 SDK patches changed')
    added = patches()
    later = [p for p in plan['patches'] if p['id'].startswith(('db_cache_', 'startup_owners_', 'gc_lifecycle_', 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))]
    plan['patches'] = retained + added + later
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    lp = PROJECT / 'evidence/numeric_boundaries/edit_ledger.json'
    ledger = json.loads(lp.read_text(encoding='utf-8'))
    ledger['patch_specification_sha256'] = digest(path)
    ledger['supplemental_non_numeric_patches'] = [x for x in ledger['supplemental_non_numeric_patches']
        if not x.startswith((PREFIX, 'db_cache_', 'startup_owners_', 'gc_lifecycle_', 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))] + [p['id'] for p in added + later]
    ledger['unchanged_info_cleanup_baseline'] = {'path': str(BASE), 'sha256': digest(BASE)}
    lp.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    root = PROJECT / 'evidence/info_cleanup'
    root.mkdir(parents=True, exist_ok=True)
    report = {'status': 'SDK_INFO_CLEANUP_CALLERS_DECLARED', 'baseline': ledger['unchanged_info_cleanup_baseline'],
              'recipe': {'path': str(Path(__file__).resolve()), 'sha256': digest(Path(__file__).resolve())},
              'patch_specification': {'path': str(path), 'sha256': digest(path)}, 'previous_patches': 568,
              'added_patches': len(added), 'total_patches': len(plan['patches']),
              'files': sorted({p['file'] for p in added}), 'patches': added,
              'gamecore_loaded': False, 'game_launched': False}
    (root / 'caller_patch_plan.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('status', 'added_patches', 'total_patches')}))


if __name__ == '__main__':
    main()
