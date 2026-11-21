"""Publish the finite SDK count correction without promoting a runtime."""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter
import gzip
import hashlib
import json
import re
import sys

sys.dont_write_bytecode = True
from verify_retail_save_header import artifact, require

PROJECT = Path(__file__).absolute().parents[1]
STAGE = PROJECT/'evidence/serialization/direct_stream_counts'
INDEX = PROJECT/'evidence/save_menu/20261013_original_screen/current_progress.json'
DOC = PROJECT/'docs/M7_RETAIL_SAVE_BOUNDARY.md'
PRIOR = PROJECT/'evidence/retail_save_container/player_ai_late/post_publication_checks.json'
REVIEWED = {
    'tracking': ('port_patch_tracking.json', '24240fb57d0758f2580468f84d61b99163596046e58caab364688eb51313aa7d'),
    'contract': ('site_contract.json', 'b732fb5f6b71df0893b4507218f6fdd1f0e7de4636f7a613c8dfe94a3f9a56d3'),
    'independent': ('independent_review.json', '88ca9af3e3f221f5cfc6a1050863c03c9a86d6c7614a0db93fa3585a868d8e46'),
    'syntax': ('../direct_stream_count_syntax/build_result.json', '07357a0b3ead466d40aa7f226e2b527736bd0e1c4a3f3584c4a39af9e76c0612'),
    'native': ('build_result.json', '9bc50d1748891107efcecb3a422973b12b2c85aeaf4c44aba0bffeda309e4446'),
    'coverage': ('coverage_review.json', '3ffcb2bee8e9b70dd9bdb824db319ce927bc764cddeb96cf3c28bbf56c0af8cb'),
}


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def unchanged(row):
    current = artifact(row['path'])
    require(all(current[k] == row[k] for k in ('path', 'bytes', 'sha256')), 'Evidence changed: '+row['path'])


def frozen_runtime(index):
    require(artifact(PRIOR)['sha256'] == '837b5dd20101bbf54991422f45caeee6dee69b81bf9c74732980081aeb840112',
        'Previous protected-runtime audit changed')
    prior = load(PRIOR)
    rows = prior['frozen_runtime_inputs']
    require(len(rows) == 24, 'Unexpected frozen input graph')
    for row in rows:
        unchanged(row)
    audit_path = PROJECT/'evidence/goody_hut/runtime_fonts/preparation_identity_audit.json'
    require(artifact(audit_path)['sha256'] == 'e7b3de4e0c7ac30e8933ac52a8d5d2df0f32d0457dbf08fb40089164cb28719e',
        'Prepared runtime identity audit changed')
    audit = load(audit_path)
    require(len(audit['shared_terrain_inputs']) == 2, 'Unexpected shared terrain inputs')
    for row in audit['shared_terrain_inputs']:
        unchanged(row)
    runtime = index['current_prepared_runtime']
    unchanged(runtime['request'])
    require(runtime['run_id'] == '20261020T110323Z_27da680b90f1' and
        runtime['host_build_id'] == '20261018T024443Z_23a2e7fdb8ea' and
        runtime['current_source_candidate'] is False and runtime['default_promoted'] is False and
        index['prepared_runtime_matches_latest_source'] is False and index['full_engine_goal_complete'] is False,
        'Runtime identity or full-engine scope changed')
    return rows


def main():
    require(len(sys.argv) == 1 and not sys.flags.optimize, 'Unexpected publication arguments')
    require(artifact(INDEX)['sha256'] == '518b6fe8b3545d231586ceb6edbd21e05c1d6811315346535338232a092dd70d' and
        artifact(DOC)['sha256'] == '3465bdacc61b7982bf98abe9c07d8da4cb1991418c9992c17c600bebd1bd8231',
        'Finite-count publication baseline changed')
    require(not (STAGE/'progress_update.json').exists(), 'Publication already exists')
    paths = {name:(STAGE/file).resolve() for name,(file,_) in REVIEWED.items()}
    for name,(_,sha) in REVIEWED.items():
        require(len(sha) == 64 and artifact(paths[name])['sha256'] == sha, 'Unreviewed proof: '+name)
    reports = {name:load(path) for name,path in paths.items()}
    tracking, contract, review, syntax, native, coverage = (reports[name] for name in REVIEWED)
    require(tracking['status'] == 'PORT_PATCH_TRACKING_RAM_REGEN_VERIFIED' and
        review['status'] == 'PASS_INDEPENDENT_FINITE_DIRECT_COUNT_SOURCE_REVIEW', 'Source/recipe proof required')
    require(contract['finite_scope'] == dict(cpp_files=8, static_sites=18, width_fixes=15, cast_range_fixes=3,
        int_sites=16, uint_sites=2, preserve_unsigned_sites=39, preserve_existing_checked_sites=1), 'Finite scope changed')
    require(review['summary']['modified_sites'] == 18 and review['summary']['current_regex_sites'] == 40 and
        review['summary']['manifest_rows_changed'] == 8 and review['summary']['historical_unmodified_source_pins'] == 66 and
        all(review['manual_review'].values()), 'Independent review is incomplete')
    for row in tracking['after']+tracking['protected']+tracking['evidence']:
        unchanged(row)
    for backup in tracking['backups']:
        unchanged(backup)
        raw = gzip.decompress(Path(backup['path']).read_bytes())
        require(len(raw) == backup['original_bytes'] and hashlib.sha256(raw).hexdigest() == backup['original_sha256'],
            'Changed-file recovery backup failed roundtrip')
    require(syntax['status'] == 'PASS_ACTUAL_SDK_DIRECT_STREAM_COUNT_SYNTAX' and
        syntax['all_eight_changed_translation_units_syntax_checked'] and len(syntax['results']) == 8 and
        syntax['pch_or_objects_generated'] is False and syntax['code_generation_or_link_performed'] is False,
        'All eight actual translation-unit syntax checks required')
    require(native['status'] == 'PASS_SDK_DIRECT_STREAM_COUNT_ABI_COMPONENT' and
        native['full_popup_writer_exercised'] is True and native['other_ten_count_fragments_only'] is True and
        native['all_canonical_popup_wires_byte_identical'] is True and len(native['canonical_wires']) == 3,
        'Native component scope changed')
    require(native['generated_extracts']['full_popup_body_retained_verbatim'] is True and
        len(native['generated_extracts']['writer_bodies']) == 8 and
        all(row['candidate_preflight_before_first_write'] for row in native['generated_extracts']['writer_bodies']),
        'Actual writer extraction/preflight proof missing')
    require([(r['arch'],r['flavor']) for r in native['results']] == [('x86','O2'),('x64','O2'),('x64','Od')],
        'Cross-architecture/mode proof missing')
    for report in (syntax,native):
        require(report['protected_unchanged'] and report['host_gamecore_or_hwnd_executed'] is False and
            report['full_engine_goal_complete'] is False, 'Test exceeded the permitted scope')
        for row in report['inputs']+report['protected']+report['consumed_project_headers']:
            unchanged(row)
    for result in syntax['results']:
        require(result['returncode'] == 0, 'Actual source syntax failure')
        for name in ('source','response','log'):
            unchanged(result[name])
    for result in native['results']:
        test = result['test']; is64 = result['arch'] == 'x64'
        require(test['status'] == 'PASS_SDK_DIRECT_STREAM_COUNTS' and test['source_count_paths'] == 18 and
            test['typed_fragment_paths'] == 10 and test['popup_full_body_cases'] == 3 and
            test['canonical_count_bytes'] == 4 and test['typed_fragment_loop_headers_exercised'] and
            test['oversized_preflight_rejections'] == (113 if is64 else 0) and
            test['inclusive_limit_cases'] == (39 if is64 else 0) and result['executable_attested_before_launch'],
            'Reviewed native count/loop/boundary coverage changed')
        require(all(test[name] is False for name in ('non_popup_payloads_verified','hash_resolution_performed',
            'gamecore_loaded','window_created','user_saves_accessed','complete_save_validated',
            'ruleset_compatibility_verified','restore_approved')), 'Native test exceeded component scope')
        for row in [result['executable'],result['map'],result['test_log'],*result['compile_logs'],
                    *result['dependencies'],*result['responses']]:
            unchanged(row)
    for row in native['canonical_wires']:
        unchanged(row)
    require(coverage['status'].startswith('PASS_'), 'Independent native coverage review failed')
    # The same finite query is re-evaluated rather than inferred from patch counts.
    pattern = re.compile(r'(?:kStream|saveTo)\s*<<\s*[^;]*\.size\(\)')
    current = [(p.name,line,text.strip()) for p in (PROJECT/'Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2').glob('*.cpp')
        for line,text in enumerate(p.read_bytes().decode('latin1').splitlines(),1) if pattern.search(text)]
    require(len(current) == 40, 'Finite direct-count query changed after review')
    index = load(INDEX)
    frozen = frozen_runtime(index)
    before = dict(index=artifact(INDEX), document=artifact(DOC))
    for name,path in (('index',INDEX),('document',DOC)):
        destination = STAGE/('publication_'+name+'.before.gz')
        require(not destination.exists(), 'Inspect existing publication backup')
        raw = path.read_bytes(); zipped = gzip.compress(raw,mtime=0)
        require(gzip.decompress(zipped) == raw, 'Publication backup roundtrip failed')
        destination.write_bytes(zipped)
    warnings = Counter(m.group(0) for r in syntax['results'] for s in r['warning_records']
        for m in [re.search(r'\bC\d{4}\b',s)] if m)
    checks = [r['test']['checks'] for r in native['results']]
    paragraph = '\n'.join([
        '## Finite direct SDK stream-count corrections', '',
        'The preceding two static inventories are historical baselines. Their finite Expansion2 cpp query had 58 direct `.size()` insertions: 15 native-size width mismatches, three unchecked signed casts, 39 already-four-byte unsigned containers and one existing checked conversion. All **18 selected sites in eight copied SDK translation units** are now corrected. The other **40 sites remain unchanged**, and the same recorded query returns exactly 40 direct sites. This is not an exhaustive audit of indirect, templated or other serialization forms.', '',
        'Army, Culture, DiplomacyRequests, Economic, PlayerEspionage, PopupReturn, ReplayInfo and ReplayMessage now preflight the selected counts before each writer\'s first output. Sixteen static sites match signed int32 readers and two match uint32 readers. Every count word and loop uses its checked local. PlayerEspionage checks all **22** heist lists before version 0; this makes **39 runtime guard evaluations** across the 18 static sites. ReplayInfo keeps version 1 and its separate child-message version 2; ReplayMessage itself has no version word and is checked before its first turn field. Valid payloads, version words, IDs, balance and schemas are unchanged. The ordered port recipe reproduces all eight files byte-for-byte in RAM; only eight manifest rows change. Ten changed-file gzip backups roundtrip correctly. No full generator or project copy was used.', '',
        f'`direct_stream_count_syntax/build_result.json` checks all eight actual translation units against **{len(syntax["consumed_project_headers"])} tracked headers**, without objects, PCH, code generation or linking. It records **{sum(warnings.values())} legacy warning occurrences** across those files: '+', '.join(f'{code} {count}' for code,count in sorted(warnings.items()))+'. These repeated diagnostics are not zero-warning evidence.', '',
        f'`direct_stream_counts/build_result.json` uses archived x86 and current x64 SDK streams. Native x86/O2 and x64/O2/Od pass **{checks[0]}/{checks[1]}/{checks[2]} checks**. The actual complete PopupReturn writer bodies, with seven real `std::vector<int>` and one `std::vector<CvString>`, produce identical full wire bytes in three empty/single/populated cases, including empty, embedded-NUL and UTF-8 strings and boundary canaries. The other ten static count sites use authenticated entry guards, count statements and typed loop headers with visit-counter bodies; their record payloads are explicitly not tested. Two FStaticVector unsigned-size shims test size-return/guard policy only. Each x64 mode rejects **113** oversized entry cases without emitting bytes and accepts **39** inclusive guard limits, including all 22 heist positions. Native-size negative controls expose the former eight-byte counts. These are component ABI/count checks, not full writer, GameCore, save restore or ruleset compatibility proof.', '',
        'Objects, environment setup, duplicate/negative-control fixture outputs and unneeded owned export intermediates are retired with identity/hash receipts. Only three canonical Popup fixtures are retained. R11/B11 and the default Host are unchanged, held, and do not contain these working-source changes. Full Player framing, container finish validation, actual save round trips, original UI/3D/full gameplay and measured multicore behavior remain required.', '',
    ])
    text = DOC.read_text(encoding='utf-8')
    start = text.index('The two `player_count_width/remaining_direct_counts_*.json` static inventories')
    end = text.index('## Limits of external container evidence',start)
    text = text[:start]+paragraph+'\n'+text[end:]
    DOC.write_text(text,encoding='utf-8')
    documentation = artifact(DOC)
    for value in index.values():
        if isinstance(value,dict) and isinstance(value.get('documentation'),dict) and value['documentation'].get('path') == str(DOC):
            value['documentation'] = documentation
    inventory = index['remaining_direct_stream_count_inventory']
    inventory.update(status='FINITE_DIRECT_COUNT_FIXES_COMPONENT_VERIFIED', baseline_sites=58,
        classification_counts_scope='Historical pre-fix inventories', remaining_direct_sites=40,
        remaining_width_fixes=0, remaining_unchecked_cast_guards=0, native_fixes_verified=True,
        current_source_review=artifact(paths['independent']), documentation=documentation)
    index['sdk_direct_stream_count_stage'] = dict(status='PASS_FINITE_DIRECT_COUNTS_ABI_AND_ACTUAL_SDK_SYNTAX_COMPONENT',
        proofs={name:artifact(path) for name,path in paths.items()}, cpp_files=8, selected_sites=18,
        native_width_fixes=15, checked_cast_guards=3, signed_sites=16, unsigned_sites=2,
        preserved_direct_sites=40, first_write_preflight=True, heist_lists_checked=22,
        full_popup_wire_cases=3, other_count_fragment_sites=10, non_popup_payloads_verified=False,
        native_checks=checks, oversized_rejections_per_x64_mode=113, inclusive_limits_per_x64_mode=39,
        full_sdk_recompiled=False, integrated_into_current_host=False, sdk_restore_verified=False,
        full_player_framed=False, ruleset_compatibility_verified=False, documentation=documentation)
    index['current_prepared_runtime']['source_scope_note'] = (
        'R11 preserves the B11 frozen input graph. Working SDK vector-count helper, PlayerTraits and eighteen direct '
        'stream-count sites in eight SDK translation units changed. These fixes and retail-state readers are not '
        'compiled into the frozen prepared runtime; it is not the current source candidate.')
    INDEX.write_text(json.dumps(index,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    frozen_runtime(index)
    receipt = dict(status='PUBLISHED_FINITE_DIRECT_STREAM_COUNT_COMPONENT_FIXES',
        utc=datetime.now(timezone.utc).isoformat(), previous_goal_turn_classification='progress', before=before,
        after=dict(index=artifact(INDEX),document=artifact(DOC)), proofs={name:artifact(path) for name,path in paths.items()},
        frozen_runtime_inputs_unchanged=len(frozen), current_source_candidate=False,
        host_runtime_or_default_promoted=False, full_player_framed=False, sdk_restore_verified=False,
        full_engine_goal_complete=False)
    (STAGE/'progress_update.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status=receipt['status'],index=receipt['after']['index'],document=receipt['after']['document'],
        receipt=artifact(STAGE/'progress_update.json'))))


if __name__ == '__main__':
    main()
