"""Fresh compile-only plan after an unrecorded background launcher exit."""
from pathlib import Path
import ast
import gzip
import hashlib
import json
import subprocess
import sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).absolute().parent
PROJECT=ROOT.parents[2]
sys.path.insert(0,str(PROJECT/'tools'))
import build_exit_confirm_host as common


def ref(path):return common.artifact(Path(path).absolute())
def read(path):return json.loads(Path(path).read_text('utf-8-sig'))
def write_new(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf8') as stream:json.dump(value,stream,indent=2);stream.write('\n')
    return ref(path)


def main():
    old=ROOT/'host_build';stage=ROOT/'host_build_retry01'
    assert not stage.exists()
    assert ref(old/'plan.json')['sha256']=='5204494a33cd320a4d39a849c941b6748c1f3c21d27348260127ded8cb344779'
    assert not (old/'attempts').exists()
    assert not (old/'driver.stdout.txt').read_bytes() and not (old/'driver.stderr.txt').read_bytes()
    write_new(old/'launcher_interruption.json',dict(status='UNATTESTED_LAUNCHER_EXIT_BEFORE_BUILDER_OUTPUTS',
        launcher=ref(old/'launcher.json'),stdout=ref(old/'driver.stdout.txt'),stderr=ref(old/'driver.stderr.txt'),
        plan=ref(old/'plan.json'),builder_attempt_directories_observed=0,
        child_exit_code_recorded=False,returncode_or_guard_state_reconstructed=False,
        original_plan_replayed=False,source_feature_changes_for_retry=0,
        next_method='Foreground recorded Python runner held open through actual builder exit.'))
    tool=PROJECT/'tools/build_menu_suite_host.py';before=tool.read_bytes();before_ref=ref(tool)
    assert before_ref['sha256']=='326f37dbcba536ad8aba7efd78d3c7a4f8ccd1e44a09252f740c9ee44e515ce4'
    needle=b"STAGE = PROJECT / 'evidence/world_terrain_original/phase10/host_build'"
    replacement=b"STAGE = PROJECT / 'evidence/world_terrain_original/phase10/host_build_retry01'"
    assert before.count(needle)==1
    backup=ROOT/'source_before'/('tools__build_menu_suite_host.py.'+before_ref['sha256'][:16]+'.gz')
    assert not backup.exists();backup.write_bytes(gzip.compress(before,mtime=0))
    assert gzip.decompress(backup.read_bytes())==before
    after=before.replace(needle,replacement)
    assert after.replace(replacement,needle)==before
    definitions=lambda raw:[ast.dump(n,include_attributes=False) for n in ast.parse(raw.decode('utf8')).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))]
    assert definitions(before)==definitions(after)
    tool.write_bytes(after)
    retarget=write_new(ROOT/'retry_tools.json',dict(status='PASS_RETRY_STAGE_ONLY_RETARGET',
        before=before_ref,backup=ref(backup),after=ref(tool),exact_inverse_bytes=True,
        all_functions_and_classes_unchanged=True,compiler_flags_and_boundary_changes=0))
    previous=read(old/'source_manifest.json');rows={common.key(row['path']):row for row in previous['sources']}
    changed=[]
    for key,row in list(rows.items()):
        current=ref(row['path'])
        if current['sha256']!=row['sha256']:
            assert Path(row['path'])==tool
            changed.append(row['path'])
        rows[key]=current
    previous_freeze=read(ROOT/'source_freeze.json')
    freeze=write_new(ROOT/'retry_freeze.json',dict(status='PASS_SAME_FEATURE_SOURCE_FROZEN_FOR_RECORDED_RETRY',
        sources=[ref(row['path']) for row in previous_freeze['sources']],previous=ref(ROOT/'source_freeze.json'),
        changed_tool_context_only=changed,feature_source_or_tests_changed=False))
    components=write_new(ROOT/'retry_receipts.json',dict(status='PASS_PREVIOUS_COMPONENTS_PLUS_RECORDED_RETRY_CONTEXT',
        components=ref(ROOT/'component_receipts.json'),retarget=retarget,source_freeze=freeze,
        interrupted_launcher=ref(old/'launcher_interruption.json'),native_execution_allowed=False))
    for row in (retarget,freeze,components,ref(Path(__file__))):rows[common.key(row['path'])]=row
    dummy=PROJECT/'Build/UiWindowHost/20000101T000000Z_000000000000/frozen/project'
    longest=max(len(str(dummy/Path(row['path']).relative_to(PROJECT))) for row in rows.values())
    assert longest<260,longest
    manifest=write_new(stage/'source_manifest.json',dict(schema='zerosis.phase10.recorded_retry.source_manifest.v1',
        sources=list(rows.values()),parent_source_manifest=ref(old/'source_manifest.json'),
        max_future_frozen_path=longest,native_execution_allowed=False,components=components))
    command=[sys.executable,'-B','-X','utf8',str(tool),'--plan',str(stage/'plan.json'),
        '--catalog-count','74','--source-manifest',manifest['path']]
    result=subprocess.run(command,cwd=PROJECT,capture_output=True,check=False,timeout=300,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    (stage/'plan.stdout.txt').write_bytes(result.stdout);(stage/'plan.stderr.txt').write_bytes(result.stderr)
    assert result.returncode==0,result.stderr.decode(errors='replace')
    plan=read(stage/'plan.json');old_plan=read(old/'plan.json')
    assert plan['direct_child_phases']==old_plan['direct_child_phases'] and len(plan['direct_child_phases'])==12
    for key in ('tools','toolchain_inputs','vcvars','prior_responses','prior_link_response','include_roots',
                'parent','common_helper','menu_gate','catalog_count','protected_artifacts'):
        assert plan[key]==old_plan[key],key
    assert not plan['host_sdk_clr_hwnd_gpu_or_game_execution_allowed'] and not plan['automatic_retry_allowed']
    review=write_new(ROOT/'retry_plan_review.json',dict(status='PASS_FRESH_RECORDED_RETRY_PLAN_COMPILER_ONLY',
        plan=ref(stage/'plan.json'),builder=ref(tool),manifest=manifest,retarget=retarget,
        source_feature_changes=0,prior_responses_toolchain_provider_protection_unchanged=True,
        native_execution_allowed=False,original_plan_replayed=False,plan_preparation_exit_code=result.returncode,
        current_inputs=len(plan['current_source_inputs']),protected_inputs=len(plan['protected_artifacts']),
        direct_phases=plan['direct_child_phases'],foreground_exit_recording_required=True))
    print(json.dumps(dict(status='PASS_FRESH_RECORDED_RETRY_PLAN_COMPILER_ONLY',plan=review['path'],
        plan_sha256=ref(stage/'plan.json')['sha256'],builder_sha256=ref(tool)['sha256'])))


if __name__=='__main__':main()
