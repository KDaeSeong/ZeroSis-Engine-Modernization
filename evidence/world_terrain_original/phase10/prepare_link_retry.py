"""Fresh compiler-only plan for readonly-donor hardlink access."""
from pathlib import Path
import ast,gzip,importlib.util,json,subprocess,sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).absolute().parent
PROJECT=ROOT.parents[2]
spec=importlib.util.spec_from_file_location('retry_helpers',ROOT/'prepare_recorded_retry.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
ref,read,write_new=m.ref,m.read,m.write_new

def main():
    old=ROOT/'host_build_retry01';stage=ROOT/'host_build_retry02'
    assert not stage.exists() and read(old/'controller_exit.json')['returncode']==1
    attempts=list((old/'attempts').iterdir());assert len(attempts)==1
    failure=read(attempts[0]/'failure.json');assert 'WinError 5' in str(failure) and 'hostmain.cpp' in str(failure)
    issue=write_new(ROOT/'retry01_link_failure.json',dict(status='RECORDED_READONLY_DONOR_LINK_FAILURE',
        actual_exit=ref(old/'controller_exit.json'),failure=ref(attempts[0]/'failure.json'),
        next_method='Foreground recorded compiler controller with readonly hardlink access.',
        source_features_changed=False,original_attributes_must_not_change=True,old_plan_replayed=False))
    tool=PROJECT/'tools/build_menu_suite_host.py';before=tool.read_bytes();before_ref=ref(tool)
    assert before_ref['sha256']=='b6921fb87deb9ff6b26d3d5054140e9751b046aabbcbf2b7c2bfcf9c22ed7dd2'
    a=b"STAGE = PROJECT / 'evidence/world_terrain_original/phase10/host_build_retry01'"
    b=b"STAGE = PROJECT / 'evidence/world_terrain_original/phase10/host_build_retry02'"
    assert before.count(a)==1;after=before.replace(a,b);assert after.replace(b,a)==before
    defs=lambda raw:[ast.dump(n,include_attributes=False) for n in ast.parse(raw.decode('utf8')).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))]
    assert defs(before)==defs(after)
    backup=ROOT/'source_before'/('tools__build_menu_suite_host.py.'+before_ref['sha256'][:16]+'.gz')
    assert not backup.exists();backup.write_bytes(gzip.compress(before,mtime=0));assert gzip.decompress(backup.read_bytes())==before
    tool.write_bytes(after)
    tools=write_new(ROOT/'retry02_tools.json',dict(status='PASS_LINK_RETRY_STAGE_ONLY_RETARGET',
        before=before_ref,backup=ref(backup),after=ref(tool),exact_inverse_bytes=True,all_functions_unchanged=True))
    manifest=read(old/'source_manifest.json');rows={m.common.key(row['path']):ref(row['path']) for row in manifest['sources']}
    freeze=write_new(ROOT/'retry02_freeze.json',dict(status='PASS_UNCHANGED_FEATURE_SOURCE_FOR_LINK_RETRY',
        sources=[ref(row['path']) for row in read(ROOT/'retry_freeze.json')['sources']],
        previous=ref(ROOT/'retry_freeze.json'),source_or_tests_changed=False,only_builder_stage_changed=True))
    receipts=write_new(ROOT/'retry02_receipts.json',dict(status='PASS_RECORDED_READONLY_LINK_RETRY_CONTEXT',
        components=ref(ROOT/'component_receipts.json'),freeze=freeze,tools=tools,actual_failure=issue))
    for row in (freeze,tools,receipts,ref(Path(__file__))):rows[m.common.key(row['path'])]=row
    dummy=PROJECT/'Build/UiWindowHost/20000101T000000Z_000000000000/frozen/project'
    assert max(len(str(dummy/Path(row['path']).relative_to(PROJECT))) for row in rows.values())<260
    target=write_new(stage/'source_manifest.json',dict(schema='zerosis.phase10.hardlink_retry.source_manifest.v1',
        sources=list(rows.values()),previous_manifest=ref(old/'source_manifest.json'),native_execution_allowed=False))
    controller=(old/'run_recorded_build.py').read_bytes();a=b'phase10/host_build_retry01/plan.json';b=b'phase10/host_build_retry02/plan.json'
    assert controller.count(a)==1;(stage/'run_recorded_build.py').write_bytes(controller.replace(a,b))
    result=subprocess.run([sys.executable,'-B','-X','utf8',str(tool),'--plan',str(stage/'plan.json'),
        '--catalog-count','74','--source-manifest',target['path']],cwd=PROJECT,capture_output=True,check=False,
        timeout=300,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    (stage/'plan.stdout.txt').write_bytes(result.stdout);(stage/'plan.stderr.txt').write_bytes(result.stderr)
    assert result.returncode==0,result.stderr.decode(errors='replace')
    plan=read(stage/'plan.json');previous=read(old/'plan.json')
    for key in ('tools','toolchain_inputs','vcvars','prior_responses','prior_link_response','include_roots','parent',
                'common_helper','menu_gate','catalog_count','protected_artifacts','direct_child_phases'):
        assert plan[key]==previous[key],key
    assert not plan['host_sdk_clr_hwnd_gpu_or_game_execution_allowed'] and not plan['automatic_retry_allowed']
    write_new(ROOT/'retry02_plan_review.json',dict(status='PASS_FRESH_READONLY_LINK_RETRY_COMPILER_ONLY',
        plan=ref(stage/'plan.json'),builder=ref(tool),manifest=target,tools=tools,freeze=freeze,
        source_feature_changes=0,original_plan_replayed=False,original_flags_and_providers_unchanged=True,
        native_execution_allowed=False,actual_prior_failure=issue))
    print(json.dumps(dict(status='PASS_FRESH_READONLY_LINK_RETRY_COMPILER_ONLY',
        plan_sha256=ref(stage/'plan.json')['sha256'],builder_sha256=ref(tool)['sha256'])))

if __name__=='__main__':main()
