"""Seal full current metadata after all reward-option source work ends."""
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
STAGE=Path(__file__).absolute().parent
PROJECT=STAGE.parents[2]
sys.path.insert(0,str(PROJECT/'tools'))
import build_exit_confirm_host as common


def main():
    previous=PROJECT/'evidence/game_menu/options_video_preview/host_build/source_manifest_sealed.json'
    prior=json.loads(previous.read_text('utf8'))
    paths={common.key(row['path']):Path(row['path']) for row in prior['sources']}
    names=['Source/Host/MenuOptionsContract.h','Source/Host/MenuOptionsStore.h','Source/Host/MenuOptionsHostBinding.h',
        'Source/Host/HostServices.h','Source/Host/MenuRewardOptionsLayout.h',
        'Source/Host/MenuFrontEndOptionsModel.h','Source/Host/MenuFrontEndOptionsView.h',
        'Source/Presentation/UiMenuOptions.lua','tools/civ5_ui_assets.py','tools/menu_options_assets.py','tools/ui_pixel_scene.py',
        'Tests/menu_reward_options_contract.cpp','Tests/menu_reward_options_contract.py',
        'Tests/menu_reward_options_view.cpp','Tests/menu_reward_options_view.py',
        'Tests/menu_reward_host_binding.cpp','Tests/menu_reward_host_binding.py',
        'Tests/menu_options_contract.cpp','Tests/menu_options_contract.py','Tests/menu_options_host_binding.cpp',
        'Tests/menu_options_scene.py','Tests/menu_options_followup_contract.py',
        'Tests/menu_resolution_preview.cpp','Tests/menu_resolution_preview.py',
        'Tests/menu_frontend_options_offline.cpp','Tests/menu_frontend_options_offline.py',
        'evidence/game_menu/options_reward_popups/work.py',
        'evidence/game_menu/options_reward_popups/requirements.json',
        'evidence/game_menu/options_reward_popups/requirements_addendum.json',
        'evidence/game_menu/options_reward_popups/migration_plan.json',
        'evidence/game_menu/options_reward_popups/refresh_embedded_options.py',
        'evidence/game_menu/options_reward_popups/embedded_options.plan.json',
        'evidence/game_menu/options_reward_popups/embedded_options.result.json',
        'evidence/game_menu/options_reward_popups/embedded_options_revision2.plan.json',
        'evidence/game_menu/options_reward_popups/embedded_options_revision2.result.json',
        'evidence/game_menu/options_reward_popups/collect_component_cleanup.py',
        'evidence/game_menu/options_reward_popups/make_build_manifest.py']
    for name in names:
        path=PROJECT/name;assert path.is_file() and path.is_relative_to(PROJECT),str(path)
        paths[common.key(path)]=path
    output=STAGE/'host_build/source_manifest_sealed.json'
    assert not output.exists();output.parent.mkdir(parents=True,exist_ok=True)
    rows=[common.artifact(path) for _,path in sorted(paths.items())]
    assert all(set(('path','bytes','sha256','file_identity','mtime_ns','file_attributes','links'))<=set(row) for row in rows)
    assert not any(Path(row['path']).name in ('current_work.json','current_progress.json') for row in rows)
    value=dict(schema='zerosis.options_reward_popups.source_manifest.v1',sources=rows,catalog_count=74,sidecar_files=154,
        native_host_sdk_window_gpu_executed=False,no_mutable_current_progress_reports=True,
        source_identity_policy='Authenticated production artifact reader, real os.stat identity/mtime/attributes.')
    with output.open('x',encoding='utf8') as stream:json.dump(value,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(status='PASS_CURRENT_FULL_METADATA_SOURCE_MANIFEST',sources=len(rows),artifact=common.artifact(output))))


if __name__=='__main__':main()
