"""Attest current overwrite payloads through the preserved read-only PE parser.

The shared deletion attestor is imported as Python source, without changing
its file or evidence. Only this stage's scope/approved-source contract and its
historical negative-control detail are injected into that private module.
No PE image is mapped, loaded as native code, or executed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re

PROJECT = Path(__file__).absolute().parents[3]
STAGE = Path(__file__).absolute().parent
SHARED = PROJECT / 'evidence/save_delete/linked_candidate/verify_candidate.py'
SHARED_SHA256 = 'dd06ea0c0b31faa2423639eb2f95fdd11c3ffcd6ae1ae48a9505280e3d6ba4da'
SOURCE_CONFORMANCE = PROJECT / 'evidence/save_overwrite/source_contract/conformance.json'
SOURCE_CONFORMANCE_SHA256 = '7b69f3fca41b188d7ff6b403183f0cc2964d47d2e9f135ad9b339f7ff04e43cb'
DONOR = '20261016T110835Z_800f48fd88c0'
REQUIRED_CURRENT_FEATURE = (
    'Source/Host/NativeSaveCatalog.h', 'Source/Host/UiSaveMenuContract.h',
    'Source/Host/UiPopupContext.h', 'Source/Host/InteractiveGameSession.h',
    'Source/Host/UiScene.lua', 'Source/Presentation/UiPresentationInput.lua',
    'tools/ui_pixel_scene.py',
)
UNCHANGED_BASELINES = ('Source/Host/UiLoadMenuContract.h', 'tools/prepare_ui_popup_assets.py')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_shared():
    if sha(SHARED) != SHARED_SHA256:
        raise RuntimeError('Preserved common attestor changed before import')
    spec = importlib.util.spec_from_file_location('zerosis_preserved_delete_pe_attestor', SHARED)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.require(module.norm(module.PROJECT) == module.norm(PROJECT), 'Shared attestor points to another project')
    module.STAGE = STAGE
    module.REQUIRED_FEATURE_SOURCES = REQUIRED_CURRENT_FEATURE
    module.read_feature_scope = lambda inputs: read_feature_scope(module, inputs)
    original_negative = module.verify_historical_negative

    def negative(inputs, scope, current_scene):
        result = original_negative(inputs, scope, current_scene)
        donor = json.loads(inputs.ref(scope['donor_build']).decode('utf-8-sig'))
        rows = [row for row in donor['sources'] if Path(row['original_source']).name == 'UiPresentationInput.lua']
        module.require(len(rows) == 1, 'Historical input addendum is absent or duplicated')
        old = inputs.ref(rows[0])
        current = inputs.read(PROJECT / 'Source/Presentation/UiPresentationInput.lua')
        module.require(old != current, 'Historical donor is not a different-input negative control')
        # B6 remains valid evidence for the previous deletion stage. Only this
        # new overwrite acceptance is rejected; do not relabel its old scope.
        result.pop('rejected_as_current_owned_delete', None)
        result['rejected_as_current_owned_overwrite'] = True
        result['current_overwrite_feature_rejected'] = True
        result['historical_input_addendum_sha256'] = module.digest(old)
        result['current_input_addendum_sha256'] = module.digest(current)
        result['rejection'] = 'Actual historical embedded scene and both approved current Scene/input-addendum source bytes differ'
        return result

    module.verify_historical_negative = negative
    return module


def read_feature_scope(shared, inputs):
    inputs.read(Path(__file__))
    shared.require(shared.digest(inputs.read(SHARED)) == SHARED_SHA256, 'Preserved common attestor changed')
    scope_path = STAGE / 'scope.json'
    scope = inputs.document(scope_path)
    shared.require(scope['schema'] == 'zerosis.owned_save_overwrite_linked_scope.v1' and
                   scope['retail_mod_test_hold_active'] is True and scope['default_promoted'] is False and
                   scope['host_gamecore_hwnd_executed'] is False,
                   'Overwrite linked candidate did not preserve its private hold/scope')
    for row in scope['protected_artifacts'].values():
        inputs.ref(row)
    inputs.ref(scope['header_recovery'])
    inputs.ref(scope['prepared_assets_recovery'])
    inputs.ref(scope['common_helper'])
    raw = inputs.ref(scope['prior_source_conformance'], SOURCE_CONFORMANCE)
    shared.require(shared.digest(raw) == SOURCE_CONFORMANCE_SHA256, 'Approved overwrite source receipt differs')
    source = json.loads(raw.decode('utf-8-sig'))
    shared.require(source['status'] == 'PASS_SOURCE_AND_COMPONENT_ONLY', 'Approved overwrite source stage is absent')
    pinned = {}
    for row in source['sources']:
        path = Path(row['path'])
        shared.require(path.is_absolute() and path.is_relative_to(PROJECT), 'Approved source escaped the current project')
        relative = path.relative_to(PROJECT).as_posix()
        shared.require(relative not in pinned, 'Duplicate approved overwrite source')
        inputs.ref(row, PROJECT / relative)
        pinned[relative] = row
    shared.require(set(REQUIRED_CURRENT_FEATURE) <= set(pinned), 'Approved source stage omitted a current overwrite input')

    declared = scope.get('source19_seals')
    if declared is not None:
        shared.require(type(declared) in (dict, list), 'Declared source ledger has an unknown schema')
        declared_rows = list(declared.values()) if isinstance(declared, dict) else declared
        observed = {}
        for row in declared_rows:
            path = Path(row['path'])
            shared.require(path.is_absolute() and path.is_relative_to(PROJECT), 'Declared source escaped the project')
            relative = path.relative_to(PROJECT).as_posix()
            shared.require(relative not in observed, 'Declared source ledger repeats an input')
            observed[relative] = row
        shared.require(observed == pinned, 'Declared source ledger differs from the sealed source conformance')

    donor = json.loads(inputs.ref(scope['donor_build']).decode('utf-8-sig'))
    shared.require(donor['build_id'] == DONOR and donor['status'] == 'UI_WINDOW_HOST_CANDIDATE_BUILT',
                   'Overwrite donor is not the retained successful B6 candidate')
    unchanged = scope['unchanged_baseline_seals']
    shared.require(type(unchanged) is dict and set(unchanged) == set(UNCHANGED_BASELINES),
                   'Unchanged baseline seals must name exactly the retained load contract and preparer')
    for relative in UNCHANGED_BASELINES:
        row = unchanged[relative]
        current = inputs.ref(row, PROJECT / relative)
        if relative.endswith('UiLoadMenuContract.h'):
            rows = [entry for entry in donor['sources'] if shared.norm(entry['original_source']) == shared.norm(PROJECT / relative)]
            shared.require(len(rows) == 1 and inputs.ref(rows[0]) == current,
                           'Unchanged LoadMenu contract differs from the sealed B6 source')
        else:
            frozen = PROJECT / 'Build/UiWindowHost' / DONOR / 'frozen/project' / relative
            shared.require(inputs.read(frozen) == current and
                           shared.digest(current) == donor['source_hashes_before']['popup_asset_preparer'],
                           'Unchanged UI preparer differs from the sealed B6 input')
        pinned[relative] = row
    return scope_path, scope, pinned


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--build-id')
    mode.add_argument('--readiness-only', action='store_true')
    args = parser.parse_args()
    shared = load_shared()
    if args.build_id:
        shared.require(re.fullmatch(r'\d{8}T\d{6}Z_[0-9a-f]{12}', args.build_id), 'Invalid immutable build ID')
        shared.require(args.build_id != DONOR, 'Historical B6 cannot be the new overwrite candidate')
        shared.require(not (STAGE / ('attestation_' + args.build_id + '.json')).exists(), 'Successful attestation already exists')
    boundaries = dict(host_executed=False, gamecore_loaded=False, dll_loaded=False, hwnd_created=False,
                      mods_or_user_saves_accessed=False, retail_user_settings_accessed=False,
                      game_process_queries=0, default_promoted=False, binary_modified=False,
                      shared_attestor_or_historical_evidence_modified=False)
    try:
        if args.readiness_only:
            inputs = shared.Inputs()
            scope_path, scope, pinned = read_feature_scope(shared, inputs)
            inputs.finish()
            result = dict(status='PASS_READ_ONLY_SOURCE_SCOPE_READY_NO_PE_INSPECTION',
                          candidate_scope=shared.artifact(scope_path, inputs), approved_feature_sources=pinned,
                          source_conformance=scope['prior_source_conformance'], actual_pe_inspected=False)
            filename = 'readiness_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json'
        else:
            result = shared.verify(args.build_id)
            result.update(status='PASS', native_overwrite_verified=False, native_binding_execution_verified=False,
                          retail_save_mod_compatibility_verified=False, actual_pe_inspected=True,
                          feature_scope='CURRENT_OWNED_SAVE_OVERWRITE_SOURCE_APPROVAL_AND_EXACT_EMBEDDED_SCENE_INPUT_BYTES')
            filename = 'attestation_' + args.build_id + '.json'
    except Exception as error:
        failure = dict(schema='zerosis.owned_save_overwrite_linked_pe_attestation.v1', status='FAIL',
                       build_id=args.build_id, utc=datetime.now(timezone.utc).isoformat(),
                       error_type=type(error).__name__, error=str(error), verifier_sha256=sha(Path(__file__)),
                       shared_attestor_sha256=sha(SHARED), **boundaries)
        output = shared.write_new('failure_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json', failure)
        print(json.dumps(dict(status='FAIL', report=str(output), error=str(error))))
        raise
    result.update(schema='zerosis.owned_save_overwrite_linked_pe_attestation.v1',
                  utc=datetime.now(timezone.utc).isoformat(), verifier_sha256=sha(Path(__file__)),
                  shared_attestor={'path': str(SHARED), 'sha256': SHARED_SHA256}, **boundaries)
    output = shared.write_new(filename, result)
    print(json.dumps(dict(status=result['status'], build_id=args.build_id, report=str(output), sha256=sha(output),
                          payloads=len(result.get('pe_catalog', {}).get('exact_payloads', {})),
                          host_executed=False, native_overwrite_verified=False)))


if __name__ == '__main__':
    main()
