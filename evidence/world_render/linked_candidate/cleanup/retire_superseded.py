"""Plan exact B6/R6 retirement; reuse the sealed same-handle unlink engine.

No historical cleanup plan is read or replayed. Planning requires an explicitly
reviewed preparation digest. Apply requires the new plan digest and is single
use, including after failure. The post action checks retained current inputs.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import ctypes
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys

sys.dont_write_bytecode = True
PROJECT = Path(__file__).absolute().parents[4]
STAGE = PROJECT / 'evidence/world_render/linked_candidate'
CLEANUP = STAGE / 'cleanup'
SELF = Path(__file__).absolute()
BASE = PROJECT / 'evidence/save_overwrite/linked_candidate/cleanup/retire_superseded.py'
BASE_SHA = 'e91d7d8667f53cbd800d559093ce1a45f9ed9efd7964b65b66082663b8af9ce9'
SCOPE_SHA = 'c63aaa0a5d6dac258c430d719418db0948e8f1b36b73e0fd947ea5834d738f22'
B6, R6 = '20261016T110835Z_800f48fd88c0', '20261016T111333Z_1c377d9577e6'
B7, R7 = '20261016T122615Z_1af4a5449cf1', '20261016T123256Z_fae85fb9fe79'
B8, R8 = '20261016T142908Z_fc2e23c1fd1e', '20261016T143731Z_bc358fc8d62a'
B3, R3 = '20261014T110906Z_a60e98e7bde6', '20261014T114953Z_5248d2dd93bc'
BUILD_SHA = 'f1353330edad0c93ed6e8ee42af996f87b052b6920404df3b8411b5ec4895d63'
PE_SHA = '978ecb48269d4bcf3959895285f06f2ee75a3ab8d1bdb6b00d819d124b554452'
FINALIZER_SHA = '06e25f7750cecb4d2d401a36541e575d3a58dd0723f47a43bb47572156fceb3a'
IDENTITY_SHA = '886ccc6a60b3c03b0e1777e7e2738f42a1f337ee42a7afe057c35d6cafcf7a23'
PREPARED_SHA = '94de2deb8830f8e60480b3753761a1b09dba920d99565272ee030cf0edf03eda'
COMPLETION_SHA = '16754537417f4aa6ba0654bffa4dedd233bbc23d8d911c01b16cce52434096cf'
COMPLETER_SHA = '26ecbccd62532bf8689c2359111cbf27c6ffbdfcdace6d20c6de5d82d1ed4be8'
COMPLETION_START_SHA = '84090497505dbaf287d13d9f485fbcd791de224c39bb50d13f40870b11568ff4'
OLD_HOST_SHA = 'b436c8f26a23132bcf01928e3dc269992f2f91a1edd3ed5317542e39a7133586'
OLD_ROOTS = (PROJECT / f'Build/UiWindowHost/{B6}', PROJECT / f'Build/InteractiveGameRuntime/{R6}',
             PROJECT / f'evidence/ui_window_host/{B6}', PROJECT / f'evidence/interactive_game/{R6}')
PLAN, RESULT = CLEANUP / 'plan.json.gz', CLEANUP / 'result.json'
JOURNAL, REVIEW = CLEANUP / 'removed.jsonl', CLEANUP / 'retirement_review.json'
POST = STAGE / 'post_retirement_preflight.json'
SCHEMA = 'zerosis.world_camera_civilian.exact_superseded_cleanup.v1'
SHA = re.compile(r'[0-9a-f]{64}')
ROLES = (('host_main', 'HostMain'), ('window', 'BitmapWindow'), ('renderer', 'BitmapRenderer'),
         ('world_renderer', 'WorldViewRenderer'), ('terrain_renderer', 'WorldTerrainRenderer'))
CODE_SUFFIXES = {'.py', '.lua', '.h', '.hpp', '.hh', '.cpp', '.c', '.cs', '.xml', '.sql', '.ps1'}
SAVE_SUFFIXES = {'.zssave', '.civ5save', '.save', '.bak'}
USER_NAMES = {'sessions', 'saves', 'save', 'userdata'}


def require(value, message):
    if not value:
        raise RuntimeError(message)


def key(path):
    return os.path.normcase(os.path.abspath(path))


def artifact(path):
    path = Path(path)
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': digest}


def read(path):
    require(Path(path).stat().st_size < 16 * 1024 * 1024, 'Oversized owned JSON receipt')
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def safe_name(path):
    path = Path(path)
    return path.suffix.casefold() not in SAVE_SUFFIXES and not any(x.casefold() in USER_NAMES for x in path.parts)


def install_guard():
    retail = key(r"C:\Users\home\OneDrive\Documents\My Games\Sid Meier's Civilization 5")
    def audit(event, arguments):
        if event in ('open', 'os.listdir', 'os.scandir') and arguments and isinstance(arguments[0], (str, bytes, os.PathLike)):
            target = key(os.fsdecode(arguments[0]))
            if target.startswith('\\\\?\\'):
                target = target[4:]
            require(target != retail and not target.startswith(retail + os.sep), 'Retail user paths are forbidden')
        require(event not in ('subprocess.Popen', 'os.system', 'os.startfile', 'os.startfile/2',
                             'os.exec', 'os.posix_spawn', 'os.spawn'), 'Process execution is forbidden')
        if event == 'ctypes.dlopen':
            name = str(arguments[0]).casefold()
            require(name in ('kernel32', 'kernel32.dll'), 'Only the file-metadata kernel32 API is permitted')
    sys.addaudithook(audit)


def load_base():
    require(artifact(BASE)['sha256'] == BASE_SHA, 'Sealed same-handle cleanup engine changed')
    spec = importlib.util.spec_from_file_location('_world_render_same_handle_retirement', BASE)
    require(spec is not None and spec.loader is not None, 'Cannot load the exact cleanup engine')
    base = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(base)
    base.PROJECT, base.STAGE, base.CLEANUP = PROJECT, STAGE, CLEANUP
    base.PLAN, base.RESULT, base.JOURNAL, base.REVIEW = PLAN, RESULT, JOURNAL, REVIEW
    base.OLD_ROOTS = OLD_ROOTS
    # Legacy preflight labels B6/R6 mean retained prior, B7/R7 mean current.
    base.B5, base.R4, base.B6, base.R6, base.B7, base.R7 = B6, R6, B7, R7, B8, R8
    base.OLD_HOST_SHA = OLD_HOST_SHA
    require(base.DISPOSITION_CLASS == 21 and base.DISPOSITION_FLAGS == 0x17, 'Unexpected unlink policy')
    return base


def exact_objects():
    return {key(PROJECT / f'Build/UiWindowHost/{B8}/{phase}/tu_{index:02d}_{role}/obj/{name}.obj')
            for index, (role, name) in enumerate(ROLES) for phase in ('dependency_discovery', 'final')}


def proof_gate(base, runtime_id, preparation_sha):
    require(runtime_id == R8 and preparation_sha == IDENTITY_SHA, 'An exact reviewed R8 preparation digest is required')
    paths = {'scope': STAGE / 'scope.json', 'build': PROJECT / f'evidence/ui_window_host/{B8}/build_result.json',
             'pe': STAGE / f'attestation_{B8}.json', 'prepared': STAGE / 'prepared.json',
             'identity': STAGE / 'preparation_identity_audit.json', 'finalizer': STAGE / 'finalize_candidate.py',
             'completion': STAGE / 'preparation_completion.json', 'completer': STAGE / 'complete_preparation.py',
             'completion_start': STAGE / 'completion_start.json'}
    refs = {name: artifact(base.boundary(path)) for name, path in paths.items()}
    require(refs['scope']['sha256'] == SCOPE_SHA and refs['build']['sha256'] == BUILD_SHA and
            refs['pe']['sha256'] == PE_SHA and refs['identity']['sha256'] == preparation_sha and
            refs['prepared']['sha256'] == PREPARED_SHA and refs['completion']['sha256'] == COMPLETION_SHA and
            refs['completer']['sha256'] == COMPLETER_SHA and refs['completion_start']['sha256'] == COMPLETION_START_SHA and
            refs['finalizer']['sha256'] == FINALIZER_SHA, 'Reviewed current candidate proof changed')
    scope, build, pe, prepared, identity = (read(paths[name]) for name in ('scope', 'build', 'pe', 'prepared', 'identity'))
    require(scope['retail_mod_test_hold_active'] is True and scope['execution_allowed'] is False and
            build['status'] == 'UI_WINDOW_HOST_CANDIDATE_BUILT' and build['build_id'] == B8 and
            pe['status'] == 'PASS' and pe['build_report']['sha256'] == BUILD_SHA and
            prepared['status'] == 'PREPARED_NOT_EXECUTED' and prepared['host_build_id'] == B8 and prepared['run_id'] == R8 and
            identity['status'] == 'PASS_PREPARED_NOT_EXECUTED' and identity['host_build_id'] == B8 and identity['run_id'] == R8,
            'Current compile/link/PE/private-preparation acceptance is incomplete')
    completion = read(paths['completion'])
    require(completion['status'] == 'PASS_STATIC_COMPLETION_OF_EXISTING_PRIVATE_PREPARATION' and
            completion['prepared'] == refs['prepared'] and completion['identity_audit'] == refs['identity'] and
            completion['checker'] == refs['completer'] and completion['pe_attestation'] == refs['pe'] and
            completion['static_completion']['started'] == refs['completion_start'] and
            completion['runner_main_calls'] == 0 and completion['materializer_calls'] == 0 and
            completion['new_runtime_created_by_completion'] is False, 'Static completion lineage differs')
    require(identity['prepared'] == refs['prepared'] and identity['host_build']['sha256'] == BUILD_SHA and
            identity['request'] == artifact(PROJECT / f'evidence/interactive_game/{R8}/request.json') and
            identity['runtime_inputs'] == 24 and len(identity['immutable_cache_links']) == 15 and
            len(identity['private_databases']) == 2 and len(identity['current_frozen_manifest_support']) == 5 and
            identity['host_gamecore_hwnd_executed'] is False and identity['retail_user_state_or_processes_accessed'] is False and
            not identity['forbidden_access_attempts'] and identity['outer_process_or_ctypes_calls'] == 0,
            'Current private identity/no-execution proof differs')
    for row in base.typed_rows([identity['provenance'], prepared['static_completion'], completion['static_completion']]):
        observed = artifact(base.boundary(row['path']))
        require(observed['sha256'] == row['sha256'] and ('bytes' not in row or observed['bytes'] == row['bytes']),
                'Preserved producer/wrapper or original failure evidence changed')
    request = read(PROJECT / f'evidence/interactive_game/{R8}/request.json')
    require(request['smoke'] is False and request['resume_from'] is None and request['ui_support_from_run'] is None and
            request['unit_assets']['package']['sha256'] == scope['current_unit_assets']['binary']['sha256'] and
            not (PROJECT / f'Build/InteractiveGameRuntime/{R8}/sessions').exists(), 'Current runtime is not the accepted private preparation')
    require(artifact(build['executable']['path'])['sha256'] == pe['executable']['sha256'], 'Current executable changed')
    return {'refs': refs, 'scope': scope, 'build': build, 'pe': pe, 'identity': identity,
            'preparation_sha256': preparation_sha, 'runtime_id': runtime_id}


def safe_inventory(base, root):
    # Detect possible user state before walking descendants or reading bodies.
    for ancestor in (root, *root.parents):
        info = ancestor.lstat()
        require(not stat.S_ISLNK(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & 0x400,
                'Reparse old namespace must be held')
        if key(ancestor) == key(PROJECT):
            break
    for parent, directories, filenames in os.walk(root, followlinks=False):
        base.boundary(parent)
        require(all(name.casefold() not in USER_NAMES for name in directories), 'Possible user directory in an old root; hold all files')
        for name in directories:
            info = (Path(parent) / name).lstat()
            require(stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode) and
                    not getattr(info, 'st_file_attributes', 0) & 0x400, 'Reparse/unknown child directory must be held')
        for name in filenames:
            require(safe_name(Path(parent) / name), 'Possible user save in an old root; hold all files')
            info = (Path(parent) / name).lstat()
            require(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode) and
                    not getattr(info, 'st_file_attributes', 0) & 0x400, 'Reparse/unknown child file must be held')
    return base.inventory(root)


def retained_reports():
    builds = (B3, B7, B8, '20261011T124501Z_5bf7bf678d40')
    runtimes = (R3, R7, R8, '20261012T121847Z_732a6d5f07ea')
    return [*(PROJECT / f'evidence/ui_window_host/{value}/build_result.json' for value in builds),
            *(PROJECT / f'evidence/interactive_game/{value}/request.json' for value in runtimes),
            PROJECT / 'Play/EarlyAccess/release.json']


def load_plan():
    require(PLAN.stat().st_size < 32 * 1024 * 1024, 'Oversized compressed plan')
    with gzip.open(PLAN, 'rb') as stream:
        raw = stream.read(32 * 1024 * 1024 + 1)
    require(len(raw) < 32 * 1024 * 1024, 'Oversized exact plan')
    return json.loads(raw)


def plan(base, runtime_id, preparation_sha):
    require(not any(os.path.lexists(path) for path in (PLAN, RESULT, JOURNAL, REVIEW, CLEANUP / 'plan_summary.json')),
            'An existing or partial exact plan is never silently regenerated')
    gate = proof_gate(base, runtime_id, preparation_sha)
    preflight = base.donor_and_runtime_preflight()
    cache, old_inventory, directories, keeps, held, selected = {}, [], [], set(), [], []
    old_build = read(OLD_ROOTS[2] / 'build_result.json')
    old_request = read(OLD_ROOTS[3] / 'request.json')
    require(old_request['smoke'] is False and old_request['resume_from'] is None, 'Old runtime is not a disposable fresh preparation')
    old_refs = {}
    for value in (old_build, old_request):
        for ref in base.typed_rows(value):
            path = Path(ref['path'])
            if any(path.is_relative_to(root) for root in OLD_ROOTS):
                require(key(path) not in old_refs or old_refs[key(path)] == ref['sha256'], 'Conflicting old artifact receipts')
                old_refs[key(path)] = ref['sha256']
    protected_paths = {str(path) for path in retained_reports()} | {str(SELF), str(BASE)}
    protected_paths.update(row['path'] for row in gate['refs'].values())
    protected_paths.update(row['path'] for row in gate['scope']['protected_artifacts'])
    for current in [*retained_reports(), *[Path(row['path']) for row in gate['refs'].values() if Path(row['path']).suffix == '.json']]:
        for ref in base.typed_rows(read(current)):
            path = Path(ref['path'])
            if path.is_relative_to(PROJECT) and safe_name(path) and key(path) not in exact_objects() and path.is_file():
                require(not any(path.is_relative_to(root) for root in OLD_ROOTS[:2]), 'A current typed artifact still requires an old Build path')
                protected_paths.add(str(path))
    # All old evidence is kept. Its historical artifact dictionaries are not
    # recursively opened as if they were current runtime dependencies.
    for root in OLD_ROOTS:
        files, dirs = safe_inventory(base, root)
        directories.extend(dirs)
        for path in files:
            # Alias names are classified before any candidate body is hashed.
            for alias in base.aliases(path):
                other = Path(alias)
                if any(other.is_relative_to(candidate) for candidate in OLD_ROOTS):
                    require(safe_name(other), 'Possible user-data alias in an old namespace')
                else:
                    base.allowed_retained_alias(other, {Path(row['path']).name for row in old_request['runtime_inputs'] if Path(row['path']).suffix.lower() != '.db'})
            row = base.snapshot(path, cache)
            old_inventory.append(row)
            if root in OLD_ROOTS[2:]:
                keeps.add(str(path))
                protected_paths.add(str(path))
    protected_rows = {key(path): base.snapshot(path, cache) for path in sorted(protected_paths, key=key)}
    witnesses = defaultdict(list)
    for row in protected_rows.values():
        witnesses[(row['sha256'], row['bytes'])].append(row['path'])
    source_duplicates = []
    side_outputs = {key(OLD_ROOTS[0] / name) for name in ('read_build_environment.cmd', 'final/ZeroSisHost_x64.exp', 'final/ZeroSisHost_x64.lib')}
    original_hashes = {}
    for row in [*old_build['compiler_inputs'], *old_build['sources']]:
        original = row.get('original_path', row.get('original_source'))
        if original is not None:
            require(key(original) not in original_hashes or original_hashes[key(original)] == row['sha256'],
                    'Old original-source hash declarations conflict')
            original_hashes[key(original)] = row['sha256']
    for role, name in (('builder', 'build_ui_window_host.py'), ('popup_asset_preparer', 'prepare_ui_popup_assets.py'),
                       ('ui_asset_codec', 'civ5_ui_assets.py')):
        original_hashes[key(PROJECT / 'tools' / name)] = old_build['source_hashes_before'][role]
    for row in sorted(old_inventory, key=lambda value: key(value['path'])):
        path = Path(row['path'])
        if str(path) in keeps:
            continue
        if key(path) in old_refs:
            require(row['sha256'] == old_refs[key(path)], 'An old artifact was modified; hold all cleanup')
        code = path.suffix.casefold() in CODE_SUFFIXES and not path.name.casefold().endswith('.generated.h')
        matches = witnesses.get((row['sha256'], row['bytes']), [])
        if code:
            if not matches:
                keeps.add(str(path)); protected_rows[key(path)] = row
                witnesses[(row['sha256'], row['bytes'])].append(str(path))
                held.append({'path': str(path), 'reason': 'unique handwritten frozen source/tool without retained hash witness'})
                continue
        mirror = OLD_ROOTS[0] / 'frozen/project'
        known_mirror = path.is_relative_to(mirror) and original_hashes.get(key(PROJECT / path.relative_to(mirror))) == row['sha256']
        known = key(path) in old_refs or key(path) in side_outputs or known_mirror
        if not known:
            keeps.add(str(path)); protected_rows[key(path)] = row
            held.append({'path': str(path), 'reason': 'unmapped owned file retained conservatively'})
            continue
        if code:
            source_duplicates.append({'retired': str(path), 'sha256': row['sha256'], 'retained': matches[0]})
        selected.append({**row, 'reason': 'superseded_attested_B6_R6_artifact_with_source_witness_when_required'})
    # A changed private DB or launcher never becomes a candidate merely because
    # an older request calls it disposable.
    for row in old_request['runtime_inputs']:
        path = Path(row['path'])
        if path.suffix.casefold() == '.db':
            snap = next(item for item in old_inventory if key(item['path']) == key(path))
            require(snap['sha256'] == row['sha256'] and snap['links'] == 1, 'Old private database changed or is aliased')
    old_cache = PROJECT / f'Build/RuntimeInputCache/{OLD_HOST_SHA[:2]}/{OLD_HOST_SHA}'
    entries = [row for row in old_request['materializations'] if row.get('sha256') == OLD_HOST_SHA]
    require(len(entries) == 1 and key(entries[0]['cache']) == key(old_cache) and
            key(entries[0]['target']) == key(OLD_ROOTS[1] / 'ZeroSisHost_x64.exe') and
            entries[0]['materialization_method'] == 'hardlink', 'Old Host cache ownership is ambiguous')
    names = base.aliases(old_cache)
    hits = [str(path) for path in retained_reports() if OLD_HOST_SHA in path.read_text(encoding='utf-8-sig')]
    cache_scope = {'path': str(old_cache), 'sha256': OLD_HOST_SHA, 'included': False,
                   'exact_link_names': names, 'current_report_hash_reference_hits': hits}
    if not hits and {key(name) for name in names} == {key(old_cache), key(entries[0]['target'])}:
        row = base.snapshot(old_cache, cache)
        require(row['sha256'] == OLD_HOST_SHA and row['links'] == 2 and row['attributes'] & 1, 'Old Host-only cache changed')
        selected.append({**row, 'reason': 'old_Host_cache_with_only_old_R6_link_and_no_current_reference'})
        cache_scope['included'] = True
    discovery = {key(row['path']): row for tu in gate['build']['dependency_discovery']['translation_units'] for row in tu['objects']}
    final_objects = gate['pe']['cpp_compilation']['final_amd64_objects']
    for index, (role, stem) in enumerate(ROLES):
        for phase in ('dependency_discovery', 'final'):
            path = PROJECT / f'Build/UiWindowHost/{B8}/{phase}/tu_{index:02d}_{role}/obj/{stem}.obj'
            ref = discovery[key(path)] if phase == 'dependency_discovery' else final_objects[role]
            row = base.snapshot(path, cache)
            require(key(ref['path']) == key(path) and row['sha256'] == ref['sha256'], 'Completed current object differs from actual compile/PE proof')
            selected.append({**row, 'reason': 'B8_completed_' + phase + '_object'})
    selected_keys = {key(row['path']) for row in selected}
    require(len(selected_keys) == len(selected) and exact_objects() <= selected_keys and
            not selected_keys.intersection(protected_rows), 'Duplicate or protected candidate path')
    immutable_names = {Path(row['path']).name for row in old_request['runtime_inputs'] if Path(row['path']).suffix.lower() != '.db'}
    groups = defaultdict(list)
    for row in selected:
        groups[tuple(row['file_id'])].append(row)
    group_rows = []
    for identity, targets in sorted(groups.items(), key=lambda pair: key(pair[1][0]['path'])):
        first = targets[0]; names = base.aliases(first['path'])
        require(len(names) == first['links'] and {key(row['path']) for row in targets} <= {key(name) for name in names}, 'Hardlink namespace changed')
        retained = [name for name in names if key(name) not in selected_keys]
        for name in retained:
            base.allowed_retained_alias(name, immutable_names)
            row = base.snapshot(name, cache)
            require(row['file_id'] == first['file_id'] and row['sha256'] == first['sha256'], 'Retained alias differs from the owned input')
            protected_rows[key(name)] = row
        group_rows.append({'file_id': list(identity), 'initial_links': first['links'], 'initial_link_names': names,
            'target_names': [row['path'] for row in targets], 'retained_names': retained,
            'all_named_links_retired': not retained, 'logical_content_bytes': first['bytes'],
            'standard_allocation_reclaim_bytes': first['standard_allocation_bytes'] if not retained else 0,
            'get_compressed_reclaim_bytes': first['get_compressed_file_size_bytes'] if not retained else 0})
    protected = list(protected_rows.values())
    for row in [*protected, *selected]:
        base.same_snapshot(base.snapshot(row['path'], cache), base.row_snapshot(row))
    require(all(artifact(row['path']) == row for row in gate['refs'].values()), 'Current proof changed during exact planning')
    totals = {'files': len(selected), 'old_B6_R6_files': sum(Path(row['path']).is_relative_to(root) for row in selected for root in OLD_ROOTS),
              'B8_objects': len(exact_objects()), 'old_Host_only_cache_files': int(cache_scope['included']),
              'logical_path_bytes': sum(row['bytes'] for row in selected), 'unique_target_file_ids': len(groups),
              'expected_unique_standard_allocation_reclaim_bytes': sum(row['standard_allocation_reclaim_bytes'] for row in group_rows),
              'expected_unique_GetCompressedFileSizeW_reclaim_bytes': sum(row['get_compressed_reclaim_bytes'] for row in group_rows),
              'protected_paths': len(protected), 'retained_old_files': len(keeps)}
    review = {'status': 'EXACT_CANDIDATES_REVIEWED_NOT_APPLIED', 'utc': datetime.now(timezone.utc).isoformat(),
        'current_build_id': B8, 'current_runtime_id': R8, 'prior_build_id': B7, 'prior_runtime_id': R7,
        'proofs': gate['refs'], 'current_dependency_preflight': preflight, 'held_files': held,
        'handwritten_source_hash_witnesses': source_duplicates, 'old_host_only_cache': cache_scope, 'totals': totals,
        'historical_receipts': 'All old evidence/report/request files remain. Deleted object/source-copy paths in immutable historical receipts are historical, not replayable live closures.',
        'limits': ['Allocation counts file identities once only when all enumerated links are retired; this is not measured free volume space.',
                   'No native execution or original game/mod/save acceptance is added. A partial apply is never replayed.']}
    base.write_new(REVIEW, review)
    payload = {'schema': SCHEMA, 'current_build_id': B8, 'current_runtime_id': R8,
        'helper': artifact(SELF), 'low_level_helper': artifact(BASE), 'review': artifact(REVIEW), 'proofs': gate['refs'],
        'preparation_sha256': preparation_sha, 'files': selected, 'protected': protected, 'hardlink_groups': group_rows,
        'old_roots': [str(path) for path in OLD_ROOTS], 'old_root_inventory': old_inventory, 'old_directories': directories,
        'keep_old_paths': sorted(keeps, key=key), 'old_host_only_cache': cache_scope, 'totals': totals,
        'allowed_disposition_class': 21, 'allowed_disposition_flags': 0x17,
        'historical_reports_unchanged': True, 'no_process_queries_or_retail_access': True}
    with PLAN.open('xb') as stream:
        stream.write(gzip.compress((json.dumps(payload, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8'), mtime=0))
        stream.flush(); os.fsync(stream.fileno())
    summary = {'status': 'PLANNED_NOT_APPLIED', 'plan': artifact(PLAN), 'review': artifact(REVIEW), 'totals': totals}
    base.write_new(CLEANUP / 'plan_summary.json', summary)
    print(json.dumps(summary))


def validate(base, payload):
    require(payload['schema'] == SCHEMA and payload['current_build_id'] == B8 and payload['current_runtime_id'] == R8 and
            payload['allowed_disposition_class'] == 21 and payload['allowed_disposition_flags'] == 0x17,
            'Unsupported new exact cleanup plan')
    require(artifact(SELF) == payload['helper'] and artifact(BASE) == payload['low_level_helper'] and
            artifact(REVIEW) == payload['review'], 'Reviewed helper/engine/plan review changed')
    require(payload['old_roots'] == [str(path) for path in OLD_ROOTS], 'Old namespace scope changed')
    gate = proof_gate(base, R8, payload['preparation_sha256'])
    require(gate['refs'] == payload['proofs'], 'Reviewed candidate proof binding changed')
    keeps = {key(path) for path in payload['keep_old_paths']}
    files = payload['files']; selected = {key(row['path']) for row in files}
    require(len(files) == payload['totals']['files'] == len(selected) and exact_objects() <= selected and
            not selected.intersection(keeps), 'Invalid exact candidate set')
    old_cache = key(PROJECT / f'Build/RuntimeInputCache/{OLD_HOST_SHA[:2]}/{OLD_HOST_SHA}')
    for row in files:
        path = Path(row['path'])
        allowed = any(path.is_relative_to(root) for root in OLD_ROOTS[:2]) or key(path) in exact_objects() or (
            key(path) == old_cache and payload['old_host_only_cache']['included'] and row['sha256'] == OLD_HOST_SHA)
        require(allowed and safe_name(path) and SHA.fullmatch(row['sha256']) and row['links'] >= 1, 'Unknown/protected candidate path')
    protected = {key(row['path']): row for row in payload['protected']}
    require(not selected.intersection(protected) and keeps <= set(protected), 'Protected old/current path selected')
    group_names = []
    for group in payload['hardlink_groups']:
        targets, retained, initial = map(lambda values: {key(path) for path in values},
                                        (group['target_names'], group['retained_names'], group['initial_link_names']))
        require(len(initial) == group['initial_links'] and initial == targets | retained and not targets & retained and
                targets <= selected and retained <= set(protected) and group['all_named_links_retired'] == (not retained),
                'Invalid exact hardlink alias accounting')
        group_names.extend(targets)
    require(len(group_names) == len(selected) and set(group_names) == selected, 'Missing/duplicate hardlink group target')
    base.KEEP = tuple(Path(path) for path in payload['keep_old_paths'])


def post(base, payload):
    validate(base, payload)
    result = read(RESULT)
    require(result['status'] == 'COMPLETE' and result['plan'] == artifact(PLAN) and result['protected_unchanged'] is True,
            'Only a completed exact apply can receive a post-retirement PASS')
    require(not os.path.lexists(POST), 'Existing post-retirement evidence is immutable')
    removed = Counter()
    for row in payload['files']:
        require(not os.path.lexists(row['path']), 'A removed target reappeared')
        removed[tuple(row['file_id'])] += 1
    for row in payload['protected']:
        base.same_snapshot(base.snapshot(row['path']), row, removed[tuple(row['file_id'])])
    proof = base.donor_and_runtime_preflight()
    require(proof['status'] == 'PASS' and set(proof['current']) == {B7, B8} and
            proof['blocked_old_path_attempts'] == [] and proof['target_directory_created'] is False, 'Retained current preflight failed')
    proof.update(schema='zerosis.world_camera_civilian.post_retirement_preflight.v1', utc=datetime.now(timezone.utc).isoformat(),
                 helper=artifact(SELF), plan=artifact(PLAN), result=artifact(RESULT), proofs=payload['proofs'],
                 current_build_id=B8, current_runtime_id=R8, prior_build_id=B7, prior_runtime_id=R7,
                 host_gamecore_hwnd_executed=False, retail_user_state_or_processes_accessed=False)
    base.write_new(POST, proof)
    print(json.dumps({'status': proof['status'], 'post_retirement_preflight': artifact(POST)}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('plan', 'apply', 'post'))
    parser.add_argument('--helper-sha256', required=True)
    parser.add_argument('--runtime-id')
    parser.add_argument('--preparation-sha256')
    parser.add_argument('--plan-sha256')
    args = parser.parse_args()
    require(SHA.fullmatch(args.helper_sha256) and artifact(SELF)['sha256'] == args.helper_sha256, 'Reviewed new helper digest is required')
    install_guard()
    base = load_base()
    if args.action == 'plan':
        plan(base, args.runtime_id, args.preparation_sha256)
    else:
        require(SHA.fullmatch(str(args.plan_sha256)) and artifact(PLAN)['sha256'] == args.plan_sha256, 'Reviewed new plan digest is required')
        payload = load_plan(); validate(base, payload)
        if args.action == 'apply':
            base.donor_and_runtime_preflight()
            for root in OLD_ROOTS:
                safe_inventory(base, root)
            base.validate_plan_shape = lambda current: validate(base, current)
            base.apply(args.plan_sha256)
        else:
            post(base, payload)


if __name__ == '__main__':
    main()
