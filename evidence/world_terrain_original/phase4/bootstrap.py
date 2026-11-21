"""Reuse accounting and preservation logic for the original water-surface follow-up."""
from pathlib import Path
import json,sys
sys.dont_write_bytecode=True
stage=Path(__file__).absolute().parent
source=(stage.parent/'phase3/work.py').read_text('utf8').replace('Phase-three changed-file','Phase-four changed-file')
source=source.replace("previous=PROJECT/'evidence/world_terrain_original/phase2/current_work.json'","previous=PROJECT/'evidence/world_terrain_original/phase3/current_work.json'")
source=source.replace("PROJECT/'evidence/world_terrain_original/phase2',","PROJECT/'evidence/world_terrain_original/phase2',PROJECT/'evidence/world_terrain_original/phase3',")
source=source.replace("PROJECT/'evidence/sdk_runtime_play/historical_os_inputs']","PROJECT/'Build/OriginalWaterAssets/2ff227dae9d16398e038e8ea33624940a9581e0eb2d37c3891121fae22c25afc',PROJECT/'evidence/sdk_runtime_play/historical_os_inputs']")
names=['Source/Presentation/WorldTerrainRenderer.cpp','Source/Presentation/WorldViewRenderer.h','Source/Presentation/WorldTerrainReuse.h',
    'Source/Presentation/OriginalTerrainShader.h','Source/Presentation/OriginalTerrainGpu.inc','Source/Presentation/OriginalTerrainGpuTypes.inc',
    'Source/Presentation/OriginalWaterGpu.inc','Source/Host/InteractiveGameLoop.h','tools/build_menu_suite_host.py',
    'tools/attest_prepared_menu_host.py','docs/WORLD_TERRAIN_ORIGINAL_PLAN.md','docs/CLAUDE_HANDOFF.md',
    'evidence/save_menu/20261013_original_screen/current_progress.json']
start=source.index('    names=[');end=source.index('    write_new',start)
source=source[:start]+'    names='+repr(names)+'\n'+source[end:]
source=source.replace("previous_phase='phase2'","previous_phase='phase3'")
source=source.replace('Phase2 cleanup ledger confirms127 intermediates retired, including failed3377 discovery; current77 six objects retired. Preserve77,8470, live4c8f and40a user saves.',
    'Phase3 exact cleanup ledger confirms122 intermediates retired; currenta0 six objects retired. Preservea0,77,live4c8f,40a user saves and all unique original CPU/shader evidence.')
source=source.replace('WORKING_ORIGINAL_WATER_PHASE3','WORKING_ORIGINAL_WATER_SURFACE_PHASE4')
path=stage/'work.py';assert not path.exists();path.write_text(source,encoding='utf8')
print(json.dumps(dict(status='PASS_REUSED_ACCOUNTING_DRIVER',changed_file_backup_count=len(names),full_project_copy=False)))
