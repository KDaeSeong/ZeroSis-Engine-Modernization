"""Pin an offline, independent source review; do not load graphics or game code."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).with_suffix('.json')
SOURCE = {
    'types': 'Source/Presentation/OriginalWaterSurfaceGpuTypes.inc',
    'gpu': 'Source/Presentation/OriginalWaterSurfaceGpu.inc',
    'shader': 'Source/Presentation/OriginalWaterSurfaceShader.h',
    'binding': 'Source/Presentation/OriginalWaterSurfaceBinding.h',
    'targets': 'Source/Presentation/OriginalWaterSurfaceTargets.inc',
    'reflection': 'Source/Presentation/OriginalWaterReflection.inc',
    'surface_model': 'Source/Presentation/OriginalWaterSurfaceModel.h',
    'optics_model': 'Source/Presentation/OriginalWaterOpticsModel.h',
    'lean_package': 'Source/Presentation/OriginalWaterLeanPackage.h',
    'units': 'Source/Presentation/WorldTerrainUnits.inc',
    'renderer': 'Source/Presentation/WorldTerrainRenderer.cpp',
    'terrain_shader': 'Source/Presentation/OriginalTerrainShader.h',
    'terrain_gpu': 'Source/Presentation/OriginalTerrainGpu.inc',
    'terrain_types': 'Source/Presentation/OriginalTerrainGpuTypes.inc',
    'reuse': 'Source/Presentation/WorldTerrainReuse.h',
    'dto': 'Source/Presentation/WorldViewRenderer.h',
    'state': 'Source/Host/WorldViewState.h',
    'loop': 'Source/Host/InteractiveGameLoop.h',
    'water_gpu': 'Source/Presentation/OriginalWaterGpu.inc',
    'water_state': 'Source/Presentation/OriginalWaterState.h',
    'water_types': 'Source/Presentation/OriginalWaterGpuTypes.inc',
    'water_binding': 'Source/Presentation/OriginalWaterBinding.h',
    'builder': 'tools/build_menu_suite_host.py',
    'attestor': 'tools/attest_prepared_menu_host.py',
}


def record(path):
    p = ROOT / path
    data = p.read_bytes()
    st = p.stat()
    return {'path': str(p), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
            'file_identity': [st.st_dev, st.st_ino], 'mtime_ns': st.st_mtime_ns,
            'file_attributes': getattr(st, 'st_file_attributes', 0), 'links': st.st_nlink}


before = {k: record(v) for k, v in SOURCE.items()}
src = {k: (ROOT / v).read_text(encoding='utf-8-sig') for k, v in SOURCE.items()}
checks = []


def require(name, source, text, reason):
    needles = [text] if isinstance(text, str) else text
    ok = all(n in src[source] for n in needles)
    checks.append({'name': name, 'pass': ok, 'source': SOURCE[source],
                   'line': src[source][:src[source].find(needles[0])].count('\n') + 1 if ok else None,
                   'review': reason})


def ordered(name, source, texts, reason):
    at = 0
    ok = True
    for text in texts:
        pos = src[source].find(text, at)
        if pos < 0:
            ok = False
            break
        at = pos + len(text)
    checks.append({'name': name, 'pass': ok, 'source': SOURCE[source], 'review': reason})


require('surface-package-pin', 'binding', '69c6780dbeb5f8605d8231cef944d0ec9392109b6ccc81a9d3b76ae83cfd0ef7',
        'The supplemental packet is fixed by SHA; no unpinned replacement or original asset write is introduced.')
require('raw-plane-runtime-candidate', 'binding', ['RawLevelCandidate=0.19836', 'WorldPlaneCandidate=static_cast<float>((RawLevelCandidate-OriginalTerrain::HeightOffsetCandidate)*OriginalTerrain::HeightWorldScaleCandidate)'],
        'Raw waterline and existing height conversion are explicit candidates; neither establishes original runtime cb1[12].x.')
require('plane-model-same-height-conversion', 'surface_model', ['double rawLevel=0.19836', 'static_cast<double>(Terrain::HeightOffsetCandidate)', '(plane.rawLevel-plane.heightOffset)*plane.worldScale'],
        'Default geometry and Root binding use the same double conversion before float emission. The independent pipeline asserts the final float bits.')
ordered('skip-unknown-before-height-sampling', 'surface_model', ['if(!context.QuadKnown(px,py,step))', 'const int extent=static_cast<int>(step);const Node a=context.Sample'],
        'Every texel inside each LOD quad, not only its corners, must be known before height samples are consumed.')
require('known-owner-and-mask', 'surface_model', ['if(!owner.exists||!grid.cells[static_cast<std::size_t>(owner.y)*grid.width+owner.x].revealed)return false;', 'return atlas.known[Index(x,y)]!=0;'],
        'Atlas known bits alone cannot expose a detached unknown plot; both ownership and known mask gate access.')
require('known-water-clip-and-known-land-contour', 'surface_model', ['if(cell.revealed&&cell.water)', 'if(!cell.revealed||cell.water)continue;', 'ClipHex(clipped,hex)', 'ClipLine(ca,cb,hex)'],
        'Plane polygons are clipped to known water cells; contour ribbons additionally require a known land neighbor.')
require('shared-crossing-and-bounded-lod-policy', 'surface_model', ['if(std::tie(b.x,b.y)<std::tie(a.x,a.y))std::swap(a,b);', 'Snap(a.x+(b.x-a.x)*t)', 'policy.adaptive&&step<64', 'result.vertices.size()==total'],
        'Shared edge orientation/snapping, deterministic bounded LOD and a counted emission pass prevent unbounded or inconsistent geometry; they are current reconstruction policies.')
ordered('capture-skips-unknown-payload', 'water_state', ['if(!plot.revealed)continue;', 'cell.water=plot.water', 'cell.river={{plot.riverW,plot.riverNW,plot.riverNE}}'],
        'The detached CPU water grid never evaluates hidden water, relief, terrain, river or flow payload.')
require('grid-reuse-ignores-camera-visibility-time', 'water_state', ['inline bool SameWaterGrid', 'if(x.revealed!=y.revealed)return false;if(!x.revealed)continue;'],
        'Static grid equality compares explored physical fields, wrap and dimensions. Camera/visible-only/three clocks are absent from that grid.')
require('weak-atlas-identity-and-key', 'types', ['OW::Grid key;std::weak_ptr<OriginalSurface> surface;', 'std::vector<std::array<std::vector<OW::DrawRange>,2>> ranges;'],
        'One owner geometry retains a static key plus weak atlas identity; every owner/kind can hold multiple contour ranges.')
require('geometry-rebuild-atlas-or-key-only', 'renderer', ['!OW::SameWaterGrid(activeSurface->geometry->key,waterGrid)', 'activeSurface->geometry->surface.lock()!=groundData->original->surface'],
        'Camera or visible-only changes reuse this static mesh while drawing fresh plot state; a replacement height atlas forces rebuild.')
require('exact-water-mask', 'gpu', ['revealed&&result->key.cells[i].water?1u:0u', 'td.Format=DXGI_FORMAT_R8_UINT'],
        'The final plane fragment must also belong to the exact known-water cell, independent of blended colour.')
require('plot-id-fragment-classification', 'shader', ['uint2 state=PlotState.Load(int3(cell,0));if(state.y==0)discard;', 'WaterMask.Load(int3(cell,0))==0)discard;', 'o.pick=state.x;'],
        'Cube-rounded tile classification and integer Load operations write the current visible tile ID; hidden explored tiles write zero.')
require('water-color-plus-id-shore-color-only', 'gpu', ['OMSetRenderTargets(kind==0?2:1,output,frame.depthView.Get())', 'kind==0?cache.depthState.Get():water.depthReadOnly.Get()', 'kind==0?cache.blendState.Get():water.alphaBlend.Get()'],
        'Plane kind writes normal depth and colour/ID; shoreline kind binds only colour with depth writes disabled and RGB-only alpha blend.')
require('normal-depth-less-writes', 'renderer', ['dd.DepthWriteMask=D3D11_DEPTH_WRITE_MASK_ALL;dd.DepthFunc=D3D11_COMPARISON_LESS;', 'blend.RenderTarget[0].RenderTargetWriteMask=D3D11_COLOR_WRITE_ENABLE_ALL;'],
        'Opaque plane writes its real rasterized depth. IndependentBlend remains false so the opaque write mask also applies to its integer target.')
require('shore-river-readonly-rgb', 'water_gpu', ['depth.DepthWriteMask=D3D11_DEPTH_WRITE_MASK_ZERO', 'D3D11_COMPARISON_LESS_EQUAL', 'D3D11_COLOR_WRITE_ENABLE_RED|D3D11_COLOR_WRITE_ENABLE_GREEN|D3D11_COLOR_WRITE_ENABLE_BLUE', 'OMSetRenderTargets(1,&target'],
        'Shore/rivers leave alpha, scene integer IDs and scene depth unchanged.')
require('rivers-only-filter-retained', 'water_gpu', ['bool riversOnly=false', 'if(riversOnly)', 'OW::SurfaceKind::River', 'result->riversOnly=riversOnly;'],
        'Plane mode suppresses the previous water and coast overlays, retaining original river geometry; empty mode keeps the old route.')
require('mode-toggle-invalidates-river-geometry', 'renderer', ['activeWater->geometry->riversOnly!=surfaceEnabled', 'groundData->original->surface,surfaceEnabled)'],
        'Switching plane mode cannot reuse a geometry object prepared for the other overlay mode.')
require('unit-height-max-same-plane', 'units', 'ground=std::max(ground,OriginalWaterSurfaceBinding::WorldPlaneCandidate);',
        'Visible water units stand on max(terrain,plane), rather than sinking to the old underwater height.')
require('anchor-height-max-same-plane', 'terrain_gpu', 'elevation=std::max(elevation,OriginalWaterSurfaceBinding::WorldPlaneCandidate);',
        'Projected centers use the identical water plane height. Later center selection is checked against the winning pixel ID.')
ordered('center-proof-after-surface-id', 'renderer', ['DrawWaterSurface(view,cache,', 'ReadBack(cache,surfaces.ids.Get()', 'result.picking.keys[key-1]==WorldViewHitKey::Plot(it->first)'],
        'Centers and contour spans come from the post-plane integer raster, never a different neighboring tile.')
require('ground-key-mode-and-water-package', 'reuse', ['key.waterSurface_=view.waterSurfaceAssetsPath;', 'if(!key.waterSurface_.empty())key.waterPackage_=view.waterAssetsPath;', 'waterSurface_!=view.waterSurfaceAssetsPath', '(!waterSurface_.empty()&&waterPackage_!=view.waterAssetsPath)'],
        'Plane mode/package and its water packet invalidate cached IDs and centers; empty legacy mode does not gain unrelated invalidations.')
ordered('frame-work-before-owner-publication', 'renderer', ['if(callerTarget)cache.context->CopyResource(callerTarget,finalColour);', 'cache.ground.Publish(', 'if(surfaceGeometryCandidate)activeSurface->geometry=std::move(surfaceGeometryCandidate);', 'if(surfaceTargetsCandidate)activeSurface->targets=std::move(surfaceTargetsCandidate);', 'if(surfaceCandidate)cache.waterSurface=std::move(surfaceCandidate);', '*frame=std::move(result);return true;'],
        'Potentially failing frame preparation/readback/caller copy precedes owner swaps; the old surface catalog/geometry/target set survives a candidate failure.')
require('private-size-keyed-targets', 'targets', ['width<=4096 && height<=4096', 'candidate->reflectionWidth=(mapWidth+1)/2;', 'candidate->reflectionHeight=(height+1)/2;', 'return candidate;'],
        'One bounded owner set, half reflection rounded up, full private refraction copies, candidate-only creation; runtime allocation remains unmeasured.')
require('unorm-sampling-and-explicit-gamma', 'targets', ['resource.Format=DXGI_FORMAT_B8G8R8A8_UNORM;', 'target.Format=DXGI_FORMAT_B8G8R8A8_UNORM_SRGB;'],
        'Private scene inputs expose stored encoded bytes through UNORM SRVs; reflection drawing uses sRGB RTV then explicit shader gamma.')
require('main-encoded-output-no-double-gamma', 'renderer', ['td.Format=fogEnabled||surfaceEnabled?DXGI_FORMAT_B8G8R8A8_TYPELESS', 'colorView.Format=DXGI_FORMAT_B8G8R8A8_UNORM;', '&next->colorRawView'],
        'Water shader encoded output binds a raw UNORM RTV, distinct from existing linear-terrain sRGB RTV; shore blend remains an explicit encoded-space policy.')
require('separate-copy-targets-compatible-families', 'targets', ['source.color.Get()!=destination.refractionColor.Get()', 'source.depth.Get()!=destination.refractionDepth.Get()', 'source.ids.Get()!=destination.refractionIds.Get()', 'DXGI_FORMAT_D32_FLOAT', 'DXGI_FORMAT_R32_UINT', 'D3D11_COMMONSHADER_INPUT_RESOURCE_SLOT_COUNT'],
        'Copy source and destination are distinct; single-sample shapes/format families are validated and OM/all PS SRVs detached before copies.')
ordered('main-ground-copy-water-river-unit-fog-order', 'renderer', ['if(groundData->original)DrawOriginalGround', 'CopyWaterRefractionInputs(cache,surfaces,*surfaceTargets);', 'DrawWaterSurface(view,cache,', 'if(waterEnabled)DrawOriginalWater', 'DrawTerrainUnits(cache,unitGroups);', 'if(fogEnabled)DrawOriginalFog'],
        'Refraction snapshots only current ground before any new water/rivers/units or FOW. Water and rivers retain terrain depth interactions; FOW owns final colour.')
ordered('refraction-same-positive-id-before-read', 'shader', ['if(pick==0)return fallback;', 'uint id=SceneId.Load(int3(at,0));if(id!=pick)return fallback;', 'float depth=SceneDepth.Load', 'depth<=p.p.z+0.0000001', 'source.y>=reflectionInfo.z)return fallback;', 'SceneColour.Load(int3(at,0))'],
        'No source colour/depth is consumed from hidden or neighboring tile IDs; accepted source must be behind the plane and reconstruct below it.')
require('refraction-map-clamp-and-finite-world', 'shader', ['int2(viewport.xy)-1', '(at.x+0.5)/viewport.x', 'inverseViewProjection', '!all(isfinite(source.xyz))'],
        'Displacement is clamped to map pixels rather than the sidebar and inverse-projects pixel centers through the same main VP.')
require('reflection-only-private-target', 'reflection', ['OMSetRenderTargets(1,&colour,targets.reflectionDepthView.Get())', 'ClearRenderTargetView(targets.reflectionView.Get(),transparent)', 'ClearDepthStencilView(targets.reflectionDepthView.Get()', 'XMMatrixReflect(XMVectorSet(0,1,0,-planeY))*mainVP'],
        'A mirrored row-vector VP renders into a transparent private half-resolution colour target and private depth. Main colour/depth/ID are never bound by this helper.')
require('reflection-state-explicit-first-draw', 'reflection', ['GSSetShader(nullptr,nullptr,0)', 'HSSetShader(nullptr,nullptr,0)', 'DSSetShader(nullptr,nullptr,0)', 'SOSetTargets(0,nullptr,nullptr);cache.context->SetPredication(nullptr,FALSE);'],
        'Latest Root update suppresses caller stream-output/predication state before the first reflection draw, matching the main pass setup.')
require('reflection-clip-buffer-and-zero-restore', 'reflection', ['const float reflectionClip[4]={planeY,1,0,0}', 'PSSetConstantBuffers(2,1,&clip)', 'const float noClip[4]={0,0,0,0}', 'UpdateSubresource(cache.constants.Get(),0,nullptr,&mainConstants'],
        'Reflection b2 clips below-plane geometry; RAII restores main camera, clip disabled, previous viewports, normal shaders/raster/depth/blend even on C++ exceptions.')
ordered('reflection-terrain-clip-before-material', 'terrain_shader', ['if(clipInfo.y>0.5 && p.height<clipInfo.x)discard;', 'if(state.y==0){if(clipInfo.y>0.5)discard;return o;}', 'Diffuse[i].Sample'],
        'Unknown reflection pixels are discarded before material sampling; below-plane terrain is also discarded before shading.')
require('reflection-visible-unit-source-only', 'units', ['if(plot.revealed&&plot.visible)', 'if(art==cache.units->arts.end()||plot==visible.end())continue;'],
        'Reflection cannot create unseen units: the common prepared groups contain only detached visible units.')
require('reflection-legacy-clip-before-texture', 'renderer', 'if(clipInfo.y>0.5 && (p.height<clipInfo.x||p.fog<0))discard;',
        'Legacy unit shader honors the same world-space below-plane/unknown reflection clip.')
ordered('units-prepared-once-reused-twice', 'renderer', ['const auto unitGroups=PrepareTerrainUnits(view,cache,*groundData,result);UploadTerrainUnits(cache,unitGroups);', 'DrawWaterReflection(view,cache,*groundData,unitGroups,', 'DrawTerrainUnits(cache,unitGroups);'],
        'Current unit pose buffers and stats are prepared once; reflection and main pass draw the same buffers without a second SDK capture/RNG call.')
require('reflection-no-recursion-no-reprepare', 'reflection', ['DrawOriginalGround(view,cache,*ground.original,false);', 'DrawTerrainUnits(cache,unitGroups);'],
        'The reflection helper draws only ground and prepared units. It never calls water/surface, SDK, animation, geometry preparation or frame metadata mutation.')
require('reflection-culling-union', 'terrain_gpu', ['if(view.waterSurfaceAssetsPath.empty())continue;', 'const auto reflected=XMMatrixReflect', 'const auto mirrored=XMVector3TransformCoord'],
        'Surface mode retains chunks visible in either main or reflected camera; existing finite bounds remain explicit limitations.')
require('slots-layout-match', 'gpu', ['bd.ByteWidth=sizeof(WaterSurfaceConstants)', 'PSSetShaderResources(0,11,resources)', 'PSSetSamplers(0,2,samplers)', 'DXGI_FORMAT_R16G16B16A16_UNORM:DXGI_FORMAT_R16_UNORM'],
        'b1 uses 272-byte CPU/HLSL layout; t0..t10 and s0..s1 match typed shader declarations and the 32-byte water vertex layout.')
require('layout-size-static-assert', 'types', 'static_assert(sizeof(WaterSurfaceConstants)==272',
        'Thirteen float4s plus inverse VP64 have an explicit 272-byte compile-time contract.')
require('surface-bindings-cleared-restored', 'gpu', ['PSSetShaderResources(0,11,empty)', 'PSSetSamplers(0,2,noSamplers)', 'VSSetConstantBuffers(1,1,&nullBuffer)', 'PSSetConstantBuffers(1,1,&nullBuffer)', 'OMSetDepthStencilState(cache.depthState.Get(),0)', 'PSSetShader(cache.ps.Get()'],
        'After water/shore draw, 11 SRVs, both samplers and b1 in both stages are unbound; legacy unit layout/shaders and normal write depth are restored.')
require('reflection-bindings-cleared', 'reflection', ['~RestoreReflectionState() noexcept', 'OMSetRenderTargets(0,nullptr,nullptr)', 'PSSetShaderResources(0,25,empty)', 'RSSetViewports(viewportCount'],
        'The private reflection image is unbound before consumption. Main b2 is explicitly reset and unbound before FOW.')
require('lean-decoded-scale-once', 'shader', ['mean=a.rg*2-1;second=float3(a.b,a.a,cross*2-1);', 'if(mirrorX){mean.x=-mean.x;second.z=-second.z;}', 'float2 weights=float2(0.5,0.5)/opticsInfo.x', 'covariance=second-float3(mean.x*mean.x,mean.y*mean.y,mean.x*mean.y)'],
        'Original channel/sign/mirror and covariance operations apply the candidate runtime scale only once after raw UNORM decoding; equal mixture weights are a candidate.')
require('optics-confirmed-operations-and-candidate-composite', 'shader', ['float diagonal=(wide?16.0:1.0)/k', 'if(!isfinite(q)||q>=16)return 0', 'base=screen-1+6*covariance.xy', 'float2(-2,6)*determinant', 'coverage=saturate(r.a)', 'saturate(deep.a*(1+coverage))', '0.4545454680919647216796875'],
        'Confirmed Gaussian/covariance offsets, gamma literals and original alpha factor are present. Cache camera, coverage fallback and opaque composite are separate current policies.')
require('presentation-path-explicit-opt-in', 'loop', ['L"ZEROSIS_WATER_SURFACE_ASSETS"', 'if(!waterSurfaceAssetsPath.empty()&&waterAssetsPath.empty())', 'view.waterSurfaceAssetsPath=waterSurfaceAssetsPath;'],
        'The new plane/LEAN mode requires an explicit private environment path plus existing water packet; no default runtime, game install or registration is changed.')
require('three-clocks-detached', 'dto', ['double animationSeconds=0.0;', 'double fogAnimationSeconds=0.0;', 'double waterAnimationSeconds=0.0;', 'std::wstring waterSurfaceAssetsPath;'],
        'Presentation clocks and surface asset path remain detached DTO tail fields with defaults; no SDK ABI/save schema migration is introduced.')
ordered('time-only-refresh-preserves-input-generation', 'loop', ['const auto refreshAnimation=[&](double seconds)', 'retainedView.waterAnimationSeconds=seconds;', 'RenderWorldViewToTexture(retainedView,device,context,target,&candidate,why,nullptr,false)', 'const auto generation=window.SceneGeneration();', 'window.SceneGeneration()!=generation'],
        'Animation-only refresh mutates detached clocks, reuses retained hit maps and explicitly rejects a changed input generation; it makes no new SDK call.')
require('public-sdk-no-new-lake-query', 'dto', 'bool lake=false; // Public ICvPlot1 has no lake classification query.',
        'Lake is still a detached default. This phase adds no private ABI query or guessed SDK vtable member.')
require('owner-release-reset', 'renderer', 'void ReleaseWorldTerrainResources(){GpuTerrainCache().reset();LegacyTerrainCache().reset();}',
        'Both render-owner caches release their references. Actual external-context binding/VRAM release is not established by source review and remains a GPU lifecycle gate.')

references = {}
for rel in [
    'evidence/world_terrain_original/phase4/review/build_tools_update.json',
    'evidence/world_terrain_original/phase4/requirements.json',
    'evidence/world_terrain_original/phase4/semantics/optics_contract.json',
    'evidence/world_terrain_original/phase4/optics/current.json',
    'evidence/world_terrain_original/phase4/model/current_surface.json',
    'evidence/world_terrain_original/phase4/pipeline/cpu/result.json',
    'evidence/world_terrain_original/phase4/cache_cpu/result.json',
    'evidence/world_terrain_original/phase4/shader/completion.json',
    'evidence/world_terrain_original/phase4/shader/integration_review.json',
]:
    if not (ROOT / rel).is_file():
        raise RuntimeError('Required retained reference missing: ' + rel)
    references[rel] = record(rel)

after = {k: record(v) for k, v in SOURCE.items()}
assert before == after, 'A reviewed source changed during review'
assert all(row['pass'] for row in checks), [r['name'] for r in checks if not r['pass']]
assert 'IsLake(' not in src['state']
assert all(clock not in src['reuse'] for clock in ['animationSeconds', 'fogAnimationSeconds', 'waterAnimationSeconds'])
assert 'WithCore(' not in src['loop'].split('const auto refreshAnimation=[&](double seconds)', 1)[1].split('publish();', 1)[0]
assert all(word not in src['reflection'] for word in ['PrepareTerrainUnits(', 'UploadTerrainUnits(', 'DrawWaterSurface(', 'DrawOriginalWater('])

result = {
    'schema': 'zerosis.original_water_surface.phase4.independent_integration_review.v1',
    'status': 'PASS_OFFLINE_SOURCE_INTEGRATION_REVIEW_WITH_RUNTIME_CALIBRATION_AND_GPU_GATES_OPEN',
    'method': 'Independent manual source/call-order/data-flow review pinned by exact SHA, with reproducible source-presence/order guards; these guards are not a GPU/runtime test.',
    'source_files_before': before,
    'source_files_after': after,
    'source_files_unchanged_during_review': True,
    'checks': checks,
    'checks_passed': len(checks),
    'blocking_findings': [],
    'findings': [],
    'references': references,
    'original_rules_and_candidate_limits': [
        'Original LEAN bit channels/sign/mirror, mixed moments/covariance, narrow/wide Gaussian regularization, four reflection taps and gamma literals have instruction-level evidence. Original D3D upload format remains a strong UNORM16 inference rather than a traced creation call.',
        'The original fixed surface shader reads cb1[12].x. Its runtime value and relation to CoastWaterline.Height remain untraced; .19836 and the current raw-height/world-Y mapping are explicit calibration candidates.',
        'Surface contour clipping follows the available atlas, shared deterministic crossings and bounded adaptive sampling. Original contour extraction, LOD resolution/order and coast profile application are not established.',
        'Current equal two-layer blend weights, scale/header relation, UV/time constants, light vectors/colours, roughness K values, Fresnel composite clamp, reflection camera/resolution/wrapping/coverage fallback and shoreline encoded-space blend are explicit policies requiring actual comparison.',
        'Selected original PS0/PS2 do not establish this separate screen-scene colour/depth refraction pair. The new same-positive-ID isolated-scene refraction, attenuation and displacement are implementation candidates, not a claim of original scene-refraction restoration.',
        'The original extra saturate(4h)*q2^3*DepthColour lighting term, complete original blend/light/shadow/FOW integration and cache pass scheduling/resolution are not restored by this phase. Current narrow+wide lobes for both lights also differ from the selected original lobe combination.',
        'Surface alpha uses the confirmed original factor saturate(DepthColour.a*(1+reflectionAlpha)), but applies it inside an opaque main-scene composite because the original blend state remains unknown.',
        'Piece placement remains: 규칙 동등, 배치 동등은 미검증.',
    ],
    'remaining_acceptance': [
        'Actual C++ compile/link and independent prepared-pair attestation must pin these final source bytes before a new offline build is accepted.',
        'No live D3D11 creation/copy/binding/depth/ID raster, sampler result, visual alignment, reflection/refraction acceptance, GPU performance or VRAM lifetime has been tested.',
        'Original runtime water height, optics parameters, cache producer coordinates and display parity require a separately authorized actual game/screen comparison.',
    ],
    'review_production_source_modified': False,
    'only_existing_files_modified_by_reviewer': ['tools/build_menu_suite_host.py', 'tools/attest_prepared_menu_host.py'],
    'review_generated_temporary_build_or_package_files': 0,
    'review_owned_artifacts': [str(Path(__file__)), str(OUT)],
    'host_gamecore_clr_hwnd_gpu_audio_or_game_executed': False,
    'native_or_shader_compiler_executed_by_this_review': False,
    'original_mods_settings_saves_default_runtime_registration_changed': False,
}
OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'status': result['status'], 'source_files': len(SOURCE), 'checks': len(checks),
                  'report_bytes': OUT.stat().st_size, 'sha256': hashlib.sha256(OUT.read_bytes()).hexdigest()}, ensure_ascii=False))
