"""Publish actual Traits count fixes and bounded Player states without runtime promotion."""
from __future__ import annotations
from datetime import datetime, timezone
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
from verify_retail_save_header import artifact, require
from publish_retail_team_stage import writer_body

PROJECT = Path(__file__).absolute().parents[1]
STAGE = PROJECT/'evidence/retail_save_container/player_ai_late'
INDEX = PROJECT/'evidence/save_menu/20261013_original_screen/current_progress.json'
DOC = PROJECT/'docs/M7_RETAIL_SAVE_BOUNDARY.md'
ABI_SHA = '362820a44926883cef18022eb65da3ccdc60ac99ac128ab05c1f3c57dda1b051'


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def main():
    require(len(sys.argv) == 1 and not sys.flags.optimize, 'Unexpected Player late publication arguments')
    require(artifact(INDEX)['sha256'] == 'c66617c560ed15f754bd6c5c23fe1c02373405f1c25657bc79582f1a07dfc4f5' and
        artifact(DOC)['sha256'] == '0317de0329b8feefa246b249387ad58d490de3ec9e47cab4d68ec11a937797ae',
        'Player late publication baseline changed')
    paths = dict(component=STAGE/'build_result.json', abi=PROJECT/'evidence/serialization/player_traits_count/build_result.json',
        syntax=PROJECT/'evidence/serialization/player_count_syntax/build_result.json',
        tracking=PROJECT/'evidence/serialization/player_count_width/port_patch_tracking.json',
        inventory_a=PROJECT/'evidence/serialization/player_count_width/remaining_direct_counts_a.json',
        inventory_b=PROJECT/'evidence/serialization/player_count_width/remaining_direct_counts_b.json')
    for name, sha in (('component','7be36c1e6912c83c65dd3426426165965ecdb49bd77eb7dc91de295406b9e071'),
        ('abi',ABI_SHA), ('syntax','c7c67e2065af9c5a81e986b8487a84d7de4337b3330d41abaa27dec30080800a'),
        ('inventory_a','0613bacda43b7a677cdb808fddf1370c86c9d11c28efb754f4d67a1ae4be2f26'),
        ('inventory_b','394016c31474f1ba5bb2ecee3ad458aa13b6312e5074e1a581bd9e648af724ea')):
        require(artifact(paths[name])['sha256'] == sha, 'Reviewed '+name+' proof changed')
    proof, abi, syntax, tracking = (load(paths[n]) for n in ('component','abi','syntax','tracking'))
    inventory_a, inventory_b = load(paths['inventory_a']), load(paths['inventory_b'])
    for relative, pin in inventory_a['source_pins'].items():
        path = Path(relative)
        actual = artifact(path if path.is_absolute() else PROJECT/path)
        require(actual['bytes'] == pin['bytes'] and actual['sha256'] == pin['sha256'], 'Inventory A source changed')
    for pin in inventory_b['source_files'].values():
        require(artifact(pin['path']) == pin, 'Inventory B source changed')
    inventoried = [(row['cpp'],row['ported_line']) for row in inventory_a['sites']] + [
        (row['source'].split(':',1)[1],row['cpp_line']) for row in inventory_b['sites']]
    pattern = re.compile(r'(?:kStream|saveTo)\s*<<\s*[^;]*\.size\(\)')
    observed = {(path.name,line) for path in (PROJECT/'Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2').glob('*.cpp')
        for line,text in enumerate(path.read_bytes().decode('latin1').splitlines(),1) if pattern.search(text)}
    classes = Counter(row['classification'] for row in inventory_a['sites']+inventory_b['sites'])
    require(len(inventoried) == len(set(inventoried)) == 58 and set(inventoried) == observed and
        classes == dict(NATIVE_SIZE_T_WIDTH_MISMATCH=15,ALREADY_FIXED_UNSIGNED_WIDTH=39,
            CHECKED_FIXED_WIDTH=1,UNCHECKED_NARROWING_ONLY=3), 'Finite direct-count inventory no longer matches sources')
    require(proof['status'] == 'PASS_X64_RETAIL_PLAYER_AI_LATE_COMPONENT' and
        abi['status'] == 'PASS_SDK_PLAYER_TRAITS_COUNT_ABI_COMPONENT' and
        syntax['status'] == 'PASS_ACTUAL_SDK_PLAYER_TRAITS_COUNT_SYNTAX' and
        tracking['status'] == 'PORT_PATCH_TRACKING_RAM_REGEN_VERIFIED', 'Scoped actual proofs required')
    for report in (proof, abi, syntax):
        require(report['protected_unchanged'] and report['host_gamecore_or_hwnd_executed'] is False and
            report['full_engine_goal_complete'] is False, 'Proof exceeded permitted scope')
        for row in report['inputs']+report['protected']:
            require(artifact(row['path']) == row, 'Verified proof input/protected artifact changed')
    require(syntax['actual_cvtraits_translation_unit_syntax_checked'] and not syntax['code_generation_or_link_performed'] and
        not syntax['pch_or_objects_generated'], 'Actual syntax-only proof missing')
    for row in syntax['consumed_project_headers']:
        require(artifact(row['path']) == row, 'Actual syntax consumed header changed')
    for result in syntax['results']:
        for field in ('source','response','log'):
            require(artifact(result[field]['path']) == result[field], 'Retained syntax evidence changed')
    require([(r['arch'],r['flavor']) for r in abi['results']] == [('x86','O2'),('x64','O2'),('x64','Od')] and
        abi['all_canonical_wires_byte_identical'] is True, 'Actual cross-architecture wire comparison missing')
    require(all(f['body_retained_verbatim'] is True for f in abi['generated_extracts']['families']),
        'Full retained writer bodies were not compiled verbatim')
    for row in abi['consumed_project_headers']+abi['canonical_wires']:
        require(artifact(row['path']) == row, 'ABI header or retained canonical fixture changed')
    for result in abi['results']:
        for row in [result['executable'],result['map'],result['test_log'],*result['responses'],*result['dependencies'],*result['compile_logs']]:
            require(artifact(row['path']) == row, 'Retained native Traits evidence changed')
        t = result['test']; is64 = result['arch'] == 'x64'
        require(t['status'] == 'PASS_SDK_PLAYER_TRAITS_COUNT' and t['checks'] == (1194 if is64 else 570) and
            t['canonical_direct_count_bytes'] == 4 and t['legacy64_direct_count_bytes'] == (8 if is64 else 0) and
            t['oversized_preflight_rejections'] == (9 if is64 else 0) and t['production_reader_cases'] == (3 if is64 else 0) and
            t['legacy_exact_boundaries_rejected'] == (3 if is64 else 0) and t['synthetic_cases'] == 3 and
            t['full_writer_body_extracted'] is True and t['hash_resolution_test_hooks_only'] is True and
            t['free_trait_uint_size_shim'] is True and result['executable_attested_before_launch'] is True,
            'Native Traits count/guard/reader scope differs')
        for flag in ('gamecore_loaded','window_created','user_saves_accessed','complete_save_validated','ruleset_compatibility_verified','restore_approved'):
            require(t[flag] is False, 'Native ABI test exceeds component scope')
    for result in proof['results']:
        for field in ('executable','dependencies','response','test_log','compile_log'):
            require(artifact(result[field]['path']) == result[field], 'Retained Player late evidence changed')
        for flag in ('gamecore_loaded','window_created','game_accessed','user_saves_accessed','complete_player_validated',
            'complete_save_validated','ruleset_compatibility_verified','restore_approved'):
            require(result['test'][flag] is False, 'Player late test exceeds framing scope')
    tests = proof['results'][0]['test']; public = tests['public']
    require(tests == proof['results'][1]['test'] and tests['checks'] == 20253 and tests['truncations'] == 4520 and
        tests['mutations'] == 2048 and public['next_inflated_offset'] == 2421545 and public['espionage_version'] == 0 and
        public['danger_plot_count'] == 960 and public['array_records'] == 1247, 'Reviewed Player late evidence changed')

    comparisons = []
    for file, signature in (
        ('CvMinorCivAI.cpp','void CvMinorCivAI::Write(FDataStream& kStream) const'),
        ('CvMinorCivAI.cpp','FDataStream& operator<<(FDataStream& saveTo, const CvMinorCivQuest& readFrom)'),
        ('CvDealAI.cpp','void CvDealAI::Write(FDataStream& kStream) const'),
        ('CvBuilderTaskingAI.cpp','void CvBuilderTaskingAI::Write(FDataStream& kStream)'),
        ('CvCityConnections.cpp','void CvCityConnections::Write(FDataStream& kStream) const'),
        ('CvDangerPlots.cpp','void CvDangerPlots::Write(FDataStream& kStream) const')):
        pair = [PROJECT/'Source'/root/'CvGameCoreDLL_Expansion2'/file for root in ('SDK_BNW_Original','SDK_BNW_x64')]
        bodies = [writer_body(p, signature) for p in pair]
        require(bodies[0] == bodies[1], 'Original/ported late writer differs: '+signature)
        comparisons.append(dict(signature=signature, sources=[artifact(p) for p in pair], crlf_normalized_only=True,
            body_bytes=len(bodies[0]), body_sha256=hashlib.sha256(bodies[0]).hexdigest(), equal=True))
    for row in tracking['after']:
        current = artifact(row['path'])
        require(all(current[k] == row[k] for k in ('path','bytes','sha256')), 'Tracked Traits patch changed')
    trait = PROJECT/'Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvTraitClasses.cpp'
    require(artifact(trait)['sha256'] == 'f9b66e589e47abd0bad339a08187c4124f572961575a983da79f91348598eaf6', 'Traits patch changed')
    conformance = dict(status='PLAYER_LATE_SOURCE_CONFORMANCE_RECORDED', matching_writers=comparisons,
        traits_writer=artifact(trait), traits_write_difference='Three preflight int counts and their writes/loop bounds; two size_t widths plus one prior unchecked cast',
        traits_tracking=artifact(paths['tracking']), native_full_writer_abi=artifact(paths['abi']), actual_sdk_syntax=artifact(paths['syntax']),
        versions=dict(minor_civ_ai=1,minor_quest=2,deal_ai=1,builder_tasking_ai=2,city_connections=1,danger_plots=1,traits=19),
        minimum_bytes=dict(whole=3955,minor_civ_ai=3409,deal_ai=4,builder_tasking_ai=14,city_connections=12,danger_plots=13,traits=503),
        initialized_minor_quest_lists_required=22, minor_team_bool_width=80, minor_quest_bytes=21,
        city_dimension_policy='Count D once; derived D*D cells are byte bounded, with original uint32 product limit',
        traits_layout=dict(int_prefix=65,bools=19,yield_columns=6,raw_yield_arrays=7,firaxis_vector_row_bytes=24),
        ruleset_compatibility_verified=False, full_player_framed=False, sdk_restore_verified=False)
    before = dict(index=artifact(INDEX),document=artifact(DOC))
    for source, name in ((INDEX,'current_progress.before_player_ai_late.json.gz'),(DOC,'M7_RETAIL_SAVE_BOUNDARY.before_player_ai_late.md.gz')):
        target = STAGE/name; require(not target.exists(), 'Player late publication backup exists')
        target.write_bytes(gzip.compress(source.read_bytes(),mtime=0))
    (STAGE/'source_conformance.json').write_text(json.dumps(conformance,indent=2)+'\n',encoding='utf-8')
    section = f'''## Player late states and actual Traits count correction

`RetailSavePlayerAiLate.h` with Minor, Infrastructure and Traits helpers frames six more source-ordered Player states: MinorCivAI1 (Quest2), DealAI1, BuilderTaskingAI2, CityConnections1, DangerPlots1 and PlayerTraits19. It stops before Espionage0. It is still not a complete Player, PlayerAI, all-player stream, compatible ruleset or restore path. All spans share a bounded Reader and return approval flags false.

MinorAI requires exactly **22 initialized outer quest lists**, which are absent as a count on the wire. `RetailPlayerAiLateProfile::InitializedMinorQuests` is mandatory and never inferred from a plausible following version. The source has uncounted int[22][22], twelve int[22], six bool[22], two bool[80] and its final bool; minimum **3409 + 21Q** bytes. Each signed quest count charges declared rows; the capacity estimate of five is not a maximum. Builder uses a u32 FStaticVector count. City writes a u32 dimension D, interleaved raw-char cells of total **2D²** bytes and a four-byte city count read as signed. D is charged once as declared rows; its derived cells consume only byte budget. Original uint32 D² overflow is rejected before an O(1) bounded skip. Danger writes its player enum, allocated bool, signed map-grid count and uint32 values regardless of that flag. The public grid is compared with the already-framed Map's **960** plots.

Traits v19 has an empty minimum of **503 bytes**: 65 ints, 19 canonical bools, two four-byte enums, seven uncounted yield[6] columns, hash/int arrays, Maya choices, no-train flags, free units, combat columns, three counted vectors of unprefixed Firaxis::Array<int,6> rows and luxury areas. Generic zero hashes omit the value. The whole six-state empty minimum is **3955 bytes**. Independent empty/sparse/populated fixtures exercise seven quests (above the estimate), nonzero route matrices, false allocation with a populated danger grid, zero hashes, signed values and row counts. Both AMD64 modes pass **{tests['checks']:,} checks**, **{tests['truncations']:,} byte-prefix cuts** and **2048 deterministic mutations** ({tests['accepted_mutations']} structural returns / {tests['rejected_mutations']} typed rejections). No returned mutation is approved as a game state. Production dependency evidence includes all 20 required headers and no SDK header; tests run hidden at below-normal priority, with PE/import checks before execution.

The authenticated public diagnostic stream now advances **[{public['start_offset']},{public['next_inflated_offset']})**, **{public['next_inflated_offset']-public['start_offset']:,} bytes** and **{public['array_records']} declared rows**. The spans are minor **{public['minor_civ_ai_bytes']}**, deal **{public['deal_ai_bytes']}**, builder **{public['builder_tasking_ai_bytes']}**, connections **{public['city_connections_bytes']}**, danger **{public['danger_plots_bytes']}**, and traits **{public['traits_bytes']}** bytes. The next exact word is the source's **Espionage version 0**. **{public['input_bytes']-public['next_inflated_offset']:,} following bytes remain unframed**, including that observed four-byte version word. Game width five, strategy width four, initialized building/tech catalogs and initialized minor lists are structural hypotheses; the compression finish contract, full ruleset compatibility and retail restore remain unapproved. No public compressed/inflated save or embedded DB file is retained.

This investigation also corrected the actual working SDK writer. `CvPlayerTraits::Write` previously inserted native `.size()` for `std::vector<MayaBonusChoice>` and `std::vector<bool>`, producing **eight bytes on x64** where its reader consumes an int32. Its luxury-area `(int).size()` also narrowed unchecked. All three now pass `CvChecked::Integer<int>` **before the first stream write**, and write/iterate using those same checked counts. Values above **INT_MAX** are rejected before output. Valid payloads, IDs and version 19 remain unchanged. FreeTraitUnits, Builder and City containers are FStaticVector with an already-four-byte unsigned size; those writers were preserved. The port recipe reproduces the single changed SDK file exactly; source/recipe/manifest backups are changed-file gzip only.

`serialization/player_traits_count/build_result.json` binds exact extracted full writer bodies to actual x86/x64 SDK streams and native enum codecs, with explicit hash-resolution hooks and a uint-size free-unit shim. Original x86 passes **570 checks**; both x64 modes pass **1194 checks**, including **nine** oversized preflight rejections each. Three complete canonical writer/canary outputs match byte-for-byte across x86 and both x64 modes. The production Traits reader reaches the exact body end for all three canonical cases and rejects the exact end for all three legacy controls. Canonical wire comparison and oversized-count preflight rejection are component evidence, not actual ruleset/GameCore loading or complete save compatibility. `player_count_syntax/build_result.json` separately checks the actual full CvTraitClasses.cpp translation unit against 150 tracked headers, without code generation or linking; **78 existing legacy warnings** are recorded (71 encoding, five enum-declaration, two deprecated-library diagnostics). This is not a full SDK rebuild. Objects, duplicate/obsolete test outputs and setup files are retired with path/identity/hash receipts. R11/B11 and the default Host remain unchanged and do not include these working-source changes. Full original UI/gameplay, retail round trips and measured multicore behavior remain required.

The two `player_count_width/remaining_direct_counts_*.json` static inventories exactly cover the remaining **58** direct `.size()` insertions matching the recorded stream-site query: **15 width mismatches**, **39 already-four-byte containers**, **one checked conversion**, and **three unchecked casts with no width change**. They pin declarations, typedefs, allocator/size-return evidence and original count readers; no site is unresolved. These are a finite next fix batch, not new native stream passes or an exhaustive audit of all serialization forms. The 15 width fixes and three cast guards remain pending; the preserved FStaticVector writers are not mislabeled as native-size defects.

'''
    text = DOC.read_text(encoding='utf-8');marker = '## Limits of external container evidence\n'
    require(marker in text and '## Player late states and actual Traits count correction' not in text, 'Late document marker changed')
    text = text.replace('Its body and **7,358,850 remaining bytes** are unread.',
        'Its body and **7,358,850 remaining bytes** were unread at the middle-state stage; the following section records the subsequent extension.')
    DOC.write_text(text.replace(marker,section+marker),encoding='utf-8')
    index = load(INDEX);index['status'] = 'RETAIL_PLAYER_THROUGH_TRAITS_COMPONENT_PASS_FULL_PLAYER_AND_RESTORE_PENDING'
    index['retail_player_ai_late_stage'] = dict(status='PASS_CONDITIONAL_PLAYER_THROUGH_TRAITS_FULL_PLAYER_AND_RESTORE_PENDING',
        headers=[artifact(PROJECT/'Source/Host'/n) for n in ('RetailSavePlayerAiLate.h','RetailSavePlayerMinor.h','RetailSavePlayerInfrastructure.h','RetailSavePlayerTraits.h')],
        test=artifact(PROJECT/'Tests/retail_player_ai_late.cpp'),component_proof=artifact(paths['component']),
        source_conformance=artifact(STAGE/'source_conformance.json'),public=public,profile=proof['public_profile'],
        checks_per_mode=tests['checks'],truncations_per_mode=tests['truncations'],mutations_per_mode=2048,
        player_late_states_framed=True,player_structure_framed=False,remaining_player_state_framed=False,ruleset_compatibility_verified=False,
        sdk_restore_verified=False,integrated_into_current_host=False,documentation=artifact(DOC))
    index['sdk_player_traits_count_stage'] = dict(status='PASS_ACTUAL_TRAITS_COUNT_ABI_AND_SDK_SYNTAX_COMPONENT',
        sdk_source=artifact(trait),tracking=artifact(paths['tracking']),native_abi=artifact(paths['abi']),syntax=artifact(paths['syntax']),
        size_t_width_fixes=2,unchecked_signed_cast_fixes=1,signed_count_limit=2147483647,checked_before_first_output=True,
        native_checks=[r['test']['checks'] for r in abi['results']],canonical_wire_cases=3,canonical_wire_bytes_equal=True,
        oversized_preflight_rejections_per_x64_mode=9,production_reader_cases_per_x64_mode=3,
        full_sdk_recompiled=False,integrated_into_current_host=False,sdk_restore_verified=False,documentation=artifact(DOC))
    index['remaining_direct_stream_count_inventory'] = dict(status='STATIC_CLASSIFICATION_COMPLETE_NATIVE_FIXES_PENDING',
        scope='Expansion2 cpp direct kStream/saveTo insertions of .size(); not all serialization forms',
        artifacts=[artifact(paths['inventory_a']),artifact(paths['inventory_b'])],sites=58,classification_counts=dict(classes),
        remaining_width_fixes=15,remaining_unchecked_cast_guards=3,native_fixes_verified=False,documentation=artifact(DOC))
    for name in ('retail_save_header_stage','retail_save_pregame_stage','retail_save_inflate_stage','retail_save_state_stage',
        'retail_save_map_stage','retail_post_map_stage','sdk_vector_count_abi_stage','retail_player_boundary_stage','retail_player_ai_mid_stage'):
        index[name]['documentation'] = artifact(DOC)
    require(index['full_engine_goal_complete'] is False and index['prepared_runtime_matches_latest_source'] is False and
        index['current_prepared_runtime']['current_source_candidate'] is False,'Runtime or whole-goal scope changed')
    index['current_prepared_runtime']['source_scope_note'] = 'R11 preserves the B11 frozen input graph. Working SDK vector-count helper and PlayerTraits count writer changed; neither these fixes nor the retail-state readers are compiled into this prepared runtime.'
    INDEX.write_text(json.dumps(index,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    receipt = dict(status='PUBLISHED_PLAYER_THROUGH_TRAITS_AND_ACTUAL_COUNT_FIX',utc=datetime.now(timezone.utc).isoformat(),
        previous_goal_turn_classification='progress',before=before,after=dict(index=artifact(INDEX),document=artifact(DOC)),
        proofs={k:artifact(v) for k,v in paths.items()},conformance=artifact(STAGE/'source_conformance.json'),
        host_runtime_or_default_promoted=False,full_player_or_restore_approved=False,full_engine_goal_complete=False)
    (STAGE/'progress_update.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status=receipt['status'],index=receipt['after']['index'],document=receipt['after']['document'])))


if __name__ == '__main__':
    main()
