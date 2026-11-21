"""Execute only the import-audited standalone symbol-service consumer."""
import json
import re
from pathlib import Path
from collect_baseline import PROJECT, read_text, pe_header
from native_build import run
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts


def main():
    root = PROJECT / 'evidence/debug'
    bp = root / 'build_result.json'
    build = json.loads(bp.read_text(encoding='utf-8'))
    check_artifacts(build)
    consumer = build['consumer']
    exe = Path(consumer['executable']['path'])
    allowed = {'kernel32.dll', 'dbghelp.dll', 'psapi.dll', 'msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll'}
    deps = consumer['imports']['dependencies']
    if pe_header(exe)['architecture'] != 'x64' or not deps or any(d.lower() not in allowed and not d.lower().startswith('api-ms-win-crt-') for d in deps):
        raise RuntimeError('Debug consumer architecture/import audit failed')
    result = run([exe], cwd=exe.parent, timeout=90)
    log = root / 'execution.log'
    log.write_bytes(result.stdout + result.stderr)
    text = read_text(log)
    match = re.search(r'^PASS\|(\d+)\s*$', text, re.M)
    lines = re.search(r'^SOURCE_LINE\|(\d+)\|(\d+)\|(\d+)\s*$', text, re.M)
    markers = ['THREADS|8|512_symbol_queries|0_backend_overlap',
               'SYMBOLS|real_local_PDB|name_line_module|unload_reload|UTF8',
               'FAULTS|19|failed_calls_reported|retry|cleanup_handle_retained']
    issues = []
    if result.returncode or not match or not lines or any(m not in text for m in markers):
        issues.append('Isolated native symbol-service execution failed')
    if lines and not int(lines[2]) <= int(lines[1]) <= int(lines[3]):
        issues.append('PDB source line is outside the actual test function')
    report = {
        'status': 'DEBUG_NATIVE_SYMBOL_COMPONENT_PASS' if not issues else 'DEBUG_NATIVE_SYMBOL_COMPONENT_FAIL',
        'build': artifact(bp), 'verifier': artifact(Path(__file__).resolve()),
        'execution': {'exit_code': result.returncode, 'log': artifact(log), 'checks': int(match[1]) if match else 0},
        'fault_cases': 19 if not issues else None,
        'workers': 8, 'symbol_queries': 512, 'backend_overlap': 0 if not issues else None,
        'local_pdb_source_line': int(lines[1]) if lines else None,
        'issues': issues, 'windows_dbghelp_executed': True,
        'original_debug_runtime_compared': False, 'sdk_stack_walk_verified': False,
        'official_gamecore_integrated': False, 'loader_lock_bootstrap_fixed': False,
        'gamecore_loaded': False, 'game_launched': False, 'game_multicore_verified': False,
    }
    (root / 'conformance.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(text)
    print(report['status'])
    if issues:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
