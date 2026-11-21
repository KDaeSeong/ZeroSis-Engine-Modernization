"""Check selected original instructions and separate operations from calibration."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[3]

SPEC = {
    'WaterShader_0_vs.asm': {
        'constant_height_plane': [
            'mul r0.xyzw, v0.yyyy, cb1[1].xyzw',
            'mad r0.xyzw, v0.xxxx, cb1[0].xyzw, r0.xyzw',
            'mad r0.xyzw, cb1[12].xxxx, cb1[2].xyzw, r0.xyzw',
            'add r0.xyzw, r0.xyzw, cb1[3].xyzw'],
        'fixed_world_height': ['mov o3.xy, v0.xyxx', 'mov o3.z, cb1[12].x'],
        'uv_pair_zero': ['mad o1.zw, r0.xxxy, r0.zzzw, cb1[11].xxxx',
                         'mad o1.xy, v0.xyxx, cb1[9].xxxx, cb1[11].xxxx'],
        'uv_pair_one': ['mad o2.zw, r0.xxxy, r0.zzzw, cb1[11].xxxx',
                        'mad o2.xy, -v0.xyxx, cb1[9].zzzz, cb1[11].xxxx']},
    'WaterShader_0_ps.asm': {
        'depth_colour_lookup': [
            'sample_indexable(texture2d)(float,float,float,float) r1.x, v5.zwzz, t7.wxyz, s7',
            'mul_sat r1.x, r1.x, l(4.000000)', 'add r1.x, -r1.x, l(1.000000)',
            'mov r1.y, l(0)',
            'sample_l_indexable(texture2d)(float,float,float,float) r1.xyzw, r1.xyxx, t6.xyzw, s6, l(0.000000)'],
        'slope_decode': [
            'sample_indexable(texture2d)(float,float,float,float) r2.xy, v1.xyxx, t0.xyzw, s0',
            'mad r2.xy, r2.xyxx, l(2.000000, 2.000000, 0.000000, 0.000000), l(-1.000000, -1.000000, 0.000000, 0.000000)',
            'sample_indexable(texture2d)(float,float,float,float) r2.zw, v1.zwzz, t0.zwxy, s0',
            'add r2.zw, r2.zzzw, r2.zzzw',
            'mad r2.zw, r2.zzzw, l(0.000000, 0.000000, -1.000000, 1.000000), l(0.000000, 0.000000, 1.000000, -1.000000)'],
        'water_colour_alpha': ['mov_sat o0.w, r1.w'],
        'unexplored_discard': [
            'sample_indexable(texture2d)(float,float,float,float) r0.xy, v5.xyxx, t10.xzyw, s10',
            'eq r0.z, r0.x, l(0.000000)', 'discard_nz r0.z'],
        'fow_lut_amount': [
            'sample_indexable(texture3d)(float,float,float,float) r2.xyz, r1.xyzx, t11.xyzw, s11',
            'mad r0.x, r0.y, -r0.x, r0.x', 'add r0.yzw, -r1.xxyz, r2.xxyz',
            'mad r0.xyz, r0.xxxx, r0.yzwy, r1.xyzx'],
        'water_distance_fog': [
            'mul r1.xy, r1.xzxx, cb1[20].yxyy', 'mul r1.y, r1.y, l(1.442695)',
            'exp r1.y, r1.y', 'add r1.y, -r1.y, l(1.000000)',
            'mul r1.x, r1.y, r1.x', 'div r1.x, r1.x, r1.z',
            'mul r1.x, r1.x, l(1.442695)', 'exp r1.x, r1.x',
            'min r1.x, r1.x, l(1.000000)', 'add r1.x, -r1.x, l(1.000000)']},
    'WaterShader_1_ps.asm': {
        'alternate_colour_and_alpha': [
            'sample_indexable(texture2d)(float,float,float,float) r1.xyz, v2.zwzz, t6.xyzw, s6',
            'sample_indexable(texture2d)(float,float,float,float) r0.z, v2.zwzz, t5.xywz, s5'],
        'colour_key_after_gamma': [
            'log r1.xyz, r1.xyzx',
            'mul r1.xyz, r1.xyzx, l(0.454545, 0.454545, 0.454545, 0.000000)',
            'exp r1.xyz, r1.xyzx',
            'sample_indexable(texture3d)(float,float,float,float) r1.xyz, r1.xyzx, t12.xyzw, s12']},
    'WaterShader_2_ps.asm': {
        'lean_cross_moment_decode': [
            'sample_indexable(texture2d)(float,float,float,float) r3.xyzw, v1.xyxx, t0.zwxy, s0',
            'sample_indexable(texture2d)(float,float,float,float) r1.w, v1.xyxx, t1.yzwx, s1',
            'mad r4.xy, r3.zwzz, l(2.000000, 2.000000, 0.000000, 0.000000), l(-1.000000, -1.000000, 0.000000, 0.000000)',
            'mul r4.zw, r0.zzzz, r4.xxxy', 'mad r3.z, r1.w, l(2.000000), l(-1.000000)'],
        'covariance_is_second_moment_minus_mean_product': [
            'mul r0.zw, r4.zzzw, r6.yyyx', 'add r3.xy, r0.zwzz, r0.zwzz',
            'dp2 r3.z, r4.zwzz, r6.xyxx', 'add r1.yzw, r1.yyzw, r3.xxyz',
            'mad r1.yzw, -r7.xxyx, r7.xxyy, r1.yyzw'],
        'gaussian_lobe_and_rejection': [
            'mul r5.z, r5.z, l(0.500000)', 'div r5.z, r5.z, r4.w',
            'ge r5.w, l(0.000000), r4.w', 'ge r6.y, r5.z, l(16.000000)',
            'or r5.w, r5.w, r6.y', 'mul r5.z, r5.z, l(-1.442695)',
            'exp r5.z, r5.z', 'sqrt r4.w, r4.w', 'div r4.w, r5.z, r4.w'],
        'reflection_quarter_average': [
            'sample_indexable(texture2d)(float,float,float,float) r8.xyzw, r3.zwzz, t4.xyzw, s4',
            'mul r8.xyzw, r8.xyzw, l(0.250000, 0.250000, 0.250000, 0.250000)',
            'mad r6.xyzw, r6.xyzw, l(0.250000, 0.250000, 0.250000, 0.250000), r8.xyzw']},
    'RiverShader_0_vs.asm': {
        'river_phase_uv': ['mad o2.xy, -cb0[4].xxxx, l(0.000000, 0.050000, 0.000000, 0.000000), v3.xyxx']},
    'RiverShader_0_ps.asm': {
        'view_angle_colour': [
            'add r0.xyz, -v3.xyzx, cb1[12].xyzx', 'dp3 r0.x, r0.xyzx, r0.xyzx',
            'rsq r0.x, r0.x', 'mul_sat r0.x, r0.x, r0.z',
            'mad r0.y, r0.x, l(-2.000000), l(3.000000)',
            'mul r0.x, r0.x, r0.x', 'mul r0.x, r0.x, r0.y'],
        'single_texture_premultiplied_mix': [
            'sample_indexable(texture2d)(float,float,float,float) r1.xyzw, v2.zwzz, t1.xyzw, s1',
            'add r2.x, -r1.w, l(1.000000)', 'mul r1.xyzw, r1.wwww, r1.xyzw',
            'mad o0.xyzw, r0.xyzw, r2.xxxx, r1.xyzw']}
}


def ref(path):
    raw = path.read_bytes()
    return dict(path=str(path),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())


def main():
    results = []
    for name, checks in SPEC.items():
        path = STAGE/'bytecode'/name
        lines = [line.strip() for line in path.read_text('utf8').splitlines() if line.strip() and not line.startswith('//')]
        values = {label:any(lines[start:start+len(sequence)]==sequence for start in range(len(lines)-len(sequence)+1))
                  for label,sequence in checks.items()}
        if name=='RiverShader_0_ps.asm':
            values['flow_uv_not_consumed_by_this_ps'] = not any('v2.xy' in line or 'v2.y' in line for line in lines)
            values['one_declared_texture_only_t1'] = [line for line in lines if line.startswith('dcl_resource')] == [
                'dcl_resource_texture2d (float,float,float,float) t1']
        assert all(values.values()), (name,values)
        results.append(dict(listing=ref(path),checks=values))
    public = PROJECT/'Source/SDK_BNW_Original/CvGameCoreDLLUtil/include/CvDllInterfaces.h'
    adapter = PROJECT/'Source/SDK_BNW_Original/CvGameCoreDLL_Expansion2/CvDllPlot.h'
    internal = PROJECT/'Source/SDK_BNW_Original/CvGameCoreDLL_Expansion2/CvPlot.h'
    assert 'IsLake' not in public.read_bytes().decode('latin1') and 'IsLake' not in adapter.read_bytes().decode('latin1')
    assert 'bool isLake() const;' in internal.read_bytes().decode('latin1')
    result = dict(schema='zerosis.original_water.phase3.selected_shader_semantics.v1',
        status='PASS_ORIGINAL_INSTRUCTIONS_WITH_EXPLICIT_CALIBRATION_CANDIDATES',
        checks=sum(len(row['checks']) for row in results), shaders=results,
        source_disassembly=ref(STAGE/'bytecode/result.json'), sdk_contract=ref(STAGE/'sdk_river_contract.json'),
        coast_text_contract=ref(STAGE/'coast_text_contract.json'),
        public_lake_contract=dict(public_plot_is_lake=False, public_adapter_is_lake=False, internal_plot_is_lake=True,
                                 source_pins=[ref(public),ref(adapter),ref(internal)],
                                 policy='Do not call an unexposed private member through the public ABI. Lake classification is unsupported or an explicit public-data candidate.'),
        confirmed_operations=dict(
            water_plane='Original Water VS0 uses vertex xy and fixed original Z=cb1[12].x. It does not fetch per-vertex terrain height or add wave displacement in this pass.',
            water_uv=['(x,y)*cb1[9].x + cb1[11].x','(-x,y)*cb1[9].y + cb1[11].x',
                      '(-x,-y)*cb1[9].z + cb1[11].x','(x,-y)*cb1[9].w + cb1[11].x'],
            depth_colour='h=texture t7.A; u=1-saturate(4*h); sample t6 at (u,0), explicit LOD0. Pass0 alpha=saturate(t6.A).',
            two_layer_weights='b=2*t5.RG-1 at projected world position; a=(b.x-b.y+2,-b.x-b.y+2); weights=a/(a.x+a.y)/cb1[13].x.',
            two_slopes='A=(2*t0(uv0).R-1,2*t0(uv0).G-1); B=(1-2*t0(uv1).R,2*t0(uv1).G-1); mean=w0*A+w1*B; unnormalised shading vector=(mean.x,mean.y,1).',
            lean_second_moments='PS2 uses t0.B/A and signed t1.R cross terms, weighted by w0^2/w1^2, adds layer cross-products, then subtracts mean*mean to form covariance terms.',
            gaussian_reflection='Each selected lobe uses covariance plus a diagonal reciprocal runtime parameter; q=0.5*v^T*C^-1*v, exp(-q)/sqrt(det(C)). det<=0 or q>=16 rejects that lobe. A wider term adds 16/runtime_parameter to the diagonal and multiplies by0.005.',
            reflection_cache='PS2 samples t4 four times at projected/variance-derived offsets and averages with0.25 weights before RGB gamma2.2.',
            water_fow='t10.R==0 discards; pre-FOW RGB is mixed from constant0.4 gray by R, then t11 3D LUT by R*(1-B).',
            water_distance='Same height/distance exponential structure as terrain: delta=world-cb1[21], heightK=cb1[20].x, density=.y, Ramp row=.w, fog colour=cb1[35].rgb. Actual values remain untraced.',
            river_uv='River VS output TEXCOORD0 pair is (inputU,inputV-0.05*cb0[4].x). The selected River PS0 does not consume that pair.',
            river_colour='s=saturate(normalize(cb1[12].xyz-world).z); apply smoothstep polynomial s*s*(3-2*s) twice; RGB=2-s*(1.705882,1.643137,1.6); alpha=inputColour.A. Then output=(1-t1.A)*RGBA + t1.A*t1.RGBA at projected map UV.'),
        resource_name_strength=dict(
            water_descriptor='Static registry lists LEAN1_1, LEAN1_2, LEAN2_1, LEAN2_2, ReflectionMap, WaterBlendMap, WaterColor, WorldHeightMap, WaterFogRamp, OverlayMap, FOWMask, TransFOWColor, ColorKey, DynamicShadowTexture in that order.',
            caveat='RDEF names are stripped. Raw texture registers/swizzles and the operations are direct evidence. Matching descriptor order to t0..t13 is a supported interpretation; exact runtime CPU resource bindings and cache generation remain untraced.',
            river_descriptor='River binding table is runtime-filled; the selected shader reads only t1, whose asset identity is not established here.'),
        implementation_scope=dict(
            chosen='World-space colour-only atlas-following overlay after ground and before units/global FOW; no depth or integer-ID writes.',
            reused_original_operations='Depth lookup coordinate 1-saturate(4h), four mirrored UV forms, original DDS/coast text values and exact public river representative-edge mapping.',
            omitted='Raw LEAN source blobs are unused by this overlay and are excluded from its package. This is a storage/scope decision, not a finding that original water does not use LEAN.',
            not_claimed='Original plane/reflection/LEAN renderer, exact coast topology, original visible river animation, GPU or image parity.'),
        calibration_candidates=['Original plane Z, UV scales and phase-to-time mapping are runtime constants not recovered by the shader bytecode.',
            'Current atlas height to original WorldHeightMap alpha conversion and water lookup row/colour-space calibration remain candidates.',
            'Reflection-map generation, environment lighting, sampler states, cache dimensions/order and runtime LEAN roughness parameters remain unverified.',
            'Ribbon width, caps/joins, current world UV length/speed, coast meander and source-spline length units remain candidates.',
            'Public ICvPlot1 has no IsLake; no private-field or new-vtable inference is authorised.',
            'Actual unknown-data leakage, depth/occlusion, underwater units and raster ID equality require future controlled GPU/game acceptance.'],
        temporary_dxbc_retention='Six selected cso files were deleted after file-ID/SHA/mtime/link/attribute/FILE_STANDARD_INFO allocation checks; cleanup receipt is in bytecode/cleanup_result.json.',
        existing_evidence_or_original_assets_modified=False,host_gamecore_clr_hwnd_gpu_audio_or_game_executed=False,
        placement_report='규칙 동등, 배치 동등은 미검증')
    with (STAGE/'shader_semantics.json').open('x',encoding='utf8') as stream:
        json.dump(result,stream,indent=2)
        stream.write('\n')
    print(json.dumps(dict(status=result['status'],instruction_sequences=result['checks'],
                         selected_shaders=len(results),public_is_lake=False)))


if __name__=='__main__':
    main()
