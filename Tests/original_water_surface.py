"""Strict CPU-only fixed-plane surface, contour, privacy and bounded-LOD checks."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import sys

sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[1]
ROOT=PROJECT/'evidence/world_terrain_original/phase4/model'
sys.path.insert(0,str(PROJECT/'tools'));sys.path.insert(0,str(PROJECT/'Tests'))
import build_exit_confirm_host as common
from menu_replay_restoration import build_cxx14
from native_build import run
from menu_suite_storage import storage


def write_new(path,value):
    with path.open('x',encoding='utf8',newline='\n') as stream:
        json.dump(value,stream,indent=1,ensure_ascii=False);stream.write('\n')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--attempt',type=int,default=0);args=parser.parse_args();assert 0<=args.attempt<=9
    stage=ROOT/('cpu' if args.attempt==0 else f'cpu_retry{args.attempt:02d}')
    assert not stage.exists(),'Inspect the original attempt, resolve the cause, then use a named retry'
    assert not any(os.environ.get(name) for name in ('CL','_CL_','LINK'))
    stage.mkdir(parents=True);build=stage/'build';build.mkdir()
    inputs=[PROJECT/name for name in ('Source/Presentation/OriginalWaterSurfaceModel.h','Source/Presentation/OriginalWaterModel.h',
        'Source/Presentation/OriginalWaterState.h','Source/Presentation/OriginalTerrainModel.h','Source/Presentation/OriginalTerrainBinding.h',
        'Tests/original_water_surface.cpp','Tests/original_water_surface.py')]
    before=[common.artifact(path) for path in inputs]
    assert before[1]['sha256']=='75552fe2a8002772795c0fa6d14c396ee566615e826b4d627815bfc7b6b59ba4'
    assert before[2]['sha256']=='1c064d632cc056f1de81204dbaaf000061ef5067c5cbb04abf3157e6eca8c6ee'
    text=inputs[0].read_text('ascii')
    assert not re.search(r'\b(rand|srand|CreateWindow|D3D11CreateDevice|LoadLibrary|GetProcAddress)\s*\(',text)
    assert 'WorldViewRenderer.h' not in text and 'OriginalWaterPackage.h' not in text
    write_new(stage/'started.json',dict(inputs=before,host_sdk_clr_hwnd_gpu_audio_or_game_execution=False,
        independent_oracles=['Fully wet rectangle area','Regular hexagon half area cut by a linear height slope',
            'Exact level-edge contour total length','Circle-area convergence under explicit triangle-grid LOD',
            'Canonical contour graph degree on ordinary and periodic narrow maps',
            'Guarded unknown texel NaN/Inf and inactive material IDs do not change output']))
    compiled=build_cxx14('original_water_surface',build,stage,inputs[-2],[PROJECT/'Source/Presentation'])
    imports=run([Path(compiled['compiler']).with_name('dumpbin.exe'),'/dependents',compiled['path']],cwd=build,timeout=30)
    names=sorted(set(re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$',imports.stdout.decode('mbcs',errors='replace'),re.M)))
    assert imports.returncode==0 and {name.lower() for name in names}=={'kernel32.dll'},names
    (stage/'imports.txt').write_text(imports.stdout.decode('mbcs',errors='replace'),encoding='utf8')
    executed=common.artifact(compiled['path']);done=run([compiled['path']],cwd=build,timeout=180)
    stdout=done.stdout.decode('ascii');stderr=done.stderr.decode('ascii');(stage/'console.txt').write_text(stdout+stderr,encoding='ascii')
    match=re.fullmatch(r'PASS_ORIGINAL_WATER_SURFACE checks=(\d+)\s*',stdout)
    assert done.returncode==0 and not stderr and match,(done.returncode,stdout,stderr)
    after=[common.artifact(path) for path in inputs];assert before==after
    rows=[]
    for path in sorted(build.iterdir()):
        assert path.is_file() and path.suffix in ('.exe','.obj','.map','.rsp','.cmd')
        row=dict(common.artifact(path),allocated_bytes=storage.allocated(path));assert row['links']==1 and not row['file_attributes']&0x401;rows.append(row)
    write_new(stage/'cleanup_plan.json',dict(directory=str(build),files=rows,protected_inputs=after,exact_owned_intermediates_only=True))
    for row in rows:
        path=Path(row['path']);assert path.is_relative_to(build);actual=common.artifact(path)
        assert all(actual[key]==row[key] for key in ('bytes','sha256','file_identity','mtime_ns','file_attributes','links'));path.unlink()
    assert not any(build.iterdir());build.rmdir()
    cleanup=dict(status='PASS_EXACT_OWNED_CPU_INTERMEDIATES_REMOVED',files=rows,deleted_files=len(rows),
        deleted_logical_bytes=sum(row['bytes'] for row in rows),released_unique_allocated_bytes=sum(row['allocated_bytes'] for row in rows),protected_inputs_unchanged=True)
    write_new(stage/'cleanup_result.json',cleanup)
    result=dict(schema='zerosis.original_water.phase4.surface_cpu.v1',status='PASS_FIXED_WATER_PLANE_AND_HEIGHT_CONTOURS_CXX14',
        checks=int(match[1]),inputs_before=before,inputs_after=after,build=compiled,executed_console=executed,imported_dlls=names,
        cleanup=common.artifact(stage/'cleanup_result.json'),retained_test_executable=False,
        original_input_sources_unchanged=True,host_sdk_clr_hwnd_gpu_audio_or_game_executed=False,gpu_id_depth_and_native_parity_verified=False,
        plane_contract='Vertex.y=(rawLevel-heightOffset)*worldScale; water Vertex.depth preserves interpolated seabed raw h; crossings use rawLevel exactly',
        topology_contract='Same terrain triangle diagonal, height clipping then exact explored SDK water-hex clipping; shoreline from the same raw crossings with actual known shared land-water neighbors',
        equality_policy='Level edges emitted once only with wet and dry side witnesses; coplanar faces do not emit contours',
        privacy='Grid exploration and Atlas.known gate before height read, including every interior texel of coarser LOD quads; unknown NaN/Inf/material values excluded',
        limits=dict(max_cells=16384,max_atlas_texels=67108864,max_vertices=2097152,max_contours=131072,initial_step=4,allowed_steps=[1,2,4,8,16,32,64]),
        candidate_policies=['Default waterline .19836, height offset and scale calibration.',
            '2^-24 source-texel coordinate snapping, 1e-12 source-area degeneracy threshold.',
            'Default step4 or caller step1 followed by power-of-two adaptive count pass; precision and topology differ from full resolution.',
            'Coast width .08 and UV scale; nearest actual known land neighbor tags the raw contour without moving its centreline.',
            'Nonwrapped border samples require valid explored SDK ownership; endpoint index extension clamps only the last original texel.',
            'CPU plane/contours do not prove GPU depth, exact picking, projection, optics, refraction or original screen parity.'])
    write_new(stage/'result.json',result)
    print(json.dumps(dict(status=result['status'],checks=result['checks'],result=str(stage/'result.json'),
        deleted_files=len(rows),released_unique_allocated_bytes=cleanup['released_unique_allocated_bytes'])))


if __name__=='__main__':main()
