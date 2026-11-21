"""Publish bounded Player AI framing while preserving runtime/restore gates."""
from __future__ import annotations
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
from verify_retail_save_header import artifact, require
from publish_retail_team_stage import writer_body

PROJECT = Path(__file__).absolute().parents[1]
STAGE = PROJECT/'evidence/retail_save_container/player_ai_mid'
INDEX = PROJECT/'evidence/save_menu/20261013_original_screen/current_progress.json'
DOC = PROJECT/'docs/M7_RETAIL_SAVE_BOUNDARY.md'


def main():
    require(len(sys.argv) == 1 and not sys.flags.optimize, 'Unexpected Player AI middle publication arguments')
    require(artifact(INDEX)['sha256'] == '2a4f356375eb2ad3381fe5d5bfd12dcb62579d2829172239e45e56bd3746bada' and
        artifact(DOC)['sha256'] == 'eb545a594d4542da80a265f5e19b3d88dde08eaa56624b0fadcde41a627a2a0b',
        'Player AI middle publication baseline changed')
    proof_path = STAGE/'build_result.json'
    require(artifact(proof_path)['sha256'] == '485694fe01e585d7973b25c0ce3776c3c23ac9f7a5cc66576ecb4ce87e99ea23',
        'Reviewed Player AI middle native proof changed')
    proof = json.loads(proof_path.read_text(encoding='utf-8'))
    require(proof['status'] == 'PASS_X64_RETAIL_PLAYER_AI_MID_COMPONENT' and proof['protected_unchanged'] and
        not proof['full_player_framed'] and not proof['sdk_restore_verified'] and not proof['host_gamecore_or_hwnd_executed'],
        'Scoped native Player AI middle proof required')
    for row in proof['inputs']+proof['protected']:
        require(artifact(row['path']) == row, 'Verified Player AI middle input/protected artifact changed')
    for result in proof['results']:
        for field in ('executable', 'dependencies', 'response', 'test_log', 'compile_log'):
            require(artifact(result[field]['path']) == result[field], 'Retained Player AI middle evidence changed')
        for flag in ('gamecore_loaded', 'window_created', 'game_accessed', 'user_saves_accessed',
            'complete_player_validated', 'complete_save_validated', 'ruleset_compatibility_verified', 'restore_approved'):
            require(result['test'][flag] is False, 'Player AI middle test exceeds approval scope')
    tests = proof['results'][0]['test']
    require(tests == proof['results'][1]['test'] and tests['checks'] == 95212 and
        tests['truncations'] == 72463 and tests['mutations'] == 2048, 'Reviewed Player AI middle native modes disagree')
    public = tests['public']
    require(public['diplomacy_ai_offset'] == 2326136 and public['next_inflated_offset'] == 2403477 and
        public['minor_civ_ai_version'] == 1 and public['array_records'] == 724 and not public['profile_ruleset_verified'],
        'Conditional public Player AI middle framing changed')

    comparisons = []
    signatures = (
        ('CvDiplomacyAI.cpp', 'void CvDiplomacyAI::Write(FDataStream& kStream) const'),
        ('CvDiplomacyAI.cpp', 'FDataStream& operator<<(FDataStream& saveTo, const DiploLogData& readFrom)'),
        ('CvDiplomacyAI.cpp', 'FDataStream& operator<<(FDataStream& saveTo, const DeclarationLogData& readFrom)'),
        ('CvReligionClasses.cpp', 'void CvPlayerReligions::Write(FDataStream& kStream)'),
        ('CvReligionClasses.cpp', 'void CvReligionAI::Write(FDataStream& kStream)'),
        ('CvTechClasses.cpp', 'void CvPlayerTechs::Write(FDataStream& kStream)'),
        ('CvTechAI.cpp', 'void CvTechAI::Write(FDataStream& kStream) const'),
        ('CvFlavorManager.cpp', 'void CvFlavorManager::Write(FDataStream& kStream)'),
        ('CvTacticalAI.cpp', 'void CvTacticalAI::Write(FDataStream& kStream)'),
        ('CvTacticalAI.cpp', 'FDataStream& operator<<(FDataStream& saveTo, const CvTemporaryZone& readFrom)'),
        ('CvHomelandAI.cpp', 'void CvHomelandAI::Write(FDataStream& kStream)'))
    for file, signature in signatures:
        paths = [PROJECT/'Source'/root/'CvGameCoreDLL_Expansion2'/file for root in ('SDK_BNW_Original','SDK_BNW_x64')]
        bodies = [writer_body(p, signature) for p in paths]
        require(bodies[0] == bodies[1], 'Player AI middle retained writer differs: '+signature)
        comparisons.append(dict(signature=signature, sources=[artifact(p) for p in paths], crlf_normalized_only=True,
            body_bytes=len(bodies[0]), body_sha256=hashlib.sha256(bodies[0]).hexdigest(), equal=True))
    player_bodies = [writer_body(PROJECT/'Source'/root/'CvGameCoreDLL_Expansion2/CvPlayer.cpp',
        'void CvPlayer::Write(FDataStream& kStream)') for root in ('SDK_BNW_Original','SDK_BNW_x64')]
    ordered = ('m_pDiplomacyAI','m_pReligions','m_pReligionAI','m_pPlayerTechs','m_pFlavorManager',
        'm_pTacticalAI','m_pHomelandAI','m_pMinorCivAI')
    for body in player_bodies:
        positions = [body.index((name+'->Write(kStream);').encode('ascii')) for name in ordered]
        require(positions == sorted(positions), 'Player AI middle nested writer order changed')
    segments = [b[b.index(b'm_pDiplomacyAI->Write(kStream);'):b.index(b'm_pMinorCivAI->Write(kStream);')] for b in player_bodies]
    require(segments[0] == segments[1], 'Original/ported Player AI middle call segment differs')
    enum_proof = artifact(PROJECT/'evidence/serialization/candidate/conformance.json')
    require(enum_proof['sha256'] == '24d80941049f5fa4fa050bc138742806bfaeb7e249195dd330dd5b1959f15e22',
        'Original enum codec evidence changed')
    conformance = dict(status='PLAYER_AI_MID_SOURCE_CONFORMANCE_RECORDED', writer_comparisons=comparisons,
        player_call_order=list(ordered), inspected_call_segment_sha256=hashlib.sha256(segments[0]).hexdigest(),
        versions=dict(diplomacy_ai=4, player_religions=1, religion_ai=1, player_techs=1, tech_ai=1,
            flavor_manager=1, tactical_ai=1, temporary_zone=1, homeland_ai=1),
        diplomacy=dict(bytes=71856, strict_bools=5388, major=22, minor=41, civilization=63,
            demand_target_char_bytes=1, declaration_player_enum_bytes=4, enum_codec_proof=enum_proof,
            log_records=1320, log_record_bytes=8, declaration_records=60, declaration_record_bytes=21),
        minimum_bytes=dict(whole=71944, diplomacy_ai=71856, player_religions=12, religion_ai=4,
            player_techs=44, flavor_manager=8, tactical_ai=12, homeland_ai=8),
        tech_catalog_profile='InitializedTechs is mandatory; null omits seven arrays without a presence marker',
        tech_ai_zero_hash_retains_weight=True, tactical_zone_bytes=24, tactical_naval_int_bytes=4,
        required_profile=proof['public_profile'], ruleset_compatibility_verified=False,
        full_player_framed=False, sdk_restore_verified=False)
    before = dict(index=artifact(INDEX), document=artifact(DOC))
    for source, name in ((INDEX, 'current_progress.before_player_ai_mid.json.gz'), (DOC, 'M7_RETAIL_SAVE_BOUNDARY.before_player_ai_mid.md.gz')):
        target = STAGE/name
        require(not target.exists(), 'Player AI middle publication backup already exists')
        target.write_bytes(gzip.compress(source.read_bytes(), mtime=0))
    (STAGE/'source_conformance.json').write_text(json.dumps(conformance, indent=2)+'\n', encoding='utf-8')
    section = f'''## Player middle states through HomelandAI

`RetailSavePlayerAiMid.h` and its Diplomacy, ReligionTech and Tactical helpers extend the prior Player prefix by seven source-ordered nested states: DiplomacyAI4, PlayerReligions1, ReligionAI1, PlayerTechs1 (TechAI1), FlavorManager1, TacticalAI1 and HomelandAI1. A single bounded Reader preserves byte and declared-record budgets across them. It stops before MinorCivAI. Complete Player/CvPlayerAI, later players, ruleset compatibility and restore remain unsupported.

Diplomacy has exactly **71,856 bytes**, using serialized widths **22 major / 41 minor / 63 civilization players**, including **5,388 canonical bool bytes**. Its demand target is a **one-byte char**, not an int32. The logs are 1,320 records of eight bytes and 60 declarations of 21 bytes, without native padding; PlayerTypes in declarations uses the verified four-byte original codec. Version 4 is required. There are no on-wire counts in this fixed state, so its fixed rows consume the byte budget rather than the declared-count budget.

PlayerReligions writes two int32 scalars, despite the founding-religion field's `m_b` name. ReligionAI writes only its version. The **initialized tech catalog** is an explicit mandatory profile: the null branch silently omits seven hash arrays. Generic zero hashes omit their bool/int value; TechAI instead retains a weight even after hash zero. FlavorManager's signed count owns two unprefixed int columns. TacticalAI uses a u32 FStaticVector count and **24-byte** versioned temporary zones; their naval flag is an int32 and accepts nonzero integer values. HomelandAI is eight bytes. The combined empty lower bound is **71,944 bytes**; no technology/flavor width is guessed from a following version word.

`Tests/retail_player_ai_mid.cpp` independently writes empty, one-zone and populated thirteen-zone cases. The populated case deliberately exceeds the vector's capacity estimate of ten. Literal offsets exposed and corrected a three-byte fixture discrepancy before native execution. Both AMD64 `/O2` and `/Od /RTC1` pass **{tests['checks']:,} checks**, **{tests['truncations']:,} byte-prefix cuts**, and **2,048 deterministic mutations** ({tests['accepted_mutations']} structural returns / {tests['rejected_mutations']} typed rejections). Every bool, nested version, invalid profile/count, exact/short byte and aggregate budget is tested. Structural returns are not accepted game states. Compiler warnings are rejected; actual dependencies consume all 16 required production headers and no SDK header. PE/import checks run before execution and permit only AMD64 PE32+ with `kernel32.dll`. Tests run hidden, at below-normal priority, without Host/GameCore or windows.

The authenticated public diagnostic stream advances from **2,326,136** to **{public['next_inflated_offset']:,}**, reading **{public['next_inflated_offset']-public['start_offset']:,} bytes** and **{public['array_records']} declared rows**. The seven spans are Diplomacy **{public['diplomacy_ai_bytes']:,}**, player religion **{public['player_religions_bytes']}**, religion AI **{public['religion_ai_bytes']}**, techs **{public['player_techs_bytes']:,}**, flavors **{public['flavor_manager_bytes']}**, tactical **{public['tactical_ai_bytes']}**, and homeland **{public['homeland_ai_bytes']}** bytes. The next exact word is MinorCivAI version **1**. Its body and **{public['input_bytes']-public['next_inflated_offset']:,} remaining bytes** are unread. Earlier Game width five, GrandStrategy width four and initialized building/tech catalogs remain explicit structural hypotheses, not authenticated ruleset compatibility. The original public compression finish/Adler contract is still unapproved.

`player_ai_mid/source_conformance.json` hashes eleven matching Original/ported writer bodies and the Player call segment. Native objects/setup were retired with identities and hashes; current test executables and small proof files are retained. No retail installation, MODS, user saves/settings or game processes were accessed. R11/B11, the default runtime and all full-game UI/gameplay/multicore/restore gates remain unchanged.

'''
    text = DOC.read_text(encoding='utf-8')
    marker = '## Limits of external container evidence\n'
    require(marker in text and '## Player middle states through HomelandAI' not in text, 'Player AI middle documentation marker changed')
    text = text.replace('that body and **7,436,191 remaining bytes** are unframed.',
        'that body and **7,436,191 remaining bytes** were unframed at this prefix stage; the next section records the subsequent extension.')
    DOC.write_text(text.replace(marker, section+marker), encoding='utf-8')
    index = json.loads(INDEX.read_text(encoding='utf-8'))
    index['status'] = 'RETAIL_PLAYER_AI_MID_COMPONENT_PASS_FULL_PLAYER_AND_RESTORE_PENDING'
    index['retail_player_ai_mid_stage'] = dict(status='PASS_CONDITIONAL_PLAYER_AI_MID_FULL_PLAYER_AND_RESTORE_PENDING',
        headers=[artifact(PROJECT/'Source/Host'/name) for name in ('RetailSavePlayerAiMid.h','RetailSavePlayerDiplomacy.h',
            'RetailSavePlayerReligionTech.h','RetailSavePlayerTactical.h')], test=artifact(PROJECT/'Tests/retail_player_ai_mid.cpp'),
        component_proof=artifact(proof_path), source_conformance=artifact(STAGE/'source_conformance.json'),
        public=public, profile=proof['public_profile'], checks_per_mode=tests['checks'], truncations_per_mode=tests['truncations'],
        mutations_per_mode=2048, player_ai_mid_framed=True, player_structure_framed=False,
        remaining_player_state_framed=False, ruleset_compatibility_verified=False, sdk_restore_verified=False,
        integrated_into_current_host=False, documentation=artifact(DOC))
    for name in ('retail_save_header_stage','retail_save_pregame_stage','retail_save_inflate_stage','retail_save_state_stage',
        'retail_save_map_stage','retail_post_map_stage','sdk_vector_count_abi_stage','retail_player_boundary_stage'):
        index[name]['documentation'] = artifact(DOC)
    require(index['prepared_runtime_matches_latest_source'] is False and index['full_engine_goal_complete'] is False and
        index['current_prepared_runtime']['current_source_candidate'] is False, 'Runtime/full-goal scope changed')
    INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    receipt = dict(status='PUBLISHED_CONDITIONAL_RETAIL_PLAYER_AI_MID', utc=datetime.now(timezone.utc).isoformat(),
        previous_goal_turn_classification='progress', before=before, after=dict(index=artifact(INDEX), document=artifact(DOC)),
        component=artifact(proof_path), conformance=artifact(STAGE/'source_conformance.json'),
        full_player_or_restore_approved=False, host_runtime_or_default_promoted=False, full_engine_goal_complete=False)
    (STAGE/'progress_update.json').write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(status=receipt['status'], index=receipt['after']['index'], document=receipt['after']['document'])))


if __name__ == '__main__':
    main()
