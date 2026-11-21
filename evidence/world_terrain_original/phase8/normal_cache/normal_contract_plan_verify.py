"""Independent file-only plan audit; does not import or invoke the builder."""
from pathlib import Path
import ast,gzip,hashlib,json,os,stat

ROOT=Path(__file__).absolute().parent
PROJECT=ROOT.parents[3]
PHASE=ROOT.parent
PLAN_SHA='9f65803e802aef8390d18733d56140d4f3c030fed3513691142aa9b5444c69c7'
PARENT_SHA='4f7e6b1938da96445b76481a41f8742d0626c9a63199f40e58e9f57f46b6977a'


def key(path):return os.path.normcase(os.path.abspath(path))
def sha(raw):return hashlib.sha256(raw).hexdigest()
def shape(row):return (row['bytes'],row['sha256'])
def artifact(path):
    path=Path(path).absolute();before=path.stat();raw=path.read_bytes();after=path.stat()
    assert (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)==(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns)
    return dict(path=str(path),bytes=len(raw),sha256=sha(raw))
def checked(row):
    actual=artifact(row['path']);assert shape(actual)==shape(row),row['path'];return actual


def main():
    target=ROOT/'normal_contract_plan_review.json';assert not target.exists()
    plan_path=PHASE/'host_build/plan.json';plan_ref=artifact(plan_path);assert plan_ref['sha256']==PLAN_SHA
    plan=json.loads(plan_path.read_bytes());assert plan['schema']=='zerosis.menu_suite_host.plan.v1'
    assert plan['status']=='FILE_ONLY_PLAN_REQUIRES_ACTUAL_DEPENDENCY_DISCOVERY'
    parent_ref=checked(plan['parent']);assert parent_ref['sha256']==PARENT_SHA
    parent=json.loads(Path(parent_ref['path']).read_bytes());assert parent['build_id']=='20261115T093013Z_23c5037b12b9'
    before={key(row['path']):row for row in parent['current_source_inputs']}
    after={key(row['path']):row for row in plan['current_source_inputs']}
    assert len(after)==len(plan['current_source_inputs'])==1058 and len(before)==1028
    removed=set(before)-set(after);added=set(after)-set(before)
    changed={path for path in set(before)&set(after) if shape(before[path])!=shape(after[path])}
    assert not removed and len(added)==30 and len(changed)==16
    backups={}
    backup_refs=[]
    for name in ('source_before.json','source_before_extra01.json'):
        document=json.loads((PHASE/name).read_bytes());assert document['full_project_copy'] is False
        for row in document['backups']:
            packed=Path(row['backup']['path']).read_bytes();assert sha(packed)==row['backup']['sha256']
            original=gzip.decompress(packed);assert sha(original)==row['source']['sha256'] and len(original)==row['source']['bytes']
            backups.setdefault(key(row['source']['path']),[]).append((row,original))
    for path in changed:
        assert path in backups and any(shape(row['source'])==shape(before[path]) for row,_ in backups[path])
        checked(after[path])
        assert Path(after[path]['path']).is_relative_to(PROJECT/'Source/Presentation') or key(Path(after[path]['path']).parent)==key(PROJECT/'tools')
    new_rel=[]
    for path in added:
        row=after[path];checked(row);relative=Path(row['path']).relative_to(PROJECT).as_posix();new_rel.append(relative)
        allowed=(relative.startswith('Source/Presentation/OriginalDynamicShadow') or
            relative.startswith('Source/Presentation/OriginalScreenLighting') or
            relative.startswith('Source/Presentation/OriginalWaterFog') or relative=='Source/Presentation/OriginalTerrainNormalModel.h' or
            relative.startswith('Tests/original_') or relative in ('evidence/world_terrain_original/phase8/component_receipts.json',
            'evidence/world_terrain_original/phase8/requirements.json','evidence/world_terrain_original/phase8/root_source_freeze.json',
            'evidence/world_terrain_original/phase8/screen_lighting/screen_provider_contract.py',
            'evidence/world_terrain_original/phase8/normal_cache/normal_contract_bulk_dag.py',
            'evidence/world_terrain_original/phase8/normal_cache/normal_contract_pe.py',
            'evidence/world_terrain_original/phase8/normal_cache/normal_contract_reference.py'))
        assert allowed,relative
    for path,row in after.items():
        info=Path(row['path']).lstat();assert stat.S_ISREG(info.st_mode) and not info.st_file_attributes&0x400
        assert (info.st_size,info.st_mtime_ns,info.st_file_attributes,[info.st_dev,info.st_ino])==(
            row['bytes'],row['mtime_ns'],row['file_attributes'],row['file_identity']),row['path']
        if path in before and path not in changed:assert shape(row)==shape(before[path])
    manifest_ref=checked(plan['source_manifest']);manifest=json.loads(Path(manifest_ref['path']).read_bytes())
    manifest_rows={key(row['path']):row for row in manifest['sources']}
    assert len(manifest_rows)==len(manifest['sources'])==431 and manifest['native_execution_allowed'] is False
    assert set(manifest_rows)=={key(path) for path in plan['additional_sources']}
    assert all(path in after and shape(row)==shape(after[path]) for path,row in manifest_rows.items())
    forbidden=[]
    for path in set(manifest_rows)|set(after):
        pp=Path(path);lower=pp.as_posix().lower()
        if '/docs/' in lower or pp.name.lower() in ('current_work.json','current_progress.json','global_current_progress.json','claude_handoff.md'):
            forbidden.append(path)
    assert not forbidden,forbidden
    checked(manifest['offline_component_binding'])
    baseline=json.loads(gzip.decompress((PHASE/'protection_before.json.gz').read_bytes()))
    protected_before={key(row['path']):row for row in baseline['protected_artifacts']}
    protected={key(row['path']):row for row in plan['protected_artifacts']}
    assert len(protected)==len(plan['protected_artifacts'])==4544
    fields=('bytes','sha256','file_identity','mtime_ns','file_attributes')
    for path,row in protected.items():
        assert path in protected_before and all(row[field]==protected_before[path][field] for field in fields),row['path']
    runtimes={}
    for run in ('20261115T101941Z_99b3c393ee9a','20261115T011241Z_4c8fd55e99db','20261108T003146Z_40a8030edf08'):
        directory=PROJECT/'Build/InteractiveGameRuntime'/run
        live=set()
        for current,children,files in os.walk(directory,followlinks=False):
            for name in children:assert not (Path(current)/name).lstat().st_file_attributes&0x400
            for name in files:live.add(key(Path(current)/name))
        assert live and live<=set(protected)
        runtimes[run]=dict(all_live_files_protected=len(live),user_session_files=sum('/sessions/' in Path(path).as_posix() for path in live))
    sdk_sha='430f3122d0b555d6daae14aa7c011ef43ce8f978270477c8af596ca4b0493ab9'
    assert any(row['sha256']==sdk_sha and Path(row['path']).name=='CvGameCoreDLL_Expansion2_x64.dll' for row in protected.values())
    for name in ('compiler','linker'):assert plan['tools'][name]==parent[name];checked(plan['tools'][name])
    assert plan['toolchain_inputs']==parent['toolchain_inputs'] and plan['vcvars']==parent['vcvars']
    assert plan['system_tool_selection'] is None
    pins={'common_helper':'69133de112bd30e088626379adce382912f26086aae701c8a2683fbbe0e8fd94',
        'menu_gate':'587d564e7df4e59fca5356e6f94b15b4bc3aba4a36fed11ba150ac355af08067',
        'pure_parser':'723e8d4594ce148336149f34c2ee535512c14ad283165b4fd729473eb302123f',
        'pure_build_helper':'07f50b1ab7482591792b44cc8767f27c709884f5f487b0eada7459f28c8da558'}
    for name,pin in pins.items():assert checked(plan[name])['sha256']==pin
    tools_update=json.loads((ROOT/'normal_contract_build_tools_update.json').read_bytes())
    for row in tools_update['updates']:assert artifact(row['path'])['sha256']==row['after']['sha256'];ast.parse(Path(row['path']).read_bytes())
    assert plan['builder']['sha256']==next(row['after']['sha256'] for row in tools_update['updates'] if Path(row['path']).name=='build_menu_suite_host.py')
    expected_phases=['environment']+['discover_'+unit for unit in ('host_main','window','renderer','world_renderer','terrain_renderer')]+[
        'compile_'+unit for unit in ('host_main','window','renderer','world_renderer','terrain_renderer')]+['link']
    assert plan['direct_child_phases']==expected_phases and plan['allowed_native_children']=='EXACT_ENVIRONMENT_AND_COMPILER_LINKER_ONLY'
    false_flags=('host_sdk_clr_hwnd_gpu_or_game_execution_allowed','full_ui_preparer_main_allowed','default_promotion_allowed',
                 'automatic_retry_allowed','full_engine_goal_complete')
    assert all(plan.get(name) is False for name in false_flags)
    assert plan['dependency_count_policy']=='ACTUAL_FIVE_ZS_REPORTS_NO_PREASSUMED_COUNTS'
    assert set(plan['prior_responses'])=={'host_main','window','renderer','world_renderer','terrain_renderer'}
    for row in plan['prior_responses'].values():checked(row)
    checked(plan['prior_link_response'])
    freeze_ref=artifact(PHASE/'root_source_freeze.json');freeze=json.loads(Path(freeze_ref['path']).read_bytes())
    assert freeze['status']=='PASS_ROOT_SOURCE_INTEGRATION_FREEZE' and freeze['native_execution'] is False
    for row in freeze['sources']:assert shape(checked(row))==shape(after[key(row['path'])])
    assert next(row['sha256'] for row in freeze['sources'] if Path(row['path']).name=='WorldTerrainRenderer.cpp')=='ab8d711d4424ae5601b74a43e5b68296122889469c91813b59b7b2580dd066bd'
    assert artifact(plan_path)==plan_ref
    report=dict(schema='zerosis.phase8.normal_contract.independent_host_plan_review.v1',status='PASS_EXACT_OFFLINE_HOST_BUILD_PLAN_SCOPE_AND_PROTECTION',
        plan=plan_ref,parent=parent_ref,source_manifest=manifest_ref,current_inputs=1058,changed_existing=sorted(after[path]['path'] for path in changed),
        changed_existing_count=16,added_sources=sorted(new_rel),added_source_count=30,source_deletions=0,
        source_backup_gzip_claims_verified=True,manifest_rows=431,mutable_docs_or_progress_inputs=[],root_source_freeze=freeze_ref,
        protected_artifacts=4544,protected_rows_equal_preverified_baseline=True,protected_runtime_trees=runtimes,
        gamecore430_protected=True,compiler_linker_toolchain_unchanged=True,helper_pins_unchanged=pins,
        planned_direct_child_phases=expected_phases,native_hold_flags={name:False for name in false_flags},
        immutable_provider_dataset_rehashed_again=False,scope_method='Changed16/new30+tool/freeze/recipe hash checks; all current source metadata; protected row equality to the root-preverified6737 baseline and runtime-tree membership.',
        builder_imported_or_executed=False,plan_or_host_build_executed=False,host_gamecore_clr_hwnd_gpu_audio_or_game_executed=False,
        blockers=[])
    with target.open('x',encoding='utf-8',newline='\n') as stream:json.dump(report,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(status=report['status'],path=str(target),sha256=sha(target.read_bytes()),changed=16,added=30,protected=4544,planned_phases=12)))


if __name__=='__main__':main()
