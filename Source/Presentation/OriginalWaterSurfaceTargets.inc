void CreateSceneReflectionImages(Cache& cache,SurfaceTargets& target,unsigned side=OSL::OriginalReflectionSide){
    // The original Reflection Texture Raw producer allocates 1024x1024.
    // RGBA8 typeless/UNORM sampling is recovered; the mirrored camera and
    // water plane remain isolated policies pending original matrix inputs.
    Require(side==OSL::OriginalReflectionSide||side==OSL::OriginalDisabledReflectionSide,"Invalid original reflection allocation side");
    target.reflectionWidth=target.reflectionHeight=side;
    D3D11_TEXTURE2D_DESC texture{};texture.Width=target.reflectionWidth;texture.Height=target.reflectionHeight;
    texture.MipLevels=texture.ArraySize=1;texture.SampleDesc.Count=1;texture.Usage=D3D11_USAGE_DEFAULT;
    texture.Format=DXGI_FORMAT_R8G8B8A8_TYPELESS;texture.BindFlags=D3D11_BIND_RENDER_TARGET|D3D11_BIND_SHADER_RESOURCE;
    Check(cache.device->CreateTexture2D(&texture,nullptr,&target.reflectionColor),"Isolated scene reflection colour target");
    D3D11_RENDER_TARGET_VIEW_DESC view{};view.Format=DXGI_FORMAT_R8G8B8A8_UNORM_SRGB;view.ViewDimension=D3D11_RTV_DIMENSION_TEXTURE2D;
    Check(cache.device->CreateRenderTargetView(target.reflectionColor.Get(),&view,&target.reflectionView),"Isolated reflection sRGB render view");
    view.Format=DXGI_FORMAT_R8G8B8A8_UNORM;
    Check(cache.device->CreateRenderTargetView(target.reflectionColor.Get(),&view,&target.reflectionRawView),"Isolated reflection encoded render view");
    D3D11_SHADER_RESOURCE_VIEW_DESC resource{};resource.Format=DXGI_FORMAT_R8G8B8A8_UNORM;resource.ViewDimension=D3D11_SRV_DIMENSION_TEXTURE2D;resource.Texture2D.MipLevels=1;
    Check(cache.device->CreateShaderResourceView(target.reflectionColor.Get(),&resource,&target.reflectionResource),"Isolated reflection raw colour view");
    texture.Format=DXGI_FORMAT_D32_FLOAT;texture.BindFlags=D3D11_BIND_DEPTH_STENCIL;
    Check(cache.device->CreateTexture2D(&texture,nullptr,&target.reflectionDepth),"Isolated scene reflection depth target");
    D3D11_DEPTH_STENCIL_VIEW_DESC depth{};depth.Format=DXGI_FORMAT_D32_FLOAT;depth.ViewDimension=D3D11_DSV_DIMENSION_TEXTURE2D;
    Check(cache.device->CreateDepthStencilView(target.reflectionDepth.Get(),&depth,&target.reflectionDepthView),"Isolated scene reflection depth view");
}

std::unique_ptr<SurfaceTargets> CreateWaterSurfaceTargets(Cache& cache,unsigned width,unsigned height,unsigned mapWidth,
    unsigned reflectionSide=OSL::OriginalReflectionSide){
    Require(cache.device.Get()!=nullptr && width>0 && height>0 && width<=4096 && height<=4096 && mapWidth>0 && mapWidth<=width,
        "Invalid isolated water surface target dimensions");
    auto candidate=std::make_unique<SurfaceTargets>();
    candidate->width=width;candidate->height=height;candidate->mapWidth=mapWidth;
    // Original WaterShader blends its own source colour with the destination.
    // It does not consume our former private colour/depth/ID refraction copies.
    CreateSceneReflectionImages(cache,*candidate,reflectionSide);
    // Ownership is published by the caller only after every creation succeeds.
    return candidate;
}

