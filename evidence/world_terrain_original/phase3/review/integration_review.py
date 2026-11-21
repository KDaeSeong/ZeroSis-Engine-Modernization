"""Read-only integration review of the current water/shore/river candidate."""
from __future__ import annotations
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[3]
PHASE = STAGE.parent
spec = importlib.util.spec_from_file_location('water_integration_storage', PROJECT/'tools/audit_exit_host_storage.py')
storage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(storage)


def ref(path):
    path=Path(path).absolute()
    before=storage.ordinary(path)
    sha=storage.digest(path)
    after=storage.ordinary(path)
    assert storage.metadata(before)==storage.metadata(after)
    return dict(path=str(path),**storage.metadata(after),sha256=sha)


def body(text,signature):
    begin=text.index('{',text.index(signature));depth=1;end=begin+1
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[begin+1:end-1]


def normal(text):
    return '\n'.join(line.strip() for line in text.splitlines() if line.strip())


def main():
    names=['Source/Presentation/OriginalWaterBinding.h','Source/Presentation/OriginalWaterShader.h',
           'Source/Presentation/OriginalWaterGpuTypes.inc','Source/Presentation/OriginalWaterGpu.inc',
           'Source/Presentation/OriginalWaterBridge.h','Source/Presentation/OriginalWaterModel.h',
           'Source/Presentation/OriginalWaterState.h','Source/Presentation/OriginalWaterPackage.h',
           'Source/Presentation/WorldTerrainRenderer.cpp','Source/Presentation/WorldViewRenderer.h',
           'Source/Presentation/WorldTerrainReuse.h','Source/Presentation/OriginalTerrainGpu.inc',
           'Source/Host/WorldViewState.h','Source/Host/InteractiveGameLoop.h']
    pins=[ref(PROJECT/name) for name in names]
    texts={name:(PROJECT/name).read_text('utf8') for name in names}
    binding,shader,types,gpu,bridge,model,state,package,renderer,dto,reuse,terrain,host,loop=[texts[name] for name in names]
    expected={'OriginalWaterModel.h':'75552fe2a8002772795c0fa6d14c396ee566615e826b4d627815bfc7b6b59ba4',
              'OriginalWaterState.h':'1c064d632cc056f1de81204dbaaf000061ef5067c5cbb04abf3157e6eca8c6ee',
              'OriginalWaterPackage.h':'45999ed0d3546565920f3d03922307b16217e9fd42a6e79a884257c66cfdb230'}
    assert all(row['sha256']==expected[Path(row['path']).name] for row in pins if Path(row['path']).name in expected)
    completed=json.loads((PHASE/'assets/completion.json').read_text('utf8'))
    compiled_sha=re.search(r'PackageSha256="([0-9a-f]{64})"',binding)[1]
    package_ref=ref(completed['package']['path'])
    assert package_ref['sha256']==completed['package']['sha256']==compiled_sha
    strict_path=PHASE/'shader/attempt03/result.json'
    strict=json.loads(strict_path.read_text('utf8'))
    assert strict['status']=='PASS_STRICT_WATER_OVERLAY_COLOUR_ONLY_ABI'
    assert all(ref(row['path'])['sha256']==row['sha256'] for row in strict['inputs'])
    source_before=json.loads((PHASE/'source_before.json').read_text('utf8'))
    prior_loop=next(row for row in source_before['backups'] if Path(row['source']['path'])==PROJECT/names[-1])
    prior_text=gzip.decompress(Path(prior_loop['backup']['path']).read_bytes()).decode('utf8').replace('\r\n','\n')
    old_refresh=body(prior_text,'const auto refreshAnimation=')
    new_refresh=body(loop,'const auto refreshAnimation=')
    without_water=re.sub(r'\s*if\(waterAnimation\)retainedView\.waterAnimationSeconds=seconds;','',new_refresh)
    revealed=body(host,'if(value.revealed)')
    hidden_prefix=state[:state.index('if(!plot.revealed)continue;')]
    hidden_prefix=re.sub(r'//[^\n]*','',hidden_prefix)
    same=body(state,'inline bool SameWaterGrid(')
    draw=body(gpu,'void DrawOriginalWater(')
    render=body(renderer,'bool RenderWorldTerrainImpl(')
    checks={
        'compiled_package_whole_sha_matches_actual':package_ref['sha256']==compiled_sha,
        'package_canonical_25_roles':'u32()==25' in package and 'role<=14' in package,
        'gpu_uploads_14_dds_in_role_order':'std::array<ComPtr<ID3D11ShaderResourceView>,14> textures;' in types and 'static_cast<OW::AssetRole>(i+1)' in gpu,
        'package_sha_validated_before_gpu_upload':'OW::DecodePackage(std::move(input.data),OW::PackageSha256)' in gpu,
        'dds_mip_offsets_row_pitches_used':'package.bytes.data()+level.offset,static_cast<UINT>(level.rowPitch)' in gpu,
        'styles13_profiles9_parser_required':'result.styles.size()==13 && result.profiles.size()==9' in package,
        'unused_raw_lean_excluded':type(completed['included_lean_raw_assets']) is int and completed['included_lean_raw_assets']==0,
        'terrain_and_fog_packages_not_copied':completed['terrain_and_fog_package_copies']==0,
        'sdk_river_getters_only_revealed':all(host.count('plot->'+name+'(')==revealed.count('plot->'+name+'(')==1 for name in
            ['IsWOfRiver','IsNWOfRiver','IsNEOfRiver','GetRiverEFlowDirection','GetRiverSEFlowDirection','GetRiverSWFlowDirection']),
        'flow_e_only_if_present':'if(value.riverW)value.flowE=static_cast<int>(plot->GetRiverEFlowDirection());' in revealed,
        'flow_se_only_if_present':'if(value.riverNW)value.flowSE=static_cast<int>(plot->GetRiverSEFlowDirection());' in revealed,
        'flow_sw_only_if_present':'if(value.riverNE)value.flowSW=static_cast<int>(plot->GetRiverSWFlowDirection());' in revealed,
        'host_flow_domains_sdk_exact':all(part in revealed for part in ['value.flowE!=0&&value.flowE!=3','value.flowSE!=1&&value.flowSE!=4','value.flowSW!=2&&value.flowSW!=5']),
        'unknown_fields_not_read_by_water_capture':re.search(r'plot\.(?:water|lake|hills|mountain|terrainId|riverW|riverNW|riverNE|flowE|flowSE|flowSW)\b',hidden_prefix) is None,
        'capture_canonical_edge_mapping':'cell.river={{plot.riverW,plot.riverNW,plot.riverNE}};' in state,
        'unknown_key_cells_skip_all_payloads':'if(!x.revealed)continue;' in same and same.index('if(!x.revealed)continue;')<same.index('Detail::ValidCell(x)'),
        'topology_requires_both_explored':'if(!cell.revealed)continue;' in model and 'if(!next.revealed)continue;' in model,
        'water_state_has_no_clock_camera_or_visible_payload':not any(name in same for name in ['animationSeconds','AnimationSeconds','cameraX','cameraY','visible','tileWidth']),
        'dto_tail_copy_maps_all_new_fields':'plot.lake,plot.riverW,plot.riverNW,plot.riverNE,plot.flowE,plot.flowSE,plot.flowSW' in loop,
        'lake_remains_false_without_private_sdk_query':'bool lake=false;' in host and 'bool lake=false;' in dto and re.search(r'(?:->|\.)[Ii]sLake\s*\(',host+loop) is None,
        'one_colour_rt_bound':'OMSetRenderTargets(1,&target,surfaces.depthView.Get())' in draw,
        'depth_reads_only':'DepthWriteMask=D3D11_DEPTH_WRITE_MASK_ZERO' in gpu and 'DepthFunc=D3D11_COMPARISON_LESS_EQUAL' in gpu,
        'rgb_only_write_mask':'D3D11_COLOR_WRITE_ENABLE_RED|D3D11_COLOR_WRITE_ENABLE_GREEN|D3D11_COLOR_WRITE_ENABLE_BLUE' in gpu,
        'target_alpha_preserved':'target.SrcBlendAlpha=D3D11_BLEND_ZERO;target.DestBlendAlpha=D3D11_BLEND_ONE;' in gpu,
        '15_srvs_unbound':'PSSetShaderResources(0,15,empty)' in draw,
        '2_samplers_unbound':'PSSetSamplers(0,2,noSamplers)' in draw,
        'owned_cb1_unbound_both_stages':'VSSetConstantBuffers(1,1,&nullBuffer)' in draw and 'PSSetConstantBuffers(1,1,&nullBuffer)' in draw,
        'normal_depth_blend_restored':'OMSetDepthStencilState(cache.depthState.Get(),0)' in draw and 'OMSetBlendState(cache.blendState.Get(),nullptr,0xffffffffu)' in draw,
        'normal_shader_layout_sampler_restored':all(part in draw for part in ['IASetInputLayout(cache.layout.Get())','VSSetShader(cache.vs.Get()','PSSetShader(cache.ps.Get()','PSSetSamplers(0,1,&sampler)']),
        'stage_order_ground_water_units_fow':render.index('DrawOriginalGround(view')<render.index('DrawOriginalWater(view')<render.index('if(!view.unitAssetsPath.empty()){')<render.index('DrawOriginalFog(view'),
        'global_material_order_water_coast_river':'for(unsigned kind=0;kind<3;++kind)for(const auto& draw:ground.draws)' in draw,
        'owner_material_ranges_partitioned':'std::vector<std::array<OW::DrawRange,3>> ranges;' in types and 'part.count%3==0' in gpu,
        'one_owned_cache_and_weak_atlas':'std::unique_ptr<WaterCatalog> water;' in renderer and 'std::unique_ptr<WaterGeometry> geometry;' in types and 'std::weak_ptr<OriginalSurface> surface;' in types,
        'geometry_reuses_canonical_grid_and_atlas_identity':'OW::SameWaterGrid(activeWater->geometry->key,waterGrid)' in render and 'activeWater->geometry->surface.lock()!=groundData->original->surface' in render,
        'camera_changes_reuse_terrain_surface':'OT::SameTerrainCells(old->cells,cells))return old;' in terrain,
        'water_clock_only_updates_water_shading':'constants.shade[0]=static_cast<float>(view.waterAnimationSeconds)' in draw and 'view.fogAnimationSeconds' not in draw and 'view.animationSeconds' not in draw,
        '3_clocks_have_independent_flags':all(part in new_refresh for part in ['if(unitAnimation)retainedView.animationSeconds=seconds;','if(fogAnimation)retainedView.fogAnimationSeconds=seconds;','if(waterAnimation)retainedView.waterAnimationSeconds=seconds;']),
        'animation_input_generation_body_unchanged_except_new_clock':normal(without_water)==normal(old_refresh),
        'animation_does_not_call_sdk_rng_or_turns':re.search(r'WithCore|\b(?:rand|srand|AdvanceTurn|Save)\s*\(',new_refresh) is None,
        'time_only_keeps_ground_key':all(name not in reuse for name in ['waterAnimationSeconds','fogAnimationSeconds','animationSeconds']),
        'id_readback_remains_ground_candidate_only':'if(candidate){\n            result.picking.indices.resize' in render,
        'water_published_after_fallible_frame_work':render.index('if(waterGeometryCandidate)activeWater->geometry=')>render.index('if(callerTarget)cache.context->CopyResource') and render.index('if(waterCandidate)cache.water=')>render.index('cache.ground.Publish'),
        'render_owner_release_resets_both_caches':'GpuTerrainCache().reset();LegacyTerrainCache().reset();' in renderer and '~ReleasePresentation(){ReleaseWorldTerrainResources();}' in loop,
        'empty_water_path_keeps_legacy':'const bool waterEnabled=!view.waterAssetsPath.empty();' in render and 'Require(!waterEnabled||cache.original' in render and 'if(waterEnabled)DrawOriginalWater(' in render,
        'bridge_profiles_validated_before_callback':bridge.index('for(const auto& profile:profiles)')<bridge.index('auto mesh=BuildMesh('),
        'coast_water_weight_from_owner_side':'const double depth=coast?(edge.ownerWater?1-side:side):1;' in model and 'colour=lerp(bank.rgb,foam.rgb,saturate(p.depth));' in shader,
    }
    assert all(checks.values()),[name for name,passed in checks.items() if not passed]

    listing_path=PHASE/'shader/attempt03/pixel.asm'
    listing=listing_path.read_text('utf8')
    input_signature=listing.split('Input signature:')[1].split('Output signature:')[0]
    depth=re.search(r'^// TEXCOORD\s+2\s+([xyzw])\s+(\d+)\s+NONE\s+float',input_signature,re.M)
    assert depth
    depth_register='v'+depth[2]+'.'+depth[1]
    lines=[line.strip() for line in listing.splitlines() if line.strip() and not line.startswith('//')]
    expected_coast=[
        'sample_indexable(texture2d)(float,float,float,float) r3.xyzw, r2.xyxx, t7.xyzw, s0',
        'mov_sat r1.w, '+depth_register,
        'add r2.xzw, -r1.xxyz, r3.xxyz',
        'mad r2.xzw, r1.wwww, r2.xxzw, r1.xxyz']
    assert any(lines[start:start+4]==expected_coast for start in range(len(lines)-3))
    coast_cases=[]
    for owner_water in [False,True]:
        for side in [0,0.25,0.5,0.75,1]:
            weight=1-side if owner_water else side
            coast_cases.append(dict(owner_water=owner_water,side=side,foam_weight=weight,bank_weight=1-weight))
    assert coast_cases[0]['foam_weight']==0 and coast_cases[4]['foam_weight']==1
    assert coast_cases[5]['foam_weight']==1 and coast_cases[9]['foam_weight']==0
    coast_proof=dict(status='PASS_COMPILED_COAST_USES_OWNER_INDEPENDENT_WATER_WEIGHT',listing=ref(listing_path),
        input_semantic='TEXCOORD2',input_register=depth_register,checked_sequence=expected_coast,
        interpretation='CoastWave t7 RGB minus mixed bank RGB, multiplied by saturate(TEXCOORD2 depth), then added to bank RGB.',
        owner_side_arithmetic_cases=coast_cases,gpu_executed=False)
    with (STAGE/'coast_direction_bytecode.json').open('x',encoding='utf8') as stream:
        json.dump(coast_proof,stream,indent=2);stream.write('\n')
    assert [ref(row['path']) for row in pins]==pins
    result=dict(schema='zerosis.original_water.phase3.integration_review.v1',
        status='PASS_READ_ONLY_WATER_COAST_RIVER_INTEGRATION_REVIEW',source_checks=checks,
        sources_before=pins,sources_after=pins,package=package_ref,
        package_completion=ref(PHASE/'assets/completion.json'),strict_shader=ref(strict_path),
        coast_direction_bytecode=ref(STAGE/'coast_direction_bytecode.json'),
        prior_loop_backup=prior_loop,animation_body_comparison='Exact normalised body comparison after removing only the new independent water-clock assignment.',
        findings=[],blocking_findings=0,
        reviewed_contracts=[
            'Canonical E/SE/SW river fields and valid flow domains are captured only for explored plots and only when the representative edge exists.',
            'Both plots must be explored before a physical coast/river edge is created; hidden payload numbers are neither read nor validated.',
            'Model geometry follows the sanitised atlas with known-centre fallback for unknown-adjacent vertices. Shader exact integer ownership discards unknown fragments before any asset sample.',
            'Water overlay binds only colour target0, keeps depth read-only and writes RGB only. Ground integer IDs, stored depth and alpha are unaffected by the overlay configuration.',
            'All water surfaces draw before every coast and river range. Per-owner material ranges remain bounded triangle lists.',
            'All15 water SRVs, both samplers and owned VS/PS b1 are unbound; base shaders/layout/sampler and ordinary depth/blend are restored before units. Shared VS b0 remains the terrain/unit camera.',
            'Water geometry has a canonical static grid key and weak atlas identity. Camera/visibility changes reuse it when the terrain surface is unchanged; three presentation clocks are independent of SDK turn/RNG and cached IDs.',
            'Only completed frame candidates are published. Current/candidate resource owners are bounded and render-owner release resets both existing Cache entries.',
            'No new SDK lake query or ABI/save/schema change is introduced. Empty water path leaves the previous V1/V2 path available.'
        ],
        limits=[
            'This review checks code, exact bytes and existing offline shader output. It does not execute Host, GameCore, CLR, HWND, GPU, sound or a game.',
            'Live raster ID equality, depth/occlusion, actual COM release timing, visual seam behaviour and performance remain pending.',
            'The overlay is a candidate atlas-following colour pass, not the original fixed water plane or full LEAN/reflection renderer. Width, meander, height/UV/time/alpha/lighting calibrations remain explicit candidates.',
            'CoastProfileY is an internal helper for trusted parser output; BuildAtlasMesh validates full profile shape before calling it. No extra direct malformed-helper contract is claimed.',
            'C++ bridge execution and full Host compile/link are separate root/asset-agent gates.'
        ],
        source_or_game_files_modified=False,host_gamecore_clr_hwnd_gpu_audio_or_game_executed=False,
        placement_report='규칙 동등, 배치 동등은 미검증')
    with (STAGE/'integration_review.json').open('x',encoding='utf8') as stream:
        json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(status=result['status'],source_checks=len(checks),source_files=len(pins),
                         blocking_findings=0,compiled_coast_direction_cases=len(coast_cases))))


if __name__=='__main__':
    main()
