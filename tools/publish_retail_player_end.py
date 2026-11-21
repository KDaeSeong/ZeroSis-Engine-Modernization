"""Publish a bounded one-player wire proof without changing a playable runtime."""
from __future__ import annotations

from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
from verify_retail_save_header import artifact, require, key
from publish_retail_player_units import allocation, read, same

PROJECT = Path(__file__).resolve().parents[1]
STAGE = PROJECT / 'evidence/retail_save_container/player_end'
INDEX = PROJECT / 'evidence/save_menu/20261013_original_screen/current_progress.json'
DOCUMENT = PROJECT / 'docs/M7_RETAIL_SAVE_BOUNDARY.md'
BASELINES = {
    'index': 'e2cbfd5e3905df9316e4ba326b61bbe0b62ffd418c53b0c202d6817aac101714',
    'document': '06c06b0566266d7c7a54c9968359a4fc400d261f1142aa3ac57bcc958f8616df',
}


def main():
    require(len(sys.argv) == 1 and not sys.flags.optimize, 'Unexpected publisher arguments')
    require(not (STAGE / 'progress_update.json').exists(), 'This publisher is one-use')
    paths = {'index': INDEX, 'document': DOCUMENT}
    before_bytes = {name: path.read_bytes() for name, path in paths.items()}
    before = {name: artifact(path) for name, path in paths.items()}
    require(all(before[name]['sha256'] == sha for name, sha in BASELINES.items()),
            'Publication baseline changed; review it instead of replacing it')
    allocation_before = {name: allocation(path) for name, path in paths.items()}
    build_path = STAGE / 'build_result.json'
    build = read(build_path)
    require(build['status'] == 'PASS_X64_RETAIL_PLAYER_END_COMPONENT' and
            build['protected_unchanged'] is True and not build['full_engine_goal_complete'] and
            build['public_player0_wire_framed'] is True and not build['host_gamecore_or_hwnd_executed'],
            'Missing bounded component proof')
    for row in build['inputs'] + build['source_inputs'] + build['protected']:
        same(row)
    same(build['source_conformance'])
    for mode in build['results']:
        for name in ('executable', 'dependencies', 'response', 'compile_log', 'test_log'):
            same(mode[name])
    test = build['results'][0]['test']
    public = test['public']
    require(public['start_offset'] == 2444247 and public['next_inflated_offset'] > 2444247 and
            public['complete_player_wire_framed'] is True and
            public['first_player_id'] == 0 and public['next_player_prefix_id'] == 1,
            'Wrong source-ordered Player0 and adjacent Player1 witness')
    backups = []
    for name in paths:
        path = STAGE / ('publication_' + name + '.before.gz')
        require(not path.exists(), 'Existing publication backup needs review')
        compressed = gzip.compress(before_bytes[name], compresslevel=9, mtime=0)
        require(gzip.decompress(compressed) == before_bytes[name], 'Backup roundtrip failed')
        path.write_bytes(compressed)
        require(gzip.decompress(path.read_bytes()) == before_bytes[name], 'Saved backup roundtrip failed')
        backups.append({'original': before[name], 'compressed': artifact(path), 'roundtrip': True})

    addition = f'''
## One complete PlayerAI wire object and the Player suffix

`RetailSavePlayerEnd.h` frames the real Army free list, every live Army v1,
all 20 factory operation types, the remaining Player v16 fields and the final
CvPlayerAI v1 word. Army formation slots contain three int32 values, including
the misleadingly named m_bStartedOnOperation. Operation inheritance is followed
exactly: an inherited serializer does not add another version. An outer map-key
and operation-body ID mismatch is observed, not silently repaired or rejected
as an extra wire rule. Object-reference integrity remains unverified.

The suffix contains replay-name strings, replay-value maps, vote/unit-cost
pairs, trimmed plot IDs, two counters, 64 conquest bools, an embarked-graphic
string and Achievement v1. The mandatory current writer profile requires 64
flags and excludes the obsolete popup queue from Player versions <=10. The
minimum canonical suffix is 144 bytes. Player achievements end the base class;
the actual CvPlayerAI object adds one uint32 version 1. Stopping before this
word would not frame a complete PlayerAI object.

`RetailSavePlayer.h` assembles all seven bounded stages with one shared record
budget. It returns completePlayerWireFramed only after the final word succeeds;
completePlayerVerified, completeSaveVerified, rulesetCompatibilityVerified and
restoreApproved remain false. Explicit catalog/writer profiles are hypotheses,
not verified ruleset identities. The original retail top-level save loop is not
available in the copied SDK. The private .zssave per-player sections are not
substituted for the contiguous retail stream.

Optimized and checked headless x64 builds each passed {test['checks']:,} checks,
{test['truncations']:,} truncations and {test['mutations']:,} deterministic
mutations. Independent literal fixtures include real Army bodies and all 20
operation forms; budgets, versions, counts, bools and trailing bytes are checked.

The authenticated public RAM-only input follows Map, 64 Teams and every Player0
stage in source order, without byte-pattern searching. It reaches the suffix at
2,444,247 and the complete first PlayerAI end at {public['next_inflated_offset']:,}.
The next exact offset is independently parsed as the next Player prefix with
ID 1. This confirms one structural Player0 boundary, not all 64 players, complete
save validation or restored gameplay. No full save body or embedded database is
retained.

Evidence: `evidence/retail_save_container/player_end/build_result.json` and
`source_conformance.json`. Remaining Players/Supporting, compression finish,
cross-object/ruleset validation, the Unit GreatWork writer defect, SDK restore,
UI/3D, full campaign and useful measured multicore performance remain unfinished.
Current Host/SDK bytes, default publication and native execution hold are
unchanged. This portable component is not integrated into the current Host.

'''
    text = before_bytes['document'].decode('utf8')
    marker = '## Player unit list and complete Unit v9 wire bodies'
    require(text.count(marker) == 1, 'Missing unique documentation insertion point')
    newline = '\r\n' if b'\r\n' in before_bytes['document'] else '\n'
    addition = addition.replace('\n', newline)
    DOCUMENT.write_bytes(text.replace(marker, addition + marker, 1).encode('utf8'))
    document = artifact(DOCUMENT)
    index = json.loads(before_bytes['index'])
    preserved_runtime = json.loads(json.dumps(index.get('current_prepared_runtime')))
    preserved_default = json.loads(json.dumps(index.get('default_publication')))

    def rebind(value):
        if isinstance(value, dict):
            if value.get('path') and key(value['path']) == key(DOCUMENT) and value.get('sha256') == before['document']['sha256']:
                value.update(document)
            else:
                for item in value.values():
                    rebind(item)
        elif isinstance(value, list):
            for item in value:
                rebind(item)

    rebind(index)
    stage = {'status': 'PASS_ONE_PLAYER_WIRE_PUBLIC_PLAYER0_ONLY_RESTORE_PENDING',
        'headers': [artifact(PROJECT / 'Source/Host' / name) for name in (
            'RetailSavePlayer.h', 'RetailSavePlayerEnd.h',
            'RetailSavePlayerEndFields.h', 'RetailSavePlayerOperations.h')],
        'test': artifact(PROJECT / 'Tests/retail_player_end.cpp'),
        'component_proof': artifact(build_path), 'source_conformance': build['source_conformance'],
        'public': public, 'checks_per_mode': test['checks'], 'truncations_per_mode': test['truncations'],
        'mutations_per_mode': test['mutations'], 'synthetic_cases': test['synthetic_cases'],
        'canonical_suffix_minimum_bytes': 144, 'supported_operation_types': 20,
        'player_structure_framed': True, 'public_player0_wire_framed': True,
        'remaining_players_framed': False, 'complete_player_validated': False,
        'ruleset_compatibility_verified': False, 'sdk_restore_verified': False,
        'integrated_into_current_host': False, 'protected_input_count': len(build['protected']),
        'retired_intermediate_logical_bytes': build['retired_logical_bytes'],
        'documentation': document, 'full_engine_goal_complete': False}
    require('retail_player_end_stage' not in index, 'Existing Player end publication needs review')
    index['retail_player_end_stage'] = stage
    index['status'] = 'RETAIL_PLAYER0_WIRE_COMPONENT_PASS_REMAINING_PLAYERS_AND_RESTORE_PENDING'
    index['full_engine_goal_complete'] = False
    require(index.get('current_prepared_runtime') == preserved_runtime and
            index.get('default_publication') == preserved_default, 'Runtime publication was changed')
    INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    receipt = {'schema': 'zerosis.retail.player_end.publication.v1',
        'status': 'PUBLISHED_ONE_PLAYER_WIRE_PUBLIC_PLAYER0_ONLY', 'publisher': artifact(Path(__file__)),
        'utc': datetime.now(timezone.utc).isoformat(), 'before': before,
        'after': {name: artifact(path) for name, path in paths.items()},
        'publication_allocation_before': allocation_before,
        'publication_allocation_after': {name: allocation(path) for name, path in paths.items()},
        'allocation_api': 'GetFileInformationByHandleEx(FileStandardInfo).AllocationSize; file data only',
        'backups': backups, 'stage': stage, 'old_prepared_runtime_record_unchanged': True,
        'default_publication_record_unchanged': True, 'full_engine_goal_complete': False}
    target = STAGE / 'progress_update.json'
    target.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'status': receipt['status'], 'receipt': artifact(target)}))


if __name__ == '__main__':
    main()
