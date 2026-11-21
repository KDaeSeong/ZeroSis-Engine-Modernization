"""Build and run the isolated trade-route presentation value-state regression."""
import datetime
import json
import re
import uuid
from pathlib import Path

from build_native_host import compile_program
from collect_baseline import PROJECT, read_text
from native_build import run
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts

TEST = PROJECT / 'Tests/trade_route_presentation.cpp'
HEADER = PROJECT / 'Source/Host/TradeRoutePresentation.h'
TOOL = Path(__file__).resolve()
EVIDENCE = PROJECT / 'evidence/host_trade_route_presentation'


def canonical(path):
    return str(Path(path).resolve()).casefold()


def main():
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    run_id = stamp + '_' + uuid.uuid4().hex[:12]
    run_root = EVIDENCE / run_id
    run_root.mkdir(parents=True, exist_ok=False)

    frozen_paths = (TEST, HEADER, TOOL)
    before = {canonical(path): artifact(path)['sha256'] for path in frozen_paths}
    built = compile_program('sdk_host_trade_route_presentation_' + run_id, TEST)

    compiler_inputs = {canonical(row['path']): row for row in built['compiler_inputs']}
    for path in (TEST, HEADER):
        key = canonical(path)
        if key not in compiler_inputs:
            raise RuntimeError('Expected trade-route test dependency was not compiler-consumed: ' + str(path))
        if compiler_inputs[key]['sha256'] != before[key]:
            raise RuntimeError('Compiler consumed a different frozen input: ' + str(path))
    for path in frozen_paths:
        if artifact(path)['sha256'] != before[canonical(path)]:
            raise RuntimeError('A frozen test input changed during build: ' + str(path))

    executable = Path(built['executable']['path'])
    result = run([executable], cwd=executable.parent, timeout=60)
    log_path = run_root / 'execution.log'
    log_path.write_bytes(result.stdout + result.stderr)
    output = read_text(log_path)
    marker = re.search(r'TRADE_ROUTE_PRESENTATION_PASS checks=(\d+) GAMECORE_LOADED=false', output)
    if result.returncode or not marker or int(marker[1]) <= 0:
        raise RuntimeError(f'Boundary regression failed exit=0x{result.returncode & 0xffffffff:08X}: ' + output[-5000:])

    for path in frozen_paths:
        if artifact(path)['sha256'] != before[canonical(path)]:
            raise RuntimeError('A frozen test input changed during execution: ' + str(path))
    check_artifacts(built)

    report = {
        'status': 'TRADE_ROUTE_PRESENTATION_COMPONENT_PASS',
        'run_id': run_id,
        'test': artifact(TEST),
        'implementation_header': artifact(HEADER),
        'runner': artifact(TOOL),
        'build': built,
        'run_log': artifact(log_path),
        'native_checks': int(marker[1]),
        'gamecore_loaded': False,
        'sdk_dll_loaded': False,
        'scope': 'OWNED_TRADE_ROUTE_PATH_DIRECTION_POPUP_DESTROY_VALIDATION_AND_SNAPSHOT_STATE',
        'limitations': 'Does not establish GameCore callback order at runtime or world rendering behavior.',
    }
    report_path = run_root / 'conformance.json'
    report_path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    check_artifacts(report)
    print(json.dumps({'status': report['status'], 'checks': report['native_checks'],
                      'executable_sha256': built['executable']['sha256'],
                      'report': artifact(report_path)}), flush=True)


if __name__ == '__main__':
    main()
