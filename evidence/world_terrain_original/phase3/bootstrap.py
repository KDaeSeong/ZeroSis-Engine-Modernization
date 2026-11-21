"""Reuse the preceding accounting workflow; back up changed files, never the project."""
from pathlib import Path
import json,sys
sys.dont_write_bytecode=True
stage=Path(__file__).absolute().parent
source=(stage.parent/'phase2/work.py').read_text('utf8')
source=source.replace('Phase-two changed-file','Phase-three changed-file')
source=source.replace("previous=PROJECT/'evidence/world_terrain_original/phase1/current_work.json'","previous=PROJECT/'evidence/world_terrain_original/phase2/current_work.json'")
source=source.replace("PROJECT/'evidence/world_terrain_original/phase1',","PROJECT/'evidence/world_terrain_original/phase1',PROJECT/'evidence/world_terrain_original/phase2',")
source=source.replace("PROJECT/'evidence/sdk_runtime_play/historical_os_inputs']","PROJECT/'Build/OriginalFogAssets/42ae12554e1514dd48a9a5df25f47b4280d22d180dff29d169c602334e879bcc',PROJECT/'evidence/sdk_runtime_play/historical_os_inputs']")
start=source.index('    names=[');end=source.index('    write_new',start)
names=['Source/Presentation/WorldTerrainRenderer.cpp','Source/Presentation/WorldViewRenderer.h',
    'Source/Host/WorldViewState.h','Source/Host/InteractiveGameLoop.h',
    'tools/build_menu_suite_host.py','tools/attest_prepared_menu_host.py',
    'docs/WORLD_TERRAIN_ORIGINAL_PLAN.md','docs/CLAUDE_HANDOFF.md',
    'evidence/save_menu/20261013_original_screen/current_progress.json']
source=source[:start]+'    names='+repr(names)+'\n'+source[end:]
source=source.replace("previous_phase='phase1'","previous_phase='phase2'")
source=source.replace('Phase1 current six objects and failed713-file snapshot already retired; CPU/shader intermediates have exact cleanup receipts.',
    'Phase2 cleanup ledger confirms127 intermediates retired, including failed3377 discovery; current77 six objects retired. Preserve77,8470, live4c8f and40a user saves.')
source=source.replace('WORKING_ORIGINAL_FOG_PHASE2','WORKING_ORIGINAL_WATER_PHASE3')
output=stage/'work.py';assert not output.exists();output.write_text(source,encoding='utf8')
print(json.dumps(dict(status='PASS_REUSED_ACCOUNTING_DRIVER',changed_file_backup_count=len(names),full_project_copy=False)))
