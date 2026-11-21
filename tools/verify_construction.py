"""Reproduce original constructor leaks and verify cleanup with preserved failures."""
import json
import re
from pathlib import Path
from collect_baseline import PROJECT, digest, pe_header, read_text
from native_build import run
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts

MARKERS = {'original': 'ORIGINAL_REMAINS|game_arrays=63|map_arrays=14|map_counts=13',
           'candidate': 'CANDIDATE_CLEAN|arrays=0|map_count=0'}
COMMON = ('FAILURES|game=13|map=13|successful_constructions=30',
          'RETRY|every_failed_construction_followed_by_success',
          'SCOPE|instrumented_game_reset_host_containers|no_gamecore_loaded|no_game_database_io')


def main():
    root = PROJECT / 'evidence/construction'
    bp = root / 'build_result.json'
    build = json.loads(bp.read_text(encoding='utf-8'))
    check_artifacts(build)
    allowed = {'kernel32.dll', 'msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll'}
    rows, issues = [], []
    for name in ('original', 'candidate'):
        entry = build['builds'][name]
        exe = Path(entry['executable']['path'])
        deps = entry['imports']['dependencies']
        if pe_header(exe)['architecture'] != 'x64' or digest(Path(entry['executable']['log'])) != entry['executable']['log_sha256']:
            raise RuntimeError('Constructor build provenance mismatch')
        if not deps or any(d.lower() not in allowed and not d.lower().startswith('api-ms-win-crt-') for d in deps):
            raise RuntimeError('Unexpected constructor runtime dependency')
        result = run([exe], cwd=exe.parent, timeout=30)
        log = root / (name + '_execution.log')
        log.write_bytes(result.stdout + result.stderr)
        text = read_text(log)
        match = re.search(r'^PASS\|(\d+)\s*$', text, re.M)
        checks = int(match[1]) if match else 0
        if result.returncode or checks < 7000 or any(marker not in text for marker in (*COMMON, MARKERS[name])):
            issues.append('Constructor observations failed: ' + name)
        rows.append({'name': name, 'executable': artifact(exe), 'exit_code': result.returncode,
                     'log': artifact(log), 'checks': checks})
        print(text, flush=True)
    report = {'status': 'CONSTRUCTION_NATIVE_PASS' if not issues else 'CONSTRUCTION_NATIVE_FAIL',
              'build': artifact(bp), 'verifier': artifact(Path(__file__).resolve()), 'runs': rows, 'issues': issues,
              'game_failure_cases': 13, 'map_failure_cases': 13, 'successful_constructions_per_variant': 30,
              'original_game_array_leaks': 63, 'original_map_array_leaks': 14, 'original_map_counter_remnants': 13,
              'original_constructor_defects_reproduced': not issues,
              'candidate_constructor_storage_and_counter_restored': not issues,
              'exact_sdk_bodies_executed': True, 'game_reset_timer_host_containers_instrumented': True,
              'whole_gc_lifecycle_verified': False, 'host_side_effects_rolled_back': False,
              'real_game_reset_database_io_executed': False, 'gamecore_loaded': False,
              'game_launched': False, 'game_multicore_verified': False}
    (root / 'conformance.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(report['status'])
    if issues:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
