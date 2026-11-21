"""Incremental audit of a fresh stage after loss of the first build record."""
from pathlib import Path
import ast,collections,gzip,hashlib,json,os,stat

ROOT=Path(__file__).absolute().parent
PROJECT=ROOT.parents[3]
PHASE=ROOT.parent
def sha(raw):return hashlib.sha256(raw).hexdigest()
def key(value):return os.path.normcase(os.path.abspath(value))
def checked(path,digest=None):
    path=Path(path);raw=path.read_bytes()
    if digest:assert sha(raw)==digest
    return dict(path=str(path),bytes=len(raw),sha256=sha(raw))


def main():
    output=ROOT/'normal_contract_retry_plan_review.json';assert not output.exists()
    old_path=PHASE/'host_build/plan.json';new_path=PHASE/'host_build_retry01/plan.json'
    old_ref=checked(old_path,'9f65803e802aef8390d18733d56140d4f3c030fed3513691142aa9b5444c69c7')
    new_ref=checked(new_path,'aaa51f353c8fd028ee9338508af3715fbe8203e38dcb7b10ed12189a34e37eba')
    approval_ref=checked(ROOT/'normal_contract_plan_review.json','f577ed4c9c4235fac7b4e4016adeb32cb8efe86559c4c8fbb8b01b40063a71ea')
    old=json.loads(old_path.read_bytes());new=json.loads(new_path.read_bytes())
    assert set(old)==set(new) and {k for k in old if old[k]!=new[k]}=={'builder','source_manifest','current_source_inputs','protected_artifacts'}
    retarget_path=PHASE/'host_build_retry01/stage_retarget.json';retarget_ref=checked(retarget_path);retarget=json.loads(retarget_path.read_bytes())
    previous=gzip.decompress(Path(retarget['backup']['path']).read_bytes());current=Path(new['builder']['path']).read_bytes()
    assert sha(previous)==old['builder']['sha256']==retarget['before']['sha256']=='3e2baa63fc5ef74f91cb6c586fab92a0552274779dbece7da5c1b18f96821ca9'
    assert sha(current)==new['builder']['sha256']==retarget['after']['sha256']=='58259d8d079d8ea0b5c1da011034014d1fc44b6b56de9d692ab360d20750d75f'
    a=retarget['old'].encode();b=retarget['new'].encode();assert previous.count(a)==1 and current.count(b)==1
    assert previous.replace(a,b)==current and current.replace(b,a)==previous
    old_ast=ast.parse(previous);new_ast=ast.parse(current)
    funcs=lambda tree:[ast.dump(node,include_attributes=False) for node in tree.body if isinstance(node,(ast.FunctionDef,ast.ClassDef))]
    assert funcs(old_ast)==funcs(new_ast)
    old_sources={key(row['path']):row for row in old['current_source_inputs']};new_sources={key(row['path']):row for row in new['current_source_inputs']}
    assert set(old_sources)==set(new_sources) and len(new_sources)==1058
    delta=[path for path in old_sources if old_sources[path]!=new_sources[path]]
    assert delta==[key(new['builder']['path'])]
    assert {name for name in old_sources[delta[0]] if old_sources[delta[0]][name]!=new_sources[delta[0]][name]}=={'bytes','sha256','mtime_ns'}
    old_manifest=json.loads(Path(old['source_manifest']['path']).read_bytes());new_manifest=json.loads(Path(new['source_manifest']['path']).read_bytes())
    assert {k for k in old_manifest if old_manifest[k]!=new_manifest[k]}=={'sources'}
    am={key(row['path']):row for row in old_manifest['sources']};bm={key(row['path']):row for row in new_manifest['sources']}
    assert set(am)==set(bm) and len(bm)==431 and [path for path in am if am[path]!=bm[path]]==delta
    assert checked(new['source_manifest']['path'])['sha256']==new['source_manifest']['sha256']
    partial_id='20261115T115920Z_a4b5d1514cc1';partial=PROJECT/'Build/UiWindowHost'/partial_id
    aliases=collections.Counter()
    for directory,children,files in os.walk(partial,followlinks=False):
        for name in children:assert not (Path(directory)/name).lstat().st_file_attributes&0x400
        for name in files:
            info=(Path(directory)/name).lstat();assert stat.S_ISREG(info.st_mode) and not info.st_file_attributes&0x400
            aliases[(info.st_dev,info.st_ino)]+=1
    ap={key(row['path']):row for row in old['protected_artifacts']};bp={key(row['path']):row for row in new['protected_artifacts']}
    assert set(ap)==set(bp) and len(bp)==4544
    link_deltas=[]
    for path,row in bp.items():
        old_row=ap[path]
        if old_row==row:continue
        assert {name for name in old_row if old_row[name]!=row[name]}=={'links'}
        assert row['links']-old_row['links']==aliases[tuple(row['file_identity'])]==1
        link_deltas.append(dict(path=row['path'],before=old_row['links'],after=row['links'],file_identity=row['file_identity']))
    assert len(link_deltas)==571
    assert partial_id.encode() not in new_path.read_bytes(),'Fresh plan must not consume incomplete outputs'
    phases=old['direct_child_phases'];assert len(phases)==12 and new['direct_child_phases']==phases
    holds=('host_sdk_clr_hwnd_gpu_or_game_execution_allowed','full_ui_preparer_main_allowed','default_promotion_allowed','automatic_retry_allowed','full_engine_goal_complete')
    assert all(old.get(name) is False and new.get(name) is False for name in holds)
    assert new['allowed_native_children']=='EXACT_ENVIRONMENT_AND_COMPILER_LINKER_ONLY'
    freeze=PHASE/'root_source_freeze.json';freeze_doc=json.loads(freeze.read_bytes())
    for row in freeze_doc['sources']:
        assert checked(row['path'])['sha256']==row['sha256']==new_sources[key(row['path'])]['sha256']
    interruptions=list((PHASE/'host_build/attempts').rglob('interruption.json'));assert len(interruptions)==1
    assert not (PROJECT/'evidence/ui_window_host'/partial_id/'build_result.json').exists()
    assert not list((PHASE/'host_build/attempts').rglob('run.json'))
    report=dict(schema='zerosis.phase8.normal_contract.fresh_stage_plan_review.v1',status='PASS_FRESH_RETRY_STAGE_ONLY_GUARDS_AND_SOURCE_SCOPE_UNCHANGED',
        old_approved_plan=old_ref,old_independent_approval=approval_ref,new_plan=new_ref,stage_retarget=retarget_ref,
        builder_change='Exact STAGE string only; byte reverse and all function/class AST bodies unchanged',
        current_source_rows=1058,source_manifest_rows=431,engine_or_shader_source_changes=0,source_row_changes=1,
        protected_rows=4544,content_size_id_time_attrs_changes=0,verified_linkcount_changes=571,
        link_changes_explained_by_exact_partial_build_aliases=True,partial_build_consumed_by_fresh_plan=False,
        partial_build_status='STATIC_OUTPUTS_PRESENT_FINAL_REPORT_AND_PROCESS_COMMAND_RECORDS_MISSING_NOT_CERTIFIED',
        interruption_receipt=checked(interruptions[0]),planned_direct_children=phases,native_hold_flags={name:False for name in holds},
        compiler_linker_provider_helper_and_ui_gates_unchanged=True,old_plan_replay_allowed=False,
        original_process_exit_codes_reconstructed=False,original_run_or_report_fabricated=False,
        actual_plan_or_host_build_run_by_this_review=False,host_gamecore_clr_hwnd_gpu_audio_or_game_executed=False,
        blockers=[])
    with output.open('x',encoding='utf-8',newline='\n') as stream:json.dump(report,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(status=report['status'],path=str(output),sha256=sha(output.read_bytes()),engine_changes=0,stage_only=True)))


if __name__=='__main__':main()
