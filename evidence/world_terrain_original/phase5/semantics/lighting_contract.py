"""Check selected original instructions and record lighting contracts without graphics use."""
from pathlib import Path
import hashlib
import json
import math
import struct

STAGE = Path(__file__).resolve().parent
PROJECT = STAGE.parents[3]
EVIDENCE = PROJECT/'evidence/world_terrain_original'
OUT = STAGE/'lighting_contract.json'
FILES = {
    'water': EVIDENCE/'phase3/semantics/bytecode/WaterShader_2_ps.asm',
    'cache_vs': STAGE/'bytecode/CacheBake_0_vs.asm',
    'cache0': STAGE/'bytecode/CacheBake_0_ps.asm',
    'cache1': STAGE/'bytecode/CacheBake_1_ps.asm',
    'normal': STAGE/'bytecode/NormalCalculate_0_ps.asm',
    'terrain': STAGE/'bytecode/TerrainShader_0_ps.asm',
    'self_shadow': STAGE/'shadow/TerrainShaderScreen_3_ps.asm',
    'pipeline': EVIDENCE/'retail_terrain_pipeline_probe.json',
    'registry': EVIDENCE/'retail_renderer_probe.json',
    'phase0_semantics': EVIDENCE/'terrain_shader_semantics.json',
    'phase4_current': EVIDENCE/'phase4/current_work.json',
}


def ref(path):
    st = path.stat()
    data = path.read_bytes()
    return dict(path=str(path), bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                file_identity=[st.st_dev, st.st_ino], mtime_ns=st.st_mtime_ns,
                file_attributes=getattr(st, 'st_file_attributes', 0), links=st.st_nlink)


before = {k: ref(p) for k, p in FILES.items()}
text = {k: p.read_text('utf-8-sig') for k, p in FILES.items()}
checks = []


def seq(name, key, instructions):
    lines = text[key].splitlines()
    cursor = 0
    hits = []
    for needle in instructions:
        hit = next((i for i in range(cursor, len(lines)) if lines[i].strip() == needle), None)
        assert hit is not None, (name, needle)
        hits.append(hit + 1)
        cursor = hit + 1
    checks.append(dict(name=name, source=key, pass_=True, lines=hits, instructions=instructions))


seq('water-unknown-before-textures', 'water', [
    'sample_indexable(texture2d)(float,float,float,float) r0.xy, v5.xyxx, t10.xzyw, s10',
    'eq r0.z, r0.x, l(0.000000)', 'discard_nz r0.z'])
seq('water-depth-palette-sample', 'water', [
    'sample_indexable(texture2d)(float,float,float,float) r1.x, v5.zwzz, t7.wxyz, s7',
    'mul_sat r1.x, r1.x, l(4.000000)', 'add r2.x, -r1.x, l(1.000000)',
    'sample_l_indexable(texture2d)(float,float,float,float) r2.xyzw, r2.xyxx, t6.xyzw, s6, l(0.000000)'])
seq('water-raw-n-lambert', 'water', ['mov r7.z, l(1.000000)', 'dp3_sat r0.z, cb1[14].xyzx, r7.xyzx'])
seq('water-secondary-q-and-reject', 'water', ['mul r1.w, r1.w, l(0.500000)',
    'div r1.w, r1.w, r0.w', 'ge r3.x, l(0.000000), r0.w', 'ge r3.y, r1.w, l(16.000000)'])
seq('water-raw-fresnel-fifth-power', 'water', ['dp3 r0.w, r7.xyzx, r4.xyzx',
    'add r0.w, -r0.w, l(1.000000)', 'mul r1.y, r0.w, r0.w',
    'mul r1.y, r1.y, r1.y', 'mul r0.w, r0.w, r1.y'])
seq('water-exact-pre-shadow-composite', 'water', ['mul r4.xyz, r4.wwww, cb1[16].xyzx',
    'movc r4.xyz, r5.wwww, l(0,0,0,0), r4.xyzx',
    'mul r3.yzw, r3.yyyy, cb1[17].xxyz', 'movc r3.xyz, r3.xxxx, l(0,0,0,0), r3.yzwy',
    'add r3.xyz, r3.xyzx, r4.xyzx', 'mad r3.xyz, r3.xyzx, r0.wwww, r2.xyzx',
    'mul r4.xyz, r2.xyzx, cb1[16].xyzx', 'mul r4.xyz, r5.xxxx, r4.xyzx',
    'mad r3.xyz, r3.xyzx, r0.zzzz, r4.xyzx', 'mad r3.xyz, r6.xyzx, cb1[36].xxxx, r3.xyzx',
    'mul r0.z, r1.w, r1.w', 'mul r0.z, r1.w, r0.z', 'mul r0.z, r1.x, r0.z',
    'mad r1.xyz, r0.zzzz, r2.xyzx, r3.xyzx'])
seq('water-dynamic-shadow-r-alpha-gamma', 'water', [
    'sample_indexable(texture2d)(float,float,float,float) r0.z, r0.zwzz, t13.yzxw, s13',
    'mov_sat r0.z, r0.z', 'mul r0.z, r0.z, cb1[34].x', 'mul r2.xyz, r0.zzzz, r1.xyzx',
    'mad r1.xyz, r2.xyzx, l(-0.670000, -0.670000, -0.670000, 0.000000), r1.xyzx',
    'mad_sat o0.w, r6.w, r2.w, r2.w', 'log r1.xyz, r1.xyzx',
    'mul r1.xyz, r1.xyzx, l(0.454545, 0.454545, 0.454545, 0.000000)', 'exp r1.xyz, r1.xyzx'])
seq('water-overlay-fow-lut', 'water', [
    'sample_indexable(texture2d)(float,float,float,float) r2.xyzw, v5.xyxx, t9.xyzw, s9',
    'add r0.z, -r2.w, l(1.000000)', 'mad r1.xyz, r1.xyzx, r0.zzzz, r2.xyzx',
    'add r1.xyz, r1.xyzx, l(-0.400000, -0.400000, -0.400000, 0.000000)',
    'mad r1.xyz, r0.xxxx, r1.xyzx, l(0.400000, 0.400000, 0.400000, 0.000000)',
    'sample_indexable(texture3d)(float,float,float,float) r2.xyz, r1.xyzx, t11.xyzw, s11',
    'mad r0.x, r0.y, -r0.x, r0.x', 'add r0.yzw, -r1.xxyz, r2.xxyz',
    'mad r0.xyz, r0.xxxx, r0.yzwy, r1.xyzx'])
seq('cache-base-normal-direct-vs', 'cache_vs', ['mov o1.xyz, v1.xyzx'])
seq('cache-nonstandard-tangent-basis', 'cache0', [
    'mul r0.xyz, v1.yzxy, l(0.000000, 1.000000, 0.000000, 0.000000)',
    'mad r1.xyz, v1.yzxy, l(0.000000, 0.000000, 1.000000, 0.000000), -r0.yzxy',
    'mad r0.xyz, -v1.zxyz, l(0.000000, 0.000000, 1.000000, 0.000000), r0.xyzx',
    'dp2 r0.w, r1.xzxx, r1.xzxx', 'rsq r0.w, r0.w', 'mul r1.xyz, r0.wwww, r1.xyzx',
    'dp2 r0.w, r0.yzyy, r0.yzyy', 'rsq r0.w, r0.w', 'mul r0.xyz, r0.wwww, r0.xyzx'])
seq('cache-encoded-normal-reconstruct-no-final-normalize', 'cache0', [
    'sample_indexable(texture2d)(float,float,float,float) r2.xyz, v2.xyxx, t0.xyzw, s0',
    'mad r2.xyz, r2.xyzx, l(2.000000, 2.000000, 2.000000, 0.000000), l(-1.000000, -1.000000, -1.000000, 0.000000)',
    'mul r0.xyz, r0.xyzx, r2.yyyy', 'mad r0.xyz, r2.xxxx, r1.xyzx, r0.xyzx',
    'mad r0.xyz, r2.zzzz, v1.xyzx, r0.xyzx',
    'sample_indexable(texturecube)(float,float,float,float) r1.xyz, r0.xyzx, t5.xyzw, s5'])
seq('cache-cube-irradiance-mix-no-shadow-clamp', 'cache0', [
    'sample_indexable(texturecube)(float,float,float,float) r0.xyz, r0.xyzx, t4.xyzw, s4',
    'mul r0.xyz, r0.xyzx, l(1.700000, 1.700000, 1.700000, 0.000000)',
    'mad r1.xyz, r1.xyzx, l(1.700000, 1.700000, 1.700000, 0.000000), -r0.xyzx',
    'sample_indexable(texture2d)(float,float,float,float) r0.w, v2.xyxx, t2.yzwx, s2',
    'mad r0.xyz, r0.wwww, r1.xyzx, r0.xyzx'])
seq('cache-diffuse-gamma-lut-alpha', 'cache0', [
    'sample_indexable(texture2d)(float,float,float,float) r1.xyz, v2.xyxx, t1.xyzw, s1',
    'mad r0.xyz, r1.xyzx, r0.xyzx, l(0.001000, 0.001000, 0.001000, 0.000000)',
    'log r0.xyz, r0.xyzx', 'mul r0.xyz, r0.xyzx, l(0.454545, 0.454545, 0.454545, 0.000000)',
    'exp r0.xyz, r0.xyzx', 'sample_indexable(texture3d)(float,float,float,float) r0.xyz, r0.xyzx, t8.xyzw, s8',
    'mov o0.xyz, r0.xyzx', 'mov o0.w, l(1.000000)'])
seq('cache-specular-power-shadow-rgba-separate', 'cache1', [
    'dp3_sat r0.x, cb1[21].xyzx, r0.xyzx', 'log r0.x, r0.x',
    'add_sat r1.x, -r1.w, l(1.000000)',
    'sample_indexable(texture2d)(float,float,float,float) r2.xyzw, v2.xyxx, t3.xyzw, s3',
    'mad r0.y, r2.w, l(64.000000), l(1.000000)', 'mul r0.x, r0.x, r0.y', 'exp r0.x, r0.x',
    'mul r0.x, r0.y, r0.x', 'mul r0.x, r1.x, r0.x', 'mul r0.xyzw, r2.xyzw, r0.xxxx',
    'log r0.xyz, r0.xyzx', 'mov o1.w, r0.w',
    'mul r0.xyz, r0.xyzx, l(0.454545, 0.454545, 0.454545, 0.000000)', 'exp r0.xyz, r0.xyzx',
    'sample_indexable(texture3d)(float,float,float,float) r0.xyz, r0.xyzx, t8.xyzw, s8', 'mov o1.xyz, r0.xyzx'])
seq('normal-sobel8-and-normalization', 'normal', [
    'dp3 r0.z, r0.xyzx, l(1.000000, -1.000000, 2.000000, 0.000000)',
    'dp3 r1.x, r1.yzxy, l(1.000000, -1.000000, -2.000000, 0.000000)',
    'mul r1.x, l(0.500000), cb1[1].x',
    'dp3 r0.x, r0.xywx, l(1.000000, 1.000000, 2.000000, 0.000000)',
    'dp3 r0.y, r1.yzwy, l(-1.000000, -1.000000, -2.000000, 0.000000)',
    'mul r0.xy, r2.xyxx, l(2.000000, -2.000000, 0.000000, 0.000000)',
    'add r0.xyz, -r0.xyzx, l(0.000000, 0.000000, 4.000000, 0.000000)',
    'rsq r1.z, r0.z',
    'mad o0.xyz, r1.xyzx, l(0.500000, 0.500000, 2.000000, 0.000000), l(0.500000, 0.500000, 0.500000, 0.000000)'])
seq('terrain-mask-r-saturate-then-runtime-strength', 'terrain', [
    'sample_indexable(texture2d)(float,float,float,float) r0.x, r0.xyxx, t3.xyzw, s3',
    'mov_sat r0.x, r0.x', 'mul r0.x, r0.x, cb1[25].x'])
seq('terrain-linear-screen-light-plus-cache', 'terrain', [
    'sample_indexable(texture2d)(float,float,float,float) r0.yzw, v2.xyxx, t8.wxyz, s8',
    'log r0.yzw, r0.yyzw', 'mul r0.yzw, r0.yyzw, l(0.000000, 2.200000, 2.200000, 2.200000)',
    'exp r0.yzw, r0.yyzw',
    'sample_indexable(texture2d)(float,float,float,float) r1.xyz, r1.xyxx, t9.xyzw, s9',
    'sample_indexable(texture2d)(float,float,float,float) r2.xyz, v2.xyxx, t0.xyzw, s0',
    'movc r2.xyz, cb1[28].xxxx, r2.xyzx, l(0,0,0,0)',
    'log r3.xyz, r2.xyzx', 'mul r3.xyz, r3.xyzx, l(2.200000, 2.200000, 2.200000, 0.000000)',
    'exp r3.xyz, r3.xyzx', 'mad r0.yzw, r0.yyzw, r1.xxyz, r3.xxyz',
    'log r0.yzw, r0.yyzw', 'mul r0.yzw, r0.yyzw, l(0.000000, 0.454545, 0.454545, 0.454545)',
    'exp r0.yzw, r0.yyzw', 'movc r0.yzw, cb1[27].xxxx, r0.yyzw, r2.xxyz'])
seq('terrain-world-lut-premul-overlay-fow-base', 'terrain', [
    'sample_indexable(texture3d)(float,float,float,float) r1.xyz, r0.yzwy, t7.xyzw, s7',
    'add r1.xyz, -r0.yzwy, r1.xyzx', 'mad r0.xyz, r0.xxxx, r1.xyzx, r0.yzwy',
    'sample_indexable(texture2d)(float,float,float,float) r1.xyzw, v3.xyxx, t1.xyzw, s1',
    'add r0.w, -r1.w, l(1.000000)', 'mad r0.xyz, r0.xyzx, r0.wwww, r1.xyzx',
    'sample_indexable(texture2d)(float,float,float,float) r1.xyz, v2.zwzz, t5.xyzw, s5',
    'sample_indexable(texture2d)(float,float,float,float) r2.xy, v3.xyxx, t4.xzyw, s4',
    'mad r0.xyz, r2.xxxx, r0.xyzx, r1.xyzx', 'mad r0.w, r2.y, -r2.x, r2.x',
    'sample_indexable(texture3d)(float,float,float,float) r1.xyz, r0.xyzx, t6.xyzw, s6'])
seq('terrain-distance-and-height-fog-alpha1', 'terrain', [
    'add r2.xyz, v4.xyzx, -cb1[19].xyzx', 'mul r0.w, r2.z, cb2[1].x',
    'mul r1.w, r1.w, cb2[1].y', 'div r0.w, r0.w, r2.z',
    'min r0.w, r0.w, l(1.000000)', 'add r0.w, -r0.w, l(1.000000)',
    'mov r2.y, cb2[1].w',
    'sample_indexable(texture2d)(float,float,float,float) r1.w, r2.xyxx, t2.yzwx, s2',
    'mad o0.xyz, r0.wwww, r1.xyzx, r0.xyzx', 'mov o0.w, l(1.000000)'])
seq('self-shadow-global-height-alpha-start', 'self_shadow', [
    'sample_indexable(texture2d)(float,float,float,float) r0.z, r0.zwzz, t0.xywz, s0',
    'mul r0.z, r0.z, cb1[16].z', 'mad r0.z, r0.z, l(255.000000), cb0[75].z',
    'mad r0.z, r0.w, l(0.314485), r0.z'])
seq('self-shadow-40-ray-soft-factor', 'self_shadow', [
    'uge r2.w, r2.z, l(40)', 'mad r1.zw, r0.xxxy, cb1[22].xxxy, r1.zzzw',
    'mad r2.y, r0.w, l(0.314485), r2.y',
    'sample_indexable(texture2d)(float,float,float,float) r2.w, r1.zwzz, t0.xyzw, s0',
    'mad r2.w, r2.w, l(255.000000), l(-64.000000)', 'mul_sat r2.w, r2.w, l(0.010417)',
    'min r2.w, r2.w, r2.x', 'movc r2.x, r3.x, r2.w, r2.x',
    'mul o0.xyzw, r0.xxxx, cb0[75].zzzz'])

# The original q2 register survives its rejection test and all reflection work.
water_lines = text['water'].splitlines()
q_begin = next(i for i, v in enumerate(water_lines) if v == 'div r1.w, r1.w, r0.w')
q_end = next(i for i, v in enumerate(water_lines) if v == 'mul r0.z, r1.w, r1.w')
writes = []
for i in range(q_begin + 1, q_end):
    words = water_lines[i].strip().split()
    if len(words) > 1 and words[1].rstrip(',').startswith('r1.') and 'w' in words[1].split('.')[1]:
        writes.append(i + 1)
assert not writes

pipeline = json.loads(text['pipeline'])
effects = {v['name']: v for v in pipeline['effect_records']['effects'].values()}
semantics = json.loads(text['phase0_semantics'])
exe = Path(semantics['exe']['path'])
exe_before = ref(exe)
assert exe_before['sha256'] == 'b7c8977ebab33ba6c1abf65d63fa310f8d096341465e0fc419f1b4da0fcd8818'
raw_exe = exe.read_bytes()
literal_specs = {
    'water': ('WaterShader', 2, {'negative_shadow': 0xbf2b851f, 'gray': 0x3ecccccd,
              'gamma': 0x400ccccd, 'inverse_gamma': 0x3ee8ba2f, 'log2e': 0x3fb8aa3b}),
    'cache': ('CacheBake', 1, {'irradiance_gain': 0x3fd9999a, 'albedo_epsilon': 0x3a83126f,
              'inverse_gamma': 0x3ee8ba2f, 'gloss_gain': 0x42800000}),
    'self_shadow': ('TerrainShaderScreen', 3, {'ray_rise': 0x3ea1043d, 'soft_inverse96': 0x3c2aaaab}),
}
literals = {}
for group, (effect, index, entries) in literal_specs.items():
    b = effects[effect]['passes'][index]['ps']['sm5']
    offset = int(b['file_offset'], 16)
    raw = raw_exe[offset:offset + b['bytes']]
    assert hashlib.sha256(raw).hexdigest() == b['sha256']
    literals[group] = {'source_blob': b, 'constants': {}}
    for name, bits in entries.items():
        pattern = struct.pack('<I', bits)
        offsets = [i for i in range(0, len(raw)-3, 4) if raw[i:i+4] == pattern]
        assert offsets, (group, name)
        literals[group]['constants'][name] = dict(bits=f'0x{bits:08x}',
            float32_value=struct.unpack('<f', pattern)[0], blob_byte_offsets=offsets)

registry = json.loads(text['registry'])
runtime_registry = [r for r in registry['shader_registry']['shaders']
                    if r['name'] in ('NormalCalculate', 'CacheBake', 'TerrainShader', 'TerrainShaderScreen')]
assert len(runtime_registry) == 4 and all(r['binding_table_kind'] == 'runtime-filled (.bss)' for r in runtime_registry)
assert len([l for l in text['normal'].splitlines() if l.startswith('sample_indexable')]) == 8
assert ref(exe) == exe_before
after = {k: ref(p) for k, p in FILES.items()}
assert before == after
result = dict(
    schema='zerosis.original_lighting.phase5.instruction_contract.v1',
    status='PASS_SELECTED_ORIGINAL_LIGHTING_FORMULAS_AND_RUNTIME_UNKNOWN_BOUNDARIES',
    inputs_before=before, inputs_after=after, original_exe=exe_before,
    checks=checks, instruction_checks=len(checks), exact_float32_literals=literals,
    water_q2_lifetime=dict(exponent_line=q_begin+1, first_cubic_use_line=q_end+1,
        intervening_r1w_writes=writes, rejected_gaussian_does_not_discard_q2=True,
        depth_alpha='r2.w remains depth-palette alpha until output alpha; intervening r2.xyz writes do not touch w'),
    confirmed_water=dict(
        samples={'t6': 'DepthColour at (1-saturate(4*t7.A),0), LOD0', 't7': 'underlying WorldHeightMap.A',
                 't4': 'four reflection samples', 't13': 'projected shadow R', 't9': 'premultiplied map overlay',
                 't10': 'FOW R and B', 't11': '3D FOW colour LUT', 't8': 'fog ramp R'},
        parameters={'cb1[14].xyz': 'primary light direction', 'cb1[15].xyz': 'secondary light direction',
                    'cb1[16].xyz/w': 'primary RGB/K', 'cb1[17].xyz/w': 'secondary RGB/K',
                    'cb1[18]/[19]': 'primary/secondary warped-view origin and mix',
                    'cb1[20]': 'height density, distance density, unused z, fog-ramp row',
                    'cb1[21].xyz': 'camera in original Z-up world', 'cb1[22..25]': 'reflection projector',
                    'cb1[26..29]': 'dynamic-shadow projector', 'cb1[30..33]': 'WaterBlendMap UV projector',
                    'cb1[34].x': 'shadow strength', 'cb1[35].rgb': 'distance-fog colour',
                    'cb1[36].x': 'reflection RGB gain'},
        pre_shadow='L*(D.rgb + F*(G1*C1 + G2*C2)) + Gwide1*D.rgb*C1 + reflectionMean.rgb^gamma*reflectionGain + saturate(4*h)*q2^3*D.rgb',
        definitions={'D': 'DepthColour sample value without another RGB gamma conversion in this shader',
                     'N': '(mixedMeanX,mixedMeanY,1), not normalized',
                     'L': 'saturate(dot(N,primaryLight))', 'F': '(1-dot(N,normalizedCameraMinusWorld))^5, no internal clamp/F0',
                     'G1/G2': 'rejection-masked narrow primary/secondary Gaussian',
                     'Gwide1': 'rejection-masked wide primary Gaussian, including literal .005 multiplier',
                     'q2': 'unmasked secondary Gaussian exponent, even when narrow G2 is rejected'},
        shadow='preShadow + negativeShadowLiteral*(saturate(shadowSampleR)*shadowStrength*preShadow)',
        alpha='saturate(D.a + reflectionMean.a*D.a), not modified by overlay/FOW/distance colour operations',
        colour_order=['shadow multiply', 'RGB^inverseGamma', 'premultiplied overlay',
                      'lerp(grayLiteral,colour,FOW.R)', 'lerp(colour,FOW_LUT(colour),R*(1-B))', 'distance/height fog'],
        distance='Same E-based expression as final terrain; original d.z is world Z-up. Water ramp coordinate is .5*(v4.y/v4.z)+.5, row cb1[20].w, sample t8.R. Final fog colour cb1[35].rgb; alpha remains the previous water alpha.'),
    confirmed_terrain_cache=dict(
        base_normal='VS passes input normal n directly',
        tangent='(-nz,0,nx)/sqrt(nz^2+nx^2)', bitangent='(0,nz,-ny)/sqrt(nz^2+ny^2)',
        decoded='m=2*normalCache.rgb-1; N=T*m.x+B*m.y+n*m.z; do not normalize final N',
        irradiance='cube4(N)*gain + shadowR*(cube5(N)*gain-cube4(N)*gain); no shadow clamp in this branch',
        diffuse='LUT_t8(pow(albedoSample.rgb*irradiance+epsilon,inverseGamma)); alpha=1',
        specular='e=64*specSample.a+1; f=pow(saturate(dot(N,cb1[21].xyz)),e)*e*saturate(1-shadowR); output1.rgb=LUT_t8(pow(specSample.rgb*f,inverseGamma)); output1.a=specSample.a*f',
        slots={'t0': 'encoded tangent-space normal cache', 't1': 'albedo sample', 't2.R': 'shadow interpolation scalar',
               't3': 'specular RGBA cache (pass1)', 't4/t5': 'two irradiance cubemaps', 't8': 'same 3D LUT for diffuse and specular'}),
    confirmed_normal_filter=dict(
        source='eight t0.R samples; actual producer binding not traced',
        offsets='(-a,+z),(-a,-b),(+a,-b),(+a,+z),(-a,+b),(+a,+b),(+z,-b),(+z,+b), where cb1[0]=(a,b,z,*)',
        sx='NW-NE+2*Left+SW-SE-2*Right', sy='NW+NE+2*North-SW-SE-2*South',
        encoded='0.5+0.5*normalize(-strength*Sx,+strength*Sy,4), strength=cb1[1].x; alpha0',
        caveat='Calling offsets cardinal assumes runtime z=0. Material-height cache versus global-heightfield source is not established by the shader.'),
    confirmed_final_terrain=dict(
        cache='C0=cb1[28].x ? sample(t0).rgb : 0',
        screen_light='cb1[27].x ? pow(pow(t8.rgb,gamma)*t9(screenUV).rgb+pow(C0,gamma),inverseGamma) : C0',
        colour_key='lerp(C,LUT_t7(C),saturate(projectedMask_t3.R)*cb1[25].x)',
        overlay='premultipliedOverlay.rgb+(1-premultipliedOverlay.a)*C',
        fow='C=lerp(baseLayer_t5,C,FOW_t4.R); C=lerp(C,LUT_t6(C),R*(1-B))',
        distance='E(x)=exp2(x*exactLog2E); d=world-camera; f=(1-min(E((1-E(d.z*heightDensity))*dot(d,d)*distanceDensity/d.z),1))*FogRamp.R; C=lerp(C,FogColor,f)',
        alpha='1',
        specular_routing='CacheBake output1 is confirmed, but how it becomes final t0 or another light buffer is not traced.'),
    confirmed_self_shadow=dict(
        source='t0.A times 255 times cb1[16].z, distinct from the NormalCalculate t0.R samples',
        direction='cb1[17].xy/max(abs(x),abs(y))', world_step='length(direction*cb1[16].xy)',
        initial='ray=heightA*255*heightScale+cb0[75].z; then one step/rise before the loop',
        loop='40 iterations: UV+=direction*cb1[22].xy; ray+=worldStep*exactRayRise; if sampleA*255*heightScale>ray then lit=min(lit,1-saturate((sampleA*255-64)*exactInverse96))',
        result='(1-lit)*cb0[75].z in all RGBA lanes',
        first_sample='Loop first sample is the second step from the original source, due to pre-loop plus loop advancement.',
        caveat='UV scale/offset, bias/amplitude, ray direction and the exact relation to current atlas units remain runtime candidates; unknown sample rejection is an added privacy policy.'),
    fixed_pipeline_blend_evidence=dict(
        shader_internal_premultiplied_overlay_confirmed=True,
        water_alpha_output_confirmed=True,
        hardware_om_blend_state_confirmed=False,
        cache_pass_frame_order_resolution_confirmed=False,
        effect_pass_record=pipeline['effect_records']['pass_record'],
        runtime_registry=runtime_registry,
        limitation='Selected DXBC contains shader operations and output signatures, not the external OM blend descriptors. The established pass table contains VS/PS/GS/HS/DS handles only; it is not blend-state evidence.'),
    recommended_phase5_scope=[
        'Implement the confirmed Water pre-shadow/alpha/encoding/composition order with explicit runtime parameter policy and original q2 lifetime; keep invalid/overflow guards separate.',
        'Implement exact CacheBake basis, cube mixture, diffuse/specular gamma+LUT and final terrain functions as pure CPU references and HLSL helpers with explicit sample inputs.',
        'Reuse mixed material diffuse/height/specular outputs and current geometry. Fuse pointwise formulas when their sampled inputs are the same; do not claim equivalent cache filtering or cache pass scheduling.',
        'Use the minimal original cubemap/Terrain-LUT packet. Map t4 to sunlight and t5 to shadowlight only as an explicit binding interpretation; keep continent and cube-axis mapping policies stated.',
        'Choose a neutral material normal or a current material-height Sobel producer as an explicit candidate. Never relabel global geometry normal as the confirmed original material-normal cache.',
        'Expose explicit shadow inputs/default0; an optional 40-step current-atlas shadow producer needs its own units/known-ray policy. It does not restore dynamic scene shadow production.',
        'Keep current colour/depth/integer-ID contracts and isolated-scene refraction; hardware water compositing and specular-target routing remain explicit policies until independently traced.',
    ],
    unknowns=[
        'All runtime light vectors/colours/K/scale, projection matrices, blend UV/time coefficients and shadow strengths/biases.',
        'Original NormalCalculate input texture producer, cache texel offset/strength, tangent source normals and normal-cache sampling resolution.',
        'Actual resource upload formats, sunlight/shadowlight identity/order and LUT asset selection despite confirmed shader dimensions/slots.',
        'The original CacheBake specular target consumer, final light-buffer production and frame/cache pass ordering/resolution.',
        'Original D3D OM blend/depth descriptors and the full render-state ordering; exact output alpha is not hardware blend proof.',
        'Screen-scene refraction is a separate new candidate; examined original water PS0/2 did not establish that separate source pair.',
    ],
    safety_separation='Finite input/range guards, degenerate tangent rejection, nonfinite q handling, zero-height fog limit, unknown ray fallback and optical overflow handling are explicit current policies, not additional proven original algebra.',
    protected_phases_unchanged=True, scratch_binary_files_retained=0,
    host_gamecore_clr_hwnd_gpu_audio_or_game_executed=False,
    source_or_existing_docs_modified=False,
)
OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
print(json.dumps(dict(status=result['status'], instruction_checks=len(checks),
                      original_binary_float_groups=len(literals), bytes=OUT.stat().st_size,
                      sha256=hashlib.sha256(OUT.read_bytes()).hexdigest())))
