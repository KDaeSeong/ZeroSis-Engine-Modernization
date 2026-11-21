"""Production geometry/cache CPU conformance and source-only seed capture gate."""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
import sys

sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[1]
STAGE=PROJECT/'evidence/world_terrain_original/phase1/geometry_tests'
BUILD=STAGE/'work'
MODEL_SHA='8152cd67c7e1e7eae59f28c901383df2e055a8350e3ebd2770a8000031677113'
sys.path[0:0]=[str(PROJECT/'tools'),str(PROJECT/'Tests')]
import build_exit_confirm_host as common
from menu_replay_restoration import build_cxx14
from native_build import run
from menu_suite_storage import storage

def write_new(path,value):
    with path.open('x',encoding='utf8') as stream:json.dump(value,stream,indent=2);stream.write('\n')

def seed_gate():
    paths=[PROJECT/name for name in ('Source/Host/WorldViewState.h','Source/Host/InteractiveGameLoop.h',
        'Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvDllPreGame.cpp','Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvPreGame.cpp')]
    world,present=[path.read_text('utf8') for path in paths[:2]]
    adapter,implementation=[path.read_bytes().decode('latin1') for path in paths[2:]]
    prefix=world[world.index('static WorldViewState Capture('):world.index('result.turn=game->GetGameTurn();')]
    checks=dict(one_pregame_seed_getter=prefix.count('pregame->mapRandomSeed()')==1,
        seed_value_assignment='result.mapRandomSeed=pregame->mapRandomSeed();' in prefix,
        no_seed_set_or_random_advance_in_capture_prefix=re.search(r'\b(?:rand|srand|setMapRandomSeed|GetMapRand|GetSorenRand|setSyncRandomSeed)\s*\(',prefix) is None,
        presentation_copies_detached_seed='result.mapRandomSeed=state.mapRandomSeed;' in present,
        adapter_returns_value_getter=re.search(r'unsigned int CvDllPreGame::mapRandomSeed\(\)\s*\{\s*return CvPreGame::mapRandomSeed\(\);\s*\}',adapter) is not None,
        implementation_returns_seed_field=re.search(r'unsigned int mapRandomSeed\(\)\s*\{\s*return s_mapRandomSeed;\s*\}',implementation) is not None)
    assert all(checks.values()),checks
    return dict(status='PASS_SOURCE_ONLY_SEED_VALUE_TRANSPORT_NO_RNG_ADVANCE',checks=checks,sources=[common.artifact(path) for path in paths],
        gamecore_executed=False,scope='Source bodies only; no real GameCore/RNG/native execution occurred.')

def main():
    assert not BUILD.exists() and not(STAGE/'result.json').exists(),'Inspect the existing owned attempt before retrying'
    assert not any(os.environ.get(name) for name in ('CL','_CL_','LINK'))
    STAGE.mkdir(parents=True,exist_ok=True);BUILD.mkdir()
    names=['Source/Presentation/OriginalTerrainModel.h','Source/Presentation/OriginalTerrainGeometry.h',
        'Source/Presentation/WorldTerrainReuse.h','Source/Presentation/WorldViewRenderer.h','Source/Presentation/WorldCameraControls.h',
        'Source/Presentation/BitmapRenderer.h','Tests/original_terrain_geometry.cpp','Tests/original_terrain_geometry.py']
    before=[common.artifact(PROJECT/name) for name in names];assert before[0]['sha256']==MODEL_SHA
    write_new(STAGE/'started.json',dict(inputs=before,native_host_sdk_gpu_executed=False))
    gate=seed_gate();write_new(STAGE/'seed_capture_static.json',gate)
    compiled=build_cxx14('original_terrain_geometry',BUILD,STAGE,PROJECT/'Tests/original_terrain_geometry.cpp',[PROJECT/'Source/Presentation'])
    imports=run([Path(compiled['compiler']).with_name('dumpbin.exe'),'/dependents',compiled['path']],cwd=BUILD,timeout=30)
    libraries=sorted(set(re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$',imports.stdout.decode('mbcs',errors='replace'),re.M)))
    assert imports.returncode==0 and {name.lower() for name in libraries}=={'kernel32.dll'},libraries
    executable=common.artifact(compiled['path']);output=run([compiled['path']],cwd=BUILD,timeout=60)
    stdout=output.stdout.decode('ascii');stderr=output.stderr.decode('ascii')
    match=re.fullmatch(r'PASS_ORIGINAL_TERRAIN_GEOMETRY checks=(\d+) polygon_samples=(\d+) shared_triangle_tiles=2\s*',stdout)
    assert output.returncode==0 and not stderr and match,(output.returncode,stdout,stderr)
    after=[common.artifact(PROJECT/name) for name in names];assert before==after
    assert [common.artifact(row['path']) for row in gate['sources']]==gate['sources']
    rows=[]
    for path in sorted(BUILD.iterdir()):
        assert path.is_file() and path.suffix in ('.exe','.obj','.map','.rsp','.cmd')
        row=common.artifact(path);assert row['links']==1 and not row['file_attributes']&0x401
        row['allocated_bytes']=storage.allocated(path);rows.append(row)
    write_new(STAGE/'cleanup_plan.json',dict(directory=str(BUILD),files=rows,protected_sources=after))
    for row in rows:
        now=common.artifact(row['path']);assert all(now[k]==row[k] for k in ('bytes','sha256','file_identity','mtime_ns','file_attributes','links'))
        Path(row['path']).unlink()
    assert not any(BUILD.iterdir());BUILD.rmdir()
    cleanup=dict(status='PASS_EXACT_OWNED_GEOMETRY_CPU_INTERMEDIATES_REMOVED',files=rows,deleted_files=len(rows),
        released_unique_allocated_bytes=sum(row['allocated_bytes'] for row in rows))
    write_new(STAGE/'cleanup_result.json',cleanup)
    proof=dict(status='PASS_PRODUCTION_CPP14_TERRAIN_GEOMETRY_PICKING_AND_INFORMATION_BOUNDARY',checks=int(match[1]),
        polygon_samples=int(match[2]),shared_one_texel_triangle_distinct_tile_owners=2,
        reference='Independent integer six-triangle hex polygons, boundary-inclusive ownership sets; exact sqrt(3)/2 reference spacing.',
        cases=['grid64 source/cube/offset/world roundtrips, negative rows and map wrapping/outside',
            'per-fragment world picking across one shared global-grid triangle',
            'unknown terrain/NW/continent mutation leaves cells, full atlas and sampled heights unchanged',
            'unknown NaN heights/IDs ignored; revealed invisible terrain retained',
            'bad map/plot identity, incomplete atlas and nonfinite height coordinates rejected',
            'map seed, natural-wonder and terrain-ID cache invalidation'],
        source_seed_gate=common.artifact(STAGE/'seed_capture_static.json'),inputs_before=before,inputs_after=after,
        build=compiled,executed_console=executable,imported_dlls=libraries,cleanup=common.artifact(STAGE/'cleanup_result.json'),
        native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False,gpu_pixel_id_or_original_game_parity_verified=False)
    write_new(STAGE/'result.json',proof)
    print(json.dumps({key:proof[key] for key in ('status','checks','polygon_samples','shared_one_texel_triangle_distinct_tile_owners')}))

if __name__=='__main__':main()
