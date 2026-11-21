std::unique_ptr<WaterCatalog> LoadWaterCatalog(Cache& cache,const std::wstring& path){
    Reader input(path);auto package=OW::DecodePackage(std::move(input.data),OW::PackageSha256);
    auto result=std::make_unique<WaterCatalog>();result->path=path;
    for(unsigned i=0;i<result->textures.size();++i){
        const auto& texture=OW::FindAsset(package,static_cast<OW::AssetRole>(i+1)).texture;
        D3D11_TEXTURE2D_DESC td{};td.Width=texture.width;td.Height=texture.height;td.MipLevels=texture.mips;
        td.ArraySize=1;td.SampleDesc.Count=1;td.Usage=D3D11_USAGE_IMMUTABLE;td.BindFlags=D3D11_BIND_SHADER_RESOURCE;
        td.Format=texture.format==OW::TextureFormat::Bc1?DXGI_FORMAT_BC1_UNORM:
            texture.format==OW::TextureFormat::Bc3?DXGI_FORMAT_BC3_UNORM:DXGI_FORMAT_B8G8R8A8_UNORM;
        std::vector<D3D11_SUBRESOURCE_DATA> levels;
        for(const auto& level:texture.levels)levels.push_back({package.bytes.data()+level.offset,static_cast<UINT>(level.rowPitch),0});
        ComPtr<ID3D11Texture2D> image;Check(cache.device->CreateTexture2D(&td,levels.data(),&image),"Original water texture upload");
        Check(cache.device->CreateShaderResourceView(image.Get(),nullptr,&result->textures[i]),"Original water texture view");
    }
    result->styles=std::move(package.styles);result->profiles=std::move(package.profiles);
    ComPtr<ID3DBlob> vsBytes,psBytes,diagnostic;const UINT flags=D3DCOMPILE_ENABLE_STRICTNESS|D3DCOMPILE_WARNINGS_ARE_ERRORS;
    Check(D3DCompile(OW::ShaderSource,sizeof(OW::ShaderSource)-1,"OriginalWater",nullptr,nullptr,"vertexMain","vs_5_0",
        flags,0,&vsBytes,&diagnostic),"Original water vertex shader compilation");
    Check(D3DCompile(OW::ShaderSource,sizeof(OW::ShaderSource)-1,"OriginalWater",nullptr,nullptr,"pixelMain","ps_5_0",
        flags,0,&psBytes,&diagnostic),"Original water pixel shader compilation");
    Check(cache.device->CreateVertexShader(vsBytes->GetBufferPointer(),vsBytes->GetBufferSize(),nullptr,&result->vs),"Original water vertex shader");
    Check(cache.device->CreatePixelShader(psBytes->GetBufferPointer(),psBytes->GetBufferSize(),nullptr,&result->ps),"Original water pixel shader");
    const D3D11_INPUT_ELEMENT_DESC elements[]={
        {"POSITION",0,DXGI_FORMAT_R32G32B32_FLOAT,0,0,D3D11_INPUT_PER_VERTEX_DATA,0},
        {"TEXCOORD",0,DXGI_FORMAT_R32G32_FLOAT,0,12,D3D11_INPUT_PER_VERTEX_DATA,0},
        {"TEXCOORD",1,DXGI_FORMAT_R32_FLOAT,0,20,D3D11_INPUT_PER_VERTEX_DATA,0},
        {"TEXCOORD",2,DXGI_FORMAT_R32_FLOAT,0,24,D3D11_INPUT_PER_VERTEX_DATA,0},
        {"TEXCOORD",3,DXGI_FORMAT_R32_FLOAT,0,28,D3D11_INPUT_PER_VERTEX_DATA,0}};
    Check(cache.device->CreateInputLayout(elements,static_cast<UINT>(std::size(elements)),vsBytes->GetBufferPointer(),vsBytes->GetBufferSize(),&result->layout),"Original water vertex layout");
    D3D11_BUFFER_DESC cb{};cb.ByteWidth=sizeof(WaterConstants);cb.Usage=D3D11_USAGE_DEFAULT;cb.BindFlags=D3D11_BIND_CONSTANT_BUFFER;
    Check(cache.device->CreateBuffer(&cb,nullptr,&result->constants),"Original water constants");
    D3D11_SAMPLER_DESC sd{};sd.Filter=D3D11_FILTER_MIN_MAG_MIP_LINEAR;sd.MaxLOD=D3D11_FLOAT32_MAX;
    sd.AddressU=sd.AddressV=sd.AddressW=D3D11_TEXTURE_ADDRESS_WRAP;sd.ComparisonFunc=D3D11_COMPARISON_NEVER;
    Check(cache.device->CreateSamplerState(&sd,&result->wrapSampler),"Original water wrap sampler");
    sd.AddressU=sd.AddressV=sd.AddressW=D3D11_TEXTURE_ADDRESS_CLAMP;
    Check(cache.device->CreateSamplerState(&sd,&result->clampSampler),"Original water clamp sampler");
    D3D11_DEPTH_STENCIL_DESC depth{};depth.DepthEnable=TRUE;depth.DepthWriteMask=D3D11_DEPTH_WRITE_MASK_ZERO;depth.DepthFunc=D3D11_COMPARISON_LESS_EQUAL;
    Check(cache.device->CreateDepthStencilState(&depth,&result->depthReadOnly),"Original water read-only depth state");
    D3D11_BLEND_DESC blend{};auto& target=blend.RenderTarget[0];target.BlendEnable=TRUE;
    target.SrcBlend=D3D11_BLEND_SRC_ALPHA;target.DestBlend=D3D11_BLEND_INV_SRC_ALPHA;target.BlendOp=D3D11_BLEND_OP_ADD;
    target.SrcBlendAlpha=D3D11_BLEND_ZERO;target.DestBlendAlpha=D3D11_BLEND_ONE;target.BlendOpAlpha=D3D11_BLEND_OP_ADD;
    target.RenderTargetWriteMask=D3D11_COLOR_WRITE_ENABLE_RED|D3D11_COLOR_WRITE_ENABLE_GREEN|D3D11_COLOR_WRITE_ENABLE_BLUE;
    Check(cache.device->CreateBlendState(&blend,&result->alphaBlend),"Original water RGB-only alpha blend");
    return result;
}

std::unique_ptr<WaterGeometry> PrepareWaterGeometry(Cache& cache,WaterCatalog& catalog,OW::Grid key,const std::shared_ptr<OriginalSurface>& surface,bool riversOnly=false){
    auto mesh=OW::BuildAtlasMesh(key,surface->atlas,catalog.styles,catalog.profiles);
    if(riversOnly){
        std::vector<OW::Vertex> kept;std::vector<OW::DrawRange> ranges;
        for(const auto& range:mesh.ranges){const auto start=kept.size();
            for(unsigned i=range.start;i<range.start+range.count;++i)
                if(mesh.vertices[i].kind==static_cast<float>(OW::SurfaceKind::River))kept.push_back(mesh.vertices[i]);
            if(kept.size()!=start)ranges.push_back({range.ownerCell,static_cast<unsigned>(start),static_cast<unsigned>(kept.size()-start)});
        }
        mesh.vertices.swap(kept);mesh.ranges.swap(ranges);
    }
    auto result=std::make_unique<WaterGeometry>();result->key=std::move(key);result->surface=surface;
    result->riversOnly=riversOnly;
    result->ranges.resize(result->key.cells.size());
    for(const auto& range:mesh.ranges){
        Require(range.ownerCell<result->ranges.size()&&range.start<=mesh.vertices.size()&&range.count<=mesh.vertices.size()-range.start,"Invalid water draw range");
        unsigned cursor=range.start;
        while(cursor<range.start+range.count){
            const auto kind=static_cast<unsigned>(mesh.vertices[cursor].kind);
            Require(kind<3&&mesh.vertices[cursor].kind==static_cast<float>(kind),"Invalid water material kind");
            auto& part=result->ranges[range.ownerCell][kind];Require(part.count==0,"Water material ranges must remain contiguous");
            part.ownerCell=range.ownerCell;part.start=cursor;
            do{++cursor;}while(cursor<range.start+range.count&&mesh.vertices[cursor].kind==static_cast<float>(kind));
            part.count=cursor-part.start;Require(part.count%3==0,"Water material range is not a triangle list");
        }
    }
    if(!mesh.vertices.empty()){
        Require(mesh.vertices.size()<=OW::MaxVertices&&mesh.vertices.size()*sizeof(OW::Vertex)<=UINT_MAX,"Water mesh exceeds its bounded GPU upload");
        D3D11_BUFFER_DESC bd{};bd.ByteWidth=static_cast<UINT>(mesh.vertices.size()*sizeof(OW::Vertex));bd.Usage=D3D11_USAGE_IMMUTABLE;bd.BindFlags=D3D11_BIND_VERTEX_BUFFER;
        const D3D11_SUBRESOURCE_DATA initial{mesh.vertices.data(),0,0};Check(cache.device->CreateBuffer(&bd,&initial,&result->vertices),"Original water overlay vertex upload");
    }
    return result;
}

void DrawOriginalWater(const WorldView& view,Cache& cache,WaterCatalog& catalog,const WaterGeometry& geometry,
    const OriginalGroundData& ground,FrameTargets& surfaces,float cameraDistance,bool fogEnabled){
    if(!geometry.vertices)return;
    ID3D11RenderTargetView* target=surfaces.colorView.Get();cache.context->OMSetRenderTargets(1,&target,surfaces.depthView.Get());
    cache.context->OMSetDepthStencilState(catalog.depthReadOnly.Get(),0);cache.context->OMSetBlendState(catalog.alphaBlend.Get(),nullptr,0xffffffffu);
    cache.context->IASetInputLayout(catalog.layout.Get());cache.context->VSSetShader(catalog.vs.Get(),nullptr,0);cache.context->PSSetShader(catalog.ps.Get(),nullptr,0);
    ID3D11Buffer* vertices=geometry.vertices.Get();const UINT stride=sizeof(OW::Vertex),offset=0;cache.context->IASetVertexBuffers(0,1,&vertices,&stride,&offset);
    ID3D11Buffer* cb=catalog.constants.Get();cache.context->VSSetConstantBuffers(1,1,&cb);cache.context->PSSetConstantBuffers(1,1,&cb);
    std::array<ID3D11ShaderResourceView*,15> resources{};for(unsigned i=0;i<catalog.textures.size();++i)resources[i]=catalog.textures[i].Get();
    resources[14]=ground.plotState.Get();cache.context->PSSetShaderResources(0,static_cast<UINT>(resources.size()),resources.data());
    ID3D11SamplerState* samplers[]={catalog.wrapSampler.Get(),catalog.clampSampler.Get()};cache.context->PSSetSamplers(0,2,samplers);
    WaterConstants constants{};constants.mapInfo[0]=static_cast<float>(view.gridWidth);constants.mapInfo[1]=static_cast<float>(view.gridHeight);
    constants.mapInfo[2]=view.wrapX?1.0f:0.0f;constants.mapInfo[3]=view.wrapY?1.0f:0.0f;
    constants.shade[0]=static_cast<float>(view.waterAnimationSeconds);constants.shade[1]=OT::HeightWorldScaleCandidate;
    constants.shade[2]=OT::HeightOffsetCandidate;constants.shade[3]=fogEnabled?1.0f:0.0f;
    std::copy(std::begin(OW::CandidateWaterUvScales),std::end(OW::CandidateWaterUvScales),constants.uvScales);
    constants.eye[1]=cameraDistance*0.65f;constants.eye[2]=-cameraDistance*0.7599342f;constants.eye[3]=OT::RetailWorldUnitsPerHexCandidate;
    constants.motion[0]=OW::CandidateWaterTranslation;constants.motion[1]=OW::CandidateRiverTranslation;
    const float centerX=static_cast<float>(view.cameraX)+static_cast<float>(view.cameraY&1)*0.5f,centerZ=-static_cast<float>(view.cameraY)*OT::RowSpacing;
    // Global material order prevents a later neighbour's water surface from
    // covering an earlier coast or river. Tile ownership and depth stay separate.
    for(unsigned kind=0;kind<3;++kind)for(const auto& draw:ground.draws){
        const auto owner=static_cast<std::size_t>(draw.mesh->row)*view.gridWidth+draw.mesh->column;
        const auto& range=geometry.ranges.at(owner)[kind];if(!range.count)continue;
        const float dx=static_cast<float>(draw.column)-static_cast<float>(draw.mesh->column),dz=-(static_cast<float>(draw.row)-static_cast<float>(draw.mesh->row))*OT::RowSpacing;
        constants.placement[0]=dx-centerX;constants.placement[1]=dz-centerZ;constants.placement[2]=dx;constants.placement[3]=dz;
        cache.context->UpdateSubresource(catalog.constants.Get(),0,nullptr,&constants,0,0);cache.context->Draw(range.count,range.start);
    }
    ID3D11ShaderResourceView* empty[15]{};cache.context->PSSetShaderResources(0,15,empty);
    ID3D11SamplerState* noSamplers[2]{};cache.context->PSSetSamplers(0,2,noSamplers);
    ID3D11Buffer* nullBuffer=nullptr;cache.context->VSSetConstantBuffers(1,1,&nullBuffer);cache.context->PSSetConstantBuffers(1,1,&nullBuffer);
    cache.context->OMSetDepthStencilState(cache.depthState.Get(),0);cache.context->OMSetBlendState(cache.blendState.Get(),nullptr,0xffffffffu);
    cache.context->IASetInputLayout(cache.layout.Get());cache.context->VSSetShader(cache.vs.Get(),nullptr,0);cache.context->PSSetShader(cache.ps.Get(),nullptr,0);
    ID3D11SamplerState* sampler=cache.sampler.Get();cache.context->PSSetSamplers(0,1,&sampler);
}
