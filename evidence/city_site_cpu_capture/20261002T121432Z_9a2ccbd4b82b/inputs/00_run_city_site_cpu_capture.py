"""Capture one normal CitySite SDK workload using an owned WPR instance.

The reader and capture-time topology are retained with the immutable ETL.
This diagnostic never changes processor affinity, inserts work, or benchmarks
performance. Only this invocation's named WPR session may be stopped/cancelled.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

from collect_baseline import PROJECT, digest
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts

WPR = Path(r'C:\Windows\System32\wpr.exe')
PROFILE = PROJECT / 'tools/city_site_cpu.wprp'
RUNNER = PROJECT / 'tools/run_new_game_probe.py'
ROOT = PROJECT / 'evidence/city_site_cpu_capture'


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--reader-proof', type=Path,
                        default=PROJECT / 'evidence/city_site_cpu_trace/conformance.json')
    parser.add_argument('--language', choices=('en_US', 'ko_KR'), default='en_US')
    parser.add_argument('--timeout', type=int, default=120)
    args = parser.parse_args()
    if not 30 <= args.timeout <= 150:
        parser.error('The bounded SDK diagnostic timeout must be 30 to 150 seconds')

    reader_proof_path = args.reader_proof.resolve()
    reader_proof = json.loads(reader_proof_path.read_text(encoding='utf8'))
    check_artifacts(reader_proof)
    if reader_proof.get('status') != 'CITY_SITE_CPU_TRACE_OFFLINE_PASS':
        raise RuntimeError('The CPU trace reader must have a passing frozen component proof')
    reader = Path(reader_proof['reader_artifact']['path'])
    check_artifacts(reader_proof['reader_artifact'])
    sdk_report_path = PROJECT / 'evidence/city_site_sdk/build_result.json'
    sdk = json.loads(sdk_report_path.read_text(encoding='utf8'))
    check_artifacts(sdk)
    if sdk.get('status') != 'CITY_SITE_SDK_CANDIDATE_LINKED' or \
       sdk.get('cpu_trace_default_enabled') is not False or \
       sdk.get('cpu_trace_provider_guid') != '2d76305f-91f4-4d48-9b32-281507669f73':
        raise RuntimeError('The selected isolated SDK does not have the verified optional trace provider')

    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_') + uuid.uuid4().hex[:12]
    evidence = ROOT / run_id
    evidence.mkdir(parents=True, exist_ok=False)
    recording = PROJECT / 'Build/CitySiteCpuCapture' / run_id
    recording.mkdir(parents=True, exist_ok=False)
    temporary_recording = recording / 'wpr_temporary'
    temporary_recording.mkdir()
    instance = 'ZeroSisCitySite_' + run_id
    etl = recording / 'city_site_cpu.etl'
    inputs = [Path(__file__).resolve(), PROFILE, RUNNER, reader_proof_path, sdk_report_path]
    before = {str(path): digest(path) for path in inputs}
    frozen = evidence / 'inputs'
    frozen.mkdir()
    frozen_inputs = []
    for index, source in enumerate(inputs):
        destination = frozen / f'{index:02d}_{source.name}'
        shutil.copy2(source, destination)
        if digest(destination) != before[str(source)]:
            raise RuntimeError('A capture input changed while freezing')
        frozen_inputs.append(artifact(destination))
    frozen_profile = frozen / f'01_{PROFILE.name}'
    report = {'capture_id': run_id, 'status': 'CPU_CAPTURE_NOT_STARTED',
              'instance_name': instance, 'language': args.language,
              'inputs': frozen_inputs, 'reader': artifact(reader), 'wpr': artifact(WPR),
              'capture_started': False, 'gamecore_loaded': False,
              'physical_multicore_verified': False, 'performance_improvement_verified': False,
              'accepted_stage_promoted': False, 'commands': []}

    def execute(name: str, command: list[str | Path], timeout: int = 30):
        command = [str(item) for item in command]
        result = subprocess.run(command, cwd=PROJECT, capture_output=True,
                                creationflags=subprocess.CREATE_NO_WINDOW, timeout=timeout)
        log = evidence / (name + '.log')
        log.write_bytes(result.stdout + result.stderr)
        report['commands'].append({'name': name, 'command': command,
                                   'exit_code': result.returncode, 'log': artifact(log)})
        return result

    started = False
    try:
        status = execute('global_status_before', [WPR, '-status'])
        if status.returncode or b'WPR is not recording' not in status.stdout + status.stderr:
            report['status'] = 'EXISTING_WPR_SESSION_REFUSED'
            return 2
        profile = execute('profile_details', [WPR, '-profiledetails',
                           str(frozen_profile) + '!ZeroSisCitySite', '-filemode'])
        profile_text = (profile.stdout + profile.stderr).decode('mbcs', errors='replace')
        if profile.returncode or not all(key in profile_text for key in
            ('CSwitch', 'ProcessThread', '2d76305f-91f4-4d48-9b32-281507669f73')):
            raise RuntimeError('WPR rejected the exact kernel and marker profile')
        topology = evidence / 'topology_before.json'
        snapshot = execute('topology_before', [reader, '--write-topology', topology])
        if snapshot.returncode or not topology.is_file():
            raise RuntimeError('Could not retain capture-time topology')
        report['topology_before'] = artifact(topology)
        own_before = execute('owned_status_before', [WPR, '-status', '-instancename', instance])
        if own_before.returncode or b'WPR is not recording' not in own_before.stdout + own_before.stderr:
            raise RuntimeError('The unique owned recording instance is not idle')
        start = execute('start', [WPR, '-start', str(frozen_profile) + '!ZeroSisCitySite',
                        '-filemode', '-recordtempto', temporary_recording,
                        '-instancename', instance])
        if start.returncode:
            report['status'] = 'WPR_CAPTURE_START_FAILED'
            return 2
        started = report['capture_started'] = True
        print('CITY_SITE_CPU_CAPTURE_STARTED ' + run_id, flush=True)
        sdk_run = execute('sdk_run', [sys.executable, '-B', '-X', 'utf8', RUNNER,
                          '--shared-lua', '--sdk-new-game', '--sdk-save-restore',
                          '--sdk-explore', '--workers', '0', '--sdk-city-sites',
                          '--city-site-workers', '4', '--city-site-cpu-trace',
                          '--save-restore', '--ui-popups', '--fixture-promotions',
                          '--fixture-unit-actions', '--extra-turns', '48',
                          '--language', args.language, '--timeout', str(args.timeout)],
                          timeout=args.timeout + 25)
        ids = re.findall(rb'^RUN_NEW_GAME (\d{8}T\d{6}Z_[0-9a-f]{12})\r?$', sdk_run.stdout, re.M)
        if len(ids) != 1:
            raise RuntimeError('The captured SDK diagnostic did not identify one immutable run')
        sdk_run_id = ids[0].decode('ascii')
        result_path = PROJECT / 'evidence/save_restore' / sdk_run_id / 'result.json'
        runtime = json.loads(result_path.read_text(encoding='utf8'))
        check_artifacts(runtime)
        report.update(sdk_run=artifact(result_path), sdk_run_id=sdk_run_id,
                      process_id=runtime.get('process_id'), gamecore_loaded=True)
        if sdk_run.returncode or runtime.get('status') != 'ISOLATED_NATIVE_SAVE_RESTORE_EXTENDED_PASS' or \
           runtime.get('city_site_cpu_trace_enabled') is not True:
            raise RuntimeError('The actual captured SDK run did not pass its runtime gates')
        stop = execute('stop', [WPR, '-stop', etl, '-instancename', instance], timeout=60)
        if stop.returncode or not etl.is_file():
            raise RuntimeError('The owned WPR recording could not be stopped and retained')
        started = False
        report['etl'] = artifact(etl)
        after_topology = evidence / 'topology_after.json'
        snapshot = execute('topology_after', [reader, '--write-topology', after_topology])
        if snapshot.returncode:
            raise RuntimeError('Could not retain post-capture topology')
        report['topology_after'] = artifact(after_topology)
        parsed = execute('reader', [reader, etl, '--topology', topology], timeout=120)
        if parsed.returncode not in (0, 3):
            raise RuntimeError('ETL reader failed rather than producing a scoped scheduling conclusion')
        payload = json.loads(parsed.stdout.decode('utf8', errors='strict'))
        parsed_path = evidence / 'reader.json'
        parsed_path.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf8')
        report['reader_result'] = artifact(parsed_path)
        report['status'] = 'ACTUAL_CITY_SITE_CPU_TRACE_RETAINED_PENDING_STRICT_VALIDATION'
        return 0
    except Exception as error:
        report.update(status='CITY_SITE_CPU_CAPTURE_FAILED', error=str(error))
        return 2
    finally:
        if started:
            execute('cancel_owned_after_failure', [WPR, '-cancel', '-instancename', instance])
        execute('owned_status_after', [WPR, '-status', '-instancename', instance])
        execute('global_status_after', [WPR, '-status'])
        after = {str(path): digest(path) for path in inputs}
        report['inputs_unchanged'] = before == after
        report['input_hashes_before'] = before
        report['input_hashes_after'] = after
        if before != after:
            report['status'] = 'CITY_SITE_CPU_CAPTURE_INPUT_CHANGED'
        target = evidence / 'result.json'
        target.write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
        print(json.dumps({'status': report['status'], 'result': artifact(target)}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    raise SystemExit(main())
