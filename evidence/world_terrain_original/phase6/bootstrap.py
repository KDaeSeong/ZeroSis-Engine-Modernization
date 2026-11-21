"""Reuse the prior exact accounting helper with only this milestone retargeted."""
from pathlib import Path
import ast, json, sys
sys.dont_write_bytecode = True
STAGE = Path(__file__).absolute().parent
source = (STAGE.parent / 'phase5/work.py').read_text('utf8')
replacements = {
    'Phase-five changed-file': 'Phase-six changed-file',
    "previous = PROJECT / 'evidence/world_terrain_original/phase4/current_work.json'": "previous = PROJECT / 'evidence/world_terrain_original/phase5/current_work.json'",
    'range(1, 5)': 'range(1, 6)',
    "        'evidence/sdk_runtime_play/historical_os_inputs')": "        'Build/OriginalLightingAssets/d0873d3915da23e45ee1b66187bb7e4174673a1e8cce1fea16b6151ff515e424',\n        'evidence/sdk_runtime_play/historical_os_inputs')",
    "evidence/world_terrain_original/phase4/cleanup_summary.json": "evidence/world_terrain_original/phase5/cleanup_summary.json",
    "previous_phase='phase4'": "previous_phase='phase5'",
    'Keep phase4/phase3 recovery': 'Keep phase5/phase4 recovery',
    'Reuse four original asset packages.': 'Reuse all five original asset packages.',
    'WORKING_ORIGINAL_LIGHTING_COMPOSITION_PHASE5': 'WORKING_ORIGINAL_NORMAL_SHADOW_SPECULAR_PHASE6',
}
for old, new in replacements.items():
    assert old in source, old
    source = source.replace(old, new)
start = source.index('    names = [\n')
end = source.index('    write_new(STAGE', start)
names = ['Source/Presentation/' + name for name in (
    'WorldTerrainRenderer.cpp', 'WorldViewRenderer.h', 'WorldTerrainReuse.h',
    'OriginalTerrainShader.h', 'OriginalTerrainGpu.inc', 'OriginalTerrainGpuTypes.inc',
    'OriginalLightingGpu.inc', 'OriginalLightingGpuTypes.inc', 'OriginalLightingBinding.h',
    'OriginalWaterSurfaceShader.h', 'OriginalWaterSurfaceGpu.inc', 'OriginalWaterSurfaceGpuTypes.inc',
    'OriginalWaterReflection.inc', 'OriginalWaterSurfaceTargets.inc')]
names += ['Source/Host/InteractiveGameLoop.h', 'tools/build_menu_suite_host.py',
          'tools/attest_prepared_menu_host.py', 'docs/WORLD_TERRAIN_ORIGINAL_PLAN.md',
          'docs/CLAUDE_HANDOFF.md', 'evidence/save_menu/20261013_original_screen/current_progress.json']
source = source[:start] + '    names = ' + repr(names) + '\n' + source[end:]
ast.parse(source)
target = STAGE / 'work.py'
assert not target.exists()
target.write_text(source, encoding='utf8')
print(json.dumps(dict(status='PASS_REUSED_PHASE6_ACCOUNTING_DRIVER', backups=len(names), whole_project_copies=0)))
