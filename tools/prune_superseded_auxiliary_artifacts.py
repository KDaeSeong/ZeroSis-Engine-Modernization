"""Preview/apply narrowly scoped retirement of superseded auxiliary artifacts.

This is separate from prune_superseded_runtime_artifacts.py. It only handles
historical validation copies and generated review bundles whose sources remain.
Default invocation creates a review plan and compact file ledger; deletion only
occurs when an explicit --apply plan path is supplied after review.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import stat
import uuid

ROOT = Path(__file__).resolve().parents[1]
BASE_PROTECTED = ROOT / 'evidence/storage_cleanup/20261005T082918Z_ca2240df4d1f/protected.json.gz'
FVS_RUN = re.compile(r'\d{8}T\d{6}Z_[0-9a-f]{10}')
UUID_DIR = re.compile(r'[0-9a-f]{32}')
PREP_DIR = re.compile(r'\d{8}T\d{6}Z_[A-Za-z0-9_.-]+')
FVS_PASS = 'FOUND_VALUE_SCORES_ORIGINAL_BODY_DIFFERENTIAL_PASS'


def load_primary_helpers():
    path = ROOT / 'tools/prune_superseded_runtime_artifacts.py'
    spec = importlib.util.spec_from_file_location('zeros_is_primary_pruner', path)
    if spec is None or spec.loader is None:
        raise RuntimeError('Cannot load primary pruning safety helpers')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PRIMARY = load_primary_helpers()


def require(value: bool, message: str) -> None:
    if not value:
        raise RuntimeError(message)


def normalized(path: Path) -> str:
    return os.path.normcase(str(path.resolve(strict=True))).rstrip('\\/')


def intersects(path: Path, other: Path) -> bool:
    a, b = normalized(path), normalized(other)
    sep = os.sep
    return a == b or a.startswith(b + sep) or b.startswith(a + sep)


def protected_map() -> tuple[dict[str, str], str]:
    PRIMARY.boundary(BASE_PROTECTED)
    base_sha = PRIMARY.digest(BASE_PROTECTED)
    with gzip.open(BASE_PROTECTED, 'rt', encoding='utf8') as stream:
        data = json.load(stream)
    require(isinstance(data, dict) and len(data) >= 1000, 'Stable protected map is missing or unexpectedly small')
    result: dict[str, str] = {}
    for name, expected in data.items():
        path = Path(name)
        require(path.is_absolute() and isinstance(expected, str) and re.fullmatch(r'[0-9a-f]{64}', expected),
                'Malformed protected-map entry: ' + str(name))
        result[normalized(path)] = expected
    return result, base_sha


def is_protected(path: Path, protected: dict[str, str]) -> bool:
    key = normalized(path)
    sep = os.sep
    return any(key == p or key.startswith(p + sep) or p.startswith(key + sep) for p in protected)


def regular_files(directory: Path):
    directory = PRIMARY.boundary(directory)
    for current, dirs, files in os.walk(directory, topdown=True, followlinks=False):
        current_path = PRIMARY.boundary(Path(current))
        for name in list(dirs):
            child = PRIMARY.boundary(current_path / name)
            info = child.lstat()
            require(stat.S_ISDIR(info.st_mode), 'Unexpected non-directory in target tree: ' + str(child))
        for name in files:
            yield PRIMARY.boundary(current_path / name), PRIMARY.regular(current_path / name)


def stage_bundle_sources() -> dict:
    stage = PRIMARY.boundary(ROOT / 'Stage/BootstrapAudit')
    manifest_path = PRIMARY.boundary(stage / 'review_bundle.json')
    manifest = json.loads(manifest_path.read_text(encoding='utf8'))
    require(manifest.get('status') == 'STATIC_BOOTSTRAP_AUDIT_REVIEW_READY_RUNTIME_GATE_OPEN',
            'Bootstrap review bundle has an unexpected status')
    rows = manifest.get('files')
    require(isinstance(rows, list) and rows, 'Bootstrap review bundle has no file mapping')
    seen_targets = set()
    for row in rows:
        source = PRIMARY.boundary(Path(row['source']))
        target = PRIMARY.boundary(Path(row['path']))
        require(source.is_file() and target.is_file(), 'Bootstrap review source/target is missing')
        require(source != target and target.is_relative_to(stage), 'Bootstrap mapping escapes its review bundle')
        require(target.relative_to(stage) == source.relative_to(ROOT), 'Bootstrap copy path does not mirror source path')
        require(target not in seen_targets, 'Duplicate bootstrap review target')
        seen_targets.add(target)
        require(source.stat().st_size == target.stat().st_size, 'Bootstrap source/target sizes differ')
    return {'manifest': str(manifest_path), 'files': len(rows), 'sources_exist': True,
            'mirrored_paths': True, 'source_sizes_match': True}


def collect_candidates(protected: dict[str, str]) -> tuple[list[Path], dict]:
    candidates: list[Path] = []
    fvs = {'latest_passing_run': None, 'passing_runs': [], 'retained': None}

    host_validation = PRIMARY.boundary(ROOT / 'Build/Host/validation')
    for child in sorted(host_validation.iterdir()):
        if child.is_dir() and UUID_DIR.fullmatch(child.name):
            candidate = PRIMARY.boundary(child)
            require(not is_protected(candidate, protected), 'Protected host validation directory: ' + str(candidate))
            candidates.append(candidate)

    database_corpus = PRIMARY.boundary(ROOT / 'Build/Database/corpus')
    for child in sorted(database_corpus.iterdir()):
        if child.is_dir() and UUID_DIR.fullmatch(child.name):
            candidate = PRIMARY.boundary(child)
            if not is_protected(candidate, protected):
                candidates.append(candidate)

    build_fvs = PRIMARY.boundary(ROOT / 'Build/FoundValueScores')
    evidence_fvs = PRIMARY.boundary(ROOT / 'evidence/found_value_scores')
    evidence_runs = {}
    passing = []
    for child in evidence_fvs.iterdir():
        if not child.is_dir() or not FVS_RUN.fullmatch(child.name):
            continue
        evidence_runs[child.name] = child
        report = child / 'conformance.json'
        if report.is_file():
            result = json.loads(report.read_text(encoding='utf8'))
            if result.get('status') == FVS_PASS:
                passing.append(child.name)
    require(passing, 'No passing FoundValueScores baseline could be retained')
    latest = max(passing)
    fvs.update({'latest_passing_run': latest, 'passing_runs': sorted(passing), 'retained': latest})
    build_runs = {child.name: child for child in build_fvs.iterdir()
                  if child.is_dir() and FVS_RUN.fullmatch(child.name)}
    require(latest in build_runs and latest in evidence_runs, 'Latest passing score baseline lacks its build/evidence pair')
    for run_id in sorted(set(build_runs) | set(evidence_runs)):
        if run_id == latest:
            continue
        pair = [build_runs.get(run_id), evidence_runs.get(run_id)]
        require(all(path is not None for path in pair), 'Unpaired FoundValueScores run requires manual review: ' + run_id)
        for path in pair:
            candidate = PRIMARY.boundary(path)
            require(not is_protected(candidate, protected), 'Protected FoundValueScores directory: ' + str(candidate))
            candidates.append(candidate)

    prep = PRIMARY.boundary(ROOT / 'evidence/interactive_ui_preparation')
    for child in sorted(prep.iterdir()):
        if child.is_dir() and PREP_DIR.fullmatch(child.name):
            candidate = PRIMARY.boundary(child)
            if not is_protected(candidate, protected):
                candidates.append(candidate)

    bundle = stage_bundle_sources()
    stage = PRIMARY.boundary(ROOT / 'Stage/BootstrapAudit')
    require(not is_protected(stage, protected), 'Bootstrap review bundle intersects current protected references')
    candidates.append(stage)

    unique = list(dict.fromkeys(candidates))
    require(unique and len(unique) == len(candidates), 'Empty or duplicate auxiliary target list')
    for index, candidate in enumerate(unique):
        for other in unique[index + 1:]:
            require(not intersects(candidate, other), 'Overlapping auxiliary targets')
        require(not is_protected(candidate, protected), 'Target intersects the protected closure: ' + str(candidate))
    return unique, {'found_value_scores': fvs, 'bootstrap_bundle': bundle}


def validate_target_scope(path: Path, retained_fvs: str) -> Path:
    path = PRIMARY.boundary(path)
    parts = path.relative_to(ROOT).parts
    allowed = False
    if len(parts) == 4 and parts[:3] == ('Build', 'Host', 'validation'):
        allowed = bool(UUID_DIR.fullmatch(parts[3]))
    elif len(parts) == 4 and parts[:3] == ('Build', 'Database', 'corpus'):
        allowed = bool(UUID_DIR.fullmatch(parts[3]))
    elif len(parts) == 3 and parts[:2] == ('Build', 'FoundValueScores'):
        allowed = bool(FVS_RUN.fullmatch(parts[2])) and parts[2] != retained_fvs
    elif len(parts) == 3 and parts[:2] == ('evidence', 'found_value_scores'):
        allowed = bool(FVS_RUN.fullmatch(parts[2])) and parts[2] != retained_fvs
    elif len(parts) == 3 and parts[:2] == ('evidence', 'interactive_ui_preparation'):
        allowed = bool(PREP_DIR.fullmatch(parts[2]))
    elif parts == ('Stage', 'BootstrapAudit'):
        allowed = True
    require(allowed, 'Target escaped the approved auxiliary scope: ' + str(path))
    return path


def volume_free() -> int:
    return shutil.disk_usage(ROOT).free


def make_plan() -> None:
    PRIMARY.no_active_host()
    protected, protected_sha = protected_map()
    candidates, details = collect_candidates(protected)
    output = ROOT / 'evidence/storage_cleanup_auxiliary' / (
        datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_') + uuid.uuid4().hex[:12])
    evidence_root = PRIMARY.boundary(ROOT / 'evidence')
    aux_root = evidence_root / 'storage_cleanup_auxiliary'
    aux_root.mkdir(exist_ok=True)
    PRIMARY.boundary(aux_root)
    output.mkdir()
    free_before = volume_free()
    ledger = output / 'retired-files.jsonl.gz'
    count = logical = 0
    identities: dict[tuple[int, int], dict] = {}
    digest_cache: dict[tuple[int, int, int, int], str] = {}
    directories = []
    with gzip.open(ledger, 'wt', encoding='utf8') as stream:
        for directory in candidates:
            file_count = byte_count = 0
            for path, info in regular_files(directory):
                identity = (info.st_dev, info.st_ino)
                identity_with_state = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
                sha = digest_cache.get(identity_with_state)
                if sha is None:
                    sha = PRIMARY.digest(path)
                    digest_cache[identity_with_state] = sha
                allocated = PRIMARY.stored(path)
                inode = identities.setdefault(identity, {'links': info.st_nlink, 'planned_links': 0,
                                                          'allocated': allocated})
                inode['planned_links'] += 1
                row = {'path': str(path.relative_to(ROOT)), 'sha256': sha, 'bytes': info.st_size,
                       'mtime_ns': info.st_mtime_ns, 'device': info.st_dev, 'file_id': info.st_ino,
                       'links': info.st_nlink, 'allocated_bytes': allocated}
                stream.write(json.dumps(row, separators=(',', ':')) + '\n')
                file_count += 1
                byte_count += info.st_size
            directories.append({'path': str(directory.relative_to(ROOT)), 'files': file_count,
                                'logical_bytes': byte_count})
            count += file_count
            logical += byte_count
    free_after = volume_free()
    report = {'status': 'PREVIEW_ONLY', 'scope': 'USER_REQUESTED_RETIREMENT_OF_SUPERSEDED_AUXILIARY_ARTIFACTS',
              'root': str(ROOT), 'base_protected_map': {'path': str(BASE_PROTECTED), 'sha256': protected_sha,
                  'files': len(protected)}, 'directories': directories, 'files': count, 'logical_bytes': logical,
              'estimated_reclaimable_file_storage': sum(v['allocated'] for v in identities.values()
                  if v['links'] == v['planned_links']),
              'volume_free_before': free_before, 'volume_free_after_preview': free_after,
              'unchanged_before_delete': free_before == free_after, 'found_value_scores': details['found_value_scores'],
              'bootstrap_bundle_mapping': details['bootstrap_bundle'], 'ledger': str(ledger),
              'ledger_sha256': PRIMARY.digest(ledger), 'protected_hashes_checked': False,
              'deletion_performed': False, 'archives_created': False}
    plan_path = output / 'plan.json'
    plan_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'status': report['status'], 'plan': str(plan_path), 'directories': len(candidates),
                      'files': count, 'logical_gib': round(logical / 1024**3, 3),
                      'reclaimable_gib': round(report['estimated_reclaimable_file_storage'] / 1024**3, 3),
                      'free_before': free_before, 'free_after_preview': free_after,
                      'latest_fvs_pass': details['found_value_scores']['latest_passing_run']}, ensure_ascii=False), flush=True)


def apply_plan(plan_path: Path) -> None:
    """Apply only a separately reviewed preview; this path is not invoked here."""
    PRIMARY.no_active_host()
    plan_path = PRIMARY.boundary(plan_path)
    require(plan_path.is_relative_to(ROOT / 'evidence/storage_cleanup_auxiliary'), 'Plan outside auxiliary cleanup evidence')
    require(not (plan_path.parent / 'cleanup.json').exists(), 'This plan was already started; review its cleanup report instead of replaying it')
    report = json.loads(plan_path.read_text(encoding='utf8'))
    require(report.get('status') == 'PREVIEW_ONLY' and report.get('root') == str(ROOT), 'Wrong auxiliary plan')
    base = report['base_protected_map']
    require(Path(base['path']) == BASE_PROTECTED and PRIMARY.digest(BASE_PROTECTED) == base['sha256'],
            'Stable protected map changed or plan uses another protection base')
    with gzip.open(base['path'], 'rt', encoding='utf8') as stream:
        protected_json = json.load(stream)
    protected = {normalized(Path(name)): sha for name, sha in protected_json.items()}
    retained_fvs = report['found_value_scores']['retained']
    targets = [validate_target_scope(ROOT / row['path'], retained_fvs) for row in report['directories']]
    require(len(set(targets)) == len(targets), 'Duplicate apply targets')
    for i, target in enumerate(targets):
        require(not is_protected(target, protected), 'Apply target intersects protected closure: ' + str(target))
        require(all(not intersects(target, other) for other in targets[i + 1:]), 'Apply targets overlap')
    expected_candidates, details = collect_candidates(protected)
    require({normalized(path) for path in targets} == {normalized(path) for path in expected_candidates},
            'Current approved candidate set differs from the reviewed plan')
    require(details['found_value_scores']['retained'] == retained_fvs,
            'Latest passing FoundValueScores baseline changed')
    ledger = PRIMARY.boundary(Path(report['ledger']))
    require(ledger.parent == plan_path.parent and PRIMARY.digest(ledger) == report['ledger_sha256'],
            'Retirement ledger changed or escaped the reviewed plan directory')
    free_before = volume_free()
    verified: dict[tuple[int, int, int, int], str] = {}
    for name, expected in protected.items():
        path = Path(name)
        info = PRIMARY.regular(path)
        identity = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
        if identity not in verified:
            verified[identity] = PRIMARY.digest(path)
        require(verified[identity] == expected, 'Protected content changed before cleanup: ' + name)
    for target in targets:
        PRIMARY.boundary(target)
    # Reuse the primary implementation's native readonly-safe unlink self-test.
    test = plan_path.parent / 'readonly-hardlink-check'
    test.mkdir()
    source, alias = test / 'source', test / 'alias'
    source.write_bytes(b'preserved-readonly-hardlink')
    os.link(source, alias)
    os.chmod(source, stat.S_IREAD)
    attrs = source.stat().st_file_attributes
    PRIMARY.unlink_without_attribute_changes(alias)
    require(not alias.exists() and source.read_bytes() == b'preserved-readonly-hardlink'
            and source.stat().st_file_attributes == attrs, 'Readonly hardlink deletion self-test failed')
    PRIMARY.unlink_without_attribute_changes(source)
    test.rmdir()
    output = plan_path.parent / 'cleanup.json'
    progress = {'status': 'REMOVING', 'removed_files': 0, 'removed_logical_bytes': 0,
                'volume_free_before': free_before, 'protected_hashes_verified_before': True,
                'protected_hashes_verified_after': False, 'readonly_hardlink_selftest': True,
                'completed_directories': [], 'errors': []}
    def checkpoint():
        output.write_text(json.dumps(progress, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    checkpoint()
    try:
        PRIMARY.no_active_host()
        with gzip.open(ledger, 'rt', encoding='utf8') as stream:
            for line in stream:
                row = json.loads(line)
                path = PRIMARY.boundary(ROOT / row['path'])
                require(any(path.is_relative_to(t) for t in targets), 'Ledger path outside targets')
                info = PRIMARY.regular(path)
                require((info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns) ==
                        (row['device'], row['file_id'], row['bytes'], row['mtime_ns']), 'File identity changed: ' + str(path))
                require(PRIMARY.digest(path) == row['sha256'], 'File content changed: ' + str(path))
                PRIMARY.unlink_without_attribute_changes(path)
                require(not path.exists(), 'File remains after unlink: ' + str(path))
                progress['removed_files'] += 1
                progress['removed_logical_bytes'] += row['bytes']
                if progress['removed_files'] % 1000 == 0:
                    checkpoint()
                    print(json.dumps({'phase': 'auxiliary_delete', 'files': progress['removed_files'],
                                      'planned': report['files']}), flush=True)
        for target in targets:
            for current, dirs, files in os.walk(target, topdown=False, followlinks=False):
                require(not files, 'Unplanned file remains: ' + current)
                PRIMARY.boundary(Path(current)).rmdir()
            progress['completed_directories'].append(str(target.relative_to(ROOT)))
        verified.clear()
        for name, expected in protected.items():
            path = Path(name)
            info = PRIMARY.regular(path)
            identity = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
            if identity not in verified:
                verified[identity] = PRIMARY.digest(path)
            require(verified[identity] == expected, 'Protected content changed after cleanup: ' + name)
        require(progress['removed_files'] == report['files'], 'Removed file count differs from ledger')
        progress['protected_hashes_verified_after'] = True
        progress['volume_free_after'] = volume_free()
        progress['status'] = 'PASS_AUXILIARY_ARTIFACT_RETIREMENT'
    except Exception as error:
        progress['status'] = 'FAILED_PARTIAL_RETIREMENT_RETAINED'
        progress['errors'].append(type(error).__name__ + ': ' + str(error))
        raise
    finally:
        progress['volume_free_after'] = volume_free()
        progress['volume_free_delta'] = progress['volume_free_after'] - progress['volume_free_before']
        checkpoint()
        print(json.dumps({'status': progress['status'], 'removed_files': progress['removed_files'],
                          'removed_logical_gib': round(progress['removed_logical_bytes'] / 1024**3, 3),
                          'report': str(output), 'errors': progress['errors']}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', type=Path)
    options = parser.parse_args()
    if options.apply:
        apply_plan(options.apply)
    else:
        make_plan()
