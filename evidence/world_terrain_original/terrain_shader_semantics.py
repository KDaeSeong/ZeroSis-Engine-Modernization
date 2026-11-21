"""Pin what the retail terrain and fog-of-war shaders compute, from their fxc /dumpbin listings.

The shader-model-5 blobs named in retail_terrain_pipeline_probe.json are cut out of the retail EXE (read as bytes),
checked against the SHA-256 recorded there, disassembled by the Windows SDK fxc /dumpbin into a temporary directory
that is removed afterwards, and checked for the exact instructions each interpretation relies on.
fxc only disassembles bytecode; no game, Host, window or GPU is used.
usage: python -B -X utf8 terrain_shader_semantics.py [--listings DIR]
       (--listings reads existing <offset>_<stage>.asm files instead of running fxc)
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
STAGE = Path(__file__).absolute().parent
GAME_EXE = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V\CivilizationV_DX11.exe")
EXE_SHA = 'b7c8977ebab33ba6c1abf65d63fa310f8d096341465e0fc419f1b4da0fcd8818'
FXC = Path(r'C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\fxc.exe')

# effect, pass, slot -> exact instructions (whitespace-stripped lines) that must appear, in order where listed together.
SPEC = {
    ('TerrainShader', 0, 'vs'): dict(meaning='Tessellation control points: vertex id low/high byte is the grid x/y (offset -3); '
                                             'height = heightfield alpha * cb1[16].z * 255.',
                                     seq=[['and r0.x, v0.x, l(255)', 'utof r0.x, r0.x', 'add r0.y, r0.x, l(-3.000000)',
                                           'ushr r0.x, v0.x, l(8)'], ['mul r0.x, r0.x, cb1[16].z', 'mul o0.x, r0.x, l(255.000000)']]),
    ('TerrainShader', 0, 'hs'): dict(meaning='4x4 control points per quad patch, integer partitioning, one tessellation factor '
                                             'cb1[14].x for every edge and the inside.',
                                     seq=[['dcl_input_control_point_count 16', 'dcl_output_control_point_count 16',
                                           'dcl_tessellator_domain domain_quad', 'dcl_tessellator_partitioning partitioning_integer'],
                                          ['mov o[r0.x + 0].x, cb1[14].x'], ['mov o[r0.x + 4].x, cb1[14].x']]),
    ('TerrainShader', 0, 'ds'): dict(meaning='Bicubic surface: height = (u^3,u^2,u,1) B M H M^T B^T with the 4x4 control heights '
                                             'and basis rows cb1[10..13]; cache UV, world position, map-space UV (cb1[4..7]) '
                                             'and the screen position are passed on.',
                                     seq=[['dcl_input_control_point_count 16', 'dcl_tessellator_domain domain_quad'],
                                          ['dp4 r2.x, cb1[10].xyzw, r1.xyzw', 'dp4 r2.y, cb1[11].xyzw, r1.xyzw',
                                           'dp4 r2.z, cb1[12].xyzw, r1.xyzw', 'dp4 r2.w, cb1[13].xyzw, r1.xyzw', 'dp4 r0.x, r2.xyzw, r0.xyzw'],
                                          ['mul o2.xy, r0.yzyy, cb0[5].xyxx'],
                                          ['mad o3.xyzw, r1.xyzw, l(0.500000, -0.500000, 1.000000, 1.000000), '
                                           'l(0.500000, 0.500000, 0.000000, 0.000000)']]),
    ('TerrainShader', 3, 'vs'): dict(meaning='Non-tessellated grid: same height fetch per vertex (alpha * cb1[16].z * 255), '
                                             'FOW base-layer UV o2.zw from world xy, map-space UV o3 from cb1[4..7].',
                                     seq=[['mul r0.xy, r0.xyxx, cb1[16].xyxx'], ['mul r0.z, r0.z, cb1[16].z', 'mul r0.z, r0.z, l(255.000000)'],
                                          ['add r1.xy, r0.xyxx, cb1[9].zwzz', 'mul o2.zw, r1.xxxy, cb1[9].xxxy'],
                                          ['mad o3.xyzw, r1.xyzw, l(0.500000, -0.500000, 1.000000, 1.000000), '
                                           'l(0.500000, 0.500000, 0.000000, 0.000000)']]),
    ('TerrainShader', 0, 'ps'): dict(
        meaning='Final terrain colour: lit cache t0 (+ albedo cache t8 x screen light buffer t9 in linear space when cb1[27]); '
                'colour LUT t7 weighted by a world-projected mask t3 * cb1[25].x; premultiplied overlay t1 in map space; '
                'FOW: lerp(base layer t5, colour, mask.x) then LUT t6 weighted mask.x*(1-mask.z); exponential height/distance '
                'fog toward cb2[0] scaled by FogRamp t2 row cb2[1].w.',
        seq=[['sample_indexable(texture2d)(float,float,float,float) r0.yzw, v2.xyxx, t8.wxyz, s8'],
             ['sample_indexable(texture2d)(float,float,float,float) r1.xyz, r1.xyxx, t9.xyzw, s9',
              'sample_indexable(texture2d)(float,float,float,float) r2.xyz, v2.xyxx, t0.xyzw, s0',
              'movc r2.xyz, cb1[28].xxxx, r2.xyzx, l(0,0,0,0)'],
             ['movc r0.yzw, cb1[27].xxxx, r0.yyzw, r2.xxyz',
              'sample_indexable(texture3d)(float,float,float,float) r1.xyz, r0.yzwy, t7.xyzw, s7'],
             ['sample_indexable(texture2d)(float,float,float,float) r1.xyzw, v3.xyxx, t1.xyzw, s1',
              'add r0.w, -r1.w, l(1.000000)', 'mad r0.xyz, r0.xyzx, r0.wwww, r1.xyzx',
              'sample_indexable(texture2d)(float,float,float,float) r1.xyz, v2.zwzz, t5.xyzw, s5',
              'add r0.xyz, r0.xyzx, -r1.xyzx',
              'sample_indexable(texture2d)(float,float,float,float) r2.xy, v3.xyxx, t4.xzyw, s4',
              'mad r0.xyz, r2.xxxx, r0.xyzx, r1.xyzx', 'mad r0.w, r2.y, -r2.x, r2.x',
              'sample_indexable(texture3d)(float,float,float,float) r1.xyz, r0.xyzx, t6.xyzw, s6'],
             ['add r1.xyz, -r0.xyzx, cb2[0].xyzx', 'add r2.xyz, v4.xyzx, -cb1[19].xyzx', 'mul r0.w, r2.z, cb2[1].x',
              'mul r0.w, r0.w, l(1.442695)', 'exp r0.w, r0.w', 'add r0.w, -r0.w, l(1.000000)', 'dp3 r1.w, r2.xyzx, r2.xyzx',
              'mul r1.w, r1.w, cb2[1].y'],
             ['mov r2.y, cb2[1].w', 'sample_indexable(texture2d)(float,float,float,float) r1.w, r2.xyxx, t2.yzwx, s2',
              'mul r0.w, r0.w, r1.w', 'mad o0.xyz, r0.wwww, r1.xyzx, r0.xyzx']]),
    ('TerrainShader', 1, 'ps'): dict(meaning='Same as pass 0 without the albedo x screen-light term (t8/t9 absent).',
                                     seq=[['sample_indexable(texture2d)(float,float,float,float) r2.xy, v3.xyxx, t4.xzyw, s4'],
                                          ['mad o0.xyz, r0.xxxx, r1.xyzx, r0.yzwy']], absent=['t8', 't9']),
    ('TerrainShader', 2, 'ps'): dict(meaning='Overlay only: returns t1 at the map-space UV.',
                                     seq=[['sample_indexable(texture2d)(float,float,float,float) o0.xyzw, v3.xyxx, t1.xyzw, s1']]),
    ('NormalCalculate', 0, 'ps'): dict(meaning='Sobel filter of the height cache (8 taps, offsets cb1[0], strength cb1[1].x), '
                                               'normal encoded n*0.5+0.5.',
                                       seq=[['dp3 r0.z, r0.xyzx, l(1.000000, -1.000000, 2.000000, 0.000000)'],
                                            ['mul r1.x, l(0.500000), cb1[1].x'],
                                            ['mad o0.xyz, r1.xyzx, l(0.500000, 0.500000, 2.000000, 0.000000), '
                                             'l(0.500000, 0.500000, 0.500000, 0.000000)']], samples=8),
    ('CacheBake', 0, 'ps'): dict(meaning='Cache lighting: tangent-space normal from the normal cache, two irradiance cubes '
                                         '(x1.7) lerped by the shadow cache t2, times albedo t1, gamma 1/2.2, colour LUT t8.',
                                 seq=[['mad r2.xyz, r2.xyzx, l(2.000000, 2.000000, 2.000000, 0.000000), l(-1.000000, -1.000000, -1.000000, 0.000000)'],
                                      ['mul r0.xyz, r0.xyzx, l(1.700000, 1.700000, 1.700000, 0.000000)',
                                       'mad r1.xyz, r1.xyzx, l(1.700000, 1.700000, 1.700000, 0.000000), -r0.xyzx',
                                       'sample_indexable(texture2d)(float,float,float,float) r0.w, v2.xyxx, t2.yzwx, s2',
                                       'mad r0.xyz, r0.wwww, r1.xyzx, r0.xyzx',
                                       'sample_indexable(texture2d)(float,float,float,float) r1.xyz, v2.xyxx, t1.xyzw, s1',
                                       'mad r0.xyz, r1.xyzx, r0.xyzx, l(0.001000, 0.001000, 0.001000, 0.000000)'],
                                      ['mul r0.xyz, r0.xyzx, l(0.454545, 0.454545, 0.454545, 0.000000)', 'exp r0.xyz, r0.xyzx',
                                       'sample_indexable(texture3d)(float,float,float,float) r0.xyz, r0.xyzx, t8.xyzw, s8']]),
    ('CacheBake', 1, 'ps'): dict(meaning='Pass 0 plus a specular target: (N.cb1[21])^(64*gloss+1) * (64*gloss+1) * '
                                         '(1-shadow) * spec cache t3, gamma and LUT.',
                                 seq=[['dp3_sat r0.x, cb1[21].xyzx, r0.xyzx', 'log r0.x, r0.x'],
                                      ['add_sat r1.x, -r1.w, l(1.000000)'],
                                      ['sample_indexable(texture2d)(float,float,float,float) r2.xyzw, v2.xyxx, t3.xyzw, s3',
                                       'mad r0.y, r2.w, l(64.000000), l(1.000000)', 'mul r0.x, r0.x, r0.y', 'exp r0.x, r0.x',
                                       'mul r0.x, r0.y, r0.x', 'mul r0.x, r1.x, r0.x', 'mul r0.xyzw, r2.xyzw, r0.xxxx']]),
    ('TerrainShaderScreen', 0, 'vs'): dict(
        meaning='Blend-mesh vertex: position already in cache clip space (+cb0[0].xy); 8 material slots from BLENDINDICES0/1 '
                'index cb2[] = (texture scale, projection); projection 0 -> world.xy*scale*0.33, 1 -> world.xz*scale*0.66, '
                '2 -> world.yz*scale*0.66; the 8 weights come from TEXCOORD2/3.',
        seq=[['add o0.xy, v0.xyxx, cb0[0].xyxx', 'mov r0.x, v5.x',
              'eq r0.yz, cb2[r0.x + 0].yyyy, l(0.000000, 1.000000, 2.000000, 0.000000)', 'if_nz r0.y',
              'mul r0.yw, v2.xxxz, cb2[r0.x + 0].xxxx', 'mul r1.xy, r0.ywyy, l(0.660000, 0.660000, 0.000000, 0.000000)', 'else',
              'mul r0.yw, v2.xxxy, cb2[r0.x + 0].xxxx', 'mul r1.xy, r0.ywyy, l(0.330000, 0.330000, 0.000000, 0.000000)', 'endif',
              'if_nz r0.z', 'mul r0.xy, v2.yzyy, cb2[r0.x + 0].xxxx', 'mul r1.xy, r0.xyxx, l(0.660000, 0.660000, 0.000000, 0.000000)'],
             ['mov r1.zw, v3.xxxy', 'mov o3.xyzw, r1.xyzw', 'mov r2.zw, v3.zzzw', 'mov o4.xyzw, r2.xyzw']]),
    ('TerrainShaderScreen', 1, 'vs'): dict(
        meaning='Alternative weights: 5x5 Gaussian (centre 0.157207) over a uint terrain-id texture (row 1023-y), each id '
                'mapped through cb0[9+id] to one of 8 slots chosen by BLENDINDICES0.x (0/1/2).',
        seq=[['add r0.x, -v1.y, l(1023.000000)'], ['ieq r2.xy, v5.xxxx, l(1, 2, 0, 0)'],
             ['add r1.y, r1.y, l(0.002456)'], ['add r1.y, r1.y, l(0.157207)']], count={'ld_aoffimmi_indexable(': 25}),
    ('TerrainShaderScreen', 1, 'ps'): dict(
        meaning='8-layer height blend into 3 targets: per layer d=albedo^2, h=height, s=spec^2 (skipped when weight<=0.01); '
                'W_i = (d_i.a)^4 * w_i = albedo_alpha^8 * w_i; outputs sum(W d)/sum W, sum(W h)/sum W, sum(W s)/sum W.',
        seq=[['lt r0.xy, l(0.010000, 0.010000, 0.000000, 0.000000), v3.zwzz', 'if_nz r0.x',
              'sample_indexable(texture2d)(float,float,float,float) r1.xyzw, v3.xyxx, t0.xyzw, s0',
              'sample_indexable(texture2d)(float,float,float,float) r0.x, v3.xyxx, t8.xyzw, s1', 'mov x1[0].x, r0.x',
              'sample_indexable(texture2d)(float,float,float,float) r2.xyzw, v3.xyxx, t16.xyzw, s2',
              'mul r1.xyzw, r1.xyzw, r1.xyzw', 'mov x0[0].xyzw, r1.xyzw', 'mul r1.xyzw, r2.xyzw, r2.xyzw'],
             ['mov r0.x, x0[0].w'], ['mul r0.xyzw, r0.xyzw, r0.xyzw', 'mul r0.xyzw, r0.xyzw, r0.xyzw', 'mov r2.xy, v3.zwzz',
                                     'mov r2.zw, v4.zzzw', 'mul r0.xyzw, r0.xyzw, r2.xyzw'],
             ['dp4 r2.x, r0.xyzw, l(1.000000, 1.000000, 1.000000, 1.000000)', 'dp4 r2.y, r1.xyzw, l(1.000000, 1.000000, 1.000000, 1.000000)',
              'add r2.x, r2.y, r2.x'],
             ['div o0.xyzw, r3.xyzw, r2.xxxx', 'div o1.xyzw, r0.xxxx, r2.xxxx', 'div o2.xyzw, r4.xyzw, r2.xxxx']],
        count={'lt r0.xy, l(0.010000, 0.010000, 0.000000, 0.000000), v': 4, 'dcl_resource_texture2d': 24}),
    ('TerrainShaderScreen', 0, 'ps'): dict(meaning='Same 8-layer blend without the spec target (2 outputs, 16 textures).',
                                           seq=[['dcl_output o0.xyzw', 'dcl_output o1.xyzw']],
                                           count={'dcl_resource_texture2d': 16, 'dcl_output o': 2}),
    ('TerrainShaderScreen', 3, 'ps'): dict(meaning='Terrain self-shadow: 40-step march over the heightfield along cb1[17].xy, ray '
                                                   'rises 0.314485 per unit; soft term 1-sat((h*255-64)/96); output (1-lit)*cb0[75].z.',
                                           seq=[['uge r2.w, r2.z, l(40)'], ['mad r2.y, r0.w, l(0.314485), r2.y'],
                                                ['mad r2.w, r2.w, l(255.000000), l(-64.000000)', 'mul_sat r2.w, r2.w, l(0.010417)'],
                                                ['mul o0.xyzw, r0.xxxx, cb0[75].zzzz']]),
    ('TerrainShaderScreen', 4, 'ps'): dict(meaning='Un-premultiply copy: rgb / a, alpha 1.',
                                           seq=[['div o0.xyz, r0.xyzx, r0.wwww', 'mov o0.w, l(1.000000)']]),
    ('CompositeShader', 1, 'ps'): dict(meaning='Copy with alpha 0.3.', seq=[['mov o0.w, l(0.300000)']]),
    ('TerrainDecalShader', 1, 'ps'): dict(meaning='Decal diffuse, signed height (2y-1 < 0 -> (1-x, 2|..|) subtract form) and spec.',
                                          seq=[['mad r0.z, r0.y, l(2.000000), l(-1.000000)', 'lt r0.z, r0.z, l(-0.000100)'],
                                               ['movc o1.xyzw, r0.zzzz, r1.xyzw, r2.xyzw'],
                                               ['sample_indexable(texture2d)(float,float,float,float) o2.xyzw, v2.xyxx, t2.xyzw, s2']]),
    ('FOWDrawMask', 0, 'vs'): dict(meaning='Instanced hex geometry (matrix index from NORMAL.x into cb0[96]); mask value from TEXCOORD0.x.',
                                   seq=[['ftou r0.x, v1.x', 'ishl r0.x, r0.x, l(2)'], ['mov o2.xyz, v2.xxxx']]),
    ('FOWDrawMask', 0, 'ps'): dict(meaning='Writes the mask value to G.', seq=[['mov o0.xzw, l(0,0,0,1.000000)', 'mov o0.y, v2.x']]),
    ('FOWDrawMask', 1, 'ps'): dict(meaning='Writes the mask value to R and B.', seq=[['mov o0.xz, v2.xxxx']]),
    ('FOWDrawMask', 2, 'ps'): dict(meaning='Writes the mask value to R.', seq=[['mov o0.x, v2.x']]),
    ('FOWDrawMask', 3, 'ps'): dict(meaning='Clears to 0.', seq=[['mov o0.xyzw, l(0,0,0,0)']]),
    ('FOWParticleShader', 0, 'ps'): dict(meaning='Cloud particle: discard where mask.x < 0.01; alpha = mask.x * particle alpha.',
                                         seq=[['sample_indexable(texture2d)(float,float,float,float) r0.x, v1.zwzz, t1.yxzw, s1',
                                               'lt r0.y, r0.x, l(0.010000)', 'discard_nz r0.y'],
                                              ['mul r0.x, r0.x, r1.w'], ['mov o0.w, r0.x']]),
    ('FOWBaseLayer', 0, 'vs'): dict(meaning='Instanced; base-layer UV from world xy (cb0[196]), mask UV from cb0[192..195].',
                                    seq=[['mul o1.xy, r0.xyxx, cb0[196].xyxx']]),
    ('FOWBaseLayer', 0, 'ps'): dict(meaning='Base layer colour with alpha = mask.x * texture alpha.',
                                    seq=[['mul o0.w, r0.x, r1.w', 'mov o0.xyz, r1.xyzx']]),
}


def has_sequence(lines, wanted):
    for start in range(len(lines) - len(wanted) + 1):
        if lines[start:start + len(wanted)] == wanted:
            return True
    return False


def main(argv) -> int:
    pipeline = json.loads((STAGE / 'retail_terrain_pipeline_probe.json').read_text('utf8'))
    require_sha = pipeline['exe']['sha256']
    effects = {e['name']: e for e in pipeline['effect_records']['effects'].values()}
    listings_dir = Path(argv[argv.index('--listings') + 1]) if '--listings' in argv else None
    raw = GAME_EXE.read_bytes() if listings_dir is None else None
    if raw is not None and hashlib.sha256(raw).hexdigest() != EXE_SHA:
        raise SystemExit('Retail EXE differs from the analysed build')
    if require_sha != EXE_SHA:
        raise SystemExit('pipeline probe was made from another EXE')
    results, failures = [], []
    with tempfile.TemporaryDirectory(prefix='civ5_terrain_dxbc_') as scratch:
        for (effect, index, slot), spec in SPEC.items():
            blob = effects[effect]['passes'][index][slot]['sm5']
            name = f"{blob['file_offset']}_{slot}"
            if listings_dir is None:
                offset = int(blob['file_offset'], 16)
                data = raw[offset:offset + blob['bytes']]
                if hashlib.sha256(data).hexdigest() != blob['sha256']:
                    raise SystemExit('blob hash differs: ' + name)
                source, listing = Path(scratch) / (name + '.cso'), Path(scratch) / (name + '.asm')
                source.write_bytes(data)
                done = subprocess.run([str(FXC), '/nologo', '/dumpbin', '/Fc', str(listing), str(source)],
                                      capture_output=True, timeout=120)
                if done.returncode:
                    raise SystemExit('fxc failed for ' + name)
            else:
                listing = listings_dir / (name + '.asm')
            text = listing.read_text('utf8', errors='replace')
            lines = [line.strip() for line in text.splitlines() if line.strip() and not line.startswith('//')]
            checks = {}
            for k, wanted in enumerate(spec.get('seq', [])):
                checks[f'sequence_{k}'] = has_sequence(lines, wanted)
            for needle, expected in spec.get('count', {}).items():
                checks[f'count {needle} == {expected}'] = sum(1 for line in lines if line.startswith(needle)) == expected
            if 'samples' in spec:
                checks[f"samples == {spec['samples']}"] = sum(1 for line in lines if line.startswith('sample')) == spec['samples']
            for register in spec.get('absent', []):
                checks[f'{register} not declared'] = not any(line.startswith('dcl_resource') and line.endswith(' ' + register)
                                                             for line in lines)
            ok = all(checks.values())
            if not ok:
                failures.append(dict(effect=effect, pass_index=index, slot=slot, failed=[k for k, v in checks.items() if not v]))
            results.append(dict(effect=effect, pass_index=index, slot=slot, blob=blob['file_offset'], model=blob['model'],
                                sha256=blob['sha256'], listing_sha256=hashlib.sha256(text.encode('utf8')).hexdigest(),
                                instructions=sum(1 for line in lines if not line.startswith(('dcl_', 'vs_', 'ps_', 'hs_', 'ds_'))),
                                meaning=spec['meaning'], checks=checks, status='PASS' if ok else 'FAIL'))
    value = dict(schema='zerosis.world_terrain_original.terrain_shader_semantics.v1',
                 exe=dict(path=str(GAME_EXE), sha256=EXE_SHA),
                 tool=dict(path=str(FXC), sha256=hashlib.sha256(FXC.read_bytes()).hexdigest() if FXC.exists() else None,
                           mode='/dumpbin' if listings_dir is None else 'existing listings'),
                 pipeline_probe=hashlib.sha256((STAGE / 'retail_terrain_pipeline_probe.json').read_bytes()).hexdigest(),
                 shaders=results, failures=failures, status='PASS' if not failures else 'FAIL',
                 game_or_host_executed=False, gpu_used=False, scratch='temporary directory, removed after the run')
    out = STAGE / 'terrain_shader_semantics.json'
    if out.exists():
        out.unlink()
    with out.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, indent=1, ensure_ascii=False)
        stream.write('\n')
    print(json.dumps(dict(status=value['status'], shaders=len(results), failures=failures)))
    return 0 if not failures else 1


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
