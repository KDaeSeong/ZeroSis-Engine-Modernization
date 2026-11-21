"""Record current source-level blockers to complete GC failure/restart recovery."""
import json
import re
from pathlib import Path
from collect_baseline import PROJECT
from probe_world_builder import artifact
from build_bootstrap_component import body


def main():
    sdk = PROJECT / 'Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2'
    signatures = {
        'CvGlobals.cpp': ('void CvGlobals::init()', 'void CvGlobals::uninit()', 'void CvGlobals::deleteInfoArrays()',
                          'ICvDLLDatabaseUtility1* CvGlobals::getDatabaseLoadUtility()',
                          'void CvGlobals::releaseDatabaseLoadUtility()', 'CvGlobals::~CvGlobals()'),
        'CvDllContext.cpp': ('void CvDllGameContext::Init()', 'void CvDllGameContext::Uninit()', 'bool CvDllGameContext::ShutdownSingleton()'),
        'CvDllDatabaseUtility.cpp': ('bool CvDllDatabaseUtility::CacheGameDatabaseData()',
                                     'bool CvDllDatabaseUtility::FlushGameDatabaseData()',
                                     'unsigned int CvDllDatabaseUtility::DecrementReference()',
                                     'bool CvDllDatabaseUtility::PrefetchGameData()', 'static bool ZeroSisCacheFlavorTypes()',
                                     'bool CvDllDatabaseUtility::SetGlobalActionInfo()'),
        'CvTypes.cpp': ('void CvTypes::AcquireTypes(',),
        'CvPlayerAI.cpp': ('void CvPlayerAI::initStatics()', 'void CvPlayerAI::freeStatics()'),
        'CvPlayer.cpp': ('CvPlayer::CvPlayer()', 'CvPlayer::~CvPlayer()'),
        'CvTeam.cpp': ('CvTeam::CvTeam()', 'CvTeam::~CvTeam()', 'void CvTeam::initStatics()', 'void CvTeam::freeStatics()')}
    functions = []
    for name, wanted in signatures.items():
        p = sdk / name
        text = p.read_bytes().decode('latin1')
        for signature in wanted:
            functions.append({'source': artifact(p), 'signature': signature,
                              'line': text.count('\n', 0, text.index(signature)) + 1,
                              'body': body(text, signature).replace('\r\n', '\n')})
    refs = []
    for p in sorted(sdk.iterdir()):
        if p.suffix.lower() not in ('.cpp', '.h'):
            continue
        for line_no, line in enumerate(p.read_bytes().decode('latin1').splitlines(), 1):
            if re.search(r'\bm_pkDatabaseLoadUtility\b|\bdeleteInfoArrays\s*\(', line):
                refs.append({'source': artifact(p), 'line': line_no, 'text': line.strip()})
    find = lambda signature: next(r['body'] for r in functions if r['signature'] == signature)
    info_fields = re.findall(r'\bdeleteInfoArray\((m_\w+)\)', find('void CvGlobals::deleteInfoArrays()'))
    uninit = find('void CvGlobals::uninit()')
    report = {'status': 'GC_INITIALIZATION_SOURCE_BLOCKERS_RECORDED_NOT_RUNTIME_PROOF',
              'auditor': artifact(Path(__file__).resolve()), 'functions': functions, 'textual_references': refs,
              'info_array_cleanup_fields': info_fields,
              'uninit_mentions_database_loader_owner': 'm_pkDatabaseLoadUtility' in uninit,
              'uninit_releases_database_loader_owner': 'releaseDatabaseLoadUtility();' in uninit,
              'context_shutdown_releases_database_loader_owner': 'GC.releaseDatabaseLoadUtility();' in find('bool CvDllGameContext::ShutdownSingleton()'),
              'uninit_calls_info_array_cleanup': 'deleteInfoArrays(' in uninit,
              'uninit_flushes_loader_cache_flag': 'FlushGameDatabaseData(' in uninit,
              'root_lifecycle_component_evidence': artifact(PROJECT / 'evidence/gc_lifecycle/conformance.json'),
              'findings': [
                  {'id': 'GC-ROOT-CONTROL', 'observation': 'Context Init/Uninit now coordinate Idle/Starting/Ready/Stopping/CleanupPending, automatic failure cleanup, forty-five ordered cleanup checkpoints, and sixty-eight cached type resets. Active or pending GC blocks host rebinding/context shutdown.',
                   'component_evidence': artifact(PROJECT / 'evidence/gc_lifecycle/conformance.json'),
                   'next_action': 'Integrate with the real state-owning host, audit transitive child recovery, and enforce ordinary game-call and borrowed-interface quiescence.'},
                  {'id': 'GC-INIT-RETURNS', 'observation': 'The database startup phase now checks the connection, loader, Defines preparation, postprocessing and cache return values before player/team static creation.',
                   'component_evidence': artifact(PROJECT / 'evidence/database_cache/conformance.json'),
                   'next_action': 'Coordinate root cleanup and host-visible state after the propagated failure; the contiguous DB phase test is not whole-init rollback.'},
                  {'id': 'GC-LOADER-OWNER', 'observation': 'uninit and context shutdown now detach/reset and release the retained loader reference before host/heap teardown.',
                   'component_evidence': artifact(PROJECT / 'evidence/database_loader/conformance.json'),
                   'next_action': 'Integrate with the full state-owning host and require outstanding callers to finish before heap shutdown.'},
                  {'id': 'GC-INFO-ARRAYS', 'observation': 'uninit now clears all forty directly declared rule pointer collections, both owned string arrays, lookup items and related counts after existing borrowers finish.',
                   'component_evidence': artifact(PROJECT / 'evidence/info_cleanup/conformance.json'),
                   'source_inventory': artifact(PROJECT / 'evidence/info_cleanup/source_audit.json'),
                   'next_action': 'Integrate this cleanup with the complete init failure controller and concrete entry/borrower lifecycle; component entries are instrumented.'},
                  {'id': 'GC-CACHE-RETRY', 'observation': 'Releasing the GC cached loader makes the next factory request start with a fresh caching flag; old caller references remain separate owners.',
                   'next_action': 'The cache flag now stays pending on required failures; implement full GC init state handling and prevent old external references from doing game work across generations.'},
                  {'id': 'GC-PREFETCH-ERRORS', 'observation': 'All sixty-two collection calls now propagate prepare/step/CacheResults failures. Flavor publication preserves the previous array on failure; CvTypes propagates required SQL failures.',
                   'component_evidence': artifact(PROJECT / 'evidence/database_cache/conformance.json'),
                   'next_action': 'Audit nested concrete CacheResults helpers for internally ignored failures and integrate partial-state cleanup with the full initialization controller.'},
                  {'id': 'GC-INIT-LOCAL-REFERENCE', 'observation': 'The local queried database loader reference now uses the live SDK Destroy dispatcher through ZeroSisHostBinding::Owned.',
                   'next_action': 'Verify its lifetime throughout the remaining full GC success/failure stages and host integration.'},
                  {'id': 'GC-ACTION-CONSTRUCTION', 'observation': 'SetGlobalActionInfo now checks signed buffer arithmetic and scopes the sorting buffer and unpublished action until publication succeeds.',
                   'component_evidence': artifact(PROJECT / 'evidence/startup_owners/conformance.json'),
                   'next_action': 'Integrate caller cleanup after partial action metadata mutation; inspect concrete hotkey/entry implementations before claiming whole-cache recovery.'},
                  {'id': 'GC-CHILD-CONSTRUCTION', 'observation': 'Player direct children (26) and the team-tech child are now scoped until constructor reset completes; normal player teardown releases culture, and duplicate player/team static initialization is rejected.',
                   'component_evidence': artifact(PROJECT / 'evidence/startup_owners/conformance.json'),
                   'source_inventory': artifact(PROJECT / 'evidence/startup_owners/source_audit.json'),
                   'next_action': 'Root lifecycle control now has forty-five cleanup checkpoints; audit nested concrete children, real reset(false), and external borrower quiescence.'}],
              'scope': 'TEXTUAL_CPP_HEADER_REFERENCES_AND_EXACT_FUNCTION_BODIES_NOT_COMPLETE_CALL_GRAPH_OR_LIFETIME_TEST',
              'gamecore_loaded': False, 'game_launched': False, 'whole_gc_lifecycle_verified': False}
    root = PROJECT / 'evidence/gc_initialization'
    root.mkdir(parents=True, exist_ok=True)
    (root / 'source_audit.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': report['status'], 'functions': len(functions), 'info_array_fields': len(info_fields),
                      'textual_owner_and_cleanup_references': len(refs), 'findings': [f['id'] for f in report['findings']]}))


if __name__ == '__main__':
    main()
