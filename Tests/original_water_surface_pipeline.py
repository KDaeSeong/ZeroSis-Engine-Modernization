"""Bounded 40x24 CPU surface/real-LEAN/optics integration plus unchanged ground-cache regression."""
from __future__ import annotations
import argparse
import gzip
import json
import os
from pathlib import Path
import re
import sys
import time

sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[1]
PHASE=PROJECT/'evidence/world_terrain_original/phase4'
PACKAGE_SHA='69c6780dbeb5f8605d8231cef944d0ec9392109b6ccc81a9d3b76ae83cfd0ef7'
PACKAGE=PROJECT/'Build/OriginalWaterLeanAssets'/PACKAGE_SHA/'water-lean-assets.bin'
sys.path[0:0]=[str(PROJECT/'tools'),str(PROJECT/'Tests')]
import build_exit_confirm_host as common
import world_terrain_reuse as original
from menu_replay_restoration import build_cxx14
from native_build import run
from menu_suite_storage import storage


def write_new(path,value):
    with path.open('x',encoding='utf8',newline='\n') as stream:
        json.dump(value,stream,indent=1,ensure_ascii=False);stream.write('\n')


def cleanup(build,stage,protected):
    rows=[]
    for path in sorted(build.iterdir()):
        assert path.is_file() and path.suffix in ('.exe','.obj','.map','.rsp','.cmd')
        row=dict(common.artifact(path),allocated_bytes=storage.allocated(path));assert row['links']==1 and not row['file_attributes']&0x401;rows.append(row)
    write_new(stage/'cleanup_plan.json',dict(directory=str(build),files=rows,protected_inputs=protected))
    for row in rows:
        path=Path(row['path']);assert path.is_relative_to(build);now=common.artifact(path)
        assert all(now[key]==row[key] for key in ('bytes','sha256','file_identity','mtime_ns','file_attributes','links'));path.unlink()
    assert not any(build.iterdir());build.rmdir()
    result=dict(status='PASS_EXACT_OWNED_CPU_INTERMEDIATES_REMOVED',files=rows,deleted_files=len(rows),
        deleted_logical_bytes=sum(row['bytes'] for row in rows),released_unique_allocated_bytes=sum(row['allocated_bytes'] for row in rows))
    write_new(stage/'cleanup_result.json',result);return result


def cache_regression():
    stage=PHASE/'cache_cpu';sources=[PROJECT/name for name in ('Tests/world_terrain_reuse.py','Tests/world_terrain_reuse.cpp',
        'Source/Presentation/WorldTerrainReuse.h','Source/Presentation/WorldViewRenderer.h','Source/Presentation/WorldTerrainRenderer.h',
        'Source/Presentation/WorldCameraControls.h','Source/Presentation/BitmapRenderer.h')]
    before=[common.artifact(path) for path in sources]
    complete=stage/'regression_result.json'
    if complete.exists():
        prior=json.loads(complete.read_text('utf8'));assert prior['inputs_after']==before
        assert prior['status']=='PASS_UNCHANGED_179_GROUND_CACHE_TESTS_WITH_SURFACE_DTO'
        return common.artifact(complete)
    assert not stage.exists() and not original.BUILD.exists(),'Inspect existing CPU cache attempt before another run'
    default_build=original.BUILD
    original.STAGE=stage # Only STAGE is overridden; original BUILD is retained.
    original.main()
    assert original.BUILD==default_build and not original.BUILD.exists()
    after=[common.artifact(path) for path in sources];assert after==before
    result=json.loads((stage/'result.json').read_text('utf8'));assert result['checks']==179
    assert result['status']=='PASS_ACTUAL_PRODUCTION_HEADER_CPU_CACHE_TESTS'
    assert result['build']['compiler_and_linker_warnings']==0 and {name.lower() for name in result['imported_dlls']}=={'kernel32.dll'}
    write_new(complete,dict(schema='zerosis.original_water.phase4.original_cache_regression.v1',
        status='PASS_UNCHANGED_179_GROUND_CACHE_TESTS_WITH_SURFACE_DTO',checks=179,
        original_result=common.artifact(stage/'result.json'),inputs_before=before,inputs_after=after,
        overridden_globals={'STAGE':str(stage)},unchanged_build_global=str(default_build),
        original_cpp_and_python_unmodified=True,host_sdk_clr_hwnd_gpu_audio_or_game_executed=False))
    return common.artifact(complete)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--attempt',type=int,default=0);args=parser.parse_args();assert 0<=args.attempt<=9
    assert not any(os.environ.get(name) for name in ('CL','_CL_','LINK'))
    cache=cache_regression()
    stage=PHASE/'pipeline'/('cpu' if args.attempt==0 else f'cpu_retry{args.attempt:02d}')
    assert not stage.exists(),'Inspect the existing pipeline before using a named retry'
    stage.mkdir(parents=True);build=stage/'build';build.mkdir()
    names=['Source/Presentation/OriginalWaterSurfaceModel.h','Source/Presentation/OriginalWaterOpticsModel.h',
        'Source/Presentation/OriginalWaterLeanPackage.h','Source/Presentation/OriginalWaterSurfaceBinding.h',
        'Source/Presentation/OriginalWaterState.h','Source/Presentation/OriginalWaterModel.h',
        'Source/Presentation/OriginalTerrainModel.h','Source/Presentation/OriginalTerrainBinding.h','Source/Presentation/OriginalTerrainSha256.h',
        'Source/Presentation/WorldTerrainReuse.h','Source/Presentation/WorldViewRenderer.h',
        'Source/Presentation/WorldCameraControls.h','Source/Presentation/BitmapRenderer.h',
        'Tests/original_water_surface_pipeline.cpp','Tests/original_water_surface_pipeline.py']
    before=[common.artifact(PROJECT/name) for name in names];packet_before=common.artifact(PACKAGE)
    assert before[0]['sha256']=='4c253c1b8d0d29f104974a93de61d96b7b04d60be4ec690334ff20ba95036a88'
    assert before[1]['sha256']=='7cdb4b6f35271e071d878b31bcdb019cbbf8c1b6384e6fc8ed2201db7d2d68ea'
    assert packet_before['sha256']==PACKAGE_SHA and packet_before['bytes']==3495363
    source=(PROJECT/names[-2]).read_text('ascii')
    assert source.count('T::Atlas atlas;')==1 and not re.search(r'\b(rand|srand|CreateWindow|D3D11CreateDevice|LoadLibrary)\s*\(',source)
    write_new(stage/'started.json',dict(inputs=before,sealed_lean_packet=packet_before,cache_regression=cache,
        dimensions=[40,24],atlas_dimensions=[2560,1536],revealed_plots=36,single_fixture_atlas=True,
        timeout_seconds=90,memory_limit_bytes=384*1024**2,
        self_process_memory_api='KERNEL32!K32GetProcessMemoryInfo(GetCurrentProcess()) only',
        host_sdk_clr_hwnd_gpu_audio_or_game_executed=False))
    compiled=None;executed=None;metrics=None;libraries=[];wall_seconds=None;failure=None
    try:
        compiled=build_cxx14('original_water_surface_pipeline',build,stage,PROJECT/names[-2],[PROJECT/'Source/Presentation'])
        imports=run([Path(compiled['compiler']).with_name('dumpbin.exe'),'/dependents',compiled['path']],cwd=build,timeout=30)
        libraries=sorted(set(re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$',imports.stdout.decode('mbcs',errors='replace'),re.M)))
        assert imports.returncode==0 and {name.lower() for name in libraries}=={'kernel32.dll'},libraries
        (stage/'imports.txt').write_text(imports.stdout.decode('mbcs',errors='replace'),encoding='utf8')
        executed=common.artifact(compiled['path']);started=time.perf_counter();done=run([compiled['path'],PACKAGE],cwd=build,timeout=90)
        wall_seconds=time.perf_counter()-started;stdout=done.stdout.decode('ascii');stderr=done.stderr.decode('ascii')
        (stage/'console.txt').write_text(stdout+stderr,encoding='ascii');match=re.fullmatch(r'PASS_ORIGINAL_WATER_SURFACE_PIPELINE (.+)\s*',stdout)
        assert done.returncode==0 and not stderr and match,(done.returncode,stdout,stderr)
        metrics={}
        for field in match[1].split():
            name,value=field.split('=',1);metrics[name]=value if name.endswith('_sha') else int(value)
        assert (metrics['width'],metrics['height'],metrics['revealed'],metrics['unknown_plots'])==(2560,1536,36,924)
        assert metrics['peak_working_set']<=metrics['memory_limit']==384*1024**2 and metrics['peak_commit']<=metrics['memory_limit']
        assert metrics['elapsed_ms']<=85000 and metrics['optics_samples']>=128 and metrics['key_checks']==22
    except BaseException as error:
        failure=error
        for name in names[-2:]:
            path=PROJECT/name;target=stage/('failed_'+path.name+'.gz')
            with target.open('xb') as stream:stream.write(gzip.compress(path.read_bytes(),mtime=0))
        write_new(stage/'failure.json',dict(error_type=type(error).__name__,message=str(error)[:6000],
            compiled=compiled,source_originals_modified=False,host_sdk_clr_hwnd_gpu_audio_or_game_executed=False))
    finally:
        after=[common.artifact(PROJECT/name) for name in names];packet_after=common.artifact(PACKAGE)
        assert before==after and packet_before==packet_after
        removed=cleanup(build,stage,after+[packet_after])
    if failure is not None:raise failure
    proof=dict(schema='zerosis.original_water.phase4.cpu_surface_optics_pipeline.v1',status='PASS_REAL_LEAN_40X24_FIXED_SURFACE_OPTICS_PIPELINE',
        metrics=metrics,wall_seconds=wall_seconds,inputs_before=before,inputs_after=after,
        sealed_lean_packet=packet_before,sealed_lean_packet_after=packet_after,cache_regression=cache,
        build=compiled,executed_console=executed,imported_dlls=libraries,cleanup=common.artifact(stage/'cleanup_result.json'),
        retained_console=False,single_large_fixture_atlas=True,large_atlas_extra_copies=0,raw_game_asset_copies=0,
        scenario='Real SHA-pinned water LEAN packet -> unscaled two-layer moments -> one explicit scale -> covariance/Gaussian -> analytic reflection-tap fixture/gamma; 40x24 detached DTO -> atlas -> fixed plane/contours',
        frame_cache='Actual ground key invalidates on plane mode/package changes and water package changes while plane mode active; surface grid key ignores presentation-only clock/camera',
        root_plane_float_matches=True,unknown_poison_preserves_vertex_range_contour_digest=True,
        explicit_candidates=['Header outputScale -> runtime S binding remains unverified; supplied CandidateOpticsPolicy.scale is explicit.',
            'CPU nearest texel selection and analytic reflection taps are fixtures; GPU sampler/scene reflection/refraction parity is not proven.',
            'Default surface level, offset/scale, LOD and coast width remain calibration candidates.'],
        host_sdk_clr_hwnd_gpu_audio_or_game_executed=False,gpu_or_native_frame_acceptance_verified=False)
    write_new(stage/'result.json',proof)
    print(json.dumps(dict(status=proof['status'],checks=metrics['checks'],peak_working_set=metrics['peak_working_set'],
        peak_commit=metrics['peak_commit'],elapsed_ms=metrics['elapsed_ms'],result=str(stage/'result.json'),
        cache_result=cache['path'],deleted_files=removed['deleted_files'],released_unique_allocated_bytes=removed['released_unique_allocated_bytes'])))


if __name__=='__main__':main()
