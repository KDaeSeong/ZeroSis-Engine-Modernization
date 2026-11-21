"""Independent phase-ten file-only plan audit; no builder or launcher is imported."""
from pathlib import Path
import ast,gzip,hashlib,json,os,stat,sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).absolute().parent
PHASE=ROOT.parent
PROJECT=PHASE.parents[2]
PLAN_SHA='5204494a33cd320a4d39a849c941b6748c1f3c21d27348260127ded8cb344779'
PARENT_SHA='1334205b2b3cd302ffbd49f4e21184db103423d91c74fa721befc6f85cece07c'


def key(path):return os.path.normcase(os.path.abspath(path))
def shape(row):return row['bytes'],row['sha256']
def artifact(path):
    path=Path(path).absolute();before=path.stat()
    with path.open('rb')as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    after=path.stat();assert (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)==(
        after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns)
    return dict(path=str(path),bytes=after.st_size,sha256=digest)
def checked(row):
    actual=artifact(row['path']);assert shape(actual)==shape(row),row['path'];return actual
def load(path):return json.loads(Path(path).read_bytes())


def main():
    output=ROOT/'cache_plan_review.json';assert not output.exists()
    plan_path=PHASE/'host_build/plan.json';plan_ref=artifact(plan_path);assert plan_ref['sha256']==PLAN_SHA
    plan=load(plan_path);assert plan['schema']=='zerosis.menu_suite_host.plan.v1'
    assert plan['status']=='FILE_ONLY_PLAN_REQUIRES_ACTUAL_DEPENDENCY_DISCOVERY'
    parent_ref=checked(plan['parent']);assert parent_ref['sha256']==PARENT_SHA
    parent=load(parent_ref['path']);assert parent['build_id']=='20261115T121456Z_dbb01a1f4f50'
    before={key(row['path']):row for row in parent['current_source_inputs']}
    after={key(row['path']):row for row in plan['current_source_inputs']}
    assert len(before)==1058 and len(after)==len(plan['current_source_inputs'])==1084
    removed=set(before)-set(after);added=set(after)-set(before)
    changed={name for name in set(before)&set(after)if shape(before[name])!=shape(after[name])}
    assert not removed and len(added)==26 and len(changed)==24
    backups={}
    for name in ('source_before.json','source_before_additional01.json','source_before_additional02.json','source_before_additional03.json'):
        document=load(PHASE/name)
        for row in document['backups']:
            packed=Path(row['backup']['path']).read_bytes()
            assert hashlib.sha256(packed).hexdigest()==row['backup']['sha256']
            raw=gzip.decompress(packed)
            assert (len(raw),hashlib.sha256(raw).hexdigest())==shape(row['source'])
            backups.setdefault(key(row['source']['path']),[]).append(row['source'])
    # The authorized direction-only update also retains its original byte source.
    update=load(ROOT/'cache_test_direction_update.json')
    backup=gzip.decompress(Path(update['backup']['path']).read_bytes())
    test_key=key(update['path']);assert (len(backup),hashlib.sha256(backup).hexdigest())==shape(before[test_key])
    backups.setdefault(test_key,[]).append(dict(path=update['path'],**update['before']))
    for name in changed:
        assert name in backups and any(shape(row)==shape(before[name])for row in backups[name]),after[name]['path']
        checked(after[name])
        file=Path(after[name]['path'])
        assert any(file.is_relative_to(PROJECT/relative)for relative in ('Source','Tests','tools'))
    preparation=load(PHASE/'manifest_preparation.json')
    manifest_ref=checked(plan['source_manifest']);manifest=load(manifest_ref['path'])
    manifest_rows={key(row['path']):row for row in manifest['sources']}
    assert len(manifest_rows)==len(manifest['sources'])==458 and manifest['native_execution_allowed'] is False
    assert set(manifest_rows)=={key(path)for path in plan['additional_sources']}
    assert all(name in after and shape(row)==shape(after[name])for name,row in manifest_rows.items())
    allowed_new={key(path)for path in preparation['new_sources']}
    assert added<=allowed_new
    for name in added:checked(after[name])
    assert {key(path)for path in preparation['changed_existing']}==changed
    assert preparation['removals']==[] and preparation['parent_rows']==431
    for name,row in after.items():
        file=Path(row['path']);info=file.lstat();assert stat.S_ISREG(info.st_mode)and not info.st_file_attributes&0x400
        assert (info.st_size,info.st_mtime_ns,info.st_file_attributes,[info.st_dev,info.st_ino])==(
            row['bytes'],row['mtime_ns'],row['file_attributes'],row['file_identity']),file
        lower=file.as_posix().lower()
        assert '/docs/'not in lower and file.name.lower()not in ('current_work.json','current_progress.json','global_current_progress.json','claude_handoff.md')
    component_ref=checked(manifest['offline_component_binding']);components=load(component_ref['path'])
    assert len(components['proofs'])==20
    for proof in components['proofs'].values():checked(proof['artifact']);assert proof['status'].startswith('PASS')
    assert components['proofs']['cache_model_cpu']['checks']==366342
    assert components['proofs']['cache_legacy_model_geometry']['checks']==90876
    assert components['proofs']['original_68_claims']['checks']==68
    assert components['native_host_sdk_clr_hwnd_gpu_audio_or_game_executed']is False
    freeze_ref=artifact(PHASE/'source_freeze.json');freeze=load(freeze_ref['path'])
    for row in freeze['sources']:assert shape(checked(row))==shape(after[key(row['path'])])
    baseline=load_gzip(PHASE/'protection_before.json.gz')
    protected_before={key(row['path']):row for row in baseline['protected_artifacts']}
    protected={key(row['path']):row for row in plan['protected_artifacts']}
    assert len(protected)==len(plan['protected_artifacts'])==4739
    fields=('bytes','sha256','file_identity','mtime_ns','file_attributes')
    for name,row in protected.items():assert name in protected_before and all(row[f]==protected_before[name][f]for f in fields),row['path']
    runtimes={}
    for run in ('20261115T134603Z_aa8853762399','20261115T101941Z_99b3c393ee9a','20261115T011241Z_4c8fd55e99db','20261108T003146Z_40a8030edf08'):
        directory=PROJECT/'Build/InteractiveGameRuntime'/run;live=set()
        for current,children,files in os.walk(directory,followlinks=False):
            for name in children:assert not (Path(current)/name).lstat().st_file_attributes&0x400
            live.update(key(Path(current)/name)for name in files)
        assert live and live<=set(protected)
        runtimes[run]=dict(all_live_files_protected=len(live),user_session_files=sum('/sessions/'in Path(name).as_posix()for name in live))
    assert any(row['sha256']=='430f3122d0b555d6daae14aa7c011ef43ce8f978270477c8af596ca4b0493ab9'for row in protected.values())
    for name in ('compiler','linker','dumpbin'):assert plan['tools'][name]==parent[name];checked(plan['tools'][name])
    assert plan['toolchain_inputs']==parent['toolchain_inputs']and plan['vcvars']==parent['vcvars']and plan['system_tool_selection']is None
    pins={'common_helper':'69133de112bd30e088626379adce382912f26086aae701c8a2683fbbe0e8fd94',
        'menu_gate':'587d564e7df4e59fca5356e6f94b15b4bc3aba4a36fed11ba150ac355af08067',
        'pure_parser':'723e8d4594ce148336149f34c2ee535512c14ad283165b4fd729473eb302123f',
        'pure_build_helper':'07f50b1ab7482591792b44cc8767f27c709884f5f487b0eada7459f28c8da558'}
    for name,pin in pins.items():assert checked(plan[name])['sha256']==pin
    retarget=load(ROOT/'cache_build_tools_retarget.json')
    for row in retarget['files']:assert checked(row['after'])['sha256']==row['after']['sha256'];ast.parse(Path(row['after']['path']).read_bytes())
    assert checked(plan['builder'])['sha256']=='326f37dbcba536ad8aba7efd78d3c7a4f8ccd1e44a09252f740c9ee44e515ce4'
    units=('host_main','window','renderer','world_renderer','terrain_renderer')
    phases=['environment']+['discover_'+unit for unit in units]+['compile_'+unit for unit in units]+['link']
    assert plan['direct_child_phases']==phases and plan['allowed_native_children']=='EXACT_ENVIRONMENT_AND_COMPILER_LINKER_ONLY'
    false_flags=('host_sdk_clr_hwnd_gpu_or_game_execution_allowed','full_ui_preparer_main_allowed','default_promotion_allowed','automatic_retry_allowed','full_engine_goal_complete')
    assert all(plan.get(flag)is False for flag in false_flags)
    assert plan['dependency_count_policy']=='ACTUAL_FIVE_ZS_REPORTS_NO_PREASSUMED_COUNTS'and set(plan['prior_responses'])==set(units)
    languages={}
    for unit,row in plan['prior_responses'].items():
        checked(row);raw=Path(row['path']).read_bytes();text=raw.decode('utf-16')if raw.startswith(b'\xff\xfe')else raw.decode('utf-8-sig')
        flags=set(text.splitlines());language='/std:c++17'if unit=='terrain_renderer'else'/std:c++14'
        assert {language,'/O2','/W4','/WX','/fp:strict'}<=flags;languages[unit]=language
    checked(plan['prior_link_response'])
    launcher=PHASE/'host_build/start_recorded_build.ps1';text=launcher.read_text(encoding='utf8')
    assert '-WindowStyle Hidden'in text and '-RedirectStandardOutput'in text and '-RedirectStandardError'in text
    assert '--build-plan'in text and '--plan-sha256'in text and 'single-use'in text
    assert 'ZeroSisHost_x64.exe'not in text and 'Start-Process'in text
    assert not any((PHASE/'host_build'/name).exists()for name in ['launcher.json','driver.stdout.txt','driver.stderr.txt'])
    assert artifact(plan_path)==plan_ref
    report=dict(schema='zerosis.phase10.cache.independent_host_plan_review.v1',status='PASS_EXACT_COMPILE_ONLY_PLAN_SCOPE_AND_NATIVE_HOLD',
        plan=plan_ref,parent=parent_ref,source_manifest=manifest_ref,current_inputs=len(after),changed_existing_count=len(changed),
        changed_existing=sorted(after[name]['path']for name in changed),added_source_count=len(added),added_sources=sorted(after[name]['path']for name in added),
        source_deletions=0,manifest_rows=458,parent_manifest_rows=431,component_receipts=component_ref,source_freeze=freeze_ref,
        component_proofs=20,source_backup_gzip_claims_verified=True,mutable_docs_or_progress_inputs=[],protected_artifacts=len(protected),
        protected_rows_equal_root_preverified7300_baseline=True,protected_runtime_trees=runtimes,gamecore430_protected=True,
        compiler_linker_toolchain_and_provider_unchanged=True,helper_pins=pins,planned_direct_child_phases=phases,
        translation_unit_languages=languages,native_hold_flags={flag:False for flag in false_flags},recorded_launcher=artifact(launcher),
        recorded_launcher_executed_by_this_auditor=False,immutable_provider_dataset_rehashed_again=False,
        audit_method='All changed/new/frozen code and tool SHA; all current-input metadata; protected row equality and live runtime-tree membership. No duplicate full protected-payload scan.',
        builder_or_launcher_imported_or_executed_by_this_audit=False,file_only_plan_previously_generated=True,
        compiler_linker_host_gamecore_clr_hwnd_gpu_audio_or_game_executed_by_this_auditor=False,blockers=[])
    with output.open('x',encoding='utf8',newline='\n')as stream:json.dump(report,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(status=report['status'],artifact=artifact(output),plan_sha256=PLAN_SHA,changed=24,new=26,protected=4739,phases=12)))


def load_gzip(path):return json.loads(gzip.decompress(Path(path).read_bytes()))


if __name__=='__main__':main()
