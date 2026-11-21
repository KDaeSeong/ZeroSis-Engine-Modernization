"""Seal current full metadata for the native offline follow-up Host source manifest (file-only)."""
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[2]
sys.path.insert(0, str(PROJECT / 'tools'))
import build_exit_confirm_host as common

NAMES = [
    # Production sources changed or added by this wave.
    'Source/Host/MenuFrontEndOptionsModel.h', 'Source/Host/UiPopupContext.h', 'Source/Host/UiLocaleArguments.h',
    # Controlled component checks and the asset/skin producers they bind.
    'Tests/menu_frontend_options_offline.cpp', 'Tests/menu_frontend_options_offline.py',
    'Tests/ui_locale_arguments.cpp', 'Tests/ui_locale_arguments.py',
    'Tests/menu_frontend_grid_layout.py', 'Tests/menu_replay_restoration.py',
    'Tests/menu_reward_options_view.py', 'Tests/menu_resolution_preview_view.py',
    'tools/menu_frontend_skin_pages.py', 'tools/menu_frontend_assets_v4.py', 'tools/attest_prepared_menu_host.py',
    # Retail static evidence and wave records.
    'evidence/game_menu/frontend_windowtrim/retail_image_probe.py',
    'evidence/game_menu/frontend_windowtrim/retail_image_probe.json',
    'evidence/game_menu/frontend_windowtrim/texture_facts.py',
    'evidence/game_menu/frontend_windowtrim/texture_facts.json',
    'evidence/game_menu/frontend_windowtrim/findings.json',
    'evidence/game_menu/native_offline_followup/work.py',
    'evidence/game_menu/native_offline_followup/startup.json',
    'evidence/game_menu/native_offline_followup/retail_slider_key_probe.py',
    'evidence/game_menu/native_offline_followup/retail_slider_key_probe.json',
    'evidence/game_menu/native_offline_followup/frontend_v4/assets_v4.json',
    'evidence/game_menu/native_offline_followup/frontend_v4_render_check.py',
    'evidence/game_menu/native_offline_followup/frontend_v4_render_check.json',
    'evidence/game_menu/native_offline_followup/make_build_manifest.py']


def main():
    previous = PROJECT / 'evidence/game_menu/replay_season_wheel/host_build/source_manifest.json'
    prior = json.loads(previous.read_text('utf8'))
    paths = {common.key(row['path']): Path(row['path']) for row in prior['sources']}
    for name in NAMES:
        path = PROJECT / name
        assert path.is_file() and path.is_relative_to(PROJECT), str(path)
        paths[common.key(path)] = path
    for path in paths.values():
        assert path.is_file(), 'A previous manifest source is absent: ' + str(path)
    output = STAGE / 'host_build/source_manifest.json'
    assert not output.exists()
    output.parent.mkdir(parents=True, exist_ok=True)
    rows = [common.artifact(path) for _, path in sorted(paths.items())]
    assert all({'path', 'bytes', 'sha256', 'file_identity', 'mtime_ns', 'file_attributes', 'links'} <= set(row) for row in rows)
    assert not any(Path(row['path']).name in ('current_work.json', 'current_progress.json') for row in rows)
    value = dict(schema='zerosis.native_offline_followup.source_manifest.v1', sources=rows, previous_manifest=common.artifact(previous),
                 added_or_refreshed=NAMES, catalog_count=74, sidecar_files=154,
                 sidecar_asset_root='Source/Assets/UIFrontEndV4',
                 native_host_sdk_window_gpu_executed=False, no_mutable_current_progress_reports=True,
                 source_identity_policy='Authenticated production artifact reader, real os.stat identity/mtime/attributes.')
    with output.open('x', encoding='utf8') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
    print(json.dumps(dict(status='PASS_CURRENT_FULL_METADATA_SOURCE_MANIFEST', sources=len(rows),
                          previous=len(prior['sources']), artifact=common.artifact(output))))


if __name__ == '__main__':
    main()
