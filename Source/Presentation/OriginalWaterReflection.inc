void DrawWaterReflection(Cache& cache,const GroundData& ground,
    const std::map<unsigned,Group>& unitGroups,SurfaceTargets& targets,const XMMATRIX& mainVP,float planeY){
    Require(ground.original&&cache.clipConstants.Get()&&targets.reflectionView.Get()&&targets.reflectionDepthView.Get()&&
        targets.reflectionWidth>0&&targets.reflectionHeight>0&&targets.reflectionWidth<=4096&&targets.reflectionHeight<=4096&&
        std::isfinite(planeY)&&std::abs(planeY)<=1000000,"Invalid isolated water reflection inputs");
    XMFLOAT4X4 mainConstants;XMStoreFloat4x4(&mainConstants,mainVP);
    struct RestoreReflectionState final {
        Cache& cache;XMFLOAT4X4 mainConstants;
        std::array<D3D11_VIEWPORT,D3D11_VIEWPORT_AND_SCISSORRECT_OBJECT_COUNT_PER_PIPELINE> viewports{};
        UINT viewportCount=D3D11_VIEWPORT_AND_SCISSORRECT_OBJECT_COUNT_PER_PIPELINE;
        RestoreReflectionState(Cache& value,const XMFLOAT4X4& matrix):cache(value),mainConstants(matrix){
            cache.context->RSGetViewports(&viewportCount,viewports.data());
        }
        ~RestoreReflectionState() noexcept {
            cache.context->OMSetRenderTargets(0,nullptr,nullptr);
            ID3D11ShaderResourceView* empty[45]{};cache.context->PSSetShaderResources(0,45,empty);
            ID3D11Buffer* noLighting=nullptr;cache.context->PSSetConstantBuffers(3,1,&noLighting);
            cache.context->PSSetConstantBuffers(6,1,&noLighting);
            ID3D11SamplerState* noLightingSampler=nullptr;cache.context->PSSetSamplers(1,1,&noLightingSampler);
            cache.context->PSSetSamplers(5,1,&noLightingSampler);
            cache.context->UpdateSubresource(cache.constants.Get(),0,nullptr,&mainConstants,0,0);
            ID3D11Buffer* camera=cache.constants.Get();cache.context->VSSetConstantBuffers(0,1,&camera);
            const float noClip[4]={0,0,0,0};cache.context->UpdateSubresource(cache.clipConstants.Get(),0,nullptr,noClip,0,0);
            ID3D11Buffer* clip=cache.clipConstants.Get();cache.context->PSSetConstantBuffers(2,1,&clip);
            cache.context->RSSetViewports(viewportCount,viewportCount?viewports.data():nullptr);
            cache.context->RSSetState(cache.raster.Get());cache.context->OMSetDepthStencilState(cache.depthState.Get(),0);
            cache.context->OMSetBlendState(cache.blendState.Get(),nullptr,0xffffffffu);
            cache.context->IASetInputLayout(cache.layout.Get());cache.context->VSSetShader(cache.vs.Get(),nullptr,0);
            cache.context->PSSetShader(cache.ps.Get(),nullptr,0);
            ID3D11SamplerState* sampler=cache.sampler.Get();cache.context->PSSetSamplers(0,1,&sampler);
        }
    } restore(cache,mainConstants);

    // A retained reflection SRV from a previous frame must be unbound before
    // this private image becomes a render target. No main colour/depth/ID
    // resource is bound or cleared by this pass.
    ID3D11ShaderResourceView* empty[45]{};cache.context->PSSetShaderResources(0,45,empty);
    const float transparent[4]={0,0,0,0};
    cache.context->ClearRenderTargetView(targets.reflectionView.Get(),transparent);
    cache.context->ClearDepthStencilView(targets.reflectionDepthView.Get(),D3D11_CLEAR_DEPTH,1,0);
    ID3D11RenderTargetView* colour=targets.reflectionView.Get();
    cache.context->OMSetRenderTargets(1,&colour,targets.reflectionDepthView.Get());
    cache.context->OMSetDepthStencilState(cache.depthState.Get(),0);
    cache.context->OMSetBlendState(cache.blendState.Get(),nullptr,0xffffffffu);
    cache.context->RSSetState(cache.raster.Get());
    const D3D11_VIEWPORT viewport{0,0,static_cast<float>(targets.reflectionWidth),static_cast<float>(targets.reflectionHeight),0,1};
    cache.context->RSSetViewports(1,&viewport);
    cache.context->IASetPrimitiveTopology(D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST);
    cache.context->IASetInputLayout(cache.layout.Get());cache.context->VSSetShader(cache.vs.Get(),nullptr,0);
    cache.context->PSSetShader(cache.ps.Get(),nullptr,0);
    cache.context->GSSetShader(nullptr,nullptr,0);cache.context->HSSetShader(nullptr,nullptr,0);cache.context->DSSetShader(nullptr,nullptr,0);
    cache.context->SOSetTargets(0,nullptr,nullptr);cache.context->SetPredication(nullptr,FALSE);
    ID3D11SamplerState* sampler=cache.sampler.Get();cache.context->PSSetSamplers(0,1,&sampler);

    const XMMATRIX mirrorVP=XMMatrixReflect(XMVectorSet(0,1,0,-planeY))*mainVP;
    XMFLOAT4X4 reflectedConstants;XMStoreFloat4x4(&reflectedConstants,mirrorVP);
    // Until the retail bounds/axis producer is available, this remains a
    // candidate camera. The water consumer must use this exact producer,
    // rather than reconstructing reflection UVs from its main-screen pixels.
    targets.reflectionViewProjection=reflectedConstants;targets.reflectionProjectionValid=true;
    cache.context->UpdateSubresource(cache.constants.Get(),0,nullptr,&reflectedConstants,0,0);
    ID3D11Buffer* camera=cache.constants.Get();cache.context->VSSetConstantBuffers(0,1,&camera);
    const float reflectionClip[4]={planeY,1,0,0};
    cache.context->UpdateSubresource(cache.clipConstants.Get(),0,nullptr,reflectionClip,0,0);
    ID3D11Buffer* clip=cache.clipConstants.Get();cache.context->PSSetConstantBuffers(2,1,&clip);

    // Original Raw callbacks are units, wonders, landmarks and ice. Terrain
    // and forests are not fallback reflection providers. Missing providers
    // stay absent until their own geometry and submission contracts exist.
    const auto scenes=OriginalReflection::MakePlan(OriginalReflection::SceneMask,
        static_cast<unsigned>(OriginalReflection::Scene::Units));
    if(OriginalReflection::Includes(scenes,OriginalReflection::Scene::Units))
        DrawTerrainUnits(cache,unitGroups);
}
