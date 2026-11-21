"""Narrow the original water optics operations using retained pinned listings."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import struct
import sys

sys.dont_write_bytecode=True
STAGE=Path(__file__).absolute().parent
PROJECT=STAGE.parents[3]
PRIOR=PROJECT/'evidence/world_terrain_original/phase3/semantics/bytecode'


def ref(path):
    raw=path.read_bytes()
    return dict(path=str(path),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())


def lines(name):
    return [line.strip() for line in (PRIOR/name).read_text('utf8').splitlines() if line.strip() and not line.startswith('//')]


def sequence(code,wanted):
    return any(code[i:i+len(wanted)]==wanted for i in range(len(code)-len(wanted)+1))


def writes(line,register,component):
    if ' ' not in line:return False
    destination=line.split(' ',1)[1].split(',',1)[0]
    return destination.startswith(register+'.') and component in destination.split('.')[1]


def main():
    ps=lines('WaterShader_2_ps.asm');ps0=lines('WaterShader_0_ps.asm');vs=lines('WaterShader_0_vs.asm')
    checked={
      'primary_scale_applied_to_layer_weights':sequence(ps,['div r0.zw, r0.zzzw, r1.yyyy','div r0.zw, r0.zzzw, cb1[13].xxxx']),
      'raw_rg_signed_means':sequence(ps,[
        'sample_indexable(texture2d)(float,float,float,float) r3.xyzw, v1.xyxx, t0.zwxy, s0',
        'sample_indexable(texture2d)(float,float,float,float) r1.w, v1.xyxx, t1.yzwx, s1',
        'mad r4.xy, r3.zwzz, l(2.000000, 2.000000, 0.000000, 0.000000), l(-1.000000, -1.000000, 0.000000, 0.000000)']),
      'signed_cross_mirror':sequence(ps,['mad r5.z, -r1.w, l(2.000000), l(1.000000)','mul r5.xyz, r1.zzzz, r5.xyzx']),
      'covariance_outer_product_subtraction':'mad r1.yzw, -r7.xxyx, r7.xxyy, r1.yyzw' in ps,
      'non_normalised_material_normal':'mov r7.z, l(1.000000)' in ps and 'dp3_sat r0.z, cb1[14].xyzx, r7.xyzx' in ps,
      'unclamped_fresnel_fifth_power':sequence(ps,['dp3 r0.w, r7.xyzx, r4.xyzx','add r0.w, -r0.w, l(1.000000)',
        'mul r1.y, r0.w, r0.w','mul r1.y, r1.y, r1.y','mul r0.w, r0.w, r1.y']),
      'gaussian_det_and_q_rejection':sequence(ps,['ge r5.w, l(0.000000), r4.w','ge r6.y, r5.z, l(16.000000)','or r5.w, r5.w, r6.y']),
      'gaussian_no_two_pi':sequence(ps,['mul r5.z, r5.z, l(-1.442695)','exp r5.z, r5.z','sqrt r4.w, r4.w','div r4.w, r5.z, r4.w']),
      'wide_diagonal16_and_multiplier005':'div r5.z, l(16.000000), cb1[16].w' in ps and 'mul r5.x, r5.x, l(0.005000)' in ps,
      'reflection_projected_uv':sequence(ps,['div r3.zw, r6.xxxy, r6.zzzz',
        'mad r3.zw, r3.zzzw, l(0.000000, 0.000000, 0.500000, -0.500000), l(0.000000, 0.000000, -0.500000, -0.500000)',
        'mad r1.yz, r1.yyzy, l(0.000000, 6.000000, 6.000000, 0.000000), r3.zzwz']),
      'four_reflection_taps':sum('t4.xyzw' in line and line.startswith('sample') for line in ps)==4,
      'asymmetric_third_reflection_offset':'mad r3.zw, r0.wwww, l(0.000000, 0.000000, -2.000000, 6.000000), r1.yyyz' in ps,
      'reflection_gamma_after_average':sequence(ps,['mad r6.xyzw, r8.xyzw, l(0.250000, 0.250000, 0.250000, 0.250000), r6.xyzw',
        'log r6.xyz, r6.xyzx','mul r6.xyz, r6.xyzx, l(2.200000, 2.200000, 2.200000, 0.000000)','exp r6.xyz, r6.xyzx']),
      'ps0_alpha_from_depth_table':'mov_sat o0.w, r1.w' in ps0,
      'ps2_reflection_depth_alpha':'mad_sat o0.w, r6.w, r2.w, r2.w' in ps,
      'fow_clip_only_mask_r_zero':sequence(ps,['sample_indexable(texture2d)(float,float,float,float) r0.xy, v5.xyxx, t10.xzyw, s10',
        'eq r0.z, r0.x, l(0.000000)','discard_nz r0.z']) and sum('discard' in line for line in ps)==1,
      'constant_water_plane':'mov o3.z, cb1[12].x' in vs,
      'shadow_source_red':sequence(ps,['sample_indexable(texture2d)(float,float,float,float) r0.z, r0.zwzz, t13.yzxw, s13',
        'mov_sat r0.z, r0.z','mul r0.z, r0.z, cb1[34].x']),
    }
    q2=ps.index('div r1.w, r1.w, r0.w')
    cubic=ps.index('mul r0.z, r1.w, r1.w',q2)
    checked['q2_lifetime_through_cubic_depth_term']=not any(writes(line,'r1','w') for line in ps[q2+1:cubic]) and sequence(ps[cubic:],[
        'mul r0.z, r1.w, r1.w','mul r0.z, r1.w, r0.z','mul r0.z, r1.x, r0.z','mad r1.xyz, r0.zzzz, r2.xyzx, r3.xyzx'])
    det2=ps.index('mad r0.w, r5.y, r5.z, -r3.w')
    first_tap=ps.index('mad r3.zw, r0.wwww, l(0.000000, 0.000000, 2.000000, 2.000000), r1.yyyz',det2)
    checked['reflection_offset_uses_secondary_determinant']=not any(writes(line,'r0','w') for line in ps[det2+1:first_tap])
    assert all(checked.values()),[name for name,passed in checked.items() if not passed]

    pipeline_path=PROJECT/'evidence/world_terrain_original/retail_terrain_pipeline_probe.json'
    pipeline=json.loads(pipeline_path.read_text('utf8'))
    effect=next(value for value in pipeline['effect_records']['effects'].values() if value['name']=='WaterShader')
    blob=effect['passes'][2]['ps']['sm5']
    prior=json.loads((PROJECT/'evidence/world_terrain_original/terrain_shader_semantics.json').read_text('utf8'))
    exe=Path(prior['exe']['path']);raw=exe.read_bytes();assert hashlib.sha256(raw).hexdigest()==pipeline['exe']['sha256']
    offset=int(blob['file_offset'],16);code=raw[offset:offset+blob['bytes']]
    assert hashlib.sha256(code).hexdigest()==blob['sha256']
    constants=[]
    for name,value,expected in [('gamma',2.2,3),('inverse_gamma',1/2.2,3),('log2e',1.442695,2),('wide_multiplier',0.005,1)]:
        packed=struct.pack('<f',value);positions=[i for i in range(len(code)-3) if code[i:i+4]==packed]
        assert len(positions)==expected
        constants.append(dict(name=name,float32=struct.unpack('<f',packed)[0],bytes_le=packed.hex(),
                              occurrences=len(positions),offsets_in_dxbc=positions))
    assert code.count(struct.pack('<f',0.454545))==0
    assert code.count(struct.pack('<f',1/struct.unpack('<f',struct.pack('<f',2.2))[0]))==0
    slots=[]
    for name,listing in [('PS0',ps0),('PS2',ps)]:
        slots.append(dict(pass_name=name,declared_resources=[line for line in listing if line.startswith('dcl_resource')],
                          texture_sample_instructions=[line for line in listing if line.startswith('sample')]))
    result=dict(schema='zerosis.original_water.phase4.optics_contract.v1',
        status='PASS_PINNED_OPTICS_OPERATIONS_WITH_EXPLICIT_RUNTIME_CANDIDATES',checks=checked,
        prior_listings=[ref(PRIOR/name) for name in ['WaterShader_0_vs.asm','WaterShader_0_ps.asm','WaterShader_2_ps.asm']],
        pipeline=ref(pipeline_path),original_exe=dict(path=str(exe),sha256=pipeline['exe']['sha256']),ps2_blob=blob,
        binary_float_literals=constants,resource_inventory=slots,lean_encoding=ref(STAGE/'lean_encoding.json'),
        exact_float_sample_decode=dict(mean='(2*plane0.R-1, 2*plane0.G-1)',second='(plane0.B, plane0.A, 2*plane1.R-1)',
            mirrored_x='Negate mean.x and second.xy; diagonal moments and mean.y unchanged.',
            scale='a=(b.x-b.y+2,-b.x-b.y+2), b=2*WaterBlendMap.RG-1; w=a/sum(a)/S with S=runtime cb1[13].x.',
            mixed_mean='m=w0*m0+w1*m1',
            mixed_second='Mxx=w0^2*M0xx+w1^2*M1xx+2*a.x*b.x; Myy=w0^2*M0yy+w1^2*M1yy+2*a.y*b.y; Mxy=w0^2*M0xy+w1^2*M1xy+a.x*b.y+a.y*b.x, a=w0*m0,b=w1*m1.',
            covariance='C=(Mxx-m.x^2,Myy-m.y^2,Mxy-m.x*m.y). No original PSD clamp is present here.'),
        exact_gaussian=dict(
            half_slope='H=normalize(O+t*(V-O))+L; h=H.xy/H.z-m, where V=normalize(camera-world), O/t from cb1[18] or cb1[19], and L from cb1[14] or cb1[15].',
            regularisation='A=Cxx+d,D=Cyy+d,B=Cxy; d=1/k for narrow and16/k for wide; det=A*D-B^2.',
            q='0.5*(D*hx^2-2*B*hx*hy+A*hy^2)/det',
            value='exp2(-q*float32(1.442695))/sqrt(det); zero for det<=0 or q>=16; wide result timesfloat32(.005). No2*pi or SchlickF0.',
            original_domain='The original computes divisions/sqrt before rejecting invalid lobes; finite early rejection is an explicit implementation safety policy.'),
        exact_reflection=dict(
            projected_uv='P=world transformed by cb1[22..25], retaining clipX/clipY/clipW; uv=(0.5*P.x/P.w-0.5,-0.5*P.y/P.w-0.5).',
            base='base=uv+6*(Cxx,Cyy)',
            tap_offsets='secondary-lobe determinant times[(2,2),(2,-2),(-2,6),(-2,-2)]',
            average='RGBA=(tap0+tap1+tap2+tap3)*0.25 in the recorded add order, then RGB^(original float32 gamma2.2); alpha is not gamma-converted.',
            producer='t4 is ReflectionMap by descriptor-order interpretation; its actual CPU producer/camera/cache dimensions are untraced.'),
        exact_lighting=dict(
            material_vector='N=(m.x,m.y,1), not normalized',
            diffuse='saturate(dot(N,L1))',
            fresnel='f=(1-dot(N,V))^5 via square,square,multiply; neither input dot nor f is clamped, and no F0 term is added.',
            colour_before_shadow='diffuse*(DepthColour+f*(G1*colour1+G2*colour2))+Gwide*DepthColour*colour1+reflectionLinear*cb1[36].x+saturate(4*h)*q2^3*DepthColour',
            shadow='Multiply RGB by1-.67*saturate(t13.R)*cb1[34].x after the projective shadow sample.',
            encode='RGB^(float32 from bits0x3ee8ba2f) before overlay/FOW/distance fog; not the truncated literal0.454545f.'),
        alpha_depth_fow_clip=dict(
            depth='h=t7.A; depthU=1-saturate(4*h); t6(depthU,0), LOD0.',
            alpha_ps0='saturate(DepthColour.A)',alpha_ps2='saturate(DepthColour.A*(1+reflectionAverage.A))',
            clip='Only confirmed pixel discard in PS0/2 is FOW mask R==0; regular hardware plane/terrain depth clipping is a separate runtime state.',
            fow='After premultiplied overlay, lerp(0.4 gray,colour,R), then lerp with t11 LUT by R*(1-B), then original exponential distance fog.',
            refraction='These passes do not establish an independent screen-scene colour/depth refraction pair. A new isolated scene refraction path must be labelled a candidate, not original shader parity.'),
        surface_and_contour=dict(
            water_plane='Water VS0 fixes original Z=cb1[12].x. The runtime value and link to coast text Waterline.Height are untraced.',
            coast_values='Exact coaststyles Height/Offset/Character values and 9 profiles are pinned in phase3/semantics/coast_text_contract.json; original contour extraction/interpolation/application is untraced.',
            z_up='Original (X,Y,Zup) maps to current (X,-Z,Y) before any explicitly chosen world-unit scale. Original N=(mx,my,1) maps to current (mx,1,-my).',
            candidate_height_bridge='Current atlas uses candidate WorldY=(rawHeight-HeightOffsetCandidate)*HeightWorldScaleCandidate; inverse rawHeight=WorldY/scale+offset. Applying coast text heights through it is a candidate.'),
        candidate_boundaries=['RawRGBA16/R16 UNORM views are strongly supported by16-bit linear generation commands and word/covariance diagnostics; original upload-format code remains untraced.',
            'Header outputScale matches original batch arguments. Assigning it to runtime S=cb1[13].x remains a compatibility inference.',
            'Plane height, all matrices/light/warp/k/UV/time/reflection coefficients and reflection producer dimensions remain runtime candidates.',
            'Safe finite rejection of invalid covariance/division/colour-log inputs, near-horizontal epsilon and scene-refraction privacy policies are explicit additions.',
            'Actual GPU depth/ID correctness, visual match, scene reflection/refraction and performance remain pending.'],
        cpu_api=dict(namespace='ZeroSisPresentation::OriginalWaterOptics',header=ref(PROJECT/'Source/Presentation/OriginalWaterOpticsModel.h'),
            asset_adapter='FromScalars(decoded.meanX,decoded.meanY,decoded.secondXX,decoded.secondYY,decoded.secondXY), with asset decode shaderScale=1.',
            functions=['FromScalars','FromArray','NormalizedLayerWeights','WeightsFromBlendRG','MixLayers','GaussianLobe','NormalizeView','WarpedHalfSlope','RetailFresnel','RetailDiffuse','ProjectedReflectionUv','ReflectionUvs','AverageReflectionLinear','EncodeLighting','Validate(CandidateOpticsPolicy)']),
        existing_original_files_modified=False,temporary_asset_or_dxbc_bytes_written=0,
        host_gamecore_clr_hwnd_gpu_audio_or_game_executed=False)
    with (STAGE/'optics_contract.json').open('x',encoding='utf8') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(status=result['status'],instruction_checks=len(checked),literal_groups=len(constants),new_native_executions=0)))


if __name__=='__main__':main()
