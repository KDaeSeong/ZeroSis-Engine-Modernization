"""Create the next wave's storage/preservation helper from the closed baseline."""
from pathlib import Path

STAGE=Path(__file__).absolute().parent
PROJECT=STAGE.parents[2]
text=(PROJECT/'evidence/game_menu/replay_hover_frame/work.py').read_text('utf8')
text=text.replace("PREVIOUS=PROJECT/'evidence/game_menu/replay_scroll_graph'", "PREVIOUS=PROJECT/'evidence/game_menu/replay_hover_frame'")
text=text.replace('zerosis.replay_hover_frame','zerosis.options_video_preview')
text=text.replace("old_cleanup['all_recorded_deleted_paths_currently_absent']", "old_cleanup['all_deleted_paths_currently_absent']")
text=text.replace("old_cleanup['unexpected_regenerable_current_intermediates']", "old_cleanup['unexpected_regenerable_intermediates']")
text=text.replace("old_cleanup['deleted_files']", "old_cleanup['deletion_events']")
text=text.replace("old_cleanup['deleted_file_count']", "old_cleanup['deletion_event_count']")
text=text.replace("'Source/Host/HostRun.h','Source/Host/MenuFrontEndAssets.h'", "'Source/Host/HostRun.h','Source/Host/MenuFrontEndAssets.h','Source/Host/MenuOptionsContract.h',\n        'Source/Host/MenuOptionsStore.h','Source/Host/MenuOptionsHostBinding.h',\n        'Source/Host/MenuFrontEndOptionsModel.h','Source/Host/MenuFrontEndOptionsView.h'")
begin=text.index('    requirements=dict(')
end=text.index("    write_new(STAGE/'requirements.json'",begin)
requirements="""    requirements=dict(schema='zerosis.options_video_preview.requirements.v1',requirements=[
        'Restore original ApplyResButton and20-second resolution/fullscreen confirmation through real existing display apply/readback/rollback.',
        'Use original OnApplyRes, ShowResolutionCountdown, OnCountdownYes/No and timeout/escape policies for the supported display fields; retain unrelated cached edits.',
        'Keep last-confirmed display state and active exclusive option ownership coherent across repeated preview, confirm, reject, timeout, close and backend/persistence failure.',
        'Use uncapped monotonic elapsed time for expiry; keep animation delta clamping separate.',
        'Preserve existing V1/V2 settings bytes on read, V2 field order/keys/schema on commit, all GameCore/save/Mod IDs and balance. No new preference fields.',
        'Reuse existing assets where exact source controls can be rendered; any missing control/asset/font input must be tracked rather than guessed.',
        'Do not execute Host/SDK/CLR/HWND/GPU/audio/native display or screen tools; allow pure Lua/C++14 consoles and actual compile/link/file-only preparation.',
        'Protect currentee8c/9a1 and required original/default/recovery data; remove owned intermediates and enforce10GiB confirmed-disposable threshold.'
    ],affected_modules=['MenuOptionsSession transient display preview','Front-end options model/view/lifecycle timer','Source-backed original confirmation layout/assets if required'],
        save_compatibility='No settings version/keys or GameCore/save schema/IDs change. Preview state is transient and belongs to the existing private Host options owner.',
        deployment='Explicit prepared profile only; no original game/MODS/default/global registration changes.',
        native_execution=False,full_engine_goal_complete=False,previous_goal_turn_classification='progress')
"""
text=text[:begin]+requirements+text[end:]
text=text.replace('WORKING_ORIGINAL_GRAPH_POINTER_GUIDES_AND_FRAME','WORKING_ORIGINAL_VIDEO_SETTINGS_CONFIRMATION_AND_ROLLBACK')
output=STAGE/'work.py'
assert not output.exists()
compile(text,str(output),'exec')
with output.open('x',encoding='utf8') as stream:stream.write(text)
print('CREATED_SOURCE_BACKED_VIDEO_PREVIEW_BASELINE_HELPER')
