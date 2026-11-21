"""Reviewed alternate apply entrypoint for the existing exact eight-path plan.

The original prepare.py, helper, inventory and plan remain unchanged. Only the
protected-file verifier is expressed here as one streaming project_files pass.
--self-test is a small in-memory contract test and never scans/deletes files.
Application requires BOTH the completed original plan SHA and this code's SHA.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import stat
from types import SimpleNamespace

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
PREPARE = OUT / 'prepare.py'
HELPER = ROOT / 'tools/prune_superseded_runtime_artifacts.py'
PREPARE_SHA = '709a0a6dacd4701a4a24cbedcf604dff0e2d16088a12dc629588a15b7f2a778c'
HELPER_SHA = '99eed1b129e24139b435feb34e2a88172ba7332ffaf9a3e4d3d20f9dfa177baa'
INVENTORY_SHA = 'a260f5d11b62aa9a26ba27a2934d9aac8bc486c9721c276217136e50db776b59'
IDS = ('20261009T095944Z_69db988e03ae', '20261009T100903Z_f17699843268',
       '20261009T101239Z_5ca855aa154e', '20261009T101731Z_2d8009cc967c')
DIRS = tuple(ROOT / group / value for value in IDS for group in ('Build/UiWindowHost', 'evidence/ui_window_host'))
FILE_COUNT = 2608
SHA = re.compile(r'[0-9a-f]{64}\Z')


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load_original():
    require(OUT == ROOT / 'evidence/storage_cleanup/20261009_economic_build_retries', 'Wrong cleanup output root')
    require(digest(PREPARE) == PREPARE_SHA and digest(HELPER) == HELPER_SHA,
            'Original reviewed preparation script/helper changed before import')
    spec = importlib.util.spec_from_file_location('economic_retirement_original_pinned', PREPARE)
    require(spec is not None and spec.loader is not None, 'Cannot load the pinned preparation module')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    require(module.ROOT == ROOT and module.OUT == OUT and tuple(module.IDS) == IDS and tuple(module.DIRS) == DIRS and
            Path(module.p.__file__).resolve() == HELPER, 'Original module scope/helper identity differs')
    return module


def verify_protected(rows, *, root, entries, hash_file, excluded):
    """One pass; trust only path/stat supplied by the pinned guarded iterator.

    Production entries come directly from original project_files(), which checks
    directory resolution/ancestors and each regular, non-reparse leaf. No second
    path.resolve()/lstat walk is performed for the same protected file. Hashes
    are deduplicated by file identity within THIS invocation only. A second call
    always reads and hashes every distinct identity again.
    """
    require(isinstance(rows, list), 'Protected ledger must be a list')
    expected = {}
    for row in rows:
        require(isinstance(row, dict) and isinstance(row.get('path'), str), 'Malformed protected row')
        relative = Path(row['path'])
        require(not relative.is_absolute() and not relative.drive and relative.parts and
                not any(part in ('.', '..') for part in relative.parts), 'Protected ledger path escaped its project')
        path = root / relative
        require(path.is_relative_to(root) and path != root and not any(path.is_relative_to(item) for item in excluded),
                'Protected ledger includes an excluded or outside path')
        require(row['path'] == str(relative) and row['path'] not in expected and
                isinstance(row.get('sha256'), str) and SHA.fullmatch(row['sha256']) is not None,
                'Protected ledger has duplicate/noncanonical paths or malformed SHA')
        require(all(type(row.get(field)) is int and row[field] >= 0 for field in ('device', 'file_id', 'bytes', 'mtime_ns')),
                'Protected ledger identity is malformed')
        expected[row['path']] = row
    visited, hashes = set(), {}
    for path, info in entries:
        require(path.is_absolute() and path.is_relative_to(root) and path != root and
                not any(part == '..' for part in path.parts) and not any(path.is_relative_to(item) for item in excluded),
                'Protected enumeration escaped its project or entered an excluded target')
        relative = str(path.relative_to(root))
        require(relative in expected and relative not in visited, 'Surviving project membership added or duplicated a file')
        require(stat.S_ISREG(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & 0x400,
                'Protected enumeration supplied a non-regular or reparse leaf')
        row = expected[relative]
        identity = int(info.st_dev), int(info.st_ino), info.st_size, info.st_mtime_ns
        require(identity == (row['device'], row['file_id'], row['bytes'], row['mtime_ns']),
                'Protected file identity changed: ' + str(path))
        if identity not in hashes:
            hashes[identity] = hash_file(path)
        require(hashes[identity] == row['sha256'], 'Protected file bytes changed: ' + str(path))
        visited.add(relative)
    require(visited == expected.keys(), 'Surviving project membership omitted a protected file')
    return {'files': len(visited), 'unique_file_identities_hashed': len(hashes), 'enumeration_passes': 1,
            'hashes_reused_from_another_phase': False}


def apply(plan_sha, code_sha):
    require(SHA.fullmatch(plan_sha) is not None and SHA.fullmatch(code_sha) is not None and
            digest(Path(__file__)) == code_sha, 'Missing or changed reviewed apply code SHA')
    original = load_original()
    p = original.p
    p.no_active_host()
    require(not (OUT / 'cleanup.json').exists(), 'This cleanup already started; do not replay it')
    p.boundary(OUT)
    require(digest(OUT / 'plan.json') == plan_sha and digest(OUT / 'inventory.json') == INVENTORY_SHA,
            'Unreviewed/mutated original plan or inventory')
    plan = original.read(OUT / 'plan.json')
    require(plan['status'] == 'SEALED_EXACT_FOUR_UNEXECUTED_HOSTS' and plan['root'] == str(ROOT) and
            plan['exact_host_ids'] == list(IDS) and plan['files'] == FILE_COUNT and
            plan['inventory_sha256'] == INVENTORY_SHA and plan['script_sha256'] == PREPARE_SHA and
            plan['helper_sha256'] == HELPER_SHA, 'Sealed original scope/code contract changed')
    require(set(plan['artifacts']) == {'diagnostics.json.gz', 'retired-files.json.gz', 'retired-directories.json.gz',
            'references.json.gz', 'protected-final.json.gz', 'references-final.json.gz'}, 'Original artifact set changed')
    for name, sha in plan['artifacts'].items():
        require(Path(name).name == name and SHA.fullmatch(sha) is not None and digest(OUT / name) == sha,
                'Original protection or diagnostic archive changed')
    # Preserve the original full target membership, boundary, identity, link,
    # SHA, diagnostic recovery and exclusive-use checks without substituting
    # any fast path for the 2,608 potential deletions.
    report, rows = original.verify_inventory()
    require(len(rows) == report['file_count'] == FILE_COUNT and
            {row['absolute_path'] for row in report['targets']} == {str(path) for path in DIRS},
            'Target file count or exact eight-directory inventory changed')
    references = original.reference_audit()
    original.target_processes_clear()
    guards = original.gzread(OUT / 'protected-final.json.gz')
    require(len(guards) == plan['protected_files'], 'Sealed protected-file count changed')
    replacement = plan.get('replacement_host')
    require(isinstance(replacement, str) and p.RUN.fullmatch(replacement) and replacement not in IDS, 'Wrong replacement Host')
    replacement_report = p.boundary(ROOT / 'evidence/ui_window_host' / replacement / 'build_result.json')
    require(digest(replacement_report) == plan['replacement_report_sha256'], 'Replacement Host build report changed')
    replacement_value = original.read(replacement_report)
    replacement_exe = p.boundary(Path(replacement_value['executable']['path']))
    require(replacement_value.get('build_id') == replacement and replacement_value.get('status') == 'UI_WINDOW_HOST_CANDIDATE_BUILT' and
            replacement_value.get('source_inputs_unchanged') is True and
            replacement_exe.is_relative_to(ROOT / 'Build/UiWindowHost' / replacement) and
            digest(replacement_exe) == replacement_value['executable']['sha256'], 'Successful current replacement was not preserved')
    protected_paths = {row['path'] for row in guards}
    must_preserve = [row['path'] for row in references['runtime_hosts']] + [row['path'] for row in references['native_saves']]
    must_preserve += [str(replacement_report.relative_to(ROOT)), str(replacement_exe.relative_to(ROOT))]
    require(all(name in protected_paths for name in must_preserve) and references['manual_native_save_count'] >= 8,
            'Current runtimes, user saves or replacement are absent from the sealed protection set')
    before = verify_protected(guards, root=ROOT, entries=original.project_files(), hash_file=p.digest, excluded=(*DIRS, OUT))
    require(digest(Path(__file__)) == code_sha and digest(PREPARE) == PREPARE_SHA and digest(HELPER) == HELPER_SHA and
            digest(OUT / 'plan.json') == plan_sha and digest(OUT / 'inventory.json') == INVENTORY_SHA,
            'Reviewed code or plan changed during preflight')
    status = {'status': 'APPLY_STARTED_DO_NOT_REPLAY', 'plan_sha256': plan_sha,
              'apply_entrypoint': str(Path(__file__).relative_to(ROOT)), 'apply_entrypoint_sha256': code_sha,
              'original_prepare_sha256': PREPARE_SHA, 'original_helper_sha256': HELPER_SHA, 'original_inventory_sha256': INVENTORY_SHA,
              'protected_verification_before': before, 'protected_hashes_verified_before': True,
              'removed_files': 0, 'removed_logical_bytes': 0, 'volume_free_bytes_before': shutil.disk_usage(ROOT).free,
              'source_tools_tests_current_builds_runtime_and_saves_deleted': False,
              'manual_native_saves_protected': references['manual_native_save_count'], 'replacement_host': replacement, 'errors': []}
    original.write_new(OUT / 'cleanup.json', status)
    try:
        p.no_active_host()
        for row in rows:
            path = p.boundary(ROOT / row['path']); info = p.regular(path)
            require(original.inside_targets(path) and original.identity(info)[:4] ==
                    (row['device'], row['file_id'], row['bytes'], row['mtime_ns']) and
                    1 <= info.st_nlink <= row['links'] and p.digest(path) == row['sha256'],
                    'Target changed immediately before unlink')
            original.unused(path)
            p.unlink_without_attribute_changes(path)
            require(not path.exists(), 'Retired file remains')
            status['removed_files'] += 1
            status['removed_logical_bytes'] += row['bytes']
        folders = original.gzread(OUT / 'retired-directories.json.gz')
        for row in sorted(folders, key=lambda item: len(Path(item['path']).parts), reverse=True):
            path = p.boundary(ROOT / row['path']); info = path.lstat()
            require(original.inside_targets(path) and (int(info.st_dev), int(info.st_ino)) ==
                    (row['device'], row['file_id']), 'Retired directory identity changed')
            path.rmdir()
        # New enumeration and new local hash dictionary; no preflight hashes
        # cross the mutation boundary, even when file ID/mtime stayed the same.
        after = verify_protected(guards, root=ROOT, entries=original.project_files(), hash_file=p.digest, excluded=(*DIRS, OUT))
        require(status['removed_files'] == FILE_COUNT and not any(path.exists() for path in DIRS), 'Cleanup membership/count differs')
        require(digest(Path(__file__)) == code_sha, 'Alternate apply source changed during operation')
        status.update(status='PASS_EXACT_FOUR_UNEXECUTED_HOST_RETIREMENT', protected_hashes_verified_after=True,
                      protected_verification_after=after)
    except BaseException as exc:
        status.update(status='PARTIAL_FAILURE_DO_NOT_REPLAY', errors=[str(exc)])
        raise
    finally:
        status['volume_free_bytes_after'] = shutil.disk_usage(ROOT).free
        (OUT / 'cleanup.json').write_text(json.dumps(status, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
        print(json.dumps(status, ensure_ascii=False), flush=True)


def self_test():
    """No filesystem enumeration, native call, receipt or deletion is made."""
    root = ROOT
    names = ('contract/a.txt', 'contract/a-link.txt', 'contract/b.txt')
    contents = dict(zip(names, (b'alpha', b'alpha', b'beta')))
    infos, rows = {}, []
    for index, name in enumerate(names):
        info = SimpleNamespace(st_dev=7, st_ino=11 if index < 2 else 12, st_size=len(contents[name]),
                               st_mtime_ns=12345, st_mode=stat.S_IFREG, st_file_attributes=0)
        infos[name] = info
        rows.append({'path': str(Path(name)), 'device': 7, 'file_id': info.st_ino, 'bytes': info.st_size,
                     'mtime_ns': info.st_mtime_ns, 'sha256': hashlib.sha256(contents[name]).hexdigest()})
    calls = []
    def hashed(path):
        name = path.relative_to(root).as_posix(); calls.append(name)
        return hashlib.sha256(contents[name]).hexdigest()
    class OnePass:
        def __init__(self, values):
            self.values, self.used = values, False
        def __iter__(self):
            require(not self.used, 'Contract enumerator was consumed twice')
            self.used = True
            return iter(self.values)
    def entries():
        return [(root / name, infos[name]) for name in names]
    for _ in range(2):
        result = verify_protected(rows, root=root, entries=OnePass(entries()), hash_file=hashed, excluded=())
        require(result['files'] == 3 and result['unique_file_identities_hashed'] == 2, 'Hardlink/single-pass contract differs')
    require(calls == ['contract/a.txt', 'contract/b.txt'] * 2, 'A hash was reused across verification phases')
    rejected = 0
    def bad(test_rows, test_entries, *, excluded=()):
        nonlocal rejected
        try:
            verify_protected(test_rows, root=root, entries=OnePass(test_entries), hash_file=hashed, excluded=excluded)
        except RuntimeError:
            rejected += 1
        else:
            raise RuntimeError('Malformed protection input was accepted')
    bad(rows, entries()[:-1])
    bad(rows, entries() + [entries()[0]])
    bad(rows + [rows[0]], entries())
    bad([{**row, 'mtime_ns': 3} if index == 0 else row for index, row in enumerate(rows)], entries())
    bad([{**row, 'file_id': 99} if index == 0 else row for index, row in enumerate(rows)], entries())
    bad([{**row, 'sha256': '0' * 64} if index == 1 else row for index, row in enumerate(rows)], entries())
    bad(rows, entries(), excluded=(root / 'contract',))
    bad([{**rows[0], 'path': '../outside.txt'}], [])
    bad(rows, [(root.parent / 'outside.txt', infos[names[0]]), *entries()[1:]])
    invalid = SimpleNamespace(**vars(infos[names[0]])); invalid.st_file_attributes = 0x400
    bad(rows, [(root / names[0], invalid), *entries()[1:]])
    invalid = SimpleNamespace(**vars(infos[names[0]])); invalid.st_mode = stat.S_IFDIR
    bad(rows, [(root / names[0], invalid), *entries()[1:]])
    contents[names[2]] = b'changed'
    bad(rows, entries())
    require(rejected == 12, 'Protection rejection checks were omitted')
    print(json.dumps({'status': 'PASS_SINGLE_PASS_PROTECTION_CONTRACT_ONLY', 'positive_passes': 2,
          'negative_cases': rejected, 'cross_phase_hash_reuse': False, 'project_scan_executed': False,
          'deletion_executed': False, 'code_sha256': digest(Path(__file__))}, sort_keys=True))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--apply-plan-sha256')
    parser.add_argument('--apply-code-sha256')
    args = parser.parse_args()
    if args.self_test:
        if args.apply_plan_sha256 or args.apply_code_sha256:
            parser.error('--self-test cannot be combined with application arguments')
        self_test()
    elif args.apply_plan_sha256 and args.apply_code_sha256:
        apply(args.apply_plan_sha256, args.apply_code_sha256)
    else:
        parser.error('Use --self-test, or provide both reviewed --apply-plan-sha256 and --apply-code-sha256')
