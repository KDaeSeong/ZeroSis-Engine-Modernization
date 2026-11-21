"""Compile just the changed terrain VS/PS and compose ten current-stage proofs."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import sys

sys.dont_write_bytecode = True
STAGE = Path(__file__).resolve().parent
PROJECT = STAGE.parents[3]
spec = importlib.util.spec_from_file_location('retained_phase5_shader_contract', STAGE.parents[1]/'phase5/shader/strict_lighting_shader.py')
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
ref, write_new = h.ref, h.write_new
P = PROJECT/'Source/Presentation'


def source_checks(shader):
    s = h.base.clean(shader)
    pixel = s[s.index('O pixelMain('):]
    guard = pixel.index('if(state.y==0)')
    return dict(
        no_depth_uav_atomic=not re.search(r'SV_Depth|RWTexture|RWBuffer|Interlocked', s),
        exact_tile_state='Texture2D<uint2> PlotState : register(t24);' in s,
        integer_id_output='uint pick:SV_Target1;' in s and 'o.pick=state.x;' in pixel,
        unknown_before_material=guard < pixel.index('Diffuse[i].Sample('),
        unknown_before_selector=guard < pixel.index('LightingSelector.Load('),
        unknown_before_detail_shadow=guard < pixel.index('DetailNormalField.SampleLevel(') < pixel.index('HeightShadowField.SampleLevel('),
        detail_t41='Texture2D<float4> DetailNormalField : register(t41);' in s,
        shadow_t42='Texture2D<float> HeightShadowField : register(t42);' in s,
        candidate66_field_uv='float2 fieldUv=(p.uv*64+1)/66;' in pixel,
        decoded_detail_normal='DetailNormalField.SampleLevel(LightingSampler,fieldUv,0).rgb*2-1' in pixel,
        base_and_detail_separate='TerrainCacheBake(continent,p.normal,detailNormal,shadow,' in pixel,
        basis_original_no_final_normalize='tangent*materialNormal.x+bitangent*materialNormal.y+n*materialNormal.z' in s,
        irradiance_original_order='irradianceBase=sun*1.7,irradianceDelta=shade*1.7-irradianceBase' in s and 'shadow*irradianceDelta+irradianceBase' in s,
        original_diffuse_epsilon='LightingEncode(albedo*irradiance+0.001)' in s,
        original_specular_exponent='float exponent=64*specular.a+1;' in s,
        final_t8_is_baked_specular='pow(max(bakedSpecular,0),2.2)*screenLighting.rgb+pow(max(colour,0),2.2)' in s,
        actual_composition_uses_baked_spec='TerrainComposition(continent,baked,bakedSpecular.rgb)' in pixel,
        original_enable_gates='compositionInfo.x>0.5?baked:0' in s and 'if(compositionInfo.y>0.5)' in s,
        exact_inverse_gamma='0.4545454680919647216796875' in s,
        reflection_height_unknown_clip='if(clipInfo.y>0.5 && p.height<clipInfo.x)discard;' in pixel and 'if(state.y==0){if(clipInfo.y>0.5)discard;return o;}' in pixel,
        auxiliary_specular_kept='o.specularSquared=bakedSpecular;' in pixel,
        vertex_position_unchanged='p.p=mul(float4(v.p+float3(placement.x,0,placement.y),1),viewProjection);' in s,
        terrain_vertex44='sizeof(OriginalVertex)==44' in (P/'OriginalTerrainGpuTypes.inc').read_text('utf8'),
        terrain_cb192='sizeof(OriginalConstants)==192' in (P/'OriginalTerrainGpuTypes.inc').read_text('utf8'),
        lighting_cb80='sizeof(OriginalLightingConstants)==80' in (P/'OriginalLightingGpuTypes.inc').read_text('utf8'))


def reflection(listing, profile, data):
    value = h.reflection(listing, 'terrain', profile, data)
    if profile == 'ps_5_0':
        added = h.binding_rows(listing, [('DetailNormalField', 't41', 1), ('HeightShadowField', 't42', 1)])
        value['resources'] += added
        value['checks']['field_t41_t42_exact_slots'] = all(r['matches'] for r in added)
        lines = [v.strip() for v in listing.splitlines() if v.strip() and not v.startswith('//')]
        value['checks']['normal_shadow_declared_float'] = all(any(v.startswith('dcl_resource_texture2d (float,float,float,float) t'+str(n)) for v in lines) for n in (41, 42))
    return value


def current_inputs():
    names = ['OriginalTerrainShader.h', 'OriginalTerrainGpuTypes.inc', 'OriginalLightingGpuTypes.inc',
             'OriginalLightingFieldShader.h', 'OriginalLightingFieldGpuTypes.inc', 'OriginalLightingFieldGpu.inc',
             'OriginalLightingFieldModel.h', 'OriginalLightingFieldBridge.inc', 'OriginalLightingFieldBinding.h', 'OriginalLightingModel.h',
             'OriginalWaterSurfaceShader.h', 'OriginalWaterSurfaceGpuTypes.inc']
    return [ref(P/n) for n in names] + [ref(Path(__file__)), ref(STAGE.parents[1]/'phase5/shader/strict_lighting_shader.py')]


def reusable():
    old_path = STAGE.parents[1]/'phase5/shader/current.json'
    old = json.loads(old_path.read_text('utf8'))
    for name in ['OriginalWaterSurfaceShader.h', 'OriginalWaterSurfaceGpuTypes.inc']:
        row = next(r for r in old['fixed_inputs'] if Path(r['path']).name == name)
        assert ref(row['path']) == row
    assert h.base.digest(h.base.literal(h.RENDERER)) == old['literal_sha256']['legacy']
    field_dir = STAGE.parent/'review/field_shader/attempt02'
    field_path = field_dir/'result.json'
    field = json.loads(field_path.read_text('utf8'))
    assert field['status'] == 'PASS_STRICT_PRIVATE_MATERIAL_HEIGHT_SOBEL_SHADER_ABI'
    for row in field['inputs']:
        assert ref(row['path']) == row
    literals = re.findall(r'R"HLSL\((.*?)\)HLSL"', (P/'OriginalLightingFieldShader.h').read_text('utf8'), re.S)
    assert len(literals) == 2
    assert {k: h.base.digest(v) for k, v in zip(['height', 'normal'], literals)} == field['literal_sha256']
    rows = [dict(v, proof=ref(old_path)) for v in old['passes'] if v['stem'] in ('surface', 'legacy')]
    rows += [dict(v, proof=ref(field_path)) for v in field['passes']]
    assert len(rows) == 8 and all(v['exit_code'] == 0 and all(v['reflection']['checks'].values()) for v in rows)
    patch_path = Path(old['surface_patch']['path'])
    assert ref(patch_path) == old['surface_patch']
    compiler = json.loads(patch_path.read_text('utf8'))['compiler']
    assert ref(compiler['path']) == compiler
    return rows, compiler, [ref(old_path), ref(field_path)]


def seal():
    path = STAGE/'current.json'
    current = json.loads(path.read_text('utf8'))
    assert current['status'] == 'PASS_TEN_CURRENT_PHASE6_SHADER_STAGES'
    assert current_inputs() == current['fixed_inputs']
    review_path = STAGE.parent/'review/integration_review.json'
    review = json.loads(review_path.read_text('utf8'))
    assert not review['blocking_findings'] and review['source_files_unchanged_during_review']
    rows = list(review['source_files_after'].values())
    assert all(ref(r['path'])['sha256'] == r['sha256'] for r in rows)
    assert h.base.digest(h.base.literal(h.RENDERER)) == current['legacy_literal_sha256']
    write_new(STAGE/'source_seal.json', dict(status='PASS_PHASE6_FINAL_SHADER_SOURCE_SEAL', current_result=ref(path),
        independent_integration_review=ref(review_path), fixed_inputs=current['fixed_inputs'], source_files=rows,
        renderer=ref(h.RENDERER), host_gamecore_clr_hwnd_gpu_audio_or_game_executed=False))
    print(json.dumps(dict(status='PASS_PHASE6_FINAL_SHADER_SOURCE_SEAL', source_seal=ref(STAGE/'source_seal.json'))))


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument('--seal', action='store_true')
    args = cli.parse_args()
    if args.seal:
        seal()
        return
    reused, compiler, references = reusable()
    fixed = current_inputs()
    shader = h.base.literal(P/'OriginalTerrainShader.h')
    checks = source_checks(shader)
    assert all(checks.values()), [k for k, v in checks.items() if not v]
    stage = STAGE/'attempt01'
    assert not stage.exists(), 'Inspect the owned terrain attempt before retrying'
    stage.mkdir()
    write_new(stage/'started.json', dict(fixed_inputs=fixed, compiler=compiler, source_checks=checks, reused_references=references))
    owned, passes = [], []
    unchanged = False
    try:
        source = stage/'terrain.hlsl'
        source.write_bytes(shader.encode('ascii'))
        owned.append(source)
        for entry, profile in [('vertexMain', 'vs_5_0'), ('pixelMain', 'ps_5_0')]:
            key = 'terrain_'+profile
            binary, listing = stage/(key+'.cso'), stage/(key+'.asm')
            owned += [binary, listing]
            command = [compiler['path'], '/nologo', '/Ges', '/WX', '/T', profile, '/E', entry,
                       '/Fo', str(binary), '/Fc', str(listing), str(source)]
            done = subprocess.run(command, cwd=stage, capture_output=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
            raw_log = done.stdout+done.stderr
            log = raw_log.decode('mbcs', errors='replace')
            log_path = stage/(key+'_compiler.txt')
            log_path.write_text(log[:4000], encoding='utf8')
            row = dict(stem='terrain', entry=entry, profile=profile, command=command, exit_code=done.returncode,
                log=ref(log_path), complete_log_sha256=hashlib.sha256(raw_log).hexdigest(), compiler_warning='warning' in log.lower())
            if binary.exists():
                row['bytecode'] = ref(binary)
            if binary.exists() and listing.exists():
                row['listing'] = ref(listing)
                row['reflection'] = reflection(listing.read_text('utf8'), profile, binary.read_bytes())
            passes.append(row)
    finally:
        unchanged = current_inputs() == fixed and ref(compiler['path']) == compiler
        files = [ref(p) for p in owned if p.exists()]
        for row in files:
            q = Path(row['path'])
            assert q.resolve().parent == stage.resolve() and row['links'] == 1 and not row['file_attributes'] & 0x401
            assert ref(q) == row
        write_new(stage/'cleanup_plan.json', dict(files=files, exact_leaf_only=True, protected_inputs=fixed))
        for row in files:
            q = Path(row['path'])
            assert ref(q) == row
            q.unlink()
        write_new(stage/'cleanup_result.json', dict(status='PASS_EXACT_TWO_TERRAIN_SHADER_INTERMEDIATES_REMOVED',
            files=files, deleted_files=len(files), released_unique_allocated_bytes=sum(r['allocated_bytes'] for r in files),
            all_absent=all(not Path(r['path']).exists() for r in files)))
    passed = unchanged and len(passes) == 2 and all(v['exit_code'] == 0 and not v['compiler_warning']
        and v.get('reflection') and all(v['reflection']['checks'].values()) for v in passes)
    result = dict(status='PASS_TWO_STRICT_DETAIL_SHADOW_SPEC_TERRAIN_STAGES' if passed else 'FAIL_TERRAIN_PHASE6_SHADER',
        source_checks=checks, fixed_inputs=fixed, passes=passes, compiler=compiler,
        cleanup=ref(stage/'cleanup_result.json'), host_gamecore_clr_hwnd_gpu_audio_or_game_executed=False)
    write_new(stage/'result.json', result)
    assert passed, 'See the exact terrain attempt result; no source seal was written'
    current = dict(status='PASS_TEN_CURRENT_PHASE6_SHADER_STAGES', fixed_inputs=fixed, source_checks=checks,
        passes=[dict(v, proof=ref(stage/'result.json')) for v in passes]+reused, reused_references=references,
        compiler=compiler, actual_new_compile_count_this_phase=8, reused_from_previous_phase=4,
        unnecessary_recompilations=0, current_stage_count=10,
        legacy_literal_sha256=h.base.digest(h.base.literal(h.RENDERER)), final_source_seal='PENDING_INDEPENDENT_REVIEW',
        host_gamecore_clr_hwnd_gpu_audio_or_game_executed=False)
    write_new(STAGE/'current.json', current)
    print(json.dumps(dict(status=current['status'], new_terrain_compiles=2, stage_count=10,
        source_checks=len(checks), current_sha256=ref(STAGE/'current.json')['sha256'])))


if __name__ == '__main__':
    main()
