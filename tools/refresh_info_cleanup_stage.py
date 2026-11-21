"""Stage the verified rule information ownership integration, refresh static audit, check integrity.

Run refresh_info_cleanup_integration first. Does not load GameCore or run Civ V.
"""
import argparse
import json
import sys
from pathlib import Path
from collect_baseline import PROJECT, digest
from native_build import run


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--from-step', help='Resume after terminal completion or failure and validation of preceding recorded steps.')
    args = parser.parse_args()
    names = ('audit_gc_initialization', 'stage_localization_values', 'stage_localization_provider', 'stage_world_builder_types', 'stage_world_builder_mod_data', 'stage_world_builder_map_wire', 'stage_world_builder_map_object', 'stage_world_builder_map_bridge', 'stage_filesystem_provider', 'stage_logging_provider', 'stage_bootstrap_component', 'stage_debug_provider', 'stage_globals_cleanup', 'stage_construction', 'stage_host_binding', 'stage_database_postprocess', 'stage_database_loader', 'stage_info_cleanup', 'stage_sdk_x64_port', 'audit_static_initialization', 'verify_static_initialization', 'stage_static_initialization', 'verify_project')
    if args.from_step and args.from_step not in names:
        parser.error('Unknown integration step')
    root = PROJECT / 'evidence/info_cleanup/stage_refresh'
    root.mkdir(parents=True, exist_ok=True)
    results = root / 'results.json'
    prior = json.loads(results.read_text(encoding='utf-8')) if args.from_step and results.exists() else []
    start = names.index(args.from_step) if args.from_step else 0
    rows = [r for r in prior if names.index(r['step']) < start]
    if args.from_step and [r['step'] for r in rows if r['exit_code'] == 0] != list(names[:start]):
        raise RuntimeError('Resume requires preceding successful recorded steps')
    for name in names[start:]:
        script = PROJECT / 'tools' / (name + '.py')
        log = root / (name + '.log')
        print('RUN ' + name, flush=True)
        result = run([sys.executable, script], cwd=PROJECT, timeout=1800)
        log.write_bytes(result.stdout + result.stderr)
        rows.append({'step': name, 'exit_code': result.returncode,
                     'script': {'path': str(script), 'sha256': digest(script)},
                     'log': {'path': str(log), 'sha256': digest(log)}})
        results.write_text(json.dumps(rows, indent=2) + '\n', encoding='utf-8')
        if result.returncode:
            print((result.stdout + result.stderr).decode('utf-8', errors='replace')[-6000:])
            raise SystemExit(result.returncode)
        print('PASS ' + name, flush=True)
    print('INFO_CLEANUP_STAGE_REFRESH_PASS', flush=True)


if __name__ == '__main__':
    main()
