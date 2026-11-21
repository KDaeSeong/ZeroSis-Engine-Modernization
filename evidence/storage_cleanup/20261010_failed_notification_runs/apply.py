"""Reviewed, one-use seal/apply for exactly four failed Notification run folders.

No default action. Both modes require exact plan and code SHA arguments. Seal
does no deletion; apply is a separate root-reviewed call using its sealed SHA.
No imported helper is replaced or patched. Every write stays in OUT except the
explicit per-file unlinks/empty-directory removals inside the four targets.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter
import ctypes
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
import sys

SELF = Path(__file__).resolve()
OUT = SELF.parent
ROOT = OUT.parents[2]
EXPECTED_ROOT = Path(r"C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization")
RUNS = ('20261009T144109Z_de7705b9790b', '20261009T145225Z_edf44c8f1c55')
TARGETS = tuple(ROOT / group / run for run in RUNS for group in
                ('Build/InteractiveGameRuntime', 'evidence/interactive_game'))
FRESH = '20261009T155510Z_59a23754e9cf'
RESTORE = '20261009T160013Z_804760e7018f'
HOST = '20261009T155317Z_8f390480966b'
REVIEWED_PLAN_SHA = 'b31b599fad00f1d31e481e3bccf40f24a0e25db6c67c624dff8ffe2ebd972395'
EXPECTED_FILES = 1955
EXPECTED_GUARDS = 6488
EXPECTED_ALIASES = 16109


def require(value, message):
    if not value:
        raise RuntimeError(message)


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def gzread(path):
    with gzip.open(path, 'rt', encoding='utf-8') as stream:
        return json.load(stream)


def artifact(path):
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': digest(path)}


def check_out(record):
    path = Path(record['path'])
    require(path.parent == OUT and path.is_file() and path.resolve(strict=True) == path,
            'Pinned evidence is outside this exact OUT or resolves elsewhere')
    require(path.stat().st_size == record['bytes'] and digest(path) == record['sha256'],
            'Pinned evidence bytes/SHA changed: ' + path.name)
    return path


def load_contract(path, plan_sha, code_sha):
    require(ROOT == EXPECTED_ROOT and OUT == ROOT / 'evidence/storage_cleanup/20261010_failed_notification_runs',
            'Unexpected cleanup root')
    path = Path(os.path.abspath(path))
    require(path.parent == OUT and path.name in ('plan.json', 'sealed-plan.json'), 'Unexpected plan location')
    require(re.fullmatch(r'[0-9a-f]{64}', plan_sha) and re.fullmatch(r'[0-9a-f]{64}', code_sha),
            'Exact lowercase plan/code SHA required')
    require(digest(path) == plan_sha and digest(SELF) == code_sha, 'Plan or apply code SHA differs')
    value = read(path)
    if path.name == 'sealed-plan.json':
        require(value['status'] == 'SEALED_NOT_APPLIED' and value['apply_code']['sha256'] == code_sha,
                'Sealed code/status differs')
        draft_path = check_out(value['draft'])
        require(value['draft']['sha256'] == REVIEWED_PLAN_SHA, 'Sealed draft is not the root-reviewed plan')
        draft = read(draft_path)
    else:
        require(plan_sha == REVIEWED_PLAN_SHA, 'Draft differs from the exact root-reviewed SHA')
        draft = value
    require(draft['status'] == 'DRAFT_ONLY_NOT_AUTHORIZED_FOR_APPLY' and draft['root'] == str(ROOT) and
            draft['exact_targets'] == [str(x) for x in TARGETS] and draft['target_count'] == 4 and
            draft['file_count'] == EXPECTED_FILES and draft['critical_guard_count'] == EXPECTED_GUARDS and
            draft['outside_alias_path_count'] == EXPECTED_ALIASES, 'Reviewed target/protection contract differs')
    source = check_out(draft['script'])
    require(source == OUT / 'prepare.py', 'Unexpected preparation helper')
    spec = importlib.util.spec_from_file_location('notification_retirement_prepare', source)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    require(m.ROOT == ROOT and tuple(m.TARGETS) == TARGETS and m.HELPER_SHA == draft['helper']['sha256'] and
            digest(m.HELPER) == m.HELPER_SHA, 'Literal targets or reusable safety helper changed')
    m.p.boundary(OUT)
    return m, draft, value


class PhaseFiles:
    """Fresh hashes per phase; cached ancestor checks and NTFS identity dedup."""
    def __init__(self, m):
        self.m, self.parents, self.hashes = m, set(), {}

    def inspect(self, path, outside_project=False):
        path = Path(path)
        require(path == Path(os.path.abspath(path)), 'File path is not absolute and normalized')
        if not outside_project:
            require(path.is_relative_to(ROOT) and path != ROOT, 'Protected file escaped project')
        for parent in path.parents:
            if parent in self.parents:
                break
            info = parent.lstat()
            require(stat.S_ISDIR(info.st_mode) and not info.st_file_attributes & 0x400,
                    'Reparse/non-directory ancestor: ' + str(parent))
            self.parents.add(parent)
        info = self.m.p.regular(path)
        key = self.m.identity(info)
        if key not in self.hashes:
            self.hashes[key] = digest(path)
        require(self.m.identity(self.m.p.regular(path)) == key, 'File changed during phase: ' + str(path))
        return info, self.hashes[key]


def load_ledgers(m, draft):
    inventory = gzread(check_out(draft['inventory']))
    protected = gzread(check_out(draft['protection']))
    rows, dirs, aliases = inventory['files'], inventory['directories'], inventory['external_hardlinks']
    guards = protected['critical_guards']
    require(len(rows) == EXPECTED_FILES and len({row['path'] for row in rows}) == EXPECTED_FILES,
            'Target ledger count/uniqueness differs')
    require(len(dirs) == draft['directory_count'] and len({row['path'] for row in dirs}) == len(dirs),
            'Directory ledger count/uniqueness differs')
    require(len(guards) == EXPECTED_GUARDS and len({row['path'] for row in guards}) == len(guards),
            'Protected ledger count/uniqueness differs')
    require(sum(len(group['surviving_aliases']) for group in aliases) == EXPECTED_ALIASES,
            'External alias ledger differs')
    require(len(protected['manual_saves']) == 9 and protected['original_manual_save_count'] == 8 and
            protected['additional_ea_save_count'] == 1, 'Nine manual/EA saves are not pinned')
    require(protected['reference_holds'] == draft['reference_holds'] == [], 'Unresolved references block sealing/apply')
    for row in [*rows, *dirs]:
        path = ROOT / row['path']
        require(not Path(row['path']).is_absolute() and path == Path(os.path.abspath(path)) and m.inside(path),
                'Target ledger contains an escaped/unnormalized path')
    for row in guards:
        require(not m.inside(ROOT / row['path']), 'Protected file overlaps deletion targets')
    return rows, dirs, aliases, guards, protected


def verify_diagnostics(m, draft):
    archive = gzread(check_out(draft['diagnostics']))
    expected, missing = m.diagnostic_sources()
    require({row['path'] for row in archive['records']} == {str(path.relative_to(ROOT)) for path in expected},
            'Required raw diagnostic path set differs')
    require(archive['missing_failure_packets'] == missing and len(archive['records']) == 65,
            'Failure packet absence/source record contract differs')
    for row in archive['records']:
        raw = base64.b64decode(archive['blobs_by_sha256'][row['sha256']], validate=True)
        require(len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256'],
                'Diagnostic byte restoration failed')


def verify_guards(m, guards, protected, removed=None):
    removed = removed or Counter()
    phase = PhaseFiles(m)
    for row in guards:
        info, sha = phase.inspect(ROOT / row['path'])
        pair = row['device'], row['file_id']
        require(m.identity(info) == (*pair, row['bytes'], row['mtime_ns'], row['links'] - removed[pair], row['attributes'])
                and sha == row['sha256'], 'Protected identity/mtime/SHA changed: ' + row['path'])
    expected_source = {row['path'] for row in guards if Path(row['path']).parts[0] in ('Source', 'tools', 'Tests')}
    observed_source = set()
    for name in ('Source', 'tools', 'Tests'):
        for path, _, is_dir in m.walk_owned(ROOT / name):
            if not is_dir:
                observed_source.add(str(path.relative_to(ROOT)))
    require(observed_source == expected_source, 'Source/tools/Tests path set changed')
    manual_ids = list(dict.fromkeys(re.findall(r'\d{8}T\d{6}Z_[0-9a-f]{12}',
                      (ROOT / 'tools/Start-Engine.ps1').read_text(encoding='utf-8-sig'))))
    require(manual_ids == protected['manual_runtime_ids'], 'Manual launcher routes changed')
    actual_saves = set()
    for run in manual_ids:
        root = ROOT / 'Build/InteractiveGameRuntime' / run
        actual_saves.update(str(path.relative_to(ROOT)) for path in
                            [*root.glob('*.zssave'), *root.glob('sessions/*/*.zssave')])
    require(actual_saves == {row['path'] for row in protected['manual_saves']}, 'Manual/EA save set changed')


def verify_targets(m, rows, dirs):
    expected, expected_dirs = ({row['path']: row for row in values} for values in (rows, dirs))
    seen, seen_dirs, phase = set(), set(), PhaseFiles(m)
    for root in TARGETS:
        require(m.p.legal_target(root) == root, 'Exact target root boundary differs')
        for path, info, is_dir in m.walk_owned(root):
            relative = str(path.relative_to(ROOT))
            if is_dir:
                require(relative in expected_dirs, 'Unexpected target directory')
                row = expected_dirs[relative]
                require((info.st_dev, info.st_ino, info.st_mtime_ns, info.st_file_attributes) ==
                        (row['device'], row['file_id'], row['mtime_ns'], row['attributes']),
                        'Target directory identity/mtime/attributes changed')
                seen_dirs.add(relative)
            else:
                require(relative in expected, 'Unexpected target file')
                row = expected[relative]
                current, sha = phase.inspect(path)
                require(m.identity(current) == (row['device'], row['file_id'], row['bytes'], row['mtime_ns'],
                                                row['links'], row['attributes']) and sha == row['sha256'],
                        'Target identity/mtime/SHA changed: ' + relative)
                seen.add(relative)
    require(seen == set(expected) and seen_dirs == set(expected_dirs), 'Target file/directory set differs')


def verify_aliases(m, aliases, after=False):
    phase = PhaseFiles(m)
    for group in aliases:
        links = group['links_after_exact_unlinks'] if after else group['links_before']
        for row in group['surviving_aliases']:
            path = Path(row['path'])
            require(not m.inside(path), 'External survivor is in the deletion scope')
            info, sha = phase.inspect(path, outside_project=not row['inside_project'])
            require(m.identity(info) == (row['device'], row['file_id'], row['bytes'], row['mtime_ns'],
                                        links, row['attributes']) and sha == row['sha256'],
                    'External alias identity/mtime/SHA changed: ' + str(path))
        names = {str(path).casefold() for path in m.hardlink_names(Path(group['surviving_aliases'][0]['path']))}
        wanted = {row['path'].casefold() for row in group['surviving_aliases']}
        if not after:
            wanted.update(path.casefold() for path in group['target_paths'])
        require(names == wanted, 'External alias name/count set changed')


def final_gate(m):
    processes = m.process_audit()
    require(not processes['other_active_hosts_or_compilers'], 'No-active gate: Host/compiler/linker is still active')
    records, requests, results = [], [], []

    def pin(path, expected=None):
        path = m.p.boundary(Path(path))
        require(not m.inside(path), 'Accepted proof points into a retirement target')
        record = artifact(path)
        require(expected is None or record['sha256'] == expected, 'Accepted proof SHA mismatch')
        records.append(record)

    for index, run in enumerate((FRESH, RESTORE)):
        evidence = ROOT / 'evidence/interactive_game' / run
        result_path, request_path = evidence / 'result.json', evidence / 'request.json'
        value, request = read(result_path), read(request_path)
        wanted = 'CONTINUOUS_INTERACTIVE_SDK_TREE_DECISION_UI_' + ('RESTORE_SMOKE_PASS' if index else 'SMOKE_PASS')
        require(value.get('run_id') == run and value.get('status') == wanted and
                type(value.get('returncode')) is int and value['returncode'] == 0 and
                value.get('timed_out') is False and value.get('failures') == [], 'Latest native pair is not terminal PASS')
        require(request.get('run_id') == run and request.get('notification_panel') is True and
                request.get('action_info_panel') is True and request.get('smoke') is True,
                'Latest native request flags differ')
        require(read(evidence / 'host_build.json')['build_id'] == HOST, 'Latest native pair used another Host')
        pin(result_path); pin(request_path); pin(evidence / 'host_build.json')
        pin(value['request']['path'], value['request']['sha256'])
        requests.append(request); results.append(value)
    lineage = requests[1].get('resume_from')
    require(requests[0].get('resume_from') is None and isinstance(lineage, dict) and lineage.get('run_id') == FRESH and
            results[1].get('resume_from_run') == FRESH and results[1].get('checkpoint_input_unchanged') is True and
            results[1].get('semantic_restore_equal') is True and results[1].get('fresh_process_restore_verified') is True,
            'Fresh/restore lineage/state proof differs')
    for name, sha in m.p.refs(lineage):
        pin(name, sha)
    require(lineage['run_result']['sha256'] == digest(ROOT / 'evidence/interactive_game' / FRESH / 'result.json') and
            lineage['checkpoint_source']['sha256'] == lineage['checkpoint_input']['sha256'] and
            Path(lineage['checkpoint_source']['path']).is_relative_to(ROOT / 'Build/InteractiveGameRuntime' / FRESH) and
            Path(lineage['checkpoint_input']['path']).is_relative_to(ROOT / 'Build/InteractiveGameRuntime' / RESTORE),
            'Restore checkpoint/source-result identity differs')
    host_result = ROOT / 'evidence/ui_window_host' / HOST / 'build_result.json'
    build = read(host_result)
    require(build.get('build_id') == HOST and build.get('status') == 'UI_WINDOW_HOST_CANDIDATE_BUILT',
            'Latest protected Host build differs')
    pin(host_result); pin(build['executable']['path'], build['executable']['sha256'])
    return {'status': 'PASS_LATEST_NATIVE_PAIR_AND_NO_ACTIVE_HOST_COMPILER', 'host': HOST,
            'fresh': FRESH, 'restore': RESTORE,
            'artifacts': sorted({row['path']: row for row in records}.values(), key=lambda row: row['path']),
            'processes_observed': processes['processes_observed']}


def current_references(m):
    documents = set((ROOT / 'evidence').glob('*/*/request.json'))
    documents.update((ROOT / 'evidence/ui_window_host').glob('*/build_result.json'))
    records = []
    for path in sorted(documents):
        if m.inside(path):
            continue
        m.p.boundary(path)
        raw = path.read_bytes()
        require(not any(run.encode() in raw for run in RUNS), 'Surviving request/build references a target')
        records.append({'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
    return records


def seal(m, draft, code_sha):
    for name in ('seal-started.json', 'sealed-plan.json', 'protected-final.json.gz', 'apply-started.json', 'cleanup.json'):
        require(not (OUT / name).exists(), 'Seal/apply was already attempted; do not replay')
    # This rejects active Host/compiler/linker before even writing a seal marker.
    first_gate = final_gate(m)
    m.write_new('seal-started.json', {'utc': datetime.now(timezone.utc).isoformat(),
                'draft_sha256': REVIEWED_PLAN_SHA, 'apply_code_sha256': code_sha, 'no_deletion': True})
    try:
        rows, dirs, aliases, guards, protected = load_ledgers(m, draft)
        verify_diagnostics(m, draft)
        verify_targets(m, rows, dirs)
        verify_aliases(m, aliases)
        verify_guards(m, guards, protected)
        refs = current_references(m)
        final = final_gate(m)
        require(first_gate['artifacts'] == final['artifacts'], 'Accepted proof changed during seal')
        sealed_guards = m.write_new('protected-final.json.gz', protected, True)
        sealed = {'schema': 1, 'status': 'SEALED_NOT_APPLIED', 'utc': datetime.now(timezone.utc).isoformat(),
                  'root': str(ROOT), 'draft': artifact(OUT / 'plan.json'), 'apply_code': artifact(SELF),
                  'prepare_code': draft['script'], 'safety_helper': draft['helper'],
                  'exact_targets': [str(path) for path in TARGETS], 'file_count': EXPECTED_FILES,
                  'protected_files': EXPECTED_GUARDS, 'manual_saves': 9, 'outside_alias_paths': EXPECTED_ALIASES,
                  'protected_final': sealed_guards, 'final_gate': final, 'reference_documents': refs,
                  'no_deletion_performed': True}
        report = m.write_new('sealed-plan.json', sealed)
        print(json.dumps({'status': sealed['status'], 'plan': report, 'code_sha256': code_sha}), flush=True)
    except Exception as exc:
        m.write_new('seal-failed.json', {'status': 'SEAL_FAILED_DO_NOT_REPLAY', 'error': repr(exc),
                    'utc': datetime.now(timezone.utc).isoformat(), 'deletion_performed': False})
        raise


def write_receipt(value):
    temporary = OUT / 'cleanup.json.new'
    with temporary.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2); stream.write('\n')
    os.replace(temporary, OUT / 'cleanup.json')


def exclusive_probe(m, path):
    handle = m.p.K.CreateFileW(str(path), 0x80010000, 0, None, 3, 0x00200000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    m.p.K.CloseHandle(handle)


def apply(m, draft, sealed, plan_sha, code_sha):
    for name in ('apply-started.json', 'cleanup.json', 'cleanup.json.new', 'removed-files.jsonl'):
        require(not (OUT / name).exists(), 'Apply was already attempted; do not replay')
    require(sealed['exact_targets'] == [str(path) for path in TARGETS] and
            sealed['file_count'] == EXPECTED_FILES and sealed['protected_files'] == EXPECTED_GUARDS,
            'Sealed target/guard contract differs')
    # Preserve the same strict no-active gate as the draft; no exceptions for
    # unrelated compilers or Hosts are introduced by this application entry point.
    gate = final_gate(m)
    require(gate['artifacts'] == sealed['final_gate']['artifacts'], 'Accepted native proof changed after seal')
    rows, dirs, aliases, _, _ = load_ledgers(m, draft)
    protected = gzread(check_out(sealed['protected_final']))
    guards = protected['critical_guards']
    require(len(guards) == EXPECTED_GUARDS, 'Final protected guard count differs')
    marker = m.write_new('apply-started.json', {'utc': datetime.now(timezone.utc).isoformat(),
                         'sealed_plan_sha256': plan_sha, 'apply_code_sha256': code_sha,
                         'draft_sha256': REVIEWED_PLAN_SHA, 'no_replay': True})
    receipt = {'status': 'APPLY_STARTED_DO_NOT_REPLAY', 'start': marker, 'plan_sha256': plan_sha,
               'apply_code_sha256': code_sha, 'prepare_code_sha256': draft['script']['sha256'],
               'safety_helper_sha256': draft['helper']['sha256'],
               'removed_files': 0, 'removed_logical_bytes': 0, 'removed_directories': 0,
               'protected_files': EXPECTED_GUARDS, 'manual_saves': 9, 'outside_alias_paths': EXPECTED_ALIASES,
               'removed_journal': {'path': str(OUT / 'removed-files.jsonl'), 'rows': 0, 'bytes': 0},
               'volume_free_bytes_before': shutil.disk_usage(ROOT).free}
    write_receipt(receipt)
    removed = Counter(); journal_hash = hashlib.sha256(); journal = None
    try:
        verify_diagnostics(m, draft)
        require(current_references(m) == sealed['reference_documents'], 'Surviving request/build records changed after seal')
        verify_targets(m, rows, dirs)
        verify_aliases(m, aliases)
        verify_guards(m, guards, protected)
        require(final_gate(m)['artifacts'] == sealed['final_gate']['artifacts'], 'Final gate/proof changed before unlink')
        journal = (OUT / 'removed-files.jsonl').open('xb', buffering=0)
        for row in rows:
            path = m.p.boundary(ROOT / row['path'])
            require(m.inside(path), 'Immediate deletion path escaped the four targets')
            pair = row['device'], row['file_id']
            wanted = (*pair, row['bytes'], row['mtime_ns'], row['links'] - removed[pair], row['attributes'])
            require(m.identity(m.p.regular(path)) == wanted and digest(path) == row['sha256'],
                    'Immediate target identity/mtime/SHA differs')
            exclusive_probe(m, path)
            require(m.identity(m.p.regular(path)) == wanted, 'Target identity changed immediately before unlink')
            m.p.unlink_without_attribute_changes(path)
            require(not path.exists(), 'Target alias remains after unlink')
            removed[pair] += 1
            receipt['removed_files'] += 1; receipt['removed_logical_bytes'] += row['bytes']
            receipt['last_removed_path'] = row['path']; receipt['last_removed_sha256'] = row['sha256']
            receipt['journal_incomplete_possible'] = True
            line = (json.dumps({'path': row['path'], 'sha256': row['sha256']}, ensure_ascii=False,
                               separators=(',', ':')) + '\n').encode('utf-8')
            require(journal.write(line) == len(line), 'Removal journal write was incomplete')
            journal.flush(); journal_hash.update(line)
            receipt['removed_journal']['rows'] += 1; receipt['removed_journal']['bytes'] += len(line)
            receipt['removed_journal']['sha256'] = journal_hash.hexdigest()
            receipt['journal_incomplete_possible'] = False
            if receipt['removed_files'] % 100 == 0:
                write_receipt(receipt)
        for row in sorted(dirs, key=lambda item: len(Path(item['path']).parts), reverse=True):
            path = m.p.boundary(ROOT / row['path']); info = path.lstat()
            require(m.inside(path) and stat.S_ISDIR(info.st_mode) and not info.st_file_attributes & 0x400 and
                    (info.st_dev, info.st_ino) == (row['device'], row['file_id']) and not any(path.iterdir()),
                    'Unexpected/reparsed/nonempty target directory')
            path.rmdir()
            receipt['removed_directories'] += 1
        verify_guards(m, guards, protected, removed)
        verify_aliases(m, aliases, after=True)
        require(current_references(m) == sealed['reference_documents'], 'Surviving request/build records changed during apply')
        require(final_gate(m)['artifacts'] == sealed['final_gate']['artifacts'], 'Accepted proof changed during apply')
        require(all(not path.exists() for path in TARGETS), 'A retired target remains')
        receipt.update(status='PASS_EXACT_FOUR_FAILED_NOTIFICATION_DIRECTORIES_REMOVED',
                       protected_sha_verified_before_and_after=True, manual_saves_unchanged=9,
                       external_alias_sha_verified_before_and_after=True,
                       estimated_reclaimed_allocated_bytes=draft['reclaimable_allocated_bytes_if_all_exact_unlinks_succeed'],
                       volume_free_bytes_after=shutil.disk_usage(ROOT).free,
                       source_build_native_launch_or_runtime_compression_performed=False)
    except Exception as exc:
        receipt.update(status='FAILED_DO_NOT_REPLAY', error=repr(exc))
        write_receipt(receipt)
        raise
    finally:
        if journal is not None:
            journal.close()
    write_receipt(receipt)
    print(json.dumps({'status': receipt['status'], 'removed_files': receipt['removed_files'],
                      'removed_logical_bytes': receipt['removed_logical_bytes'],
                      'receipt': artifact(OUT / 'cleanup.json')}), flush=True)


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--seal', type=Path)
    mode.add_argument('--apply', type=Path)
    parser.add_argument('--plan-sha256', required=True)
    parser.add_argument('--code-sha256', required=True)
    args = parser.parse_args()
    path = Path(os.path.abspath(args.seal or args.apply))
    m, draft, value = load_contract(path, args.plan_sha256, args.code_sha256)
    if args.seal:
        require(path.name == 'plan.json', 'Seal requires the reviewed draft plan')
        seal(m, draft, args.code_sha256)
    else:
        require(path.name == 'sealed-plan.json', 'Apply requires a reviewed sealed plan')
        apply(m, draft, value, args.plan_sha256, args.code_sha256)


if __name__ == '__main__':
    main()
