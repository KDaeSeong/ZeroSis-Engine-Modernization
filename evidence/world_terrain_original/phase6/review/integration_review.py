"""Pin the independent phase-six field, final-specular and render-owner review."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[4]
STAGE = Path(__file__).resolve().parent
NAMES = [
 'OriginalLightingFieldBinding.h', 'OriginalLightingFieldModel.h', 'OriginalLightingFieldBridge.inc',
 'OriginalLightingFieldShader.h', 'OriginalLightingFieldGpuTypes.inc', 'OriginalLightingFieldGpu.inc',
 'OriginalLightingModel.h', 'OriginalLightingBinding.h', 'OriginalLightingState.h', 'OriginalLightingGpu.inc',
 'OriginalLightingGpuTypes.inc', 'OriginalLightingPackage.h', 'OriginalTerrainShader.h', 'OriginalTerrainGpuTypes.inc',
 'OriginalTerrainGpu.inc', 'OriginalTerrainModel.h', 'WorldTerrainRenderer.cpp', 'WorldTerrainReuse.h',
 'WorldViewRenderer.h', 'WorldTerrainUnits.inc', 'OriginalWaterSurfaceShader.h', 'OriginalWaterSurfaceGpuTypes.inc',
 'OriginalWaterSurfaceGpu.inc', 'OriginalWaterSurfaceTargets.inc', 'OriginalWaterReflection.inc',
 'OriginalWaterSurfaceModel.h', 'OriginalWaterGpu.inc', 'OriginalWaterState.h', 'OriginalFogShader.h', 'OriginalFogGpu.inc',
]
PATHS = ['Source/Presentation/'+n for n in NAMES] + ['Source/Host/WorldViewState.h', 'Source/Host/InteractiveGameLoop.h',
 'tools/build_menu_suite_host.py', 'tools/attest_prepared_menu_host.py']


def ref(path):
    path = ROOT/path
    raw, st = path.read_bytes(), path.stat()
    return dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
        file_identity=[st.st_dev, st.st_ino], mtime_ns=st.st_mtime_ns,
        file_attributes=getattr(st, 'st_file_attributes', 0), links=st.st_nlink)


before = {n: ref(n) for n in PATHS}
src = {Path(n).name: (ROOT/n).read_text('utf8') for n in PATHS}
checks = []


def check(name, file, needles, explanation, ordered=False):
    if isinstance(needles, str):
        needles = [needles]
    at, lines = 0, []
    for needle in needles:
        pos = src[file].find(needle, at if ordered else 0)
        assert pos >= 0, (name, needle)
        at = pos+len(needle)
        lines.append(src[file][:pos].count('\n')+1)
    checks.append(dict(name=name, pass_=True, source=file, lines=lines, review=explanation))


check('field-cache-single-owner', 'OriginalTerrainGpuTypes.inc', 'std::unique_ptr<LightingField> lightingField;',
      'Each canonical existing mesh owns one completed normal/shadow field; weak atlas mesh lookup bounds camera retention.')
check('ready-presentation-short-circuit', 'OriginalLightingFieldBridge.inc', ['if(!missing)return;', 'const auto domain=FM::CaptureDomain(view);'],
      'Ready fields avoid all domain recapture, CPU height/ray sampling, allocation and private bake work on presentation-only refresh.', ordered=True)
check('canonical-wrapped-mesh-reuse', 'OriginalLightingFieldBridge.inc', ['auto& mesh=*draw.mesh;if(mesh.slots.count==0||mesh.lightingField)continue;',
      'const FM::TileSpec supportSpec{mesh.column,mesh.row,FB::TileTexels,2};', 'const FM::TileSpec shadowSpec{mesh.column,mesh.row,FB::TileTexels,1};'],
      'Wrapped draw images share the same canonical mesh field. A new atlas yields new mesh owners, while camera/visible-only changes can reuse the same static field.')
check('candidate-before-publication', 'OriginalLightingFieldBridge.inc', ['auto candidate=BuildLightingField(',
      'Require(candidate&&candidate->normal.Get()&&candidate->shadow.Get()', 'mesh.lightingField=std::move(candidate);'],
      'Every field has both resources before ownership is published; existing fields are never moved from during failed preparation.', ordered=True)
check('confirmed-strength-candidate-geometry-calibration', 'OriginalLightingFieldBinding.h', ['NormalStrength=16.0f',
      'HeightSide=68,NormalSide=66,TileTexels=64', 'ShadowHeightScale=', 'ShadowHeightOffset=', 'ShadowBiasAndStrength=0.125',
      'ScreenLightCandidate=1.0f'],
      'Normal strength16 is recovered from retail. Cache size/precision, shadow coordinate conversion, direction/bias and screen light1 are explicit current policies.')
check('unknown-domain-does-not-read-material-payload', 'OriginalLightingFieldModel.h',
      'result.revealed[index]=static_cast<std::uint8_t>(plot.revealed?1u:0u);',
      'The field domain captures only dimensions, wrap, coordinates and reveal state, with no continent/water/terrain/river payload.')
check('strict-bilinear-support-before-height', 'OriginalLightingFieldModel.h', ['if(!RevealedAt(domain,x,y))return false;',
      'KnownNode(domain,atlas,ix,iy)&&KnownNode(domain,atlas,ix+1,iy)',
      'if(span==0||!known(x,y))return result;', 'if(!known(x,y))return result;alpha[i]=sample(x,y);'],
      'All four source nodes are known before a bilinear height read, including zero-weight corners; unknown rays stop without sampling.')
check('shadow-original-forty-step-order', 'OriginalLightingFieldModel.h', ['x+=dx;y+=dy;',
      'for(unsigned i=0;i<40;++i){x+=dx;y+=dy;', 'return RawShadow40(initial,alpha,stepLength,params);'],
      'Actual sampled ray coordinates begin at step2 and end at step41. Exact original rise/inverse96 constants are used.', ordered=True)
check('shadow-raw-original-arithmetic', 'OriginalLightingFieldModel.h', ['RayRise=0.3144854605197906494140625',
      'Inverse96=0.010416666977107524871826171875', '(initialAlpha*params.heightScale)*255+params.biasAndStrength',
      'ray+=rise;double lit=1;', '(sample*255-64)*Inverse96', '(1-lit)*params.biasAndStrength'],
      'Raw reference preserves original height, ray bias/rise, soft occlusion and shared bias/amplitude operations; protection/fallback policies remain separate.')
check('height-shader-known-before-textures', 'OriginalLightingFieldShader.h', ['if(Known.Load(int3(at,0))==0)return 0;',
      'Diffuse[i].SampleLevel(RawWrap,uv,0)', 'HeightMap[i].SampleLevel(RawWrap,uv,0)'],
      'Unknown source pixels return neutral height before any raw material sample; alpha^8 weighting and explicit mip0 are preserved.', ordered=True)
check('height-wrap-policy-bound', 'OriginalLightingFieldGpu.inc', ['constants.parameters[1]=static_cast<float>(surface.width);',
      'constants.parameters[2]=static_cast<float>(surface.height);',
      'constants.parameters[3]=(surface.wrapX?1.0f:0.0f)+(surface.wrapY?2.0f:0.0f);'],
      'The corrected height shader receives map dimensions/wrap bits and canonicalizes halo world UVs, matching CPU material callbacks.')
check('gpu-normal-known-tap-fallback', 'OriginalLightingFieldShader.h', ['if(Known.Load(int3(at,0))==0)return center;',
      'if(Known.Load(int3(c,0))==0)return float4(0.5,0.5,1,0);',
      'normalize(float3(-parameters.x*sx,parameters.x*sy,4))'],
      'Eight-tap Sobel uses known height only; unsupported taps fall back to the known center and unsupported centers produce neutral encoded normals.')
check('bounded-owned-resource-shapes', 'OriginalLightingFieldGpu.inc', ['td.Width=td.Height=68;',
      'td.Format=DXGI_FORMAT_R16_FLOAT', 'td.Width=td.Height=66;',
      'DXGI_FORMAT_R16G16B16A16_UNORM', 'td.Format=DXGI_FORMAT_R16_UNORM;', 'td.Format=DXGI_FORMAT_R8_UINT;'],
      'One shared68 height target and per-mesh66 normal/shadow fields use fixed bounds. These formats/resolutions remain reconstruction policies.')
check('bake-real-mixed-height-source', 'OriginalLightingFieldGpu.inc', ['OT::QuantizeWeights(OT::KernelWeights(',
      'resources[i]=catalog.textures.at(row.diffuse).Get()', 'resources[8+i]=catalog.textures[row.height].Get()',
      'resources[16]=knownResource.Get();'],
      'The private height raster consumes actual original raw diffuse alpha and material height textures, using current bounded top8 and halo vertex interpolation.')
check('offscreen-height-then-normal', 'OriginalLightingFieldGpu.inc', ['OMSetRenderTargets(1,&output,nullptr);',
      'DrawIndexed(68*68*6,0,0)', 'OMSetRenderTargets(0,nullptr,nullptr);',
      'PSSetShaderResources(0,43,empty.data());', 'output=normalView.Get();',
      'heightInputs[]={baker.heightResource.Get(),knownResource.Get()}', 'cache.context->Draw(3,0);return result;'],
      'Height output is detached before it becomes a normal-pass input. Both private passes write one colour target with no scene depth or ID binding.', ordered=True)
check('offscreen-depth-disabled-no-id', 'OriginalLightingFieldGpu.inc', ['depth.DepthEnable=FALSE;',
      'depth.DepthWriteMask=D3D11_DEPTH_WRITE_MASK_ZERO', 'OMSetDepthStencilState(baker.depthDisabled.Get(),0)'],
      'Private production never writes scene depth or integer selection IDs.')
check('save-private-pipeline-state', 'OriginalLightingFieldGpu.inc', ['PSGetShaderResources(0,43,rawResources.data())',
      'OMGetRenderTargets(', 'IAGetVertexBuffers(', 'VSGetConstantBuffers(4,1,&vertexConstants)',
      'PSGetConstantBuffers(4,1,&pixelConstants)', 'RSGetViewports(', 'GetPredication('],
      'All owner pipeline state touched by the private bake is captured; b0 camera and b3 lighting are untouched.')
check('restore-private-pipeline-state', 'OriginalLightingFieldGpu.inc', ['~RestoreLightingFieldPipeline() noexcept',
      'PSSetShaderResources(0,43,empty.data())', 'VSSetConstantBuffers(4,1,&vcb)', 'PSSetConstantBuffers(4,1,&pcb)',
      'SetPredication(predicate.Get(),predicateValue)', 'OMSetDepthStencilState(depthState.Get(),stencil)',
      'OMSetRenderTargets(static_cast<UINT>(oldOutputs.size()),oldOutputs.data(),depthTarget.Get())',
      'PSSetShaderResources(0,43,oldResources.data())'],
      'RAII restores framebuffer/depth, viewport, vertex/index/layout, shaders, b4, sampler, predicate and all43 SRVs, including exceptions.')
check('private-bake-has-no-stream-output-side-effects', 'OriginalLightingFieldGpu.inc',
      'SOSetTargets(0,nullptr,nullptr);cache.context->SetPredication(nullptr,FALSE);',
      'The render owner intentionally detaches stream output before every bake and again in the main/reflection pass; arbitrary external stream-output preservation is not promised.')
check('prepare-before-reflection-and-main', 'WorldTerrainRenderer.cpp', ['if(lightingEnabled)PrepareLightingFields(view,cache,*groundData->original);',
      'if(surfaceTargets)DrawWaterReflection(', 'if(groundData->original)DrawOriginalGround('],
      'Fields are ready before either ground draw; reflected/main terrain share the same current field and pose geometry.', ordered=True)
check('base-vs-normal-separate-from-detail', 'OriginalTerrainShader.h', ['float3 normal:TEXCOORD5;',
      'TerrainCacheBake(continent,p.normal,detailNormal,shadow,albedo,',
      'tangent*materialNormal.x+bitangent*materialNormal.y+n*materialNormal.z'],
      'The source follows original NORMAL0 base n plus independent sampled detail m. Current atlas NORMAL0 supply is a remaining geometry-policy boundary.')
check('field-slots41-42-correct', 'OriginalTerrainGpu.inc', ['std::array<ID3D11ShaderResourceView*,43> resources{};',
      'resources[41]=mesh.lightingField->normal.Get();resources[42]=mesh.lightingField->shadow.Get();'],
      't41/t42 supply the corresponding per-canonical-mesh resources; original material/ID/lighting resource ranges stay intact.')
check('field-fetches-after-exact-unknown-gate', 'OriginalTerrainShader.h', ['if(state.y==0){if(clipInfo.y>0.5)discard;return o;}',
      'LightingSelector.Load(int3(cell,0))', 'DetailNormalField.SampleLevel(', 'HeightShadowField.SampleLevel('],
      'Exact state denies unknown fragments before selector/detail/shadow reads; the field filter cannot reveal hidden tile payload.', ordered=True)
check('confirmed-final-specular-routing', 'OriginalTerrainShader.h', ['pow(max(bakedSpecular,0),2.2)*screenLighting.rgb+pow(max(colour,0),2.2)',
      'TerrainComposition(continent,baked,bakedSpecular.rgb)'],
      'Final t8 semantic correction is implemented: decoded baked specular is weighted by the screen-light input and added to decoded lit diffuse before encoding.')
check('both-enables-and-no-added-specular-gain', 'OriginalTerrainGpu.inc', ['parameters.composition[0]=1;parameters.composition[1]=1;',
      'parameters.screenLight[0]=parameters.screenLight[1]=parameters.screenLight[2]=FB::ScreenLightCandidate;'],
      'Both original gates are enabled for the opt-in path. Screen light1 replaces the untraced producer; there is no extra invented gain.')
check('retained-depth-id-position', 'OriginalTerrainShader.h', ['p.p=mul(float4(v.p+float3(placement.x,0,placement.y),1),viewProjection);',
      'uint pick:SV_Target1;', 'o.pick=state.x;'],
      'New fields and final RGB composition do not move vertices or change exact tile ID classification.')
check('ground-unbinds43-and-lighting', 'OriginalTerrainGpu.inc', ['std::array<ID3D11ShaderResourceView*,43> clear{};',
      'PSSetConstantBuffers(3,1,&nullBuffer)', 'PSSetSamplers(1,1,&nullSampler)'],
      'Every ground pass releases field/lighting SRV bindings before surface/units/FOW use their slots.')
check('reflection-unbinds43', 'OriginalWaterReflection.inc', ['empty[43]', 'PSSetShaderResources(0,43,empty)',
      'PSSetConstantBuffers(3,1,&noLighting)', 'PSSetSamplers(1,1,&noLightingSampler)'],
      'Reflection RAII clears the new slots as well as lighting inputs while restoring main camera and clipping.')
check('gamma-views-and-units', 'OriginalWaterReflection.inc', ['lighting?targets.reflectionRawView.Get():targets.reflectionView.Get()',
      'DrawOriginalGround(view,cache,*ground.original,false,lighting);', 'colour=targets.reflectionView.Get();', 'DrawTerrainUnits(cache,unitGroups);'],
      'Encoded original lighting uses raw UNORM, then linear unit output returns to the existing sRGB view; reflection stays a private target.', ordered=True)
check('cache-key-no-clock', 'WorldTerrainReuse.h', 'lightingPackage_!=view.lightingAssetsPath',
      'Lighting path changes invalidate current ground metadata; clocks never enter the terrain key or field domain.')
check('input-generation-unchanged', 'InteractiveGameLoop.h', ['RenderWorldViewToTexture(retainedView,device,context,target,&candidate,why,nullptr,false)',
      'window.SceneGeneration()!=generation'],
      'Presentation-only refresh retains input/hit generation and never advances SDK state.')
check('owner-release', 'WorldTerrainRenderer.cpp', 'GpuTerrainCache().reset();LegacyTerrainCache().reset();',
      'Render-owner destruction releases atlas meshes/field SRVs/shared baker references. Driver/context memory lifetime is still an actual-GPU gate.')

assert all(c not in src['WorldTerrainReuse.h'] for c in ['animationSeconds', 'fogAnimationSeconds', 'waterAnimationSeconds'])
assert 'IsLake(' not in src['WorldViewState.h']
references = {}
for rel in ['phase6/semantics/retail_cache_bindings.json', 'phase6/shader/current.json',
            'phase6/review/field_shader/attempt02/result.json', 'phase6/review/material_sampler/attempt01/result.json',
            'phase6/field_cpu/cpu/result.json', 'phase6/field_cpu/lighting_api/cpu/result.json',
            'phase6/pipeline/cpu01/result.json', 'phase6/review/build_tools_update.json']:
    references[rel] = ref('evidence/world_terrain_original/'+rel)
current = json.loads((ROOT/'evidence/world_terrain_original/phase6/shader/current.json').read_text('utf8'))
assert len(current['passes']) == 10
assert all(p['exit_code'] == 0 and all(p['reflection']['checks'].values()) for p in current['passes'])
for row in current['fixed_inputs']:
    assert ref(Path(row['path']))['sha256'] == row['sha256']
after = {n: ref(n) for n in PATHS}
assert before == after
value = dict(schema='zerosis.original_detail.phase6.independent_integration_review.v1',
    status='PASS_PHASE6_DETAIL_SHADOW_FINAL_SPEC_SOURCE_INTEGRATION_WITH_RUNTIME_GATES_OPEN',
    source_files_before=before, source_files_after=after, source_files_unchanged_during_review=True,
    checks=checks, integration_checks=len(checks), terrain_shader_source_checks=len(current['source_checks']),
    shader_stages=10, blocking_findings=[], findings=[], references=references,
    resolved_findings=['The private height halo now canonicalizes wrap coordinates before texture sampling; the changed height VS/PS alone were recompiled and the normal pair reused.',
        'Final terrain t8 is correctly named and supplied as baked specular cache after retail descriptor-provider trace; the previous albedo interpretation is superseded without editing old evidence.'],
    confirmed_original_connections=['Mixed material height→cardinal Sobel strength16',
        'Separate VS NORMAL0 base and texture0 detail normal→CacheBake', '40step Macro Shadow→CacheBake t2',
        'CacheBake specular output1→final TerrainShader t8, screen-light weighted linear sum before original gamma'],
    remaining_limits=['Original CPU NORMAL0 generation, screen-light t9 production/runtime values and actual light/UV/bias constants.',
        'Current68/66 sizes, half/UNORM16 formats, halo top8 policy, mip0/cube/LUT sampling, atlas shadow mapping and cache ordering/resolution are explicit reconstruction policies.',
        'Complete original external OM blend/depth states and every packed-cache/special-case route remain untraced.',
        'Unknown support/ray fallback and invalid-domain finite/gamma guards are current protection policies.',
        'Global phase2 FOW remains; original water-specific .4 replacement is still not wired per fragment on GPU.',
        'No actual GPU target/resource creation, sampling/raster acceptance, lifecycle/performance, screen or gameplay validation occurred.',
        '규칙 동등, 배치 동등은 미검증.'],
    review_production_source_modified=False,
    existing_files_modified_by_reviewer=['tools/build_menu_suite_host.py', 'tools/attest_prepared_menu_host.py'],
    host_gamecore_clr_hwnd_gpu_audio_or_game_executed=False,
    original_mods_settings_saves_default_runtime_registration_changed=False)
out = STAGE/'integration_review.json'
with out.open('x', encoding='utf8') as stream:
    stream.write(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
print(json.dumps(dict(status=value['status'], source_files=len(PATHS), checks=len(checks),
    sha256=hashlib.sha256(out.read_bytes()).hexdigest())))
