"""Aggregate the bounded reflection task's current evidence and storage totals."""
from pathlib import Path
import importlib.util
import json
import sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).absolute().parent
PROJECT=ROOT.parents[3]
spec=importlib.util.spec_from_file_location('reflection_final_reader',PROJECT/'evidence/world_terrain_original/phase10/reflection/water_pe_view.py')
reader=importlib.util.module_from_spec(spec);spec.loader.exec_module(reader)


def main():
    output=ROOT/'reflection_completion.json';assert not output.exists()
    relatives=['reflection_projection_contract.json','reflection_components02/reflection_result.json',
        'reflection_root_integration_review.json','reflection_water_regressions03/reflection_result.json']
    records=[json.loads((ROOT/name).read_text('utf8')) for name in relatives]
    assert all(item['status'].startswith('PASS') for item in records)
    for item in records[1]['inputs']:assert reader.ref(item['path'])==item
    for item in records[2]['inputs'].values():assert reader.ref(item['path'])==item
    metadata_only_changes=[]
    for item in records[3]['inputs']:
        current=reader.ref(item['path'])
        differences=[key for key in item if current[key]!=item[key]]
        assert not differences or differences==['mtime_ns'],str(item['path'])
        if differences:metadata_only_changes.append(dict(tested=item,current=current,reason='Timestamp only; tested bytes, SHA, identity and attributes remain identical.'))
    assert records[1]['checks']==144 and len(records[0]['instruction_checks'])==58 and len(records[2]['checks'])==20
    assert records[3]['total_checks']==1401219 and records[3]['carried_forward']['checks']==853718
    assert records[3]['results'][0]['checks']==547501
    cleanups=[]
    for stage in ['reflection_components01','reflection_components02','reflection_water_regressions01',
                  'reflection_water_regressions02','reflection_water_regressions03']:
        path=ROOT/stage/'reflection_cleanup_result.json';value=json.loads(path.read_text('utf8'))
        assert value['status'].startswith('PASS') and value['work_absent'] and not (path.parent/'work').exists()
        cleanups.append(dict(receipt=reader.ref(path),files=value.get('removed_files',value.get('files')),
            logical_bytes_removed=value['logical_bytes_removed'],allocated_bytes_removed=value['allocated_bytes_removed']))
    files=list(ROOT.rglob('*'));unique={}
    for path in files:
        if not path.is_file():continue
        info=path.stat();unique.setdefault((info.st_dev,info.st_ino),info.st_size)
    added=[PROJECT/'Source/Presentation/OriginalReflectionProjectionModel.h',PROJECT/'Tests/original_reflection_projection.cpp']
    result=dict(schema='zerosis.phase12.reflection_completion.v1',status='PASS_REFLECTION_STATIC_COMPONENT_AND_SHARED_CANDIDATE_INTEGRATION_WITH_HEIGHT_REGRESSIONS',
        scope='NoNative0',writer=reader.ref(Path(__file__).absolute()),evidence=[reader.ref(ROOT/name) for name in relatives],
        added_source_and_test=[reader.ref(path) for path in added],existing_shared_source_modified_by_this_agent=0,
        metadata_only_changes_after_cpu_check=metadata_only_changes,
        counts=dict(original_instruction_assertions=58,cpu_projection_checks=144,root_integration_review_conditions=20,
            water_surface_checks_reused=853718,water_bridge_checks=547501,water_height_total=1401219),
        previous_regression_failures=dict(attempt01='Stale centered-float atlas/oracle lacked raw16 metadata and explicit world origin.',
            attempt02='Remaining mutation delta/depth/colour assertions still used unquantized heights.',
            correction_owner='root; existing test oracles updated without loosening tolerances',closed_by=reader.ref(ROOT/relatives[-1])),
        limits=dict(original_frame_bounds_axis_provider=False,current_to_original_calibration=False,original_projector_production_enabled=False,
            original_water_plane_clipping=False,indexed_view_adjustment=False,d3dx_bitwise_parity=False,
            runtime_raw_camera='Explicit candidate mirror of current main VP, now shared exactly with Water consumer.',
            original_scene_providers='Current Raw supports visible units; wonders/landmarks/ice remain pending.',game_and_screen_checks='HELD'),
        cleanup=cleanups,cleanup_totals=dict(files=sum(row['files'] for row in cleanups),
            cumulative_intermediate_logical_bytes_removed=sum(row['logical_bytes_removed'] for row in cleanups),
            note='Cumulative per-attempt deletions are not a claim of an equal net free-space increase.'),
        retained_before_this_receipt=dict(files=sum(path.is_file() for path in files),unique_file_bytes=sum(unique.values()),
            source_test_bytes=sum(path.stat().st_size for path in added),whole_asset_or_project_copies=0,work_directories=0),
        native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False)
    with output.open('x',encoding='utf8') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(status=result['status'],cleanup=result['cleanup_totals'],retained=result['retained_before_this_receipt'],output=reader.ref(output))))


if __name__=='__main__':main()
