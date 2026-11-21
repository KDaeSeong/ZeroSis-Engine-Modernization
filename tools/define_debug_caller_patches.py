"""Preserve the compiled 551-patch SDK and route stack walking through its debug owner."""
import json
from pathlib import Path
from collect_baseline import PROJECT, digest

PREFIX = 'debug_callers_'
BASE = PROJECT / 'evidence/sdk_x64/attempts/attempt_022/sdk_x64_patches.json'
TARGET = 'FirePlace/include/FireWorks/Win32/FDebugHelper.inl'


def patches():
    source = PROJECT / 'Source/SDK_BNW_Original' / TARGET
    original = source.read_bytes().decode('latin1')
    baseline = json.loads(BASE.read_text(encoding='utf-8'))
    text = original
    for patch in baseline['patches']:
        if patch['file'] == TARGET:
            if text.count(patch['old']) != patch['count']:
                raise RuntimeError('Debug stack baseline drift')
            text = text.replace(patch['old'], patch['new'])
    replacement = '''// The x64 provider owns DbgHelp serialization and a bounded current-thread walk.
// Keep this SDK template and the FDebugHelper object layout unchanged at the ABI.
namespace ZeroSisDebug {
typedef bool (*StackVisitor)(STACKFRAME64& frame, void* user);
bool WalkCurrentThread(HANDLE process, const CONTEXT& context, StackVisitor visitor, void* user);
}
template< class Function > void FDebugHelper::WalkStack( const CONTEXT& context, Function Func )
{
    ZeroSisDebug::WalkCurrentThread(hCurrentProcess, context,
        [](STACKFRAME64& frame, void* user) -> bool {
            return (*static_cast<Function*>(user))(frame);
        }, &Func);
}
'''
    if '\r\n' in text:
        replacement = replacement.replace('\n', '\r\n')
    return [{'id': PREFIX + 'stack_walk', 'file': TARGET, 'source_sha256': digest(source),
             'old': text, 'new': replacement, 'count': 1,
             'reason': 'Pass a private valid context to x64 StackWalk64, share DbgHelp serialization, and bound/cycle-check traversal without holding the lock in client callbacks.'}]


def main():
    path = PROJECT / 'Source/Porting/sdk_x64_patches.json'
    plan = json.loads(path.read_text(encoding='utf-8'))
    baseline = json.loads(BASE.read_text(encoding='utf-8'))
    retained = [p for p in plan['patches'] if not p['id'].startswith((PREFIX, 'globals_callers_','construction_callers_','host_callers_','db_postprocess_', 'db_loader_', 'info_cleanup_' ,'db_cache_', 'startup_owners_', 'gc_lifecycle_', 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))]
    if retained != baseline['patches'] or len(retained) != 551:
        raise RuntimeError('Accepted 551 SDK patches changed')
    added = patches()
    later = [p for p in plan['patches'] if p['id'].startswith(('globals_callers_','construction_callers_','host_callers_','db_postprocess_', 'db_loader_', 'info_cleanup_' ,'db_cache_', 'startup_owners_', 'gc_lifecycle_', 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))]
    plan['patches'] = retained + added + later
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    ledger_path = PROJECT / 'evidence/numeric_boundaries/edit_ledger.json'
    ledger = json.loads(ledger_path.read_text(encoding='utf-8'))
    ledger['patch_specification_sha256'] = digest(path)
    ledger['supplemental_non_numeric_patches'] = [x for x in ledger['supplemental_non_numeric_patches'] if not x.startswith((PREFIX, 'globals_callers_','construction_callers_','host_callers_','db_postprocess_', 'db_loader_', 'info_cleanup_' ,'db_cache_', 'startup_owners_', 'gc_lifecycle_', 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))] + [p['id'] for p in added + later]
    ledger['unchanged_debug_caller_baseline'] = {'path': str(BASE), 'sha256': digest(BASE)}
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    root = PROJECT / 'evidence/debug/stack'
    root.mkdir(parents=True, exist_ok=True)
    report = {'status': 'SDK_DEBUG_STACK_CALLERS_DECLARED', 'baseline': ledger['unchanged_debug_caller_baseline'],
              'recipe': {'path': str(Path(__file__).resolve()), 'sha256': digest(Path(__file__).resolve())},
              'patch_specification': {'path': str(path), 'sha256': digest(path)},
              'previous_patches': 551, 'added_patches': len(added), 'total_patches': len(plan['patches']),
              'files': [TARGET], 'patches': added, 'gamecore_loaded': False, 'game_launched': False}
    (root / 'caller_patch_plan.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('status', 'added_patches', 'total_patches')}))


if __name__ == '__main__':
    main()
