"""Cross-check every factual claim in docs/WORLD_TERRAIN_ORIGINAL_PLAN.md against the stage records and sources.

Read-only; no game, Host or tool other than Python is run.
usage: python -B -X utf8 plan_check.py
"""
from __future__ import annotations
import csv
import hashlib
import io
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[1]
checks = {}


def check(name, value):
    checks[name] = bool(value)


def ref(path: Path):
    raw = path.read_bytes()
    return dict(path=str(path.relative_to(PROJECT)).replace('\\', '/'), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


inventory = json.loads((STAGE / 'asset_inventory.json').read_text('utf8'))
details = json.loads((STAGE / 'asset_details.json').read_text('utf8'))
probe = json.loads((STAGE / 'retail_renderer_probe.json').read_text('utf8'))
pipeline = json.loads((STAGE / 'retail_terrain_pipeline_probe.json').read_text('utf8'))
semantics = json.loads((STAGE / 'terrain_shader_semantics.json').read_text('utf8'))
pieces = json.loads((STAGE / 'pieces_library_format.json').read_text('utf8'))
disasm = json.loads((STAGE / 'shader_disasm_index.json').read_text('utf8'))
blend_cpu = json.loads((STAGE / 'retail_terrain_blend_cpu_probe.json').read_text('utf8'))
id_rows = json.loads((STAGE / 'pieces_id_rows.json').read_text('utf8'))
placement = json.loads((STAGE / 'retail_piece_placement_probe.json').read_text('utf8'))
cells = json.loads((STAGE / 'piece_cells.json').read_text('utf8'))
map_cells = json.loads((STAGE / 'retail_map_cells_probe.json').read_text('utf8'))
remaining = json.loads((STAGE / 'retail_terrain_remaining_probe.json').read_text('utf8'))
renderer = (PROJECT / 'Source/Presentation/WorldTerrainRenderer.cpp').read_text('utf8')
plan = (PROJECT / 'docs/WORLD_TERRAIN_ORIGINAL_PLAN.md').read_text('utf8')


def rows(text):
    return {(r['Continent ID'], r[' ID (unique for continent)'], r['Diffuse']): r
            for r in csv.DictReader(io.StringIO(text))}


dlc = rows(inventory['definitions']['Assets/DLC/Shared/Terrain/TerrainDef.csv']['text'])
fpk = rows(details['text']['terraindef.csv']['text'])
check('terraindef_columns', list(next(iter(dlc.values())).keys())[4:7] ==
      ['BaseDominance', 'Texture Scale', 'Projection(0=horizontal 1=vertical)'])
check('mesa_scale_differs', dlc[('0', '40', 'Generic_Mesa_D.dds')]['Texture Scale'] == '0.05' and
      fpk[('0', '40', 'Generic_Mesa_D.dds')]['Texture Scale'] == '0.03')
amer = ('1', '10', 'Amer_Mountain_Base_D.dds')
check('amer_mountain_projection_differs', dlc[amer]['Projection(0=horizontal 1=vertical)'] == '0' and
      fpk[amer]['Projection(0=horizontal 1=vertical)'] == '1')
dominant = sorted(r['Diffuse'] for r in dlc.values() if r['BaseDominance'] == '1')
check('dominance_rows', dominant == ['Afri_Mountain_Base_D.dds', 'Amer_Crater_D.dds', 'Amer_Mountain_Base_D.dds',
                                     'Amer_Mountain_Top_D.dds', 'Asia_Mountain_Base_D.dds', 'Euro_Mountain_Base_D.dds',
                                     'Generic_Gibraltar_D.dds'] and
      fpk[('1', '35', 'Amer_Mountain_Top_D.dds')]['BaseDominance'] == '0')
scales = {r['Diffuse']: r['Texture Scale'] for r in dlc.values()}
check('scale_examples', scales['Euro_Grassland_D.dds'] == '0.014' and scales['Euro_Coast_D.dds'] == '0.17' and
      scales['Euro_Shallow_Seas_D.dds'] == '0.004')
dds = details['dds']
check('grass_sizes', (dds['euro_grassland_d.dds']['width'], dds['euro_grassland_d.dds']['format']) == (1024, 'BC3') and
      (dds['euro_grassland_h.dds']['width'], dds['euro_grassland_h.dds']['format']) == (2048, 'BC3') and
      dds['euro_mountain_base_h.dds']['width'] == 512)
check('hexgridid', (dds['hexgridid.dds']['width'], dds['hexgridid.dds']['height'], dds['hexgridid.dds']['mips']) == (320, 320, 0))
check('tf_blend', (dds['tf_blend.dds']['width'], dds['tf_blend.dds']['height']) == (128, 128))
check('cloud_tiles', [(dds[f'fogcloudtile_dif_0{i}.dds']['width'], dds[f'fogcloudtile_dif_0{i}.dds']['format']) for i in (1, 2, 3)]
      == [(1024, 'BC3'), (1024, 'BC1'), (1024, 'BC3')] and (dds['fx_fog_dif.dds']['width'], dds['fx_fog_dif.dds']['format']) == (512, 'BC3'))
check('fog_ramp', (dds['fogramp.dds']['width'], dds['fogramp.dds']['height']) == (128, 8))
check('fog_color', details['text']['fogcolor.csv']['text'].strip() == '146,182,243')
check('forests_xml', 'num_tiles="4" random_trees_per_tile="360"' in details['text']['forests.xml']['text'] and
      'overlay_alpha=".60"' in details['text']['forests.xml']['text'])
check('hexgrid_xml', '<HexGrid color = "255,255,255,75" width=".2"/>' in details['text']['hexgrid.xml']['text'])
check('pieces_library', inventory['pieces_library']['bytes'] == 27595584 and inventory['pieces_library']['head_hex'].startswith('14000000' + '00e00500'))
shaders = {row['name']: row for row in probe['shader_registry']['shaders']}
check('shader_count', len(shaders) == 0x5e)
check('terrain_ids', [shaders[n]['id'] for n in ('TerrainShader', 'NormalCalculate', 'CacheBake', 'TerrainShaderScreen',
                                                    'CompositeShader', 'TerrainDecalShader')] == list(range(0x49, 0x4f)))
check('fow_ids', [shaders[n]['id'] for n in ('FOWCell', 'FOWParticleShader', 'FOWDrawMask', 'FOWBaseLayer')] == list(range(0x32, 0x36)))
check('dxbc', probe['embedded_dxbc']['blobs'] == 1417 and probe['embedded_dxbc']['stages'] == {'PS': 1034, 'VS': 380, 'HS': 2, 'DS': 1})
check('fluid_fow_descriptors', probe['fluid_fow_setup']['pooled_descriptor_allocations_0x8c69b0'] == 4)
check('renderer_fog_constants', 'o.color=float4(0.002,0.003,0.004,1)' in renderer and 'p.visible?1.0f:0.30f' in renderer)
check('renderer_water_uv_light', 'p.water*0.72' in renderer and '*0.8f' in renderer and '0.48f+0.52f*' in renderer)
check('renderer_material_per_tile', 'unsigned MaterialId(const WorldViewPlot& p)' in renderer and 'D3D11_BLEND_DESC blend{}' in renderer)
check('fxc_available', Path(r'C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\fxc.exe').is_file())
check('plan_mentions_descriptors_not_render_targets', '렌더 타깃 4개' not in plan and '설명자' in plan)
effects = {e['name']: e['passes'] for e in pipeline['effect_records']['effects'].values()}


def blob(effect, index, slot):
    return effects[effect][index][slot]['sm5']['file_offset']


check('pipeline_exe', pipeline['exe']['sha256'] == probe['exe']['sha256'] and pipeline['executed'] is False)
check('pipeline_terrain_tessellation', [blob('TerrainShader', 0, s) for s in ('vs', 'ps', 'hs', 'ds')] ==
      ['00ef1e90', '00f02858', '00f152f0', '00f15a80'] and len(effects['TerrainShader']) == 8 and
      all('hs' not in p for p in effects['TerrainShader'][3:]))
check('pipeline_blend_is_screen_effect', blob('TerrainShaderScreen', 1, 'ps') == '00f0d840' and
      [blob('CacheBake', i, 'ps') for i in (0, 1)] == ['00f07878', '00f08a18'] and blob('NormalCalculate', 0, 'ps') == '00f06530')
check('pipeline_fxsb_reader', 'four times' in pipeline['pieces_library_loader']['layout'] and
      'cmp dword ptr [esp + 0x24], 0x14' in pipeline['pieces_library_loader']['version_check'])
meaning = {(r['effect'], r['pass_index'], r['slot']): r for r in semantics['shaders']}
check('semantics_pass', semantics['status'] == 'PASS' and len(semantics['shaders']) == 26 and
      semantics['tool']['mode'] == '/dumpbin' and semantics['game_or_host_executed'] is False and
      semantics['pipeline_probe'] == hashlib.sha256((STAGE / 'retail_terrain_pipeline_probe.json').read_bytes()).hexdigest())
check('semantics_blend_alpha8', 'albedo_alpha^8 * w_i' in meaning[('TerrainShaderScreen', 1, 'ps')]['meaning'] and
      meaning[('TerrainShaderScreen', 1, 'ps')]['status'] == 'PASS')
check('semantics_projection_scale', '0.33' in meaning[('TerrainShaderScreen', 0, 'vs')]['meaning'] and
      '0.66' in meaning[('TerrainShaderScreen', 0, 'vs')]['meaning'])
check('semantics_shadow_march', '40-step' in meaning[('TerrainShaderScreen', 3, 'ps')]['meaning'] and
      '0.314485' in meaning[('TerrainShaderScreen', 3, 'ps')]['meaning'])
check('semantics_fow_channels', [meaning[('FOWDrawMask', i, 'ps')]['meaning'] for i in range(3)] ==
      ['Writes the mask value to G.', 'Writes the mask value to R and B.', 'Writes the mask value to R.'])
check('pieces_format', pieces['file']['sha256'] == '86faac1e80634b0031a9df98889682fbc17ddc72341fc68fbf5b33e7ce4c1c7a' and
      pieces['version'] == 20 and pieces['pieces'] == 299 and pieces['image_sizes'] == {'128': 148, '512': 151} and
      [s['element_bytes'] for s in pieces['sections'].values()] == [4, 1, 2, 0x56c])
by_csv = {p['csv']: p for p in pieces['piece_rows']}
check('pieces_id_not_terraindef', by_csv['Amer_Grass_1_1.csv']['id_values'] == [0, 11] and
      fpk[('1', '2', 'Amer_Grassland_D.dds')]['Diffuse'] == 'Amer_Grassland_D.dds')
check('disasm_index_counts', disasm['blobs'] == 1417 and not disasm['failures'] and
      all(r['instructions'] > 0 for r in disasm['rows']) and
      sum(1 for r in disasm['rows'] if r['model'] == 'ps_5_0') == 362)
check('plan_states_results', '확산 알파의 8제곱' in plan and '0.314485' in plan and '쌍삼차' in plan and
      'R×(1−B)' in plan and '299' in plan)
check('cpu_probe_exe', blend_cpu['exe']['sha256'] == probe['exe']['sha256'] and blend_cpu['executed'] is False)
check('cpu_terraindef_format', blend_cpu['terraindef_loader']['format'] == '%i %s %s %s %f %f %i %x' and
      'BaseDominance is scanned but never stored' in blend_cpu['terraindef_loader']['consequence'])
check('cpu_kernel', blend_cpu['blend_kernel']['normalised_5x5'][2][2] == 0.157207 and
      blend_cpu['blend_kernel']['one_dimensional'][0] == 0.125 and
      'centre 0.157207' in meaning[('TerrainShaderScreen', 1, 'vs')]['meaning'])
check('cpu_vertex_layout', blend_cpu['blend_mesh_vertex']['stride_bytes'] == 48 and
      blend_cpu['blend_mesh_vertex']['projection'].startswith('normal.z > 0.9 -> 0'))
check('cpu_pass_choice', blend_cpu['pass_choice']['option'] == 'GraphicsDetailSettings.TerrainUseAdvancedGPU')
check('cpu_other_textures', 'LayoutSystem' in blend_cpu['other_textures']['tf_blend'] and
      'Not named' in blend_cpu['other_textures']['hexgridid'])
check('piece_ids_are_rows', id_rows['status'] == 'PASS' and id_rows['typed_checks']['checked'] == id_rows['typed_checks']['matched'] >= 300 and
      id_rows['row0'] == {'dlc': 'Asia_Tundra_D.dds', 'fpk': 'NULL'} and
      id_rows['inputs']['pieces_library_format.json'] == hashlib.sha256((STAGE / 'pieces_library_format.json').read_bytes()).hexdigest())
check('plan_states_cpu_results', '이 EXE의 지형 혼합에는 쓰이지 않는다' in plan and '0.636056' in plan and '**행 번호**' in plan and
      'TerrainUseAdvancedGPU' in plan and 'LayoutSystem' in plan and '상위 8재질' in plan)
check('plan_no_stale_cpu_guesses', 'TerrainDef ID와 같은 체계가 아니다' not in plan and
      '정확한 역할은 아직 미확정이다' not in plan and 'BaseDominance의 쓰임.' not in plan)
check('placement_probe_exe', placement['exe']['sha256'] == probe['exe']['sha256'] and placement['executed'] is False)
check('placement_orientations', [o['translation'] for o in placement['orientations']] ==
      [[0, 0, 0], [1, -3, 2], [-4, 0, 4], [-2, -3, 5]] and [o['table_index'] for o in placement['orientations']] == [0, 2, 6, 9])
check('placement_texels', placement['texel_geometry']['examples']['(64,64)'] == [1.0, 1.0, -2.0] and
      placement['texel_defaults']['id'] == 3 and dlc[('0', '5', 'Euro_Coast_D.dds')] and
      list(dlc)[3] == ('0', '5', 'Euro_Coast_D.dds') and list(fpk)[3] == ('0', '5', 'Euro_Coast_D.dds'))
check('placement_rules', any('rand()' in line for line in placement['matcher_pass']['rule']) and
      placement['level_loop']['rule'].startswith('for level = highest'))
check('piece_cells', cells['file']['sha256'] == pieces['file']['sha256'] and len(cells['piece_rows']) == 299 and
      cells['terrain_bits']['0'] == ['grass'] and cells['terrain_bits']['10'] == ['mountain'] and
      cells['terrain_bits']['14'] == ['ocean'] and sorted(cells['levels']) == ['1', '2', '3', '4'] and
      max(len(r['owned']) for r in cells['piece_rows']) == 3)
check('piece_levels', cells['levels']['3']['owned_cells'].get('3', 0) > 100 and cells['levels']['1']['owned_cells'].get('1', 0) > 60)
check('plan_states_placement', '### 2.7' in plan and 'first-fit' in plan and '(1,−3,2)' in plan and
      '육각 하나가 가로 64텍셀' in plan and '`rand()`' in plan)
check('plan_no_stale_placement', '아직 해독하지 못했다' not in plan and '패턴 위치 계산으로 보임' not in plan)
check('map_cells_exe', map_cells['exe']['sha256'] == probe['exe']['sha256'] and map_cells['executed'] is False)
check('map_cells_seed', map_cells['sdk_names']['slots']['ICvPreGame1 0x118'] == 'mapRandomSeed' and
      map_cells['sdk_names']['slots']['ICvGameContext1 0x1c'] == 'GetPreGame' and 'srand(' in map_cells['seed']['rule'])
wonder_bits = {'FEATURE_GEYSER': 'geyser', 'FEATURE_CRATER': 'crater', 'FEATURE_GIBRALTAR': 'gibraltar', 'FEATURE_MESA': 'mesa',
               'FEATURE_REEF': 'reef', 'FEATURE_VOLCANO': 'volcano', 'FEATURE_POTOSI': 'cerro_de_potosi', 'FEATURE_ULURU': 'uluru',
               'FEATURE_MT_SINAI': 'sinai', 'FEATURE_MT_KAILASH': 'kailash', 'FEATURE_SRI_PADA': 'sri_pada',
               'FEATURE_KILIMANJARO': 'kilimanjaro', 'FEATURE_LAKE_VICTORIA': 'lake_victoria', 'FEATURE_FUJI': 'fuji'}
check('map_cells_bits_match_piece_names', all(
    cells['terrain_bits'][str(int(map_cells['plot_to_cell']['natural_wonders'][feature], 16).bit_length() - 1)] == [name]
    for feature, name in wonder_bits.items()))
check('map_cells_terrain_rule', 'flat: terrain 0 -> 0x1, 2 -> 0x4, 3 -> 0x8, 4 -> 0x10, other -> 0x2' in
      map_cells['plot_to_cell']['terrain_rule'] and cells['terrain_bits']['2'] == ['desert'] and cells['terrain_bits']['1'] == ['plains'])
check('plan_states_seed', '### 2.8' in plan and 'mapRandomSeed' in plan and 'SOLOMONS_MINES' in plan)
check('plan_no_stale_seed', '초기화하는지는 찾지 못했다' not in plan and '아직 찾지 못했다' not in plan)
check('remaining_exe', remaining['exe']['sha256'] == probe['exe']['sha256'] and remaining['executed'] is False)
check('remaining_lookup', remaining['file_lookup']['package']['guid'] == '{8871E748-29A4-4910-8C57-8C99E32D0167}' and
      'file name without directories' in remaining['file_lookup']['key'] and
      'returns immediately' in remaining['file_lookup']['rule'])
check('remaining_dlc_values', dlc[('0', '40', 'Generic_Mesa_D.dds')]['Texture Scale'] == '0.05' and
      dlc[amer]['Projection(0=horizontal 1=vertical)'] == '0' and id_rows['row0']['dlc'] == 'Asia_Tundra_D.dds')
check('remaining_spec_flag', 'TerrainDetailLevel is 2 or 3' in remaining['spec_cache_flag']['rule'] and
      'TerrainTessLevel != 0' in remaining['spec_cache_flag']['rule'])
check('remaining_second_loop', 'final after the first loop' in remaining['second_plot_loop']['consequence'])
check('plan_states_remaining', '### 2.9' in plan and 'Upgrade1.Civ5Pkg' in plan and '`TerrainTessLevel`이 0이 아니다' in plan)
check('plan_no_stale_remaining', '우선순위)는 미확정이다' not in plan and '강·지물 처리로 보임' not in plan and
      '켜지는 TerrainDetailLevel 값' not in plan)
check('plan_no_stale_guesses', 'CacheBake라는 이름으로 볼 때' not in plan and 'HS/DS 셰이더가 지형 테셀레이션인지 여부' not in plan)
value = dict(schema='zerosis.world_terrain_original.plan_check.v1', plan=ref(PROJECT / 'docs/WORLD_TERRAIN_ORIGINAL_PLAN.md'),
             inputs=[ref(STAGE / name) for name in ('asset_inventory.json', 'asset_details.json', 'retail_renderer_probe.json',
                                                    'retail_terrain_pipeline_probe.json', 'terrain_shader_semantics.json',
                                                    'pieces_library_format.json', 'shader_disasm_index.json',
                                                    'retail_terrain_blend_cpu_probe.json', 'pieces_id_rows.json',
                                                    'retail_piece_placement_probe.json', 'piece_cells.json',
                                                    'retail_map_cells_probe.json', 'retail_terrain_remaining_probe.json')] +
                    [ref(PROJECT / 'Source/Presentation/WorldTerrainRenderer.cpp')],
             checks=checks, status='PASS' if all(checks.values()) else 'FAIL', native_execution=False)
out = STAGE / 'plan_check.json'
if out.exists():
    out.unlink()
with out.open('x', encoding='utf8', newline='\n') as stream:
    json.dump(value, stream, indent=2, ensure_ascii=False)
    stream.write('\n')
print(json.dumps(dict(status=value['status'], failed=[k for k, v in checks.items() if not v], checks=len(checks))))
