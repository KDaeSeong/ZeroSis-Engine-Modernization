"""Close an already-passing binding fixture and retire five failed consoles."""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode=True
STAGE=Path(__file__).absolute().parents[1]
PROJECT=STAGE.parents[2]
ROOT=PROJECT/'Build/MenuRewardHostBinding'
FINAL='4d2aac9a11814351'
FAILED=('1665d79393da716c','2d0cf9835151bddb','33dbb9ba1da0aa3d','ef407e7185a2c038')
sys.path.insert(0,str(PROJECT/'tools'))
from menu_suite_storage import storage


def read(path):return json.loads(Path(path).read_bytes())
def write_new(path,value):
    with Path(path).open('x',encoding='utf8') as stream:json.dump(value,stream,indent=2);stream.write('\n')
def artifact(path):
    path=Path(path).absolute();info=storage.ordinary(path)
    return dict(path=str(path),sha256=storage.digest(path),allocated_bytes=storage.allocated(path),**storage.metadata(info))
def key(path):return os.path.normcase(os.path.abspath(os.fspath(path))).casefold()
def stable(a,b):
    fields=('path','sha256','bytes','file_identity','mtime_ns','file_attributes','allocated_bytes')
    return all(field not in b or (key(a[field])==key(b[field]) if field=='path' else a[field]==b[field]) for field in fields)
def checked(row):
    now=artifact(row['path']);assert stable(now,row),row['path'];return now
def ancestors(path):
    path=Path(path).absolute()
    for part in (path,*path.parents):
        info=os.stat(part,follow_symlinks=False)
        assert not info.st_file_attributes&0x400,str(part)
def path_rows(value):
    if isinstance(value,dict):
        if isinstance(value.get('path'),str):yield value
        for child in value.values():yield from path_rows(child)
    elif isinstance(value,list):
        for child in value:yield from path_rows(child)


def make_plan():
    result_path=STAGE/'binding'/FINAL/'result.json';result=read(result_path)
    assert result['status']=='PASS_COMMITTED_REWARD_HOST_BINDING_LEGACY_REGRESSION_AND_RETAINED_LUA'
    assert result['inputs_before']==result['inputs_after'] and result['compiler_and_linker_warnings']==0
    assert result['strict_committed_only_publication_verified'] and result['sdk_rules_and_dll_unchanged']
    inputs=[checked(row) for row in result['inputs_after']]
    retained=[checked(result[field]) for field in ('component_build','legacy_regression_build')]
    protected_path=STAGE/'protection_before.json.gz'
    protected=json.loads(gzip.decompress(protected_path.read_bytes()))
    protected_paths={key(row['path']) for row in protected['protected_artifacts']}
    protected_ids={tuple(row['file_identity']) for row in protected['protected_artifacts']}
    retained_paths={key(row['path']) for row in retained}
    candidates=[];proofs=[]
    for attempt in FAILED:
        proof_path=STAGE/'binding'/attempt/'result.json';proof=read(proof_path);proofs.append(artifact(proof_path))
        assert proof['status'].startswith('FAIL_')
        allowed={key(ROOT/attempt/'component/MenuRewardHostBinding.exe'),key(ROOT/attempt/'legacy/MenuOptionsHostBindingRegression.exe')}
        for field in ('component_build','legacy_regression_build'):
            row=proof.get(field)
            if not row:continue
            path=Path(row['path']).absolute();assert key(path) in allowed
            assert path.is_relative_to(ROOT) and path.resolve()==path
            ancestors(path);current=checked(row)
            assert current['links']==1 and not current['file_attributes']&0x400
            assert key(path) not in retained_paths and key(path) not in protected_paths
            assert tuple(current['file_identity']) not in protected_ids
            candidates.append(dict(current,failed_attempt=attempt,failed_result=str(proof_path),
                reason='REGENERABLE_FAILED_FIXTURE_CONSOLE_SUPERSEDED_BY_FINAL_PASS_4d2aac9a11814351'))
    assert len(candidates)==5 and len({key(row['path']) for row in candidates})==5
    # A failed console cannot be a current source, provider or retained product.
    forbidden={key(row['path']) for row in [*inputs,*retained]}
    assert not any(key(row['path']) in forbidden for row in candidates)
    assert result['binding_fixture']['checks']==33 and result['legacy_regression']['checks']==26
    return dict(schema='zerosis.reward_binding.failed_console_retirement.plan.v1',
        status='REVIEWED_EXACT_FIVE_SUPERSEDED_FAILED_CONSOLES_ONLY',final_result=artifact(result_path),
        current_inputs_verified=inputs,retained_successful_products=retained,failed_result_proofs=proofs,
        protected_snapshot=artifact(protected_path),protected_paths_checked=len(protected_paths),
        protected_file_ids_checked=len(protected_ids),protected_or_current_source_matches=0,
        exact_root=str(ROOT),candidates=candidates,
        native_host_sdk_hwnd_gpu_audio_executed=False,tests_or_builds_reexecuted=False,
        source_default_registered_runtime_or_user_save_deleted=False)


def main():
    cli=argparse.ArgumentParser();cli.add_argument('action',choices=['plan','apply']);cli.add_argument('--plan-sha');args=cli.parse_args()
    binding=STAGE/'binding';plan_path=binding/'failed_console_retirement.plan.json'
    output=binding/'failed_console_retirement.result.json';delivery=binding/'delivery.json'
    assert not output.exists() and not delivery.exists()
    if args.action=='plan':
        assert not args.plan_sha;plan=make_plan();write_new(plan_path,plan)
        print(json.dumps(dict(status=plan['status'],plan_sha=storage.digest(plan_path),files=len(plan['candidates']),
            allocated_bytes=sum(row['allocated_bytes'] for row in plan['candidates']))));return
    assert args.plan_sha and storage.digest(plan_path)==args.plan_sha
    plan=read(plan_path)
    for row in [plan['final_result'],*plan['current_inputs_verified'],*plan['retained_successful_products'],
                *plan['failed_result_proofs'],plan['protected_snapshot']]:checked(row)
    for row in plan['candidates']:
        path=Path(row['path']);ancestors(path);current=checked(row)
        assert path.is_relative_to(ROOT) and path.resolve()==path and current['links']==1
    deleted=[]
    for row in plan['candidates']:
        path=Path(row['path']);checked(row);path.unlink()
        assert not os.path.lexists(path)
        deleted.append(dict(row,result='DELETED_EXACT_OWNED_SUPERSEDED_FAILED_BINDING_FIXTURE_CONSOLE'))
    for row in [*plan['current_inputs_verified'],*plan['retained_successful_products'],*plan['failed_result_proofs']]:checked(row)
    retirement=dict(schema='zerosis.reward_binding.failed_console_retirement.result.v1',
        status='PASS_EXACT_FIVE_FAILED_BINDING_CONSOLES_RETIRED',utc=datetime.now(timezone.utc).isoformat(),
        reviewed_plan=artifact(plan_path),deletion_events=deleted,files_deleted=len(deleted),
        gross_deleted_logical_bytes=sum(row['bytes'] for row in deleted),
        gross_deleted_allocated_bytes=sum(row['allocated_bytes'] for row in deleted),
        all_deleted_paths_absent=True,retained_successful_products=[checked(row) for row in plan['retained_successful_products']],
        failed_reports_preserved=[checked(row) for row in plan['failed_result_proofs']],
        source_default_registered_runtime_or_user_save_deleted=False,native_host_sdk_hwnd_gpu_audio_executed=False)
    write_new(output,retirement)
    final=read(plan['final_result']['path']);lua=final['lua']
    receipt=dict(schema='zerosis.reward_binding.delivery.v1',
        status='PASS_CURRENT_HOST_BINDING_EMBEDDED_LUA_AND_EXACT_FAILED_CONSOLE_RETIREMENT',
        utc=datetime.now(timezone.utc).isoformat(),report=checked(plan['final_result']),
        current_inputs_verified=[checked(row) for row in plan['current_inputs_verified']],
        before_after_inputs_equal=True,current_input_count=len(plan['current_inputs_verified']),
        retained_consoles=[checked(row) for row in plan['retained_successful_products']],
        failed_fixture_retirement=artifact(output),
        controlled_checks=dict(binding_cpp=33,legacy_cpp=26,
            retained_lua=sum(lua[name]['checks'] for name in ('full_existing_harness','reward_only_probe','popup_visibility_probe')),
            real_snapshot_contracts=len(lua['actual_snapshot_contracts']),invalid_snapshot_contracts_rejected=lua['rejected_invalid_snapshot_contracts']),
        actual_sdk430_consumer_sources_match=True,sdk_rules_and_dll_unchanged=True,
        committed_only_snapshot_publication_verified=True,compiler_and_linker_warnings=0,
        original_reward_callback_and_popup_visibility_verified=True,
        original_settings_or_user_save_opened=False,full_original_options_script_executed=False,
        native_host_sdk_hwnd_gpu_audio_executed=False,full_engine_goal_complete=False,
        latest_owned_intermediate_cleanup=final['owned_intermediate_cleanup'],
        scope='Existing successful C++ and exact embedded Lua evidence closed by file/hash checks only; tests were not repeated. Failed attempts remain as small diagnostic reports, not current acceptance evidence.')
    write_new(delivery,receipt)
    print(json.dumps(dict(status=receipt['status'],delivery=str(delivery),deleted=len(deleted),
        allocated_bytes=retirement['gross_deleted_allocated_bytes'],current_inputs=len(plan['current_inputs_verified']))))


if __name__=='__main__':main()
