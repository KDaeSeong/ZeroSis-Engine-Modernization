// Included after ScreenLightingGpu and the private renderer Check helper.
ScreenLightingGpu CreateScreenLightingGpu(ID3D11Device* device){
    Require(device!=nullptr,"Screen reflection device is unavailable");
    ScreenLightingGpu result;D3D11_BUFFER_DESC buffer{};
    buffer.ByteWidth=sizeof(OSL::Constants);buffer.Usage=D3D11_USAGE_DEFAULT;
    buffer.BindFlags=D3D11_BIND_CONSTANT_BUFFER;
    Check(device->CreateBuffer(&buffer,nullptr,&result.constants),"Screen reflection constants");
    D3D11_SAMPLER_DESC sampler{};sampler.Filter=D3D11_FILTER_MIN_MAG_MIP_LINEAR;
    sampler.AddressU=sampler.AddressV=sampler.AddressW=D3D11_TEXTURE_ADDRESS_CLAMP;
    sampler.MaxAnisotropy=1;sampler.ComparisonFunc=D3D11_COMPARISON_NEVER;
    sampler.MaxLOD=D3D11_FLOAT32_MAX;
    Check(device->CreateSamplerState(&sampler,&result.sampler),"Original screen light linear clamp sampler");
    return result;
}
void BindScreenLighting(ID3D11DeviceContext* context,ScreenLightingGpu& gpu,
    ID3D11ShaderResourceView* reflection,unsigned width,unsigned height,
    const OSL::Policy& policy){
    Require(context && gpu.constants && gpu.sampler,"Screen reflection binding is incomplete");
    const auto constants=OSL::MakeConstants(width,height,policy,reflection!=nullptr);
    context->UpdateSubresource(gpu.constants.Get(),0,nullptr,&constants,0,0);
    ID3D11Buffer* buffer=gpu.constants.Get();context->PSSetConstantBuffers(6,1,&buffer);
    ID3D11SamplerState* sampler=gpu.sampler.Get();context->PSSetSamplers(5,1,&sampler);
    ID3D11ShaderResourceView* view=constants.flags[0]>.5f?reflection:nullptr;
    context->PSSetShaderResources(44,1,&view);
}
void UnbindScreenLighting(ID3D11DeviceContext* context){
    Require(context!=nullptr,"Screen reflection context is unavailable");
    ID3D11ShaderResourceView* view=nullptr;context->PSSetShaderResources(44,1,&view);
}

std::unique_ptr<ScreenLightCatalog> LoadOriginalScreenLightCatalog(Cache& cache,const std::wstring& path){
    Reader input(path);
    const auto package=OriginalScreenLightAssets::DecodePackage(std::move(input.data),OriginalScreenLightAssets::PackageSha256);
    auto result=std::make_unique<ScreenLightCatalog>();result->path=path;
    const auto& source=package.texture;
    D3D11_TEXTURE2D_DESC texture{};texture.Width=source.width;texture.Height=source.height;
    texture.MipLevels=source.mips;texture.ArraySize=1;texture.Format=DXGI_FORMAT_BC3_UNORM;
    texture.SampleDesc.Count=1;texture.Usage=D3D11_USAGE_IMMUTABLE;texture.BindFlags=D3D11_BIND_SHADER_RESOURCE;
    std::vector<D3D11_SUBRESOURCE_DATA> levels;
    for(const auto& level:source.levels)
        levels.push_back({package.bytes.data()+level.offset,static_cast<UINT>(level.rowPitch),static_cast<UINT>(level.bytes)});
    ComPtr<ID3D11Texture2D> image;
    Check(cache.device->CreateTexture2D(&texture,levels.data(),&image),"Original specscreenmap BC3 mip upload");
    D3D11_SHADER_RESOURCE_VIEW_DESC view{};view.Format=DXGI_FORMAT_BC3_UNORM;
    view.ViewDimension=D3D11_SRV_DIMENSION_TEXTURE2D;view.Texture2D.MipLevels=source.mips;
    Check(cache.device->CreateShaderResourceView(image.Get(),&view,&result->texture),"Original specscreenmap UNORM view");
    return result;
}
