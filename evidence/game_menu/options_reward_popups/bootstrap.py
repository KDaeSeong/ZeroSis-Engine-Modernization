"""Prepare protected baseline and explicit private-preference V3 migration."""
from pathlib import Path
import json

STAGE=Path(__file__).absolute().parent
PROJECT=STAGE.parents[2]
text=(PROJECT/'evidence/game_menu/options_video_preview/work.py').read_text('utf8')
text=text.replace("PREVIOUS=PROJECT/'evidence/game_menu/replay_hover_frame'", "PREVIOUS=PROJECT/'evidence/game_menu/options_video_preview'")
text=text.replace('zerosis.options_video_preview','zerosis.options_reward_popups')
text=text.replace("old_cleanup['unexpected_regenerable_intermediates']", "old_cleanup['current_wave_candidate_tmp_files']")
text=text.replace("'Source/Host/MenuOptionsStore.h','Source/Host/MenuOptionsHostBinding.h'", "'Source/Host/MenuOptionsStore.h','Source/Host/MenuOptionsHostBinding.h','Source/Host/HostServices.h'")
text=text.replace('WORKING_ORIGINAL_VIDEO_SETTINGS_CONFIRMATION_AND_ROLLBACK','WORKING_ORIGINAL_NO_REWARD_POPUPS_OPTION_AND_V3_MIGRATION')
begin=text.index('    requirements=dict(')
end=text.index("    write_new(STAGE/'requirements.json'",begin)
requirements="""    requirements=dict(schema='zerosis.options_reward_popups.requirements.v1',requirements=[
        'Connect original NoRewardPopupsCheckbox through the owned front-end option transaction, real Host preference snapshot and existing SDK IsOptionNoRewardPopups callback.',
        'Preserve defaultfalse and all SDK reward calculation/rule/balance code. The option selects the existing popup/notification presentation branches only.',
        'Read private V1/V2 bytes without rewriting and default the new bool tofalse. Explicit changed commits write canonical V3 with one appended noRewardPopups line.',
        'Keep all existing keys/order/control IDs, game/save/Mod schemas and video20second preview/partialcommit/rollback/owner semantics intact.',
        'Expose only committed/applied Host state via an atomic bool; cached edits, cancel and display-only preview must not leak the new draft to SDK readers.',
        'Use original checkbox/stack/source localization and existing V3 asset/font data where coverage is proven; do not clone a whole asset pack.',
        'Native Host/SDK/CLR/window/GPU/audio/game/screen execution remains held. Pure/source-extracted C++14 and file-only checks/preparation may continue.',
        'Protect current8837/1fba and original/default/recovery inputs. Remove owned intermediates and enforce10GiB confirmed-disposable threshold.'
    ],affected_modules=['Private preference V3 codec/store migration','Host binding and SDK UI preference callback','Source-backed game-options model/view'],
        save_compatibility='Only private Host preferences gain an explicitly planned V3 read/write schema. Existing V1/V2 read bytes and all GameCore/save/Mod IDs/schemas remain unchanged.',
        deployment='Explicit prepared profile only; original game/MODS/default/global registration unchanged.',
        native_execution=False,full_engine_goal_complete=False,previous_goal_turn_classification='progress')
"""
text=text[:begin]+requirements+text[end:]
output=STAGE/'work.py';assert not output.exists()
compile(text,str(output),'exec')
with output.open('x',encoding='utf8') as stream:stream.write(text)
migration=dict(schema='zerosis.private_options.reward_popups_migration_plan.v1',
    previous_versions=[1,2],new_version=3,new_field=dict(key='noRewardPopups',kind='canonical_bool_0_or_1',default=False),
    order='Append noRewardPopups immediately after existing policyInfo; preserve every pre-existing field/order.',
    read_policy='Decode V1/V2 using exact original-version canonical comparison, supplyfalse only in memory, perform zero write.',
    commit_policy='After an explicitly changed successful Apply/partial non-resolution commit/confirmed display promotion, atomically write canonical V3. No-opApply/Cancel/reject performs no write.',
    store_policy='Compute encoded schema version before publication; after atomic replacement only nonthrowing bookkeeping updates the observed schema.',
    preview_policy='Display-only preview uses committedfalse/true; Yes promotes display fields and retains reward draft, No/timeout restores baseline, OnOK non-resolution commit promotes reward before display preview.',
    host_policy='Initialize an atomic bool from decoded committed settings, update and acquire-read via actual apply/readback; rollback restores its exact old value.',
    no_changes=['GameCore/save/Mod schema or IDs','SDK reward computations/balance','Existing UI control IDs','Original retail preferences/configuration or user saves'],
    native_execution=False,full_engine_goal_complete=False)
target=STAGE/'migration_plan.json';assert not target.exists()
with target.open('x',encoding='utf8') as stream:json.dump(migration,stream,indent=2);stream.write('\n')
print('CREATED_EXPLICIT_V3_MIGRATION_AND_PROTECTED_BASELINE_HELPER')
