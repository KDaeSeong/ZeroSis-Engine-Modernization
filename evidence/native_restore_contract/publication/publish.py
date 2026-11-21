"""Publish verified build receipts; no build or runtime process is started."""
from pathlib import Path
import datetime
import gzip
import hashlib
import json
import sys

P = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(P / 'tools'))
import relink_native_save_host as h

U = Path(__file__).parent
S = P / 'evidence/native_restore_contract/host_build/e6399c82ee5c15c73b86'
BUILD = '20261024T042219Z_e6399c82ee5c'


def pinned(path, expected):
    row = h.artifact(path)
    assert row['sha256'] == expected, str(path)
    return row


def main():
    assert sys.dont_write_bytecode and not (U / 'progress_update.json').exists()
    pre_ref = pinned(U / 'pre_edit.json',
        '435543ec412350b744805bfe251854c00b807a2a52664c4bb9272a0ddd172605')
    pre = h.document(pre_ref['path'])
    for row in pre['metadata']:
        h.sealed(row['before'])
        h.sealed(row['backup'])
        raw = gzip.decompress(Path(row['backup']['path']).read_bytes())
        assert len(raw) == row['before']['bytes']
        assert hashlib.sha256(raw).hexdigest() == row['before']['sha256']
    for row in pre['source_contracts']:
        h.sealed(row)
    build_ref = pinned(P / 'evidence/ui_window_host' / BUILD / 'build_result.json',
        '8746bbe6614cc206e6fa87a1fb62b0f636a160e2dcb76e0a15214aad93d09300')
    build = h.document(build_ref['path'])
    attestation = pinned(S / 'attestation.json',
        '87a0ef71a309ef0151eaf005b4b7d7a2475496b4cdfbc41eda316a2ca31a3198')
    assert h.document(attestation['path'])['status'] == 'PASS_CURRENT_NATIVE_RESTORE_HOST_STATIC_ATTESTATION'
    retirement = pinned(S / 'retirement/result.json',
        '0d2902ac9cc8b135b630b63b49835fb8301cc07ffc761daa3cd279fb93389597')
    retired = h.document(retirement['path'])
    assert retired['deleted_files'] == 6 and retired['all_targets_absent']
    assert all(not Path(path).exists() for path in retired['deleted_paths'])
    assert build['compiler_dependency_count'] == 549
    assert len(build['current_source_inputs']) == 592 and len(build['sources']) == 85
    for row in build['current_source_inputs']:
        h.sealed(row)
    terminal = pinned(P / 'evidence/sdk_runtime_play/latest_pair_execution/terminal_audit.json',
        '7f40418b3ffab0f1b0a68984cc8f9577c1a0b78ffe19cecf3e330f0a04b3f3de')
    stop = h.artifact(P / 'evidence/sdk_runtime_play/latest_pair_execution/user_stop.json')
    stop_value = h.document(stop['path'])
    assert stop_value['no_further_computer_use_after_escape']
    assert stop_value['further_computer_use_or_native_launch_requires_direct_human_resume']
    component = h.sealed(pre['component'])
    saved_game = h.sealed(pre['source_order_saved_games'])
    syntax = h.sealed(pre['actual_host_syntax'])
    assert all(row['self_test']['checks'] == 1244
        for row in h.document(component['path'])['results'].values())
    for name, count in [('HostRun.h', 3), ('InteractiveGameSession.h', 1)]:
        source = (P / 'Source/Host' / name).read_text(encoding='utf-8-sig')
        assert source.count('SdkGameRestore::VerifyRoundtrip(') == count

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    index_path = Path(pre['metadata'][0]['before']['path'])
    doc_path = Path(pre['metadata'][1]['before']['path'])
    index = h.document(index_path)
    assert index['current_host_build_id'] == '20261024T021245Z_18bbd0dd26e7'
    index['previous_linked_candidate_compile_link_proof'] = index['last_linked_candidate_compile_link_proof']
    index['previous_linked_candidate_pe_attestation'] = index['last_linked_candidate_pe_attestation']
    index['status'] = 'CURRENT_NATIVE_RESTORE_CONTRACT_HOST_LINKED_STATIC_PASS_RUNTIME_PENDING'
    index['current_host_build_id'] = BUILD
    for key in ['latest_source_matches_linked_candidate', 'latest_host_source_matches_current_link_proof',
                'latest_cpp_source_matches_actual_host_syntax_proof']:
        index[key] = True
    index['last_linked_candidate_compile_link_proof'] = build_ref
    index['last_linked_candidate_pe_attestation'] = attestation
    index['latest_actual_host_syntax_proof'] = attestation
    index['latest_actual_host_syntax_proof_scope'] = (
        'Actual five current Host units compiled and linked; SDK execution, external frontend '
        'runtime behavior and original UI acceptance are separate gates.')
    index['latest_source_matches_linked_candidate_scope'] = (
        'Current five Host units, 549 compiler inputs, 85 source manifest rows, 592 current source '
        'inputs and the unchanged 67-payload catalog. SDK/runtime/full-engine acceptance is separate.')
    for key in ['prepared_runtime_matches_current_linked_candidate', 'prepared_runtime_matches_latest_source',
                'latest_private_prepared_pair_matches_current_host_and_selected_sdk_sources',
                'default_prepared_runtime_matches_latest_source', 'full_engine_goal_complete']:
        index[key] = False
    old_stage = index['native_save_host_relink_stage']
    old_stage.update(source_current_host_link_matches=False, source_matched_when_built=True,
        superseded_for_latest_host_source_by=BUILD)
    pair = index['latest_host_sdk_preparation_stage']
    pair.update(status='PREPARED_PAIR_STARTUP_AND_NORMAL_CLOSE_VERIFIED_FULL_PLAY_PENDING',
        current_host_source_closure_matches_candidate=False, latest_private_pair_matches_current_selected_sources=False,
        source_matched_when_prepared=True, host_or_sdk_executed=True, initialization_and_normal_close_verified=True,
        initial_and_final_native_saves_created=True, city_founding_verified=False, turn_progress_verified=False,
        native_restore_verified=False, new_current_host_included=False, host_sdk_execution_verified=False,
        execution_proofs=dict(terminal_audit=terminal, human_stop=stop))
    pair['execution_verification_scope'] = (
        'Observed turn-zero window, initial/final native saves, loaded/unloaded GameCore and normal close. '
        'No city founding, turns or restore/reopen verified. This uses the prior b9 Host.')
    index['latest_isolated_runtime_execution'] = dict(run_id=pair['run_id'], host_build_id=pair['host_build_id'],
        status='STARTUP_AND_NORMAL_CLOSE_VERIFIED_UI_ACTIONS_STOPPED_BY_HUMAN', terminal_audit=terminal,
        user_stop=stop, new_current_host_executed=False, city_founding_verified=False, turn_progress_verified=False,
        sdk_restore_verified=False, further_computer_use_or_native_launch_requires_direct_human_resume=True)
    index['native_restore_contract_stage'] = dict(
        status='CURRENT_SOURCE_LINKED_STATIC_VERIFIED_RUNTIME_PENDING', utc=now, build_id=BUILD,
        requirements=[
            'Replace whole-Game exemption in all four restore paths with source-order and named SDK effects',
            'Reject unsafe signed session increment before SDK stream reads',
            'Derive victory width and actual seed option from active SDK state',
            'Preserve every other native section exactly without a native wire-version change'],
        production_source_changes=pre['source_contracts'], component=component, actual_saved_games=saved_game,
        integration_change_receipt=h.artifact(P / 'evidence/native_restore_contract/source_backups/integration.source_change.json'),
        component_modes=['O2', 'OdRTC1'], checks_per_mode=1244, truncations_per_mode=102,
        directed_corruptions_per_mode=242, atomic_failure_cases_per_mode=352,
        actual_host_main_syntax=syntax, build_result=build_ref, static_attestation=attestation,
        executable=h.sealed(build['executable']), compiler_dependency_count=549, source_manifest_count=85,
        current_source_count=592, production_restore_callers=4, exact_pe_ui_payloads=67,
        actual_child_build_commands=7, actual_compile_commands=5, actual_link_commands=1,
        production_callers_compiled=True, native_v1_wire_schema_changed=False,
        allowed_sdk_reload_effects=['sessions plus one', 'one exact localized reload replay event',
            'positive AI autoplay normalizes to one', 'game OVER normalizes to EXTENDED',
            'advisor set permutation with exact unique values',
            'actual NEW_RANDOM_SEED allows only Jon seed/reset change while call count remains exact'],
        non_game_sections_required_exact=132, source_order_game_tail_and_exact_eof_checked=True,
        intermediates_retirement=retirement, new_host_executed=False, sdk_restore_verified=False,
        native_restore_approved=False, retail_save_conversion_or_compatibility_verified=False,
        prepared_runtime_updated=False, sdk_rebuilt=False, mods_updated=False, default_promoted=False,
        original_ui_3d_full_campaign_accepted=False, measured_multicore_benefit_accepted=False,
        further_computer_use_or_native_launch_requires_direct_human_resume=True, full_engine_goal_complete=False)

    section = '## Source-order native restore contract in the current private Host'
    before_doc = doc_path.read_bytes()
    assert section.encode() not in before_doc
    addition = '''

## Source-order native restore contract in the current private Host

The current private Host is 20261024T042219Z_e6399c82ee5c (6,513,152-byte AMD64 PE32+, SHA256 2212f0e5...).
Four production restore paths now use a shared source-order contract instead of excluding the entire Game section.
It parses GameFront, GameTail and embedded database through exact EOF, requires the other 132 sections byte for byte,
and permits only audited SDK reload effects: session/replay increments, exact localized text, AI and game-state
normalization, advisor set reordering with exact unique values, and the actual NEW_RANDOM_SEED policy. Jon RNG
reseeding preserves call count and advances its unsigned reset count; Map RNG remains exact. Unsafe signed session
increments are rejected before SDK stream reads. Victory width and seed policy come from the active SDK state.
Native V1 fields and version are unchanged.

Portable O2 and Od/RTC1 each pass 1,244 checks, including 102 truncations, 242 directed corruptions, 352 failure-output
atomicity cases and 36 valid cases. The older native fixture and latest prepared pair's actual initial/final saves
pass complete source-order Game inspection with the explicit width-five profile. The initial/final saves are from
one live session, not a restore pair; their differences do not prove restore corruption or accepted reload deltas.
Python independently checks checksums and Bundle identity; test-only SHA does not replace production Windows CNG.

The private build reuses 585 immutable frozen aliases (70,549,125 logical bytes) and copies 201,983 source bytes.
All five units compile once with retained C++14/C++17 and charset settings, then one UUID-inclusive link succeeds:
seven child commands including environment setup. Dependencies are 465/266/270/279/301, union 549, with 85 source
manifest rows and 592 current-source rows. Independent static inspection confirms the same 24 PE imports, all 67
exact ordered UI payloads and one read-only contract marker. Marker inclusion does not prove runtime restoration.

The resumed prior b9/430f3122 pair, 20261024T031412Z_e06aeb61ed6a, showed its turn-zero window and exited normally
after 76.622 seconds with initial/final native saves and GameCore unload recorded. Physical Escape stopped Computer
Use before a confirmed city-found or turn-advance action. Its 24 immutable inputs remain exact. This used the prior
b9 Host and does not contain the new contract. The default runtime is unchanged; another native/UI trial requires
direct human resumption. The new current Host is linked but has not been executed or prepared into a new runtime.

Evidence: evidence/native_restore_contract/component_retry01/result.json, latest_pair_saved_game_retry01/result.json,
host_build/e6399c82ee5c15c73b86/{run,attestation}.json and retirement/result.json, together with
evidence/sdk_runtime_play/latest_pair_execution/terminal_audit.json. The first portable compile's narrowing warning
is preserved; explicit int16_t literals fix it without warning suppression. A follow-up wrapper's working-directory
guard stopped before execution; four corrected stdin-only inspections succeeded without another build. Independent
audit codec setup rejections are retained in its attestation.

After static validation, five COFF objects and the environment script are retired: 22,120,027 logical bytes and
22,130,832 allocated file-data bytes measured before last-link deletion; six empty directories are removed. The
executable, maps, source/dependency inputs, command/log receipts, gzip recovery and native saves remain. No large
object backup is created. These are scoped file-data metrics, not a whole-project or volume-free delta. Full SDK
restore/reopen, retail producer/catalog/ruleset conversion, original UI/3D/campaign, original save/mod compatibility
and measured multicore benefit remain incomplete.
'''
    index_path.write_bytes((json.dumps(index, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    doc_path.write_bytes(before_doc + addition.encode('utf-8'))
    changes = [{**row, 'after': h.artifact(row['before']['path'])} for row in pre['metadata']]
    for row in build['current_source_inputs'] + pre['source_contracts']:
        h.sealed(row)
    result = dict(schema='zerosis.native_restore.progress_publication.v1', utc=now,
        status='PASS_CURRENT_RESTORE_HOST_PROOF_PUBLISHED_WITHOUT_RUNTIME_PROMOTION', publisher=h.artifact(__file__),
        pre_edit=pre_ref, build_result=build_ref, static_attestation=attestation, retirement=retirement,
        source_component=component, saved_game_inspection=saved_game, terminal_audit=terminal, user_stop=stop,
        changed_metadata=changes, current_host_source_matches_linked_candidate=True,
        prepared_runtime_matches_new_current_host=False, new_host_executed=False,
        original_ui_3d_campaign_accepted=False, full_engine_goal_complete=False)
    h.write(U / 'progress_update.json', result)
    print(json.dumps(dict(status=result['status'], publication=h.artifact(U / 'progress_update.json'),
        metadata_revisions=2, current_build_id=BUILD, new_host_executed=False)))


if __name__ == '__main__':
    main()
