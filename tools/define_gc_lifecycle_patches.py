"""Compose root GC lifecycle changes over the immutable attempt_031 recipe."""
import json
import re
from pathlib import Path
from collect_baseline import PROJECT, digest
from build_bootstrap_component import body

PREFIX = 'gc_lifecycle_'
BASE = PROJECT / 'evidence/sdk_x64/attempts/attempt_031/sdk_x64_patches.json'
GLOBALS = 'CvGameCoreDLL_Expansion2/CvGlobals.cpp'
HEADER = 'CvGameCoreDLL_Expansion2/CvGlobals.h'
CONTEXT = 'CvGameCoreDLL_Expansion2/CvDllContext.cpp'
TYPES = 'CvGameCoreDLL_Expansion2/CvTypes.cpp'
TYPES_HEADER = 'CvGameCoreDLL_Expansion2/CvTypes.h'


def baseline_text(relative):
    text = (PROJECT / 'Source/SDK_BNW_Original' / relative).read_bytes().decode('latin1')
    for patch in json.loads(BASE.read_text(encoding='utf-8'))['patches']:
        if patch['file'] == relative:
            if text.count(patch['old']) != patch['count']: raise RuntimeError('GC lifecycle baseline drift: ' + patch['id'])
            text = text.replace(patch['old'], patch['new'])
    return text


def type_defaults():
    result = re.findall(r'^(?:GreatWorkArtifactClass|GreatWorkSlotType|MissionTypes|unsigned int)\s+(s_\w+)\s*=\s*([^;]+);', baseline_text(TYPES), re.M)
    if len(result) != 68: raise RuntimeError('Expected all sixty-eight cached type globals')
    return result


def cleanup_statements():
    original = body(baseline_text(GLOBALS), 'void CvGlobals::uninit()').replace('\r\n', '\n')
    statements = []
    for line in original.splitlines():
        stripped = line.strip()
        if stripped.startswith(('CvPlayerAI::freeStatics();', 'CvTeam::freeStatics();', 'SAFE_DELETE(', 'm_kGlobalDefinesLookup.Release();', 'releaseDatabaseLoadUtility();', 'deleteInfoArrays();')):
            statements.append(line)
        elif stripped.startswith('gDLL->UninitGlobals();'):
            statements.append('''        if(lifecycle.Host() != NULL)
        {
            if(gDLL != lifecycle.Host()) throw std::logic_error("GameCore host changed before cleanup");
            gDLL->UninitGlobals();
        }''')
    if len(statements) != 44: raise RuntimeError('GC cleanup inventory changed')
    statements.append('    CvTypes::ResetTypes();')
    return statements


def patches():
    rows = []
    def add(name, relative, old, new, reason):
        text = baseline_text(relative)
        if text.count(old) != 1: raise RuntimeError('GC lifecycle patch mismatch: ' + name)
        new = new.replace('\r\n', '\n')
        if '\r\n' in text: new = new.replace('\n', '\r\n')
        rows.append({'id': PREFIX + name, 'file': relative, 'source_sha256': digest(PROJECT / 'Source/SDK_BNW_Original' / relative),
                     'old': old, 'new': new, 'count': 1, 'reason': reason})
    for rel, name in ((GLOBALS, 'globals_include'), (CONTEXT, 'context_include')):
        add(name, rel, '#include "ZeroSisHostBinding.h"', '#include "ZeroSisHostBinding.h"\n#include "ZeroSisGlobalsLifecycle.h"',
            'Share one lifecycle state and host mutation gate without changing SDK object layout or exported interface slots.')
    old = '\tvoid init();\r\n\tvoid uninit();'
    add('private_gc_entrypoints', HEADER, old, 'private:\n\tfriend class CvDllGameContext;\n\tvoid init();\n\tvoid uninit();\npublic:',
        'Require the state-owning context wrapper at the only two SDK lifecycle call sites; keep class layout and virtual interfaces unchanged.')
    for sig, method, callback in (('void CvDllGameContext::Init()', 'Initialize', '[&]() { GC.init(); }, [&]() { GC.uninit(); }'),
                                   ('void CvDllGameContext::Uninit()', 'Uninitialize', '[&]() { GC.uninit(); }')):
        old = body(baseline_text(CONTEXT), sig)
        new = sig + '''
{
    ZeroSisHostBinding::Lease mutation(ZeroSisHostBinding::ProcessGate());
    if(!mutation) throw std::logic_error("GameCore lifecycle mutation is busy");
    ZeroSisGlobalsLifecycle::ProcessState().''' + method + '(&GC, ' + callback + ');\n}'
        add(method.lower(), CONTEXT, old, new, 'Serialize lifecycle mutation, reject duplicate/reentrant starts, and drain partial startup with retryable cleanup.')
    old = body(baseline_text(GLOBALS), 'void CvGlobals::init()')
    new = old.replace('CvAssertMsg(gDLL != NULL, "Civ app needs to set gDLL");',
                      'if(gDLL == NULL) throw std::runtime_error("GameCore initialization requires an engine host");\n\tCvTypes::ResetTypes();')
    new = new.replace('gDLL->InitGlobals();', 'ZeroSisGlobalsLifecycle::ProcessState().EnterHost(gDLL);\n\tgDLL->InitGlobals();')
    add('host_partial_initialization', GLOBALS, old, new, 'Reject a missing host, reset cached type generation, and record host entry before a possibly partial InitGlobals call.')
    old = body(baseline_text(GLOBALS), 'void CvGlobals::uninit()')
    new = 'void CvGlobals::uninit()\n{\n    ZeroSisGlobalsLifecycle::Controller& lifecycle = ZeroSisGlobalsLifecycle::ProcessState();\n'
    for i, statement in enumerate(cleanup_statements()):
        new += '    lifecycle.CleanupStep(' + str(i) + ', [&]() {\n' + statement + '\n    });\n'
    new += '}'
    add('ordered_cleanup', GLOBALS, old, new, 'Preserve the original borrower/owner teardown order with forty-five checkpoints; retain later resources on host cleanup failure and resume at the failed step.')
    ctor = body(baseline_text(GLOBALS), 'CvGlobals::CvGlobals()')
    old = ctor[-160:]
    fields = ['m_pAICityStrategies', 'm_pUnits', 'm_pProjects', 'm_pPromotions', 'm_pNotifications', 'm_pImprovements',
              'm_paszFootstepAudioTags', 'm_paszFlavorTypes']
    additions = '\n'.join('\t' + field + ' = NULL;' for field in fields)
    new = old.replace('{\r\n}', '{\n' + additions + '\n\tm_iNumFootstepAudioTags = 0;\n\tm_iNumFlavorTypes = 0;\n}')
    add('explicit_empty_owners', GLOBALS, old, new, 'Initialize every direct cleanup pointer explicitly instead of relying on process-global zero initialization.')
    for name, sig in (('binding_guard', 'bool CvDllGameContext::SetDLLIFace('), ('shutdown_guard', 'bool CvDllGameContext::ShutdownSingleton()')):
        old = body(baseline_text(CONTEXT), sig)
        new = old.replace('if(!mutation) { SetLastError(ERROR_BUSY); return false; }',
                          'if(!mutation || !ZeroSisGlobalsLifecycle::ProcessState().IsIdle()) { SetLastError(ERROR_BUSY); return false; }')
        add(name, CONTEXT, old, new, 'Keep the host, context and private heap alive while GC is ready or awaits cleanup; do not query/release a replacement host.')
    add('reset_types_declaration', TYPES_HEADER, 'void AcquireTypes(Database::Connection& db);',
        'void AcquireTypes(Database::Connection& db);\nvoid ResetTypes() noexcept;', 'Declare complete cached type generation reset without save or enum value changes.')
    old = 'void CvTypes::AcquireTypes(Database::Connection& db)'
    reset = 'void CvTypes::ResetTypes() noexcept\n{\n' + '\n'.join('\t' + name + ' = ' + value + ';' for name, value in type_defaults()) + '\n}\n\n'
    add('reset_type_generation', TYPES, old, reset + old, 'Restore all sixty-eight cached types to original defaults after cleanup and before a new initialization generation.')
    return rows


def main():
    path = PROJECT / 'Source/Porting/sdk_x64_patches.json'
    plan, baseline = (json.loads(p.read_text(encoding='utf-8')) for p in (path, BASE))
    retained = [p for p in plan['patches'] if not p['id'].startswith((PREFIX, 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))]
    if retained != baseline['patches'] or len(retained) != 588: raise RuntimeError('Accepted 588 SDK patches changed')
    later = [p for p in plan['patches'] if p['id'].startswith(('lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))]
    added = patches(); plan['patches'] = retained + added + later
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    lp = PROJECT / 'evidence/numeric_boundaries/edit_ledger.json'
    ledger = json.loads(lp.read_text(encoding='utf-8'))
    ledger['patch_specification_sha256'] = digest(path)
    ledger['supplemental_non_numeric_patches'] = [x for x in ledger['supplemental_non_numeric_patches'] if not x.startswith((PREFIX, 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))] + [p['id'] for p in added + later]
    ledger['unchanged_gc_lifecycle_baseline'] = {'path': str(BASE), 'sha256': digest(BASE)}
    lp.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    root = PROJECT / 'evidence/gc_lifecycle'; root.mkdir(parents=True, exist_ok=True)
    report = {'status': 'SDK_GC_LIFECYCLE_DECLARED', 'baseline': ledger['unchanged_gc_lifecycle_baseline'],
              'recipe': {'path': str(Path(__file__).resolve()), 'sha256': digest(Path(__file__).resolve())},
              'patch_specification': {'path': str(path), 'sha256': digest(path)}, 'previous_patches': 588,
              'added_patches': len(added), 'total_patches': len(plan['patches']), 'patches': added,
              'files': sorted({p['file'] for p in added}),
              'gamecore_loaded': False, 'game_launched': False}
    (root / 'caller_patch_plan.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('status', 'added_patches', 'total_patches')}))


if __name__ == '__main__': main()
