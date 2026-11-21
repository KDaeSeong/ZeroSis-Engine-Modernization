"""Preserve the accepted SDK and move bootstrap work outside the DLL loader lock."""
import json
from pathlib import Path
from collect_baseline import PROJECT, digest

PREFIX = 'bootstrap_callers_'
BASE = PROJECT / 'evidence/sdk_x64/attempts/attempt_021/sdk_x64_patches.json'


def baseline_text(relative):
    source = PROJECT / 'Source/SDK_BNW_Original' / relative
    text = source.read_bytes().decode('latin1')
    baseline = json.loads(BASE.read_text(encoding='utf-8'))
    for p in baseline['patches']:
        if p['file'] == relative:
            if text.count(p['old']) != p['count']:
                raise RuntimeError('Bootstrap baseline patch drift')
            text = text.replace(p['old'], p['new'])
    return text


def patches():
    result = []
    def add(name, file, old, new, reason):
        if '\r\n' in baseline_text(file):
            old = old.replace('\r\n', '\n').replace('\n', '\r\n')
            new = new.replace('\r\n', '\n').replace('\n', '\r\n')
        result.append({'id': PREFIX + name, 'file': file,
                       'source_sha256': digest(PROJECT / 'Source/SDK_BNW_Original' / file),
                       'old': old, 'new': new, 'count': 1, 'reason': reason})
    dll = 'CvGameCoreDLL_Expansion2/CvGameCoreDLL.cpp'
    add('includes', dll, '#include "CvDllContext.h"', '#include "CvDllContext.h"\n#include "ZeroSisBootstrap.h"\n#include "../../Providers/Debug/SdkDebugHelper.h"',
        'Use the checked bootstrap lifecycle and real debug cleanup contract.')
    text = baseline_text(dll)
    old = text[text.index('extern "C" ICvGameContext1* DllGetGameContext()'):]
    new = '''namespace
{
HMODULE g_ZeroSisModule = NULL;
class GameCoreBootstrapBackend final : public ZeroSisBootstrap::Backend
{
public:
    bool BeginTimer() noexcept override
    {
        const MMRESULT result = timeBeginPeriod(1);
        if(result != TIMERR_NOERROR) { SetLastError(ERROR_NOT_SUPPORTED); return false; }
        return true;
    }
    bool EndTimer() noexcept override
    {
        const MMRESULT result = timeEndPeriod(1);
        if(result != TIMERR_NOERROR) { SetLastError(ERROR_GEN_FAILURE); return false; }
        return true;
    }
    bool BeginSymbols(HMODULE module) override { return FDebugHelper::GetInstance().LoadSymbols(module); }
    bool EndSymbols() noexcept override { return ZeroSisDebug::Shutdown(); }
    void* CreateContext() override
    {
        CvDllGameContext::InitializeSingleton();
        return static_cast<ICvGameContext1*>(CvDllGameContext::GetSingleton());
    }
    bool DestroyContext() noexcept override
    {
        try
        {
            if(!CvDllGameContext::ShutdownSingleton()) return false;
            GC.setDLLIFace(NULL);
            return true;
        }
        catch(...) { SetLastError(ERROR_DLL_INIT_FAILED); return false; }
    }
};
GameCoreBootstrapBackend& BootstrapBackend() { static GameCoreBootstrapBackend backend; return backend; }
ZeroSisBootstrap::Lifecycle& BootstrapLifecycle() { static ZeroSisBootstrap::Lifecycle lifecycle; return lifecycle; }
}

extern "C" ICvGameContext1* DllGetGameContext()
{
    return static_cast<ICvGameContext1*>(BootstrapLifecycle().Start(BootstrapBackend(), g_ZeroSisModule));
}
extern "C" BOOL ZeroSisShutdownGameCore()
{
    return BootstrapLifecycle().Shutdown() ? TRUE : FALSE;
}
extern "C" DWORD ZeroSisGetBootstrapError()
{
    return BootstrapLifecycle().LastError();
}
// DllMain only records the module. The host must explicitly shut down after
// releasing SDK objects and before FreeLibrary; no game teardown runs here.
BOOL APIENTRY DllMain(HANDLE module, DWORD reason, LPVOID)
{
    if(reason == DLL_PROCESS_ATTACH) g_ZeroSisModule = static_cast<HMODULE>(module);
    return TRUE;
}
'''
    add('entrypoints', dll, old, new, 'Run timer, symbols and game context only after DllMain; add explicit quiescent shutdown and failure reporting.')
    definition = 'CvGameCoreDLL_Expansion2/CvGameCoreDLL.def'
    add('exports', definition, baseline_text(definition), 'EXPORTS\n\tDllGetGameContext\n\tZeroSisShutdownGameCore\n\tZeroSisGetBootstrapError\n',
        'Preserve the original context export and expose additive C shutdown/error functions to the new x64 host.')
    header = 'CvGameCoreDLL_Expansion2/CvDllContext.h'
    add('shutdown_declaration', header, '\tstatic void DestroySingleton();',
        '\tstatic void DestroySingleton();\n\tstatic bool ShutdownSingleton();',
        'Add a checked shutdown without changing existing class fields, vtable or DestroySingleton signature.')
    context = 'CvGameCoreDLL_Expansion2/CvDllContext.cpp'
    add('context_includes', context, '#include "CvDllContext.h"', '#include "CvDllContext.h"\n#include <memory>\n#include <new>',
        'Use temporary ownership during partial adapter construction and report allocation failure.')
    text = baseline_text(context)
    old = '''\tm_pNetworkSyncronizer = new CvDllNetworkSyncronization();
\tm_pNetMessageHandler = new CvDllNetMessageHandler();
\tm_pScriptSystemUtility = new CvDllScriptSystemUtility();
\tm_pWorldBuilderMapLoader = new CvDllWorldBuilderMapLoader();'''
    new = '''\tstd::unique_ptr<CvDllNetworkSyncronization> network(new CvDllNetworkSyncronization());
\tstd::unique_ptr<CvDllNetMessageHandler> messages(new CvDllNetMessageHandler());
\tstd::unique_ptr<CvDllScriptSystemUtility> scripts(new CvDllScriptSystemUtility());
\tstd::unique_ptr<CvDllWorldBuilderMapLoader> maps(new CvDllWorldBuilderMapLoader());
\tm_pNetworkSyncronizer = network.release();
\tm_pNetMessageHandler = messages.release();
\tm_pScriptSystemUtility = scripts.release();
\tm_pWorldBuilderMapLoader = maps.release();'''
    add('context_partial_construction', context, old, new,
        'Retain temporary ownership until all four adapters exist, releasing already-created adapters on an exception.')
    start = text.index('void CvDllGameContext::InitializeSingleton()')
    end = text.index('CvDllGameContext* CvDllGameContext::GetSingleton()', start)
    old = text[start:end]
    new = '''void CvDllGameContext::InitializeSingleton()
{
\tif(s_pSingleton != NULL) return;
\tif(s_hHeap != INVALID_HANDLE_VALUE) { SetLastError(ERROR_BUSY); throw std::bad_alloc(); }
\tHANDLE heap = HeapCreate(0, 0, 0);
\tif(heap == NULL) throw std::bad_alloc();
\ts_hHeap = heap;
\tULONG information = 2;
\tHeapSetInformation(s_hHeap, HeapCompatibilityInformation, &information, sizeof(information));
\ttry
\t{
\t\ts_pSingleton = FNEW(CvDllGameContext(), c_eCiv5GameplayDLL, 0);
\t\tif(s_pSingleton == NULL) throw std::bad_alloc();
\t}
\tcatch(...)
\t{
\t\tif(HeapDestroy(s_hHeap)) s_hHeap = INVALID_HANDLE_VALUE;
\t\tthrow;
\t}
}
//------------------------------------------------------------------------------
bool CvDllGameContext::ShutdownSingleton()
{
\tSAFE_DELETE(s_pSingleton);
\tif(s_hHeap == INVALID_HANDLE_VALUE) return true;
\tif(!HeapDestroy(s_hHeap)) return false;
\ts_hHeap = INVALID_HANDLE_VALUE;
\treturn true;
}
//------------------------------------------------------------------------------
void CvDllGameContext::DestroySingleton()
{
\tShutdownSingleton();
}
//------------------------------------------------------------------------------
'''
    add('context_lifecycle', context, old, new,
        'Make initialization idempotent, reclaim failed construction, and retain failed heap cleanup for explicit retry.')
    old = '\treturn HeapAlloc(s_hHeap, 0, bytes);'
    new = '''\tif(s_hHeap == INVALID_HANDLE_VALUE || s_hHeap == NULL) { SetLastError(ERROR_INVALID_STATE); throw std::bad_alloc(); }
\tvoid* memory = HeapAlloc(s_hHeap, 0, bytes);
\tif(memory == NULL) throw std::bad_alloc();
\treturn memory;'''
    add('adapter_allocation', context, old, new,
        'Throw on failed adapter allocation so constructors never run through a null custom operator-new result.')
    for p in result:
        if baseline_text(p['file']).count(p['old']) != 1:
            raise RuntimeError('Bootstrap patch match differs: ' + p['id'])
    return result


def main():
    path = PROJECT / 'Source/Porting/sdk_x64_patches.json'
    plan = json.loads(path.read_text(encoding='utf-8'))
    baseline = json.loads(BASE.read_text(encoding='utf-8'))
    retained = [p for p in plan['patches'] if not p['id'].startswith((PREFIX, 'debug_callers_','globals_callers_','construction_callers_','host_callers_','db_postprocess_', 'db_loader_', 'info_cleanup_' ,'db_cache_', 'startup_owners_', 'gc_lifecycle_', 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))]
    if retained != baseline['patches'] or len(retained) != 543:
        raise RuntimeError('Accepted 543 SDK patches changed')
    added = patches()
    later = [p for p in plan['patches'] if p['id'].startswith(('debug_callers_','globals_callers_','construction_callers_','host_callers_','db_postprocess_', 'db_loader_', 'info_cleanup_' ,'db_cache_', 'startup_owners_', 'gc_lifecycle_', 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))]
    plan['patches'] = retained + added + later
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    ledger_path = PROJECT / 'evidence/numeric_boundaries/edit_ledger.json'
    ledger = json.loads(ledger_path.read_text(encoding='utf-8'))
    ledger['patch_specification_sha256'] = digest(path)
    prefixes = ('serialization_', 'temp_callers_', 'auto_callers_', 'db_callers_', 'localization_callers_',
                'world_mod_access_', 'world_map_access_', 'world_map_bridge_access_', 'logging_callers_', PREFIX, 'debug_callers_','globals_callers_','construction_callers_','host_callers_','db_postprocess_', 'db_loader_', 'info_cleanup_' ,'db_cache_', 'startup_owners_', 'gc_lifecycle_', 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_')
    ledger['supplemental_non_numeric_patches'] = [p['id'] for p in plan['patches'] if p['id'].startswith(prefixes)]
    ledger['unchanged_bootstrap_caller_baseline'] = {'path': str(BASE), 'sha256': digest(BASE)}
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    root = PROJECT / 'evidence/bootstrap'
    root.mkdir(parents=True, exist_ok=True)
    report = {'status': 'SDK_BOOTSTRAP_CALLERS_DECLARED', 'baseline': ledger['unchanged_bootstrap_caller_baseline'],
              'recipe': {'path': str(Path(__file__).resolve()), 'sha256': digest(Path(__file__).resolve())},
              'patch_specification': {'path': str(path), 'sha256': digest(path)},
              'previous_patches': 543, 'added_patches': len(added), 'total_patches': len(plan['patches']),
              'files': sorted({p['file'] for p in added}), 'patches': added,
              'gamecore_loaded': False, 'game_launched': False}
    (root / 'caller_patch_plan.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('status', 'added_patches', 'total_patches', 'files')}))


if __name__ == '__main__':
    main()
