"""Rebuild dependent integration evidence after the owned-city-strategy cleanup.

Run refresh_world_builder_dependencies first. All executables here are isolated
component tests; the produced GameCore DLL is linked and inspected, never loaded.
"""
import argparse
import json
import sys
from pathlib import Path
from collect_baseline import PROJECT, digest
from native_build import run


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--from-step', help='Resume only after inspecting a previous terminal failure.')
    args = parser.parse_args()
    names = (
        'build_bootstrap_component', 'verify_bootstrap_component', 'bootstrap_evidence',
        'build_world_builder_map_wire', 'verify_world_builder_map_wire',
        'build_world_builder_map_object', 'verify_world_builder_map_object',
        'build_world_builder_map_bridge', 'verify_world_builder_map_bridge',
        'build_filesystem_provider', 'verify_filesystem_provider',
        'build_logging_provider', 'verify_logging_provider',
        'build_debug_provider', 'verify_debug_provider', 'verify_debug_stack',
        'globals_cleanup_evidence', 'analyze_sdk_x64', 'probe_debug_link',
        'probe_filesystem_link', 'probe_logging_link', 'probe_world_builder_map_link',
        'probe_world_builder_map_bridge_link', 'verify_world_builder_map_integration')
    if args.from_step and args.from_step not in names:
        parser.error('Unknown integration step')
    link = json.loads((PROJECT / 'evidence/sdk_x64/link_analysis.json').read_text(encoding='utf-8'))
    mapping = {'Lua51': 'lua', 'Streams': 'stream', 'Serialization': 'serialization', 'Foundation': 'foundation',
               'TempHeap': 'temp-heap', 'AutoArchive': 'auto-archive', 'Database': 'database', 'FLua': 'flua',
               'Strings': 'string', 'Localization': 'localization', 'WorldBuilderTypes': 'world-builder-types',
               'WorldBuilderModData': 'world-builder-mod-data', 'WorldBuilderMapBridge': 'world-builder-map',
               'FileSystem': 'filesystem', 'Logging': 'logging', 'Debug': 'debug'}
    if {p['name'] for p in link['providers']} != set(mapping):
        raise RuntimeError('Expected all sixteen existing provider inputs')
    link_args = ['--vs', r'C:\Program Files\Microsoft Visual Studio\2022\Community']
    for provider in link['providers']:
        link_args += ['--' + mapping[provider['name']] + '-provider', provider['build_report']['path']]
    root = PROJECT / 'evidence/globals_cleanup/integration_refresh'
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
        result = run([sys.executable, script, *(link_args if name == 'analyze_sdk_x64' else [])], cwd=PROJECT, timeout=1800)
        log.write_bytes(result.stdout + result.stderr)
        rows.append({'step': name, 'exit_code': result.returncode,
                     'script': {'path': str(script), 'sha256': digest(script)},
                     'log': {'path': str(log), 'sha256': digest(log)}})
        results.write_text(json.dumps(rows, indent=2) + '\n', encoding='utf-8')
        if result.returncode:
            print((result.stdout + result.stderr).decode('utf-8', errors='replace')[-6000:])
            raise SystemExit(result.returncode)
        print('PASS ' + name, flush=True)
    print('GLOBALS_CLEANUP_INTEGRATION_REFRESH_PASS', flush=True)


if __name__ == '__main__':
    main()
