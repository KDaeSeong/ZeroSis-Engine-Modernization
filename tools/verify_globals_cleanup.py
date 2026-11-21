"""Execute import-audited original/candidate cleanup ownership regression."""
import json
import re
from pathlib import Path
from collect_baseline import PROJECT, digest, pe_header, read_text
from native_build import run
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts

MARKERS = {'original': 'ORIGINAL_LEAK|holders=128|entries=608|arrays=608',
           'candidate': 'CANDIDATE_CLEAN|holders=0|entries=0|arrays=0'}


def main():
    root = PROJECT / 'evidence/globals_cleanup'
    bp = root / 'build_result.json'
    build = json.loads(bp.read_text(encoding='utf-8'))
    check_artifacts(build)
    allowed = {'kernel32.dll', 'msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll'}
    runs = []
    issues = []
    for name in ('original', 'candidate'):
        entry = build['builds'][name]
        executable = Path(entry['executable']['path'])
        deps = entry['imports']['dependencies']
        if pe_header(executable)['architecture'] != 'x64' or digest(Path(entry['executable']['log'])) != entry['executable']['log_sha256']:
            raise RuntimeError('Globals cleanup build provenance mismatch')
        if not deps or any(d.lower() not in allowed and not d.lower().startswith('api-ms-win-crt-') for d in deps):
            raise RuntimeError('Unexpected cleanup runtime dependency')
        result = run([executable], cwd=executable.parent, timeout=30)
        log = root / (name + '_execution.log')
        log.write_bytes(result.stdout + result.stderr)
        text = read_text(log)
        match = re.search(r'^PASS\|(\d+)\s*$', text, re.M)
        checks = int(match[1]) if match else 0
        if result.returncode or checks < 5000 or MARKERS[name] not in text or 'CASES|132|holder_cases=128|host_cases=66' not in text:
            issues.append('Missing native cleanup observation: ' + name)
        runs.append({'name': name, 'executable': artifact(executable), 'exit_code': result.returncode,
                     'log': artifact(log), 'checks': checks, 'cases': 132})
        print(text, flush=True)
    report = {'status': 'GLOBALS_CLEANUP_NATIVE_PASS' if not issues else 'GLOBALS_CLEANUP_NATIVE_FAIL',
              'build': artifact(bp), 'verifier': artifact(Path(__file__).resolve()), 'runs': runs, 'issues': issues,
              'cases_per_variant': 132, 'original_leaked_holders': 128, 'original_leaked_entries': 608,
              'original_leaked_arrays': 608, 'candidate_live_ownership_after_cleanup': 0,
              'exact_cleanup_bodies_executed': True, 'other_owners_and_host_instrumented': True,
              'whole_gc_init_uninit_verified': False, 'duplicate_gc_shutdown_verified': False,
              'gamecore_loaded': False, 'game_launched': False, 'game_multicore_verified': False}
    (root / 'conformance.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(report['status'])
    if issues:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
