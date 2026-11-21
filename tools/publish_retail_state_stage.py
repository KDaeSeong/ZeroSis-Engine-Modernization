"""Publish the verified state component without changing any runtime bundle."""
from __future__ import annotations
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
from verify_retail_save_header import artifact, require

PROJECT = Path(__file__).absolute().parents[1]
STAGE = PROJECT/'evidence/retail_save_container/game_state'
INDEX = PROJECT/'evidence/save_menu/20261013_original_screen/current_progress.json'
DOC = PROJECT/'docs/M7_RETAIL_SAVE_BOUNDARY.md'


def main():
    require(len(sys.argv) == 1 and not sys.flags.optimize, 'Unexpected publication invocation')
    require(artifact(INDEX)['sha256'] == '69fd0a23b659ec64473654b34efbf9cbb08afa6014e526af7df7ac110a3edb70' and
            artifact(DOC)['sha256'] == '3d190b8a0587bb14e9afbe93dfa79ca683b44ead6c5fa429b23185c796919ed1',
            'Publication baseline changed; inspect before retrying')
    proof = json.loads((STAGE/'build_result.json').read_text(encoding='utf-8'))
    require(proof['status'] == 'PASS_X64_RETAIL_STATE_COMPONENT' and proof['protected_unchanged'] and
            not proof['host_gamecore_or_hwnd_executed'] and not proof['sdk_restore_verified'], 'Component proof required')
    for row in proof['inputs']:
        require(artifact(row['path']) == row, 'Verified state component input changed')
    for row in proof['protected']:
        require(artifact(row['path']) == row, 'Protected baseline changed')
    for row in proof['results']:
        require(artifact(row['executable']['path']) == row['executable'], 'Native state executable changed')
        require(row['test']['checks'] == 41613 and row['test']['truncations'] == 12999 and
                row['test']['mutations'] == 2048 and not row['test']['complete_save_validated'], 'Unexpected component result')
    public = proof['results'][0]['test']['public']
    require(public == proof['results'][1]['test']['public'] and public['game_bytes'] == 11254 and
            public['database_offset'] == 8182 and public['database_bytes'] == 3072 and
            public['map_offset'] == 11254 and public['next_inflated_offset'] == 11984 and
            (public['map_width'], public['map_height']) == (40, 24), 'Public boundary differs')
    before = dict(index=artifact(INDEX), document=artifact(DOC))
    for source, name in ((INDEX, 'current_progress.before_game_state.json.gz'), (DOC, 'M7_RETAIL_SAVE_BOUNDARY.before_game_state.md.gz')):
        target = STAGE/name
        require(not target.exists(), 'Publication backup already exists')
        target.write_bytes(gzip.compress(source.read_bytes(), mtime=0))

    sdk_names = ['CvGame.cpp', 'CvMap.cpp', 'CvDealClasses.cpp', 'CvReligionClasses.cpp', 'CvBeliefClasses.cpp',
                 'CvCultureClasses.cpp', 'CvVotingClasses.cpp', 'CvTradeClasses.cpp', 'CvStructs.cpp',
                 'CvRandom.cpp', 'CvReplayMessage.cpp', 'CvInfosSerializationHelper.h', 'CvGlobals.cpp']
    sdk = [artifact(PROJECT/'Source'/tree/'CvGameCoreDLL_Expansion2'/name)
           for tree in ('SDK_BNW_Original', 'SDK_BNW_x64') for name in sdk_names]
    sdk += [artifact(PROJECT/'Source/SDK_BNW_x64'/name) for name in
            ('FirePlace/include/FireWorks/FDataStream.h', 'FirePlace/include/FireWorks/FStlContainerSerialization.h',
             'FirePlace/include/FireWorks/FFreeListTrashArray.h', 'FirePlace/include/FireWorks/FFreeListArrayBase.h',
             'FirePlace/include/FireWorks/FFastVector.h', 'CvGameCoreDLLUtil/include/CvDLLUtilDefines.h')]
    preg = json.loads((PROJECT/'evidence/retail_save_container/pregame_boundary/source_conformance.json').read_text())
    for row in preg['selected_enum_artifacts_rehashed']:
        require(artifact(row['path']) == {k: row[k] for k in ('path', 'bytes', 'sha256')}, 'Selected enum proof changed')
    conformance = dict(schema='zerosis.retail_save.state_conformance.v1',
        status='PASS_LATEST_BNW_GAME_AND_MAP_PREFIX_FRAMING_ONLY', sdk_sources=sdk,
        component=artifact(STAGE/'build_result.json'), source_headers=[artifact(x['path']) for x in proof['inputs'][:4]],
        selected_enum_proof=artifact(PROJECT/'evidence/serialization/candidate/conformance.json'),
        selected_enum_artifacts_rehashed=len(preg['selected_enum_artifacts_rehashed']),
        references=artifact(PROJECT/'evidence/retail_save_container/pregame_boundary/upstream.json'),
        public=public, public_database=proof['results'][0]['independent_database_check'],
        fixed_players=64, fixed_civilization_teams=63, fixed_trade_major_civilizations=22, fixed_yields=6,
        victory_inner_width_must_be_explicit=True, public_profile_victory_awards=5,
        public_profile_ruleset_width_verified=False, project_production_list_can_grow_past_22=True,
        original_sdk_victory_writer_outer_count_uses_special_unit_count=True,
        original_sdk_victory_reader_outer_capacity_uses_victory_info_count=True,
        own_sdk_writer_not_used_as_retail_oracle=True, sdk_read_not_called=True,
        offsets_are_inflated_input_only=True, embedded_database_span_opaque_to_production_parser=True,
        complete_container_or_full_state_restore_verified=False, original_save_write_verified=False,
        host_gamecore_or_hwnd_executed=False, user_saves_accessed=False)
    (STAGE/'source_conformance.json').write_text(json.dumps(conformance, indent=2)+'\n', encoding='utf-8')

    text = DOC.read_text(encoding='utf-8')
    text = text.replace('These readers and the new bounded `RetailSaveInflate.h` decoder are separate components',
        'These readers, the bounded `RetailSaveInflate.h` decoder and the `RetailSaveState.h` Game/Map-prefix inspector are separate components')
    text = text.replace('Compressed state is still unparsed.', 'Complete compressed state is not yet framed or restored; the bounded Game/Map-prefix inspection below covers only its beginning.')
    section = '''## Inflated Game and Map-prefix framing

`Source/Host/RetailSaveState.h`, `RetailSaveStateWire.h`, `RetailSaveGameFront.h` and `RetailSaveGameTail.h` frame already inflated bytes without calling the SDK or accessing files. The latest BNW profile consumes Game v1, populated vote FreeLists, release RNG v1, replay v2, plot extras, Deals1/Deal3/TradedItem2, Religions4/Religion4/Beliefs2, Culture2/GreatWork3, Leagues5/League14 and its independently versioned resolution layers, Trade3, and the declared embedded-database bytes. Map1 follows in the public corpus; only its fixed fields and two conditional hashed resource arrays are consumed. Plot, area, landmass, supporting, Team and Player records are not yet framed. The private archive's section order is not asserted as the retail order.

Fixed player/team arrays have no count words. Hash zero has no following value. The victory-rank inner width is absent from the wire and is a **required explicit profile input**, not a hidden default of five. `CvGlobals` replaces its initial value from `NUM_VICTORY_POINT_AWARDS`. Framing cannot establish ruleset/type-hash compatibility; both approval flags remain false. Debug RNG, unsupported nested versions and profiles are explicit failures. Signed counts, per-array/aggregate counts, strings, prefix/input bytes, embedded-database bytes and map dimensions have bounded checks before multiplication or traversal. Reader limits are copied so temporary arguments cannot leave a dangling reference.

Source cross-review corrected an initially incorrect 22-entry limit on league-project contributions: `FStaticVector` can grow, and its boolean template parameter means POD, not fixed capacity. A 23-entry fixture now succeeds. The Trade matrix really does serialize 22 by 22 integers and six origin/destination yield pairs. Another existing SDK difference is retained as evidence: the victory writer uses special-unit count for its outer rows while its reader uses victory-info capacity. Our private writer is therefore not used as an independent retail oracle. No SDK serializer or save schema was changed.

The immutable public BNW corpus, inflated to **9,762,327** bytes with the previously verified SHA-256, was passed through binary stdin only. Ordered parsing returns Game `[0,11254)`, embedded DB `[8182,11254)` (**3,072 bytes**), and Map header `[11254,11984)` (**730 bytes**, **40 by 24** plots). The next offset is a plot-data start, not the end of Map or a complete save. The exact declared database span independently has a valid SQLite header and three 1,024-byte pages and was opened only in memory. It contains no `NUM_VICTORY_POINT_AWARDS` value, so the test profile's width five remains an explicit assumption, not verified ruleset compatibility. No signature search determines any boundary. No public save, inflated body or database file is retained.

`Tests/retail_save_state.cpp` uses eight independent empty/populated fixtures with explicit widths 0/1/5/7, literal minimal-byte expectations, populated nested records, zero hashes, decoy SQLite/Map bytes, exact/short budgets, every synthetic-prefix truncation, invalid versions/bools/free lists and 2,048 deterministic mutations. Actual AMD64 `/O2` and `/Od /RTC1` each pass **41,613 checks**, including **12,999 truncations**; these are component checks, not gameplay tests. The 731 returned mutation inspections never claim save acceptance. Compiler dependency proof consumes all four production headers and no SDK; executable imports are only `kernel32.dll`. `game_state/build_result.json` records inputs, commands and the retired compiler objects. The current Host and prepared R11 remain separate, unmodified by this component, and unexecuted.

The public compressed input still ends at a nonfinal empty stored-block boundary, without a final block or verified Adler trailer. Successful Game/Map-prefix inspection does not resolve the original finish contract or authorize restore. Full Map and subsequent object framing, ruleset compatibility, original save writing and retail/candidate reopening remain required.

'''
    marker = '## Limits of external container evidence\n'
    require(marker in text and '## Inflated Game and Map-prefix framing' not in text, 'Documentation publication marker differs')
    text = text.replace(marker, section+marker)
    DOC.write_text(text, encoding='utf-8')
    index = json.loads(INDEX.read_text(encoding='utf-8'))
    index['status'] = 'RETAIL_GAME_MAP_PREFIX_COMPONENT_PASS_CURRENT_HOST_NATIVE_PENDING'
    index['retail_save_state_stage'] = dict(status='PASS_LATEST_BNW_GAME_MAP_PREFIX_FULL_RETAIL_ADAPTER_PENDING',
        headers=[artifact(x['path']) for x in proof['inputs'][:4]], test=artifact(PROJECT/'Tests/retail_save_state.cpp'),
        component_proof=artifact(STAGE/'build_result.json'), conformance=artifact(STAGE/'source_conformance.json'),
        documentation=artifact(DOC), public=public, checks_per_mode=41613, synthetic_cases=8,
        truncations_per_mode=12999, mutations_per_mode=2048, modes=['O2', 'Od_RTC1'],
        explicit_victory_width_required=True, public_profile_width_verified=False,
        full_map_or_subsequent_sdk_streams_framed=False, whole_retail_container_verified=False,
        ruleset_compatibility_verified=False, sdk_restore_or_original_save_write_verified=False,
        native_component_executed=True, host_gamecore_or_hwnd_executed=False, user_saves_accessed=False,
        public_save_or_body_retained=False, integrated_into_current_host=False, default_promoted=False,
        existing_save_schema_or_ids_changed=False, full_engine_goal_complete=False)
    for name in ('retail_save_header_stage', 'retail_save_pregame_stage', 'retail_save_inflate_stage'):
        index[name]['documentation'] = artifact(DOC)
    index['current_prepared_runtime']['source_scope_note'] = ('B11 compiled/frozen frontend input graph unchanged. '
        'Retail metadata, Pregame, bounded inflate and Game/Map-prefix inspection are separate components, not enabled in this Host.')
    INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    receipt = dict(status='PUBLISHED_RETAIL_GAME_MAP_PREFIX_COMPONENT', utc=datetime.now(timezone.utc).isoformat(),
        previous_goal_turn_classification='progress', before=before, after=dict(index=artifact(INDEX), document=artifact(DOC)),
        component=artifact(STAGE/'build_result.json'), conformance=artifact(STAGE/'source_conformance.json'),
        host_runtime_or_default_promoted=False, full_engine_goal_complete=False)
    (STAGE/'progress_update.json').write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(status=receipt['status'], index=artifact(INDEX), document=artifact(DOC))))


if __name__ == '__main__':
    main()
