"""Protection and true-file-identity accounting for a file-only isolated runtime."""
from datetime import datetime, timezone
from pathlib import Path
import argparse, gzip, hashlib, json, os, sys
sys.dont_write_bytecode = True
STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[3]
sys.path.insert(0, str(PROJECT / 'tools'))
import build_exit_confirm_host as common
import build_menu_suite_host as builder
import retained_menu_suite_host_input as menu
from menu_suite_storage import storage


def write_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf8') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def backup(name):
    row = common.artifact(PROJECT / name)
    target = STAGE / 'source_before' / (name.replace('/', '__') + '.' + row['sha256'][:16] + '.gz')
    target.parent.mkdir(parents=True, exist_ok=True)
    assert not target.exists()
    target.write_bytes(gzip.compress(Path(row['path']).read_bytes(), mtime=0))
    assert hashlib.sha256(gzip.decompress(target.read_bytes())).hexdigest() == row['sha256']
    return dict(source=row, backup=common.artifact(target))


def begin():
    assert not (STAGE / 'startup.json').exists()
    previous = PROJECT / 'evidence/world_terrain_original/phase10/current_work.json'
    current = json.loads(previous.read_text('utf8'))
    assert current['latest_source_matches_linked_candidate'] and not current['storage']['after_pending']
    report = Path(current['current_host']['build_result']['path'])
    parent = json.loads(report.read_text('utf8'))
    refs = {common.key(row['path']): row for row in builder.protected_inventory(parent)}
    for row in menu.frozen_rows(parent).values():
        refs[common.key(row['path'])] = row
    roots = [PROJECT / 'Build/UiWindowHost' / identifier for identifier in (
        '20261116T114748Z_014dd63ad3bc', '20261115T121456Z_dbb01a1f4f50', '20261115T093013Z_23c5037b12b9')]
    roots += [PROJECT / 'Build/InteractiveGameRuntime' / identifier for identifier in (
        '20261115T134603Z_aa8853762399', '20261115T101941Z_99b3c393ee9a', '20261115T011241Z_4c8fd55e99db', '20261108T003146Z_40a8030edf08')]
    roots += [PROJECT / 'evidence/world_terrain_original/phase10', PROJECT / 'evidence/world_terrain_original/phase9/runtime_integration', PROJECT / 'evidence/world_terrain_original/phase8', PROJECT / 'evidence/world_terrain_original/phase7/runtime_integration', PROJECT / 'evidence/sdk_runtime_play/historical_os_inputs']
    roots += [Path(row['path']).parent for row in current['packages'].values()]
    for root in roots:
        for directory, names, leaves in os.walk(root, followlinks=False):
            for name in names:
                assert not os.stat(Path(directory) / name, follow_symlinks=False).st_file_attributes & 0x400
            for name in leaves:
                row = common.artifact(Path(directory) / name)
                refs[common.key(row['path'])] = row
    fixed = ['tools/' + name for name in (
        'prepare_latest_engine_pair.py', 'prepare_current_sdk_play.py', 'run_interactive_game.py',
        'runtime_input_cache.py', 'sealed_terrain_input.py', 'current_runtime_sdk_input.py',
        'retained_host_runtime_input.py', 'retained_menu_suite_host_input.py')]
    fixed += ['docs/NORMAL_REFLECTION_SHADOW_WATER_PHASE8.md']
    for path in [report, previous, *(PROJECT / name for name in fixed)]:
        row = common.artifact(path)
        refs[common.key(path)] = row
    rows = []
    for row in refs.values():
        now = common.artifact(row['path'])
        assert now['sha256'] == row['sha256']
        now['allocated_bytes'] = storage.allocated(row['path'])
        rows.append(now)
    (STAGE / 'protection_before.json.gz').write_bytes(gzip.compress(
        (json.dumps(dict(paths=len(rows), protected_artifacts=rows), indent=2) + '\n').encode(), mtime=0))
    write_new(STAGE / 'source_before.json', dict(backups=[backup(name) for name in (
        'docs/CLAUDE_HANDOFF.md', 'evidence/save_menu/20261013_original_screen/current_progress.json')], full_project_copy=False))
    write_new(STAGE / 'startup.json', dict(status='PASS_RUNTIME_INTEGRATION_BASELINE', utc=datetime.now(timezone.utc).isoformat(),
        protected_paths=len(rows), previous_host=parent['build_id'], confirmed_disposable_bytes=0,
        prior_cleanup=common.artifact(PROJECT / 'evidence/world_terrain_original/phase10/cleanup_summary.json'),
        threshold_bytes=10 * 1024**3, additional_payload_budget_bytes=64 * 1024**2,
        scope='File-only new-game-only isolated runtime; six asset packages reused, mutable databases private, no engine build/default promotion.',
        native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False))
    path = PROJECT / 'evidence/save_menu/20261013_original_screen/current_progress.json'
    value = json.loads(path.read_text('utf8'))
    value.update(status='WORKING_PHASE11_LATEST_PHASE10_ISOLATED_RUNTIME_INTEGRATION', current_source_working_stage=str(STAGE),
        latest_source_matches_linked_candidate=True, prepared_runtime_matches_latest_source=False, full_engine_goal_complete=False)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps(dict(status='PASS_RUNTIME_INTEGRATION_BASELINE', protected=len(rows))))


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument('action', choices=['begin', 'measure', 'verify'])
    cli.add_argument('label', nargs='?')
    args = cli.parse_args()
    if args.action == 'begin':
        begin()
    elif args.action == 'measure':
        assert args.label in ('before', 'prestage', 'after')
        value = storage.measure_storage()
        value.update(utc=datetime.now(timezone.utc).isoformat(), native_execution=False,
            scope_note='Allocation counted once per real os.stat identity; receipt/index writes follow scan.')
        value.pop('source_replacement_released_after_this_receipt', None)
        write_new(STAGE / ('storage_' + args.label + '.json'), value)
        print(json.dumps({key: value[key] for key in ('status', 'file_paths', 'unique_allocated_bytes')}))
    else:
        assert args.label in ('prestage', 'after')
        previous = json.loads(gzip.decompress((STAGE / 'protection_before.json.gz').read_bytes()))
        bad, aliases = [], 0
        for row in previous['protected_artifacts']:
            now = common.artifact(row['path'])
            if any(now[key] != row[key] for key in ('bytes', 'sha256', 'file_identity', 'mtime_ns', 'file_attributes')):
                bad.append(row['path'])
            aliases += now.get('links') != row.get('links')
        value = dict(status='PASS' if not bad else 'FAIL', paths=previous['paths'], differences=bad,
            alias_changes=aliases, native_execution=False)
        write_new(STAGE / ('protection_' + args.label + '.json'), value)
        assert not bad
        print(json.dumps(dict(status='PASS', protected=previous['paths'], differences=0, alias_changes=aliases)))


if __name__ == '__main__':
    main()
