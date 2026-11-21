"""Match tested bootstrap/context bodies to the actually compiled SDK callers."""
import json
from pathlib import Path
from collect_baseline import PROJECT, digest, read_text
from verify_world_builder_map_object import check_artifacts
from define_bootstrap_patches import BASE, PREFIX, patches
from build_bootstrap_component import body


def validate():
    root = PROJECT / 'evidence/bootstrap'
    build, result, declared = (json.loads((root / name).read_text(encoding='utf-8'))
                               for name in ('build_result.json', 'conformance.json', 'caller_patch_plan.json'))
    check_artifacts([build, result, declared])
    if result['status'] != 'BOOTSTRAP_NATIVE_COMPONENT_PASS' or result['issues']:
        raise RuntimeError('Bootstrap native component failed')
    runs = result['runs']
    if [r['exit_code'] for r in runs] != [0, 0, 0, 0] or [r['checks'] for r in runs[:2]] != [501, 118]:
        raise RuntimeError('Bootstrap native checks differ')
    markers = ['CONCURRENCY|8|256_start_calls|one_context',
               'CONTEXT_RECOVERY|idempotent|partial_constructor_no_leak|failed_heap_destroy_retained',
               'ORIGINAL_DUPLICATE|contexts=1|adapters=4|heap=0',
               'ORIGINAL_PARTIAL|contexts=0|adapters=2|heap=1']
    if any(marker not in read_text(Path(row['log']['path'])) for row, marker in zip(runs, markers)):
        raise RuntimeError('Bootstrap native behavior or defect reproduction missing')
    plan = json.loads((PROJECT / 'Source/Porting/sdk_x64_patches.json').read_text(encoding='utf-8'))
    baseline = json.loads(BASE.read_text(encoding='utf-8'))
    added = patches()
    if len(plan['patches']) != 693 or len(added) != 8 or declared['patches'] != added:
        raise RuntimeError('Bootstrap patch count/recipe differs')
    if [p for p in plan['patches'] if not p['id'].startswith((PREFIX, 'debug_callers_','globals_callers_','construction_callers_','host_callers_','db_postprocess_', 'db_loader_', 'info_cleanup_' ,'db_cache_', 'startup_owners_', 'gc_lifecycle_', 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))] != baseline['patches'] or [p for p in plan['patches'] if p['id'].startswith(PREFIX)] != added:
        raise RuntimeError('Bootstrap changed a retained SDK patch')
    # Later reviewed families can refine a bootstrap body. Replay the complete
    # retained recipe rather than requiring historical replacement substrings.
    for relative in {p['file'] for p in added}:
        expected = (PROJECT / 'Source/SDK_BNW_Original' / relative).read_bytes().decode('latin1')
        for patch in plan['patches']:
            if patch['file'] == relative:
                if expected.count(patch['old']) != patch['count']:
                    raise RuntimeError('Bootstrap patch replay mismatch: ' + patch['id'])
                expected = expected.replace(patch['old'], patch['new'])
        current = (PROJECT / 'Source/SDK_BNW_x64' / relative).read_bytes().decode('latin1')
        if current != expected:
            raise RuntimeError('Compiled SDK bootstrap source differs: ' + relative)
    sdk = json.loads((PROJECT / 'evidence/sdk_x64/build_result.json').read_text(encoding='utf-8'))
    if sdk['status'] != 'SDK_X64_ALL_OBJECTS_COMPILED' or len(sdk['objects']) != 161 or sdk['patch_specification']['sha256'] != digest(PROJECT / 'Source/Porting/sdk_x64_patches.json'):
        raise RuntimeError('Bootstrap SDK callers have not compiled')
    header = PROJECT / 'Source/Porting/ZeroSisBootstrap.h'
    if {'path': str(header), 'sha256': digest(header)} not in sdk['support_inputs'] or {'path': str(header), 'sha256': digest(header)} not in build['sources']:
        raise RuntimeError('SDK and bootstrap tests used different lifecycle headers')
    text = (PROJECT / 'Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvDllContext.cpp').read_bytes().decode('latin1')
    fixture = Path(build['fixture']['path']).read_text(encoding='utf-8')
    for signature in ('CvDllGameContext::CvDllGameContext()', 'void CvDllGameContext::InitializeSingleton()',
                      'void CvDllGameContext::DestroySingleton()', 'bool CvDllGameContext::ShutdownSingleton()',
                      'void* CvDllGameContext::Allocate(size_t bytes)'):
        if body(text, signature).replace('\r\n', '\n') not in fixture:
            raise RuntimeError('Tested context body differs from actual SDK: ' + signature)
    if not result['context_adapter_types_instrumented'] or any(result[k] for k in
            ('actual_gamecore_context_executed', 'gamecore_loaded', 'game_launched', 'game_multicore_verified')):
        raise RuntimeError('Bootstrap scope exceeds isolated caller tests')
    entry = {'name': 'BootstrapCallers', 'build': {'path': str(root / 'build_result.json'), 'sha256': digest(root / 'build_result.json')},
             'conformance': {'path': str(root / 'conformance.json'), 'sha256': digest(root / 'conformance.json')},
             'caller_plan': {'path': str(root / 'caller_patch_plan.json'), 'sha256': digest(root / 'caller_patch_plan.json')},
             'validator': {'path': str(Path(__file__).resolve()), 'sha256': digest(Path(__file__).resolve())},
             'scope': 'LIFECYCLE_AND_EXTRACTED_CONTEXT_BODIES_MATCH_161_COMPILED_SDK_OBJECTS_NOT_GAME_EXECUTION'}
    return build, result, entry


if __name__ == '__main__':
    _, result, _ = validate()
    print(json.dumps({'status': 'BOOTSTRAP_CALLERS_EVIDENCE_PASS', 'checks': sum(r['checks'] for r in result['runs'][:2]), 'compiled_gamecore_objects': 161}))
