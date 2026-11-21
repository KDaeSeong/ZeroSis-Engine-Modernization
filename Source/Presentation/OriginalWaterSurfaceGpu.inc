std::unique_ptr<WaterSurfaceCatalog> LoadWaterSurfaceCatalog(Cache& cache,const std::wstring& path){
    Reader input(path);const auto package=WL::DecodePackage(std::move(input.data),WB::LeanPackageSha256);
    const auto& texture=WL::FindAsset(package,WL::AssetRole::WaterBumps).texture;
    auto result=std::make_unique<WaterSurfaceCatalog>();result->path=path;WO::Validate(result->optics);
    for(unsigned plane=0;plane<2;++plane){
        D3D11_TEXTURE2D_DESC td{};td.Width=texture.width;td.Height=texture.height;td.MipLevels=texture.mips;td.ArraySize=1;
        td.Format=plane==0?DXGI_FORMAT_R16G16B16A16_UNORM:DXGI_FORMAT_R16_UNORM;td.SampleDesc.Count=1;
        td.Usage=D3D11_USAGE_IMMUTABLE;td.BindFlags=D3D11_BIND_SHADER_RESOURCE;
        std::vector<D3D11_SUBRESOURCE_DATA> data;
        for(const auto& level:texture.planes[plane].levels)data.push_back({package.bytes.data()+level.offset,static_cast<UINT>(level.rowPitch),0});
        ComPtr<ID3D11Texture2D> image;Check(cache.device->CreateTexture2D(&td,data.data(),&image),"Water LEAN plane upload");
        Check(cache.device->CreateShaderResourceView(image.Get(),nullptr,&result->lean[plane]),"Water LEAN plane view");
    }
    ComPtr<ID3DBlob> vs,ps,diagnostic;const UINT flags=D3DCOMPILE_ENABLE_STRICTNESS|D3DCOMPILE_WARNINGS_ARE_ERRORS;
    const std::string shader=std::string("#define DYNAMIC_SHADOW_SLOT t11\n")+DS::SamplingSource+WS::ShaderSource;
    Check(D3DCompile(shader.data(),shader.size(),"WaterSurface",nullptr,nullptr,"vertexMain","vs_5_0",flags,0,&vs,&diagnostic),"Water surface VS compilation");
    Check(D3DCompile(shader.data(),shader.size(),"WaterSurface",nullptr,nullptr,"pixelMain","ps_5_0",flags,0,&ps,&diagnostic),"Water surface PS compilation");
    Check(cache.device->CreateVertexShader(vs->GetBufferPointer(),vs->GetBufferSize(),nullptr,&result->vs),"Water surface VS");
    Check(cache.device->CreatePixelShader(ps->GetBufferPointer(),ps->GetBufferSize(),nullptr,&result->ps),"Water surface PS");
    const D3D11_INPUT_ELEMENT_DESC elements[]={
        {"POSITION",0,DXGI_FORMAT_R32G32B32_FLOAT,0,0,D3D11_INPUT_PER_VERTEX_DATA,0},
        {"TEXCOORD",0,DXGI_FORMAT_R32G32_FLOAT,0,12,D3D11_INPUT_PER_VERTEX_DATA,0},
        {"TEXCOORD",1,DXGI_FORMAT_R32_FLOAT,0,20,D3D11_INPUT_PER_VERTEX_DATA,0},
        {"TEXCOORD",2,DXGI_FORMAT_R32_FLOAT,0,24,D3D11_INPUT_PER_VERTEX_DATA,0},
        {"TEXCOORD",3,DXGI_FORMAT_R32_FLOAT,0,28,D3D11_INPUT_PER_VERTEX_DATA,0}};
    Check(cache.device->CreateInputLayout(elements,static_cast<UINT>(std::size(elements)),vs->GetBufferPointer(),vs->GetBufferSize(),&result->layout),"Water surface layout");
    D3D11_BUFFER_DESC bd{};bd.ByteWidth=sizeof(WaterSurfaceConstants);bd.Usage=D3D11_USAGE_DEFAULT;bd.BindFlags=D3D11_BIND_CONSTANT_BUFFER;
    Check(cache.device->CreateBuffer(&bd,nullptr,&result->constants),"Water surface constants");
    for(unsigned kind=0;kind<2;++kind){
        const auto blend=OriginalWaterBlend::MakeMrtDescription(kind==0);
        Check(cache.device->CreateBlendState(&blend,&result->originalAlphaBlend[kind]),"Original water alpha blend with exact integer MRT outputs");
    }
    return result;
}

std::unique_ptr<WaterSurfaceGeometry> PrepareWaterSurfaceGeometry(Cache& cache,OW::Grid key,const std::shared_ptr<OriginalSurface>& surface){
    const auto mesh=WS::BuildSurface(key,surface->atlas);auto result=std::make_unique<WaterSurfaceGeometry>();
    result->key=std::move(key);result->surface=surface;result->ranges.resize(result->key.cells.size());
    for(const auto& range:mesh.ranges){const auto kind=static_cast<unsigned>(range.kind);
        Require(kind<2&&range.ownerCell<result->ranges.size()&&range.start<=mesh.vertices.size()&&range.count<=mesh.vertices.size()-range.start,"Invalid water surface range");
        result->ranges[range.ownerCell][kind].push_back({range.ownerCell,range.start,range.count});
    }
    if(!mesh.vertices.empty()){
        Require(mesh.vertices.size()<=OW::MaxVertices&&mesh.vertices.size()*sizeof(OW::Vertex)<=UINT_MAX,"Water surface vertex bound exceeded");
        D3D11_BUFFER_DESC bd{};bd.ByteWidth=static_cast<UINT>(mesh.vertices.size()*sizeof(OW::Vertex));bd.Usage=D3D11_USAGE_IMMUTABLE;bd.BindFlags=D3D11_BIND_VERTEX_BUFFER;
        const D3D11_SUBRESOURCE_DATA initial{mesh.vertices.data(),0,0};Check(cache.device->CreateBuffer(&bd,&initial,&result->vertices),"Fixed water surface mesh upload");
    }
    std::vector<unsigned char> mask(result->key.cells.size());
    for(std::size_t i=0;i<mask.size();++i)mask[i]=result->key.cells[i].revealed&&result->key.cells[i].water?1u:0u;
    D3D11_TEXTURE2D_DESC td{};td.Width=static_cast<UINT>(result->key.width);td.Height=static_cast<UINT>(result->key.height);td.MipLevels=td.ArraySize=1;td.SampleDesc.Count=1;
    td.Format=DXGI_FORMAT_R8_UINT;td.Usage=D3D11_USAGE_IMMUTABLE;td.BindFlags=D3D11_BIND_SHADER_RESOURCE;
    const D3D11_SUBRESOURCE_DATA initial{mask.data(),td.Width,0};ComPtr<ID3D11Texture2D> texture;
    Check(cache.device->CreateTexture2D(&td,&initial,&texture),"Exact water cell mask upload");
    Check(cache.device->CreateShaderResourceView(texture.Get(),nullptr,&result->waterMask),"Exact water cell mask view");return result;
}

void DrawWaterSurface(const WorldView& view,Cache& cache,WaterCatalog& water,WaterSurfaceCatalog& catalog,
    const WaterSurfaceGeometry& geometry,const OriginalGroundData& ground,FrameTargets& frame,SurfaceTargets& targets,
    const XMMATRIX& matrix,float cameraDistance,unsigned mapWidth,unsigned height,bool fogEnabled,FogCatalog* fog,const FogMask* mask){
    if(!geometry.vertices)return;
    WaterSurfaceConstants constants{};
    constants.reflectionViewProjection=targets.reflectionViewProjection;
    Require(!fogEnabled||(fog&&mask),"Original water fog inputs are incomplete");
    XMFLOAT4X4 cameraConstants;XMStoreFloat4x4(&cameraConstants,matrix);
    cache.context->UpdateSubresource(cache.constants.Get(),0,nullptr,&cameraConstants,0,0);
    ID3D11Buffer* cameraBuffer=cache.constants.Get();cache.context->VSSetConstantBuffers(0,1,&cameraBuffer);
    constants.mapInfo[0]=static_cast<float>(view.gridWidth);constants.mapInfo[1]=static_cast<float>(view.gridHeight);
    constants.mapInfo[2]=view.wrapX?1.0f:0.0f;constants.mapInfo[3]=view.wrapY?1.0f:0.0f;
    constants.eye[1]=cameraDistance*0.65f;constants.eye[2]=-cameraDistance*0.7599342f;constants.eye[3]=OT::RetailWorldUnitsPerHexCandidate;
    constants.viewport[0]=static_cast<float>(mapWidth);constants.viewport[1]=static_cast<float>(height);
    constants.viewport[2]=static_cast<float>(frame.width);constants.viewport[3]=static_cast<float>(frame.height);
    constants.reflection[0]=static_cast<float>(targets.reflectionWidth);constants.reflection[1]=static_cast<float>(targets.reflectionHeight);
    constants.reflection[2]=WB::WorldPlaneCandidate;constants.reflection[3]=static_cast<float>(view.waterAnimationSeconds);
    constants.optics[0]=static_cast<float>(catalog.optics.scale);constants.optics[1]=static_cast<float>(catalog.optics.primaryK);
    constants.optics[2]=static_cast<float>(catalog.optics.secondaryK);constants.optics[3]=static_cast<float>(catalog.optics.reflectionStrength);
    for(unsigned i=0;i<4;++i)constants.uvScales[i]=static_cast<float>(catalog.optics.uvScales[i]);
    constants.motion[0]=static_cast<float>(catalog.optics.uvTranslation);constants.motion[1]=WB::CandidateRefractionDisplacement;constants.motion[2]=fogEnabled?1.0f:0.0f;
    constants.motion[3]=targets.reflectionProjectionValid?1.0f:0.0f;
    constants.fogDistance[0]=OF::CandidateHeightK;constants.fogDistance[1]=OF::CandidateDensity;
    constants.fogDistance[2]=OF::CandidateRampRow;constants.fogDistance[3]=OT::RetailWorldUnitsPerHexCandidate;
    if(fogEnabled)for(unsigned i=0;i<3;++i)constants.fogColour[i]=fog->colour[i];
    constants.fogColour[3]=1;
    std::copy(std::begin(OriginalWaterFog::CandidateOverlay),std::end(OriginalWaterFog::CandidateOverlay),constants.waterOverlay);
    constants.light0[0]=-0.40824829f;constants.light0[1]=0.40824829f;constants.light0[2]=0.81649658f;constants.light0[3]=0.02f;
    constants.light1[0]=0.35f;constants.light1[1]=-0.3f;constants.light1[2]=0.85f;constants.light1[3]=0.008f;
    // Runtime cb1[16/17] colours and projected shadow texture are not captured.
    // Keep their candidate values separate from the confirmed shader equation.
    constants.lightColour0[0]=0.02f;constants.lightColour0[1]=0.0192f;constants.lightColour0[2]=0.018f;
    constants.lightColour1[0]=0.0072f;constants.lightColour1[1]=0.00768f;constants.lightColour1[2]=0.008f;
    constants.shadow[0]=0;constants.shadow[1]=1;
    constants.absorption[0]=1.2f;constants.absorption[1]=0.35f;constants.absorption[2]=0.14f;constants.absorption[3]=0.65f;
    constants.warp0[0]=static_cast<float>(catalog.optics.primaryWarpOrigin.x);constants.warp0[1]=static_cast<float>(catalog.optics.primaryWarpOrigin.y);
    constants.warp0[2]=static_cast<float>(catalog.optics.primaryWarpOrigin.z);constants.warp0[3]=static_cast<float>(catalog.optics.primaryWarpMix);
    constants.warp1[0]=static_cast<float>(catalog.optics.secondaryWarpOrigin.x);constants.warp1[1]=static_cast<float>(catalog.optics.secondaryWarpOrigin.y);
    constants.warp1[2]=static_cast<float>(catalog.optics.secondaryWarpOrigin.z);constants.warp1[3]=static_cast<float>(catalog.optics.secondaryWarpMix);
    cache.context->IASetInputLayout(catalog.layout.Get());cache.context->VSSetShader(catalog.vs.Get(),nullptr,0);cache.context->PSSetShader(catalog.ps.Get(),nullptr,0);
    ID3D11Buffer* vertices=geometry.vertices.Get();const UINT stride=sizeof(OW::Vertex),offset=0;cache.context->IASetVertexBuffers(0,1,&vertices,&stride,&offset);
    ID3D11Buffer* cb=catalog.constants.Get();cache.context->VSSetConstantBuffers(1,1,&cb);cache.context->PSSetConstantBuffers(1,1,&cb);
    ID3D11ShaderResourceView* resources[]={catalog.lean[0].Get(),catalog.lean[1].Get(),targets.reflectionResource.Get(),nullptr,
        nullptr,nullptr,water.textures[0].Get(),nullptr,water.textures[7].Get(),ground.plotState.Get(),geometry.waterMask.Get(),
        cache.dynamicShadow?cache.dynamicShadow->depthResource.Get():nullptr,
        fogEnabled?mask->texture.Get():nullptr,fogEnabled?fog->lut.Get():nullptr,fogEnabled?fog->textures[5].Get():nullptr};
    cache.context->PSSetShaderResources(0,15,resources);
    ID3D11SamplerState* samplers[]={water.wrapSampler.Get(),water.clampSampler.Get(),fogEnabled?mask->sampler.Get():nullptr};cache.context->PSSetSamplers(0,3,samplers);
    ID3D11Buffer* dynamicBuffer=cache.dynamicShadow?cache.dynamicShadow->constants.Get():nullptr;cache.context->PSSetConstantBuffers(5,1,&dynamicBuffer);
    const float centerX=static_cast<float>(view.cameraX)+static_cast<float>(view.cameraY&1)*0.5f,centerZ=-static_cast<float>(view.cameraY)*OT::RowSpacing;
    for(unsigned kind=0;kind<2;++kind){
        ID3D11RenderTargetView* output[]={frame.colorRawView.Get(),frame.idView.Get(),nullptr,nullptr,frame.waterFragmentView.Get()};
        cache.context->OMSetRenderTargets(fogEnabled?5:(kind==0?2:1),output,frame.depthView.Get());
        cache.context->OMSetDepthStencilState(kind==0?cache.depthState.Get():water.depthReadOnly.Get(),0);
        cache.context->OMSetBlendState(catalog.originalAlphaBlend[kind].Get(),nullptr,0xffffffffu);
        for(const auto& draw:ground.draws){
            const auto owner=static_cast<std::size_t>(draw.mesh->row)*view.gridWidth+draw.mesh->column;
            const auto& ranges=geometry.ranges.at(owner)[kind];if(ranges.empty())continue;
            const float dx=static_cast<float>(draw.column)-static_cast<float>(draw.mesh->column),dz=-(static_cast<float>(draw.row)-static_cast<float>(draw.mesh->row))*OT::RowSpacing;
            constants.placement[0]=dx-centerX;constants.placement[1]=dz-centerZ;constants.placement[2]=dx;constants.placement[3]=dz;
            cache.context->UpdateSubresource(catalog.constants.Get(),0,nullptr,&constants,0,0);
            for(const auto& range:ranges)cache.context->Draw(range.count,range.start);
        }
    }
    ID3D11ShaderResourceView* empty[15]{};cache.context->PSSetShaderResources(0,15,empty);ID3D11SamplerState* noSamplers[3]{};cache.context->PSSetSamplers(0,3,noSamplers);
    ID3D11Buffer* nullBuffer=nullptr;cache.context->VSSetConstantBuffers(1,1,&nullBuffer);cache.context->PSSetConstantBuffers(1,1,&nullBuffer);
    cache.context->PSSetConstantBuffers(5,1,&nullBuffer);
    cache.context->OMSetDepthStencilState(cache.depthState.Get(),0);cache.context->OMSetBlendState(cache.blendState.Get(),nullptr,0xffffffffu);
    cache.context->IASetInputLayout(cache.layout.Get());cache.context->VSSetShader(cache.vs.Get(),nullptr,0);cache.context->PSSetShader(cache.ps.Get(),nullptr,0);
    ID3D11SamplerState* sampler=cache.sampler.Get();cache.context->PSSetSamplers(0,1,&sampler);
}
