"""Phase-eight changed-file backups, protected receipts and allocation accounting."""
from datetime import datetime, timezone
import argparse, gzip, hashlib, json, os, sys
from pathlib import Path
sys.dont_write_bytecode = True
STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[2]
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
    path = PROJECT / name
    row = common.artifact(path)
    target = STAGE / 'source_before' / (name.replace('/', '__') + '.' + row['sha256'][:16] + '.gz')
    target.parent.mkdir(parents=True, exist_ok=True)
    assert not target.exists()
    target.write_bytes(gzip.compress(path.read_bytes(), mtime=0))
    assert hashlib.sha256(gzip.decompress(target.read_bytes())).hexdigest() == row['sha256']
    return dict(source=row, backup=common.artifact(target))


def begin():
    assert not (STAGE / 'startup.json').exists()
    previous = PROJECT / 'evidence/world_terrain_original/phase7/runtime_integration/current_work.json'
    current = json.loads(previous.read_text('utf8'))
    assert current['latest_source_matches_linked_candidate'] and not current['storage']['after_pending']
    report = Path(current['current_host']['build_result']['path'])
    parent = json.loads(report.read_text('utf8'))
    refs = {common.key(row['path']): row for row in builder.protected_inventory(parent)}
    for row in menu.frozen_rows(parent).values():
        refs[common.key(row['path'])] = row
    roots = [PROJECT / 'Build/UiWindowHost' / parent['build_id']]
    roots += [PROJECT / 'Build/InteractiveGameRuntime' / name for name in ('20261115T101941Z_99b3c393ee9a', '20261115T011241Z_4c8fd55e99db', '20261108T003146Z_40a8030edf08')]
    roots += [PROJECT / 'evidence/world_terrain_original' / ('phase' + str(i)) for i in range(1, 8)]
    roots += [PROJECT / name for name in (
        'Build/OriginalTerrainAssets/02104c582759bf0cefb58f97379699e45300eb2a9c6da6fdd3c65d1440cb84e8',
        'Build/OriginalFogAssets/42ae12554e1514dd48a9a5df25f47b4280d22d180dff29d169c602334e879bcc',
        'Build/OriginalWaterAssets/2ff227dae9d16398e038e8ea33624940a9581e0eb2d37c3891121fae22c25afc',
        'Build/OriginalWaterLeanAssets/69c6780dbeb5f8605d8231cef944d0ec9392109b6ccc81a9d3b76ae83cfd0ef7',
        'Build/OriginalLightingAssets/d0873d3915da23e45ee1b66187bb7e4174673a1e8cce1fea16b6151ff515e424',
        'evidence/sdk_runtime_play/historical_os_inputs')]
    for root in roots:
        for directory, names, leaves in os.walk(root, followlinks=False):
            for name in names:
                assert not os.stat(Path(directory) / name, follow_symlinks=False).st_file_attributes & 0x400
            for name in leaves:
                row = common.artifact(Path(directory) / name)
                refs[common.key(row['path'])] = row
    for path in (report, previous, PROJECT / 'tools/current_runtime_sdk_input.py'):
        row = common.artifact(path)
        refs[common.key(path)] = row
    for path in (PROJECT / 'evidence/world_terrain_original').iterdir():
        if path.is_file():
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
    names = ['Source/Presentation/WorldTerrainRenderer.cpp', 'Source/Presentation/WorldTerrainReuse.h', 'Source/Presentation/OriginalTerrainShader.h', 'Source/Presentation/OriginalTerrainGpu.inc', 'Source/Presentation/OriginalTerrainGpuTypes.inc', 'Source/Presentation/OriginalTerrainGeometry.h', 'Source/Presentation/OriginalLightingGpu.inc', 'Source/Presentation/OriginalLightingGpuTypes.inc', 'Source/Presentation/OriginalLightingBinding.h', 'Source/Presentation/OriginalLightingModel.h', 'Source/Presentation/OriginalLightingFieldModel.h', 'Source/Presentation/OriginalLightingFieldBinding.h', 'Source/Presentation/OriginalLightingFieldShader.h', 'Source/Presentation/OriginalLightingFieldGpu.inc', 'Source/Presentation/OriginalLightingFieldBridge.inc', 'Source/Presentation/OriginalLightingFieldGpuTypes.inc', 'Source/Presentation/OriginalWaterSurfaceShader.h', 'Source/Presentation/OriginalWaterSurfaceGpu.inc', 'Source/Presentation/OriginalWaterSurfaceGpuTypes.inc', 'Source/Presentation/OriginalWaterReflection.inc', 'Source/Presentation/OriginalWaterSurfaceTargets.inc', 'Source/Presentation/OriginalFogGpu.inc', 'Source/Presentation/OriginalFogGpuTypes.inc', 'Source/Presentation/OriginalFogShader.h', 'Source/Presentation/WorldTerrainUnits.inc', 'tools/build_menu_suite_host.py', 'tools/attest_prepared_menu_host.py', 'docs/WORLD_TERRAIN_ORIGINAL_PLAN.md', 'docs/CLAUDE_HANDOFF.md', 'evidence/save_menu/20261013_original_screen/current_progress.json']
    write_new(STAGE / 'source_before.json', dict(backups=[backup(name) for name in names], full_project_copy=False))
    cleanup = json.loads((PROJECT / 'evidence/world_terrain_original/phase7/runtime_integration/overlay/cleanup_result.json').read_text('utf8'))
    write_new(STAGE / 'startup.json', dict(
        status='PASS_BASELINE_AND_CHANGED_FILE_BACKUPS', utc=datetime.now(timezone.utc).isoformat(),
        protected_paths=len(rows), previous_host=parent['build_id'], previous_phase='phase7',
        confirmed_disposable_bytes=0, threshold_bytes=10 * 1024**3,
        prior_cleanup=common.artifact(PROJECT / 'evidence/world_terrain_original/phase7/runtime_integration/overlay/cleanup_result.json'),
        prior_cleanup_status=cleanup.get('status'),
        retention='Keep latest23c and prepared99b3, recovery4c8f,40a user saves, prior receipts, current dependencies and original evidence. Reuse all five packs; no native execution.',
        native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False))
    path = PROJECT / 'evidence/save_menu/20261013_original_screen/current_progress.json'
    value = json.loads(path.read_text('utf8'))
    value.update(status='WORKING_NORMAL_CACHE_SCREEN_LIGHT_DYNAMIC_SHADOW_WATER_FOG_PHASE8', current_source_working_stage=str(STAGE),
                 latest_source_matches_linked_candidate=False, prepared_runtime_matches_latest_source=False,
                 full_engine_goal_complete=False)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps(dict(status='PASS_BASELINE_AND_CHANGED_FILE_BACKUPS', protected=len(rows))))


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument('action', choices=['begin', 'measure', 'verify'])
    cli.add_argument('label', nargs='?')
    args = cli.parse_args()
    if args.action == 'begin':
        begin()
    elif args.action == 'measure':
        assert args.label in ('before', 'precompile', 'after')
        value = storage.measure_storage()
        value.update(utc=datetime.now(timezone.utc).isoformat(), native_execution=False,
                     scope_note='Allocation counted once per real file identity; receipt creation follows scan.')
        value.pop('source_replacement_released_after_this_receipt', None)
        write_new(STAGE / ('storage_' + args.label + '.json'), value)
        print(json.dumps({key: value[key] for key in ('status', 'file_paths', 'unique_allocated_bytes')}))
    else:
        assert args.label in ('precompile', 'after')
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
