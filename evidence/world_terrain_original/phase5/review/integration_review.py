"""Independent source/data-flow review of the final phase-five renderer integration."""
from pathlib import Path
import gzip
import hashlib
import json

ROOT = Path(__file__).resolve().parents[4]
STAGE = Path(__file__).resolve().parent
NAMES = [
 'Source/Presentation/OriginalLightingBinding.h', 'Source/Presentation/OriginalLightingPackage.h',
 'Source/Presentation/OriginalLightingModel.h', 'Source/Presentation/OriginalLightingState.h',
 'Source/Presentation/OriginalLightingGpuTypes.inc', 'Source/Presentation/OriginalLightingGpu.inc',
 'Source/Presentation/OriginalTerrainShader.h', 'Source/Presentation/OriginalTerrainGpuTypes.inc',
 'Source/Presentation/OriginalTerrainGpu.inc', 'Source/Presentation/OriginalTerrainModel.h',
 'Source/Presentation/WorldTerrainRenderer.cpp', 'Source/Presentation/WorldTerrainReuse.h',
 'Source/Presentation/WorldViewRenderer.h', 'Source/Presentation/WorldTerrainUnits.inc',
 'Source/Presentation/OriginalWaterSurfaceBinding.h', 'Source/Presentation/OriginalWaterSurfaceShader.h',
 'Source/Presentation/OriginalWaterSurfaceGpuTypes.inc', 'Source/Presentation/OriginalWaterSurfaceGpu.inc',
 'Source/Presentation/OriginalWaterSurfaceTargets.inc', 'Source/Presentation/OriginalWaterReflection.inc',
 'Source/Presentation/OriginalWaterSurfaceModel.h', 'Source/Presentation/OriginalWaterGpu.inc',
 'Source/Presentation/OriginalWaterState.h', 'Source/Presentation/OriginalFogShader.h',
 'Source/Presentation/OriginalFogGpu.inc', 'Source/Host/WorldViewState.h',
 'Source/Host/InteractiveGameLoop.h', 'tools/build_menu_suite_host.py', 'tools/attest_prepared_menu_host.py',
]


def ref(path):
    path = ROOT/path
    data = path.read_bytes()
    st = path.stat()
    return dict(path=str(path), bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
        file_identity=[st.st_dev, st.st_ino], mtime_ns=st.st_mtime_ns,
        file_attributes=getattr(st, 'st_file_attributes', 0), links=st.st_nlink)


before = {n: ref(n) for n in NAMES}
src = {n.split('/')[-1]: (ROOT/n).read_text('utf8') for n in NAMES}
checks = []


def check(name, file, needles, review, ordered=False):
    s = src[file]
    if isinstance(needles, str):
        needles = [needles]
    pos = 0
    hit = []
    for needle in needles:
        at = s.find(needle, pos if ordered else 0)
        assert at >= 0, (name, needle)
        hit.append(s[:at].count('\n')+1)
        pos = at+len(needle)
    checks.append(dict(name=name, pass_=True, source=file, lines=hit, review=review))


check('sealed-lighting-packet', 'OriginalLightingBinding.h', 'd0873d3915da23e45ee1b66187bb7e4174673a1e8cce1fea16b6151ff515e424',
      '15 asset roles reference nine unique verified blobs; only the 730040-byte minimal lighting packet is required.')
check('candidate-binding-labelled', 'OriginalLightingBinding.h', ['Candidate runtime binding', 'BC1_UNORM', 'remain unverified'],
      'Continent role mapping, cube axes, LUT-volume loader and sampler state are candidate bindings, not traced original upload calls.')
check('raw-cube-and-lut-upload', 'OriginalLightingGpu.inc', ['LG::DecodePackage(std::move(input.data),LG::LightingPackageSha256)',
      'std::array<ComPtr<ID3D11ShaderResourceView>,15> uploaded;', 'uploaded[asset.blobIndex]',
      'DXGI_FORMAT_BC1_UNORM', 'td.ArraySize=6', 'D3D11_RESOURCE_MISC_TEXTURECUBE', 'DXGI_FORMAT_R8G8B8A8_UNORM'],
      'Immutable BC1 cubemaps and raw RGBA8 3D LUTs reuse views by verified blob index; no SRGB decode or new unpinned asset is introduced.')
check('candidate-complete-before-publish', 'OriginalLightingGpu.inc', ['std::make_unique<LightingCatalog>()', 'CreateSamplerState', 'CreateBuffer', 'return result;'],
      'All resource construction succeeds before the new owner catalog is returned.', ordered=True)
check('unknown-selector-before-physical-fields', 'OriginalLightingState.h', ['if(!plot.revealed)continue;', 'if(plot.water)', 'if(plot.continent<0||plot.continent>4)'],
      'Unknown plots do not read water or continent numbers; invalid/duplicate coordinates are rejected separately.', ordered=True)
check('selector-independent-integer', 'OriginalTerrainGpu.inc', ['std::vector<unsigned char> selectors(states.size(),255);',
      'LG::CaptureLightingSelectors(view)', 'td.Format=DXGI_FORMAT_R8_UINT', '&ground.lightingSelectors'],
      'Known water selects generic0; known land selects bounded continent. This texture is separate from exact R32G32 tile ID/state.')
check('unknown-before-lighting-selector', 'OriginalTerrainShader.h', ['if(state.y==0){if(clipInfo.y>0.5)discard;return o;}', 'LightingSelector.Load(int3(cell,0))'],
      'Final terrain rejects unknown reflection or returns unknown background before any material/lighting selector samples.', ordered=True)
check('vertex-abi-adds-only-normal', 'OriginalTerrainGpuTypes.inc', ['float x,y,z,u,v,light;std::uint32_t w0,w1;float nx,ny,nz;', 'sizeof(OriginalVertex)==44', 'sizeof(OriginalConstants)==192'],
      'The vertex tail adds original-coordinate normals. Existing position/UV/light/material-weight fields and chunk constants retain their offsets.')
check('normal-layout-and-position-preserved', 'OriginalTerrainGpu.inc', ['DXGI_FORMAT_R32G32B32_FLOAT,0,32',
      'vertices.push_back({u,height,-v*OT::RowSpacing,u,v,light,w0,w1,normal.x,normal.y,normal.z});'],
      'TEXCOORD5 reads the appended 32-byte-offset float3; original geometry coordinates and weights are unchanged.')
check('original-vs-position-and-normal-tail', 'OriginalTerrainShader.h', ['p.p=mul(float4(v.p+float3(placement.x,0,placement.y),1),viewProjection);', 'p.normal=v.normal;'],
      'Lighting changes colour and the separate specular auxiliary, not vertex position or SV_Target1 classification.')
check('neutral-normal-shadow-explicit', 'OriginalTerrainShader.h', ['float3 materialNormal=float3(0,0,1);', 'float shadow=lightingInfo.y;',
      'float3(-n.z,0,n.x)', 'float3(0,n.z,-n.y)'],
      'The original tangent-basis arithmetic is present. Material-normal and shadow producers remain explicitly neutral candidates.')
check('irradiance-original-intermediate-order', 'OriginalTerrainShader.h', ['irradianceBase=sun*1.7,irradianceDelta=shade*1.7-irradianceBase;',
      'irradiance=shadow*irradianceDelta+irradianceBase;', 'LightingEncode(albedo*irradiance+0.001)'],
      'Original cube scaling, shadow interpolation and albedo epsilon/encoding order replace the provisional light multiplier.')
check('separate-specular-route', 'OriginalTerrainShader.h', ['float exponent=64*specular.a+1;',
      'pow(saturate(dot(specularAxis.xyz,N)),exponent)*exponent*saturate(1-shadow)*specular',
      'o.specularSquared=bakedSpecular;'],
      'Original CacheBake specular RGB receives gamma/LUT, alpha remains scaled separately; no guessed downstream addition is made.')
check('terrain-composition-toggle-and-premul', 'OriginalTerrainShader.h', ['compositionInfo.x>0.5?baked:0',
      'pow(max(albedo,0),2.2)*screenLighting.rgb+pow(max(colour,0),2.2)',
      'saturate(compositionInfo.z)*lightingInfo.w', 'overlayColour.rgb+(1-overlayColour.a)*colour'],
      'The confirmed cache/screen-light/mask-LUT/premultiplied overlay equations are executable with neutral candidate inputs.')
check('lighting80-and-slots25-through40', 'OriginalTerrainGpu.inc', ['OriginalLightingConstants parameters{};',
      'parameters.composition[0]=1;', 'PSSetConstantBuffers(3,1,&lightingBuffer)', 'PSSetSamplers(1,1,&lightingSampler)',
      'std::array<ID3D11ShaderResourceView*,41> resources{};', 'resources[25]=ground.lightingSelectors.Get();',
      'resources[26+i]=lighting->sunlight[i].Get();resources[31+i]=lighting->shadowlight[i].Get();resources[36+i]=lighting->terrainLut[i].Get();'],
      '80-byte b3 and 16 extra SRVs exactly match strict reflection. Default shadow, world-mask, screen-light and overlay inputs are neutral.')
check('lighting-bindings-cleanup', 'OriginalTerrainGpu.inc', ['std::array<ID3D11ShaderResourceView*,41> clear{};',
      'PSSetConstantBuffers(3,1,&nullBuffer)', 'PSSetSamplers(1,1,&nullSampler)'],
      'Ground drawing unbinds 41 SRVs, lighting b3 and sampler1 before returning to normal unit/surface shaders.')
check('mode-key-plus-package', 'WorldTerrainReuse.h', ['key.lightingPackage_=view.lightingAssetsPath;', 'lightingPackage_!=view.lightingAssetsPath'],
      'Enabling/disabling/replacing the packet invalidates exact ground metadata. No presentation clock enters the ground key.')
check('frame-target-mode-key', 'WorldTerrainRenderer.cpp', ['cache.targets->lightingEnabled==lightingEnabled',
      'fogEnabled||surfaceEnabled||lightingEnabled?DXGI_FORMAT_B8G8R8A8_TYPELESS', 'if(surfaceEnabled||lightingEnabled)'],
      'Lighting mode creates an encoded UNORM view of the existing typeless colour target without changing IDs/depth shapes.')
check('main-raw-ground-srgb-units', 'WorldTerrainRenderer.cpp', ['lightingEnabled?surfaces.colorRawView.Get():surfaces.colorView.Get()',
      'DrawOriginalGround(view,cache,*groundData->original,fogEnabled,activeLighting)', 'ID3D11RenderTargetView* target=surfaces.colorView.Get();',
      'DrawTerrainUnits(cache,unitGroups);'],
      'Encoded terrain uses raw UNORM; the main unit pass explicitly returns to the existing sRGB RTV for linear unit output.')
check('reflection-raw-ground-srgb-units', 'OriginalWaterReflection.inc', ['lighting?targets.reflectionRawView.Get():targets.reflectionView.Get()',
      'DrawOriginalGround(view,cache,*ground.original,false,lighting);', 'colour=targets.reflectionView.Get();', 'DrawTerrainUnits(cache,unitGroups);'],
      'Reflected encoded terrain and linear units switch views of the same private colour surface correctly.', ordered=True)
check('reflection-rgb-raw-view-created', 'OriginalWaterSurfaceTargets.inc', ['target.Format=DXGI_FORMAT_B8G8R8A8_UNORM;', '&candidate->reflectionRawView'],
      'The alternate reflection RTV is created transactionally with the original target set; its sampling SRV remains raw UNORM.')
check('reflection-restore-new-lighting-state', 'OriginalWaterReflection.inc', ['PSSetShaderResources(0,41,empty)',
      'PSSetConstantBuffers(3,1,&noLighting)', 'PSSetSamplers(1,1,&noLightingSampler)', 'const float noClip[4]={0,0,0,0}'],
      'RAII restores main camera/clip and clears every new lighting input, including an exceptional reflection exit.')
check('surface320-populated-light-colours', 'OriginalWaterSurfaceGpuTypes.inc', ['lightColour0[4],lightColour1[4],shadow[4]', 'sizeof(WaterSurfaceConstants)==320'],
      'Three float4s extend the old 272-byte surface buffer; shader reflection proves offsets272/288/304.')
check('surface-runtime-colour-candidates', 'OriginalWaterSurfaceGpu.inc', ['constants.lightColour0[0]=0.02f',
      'constants.lightColour1[0]=0.0072f', 'Runtime cb1[16/17] colours and projected shadow texture are not captured.'],
      'Actual formula is connected while original runtime light RGB/shadow producers stay explicit candidates.')
check('water-raw-d-and-raw-fresnel', 'OriginalWaterSurfaceShader.h', ['Refraction(p,state.x,mean,deep.rgb)',
      'float f=RetailFresnel(mean,view),diffuse=saturate(dot(float3(mean,1),light0.xyz));'],
      'No extra palette gamma decode and no old Fresnel clamp remain in the valid-domain original pre-shadow arithmetic.')
check('water-three-lobes-and-depth-cubic', 'OriginalWaterSurfaceShader.h', ['float lobe0=Gaussian(', 'float lobeWide0=Gaussian(',
      'float lobe1=Gaussian(', 'float qSquared=q1*q1,qCubed=qSquared*q1;', 'lit+=depthFactor*qCubed*deep.rgb;'],
      'Two narrow lobes and only primary wide lobe feed the original expression; finite secondary q survives q>=16 rejection.')
check('water-shadow-order-and-finite-policy', 'OriginalWaterSurfaceShader.h', ['return isfinite(result)?result:0;',
      'if(!isfinite(qCubed))qCubed=0;', 'float3 shadowed=shadowAmount*lit;lit=shadowed*(-0.67)+lit;',
      'if(!all(isfinite(lit)))lit=deep.rgb;'],
      'Gaussian, cubic and composite overflow guards are outside the original valid domain; original finite q is not artificially clamped.')
check('water-hardware-policy-not-mislabelled', 'OriginalWaterSurfaceShader.h', ['float opacity=saturate(deep.a*(1+coverage));',
      'lerp(Encoded(base),Encoded(lit),opacity)', 'o.colour=float4(composite,1)'],
      'The original alpha factor precedes an explicit encoded opaque scene composite. This does not claim a recovered OM blend state.')
check('surface-depth-and-id-unchanged', 'OriginalWaterSurfaceGpu.inc', ['OMSetRenderTargets(kind==0?2:1,output,frame.depthView.Get())',
      'kind==0?cache.depthState.Get():water.depthReadOnly.Get()', 'kind==0?cache.blendState.Get():water.alphaBlend.Get()'],
      'Water plane still writes real depth and exact ID; shoreline writes colour only with read-only depth/RGB blend.')
check('refraction-positive-same-id-depth-world', 'OriginalWaterSurfaceShader.h', ['if(pick==0)return fallback;',
      'uint id=SceneId.Load(int3(at,0));if(id!=pick)return fallback;', 'float depth=SceneDepth.Load(',
      'source.y>=reflectionInfo.z)return fallback;', 'SceneColour.Load(int3(at,0))'],
      'No neighbouring or hidden tile colour/depth is imported; source reconstructs behind and below the same plane.', ordered=True)
check('no-double-fow-and-fog', 'OriginalWaterSurfaceGpu.inc', 'constants.motion[2]=fogEnabled?1.0f:0.0f;',
      'Surface shader leaves FOW/distance to the existing one post-pass when enabled; original water gray .4 replacement is not falsely applied to all water plots/units.')
check('unchanged-global-fow-unknown-branch', 'OriginalFogShader.h', ['[branch]if(state.y==0)result=replacement;',
      'result=lerp(replacement,terrain,mask.r);', 'result=lerp(result,transformed,mask.r*(1-mask.b));'],
      'The existing cloud/base-layer FOW path remains. Its unknown branch still prevents scene-colour/LUT reads; water-specific .4 GPU wiring is explicitly outstanding.')
check('candidate-publication-after-completed-frame', 'WorldTerrainRenderer.cpp', ['if(callerTarget)cache.context->CopyResource(callerTarget,finalColour);',
      'cache.ground.Publish(', 'if(surfaceCandidate)cache.waterSurface=std::move(surfaceCandidate);',
      'if(lightingCandidate)cache.lighting=std::move(lightingCandidate);', '*frame=std::move(result);return true;'],
      'All failing frame work precedes successful ground/catalog publication. Failed candidates do not replace prior lighting owners.', ordered=True)
check('explicit-private-lighting-path', 'InteractiveGameLoop.h', ['L"ZEROSIS_LIGHTING_ASSETS"', 'count>32768',
      'view.lightingAssetsPath=lightingAssetsPath;'],
      'An opt-in bounded environment path is copied into the detached DTO; no default runtime, original game setting, registration or save change is added.')
check('animation-input-generation-unchanged', 'InteractiveGameLoop.h', ['retainedView.waterAnimationSeconds=seconds;',
      'RenderWorldViewToTexture(retainedView,device,context,target,&candidate,why,nullptr,false)',
      'window.SceneGeneration()!=generation'],
      'Detached animation refresh preserves hit metadata/input generation, with no new SDK capture or RNG consumption.')
check('owner-release', 'WorldTerrainRenderer.cpp', 'void ReleaseWorldTerrainResources(){GpuTerrainCache().reset();LegacyTerrainCache().reset();}',
      'Both C++ render-owner caches release their references. External context/driver resource lifetimes still need actual GPU acceptance.')

assert all(c not in src['WorldTerrainReuse.h'] for c in ['animationSeconds', 'fogAnimationSeconds', 'waterAnimationSeconds'])
assert 'IsLake(' not in src['WorldViewState.h']
old_rows = json.loads((ROOT/'evidence/world_terrain_original/phase5/source_before.json').read_text('utf8'))['backups']
old_terrain = next(r for r in old_rows if r['source']['path'].endswith('OriginalTerrainGpu.inc'))
old_gpu = gzip.decompress(Path(old_terrain['backup']['path']).read_bytes()).decode('utf8')
assert 'vertices.push_back({u,height,-v*OT::RowSpacing,u,v,light,w0,w1});' in old_gpu
assert 'vertices.push_back({u,height,-v*OT::RowSpacing,u,v,light,w0,w1,normal.x,normal.y,normal.z});' in src['OriginalTerrainGpu.inc']
references = {}
for rel in ['phase5/semantics/lighting_contract.json', 'phase5/shader/current.json', 'phase5/shader/header_seal.json',
            'phase5/lighting_cpu/current.json', 'phase5/pipeline/cpu01/result.json', 'phase5/assets/completion.json',
            'phase5/review/asset_pipeline_review.json', 'phase5/review/build_tools_update.json', 'phase5/calibration_notes.json']:
    references[rel] = ref('evidence/world_terrain_original/'+rel)
shader = json.loads((ROOT/'evidence/world_terrain_original/phase5/shader/current.json').read_text('utf8'))
for row in shader['fixed_inputs']:
    assert ref(Path(row['path']))['sha256'] == row['sha256']
for row in shader['passes']:
    assert row['exit_code'] == 0 and all(row['reflection']['checks'].values())
assert len(shader['passes']) == 6
after = {n: ref(n) for n in NAMES}
assert before == after
value = dict(schema='zerosis.original_lighting.phase5.independent_integration_review.v1',
    status='PASS_PHASE5_SOURCE_INTEGRATION_WITH_ORIGINAL_RUNTIME_AND_GPU_GATES_OPEN',
    source_files_before=before, source_files_after=after, source_files_unchanged_during_review=True,
    checks=checks, integration_checks=len(checks), shader_source_checks_referenced=len(shader['source_checks']),
    current_shader_stages=6, blocking_findings=[], findings=[], references=references,
    resolved_findings=['Original irradiance, secondary cubic and dynamic-shadow intermediate operation orders were corrected before strict validation.',
        'Overflow in finite-but-extreme secondary q cubic and Gaussian/composite results now has explicit separate safe fallback; only the changed two surface stages were recompiled.'],
    implementation_limits=[
        'Exact original arithmetic is implemented with explicit current sampled inputs. Material-normal/shadow producers remain neutral, and original cache filtering/order/resolution are not reconstructed.',
        'Cube axes, continent asset mapping, raw UNORM view interpretation, candidate32 TGA-volume LUT loading and forced LOD0 sampling require runtime calibration.',
        'The full original CacheBake specular-target route is unknown, so its computed auxiliary stays separate. No invented specular addition is called original.',
        'World-mask/screen-light/overlay inputs currently use neutral candidate values; dynamic scene shadow production and original external OM blend states remain untraced.',
        'Original water gray .4 FOW composition is covered by the CPU reference but not wired per fragment on the GPU. Global phase2 cloud/base-layer replacement is retained to avoid incorrectly tinting visible units or applying FOW twice.',
        'Same-positive-ID isolated-scene refraction and encoded opaque water composition remain new policies; examined original water PS did not establish that separate screen-scene source pair.',
        'Current finite/max/gamma/determinant/overflow policies protect invalid domains and do not establish bit-identical original output.',
        '규칙 동등, 배치 동등은 미검증.',
    ],
    remaining_gates=['C++ compile/link and independent prepared-pair attestation of final source closure.',
        'Actual D3D11 target creation, cube/LUT sampling, depth/ID, source-owner lifetime, performance and display acceptance.',
        'Original runtime calibration and gameplay validation remain separately held.'],
    review_production_source_modified=False,
    existing_files_modified_by_reviewer=['tools/build_menu_suite_host.py', 'tools/attest_prepared_menu_host.py'],
    original_mods_settings_saves_default_runtime_registration_changed=False,
    host_gamecore_clr_hwnd_gpu_audio_or_game_executed=False)
out = STAGE/'integration_review.json'
out.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
print(json.dumps(dict(status=value['status'], source_files=len(NAMES), integration_checks=len(checks),
    shader_source_checks=len(shader['source_checks']), sha256=hashlib.sha256(out.read_bytes()).hexdigest())))
