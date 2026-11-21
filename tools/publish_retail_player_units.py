"""Publish the bounded Unit component proof without promoting a runtime."""
from __future__ import annotations

from datetime import datetime, timezone
import ctypes
import gzip
import hashlib
import json
import msvcrt
from pathlib import Path
import sys

sys.dont_write_bytecode = True
from verify_retail_save_header import artifact, require, key

PROJECT = Path(__file__).resolve().parents[1]
STAGE = PROJECT / 'evidence/retail_save_container/player_units'
INDEX = PROJECT / 'evidence/save_menu/20261013_original_screen/current_progress.json'
DOCUMENT = PROJECT / 'docs/M7_RETAIL_SAVE_BOUNDARY.md'
BASELINES = {
    'index': '367f6a5a83bfdf92647c892aad618f2ffb911ac7da72ce6bdcdb39451a556a2a',
    'document': '63d389d2156a852636a5fb62a5bc0d871c3d939be7f931e5316b11d8930087c6',
}


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def same(row):
    current = artifact(row['path'])
    require(current['sha256'] == row['sha256'] and
            ('bytes' not in row or current['bytes'] == row['bytes']), 'Changed input: ' + row['path'])


class FileStandardInfo(ctypes.Structure):
    _fields_ = [('allocation', ctypes.c_longlong), ('eof', ctypes.c_longlong),
               ('links', ctypes.c_ulong), ('delete_pending', ctypes.c_ubyte), ('directory', ctypes.c_ubyte)]


def allocation(path):
    # Metadata only. No GameCore, renderer, window, registry or process access.
    api = ctypes.WinDLL('kernel32', use_last_error=True).GetFileInformationByHandleEx
    api.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_ulong]
    api.restype = ctypes.c_int
    info = FileStandardInfo()
    before = path.stat()
    with path.open('rb') as stream:
        require(api(msvcrt.get_osfhandle(stream.fileno()), 1, ctypes.byref(info), ctypes.sizeof(info)) != 0,
                'File allocation query failed')
    require(info.eof == before.st_size and info.links == before.st_nlink and not info.directory,
            'Allocation identity differs')
    return int(info.allocation)


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
    require(build['status'] == 'PASS_X64_RETAIL_PLAYER_UNITS_COMPONENT' and
            build['protected_unchanged'] is True and not build['full_engine_goal_complete'] and
            build['public_unit_bodies_structurally_framed'] is True and not build['host_gamecore_or_hwnd_executed'],
            'Missing bounded component proof')
    for row in build['inputs'] + build['source_inputs'] + build['protected']:
        same(row)
    same(build['source_conformance'])
    for mode in build['results']:
        for name in ('executable', 'dependencies', 'response', 'compile_log', 'test_log'):
            same(mode[name])
    test = build['results'][0]['test']
    public = test['public']
    require(public['unit_count'] > 0 and public['start_offset'] == 2428055 and
            public['next_inflated_offset'] > 2428055, 'Wrong occupied unit-pool witness')
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
## Player unit list and complete Unit v9 wire bodies

`RetailSavePlayerUnits.h` frames the actual free-list header and calls the Unit
v9 parser for every declared live object. `RetailSaveUnitArchive.h` follows C++
member declaration order, not the misleading constructor initializer-list order.
Its 147 registered values consist of 124 raw32 values, 11 bools, two opaque
strings and ten counted integer vectors, with a structural minimum of 555 bytes.
The first six values are owner, original owner, raw unit type, X, Y and unit ID.
Full archives omit count, version, name and delta-index metadata; the component
source evidence distinguishes retained original x86 evidence from the current
provider's implementation. No private full-save format is substituted.

The remaining v9 fields include scalar type hash/turn, sparse promotions, three
IDInfo pairs, a counted domain vector, three integers, a bool, 28 integers, the
current display name, scenario data, UnitReligion v2, GreatWork hash/tourism and
20-byte mission rows. Promotion hash zero still has a bool; its catalog size is
metadata, not an allocated dense table. Mission queue estimate 12 is not a cap.
A complete structural Unit has a minimum of 768 bytes, plus variable payloads.

The mandatory writer profile requires the GreatWork hash word that v9 Read
always consumes. The original Write database-query failure branch can omit this
word. That incomplete output is not inferred, scanned for, or repaired here;
this writer defect remains a separate gate before general save/restore approval.

Optimized and checked x64 headless builds each passed {test['checks']:,} checks,
{test['truncations']:,} truncated inputs and {test['mutations']:,} deterministic
mutations. Literal fixtures cover nonempty vectors/promotions, opaque strings,
mission counts above the estimate, free-list holes and multiple real body reads.
Returned mutations demonstrate bounded framing, not semantic or ruleset validity.

The authenticated public RAM-only input follows Map, 64 Teams, all previous
Player stages and the empty city list to inflated offset 2,428,055. This stage
frames {public['unit_count']} actual Unit bodies and reaches inflated offset
{public['next_inflated_offset']:,}. IDs, owners, coordinates and the exact following
army-pool header are cross-checked in the standalone test. This is structural
public-wire evidence, not instantiated SDK state, resolved catalogs or restored
gameplay. No full save body or embedded database is retained.

Evidence: `evidence/retail_save_container/player_units/build_result.json` and
`source_conformance.json`. Armies, operations, remaining Players/Supporting,
compression finish, cross-object/ruleset validation, SDK restore, UI/3D, campaign
and useful multicore performance remain unfinished. The Host, SDK DLL, default
publication, prepared runtimes and native execution hold are unchanged. This
component is not integrated into the current Host and approves no restore.

'''
    text = before_bytes['document'].decode('utf8')
    marker = '## Player city list and complete CityAI wire bodies'
    require(text.count(marker) == 1, 'Missing unique documentation insertion point')
    # Preserve all existing bytes, including line endings, outside the insertion.
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
    stage = {'status': 'PASS_UNIT_V9_WIRE_COMPONENT_PUBLIC_OCCUPIED_UNIT_LIST_ONLY_RESTORE_PENDING',
        'headers': [artifact(PROJECT / 'Source/Host' / name) for name in (
            'RetailSavePlayerUnits.h', 'RetailSaveUnit.h',
            'RetailSaveUnitArchive.h', 'RetailSaveUnitServices.h', 'RetailSaveFreeList.h')],
        'test': artifact(PROJECT / 'Tests/retail_player_units.cpp'),
        'component_proof': artifact(build_path), 'source_conformance': build['source_conformance'],
        'public': public, 'checks_per_mode': test['checks'], 'truncations_per_mode': test['truncations'],
        'mutations_per_mode': test['mutations'], 'synthetic_cases': test['synthetic_cases'],
        'unit_minimum_bytes': 768, 'archive_minimum_bytes': 555, 'archive_registered_fields': 147,
        'great_work_hash_word_profile_explicit': True, 'public_unit_bodies_structurally_framed': True,
        'unit_object_id_placement_verified': False,
        'player_structure_framed': False, 'ruleset_compatibility_verified': False,
        'sdk_restore_verified': False, 'integrated_into_current_host': False,
        'protected_input_count': len(build['protected']),
        'retired_intermediate_logical_bytes': build['retired_logical_bytes'],
        'documentation': document, 'full_engine_goal_complete': False}
    require('retail_player_units_stage' not in index, 'Existing city publication needs review')
    index['retail_player_units_stage'] = stage
    index['status'] = 'RETAIL_UNIT_OBJECTS_COMPONENT_PASS_ARMIES_OPERATIONS_AND_RESTORE_PENDING'
    index['full_engine_goal_complete'] = False
    require(index.get('current_prepared_runtime') == preserved_runtime and
            index.get('default_publication') == preserved_default, 'Runtime publication was changed')
    INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    receipt = {'schema': 'zerosis.retail.player_units.publication.v1',
        'status': 'PUBLISHED_UNIT_COMPONENT_AND_PUBLIC_OCCUPIED_UNIT_LIST_ONLY',
        'publisher': artifact(Path(__file__)),
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
