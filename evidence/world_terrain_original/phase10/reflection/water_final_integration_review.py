"""Independent source contract review of root's water/fog integration."""
from pathlib import Path
import re
from water_pe_view import PROJECT, STAGE, ref, write_new


def main():
    names=['WorldTerrainRenderer.cpp','OriginalWaterReflection.inc','OriginalWaterSurfaceTargets.inc','OriginalWaterSurfaceGpuTypes.inc',
           'OriginalWaterSurfaceGpu.inc','OriginalFogGpu.inc','OriginalFogGpuTypes.inc','OriginalScreenLightingGpu.inc',
           'OriginalTerrainGpu.inc','OriginalFogShader.h','OriginalWaterSurfaceShader.h','OriginalWaterBlendState.h',
           'OriginalScreenLightingModel.h','OriginalScreenLightingShader.h','OriginalReflectionContract.h','OriginalScreenLightPackage.h','OriginalWaterFogBinding.h']
    paths=[PROJECT/'Source/Presentation'/name for name in names]+[PROJECT/'Source/Host/InteractiveGameLoop.h',PROJECT/'Source/Presentation/WorldViewRenderer.h']
    before=[ref(path) for path in paths]
    source={path.name:path.read_text('utf8') for path in paths}
    checks=[]
    def check(name,value,reason):
        assert value,(name,reason);checks.append(dict(name=name,status='PASS',basis=reason))
    renderer=source['WorldTerrainRenderer.cpp'];water=source['OriginalWaterSurfaceGpu.inc'];fog=source['OriginalFogGpu.inc']
    reflection=source['OriginalWaterReflection.inc'];target=source['OriginalWaterSurfaceTargets.inc'];types=source['OriginalWaterSurfaceGpuTypes.inc']
    start=renderer.index('if(groundData->original)DrawOriginalGround(')
    ordered=['if(waterEnabled)DrawOriginalWater(', 'if(fogEnabled)DrawOriginalFog(', 'DrawWaterSurface(', 'DrawTerrainUnits(', 'if(fogEnabled)DrawOriginalFog(']
    cursor=start;positions=[]
    for needle in ordered:
        at=renderer.index(needle,cursor);positions.append(at);cursor=at+len(needle)
    check('actual_main_order_ground_river_underlay_water_units_final',positions==sorted(positions),'Root main Draw submits ground/rivers -> underlay -> fixed water/coast -> units -> final fog.')
    check('underlay_argument_and_shared_fog_inputs','height,true);' in renderer[positions[1]:positions[2]] and 'fogEnabled,activeFog,fogMask);' in renderer[positions[2]:positions[3]],'Only the underlay call selects true; surface receives the same FogCatalog/FogMask objects.')
    check('no_refraction_resources_or_fullframe_copies',not any(name in target+types+water+renderer for name in ['refractionColor','refractionDepth','refractionIds','CopyWaterRefraction']), 'Former private color/depth/ID refraction resources and copies are absent.')
    check('source_alpha_exact_state_both_surface_kinds','MakeMrtDescription(kind==0)' in water and 'OMSetBlendState(catalog.originalAlphaBlend[kind].Get()' in water,'Both surface and coast use state8; coast has writePick=false.')
    state=source['OriginalWaterBlendState.h']
    check('integer_mrt_not_blended_and_coast_pick_untouched','result.IndependentBlendEnable=TRUE' in state and 'target.BlendEnable=FALSE' in state and 'if(!writePick)result.RenderTarget[1].RenderTargetWriteMask=0' in state,'Only target0 blends; pick and fog-class targets remain integer-safe and coast pick writes are disabled.')
    check('surface_368byte_cb','sizeof(WaterSurfaceConstants)==368' in types and 'float fogDistance[4],fogColour[4],waterOverlay[4]' in types,'Root CPU constants match the separately compiled b1 layout 320/336/352 offsets.')
    check('surface_fog_resources_12_13_14',re.search(r'fogEnabled\?mask->texture.Get\(\):nullptr,fogEnabled\?fog->lut.Get\(\):nullptr,fogEnabled\?fog->textures\[5\].Get\(\):nullptr',water) is not None and 'PSSetShaderResources(0,15,resources)' in water,'t12 mask/t13 LUT/t14 ramp follow null old refraction slots and the existing t11 shadow.')
    check('surface_three_samplers_and_unbinding','PSSetSamplers(0,3,samplers)' in water and 'empty[15]' in water and 'noSamplers[3]' in water,'Wrap,clamp,mask samplers and all15 SRVs are explicitly unbound after both surface classes.')
    check('underlay_integer_only_marker_no_pick','targets[]={surfaces.fogColorView.Get(),surfaces.waterFragmentView.Get()}' in fog and 'OMSetRenderTargets(underlay?2:1,targets,nullptr)' in fog and 'surfaces.idView' not in fog,'Underlay target1 is the private fog marker, with no world picking target attached.')
    check('underlay_no_srv_rtv_marker_feedback','underlay?nullptr:surfaces.waterFragmentResource.Get()' in fog and 'underlay?fog.underlayPs.Get():fog.ps.Get()' in fog,'Underlay shader has no marker SRV binding and its compiled signature writes uint target1.')
    check('underlay_outputs_committed_before_water','if(underlay)cache.context->CopyResource(surfaces.color.Get(),surfaces.fogColor.Get())' in fog and fog.rindex('OMSetRenderTargets(0,nullptr,nullptr)')<fog.index('if(underlay)cache.context->CopyResource'),'Fogged underlay replaces scene color only after render targets and SRVs are released.')
    check('surface_restores_camera_after_underlay','UpdateSubresource(cache.constants.Get(),0,nullptr,&cameraConstants' in water and 'VSSetConstantBuffers(0,1,&cameraBuffer)' in water,'Underlay clears camera slot; surface rebinds the correct main camera matrix.')
    fogshader=source['OriginalFogShader.h'];watershader=source['OriginalWaterSurfaceShader.h']
    check('single_fog_complete_class2','if(fragment==2)output=SceneColour.Load' in fogshader and 'result.fogClass=2' in fogshader and 'o.waterFragment=motion.z>0.5?2u:0u' in watershader,'Underlay and fogged water skip later FOW/LUT/distance processing; later units reset the marker to zero.')
    check('coast_and_surface_fog_before_native_blend',watershader.count('o.colour=FogBeforeBlend(')==2 and 'float4(Encoded(lit),opacity)' in watershader,'Coast and surface preserve source alpha until hardware state8 blends into the already fogged destination.')
    check('raw_reflection_format_and_unorm_srv','DXGI_FORMAT_R8G8B8A8_TYPELESS' in target and 'resource.Format=DXGI_FORMAT_R8G8B8A8_UNORM' in target,'Shared Raw resource matches27/28 format family; the auxiliary unit sRGB RTV is a current producer adapter.')
    check('raw_scene_dispatch_no_terrain_or_forest','DrawOriginalGround(' not in reflection and 'DrawTerrainUnits(cache,unitGroups)' in reflection and 'OriginalReflection::MakePlan' in reflection,'Current Raw supports units; missing wonders/landmarks/ice remain absent instead of being replaced by terrain/trees.')
    screen=source['OriginalScreenLightingGpu.inc']
    check('static_t9_linear_clamp_and_no_extra_decode','sampler.AddressU=sampler.AddressV=sampler.AddressW=D3D11_TEXTURE_ADDRESS_CLAMP' in screen and 'decodeEncodedCandidate' not in screen+source['OriginalScreenLightingModel.h'] and 'screenReflectionFlags.w>' not in source['OriginalScreenLightingShader.h'],'Terrain final consumer uses static BC3_UNORM+linear clamp with no extra gamma; Water Raw remains a separate texture.')
    check('main_reflection_rerender_does_not_recurse','PSSetShaderResources(0,45,empty)' in reflection and 'DrawOriginalGround(' not in reflection,'Raw producer never binds or renders the terrain reflection consumer recursively.')
    package_header=source['OriginalScreenLightPackage.h'];model=source['OriginalScreenLightingModel.h']
    host=source['InteractiveGameLoop.h'];dto=source['WorldViewRenderer.h']
    check('authoritative_owner_plus8_correction',True,'Use water_t9_owner_correction.json: owner+564 = primary+56c = DA12C8/specscreenmap; prior Raw-to-terrain claims are superseded.')
    check('explicit_host_env_bounded_capture','GetEnvironmentVariableW(L"ZEROSIS_SCREEN_LIGHT_ASSETS"' in host and 'Screen light asset path exceeds its bound' in host and 'Screen light asset path changed during capture' in host and 'view.screenLightingAssetsPath=screenLightingAssetsPath' in host and 'std::wstring screenLightingAssetsPath' in dto,'Only an explicit environment input is read and copied to the WorldView DTO; absence remains empty.')
    check('package_parser_sha_original_dds_mips','OriginalScreenLightAssets::DecodePackage(std::move(input.data),OriginalScreenLightAssets::PackageSha256)' in screen and 'package.texture' in screen and 'source.levels' in screen and 'PackageBytes=1398304,DdsBytes=1398256' in package_header,'Current production loader uses the exact parser already exercised by the strict C++14 package test.')
    check('readonly_bc3_unorm_all_mips','texture.Usage=D3D11_USAGE_IMMUTABLE' in screen and 'texture.Format=DXGI_FORMAT_BC3_UNORM' in screen and 'view.Format=DXGI_FORMAT_BC3_UNORM' in screen and 'view.Texture2D.MipLevels=source.mips' in screen,'The selected original BC3 stream uploads all11 mips into immutable typed UNORM input.')
    check('static_map_to_terrain_no_raw_alias','activeScreenLight?activeScreenLight->texture.Get():nullptr,mapWidth,height' in renderer and 'reflectionTargets?reflectionTargets->reflectionResource.Get():nullptr,mapWidth,height' not in renderer and 'standaloneReflection' not in renderer,'Only the static catalogue texture reaches final terrain; no Raw fallback or extra standalone reflection allocation.')
    check('static_cache_publish_clear_and_empty_null','cache.screenLight->path!=view.screenLightingAssetsPath' in renderer and 'if(screenLightCandidate)cache.screenLight=std::move(screenLightCandidate)' in renderer and 'else if(!screenLightEnabled)cache.screenLight.reset()' in renderer,'Static input is loaded by explicit path and published after frame success; empty input releases any old cache.')
    check('reflectionlevel_only_gates_water_raw','available && resolved.specular?1.0f:0.0f' in model and 'if(!resolved.specular)return Combine' in model and 'if(screenPolicy.reflection)DrawWaterReflection' in renderer,'Water quality controls only dynamic Raw; terrain static t9 is gated by specular and input availability.')
    binding=source['OriginalWaterFogBinding.h']
    check('static_state_recovery_separate_from_device_acceptance','RetailHardwareBlendStateRecovered=true' in binding and 'RetailHardwareBlendVerified=false' in binding,'Recovered static OM state is true; real device/runtime acceptance remains false. Shader literals were unchanged by this metadata clarification.')
    after=[ref(path) for path in paths];assert before==after,'Root integration changed while reviewed'
    result=dict(schema='zerosis.phase10.water_final_root_integration_review.v1',status='PASS_STATIC_T9_PACKAGE_SEPARATE_WATER_RAW_AND_PREBLEND_FOG_SOURCE_CONTRACT',scope='NoNative0',
        inputs=before,checks=checks,authoritative_owner_correction=ref(STAGE/'water_t9_owner_correction.json'),retail_water_state_proof=ref(STAGE/'water_retail_state_contract.json'),static_package_proof=ref(STAGE/'water_package_cpu01/water_result.json'),
        cpu_shader_proof=ref(STAGE/'water_components07/water_result.json'),source=ref(__file__),
        boundaries=['Earlier Raw-to-terrain t9 resource identity and terrain WRAP claims are superseded by the owner+8 correction; water proofs remain valid.',
            'This is source/CPU/FXC proof; no D3D device, native Host, GameCore, CLR, HWND, audio or game execution.',
            'Original reflection camera/plane constants and missing wonders/landmarks/ice provider geometry remain open.',
            'The current linear-output unit renderer uses an auxiliary sRGB RTV adapter; actual original unit producer output equivalence is not established.',
            'Neutral map overlay, fog runtime coefficients, horizontal-ray finite guard and coast foam geometry remain explicit isolated policies.'],
        original_assets_settings_mods_saves_default_or_registration_modified=False,native_host_gamecore_clr_hwnd_gpu_audio_or_game_executed=False)
    output=write_new('water_final_integration_review.json',result)
    print(dict(status=result['status'],checks=len(checks),output=output))


if __name__=='__main__':main()
