"""Full current artifact metadata for the original-terrain phase-one Host closure."""
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
STAGE=Path(__file__).absolute().parent;PROJECT=STAGE.parents[2]
sys.path.insert(0,str(PROJECT/'tools'))
import build_exit_confirm_host as common

NAMES=[
    'Source/Presentation/WorldTerrainRenderer.cpp','Source/Presentation/WorldTerrainRenderer.h',
    'Source/Presentation/WorldViewRenderer.h','Source/Presentation/WorldTerrainReuse.h',
    'Source/Host/WorldViewState.h','Source/Host/InteractiveGameLoop.h',
    'Tests/world_terrain_reuse.cpp','tools/attest_prepared_menu_host.py',
    'tools/civ5_original_terrain_assets.py',
    'evidence/world_terrain_original/phase1/requirements.json',
    'evidence/world_terrain_original/phase1/calibration_notes.json',
    'evidence/world_terrain_original/phase1/make_build_manifest.py',
    'evidence/world_terrain_original/phase1/review_build_plan.py',
    'evidence/world_terrain_original/phase1/assets/result.json',
    'evidence/world_terrain_original/phase1/assets/format.json',
    'evidence/world_terrain_original/phase1/model/result.json',
    'evidence/world_terrain_original/phase1/package_tests/result.json',
    'evidence/world_terrain_original/phase1/geometry_tests/result.json',
    'evidence/world_terrain_original/phase1/pipeline_tests/current/result.json',
    'evidence/world_terrain_original/phase1/shaders/retry01/result.json',
    'evidence/world_terrain_original/phase1/review/gpu_integration_review.json']

def main():
    previous=PROJECT/'evidence/game_menu/idle_render_cache/host_build/source_manifest2.json'
    prior=json.loads(previous.read_text('utf8'));paths={common.key(row['path']):Path(row['path']) for row in prior['sources']}
    names=NAMES+[p.relative_to(PROJECT).as_posix() for p in (PROJECT/'Source/Presentation').glob('OriginalTerrain*')]
    names+=[p.relative_to(PROJECT).as_posix() for p in (PROJECT/'Tests').glob('original_terrain*')]
    for name in names:
        path=PROJECT/name;assert path.is_file(),name;paths[common.key(path)]=path
    rows=[common.artifact(path) for _,path in sorted(paths.items())]
    assert not any(Path(row['path']).name in ('current_work.json','current_progress.json') for row in rows)
    output=STAGE/'host_build/source_manifest2.json';assert not output.exists();output.parent.mkdir(parents=True,exist_ok=True)
    value=dict(schema='zerosis.original_terrain.phase1.source_manifest.v1',sources=rows,
        previous_manifest=common.artifact(previous),added_or_refreshed=names,catalog_count=74,
        terrain_package_sha256='02104c582759bf0cefb58f97379699e45300eb2a9c6da6fdd3c65d1440cb84e8',
        native_host_sdk_window_gpu_executed=False,default_or_registration_changed=False,
        deployment='Compiled explicit V2 candidate and one terrain package; existing prepared runtimes unchanged.')
    with output.open('x',encoding='utf8') as f:json.dump(value,f,indent=2);f.write('\n')
    print(json.dumps(dict(status='PASS_CURRENT_FULL_METADATA_SOURCE_MANIFEST',sources=len(rows),artifact=common.artifact(output))))

if __name__=='__main__':main()
