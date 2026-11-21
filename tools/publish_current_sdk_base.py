"""Publish the current base SDK integration proof without changing a runtime."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
PROJECT = Path(__file__).resolve().parents[1]
STAGE = PROJECT / 'evidence/sdk_current'
INDEX = PROJECT / 'evidence/save_menu/20261013_original_screen/current_progress.json'
DOC = PROJECT / 'docs/M7_RETAIL_SAVE_BOUNDARY.md'
PRIOR = PROJECT / 'evidence/retail_save_container/player_ai_late/post_publication_checks.json'
BASELINES = {
    INDEX: 'e6f36a67708c87ce515945b08a37bf71f491d135b5d4845d8c9cfe83770f226e',
    DOC: '9db6c263ec4886a8e55ed101f17a7d72149c7677a4e7e3cb4f10ff6d72e00a25',
    PRIOR: '837b5dd20101bbf54991422f45caeee6dee69b81bf9c74732980081aeb840112',
    STAGE / 'prebuild.json': 'd647c50a442aaa4594d5fc34409b54985c057879798dffbd9143a37f7ccfe39e',
    STAGE / 'compile_result.json': 'c59dcd8f844c347a0e0281f23ec456f4b677868332c469c6aa655315bd3ffd0e',
    STAGE / 'validation_pch_retirement.json': 'bf7e697d94befe0ecf5bec9c309951df27c27bc5397bf377070ca4aa032f41d0',
}


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def key(path):
    return os.path.normcase(os.path.abspath(path))


def artifact(path):
    path = Path(path)
    for parent in (path, *path.parents):
        if parent.exists():
            require(not parent.lstat().st_file_attributes & 0x400, 'Reparse path: ' + str(parent))
    before = path.stat()
    require(path.is_file(), 'Required file missing: ' + str(path))
    sha = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            sha.update(block)
    after = path.stat()
    require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), 'File changed while hashing')
    return dict(path=str(path), bytes=before.st_size, sha256=sha.hexdigest())


def unchanged(row):
    actual = artifact(row['path'])
    require(actual['sha256'] == row['sha256'] and
            ('bytes' not in row or actual['bytes'] == row['bytes']), 'Changed input: ' + row['path'])
    return actual


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--result-sha256', required=True)
    args = parser.parse_args()
    require(re.fullmatch('[0-9a-f]{64}', args.result_sha256), 'Exact reviewed link-result SHA-256 required')
    require(not sys.flags.optimize and not (STAGE / 'progress_update.json').exists(), 'Single-use publication')
    for path, sha in BASELINES.items():
        require(artifact(path)['sha256'] == sha, 'Publication baseline changed: ' + str(path))
    result_path = STAGE / 'base_link_result.json'
    require(artifact(result_path)['sha256'] == args.result_sha256, 'Unreviewed link result')
    link = load(result_path)
    compilation = load(STAGE / 'compile_result.json')
    prebuild = load(STAGE / 'prebuild.json')
    index = load(INDEX)
    historical_stages = json.loads(json.dumps({name: index[name] for name in (
        'sdk_vector_count_abi_stage', 'sdk_player_traits_count_stage', 'sdk_direct_stream_count_stage')}))
    runtime_before = json.dumps(index['current_prepared_runtime'], sort_keys=True)
    require(link['status'] == 'PASS_CURRENT_BASE_SDK_LINK_NOT_LOADED' and
            link['linker_exit_code'] == 0 and link['unresolved_symbols'] == 0 and
            link['linker_warnings'] == 0 and link['inputs_unchanged'] and
            link['object_count'] == 161 and link['provider_count'] == 16 and
            link['platform_library_count'] == 14, 'Final base-link proof required')
    false_flags = ('gamecore_loaded', 'host_executed', 'windows_created', 'retail_accessed',
        'sdk_source_copied', 'overlays_used', 'full_host_integration', 'retail_save_accepted',
        'full_ui_accepted', 'multicore_accepted', 'full_engine_goal_complete', 'runtime_updated', 'default_promoted')
    require(all(link[name] is False for name in false_flags), 'Link scope changed')
    require(compilation['cpp_units'] == 161 and compilation['rebuilt'] == 37 and
            compilation['reused'] == 124 and compilation['input_hashes_unchanged'], 'Compile scope changed')
    for row in link['inputs']:
        unchanged(row)
    for name in ('generated_dll', 'link_response', 'link_log', 'link_map', 'import_library', 'export_object', 'validation'):
        unchanged(link[name])
    validation = load(link['validation']['path'])
    require(validation['unresolved_symbols'] == 0 and validation['linker_warnings'] == 0 and
            len(validation['exports_match_definition_and_map']) == 3 and
            validation['import_module_set_matches_old_base'], 'PE/map validation incomplete')
    require(link['pe']['machine'] == '0x8664' and link['pe']['pe_format'] == 'PE32+' and
            len(link['pe']['exports']) == 3, 'AMD64 PE32+ and three exports required')
    protected = load(PRIOR)['frozen_runtime_inputs']
    audit_path = PROJECT / 'evidence/goody_hut/runtime_fonts/preparation_identity_audit.json'
    terrain = load(audit_path)['shared_terrain_inputs']
    require(len(protected) == 24 and len(terrain) == 2, 'Frozen graph size changed')
    for row in [*protected, *terrain, *prebuild['protected']]:
        unchanged(row)
    runtime = index['current_prepared_runtime']
    require(runtime['run_id'] == '20261020T110323Z_27da680b90f1' and
            runtime['host_build_id'] == '20261018T024443Z_23a2e7fdb8ea' and
            runtime['current_source_candidate'] is False and
            index['prepared_runtime_matches_latest_source'] is False and
            index['full_engine_goal_complete'] is False, 'Prepared runtime or goal scope changed')
    before = dict(index=artifact(INDEX), document=artifact(DOC))
    backups = []
    for name, path in (('index', INDEX), ('document', DOC)):
        dest = STAGE / ('publication_' + name + '.before.gz')
        require(not dest.exists(), 'Inspect existing publication backup')
        raw = path.read_bytes()
        compressed = gzip.compress(raw, mtime=0)
        require(gzip.decompress(compressed) == raw, 'Backup roundtrip failed')
        dest.write_bytes(compressed)
        backups.append(dict(original=before[name], compressed=artifact(dest), roundtrip=True))
    paragraph = '\n'.join([
        '## Current full base SDK compile and link (not executed)', '',
        'This later integration stage supersedes the earlier component snapshots only for current base-SDK compile/link readiness. Their syntax, wire and no-full-rebuild claims describe those earlier runs and retain their original scope. No historical component report is relabelled as a full build or runtime pass.', '',
        'The current incremental x64 build validates all **161 translation units**: **37 recompiled, 124 reused**, with all **162 cached outputs** (161 AMD64 objects and one PCH) and **1,374 tracked inputs** authenticated. This is not a clean rebuild. The current checked vector-count helper, PlayerTraits and eighteen direct-count fixes in eight SDK cpp files are included in this base object set. Compiler exit code is zero, with no unique errors or critical numeric-conversion diagnostics; other legacy warnings are not claimed absent. Existing source, cache and provider paths were reused; no SDK tree or game data copy was created.', '',
        'The actual linker consumes those current 161 objects, the **16 retained providers**, 14 explicit platform-library inputs and authenticated CRT/default libraries. Its exit code is zero with **zero unresolved symbols and zero linker warnings**. Static PE inspection confirms AMD64 PE32+, ASLR/NX, exactly the three definition exports and matching export addresses in the link map. The import-module set matches the earlier base DLL. Localized library-search lines are separate from final map owner/member evidence: searched inputs are not all claimed as selected. The Korean log emits no Loaded member lines; final archive membership comes from the map and is labelled accordingly. No DLL loading is involved.', '',
        'The new base DLL is a build component, not a replacement for the prepared runtime DLL. SaveRestore, shared-Lua, FoundValue and other runtime object overlays are not used or rebased here. B11, prepared R11, the Host, launcher, release metadata and the original-game test hold remain unchanged. The retail-state framing readers are not made into a live retail loader by linking this DLL. SDK restore, retail save writing/reopening, full original UI/3D/campaign behavior and measured multicore performance remain unverified.', '',
        'Exact inputs, child commands, PE/map checks and artifacts are recorded in `evidence/sdk_current/compile_result.json`, `base_link_result.json` and `base_link_validation.json`. Changed metadata is protected by changed-file gzip backups. Two obsolete validation PCHs totaling **9,830,400 bytes** and regenerated failed link attempts are retired with path/identity/hash receipts; the current object cache and verified base DLL remain retained.', '',
    ])
    text = DOC.read_text(encoding='utf-8')
    marker = '## Limits of external container evidence'
    require(marker in text and '## Current full base SDK compile and link (not executed)' not in text,
            'Document insertion boundary changed')
    DOC.write_text(text.replace(marker, paragraph + '\n' + marker, 1), encoding='utf-8')
    documentation = artifact(DOC)
    for value in index.values():
        if isinstance(value, dict) and isinstance(value.get('documentation'), dict) and \
                key(value['documentation']['path']) == key(DOC):
            value['documentation'] = documentation
    proofs = {
        'prebuild': artifact(STAGE / 'prebuild.json'),
        'compile': artifact(STAGE / 'compile_result.json'),
        'link': artifact(result_path), 'validation': artifact(link['validation']['path']),
        'current_recipe': unchanged(compilation['current_recipe']),
        'current_manifest': unchanged(compilation['current_manifest']),
        'validation_pch_retirement': artifact(STAGE / 'validation_pch_retirement.json'),
    }
    stage = dict(status='PASS_CURRENT_BASE_SDK_COMPILE_LINK_NOT_LOADED', proofs=proofs,
        translation_units=161, recompiled_units=37, reused_units=124, clean_rebuild=False,
        full_sdk_base_compile_verified=True, base_dll_link_verified=True, base_only=True,
        generated_dll=link['generated_dll'], exports=sorted(link['pe']['exports']), unresolved_symbols=0,
        provider_count=16, explicit_platform_library_inputs=14, compiler_jobs=1,
        hidden_below_normal_children=True, critical_numeric_warnings=0,
        other_legacy_warnings_claimed_absent=False, historical_component_proof_scope_preserved=True,
        documentation=documentation, **{name: False for name in false_flags})
    require('sdk_current_base_compile_link_stage' not in index, 'Current SDK stage already exists')
    index['sdk_current_base_compile_link_stage'] = stage
    index['latest_sdk_source_matches_base_link_candidate'] = True
    index['current_goal_turn_classification'] = 'progress'
    index['utc'] = datetime.now(timezone.utc).isoformat()
    require(json.dumps(index['current_prepared_runtime'], sort_keys=True) == runtime_before,
            'Prepared runtime must remain identical')
    for name, old in historical_stages.items():
        require(index[name]['full_sdk_recompiled'] is False and
                {k:v for k,v in index[name].items() if k != 'documentation'} ==
                {k:v for k,v in old.items() if k != 'documentation'}, 'Historical scope changed')
    write(INDEX, index)
    for row in [*protected, *terrain, *prebuild['protected'], *link['inputs']]:
        if key(row['path']) not in (key(INDEX), key(DOC)):
            unchanged(row)
    receipt = dict(status='PUBLISHED_CURRENT_BASE_SDK_COMPILE_LINK_NOT_LOADED',
        utc=datetime.now(timezone.utc).isoformat(), builder=artifact(__file__),
        before=before, after=dict(index=artifact(INDEX), document=artifact(DOC)), backups=backups,
        proofs=proofs, frozen_runtime_inputs_unchanged=24, shared_terrain_inputs_unchanged=2,
        historical_input_identities_of_modified_index_and_doc_preserved=True,
        prepared_runtime_entire_record_unchanged=True, stage=stage,
        full_engine_goal_complete=False)
    write(STAGE / 'progress_update.json', receipt)
    print(json.dumps(dict(status=receipt['status'], index=receipt['after']['index'],
        document=receipt['after']['document'], receipt=artifact(STAGE / 'progress_update.json'))))


if __name__ == '__main__':
    main()
