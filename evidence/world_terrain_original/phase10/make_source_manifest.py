"""Freeze phase-ten source and short offline receipts; never compile or launch."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,os,re,sys

sys.dont_write_bytecode=True
STAGE=Path(__file__).absolute().parent
PROJECT=STAGE.parents[2]
PARENT=PROJECT/'evidence/world_terrain_original/phase8/host_build_retry01/source_manifest.json'
HOST_ID='20261115T121456Z_dbb01a1f4f50'
HOST_SHA='1334205b2b3cd302ffbd49f4e21184db103423d91c74fa721befc6f85cece07c'
NEW_SOURCE=[
    'DeterministicWorkerPool.h','OriginalCameraModel.h','OriginalForestModel.h','OriginalForestShader.h',
    'OriginalReflectionContract.h','OriginalScreenLightPackage.h','OriginalTerrainCacheModel.h',
    'OriginalTerrainTessellationModel.h','OriginalTerrainTessellationShader.h',
    'OriginalTerrainVertexPreparation.h','OriginalWaterBlendModel.h','OriginalWaterBlendState.h',
    'WorldCameraControls.h']
NEW_TESTS=[
    'deterministic_terrain_vertices.cpp','deterministic_terrain_vertices.py',
    'original_forest_tessellation.cpp','original_forest_tessellation.py',
    'original_screen_light_package.cpp','original_terrain_cache.cpp','original_terrain_cache.py',
    'original_water_blend.cpp']
PROOFS={
    'cache_model_cpu':'cache/cache_cpu/attempt01/cache_result.json',
    'cache_original_view':'cache/cache_view_contract.json',
    'cache_owner_correction':'cache/cache_owner_contract.json',
    'cache_original_matrix':'cache/cache_matrix_reference.json',
    'cache_legacy_model_geometry':'cache_regressions/asset_cpu01/asset_result.json',
    'cache_test_direction_update':'cache/cache_test_direction_update.json',
    'cache_build_tool_retarget':'cache/cache_build_tools_retarget.json',
    'camera_static_contract':'geometry/camera_retail_contract.json',
    'forest_static_contract':'geometry/forest_assets_contract.json',
    'forest_tessellation_cpu':'geometry/forest_tessellation_cpu_attempt01/result.json',
    'forest_tessellation_shader':'geometry/shader02/result.json',
    'terrain_shader':'terrain_shader01/result.json',
    'deterministic_multicore_cpu':'multicore/parallel_attempt04/parallel_component_result.json',
    'multicore_production_review':'multicore/parallel_production_callpath_review.json',
    'water_screen_light_cpu_shader':'reflection/water_components07/water_result.json',
    'screen_light_package_cpu':'reflection/water_package_cpu01/water_result.json',
    'reflection_completion':'reflection/water_completion.json',
    'reflection_source_frozen':'reflection/water_source_frozen.json',
    'original_68_claims':'plan_check_current_receipt.json'}


def key(path):return os.path.normcase(str(Path(path).absolute()))


def artifact(path):
    path=Path(path).absolute()
    assert path.is_relative_to(PROJECT) and path.is_file()
    for parent in (path,*path.parents):assert not parent.lstat().st_file_attributes&0x400
    before=path.stat()
    with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    after=path.stat()
    fields=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_file_attributes,s.st_nlink)
    assert fields(before)==fields(after),path
    return dict(path=str(path),bytes=after.st_size,sha256=digest,file_identity=[after.st_dev,after.st_ino],
                mtime_ns=after.st_mtime_ns,file_attributes=after.st_file_attributes,links=after.st_nlink)


def read(path):return json.loads(Path(path).read_text(encoding='utf8'))


def write_new(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf8',newline='\n') as stream:json.dump(value,stream,indent=2);stream.write('\n')
    return artifact(path)


def proposed_sources():
    parent=read(PARENT);assert len(parent['sources'])==431
    rows={key(row['path']):Path(row['path']) for row in parent['sources']}
    assert len(rows)==431
    additions=[PROJECT/'Source/Presentation'/name for name in NEW_SOURCE]
    additions += [PROJECT/'Tests'/name for name in NEW_TESTS]
    additions += [Path(__file__).absolute(),STAGE/'check_plan_preserving.py',STAGE/'check_plan_current_preserving.py']
    for path in additions:
        assert path.is_file(),path
        rows[key(path)]=path
    assert not any(path.suffix.lower()=='.md' or path.name in ('current_work.json','progress.json') for path in rows.values())
    return parent,rows,additions


def proof(path):
    value=read(path);status=value.get('status')
    if status is None and Path(path).name=='cache_matrix_reference.json':
        assert artifact(path)['sha256']=='15c6db3798908ca27c9f4eee414b25746a8a8a8f201e827524665a6c538afca6'
        assert value['original_binary_executed'] is False and len(value['orientation_matrices'])==4
        status='PASS_PINNED_ORIGINAL_MATRIX_DAG_REFERENCE_CONSUMED_BY_CPU_GOLDENS'
    assert isinstance(status,str) and status.startswith('PASS'),(path,status)
    result=dict(artifact=artifact(path),status=status)
    for field in ('checks','cases','assertions','rejection_fixtures','rejections','compiled_stages','strict_stages'):
        item=value.get(field)
        if isinstance(item,(int,str,bool)):result[field]=item
        elif isinstance(item,(list,dict)):result[field+'_count']=len(item)
    return result


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--seal',action='store_true')
    cli.add_argument('--reflection-review',type=Path)
    cli.add_argument('--reflection-review-sha256')
    args=cli.parse_args()
    assert sys.dont_write_bytecode and __debug__
    parent,paths,additions=proposed_sources()
    if not args.seal:
        print(json.dumps(dict(status='PREPARED_NOT_SEALED_AWAITING_FINAL_REFLECTION_REVIEW',
            parent_rows=431,explicit_new_source=len(NEW_SOURCE),explicit_new_tests=len(NEW_TESTS),
            proposed_rows_before_short_receipts=len(paths),generator=artifact(Path(__file__)),
            source_or_tools_modified=False,native_execution=False)))
        return
    assert args.reflection_review and re.fullmatch('[0-9a-f]{64}',args.reflection_review_sha256 or '')
    review=args.reflection_review.absolute();assert review.is_relative_to(STAGE/'reflection')
    assert artifact(review)['sha256']==args.reflection_review_sha256
    targets=[STAGE/'component_receipts.json',STAGE/'requirements.json',STAGE/'source_freeze.json',
             STAGE/'host_build/source_manifest.json',STAGE/'manifest_preparation.json']
    assert all(not path.exists() for path in targets),'Preserve sealed evidence; do not replay'
    expected_tools={'build_menu_suite_host.py':'326f37dbcba536ad8aba7efd78d3c7a4f8ccd1e44a09252f740c9ee44e515ce4',
        'attest_prepared_menu_host.py':'9eeb0f990b0e5a249ab9b6211d3e68d97d80023e77cfc4894d9c288175d877fb'}
    for name,digest in expected_tools.items():assert artifact(PROJECT/'tools'/name)['sha256']==digest
    host_report=PROJECT/'evidence/ui_window_host'/HOST_ID/'build_result.json'
    assert artifact(host_report)['sha256']==HOST_SHA
    before={name:artifact(path) for name,path in paths.items()}
    proofs={name:proof(STAGE/relative) for name,relative in PROOFS.items()}
    proofs['final_reflection_review']=proof(review)
    assert read(STAGE/PROOFS['cache_model_cpu'])['checks']==366342
    assert read(STAGE/PROOFS['cache_legacy_model_geometry'])['checks']==90876
    assert read(STAGE/'plan_check_current_receipt.json')['checks']==68
    component=write_new(targets[0],dict(schema='zerosis.phase10.offline_component_binding.v1',
        status='PASS_REQUESTED_OFFLINE_COMPONENTS_CURRENT_SOURCE_NATIVE_HOLD',proofs=proofs,
        original_terrain_provider_correction='t9 specscreenmap.dds: chunk owner=primary+8; water reflection remains separate.',
        original_placement='RULE_EQUIVALENCE_PLACEMENT_EQUIVALENCE_UNVERIFIED',
        existing_five_asset_packages_reused=True,new_static_screen_light_mask_separate=True,
        native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False,real_game_or_visual_acceptance=False))
    requirements=write_new(targets[1],dict(schema='zerosis.phase10.offline_requirements.v1',
        requested_items=[2,3,4,7],parent_host=HOST_ID,parent_report_sha256=HOST_SHA,
        scope=['Original cache views and piece transform','Reflection provider and water composition',
               'Original forest metadata and recoverable tessellation/camera formulas','Deterministic useful CPU parallel work'],
        preserve=['Original installation','MODS','settings','saves','default launch','global registration','SDK save ABI'],
        required_runtime_roots=['20261115T134603Z_aa8853762399','20261115T101941Z_99b3c393ee9a',
            '20261115T011241Z_4c8fd55e99db','20261108T003146Z_40a8030edf08'],
        native_host_sdk_clr_hwnd_gpu_audio_game_and_cua_allowed=False,compiler_linker_only_when_root_applies_plan=True,
        picking_integer_identity_preserved=True,unexplored_information_must_not_be_sampled=True,
        actual_gameplay_or_screen_verification_pending=True,full_engine_goal_complete=False))
    after={name:artifact(path) for name,path in paths.items()};assert after==before,'Source changed while receipts were read'
    code=[row for row in before.values() if Path(row['path']).is_relative_to(PROJECT/'Source') or
          Path(row['path']).is_relative_to(PROJECT/'Tests') or Path(row['path']).is_relative_to(PROJECT/'tools')]
    freeze=write_new(targets[2],dict(schema='zerosis.phase10.source_freeze.v1',
        status='PASS_CURRENT_CODE_AND_APPROVED_TESTS_FROZEN_FOR_COMPILE_ONLY',sources=code,
        component_receipts=component,source_or_tests_modified_by_generator=False,
        mutable_docs_and_current_progress_excluded=True,native_execution=False))
    for reference in (component,requirements,freeze):paths[key(reference['path'])]=Path(reference['path'])
    rows=[artifact(paths[name]) for name in sorted(paths)]
    dummy=PROJECT/'Build/UiWindowHost/20000101T000000Z_000000000000/frozen/project'
    longest=max(len(str(dummy/Path(row['path']).relative_to(PROJECT))) for row in rows)
    assert longest<260,('Frozen path exceeds reviewed limit',longest)
    manifest=write_new(targets[3],dict(schema='zerosis.phase10.requested_render_cache_multicore.source_manifest.v1',
        sources=rows,offline_component_binding=component,max_future_frozen_path=longest,
        native_execution_allowed=False,parent_source_manifest=artifact(PARENT)))
    original={key(row['path']):row for row in parent['sources']}
    changed=[row['path'] for row in rows if key(row['path']) in original and
        (row['bytes'],row['sha256'])!=(original[key(row['path'])]['bytes'],original[key(row['path'])]['sha256'])]
    new=[row['path'] for row in rows if key(row['path']) not in original]
    receipt=write_new(targets[4],dict(schema='zerosis.phase10.source_manifest_preparation.v1',
        status='PASS_EXPLICIT_PARENT_ROWS_PLUS_NEW_SOURCES_AND_SHORT_COMPONENT_RECEIPTS',
        generator=artifact(Path(__file__)),manifest=manifest,parent_manifest=artifact(PARENT),
        parent_rows=431,source_rows=len(rows),changed_existing=changed,new_sources=new,removals=[],
        component_receipts=component,requirements=requirements,source_freeze=freeze,
        mutable_documents_or_progress_included=False,source_or_test_bytes_modified=False,
        compiler_linker_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False))
    print(json.dumps(dict(status='PASS_SOURCE_MANIFEST_AND_SHORT_COMPONENT_RECEIPTS_SEALED',
        rows=len(rows),changed=len(changed),new=len(new),max_future_frozen_path=longest,
        manifest=manifest,preparation=receipt)))


if __name__=='__main__':main()
