"""Seal current full metadata for the idle rendering source closure; no native execution."""
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
STAGE=Path(__file__).absolute().parent
PROJECT=STAGE.parents[2]
sys.path.insert(0,str(PROJECT/'tools'))
import build_exit_confirm_host as common

NAMES=[
    'Source/Presentation/WorldTerrainReuse.h','Source/Presentation/WorldTerrainRenderer.cpp',
    'Source/Presentation/WorldTerrainRenderer.h','Source/Presentation/WorldViewRenderer.cpp',
    'Source/Presentation/WorldViewRenderer.h','Source/Host/InteractiveGameLoop.h',
    'Tests/world_terrain_reuse.cpp','Tests/world_terrain_reuse.py','tools/attest_prepared_menu_host.py',
    'evidence/game_menu/idle_render_cache/work.py','evidence/game_menu/idle_render_cache/requirements.json',
    'evidence/game_menu/idle_render_cache/startup.json','evidence/game_menu/idle_render_cache/source_review.py',
    'evidence/game_menu/idle_render_cache/source_integration_review2.json',
    'evidence/game_menu/idle_render_cache/make_build_manifest.py',
    'evidence/game_menu/idle_render_cache/review_plan.py',
    'evidence/game_menu/idle_render_cache/finalize_records.py',
    'evidence/game_menu/idle_render_cache/independent_review.json',
    'evidence/game_menu/idle_render_cache/tests/result.json',
    'evidence/game_menu/idle_render_cache/verify_prepared_files.py',
    'evidence/game_menu/idle_render_cache/host_build/system_tool_selection.json',
    'evidence/game_menu/idle_render_cache/host_build/system_tool_signature.json']

def main():
    previous=PROJECT/'evidence/game_menu/native_slider_hover/host_build/source_manifest.json'
    prior=json.loads(previous.read_text('utf8'))
    paths={common.key(row['path']):Path(row['path']) for row in prior['sources']}
    for name in NAMES:
        path=PROJECT/name
        assert path.is_file() and path.is_relative_to(PROJECT),str(path)
        paths[common.key(path)]=path
    rows=[common.artifact(path) for _,path in sorted(paths.items())]
    assert all({'path','bytes','sha256','file_identity','mtime_ns','file_attributes','links'}<=set(row) for row in rows)
    assert not any(Path(row['path']).name in ('current_work.json','current_progress.json') for row in rows)
    output=STAGE/'host_build/source_manifest2.json';assert not output.exists()
    value=dict(schema='zerosis.idle_render_cache.source_manifest.v1',sources=rows,
        previous_manifest=common.artifact(previous),added_or_refreshed=NAMES,catalog_count=74,
        sidecar_files=154,sidecar_asset_root='Source/Assets/UIFrontEndV4',
        native_host_sdk_window_gpu_executed=False,no_mutable_current_progress_reports=True)
    with output.open('x',encoding='utf8') as f:json.dump(value,f,indent=2);f.write('\n')
    print(json.dumps(dict(status='PASS_CURRENT_FULL_METADATA_SOURCE_MANIFEST',sources=len(rows),previous=len(prior['sources']),artifact=common.artifact(output))))

if __name__=='__main__':main()
