"""Seal current full metadata for the replay season/wheel Host source manifest (file-only)."""
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[2]
sys.path.insert(0, str(PROJECT / 'tools'))
import build_exit_confirm_host as common


def main():
    previous = PROJECT / 'evidence/game_menu/options_reward_popups/host_build/source_manifest_final.json'
    prior = json.loads(previous.read_text('utf8'))
    paths = {common.key(row['path']): Path(row['path']) for row in prior['sources']}
    names = ['Source/Host/HostRun.h', 'Source/Host/MenuReplayCalendar.h', 'Source/Host/MenuReplayScrollModel.h',
             'Source/Host/MenuReplayPresentation.h',
             'Tests/menu_replay_calendar.py', 'Tests/menu_replay_calendar.cpp',
             'Tests/menu_replay_scroll_model.py', 'Tests/menu_replay_scroll_model.cpp',
             'Tests/menu_replay_restoration.py', 'Tests/menu_replay_restored_scene.cpp',
             'Tests/menu_replay_input_batch.py', 'tools/attest_prepared_menu_host.py',
             'evidence/game_menu/replay_season_wheel/work.py',
             'evidence/game_menu/replay_season_wheel/retail_static_probe.py',
             'evidence/game_menu/replay_season_wheel/retail_static_probe.json',
             'evidence/game_menu/replay_season_wheel/startup.json',
             'evidence/game_menu/replay_season_wheel/source_before.json',
             'evidence/game_menu/replay_season_wheel/receipts_before.json',
             'evidence/game_menu/replay_season_wheel/tools_before.json',
             'evidence/game_menu/replay_season_wheel/make_build_manifest.py']
    for name in names:
        path = PROJECT / name
        assert path.is_file() and path.is_relative_to(PROJECT), str(path)
        paths[common.key(path)] = path
    output = STAGE / 'host_build/source_manifest.json'
    assert not output.exists()
    output.parent.mkdir(parents=True, exist_ok=True)
    rows = [common.artifact(path) for _, path in sorted(paths.items())]
    assert all({'path', 'bytes', 'sha256', 'file_identity', 'mtime_ns', 'file_attributes', 'links'} <= set(row) for row in rows)
    assert not any(Path(row['path']).name in ('current_work.json', 'current_progress.json') for row in rows)
    value = dict(schema='zerosis.replay_season_wheel.source_manifest.v1', sources=rows, previous_manifest=common.artifact(previous),
                 added_or_refreshed=names, catalog_count=74, sidecar_files=154,
                 native_host_sdk_window_gpu_executed=False, no_mutable_current_progress_reports=True,
                 source_identity_policy='Authenticated production artifact reader, real os.stat identity/mtime/attributes.')
    with output.open('x', encoding='utf8') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
    print(json.dumps(dict(status='PASS_CURRENT_FULL_METADATA_SOURCE_MANIFEST', sources=len(rows),
                          previous=len(prior['sources']), artifact=common.artifact(output))))


if __name__ == '__main__':
    main()
