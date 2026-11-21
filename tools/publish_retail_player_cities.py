"""Publish the bounded CityAI component proof without promoting a runtime."""
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
STAGE = PROJECT / 'evidence/retail_save_container/player_cities'
INDEX = PROJECT / 'evidence/save_menu/20261013_original_screen/current_progress.json'
DOCUMENT = PROJECT / 'docs/M7_RETAIL_SAVE_BOUNDARY.md'
BASELINES = {
    'index': 'fa10ff4dff429f2b57cced2b92a49524aafab5a3ca6e9808ed9d65648645250d',
    'document': '542e233c944412da105a1cedadf144b5182896f909b562b62a5000ae69673e3a',
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
    require(build['status'] == 'PASS_X64_RETAIL_PLAYER_CITIES_COMPONENT' and
            build['protected_unchanged'] is True and not build['full_engine_goal_complete'] and
            not build['occupied_city_publicly_verified'] and not build['host_gamecore_or_hwnd_executed'],
            'Missing bounded component proof')
    for row in build['inputs'] + build['source_inputs'] + build['protected']:
        same(row)
    same(build['source_conformance'])
    for mode in build['results']:
        for name in ('executable', 'dependencies', 'response', 'compile_log', 'test_log'):
            same(mode[name])
    test = build['results'][0]['test']
    public = test['public']
    require(public['city_count'] == 0 and public['start_offset'] == 2427999 and
            public['next_inflated_offset'] == 2428055, 'Wrong public empty-pool witness')
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
## Player city list and complete CityAI wire bodies

`RetailSavePlayerCities.h` now frames the actual `FFreeListTrashArray<CvCityAI>`
header and calls the City v6 / CityAI v1 parser for every declared live object.
The header consists of five signed words, capacity next-free words and a signed
live count. Capacity is not a City version or a byte length. Free-chain and
count consistency are checked; complete object-ID placement is still unverified.

The portable City body covers buildings, production strategies, citizens,
religions, emphases, espionage, extra hit points and the CityAI tail. Minimum
CityAI size is 2,282 + 4P bytes, where P is an explicit project-catalog width.
Project weights omit their count on the wire. Initialized building/unit catalogs
and the six-yield source profile are explicit prerequisites, not ruleset proof.
CityAI writes two raw 80-int arrays; citizen plot flags are two raw 37-bool arrays.
The two appearances of the city name are intentional. CityCulture is not an
additional serialized member here. Zero-hash omission differs from ProcessAI's
mandatory hash/weight rows and is tested separately.

The optimized and checked x64 headless builds each passed {test['checks']:,}
checks, {test['truncations']:,} truncated inputs and {test['mutations']:,}
deterministic mutations. Independent occupied-city fixtures exercise project
widths, nonempty nested tables, free-list holes and multiple real body parses.
These generated bytes are component fixtures, not retail gameplay saves.

The authenticated public RAM-only stream follows Map, 64 Teams and the existing
Player stages into the city list at inflated offset 2,427,999. That particular
list has capacity 8 and **zero cities**, ending at 2,428,055. The next unread
word is a unit-pool field, not a discovered City version. Thus occupied CityAI
body compatibility has **not** been demonstrated on this public save. No full
save payload or embedded database was retained. The inflater finish contract,
units, armies, operations, remaining Players/Supporting, cross-object/ruleset
validation, SDK restore and real gameplay remain separate unfinished gates.

Evidence: `evidence/retail_save_container/player_cities/build_result.json` and
`source_conformance.json`. The current Host, SDK DLL, prepared runtime, default
publication and native execution hold are unchanged. This component is not
integrated into the current Host and does not approve restore or the full goal.

'''
    text = before_bytes['document'].decode('utf8')
    marker = '## Player fields from Traits to the city-object list'
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
    stage = {'status': 'PASS_CITY_AI_WIRE_COMPONENT_PUBLIC_EMPTY_CITY_LIST_ONLY_RESTORE_PENDING',
        'headers': [artifact(PROJECT / 'Source/Host' / name) for name in (
            'RetailSavePlayerCities.h', 'RetailSaveCity.h', 'RetailSaveFreeList.h',
            'RetailSaveCityServices.h', 'RetailSaveCityPopulation.h')],
        'test': artifact(PROJECT / 'Tests/retail_player_cities.cpp'),
        'component_proof': artifact(build_path), 'source_conformance': build['source_conformance'],
        'public': public, 'checks_per_mode': test['checks'], 'truncations_per_mode': test['truncations'],
        'mutations_per_mode': test['mutations'], 'synthetic_cases': test['synthetic_cases'],
        'city_ai_minimum_bytes_excluding_projects': 2282, 'project_catalog_width_explicit': True,
        'occupied_city_publicly_verified': False, 'city_object_id_placement_verified': False,
        'player_structure_framed': False, 'ruleset_compatibility_verified': False,
        'sdk_restore_verified': False, 'integrated_into_current_host': False,
        'protected_input_count': len(build['protected']),
        'retired_intermediate_logical_bytes': build['retired_logical_bytes'],
        'documentation': document, 'full_engine_goal_complete': False}
    require('retail_player_cities_stage' not in index, 'Existing city publication needs review')
    index['retail_player_cities_stage'] = stage
    index['status'] = 'RETAIL_CITY_AI_COMPONENT_PASS_PUBLIC_EMPTY_CITY_LIST_FRAMED_UNITS_AND_RESTORE_PENDING'
    index['full_engine_goal_complete'] = False
    require(index.get('current_prepared_runtime') == preserved_runtime and
            index.get('default_publication') == preserved_default, 'Runtime publication was changed')
    INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    receipt = {'schema': 'zerosis.retail.player_cities.publication.v1',
        'status': 'PUBLISHED_CITY_AI_COMPONENT_AND_PUBLIC_EMPTY_CITY_LIST_ONLY',
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
