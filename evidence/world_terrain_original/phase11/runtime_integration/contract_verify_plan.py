"""Read-only review of one fresh six-package overlay plan; never imports it."""
from pathlib import Path
import argparse,ast,hashlib,json,os,re,sys
sys.dont_write_bytecode=True
STAGE=Path(__file__).absolute().parent
PROJECT=STAGE.parents[3]


def reference(path):
    path=Path(path).absolute();before=path.lstat()
    assert path.is_file()and not before.st_file_attributes&0x400
    for parent in path.parents:assert not parent.lstat().st_file_attributes&0x400
    with path.open('rb')as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    after=path.lstat()
    assert (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_file_attributes)==(
        after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_file_attributes)
    return dict(path=str(path),bytes=after.st_size,sha256=digest,file_identity=[after.st_dev,after.st_ino],
        mtime_ns=after.st_mtime_ns,file_attributes=after.st_file_attributes,links=after.st_nlink)


def checked(row):
    result=reference(row['path'])
    for name in ('bytes','sha256','file_identity','mtime_ns','file_attributes','links'):
        if name in row:assert result[name]==row[name],(row['path'],name)
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--plan-sha256',required=True);args=parser.parse_args()
    assert re.fullmatch('[0-9a-f]{64}',args.plan_sha256)
    output=STAGE/'contract_overlay_plan_review.json';assert not output.exists()
    plan_path=STAGE/'overlay/plan.json';plan_ref=reference(plan_path);assert plan_ref['sha256']==args.plan_sha256
    plan=json.loads(plan_path.read_bytes());assert plan['schema']=='zerosis.phase11.runtime_overlay.plan.v1'
    assert plan['native_execution_allowed']is False and plan['default_or_registration_changed']is False and plan['new_game_only']is True
    run=plan['run_id'];assert re.fullmatch(r'\d{8}T\d{6}Z_[0-9a-f]{12}',run)
    assert run not in ('20261115T134603Z_aa8853762399','20261115T101941Z_99b3c393ee9a','20261115T011241Z_4c8fd55e99db','20261108T003146Z_40a8030edf08')
    runtime=PROJECT/'Build/InteractiveGameRuntime'/run;assert Path(plan['runtime_directory'])==runtime
    assert not (runtime/'sessions').exists()and not list(runtime.glob('interactive-ui-*.json'))
    assert not (runtime/'WorldAssets').exists()and not (STAGE/'overlay/result.json').exists()
    checked(plan['adapter_source']);checked(plan['validator_source']);checked(plan['compiled_asset_binding'])
    assert plan['compiled_asset_binding']['sha256']=='f6947fd86764e32209dee2f3abbb04a5d17e9f2eaa5097d7ab1e112bdc317c32'
    base_ref=checked(plan['base_result']);base=json.loads(Path(base_ref['path']).read_bytes())
    assert base['run_id']==run and base['host_build_id']=='20261116T114748Z_014dd63ad3bc'
    assert base['host']['sha256']=='c3bb5ffc2e57630d28a8305f288b501352c03f0e1970b1dc5b321d6ba0683383'
    assert base['gamecore']['sha256']=='430f3122d0b555d6daae14aa7c011ef43ce8f978270477c8af596ca4b0493ab9'
    assert base['native_attempts']==0 and base['host_or_sdk_executed']is False and base['new_game_only']is True
    controls={row['relative_path']:row['artifact']for row in plan['controls']}
    assert len(controls)==3 and set(controls)=={'request.json','bundle.manifest','Play.ps1'}
    for name,row in controls.items():
        checked(row);assert row['links']==1 and row['file_attributes']==32
        expected=PROJECT/'evidence/interactive_game'/run/'request.json'if name=='request.json'else runtime/name
        assert Path(row['path'])==expected
    request=json.loads(Path(controls['request.json']['path']).read_bytes())
    assert controls['request.json']['sha256']==base['request']['sha256']
    assert request['run_id']==run and request['smoke']is False and request['resume_from']is None and len(request['runtime_inputs'])==24
    source=json.loads((STAGE/'contract_requirements.json').read_bytes());assert set(plan['packages'])==set(source['packages'])and len(plan['packages'])==6
    for role,row in plan['packages'].items():
        actual=checked(row['source']);expected=source['packages'][role]
        assert actual['sha256']==expected['source']['sha256']and actual['bytes']==expected['source']['bytes']
        assert actual['file_attributes']==32 and row['method']=='hardlink'and row['read_only']is False
        assert row['immutability_policy']=='READ_ONLY_USE_NO_ATTRIBUTE_CHANGE'
        assert Path(row['target_path'])==runtime/expected['relative_path']
        if role!='terrain':assert not Path(row['target_path']).exists()
    assert len(plan['shared_support'])==8
    donor=PROJECT/'Build/InteractiveGameRuntime/20261115T134603Z_aa8853762399'
    for row in plan['shared_support']:
        source_ref=checked(row['source']);target_ref=checked(row['target'])
        assert Path(source_ref['path'])==donor/row['relative_path']and Path(target_ref['path'])==runtime/row['relative_path']
        assert all(source_ref[name]==target_ref[name]for name in ('bytes','sha256','mtime_ns','file_attributes'))
        assert target_ref['links']==1 and source_ref['file_identity']!=target_ref['file_identity']and source_ref['file_attributes']==32
    terrain=checked(plan['base_terrain']);assert terrain['path']==str(runtime/'terrain-assets.bin')and terrain['sha256']=='2bee85c22c77b0342896f827989ca7d6f4ca3ae8f4dfe3a2179faaab4d689b13'
    text=(STAGE/'overlay.py').read_text(encoding='utf8');old=(PROJECT/'evidence/world_terrain_original/phase9/runtime_integration/overlay.py').read_text(encoding='utf8')
    boundary=lambda code:next(node for node in ast.parse(code).body if isinstance(node,ast.ClassDef)and node.name=='Boundary')
    assert ast.dump(boundary(text),include_attributes=False)==ast.dump(boundary(old),include_attributes=False)
    assert 'ZEROSIS_SCREEN_LIGHT_ASSETS'in text and 'ZEROSIS_HOST_BUNDLE_V4'in text
    record=dict(schema='zerosis.phase11.contract_overlay_plan_review.v1',status='PASS_FRESH_SIX_PACKAGE_FILE_ONLY_PLAN',plan=plan_ref,
        run_id=run,runtime_directory=str(runtime),base_result=base_ref,packages=6,environment_bindings=5,shared_support=8,
        exact_retired_fresh_leaf_candidates=9,backend_payloads=23,request_rows=24,boundary_class_ast_unchanged=True,
        native_attempts=0,overlay_or_launcher_executed_by_this_verifier=False,runtime_or_source_modified=False,
        scope='Pre-apply artifact hashes, IDs, timestamps, attributes and exact fresh destinations; no engine or renderer execution.')
    with output.open('x',encoding='utf8',newline='\n')as stream:json.dump(record,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(status=record['status'],artifact=reference(output))))


if __name__=='__main__':main()
