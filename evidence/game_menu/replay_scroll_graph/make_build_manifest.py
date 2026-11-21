"""Seal explicit current sources using the authenticated production file reader."""
from __future__ import annotations
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
STAGE=Path(__file__).absolute().parent
PROJECT=STAGE.parents[2]
sys.path.insert(0,str(PROJECT/'tools'))
import build_exit_confirm_host as common


def main():
    previous=PROJECT/'evidence/game_menu/replay_calendar_legend/host_build/source_manifest_sealed.json'
    prior=json.loads(previous.read_text('utf8'))
    paths={common.key(row['path']):Path(row['path']) for row in prior['sources']}
    names=[
        'Source/Host/MenuReplayScrollModel.h','Source/Host/MenuReplayGraphGeometry.h',
        'Source/Host/MenuReplayMessageViewport.h','Source/Host/MenuReplayInputBatch.h',
        'Source/Presentation/SceneLineContract.h','Source/Presentation/BitmapKeyPolicy.h',
        'Source/Presentation/BitmapRenderer.h','Source/Presentation/BitmapRenderer.cpp',
        'Source/Presentation/BitmapWindow.cpp','Source/Presentation/WorldViewRenderer.cpp',
        'Source/Host/MenuLifecycleWindow.h','tools/menu_frontend_cpu.py',
        'Tests/menu_replay_scroll_model.cpp','Tests/menu_replay_scroll_model.py',
        'Tests/menu_replay_graph_geometry.cpp','Tests/menu_replay_graph_geometry.py',
        'Tests/menu_replay_message_viewport.cpp','Tests/menu_replay_message_viewport.py',
        'Tests/menu_replay_input_batch.cpp','Tests/menu_replay_input_batch.py',
        'Tests/scene_line_contract.cpp','Tests/scene_line_contract.py',
        'Tests/menu_frontend_cpu_lines.py',
        'evidence/game_menu/replay_scroll_graph/work.py',
        'evidence/game_menu/replay_scroll_graph/requirements.json',
        'evidence/game_menu/replay_scroll_graph/make_build_manifest.py',
    ]
    for name in names:
        path=PROJECT/name
        assert path.is_file() and path.is_relative_to(PROJECT),str(path)
        paths[common.key(path)]=path
    output=STAGE/'host_build/source_manifest_sealed.json'
    assert not output.exists()
    output.parent.mkdir(parents=True,exist_ok=True)
    rows=[common.artifact(path) for _,path in sorted(paths.items())]
    assert all(set(('path','bytes','sha256','file_identity','mtime_ns','file_attributes','links'))<=set(row) for row in rows)
    assert not any(Path(row['path']).name in ('current_progress.json','current_work.json') for row in rows)
    value=dict(schema='zerosis.replay_scroll_graph.source_manifest.v1',sources=rows,
        catalog_count=74,sidecar_files=154,native_host_sdk_window_gpu_executed=False,
        no_mutable_current_progress_reports=True,
        source_identity_policy='Actual regular-file identity/mtime/attributes from the authenticated production artifact reader')
    with output.open('x',encoding='utf8') as stream:
        json.dump(value,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(status='PASS_CURRENT_FULL_METADATA_SOURCE_MANIFEST',source_count=len(rows),artifact=common.artifact(output))))


if __name__=='__main__':main()
