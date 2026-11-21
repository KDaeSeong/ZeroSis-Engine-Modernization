"""Phase-twelve bounded source work, preservation and file-identity accounting."""
from pathlib import Path
from datetime import datetime,timezone
import gzip,importlib.util,json,os,sys
sys.dont_write_bytecode=True
STAGE=Path(__file__).absolute().parent
PROJECT=STAGE.parents[2]
spec=importlib.util.spec_from_file_location('phase11_preservation',PROJECT/'evidence/world_terrain_original/phase11/runtime_integration/work.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
base.STAGE,base.PROJECT=STAGE,PROJECT

def begin():
    assert not (STAGE/'startup.json').exists()
    previous=PROJECT/'evidence/world_terrain_original/phase11/runtime_integration/current_work.json'
    value=json.loads(previous.read_text('utf8'))
    assert value['latest_source_matches_linked_candidate'] and value['prepared_runtime_matches_latest_source']
    assert not value['storage']['after_pending'] and not value['protection']['after_pending']
    report=Path(value['current_host']['build_result']['path']);parent=json.loads(report.read_text('utf8'))
    refs={base.common.key(row['path']):row for row in base.builder.protected_inventory(parent)}
    refs.update({base.common.key(row['path']):row for row in base.menu.frozen_rows(parent).values()})
    roots=[PROJECT/'Build/UiWindowHost'/name for name in ('20261116T114748Z_014dd63ad3bc','20261115T121456Z_dbb01a1f4f50','20261115T093013Z_23c5037b12b9')]
    roots += [PROJECT/'Build/InteractiveGameRuntime'/name for name in ('20261116T123457Z_90b98a574efc',
        '20261115T134603Z_aa8853762399','20261115T101941Z_99b3c393ee9a','20261115T011241Z_4c8fd55e99db','20261108T003146Z_40a8030edf08')]
    roots += [PROJECT/'evidence/world_terrain_original'/('phase'+str(i)) for i in range(1,12)]
    roots += [Path(row['source']['path']).parent for row in value['packages'].values()]
    roots += [PROJECT/'evidence/sdk_runtime_play/historical_os_inputs']
    for root in roots:
        assert root.is_dir(),root
        for directory,names,leaves in os.walk(root,followlinks=False):
            for name in names:assert not os.stat(Path(directory)/name,follow_symlinks=False).st_file_attributes&0x400
            for name in leaves:
                row=base.common.artifact(Path(directory)/name);refs[base.common.key(row['path'])]=row
    fixed=['docs/CLAUDE_WORK_ASSIGNMENT.md','tools/prepare_latest_engine_pair.py','tools/prepare_current_sdk_play.py',
        'tools/run_interactive_game.py','tools/runtime_input_cache.py','tools/current_runtime_sdk_input.py']
    fixed += ['Source/Presentation/'+name for name in ('OriginalCameraModel.h','OriginalForestModel.h','OriginalForestShader.h',
        'OriginalTerrainTessellationModel.h','OriginalTerrainTessellationShader.h')]
    fixed += ['Tests/original_forest_tessellation.cpp','Tests/original_forest_tessellation.py']
    for path in [report,previous,*(PROJECT/name for name in fixed)]:
        row=base.common.artifact(path);refs[base.common.key(row['path'])]=row
    rows=[]
    for row in refs.values():
        now=base.common.artifact(row['path']);assert now['sha256']==row['sha256']
        now['allocated_bytes']=base.storage.allocated(row['path']);rows.append(now)
    (STAGE/'protection_before.json.gz').write_bytes(gzip.compress((json.dumps(dict(paths=len(rows),protected_artifacts=rows),indent=2)+'\n').encode(),mtime=0))
    names=['Source/Presentation/'+name for name in (
        'WorldTerrainRenderer.cpp','WorldTerrainReuse.h','WorldViewRenderer.h','OriginalTerrainModel.h','OriginalTerrainGeometry.h',
        'OriginalTerrainBinding.h','OriginalTerrainNormalModel.h','OriginalTerrainCacheModel.h','OriginalTerrainGpu.inc','OriginalTerrainGpuTypes.inc',
        'OriginalTerrainShader.h','OriginalLightingFieldModel.h','OriginalLightingFieldBinding.h','OriginalLightingFieldShader.h',
        'OriginalLightingFieldGpu.inc','OriginalLightingFieldGpuTypes.inc','OriginalLightingFieldBridge.inc','OriginalLightingGpu.inc',
        'OriginalLightingGpuTypes.inc','OriginalWaterReflection.inc','OriginalWaterSurfaceBinding.h','OriginalWaterSurfaceModel.h',
        'OriginalWaterSurfaceShader.h','OriginalWaterSurfaceGpu.inc','OriginalWaterSurfaceGpuTypes.inc','OriginalWaterSurfaceTargets.inc',
        'OriginalReflectionContract.h','OriginalDynamicShadowModel.h','OriginalDynamicShadowShader.h','OriginalDynamicShadowGpu.inc',
        'OriginalFogGpu.inc','OriginalFogGpuTypes.inc','OriginalFogShader.h')]
    names += ['Source/Host/InteractiveGameLoop.h','tools/build_menu_suite_host.py','tools/attest_prepared_menu_host.py',
        'docs/CLAUDE_HANDOFF.md','docs/WORLD_TERRAIN_ORIGINAL_PLAN.md','evidence/save_menu/20261013_original_screen/current_progress.json']
    base.write_new(STAGE/'source_before.json',dict(backups=[base.backup(name) for name in names],full_project_copy=False))
    base.write_new(STAGE/'startup.json',dict(status='PASS_PHASE12_SOURCE_BASELINE_AND_BACKUPS',utc=datetime.now(timezone.utc).isoformat(),
        requested_scope=[2,3],protected_paths=len(rows),previous=base.common.artifact(previous),
        claude_scope='4: bicubic basis, world camera and forest; existing five models/tests protected, claude_geometry outputs excluded from our writes.',
        requirements=['Verified cache sampling/mips and height calibration where evidence permits','Original reflection projection and missing scene providers',
            'Exact R32_UINT tile identity; deny unknown inputs before any sample','No original/MODS/settings/saves/default/global/save ABI changes'],
        prior_cleanup=base.common.artifact(PROJECT/'evidence/world_terrain_original/phase11/runtime_integration/overlay/cleanup_result.json'),
        confirmed_disposable_bytes=0,threshold_bytes=10*1024**3,
        existing_six_packs_reused=True,native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False))
    path=PROJECT/'evidence/save_menu/20261013_original_screen/current_progress.json';index=json.loads(path.read_text('utf8'))
    index.update(status='WORKING_PHASE12_CACHE_HEIGHT_WATER_REFLECTION',current_source_working_stage=str(STAGE),
        latest_source_matches_linked_candidate=False,prepared_runtime_matches_latest_source=False,
        prepared_runtime_matches_current_linked_candidate=False,full_engine_goal_complete=False)
    path.write_text(json.dumps(index,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(status='PASS_PHASE12_SOURCE_BASELINE_AND_BACKUPS',protected=len(rows),source_backups=len(names),native_execution=False)))

base.begin=begin
if __name__=='__main__':base.main()
