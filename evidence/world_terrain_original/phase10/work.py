"""Phase-ten file-only baseline, changed-file backups and allocation receipts."""
from datetime import datetime, timezone
import gzip
import importlib.util
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[2]
spec = importlib.util.spec_from_file_location(
    'phase8_baseline_library', PROJECT / 'evidence/world_terrain_original/phase8/work.py')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
base.STAGE, base.PROJECT = STAGE, PROJECT


def begin():
    assert not (STAGE / 'startup.json').exists()
    previous = PROJECT / 'evidence/world_terrain_original/phase9/runtime_integration/current_work.json'
    current = json.loads(previous.read_text('utf8'))
    assert current['latest_source_matches_linked_candidate']
    assert current['prepared_runtime_matches_latest_source']
    assert not current['storage']['after_pending']
    report = Path(current['current_host']['build_result']['path'])
    parent = json.loads(report.read_text('utf8'))
    refs = {base.common.key(row['path']): row for row in base.builder.protected_inventory(parent)}
    refs.update({base.common.key(row['path']): row for row in base.menu.frozen_rows(parent).values()})
    roots = [PROJECT / 'Build/UiWindowHost' / parent['build_id']]
    roots += [PROJECT / 'Build/InteractiveGameRuntime' / name for name in (
        '20261115T134603Z_aa8853762399', '20261115T101941Z_99b3c393ee9a',
        '20261115T011241Z_4c8fd55e99db', '20261108T003146Z_40a8030edf08')]
    roots += [PROJECT / 'evidence/world_terrain_original' / ('phase' + str(i)) for i in range(1, 10)]
    roots += [PROJECT / name for name in (
        'Build/OriginalTerrainAssets/02104c582759bf0cefb58f97379699e45300eb2a9c6da6fdd3c65d1440cb84e8',
        'Build/OriginalFogAssets/42ae12554e1514dd48a9a5df25f47b4280d22d180dff29d169c602334e879bcc',
        'Build/OriginalWaterAssets/2ff227dae9d16398e038e8ea33624940a9581e0eb2d37c3891121fae22c25afc',
        'Build/OriginalWaterLeanAssets/69c6780dbeb5f8605d8231cef944d0ec9392109b6ccc81a9d3b76ae83cfd0ef7',
        'Build/OriginalLightingAssets/d0873d3915da23e45ee1b66187bb7e4174673a1e8cce1fea16b6151ff515e424',
        'evidence/sdk_runtime_play/historical_os_inputs')]
    for root in roots:
        assert root.is_dir(), str(root)
        for directory, names, leaves in os.walk(root, followlinks=False):
            for name in names:
                assert not os.stat(Path(directory) / name, follow_symlinks=False).st_file_attributes & 0x400
            for name in leaves:
                row = base.common.artifact(Path(directory) / name)
                refs[base.common.key(row['path'])] = row
    for path in (report, previous, PROJECT / 'tools/current_runtime_sdk_input.py'):
        row = base.common.artifact(path)
        refs[base.common.key(path)] = row
    for path in (PROJECT / 'evidence/world_terrain_original').iterdir():
        if path.is_file():
            row = base.common.artifact(path)
            refs[base.common.key(path)] = row
    rows = []
    for row in refs.values():
        now = base.common.artifact(row['path'])
        assert now['sha256'] == row['sha256']
        now['allocated_bytes'] = base.storage.allocated(row['path'])
        rows.append(now)
    (STAGE / 'protection_before.json.gz').write_bytes(gzip.compress(
        (json.dumps(dict(paths=len(rows), protected_artifacts=rows), indent=2) + '\n').encode(), mtime=0))
    old = json.loads((PROJECT / 'evidence/world_terrain_original/phase8/source_before.json').read_text('utf8'))
    names = [Path(row['source']['path']).relative_to(PROJECT).as_posix() for row in old['backups']]
    names += ['Source/Presentation/' + name for name in (
        'OriginalTerrainModel.h', 'OriginalTerrainNormalModel.h', 'WorldViewRenderer.h',
        'WorldCameraControls.h', 'WorldUnitAssets.h', 'OriginalScreenLightingModel.h',
        'OriginalScreenLightingBinding.h', 'OriginalScreenLightingShader.h',
        'OriginalDynamicShadowModel.h', 'OriginalDynamicShadowShader.h',
        'OriginalDynamicShadowGpu.inc', 'OriginalDynamicShadowGpuTypes.inc')]
    names += ['Source/Host/InteractiveGameLoop.h']
    names = sorted({name for name in names if (PROJECT / name).is_file()})
    base.write_new(STAGE / 'source_before.json', dict(
        backups=[base.backup(name) for name in names], full_project_copy=False))
    base.write_new(STAGE / 'startup.json', dict(
        status='PASS_BASELINE_AND_CHANGED_FILE_BACKUPS', utc=datetime.now(timezone.utc).isoformat(),
        previous=base.common.artifact(previous), protected_paths=len(rows), previous_host=parent['build_id'],
        requested_items=[2, 3, 4, 7], confirmed_disposable_bytes=0, threshold_bytes=10 * 1024**3,
        requirements=[
            'Terrain cache precision and original rules from pinned evidence',
            'Reflection scene classes and water composition from pinned evidence',
            'Original trees, tessellation and camera offline implementation where evidence permits',
            'Useful deterministic CPU multicore integration with serial equivalence',
            'Exact tile picking and no unknown-material disclosure',
            'No save ABI, original installation, MODS, settings, default launch or registration changes'],
        retention='Keep aa885 latest, 99b3 prior, 4c8f recovery and 40a user sessions; reuse five packs.',
        native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False))
    path = PROJECT / 'evidence/save_menu/20261013_original_screen/current_progress.json'
    value = json.loads(path.read_text('utf8'))
    value.update(status='WORKING_TERRAIN_CACHE_REFLECTION_TREES_CAMERA_MULTICORE_PHASE10',
                 current_source_working_stage=str(STAGE), latest_source_matches_linked_candidate=False,
                 prepared_runtime_matches_latest_source=False, full_engine_goal_complete=False)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps(dict(status='PASS_BASELINE_AND_CHANGED_FILE_BACKUPS', protected=len(rows),
                          source_backups=len(names), native_execution=False)))


base.begin = begin
if __name__ == '__main__':
    base.main()
