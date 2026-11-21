std::unique_ptr<FogCatalog> LoadFogCatalog(Cache& cache,const std::wstring& path){
    Reader input(path);
    const auto package=OF::DecodePackage(std::move(input.data),OF::PackageSha256);
    auto result=std::make_unique<FogCatalog>();result->path=path;result->colour=package.fogColour;
    for(unsigned i=0;i<result->textures.size();++i){
        const auto& texture=OF::FindAsset(package,static_cast<OF::AssetRole>(i+1)).texture;
        D3D11_TEXTURE2D_DESC td{};td.Width=texture.width;td.Height=texture.height;td.MipLevels=texture.mips;
        td.ArraySize=1;td.SampleDesc.Count=1;td.Usage=D3D11_USAGE_IMMUTABLE;td.BindFlags=D3D11_BIND_SHADER_RESOURCE;
        td.Format=texture.format==OF::TextureFormat::Bc1?DXGI_FORMAT_BC1_UNORM:
            texture.format==OF::TextureFormat::Bc3?DXGI_FORMAT_BC3_UNORM:DXGI_FORMAT_B8G8R8A8_UNORM;
        std::vector<D3D11_SUBRESOURCE_DATA> levels;
        for(const auto& level:texture.levels)levels.push_back({package.bytes.data()+level.offset,static_cast<UINT>(level.rowPitch),0});
        ComPtr<ID3D11Texture2D> image;Check(cache.device->CreateTexture2D(&td,levels.data(),&image),"Original fog texture upload");
        Check(cache.device->CreateShaderResourceView(image.Get(),nullptr,&result->textures[i]),"Original fog texture view");
    }
    const auto lut=OF::CandidateFowLut32Rgba(package);
    D3D11_TEXTURE3D_DESC volume{};volume.Width=volume.Height=volume.Depth=32;volume.MipLevels=1;
    volume.Format=DXGI_FORMAT_R8G8B8A8_UNORM;volume.Usage=D3D11_USAGE_IMMUTABLE;volume.BindFlags=D3D11_BIND_SHADER_RESOURCE;
    const D3D11_SUBRESOURCE_DATA initial{lut.data(),32*4,32*32*4};ComPtr<ID3D11Texture3D> image;
    Check(cache.device->CreateTexture3D(&volume,&initial,&image),"Original candidate FOW colour LUT upload");
    Check(cache.device->CreateShaderResourceView(image.Get(),nullptr,&result->lut),"Original FOW colour LUT view");
    ComPtr<ID3DBlob> vsBytes,psBytes,underlayBytes,diagnostic;
    const UINT flags=D3DCOMPILE_ENABLE_STRICTNESS|D3DCOMPILE_WARNINGS_ARE_ERRORS;
    Check(D3DCompile(OF::ShaderSource,sizeof(OF::ShaderSource)-1,"OriginalFog",nullptr,nullptr,"vertexMain","vs_5_0",
        flags,0,&vsBytes,&diagnostic),"Original fog vertex shader compilation");
    Check(D3DCompile(OF::ShaderSource,sizeof(OF::ShaderSource)-1,"OriginalFog",nullptr,nullptr,"pixelMain","ps_5_0",
        flags,0,&psBytes,&diagnostic),"Original fog pixel shader compilation");
    Check(D3DCompile(OF::ShaderSource,sizeof(OF::ShaderSource)-1,"OriginalFog",nullptr,nullptr,"underlayMain","ps_5_0",
        flags,0,&underlayBytes,&diagnostic),"Original fog underlay pixel shader compilation");
    Check(cache.device->CreateVertexShader(vsBytes->GetBufferPointer(),vsBytes->GetBufferSize(),nullptr,&result->vs),"Original fog vertex shader");
    Check(cache.device->CreatePixelShader(psBytes->GetBufferPointer(),psBytes->GetBufferSize(),nullptr,&result->ps),"Original fog pixel shader");
    Check(cache.device->CreatePixelShader(underlayBytes->GetBufferPointer(),underlayBytes->GetBufferSize(),nullptr,&result->underlayPs),"Original fog underlay pixel shader");
    D3D11_BUFFER_DESC cb{};cb.ByteWidth=sizeof(FogConstants);cb.Usage=D3D11_USAGE_DEFAULT;cb.BindFlags=D3D11_BIND_CONSTANT_BUFFER;
    Check(cache.device->CreateBuffer(&cb,nullptr,&result->constants),"Original fog constants");
    D3D11_SAMPLER_DESC sd{};sd.Filter=D3D11_FILTER_MIN_MAG_MIP_LINEAR;sd.MaxLOD=D3D11_FLOAT32_MAX;
    sd.AddressU=sd.AddressV=sd.AddressW=D3D11_TEXTURE_ADDRESS_CLAMP;sd.ComparisonFunc=D3D11_COMPARISON_NEVER;
    Check(cache.device->CreateSamplerState(&sd,&result->clampSampler),"Original fog clamp sampler");
    sd.AddressU=sd.AddressV=sd.AddressW=D3D11_TEXTURE_ADDRESS_WRAP;
    Check(cache.device->CreateSamplerState(&sd,&result->wrapSampler),"Original fog wrap sampler");
    D3D11_DEPTH_STENCIL_DESC depth{};depth.DepthEnable=FALSE;depth.DepthWriteMask=D3D11_DEPTH_WRITE_MASK_ZERO;depth.DepthFunc=D3D11_COMPARISON_ALWAYS;
    Check(cache.device->CreateDepthStencilState(&depth,&result->depthDisabled),"Original fog depth disabled state");
    return result;
}

std::unique_ptr<FogMask> PrepareFogMask(Cache& cache,OF::Grid key){
    const auto mask=OF::BuildMask(key);
    std::vector<unsigned char> rgba(mask.texels.size()*4);
    const auto byte=[](float value){return static_cast<unsigned char>(std::floor(std::max(0.0f,std::min(1.0f,value))*255+0.5f));};
    for(std::size_t i=0;i<mask.texels.size();++i){
        const auto& value=mask.texels[i];rgba[i*4]=byte(value.r);rgba[i*4+1]=byte(value.g);rgba[i*4+2]=byte(value.b);rgba[i*4+3]=255;
    }
    auto result=std::make_unique<FogMask>();result->key=std::move(key);
    D3D11_TEXTURE2D_DESC td{};td.Width=mask.width;td.Height=mask.height;td.MipLevels=td.ArraySize=1;td.SampleDesc.Count=1;
    td.Format=DXGI_FORMAT_R8G8B8A8_UNORM;td.Usage=D3D11_USAGE_IMMUTABLE;td.BindFlags=D3D11_BIND_SHADER_RESOURCE;
    const D3D11_SUBRESOURCE_DATA initial{rgba.data(),mask.width*4,0};ComPtr<ID3D11Texture2D> texture;
    Check(cache.device->CreateTexture2D(&td,&initial,&texture),"Original state-only fog mask upload");
    Check(cache.device->CreateShaderResourceView(texture.Get(),nullptr,&result->texture),"Original fog mask view");
    D3D11_SAMPLER_DESC sd{};sd.Filter=D3D11_FILTER_MIN_MAG_MIP_LINEAR;sd.MaxLOD=D3D11_FLOAT32_MAX;
    sd.AddressU=result->key.wrapX?D3D11_TEXTURE_ADDRESS_WRAP:D3D11_TEXTURE_ADDRESS_CLAMP;
    sd.AddressV=result->key.wrapY?D3D11_TEXTURE_ADDRESS_WRAP:D3D11_TEXTURE_ADDRESS_CLAMP;
    sd.AddressW=D3D11_TEXTURE_ADDRESS_CLAMP;sd.ComparisonFunc=D3D11_COMPARISON_NEVER;
    Check(cache.device->CreateSamplerState(&sd,&result->sampler),"Original fog mask address sampler");
    return result;
}

void DrawOriginalFog(const WorldView& view,Cache& cache,FrameTargets& surfaces,FogCatalog& fog,const FogMask& mask,
    const OriginalGroundData& ground,const XMMATRIX& matrix,float cameraDistance,unsigned mapWidth,unsigned height,bool underlay=false){
    // Preserve pixels outside the map viewport. The post-pass owns colour only;
    // the integer picking target and its readback/generation are never bound.
    cache.context->OMSetRenderTargets(0,nullptr,nullptr);
    cache.context->CopyResource(surfaces.fogColor.Get(),surfaces.color.Get());
    FogConstants constants{};XMVECTOR determinant;const auto inverse=XMMatrixInverse(&determinant,matrix);
    XMStoreFloat4x4(&constants.inverseViewProjection,inverse);
    constants.viewport[0]=static_cast<float>(mapWidth);constants.viewport[1]=static_cast<float>(height);
    constants.viewport[2]=static_cast<float>(view.cameraX)+static_cast<float>(view.cameraY&1)*0.5f;
    constants.viewport[3]=-static_cast<float>(view.cameraY)*OT::RowSpacing;
    constants.mapInfo[0]=static_cast<float>(view.gridWidth);constants.mapInfo[1]=static_cast<float>(view.gridHeight);
    constants.mapInfo[2]=view.wrapX?1.0f:0.0f;constants.mapInfo[3]=view.wrapY?1.0f:0.0f;
    constants.camera[1]=cameraDistance*0.65f;constants.camera[2]=-cameraDistance*0.7599342f;
    constants.camera[3]=static_cast<float>(view.fogAnimationSeconds);
    constants.distance[0]=OF::CandidateHeightK;constants.distance[1]=OF::CandidateDensity;
    constants.distance[2]=OF::CandidateRampRow;constants.distance[3]=OT::RetailWorldUnitsPerHexCandidate;
    for(unsigned channel=0;channel<3;++channel)constants.colour[channel]=fog.colour[channel];
    constants.colour[3]=1;
    for(unsigned layer=0;layer<3;++layer){const auto& flow=OF::CandidateFlowLayers[layer];
        constants.flow[layer][0]=static_cast<float>(flow.scale);constants.flow[layer][1]=static_cast<float>(flow.speedU);
        constants.flow[layer][2]=static_cast<float>(flow.speedV);constants.flow[layer][3]=static_cast<float>(flow.phaseU);
        constants.phase[layer]=static_cast<float>(flow.phaseV);
    }
    constants.phase[3]=OF::CandidateFlowDisplacement;
    std::copy(std::begin(OriginalWaterFog::CandidateOverlay),std::end(OriginalWaterFog::CandidateOverlay),constants.waterOverlay);
    cache.context->UpdateSubresource(fog.constants.Get(),0,nullptr,&constants,0,0);
    ID3D11RenderTargetView* targets[]={surfaces.fogColorView.Get(),surfaces.waterFragmentView.Get()};
    cache.context->OMSetRenderTargets(underlay?2:1,targets,nullptr);
    cache.context->OMSetDepthStencilState(fog.depthDisabled.Get(),0);
    cache.context->OMSetBlendState(cache.blendState.Get(),nullptr,0xffffffffu);
    cache.context->IASetInputLayout(nullptr);cache.context->IASetIndexBuffer(nullptr,DXGI_FORMAT_UNKNOWN,0);
    ID3D11Buffer* nullBuffer=nullptr;const UINT zero=0;cache.context->IASetVertexBuffers(0,1,&nullBuffer,&zero,&zero);
    cache.context->VSSetShader(fog.vs.Get(),nullptr,0);cache.context->PSSetShader(underlay?fog.underlayPs.Get():fog.ps.Get(),nullptr,0);
    ID3D11Buffer* cb=fog.constants.Get();cache.context->PSSetConstantBuffers(0,1,&cb);
    ID3D11SamplerState* samplers[]={fog.clampSampler.Get(),fog.wrapSampler.Get(),mask.sampler.Get()};cache.context->PSSetSamplers(0,3,samplers);
    ID3D11ShaderResourceView* resources[]={surfaces.colorResource.Get(),surfaces.depthResource.Get(),mask.texture.Get(),ground.plotState.Get(),
        fog.textures[0].Get(),fog.textures[1].Get(),fog.textures[2].Get(),fog.textures[3].Get(),fog.textures[4].Get(),fog.lut.Get(),fog.textures[5].Get(),underlay?nullptr:surfaces.waterFragmentResource.Get()};
    cache.context->PSSetShaderResources(0,12,resources);cache.context->Draw(3,0);
    cache.context->OMSetRenderTargets(0,nullptr,nullptr);
    ID3D11ShaderResourceView* empty[12]{};cache.context->PSSetShaderResources(0,12,empty);
    ID3D11SamplerState* noSamplers[3]{};cache.context->PSSetSamplers(0,3,noSamplers);
    cache.context->PSSetConstantBuffers(0,1,&nullBuffer);
    cache.context->VSSetConstantBuffers(0,1,&nullBuffer);
    cache.context->VSSetShader(nullptr,nullptr,0);cache.context->PSSetShader(nullptr,nullptr,0);
    cache.context->OMSetDepthStencilState(nullptr,0);
    if(underlay)cache.context->CopyResource(surfaces.color.Get(),surfaces.fogColor.Get());
}
