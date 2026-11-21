"""Tie actual SDK template execution to the compiled x64 port and provider."""
import json
from pathlib import Path
from collect_baseline import PROJECT, digest, read_text, pe_header
from verify_world_builder_map_object import check_artifacts
from define_debug_caller_patches import BASE, PREFIX, TARGET, patches
from verify_debug_stack import MARKERS


def validate():
    root = PROJECT / 'evidence/debug/stack'
    build = json.loads((PROJECT / 'evidence/debug/build_result.json').read_text(encoding='utf-8'))
    result, declared = (json.loads((root / name).read_text(encoding='utf-8'))
                        for name in ('conformance.json', 'caller_patch_plan.json'))
    check_artifacts([build, result, declared])
    if result['status'] != 'SDK_X64_STACK_WALK_PASS' or result['issues']:
        raise RuntimeError('SDK stack native execution failed')
    if (result['execution']['exit_code'], result['execution']['checks'], result['native_stack_traces'],
        result['workers'], result['concurrent_stack_traces'], result['backend_cases'],
        result['invalid_context_cases'], result['backend_overlap']) != (0, 1081, 257, 8, 256, 9, 3, 0):
        raise RuntimeError('SDK stack execution accounting changed')
    text = read_text(Path(result['execution']['log']['path']))
    if 'PASS|1081' not in text or any(marker not in text for marker in MARKERS):
        raise RuntimeError('SDK stack required runtime observations missing')
    consumer = build['stack_consumer']
    if pe_header(Path(consumer['executable']['path']))['architecture'] != 'x64':
        raise RuntimeError('Stack consumer is not AMD64')
    allowed = {'kernel32.dll', 'dbghelp.dll', 'psapi.dll', 'msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll'}
    deps = consumer['imports']['dependencies']
    if not deps or any(d.lower() not in allowed and not d.lower().startswith('api-ms-win-crt-') for d in deps):
        raise RuntimeError('Unexpected stack consumer dependency')
    original = Path(build['original_stack_template']['path']).read_bytes().decode('latin1')
    fixture = Path(build['original_stack_fixture']['path']).read_text(encoding='utf-8')
    if fixture != original.replace('FDebugHelper::', 'OriginalWalkFixture::').replace('\r\n', '\n'):
        raise RuntimeError('Original SDK stack fixture was altered')
    plan = json.loads((PROJECT / 'Source/Porting/sdk_x64_patches.json').read_text(encoding='utf-8'))
    baseline = json.loads(BASE.read_text(encoding='utf-8'))
    added = patches()
    if len(plan['patches']) != 693 or len(added) != 1 or declared['patches'] != added:
        raise RuntimeError('Debug stack patch count or recipe differs')
    if [p for p in plan['patches'] if not p['id'].startswith((PREFIX, 'globals_callers_','construction_callers_','host_callers_','db_postprocess_', 'db_loader_', 'info_cleanup_' ,'db_cache_', 'startup_owners_', 'gc_lifecycle_', 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))] != baseline['patches'] or [p for p in plan['patches'] if p['id'].startswith(PREFIX)] != added:
        raise RuntimeError('Debug stack changed a retained SDK patch')
    if (PROJECT / 'Source/SDK_BNW_x64' / TARGET).read_bytes().decode('latin1') != added[0]['new']:
        raise RuntimeError('Tested/compiled SDK stack template differs')
    sdk = json.loads((PROJECT / 'evidence/sdk_x64/build_result.json').read_text(encoding='utf-8'))
    if sdk['status'] != 'SDK_X64_ALL_OBJECTS_COMPILED' or len(sdk['objects']) != 161:
        raise RuntimeError('Updated SDK stack callers have not compiled')
    if build['sdk_port_manifest'] != sdk['manifest'] or build['sdk_patch_specification'] != sdk['patch_specification']:
        raise RuntimeError('Debug consumer and SDK compile inputs differ')
    if not result['sdk_template_executed'] or not result['original_null_context_observed_at_instrumented_api']:
        raise RuntimeError('Original defect/current template observation missing')
    if any(result[k] for k in ('original_null_context_passed_to_windows', 'native_stack_termination_proves_complete_trace',
                               'get_call_stack_and_callstack_formatting_implemented', 'gamecore_loaded',
                               'game_launched', 'game_multicore_verified')):
        raise RuntimeError('Stack evidence exceeds actual execution scope')
    entry = {'name': 'DebugStackCallers',
             'conformance': {'path': str(root / 'conformance.json'), 'sha256': digest(root / 'conformance.json')},
             'caller_plan': {'path': str(root / 'caller_patch_plan.json'), 'sha256': digest(root / 'caller_patch_plan.json')},
             'validator': {'path': str(Path(__file__).resolve()), 'sha256': digest(Path(__file__).resolve())},
             'scope': 'ACTUAL_SDK_TEMPLATE_AND_NATIVE_X64_STACKS; NO_GAMECORE_MODULE_LOADED'}
    return build, result, entry


if __name__ == '__main__':
    _, result, _ = validate()
    print(json.dumps({'status': 'SDK_DEBUG_STACK_EVIDENCE_PASS', 'checks': result['execution']['checks']}))
