"""Create a review-only retirement plan for four explicitly audited run pairs.

Run only after source/test changes are frozen. This script does not delete files.
The generated plan is intentionally compatible with the existing runtime
retirement tool's apply(plan.json) verifier.
"""
from __future__ import annotations

from collections import defaultdict
import gzip
import importlib.util
import json
import os
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[3]
CONTRACT_PATH = ROOT / 'tools' / 'prune_superseded_runtime_artifacts.py'
PREVIOUS = ROOT / 'evidence' / 'storage_cleanup' / '20261007T124510Z_e6f679eb7803'
RUNS = {
    '20261007T133851Z_7dc8fa04bd24': ('UiWindowHost', 'ui_window_host'),
    '20261007T134209Z_1778edc8e063': ('UiWindowHost', 'ui_window_host'),
    '20261007T134617Z_b6d81d8dd219': ('InteractiveGameRuntime', 'interactive_game'),
    '20261007T135756Z_c423017d7791': ('InteractiveGameRuntime', 'interactive_game'),
}
PROTECTED_HOSTS = ('20261007T135521Z_f2dab4d1d447', '20261007T190026Z_e8927b74abf4')
LATEST_HOST = '20261007T190026Z_e8927b74abf4'
ACTIVE_RUNTIME = '20261007T190226Z_a6a8966d1678'
BASELINE_HOST = '20261006T132536Z_f8bcf55e3ffa'
BASELINE_RUNTIMES = ('20261006T132933Z_c6976cdbae5b', '20261006T133311Z_b83e6f290c55')
COMBAT_RUNTIME = '20261006T134330Z_9d66f439b55e'
MANUAL_RUNTIMES = (
    '20261006T133923Z_6730b22058d0',
    '20261004T000710Z_796f1ea91c5e',
    '20261003T230735Z_2003f24507ce',
    '20261003T154510Z_b1af9e8eb764',
)
RUN_RE = re.compile(r'\d{8}T\d{6}Z_[0-9a-f]{12}')
TEXT_SUFFIXES = {'.json', '.md', '.py', '.ps1', '.txt', '.log', '.xml', '.lua', '.cmd'}
MAX_REFERENCE_SCAN_BYTES = 32 * 1024 * 1024


def require(ok: bool, message: str) -> None:
    if not ok:
        raise RuntimeError(message)


def load_contract():
    spec = importlib.util.spec_from_file_location('runtime_retirement_contract', CONTRACT_PATH)
    require(spec is not None and spec.loader is not None, 'Cannot load existing cleanup contract')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    require(module.ROOT == ROOT, 'Existing cleanup contract resolved a different project root')
    return module


def inside(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def is_candidate(path: Path, targets: list[Path]) -> bool:
    return any(inside(path, target) for target in targets)


def tree_files(contract, directory: Path):
    directory = contract.boundary(directory)
    require(directory.is_dir(), 'Missing protected tree: ' + str(directory))
    yield from contract.inventory(directory)


def add_tree(contract, protected: set[Path], directory: Path) -> None:
    for path, _ in tree_files(contract, directory):
        protected.add(path)


def add_json_closure(contract, protected: set[Path], seeds: list[Path], documents: set[Path]) -> None:
    pending = list(seeds)
    visited: set[Path] = set()
    while pending:
        path = contract.boundary(pending.pop())
        require(path.is_file(), 'Missing dependency-closure seed: ' + str(path))
        if path in visited:
            continue
        visited.add(path)
        protected.add(path)
        if path.suffix.lower() != '.json':
            continue
        documents.add(path)
        try:
            node = json.loads(path.read_text(encoding='utf-8-sig'))
        except Exception as exc:
            raise RuntimeError(f'Cannot parse dependency JSON {path}: {exc}') from exc
        for name, _expected_sha in contract.refs(node):
            target = Path(name)
            if not target.is_absolute() or not inside(target, ROOT) or not target.is_file():
                continue
            target = contract.boundary(target)
            protected.add(target)
            if target.suffix.lower() == '.json' and target not in visited:
                pending.append(target)


def report_record(contract, run_id: str, category: str, evidence_root: Path) -> dict:
    reports = []
    for filename in ('build_result.json', 'result.json', 'failure_summary.json'):
        path = evidence_root / filename
        if not path.is_file():
            continue
        path = contract.boundary(path)
        raw = json.loads(path.read_text(encoding='utf-8-sig'))
        failure = raw.get('failure') or raw.get('error') or raw.get('primary_failure')
        failures = raw.get('failures')
        if not failure and isinstance(failures, list) and failures:
            failure = '; '.join(str(item) for item in failures[:4])
        if isinstance(failure, str):
            failure = failure[:700]
        reports.append({
            'report': str(path.relative_to(ROOT)),
            'status': raw.get('status'),
            'failure_summary': failure,
            'sha256': contract.digest(path),
        })
    return {'run_id': run_id, 'group': category, 'reports': reports}


def check_no_current_references(contract, protected: set[Path], targets: list[Path], output_dir: Path) -> None:
    run_ids = tuple(RUNS)
    def inspect(path: Path) -> None:
        if path.suffix.lower() not in TEXT_SUFFIXES or path.stat().st_size > MAX_REFERENCE_SCAN_BYTES:
            return
        if path == Path(__file__).resolve():
            return
        contract.regular(path)
        data = path.read_bytes()
        if not any(run_id.encode('ascii') in data for run_id in run_ids):
            return
        # UTF-16 text files contain NUL bytes between ASCII characters.
        if b'\x00' in data:
            try:
                decoded = data.decode('utf-16')
            except UnicodeError:
                decoded = ''
            hits = [run_id for run_id in run_ids if run_id in decoded]
        else:
            hits = [run_id for run_id in run_ids if run_id.encode('ascii') in data]
        if hits:
            raise RuntimeError('Candidate run is referenced outside the retirement set: '
                               + str(path) + ' -> ' + ', '.join(hits))

    scan = set(protected)
    docs = ROOT / 'docs'
    if docs.is_dir():
        for path, _ in contract.inventory(docs):
            scan.add(path)
    for path in scan:
        if inside(path, output_dir) or is_candidate(path, targets):
            continue
        inspect(path)


def create_plan() -> Path:
    contract = load_contract()
    contract.no_active_host()
    output_dir = contract.boundary(Path(__file__).resolve().parent)
    require(inside(output_dir, ROOT / 'evidence' / 'storage_cleanup'), 'Output folder is outside cleanup evidence')
    require(not (output_dir / 'plan.json').exists() and not (output_dir / 'cleanup.json').exists(),
            'Output folder already contains a plan or cleanup report')

    targets: list[Path] = []
    for run_id, (build_group, evidence_group) in RUNS.items():
        require(RUN_RE.fullmatch(run_id), 'Invalid fixed run ID')
        for relative in (Path('Build') / build_group / run_id,
                         Path('evidence') / evidence_group / run_id):
            target = contract.legal_target(ROOT / relative)
            require(target.is_dir(), 'Missing audited candidate directory: ' + str(target))
            targets.append(target)
    require(len(targets) == 8 and len(set(targets)) == 8, 'Candidate set must be exactly eight unique directories')

    # Fail closed if another host build appeared after this audit.
    host_dirs = [p.name for p in (ROOT / 'Build' / 'UiWindowHost').iterdir()
                 if p.is_dir() and RUN_RE.fullmatch(p.name)]
    require(LATEST_HOST in host_dirs and max(host_dirs) == LATEST_HOST,
            'Latest UI Host changed; refresh the retention audit before planning')

    # Load only prior path names. Prior content hashes are deliberately discarded;
    # every surviving path is hashed from its current bytes below.
    previous_path = contract.boundary(PREVIOUS / 'protected.json.gz')
    with gzip.open(previous_path, 'rt', encoding='utf-8') as stream:
        previous_protected = json.load(stream)
    protected: set[Path] = set()
    skipped_missing_prior_paths = []
    for name in previous_protected:
        path = Path(name)
        require(path.is_absolute(), 'Prior protected path is not absolute: ' + name)
        if is_candidate(path, targets):
            raise RuntimeError('Audited candidate intersects the prior protected path list: ' + name)
        if not path.exists():
            skipped_missing_prior_paths.append(name)
            continue
        info = contract.regular(path)
        protected.add(contract.boundary(path))

    preserved_trees = [ROOT / 'Source', ROOT / 'Tests', ROOT / 'tools', ROOT / 'docs']
    for host_run in PROTECTED_HOSTS:
        preserved_trees += [ROOT / 'Build' / 'UiWindowHost' / host_run,
                            ROOT / 'evidence' / 'ui_window_host' / host_run]
    preserved_trees += [ROOT / 'Build' / 'UiWindowHost' / BASELINE_HOST,
                        ROOT / 'evidence' / 'ui_window_host' / BASELINE_HOST]
    for run_id in (*BASELINE_RUNTIMES, COMBAT_RUNTIME, *MANUAL_RUNTIMES):
        preserved_trees += [ROOT / 'Build' / 'InteractiveGameRuntime' / run_id,
                            ROOT / 'evidence' / 'interactive_game' / run_id]
    preserved_trees += [ROOT / 'Build' / 'InteractiveGameRuntime' / ACTIVE_RUNTIME,
                        ROOT / 'evidence' / 'interactive_game' / ACTIVE_RUNTIME]
    for tree in preserved_trees:
        require(not is_candidate(tree, targets), 'Protected tree overlaps a candidate: ' + str(tree))
        add_tree(contract, protected, tree)

    # Seed the baseline dependency closure using the prior plan's locations but
    # never its recorded hashes, then add today's Host, restore, and combat roots.
    previous_plan = json.loads((PREVIOUS / 'plan.json').read_text(encoding='utf-8'))
    seeds = [Path(name) for name in previous_plan.get('seed_documents', [])]
    seeds += [ROOT / 'evidence' / 'ui_window_host' / LATEST_HOST / 'build_result.json',
              ROOT / 'evidence' / 'ui_window_host' / BASELINE_HOST / 'build_result.json']
    for host_run in PROTECTED_HOSTS:
        seeds.append(ROOT / 'evidence' / 'ui_window_host' / host_run / 'build_result.json')
    for run_id in (*BASELINE_RUNTIMES, COMBAT_RUNTIME, *MANUAL_RUNTIMES, ACTIVE_RUNTIME):
        evidence = ROOT / 'evidence' / 'interactive_game' / run_id
        for filename in ('request.json', 'result.json'):
            if (evidence / filename).is_file():
                seeds.append(evidence / filename)
    documents: set[Path] = set()
    add_json_closure(contract, protected, seeds, documents)

    # Resolve the exact eight save paths recorded by the preceding completed
    # preservation check; this includes root-level checkpoint-input.zssave.
    validation_path = contract.boundary(PREVIOUS / 'post_cleanup_validation.json')
    validation = json.loads(validation_path.read_text(encoding='utf-8'))
    manual_run_fragments = tuple('\\' + run_id + '\\' for run_id in MANUAL_RUNTIMES)
    manual_save_paths = [Path(item['path']) for item in validation.get('saves', [])
                         if any(fragment in item['path'] for fragment in manual_run_fragments)]
    require(validation.get('user_saves') == 8 and len(manual_save_paths) == 8,
            'Previous preservation record does not identify exactly eight manual user-save paths')
    for path in manual_save_paths:
        path = contract.boundary(path)
        require(any(inside(path, ROOT / 'Build' / 'InteractiveGameRuntime' / run_id)
                    for run_id in MANUAL_RUNTIMES), 'Recorded user save is outside a protected manual runtime: ' + str(path))
        contract.regular(path)
        protected.add(path)

    for path in protected:
        require(not is_candidate(path, targets), 'Protected path intersects a candidate directory: ' + str(path))
    check_no_current_references(contract, protected, targets, output_dir)

    # Hash current protected bytes and candidate bytes with identity caching.
    hash_cache: dict[tuple[int, int, int, int], str] = {}
    protected_hashes = {}
    for path in sorted(protected, key=lambda item: str(item).casefold()):
        path = contract.boundary(path)
        info = contract.regular(path)
        identity = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
        if identity not in hash_cache:
            hash_cache[identity] = contract.digest(path)
        protected_hashes[str(path)] = hash_cache[identity]
    for path in protected_hashes:
        require(not is_candidate(Path(path), targets), 'Protected file in candidate set: ' + path)

    protected_file = output_dir / 'protected.json.gz'
    with gzip.open(protected_file, 'wt', encoding='utf-8') as stream:
        json.dump(protected_hashes, stream, separators=(',', ':'))

    status_records = []
    for run_id, (_build_group, evidence_group) in RUNS.items():
        status_records.append(report_record(contract, run_id, evidence_group,
                                            ROOT / 'evidence' / evidence_group / run_id))
    status_file = output_dir / 'status-summary.json'
    status_file.write_text(json.dumps({'status': 'READ_ONLY_CANDIDATE_STATUS',
                                      'candidate_runs': status_records}, ensure_ascii=False, separators=(',', ':')) + '\n',
                           encoding='utf-8')

    ledger_file = output_dir / 'retired-files.jsonl.gz'
    directory_summaries = []
    total_files = logical_bytes = 0
    allocation_by_identity = defaultdict(lambda: {'links': 0, 'candidate_paths': 0, 'stored': 0})
    with gzip.open(ledger_file, 'wt', encoding='utf-8') as ledger:
        for target in targets:
            count = size = 0
            for path, info in contract.inventory(target):
                identity = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
                if identity not in hash_cache:
                    hash_cache[identity] = contract.digest(path)
                row = {'path': str(path.relative_to(ROOT)), 'sha256': hash_cache[identity],
                       'bytes': info.st_size, 'mtime_ns': info.st_mtime_ns,
                       'device': info.st_dev, 'file_id': info.st_ino}
                ledger.write(json.dumps(row, separators=(',', ':')) + '\n')
                inode_key = (info.st_dev, info.st_ino)
                bucket = allocation_by_identity[inode_key]
                bucket['links'] = info.st_nlink
                bucket['candidate_paths'] += 1
                if not bucket['stored']:
                    bucket['stored'] = contract.stored(path)
                count += 1
                size += info.st_size
                require((path.stat().st_dev, path.stat().st_ino, path.stat().st_size,
                         path.stat().st_mtime_ns) == identity, 'Candidate changed during inventory: ' + str(path))
            directory_summaries.append({'path': str(target.relative_to(ROOT)), 'files': count,
                                        'logical_bytes': size})
            total_files += count
            logical_bytes += size

    contract.no_active_host()
    require(len(directory_summaries) == 8, 'Candidate directory count changed during inventory')
    plan = {
        'status': 'PREVIEW_ONLY',
        'scope': 'EXACT_EIGHT_AUDITED_FAILED_OR_SUPERSEDED_RUNTIME_DIRECTORIES',
        'root': str(ROOT),
        'user_instruction': 'Retire only the eight specifically audited superseded or failed Build/evidence directories.',
        'manual_runtimes': list(MANUAL_RUNTIMES),
        'latest_host_build': LATEST_HOST,
        'protected_host_builds': list(PROTECTED_HOSTS),
        'protected_active_runtime': ACTIVE_RUNTIME,
        'protected_whole_trees': [str(path) for path in preserved_trees],
        'baseline_dependency_seeds': [str(path) for path in seeds],
        'current_dependency_files': len(protected_hashes),
        'current_json_documents': len(documents),
        'previous_protected_path_count': len(previous_protected),
        'previous_protected_missing_paths': skipped_missing_prior_paths,
        'manual_user_save_count': len(manual_save_paths),
        'protected': {'path': str(protected_file), 'sha256': contract.digest(protected_file)},
        'status_summary': {'path': str(status_file), 'sha256': contract.digest(status_file)},
        'ledger': {'path': str(ledger_file), 'sha256': contract.digest(ledger_file)},
        'directories': directory_summaries,
        'retired_runs': status_records,
        'files': total_files,
        'logical_bytes': logical_bytes,
        'estimated_reclaimable_file_storage': sum(
            entry['stored'] for entry in allocation_by_identity.values()
            if entry['links'] == entry['candidate_paths']),
        'source_tools_tests_game_mods_user_saves_deleted': False,
        'script_sha256': contract.digest(CONTRACT_PATH),
        'planner_sha256': contract.digest(Path(__file__)),
        'prior_protected_hashes_reused': False,
        'deletion_performed': False,
    }
    plan_path = output_dir / 'plan.json'
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return plan_path


if __name__ == '__main__':
    print(create_plan())
