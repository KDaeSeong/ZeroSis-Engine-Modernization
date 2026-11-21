"""Publish conditional Player-prefix evidence without approving Player restoration."""
from __future__ import annotations
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
from verify_retail_save_header import artifact, require
from publish_retail_team_stage import writer_body

PROJECT = Path(__file__).absolute().parents[1]
STAGE = PROJECT/'evidence/retail_save_container/player_prefix'
INDEX = PROJECT/'evidence/save_menu/20261013_original_screen/current_progress.json'
DOC = PROJECT/'docs/M7_RETAIL_SAVE_BOUNDARY.md'


def main():
    require(len(sys.argv) == 1 and not sys.flags.optimize, 'Unexpected Player-prefix publication arguments')
    require(artifact(INDEX)['sha256'] == 'abe99c330ee15996172326a7b75bd41f84c911e835287e088f8844afe18885e9' and
        artifact(DOC)['sha256'] == '2b5b24ee3f7a3f70e6900c983a057f6336c0f02788f14a889f7bc8abd27f1777', 'Player-prefix publication baseline changed')
    proof_path = STAGE/'build_result.json'
    require(artifact(proof_path)['sha256'] == '8f92e9325084a1375847f15910f977d1fe6a8430a5d93583c48882d3bb84a762', 'Reviewed Player-prefix proof changed')
    proof = json.loads(proof_path.read_text(encoding='utf-8'))
    require(proof['status'] == 'PASS_X64_RETAIL_PLAYER_PREFIX_COMPONENT' and proof['protected_unchanged'] and
        not proof['full_player_framed'] and not proof['sdk_restore_verified'] and not proof['host_gamecore_or_hwnd_executed'], 'Scoped native proof required')
    for row in proof['inputs']+proof['protected']:
        require(artifact(row['path']) == row, 'Verified Player-prefix input/protected artifact changed')
    for result in proof['results']:
        for row in (result['executable'], result['dependencies'], result['response'], result['test_log'], result['compile_log']):
            require(artifact(row['path']) == row, 'Retained Player-prefix native evidence changed')
        for flag in ('gamecore_loaded', 'window_created', 'game_accessed', 'user_saves_accessed',
            'complete_player_validated', 'complete_save_validated', 'ruleset_compatibility_verified', 'restore_approved'):
            require(result['test'][flag] is False, 'Player-prefix test exceeds approval scope')
    tests = proof['results'][0]['test']
    require(tests == proof['results'][1]['test'] and tests['mutations'] == 2048, 'Player-prefix native modes disagree')
    public = tests['public']
    require(public['player_id'] == 0 and public['front_offset'] == 2309550 and public['next_inflated_offset'] == 2326136 and
        public['diplomacy_version'] == 4 and public['grand_strategy_count'] == 4 and not public['profile_ruleset_verified'], 'Conditional public prefix changed')
    comparisons = []
    for file, owner in (('CvPlayer.cpp','CvPlayer'), ('CvPolicyClasses.cpp','CvPlayerPolicies'), ('CvPolicyAI.cpp','CvPolicyAI'),
        ('CvEconomicAI.cpp','CvEconomicAI'), ('CvCitySpecializationAI.cpp','CvCitySpecializationAI'),
        ('CvWonderProductionAI.cpp','CvWonderProductionAI'), ('CvMilitaryAI.cpp','CvMilitaryAI'), ('CvGrandStrategyAI.cpp','CvGrandStrategyAI')):
        paths = [PROJECT/('Source/'+root+'/CvGameCoreDLL_Expansion2/'+file) for root in ('SDK_BNW_Original','SDK_BNW_x64')]
        source = paths[0].read_bytes().decode('latin1')
        found = list(re.finditer(r'void\s+'+owner+r'::Write\(FDataStream& kStream\)(?: const)?', source))
        require(len(found) == 1, 'Ambiguous Player writer signature')
        bodies = [writer_body(p, found[0].group(0)) for p in paths]
        row = dict(owner=owner, sources=[artifact(p) for p in paths], crlf_normalized_only=True,
            body_bytes=[len(b) for b in bodies], body_sha256=[hashlib.sha256(b).hexdigest() for b in bodies], equal=bodies[0] == bodies[1])
        if owner == 'CvPlayer':
            marker = b'm_pPlayerPolicies->Write(kStream);'
            prefixes = [b[:b.index(marker)] for b in bodies]
            require(prefixes[0] == prefixes[1], 'Player front writer differs')
            old = b'uint iSize = m_AIOperations.size();'
            new = b'uint iSize = CvChecked::Integer<unsigned int>(m_AIOperations.size());'
            require(bodies[1].count(new) == 1 and bodies[1].replace(new, old) == bodies[0], 'Unexpected full-Player writer difference')
            row.update(front_prefix_equal=True, front_prefix_sha256=hashlib.sha256(prefixes[0]).hexdigest(),
                full_body_difference='Existing checked u32 AIOperations count outside this inspected prefix')
        else: require(row['equal'], 'Nested Player writer differs')
        comparisons.append(row)
    before = dict(index=artifact(INDEX), document=artifact(DOC))
    for source, name in ((INDEX, 'current_progress.before_player_prefix.json.gz'), (DOC, 'M7_RETAIL_SAVE_BOUNDARY.before_player_prefix.md.gz')):
        target = STAGE/name
        require(not target.exists(), 'Player-prefix publication backup already exists')
        target.write_bytes(gzip.compress(source.read_bytes(), mtime=0))
    conformance = dict(status='PLAYER_PREFIX_SOURCE_CONFORMANCE_RECORDED', writer_comparisons=comparisons,
        versions=dict(player=16, policies=2, policy_ai=1, economic_ai=1, city_specialization_ai=2, wonder_production_ai=1, military_ai=1, grand_strategy_ai=1),
        minimum_bytes='2407 + 4 * caller_grand_strategy_count', front_minimum_bytes=1028,
        front_layout=dict(first_bool=840, serialized_player_id=864, first_vector_count=872, int_vectors=26, hash_int_lists=9, bool_vectors=2, strings=2),
        military_fixed_player_rows=63, grand_strategy_fixed_major_rows=22,
        required_profile=dict(grand_strategy_count='Explicit; absent from wire; inspection supports 0..4096', building_catalog='Initialized; absent null-branch marker'),
        public_profile=proof['public_profile'], ruleset_compatibility_verified=False, full_player_framed=False, sdk_restore_verified=False)
    (STAGE/'source_conformance.json').write_text(json.dumps(conformance, indent=2)+'\n', encoding='utf-8')
    section = f'''## Player prefix through GrandStrategyAI

`RetailSavePlayerPrefix.h`, `RetailSavePlayerFront.h`, `RetailSavePlayerAiEarly.h` and `RetailSavePlayerAiStrategy.h` now frame the Player v16 front and its next six nested states: Policies2 (PolicyAI1), Economic1, CitySpecialization2, Wonder1, Military1 and GrandStrategy1. All seven spans share one bounded Reader. The parser stops before DiplomacyAI; it does not frame a complete Player, PlayerAI, all players or a retail save, and performs no SDK mutation.

The front has a **1,028-byte** empty lower bound: version, 209 four-byte scalars, the actual bool/int mixture, ID at +864, then 26 int vectors, nine hash/int lists, two bool vectors and two narrow strings. PolicyAI always writes a weight after every hash, including zero; the six policy bool tables instead omit the bool only after zero. Economic exploration/goody tables use `FFastVector` u32 counts; purchase requests are three int32s. Military uses four unprefixed **63-entry** arrays, not 64 or 80. GrandStrategy has two **22-entry** arrays and an unprefixed priority array whose width comes from the ruleset. No native struct padding is consumed.

`RetailSavePlayerProfile` requires both the grand-strategy width and the initialized-building-catalog profile. There is no silent default, byte/version scan or inferred null catalog branch. Width zero is structurally allowed; above 4096 is an explicit inspector-profile rejection, not an asserted SDK limit. Full-prefix minimum size is **2407 + 4 * G** bytes. The public check explicitly uses G=4 and the earlier Game width five, with **ruleset compatibility still unverified**. Actual loading must obtain these widths/catalog conditions from validated rules, not from a plausible next version word.

`Tests/retail_player_prefix.cpp` builds four independent empty/populated cases with G=0/1/4/7, literal minimum/extents, nonzero starts, embedded string data, zero-hash policy weights, explicit-row budgets and boundary sentinels. Both AMD64 `/O2` and `/Od /RTC1` pass **{tests['checks']:,} checks**, **{tests['truncations']:,} prefix truncations**, and **2,048 deterministic mutations** ({tests['accepted_mutations']} structural returns, {tests['rejected_mutations']} typed rejections). Returned mutations are not accepted game states. Invalid versions/bools/counts/profiles and exact/short input, prefix, array, aggregate and string limits are checked. Source dependency proof consumes the production headers, no SDK, and native imports are only `kernel32.dll`.

The same authenticated public diagnostic output is read sequentially as Game/Map, 64 Teams with ordered IDs, then Player ID **0**. Player prefix is **[{public['front_offset']},{public['next_inflated_offset']})**, **{public['next_inflated_offset']-public['front_offset']:,} bytes**, with **{public['array_records']:,} explicit array rows**. The spans are front **10,349**, policies **2,993**, economic **489**, city specialization **26**, wonders **1,372**, military **1,153**, and grand strategy **204** bytes. The next exact word is the source's DiplomacyAI version **4**; that body and **{public['input_bytes']-public['next_inflated_offset']:,} remaining bytes** are unframed. This is conditional prefix evidence, not approval of the compression finish contract, ruleset, Player restore or original save writing/reopening. Public save/body/database files are not retained.

`player_prefix/source_conformance.json` records source identities. The seven nested Write bodies and the Player front match Original/x64 after CRLF normalization. The full Player writer has one existing checked-u32 AIOperations-size difference outside this prefix; it is not falsely reported as byte-identical. Compiler objects were retired with size/hash/file-identity receipts. The current Host and R11 were not rebuilt or executed. Full SDK/Host integration, remaining Player state, actual original UI/gameplay and measured multicore behavior remain required for the overall goal.

'''
    text = DOC.read_text(encoding='utf-8'); marker = '## Limits of external container evidence\n'
    require(marker in text and '## Player prefix through GrandStrategyAI' not in text, 'Player-prefix documentation marker changed')
    text = text.replace('This is source/prefix alignment evidence only: no Player structure has yet been framed or restored.',
        'That initial observation established only source/prefix alignment. The later prefix reader below consumes the front and six nested states, while a complete Player and restore remain unsupported.')
    DOC.write_text(text.replace(marker, section+marker), encoding='utf-8')
    index = json.loads(INDEX.read_text(encoding='utf-8'))
    index['status'] = 'RETAIL_PLAYER_PREFIX_COMPONENT_PASS_FULL_PLAYER_AND_RESTORE_PENDING'
    index['retail_player_boundary_stage'].update(status='PASS_CONDITIONAL_PLAYER_PREFIX_FULL_PLAYER_AND_RESTORE_PENDING',
        headers=[artifact(PROJECT/'Source/Host'/n) for n in ('RetailSavePlayerPrefix.h','RetailSavePlayerFront.h','RetailSavePlayerAiEarly.h','RetailSavePlayerAiStrategy.h')],
        test=artifact(PROJECT/'Tests/retail_player_prefix.cpp'), component_proof=artifact(proof_path),
        source_conformance=artifact(STAGE/'source_conformance.json'), public=public, profile=proof['public_profile'],
        checks_per_mode=tests['checks'], truncations_per_mode=tests['truncations'], mutations_per_mode=2048,
        player_prefix_framed=True, player_structure_framed=False, remaining_player_state_framed=False,
        ruleset_compatibility_verified=False, sdk_restore_verified=False, integrated_into_current_host=False, documentation=artifact(DOC))
    for name in ('retail_save_header_stage','retail_save_pregame_stage','retail_save_inflate_stage','retail_save_state_stage',
                 'retail_save_map_stage','retail_post_map_stage','sdk_vector_count_abi_stage'):
        index[name]['documentation'] = artifact(DOC)
    require(index['prepared_runtime_matches_latest_source'] is False and index['full_engine_goal_complete'] is False, 'Runtime/full-goal scope changed')
    INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    receipt = dict(status='PUBLISHED_CONDITIONAL_RETAIL_PLAYER_PREFIX', utc=datetime.now(timezone.utc).isoformat(),
        previous_goal_turn_classification='progress', before=before, after=dict(index=artifact(INDEX), document=artifact(DOC)),
        component=artifact(proof_path), conformance=artifact(STAGE/'source_conformance.json'),
        full_player_or_restore_approved=False, host_runtime_or_default_promoted=False, full_engine_goal_complete=False)
    (STAGE/'progress_update.json').write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(status=receipt['status'], index=receipt['after']['index'], document=receipt['after']['document'])))


if __name__ == '__main__':
    main()
