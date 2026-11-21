"""Seal current sources for the graph-guide and authored-grid-cap UI wave."""
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
STAGE=Path(__file__).absolute().parent
PROJECT=STAGE.parents[2]
sys.path.insert(0,str(PROJECT/'tools'))
import build_exit_confirm_host as common


def main():
    previous=PROJECT/'evidence/game_menu/replay_scroll_graph/host_build/source_manifest_sealed.json'
    prior=json.loads(previous.read_text('utf8'))
    paths={common.key(row['path']):Path(row['path']) for row in prior['sources']}
    names=[
        'Source/Host/MenuReplayPointerGuides.h','Source/Host/MenuFrontEndGridLayout.h',
        'Source/Host/MenuReplayInputBatch.h','Source/Host/MenuLifecycleWindow.h',
        'Source/Host/MenuFrontEndAssets.h','Source/Host/MenuReplayPresentation.h',
        'Source/Presentation/BitmapWindow.h','Source/Presentation/BitmapWindow.cpp',
        'Tests/menu_replay_pointer_guides.cpp','Tests/menu_replay_pointer_guides.py',
        'Tests/menu_frontend_grid_layout.cpp','Tests/menu_frontend_grid_layout.py',
        'Tests/bitmap_current_pointer.cpp','Tests/bitmap_current_pointer.py',
        'Tests/menu_replay_input_batch.cpp','Tests/menu_replay_input_batch.py',
        'Tests/menu_replay_restored_scene.cpp','Tests/menu_replay_restoration.py',
        'evidence/game_menu/replay_hover_frame/work.py',
        'evidence/game_menu/replay_hover_frame/requirements.json',
        'evidence/game_menu/replay_hover_frame/make_build_manifest.py',
    ]
    for name in names:
        path=PROJECT/name;assert path.is_file() and path.is_relative_to(PROJECT),str(path)
        paths[common.key(path)]=path
    output=STAGE/'host_build/source_manifest_sealed.json'
    assert not output.exists();output.parent.mkdir(parents=True,exist_ok=True)
    rows=[common.artifact(path) for _,path in sorted(paths.items())]
    assert all(set(('path','bytes','sha256','file_identity','mtime_ns','file_attributes','links'))<=set(row) for row in rows)
    assert not any(Path(row['path']).name in ('current_work.json','current_progress.json') for row in rows)
    value=dict(schema='zerosis.replay_hover_frame.source_manifest.v1',sources=rows,catalog_count=74,sidecar_files=154,
        native_host_sdk_window_gpu_executed=False,no_mutable_current_progress_reports=True,
        source_identity_policy='Authenticated production artifact reader, real os.stat identity/mtime/attributes.')
    with output.open('x',encoding='utf8') as stream:json.dump(value,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(status='PASS_CURRENT_FULL_METADATA_SOURCE_MANIFEST',sources=len(rows),artifact=common.artifact(output))))


if __name__=='__main__':main()
