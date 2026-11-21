"""Combine distinct exact-leaf cleanup receipts, without volume-free claims."""
import argparse, json, re, sys
from pathlib import Path
sys.dont_write_bytecode = True
STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[2]
sys.path.insert(0, str(PROJECT / 'tools'))
import build_exit_confirm_host as common


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument('--build-id', required=True)
    args = cli.parse_args()
    assert re.fullmatch(r'\d{8}T\d{6}Z_[0-9a-f]{12}', args.build_id)
    names = ['semantics/bytecode/cleanup_result.json', 'semantics/shadow/cleanup_result.json',
             'assets/package_tests/attempt1/cleanup_result.json', 'lighting_cpu/cpu/cleanup_result.json',
             'lighting_cpu/cpu_retry01/cleanup_result.json', 'pipeline/cpu01/cleanup_result.json',
             'shader/attempt01/cleanup_result.json', 'shader/attempt02/cleanup_result.json',
             'pair_preparation/' + args.build_id + '/cleanup_result.json']
    rows = []
    for name in names:
        path = STAGE / name
        value = json.loads(path.read_text('utf8'))
        assert value['status'].startswith('PASS'), (name, value['status'])
        count = next((value[key] for key in ('deleted_files', 'files_deleted', 'retired_files') if key in value), None)
        allocation = next((value[key] for key in ('released_unique_allocated_bytes', 'allocated_bytes_released', 'unique_predelete_allocated_bytes') if key in value), None)
        assert type(count) is int and type(allocation) is int, (name, list(value))
        rows.append(dict(receipt=common.artifact(path), files=count, predelete_unique_allocated_bytes=allocation))
    result = dict(status='PASS_OWNED_LIGHTING_INTERMEDIATES_SUMMARIZED', nonoverlapping_receipts=rows,
                  deleted_files=sum(row['files'] for row in rows),
                  known_unique_allocated_bytes_removed=sum(row['predelete_unique_allocated_bytes'] for row in rows),
                  volume_delta_attributed=False, unknown_allocation_inferred=False,
                  source_originals_settings_mods_default_or_user_saves_deleted=False, native_execution=False)
    with (STAGE / 'cleanup_summary.json').open('x', encoding='utf8') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps({key: value for key, value in result.items() if key != 'nonoverlapping_receipts'}))


if __name__ == '__main__':
    main()
