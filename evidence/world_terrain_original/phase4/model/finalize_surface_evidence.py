"""Finalize the CPU surface contract and clean the one failed compile's owned intermediates."""
from __future__ import annotations
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[4]
sys.path.insert(0,str(PROJECT/'tools'))
from build_exit_confirm_host import artifact
from menu_suite_storage import storage
HERE=Path(__file__).absolute().parent


def write_new(path,value):
    with path.open('x',encoding='utf8',newline='\n') as stream:
        json.dump(value,stream,indent=1,ensure_ascii=False);stream.write('\n')


def main():
    old=HERE/'cpu';build=old/'build';rows=[]
    assert {path.name for path in build.iterdir()}=={'compile.rsp','read_build_environment.cmd'}
    for path in sorted(build.iterdir()):
        row=dict(artifact(path),allocated_bytes=storage.allocated(path));assert row['links']==1 and not row['file_attributes']&0x401
        rows.append(row)
    write_new(old/'cleanup_plan.json',dict(directory=str(build),files=rows,
        failure='C++ test used unary minus on unsigned loop index and int fill on uint8_t; test fixed, production header unchanged.',
        failed_test_source=artifact(old/'failed_original_water_surface.cpp.gz')))
    for row in rows:
        path=Path(row['path']);assert path.is_relative_to(build);now=artifact(path)
        assert all(now[key]==row[key] for key in ('bytes','sha256','file_identity','mtime_ns','file_attributes','links'));path.unlink()
    assert not any(build.iterdir());build.rmdir()
    cleanup=dict(status='PASS_EXACT_OWNED_FAILED_COMPILE_INTERMEDIATES_REMOVED',files=rows,deleted_files=len(rows),
        deleted_logical_bytes=sum(row['bytes'] for row in rows),released_unique_allocated_bytes=sum(row['allocated_bytes'] for row in rows))
    write_new(old/'cleanup_result.json',cleanup)
    current=HERE/'cpu_retry01/result.json';result=json.loads(current.read_text('utf8'))
    source=artifact(PROJECT/'Source/Presentation/OriginalWaterSurfaceModel.h')
    assert source['sha256']=='4c253c1b8d0d29f104974a93de61d96b7b04d60be4ec690334ff20ba95036a88'
    assert result['inputs_after'][0]==source
    proof=dict(schema='zerosis.original_water.phase4.current_surface_model.v1',status='PASS_CPU_FIXED_PLANE_HEIGHT_CONTOURS',
        production_header=source,current_component_result=artifact(current),checks=result['checks'],warnings=0,imports=result['imported_dlls'],
        type_contract=dict(namespace='ZeroSisPresentation::OriginalWater::Surface',
            vertex='OriginalWater::Vertex,32 bytes; x,y,z,u,v,kind,depth,flowSign',
            ranges='ownerCell is canonical 64x64 terrain CHUNK, not SDK plot ownership; start/count are nonindexed triangle-list vertices; kind0 water/kind1 shore',
            water_depth='Interpolated seabed raw h, with every height-crossing h=rawLevel exactly',
            water_height='(rawLevel-heightOffset)*worldScale, independent of seabed height',
            contours='Same snapped height crossings; waterCell/landCell are actual explored adjacent SDK cells; a/b are unmoved world-XZ centreline',
            shore='Only candidate width/UV; clipped into the known water/land hex pair; never writes original terrain heights or invents unknown height samples'),
        input_contract=dict(atlas='64*grid.width by64*grid.height,origin(-32,0),samewrap; existing source atlas reused by const reference',
            masks='SDK exploration and Atlas.known gate all height reads; every interior texel in a coarser sample quad is checked',
            known_nan='Any height whose SDK ownership and Atlas.known are known must be finite, including unused LOD corners',
            sdk_water='Height-clipped triangle is convex-clipped to explored water hexes; exact fragment picking remains a Root GPU responsibility'),
        equality_contract=dict(crossing='Source sample edge is oriented before interpolation; coordinate quantum2^-24 source texel',
            level_edge='Wet/dry side witnesses unioned in canonical segment map; coplanar or only-wet witnesses create no contour',
            periodic_key='Canonical periodic anchor plus directed unwrapped delta, orientation invariant; full-period nonzero segments remain nonzero'),
        bounds=dict(source_quads_at_full_resolution=67108864,source_triangles_at_full_resolution=134217728,
            plane_only_height_clip_worst_vertices_without_sdk_hex_partition=805306368,
            plane_only_unbounded_vertex_bytes=25769803776,
            note='SDK hex partition could increase that loose unbounded count; it is never allocated. Count pass aborts at configured output budget and retries explicit LOD.',
            max_output_vertices=2097152,max_output_vertex_bytes=67108864,max_contours=131072,
            max_contour_payload_bytes=8388608,max_ranges=32768,max_range_payload_bytes=524288,
            max_pending_map_entries_before_abort=262145,
            pending_payload_note='Key and contour payload are bounded; map allocator/node overhead is separate and no runtime peak-memory measurement is claimed',
            lod_steps=[1,2,4,8,16,32,64],initial_step=4,counted_before_vertex_allocation=True),
        preserved_sources=[artifact(PROJECT/'Source/Presentation/OriginalWaterModel.h'),artifact(PROJECT/'Source/Presentation/OriginalWaterState.h')],
        candidates=result['candidate_policies'],failed_attempt_cleanup=artifact(old/'cleanup_result.json'),
        host_sdk_clr_hwnd_gpu_audio_or_game_executed=False,gpu_depth_id_projection_native_screen_parity_verified=False)
    write_new(HERE/'current_surface.json',proof)
    print(json.dumps(dict(status=proof['status'],checks=proof['checks'],source_sha256=source['sha256'],cleaned_failed_files=len(rows))))


if __name__=='__main__':main()
