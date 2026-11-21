"""Independent source/data-flow review. This does not execute a graphics API."""
from pathlib import Path
import hashlib,json,math,re,sys
sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[4]
sys.path.insert(0,str(PROJECT/'Tests'))
from original_water_shader import ref,write_new
ROOT=Path(__file__).parent
SRC=PROJECT/'Source/Presentation'

def digest(text):return hashlib.sha256(text.encode('utf8')).hexdigest()
def region(text,start,end):
    a=text.index(start);b=text.index(end,a);return text[a:b]
def independent_hex_checks():
    # Oracle enumerates physical hex centres in Euclidean space, rather than
    # reusing the shader's cube-coordinate rounding to choose its expected cell.
    def shader(x,row):
        q=x-row*.5;f=[q,row,-q-row]
        c=[int(math.copysign(math.floor(abs(v)+.5),v))for v in f]
        d=[abs(c[i]-f[i])for i in range(3)]
        if d[0]>d[1]and d[0]>d[2]:c[0]=-c[1]-c[2]
        elif d[1]>d[2]:c[1]=-c[0]-c[2]
        else:c[2]=-c[0]-c[1]
        return c[0]+math.floor(c[1]*.5),c[1]
    checked=0
    for y in range(-8,13):
        for x in range(-9,14):
            for dx,dy in ((0,0),(.1,.08),(-.14,.03),(.12,-.11)):
                wx=x+(y&1)*.5+dx;row=y+dy
                candidates=sorted(((wx-(a+(b&1)*.5))**2+(.866025404*(row-b))**2,a,b)
                    for b in range(y-2,y+3)for a in range(x-2,x+3))
                expected=candidates[0][1:];assert candidates[0][0]+1e-8<candidates[1][0]
                got=shader(wx,row);assert got==expected,(x,y,dx,dy,got,expected)
                for wrap in range(4):
                    width,height=7,6;actual=(got[0]%width if wrap&1 else got[0],got[1]%height if wrap&2 else got[1])
                    oracle=(x%width if wrap&1 else x,y%height if wrap&2 else y)
                    assert actual==oracle;checked+=1
    return dict(checks=checked,oracle='nearest physical hex centre; safe interior points; both axes/negative/unwrapped/wrapped coordinates',
        caveat='Exact boundary ties and raster coverage still require GPU acceptance; the oracle does not claim rasterization equivalence.')

def main():
    fixed_names=['OriginalDynamicShadowModel.h','OriginalDynamicShadowShader.h','OriginalDynamicShadowGpuTypes.inc','OriginalDynamicShadowGpu.inc']
    fixed=[ref(SRC/n)for n in fixed_names]
    model,shader,types,gpu=[(SRC/n).read_text('utf8')for n in fixed_names]
    renderer=(SRC/'WorldTerrainRenderer.cpp').read_text('utf8');renderer_ref=ref(SRC/'WorldTerrainRenderer.cpp')
    units=(SRC/'WorldTerrainUnits.inc').read_text('utf8');water=(SRC/'OriginalWaterSurfaceGpu.inc').read_text('utf8')
    water_shader=(SRC/'OriginalWaterSurfaceShader.h').read_text('utf8');terrain=(SRC/'OriginalTerrainGpu.inc').read_text('utf8')
    assert 'cb.ByteWidth=sizeof(DynamicShadowConstants)'in gpu and'sizeof(DynamicShadowConstants)==112'in types
    assert 'td.Width=td.Height=DS::CandidateResolution'in gpu and'td.ArraySize=td.MipLevels=1'in gpu
    assert 'td.Format=DXGI_FORMAT_R32_TYPELESS'in gpu and'DXGI_FORMAT_D32_FLOAT'in gpu and'DXGI_FORMAT_R32_FLOAT'in gpu
    assert 'OMSetRenderTargets(0,nullptr,shadow.depthView.Get())'in gpu
    assert not any(token in gpu for token in ('idView','colorView','surface->atlas','animationSeconds','CaptureWorld'))
    assert 'ShadowPlotState.Load(int3(cell,0)).y==0)discard;'in shader
    assert 'mul(float4(world,1),shadowViewProjection)'in shader and'row_major float4x4 shadowViewProjection'in shader
    assert 'std::memcpy(&params.viewProjection,shadow.projection.matrix.data(),64)'in gpu
    assert 'for(const auto& plot:view.plots)if(plot.revealed&&plot.visible)'in units
    assert renderer.count('UploadTerrainUnits(cache,unitGroups)')==1 and gpu.count('cache.unitBuffers.at(entry.first)')==1
    assert 'SampleDynamicShadow(p.local)'in water_shader and'lit=shadowed*(-0.67)+lit;'in water_shader
    assert 'cache.dynamicShadow?cache.dynamicShadow->depthResource.Get():nullptr'in water
    assert 'cache.context->PSSetConstantBuffers(5,1,&nullBuffer)'in water and'PSSetShaderResources(0,12,empty)'in water
    assert 'std::array<ID3D11ShaderResourceView*,43> resources'in terrain and'SampleDynamicShadow'not in(SRC/'OriginalTerrainShader.h').read_text('utf8')
    segments={
        'unit_upload_shadow_reflection_order':region(renderer,'const auto unitGroups=PrepareTerrainUnits','const float background[4]'),
        'main_marker_clear':region(renderer,'if(fogEnabled)cache.context->ClearRenderTargetView(surfaces.waterFragmentView.Get(),zero);','cache.context->ClearDepthStencilView(surfaces.depthView.Get()'),
        'main_surface_units_fog_order':region(renderer,'if(surfaceTargets){\n            CopyWaterRefractionInputs','ID3D11Texture2D* finalColour='),
        'embedded_unit_fallback_hlsl':re.search(r'R"HLSL\((.*?)\)HLSL"',renderer,re.S)[1]}
    s=segments['unit_upload_shadow_reflection_order'];assert s.index('UploadTerrainUnits')<s.index('DrawDynamicShadow')<s.index('DrawWaterReflection')
    s=segments['main_surface_units_fog_order'];assert s.index('DrawWaterSurface')<s.index('DrawTerrainUnits')<s.index('DrawOriginalFog')
    assert 'fogEnabled?5:1'in s and'surfaces.colorView.Get(),nullptr,nullptr,nullptr,surfaces.waterFragmentView.Get()'in s
    assert 'o.waterFragment=0;'in segments['embedded_unit_fallback_hlsl']
    cpu=ROOT/'cpu04/result.json';cpu_data=json.loads(cpu.read_text('utf8'));assert cpu_data['status']=='PASS_CPU_DYNAMIC_SHADOW'and cpu_data['checks']==1631
    for r in cpu_data['inputs']:assert ref(r['path'])['sha256']==r['sha256']
    strict=ROOT/'shader01/result.json';strict_data=json.loads(strict.read_text('utf8'));assert strict_data['status']=='PASS_STRICT_DYNAMIC_SHADOW_SHADERS'
    for r in strict_data['inputs']:assert ref(r['path'])['sha256']==r['sha256']
    cleanups=[]
    for stage in ('cpu01','cpu02','cpu03','cpu04','shader01'):
        p=ROOT/stage/'cleanup_result.json';d=json.loads(p.read_text('utf8'));assert d['status']=='PASS'
        # The plan records deleted physical file identities; verify absence of
        # every owned leaf instead of counting just the JSON receipt itself.
        plan=json.loads((ROOT/stage/'cleanup_plan.json').read_text('utf8'))
        rows=plan.get('files',plan.get('exact_owned_leaves',[]));assert rows
        for r in rows:assert not Path(r['path']).exists(),r['path']
        cleanups.append(ref(p))
    groups=[
        dict(name='orthographic row-vector fit',conclusion='Fit constructs matrix columns from right/up/forward axes, with translation in the final row. Direct 64-byte copy and row_major mul(world,matrix) agree. Reserve R/(R-1) before centre snapping covers a half-texel shift; fixed candidate margin keeps all fitted corners in range.',
            evidence=['OriginalDynamicShadowModel.h:27-51','OriginalDynamicShadowGpu.inc:34-45','OriginalDynamicShadowShader.h:6-15'],
            controlled_proof='Actual C++14 CPU04 tests project corners at resolutions16/64/512/2048/4096 and translated bounds; independent nearest-centre hex oracle below checks source coordinate conversion.'),
        dict(name='source privacy and current pose',conclusion='Only nonempty public chunk palettes form the conservative terrain bounds. Bounds use the legal normalized height range without reading source heights. Ground pixel kill tests the exact public PlotState before any depth write; the producer has no material or hidden-height sample. Units are filtered by revealed AND visible plot before preparing vertices. The one uploaded current-pose VB is reused by main, reflection and shadow; no animation advances or SDK capture happen in the producer.',
            evidence=['OriginalDynamicShadowGpu.inc:30-44,79-92','OriginalDynamicShadowShader.h:35-45','WorldTerrainUnits.inc:3-27','WorldTerrainRenderer.cpp unit_upload_shadow_reflection_order']),
        dict(name='one private bounded depth target',conclusion='One lazy candidate object per Cache creates a sample1/mip1/array1 2048x2048 R32_TYPELESS texture with D32_FLOAT DSV and R32_FLOAT SRV. Nominal texel payload is16,777,216 bytes, shared per cache and not per chunk. Only a private DSV is bound and cleared; neither main IDs, main colour nor picking metadata is touched. Local unique_ptr construction publishes only after every resource/shader/layout/CB creation succeeds.',
            evidence=['OriginalDynamicShadowGpu.inc:1-28,70-71'],driver_allocation_measured=False),
        dict(name='projection receiver and original coefficient',conclusion='Known water fragments alone call the receiver after exact plot/water-mask guards. Receiver uses b5 at112bytes, PS t11 and four explicit bounded integer depth loads, so it needs no new sampler. Outside frustum/disabled returns zero. Original attenuation expression remains lit + (-.67)*(saturate(sample)*strength*lit). Terrain keeps its separate existing macro-shadow field; no arbitrary max with dynamic shadows was added.',
            evidence=['OriginalDynamicShadowShader.h:9-23','OriginalWaterSurfaceShader.h exact known guard and SampleDynamicShadow call','OriginalTerrainGpu.inc PS resources0..42'],
            candidates=['2048 camera fit and margin','light vector/bias/PCF/border-tap interpretation','opaque unit silhouette','runtime strengths1']),
        dict(name='state and hazards',conclusion='Depth receiver PS slots11/43 are detached before private depth output. RAII detaches output, clears touched PS inputs, restores OM/RS/IA/VS/PS/b5 and saved t0/11/43; private depth is no longer bound as DSV before receivers use it. Producer explicitly disables GS/HS/DS, stream output and predication. Those remain disabled under renderer ownership; this is not a promise to preserve arbitrary external stream-output/predication state. Main/reflection fully bind their own pipeline afterward. Water clears12 inputs and PS b5 after consumption.',
            evidence=['OriginalDynamicShadowGpu.inc:46-79,87-95','WorldTerrainRenderer.cpp:main pipeline rebind','OriginalWaterSurfaceGpu.inc:83-108']),
        dict(name='disabled empty and repeat frames',conclusion='When neither lighting nor surface is enabled the producer is not called or consumed. On later re-enable the same private map is cleared and refilled. Empty bounds set enabled0 in uploaded b5; source loops have no nonempty groups, so a stale map cannot produce an enabled receiver. The lazy object may remain cached while disabled, avoiding repeated allocation.',
            evidence=['OriginalDynamicShadowModel.h:27-29','OriginalDynamicShadowGpu.inc:28-45,70-71,80-94','WorldTerrainRenderer.cpp producer enabled condition']),
        dict(name='marker and single post fog',conclusion='Water writes integer Target4 while true plot IDs remain Target1. Fog-only R8_UINT marker is cleared0 per frame. Only visible depth-passing unit pixels overwrite marker0, with picking RTV unbound; failed depth tests preserve the water marker. Fog reads marker only after exact explored-state guard and immediately returns its water formula, avoiding duplicate land fog. Reflection binds colour only, so marker and main IDs cannot be overwritten there.',
            evidence=['WorldTerrainRenderer.cpp main_marker_clear/main_surface_units_fog_order/embedded_unit_fallback_hlsl','OriginalWaterSurfaceGpu.inc:89-100','OriginalFogShader.h water branch'],authorship_note='Root marker/renderer/producer integration reviewed independently; water receiver/FOW helpers were authored by this reviewer and separately compiled/tested.'),
        dict(name='retired failed CPU fixtures and cleanup',conclusion='cpu01/cpu02 failure records are explicitly retired after discovering the low-resolution snapped-fit corner issue; the fixed model includes reserve and current cpu04 recompiled1631 checks. Every exact owned build/shader leaf recorded by all five cleanup plans is absent. The existing failed records remain distinguishable from current passing evidence.',
            evidence=[str(p.relative_to(PROJECT))for p in (ROOT/'cpu01/failure.json',ROOT/'cpu02/failure.json',cpu,strict)])]
    assert fixed==[ref(SRC/n)for n in fixed_names]
    current=(SRC/'WorldTerrainRenderer.cpp').read_text('utf8')
    for name,value in segments.items():
        if name=='embedded_unit_fallback_hlsl':assert re.search(r'R"HLSL\((.*?)\)HLSL"',current,re.S)[1]==value
        else:assert value in current
    output=ROOT/'shadow_independent_review.json'
    result=dict(schema='zerosis.original_dynamic_shadow.phase8.independent_source_review.v1',status='PASS_INDEPENDENT_REVIEW_NO_BLOCKING_DEFECT_FOUND',
        fixed_production_inputs=fixed,renderer_snapshot_provisional=renderer_ref,renderer_final_source_seal='PENDING_ROOT_SCREEN_LIGHTING_INTEGRATION',
        renderer_stable_region_sha256={k:digest(v)for k,v in segments.items()},related_sources_read=[ref(SRC/n)for n in ('WorldTerrainUnits.inc','OriginalWaterSurfaceShader.h','OriginalWaterSurfaceGpu.inc','OriginalFogShader.h','OriginalTerrainGpu.inc','OriginalTerrainShader.h','OriginalWaterReflection.inc')],
        groups=groups,independent_source_coordinate_oracle=independent_hex_checks(),controlled_tests=[ref(cpu),ref(strict)],cleanup_receipts=cleanups,
        blocking_defects=[],retail_hardware_blend_state_verified=False,new_retail_om_state_proof=False,
        limitations=['Source review and offline console/FXC checks cannot prove GPU rasterization, visual quality, frame time or original state equality.',
            'Private shadow producer camera/format/resolution/bias and runtime parameter choices remain candidates.',
            'Original WaterPS attenuation equation is supported separately; it does not establish retail shadow-camera or OM blend state.'],
        native_host_gamecore_clr_hwnd_gpu_audio_or_game_executed=False,source_modified=False)
    write_new(output,result);print(json.dumps(dict(status=result['status'],groups=len(groups),coordinate_checks=result['independent_source_coordinate_oracle']['checks'],report=ref(output))))

if __name__=='__main__':main()
