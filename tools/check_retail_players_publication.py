"""Read-only content checks and a scoped allocation receipt for the 64-player proof."""
from __future__ import annotations

from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
from verify_retail_save_header import artifact, require, key, within
from publish_retail_player_units import allocation, read, same
from inspect_players_sources import inspect
from current_runtime_sdk_input import validate_current_runtime_sdk

PROJECT = Path(__file__).resolve().parents[1]
STAGE = PROJECT / 'evidence/retail_save_container/players'
INDEX = PROJECT / 'evidence/save_menu/20261013_original_screen/current_progress.json'
DOCUMENT = PROJECT / 'docs/M7_RETAIL_SAVE_BOUNDARY.md'


def main():
    require(len(sys.argv) == 1 and not sys.flags.optimize, 'Unexpected post-check arguments')
    target = STAGE / 'post_publication_checks.json'
    require(not target.exists(), 'This post-publication receipt is one-use')
    build = read(STAGE / 'build_result.json')
    publication = read(STAGE / 'progress_update.json')
    require(build['status'] == 'PASS_X64_RETAIL_PLAYERS_COMPONENT' and
            publication['status'] == 'PUBLISHED_64_PLAYER_WIRE_AND_PUBLIC_SUPPORTING',
            'Missing build or publication')
    same(publication['publisher'])
    for row in build['inputs'] + build['source_inputs']:
        same(row)
    same(build['source_conformance'])
    require(inspect(PROJECT) == read(build['source_conformance']['path']),
            'Source conformance differs after publication')
    changed = {key(INDEX): publication['after']['index'], key(DOCUMENT): publication['after']['document']}
    for row in build['protected']:
        if key(row['path']) in changed:
            same(changed[key(row['path'])])
            name = 'index' if key(row['path']) == key(INDEX) else 'document'
            require(row == publication['before'][name], 'Unreviewed metadata baseline')
        else:
            same(row)
    for mode in build['results']:
        for name in ('executable', 'dependencies', 'response', 'compile_log', 'test_log'):
            same(mode[name])
        require(not Path(mode['object']['path']).exists(), 'Retired object unexpectedly remains')
    for row in build['retired_intermediates']:
        require(not Path(row['path']).exists(), 'A retired intermediate unexpectedly remains')
    require(build['results'][0]['test'] == build['results'][1]['test'], 'Mode results differ')
    public = build['results'][0]['test']['public']
    require(public['all_expected_players_wire_framed'] and public['player_count'] == 64 and
            public['supporting_bytes'] == 4116 and public['plaintext_following_bytes'] == 0 and
            build['remaining_players_framed'] and build['public_plaintext_structurally_framed'],
            'Wrong bounded player-block and Supporting evidence')

    before = {}
    for row in publication['backups']:
        same(row['compressed'])
        content = gzip.decompress(Path(row['compressed']['path']).read_bytes())
        import hashlib
        require(len(content) == row['original']['bytes'] and
                hashlib.sha256(content).hexdigest() == row['original']['sha256'], 'Backup differs')
        before[key(row['original']['path'])] = content
    expected = json.loads(before[key(INDEX)])
    document = artifact(DOCUMENT)

    def rebind(value):
        if isinstance(value, dict):
            if value.get('path') and key(value['path']) == key(DOCUMENT) and \
                    value.get('sha256') == publication['before']['document']['sha256']:
                value.update(document)
            else:
                for item in value.values():
                    rebind(item)
        elif isinstance(value, list):
            for item in value:
                rebind(item)

    rebind(expected)
    expected['retail_players_stage'] = publication['stage']
    expected['status'] = 'RETAIL_PUBLIC_PLAINTEXT_FRAMED_CONTAINER_AND_RESTORE_PENDING'
    expected['full_engine_goal_complete'] = False
    require(expected == read(INDEX), 'Unrelated progress fields changed')
    marker = b'## One complete PlayerAI wire object and the Player suffix'
    old_head, old_tail = before[key(DOCUMENT)].split(marker, 1)
    new_head, new_tail = DOCUMENT.read_bytes().split(marker, 1)
    require(new_head.startswith(old_head) and new_tail == old_tail and
            new_head.count(b'## Contiguous initialized Player block and Supporting boundary') == 1,
            'Existing documentation bytes changed')

    sdk = validate_current_runtime_sdk(PROJECT / 'evidence/sdk_runtime_current/build_result.json',
        'dc7dd791816a870a1e6b55778b5f718ebf8f04418edf9e9a7eac5527f82bd303')
    request = PROJECT / 'evidence/interactive_game/20261022T001546Z_7fba195072e4/request.json'
    require(artifact(request)['sha256'] == 'c47775cec96ae5fc762ebadf394d894fcd524e7314ed8428d52b5220028477e7',
            'Current prepared request changed')
    runtime_inputs = read(request)['runtime_inputs']
    require(len(runtime_inputs) == 24, 'Current runtime input count differs')
    for row in runtime_inputs:
        same(row)
    hold = PROJECT / 'evidence/goody_hut/runtime_fonts/system_freeze_hold.json'
    require(artifact(hold)['sha256'] == '6e7443f5ef796c9eadee4f7fdbc4123545467031be1d5c641159283078f56a5b' and
            read(hold)['engine_native_execution_still_held'] is True and
            read(hold)['offline_resume']['native_host_gamecore_hwnd_execution_allowed'] is False,
            'Native execution hold changed')

    paths = [PROJECT / 'Source/Host/RetailSavePlayers.h']
    paths += [PROJECT / 'Tests/retail_players.cpp']
    paths += [PROJECT / 'tools' / name for name in ('inspect_players_sources.py',
        'verify_retail_players.py', 'publish_retail_players.py', 'check_retail_players_publication.py',
        'retire_failed_players_attempt.py')]
    root = Path(build['build_root'])
    require(within(root, PROJECT / 'Build/RetailSavePlayers'), 'Build path escaped')
    build_files = [p for p in root.rglob('*') if p.is_file()]
    require(len(build_files) == 6, 'Unexpected retained build files')
    paths += build_files
    paths += [p for p in STAGE.iterdir() if p.is_file() and p != target]
    paths = list({key(p): p for p in paths}.values())
    retained, identities = [], set()
    for path in paths:
        stat = path.lstat()
        require(not getattr(stat, 'st_file_attributes', 0) & 0x400, 'Reparse retained file')
        identity = (stat.st_dev, stat.st_ino)
        row = {**artifact(path), 'file_identity': list(identity),
               'allocated_file_data_bytes': allocation(path), 'links': stat.st_nlink}
        require(identity not in identities, 'Unexpected hardlink overlap in scoped new files')
        identities.add(identity)
        retained.append(row)
    metadata_logical_delta = sum(publication['after'][n]['bytes'] - publication['before'][n]['bytes']
                                 for n in ('index', 'document'))
    metadata_allocation_delta = sum(publication['publication_allocation_after'][n] -
        publication['publication_allocation_before'][n] for n in ('index', 'document'))
    report = {'schema': 'zerosis.retail.players.post_publication.v1',
        'status': 'PASS_64_PLAYERS_AND_PUBLIC_SUPPORTING_POST_PUBLICATION_CHECKS',
        'utc': datetime.now(timezone.utc).isoformat(), 'build': artifact(STAGE / 'build_result.json'),
        'publication': artifact(STAGE / 'progress_update.json'), 'index': artifact(INDEX), 'document': document,
        'source_input_count': len(build['source_inputs']), 'component_input_count': len(build['inputs']),
        'source_conformance_recomputed_equal': True, 'protected_input_count': len(build['protected']),
        'protected_unchanged_except_exact_index_and_document_publication': True,
        'existing_progress_scope_preserved': True, 'existing_documentation_bytes_preserved': True,
        'current_sdk_artifacts': sdk, 'current_prepared_request': artifact(request),
        'current_prepared_runtime_input_count': len(runtime_inputs), 'native_execution_hold': artifact(hold),
        'native_execution_still_held': True, 'public': public,
        'retained_new_files': retained, 'retained_path_count': len(paths),
        'retained_unique_file_count': len(identities),
        'new_file_logical_bytes': sum(x['bytes'] for x in retained),
        'new_file_allocated_bytes': sum(x['allocated_file_data_bytes'] for x in retained),
        'existing_metadata_logical_delta': metadata_logical_delta,
        'existing_metadata_allocated_delta': metadata_allocation_delta,
        'scoped_net_logical_delta': sum(x['bytes'] for x in retained) + metadata_logical_delta,
        'scoped_net_allocated_file_data_delta': sum(x['allocated_file_data_bytes'] for x in retained) + metadata_allocation_delta,
        'allocation_api': 'GetFileInformationByHandleEx(FileStandardInfo).AllocationSize; file metadata only',
        'scope_exclusions': ['this receipt itself', 'directory and MFT allocation',
                             'unrelated existing project files', 'volume free-space changes'],
        'retired_intermediate_logical_bytes': build['retired_logical_bytes'],
        'retired_allocation_not_measured': True, 'host_gamecore_or_hwnd_executed': False,
        'original_game_settings_or_user_saves_accessed': False, 'full_player_framed': True,
        'remaining_players_framed': True, 'public_plaintext_structurally_framed': True,
        'compression_finish_verified': False, 'sdk_restore_verified': False,
        'ruleset_compatibility_verified': False, 'full_engine_goal_complete': False}
    target.write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'status': report['status'], 'receipt': artifact(target),
        'scoped_allocated_bytes_including_receipt': report['scoped_net_allocated_file_data_delta'] + allocation(target),
        'retired_logical_bytes': report['retired_intermediate_logical_bytes']}))


if __name__ == '__main__':
    main()
