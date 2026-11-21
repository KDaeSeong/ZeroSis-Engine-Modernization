"""Check symbol-service execution and real GameCore link-only provenance."""
import json
import re
from pathlib import Path
from collect_baseline import PROJECT, digest, read_text, pe_header
from verify_world_builder_map_object import check_artifacts


def validate_component(build_path=None):
    root = PROJECT / 'evidence/debug'
    if build_path is not None and Path(build_path).resolve() != root / 'build_result.json':
        raise RuntimeError('Unexpected debug provider build path')
    build, result = (json.loads((root / name).read_text(encoding='utf-8'))
                     for name in ('build_result.json', 'conformance.json'))
    check_artifacts([build, result])
    if build['status'] != 'DEBUG_X64_SYMBOL_PROVIDER_BUILT' or build['runtime'] != '/MD':
        raise RuntimeError('Debug provider build contract differs')
    if result['status'] != 'DEBUG_NATIVE_SYMBOL_COMPONENT_PASS' or result['issues']:
        raise RuntimeError('Debug native symbol execution failed')
    if (result['execution']['exit_code'], result['execution']['checks'], result['fault_cases'],
        result['workers'], result['symbol_queries'], result['backend_overlap']) != (0, 1730, 19, 8, 512, 0):
        raise RuntimeError('Debug execution accounting differs')
    text = read_text(Path(result['execution']['log']['path']))
    for marker in ('PASS|1730', 'SOURCE_LINE|22|22|25', 'THREADS|8|512_symbol_queries|0_backend_overlap',
                   'FAULTS|19|failed_calls_reported|retry|cleanup_handle_retained',
                   'SYMBOLS|real_local_PDB|name_line_module|unload_reload|UTF8'):
        if marker not in text:
            raise RuntimeError('Debug native observation missing: ' + marker)
    consumer = build['consumer']
    if pe_header(Path(consumer['executable']['path']))['architecture'] != 'x64':
        raise RuntimeError('Debug consumer is not x64')
    allowed = {'kernel32.dll', 'dbghelp.dll', 'psapi.dll', 'msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll'}
    deps = consumer['imports']['dependencies']
    if not deps or any(d.lower() not in allowed and not d.lower().startswith('api-ms-win-crt-') for d in deps):
        raise RuntimeError('Debug consumer import contract differs')
    for row in build['logs']:
        if re.search(r'\b(?:warning|error)\s+[A-Z]+\d+', read_text(Path(row['path'])), re.I):
            raise RuntimeError('Debug build emitted a diagnostic')
    from debug_stack_evidence import validate as validate_stack
    _, _, stack = validate_stack()
    entry = {'name': 'Debug', 'library': build['library'], 'stack_walk_callers': stack,
             'build_report': {'path': str(root / 'build_result.json'), 'sha256': digest(root / 'build_result.json')},
             'conformance': {'path': str(root / 'conformance.json'), 'sha256': digest(root / 'conformance.json')},
             'runtime': '/MD', 'scope': 'REAL_WINDOWS_SDK_SYMBOL_SERVICE_NOT_GAME_RUNTIME'}
    return build, result, entry


def validate():
    build, result, _ = validate_component()
    root = PROJECT / 'evidence/debug'
    link = json.loads((root / 'link_trial.json').read_text(encoding='utf-8'))
    check_artifacts(link)
    if link['status'] != 'DEBUG_GAMECORE_LINK_CANDIDATE_PASS_NOT_LOADABLE_RELEASE':
        raise RuntimeError('Debug GameCore candidate link failed')
    if (link['before'], link['after'], link['gamecore_objects'], link['providers'], link['official_unresolved_symbols']) != (3, 0, 161, 16, 0):
        raise RuntimeError('Debug GameCore link counts differ')
    expected = {'?GetInstance@FDebugHelper@@SAAEAV1@XZ', '?LoadSymbols@FDebugHelper@@QEAA_NPEAUHINSTANCE__@@@Z', '?Shutdown@ZeroSisDebug@@YA_NXZ'}
    before, after = link['runs']
    if set(link['resolved']) != expected or set(before['unresolved']) != expected or after['unresolved']:
        raise RuntimeError('Debug symbol closure differs')
    if not before['exit_code'] or before['generated_dll'] or after['exit_code'] or not after['generated_dll']:
        raise RuntimeError('Debug candidate artifact status differs')
    if not re.search(r'LNK1120:\s*3(?!\d)', read_text(Path(before['log']['path']))):
        raise RuntimeError('Original missing debug symbols are not evidenced')
    if pe_header(Path(after['dll']['path']))['architecture'] != 'x64':
        raise RuntimeError('Candidate GameCore DLL is not AMD64')
    map_text = read_text(Path(after['map']['path']))
    if any(symbol not in map_text for symbol in expected) or 'ZeroSis_Debug_x64:SdkDebugHelper.obj' not in map_text:
        raise RuntimeError('Candidate did not link actual debug methods')
    if 'DllGetGameContext' not in read_text(Path(after['inspection']['path'])):
        raise RuntimeError('Candidate GameCore export missing')
    sdk = json.loads((PROJECT / 'evidence/sdk_x64/build_result.json').read_text(encoding='utf-8'))
    if build['sdk_port_manifest'] != sdk['manifest'] or build['sdk_patch_specification'] != sdk['patch_specification']:
        raise RuntimeError('Candidate and compiled SDK inputs differ')
    if link['official_link']['sha256'] != digest(PROJECT / 'evidence/sdk_x64/link_analysis.json'):
        raise RuntimeError('Debug candidate official baseline changed')
    reference = json.loads((root / 'reference/entrypoint_disassembly.json').read_text(encoding='utf-8'))
    check_artifacts(reference)
    if reference['status'] != 'ORIGINAL_DEBUG_STATIC_DISASSEMBLY' or reference['exit_code']:
        raise RuntimeError('Original debug inspection missing')
    if not result['windows_dbghelp_executed'] or any(result[k] for k in (
            'original_debug_runtime_compared', 'sdk_stack_walk_verified', 'official_gamecore_integrated',
            'loader_lock_bootstrap_fixed', 'gamecore_loaded', 'game_launched', 'game_multicore_verified')):
        raise RuntimeError('Debug evidence exceeds actual native component scope')
    if any(link[k] for k in ('official_report_replaced', 'gamecore_loaded', 'game_launched', 'game_multicore_verified')):
        raise RuntimeError('Unproven GameCore runtime/bootstrap claim')
    if not link['explicit_bootstrap_integrated'] or link['loader_lock_bootstrap_fixed']:
        raise RuntimeError('Wrong bootstrap integration/audit scope')
    from bootstrap_evidence import validate as validate_bootstrap
    _, _, bootstrap = validate_bootstrap()
    if link['bootstrap_callers'] != bootstrap:
        raise RuntimeError('Debug link used different bootstrap callers')
    return build, result, link


if __name__ == '__main__':
    _, result, link = validate()
    print(json.dumps({'status': 'DEBUG_EVIDENCE_PASS', 'checks': result['execution']['checks'],
                      'candidate_unresolved': link['after'], 'gamecore_loaded': False}))
