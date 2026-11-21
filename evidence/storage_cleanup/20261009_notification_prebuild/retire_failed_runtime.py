"""One explicit failed smoke runtime; fresh plan plus hash-pinned one-shot apply.

Only the exact Build runtime below can be removed. Original failure evidence,
manual games/saves, completed inputs and current development sources stay put.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import time
import uuid

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import prune_superseded_runtime_artifacts as safety
import plan_failed_ui_host_cleanup as helper

SPEC = importlib.util.spec_from_file_location('scoped_old_helpers', ROOT / 'evidence/storage_cleanup/20261009_failed_economic_runs/prepare.py')
links = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(links)
RUN = '20261009T125902Z_fd5dbd6a907a'
HOST = '20261009T123034Z_dce2558fb5c5'
MANUAL = '20261009T132430Z_a0a5dd8fd007'
KEEPS = ('20261009T123717Z_504abb2ccaf9', MANUAL, '20261009T130410Z_7c35d16e64b9', '20261009T131452Z_16632c1f4d4a')
TARGET = ROOT / 'Build/InteractiveGameRuntime' / RUN
FAILURE = ROOT / 'evidence/interactive_game' / RUN
BASELINE = ROOT / 'evidence/storage_cleanup/20261009_failed_economic_runs/post_cleanup_validation.json'
require, read, identity = safety.require, helper.read, helper.identity


def pair(row):
    return row['identity']['device'], row['identity']['file_id']


def record(path, cache):
    path, info = helper.checked_file(path)
    before = identity(info)
    key = tuple(before.values())
    if key not in cache:
        cache[key] = safety.digest(path)
    require(identity(helper.checked_file(path)[1]) == before, 'Changed while hashing: ' + str(path))
    return dict(path=str(path), identity=before, sha256=cache[key])


def contract():
    safety.no_active_host()
    target = safety.boundary(TARGET)
    require(target.parent == ROOT / 'Build/InteractiveGameRuntime' and target.name == RUN, 'Wrong target boundary')
    result, request = read(FAILURE / 'result.json'), read(FAILURE / 'request.json')
    require(result.get('run_id') == RUN and result.get('status', '').endswith('_FAILED') and
            result.get('returncode') == 1 and result.get('timed_out') is False, 'Target lacks exact terminal failure')
    require(request.get('run_id') == RUN and request.get('smoke') is True and
            request.get('cwd') == str(TARGET) and not request.get('resume_save') and not request.get('resume'), 'Target is not an isolated fresh smoke')
    ref = result['request']
    require(Path(ref['path']) == FAILURE / 'request.json' and safety.digest(ref['path']) == ref['sha256'], 'Failed request differs')
    require(RUN not in (ROOT / 'tools/Start-Engine.ps1').read_text(encoding='utf-8-sig'), 'Failed target became a manual runtime')


def requests():
    result = []
    for path in sorted((ROOT / 'evidence/interactive_game').glob('*/request.json')):
        if path.parent.name == RUN:
            continue
        value = read(path)
        require(RUN.casefold() not in json.dumps(value).casefold(), 'Surviving request refers to target: ' + str(path))
        result.append(record(path, {}))
    require(result, 'No surviving requests')
    return result


def inventory():
    files, directories, cache = [], [], {}
    for path, info, is_dir in links.walk_owned(TARGET):
        if is_dir:
            directories.append(dict(path=str(path), identity=identity(info)))
        else:
            row = record(path, cache)
            row['stored_bytes'] = safety.stored(path)
            files.append(row)
    return dict(files=sorted(files, key=lambda r:r['path']), directories=sorted(directories, key=lambda r:r['path']))


def make_plan():
    contract()
    candidates = inventory()
    protected, cache, aliases = {}, {}, []
    def protect(path, role, expected=None):
        path = Path(path)
        require(not path.is_relative_to(TARGET), 'Protected path is inside candidate')
        require(not any(path.is_relative_to(ROOT / name) for name in ('Source', 'tools')), 'Live source is not an immutable protection input')
        row = record(path, cache)
        require(expected is None or row['sha256'] == expected.lower(), 'Sealed protected SHA differs: ' + str(path))
        old = protected.setdefault(str(path), {**row, 'roles':[]})
        require(old['identity'] == row['identity'] and old['sha256'] == row['sha256'], 'Protection changed during collection')
        if role not in old['roles']:
            old['roles'].append(role)
    for row in candidates['files']:
        path = Path(row['path'])
        names = links.hardlink_names(path)
        require(len(names) == row['identity']['links'], 'Candidate hardlink count differs')
        require(all(not any(name.is_relative_to(ROOT / folder) for folder in ('Source', 'tools')) and
                    name.suffix.lower() != '.etl' for name in names), 'Candidate aliases current source/tools/CPU trace')
        aliases.append(dict(path=str(path), names=list(map(str,names))))
        for name in names:
            if not name.is_relative_to(TARGET):
                protect(name, 'surviving_hardlink', row['sha256'])
    for path, _ in safety.inventory(FAILURE):
        protect(path, 'retained_failure_diagnostics')
    request_rows = requests()
    for row in request_rows:
        protect(row['path'], 'current_request', row['sha256'])
    host = read(ROOT / 'evidence/ui_window_host' / HOST / 'build_result.json')
    require(host['status'] == 'UI_WINDOW_HOST_CANDIDATE_BUILT' and host['source_inputs_unchanged'] is True, 'Current Host is not sealed')
    protect(ROOT / 'evidence/ui_window_host' / HOST / 'build_result.json', 'required_host_report')
    protect(host['executable']['path'], 'required_host_executable', host['executable']['sha256'])
    for path, _ in safety.inventory(ROOT / 'Build/UiWindowHost' / HOST / 'frozen'):
        protect(path, 'required_frozen_source')
    for run in KEEPS:
        evidence = ROOT / 'evidence/interactive_game' / run
        runtime = ROOT / 'Build/InteractiveGameRuntime' / run
        request = read(evidence / 'request.json')
        protect(evidence / 'request.json', 'required_runtime_request')
        for row in request['runtime_inputs']:
            require(Path(row['path']).is_relative_to(runtime), 'Sealed runtime input escaped runtime')
            protect(row['path'], 'required_runtime_input', row['sha256'])
        for field in ('interactive_ui_support','interactive_ui_support_inventory','provenance','launcher_control_metadata'):
            for path, sha in safety.refs(request.get(field)):
                if not any(Path(path).is_relative_to(ROOT / folder) for folder in ('Source','tools')):
                    protect(path, 'required_sealed_support', sha)
        if run in KEEPS[2:]:
            result = read(evidence / 'result.json')
            require(result['returncode'] == 0 and result['status'].endswith('_PASS') and not result['failures'], 'Required native run not PASS')
            for path in [evidence / 'result.json', *evidence.glob('action_info_panel_validation*.json')]:
                protect(path, 'accepted_native_evidence')
        if run == MANUAL:
            for directory in (runtime, evidence):
                for path, _ in safety.inventory(directory):
                    protect(path, 'closed_manual_runtime_and_session')
    for launch in (ROOT / 'evidence/manual_play').glob('*/launch.json'):
        value = read(launch)
        if value.get('runtime') == str(ROOT / 'Build/InteractiveGameRuntime' / MANUAL):
            require(value.get('status') == 'FAILED', 'Manual launch is not terminal failed')
            for path, _ in safety.inventory(launch.parent):
                protect(path, 'manual_failure_logs')
    protect(BASELINE, 'user_save_baseline')
    saves = read(BASELINE)['saves']
    require(len(saves) == 8, 'Eight original user saves required')
    for row in saves:
        protect(row['path'], 'existing_user_save', row['sha256'])
    for path in (ROOT / 'Play/EarlyAccess').glob('*.cmd'):
        protect(path, 'manual_launcher')
    current_inventory = inventory()
    changes = []
    for group in ('files','directories'):
        before = {r['path']:r for r in candidates[group]}
        after = {r['path']:r for r in current_inventory[group]}
        changes.extend(dict(path=path,before=before.get(path),after=after.get(path))
                       for path in before.keys() | after.keys() if before.get(path) != after.get(path))
    require(not changes, 'Target changed while planning: ' + json.dumps(changes[:2]))
    current_requests = requests()
    require(current_requests == request_rows, 'Requests changed while planning: ' + json.dumps(
            [r for r in current_requests if r not in request_rows][:2]))
    safety.no_active_host()
    output = OUT / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_') + uuid.uuid4().hex[:12])
    output.mkdir(parents=True, exist_ok=False)
    ledgers = {name:helper.write_new(output / (name+'.json.gz'),value,True) for name,value in
               (('target',candidates),('protected',list(protected.values())),('aliases',aliases),('requests',request_rows))}
    helpers = [Path(__file__),Path(helper.__file__),Path(safety.__file__),Path(SPEC.origin)]
    exclusive = {pair(r):r['stored_bytes'] for r in candidates['files'] if r['identity']['links'] == 1}
    plan = dict(schema='ZEROSIS_ONE_FAILED_RUNTIME_PLAN_V1',status='PREVIEW_ONLY',root=str(ROOT),target=str(TARGET),
                run_id=RUN,ledgers=ledgers,helpers=[dict(path=str(p),sha256=safety.digest(p)) for p in helpers],
                files=len(candidates['files']),directories=len(candidates['directories']),
                logical_bytes=sum(r['identity']['bytes'] for r in candidates['files']),
                exclusive_allocation_bytes=sum(exclusive.values()),protected_files=len(protected),
                protected_roles=dict(Counter(role for r in protected.values() for role in r['roles'])),
                retained_failure_evidence=str(FAILURE),live_source_not_hash_frozen=True,
                source_tools_cpu_trace_aliases_absent=True,created_utc=datetime.now(timezone.utc).isoformat())
    result=helper.write_new(output / 'plan.json',plan)
    print(json.dumps(dict(plan=result,files=plan['files'],logical_bytes=plan['logical_bytes'],exclusive_allocation_bytes=plan['exclusive_allocation_bytes'],protected_files=len(protected)),ensure_ascii=False),flush=True)


def verify_protected(rows, removed):
    cache={}
    for row in rows:
        actual=record(row['path'],cache)
        expected=dict(row['identity'])
        expected['links']-=removed.get(pair(row),0)
        require(actual['identity']==expected and actual['sha256']==row['sha256'], 'Protected identity/content changed: '+row['path'])


def apply(plan_path, expected_sha):
    contract()
    plan_path=safety.boundary(plan_path)
    require(plan_path.is_relative_to(OUT) and plan_path.name=='plan.json' and safety.digest(plan_path)==expected_sha,'Wrong fresh plan/hash')
    plan=read(plan_path)
    require(plan['status']=='PREVIEW_ONLY' and plan['schema']=='ZEROSIS_ONE_FAILED_RUNTIME_PLAN_V1' and
            plan['root']==str(ROOT) and plan['target']==str(TARGET) and plan['run_id']==RUN,'Wrong plan scope')
    for ref in plan['helpers']:
        require(safety.digest(ref['path'])==ref['sha256'],'Cleanup helper changed')
    values={}
    for name,ref in plan['ledgers'].items():
        require(Path(ref['path']).parent==plan_path.parent and safety.digest(ref['path'])==ref['sha256'],'Ledger differs')
        with gzip.open(ref['path'],'rt',encoding='utf-8') as stream: values[name]=json.load(stream)
    require(requests()==values['requests'] and inventory()==values['target'],'Stale target/request inventory; create a fresh plan')
    verify_protected(values['protected'],{})
    alias_map={r['path']:r['names'] for r in values['aliases']}
    for path,names in alias_map.items():
        require(list(map(str,links.hardlink_names(Path(path))))==names,'Hardlink aliases changed')
    safety.no_active_host()
    started=plan_path.parent/'apply.started'
    with started.open('x',encoding='utf-8') as stream:
        stream.write(json.dumps(dict(plan_sha256=expected_sha,started_utc=datetime.now(timezone.utc).isoformat()))+'\n')
        stream.flush();os.fsync(stream.fileno())
    report=dict(status='APPLYING',plan_sha256=expected_sha,removed_files=0,removed_logical_bytes=0,
                exclusive_allocation_reclaimed=0,protected_hashes_verified_before=True,protected_hashes_verified_after=False,
                retained_failure_evidence=str(FAILURE),retired_input_scope=str(TARGET),errors=[],
                volume_free_before=shutil.disk_usage(ROOT).free)
    removed, removed_paths={},set()
    try:
        with (plan_path.parent/'removed-files.jsonl').open('x',encoding='utf-8') as journal:
            next_guard=0.0
            for row in values['target']['files']:
                if time.monotonic()>=next_guard:
                    safety.no_active_host();next_guard=time.monotonic()+5
                path=safety.boundary(Path(row['path']))
                require(path.is_relative_to(TARGET),'Immediate file boundary differs')
                expected=dict(row['identity']);expected['links']-=removed.get(pair(row),0)
                actual=record(path,{})
                require(actual['identity']==expected and actual['sha256']==row['sha256'] and safety.stored(path)==row['stored_bytes'],'Immediate deletion identity/hash/allocation differs')
                require(set(map(str,links.hardlink_names(path)))==set(alias_map[str(path)])-removed_paths,'Immediate aliases differ')
                safety.unlink_without_attribute_changes(path)
                require(not path.exists(),'Deleted alias remains')
                removed[pair(row)]=removed.get(pair(row),0)+1;removed_paths.add(str(path))
                reclaimed=row['stored_bytes'] if expected['links']==1 else 0
                report['removed_files']+=1;report['removed_logical_bytes']+=row['identity']['bytes']
                report['exclusive_allocation_reclaimed']+=reclaimed
                journal.write(json.dumps(dict(path=str(path),identity=row['identity'],sha256=row['sha256'],exclusive_allocation_reclaimed=reclaimed),ensure_ascii=False)+'\n')
                journal.flush();os.fsync(journal.fileno())
            for row in sorted(values['target']['directories'],key=lambda r:len(Path(r['path']).parts),reverse=True):
                path=safety.boundary(Path(row['path']));info=path.lstat()
                require(path==TARGET or path.is_relative_to(TARGET),'Directory boundary differs')
                require((str(info.st_dev),str(info.st_ino))==(row['identity']['device'],row['identity']['file_id']) and
                        not list(path.iterdir()),'Directory identity differs or unplanned entry remains')
                path.rmdir()
        require(not TARGET.exists() and report['removed_files']==plan['files'],'Exact target removal incomplete')
        report['status']='PASS_EXACT_FAILED_RUNTIME_REMOVED'
    except Exception as error:
        report['status']='FAILED_PARTIAL_NO_REPLAY';report['errors'].append(type(error).__name__+': '+str(error))
    finally:
        try:
            verify_protected(values['protected'],removed)
            report['protected_hashes_verified_after']=True
        except Exception as error:
            report['status']='FAILED_PROTECTED_VALIDATION';report['errors'].append(type(error).__name__+': '+str(error))
        report['protected_files']=len(values['protected'])
        report['volume_free_after']=shutil.disk_usage(ROOT).free
        report['volume_free_delta_not_attributed']=report['volume_free_after']-report['volume_free_before']
        report['retired_inputs_must_not_be_treated_as_replayable']=True
        artifact=helper.write_new(plan_path.parent/'cleanup.json',report)
        print(json.dumps(dict(**report,report=artifact),ensure_ascii=False),flush=True)
    return 0 if report['status']=='PASS_EXACT_FAILED_RUNTIME_REMOVED' else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',type=Path)
    parser.add_argument('--expect-plan-sha256')
    args=parser.parse_args()
    if args.apply:
        require(bool(args.expect_plan_sha256),'Apply requires exact fresh plan SHA')
        raise SystemExit(apply(args.apply,args.expect_plan_sha256))
    make_plan()
