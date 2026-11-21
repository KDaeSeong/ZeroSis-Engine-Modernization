"""Final file-only seal after the parent freezes the integrated renderer."""
from pathlib import Path
import argparse,hashlib,json,re,sys
sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[4]
sys.path.insert(0,str(PROJECT/'Tests'))
from original_water_shader import ref,write_new
ROOT=Path(__file__).parent
SHADOW=ROOT.parent/'dynamic_shadow'
SRC=PROJECT/'Source/Presentation'
def sha(text):return hashlib.sha256(text.encode('ascii')).hexdigest()
def lit(path,name='ShaderSource'):
    text=path.read_text('utf8');pattern=r'R"HLSL\((.*?)\)HLSL"'if path.suffix=='.cpp'else re.escape(name)+r'\[\]=R"HLSL\((.*?)\)HLSL"'
    values=re.findall(pattern,text,re.S);assert len(values)==1;return values[0]
def part(text,start,end):
    at=text.index(start);return text[at:text.index(end,at)]
def main():
    cli=argparse.ArgumentParser();cli.add_argument('--renderer-sha256',required=True);args=cli.parse_args()
    assert re.fullmatch(r'[0-9a-f]{64}',args.renderer_sha256)
    source_names=['WorldTerrainRenderer.cpp','WorldTerrainUnits.inc','OriginalDynamicShadowModel.h','OriginalDynamicShadowShader.h','OriginalDynamicShadowGpuTypes.inc','OriginalDynamicShadowGpu.inc',
        'OriginalFogShader.h','OriginalFogGpu.inc','OriginalFogGpuTypes.inc','OriginalWaterSurfaceShader.h','OriginalWaterSurfaceGpu.inc','OriginalWaterSurfaceGpuTypes.inc',
        'OriginalWaterReflection.inc','OriginalWaterSurfaceTargets.inc','OriginalLightingFieldGpu.inc','OriginalTerrainGpu.inc','OriginalTerrainShader.h',
        'OriginalScreenLightingShader.h','OriginalScreenLightingGpu.inc','OriginalScreenLightingGpuTypes.inc','OriginalScreenLightingModel.h','WorldViewRenderer.h']
    before=[ref(SRC/name)for name in source_names];assert before[0]['sha256']==args.renderer_sha256
    root_freeze=ROOT.parent/'root_source_freeze.json';freeze=json.loads(root_freeze.read_text('utf8'))
    for row in freeze['sources']:
        current=ref(row['path']);assert current['sha256']==row['sha256']and current['bytes']==row['bytes']
    owned=json.loads((ROOT/'water_source_seal.json').read_text('utf8'))
    for row in owned['sources']+owned['tests']:assert ref(row['path'])==row
    strict=json.loads((ROOT/'water_shader01/water_result.json').read_text('utf8'))
    literals=dict(fog=lit(SRC/'OriginalFogShader.h'),surface='#define DYNAMIC_SHADOW_SLOT t11\n'+lit(SRC/'OriginalDynamicShadowShader.h','SamplingSource')+lit(SRC/'OriginalWaterSurfaceShader.h'),legacy=lit(SRC/'WorldTerrainRenderer.cpp'))
    hashes={name:sha(value)for name,value in literals.items()};assert hashes==strict['compiled_literal_sha256']
    renderer=(SRC/'WorldTerrainRenderer.cpp').read_text('utf8');review=json.loads((SHADOW/'shadow_independent_review.json').read_text('utf8'))
    for row in review['fixed_production_inputs']:assert ref(row['path'])==row
    stable={
        'main_marker_clear':part(renderer,'if(fogEnabled)cache.context->ClearRenderTargetView(surfaces.waterFragmentView.Get(),zero);','cache.context->ClearDepthStencilView(surfaces.depthView.Get()'),
        'main_surface_units_fog_order':part(renderer,'if(surfaceTargets){\n            CopyWaterRefractionInputs','ID3D11Texture2D* finalColour='),
        'embedded_unit_fallback_hlsl':literals['legacy']}
    for name,text in stable.items():assert sha(text)==review['renderer_stable_region_sha256'][name]
    updated=part(renderer,'const auto unitGroups=PrepareTerrainUnits','const float background[4]')
    assert updated.index('UploadTerrainUnits')<updated.index('DrawDynamicShadow')<updated.index('DrawWaterReflection')
    assert 'if(surfaceTargets)DrawDynamicShadow'in updated and'else cache.dynamicShadow.reset();'in updated
    assert 'const bool standaloneReflection=lightingEnabled&&screenPolicy.specular&&screenPolicy.reflection&&!surfaceTargets;'in updated
    assert 'CreateLightingReflectionTargets(cache,width,height,mapWidth)'in updated
    assert 'if(screenPolicy.reflection)DrawWaterReflection'in updated and'ID3D11ShaderResourceView* clear[45]'in updated
    reflection=(SRC/'OriginalWaterReflection.inc').read_text('utf8');field=(SRC/'OriginalLightingFieldGpu.inc').read_text('utf8');terrain=(SRC/'OriginalTerrainGpu.inc').read_text('utf8')
    assert reflection.count('PSSetShaderResources(0,45,empty)')==2
    assert 'PSSetConstantBuffers(6,1,&noLighting)'in reflection and'PSSetSamplers(5,1,&noLightingSampler)'in reflection
    for required in ('PSGetShaderResources(0,45,rawResources.data())','PSSetShaderResources(0,45,oldResources.data())','PSSetShaderResources(0,45,empty.data())'):assert required in field
    assert 'std::array<ID3D11ShaderResourceView*,45> resources'in terrain and'resources[44]=reflection;'in terrain
    assert 'std::array<ID3D11ShaderResourceView*,45> clear'in terrain and'PSSetConstantBuffers(6,1,&nullBuffer)'in terrain and'PSSetSamplers(5,1,&nullSampler)'in terrain
    assert 'SampleDynamicShadow'not in(SRC/'OriginalTerrainShader.h').read_text('utf8')
    targets=(SRC/'OriginalWaterSurfaceTargets.inc').read_text('utf8')
    screen_model=(SRC/'OriginalScreenLightingModel.h').read_text('utf8')
    assert 'constexpr unsigned OriginalReflectionSide=1024;'in screen_model and'constexpr unsigned OriginalDisabledReflectionSide=32;'in screen_model
    assert 'target.reflectionWidth=target.reflectionHeight=side;'in targets
    assert 'Require(side==OSL::OriginalReflectionSide||side==OSL::OriginalDisabledReflectionSide,'in targets
    assert 'const unsigned reflectionSide=screenPolicy.reflection?OSL::OriginalReflectionSide:OSL::OriginalDisabledReflectionSide;'in renderer
    assert 'activeSurface->targets->reflectionWidth!=reflectionSide'in renderer and'CreateWaterSurfaceTargets(cache,width,height,mapWidth,reflectionSide)'in renderer
    assert 'DXGI_FORMAT_B8G8R8A8_UNORM_SRGB'in targets and'DXGI_FORMAT_B8G8R8A8_UNORM'in targets
    isolated=part(targets,'std::unique_ptr<SurfaceTargets> CreateLightingReflectionTargets','std::unique_ptr<SurfaceTargets> CreateWaterSurfaceTargets')
    assert 'CreateSceneReflectionImages'in isolated and 'CreateTexture2D'not in isolated
    assert before==[ref(SRC/name)for name in source_names]
    water=dict(schema='zerosis.original_water_fog.phase8.final_integrated_source_seal.v1',status='PASS_FINAL_WATER_FOG_SOURCE_SEAL_WITHOUT_RECOMPILE',
        final_sources=before,root_source_freeze=ref(root_freeze),owned_source_seal=ref(ROOT/'water_source_seal.json'),strict_compile=ref(ROOT/'water_shader01/water_result.json'),
        compiled_hlsl_sha256=hashes,compiled_literals_unchanged=True,extra_shader_compile_count=0,
        integration=dict(marker_clear_and_visible_units_unchanged=True,water_fog_once=True,true_plot_id_mrt_preserved=True,
            dynamic_receiver_b5_t11_unchanged=True,reflection_raw_unorm_srv_encoding_unchanged=True,
            screen_lighting_t44_shared_reflection_input=True,reflection_dimensions_enabled1024_disabled32=True,
            new_auxiliary_raw_asset_packages=0,retail_om_blend_verified=False),native_host_gamecore_clr_hwnd_gpu_audio_game_executed=False)
    water_out=ROOT/'water_final_source_reseal.json';write_new(water_out,water)
    shadow=dict(schema='zerosis.original_dynamic_shadow.phase8.final_integrated_source_seal.v1',status='PASS_FINAL_SHADOW_SOURCE_REVIEW_RESEALED',
        original_review=ref(SHADOW/'shadow_independent_review.json'),root_source_freeze=ref(root_freeze),final_sources=before,renderer_final_sha256=args.renderer_sha256,
        fixed_dynamic_sources_unchanged=True,unchanged_renderer_region_sha256={name:sha(value)for name,value in stable.items()},
        updated_renderer_region=dict(name='unit_upload_shadow_reflection_order',previous_sha256=review['renderer_stable_region_sha256']['unit_upload_shadow_reflection_order'],current_sha256=sha(updated),
            changes=['Dynamic producer now runs only when actual water surface targets exist; otherwise its private16MiB map is released.',
                'Optional1024x1024 screen-only reflection colour/depth reuses the same producer, without full-frame refraction copies.',
                'Reflection-disabled policy clears its shared colour/depth to black/one rather than sampling a previous frame.']),
        additional_review=['Main ground resources/cleanup cover0..44; t43 remains unused and dynamic shadow is not arbitrarily merged into terrain macro-shadow.',
            'Reflection entry/RAII and field bake save/restore/clear now cover45 PS slots, including t44; b6/s5 are detached by reflection/ground cleanup.',
            'Original four dynamic source files and six compiled water/fog/legacy entry points did not change; earlier controlled tests remain paired with exact source bytes.'],
        scope='The final screen-lighting equations/retail binding are reviewed separately by their owner/contract reviewer; this reseal checks their resource/lifetime interaction with water and dynamic shadows.',
        no_blocking_defect_found=True,retail_hardware_blend_verified=False,actual_gpu_parity_verified=False,native_host_gamecore_clr_hwnd_gpu_audio_game_executed=False)
    shadow_out=SHADOW/'shadow_final_source_reseal.json';write_new(shadow_out,shadow)
    print(json.dumps(dict(water=ref(water_out),shadow=ref(shadow_out))))

if __name__=='__main__':main()
