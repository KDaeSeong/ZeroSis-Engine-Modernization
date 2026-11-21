"""One-use, exact-scope retirement for the user's 2026-10-09 storage request."""
from __future__ import annotations
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import prune_superseded_runtime_artifacts as p

RUNS = ('20261007T191737Z_cb79c4f6eb96', '20261003T151838Z_d5129b807a9a')
HOST = '20261007T190026Z_e8927b74abf4'
DIRS = tuple(ROOT / group / run for run in RUNS
             for group in ('Build/InteractiveGameRuntime', 'evidence/interactive_game')) + (
    ROOT / 'Build/UiWindowHost' / HOST, ROOT / 'evidence/ui_window_host' / HOST)
CACHE = ROOT / 'Build/RuntimeInputCache'


def gzwrite(path, value):
    with gzip.open(path, 'wt', encoding='utf8') as f:
        json.dump(value, f, ensure_ascii=False, separators=(',', ':'))


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def refs(node):
    if isinstance(node, list):
        for item in node:
            yield from refs(item)
    elif isinstance(node, dict):
        if isinstance(node.get('cache'), str):
            yield str(Path(node['cache']))
        for item in node.values():
            if isinstance(item, (dict, list)):
                yield from refs(item)


def cache_refs():
    # Every surviving request, including native component/fixture requests.
    found = set()
    for q in (ROOT / 'evidence').glob('*/*/request.json'):
        if any(q.is_relative_to(d) for d in DIRS):
            continue
        found.update(refs(read(q)))
    return found


def cache_allowed(path):
    path = p.boundary(path)
    rel = path.relative_to(CACHE)
    p.require(len(rel.parts) == 2 and re.fullmatch('[0-9a-f]{2}', rel.parts[0]) and
              re.fullmatch('[0-9a-f]{64}', rel.parts[1]) and rel.parts[1].startswith(rel.parts[0]),
              'Not an exact content-addressed cache entry')
    s = p.regular(path)
    p.require(s.st_nlink == 1, 'Cache entry has a live hardlink')
    return s


def row(path, s, hashed):
    key = (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)
    sha = hashed.setdefault(key, None)
    if sha is None:
        sha = hashed[key] = p.digest(path)
    return dict(path=str(path.relative_to(ROOT)), bytes=s.st_size, sha256=sha,
                device=s.st_dev, file_id=s.st_ino, mtime_ns=s.st_mtime_ns,
                links=s.st_nlink, stored=p.stored(path))


def project_files():
    # The safety helper deliberately rejects the project root as a target.
    for child in ROOT.iterdir():
        p.boundary(child)
        if child.is_dir():
            yield from p.inventory(child)
        else:
            yield child, p.regular(child)


def diagnostic(path):
    rel=path.relative_to(ROOT)
    if rel.parts[0]=='evidence' and len(rel.parts)==4:
        return path.suffix.lower() in ('.json','.log','.txt','.py')
    if HOST in path.parts and path.name=='UiInputDispatch.h':
        return True
    if RUNS[0] not in path.parts:
        return False
    if path.name=='rules.db':
        return True
    if re.fullmatch(r'play-declare-war-(before|after)-[012]-state\.txt',path.name):
        return True
    if path.name=='play-final-state.txt':
        return True
    if re.fullmatch(r'play-scene-(32|35|37)\.(json|pick)',path.name):
        return True
    return path.parent.name in ('play-ui-30','play-ui-33','play-ui-35') and path.name in (
        'scene_manifest.json','scene.packet','preparation_inputs.json','driver_record.json')


def preview():
    p.no_active_host()
    p.require(not (OUT / 'plan.json').exists(), 'Plan already exists')
    manual = set(re.findall(p.RUN, (ROOT / 'tools/Start-Engine.ps1').read_text(encoding='utf8')))
    p.require(not manual.intersection(RUNS), 'Retired run is a manual runtime')
    p.require(read(ROOT/'evidence/interactive_game'/RUNS[0]/'result.json')['status'].endswith('FAILED'),
              'Expected the original failed range runner result')
    p.require(read(ROOT/'evidence/interactive_game'/RUNS[1]/'request.json')['smoke'] is True,
              'Old tree run is not a disposable smoke run')
    for d in DIRS:
        p.legal_target(d)
    referenced = cache_refs()
    hashed, retired, guards, identities, diagnostics = {}, [], {}, {}, []
    cache_rows = []
    for path in sorted(CACHE.glob('*/*')):
        if not re.fullmatch('[0-9a-f]{64}', path.name) or not path.is_file():
            continue
        if path.stat().st_nlink != 1 or str(path) in referenced:
            continue
        s = cache_allowed(path)
        r = row(path, s, hashed)
        p.require(r['sha256'] == path.name, 'Cache filename/content mismatch')
        cache_rows.append(r)
    retired.extend(cache_rows)
    for d in DIRS:
        for path, s in p.inventory(d):
            r = row(path, s, hashed)
            retired.append(r)
            # Keep diagnostic texts, control snapshots, original FAILED/PASS
            # reports and validator sources; do not archive binary payloads.
            if diagnostic(path):
                raw = path.read_bytes()
                diagnostics.append({'path':r['path'], 'sha256':r['sha256'], 'bytes':r['bytes'],
                                    'base64':base64.b64encode(raw).decode('ascii')})
    gzwrite(OUT/'retired-diagnostics.json.gz', diagnostics)
    p.require((OUT/'retired-diagnostics.json.gz').stat().st_size < 16*1024**2,
              'Diagnostic archive unexpectedly large')
    with gzip.open(OUT/'retired-diagnostics.json.gz','rt',encoding='utf8') as f:
        recovered=json.load(f)
    for r in recovered:
        raw=base64.b64decode(r['base64'],validate=True)
        p.require(len(raw)==r['bytes'] and hashlib.sha256(raw).hexdigest()==r['sha256'],
                  'Diagnostic archive does not recover exact bytes')
    retired_names = {r['path'] for r in retired}
    for path, s in project_files():
        if path.is_relative_to(OUT) or str(path.relative_to(ROOT)) in retired_names:
            continue
        key=(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns)
        if key not in hashed:
            hashed[key]=p.digest(path)
        guards[str(path)] = hashed[key]
    for r in retired:
        key = (r['device'], r['file_id'])
        x = identities.setdefault(key, {'links':r['links'], 'count':0, 'stored':r['stored']})
        p.require(x['links'] == r['links'], 'Link count changed during preview')
        x['count'] += 1
    gzwrite(OUT/'retired-files.json.gz', retired)
    gzwrite(OUT/'protected.json.gz', guards)
    report = dict(status='PREVIEW_ONLY', root=str(ROOT), script_sha256=p.digest(Path(__file__)),
                  helper_sha256=p.digest(ROOT/'tools/prune_superseded_runtime_artifacts.py'),
                  directories=[str(d.relative_to(ROOT)) for d in DIRS], files=len(retired),
                  cache_files=len(cache_rows), cache_bytes=sum(r['bytes'] for r in cache_rows),
                  logical_bytes=sum(r['bytes'] for r in retired), protected_files=len(guards),
                  estimated_reclaimable_bytes=sum(x['stored'] for x in identities.values()
                                                   if x['count'] == x['links']),
                  artifacts={name:p.digest(OUT/name) for name in
                             ('retired-diagnostics.json.gz','retired-files.json.gz','protected.json.gz')})
    (OUT/'plan.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({**report,'plan_sha256':p.digest(OUT/'plan.json')},ensure_ascii=False),flush=True)


def verify_guards(guards):
    identities, parents = {}, set()
    for name, expected in guards.items():
        path = Path(name)
        p.require(path.is_absolute() and path.is_relative_to(ROOT) and '..' not in path.parts,
                  'Protected path outside project')
        if path.parent not in parents:
            if path.parent != ROOT:
                p.boundary(path.parent)
            parents.add(path.parent)
        s = p.regular(path)
        key = (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns)
        if key in identities:
            p.require(identities[key][1] == expected, 'Hardlink hashes disagree')
        else:
            identities[key] = (path,expected)
    def check(item):
        path,expected=item
        p.require(p.digest(path) == expected, 'Protected content changed: '+str(path))
    # Bound parallel reads instead of serially rereading every small file.
    with ThreadPoolExecutor(max_workers=8) as pool:
        for _ in pool.map(check,identities.values(),buffersize=256):
            pass


def apply(expected_sha):
    plan_path = OUT/'plan.json'
    p.require(p.digest(plan_path) == expected_sha, 'Changed/unreviewed plan')
    p.require(not (OUT/'cleanup.json').exists(), 'Plan was already started; do not replay')
    plan = read(plan_path)
    p.require(plan['root'] == str(ROOT) and plan['status'] == 'PREVIEW_ONLY', 'Wrong plan/root')
    p.require(plan['script_sha256'] == p.digest(Path(__file__)) and
              plan['helper_sha256'] == p.digest(ROOT/'tools/prune_superseded_runtime_artifacts.py'),
              'Reviewed implementation changed')
    for name, sha in plan['artifacts'].items():
        p.require(p.digest(OUT/name) == sha, 'Sealed record changed')
    with gzip.open(OUT/'retired-files.json.gz','rt',encoding='utf8') as f: retired=json.load(f)
    with gzip.open(OUT/'protected.json.gz','rt',encoding='utf8') as f: guards=json.load(f)
    p.require(set(plan['directories']) == {str(d.relative_to(ROOT)) for d in DIRS}, 'Target changed')
    p.no_active_host()
    verify_guards(guards)
    current_refs = cache_refs()
    for r in retired:
        path = p.boundary(ROOT/r['path']); s = p.regular(path)
        if path.is_relative_to(CACHE):
            cache_allowed(path)
            p.require(str(path) not in current_refs and p.digest(path)==path.name, 'Cache now referenced')
        else:
            p.require(any(path.is_relative_to(d) for d in DIRS), 'File outside exact retired set')
        p.require((s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns)==
                  (r['device'],r['file_id'],r['bytes'],r['mtime_ns']), 'Retired identity changed')
        p.require(p.digest(path)==r['sha256'], 'Retired bytes changed')
    status=dict(status='REMOVING',plan_sha256=expected_sha,removed_files=0,removed_logical_bytes=0,
                protected_hashes_verified_before=True,volume_free_bytes_before=shutil.disk_usage(ROOT).free,
                errors=[])
    def checkpoint():
        (OUT/'cleanup.json').write_text(json.dumps(status,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    checkpoint()
    try:
        p.no_active_host()
        for r in retired:
            path=p.boundary(ROOT/r['path']); s=p.regular(path)
            p.require((s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns)==
                      (r['device'],r['file_id'],r['bytes'],r['mtime_ns']), 'Retired identity changed before unlink')
            p.require(p.digest(path)==r['sha256'], 'Retired content changed before unlink')
            if path.is_relative_to(CACHE): cache_allowed(path)
            p.unlink_without_attribute_changes(path)
            p.require(not path.exists(), 'Retired file remains')
            status['removed_files']+=1; status['removed_logical_bytes']+=r['bytes']
            if status['removed_files']%1000==0: checkpoint()
        for target in DIRS:
            for folder, dirs, files in os.walk(target,topdown=False,followlinks=False):
                p.require(not files, 'Unplanned file in retired directory')
                p.boundary(Path(folder)).rmdir()
        verify_guards(guards)
        p.require(status['removed_files']==plan['files'],'Removed count differs')
        status.update(status='PASS_EXACT_RETIREMENT_AND_ORPHAN_CACHE_CLEANUP',
                      protected_hashes_verified_after=True)
    except BaseException as exc:
        status.update(status='PARTIAL_FAILURE',errors=[str(exc)])
        raise
    finally:
        status['volume_free_bytes_after']=shutil.disk_usage(ROOT).free
        checkpoint()
        print(json.dumps(status,ensure_ascii=False),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--apply-plan-sha256')
    args=parser.parse_args()
    if args.apply_plan_sha256: apply(args.apply_plan_sha256)
    else: preview()
