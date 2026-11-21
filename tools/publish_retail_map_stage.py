"""Publish the verified full-Map component while preserving prepared runtimes."""
from __future__ import annotations
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
from verify_retail_save_header import artifact, require
PROJECT = Path(__file__).absolute().parents[1]
STAGE = PROJECT/'evidence/retail_save_container/map_state'
INDEX = PROJECT/'evidence/save_menu/20261013_original_screen/current_progress.json'
DOC = PROJECT/'docs/M7_RETAIL_SAVE_BOUNDARY.md'


def main():
    require(len(sys.argv) == 1 and not sys.flags.optimize, 'Unexpected Map publication invocation')
    require(artifact(INDEX)['sha256'] == '083a759b2941ea7192d5e8fa53f0957f380125c5bf12c371d55f12f42f231eb3' and
            artifact(DOC)['sha256'] == '648334231903e2fc80e630121126972f05e4bf07e15c1f303933296fe4970df0',
            'Map publication baseline changed; inspect before retrying')
    proof = json.loads((STAGE/'build_result.json').read_text(encoding='utf-8'))
    require(proof['status'] == 'PASS_X64_RETAIL_MAP_COMPONENT' and proof['protected_unchanged'] and
            not proof['sdk_restore_verified'] and not proof['host_gamecore_or_hwnd_executed'], 'Actual full-Map component proof required')
    for row in proof['inputs']+proof['protected']:
        require(artifact(row['path']) == row, 'Verified Map input or protected baseline changed')
    for row in proof['results']:
        require(artifact(row['executable']['path']) == row['executable'], 'Verified Map executable changed')
    public = proof['results'][0]['test']['public']
    require(public == proof['results'][1]['test']['public'] and public['plot_count'] == 960 and
            public['map_offset'] == 11254 and public['plot_offset'] == 11984 and
            public['landmasses_offset']+public['landmasses_bytes']+4 == public['next_inflated_offset'], 'Public full-Map boundaries differ')
    previous = json.loads((PROJECT/'evidence/retail_save_container/game_state/build_result.json').read_text())
    for row in previous['inputs']:
        require(artifact(row['path']) == row, 'Prior Game component source changed')
    before = dict(index=artifact(INDEX), document=artifact(DOC))
    for source, name in ((INDEX, 'current_progress.before_map.json.gz'), (DOC, 'M7_RETAIL_SAVE_BOUNDARY.before_map.md.gz')):
        target = STAGE/name
        require(not target.exists(), 'Map publication backup already exists')
        target.write_bytes(gzip.compress(source.read_bytes(), mtime=0))
    names = ('CvPlot.cpp', 'CvPlot.h', 'CvMap.cpp', 'CvMap.h', 'CvArea.cpp', 'CvArea.h',
             'CvInfos.cpp', 'CvImprovementClasses.cpp', 'CvGameCoreEnums.h')
    sdk = [artifact(PROJECT/'Source'/tree/'CvGameCoreDLL_Expansion2'/name)
           for tree in ('SDK_BNW_Original', 'SDK_BNW_x64') for name in names]
    sdk += [artifact(PROJECT/'Source/SDK_BNW_x64'/name) for name in
        ('FirePlace/include/FireWorks/FDataStream.h', 'FirePlace/include/FireWorks/FFreeListTrashArray.h',
         'FirePlace/include/FireWorks/FFreeListArrayBase.h', 'CvGameCoreDLLUtil/include/CvDLLUtilDefines.h')]
    conformance = dict(schema='zerosis.retail_save.map_conformance.v1', status='PASS_LATEST_BNW_FULL_MAP_FRAMING_ONLY',
        sdk_sources=sdk, writer_body_comparison=artifact(STAGE/'writer_body_comparison.json'),
        component=artifact(STAGE/'build_result.json'), prior_game_component=artifact(PROJECT/'evidence/retail_save_container/game_state/build_result.json'),
        public=public, public_cross_check=proof['results'][0]['public_cross_check'],
        plot_version=7, archaeology_version=2, area_version=1, landmass_version=1,
        minimum_plot_bytes=1569, minimum_area_bytes=3718, landmass_bytes=22,
        really_max_players_and_teams=80, area_target_and_yield_rows=64, yield_types=6,
        no_settling_flags=22, revealed_bitset_words=4, invisible_short_array=[80,1],
        build_outer_count_is_presence_with_separate_inner_count=True, nonzero_build_hash_value_bytes=2,
        sdk_unknown_build_read_fallback_incorrectly_reads_int32=True, unresolved_hash_restore_compatibility_verified=False,
        improvement_hash_only_sentinels=[0,4294967295], sdk_read_called=False,
        whole_container_finish_or_following_stream_order_verified=False,
        ruleset_compatibility_verified=False, sdk_restore_verified=False, original_save_write_verified=False,
        user_saves_accessed=False, host_gamecore_or_hwnd_executed=False)
    (STAGE/'source_conformance.json').write_text(json.dumps(conformance,indent=2)+'\n',encoding='utf-8')
    tests = proof['results'][0]['test']
    text = DOC.read_text(encoding='utf-8')
    text = text.replace('Plot, area, landmass, supporting, Team and Player records are not yet framed.',
        '`RetailSaveState` stops there; the `RetailSaveMap` component below additionally frames Plot, area and landmass records. Supporting, Team and Player records remain unframed.')
    text = text.replace('The current Host and prepared R11 remain separate, unmodified by this component, and unexecuted.',
        'The current Host and prepared R11 remain separate, unmodified by these components, and unexecuted.')
    section = f'''## Complete Map framing component

`RetailSaveMap.h`, `RetailSavePlot.h` and `RetailSaveMapTail.h` extend the inspected Game/Map prefix through every Plot v7, Area v1 and Landmass v1 record and the final AIMapHints word. The bounded cursor preserves the Game prefix's consumed record budget. All offsets refer to inflated input. This produces a complete Map span without SDK calls, ruleset/type-hash resolution or runtime mutation. It is not a whole-save approval or restoration.

The SDK's Plot arrays use REALLY_MAX_PLAYERS/TEAMS **80**, while Game arrays use 64. Each Plot includes short coordinates/yields/visibility, raw char fields, four DWORD reveal words, fixed `short[80][1]` invisibility with no count, optional script bytes, build presence plus a separately counted hash/short list, unit-ID pairs and archaeology v2. No native struct padding is consumed. Minimum Plot size is **1,569 bytes**. Area's first five arrays use 80 rows; target-city/yield loops use **64** rows, giving a **3,718-byte** minimum. Landmass is **22 bytes**. Both Map-tail containers use checked FreeListTrashArray metadata/links/IDs. Improvement hash 0 and 0xffffffff omit their value. Nonzero build hashes have a two-byte short; the SDK reader's unknown-hash fallback instead reads four bytes, an existing mismatch that this framing reader does not reproduce. Unresolved-hash SDK restore safety remains unverified.

Original and ported SDK Map, Plot, Area and Landmass writer bodies match after CRLF normalization; `map_state/writer_body_comparison.json` records those body identities. The pinned public Go reader stops at MapHeader and is not presented as a full-Map oracle. `source_conformance.json` records source identities and wire widths.

In the same immutable **9,762,327-byte** diagnostic output, both native modes frame all **960 plots**, **{public['area_count']} areas** and **{public['landmass_count']} landmasses**. Map is `[{public['map_offset']},{public['next_inflated_offset']})` (**{public['map_bytes']:,} bytes**), plots `[{public['plot_offset']},{public['areas_offset']})`, areas `[{public['areas_offset']},{public['landmasses_offset']})`, then landmasses and the final four-byte hint. **{proof['results'][0]['public_cross_check']['unparsed_following_bytes']:,} following bytes remain unparsed**; no private section order is inferred for them. The Map span SHA-256 is `{proof['results'][0]['public_cross_check']['map_bytes_sha256']}`. Input SHA and the original nonfinal deflate termination are unchanged. Public save/body/database files are not retained.

`Tests/retail_save_map.cpp` reuses the earlier independent Game fixture writer without copying or modifying it. Four minimal/populated cases exercise 80/64 widths, hash sentinels, unequal outer/inner build counts, scripts with decoy bytes, populated area/landmass free lists, literal minimum-byte expectations, exact/short limits, invalid versions/bools/counts, all synthetic Map byte truncations and 2,048 mutations. Actual AMD64 `/O2` and `/Od /RTC1` each pass **{tests['checks']:,} checks**, including **{tests['truncations']:,} truncations**. Returned mutated inspections do not approve saves. Compiler dependency evidence includes all seven production headers and no SDK; executables import only `kernel32.dll`. Objects and resolved failed/interrupted attempts are retired with small hash/identity ledgers. These are separate component tests, not original UI/gameplay proof or current Host integration.

The original compression finish contract, unsupported layouts, following state streams, ruleset compatibility, SDK restore/save wiring, original save writing and retail reopening remain required. Native Host/GameCore/window execution is still held during the user's original-game test.

'''
    marker = '## Limits of external container evidence\n'
    require(marker in text and '## Complete Map framing component' not in text, 'Map documentation marker differs')
    DOC.write_text(text.replace(marker,section+marker),encoding='utf-8')
    index = json.loads(INDEX.read_text(encoding='utf-8'))
    index['status'] = 'RETAIL_FULL_MAP_COMPONENT_PASS_CURRENT_HOST_NATIVE_PENDING'
    index['retail_save_map_stage'] = dict(status='PASS_LATEST_BNW_FULL_MAP_FRAMING_RETAIL_RESTORE_PENDING',
        headers=[artifact(x['path']) for x in proof['inputs'][:3]],test=artifact(PROJECT/'Tests/retail_save_map.cpp'),
        component_proof=artifact(STAGE/'build_result.json'),conformance=artifact(STAGE/'source_conformance.json'),documentation=artifact(DOC),
        public=public,checks_per_mode=tests['checks'],truncations_per_mode=tests['truncations'],mutations_per_mode=2048,
        following_sdk_streams_framed=False,whole_retail_container_verified=False,ruleset_compatibility_verified=False,
        sdk_restore_or_original_save_write_verified=False,native_component_executed=True,host_gamecore_or_hwnd_executed=False,
        public_save_or_body_retained=False,user_saves_accessed=False,integrated_into_current_host=False,
        existing_schema_or_ids_changed=False,default_promoted=False,full_engine_goal_complete=False)
    for name in ('retail_save_header_stage','retail_save_pregame_stage','retail_save_inflate_stage','retail_save_state_stage'):
        index[name]['documentation'] = artifact(DOC)
    index['current_prepared_runtime']['source_scope_note'] = ('B11 compiled/frozen frontend graph unchanged. '
        'Retail save framing/decoding components, including full Map inspection, remain separate and disabled in this Host.')
    INDEX.write_text(json.dumps(index,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    receipt = dict(status='PUBLISHED_RETAIL_FULL_MAP_COMPONENT',utc=datetime.now(timezone.utc).isoformat(),
        previous_goal_turn_classification='progress',before=before,after=dict(index=artifact(INDEX),document=artifact(DOC)),
        component=artifact(STAGE/'build_result.json'),conformance=artifact(STAGE/'source_conformance.json'),
        host_runtime_or_default_promoted=False,full_engine_goal_complete=False)
    (STAGE/'progress_update.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status=receipt['status'],index=artifact(INDEX),document=artifact(DOC))))


if __name__ == '__main__':
    main()
