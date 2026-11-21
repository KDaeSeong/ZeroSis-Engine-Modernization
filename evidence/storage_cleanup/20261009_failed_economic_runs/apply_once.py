"""Explicit, hash-pinned seal/apply entry point for the six reviewed directories.

The default is no action. Seal only observes inputs and writes this OUT folder.
Apply requires the exact sealed-plan and code hashes and writes a one-use marker.
No imported function is patched or replaced.
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
import shutil
import stat
import sys

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
SELF = Path(__file__)


def require(value, message):
    if not value:
        raise RuntimeError(message)


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    with Path(path).open('r', encoding='utf-8-sig') as stream:
        return json.load(stream)


def gzread(path):
    with gzip.open(path, 'rt', encoding='utf-8') as stream:
        return json.load(stream)


def load_contract(path, plan_sha, code_sha):
    path = Path(os.path.abspath(path))
    require(path.parent == OUT and path.name in ('reviewed-draft.json', 'sealed-plan.json'), 'Unreviewed plan location')
    require(digest(path) == plan_sha and digest(SELF) == code_sha, 'Plan/code SHA mismatch')
    plan = read(path)
    require(plan['apply_code_sha256'] == code_sha and plan['root'] == str(ROOT), 'Code/root contract differs')
    source = OUT / 'prepare.py'
    require(digest(source) == plan['prepare_code_sha256'], 'prepare.py differs from reviewed code')
    spec = importlib.util.spec_from_file_location('economic_retirement_prepare', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    require(digest(module.HELPER) == module.HELPER_SHA == plan['safety_helper_sha256'], 'Safety helper changed')
    module.p.boundary(OUT)
    require(plan['exact_absolute_targets'] == [str(x) for x in module.TARGETS] and len(module.TARGETS) == 6,
            'Target contract is not the literal six approved directories')
    return module, plan


def check_artifact(record):
    path = Path(record['path'])
    require(path.parent == OUT and digest(path) == record['sha256'], 'Pinned OUT artifact changed')
    return path


def load_inventory(m, plan):
    path = check_artifact(plan['inventory'])
    inventory = read(path)
    require(inventory['files'] == 9936 and inventory['retired_host'] == m.OLD_HOST and
            inventory['retained_host'] == m.KEEP_HOST, 'Unexpected reviewed inventory')
    require(digest(OUT / 'prepare.inventory-v1.py') == inventory['script_sha256'], 'Original inventory generator changed')
    for record in inventory['artifacts'].values():
        check_artifact(record)
    rows = gzread(OUT / 'retired-files.json.gz')
    dirs = gzread(OUT / 'retired-directories.json.gz')
    aliases = gzread(OUT / 'external-hardlinks.json.gz')
    require(len(rows) == 9936 and len({x['path'] for x in rows}) == len(rows), 'Target ledger is incomplete/duplicated')
    return inventory, rows, dirs, aliases


class PhaseFiles:
    """One phase-local identity hash cache and one validation per ancestor."""
    def __init__(self, m):
        self.m = m
        self.parents = {ROOT}
        m.p.boundary(OUT)
        self.hashes = {}

    def inspect(self, path):
        path = Path(os.path.abspath(path))
        require(path.is_relative_to(ROOT) and path != ROOT, 'Protected path escaped project')
        chain, parent = [], path.parent
        while parent not in self.parents:
            require(parent.is_relative_to(ROOT), 'Protected ancestor escaped project')
            chain.append(parent); parent = parent.parent
        for folder in reversed(chain):
            info = folder.lstat()
            require(stat.S_ISDIR(info.st_mode) and not info.st_file_attributes & 0x400, 'Reparse/non-directory ancestor')
            self.parents.add(folder)
        info = self.m.p.regular(path)
        key = self.m.identity(info)
        if key not in self.hashes:
            self.hashes[key] = digest(path)
        require(self.m.identity(self.m.p.regular(path)) == key, 'Protected file changed during this phase')
        return info, self.hashes[key]


def verify_guards(m, rows, *, compression_refresh=False, removed=None):
    phase, output = PhaseFiles(m), []
    removed = removed or Counter()
    require(len({x['path'] for x in rows}) == len(rows), 'Duplicate protected paths')
    for row in rows:
        path = ROOT / row['path']
        require(not m.inside(path), 'Protected file intersects deletion scope')
        info, sha = phase.inspect(path)
        pair = row['device'], row['file_id']
        require((info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns) ==
                (*pair, row['bytes'], row['mtime_ns']) and sha == row['sha256'], 'Protected identity/content/mtime changed: ' + str(path))
        require(info.st_nlink == row['links'] - removed[pair], 'Protected hardlink count changed unexpectedly')
        if compression_refresh:
            require((info.st_file_attributes ^ row['attributes']) & ~0x800 == 0, 'Non-compression protected attributes changed')
        else:
            require(info.st_file_attributes == row['attributes'], 'Protected attributes changed')
        output.append({**row, 'attributes': info.st_file_attributes,
                       'stored_bytes': m.p.stored(path) if compression_refresh else row['stored_bytes']})
    require(sum('manual_save' in row['reasons'] for row in rows) == 8, 'Manual-save protection count is not eight')
    return output


def verify_targets(m, rows, directories):
    expected = {row['path']: row for row in rows}
    expected_dirs = {row['path']: row for row in directories}
    seen, seen_dirs, phase = set(), set(), PhaseFiles(m)
    for root in m.TARGETS:
        m.p.legal_target(root)
        for path, info, is_dir in m.walk_owned(root):
            relative = str(path.relative_to(ROOT))
            if is_dir:
                require(relative in expected_dirs, 'Unexpected target directory')
                row = expected_dirs[relative]
                require((info.st_dev, info.st_ino, info.st_mtime_ns) ==
                        (row['device'], row['file_id'], row['mtime_ns']), 'Target directory identity/mtime changed')
                seen_dirs.add(relative)
                continue
            require(relative in expected, 'Unexpected file inside target')
            row = expected[relative]
            current, sha = phase.inspect(path)
            require(m.identity(current) == (row['device'], row['file_id'], row['bytes'], row['mtime_ns'], row['links'], row['attributes'])
                    and sha == row['sha256'], 'Target content/identity changed')
            seen.add(relative)
    require(seen == set(expected) and seen_dirs == set(expected_dirs), 'Missing target files/directories')


def verify_aliases(m, aliases, after=False):
    phase = PhaseFiles(m)
    for group in aliases:
        expected_links = group['links_after_exact_unlinks'] if after else group['links_before']
        for row in group['surviving_aliases']:
            path = Path(row['path'])
            if row['inside_project']:
                info, sha = phase.inspect(path)
            else:
                info = m.p.regular(path); sha = digest(path)
                require(m.identity(m.p.regular(path)) == m.identity(info), 'Outside-project alias changed')
            require((info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_file_attributes, info.st_nlink) ==
                    (row['device'], row['file_id'], row['bytes'], row['mtime_ns'], row['attributes'], expected_links) and
                    sha == row['sha256'], 'External alias identity/content/attributes changed')
        representative = Path(group['surviving_aliases'][0]['path'])
        actual = {str(x).casefold() for x in m.hardlink_names(representative)}
        wanted = {row['path'].casefold() for row in group['surviving_aliases']}
        if not after:
            wanted |= {path.casefold() for path in group['target_paths']}
        require(actual == wanted, 'External hardlink name set differs')


def verify_diagnostics(plan):
    archive = gzread(check_artifact(plan['diagnostics']))
    names = {row['path'] for row in archive['files']}
    require(set(plan['required_raw_diagnostic_paths']) <= names, 'Required raw snapshot/prepared/support evidence is missing')
    for row in archive['files']:
        raw = base64.b64decode(archive['blobs_by_sha256'][row['sha256']], validate=True)
        require(len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256'], 'Raw diagnostic recovery failed')


def current_references(m):
    documents = set((ROOT / 'evidence').glob('*/*/request.json'))
    documents |= set((ROOT / 'evidence/ui_window_host').glob('*/build_result.json'))
    rows = []
    for path in sorted(documents):
        if m.inside(path):
            continue
        raw = path.read_bytes()
        require(not any(value.encode() in raw for value in (*m.RUNS, m.OLD_HOST)), 'Surviving request/build depends on a target')
        rows.append({'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest()})
    return rows


def seal(m, plan, reviewed_path, reviewed_sha, code_sha):
    require(not any((OUT / name).exists() for name in ('sealed-plan.json', 'protected-final.json.gz', 'cleanup.json')),
            'Seal/apply output already exists; do not replay')
    gate = m.final_gate()
    inventory, targets, directories, aliases = load_inventory(m, plan)
    verify_diagnostics(plan)
    require(digest(Path(plan['compression_receipt']['path'])) == plan['compression_receipt']['sha256'] and
            read(plan['compression_receipt']['path'])['status'].startswith('PASS'), 'Reviewed compression receipt changed')
    verify_targets(m, targets, directories)
    verify_aliases(m, aliases)
    guards = gzread(OUT / 'protected-draft.json.gz')
    known = {row['path'] for row in guards}
    for addition in plan['additional_protected_reports']:
        path = m.p.boundary(Path(addition['path']))
        require(str(path.relative_to(ROOT)) not in known and digest(path) == addition['sha256'], 'Additional proof differs/duplicates')
        row = m.file_row(path, m.p.regular(path), {}, {})
        row['reasons'] = ['independent_economic_report']; guards.append(row); known.add(row['path'])
    require(len(guards) == 43412, 'Expected explicit 43,409 guards plus three independent reports')
    sealed_guards = verify_guards(m, guards, compression_refresh=True)
    references = current_references(m)
    final = m.write_new('protected-final.json.gz', sealed_guards, True)
    sealed = {**plan, 'status': 'SEALED_READY_FOR_ROOT_REVIEW_NOT_APPLIED',
              'sealed_utc': datetime.now(timezone.utc).isoformat(), 'reviewed_draft': {'path': str(reviewed_path), 'sha256': reviewed_sha},
              'protected_final': final, 'protected_files': len(sealed_guards), 'final_gate': gate,
              'reference_documents': references, 'file_count': len(targets), 'no_apply_performed': True}
    artifact = m.write_new('sealed-plan.json', sealed)
    print(json.dumps({'status': sealed['status'], 'plan': artifact, 'protected_files': len(sealed_guards),
                      'files': len(targets), 'code_sha256': code_sha}, ensure_ascii=False), flush=True)


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


def apply(m, plan, plan_sha, code_sha):
    require(plan['status'] == 'SEALED_READY_FOR_ROOT_REVIEW_NOT_APPLIED' and
            not (OUT / 'cleanup.json').exists() and not (OUT / 'cleanup.json.new').exists() and
            not (OUT / 'removed-files.jsonl').exists(), 'Plan applied/failed previously or not sealed')
    check_artifact(plan['reviewed_draft'])
    inventory, targets, directories, aliases = load_inventory(m, plan)
    guards = gzread(check_artifact(plan['protected_final']))
    require(len(guards) == plan['protected_files'] == 43412, 'Sealed protected set differs')
    receipt = {'status': 'APPLY_STARTED_DO_NOT_REPLAY', 'plan_sha256': plan_sha, 'code_sha256': code_sha,
               'prepare_sha256': plan['prepare_code_sha256'], 'removed_files': 0, 'removed_logical_bytes': 0,
               'removed_journal': {'path': str(OUT / 'removed-files.jsonl'), 'rows': 0, 'bytes': 0},
               'protected_files': len(guards), 'manual_saves': 8, 'volume_free_bytes_before': shutil.disk_usage(ROOT).free}
    write_receipt(receipt)
    removed_counts = Counter(); journal_hash = hashlib.sha256(); journal = None
    try:
        m.final_gate(); verify_diagnostics(plan)
        require(current_references(m) == plan['reference_documents'], 'Surviving request/build references changed after seal')
        verify_guards(m, guards); verify_targets(m, targets, directories); verify_aliases(m, aliases)
        critical_reasons = {'manual_save', 'current_provider_or_host_source', 'current_route', 'independent_economic_report'}
        critical = [row for row in guards if critical_reasons.intersection(row['reasons'])]
        verify_guards(m, critical); m.final_gate()
        journal = (OUT / 'removed-files.jsonl').open('xb', buffering=0)
        for row in targets:
            path = m.p.boundary(ROOT / row['path'])
            require(m.inside(path), 'Deletion path escaped exact six targets')
            info = m.p.regular(path); pair = row['device'], row['file_id']
            wanted = (row['device'], row['file_id'], row['bytes'], row['mtime_ns'], row['links'] - removed_counts[pair], row['attributes'])
            require(m.identity(info) == wanted and digest(path) == row['sha256'], 'Immediate target identity/mtime/SHA differs')
            exclusive_probe(m, path)
            require(m.identity(m.p.regular(path)) == wanted, 'Target identity changed immediately before unlink')
            m.p.unlink_without_attribute_changes(path)
            require(not path.exists(), 'Target alias remains after unlink')
            removed_counts[pair] += 1
            receipt['last_removed_path'] = row['path']; receipt['last_removed_sha256'] = row['sha256']
            receipt['removed_files'] += 1; receipt['removed_logical_bytes'] += row['bytes']
            receipt['journal_incomplete_possible'] = True
            line = (json.dumps({'path': row['path'], 'sha256': row['sha256']}, ensure_ascii=False,
                               separators=(',', ':')) + '\n').encode('utf-8')
            require(journal.write(line) == len(line), 'Deletion journal write was incomplete')
            journal.flush(); journal_hash.update(line)
            receipt['removed_journal']['rows'] += 1; receipt['removed_journal']['bytes'] += len(line)
            receipt['removed_journal']['sha256'] = journal_hash.hexdigest()
            receipt['journal_incomplete_possible'] = False
            if receipt['removed_files'] % 100 == 0:
                write_receipt(receipt)
        for row in sorted(directories, key=lambda value: len(Path(value['path']).parts), reverse=True):
            path = m.p.boundary(ROOT / row['path']); info = path.lstat()
            require(m.inside(path) and stat.S_ISDIR(info.st_mode) and
                    (info.st_dev, info.st_ino) == (row['device'], row['file_id']) and not any(path.iterdir()), 'Unexpected/nonempty target directory')
            path.rmdir()
        verify_guards(m, guards, removed=removed_counts); verify_aliases(m, aliases, after=True); m.final_gate()
        require(all(not path.exists() for path in m.TARGETS), 'A retired target remains')
        receipt.update(status='PASS_EXACT_SIX_FAILED_ECONOMIC_DIRECTORIES_REMOVED', protected_sha_verified_before_and_after=True,
                       manual_saves_unchanged=8, native_or_build_launched=False, source_or_replay_output_removed=False,
                       estimated_file_storage_reclaimed=inventory['estimated_reclaimable_file_storage_bytes'],
                       volume_free_bytes_after=shutil.disk_usage(ROOT).free)
    except Exception as error:
        receipt.update(status='FAILED_DO_NOT_REPLAY', error=repr(error)); write_receipt(receipt); raise
    finally:
        if journal is not None:
            journal.close()
    write_receipt(receipt)
    print(json.dumps({'status': receipt['status'], 'removed_files': receipt['removed_files'],
                      'removed_logical_bytes': receipt['removed_logical_bytes'], 'receipt': str(OUT / 'cleanup.json'),
                      'receipt_sha256': digest(OUT / 'cleanup.json')}, ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--seal', type=Path); mode.add_argument('--apply', type=Path)
    parser.add_argument('--plan-sha256', required=True); parser.add_argument('--code-sha256', required=True)
    args = parser.parse_args()
    path = Path(os.path.abspath(args.seal or args.apply))
    m, plan = load_contract(path, args.plan_sha256, args.code_sha256)
    if args.seal:
        require(path.name == 'reviewed-draft.json', 'Seal requires reviewed draft')
        seal(m, plan, path, args.plan_sha256, args.code_sha256)
    else:
        require(path.name == 'sealed-plan.json', 'Apply requires sealed plan')
        apply(m, plan, args.plan_sha256, args.code_sha256)


if __name__ == '__main__':
    main()
