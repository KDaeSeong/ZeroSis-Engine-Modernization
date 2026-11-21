// Included after Cache and OriginalLightingGpuTypes.inc in the private renderer.
// Construction is transactional: only the completed candidate is published.
std::unique_ptr<LightingCatalog> LoadLightingCatalog(Cache& cache,const std::wstring& path){
    Reader input(path);const auto package=LG::DecodePackage(std::move(input.data),LG::LightingPackageSha256);
    auto result=std::make_unique<LightingCatalog>();result->path=path;
    std::array<ComPtr<ID3D11ShaderResourceView>,15> uploaded;
    for(unsigned role=1;role<=15;++role){
        const auto& asset=LG::FindAsset(package,static_cast<LG::AssetRole>(role));auto& view=uploaded[asset.blobIndex];
        if(!view){
            if(role<=10){
                const auto& cube=asset.cube;D3D11_TEXTURE2D_DESC td{};
                td.Width=cube.width;td.Height=cube.height;td.MipLevels=cube.mips;td.ArraySize=6;
                td.Format=DXGI_FORMAT_BC1_UNORM;td.SampleDesc.Count=1;td.Usage=D3D11_USAGE_IMMUTABLE;
                td.BindFlags=D3D11_BIND_SHADER_RESOURCE;td.MiscFlags=D3D11_RESOURCE_MISC_TEXTURECUBE;
                std::vector<D3D11_SUBRESOURCE_DATA> initial;initial.reserve(cube.levels.size());
                for(const auto& level:cube.levels)initial.push_back({package.bytes.data()+level.offset,static_cast<UINT>(level.rowPitch),static_cast<UINT>(level.bytes)});
                ComPtr<ID3D11Texture2D> texture;Check(cache.device->CreateTexture2D(&td,initial.data(),&texture),"Original irradiance cube upload");
                D3D11_SHADER_RESOURCE_VIEW_DESC sd{};sd.Format=DXGI_FORMAT_BC1_UNORM;sd.ViewDimension=D3D11_SRV_DIMENSION_TEXTURECUBE;
                sd.TextureCube.MipLevels=cube.mips;Check(cache.device->CreateShaderResourceView(texture.Get(),&sd,&view),"Original irradiance cube view");
            }else{
                const auto rgba=LG::CandidateTerrainLut32Rgba(package,role-11);D3D11_TEXTURE3D_DESC td{};
                td.Width=td.Height=td.Depth=LG::CandidateTerrainLutSide;td.MipLevels=1;td.Format=DXGI_FORMAT_R8G8B8A8_UNORM;
                td.Usage=D3D11_USAGE_IMMUTABLE;td.BindFlags=D3D11_BIND_SHADER_RESOURCE;
                const D3D11_SUBRESOURCE_DATA initial{rgba.data(),LG::CandidateTerrainLutSide*4,LG::CandidateTerrainLutSide*LG::CandidateTerrainLutSide*4};
                ComPtr<ID3D11Texture3D> texture;Check(cache.device->CreateTexture3D(&td,&initial,&texture),"Candidate original terrain LUT upload");
                Check(cache.device->CreateShaderResourceView(texture.Get(),nullptr,&view),"Candidate original terrain LUT view");
            }
        }
        if(role<=5)result->sunlight[role-1]=view;
        else if(role<=10)result->shadowlight[role-6]=view;
        else result->terrainLut[role-11]=view;
    }
    const auto cacheDescription=OriginalTerrainCache::NormalCacheDescriptor();
    D3D11_SAMPLER_DESC sampler{};sampler.Filter=static_cast<D3D11_FILTER>(cacheDescription.filter);
    sampler.AddressU=static_cast<D3D11_TEXTURE_ADDRESS_MODE>(cacheDescription.addressU);
    sampler.AddressV=static_cast<D3D11_TEXTURE_ADDRESS_MODE>(cacheDescription.addressV);
    sampler.AddressW=static_cast<D3D11_TEXTURE_ADDRESS_MODE>(cacheDescription.addressW);sampler.MaxAnisotropy=1;
    sampler.ComparisonFunc=D3D11_COMPARISON_NEVER;sampler.MaxLOD=D3D11_FLOAT32_MAX;
    Check(cache.device->CreateSamplerState(&sampler,&result->clampSampler),"Original lighting linear clamp sampler");
    D3D11_BUFFER_DESC bd{};bd.ByteWidth=sizeof(OriginalLightingConstants);bd.Usage=D3D11_USAGE_DEFAULT;bd.BindFlags=D3D11_BIND_CONSTANT_BUFFER;
    Check(cache.device->CreateBuffer(&bd,nullptr,&result->constants),"Original lighting constants");return result;
}
