"""Retarget unchanged build gates and freeze current offline component proofs."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,ast,hashlib,json,os,sys
sys.dont_write_bytecode=True
STAGE=Path(__file__).absolute().parent
PROJECT=STAGE.parents[2]
sys.path[:0]=[str(PROJECT/'tools')]
import build_exit_confirm_host as common
PARENT_ID='20261116T114748Z_014dd63ad3bc'
PARENT_REPORT=PROJECT/'evidence/ui_window_host'/PARENT_ID/'build_result.json'
PARENT_SHA='3d5d63304d2076c2f309344e9103eb520875a5893282ed5abfff4104ef196b8d'
OLD_MANIFEST=PROJECT/'evidence/world_terrain_original/phase10/host_build_retry02/source_manifest.json'
NEW_SOURCE=['OriginalTerrainCacheSamplingModel.h','OriginalReflectionProjectionModel.h',
    'OriginalIceAssets.h','OriginalIceContract.h','OriginalIceShader.h']
NEW_TESTS=['original_terrain_cache_sampling.cpp','original_terrain_cache_sampling.py',
    'original_terrain_height_binding.cpp','original_reflection_projection.cpp','original_ice_contract.cpp','original_ice_contract.py']
PROOFS={
    'cache_sampling':'cache/cache_completion.json',
    'production_height_binding':'cache/cache_height_binding_completion.json',
    'height_metadata_same_bytes':'cache/cache_height_binding_metadata_reseal.json',
    'reflection':'reflection/reflection_completion.json',
    'ice_component':'scene/scene_ice_result.json',
    'ice_vs_cpu_equivalence':'scene/scene_ice_vs_equivalence.json',
    'ice_cleanup':'scene/scene_ice_cleanup.json',
    'ice_cleanup_final':'scene/scene_ice_cleanup_02.json',
    'terrain_regressions':'cache_regressions/asset_cpu01/asset_result.json',
    'deterministic_parallel':'multicore/parallel_attempt01/parallel_component_result.json',
    'height_normal_shaders':'field_shader/attempt01/result.json',
    'terrain_shader':'terrain_shader01/result.json',
    'water_projector_shader':'water_shader02/result.json',
    'original_plan_claims':'plan_check_current_receipt.json'}


def write_new(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf8') as stream:json.dump(value,stream,indent=2);stream.write('\n')
    return common.artifact(path)


def functions(raw):
    tree=ast.parse(raw.decode('utf-8-sig'))
    return [ast.dump(node,include_attributes=False) for node in tree.body if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef))]


def tools():
    assert common.artifact(PARENT_REPORT)['sha256']==PARENT_SHA
    specs=[('build_menu_suite_host.py','c2b98422b87920096e3385b2f7ca39b8bbf817125ba7e7e69e3c18d980699d7c',[
        (b"STAGE = PROJECT / 'evidence/world_terrain_original/phase10/host_build_retry02'",b"STAGE = PROJECT / 'evidence/world_terrain_original/phase12/host_build'"),
        (b"PARENT_ID = '20261115T121456Z_dbb01a1f4f50'",b"PARENT_ID = '20261116T114748Z_014dd63ad3bc'"),
        (b"PARENT_SHA = '1334205b2b3cd302ffbd49f4e21184db103423d91c74fa721befc6f85cece07c'",b"PARENT_SHA = '3d5d63304d2076c2f309344e9103eb520875a5893282ed5abfff4104ef196b8d'"),
        (b"                   '20261115T134603Z_aa8853762399')",b"                   '20261115T134603Z_aa8853762399',\r\n                   '20261116T123457Z_90b98a574efc')")]),
        ('attest_prepared_menu_host.py','9eeb0f990b0e5a249ab9b6211d3e68d97d80023e77cfc4894d9c288175d877fb',[
            (b"STAGE = PROJECT / 'evidence/world_terrain_original/phase10/pair_preparation'",b"STAGE = PROJECT / 'evidence/world_terrain_original/phase12/pair_preparation'")])]
    result=[]
    for name,digest,replacements in specs:
        path=PROJECT/'tools'/name;before=common.artifact(path);raw=path.read_bytes();assert before['sha256']==digest
        changed=raw
        for old,new in replacements:assert changed.count(old)==1;changed=changed.replace(old,new)
        assert functions(raw)==functions(changed),'A build gate or executable body changed'
        inverse=changed
        for old,new in reversed(replacements):assert inverse.count(new)==1;inverse=inverse.replace(new,old)
        assert inverse==raw
        path.write_bytes(changed)
        result.append(dict(before=before,after=common.artifact(path),functions_classes_unchanged=True,inverse_bytes_equal=True,
            changes=[dict(old=o.decode(),new=n.decode()) for o,n in replacements]))
    template=PROJECT/'evidence/world_terrain_original/phase10/host_build_retry02/run_recorded_build.py'
    raw=template.read_bytes();old=b'evidence/world_terrain_original/phase10/host_build_retry02/plan.json'
    assert raw.count(old)==1
    target=STAGE/'host_build/run_recorded_build.py';target.parent.mkdir();assert not target.exists()
    target.write_bytes(raw.replace(old,b'evidence/world_terrain_original/phase12/host_build/plan.json'))
    write_new(STAGE/'tools_retarget.json',dict(status='PASS_CONSTANT_ONLY_BUILD_GATE_RETARGET',changes=result,
        controller=common.artifact(target),controller_parent=common.artifact(template),
        native_execution=False,default_global_or_runtime_selection_changed=False))
    print(json.dumps(dict(status='PASS_CONSTANT_ONLY_BUILD_GATE_RETARGET',tools=2,executable_gate_bodies_changed=False)))


def seal():
    assert common.artifact(PARENT_REPORT)['sha256']==PARENT_SHA
    parent=json.loads(OLD_MANIFEST.read_text('utf8'));assert len(parent['sources'])==466
    paths={common.key(row['path']):Path(row['path']) for row in parent['sources']}
    additions=[PROJECT/'Source/Presentation'/name for name in NEW_SOURCE]+[PROJECT/'Tests'/name for name in NEW_TESTS]
    additions += [STAGE/name for name in ('prepare_build.py','check_water_projector.py','run_regressions.py',
        'check_plan_current_preserving.py','work.py','tools_retarget.json','host_build/run_recorded_build.py')]
    for path in additions:assert path.is_file();paths[common.key(path)]=path
    assert all(p.suffix.lower()!='.md' and p.name!='current_work.json' for p in paths.values())
    proofs={}
    for name,relative in PROOFS.items():
        path=STAGE/relative;value=json.loads(path.read_text('utf8'))
        assert value['status'].startswith('PASS'),(name,value['status'])
        proofs[name]=dict(artifact=common.artifact(path),status=value['status'])
    component=write_new(STAGE/'component_receipts.json',dict(schema='zerosis.phase12.offline_component_binding.v1',
        status='PASS_CURRENT_CACHE_HEIGHT_REFLECTION_COMPONENTS_NATIVE_HOLD',proofs=proofs,
        production=['Original stamp truncation and raw height metrics','Known-only world-height and per-axis bounds',
            'Original material height origin and Y metric','Shared Raw producer/water-consumer projector'],
        component_only=['Original reflection bounds/axis projector','Original scratch resampling coordinates',
            'Original ice vertex/assets/VS; no fractured geometry or full PS provider'],
        original_placement='RULE_EQUIVALENCE_PLACEMENT_EQUIVALENCE_UNVERIFIED',
        original_six_asset_packs_reused=True,new_asset_packs_created=0,
        native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False,actual_runtime_or_visual_acceptance=False))
    requirements=write_new(STAGE/'requirements.json',dict(schema='zerosis.phase12.offline_requirements.v1',
        requested_items=[2,3],parent_host=PARENT_ID,parent_report_sha256=PARENT_SHA,
        claude_scope_preserved='4: bicubic basis, actual world camera and forest',
        native_game_and_screen_hold=True,compile_and_link_only=True,
        exact_integer_picking=True,unexplored_data_denied_before_read=True,
        save_abi_original_install_mods_settings_saves_default_and_global_unchanged=True,
        latest_prepared_runtime='20261116T123457Z_90b98a574efc',new_runtime_not_prepared_by_this_step=True,
        full_engine_goal_complete=False))
    code=[common.artifact(p) for p in paths.values() if any(p.is_relative_to(PROJECT/d) for d in ('Source','Tests','tools'))]
    freeze=write_new(STAGE/'source_freeze.json',dict(schema='zerosis.phase12.source_freeze.v1',
        status='PASS_CURRENT_SOURCE_AND_APPROVED_TESTS_FROZEN_FOR_COMPILE_ONLY',sources=code,
        component_receipts=component,mutable_docs_and_progress_excluded=True,native_execution=False))
    for row in (component,requirements,freeze):paths[common.key(row['path'])]=Path(row['path'])
    rows=[common.artifact(paths[name]) for name in sorted(paths)]
    future=PROJECT/'Build/UiWindowHost/20000101T000000Z_000000000000/frozen/project'
    longest=max(len(str(future/Path(row['path']).relative_to(PROJECT))) for row in rows)
    assert longest<260,('Future frozen path too long',longest)
    manifest=write_new(STAGE/'host_build/source_manifest.json',dict(schema='zerosis.phase12.cache_height_reflection.source_manifest.v1',
        sources=rows,previous_manifest=common.artifact(OLD_MANIFEST),offline_component_binding=component,
        max_future_frozen_path=longest,native_execution_allowed=False))
    write_new(STAGE/'manifest_preparation.json',dict(status='PASS_SOURCE_MANIFEST_SHORT_PROOFS_SEALED',
        utc=datetime.now(timezone.utc).isoformat(),generator=common.artifact(__file__),manifest=manifest,
        source_rows=len(rows),code_rows=len(code),parent_rows=466,additions=[str(p) for p in additions],
        longest_frozen_path=longest,compiler_linker_or_native_executed=False))
    print(json.dumps(dict(status='PASS_SOURCE_MANIFEST_SHORT_PROOFS_SEALED',rows=len(rows),code_rows=len(code),longest_frozen_path=longest)))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['tools','seal']);args=parser.parse_args()
    tools() if args.action=='tools' else seal()
