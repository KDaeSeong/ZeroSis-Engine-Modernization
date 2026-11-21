"""Verify the opt-in Found-value candidate with inherited worker settings suppressed."""
import argparse
import ast
import copy
import json
import re
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from collect_baseline import PROJECT, digest
from probe_world_builder import artifact
from verify_city_site_sdk_candidate import compare_state, inspect_run
from verify_first_turn_candidate import read_artifact
from verify_world_builder_map_object import check_artifacts

ROOT = PROJECT / 'evidence/found_value_default_environment'
EXPECTED_GAMECORE = 'cd1ef26f07e39b82dc2108e79dbd927eff4215662cc3bd8a01e1c3c33587814b'
DEFAULT_PROFILE = 'SERIAL_TRACE_OFF'
FOUND_TAGS = ('ZEROSIS_FOUND_VALUE_VALUES', 'ZEROSIS_FOUND_VALUE_AREAS',
              'ZEROSIS_FOUND_VALUE_TRACE')


def validate_default_environment_metadata(request, result):
    """Validate mirrored runtime metadata and request-only inherited-env contract."""
    for label, record in (('request', request), ('result', result)):
        if record.get('found_value_default_environment_profile') != DEFAULT_PROFILE or \
           record.get('found_value_workers_enabled') is not True or \
           type(record.get('found_value_workers')) is not int or \
           record.get('found_value_workers') != 0 or \
           record.get('found_value_trace_enabled') is not False:
            raise RuntimeError('Found-value default environment metadata differs in ' + label)
    if request.get('found_value_environment_overrides') != {} or \
       request.get('inherited_found_value_environment_removed') is not True:
        raise RuntimeError('Found-value request did not clear inherited environment and launch overrides')
    # The runner currently records launch overrides and inherited clearing on the
    # request, while result mirrors profile/workers/trace. If future result
    # schemas mirror the launch fields, require those copies to agree as well.
    if 'found_value_environment_overrides' in result and result['found_value_environment_overrides'] != {}:
        raise RuntimeError('Found-value result reports a nonempty default environment override')
    if 'inherited_found_value_environment_removed' in result and \
       result['inherited_found_value_environment_removed'] is not True:
        raise RuntimeError('Found-value result reports inherited variables were not cleared')


def canonical_ui_signature(value):
    """Normalize only JSON tuple/list representation; keep every value and order."""
    return json.loads(json.dumps(value, ensure_ascii=False, separators=(',', ':')))


def ui_signatures_equal(left, right):
    options = {'ensure_ascii': False, 'sort_keys': True, 'separators': (',', ':')}
    return json.dumps(canonical_ui_signature(left), **options) == \
        json.dumps(canonical_ui_signature(right), **options)


def ui_signature_negative_cases():
    current = [(10, 'standard', [4, 8, 15], [(0, 70), (1, 55)])]
    stored = json.loads(json.dumps(current, ensure_ascii=False))
    if current == stored:
        raise RuntimeError('UI signature fixture did not exercise tuple/list serialization shape')
    if not ui_signatures_equal(current, stored):
        raise RuntimeError('Equivalent tuple/list UI signature representations did not compare equal')
    mutations = {}
    for name, edit in (
        ('turn', lambda row: row[0].__setitem__(0, 11)),
        ('mode', lambda row: row[0].__setitem__(1, 'alternate')),
        ('rng_draws', lambda row: row[0].__setitem__(2, [4, 8, 16])),
        ('ranked_rows_order', lambda row: row[0][3].reverse()),
        ('ranked_row_value', lambda row: row[0][3][0].__setitem__(1, 71)),
    ):
        changed = copy.deepcopy(stored)
        edit(changed)
        if ui_signatures_equal(current, changed):
            raise RuntimeError('UI semantic mutation escaped canonical comparison: ' + name)
        mutations[name] = 'rejected'
    return {'raw_tuple_vs_json_array_differed': True,
            'tuple_to_json_array_accepted': True, 'semantic_mutations_rejected': mutations}


def metadata_negative_cases():
    request = {'found_value_default_environment_profile': DEFAULT_PROFILE,
               'found_value_workers_enabled': True, 'found_value_workers': 0,
               'found_value_trace_enabled': False, 'found_value_environment_overrides': {},
               'inherited_found_value_environment_removed': True}
    result = {'found_value_default_environment_profile': DEFAULT_PROFILE,
              'found_value_workers_enabled': True, 'found_value_workers': 0,
              'found_value_trace_enabled': False}
    validate_default_environment_metadata(request, result)
    cases = {}
    mutations = {
        'request_workers_nonzero': (lambda r, s: r.update(found_value_workers=4), None),
        'result_trace_enabled': (None, lambda r, s: s.update(found_value_trace_enabled=True)),
        'request_environment_override': (lambda r, s: r.update(found_value_environment_overrides={'ZEROSIS_FOUND_VALUE_WORKERS': '4'}), None),
        'request_inherited_environment_not_cleared': (lambda r, s: r.update(inherited_found_value_environment_removed=False), None),
        'request_profile_mismatch': (lambda r, s: r.update(found_value_default_environment_profile='EXPLICIT_OVERRIDES'), None),
        'result_workers_wrong_type': (None, lambda r, s: s.update(found_value_workers=True)),
        'result_inherited_copy_mismatch': (None, lambda r, s: s.update(inherited_found_value_environment_removed=False)),
    }
    for name, (mutate_request, mutate_result) in mutations.items():
        bad_request = copy.deepcopy(request)
        bad_result = copy.deepcopy(result)
        if mutate_request:
            mutate_request(bad_request, bad_result)
        if mutate_result:
            mutate_result(bad_request, bad_result)
        try:
            validate_default_environment_metadata(bad_request, bad_result)
        except RuntimeError:
            cases[name] = 'rejected'
        else:
            raise RuntimeError('Default environment metadata negative case was accepted: ' + name)
    if len(cases) != len(mutations):
        raise RuntimeError('Default environment metadata regression did not cover every negative case')
    return {'valid_default_accepted': True, 'negative_cases_rejected': cases}


def local_python_closure(entry):
    tools = PROJECT / 'tools'
    pending = [entry.resolve()]
    closure = {}
    edges = []
    while pending:
        path = pending.pop()
        if path in closure:
            continue
        if not path.is_file() or not path.is_relative_to(tools):
            raise RuntimeError('Python verifier closure escaped the tools directory')
        tree = ast.parse(path.read_text(encoding='utf8'), filename=str(path))
        closure[path] = tree
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names.append(node.module)
            for name in names:
                module = tools / (name.replace('.', '/') + '.py')
                if module.is_file():
                    edges.append((path, module))
                    pending.append(module.resolve())
    return closure, edges


def comparison_path(argument):
    path = Path(argument).resolve()
    if path.is_dir():
        path = path / 'conformance.json'
    if not path.is_file():
        raise RuntimeError('The Found-value 8-matrix conformance report does not exist')
    if path.name == 'latest.json':
        pointer = json.loads(path.read_text(encoding='utf8'))
        if not isinstance(pointer, dict) or not isinstance(pointer.get('path'), str) or \
           not isinstance(pointer.get('sha256'), str):
            raise RuntimeError('Malformed Found-value comparison evidence pointer')
        target = Path(pointer['path']).resolve()
        if not target.is_file() or digest(target) != pointer['sha256']:
            raise RuntimeError('Found-value comparison pointer target changed')
        path = target
    return path


def read_sdk_identity(reference):
    if not isinstance(reference, dict):
        raise RuntimeError('Found-value run does not reference a linked SDK build report')
    sdk = read_artifact(reference)
    check_artifacts(sdk)
    gamecore = sdk.get('gamecore')
    if sdk.get('status') != 'FOUND_VALUE_SDK_CANDIDATE_LINKED' or \
       sdk.get('active_sdk_updated') is not False or sdk.get('stage_updated') is not False or \
       sdk.get('mods_updated') is not False or not isinstance(gamecore, dict) or \
       gamecore.get('sha256') != EXPECTED_GAMECORE:
        raise RuntimeError('Found-value SDK identity or no-promotion contract differs')
    return {'build_id': sdk.get('build_id'), 'gamecore_sha256': gamecore['sha256']}


def read_comparison(path):
    report = json.loads(path.read_text(encoding='utf8'))
    check_artifacts(report)
    if report.get('status') != 'ACTUAL_SDK_FOUND_VALUE_ORDERED_RESULTS_AND_RESTORE_PASS' or \
       report.get('found_value_worker_settings') != [0, 1, 2, 4] or \
       report.get('physical_multicore_verified') is not False or \
       report.get('performance_improvement_verified') is not False or \
       report.get('active_sdk_updated') is not False or report.get('stage_updated') is not False:
        raise RuntimeError('Comparison report is not the complete isolated Found-value 8-matrix proof')
    keyed = {}
    for row in report.get('runs', []):
        key = (row.get('language'), row.get('found_value_workers'))
        if key in keyed:
            raise RuntimeError('Duplicate language/worker row in comparison proof')
        keyed[key] = row
    expected = {(language, workers) for language in ('en_US', 'ko_KR') for workers in (0, 1, 2, 4)}
    if set(keyed) != expected:
        raise RuntimeError('Comparison proof does not contain EN/KO workers 0/1/2/4')
    for language in ('en_US', 'ko_KR'):
        baseline = keyed[language, 0]
        calls = baseline.get('found_value_calls')
        if not isinstance(calls, list) or len(calls) != 200 or \
           any(call.get('trace', {}).get('mode') != 'scalar-original' for call in calls):
            raise RuntimeError('Comparison proof scalar reference lacks its 200 traced calls')
        if baseline.get('inputs', {}).get('CvGameCoreDLL_Expansion2_x64.dll') != EXPECTED_GAMECORE:
            raise RuntimeError('Comparison proof worker-zero row uses a different Found-value GameCore')
        if read_sdk_identity(baseline.get('found_value_sdk_build'))['build_id'] is None:
            raise RuntimeError('Comparison proof worker-zero row lacks a build identifier')
    return report, keyed


def inspect_default_run(run_id, options, output_dir):
    row = inspect_run(run_id, options, output_dir)
    result = read_artifact(row['result'])
    request = read_artifact(result['request'])
    validate_default_environment_metadata(request, result)
    sdk_ref = request.get('found_value_sdk_build')
    sdk_identity = read_sdk_identity(sdk_ref)
    if sdk_identity['gamecore_sha256'] != EXPECTED_GAMECORE or \
       row['inputs'].get('CvGameCoreDLL_Expansion2_x64.dll') != EXPECTED_GAMECORE:
        raise RuntimeError('Default environment run did not use the required unchanged Found-value SDK candidate')
    output = Path(result['stdout']['path']).read_text(encoding='utf8')
    error = Path(result['stderr']['path']).read_text(encoding='utf8')
    if any(tag in output or tag in error for tag in FOUND_TAGS):
        raise RuntimeError('Found-value trace-off run emitted a VALUES/AREAS/TRACE record')
    if row.get('found_value_workers_enabled') is not True or row.get('found_value_workers') != 0 or \
       row.get('found_value_sdk_build') != sdk_ref:
        raise RuntimeError('Inspected default environment run differs from its request metadata')
    if row.get('final_turn') != 50 or row.get('ui_popups_enabled') is not True or \
       row.get('fixture_promotions_enabled') is not True or \
       row.get('fixture_unit_actions_enabled') is not True or \
       row.get('fixture_unit_actions_verified') is not True or not row.get('action_records'):
        raise RuntimeError('Default environment run did not verify the required 50-turn UI/action profile')
    row['default_environment_request'] = {
        'profile': request['found_value_default_environment_profile'],
        'workers_enabled': request['found_value_workers_enabled'],
        'workers': request['found_value_workers'],
        'trace_enabled': request['found_value_trace_enabled'],
        'environment_overrides': request['found_value_environment_overrides'],
        'inherited_environment_removed': request['inherited_found_value_environment_removed'],
    }
    row['found_value_trace_records_absent'] = True
    row['found_value_build_id'] = sdk_identity['build_id']
    row['found_value_gamecore_sha256'] = sdk_identity['gamecore_sha256']
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', action='append', default=[])
    parser.add_argument('--comparison')
    parser.add_argument('--ui-popups', action='store_true')
    parser.add_argument('--fixture-promotions', action='store_true')
    parser.add_argument('--fixture-unit-actions', action='store_true')
    parser.add_argument('--self-test', action='store_true', help='Run only pure default-metadata negative cases')
    args = parser.parse_args()
    if args.self_test:
        if args.run or args.comparison or args.ui_popups or args.fixture_promotions or args.fixture_unit_actions:
            parser.error('--self-test cannot be combined with runtime verification arguments')
        print(json.dumps({'status': 'FOUND_VALUE_DEFAULT_METADATA_REGRESSION_PASS',
                          'metadata_cases': metadata_negative_cases(),
                          'ui_signature_cases': ui_signature_negative_cases(),
                          'game_executed': False, 'build_performed': False}, ensure_ascii=False))
        return
    if len(args.run) != 2 or len(set(args.run)) != 2 or not args.comparison:
        parser.error('Provide exactly two distinct EN/KO run IDs and the frozen 8-matrix comparison proof')
    if not (args.ui_popups and args.fixture_promotions and args.fixture_unit_actions):
        parser.error('Default environment comparison requires --ui-popups --fixture-promotions --fixture-unit-actions')
    if any(not re.fullmatch(r'\d{8}T\d{6}Z_[0-9a-f]{12}', run_id) for run_id in args.run):
        parser.error('Only existing isolated run IDs are accepted')
    closure, edges = local_python_closure(Path(__file__).resolve())
    if len({path.name.casefold() for path in closure}) != len(closure):
        raise RuntimeError('Python verifier closure contains colliding frozen filenames')
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_') + uuid.uuid4().hex[:12]
    directory = ROOT / run_id
    frozen_dir = directory / 'validators'
    frozen_dir.mkdir(parents=True, exist_ok=False)
    before = {path: digest(path) for path in closure}
    frozen_records = []
    for path in sorted(closure, key=lambda item: str(item).casefold()):
        target = frozen_dir / path.name
        shutil.copy2(path, target)
        if digest(target) != before[path]:
            raise RuntimeError('A Python verifier changed while freezing its source')
        frozen_records.append({'original_source_path': str(path),
                               'original_source_sha256': before[path],
                               'frozen': artifact(target)})
    proof_path = comparison_path(args.comparison)
    proof_sha = digest(proof_path)
    comparison, keyed = read_comparison(proof_path)
    options = SimpleNamespace(ui_popups=True, fixture_promotions=True, fixture_unit_actions=True,
                              sdk_found_values=True, found_value_workers=0)
    rows = [inspect_default_run(item, options, directory) for item in args.run]
    by_language = {row['language']: row for row in rows}
    if len(by_language) != 2 or set(by_language) != {'en_US', 'ko_KR'}:
        raise RuntimeError('Default environment runs must cover English and Korean once each')
    comparison_rows = []
    for language in ('en_US', 'ko_KR'):
        actual = by_language[language]
        baseline = keyed[language, 0]
        actual_sdk = read_sdk_identity(actual.get('found_value_sdk_build'))
        baseline_sdk = read_sdk_identity(baseline.get('found_value_sdk_build'))
        if actual_sdk != baseline_sdk:
            raise RuntimeError('Default environment run changed the selected Found-value SDK build identity')
        if actual['inputs'] != baseline['inputs'] or actual['final_turn'] != baseline['final_turn'] or \
           actual['workers'] != baseline['workers'] or actual['command'] != baseline['command']:
            raise RuntimeError('Default environment run changed input hashes, turn length, or command profile')
        compare_state(actual, baseline)
        if not ui_signatures_equal(actual.get('official_ui_signature'),
                                   baseline.get('official_ui_signature')):
            raise RuntimeError('Default environment run changed official UI RNG or popup ranking')
        comparison_rows.append({'language': language, 'reference_run_id': baseline['run_id'],
                                'default_run_id': actual['run_id'],
                                'full_input_hashes_equal': True, 'final_turn_equal': True,
                                'native_archives_continuation_and_actions_equal': True,
                                'official_ui_signature_equal': True})
    if proof_sha != digest(proof_path):
        raise RuntimeError('The frozen 8-matrix comparison proof changed during verification')
    if any(digest(path) != value for path, value in before.items()):
        raise RuntimeError('A Python verifier source changed during default environment verification')
    source_integrity = [{'original_source_path': str(path), 'sha256_before': value,
                         'sha256_after': digest(path), 'unchanged': digest(path) == value}
                        for path, value in sorted(before.items(), key=lambda item: str(item[0]).casefold())]
    report = {
        'status': 'ACTUAL_SDK_FOUND_VALUE_DEFAULT_ENVIRONMENT_STATE_AND_UI_PASS',
        'validators': frozen_records,
        'validator_import_edges': [{'from': str(left), 'to': str(right)} for left, right in edges],
        'validator_ast_closure_files': len(closure),
        'validator_source_integrity': source_integrity,
        'validator_inputs_unchanged': True,
        'comparison_proof': {'path': str(proof_path), 'sha256': proof_sha,
                             'status': comparison['status'],
                             'found_value_workers': comparison['found_value_worker_settings']},
        'default_environment_runs': rows,
        'comparisons': comparison_rows,
        'found_value_trace_records_absent': True,
        'found_value_scores_compared_in_default_runs': False,
        'worker_jobs_observed_in_default_runs': False,
        'physical_worker_execution_absence_verified': False,
        'physical_multicore_verified': False,
        'performance_improvement_verified': False,
        'sdk_gamecore_sha256': EXPECTED_GAMECORE,
        'found_value_default_profile': DEFAULT_PROFILE,
        'actual_save_restore_50_turns_and_ui_actions_checked': True,
        'accepted_stage_promoted': False, 'active_sdk_updated': False, 'stage_updated': False,
        'scope': 'ACTUAL_SDK_DEFAULT_ENVIRONMENT_TRACE_ABSENCE_AND_MATCHING_NATIVE_STATE_CONTINUATION_UI',
    }
    check_artifacts(report)
    target = directory / 'conformance.json'
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    pointer = ROOT / 'latest.json'
    pointer_tmp = ROOT / ('latest.json.tmp-' + uuid.uuid4().hex)
    pointer_tmp.write_text(json.dumps(artifact(target), indent=2) + '\n', encoding='utf8')
    pointer_tmp.replace(pointer)
    print(json.dumps({'status': report['status'], 'runs': len(rows),
                      'evidence': artifact(target)}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
