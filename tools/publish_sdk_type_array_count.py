"""Publish scoped vector-count and public-Team evidence; never promote a runtime."""
from __future__ import annotations
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
from verify_retail_save_header import artifact, require

PROJECT = Path(__file__).absolute().parents[1]
STAGE = PROJECT/'evidence/serialization/type_array_count'
INDEX = PROJECT/'evidence/save_menu/20261013_original_screen/current_progress.json'
DOC = PROJECT/'docs/M7_RETAIL_SAVE_BOUNDARY.md'


def main():
    require(len(sys.argv) == 1 and not sys.flags.optimize, 'Unexpected publication arguments')
    require(artifact(INDEX)['sha256'] == 'a61a311f68047dbab294b34ea387915c98f3b774e295797732f619e01baa1675' and
        artifact(DOC)['sha256'] == 'fc0659c49c4695be5524ecbe2638cc1e872c5fe063ac45e4324f3e7d7ba7c990', 'Publication baseline changed')
    proof_path = STAGE/'build_result.json'
    require(artifact(proof_path)['sha256'] == '14c0edb33f21c2b2f95bb5db5a2a5374e44a064b66e70b4ab57253b6d44bbba7', 'Reviewed native proof changed')
    proof = json.loads(proof_path.read_text(encoding='utf-8'))
    require(proof['status'] == 'PASS_SDK_VECTOR_COUNT_ABI_COMPONENT' and proof['protected_unchanged'] and
        proof['public_teams_framed'] and not proof['full_sdk_recompiled'] and not proof['host_gamecore_or_hwnd_executed'], 'Scoped native evidence required')
    for row in proof['inputs']+proof['protected']:
        require(artifact(row['path']) == row, 'Verified input/protected artifact changed')
    for result in proof['results']:
        for row in [result['executable'], result['map'], result['test_log'], *result['dependencies'], *result['compile_logs']]:
            require(artifact(row['path']) == row, 'Retained native evidence changed')
    tracking_path = STAGE/'port_patch_tracking.json'
    tracking = json.loads(tracking_path.read_text(encoding='utf-8'))
    require(tracking['status'] != 'BACKED_UP_TRACKING_PENDING', 'Port tracking is not finished')
    # Exact current identities are also independently checked from the recipe.
    patches_path = PROJECT/'Source/Porting/sdk_x64_patches.json'
    manifest_path = PROJECT/'evidence/sdk_x64/port_manifest.json'
    helper = PROJECT/'Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvInfosSerializationHelper.h'
    relative = 'CvGameCoreDLL_Expansion2/CvInfosSerializationHelper.h'
    original = PROJECT/'Source/SDK_BNW_Original'/relative
    patches = json.loads(patches_path.read_text(encoding='utf-8'))['patches']
    regenerated = original.read_bytes()
    applied = []
    for patch in [p for p in patches if p['file'] == relative]:
        old, new = patch['old'].encode('latin1'), patch['new'].encode('latin1')
        require(patch['source_sha256'] == artifact(original)['sha256'] and regenerated.count(old) == patch['count'], 'Tracked vector-count patch drift')
        regenerated = regenerated.replace(old, new); applied.append(patch['id'])
    require(regenerated == helper.read_bytes() and len(applied) == 5, 'Tracked recipe does not reproduce helper')
    rows = [r for r in json.loads(manifest_path.read_text(encoding='utf-8')) if r['relative_path'] == relative]
    require(len(rows) == 1 and rows[0]['port_sha256'] == artifact(helper)['sha256'] and rows[0]['patch_ids'] == applied,
        'Working SDK manifest does not bind the tracked correction')
    before = dict(index=artifact(INDEX), document=artifact(DOC))
    for source, name in ((INDEX, 'current_progress.before_publication.json.gz'), (DOC, 'M7_RETAIL_SAVE_BOUNDARY.before_count_fix.md.gz')):
        target = STAGE/name
        require(not target.exists(), 'Publication backup already exists')
        target.write_bytes(gzip.compress(source.read_bytes(), mtime=0))
    row = proof['results'][1]['public_probe']['result']['public']
    require(row == proof['results'][2]['public_probe']['result']['public'], 'Native public modes disagree')
    section = f'''## SDK vector-count correction and public Team witness

The x64 `CvInfosSerializationHelper.h` previously passed `std::vector::size()` directly to `FDataStream` in four writer overloads. Original Win32 `size_t` is four bytes; native x64 `size_t` is eight, while all four readers consume a four-byte `uint`. `WriteDataArray`, `WriteHashedDataArray`, `WriteTypeArray` and `WriteHashedTypeArray` now convert through `CvChecked::Integer<uint>` before the first stream write and use that same count for iteration. Values above `UINT_MAX` fail before output; payloads, IDs, keys and schemas are unchanged. The working port recipe and manifest reproduce the corrected header exactly. The current Host and frozen R11 were not rebuilt or promoted.

`Tests/sdk_type_array_count.cpp` authenticates exact extracted template bodies and uses the actual archived x86 SDK stream and the retained x64 stream provider. Only type/hash resolution uses deterministic test hooks; real database IDs are not verified. Twelve empty/single/populated cases per writer family compare literal little-endian counts, complete payloads, following sentinels and EOF positions. The original x86 run passes **188 checks** with count width four. Both x64 `/O2` and `/Od /RTC1` pass **28,972 checks**: original and pre-fix bodies produce eight-byte negative controls; the corrected bodies produce four bytes with identical payloads. The actual narrowing helper accepts `UINT_MAX` and rejects `UINT_MAX+1`, without allocating a giant vector. C++14 matches the retained SDK's legacy declarations; VC9's encoding-only C4819 is suppressed without rewriting its original header. Full SDK translation units have not been recompiled for this change.

`RetailSaveSupporting.h` provides only an explicitly supplied-offset framing API for **276 + 4 * plotCount** bytes: parent v1, Barbarians v1, two unprefixed short arrays, Goody v1 and 22 by 3 signed integers. Its independent fixtures cover plot counts 0/1/960, nonzero starts, valid negative payloads, budgets, versions and **14,094 truncations** in each x64 mode. This does not establish its retail placement.

On the same authenticated public input, `RetailSaveMap` first recomputes the full Map end using the explicit, still ruleset-unverified profile five. `RetailSaveTeam.h` then frames **64** Team v1/Techs v1 records with IDs **0 through 63** from **{row['teams_offset']}** to **{row['teams_end']}**, spanning **{row['teams_bytes']:,} bytes** and **{row['array_records']:,} counted array records**. Both native modes pass **29,044 checks** including this witness. There is no signature/version scanning. Team project-art row lengths come from preceding project counts; unresolved framing hashes are rejected rather than guessed. Supporting is rejected both directly after Map and at the obtained Team end. Therefore the private archive's Map/Supporting/Team order is not a retail oracle. **{9762327-row['teams_end']:,} following bytes remain unframed**. Team-specific synthetic/truncation/mutation coverage remains a separate gate; this corpus witness does not replace it.

The public save, inflated body and embedded database are never retained as files. The original nonfinal compression termination, following Player/supporting state, unsupported layouts, ruleset compatibility, SDK restore, original save writing/reopening and actual UI/gameplay remain unresolved. `serialization/type_array_count/build_result.json` preserves exact inputs, real compiler/link evidence, commands and retired object identities. Prepared R11 still preserves B11's frozen graph and is not the latest working-source candidate. Host/GameCore/window execution remains held during the user's original-game test.

'''
    text = DOC.read_text(encoding='utf-8')
    marker = '## Limits of external container evidence\n'
    require(marker in text and '## SDK vector-count correction and public Team witness' not in text, 'Documentation marker changed')
    text = text.replace('Supporting, Team and Player records remain unframed.', 'Supporting placement and Player records remain unresolved; the later Team witness is described below.')
    text = text.replace('No SDK serializer or save schema was changed.', 'That Game/Map-prefix stage changed no SDK serializer or save schema; the later vector-count ABI correction is described below.')
    text = text.replace('**8,067,177 following bytes remain unparsed**; no private section order is inferred for them.',
        'The Map component alone leaves **8,067,177 following bytes unparsed**; the later Team witness below narrows that remainder without inferring a private section order.')
    DOC.write_text(text.replace(marker, section+marker), encoding='utf-8')
    index = json.loads(INDEX.read_text(encoding='utf-8'))
    index['status'] = 'SDK_VECTOR_COUNT_ABI_AND_PUBLIC_TEAM_FRAMING_PASS_CURRENT_HOST_NATIVE_PENDING'
    index['sdk_vector_count_abi_stage'].update(status='PASS_REAL_SDK_STREAM_ABI_FULL_SDK_AND_HOST_REBUILD_PENDING',
        native_fix_verified=True, component_proof=artifact(proof_path), port_tracking=artifact(tracking_path),
        patch_recipe=artifact(patches_path), working_port_manifest=artifact(manifest_path),
        full_sdk_recompiled=False, integrated_into_current_host=False, original_x86_checks=188,
        x64_checks_per_mode=28972, standalone_wire_proof_only=True, ruleset_compatibility_verified=False,
        sdk_restore_verified=False, documentation=artifact(DOC))
    index['retail_post_map_stage'].update(status='PASS_PUBLIC_TEAM_BATCH_FRAMING_SUPPORTING_PLACEMENT_UNRESOLVED',
        public_team_batch_framed=True, component_proof=artifact(proof_path), public=row,
        public_x64_checks_per_mode=29044, supporting_truncations_per_mode=14094,
        supporting_after_teams_matches_public=False, team_synthetic_adversarial_coverage_verified=False,
        original_coordinator_order_confirmed=False, whole_retail_container_verified=False,
        ruleset_compatibility_verified=False, sdk_restore_verified=False, integrated_into_current_host=False,
        documentation=artifact(DOC))
    for name in ('retail_save_header_stage', 'retail_save_pregame_stage', 'retail_save_inflate_stage',
                 'retail_save_state_stage', 'retail_save_map_stage'):
        index[name]['documentation'] = artifact(DOC)
    require(index['prepared_runtime_matches_latest_source'] is False and
        index['current_prepared_runtime']['current_source_candidate'] is False and
        index['full_engine_goal_complete'] is False, 'Runtime/full-goal scope changed')
    INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    receipt = dict(status='PUBLISHED_SDK_VECTOR_COUNT_AND_PUBLIC_TEAM_COMPONENTS', utc=datetime.now(timezone.utc).isoformat(),
        before=before, after=dict(index=artifact(INDEX), document=artifact(DOC)), native_proof=artifact(proof_path),
        port_tracking=artifact(tracking_path), runtime_or_default_promoted=False, full_engine_goal_complete=False)
    (STAGE/'progress_update.json').write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
    request = json.loads(Path(index['current_prepared_runtime']['request']['path']).read_text(encoding='utf-8'))
    require(len(request['runtime_inputs']) == 24, 'Prepared runtime input count changed')
    for entry in request['runtime_inputs']:
        path = Path(entry['path'])
        require(path.is_relative_to(PROJECT) and artifact(path)['sha256'] == entry['sha256'], 'Frozen prepared runtime input changed')
    seen, retained, total = set(), [], 0
    for folder in (Path(proof['build_root']), STAGE, PROJECT/'evidence/retail_save_container/post_map'):
        for path in sorted(folder.rglob('*')):
            if not path.is_file(): continue
            info = path.stat(); identity = (info.st_dev, info.st_ino)
            if identity in seen: continue
            seen.add(identity); total += info.st_size
            retained.append(dict(**artifact(path), file_identity=list(identity)))
    retired = proof['retired_logical_bytes'] + sum(json.loads(p.read_text(encoding='utf-8'))['retired_logical_bytes']
        for p in STAGE.glob('retired_failed_attempt_*.json'))
    checks = dict(status='PASS_PUBLISHED_COMPONENTS_AND_PRESERVED_RUNTIME', index=artifact(INDEX), document=artifact(DOC),
        retained_evidence_and_build=retained, retained_evidence_and_build_logical_bytes=total,
        storage_receipt_itself_excluded=True, retired_logical_bytes=retired, frozen_runtime_inputs_unchanged=24,
        current_source_runtime_rebuilt=False, full_engine_goal_complete=False)
    (STAGE/'post_publication_checks.json').write_text(json.dumps(checks, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(status=receipt['status'], index=receipt['after']['index'], document=receipt['after']['document'])))


if __name__ == '__main__':
    main()
