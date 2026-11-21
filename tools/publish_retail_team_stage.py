"""Publish Team adversarial tests, actual SDK syntax, and one Player observation."""
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
STAGE = PROJECT/'evidence/retail_save_container/team_state'
INDEX = PROJECT/'evidence/save_menu/20261013_original_screen/current_progress.json'
DOC = PROJECT/'docs/M7_RETAIL_SAVE_BOUNDARY.md'


def writer_body(path, signature):
    text = path.read_bytes().decode('latin1').replace('\r\n', '\n')
    require(text.count(signature) == 1, 'Ambiguous retained writer')
    start = text.index(signature); cursor = text.index('{', start)+1; depth = 1
    while depth:
        if text[cursor] == '{': depth += 1
        elif text[cursor] == '}': depth -= 1
        cursor += 1
    return text[start:cursor].encode('latin1')


def main():
    require(len(sys.argv) == 1 and not sys.flags.optimize, 'Unexpected Team publication arguments')
    require(artifact(INDEX)['sha256'] == 'b4f244d0447f5a4c4eb81f851524dc76fcce91376142f329cfc2990a0b1710d3' and
        artifact(DOC)['sha256'] == '1a49a6cc31844ac8b2500c517be3ee666a3a924f830f009da30855529b095e5d', 'Team publication baseline changed')
    team_path = STAGE/'build_result.json'
    syntax_path = PROJECT/'evidence/serialization/vector_count_syntax/build_result.json'
    probe_path = PROJECT/'evidence/retail_save_container/player_prefix/boundary_probe.json'
    abi_path = PROJECT/'evidence/serialization/type_array_count/build_result.json'
    team = json.loads(team_path.read_text(encoding='utf-8'))
    syntax = json.loads(syntax_path.read_text(encoding='utf-8'))
    probe = json.loads(probe_path.read_text(encoding='utf-8'))
    abi = json.loads(abi_path.read_text(encoding='utf-8'))
    require(team['status'] == 'PASS_X64_RETAIL_TEAM_COMPONENT' and team['protected_unchanged'] and
        not team['host_gamecore_or_hwnd_executed'] and not team['sdk_restore_verified'], 'Actual isolated Team proof required')
    require(syntax['status'] == 'PASS_ACTUAL_SDK_VECTOR_COUNT_SYNTAX' and syntax['all_four_real_resource_enum_instances_checked'] and
        syntax['actual_cvteam_translation_unit_syntax_checked'] and not syntax['code_generation_or_link_performed'], 'Actual SDK syntax proof required')
    for proof in (team, syntax):
        for row in proof['inputs']+proof['protected']:
            require(artifact(row['path']) == row, 'Verified component input/protected artifact changed')
    for row in abi['inputs']:
        require(artifact(row['path']) == row, 'Earlier public Team witness input changed')
    for row in syntax['consumed_project_headers']:
        require(artifact(row['path']) == row, 'Actual SDK consumed header changed')
    for result in team['results']:
        for row in (result['executable'], result['dependencies'], result['test_log'], result['compile_log']):
            require(artifact(row['path']) == row, 'Retained Team evidence changed')
    for result in syntax['results']:
        require(artifact(result['log']['path']) == result['log'], 'Syntax log changed')
    tests = team['results'][0]['test']
    require(tests == team['results'][1]['test'] and tests['mutations'] == 2048, 'Team native modes disagree')
    public = abi['results'][1]['public_probe']['result']['public']
    require(public == abi['results'][2]['public_probe']['result']['public'] and public['teams_end'] == 2309550 and
        probe['inflated_offset'] == public['teams_end'] and probe['first_16_i32'][0] == 16 and
        probe['i32_at_relative_864'] == 0 and probe['u32_at_relative_872'] == 6 and not probe['player_structure_framed'], 'Fixed Player observation changed')
    for row in probe['source_evidence']:
        require(artifact(row['path']) == row, 'Player boundary source changed')
    comparisons = []
    for file, signature in (('CvTeam.cpp', 'void CvTeam::Write(FDataStream& kStream) const'),
        ('CvTechClasses.cpp', 'void CvTeamTechs::Write(FDataStream& kStream)')):
        paths = [PROJECT/('Source/'+root+'/CvGameCoreDLL_Expansion2/'+file) for root in ('SDK_BNW_Original', 'SDK_BNW_x64')]
        bodies = [writer_body(p, signature) for p in paths]
        require(bodies[0] == bodies[1], 'Original and ported Team wire writer differ')
        comparisons.append(dict(signature=signature, sources=[artifact(p) for p in paths],
            body_bytes=len(bodies[0]), body_sha256=hashlib.sha256(bodies[0]).hexdigest(), crlf_normalized_only=True, equal=True))
    before = dict(index=artifact(INDEX), document=artifact(DOC))
    for source, name in ((INDEX, 'current_progress.before_team.json.gz'), (DOC, 'M7_RETAIL_SAVE_BOUNDARY.before_team.md.gz')):
        target = STAGE/name
        require(not target.exists(), 'Team publication backup already exists')
        target.write_bytes(gzip.compress(source.read_bytes(), mtime=0))
    conformance = dict(status='TEAM_WRITER_CONFORMANCE_AND_SOURCE_SCOPE_RECORDED', comparisons=comparisons,
        project_art_lengths='Derived from preceding project counts; no per-row length word',
        record_budget_scope='Explicit count-field rows; fixed-width payloads and derived art scalars use input/prefix byte bounds',
        team_minimum_bytes=2424, domains=5, yields=6, fixed_team_rows=64, met_team_rows=63,
        original_coordinator_order_confirmed=False, sdk_restore_verified=False)
    (STAGE/'source_conformance.json').write_text(json.dumps(conformance, indent=2)+'\n', encoding='utf-8')
    section = f'''## Independent Team coverage and actual SDK syntax

`Tests/retail_save_team.cpp` independently constructs empty and populated Team v1/Techs v1 records with literal minimum-size and payload oracles. It exercises serialized IDs, fixed team/domain/yield widths, null/sentinel hashes, all technology columns, project counts and dependent art lengths, limits, invalid values, all prefix truncations of representative empty/populated structures and 2,048 deterministic mutations. Actual AMD64 `/O2` and `/Od /RTC1` each pass **{tests['checks']:,} checks** including **{tests['truncations']:,} truncations**. Returned mutated inspections do not approve saves. Explicit count-field rows consume record budgets; fixed-width and derived project-art payloads remain bounded by input/prefix bytes. Original and ported Team/Techs writer bodies are equal after CRLF normalization; `team_state/source_conformance.json` records their identities. The earlier public 64-Team witness remains a separate input/corpus check, not a loader or ruleset approval.

The actual current x64 `CvTeam.cpp` translation unit and `Tests/sdk_vector_count_compile.cpp` both pass MSVC **`/Zs /Y-` syntax checks** using the real SDK headers. The latter explicitly instantiates all four corrected vector writer templates with `ResourceTypes` and no TestHooks. **155 project headers** were consumed and hash-checked against current sources/manifest. Syntax checks generate no object, PCH, linked library, DLL or game window. They do not establish full SDK code generation/link success or current Host integration. Compiler warnings are retained: CvTeam has C4819 **75**, C4091 **5**, C4996 **2**; the four-template probe has **66**, **5**, **2**, respectively. They concern encoding/ignored declarations/deprecated declarations; these are not reported as zero-warning builds. No pointer-width error was emitted. Exact commands, project includes and diagnostics are in `serialization/vector_count_syntax/build_result.json`.

At the sequential public Team end **2,309,550**, the first word is **16**, matching the retained `CvPlayer::Write` version. The source emits 209 four-byte scalar fields after the version; first bool is at relative **840**, Player ID at **864**, personality enum at **868**, and first vector count at **872**. The fixed observation gives ID **0** and vector count **6**. This is source/prefix alignment evidence only: no Player structure has yet been framed or restored. `CvPlayerAI::Write` writes the whole base first, then its AI version one, so it is not a leading player tag. The generic STL vector count already uses checked u32 in the current x64 port and is not a new unresolved eight-byte-count defect. No version/signature scan or private archive ordering determines this boundary.

Player subobjects, ruleset/hash resolution, original container finish/write contracts, full SDK/Host rebuild, original save restore/reopen and actual UI/gameplay checks remain required. Original-game isolation and the prepared R11/B11 frozen inputs remain preserved. These component advances do not complete the full x64/multicore goal.

'''
    text = DOC.read_text(encoding='utf-8'); marker = '## Limits of external container evidence\n'
    require(marker in text and '## Independent Team coverage and actual SDK syntax' not in text, 'Team documentation marker changed')
    text = text.replace('Team-specific synthetic/truncation/mutation coverage remains a separate gate; this corpus witness does not replace it.',
        'Independent Team-specific synthetic/truncation/mutation coverage is recorded in the next section; this corpus witness does not replace it.')
    DOC.write_text(text.replace(marker, section+marker), encoding='utf-8')
    index = json.loads(INDEX.read_text(encoding='utf-8'))
    index['status'] = 'RETAIL_TEAM_ADVERSARIAL_AND_ACTUAL_SDK_SYNTAX_PASS_PLAYER_RESTORE_PENDING'
    index['sdk_vector_count_abi_stage'].update(status='PASS_REAL_SDK_STREAM_AND_ACTUAL_TU_SYNTAX_FULL_BUILD_PENDING',
        actual_sdk_syntax_proof=artifact(syntax_path), actual_cvteam_translation_unit_syntax_checked=True,
        four_real_enum_template_instances_syntax_checked=True, code_generation_or_link_performed=False,
        full_sdk_recompiled=False, integrated_into_current_host=False, documentation=artifact(DOC))
    index['retail_post_map_stage'].update(status='PASS_PUBLIC_TEAM_BATCH_AND_INDEPENDENT_ADVERSARIAL_COMPONENT_SUPPORTING_PLACEMENT_UNRESOLVED',
        team_synthetic_adversarial_coverage_verified=True, team_component_proof=artifact(team_path),
        team_checks_per_mode=tests['checks'], team_truncations_per_mode=tests['truncations'],
        team_mutations_per_mode=2048, team_source_conformance=artifact(STAGE/'source_conformance.json'), documentation=artifact(DOC))
    index['retail_player_boundary_stage'] = dict(status='SOURCE_PREFIX_AND_FIXED_PUBLIC_BOUNDARY_OBSERVED_PLAYER_FRAMING_PENDING',
        probe=artifact(probe_path), inflated_offset=2309550, player_version_observed=16, player_id_observed=0,
        first_vector_count_observed=6, player_structure_framed=False, original_coordinator_order_confirmed=False,
        ruleset_compatibility_verified=False, sdk_restore_verified=False, host_gamecore_or_hwnd_executed=False,
        integrated_into_current_host=False, full_engine_goal_complete=False, documentation=artifact(DOC))
    for name in ('retail_save_header_stage', 'retail_save_pregame_stage', 'retail_save_inflate_stage', 'retail_save_state_stage', 'retail_save_map_stage'):
        index[name]['documentation'] = artifact(DOC)
    require(index['prepared_runtime_matches_latest_source'] is False and index['full_engine_goal_complete'] is False, 'Full/runtime scope changed')
    INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    receipt = dict(status='PUBLISHED_RETAIL_TEAM_AND_ACTUAL_SDK_SYNTAX', utc=datetime.now(timezone.utc).isoformat(),
        before=before, after=dict(index=artifact(INDEX), document=artifact(DOC)), team_proof=artifact(team_path),
        syntax_proof=artifact(syntax_path), player_probe=artifact(probe_path), previous_goal_turn_classification='progress',
        host_runtime_or_default_promoted=False, full_engine_goal_complete=False)
    (STAGE/'progress_update.json').write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(status=receipt['status'], index=receipt['after']['index'], document=receipt['after']['document'])))


if __name__ == '__main__':
    main()
