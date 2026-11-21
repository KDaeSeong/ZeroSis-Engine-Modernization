"""Prepare host replacement before publication and release it before its heap."""
import json
from pathlib import Path
from collect_baseline import PROJECT, digest
from build_bootstrap_component import body

PREFIX = 'host_callers_'
BASE = PROJECT / 'evidence/sdk_x64/attempts/attempt_025/sdk_x64_patches.json'
CONTEXT = 'CvGameCoreDLL_Expansion2/CvDllContext.cpp'
DLL = 'CvGameCoreDLL_Expansion2/CvGameCoreDLL.cpp'


def baseline_text(relative):
    text = (PROJECT / 'Source/SDK_BNW_Original' / relative).read_bytes().decode('latin1')
    for patch in json.loads(BASE.read_text(encoding='utf-8'))['patches']:
        if patch['file'] == relative:
            if text.count(patch['old']) != patch['count']:
                raise RuntimeError('Host binding baseline drift: ' + patch['id'])
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
            raise RuntimeError('Host patch match changed: ' + name)
        result.append({'id': PREFIX + name, 'file': relative,
                       'source_sha256': digest(PROJECT / 'Source/SDK_BNW_Original' / relative),
                       'old': old, 'new': new, 'count': 1, 'reason': reason})
    text = baseline_text(CONTEXT)
    add('include', CONTEXT, '#include <new>', '#include <new>\n#include "ZeroSisHostBinding.h"',
        'Use one nonblocking mutation gate and the SDK Destroy ownership boundary.')
    add('transactional_replace', CONTEXT, body(text, 'bool CvDllGameContext::SetDLLIFace('), '''bool CvDllGameContext::SetDLLIFace(ICvEngineUtility1* pDll)
{
    ZeroSisHostBinding::Lease mutation(ZeroSisHostBinding::ProcessGate());
    if(!mutation) { SetLastError(ERROR_BUSY); return false; }
    ICvEngineUtility4* pOldDll = GC.getDLLIFace();
    if(pDll == static_cast<ICvEngineUtility1*>(pOldDll))
    {
        SetLastError(ERROR_SUCCESS);
        return pOldDll != NULL;
    }
    ZeroSisHostBinding::Owned<ICvEngineUtility4> next(
        pDll != NULL ? pDll->QueryInterface<ICvEngineUtility4>() : NULL);
    if(pDll != NULL && !next) { SetLastError(ERROR_NOT_SUPPORTED); return false; }
    if(next.get() == pOldDll)
    {
        next.release(); // Identity alias does not create a second owner.
        SetLastError(ERROR_SUCCESS);
        return pOldDll != NULL;
    }
    ICvEngineUtility4* replacement = next.release();
    GC.setDLLIFace(replacement);
    ZeroSisHostBinding::Release(pOldDll);
    SetLastError(ERROR_SUCCESS);
    return replacement != NULL;
}''', 'Retain the old owned host on unsupported/throwing query, publish before releasing it, reject concurrent/reentrant mutation, preserve false on explicit null detachment.')
    add('shutdown_owned_host', CONTEXT, body(text, 'bool CvDllGameContext::ShutdownSingleton()'), '''bool CvDllGameContext::ShutdownSingleton()
{
    ZeroSisHostBinding::Lease mutation(ZeroSisHostBinding::ProcessGate());
    if(!mutation) { SetLastError(ERROR_BUSY); return false; }
    SAFE_DELETE(s_pSingleton);
    ICvEngineUtility4* ownedHost = GC.getDLLIFace();
    GC.setDLLIFace(NULL);
    ZeroSisHostBinding::Release(ownedHost);
    if(s_hHeap == INVALID_HANDLE_VALUE) { SetLastError(ERROR_SUCCESS); return true; }
    SetLastError(ERROR_SUCCESS);
    if(!HeapDestroy(s_hHeap)) return false;
    s_hHeap = INVALID_HANDLE_VALUE;
    SetLastError(ERROR_SUCCESS);
    return true;
}''', 'Destroy context borrowers first, detach/release the owned host while the private heap is alive, then destroy the heap; failed heap cleanup can be retried without releasing the host twice.')
    text = baseline_text(DLL)
    add('bootstrap_release_delegate', DLL,
        '            GC.setDLLIFace(NULL);', '',
        'ShutdownSingleton now owns host release; do not silently discard its owned interface in the bootstrap backend.')
    return result


def main():
    path = PROJECT / 'Source/Porting/sdk_x64_patches.json'
    plan = json.loads(path.read_text(encoding='utf-8'))
    base = json.loads(BASE.read_text(encoding='utf-8'))
    retained = [p for p in plan['patches'] if not p['id'].startswith((PREFIX, 'db_postprocess_', 'db_loader_', 'info_cleanup_' ,'db_cache_', 'startup_owners_', 'gc_lifecycle_', 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))]
    if retained != base['patches'] or len(retained) != 556:
        raise RuntimeError('Accepted 556 SDK patches changed')
    added = patches()
    later = [p for p in plan['patches'] if p['id'].startswith(('db_postprocess_', 'db_loader_', 'info_cleanup_' ,'db_cache_', 'startup_owners_', 'gc_lifecycle_', 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))]
    plan['patches'] = retained + added + later
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    ledger_path = PROJECT / 'evidence/numeric_boundaries/edit_ledger.json'
    ledger = json.loads(ledger_path.read_text(encoding='utf-8'))
    ledger['patch_specification_sha256'] = digest(path)
    ledger['supplemental_non_numeric_patches'] = [
        x for x in ledger['supplemental_non_numeric_patches'] if not x.startswith((PREFIX, 'db_postprocess_', 'db_loader_', 'info_cleanup_' ,'db_cache_', 'startup_owners_', 'gc_lifecycle_', 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))] + [p['id'] for p in added + later]
    ledger['unchanged_host_binding_baseline'] = {'path': str(BASE), 'sha256': digest(BASE)}
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    root = PROJECT / 'evidence/host_binding'
    root.mkdir(parents=True, exist_ok=True)
    report = {'status': 'SDK_HOST_BINDING_CALLERS_DECLARED', 'baseline': ledger['unchanged_host_binding_baseline'],
              'recipe': {'path': str(Path(__file__).resolve()), 'sha256': digest(Path(__file__).resolve())},
              'patch_specification': {'path': str(path), 'sha256': digest(path)},
              'previous_patches': 556, 'added_patches': len(added), 'total_patches': len(plan['patches']),
              'files': sorted({p['file'] for p in added}), 'patches': added,
              'gamecore_loaded': False, 'game_launched': False}
    (root / 'caller_patch_plan.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('status', 'added_patches', 'total_patches')}))


if __name__ == '__main__':
    main()
