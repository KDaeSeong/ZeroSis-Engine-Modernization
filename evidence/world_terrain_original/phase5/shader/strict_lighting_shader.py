"""Reuse the strict six-compiler harness with phase-five ABI/lighting contracts.

Only explicitly invoking this script compiles shaders. --seal is a separate
file-only final source check and requires the independent integration report.
The reused phase-four code and evidence are never edited.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import sys

sys.dont_write_bytecode = True
STAGE = Path(__file__).resolve().parent
PROJECT = STAGE.parents[3]
sys.path.insert(0, str(PROJECT/'Tests'))
import original_water_surface_shader as base
from original_water_shader import ref, write_new
from original_fog_shader import terrain_reflected_contract

PRESENTATION = PROJECT/'Source/Presentation'
RENDERER = PRESENTATION/'WorldTerrainRenderer.cpp'
LIGHT_TYPES = PRESENTATION/'OriginalLightingGpuTypes.inc'
EXTRA = [LIGHT_TYPES, PROJECT/'Tests/original_water_surface_shader.py',
         PROJECT/'Tests/original_water_shader.py', PROJECT/'Tests/original_fog_shader.py']
REAL_WRITE_NEW = base.write_new
EXTRA_FIXED = []


def source_contracts(shaders):
    s, t, l = (base.clean(shaders[name]) for name in ('surface', 'terrain', 'legacy'))
    sp = s[s.index('O pixelMain('):]
    tp = t[t.index('O pixelMain('):]
    refract = s[s.index('float3 Refraction('):s.index('struct O{')]
    return dict(
        integer_id_no_depth_uav=not re.search(r'SV_Depth|RWTexture|RWBuffer|Interlocked', s+t+l),
        exact_surface_state='Texture2D<uint2> PlotState:register(t9);' in s,
        exact_surface_water_mask='Texture2D<uint> WaterMask:register(t10);' in s,
        surface_unknown_before_sample=sp.index('if(state.y==0)discard;') < sp.index('CoastWave.Sample('),
        surface_exact_id_after_water_guard=sp.index('WaterMask.Load(') < sp.index('o.pick=state.x;'),
        positive_refraction_id_first='if(pick==0)return fallback;' in refract,
        refraction_reads_id_then_depth_then_colour=refract.index('SceneId.Load(') < refract.index('if(id!=pick)return fallback;') < refract.index('SceneDepth.Load(') < refract.index('source.y>=reflectionInfo.z') < refract.index('SceneColour.Load('),
        finite_underwater_refraction='!all(isfinite(source.xyz))||source.y>=reflectionInfo.z' in refract,
        exact_moments_decode='mean=a.rg*2-1;second=float3(a.b,a.a,cross*2-1);' in s,
        original_moment_mirror='if(mirrorX){mean.x=-mean.x;second.z=-second.z;}' in s,
        mixture_scale_once=s.count('/opticsInfo.x') == 1,
        gaussian_reject_retains_finite_q='if(q>=16)return 0;' in s and 'if(!isfinite(q)){q=0;return 0;}' in s,
        original_depth_sample_raw='Refraction(p,state.x,mean,deep.rgb)' in sp and not re.search(r'pow\s*\(\s*(?:max\s*\(\s*)?deep\.rgb', sp),
        raw_fresnel_no_composite_clamp='float f=RetailFresnel(mean,view)' in sp and 'saturate(RetailFresnel' not in sp,
        narrow_primary_and_secondary_plus_only_primary_wide=sp.count('=Gaussian(') == 3 and 'float lobeWide0=Gaussian(covariance,h0,opticsInfo.y,true' in sp and 'lobeWide1' not in sp,
        primary_lambert_fresnel='diffuse*(deep.rgb+f*(lobe0*lightColour0.rgb+lobe1*lightColour1.rgb))' in sp,
        wide_primary_depth_colour='lobeWide0*deep.rgb*lightColour0.rgb' in sp,
        reflection_not_fresnel_scaled='reflected*opticsInfo.w' in sp and 'reflected*f*' not in sp,
        original_q_secondary_cubic_order='float qSquared=q1*q1,qCubed=qSquared*q1;' in sp and 'depthFactor*qCubed*deep.rgb' in sp,
        original_shadow_intermediates='float shadowAmount=saturate(shadowInfo.x)*shadowInfo.y;' in sp and 'float3 shadowed=shadowAmount*lit;lit=shadowed*(-0.67)+lit;' in sp,
        alpha_before_encoded_policy='float opacity=saturate(deep.a*(1+coverage));' in sp and 'lerp(Encoded(base),Encoded(lit),opacity)' in sp,
        exact_inverse_gamma='0.4545454680919647216796875' in s and '0.4545454680919647216796875' in t,
        reflection_four_taps=s.count('ReflectionCache.Sample(') == 4,
        terrain_clip_and_unknown='if(clipInfo.y>0.5 && p.height<clipInfo.x)discard;' in tp and 'if(state.y==0){if(clipInfo.y>0.5)discard;return o;}' in tp,
        terrain_unknown_before_material=tp.index('if(state.y==0)') < tp.index('Diffuse[i].Sample('),
        terrain_unknown_before_selector=tp.index('if(state.y==0)') < tp.index('LightingSelector.Load('),
        selector_uint='Texture2D<uint> LightingSelector : register(t25);' in t,
        terrain_original_mrt='uint pick:SV_Target1;' in t and 'specularSquared:SV_Target2' in t and 'materialHeight:SV_Target3' in t,
        original_cube_irradiance_order='float3 irradianceBase=sun*1.7,irradianceDelta=shade*1.7-irradianceBase;' in t and 'float3 irradiance=shadow*irradianceDelta+irradianceBase;' in t,
        original_cache_diffuse='LightingEncode(albedo*irradiance+0.001)' in t,
        original_cache_specular='float exponent=64*specular.a+1;' in t and 'pow(saturate(dot(specularAxis.xyz,N)),exponent)*exponent*saturate(1-shadow)*specular' in t,
        specular_output_remains_separate='o.specularSquared=bakedSpecular;' in tp,
        neutral_normal_explicit='float3 materialNormal=float3(0,0,1);' in t,
        original_tangent_basis='float3(-n.z,0,n.x)' in t and 'float3(0,n.z,-n.y)' in t,
        terrain_screen_light_gamma='pow(max(albedo,0),2.2)*screenLighting.rgb+pow(max(colour,0),2.2)' in t,
        terrain_premultiplied_overlay='overlayColour.rgb+(1-overlayColour.a)*colour' in t,
        legacy_reflection_clip='if(clipInfo.y>0.5 && (p.height<clipInfo.x||p.fog<0))discard;' in l,
        surface_cpu320='sizeof(WaterSurfaceConstants)==320' in base.TYPES.read_text('utf8'),
        terrain_vertex44='sizeof(OriginalVertex)==44' in base.TERRAIN_TYPES.read_text('utf8'),
        terrain_cb192='sizeof(OriginalConstants)==192' in base.TERRAIN_TYPES.read_text('utf8'),
        lighting_cb80='sizeof(OriginalLightingConstants)==80' in LIGHT_TYPES.read_text('utf8'),
    )


def binding_rows(listing, expected):
    rows = []
    for name, slot, count in expected:
        found = [line for line in listing.splitlines()
                 if re.match(r'//\s*'+re.escape(name)+r'\s+', line)
                 and re.search(r'\b'+slot+r'\s+'+str(count)+r'\s*$', line)]
        rows.append(dict(name=name, slot=slot, count=count, matches=len(found) == 1))
    return rows


def reflection(listing, stem, profile, data):
    fields, resources = [], []
    if profile == 'vs_5_0':
        fields = [('viewProjection', 0, 64)]
        resources = [('Camera', 'cb0', 1)]
    if stem == 'surface':
        names = ('placement', 'mapInfo', 'eye', 'viewport', 'reflectionInfo', 'opticsInfo', 'uvScales', 'motion',
                 'light0', 'light1', 'absorption', 'warp0', 'warp1', 'lightColour0', 'lightColour1', 'shadowInfo')
        fields += [('inverseViewProjection', 0, 64)] + [(n, 64+16*i, 16) for i, n in enumerate(names)]
        resources += [('Surface', 'cb1', 1)]
        if profile == 'ps_5_0':
            resources += [(n, 't'+str(i), 1) for i, n in enumerate(('LeanMean', 'LeanCross', 'ReflectionCache', 'SceneColour',
                'SceneDepth', 'SceneId', 'DepthColour', 'Sky', 'CoastWave', 'PlotState', 'WaterMask'))]
            resources += [('WrapSampler', 's0', 1), ('ClampSampler', 's1', 1)]
    elif stem == 'terrain':
        fields += [('materials', 0, 128), ('placement', 128, 16), ('mapInfo', 144, 16),
                   ('textureOrigin', 160, 16), ('fogInfo', 176, 16)]
        resources += [('Chunk', 'cb1', 1)]
        if profile == 'ps_5_0':
            fields += [('clipInfo', 0, 16)] + [(n, 16*i, 16) for i, n in enumerate(
                ('lightingInfo', 'specularAxis', 'compositionInfo', 'screenLighting', 'overlayColour'))]
            resources += [('ReflectionClip', 'cb2', 1), ('OriginalLighting', 'cb3', 1), ('LightingSelector', 't25', 1), ('LightingSampler', 's1', 1)]
            resources += [(f'{name}[{i}]', 't'+str(first+i), 1)
                          for name, first in [('Sunlight', 26), ('Shadowlight', 31), ('TerrainLut', 36)] for i in range(5)]
    elif profile == 'ps_5_0':
        fields = [('clipInfo', 0, 16)]
        resources = [('ReflectionClip', 'cb2', 1), ('Diffuse', 't0', 1), ('GroundSampler', 's0', 1)]
    constants = base.offsets(listing, fields)
    bindings = binding_rows(listing, resources)
    lines = [line.strip() for line in listing.splitlines() if line.strip() and not line.startswith('//')]
    checks = dict(shader_model=profile in lines, constant_offsets_sizes=all(r['matches'] for r in constants),
                  resource_slots_counts=all(r['matches'] for r in bindings),
                  no_uav_or_depth=not any('dcl_uav' in line or 'oDepth' in line for line in lines))
    detail = {}
    if profile == 'ps_5_0':
        checks['colour_target0'] = bool(re.search(r'^// SV_Target\s+0\s+xyzw\s+0\s+TARGET\s+float\s+xyzw\s*$', listing, re.M))
        checks['integer_target1'] = bool(re.search(r'^// SV_Target\s+1\s+x\s+1\s+TARGET\s+uint\s+x\s*$', listing, re.M))
        checks['output_count'] = sum(l.startswith('dcl_output') for l in lines) == (4 if stem == 'terrain' else 2)
        if stem == 'terrain':
            detail['retained_terrain_abi'] = terrain_reflected_contract(listing)
            checks['retained_terrain_abi'] = all(detail['retained_terrain_abi']['checks'].values())
            checks['typed_exact_selector'] = any(l.startswith('dcl_resource_texture2d (uint,uint,uint,uint) t25') for l in lines)
            checks['ten_cube_declarations'] = sum(l.startswith('dcl_resource_texturecube ') for l in lines) == 10
            checks['five_lut_declarations'] = sum(l.startswith('dcl_resource_texture3d ') for l in lines) == 5
        if stem == 'surface':
            checks['typed_exact_inputs'] = all(any(l.startswith('dcl_resource_texture2d (uint,uint,uint,uint) t'+str(slot)) for l in lines) for slot in (5, 9, 10))
            loads = {str(slot): [dict(instruction=i, text=l) for i, l in enumerate(lines)
                if l.startswith('ld_indexable(') and re.search(r'\bt'+str(slot)+r'(?:\.|\s|$)', l)] for slot in (3, 4, 5)}
            checks['compiled_refraction_load_order'] = all(loads.values()) and loads['5'][0]['instruction'] < loads['4'][0]['instruction'] < loads['3'][0]['instruction']
            detail['restricted_loads'] = loads
        if stem in ('surface', 'terrain'):
            checks['exact_inverse_gamma_bytecode'] = base.gamma_count(data) > 0
            detail['exact_inverse_gamma_count'] = base.gamma_count(data)
    elif stem == 'terrain':
        checks['normal_float3_input'] = bool(re.search(r'^// TEXCOORD\s+5\s+xyz\s+\d+\s+NONE\s+float\s+xyz\s*$', listing, re.M))
    return dict(checks=checks, constants=constants, resources=bindings, detail=detail, instruction_count=len(lines))


def write_phase5(path, value):
    if path.name == 'result.json' and path.parent.parent == STAGE:
        value['schema'] = 'zerosis.original_lighting.phase5.strict_surface_terrain_legacy.v1'
        value['status'] = 'PASS_STRICT_PHASE5_LIGHTING_SHADER_ABI' if value['status'].startswith('PASS_') else 'FAIL_PHASE5_LIGHTING_SHADER'
        value['extra_fixed_inputs'] = EXTRA_FIXED
        value['reused_harness'] = 'Original phase4 test implementation reused read-only with phase5 source/reflection contracts.'
        value['original_operations'] = ['Selected original Water PS2 complete pre-shadow composite, raw D/F, secondary q cubic term, shadow and alpha',
            'CacheBake tangent basis/cube mixture/gamma/LUT/specular, final terrain colour arithmetic']
        value['candidates'] = ['Runtime lights/shadow/normal-cache producer/cube bindings and cache sampling',
            'Opaque scene water composition and private reflection/refraction', 'Global phase2 FOW route still used; original water .4 replacement is not wired per fragment',
            'Original OM blend states and baked-specular consumer remain untraced']
    REAL_WRITE_NEW(path, value)


def seal(stage, review_path):
    path = stage/'result.json'
    result = json.loads(path.read_text('utf8'))
    assert result['status'] == 'PASS_STRICT_PHASE5_LIGHTING_SHADER_ABI'
    assert all(ref(row['path']) == row for row in result['fixed_inputs'] + result['extra_fixed_inputs'])
    review_path = Path(review_path).resolve()
    review = json.loads(review_path.read_text('utf8'))
    assert not review.get('blocking_findings')
    assert review['source_files_unchanged_during_review']
    source_rows = list(review['source_files_after'].values())
    assert all(ref(row['path'])['sha256'] == row['sha256'] for row in source_rows)
    assert any(row['path'] == str(RENDERER) for row in source_rows)
    assert base.digest(base.literal(RENDERER)) == result['literal_sha256']['legacy']
    proof = dict(status='PASS_PHASE5_FINAL_SHADER_SOURCE_SEAL', compiled_result=ref(path), renderer=ref(RENDERER),
        integration_review=ref(review_path), source_files=source_rows, fixed_inputs=result['fixed_inputs']+result['extra_fixed_inputs'],
        literal_sha256=result['literal_sha256'], host_gamecore_clr_hwnd_gpu_audio_or_game_executed=False)
    REAL_WRITE_NEW(stage/'source_seal.json', proof)
    print(json.dumps(dict(status=proof['status'], source_seal=ref(stage/'source_seal.json'))))


def main():
    global EXTRA_FIXED
    EXTRA_FIXED = [ref(p) for p in EXTRA]
    base.ROOT = STAGE
    base.__file__ = str(Path(__file__).resolve())
    base.source_contracts = source_contracts
    base.reflection = reflection
    base.write_new = write_phase5
    base.seal = seal
    try:
        base.main()
    finally:
        assert all(ref(row['path']) == row for row in EXTRA_FIXED), 'Read-only reused harness or lighting layout changed'


if __name__ == '__main__':
    main()
