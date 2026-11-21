"""Read-only, phase-local retention audit; run only after Root publishes this phase.

The only output is this phase's new audit receipt. No cleanup, native execution,
process inspection, installed-game access, or whole-workspace scan is performed.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

sys.dont_write_bytecode = True
PROJECT = Path(__file__).absolute().parents[3]
STAGE = Path(__file__).absolute().parent
SYNTAX_STAGE = PROJECT/'evidence/serialization/direct_stream_count_syntax'
PUBLICATION = STAGE/'progress_update.json'
OUTPUT = STAGE/'post_publication_checks.json'
PREVIOUS = PROJECT/'evidence/retail_save_container/player_ai_late/post_publication_checks.json'
INDEX = PROJECT/'evidence/save_menu/20261013_original_screen/current_progress.json'
DOCUMENT = PROJECT/'docs/M7_RETAIL_SAVE_BOUNDARY.md'
TRACKING = STAGE/'port_patch_tracking.json'
IDENTITY_AUDIT = PROJECT/'evidence/goody_hut/runtime_fonts/preparation_identity_audit.json'
ABI_REPORT = STAGE/'build_result.json'
SYNTAX_REPORT = SYNTAX_STAGE/'build_result.json'
RUN_ID = '20261020T110323Z_27da680b90f1'
HOST_ID = '20261018T024443Z_23a2e7fdb8ea'
PREVIOUS_PIN = dict(path=str(PREVIOUS), bytes=40101,
    sha256='837b5dd20101bbf54991422f45caeee6dee69b81bf9c74732980081aeb840112')
INDEX_BEFORE = dict(path=str(INDEX), bytes=209372,
    sha256='518b6fe8b3545d231586ceb6edbd21e05c1d6811315346535338232a092dd70d')
DOCUMENT_BEFORE = dict(path=str(DOCUMENT), bytes=41369,
    sha256='3465bdacc61b7982bf98abe9c07d8da4cb1991418c9992c17c600bebd1bd8231')
PROTECTED_PINS = {
    'request': dict(path=str(PROJECT/'evidence/interactive_game'/RUN_ID/'request.json'), bytes=50167,
        sha256='7b04270096d0815c1ad682b3f99db2496b713db9cc7c5f5af05956d1744020f1'),
    'prepared': dict(path=str(PROJECT/'evidence/goody_hut/runtime_fonts/prepared.json'), bytes=989,
        sha256='796cdf84885c408903f96d2ff1c3d414aef2008317bdb33338d79c1e1a573fa4'),
    'runtime_identity': dict(path=str(IDENTITY_AUDIT), bytes=33616,
        sha256='e7b3de4e0c7ac30e8933ac52a8d5d2df0f32d0457dbf08fb40089164cb28719e'),
    'host_build': dict(path=str(PROJECT/'evidence/ui_window_host'/HOST_ID/'build_result.json'), bytes=662669,
        sha256='8e6a2a283d22e042202d98b5e59320de5de73d1f98c44762e409f21f7fea1a02'),
    'default_release': dict(path=str(PROJECT/'Play/EarlyAccess/release.json'), bytes=7907,
        sha256='5587028d64ff6206780837ee7112f0c34d62676fb0627ee099d4eb03aef9c2c5'),
    'default_launcher': dict(path=str(PROJECT/'tools/Start-Engine.ps1'), bytes=11697,
        sha256='c487ce6c89e374bb625961ce81cf6cbae210608c578542658038e6cb06173d7c'),
    'hold': dict(path=str(PROJECT/'evidence/goody_hut/runtime_fonts/system_freeze_hold.json'), bytes=2341,
        sha256='6e7443f5ef796c9eadee4f7fdbc4123545467031be1d5c641159283078f56a5b'),
}
SOURCE_AND_TOOLS = [PROJECT/rel for rel in (
    'Tests/sdk_direct_stream_counts.cpp', 'tools/verify_sdk_direct_stream_counts.py',
    'tools/verify_sdk_direct_stream_count_syntax.py', 'tools/publish_sdk_direct_stream_counts.py')]
OBSERVED = {}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def key(path):
    return os.path.normcase(os.path.abspath(path))


def within(path, parent):
    return Path(os.path.abspath(path)).is_relative_to(Path(os.path.abspath(parent)))


def guard(path):
    path = Path(os.path.abspath(path))
    require(within(path, PROJECT), 'Path outside the authorized engine workspace: ' + str(path))
    part = path
    while part != PROJECT.parent:
        try:
            info = part.lstat()
        except FileNotFoundError:
            pass
        else:
            require(not stat.S_ISLNK(info.st_mode) and
                    not (getattr(info, 'st_file_attributes', 0) & 0x400), 'Reparse path/ancestor: ' + str(part))
        part = part.parent
    require(path.resolve().is_relative_to(PROJECT.resolve()), 'Resolved path outside engine workspace')
    return path


def snapshot(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)


def artifact(path):
    path = guard(path)
    info = path.stat()
    require(stat.S_ISREG(info.st_mode), 'Expected a regular input file: ' + str(path))
    cached = OBSERVED.get(key(path))
    if cached is not None:
        require(cached['snapshot'] == snapshot(info), 'Input changed since it was hashed: ' + str(path))
        return dict(cached['artifact'])
    hasher = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            hasher.update(chunk)
    require(snapshot(path.stat()) == snapshot(info), 'Input changed during hashing: ' + str(path))
    row = dict(path=str(path), bytes=info.st_size, sha256=hasher.hexdigest())
    OBSERVED[key(path)] = dict(artifact=row, snapshot=snapshot(info),
                               file_identity=[info.st_dev, info.st_ino], hardlink_count=info.st_nlink)
    return dict(row)


def pin(expected, expected_path=None):
    require(isinstance(expected, dict) and set(('path', 'bytes', 'sha256')).issubset(expected), 'Malformed artifact pin')
    require(isinstance(expected['bytes'], int) and expected['bytes'] >= 0 and
            re.fullmatch(r'[0-9a-f]{64}', expected['sha256']) is not None, 'Invalid bytes/hash pin')
    if expected_path is not None:
        require(key(expected['path']) == key(expected_path), 'Artifact points at an unexpected file')
    actual = artifact(expected['path'])
    require(actual['bytes'] == expected['bytes'] and actual['sha256'] == expected['sha256'],
            'Pinned file changed: ' + actual['path'])
    return actual


def load(path):
    artifact(path)
    return json.loads(Path(path).read_bytes())


def check_publication(sha256):
    require(re.fullmatch(r'[0-9a-f]{64}', sha256) is not None, 'Publication SHA must be explicit')
    published = artifact(PUBLICATION)
    require(published['sha256'] == sha256, 'Publication receipt differs from the Root-provided SHA')
    publication = load(PUBLICATION)
    require(publication['before']['index'] == INDEX_BEFORE and publication['before']['document'] == DOCUMENT_BEFORE,
            'Publication did not start from this phase baseline')
    index = pin(publication['after']['index'], INDEX)
    document = pin(publication['after']['document'], DOCUMENT)
    expected_paths = dict(tracking=TRACKING, contract=STAGE/'site_contract.json',
                          independent=STAGE/'independent_review.json', coverage=STAGE/'native_coverage.json',
                          syntax=SYNTAX_REPORT, native=ABI_REPORT)
    require(set(publication['proofs']) == set(expected_paths), 'Publication proof set changed')
    proofs = {}
    for name, path in expected_paths.items():
        # Coverage may have a Root-selected filename, but it must remain a
        # direct JSON child of the exact current evidence stage.
        candidate = publication['proofs'][name]
        if name == 'coverage':
            selected = guard(candidate['path'])
            require(selected.parent == STAGE and selected.suffix == '.json', 'Coverage escaped this stage')
            path = selected
        proofs[name] = pin(candidate, path)
    require(len({key(row['path']) for row in proofs.values()}) == 6, 'Publication proof paths are not distinct')
    for field in ('host_runtime_or_default_promoted', 'host_gamecore_or_hwnd_executed',
                  'full_player_or_restore_approved', 'full_engine_goal_complete', 'sdk_restore_verified'):
        if field in publication:
            require(publication[field] is False, 'Publication exceeded component-only scope: ' + field)
    return publication, published, index, document, proofs


def frozen_inputs(previous, index):
    require(previous['index'] == INDEX_BEFORE and previous['document'] == DOCUMENT_BEFORE,
            'Prior audit baseline index/document changed')
    rows = previous['frozen_runtime_inputs']
    require(len(rows) == 24 and len({key(r['path']) for r in rows}) == 24,
            'Prior audit must identify twenty-four actual runtime files')
    runtime = PROJECT/'Build/InteractiveGameRuntime'/RUN_ID
    for row in rows:
        require(Path(row['path']).parent == runtime, 'Frozen runtime pin escaped R11')
        pin(row)
    protected = {name: pin(row) for name, row in PROTECTED_PINS.items()}
    identity = load(IDENTITY_AUDIT)
    require(identity['prepared'] == PROTECTED_PINS['prepared'] and identity['request'] == PROTECTED_PINS['request'] and
            identity['host_build'] == PROTECTED_PINS['host_build'], 'R11/B11 identity references changed')
    terrain = identity['shared_terrain_inputs']
    require(len(terrain) == 2 and {Path(r['path']).name for r in terrain} ==
            {'terrain-assets.manifest.json', 'terrain-assets.bin'}, 'Expected two actual shared terrain inputs')
    terrain_root = PROJECT/'Build/TerrainAssets/2bee85c22c77b0342896f827989ca7d6f4ca3ae8f4dfe3a2179faaab4d689b13'
    for row in terrain:
        require(Path(row['path']).parent == terrain_root, 'Shared terrain pin escaped its immutable root')
        pin(row)
    for field in ('host_executed', 'gamecore_loaded', 'hwnd_created', 'default_promoted', 'full_engine_goal_complete'):
        require(identity[field] is False, 'Prepared runtime identity approval changed: ' + field)
    require(index['current_host_build_id'] == HOST_ID and index['current_prepared_runtime']['run_id'] == RUN_ID and
            index['current_prepared_runtime']['host_build_id'] == HOST_ID, 'Current runtime/build pointers moved')
    current = index['current_prepared_runtime']
    for name, label in (('request', 'request'), ('prepared', 'prepared'), ('runtime_identity_audit', 'runtime_identity')):
        require(current[name] == PROTECTED_PINS[label], 'Current prepared pointer changed: ' + name)
    require(current['status'] == 'PREPARED_NOT_EXECUTED' and current['current_source_candidate'] is False and
            current['default_promoted'] is False and index['prepared_runtime_matches_latest_source'] is False,
            'Working-source component evidence was promoted to a runtime claim')
    require(index['full_engine_goal_complete'] is False and index['full_goal_redefined'] is False,
            'Original complete-engine goal was approved/redefined')
    default = index['default_publication']
    require(default['release'] == PROTECTED_PINS['default_release'] and default['launcher'] == PROTECTED_PINS['default_launcher'] and
            default['changed'] is False and default['new_candidate_promoted'] is False, 'Default publication moved')
    hold = load(PROTECTED_PINS['hold']['path'])
    isolation = index['user_mod_test_isolation']
    require(hold['engine_native_execution_still_held'] is True and
            hold['offline_resume']['native_host_gamecore_hwnd_execution_allowed'] is False and
            isolation['native_window_tests_held'] is True and isolation['retail_test_hold_still_active'] is True and
            isolation['release_requires_explicit_human_test_end'] is True, 'Retail mod-test hold changed')
    return rows, terrain, protected


def check_tracking():
    tracking = load(TRACKING)
    require(tracking['status'] == 'PORT_PATCH_TRACKING_RAM_REGEN_VERIFIED' and
            tracking['static_sites'] == 18 and tracking['native_width_fixes'] == 15 and
            tracking['cast_range_fixes'] == 3 and tracking['manifest_rows_changed'] == 8,
            'Unexpected finite patch tracking contract')
    before, after = tracking['before'], tracking['after']
    require(len(before) == len(after) == 10 and len({key(r['path']) for r in after}) == 10 and
            {key(r['path']) for r in before} == {key(r['path']) for r in after}, 'Expected ten exact modified files')
    for row in after:
        actual = pin(row)
        observed = OBSERVED[key(actual['path'])]
        require(observed['file_identity'] == row['file_identity'] and
                observed['snapshot'][3] == row['mtime_ns'], 'Frozen modified-file identity changed')
    difference = sum(r['bytes'] for r in after)-sum(r['bytes'] for r in before)
    require(difference == tracking['logical_delta_bytes'], 'Tracking modification delta is inconsistent')
    return tracking, difference


def bounded_build_root(report, parent):
    root = guard(report['build_root'])
    require(root.parent == parent and re.fullmatch(r'[0-9a-f]{16}', root.name) is not None and root.is_dir(),
            'Build report does not identify one exact current build root')
    return root


def phase_files(roots):
    # Deduplicate overlapping roots before walking. The ABI evidence stage is
    # STAGE itself; it is deliberately not added as a separate root.
    normalized = sorted({guard(root) for root in roots}, key=lambda p: (len(p.parts), key(p)))
    unique_roots = []
    for root in normalized:
        require(root.is_dir(), 'Missing current evidence/build root: ' + str(root))
        if not any(within(root, other) for other in unique_roots):
            unique_roots.append(root)
    paths = []
    for root in unique_roots:
        for directory, names, files in os.walk(root, topdown=True, followlinks=False):
            names.sort()
            files.sort()
            for name in names:
                guard(Path(directory)/name)
            for name in files:
                path = guard(Path(directory)/name)
                if key(path) != key(OUTPUT):
                    paths.append(path)
    paths.extend(SOURCE_AND_TOOLS)
    return unique_roots, sorted({key(path): path for path in paths}.values(), key=key)


def unique_files(paths):
    identities = {}
    for path in paths:
        row = artifact(path)
        observed = OBSERVED[key(path)]
        identity = tuple(observed['file_identity'])
        require(identity[1] != 0, 'Filesystem did not provide a usable file ID')
        if identity in identities:
            retained = identities[identity]
            require((retained['bytes'], retained['sha256']) == (row['bytes'], row['sha256']), 'One file ID has conflicting contents')
            retained['aliases'].append(row['path'])
        else:
            identities[identity] = dict(**row, file_identity=list(identity),
                hardlink_count=observed['hardlink_count'], aliases=[])
    return list(identities.values())


def retired_rows(reports, additional):
    collected, extra_receipts, retired_roots = [], [], []
    for label, report in reports:
        rows = report['retired_intermediates']
        require(isinstance(rows, list) and sum(r['bytes'] for r in rows) == report['retired_logical_bytes'],
                'Build retirement byte sum differs: ' + label)
        collected.extend(dict(row, receipt_scope=label) for row in rows)
    for path, expected in additional:
        path = guard(path)
        require(any(within(path, stage) for stage in (STAGE, SYNTAX_STAGE)) and path.suffix == '.json',
                'Extra retirement receipt escaped the exact phase stages')
        identity = artifact(path)
        require(identity['sha256'] == expected, 'Extra retirement receipt differs from Root-provided SHA')
        receipt = load(path)
        rows = receipt.get('retired_intermediates', receipt.get('retired_files'))
        require(isinstance(rows, list), 'Extra retirement receipt must have retired_intermediates or retired_files')
        if 'retired_logical_bytes' in receipt:
            require(sum(r['bytes'] for r in rows) == receipt['retired_logical_bytes'], 'Extra retirement sum differs')
        collected.extend(dict(row, receipt_scope=str(path)) for row in rows)
        extra_receipts.append(identity)
        for field in ('retired_root', 'retired_build_root'):
            if field in receipt:
                retired_roots.append(guard(receipt[field]))
    deduplicated = {}
    parents = (PROJECT/'Build/SdkDirectStreamCounts', PROJECT/'Build/SdkDirectStreamCountSyntax')
    for row in collected:
        path = guard(row['path'])
        stage_failure = path.parent in (STAGE, SYNTAX_STAGE) and (
            path.name in ('native_failed_attempt.json', 'failed_attempt.json') or path.name.endswith('.stage'))
        require((any(within(path, parent) for parent in parents) and path not in parents) or stage_failure,
                'Retirement row escaped this phase build families')
        require(isinstance(row['bytes'], int) and row['bytes'] >= 0 and
                re.fullmatch(r'[0-9a-f]{64}', row['sha256']) is not None, 'Malformed retired file descriptor')
        require(not path.exists(), 'Retired file is still present: ' + str(path))
        file_id = row.get('file_identity')
        identity = tuple(file_id) if isinstance(file_id, list) and len(file_id) == 2 else key(path)
        unique = (identity, row['sha256'], row['bytes'], row.get('mtime_ns'))
        if unique in deduplicated:
            deduplicated[unique]['receipt_scopes'].append(row['receipt_scope'])
        else:
            deduplicated[unique] = {**row, 'receipt_scopes': [row['receipt_scope']]}
    for root in retired_roots:
        require(any(root.parent == parent for parent in parents), 'Retired root escaped the exact build families')
        require(not root.exists(), 'Retired failed build root remains: ' + str(root))
    return list(deduplicated.values()), extra_receipts, [str(p) for p in retired_roots]


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publication-sha256', required=True,
                        help='Exact SHA-256 supplied by Root after publication is complete.')
    parser.add_argument('--retirement-receipt', nargs=2, action='append', default=[], metavar=('PATH', 'SHA256'))
    args = parser.parse_args()
    require(not sys.flags.optimize and not OUTPUT.exists(), 'Use an unoptimized first audit run; never overwrite a retained receipt')
    guard(OUTPUT)
    previous_identity = pin(PREVIOUS_PIN)
    previous = load(PREVIOUS)
    publication, published, index_identity, document_identity, proofs = check_publication(args.publication_sha256)
    index = load(INDEX)
    runtime, terrain, protected = frozen_inputs(previous, index)
    tracking, sdk_delta = check_tracking()
    native, syntax = load(ABI_REPORT), load(SYNTAX_REPORT)
    require(native['status'] == 'PASS_SDK_DIRECT_STREAM_COUNT_ABI_COMPONENT' and
            syntax['status'] == 'PASS_ACTUAL_SDK_DIRECT_STREAM_COUNT_SYNTAX' and
            native['all_canonical_popup_wires_byte_identical'] is True and
            syntax['all_eight_changed_translation_units_syntax_checked'] is True,
            'Native/syntax component evidence is not complete')
    for report in (native, syntax):
        require(report['host_gamecore_or_hwnd_executed'] is False and report['full_engine_goal_complete'] is False and
                report['protected_unchanged'] is True, 'Build proof exceeded the allowed scope')
    abi_root = bounded_build_root(native, PROJECT/'Build/SdkDirectStreamCounts')
    syntax_root = bounded_build_root(syntax, PROJECT/'Build/SdkDirectStreamCountSyntax')
    roots, files = phase_files([STAGE, SYNTAX_STAGE, abi_root, syntax_root])
    modified_ids = {tuple(OBSERVED[key(r['path'])]['file_identity']) for r in tracking['after']}
    unique = unique_files(files)
    require(not any(tuple(row['file_identity']) in modified_ids for row in unique),
            'A modified baseline file was also counted as a new retained file')
    retired, extra, retired_roots = retired_rows([('native', native), ('syntax', syntax)], args.retirement_receipt)
    intermediates = [row for row in unique if Path(row['path']).suffix.lower() in ('.obj', '.pch', '.exp', '.lib') or
                     Path(row['path']).name.lower() in ('read_build_environment.cmd', 'setup.cmd', 'build_environment.cmd',
                                                       'native_failed_attempt.json', 'failed_attempt.json') or
                     Path(row['path']).name.endswith('.stage')]
    for observed in OBSERVED.values():
        require(snapshot(Path(observed['artifact']['path']).stat()) == observed['snapshot'], 'An audited input changed before publication')
    index_doc_delta = index_identity['bytes']+document_identity['bytes']-INDEX_BEFORE['bytes']-DOCUMENT_BEFORE['bytes']
    retained_bytes = sum(row['bytes'] for row in unique)
    report = dict(schema='zerosis.sdk_direct_stream_counts.post_publication_audit.v1',
        status='PASS_DIRECT_STREAM_COUNT_PUBLICATION_AND_PHASE_STORAGE' if not intermediates else 'FAIL_REMAINING_PHASE_INTERMEDIATES',
        utc=datetime.now(timezone.utc).isoformat(), previous_goal_turn_classification='progress',
        previous_post_publication_audit=previous_identity, publication=published,
        index=index_identity, document=document_identity, proofs=proofs,
        protected_runtime_pins=protected, frozen_runtime_inputs_unchanged=len(runtime), frozen_runtime_inputs=runtime,
        shared_terrain_inputs_unchanged=len(terrain), shared_terrain_inputs=terrain,
        runtime_and_default_unchanged=True, retail_mod_test_hold_preserved=True,
        bounded_phase_roots=[str(p) for p in roots], phase_source_and_tools=[artifact(p) for p in SOURCE_AND_TOOLS],
        modified_sdk_recipe_manifest_files=tracking['after'], retained_unique_files=unique,
        hardlink_aliases_deduplicated=sum(len(row['aliases']) for row in unique),
        retired_intermediates=retired, retired_file_count=len(retired),
        retired_logical_bytes=sum(row['bytes'] for row in retired), extra_retirement_receipts=extra,
        retired_build_roots_absent=retired_roots, remaining_intermediates=intermediates,
        phase_storage=dict(scope='This eighteen-site phase only; file-ID-deduplicated logical bytes, not physical allocation or a whole-project estimate.',
            new_unique_files_excluding_this_receipt=len(unique), new_logical_bytes_excluding_this_receipt=retained_bytes,
            modified_sdk_recipe_manifest_logical_bytes_delta=sdk_delta,
            modified_index_document_logical_bytes_delta=index_doc_delta,
            retired_bytes_subtracted_again=False,
            retirement_note='Retired intermediates were created in this phase and are absent from retained files. Subtracting them again would understate final growth.',
            receipt_bytes=0, phase_net_logical_growth=0),
        audit_deleted_files=False, native_code_executed_by_audit=False, game_or_host_or_gamecore_or_hwnd_executed=False,
        retail_install_MODS_saves_settings_or_processes_accessed=False, current_host_rebuilt=False,
        full_player_framed=False, complete_save_validated=False, ruleset_compatibility_verified=False,
        sdk_restore_verified=False, full_engine_goal_complete=False)
    # Include the newly created receipt's bytes without a circular self-hash.
    for _ in range(8):
        raw = encoded(report)
        if len(raw) == report['phase_storage']['receipt_bytes']:
            break
        report['phase_storage']['receipt_bytes'] = len(raw)
        report['phase_storage']['phase_net_logical_growth'] = retained_bytes+sdk_delta+index_doc_delta+len(raw)
    raw = encoded(report)
    require(len(raw) == report['phase_storage']['receipt_bytes'], 'Audit receipt size did not converge')
    with OUTPUT.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    print(json.dumps(dict(status=report['status'], receipt=artifact(OUTPUT),
        frozen_runtime_inputs_unchanged=len(runtime), shared_terrain_inputs_unchanged=len(terrain),
        retained_unique_files=len(unique), retired_logical_bytes=report['retired_logical_bytes'],
        remaining_intermediates=len(intermediates), phase_storage=report['phase_storage'])))
    if intermediates:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
