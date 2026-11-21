"""Publish a bounded 64-player and Supporting wire proof without changing a playable runtime."""
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
STAGE = PROJECT / 'evidence/retail_save_container/players'
INDEX = PROJECT / 'evidence/save_menu/20261013_original_screen/current_progress.json'
DOCUMENT = PROJECT / 'docs/M7_RETAIL_SAVE_BOUNDARY.md'
BASELINES = {
    'index': 'b2c7416989872d3108a35c9bad5af9c7018b956bd38e66fd56b3d18c49ea1b63',
    'document': 'b313e1da324adcd6198d551dd4292b1cba2f1d9f0ba356f69179a0e16b55f4ce',
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
    require(build['status'] == 'PASS_X64_RETAIL_PLAYERS_COMPONENT' and
            build['protected_unchanged'] is True and not build['full_engine_goal_complete'] and
            build['public_all_64_players_wire_framed'] is True and build['public_plaintext_structurally_framed'] is True and not build['host_gamecore_or_hwnd_executed'],
            'Missing bounded component proof')
    for row in build['inputs'] + build['source_inputs'] + build['protected']:
        same(row)
    same(build['source_conformance'])
    for mode in build['results']:
        for name in ('executable', 'dependencies', 'response', 'compile_log', 'test_log'):
            same(mode[name])
    test = build['results'][0]['test']
    public = test['public']
    require(public['start_offset'] == 2309550 and public['player_count'] == 64 and
            public['all_expected_players_wire_framed'] is True and
            public['supporting_bytes'] == 4116 and public['plaintext_following_bytes'] == 0,
            'Wrong source-ordered 64-player and Supporting witness')
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
## Contiguous initialized Player block and Supporting boundary

`RetailSavePlayers.h` frames 64 consecutive PlayerAI objects under a mandatory
Bnw64InSlotOrder profile and explicit Player/catalog writer parameters. Each
object must match its declared slot ID and begin at the preceding returned end.
All nested counted records share one budget across all players. Only small
per-slot spans/counts are retained; the parser creates no SDK objects and does
not copy payload data. Completion flags for object references, complete save,
ruleset compatibility and restore remain false.

Original and current CvGame::InitPlayers initialize every MAX_PLAYERS slot.
CvPlayer's non-constructor reset initializes Buildings, Techs and MinorCivAI
before alive status is selected. Minor quests reset 22 lists before minor-type
checks. Normal initialized inactive and barbarian slots use the same branch;
constructor-only or pre-initialization objects remain outside this profile.
Grand-strategy width four is still an explicit external catalog parameter,
not a universal mod assumption. City project width zero is not exercised when
no City object is present. No fallback profile or byte-pattern search is used.

The existing `RetailSaveSupporting.h` is reused byte-for-byte. Supporting v1
contains Barbarians v1, two implicit P-element int16 arrays, then GoodyHuts v1
and 22 x 3 int32 results. There are no length words, bools or padding. Its exact
size is 276 + 4P bytes, where P comes from the already framed Map. Negative
short/int values are structurally valid. Existing fixed-array budget conventions
are preserved rather than charging nonexistent serialized counts.

Optimized and checked standalone x64 builds each passed {test['checks']:,}
checks, {test['truncations']:,} truncations and {test['directed_corruptions']:,}
directed corruptions. Independent literal Supporting fixtures are distinguished
from explicitly public-derived multi-player tests. Every player-version and
slot-ID boundary, a shared exact/insufficient budget, and suffix handling are
checked; the two build observations agree.

The authenticated public RAM-only diagnostic input is followed in source order:
Game/Map, 64 Teams, then 64 complete PlayerAI objects beginning at 2,309,550.
The player block ends at {public['next_inflated_offset']:,}. Supporting immediately
follows in this corpus, occupies {public['supporting_bytes']:,} bytes for 960 plots,
and leaves {public['plaintext_following_bytes']} unframed plaintext bytes. This
establishes this corpus's contiguous placement and structural plaintext end.
The copied SDK still has no original retail top-level writer. Neither this
observation nor private .zssave section order establishes a general retail schema.
The public inflater's nonfinal termination remains an unresolved container
finish contract. No full save payload or embedded database is retained.

Evidence: `evidence/retail_save_container/players/build_result.json` and
`source_conformance.json`. Container finish, catalog/type-hash and cross-object
validation, the Unit GreatWork writer defect, SDK restore and integration,
original UI/3D, full campaign and useful measured multicore performance remain
unfinished. Current runtime bytes, default publication and the native execution
hold remain unchanged. This proof is not a playable runtime or restore approval.

'''
    text = before_bytes['document'].decode('utf8')
    marker = '## One complete PlayerAI wire object and the Player suffix'
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
    stage = {'status': 'PASS_64_PLAYER_WIRE_AND_PUBLIC_SUPPORTING_ONLY_RESTORE_PENDING',
        'headers': [artifact(PROJECT / 'Source/Host' / name) for name in (
            'RetailSavePlayers.h', 'RetailSavePlayer.h', 'RetailSaveSupporting.h')],
        'test': artifact(PROJECT / 'Tests/retail_players.cpp'),
        'component_proof': artifact(build_path), 'source_conformance': build['source_conformance'],
        'public': public, 'checks_per_mode': test['checks'], 'truncations_per_mode': test['truncations'],
        'directed_corruptions_per_mode': test['directed_corruptions'],
        'synthetic_supporting_cases': test['synthetic_supporting_cases'],
        'expected_player_slots': 64, 'all_expected_players_wire_framed': True,
        'public_plaintext_structurally_framed': True, 'compression_finish_verified': False,
        'complete_save_validated': False, 'ruleset_compatibility_verified': False,
        'sdk_restore_verified': False, 'integrated_into_current_host': False,
        'protected_input_count': len(build['protected']),
        'retired_intermediate_logical_bytes': build['retired_logical_bytes'],
        'documentation': document, 'full_engine_goal_complete': False}
    require('retail_players_stage' not in index, 'Existing Player end publication needs review')
    index['retail_players_stage'] = stage
    index['status'] = 'RETAIL_PUBLIC_PLAINTEXT_FRAMED_CONTAINER_AND_RESTORE_PENDING'
    index['full_engine_goal_complete'] = False
    require(index.get('current_prepared_runtime') == preserved_runtime and
            index.get('default_publication') == preserved_default, 'Runtime publication was changed')
    INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    receipt = {'schema': 'zerosis.retail.players.publication.v1',
        'status': 'PUBLISHED_64_PLAYER_WIRE_AND_PUBLIC_SUPPORTING', 'publisher': artifact(Path(__file__)),
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
