"""Read-only review of the shared candidate Raw producer/Water consumer wiring."""
from pathlib import Path
import argparse
import gzip
import hashlib
import importlib.util
import json
import re
import sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).absolute().parent
PROJECT=ROOT.parents[3]
READER=PROJECT/'evidence/world_terrain_original/phase10/reflection/water_pe_view.py'
spec=importlib.util.spec_from_file_location('reflection_review_reader',READER)
reader=importlib.util.module_from_spec(spec);spec.loader.exec_module(reader)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--name',default='reflection_root_integration_review');args=parser.parse_args()
    assert re.fullmatch('reflection_root_integration_review(?:_[0-9]+)?',args.name)
    output=ROOT/(args.name+'.json');assert not output.exists()
    names=['OriginalWaterReflection.inc','OriginalWaterSurfaceGpuTypes.inc','OriginalWaterSurfaceGpu.inc','OriginalWaterSurfaceShader.h','WorldTerrainRenderer.cpp']
    files={name:PROJECT/'Source/Presentation'/name for name in names}
    inputs={name:reader.ref(path) for name,path in files.items()}
    source={name:path.read_text('utf8') for name,path in files.items()}
    reflection,types,gpu,shader,renderer=(source[name] for name in names)
    checks=[]
    def check(name,value,file=None,anchor=None,detail=None):
        assert value,name
        row=dict(name=name,passed=True)
        if file:
            row['file']=str(files[file])
            if anchor:
                start=source[file].index(anchor);row['line']=source[file].count('\n',0,start)+1;row['anchor']=anchor
        if detail:row['detail']=detail
        checks.append(row)
    check('producer_stores_the_exact_uploaded_matrix',
        'targets.reflectionViewProjection=reflectedConstants;targets.reflectionProjectionValid=true;' in reflection and
        'cache.context->UpdateSubresource(cache.constants.Get(),0,nullptr,&reflectedConstants,0,0);' in reflection,
        names[0],'targets.reflectionViewProjection=reflectedConstants')
    check('existing_candidate_mirror_camera_remains_explicit',
        'XMMatrixReflect(XMVectorSet(0,1,0,-planeY))*mainVP' in reflection and 'candidate camera' in reflection,
        names[0],'const XMMATRIX mirrorVP',detail='No original bounds/axis provider has been activated.')
    check('candidate_water_plane_is_not_relabelled_as_original',
        'WB::WorldPlaneCandidate' in renderer and 'const float reflectionClip[4]={planeY,1,0,0};' in reflection,
        names[0],'const float reflectionClip')
    check('new_original_input_model_not_activated_in_shared_production',
        not any('OriginalReflectionProjection::Build' in text or 'OriginalReflectionProjectionModel.h' in text for text in source.values()))
    check('new_targets_start_invalid','bool reflectionProjectionValid=false;' in types,names[1],'bool reflectionProjectionValid=false;')
    check('disabled_reflection_invalidates_before_clearing',
        renderer.index('reflectionTargets->reflectionProjectionValid=false;')<renderer.index('ClearRenderTargetView(reflectionTargets->reflectionRawView.Get(),black)'),
        names[4],'reflectionTargets->reflectionProjectionValid=false;')
    check('cpu_to_shader_same_projector_and_valid_bit',
        'constants.reflectionViewProjection=targets.reflectionViewProjection;' in gpu and 'constants.motion[3]=targets.reflectionProjectionValid?1.0f:0.0f;' in gpu,
        names[2],'constants.reflectionViewProjection=targets.reflectionViewProjection;')
    check('constant_layout_368_bytes_preserved',
        'static_assert(sizeof(WaterSurfaceConstants)==368' in types and 'XMFLOAT4X4 reflectionViewProjection;' in types,
        names[1],'static_assert(sizeof(WaterSurfaceConstants)==368')
    check('row_major_matrix_in_b1_offset_zero',
        re.search(r'cbuffer Surface:register\(b1\)\{\s*row_major float4x4 reflectionViewProjection;',shader) is not None,
        names[3],'row_major float4x4 reflectionViewProjection;')
    check('project_the_same_centered_water_world_position',
        'p.local=v.p+float3(placement.x,0,placement.y);' in shader and 'p.reflection=mul(float4(p.local,1),reflectionViewProjection);' in shader,
        names[3],'p.reflection=mul(float4(p.local,1),reflectionViewProjection);')
    check('float4_projected_position_interpolated',
        'float4 reflection:TEXCOORD6;' in shader and 'nointerpolation float4 reflection' not in shader,
        names[3],'float4 reflection:TEXCOORD6;')
    check('dedicated_projector_divided_by_w_with_original_uv',
        'projected.xy/projected.w*float2(0.5,-0.5)-0.5+6*covariance.xy' in shader and
        'Reflection(p.reflection,covariance,det1,coverage)' in shader and 'p.p.xy/viewport.xy' not in shader,
        names[3],'float2 base=projected.xy/projected.w')
    guard='if(det1>0&&motion.w>0.5&&all(isfinite(p.reflection))&&abs(p.reflection.w)>0.00000001)'
    check('disabled_nonfinite_and_near_zero_w_denied_before_raw_sample',
        guard in shader and shader.index(guard)<shader.index('reflected=Reflection(p.reflection'),
        names[3],guard,detail='Finite safety policy; arbitrary finite-overflow domains are not native-render verified.')
    function=shader[shader.index('float3 Reflection('):shader.index('float WaterDistanceFactor(')]
    check('raw_four_taps_wrap_encoded_average_then_gamma',
        function.count('ReflectionCache.Sample(WrapSampler,')==4 and 'coverage=saturate(r.a);return pow(max(r.rgb,0),2.2);' in function,
        names[3],'float3 Reflection(')
    check('raw_has_no_terrain_or_forest_fallback',
        'DrawTerrainUnits(cache,unitGroups)' in reflection and 'DrawOriginalGround(' not in reflection and 'DrawForest' not in reflection,
        names[0],'const auto scenes=OriginalReflection::MakePlan')
    check('reflection_pass_has_no_main_pick_target',
        'OMSetRenderTargets(1,&colour,targets.reflectionDepthView.Get())' in reflection and 'idView' not in reflection,
        names[0],'cache.context->OMSetRenderTargets(1,&colour')
    before=json.loads((ROOT.parent/'source_before.json').read_text('utf8'))
    row=next(row for row in before['backups'] if Path(row['source']['path'])==files[names[3]])
    backup=Path(row['backup']['path']);assert reader.ref(backup)['sha256']==row['backup']['sha256']
    previous_raw=gzip.decompress(backup.read_bytes());assert hashlib.sha256(previous_raw).hexdigest()==row['source']['sha256']
    previous=previous_raw.decode('utf8')
    start='O pixelMain(P p){';stop='    float2 retail='
    check('exact_tile_pick_and_unexplored_discard_unchanged_from_baseline',
        shader[shader.index(start):shader.index(stop)]==previous[previous.index(start):previous.index(stop)] and
        'uint pick:SV_Target1;' in shader and 'o.pick=state.x;' in shader,
        names[3],'O pixelMain(P p){',detail='The entire pixel entry through foam and integer pick is byte-equivalent after newline normalization.')
    check('main_pick_target_remains_r32_uint','td.Format=DXGI_FORMAT_R32_UINT;' in renderer,names[4],'td.Format=DXGI_FORMAT_R32_UINT;')
    compilation=ROOT.parent/'water_shader02/result.json';compiled=json.loads(compilation.read_text('utf8'))
    assert compiled['status']=='PASS_SHARED_RAW_PROJECTOR_WATER_SM5_COMPILE_ONLY'
    assert compiled['constant_buffer_bytes']==368 and compiled['independent_homogeneous_wrap_checks']==180
    assert not compiled['original_bounds_axis_projector_production_enabled'] and not compiled['native_host_sdk_clr_hwnd_gpu_audio_or_game_executed']
    for item in compiled['inputs']:
        path=Path(item['path'])
        assert reader.ref(path)==item,'Root source changed since the shader compile: '+str(path)
    for item in compiled['checks']:assert item['passed']
    for item in compiled['compiled']:
        assert item['returncode']==0 and item['warnings']==0 and '/Ges' in item['command'] and '/WX' in item['command']
        assembly=Path(item['assembly']['path']);assert reader.ref(assembly)==item['assembly']
        listing=assembly.read_text('utf-8-sig')
        assert 'row_major float4x4 reflectionViewProjection;' in listing and 'Offset:    0 Size:    64' in listing
        assert re.search(r'waterOverlay;\s*// Offset:\s*352 Size:\s*16',listing)
        if item['profile']=='ps_5_0':assert re.search(r'// SV_Target\s+1\s+x\s+1\s+TARGET\s+uint\s+x',listing)
    check('root_shader_sm5_ges_wx_and_input_hash_closure',True,detail='VS/PS, RDEF size368/projector offset0/uint pick and 180 homogeneous wrap cases verified against retained compile receipts.')
    cleanup=ROOT.parent/'water_shader02/cleanup.json';cleanup_data=json.loads(cleanup.read_text('utf8'))
    assert cleanup_data['status']=='PASS_EXACT_OWNED_SHADER_TEMP_CLEANUP'
    for item in cleanup_data['files']:assert item['deleted'] and not Path(item['before']['path']).exists()
    check('root_shader_intermediates_absent_with_receipt',True)
    assert {name:reader.ref(path) for name,path in files.items()}==inputs
    result=dict(schema='zerosis.phase12.reflection_root_integration_review.v1',
        status='PASS_CANDIDATE_RAW_WATER_SHARED_PROJECTOR_STATIC_REVIEW_ORIGINAL_INPUTS_DISABLED',
        reviewer=reader.ref(Path(__file__).absolute()),inputs=inputs,checks=checks,findings=[],
        root_shader_compile=reader.ref(compilation),root_shader_cleanup=reader.ref(cleanup),
        original_projection_contract=reader.ref(ROOT/'reflection_projection_contract.json'),
        cpu_component_checks=reader.ref(ROOT/'reflection_components02/reflection_result.json'),
        picking_baseline_backup=reader.ref(backup),
        distinction=dict(production='Candidate mirror-main-VP is now shared exactly by Raw draw and Water consumer.',
            confirmed_original='Dedicated orthographic projector operation and WaterPS UV formula are statically recovered.',
            production_original_projector_enabled=False,
            unresolved=['actual original frame bounds/axis/current-to-original units provider','original water-plane clipping',
                        'full scene callbacks beyond currently supported visible units','D3DX bitwise and indexed-view parity',
                        'native image acceptance remains held']),
        native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False)
    with output.open('x',encoding='utf8') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(status=result['status'],checks=len(checks),output=reader.ref(output))))


if __name__=='__main__':main()
