"""Execute SQL failure/rollback cases and compare owned copies of cached rules."""
import json
import re
import shutil
import uuid
from pathlib import Path
from collect_baseline import PROJECT, digest, read_text, pe_header
from native_build import run
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts

MARKERS = {
    'rollback_failure': ('ROLLBACK_FAILURE|explicit_exception|outer_transaction_canceled_by_sqlite|connection_closed',),
    'original': ('ORIGINAL_DEFECT|8_failures_reported_success|partial_writes',),
    'candidate': ('CANDIDATE_ATOMIC|8_trigger_failures_rolled_back|outer_transaction_preserved|retry_success',
                  'EDGE|5_bad_metadata_or_schema|quoted_long_utf8_key|logger_exception_rollback|deferred_commit_failure|null_closed')}
COMMON = 'SCOPE|exact_sdk_postprocessing|same_real_x64_database|no_gamecore_loaded'


def main():
    root = PROJECT / 'evidence/database_postprocess'
    bp = root / 'build_result.json'
    build = json.loads(bp.read_text(encoding='utf-8'))
    check_artifacts(build)
    allowed = {'zerosisdatabase_x64.dll', 'kernel32.dll', 'msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll'}
    for audit in build['audits']:
        if not audit['dependencies'] or any(d.lower() not in allowed and not d.lower().startswith('api-ms-win-crt-') for d in audit['dependencies']):
            raise RuntimeError('Unexpected SQL test dependency')
    rows, issues, normal = [], [], {}
    for name in ('original', 'candidate', 'rollback_failure'):
        exe = Path(build['builds']['candidate' if name == 'rollback_failure' else name]['executable']['path'])
        if pe_header(exe)['architecture'] != 'x64':
            raise RuntimeError('Unexpected SQL test architecture')
        result = run([exe, *(['--rollback-failure'] if name == 'rollback_failure' else [])], cwd=exe.parent, timeout=30)
        log = root / (name + '_execution.log')
        log.write_bytes(result.stdout + result.stderr)
        text = read_text(log)
        match = re.search(r'^PASS\|(\d+)\s*$', text, re.M)
        checks = int(match[1]) if match else 0
        golden = re.search(r'NORMAL_BEGIN\r?\n(.*?)NORMAL_END', text, re.S)
        normal[name] = golden[1].replace('\r\n', '\n') if golden else None
        if result.returncode or not checks or any(m not in text for m in (*MARKERS[name], COMMON)):
            issues.append('Postprocessing execution failed: ' + name)
        rows.append({'name': name, 'executable': artifact(exe), 'exit_code': result.returncode,
                     'log': artifact(log), 'checks': checks})
        print(json.dumps({'run': name, 'exit_code': result.returncode, 'checks': checks}), flush=True)
        if result.returncode:
            print(text[-1800:], flush=True)
    same = normal['original'] is not None and normal['original'] == normal['candidate']
    if not same:
        issues.append('Valid postprocessing rules changed')
    corpus_source = PROJECT / 'evidence/database/corpus/conformance.json'
    corpus = json.loads(corpus_source.read_text(encoding='utf-8'))
    directory = PROJECT / 'Build/DatabasePostprocess/corpus' / uuid.uuid4().hex
    directory.mkdir(parents=True)
    copies, corpus_runs, comparisons = [], [], []
    for entry in corpus['copies']:
        source = Path(entry['copy']['path'])
        if source.name not in ('Civ5CoreDatabase.db', 'Civ5DebugDatabase.db'):
            continue
        if not source.is_relative_to(PROJECT) or digest(source) != entry['copy']['sha256']:
            raise RuntimeError('Owned cached rules source changed')
        outputs = {}
        for name in ('original', 'candidate'):
            target = directory / (name + '_' + source.name)
            shutil.copyfile(source, target)
            if digest(target) != entry['copy']['sha256']:
                raise RuntimeError('Rule copy did not match source')
            before = artifact(target)
            exe = Path(build['builds'][name]['executable']['path'])
            result = run([exe, target], cwd=exe.parent, timeout=30)
            log = root / (name + '_' + source.stem + '.log')
            log.write_bytes(result.stdout + result.stderr)
            outputs[name] = result.stdout.replace(b'\r\n', b'\n')
            corpus_runs.append({'name': name, 'database': source.name, 'exit_code': result.returncode, 'log': artifact(log)})
            copies.append({'source': artifact(source), 'before_sha256': before['sha256'], 'after': artifact(target), 'only_project_owned_copy_modified': True})
            if result.returncode or b'CORPUS_RESULT|1' not in result.stdout:
                issues.append('Cached rules postprocessing failed: ' + name + '/' + source.name)
                print(result.stdout.decode('utf-8', errors='replace')[-1600:], flush=True)
        equal = outputs['original'] == outputs['candidate']
        comparisons.append({'database': source.name, 'equal_defines_resources': equal})
        if not equal:
            issues.append('Cached rules outputs changed: ' + source.name)
        if digest(source) != entry['copy']['sha256']:
            raise RuntimeError('Stable cached rules input modified')
    if len(comparisons) != 2:
        issues.append('Both cached rules databases required')
    report = {'status': 'DATABASE_POSTPROCESS_NATIVE_PASS' if not issues else 'DATABASE_POSTPROCESS_NATIVE_FAIL',
              'build': artifact(bp), 'verifier': artifact(Path(__file__).resolve()), 'runs': rows, 'issues': issues,
              'normal_rule_outputs_equal': same, 'trigger_failure_cases': 8, 'outer_transaction_cases': 4,
              'original_success_on_partial_failure_reproduced': not issues,
              'candidate_trigger_rollbacks_and_retry_verified': not issues,
              'deferred_commit_failure_rolled_back': not issues, 'logger_exception_cleanup_verified': not issues,
              'sqlite_whole_transaction_abort_propagated_as_exception': not issues,
              'metadata_schema_rejections': 5, 'corpus_source': artifact(corpus_source), 'corpus_copies': copies,
              'corpus_runs': corpus_runs, 'corpus_comparisons': comparisons,
              'same_accepted_x64_database_used_for_both_algorithms': True,
              'original_windows_game_binary_executed': False, 'global_database_accessor_instrumented': True,
              'gc_init_failure_propagation_implemented': False, 'whole_gc_lifecycle_verified': False,
              'all_sqlite_failure_modes_rollback_guaranteed': False,
              'gamecore_loaded': False, 'game_launched': False, 'game_multicore_verified': False}
    (root / 'conformance.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': report['status'], 'comparisons': comparisons, 'issues': issues}))
    if issues:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
