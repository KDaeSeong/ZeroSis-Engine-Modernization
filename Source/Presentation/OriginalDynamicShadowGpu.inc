std::unique_ptr<DynamicShadowMap> CreateDynamicShadowMap(Cache& cache){
    auto result=std::make_unique<DynamicShadowMap>();
    D3D11_TEXTURE2D_DESC td{};td.Width=td.Height=DS::CandidateResolution;td.ArraySize=td.MipLevels=1;
    td.Format=DXGI_FORMAT_R32_TYPELESS;td.SampleDesc.Count=1;td.Usage=D3D11_USAGE_DEFAULT;
    td.BindFlags=D3D11_BIND_DEPTH_STENCIL|D3D11_BIND_SHADER_RESOURCE;
    Check(cache.device->CreateTexture2D(&td,nullptr,&result->depth),"Dynamic shadow depth target");
    D3D11_DEPTH_STENCIL_VIEW_DESC dv{};dv.Format=DXGI_FORMAT_D32_FLOAT;dv.ViewDimension=D3D11_DSV_DIMENSION_TEXTURE2D;
    Check(cache.device->CreateDepthStencilView(result->depth.Get(),&dv,&result->depthView),"Dynamic shadow depth view");
    D3D11_SHADER_RESOURCE_VIEW_DESC sv{};sv.Format=DXGI_FORMAT_R32_FLOAT;sv.ViewDimension=D3D11_SRV_DIMENSION_TEXTURE2D;sv.Texture2D.MipLevels=1;
    Check(cache.device->CreateShaderResourceView(result->depth.Get(),&sv,&result->depthResource),"Dynamic shadow resource view");
    const UINT flags=D3DCOMPILE_ENABLE_STRICTNESS|D3DCOMPILE_WARNINGS_ARE_ERRORS;
    ComPtr<ID3DBlob> uv,gp,diagnostic;
    Check(D3DCompile(DS::ProducerSource,sizeof(DS::ProducerSource)-1,"DynamicShadow",nullptr,nullptr,"unitVertex","vs_5_0",flags,0,&uv,&diagnostic),"Dynamic unit shadow VS compile");
    Check(D3DCompile(DS::ProducerSource,sizeof(DS::ProducerSource)-1,"DynamicShadow",nullptr,nullptr,"groundPixel","ps_5_0",flags,0,&gp,&diagnostic),"Dynamic ground shadow PS compile");
    Check(cache.device->CreateVertexShader(uv->GetBufferPointer(),uv->GetBufferSize(),nullptr,&result->unitVs),"Dynamic unit shadow VS");
    Check(cache.device->CreatePixelShader(gp->GetBufferPointer(),gp->GetBufferSize(),nullptr,&result->groundPs),"Dynamic ground shadow PS");
    const D3D11_INPUT_ELEMENT_DESC element={"POSITION",0,DXGI_FORMAT_R32G32B32_FLOAT,0,0,D3D11_INPUT_PER_VERTEX_DATA,0};
    Check(cache.device->CreateInputLayout(&element,1,uv->GetBufferPointer(),uv->GetBufferSize(),&result->unitLayout),"Dynamic unit shadow layout");
    D3D11_BUFFER_DESC cb{};cb.ByteWidth=sizeof(DynamicShadowConstants);cb.Usage=D3D11_USAGE_DEFAULT;cb.BindFlags=D3D11_BIND_CONSTANT_BUFFER;
    Check(cache.device->CreateBuffer(&cb,nullptr,&result->constants),"Dynamic shadow constants");
    return result;
}

void DrawDynamicShadow(const WorldView& view,Cache& cache,const OriginalGroundData& ground,const std::map<unsigned,Group>& units){
    if(!cache.dynamicShadow)cache.dynamicShadow=CreateDynamicShadowMap(cache);
    auto& shadow=*cache.dynamicShadow;DS::Bounds bounds;
    // All piece heights are normalized uint16 weighted averages. Include their
    // full legal range, without inspecting any unknown source height or cell.
    const double minY=-OT::HeightOffsetCandidate*OT::HeightWorldScaleCandidate;
    const double maxY=(1-OT::HeightOffsetCandidate)*OT::HeightWorldScaleCandidate;
    for(const auto& draw:ground.draws)if(draw.mesh->slots.count){
        const auto origin=OT::PatchWorld::DisplayOrigin(draw.patch);
        const double width=static_cast<double>(draw.patch.grid[2])/OT::TexelsPerHex;
        const double depth=static_cast<double>(draw.patch.grid[3])*OT::RowSpacing/OT::TexelsPerHex;
        bounds.Add({origin[0],minY,origin[1]-depth});bounds.Add({origin[0]+width,maxY,origin[1]});}
    for(const auto& entry:units)for(const auto& v:entry.second.vertices)bounds.Add({v.x,v.y,v.z});
    shadow.projection=DS::Fit(bounds);auto& params=shadow.parameters;params={};
    std::memcpy(&params.viewProjection,shadow.projection.matrix.data(),64);
    params.mapInfo[0]=static_cast<float>(view.gridWidth);params.mapInfo[1]=static_cast<float>(view.gridHeight);
    params.mapInfo[2]=view.wrapX?1.0f:0.0f;params.mapInfo[3]=view.wrapY?1.0f:0.0f;
    params.info[0]=shadow.projection.enabled?1.0f:0.0f;params.info[1]=static_cast<float>(shadow.projection.resolution);
    params.info[2]=DS::CandidateBias;params.info[3]=1;
    struct RestoreDynamicShadow final {
        Cache& cache;std::array<ComPtr<ID3D11RenderTargetView>,8> rtv;ComPtr<ID3D11DepthStencilView> dsv;
        ComPtr<ID3D11DepthStencilState> depth;ComPtr<ID3D11BlendState> blend;ComPtr<ID3D11RasterizerState> raster;
        ComPtr<ID3D11InputLayout> layout;ComPtr<ID3D11VertexShader> vs;ComPtr<ID3D11PixelShader> ps;
        ComPtr<ID3D11HullShader> hs;ComPtr<ID3D11DomainShader> ds;
        ComPtr<ID3D11Buffer> vs7,hs7,ds7;
        ComPtr<ID3D11Buffer> vb,ib,vs5,ps5;ComPtr<ID3D11ShaderResourceView> ps0,ps11,ps43;
        UINT stencil=0,sampleMask=0,stride=0,offset=0,indexOffset=0,count=16;FLOAT factor[4]{};
        DXGI_FORMAT format=DXGI_FORMAT_UNKNOWN;D3D11_PRIMITIVE_TOPOLOGY topology{};D3D11_VIEWPORT viewports[16]{};
        explicit RestoreDynamicShadow(Cache& c):cache(c){ID3D11RenderTargetView* raw[8]{};c.context->OMGetRenderTargets(8,raw,&dsv);
            for(unsigned i=0;i<8;++i)rtv[i].Attach(raw[i]);c.context->OMGetDepthStencilState(&depth,&stencil);c.context->OMGetBlendState(&blend,factor,&sampleMask);
            c.context->RSGetState(&raster);c.context->RSGetViewports(&count,viewports);c.context->IAGetInputLayout(&layout);
            c.context->IAGetPrimitiveTopology(&topology);c.context->IAGetVertexBuffers(0,1,&vb,&stride,&offset);c.context->IAGetIndexBuffer(&ib,&format,&indexOffset);
            c.context->VSGetShader(&vs,nullptr,nullptr);c.context->PSGetShader(&ps,nullptr,nullptr);c.context->VSGetConstantBuffers(5,1,&vs5);c.context->PSGetConstantBuffers(5,1,&ps5);
            c.context->HSGetShader(&hs,nullptr,nullptr);c.context->DSGetShader(&ds,nullptr,nullptr);
            c.context->VSGetConstantBuffers(7,1,&vs7);c.context->HSGetConstantBuffers(7,1,&hs7);c.context->DSGetConstantBuffers(7,1,&ds7);
            c.context->PSGetShaderResources(0,1,&ps0);c.context->PSGetShaderResources(11,1,&ps11);c.context->PSGetShaderResources(43,1,&ps43);}
        ~RestoreDynamicShadow() noexcept {auto* c=cache.context.Get();c->OMSetRenderTargets(0,nullptr,nullptr);ID3D11ShaderResourceView* empty=nullptr;
            c->PSSetShaderResources(0,1,&empty);c->PSSetShaderResources(43,1,&empty);
            ID3D11RenderTargetView* raw[8]{};for(unsigned i=0;i<8;++i)raw[i]=rtv[i].Get();c->OMSetRenderTargets(8,raw,dsv.Get());
            c->OMSetDepthStencilState(depth.Get(),stencil);c->OMSetBlendState(blend.Get(),factor,sampleMask);c->RSSetState(raster.Get());c->RSSetViewports(count,viewports);
            c->IASetInputLayout(layout.Get());c->IASetPrimitiveTopology(topology);auto* v=vb.Get();c->IASetVertexBuffers(0,1,&v,&stride,&offset);c->IASetIndexBuffer(ib.Get(),format,indexOffset);
            c->VSSetShader(vs.Get(),nullptr,0);c->PSSetShader(ps.Get(),nullptr,0);auto* vc=vs5.Get();auto* pc=ps5.Get();c->VSSetConstantBuffers(5,1,&vc);c->PSSetConstantBuffers(5,1,&pc);
            c->HSSetShader(hs.Get(),nullptr,0);c->DSSetShader(ds.Get(),nullptr,0);
            auto* v7=vs7.Get();auto* h7=hs7.Get();auto* d7=ds7.Get();
            c->VSSetConstantBuffers(7,1,&v7);c->HSSetConstantBuffers(7,1,&h7);c->DSSetConstantBuffers(7,1,&d7);
            auto* r0=ps0.Get();auto* r11=ps11.Get();auto* r43=ps43.Get();c->PSSetShaderResources(0,1,&r0);c->PSSetShaderResources(11,1,&r11);c->PSSetShaderResources(43,1,&r43);}
    } restore(cache);
    // Explicitly detach both receiver slots before depth output. Slot11 can
    // also contain the previous water receiver binding after a failed frame.
    ID3D11ShaderResourceView* empty=nullptr;cache.context->PSSetShaderResources(11,1,&empty);cache.context->PSSetShaderResources(43,1,&empty);
    cache.context->OMSetRenderTargets(0,nullptr,shadow.depthView.Get());
    cache.context->ClearDepthStencilView(shadow.depthView.Get(),D3D11_CLEAR_DEPTH,1,0);
    cache.context->OMSetDepthStencilState(cache.depthState.Get(),0);cache.context->OMSetBlendState(cache.blendState.Get(),nullptr,0xffffffffu);
    cache.context->RSSetState(cache.raster.Get());const D3D11_VIEWPORT viewport{0,0,static_cast<float>(DS::CandidateResolution),static_cast<float>(DS::CandidateResolution),0,1};
    cache.context->RSSetViewports(1,&viewport);cache.context->IASetPrimitiveTopology(D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST);
    cache.context->GSSetShader(nullptr,nullptr,0);cache.context->HSSetShader(nullptr,nullptr,0);cache.context->DSSetShader(nullptr,nullptr,0);
    cache.context->SOSetTargets(0,nullptr,nullptr);cache.context->SetPredication(nullptr,FALSE);
    ID3D11Buffer* cb=shadow.constants.Get();cache.context->VSSetConstantBuffers(5,1,&cb);cache.context->PSSetConstantBuffers(5,1,&cb);
    auto domain=Tess::WorldDomainConstants(shadow.projection.matrix);
    const auto gridLevel=ground.lod.GridLevel();
    cache.context->PSSetShader(shadow.groundPs.Get(),nullptr,0);
    ID3D11ShaderResourceView* state=ground.plotState.Get();cache.context->PSSetShaderResources(0,1,&state);
    for(const auto& draw:ground.draws){if(!draw.mesh->slots.count)continue;
        const auto origin=OT::PatchWorld::DisplayOrigin(draw.patch);
        params.placement[0]=origin[0];params.placement[1]=origin[1];
        params.placement[2]=static_cast<float>(draw.column);params.placement[3]=static_cast<float>(draw.row);
        cache.context->UpdateSubresource(shadow.constants.Get(),0,nullptr,&params,0,0);
        DrawPlacedTerrainMesh(cache,draw,gridLevel,domain);}
    cache.context->PSSetShaderResources(0,1,&empty);cache.context->PSSetShader(nullptr,nullptr,0);
    cache.context->VSSetShader(shadow.unitVs.Get(),nullptr,0);cache.context->IASetInputLayout(shadow.unitLayout.Get());
    // Uses only the current already-filtered pose and uploaded buffers. No
    // animation clocks, SDK calls, terrain IDs or material textures are touched.
    for(const auto& entry:units){if(entry.second.vertices.empty())continue;auto* vb=cache.unitBuffers.at(entry.first).buffer.Get();const UINT stride=sizeof(Vertex),offset=0;
        cache.context->IASetVertexBuffers(0,1,&vb,&stride,&offset);cache.context->Draw(static_cast<UINT>(entry.second.vertices.size()),0);}
    params.placement[0]=params.placement[1]=params.placement[2]=params.placement[3]=0;
    cache.context->UpdateSubresource(shadow.constants.Get(),0,nullptr,&params,0,0);
}
