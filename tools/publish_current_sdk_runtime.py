"""Publish a build-only current runtime SDK candidate without promotion."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
from publish_current_sdk_base import artifact, key, load, require, unchanged, write

PROJECT = Path(__file__).resolve().parents[1]
STAGE = PROJECT / 'evidence/sdk_runtime_current'
INDEX = PROJECT / 'evidence/save_menu/20261013_original_screen/current_progress.json'
DOC = PROJECT / 'docs/M7_RETAIL_SAVE_BOUNDARY.md'
PREFLIGHT = PROJECT / 'evidence/sdk_incremental/runtime_candidate_preflight.json'
PLAN = STAGE / 'overlay_plan.json'
BUILD = STAGE / 'build_result.json'
PINS = {
    INDEX: '15115c4d1258c80ad3b88641c6ae80e58961c2a32109f77b4a3d4defc38beaad',
    DOC: '75d4808b8d3a48670a590dce87cce603907ad8e78f4eb479fff23c5c7e7beaf5',
    PREFLIGHT: 'b6245ded36cef8cdf04b5e9784cc429afa9a4e3629beb6040eb896d5099fb352',
    PLAN: 'cf05557b4e1e09b184188e4ba9e8af922147eca53db7f434bbfb6585ee877e82',
    PROJECT / 'tools/prepare_current_sdk_runtime.py': '658684dc3bcbb024be2f1a1ce56bdc6e46e463905bd2f95e4d1822354f966697',
    PROJECT / 'tools/build_current_sdk_runtime_candidate.py': '43a93dce2d8d108b91dc464230a1f4405e75728b14cd4314d969bc46f3d64144',
}
FALSE_FLAGS = (
    'gamecore_loaded', 'host_executed', 'windows_created', 'retail_accessed',
    'user_state_or_processes_accessed', 'full_host_integration', 'runtime_updated',
    'default_promoted', 'retail_save_accepted', 'full_player_restore_verified',
    'ruleset_compatibility_verified', 'full_ui_accepted', 'multicore_accepted',
    'performance_improvement_verified', 'full_engine_goal_complete',
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-sha256', required=True)
    args = parser.parse_args()
    require(not sys.flags.optimize and re.fullmatch('[0-9a-f]{64}', args.build_sha256),
            'Exact reviewed build-result SHA-256 required')
    require(not (STAGE / 'progress_update.json').exists(), 'Publication already exists')
    for path, expected in PINS.items():
        require(artifact(path)['sha256'] == expected, 'Publication baseline changed: ' + str(path))
    build_identity = artifact(BUILD)
    require(build_identity['sha256'] == args.build_sha256, 'Unreviewed candidate build')
    plan, build, preflight = load(PLAN), load(BUILD), load(PREFLIGHT)
    require(build['status'] == 'PASS_CURRENT_RUNTIME_SDK_CANDIDATE_COMPILED_LINKED_NOT_LOADED' and
            build['compiled_sdk_units'] == 11 and build['compiled_bridge_units'] == 4 and
            build['object_count'] == 165 and build['reused_current_base_objects'] == 150 and
            build['linker_exit_code'] == 0 and build['inputs_unchanged'] and
            all(build[name] is False for name in FALSE_FLAGS), 'Final build scope changed')
    require(build['shared_lua_import_library_substituted'] and build['base_export_contract_unchanged'] and
            build['borrowed_registry_unique'] and build['all_compiler_dependencies_prehashed'] and
            build['binary_pch_consumed'] is False, 'Required current-runtime contracts missing')
    reviewed = [build_identity, artifact(PLAN), artifact(PREFLIGHT),
                *build['inputs'], *preflight['protected'], *plan['generated_files']]
    for row in reviewed:
        unchanged(row)
    for name in ('generated_dll', 'link_response', 'link_log', 'link_map', 'import_library', 'export_object',
                 'validation', 'shared_lua_library', 'shared_lua_dll'):
        unchanged(build[name])
        reviewed.append(build[name])
    validation = load(build['validation']['path'])
    require(validation['unresolved_symbols'] == 0 and validation['linker_warnings'] == 0,
            'Static link validation is incomplete')
    for unit in build['compiled_units']:
        require(unit['returncode'] == 0 and not unit['critical_numeric_warning_lines'] and
                unit['all_dependencies_prehashed'] and unit['binary_pch_consumed'] is False,
                'An actual compiler unit is incomplete')
        for name in ('object', 'response', 'dependencies', 'log'):
            unchanged(unit[name])
            reviewed.append(unit[name])
    require(len(build['child_commands']) == 6 and build['this_attempt_child_command_count'] == 6 and
            build['newly_compiled_units'] == 4 and build['reused_previously_compiled_sdk_units'] == 11 and
            build['resume_proof']['previous_child_command_count'] == 13 and
            build['resume_proof']['historical_failed_status_preserved'] and
            len(build['compiled_units']) == 15 and
            len(build['pe']['exports']) == 3 and 'zerosislua51_x64.dll' in build['pe']['imports'],
            'Actual command/PE evidence incomplete')
    require(all(unit['language_standard'] == ('c++14' if unit['role'] == 'sdk_overlay' else 'c++17')
                for unit in build['compiled_units']), 'Compiler language roles differ')
    provenance = STAGE / 'provenance_repair.json'
    require(artifact(provenance)['sha256'] == '7c21bf8e9f35429f07718ee968436619e0c6a65a7788a80db10d562ef0a4f375',
            'Preparation provenance repair changed')
    reviewed.append(artifact(provenance))
    semantic = plan['semantic_proof']
    require(len(semantic['save_runtime_initializer_ids']) == 5 and
            len(semantic['new_game_patch_ids']) == 18 and semantic['all_historical_generation_replays_match'] and
            semantic['old_save_count_patches_reapplied'] is False and
            len(semantic['checked_count_writer_bodies']) == 4 and
            all(row['identical'] and row['before_sha256'] == row['after_sha256']
                for row in semantic['checked_count_writer_bodies']), 'Rebase source contract missing')
    index = load(INDEX)
    before_index = json.loads(json.dumps(index))
    require(index['full_engine_goal_complete'] is False and
            index['prepared_runtime_matches_latest_source'] is False and
            index['current_prepared_runtime']['current_source_candidate'] is False,
            'Prepared-runtime/full-engine status changed')
    before = dict(index=artifact(INDEX), document=artifact(DOC))
    backups = []
    for name, path in (('index', INDEX), ('document', DOC)):
        target = STAGE / ('publication_' + name + '.before.gz')
        require(not target.exists(), 'Inspect existing publication backup')
        raw = path.read_bytes()
        zipped = gzip.compress(raw, mtime=0)
        require(gzip.decompress(zipped) == raw, 'Changed-file backup roundtrip failed')
        target.write_bytes(zipped)
        backups.append(dict(original=before[name], compressed=artifact(target), roundtrip=True))
    paragraph = '\n'.join([
        '## Current SDK with retained runtime overlays (not executed)', '',
        'The current 714-patch SDK is now combined with the retained runtime-specific changes without reusing historical SDK overlay objects. Eleven SDK cpp files use C++14 and four bridge cpp files use their required C++17 mode, with `/MD`, strict floating-point behavior and `/Y-`. The link consumes **150 authenticated current base objects plus 15 current overlay/bridge objects, 165 total**. The eleven successful SDK compilations from the first attempt are authenticated and reused; only the four bridges are compiled during resume. The first attempt remains a failed attempt, caused by using C++14 for the first C++17 bridge. Thirteen small source/header overrides are generated (1,442,063 bytes), including one byte-identical PCH routing text header; no binary PCH, full SDK tree or game data copy is made.', '',
        'Five retained save/runtime fixes are rebased: espionage-AI static-vector reset before reading, military player-array bounds, culture opinion defaults, the optional trait improvement default and operation reinforcement initialization. Eighteen map-startup/error-cleanup patches, exploration, city-site evaluation and shared-facts found-value behavior are reproduced from authenticated historical recipes. The old count patches are not reapplied. Four complete current serialization writer bodies remain byte-identical, so these overlays preserve the latest count guards. These are source-conformance and build facts, not proof of live state restoration.', '',
        'The shared Lua import library replaces the static Lua provider exactly once. The retained Lua DLL has 124 exports including the native-exception callback boundary. Actual compiler dependency reports bind each new unit to prehashed inputs, and the linker succeeds with zero unresolved symbols and zero linker warnings. Static inspection verifies AMD64 PE32+, three public exports, the retained runtime import-module set, one borrowed-reference registry and the expected bridge symbols/owners. Old SaveRestore/NewGame/Explore/CitySite/FoundValue SDK objects are absent from the new link.', '',
        'This produces a current runtime SDK candidate only. It is never loaded, copied into R11/B11 or promoted by the launcher. The Host, prepared runtime, default release and original-game test hold remain unchanged. A corrected preparation metadata key distinguishes SiteEvaluation cpp and header witnesses; the thirteen generated files remain unchanged, and the former plan/tool are recoverable from changed-file gzip backups. Full Host integration, actual new-game/turn/save/reload behavior, retail save compatibility, original UI/3D/campaign behavior and measured multicore performance remain required. Exact source preparation, compile/link inputs and outputs are in `evidence/sdk_runtime_current/overlay_plan.json` and `build_result.json`.', '',
    ])
    text = DOC.read_text(encoding='utf-8')
    marker = '## Limits of external container evidence'
    require(marker in text and '## Current SDK with retained runtime overlays (not executed)' not in text,
            'Document insertion boundary changed')
    DOC.write_text(text.replace(marker, paragraph + '\n' + marker, 1), encoding='utf-8')
    documentation = artifact(DOC)
    for value in index.values():
        if isinstance(value, dict) and isinstance(value.get('documentation'), dict) and \
                key(value['documentation']['path']) == key(DOC):
            value['documentation'] = documentation
    stage = dict(status='PASS_CURRENT_RUNTIME_SDK_CANDIDATE_COMPILED_LINKED_NOT_LOADED',
        proofs=dict(plan=artifact(PLAN), build=build_identity, validation=build['validation'],
                    preflight=artifact(PREFLIGHT), provenance_repair=artifact(provenance)),
        generated_dll=build['generated_dll'],
        base_recipe_patch_count=714, sdk_units_compiled=11, bridge_units_compiled=4,
        reused_current_base_objects=150, reused_previously_compiled_sdk_units=11,
        newly_compiled_bridge_units=4, this_attempt_child_command_count=6,
        historical_failed_attempt_child_count=13, total_linked_objects=165, generated_source_header_files=13,
        generated_source_header_bytes=plan['generated_source_bytes'], runtime_initialization_fixes=5,
        new_game_patches=18, checked_count_writer_bodies_preserved=4,
        shared_lua_import_library_substituted=True, shared_lua_export_count=124,
        borrowed_registry_unique=True, all_compiler_dependencies_prehashed=True,
        current_runtime_overlay_sources_rebased=True, binary_pch_consumed=False,
        whole_project_or_sdk_copied=False, compiler_jobs=1, documentation=documentation,
        **{name: False for name in FALSE_FLAGS})
    require('sdk_current_runtime_candidate_stage' not in index, 'Runtime candidate stage already exists')
    index['sdk_current_runtime_candidate_stage'] = stage
    index['utc'] = datetime.now(timezone.utc).isoformat()
    index['current_goal_turn_classification'] = 'progress'
    require(index['current_prepared_runtime'] == before_index['current_prepared_runtime'] and
            index['default_publication'] == before_index['default_publication'], 'Runtime/default record changed')
    for name, old in before_index.items():
        if name in ('utc', 'current_goal_turn_classification'):
            continue
        new = index[name]
        require(new == old or (isinstance(old, dict) and isinstance(new, dict) and
                {k:v for k,v in old.items() if k != 'documentation'} ==
                {k:v for k,v in new.items() if k != 'documentation'}), 'An existing progress scope changed: ' + name)
    write(INDEX, index)
    for row in reviewed:
        if key(row['path']) not in (key(INDEX), key(DOC)):
            unchanged(row)
    receipt = dict(status='PUBLISHED_CURRENT_RUNTIME_SDK_CANDIDATE_BUILD_ONLY',
        utc=datetime.now(timezone.utc).isoformat(), publisher=artifact(__file__), before=before,
        after=dict(index=artifact(INDEX), document=artifact(DOC)), backups=backups, stage=stage,
        protected_input_count=len(preflight['protected']), protected_unchanged_except_publication=True,
        prior_progress_scope_preserved=True, prepared_runtime_entire_record_unchanged=True,
        full_engine_goal_complete=False)
    write(STAGE / 'progress_update.json', receipt)
    print(json.dumps(dict(status=receipt['status'], index=receipt['after']['index'],
        document=receipt['after']['document'], receipt=artifact(STAGE / 'progress_update.json'))))


if __name__ == '__main__':
    main()
