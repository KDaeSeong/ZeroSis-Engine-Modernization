std::unique_ptr<LightingFieldBaker> LoadLightingFieldBaker(Cache& cache){
    auto result=std::make_unique<LightingFieldBaker>();
    const auto shaders=[&](const char* source,std::size_t bytes,const char* label,
        ComPtr<ID3D11VertexShader>& vertex,ComPtr<ID3D11PixelShader>& pixel){
        ComPtr<ID3DBlob> vs,ps,diagnostic;const UINT flags=D3DCOMPILE_ENABLE_STRICTNESS|D3DCOMPILE_WARNINGS_ARE_ERRORS;
        Check(D3DCompile(source,bytes,label,nullptr,nullptr,"vertexMain","vs_5_0",flags,0,&vs,&diagnostic),"Lighting field VS compile");
        Check(D3DCompile(source,bytes,label,nullptr,nullptr,"pixelMain","ps_5_0",flags,0,&ps,&diagnostic),"Lighting field PS compile");
        Check(cache.device->CreateVertexShader(vs->GetBufferPointer(),vs->GetBufferSize(),nullptr,&vertex),"Lighting field VS");
        Check(cache.device->CreatePixelShader(ps->GetBufferPointer(),ps->GetBufferSize(),nullptr,&pixel),"Lighting field PS");return vs;
    };
    const auto heightVertex=shaders(LF::HeightShaderSource,sizeof(LF::HeightShaderSource)-1,"LightingMaterialHeight",result->heightVs,result->heightPs);
    shaders(LF::NormalShaderSource,sizeof(LF::NormalShaderSource)-1,"LightingSobelNormal",result->normalVs,result->normalPs);
    const D3D11_INPUT_ELEMENT_DESC elements[]={
        {"POSITION",0,DXGI_FORMAT_R32G32B32_FLOAT,0,0,D3D11_INPUT_PER_VERTEX_DATA,0},
        {"TEXCOORD",0,DXGI_FORMAT_R32G32_FLOAT,0,12,D3D11_INPUT_PER_VERTEX_DATA,0},
        {"TEXCOORD",2,DXGI_FORMAT_R8G8B8A8_UNORM,0,24,D3D11_INPUT_PER_VERTEX_DATA,0},
        {"TEXCOORD",3,DXGI_FORMAT_R8G8B8A8_UNORM,0,28,D3D11_INPUT_PER_VERTEX_DATA,0}};
    Check(cache.device->CreateInputLayout(elements,static_cast<UINT>(std::size(elements)),heightVertex->GetBufferPointer(),heightVertex->GetBufferSize(),&result->heightLayout),"Lighting height private input layout");
    D3D11_BUFFER_DESC bd{};bd.ByteWidth=69*69*sizeof(OriginalVertex);bd.Usage=D3D11_USAGE_DYNAMIC;
    bd.BindFlags=D3D11_BIND_VERTEX_BUFFER;bd.CPUAccessFlags=D3D11_CPU_ACCESS_WRITE;
    Check(cache.device->CreateBuffer(&bd,nullptr,&result->vertices),"Lighting height shared 69-square vertex buffer");
    std::vector<std::uint16_t> indices;indices.reserve(68*68*6);
    for(unsigned y=0;y<68;++y)for(unsigned x=0;x<68;++x){const auto a=static_cast<std::uint16_t>(y*69+x),b=static_cast<std::uint16_t>(a+1);
        const auto c=static_cast<std::uint16_t>(a+69),d=static_cast<std::uint16_t>(c+1);indices.insert(indices.end(),{a,b,c,b,d,c});}
    bd={};bd.ByteWidth=static_cast<UINT>(indices.size()*sizeof(std::uint16_t));bd.Usage=D3D11_USAGE_IMMUTABLE;bd.BindFlags=D3D11_BIND_INDEX_BUFFER;
    D3D11_SUBRESOURCE_DATA initial{indices.data(),0,0};Check(cache.device->CreateBuffer(&bd,&initial,&result->indices),"Lighting height shared grid indices");
    bd={};bd.ByteWidth=sizeof(LightingFieldConstants);bd.Usage=D3D11_USAGE_DEFAULT;bd.BindFlags=D3D11_BIND_CONSTANT_BUFFER;
    Check(cache.device->CreateBuffer(&bd,nullptr,&result->constants),"Lighting field constants");
    D3D11_TEXTURE2D_DESC td{};td.Width=td.Height=68;td.MipLevels=td.ArraySize=1;td.SampleDesc.Count=1;
    td.Format=DXGI_FORMAT_R16_FLOAT;td.Usage=D3D11_USAGE_DEFAULT;td.BindFlags=D3D11_BIND_RENDER_TARGET|D3D11_BIND_SHADER_RESOURCE;
    Check(cache.device->CreateTexture2D(&td,nullptr,&result->height),"Shared candidate material height cache");
    Check(cache.device->CreateRenderTargetView(result->height.Get(),nullptr,&result->heightView),"Shared material height output");
    Check(cache.device->CreateShaderResourceView(result->height.Get(),nullptr,&result->heightResource),"Shared material height input");
    D3D11_SAMPLER_DESC sampler{};sampler.Filter=D3D11_FILTER_MIN_MAG_MIP_LINEAR;
    sampler.AddressU=sampler.AddressV=sampler.AddressW=D3D11_TEXTURE_ADDRESS_WRAP;sampler.MaxAnisotropy=1;
    sampler.ComparisonFunc=D3D11_COMPARISON_NEVER;sampler.MaxLOD=0;
    Check(cache.device->CreateSamplerState(&sampler,&result->wrapSampler),"Candidate material mip-zero sampler");
    D3D11_DEPTH_STENCIL_DESC depth{};depth.DepthEnable=FALSE;depth.DepthWriteMask=D3D11_DEPTH_WRITE_MASK_ZERO;depth.DepthFunc=D3D11_COMPARISON_ALWAYS;
    Check(cache.device->CreateDepthStencilState(&depth,&result->depthDisabled),"Lighting field depth disabled");return result;
}

// Preserve the renderer-owned state touched by these offscreen passes. Camera
// b0 and lighting b3 are never modified. Clear own PS slots before OM changes.
struct RestoreLightingFieldPipeline final {
    Cache& cache;
    std::array<ComPtr<ID3D11ShaderResourceView>,45> resources;
    std::array<ComPtr<ID3D11RenderTargetView>,D3D11_SIMULTANEOUS_RENDER_TARGET_COUNT> outputs;
    ComPtr<ID3D11DepthStencilView> depthTarget;
    ComPtr<ID3D11DepthStencilState> depthState;UINT stencil=0;
    ComPtr<ID3D11BlendState> blend;float blendFactor[4]{};UINT sampleMask=0;
    ComPtr<ID3D11RasterizerState> raster;
    std::array<D3D11_VIEWPORT,D3D11_VIEWPORT_AND_SCISSORRECT_OBJECT_COUNT_PER_PIPELINE> viewports{};
    UINT viewportCount=D3D11_VIEWPORT_AND_SCISSORRECT_OBJECT_COUNT_PER_PIPELINE;
    ComPtr<ID3D11InputLayout> layout;D3D11_PRIMITIVE_TOPOLOGY topology=D3D11_PRIMITIVE_TOPOLOGY_UNDEFINED;
    ComPtr<ID3D11Buffer> vertices,indices,vertexConstants,pixelConstants;UINT stride=0,vertexOffset=0,indexOffset=0;DXGI_FORMAT indexFormat=DXGI_FORMAT_UNKNOWN;
    ComPtr<ID3D11VertexShader> vs;ComPtr<ID3D11PixelShader> ps;ComPtr<ID3D11GeometryShader> gs;
    ComPtr<ID3D11HullShader> hs;ComPtr<ID3D11DomainShader> ds;
    ComPtr<ID3D11SamplerState> sampler;ComPtr<ID3D11Predicate> predicate;BOOL predicateValue=FALSE;
    explicit RestoreLightingFieldPipeline(Cache& value):cache(value){
        std::array<ID3D11ShaderResourceView*,45> rawResources{};cache.context->PSGetShaderResources(0,45,rawResources.data());
        for(unsigned i=0;i<resources.size();++i)resources[i].Attach(rawResources[i]);
        std::array<ID3D11RenderTargetView*,D3D11_SIMULTANEOUS_RENDER_TARGET_COUNT> rawOutputs{};
        cache.context->OMGetRenderTargets(static_cast<UINT>(rawOutputs.size()),rawOutputs.data(),&depthTarget);
        for(unsigned i=0;i<rawOutputs.size();++i)outputs[i].Attach(rawOutputs[i]);
        cache.context->OMGetDepthStencilState(&depthState,&stencil);cache.context->OMGetBlendState(&blend,blendFactor,&sampleMask);
        cache.context->RSGetState(&raster);cache.context->RSGetViewports(&viewportCount,viewports.data());
        cache.context->IAGetInputLayout(&layout);cache.context->IAGetPrimitiveTopology(&topology);
        cache.context->IAGetVertexBuffers(0,1,&vertices,&stride,&vertexOffset);cache.context->IAGetIndexBuffer(&indices,&indexFormat,&indexOffset);
        cache.context->VSGetConstantBuffers(4,1,&vertexConstants);cache.context->PSGetConstantBuffers(4,1,&pixelConstants);
        cache.context->VSGetShader(&vs,nullptr,nullptr);cache.context->PSGetShader(&ps,nullptr,nullptr);cache.context->GSGetShader(&gs,nullptr,nullptr);
        cache.context->HSGetShader(&hs,nullptr,nullptr);cache.context->DSGetShader(&ds,nullptr,nullptr);
        cache.context->PSGetSamplers(0,1,&sampler);cache.context->GetPredication(&predicate,&predicateValue);
    }
    ~RestoreLightingFieldPipeline() noexcept {
        cache.context->OMSetRenderTargets(0,nullptr,nullptr);std::array<ID3D11ShaderResourceView*,45> empty{};cache.context->PSSetShaderResources(0,45,empty.data());
        cache.context->IASetInputLayout(layout.Get());cache.context->IASetPrimitiveTopology(topology);
        ID3D11Buffer* vb=vertices.Get();cache.context->IASetVertexBuffers(0,1,&vb,&stride,&vertexOffset);
        cache.context->IASetIndexBuffer(indices.Get(),indexFormat,indexOffset);
        ID3D11Buffer* vcb=vertexConstants.Get();ID3D11Buffer* pcb=pixelConstants.Get();cache.context->VSSetConstantBuffers(4,1,&vcb);cache.context->PSSetConstantBuffers(4,1,&pcb);
        cache.context->VSSetShader(vs.Get(),nullptr,0);cache.context->PSSetShader(ps.Get(),nullptr,0);cache.context->GSSetShader(gs.Get(),nullptr,0);
        cache.context->HSSetShader(hs.Get(),nullptr,0);cache.context->DSSetShader(ds.Get(),nullptr,0);
        ID3D11SamplerState* oldSampler=sampler.Get();cache.context->PSSetSamplers(0,1,&oldSampler);cache.context->SetPredication(predicate.Get(),predicateValue);
        cache.context->RSSetState(raster.Get());cache.context->RSSetViewports(viewportCount,viewportCount?viewports.data():nullptr);
        cache.context->OMSetDepthStencilState(depthState.Get(),stencil);cache.context->OMSetBlendState(blend.Get(),blendFactor,sampleMask);
        std::array<ID3D11RenderTargetView*,D3D11_SIMULTANEOUS_RENDER_TARGET_COUNT> oldOutputs{};
        for(unsigned i=0;i<oldOutputs.size();++i)oldOutputs[i]=outputs[i].Get();
        cache.context->OMSetRenderTargets(static_cast<UINT>(oldOutputs.size()),oldOutputs.data(),depthTarget.Get());
        std::array<ID3D11ShaderResourceView*,45> oldResources{};for(unsigned i=0;i<resources.size();++i)oldResources[i]=resources[i].Get();
        cache.context->PSSetShaderResources(0,45,oldResources.data());
    }
};

std::unique_ptr<LightingField> BuildLightingField(Cache& cache,LightingFieldBaker& baker,OriginalCatalog& catalog,
    OriginalSurface& surface,const OriginalGpuMesh& mesh,const std::vector<unsigned char>& known68,
    const std::vector<std::uint16_t>& shadow66,float normalStrength=16.0f){
    Require(known68.size()==68*68 && shadow66.size()==66*66 && std::all_of(known68.begin(),known68.end(),[](unsigned char b){return b<=1;}),"Invalid bounded lighting field arrays");
    Require(surface.width>0 && surface.height>0 && mesh.column<static_cast<unsigned>(surface.width) && mesh.row<static_cast<unsigned>(surface.height) &&
        mesh.slots.count<=8 && std::isfinite(normalStrength) && normalStrength>=0 && normalStrength<=65536,"Invalid lighting field geometry or strength");
    auto result=std::make_unique<LightingField>();D3D11_TEXTURE2D_DESC td{};td.Width=td.Height=66;
    // Original storage and active RTV/SRV views are recovered independently
    // of this candidate 66-square mip0 footprint and its halo policy.
    const auto normalDescription=OriginalTerrainCache::NormalCacheDescriptor();
    td.MipLevels=td.ArraySize=1;td.SampleDesc.Count=1;td.Usage=D3D11_USAGE_DEFAULT;
    td.Format=static_cast<DXGI_FORMAT>(normalDescription.resourceFormat);
    td.BindFlags=D3D11_BIND_RENDER_TARGET|D3D11_BIND_SHADER_RESOURCE;ComPtr<ID3D11Texture2D> normal;
    Check(cache.device->CreateTexture2D(&td,nullptr,&normal),"Candidate per-chunk normal field");ComPtr<ID3D11RenderTargetView> normalView;
    D3D11_RENDER_TARGET_VIEW_DESC normalOutput{};normalOutput.Format=static_cast<DXGI_FORMAT>(normalDescription.renderViewFormat);
    normalOutput.ViewDimension=D3D11_RTV_DIMENSION_TEXTURE2D;
    Check(cache.device->CreateRenderTargetView(normal.Get(),&normalOutput,&normalView),"Original normal UNORM output view");
    D3D11_SHADER_RESOURCE_VIEW_DESC normalInput{};normalInput.Format=static_cast<DXGI_FORMAT>(normalDescription.sampleViewFormat);
    normalInput.ViewDimension=D3D11_SRV_DIMENSION_TEXTURE2D;normalInput.Texture2D.MipLevels=1;
    Check(cache.device->CreateShaderResourceView(normal.Get(),&normalInput,&result->normal),"Original normal UNORM sample view");
    td.Format=DXGI_FORMAT_R16_UNORM;td.Usage=D3D11_USAGE_IMMUTABLE;td.BindFlags=D3D11_BIND_SHADER_RESOURCE;
    D3D11_SUBRESOURCE_DATA initial{shadow66.data(),66*2,0};ComPtr<ID3D11Texture2D> shadow;
    Check(cache.device->CreateTexture2D(&td,&initial,&shadow),"Candidate per-chunk shadow field");
    Check(cache.device->CreateShaderResourceView(shadow.Get(),nullptr,&result->shadow),"Candidate per-chunk shadow input");
    td.Width=td.Height=68;td.Format=DXGI_FORMAT_R8_UINT;initial={known68.data(),68,0};ComPtr<ID3D11Texture2D> known;
    ComPtr<ID3D11ShaderResourceView> knownResource;Check(cache.device->CreateTexture2D(&td,&initial,&known),"Candidate per-chunk known mask");
    Check(cache.device->CreateShaderResourceView(known.Get(),nullptr,&knownResource),"Candidate per-chunk known input");
    std::vector<OriginalVertex> fieldVertices;fieldVertices.reserve(69*69);
    const int startX=static_cast<int>(mesh.column*64),startY=static_cast<int>(mesh.row*64);
    for(int y=-2;y<=66;++y)for(int x=-2;x<=66;++x){const int px=startX+x,py=startY+y;
        const auto n=OT::SurfaceNormal(surface.atlas,px,py,OT::HeightWorldScaleCandidate);
        const auto weights=OT::QuantizeWeights(OT::KernelWeights(surface.atlas,catalog.table,mesh.slots,px,py,n));
        std::uint32_t w0=0,w1=0;std::memcpy(&w0,weights.data(),4);std::memcpy(&w1,weights.data()+4,4);
        const float u=static_cast<float>(x)/64.0f,v=static_cast<float>(y)/64.0f;
        const float h=OT::AtlasWorldHeight(surface.atlas,px,py);
        fieldVertices.push_back({u,h,-v*OT::RowSpacing,u,v,1,w0,w1,n.x,n.y,n.z});
    }
    LightingFieldConstants constants{};constants.origin[0]=static_cast<float>(mesh.column);constants.origin[1]=static_cast<float>(mesh.row);
    constants.origin[2]=OT::RetailWorldUnitsPerHexCandidate;constants.origin[3]=static_cast<float>(mesh.slots.count);constants.parameters[0]=normalStrength;
    constants.parameters[1]=static_cast<float>(surface.width);constants.parameters[2]=static_cast<float>(surface.height);
    constants.parameters[3]=(surface.wrapX?1.0f:0.0f)+(surface.wrapY?2.0f:0.0f);
    constants.worldAdapter[0]=OT::DisplayHeightOriginCandidate();
    constants.worldAdapter[1]=OriginalTerrainCacheSampling::SourceMetricYDefault;
    std::array<ID3D11ShaderResourceView*,45> resources{};
    for(unsigned i=0;i<mesh.slots.count;++i){const auto& material=catalog.table.expanded.at(mesh.slots.materials[i]);const auto& row=catalog.rows.at(material.row);
        constants.materials[i][0]=material.scale;constants.materials[i][1]=static_cast<float>(material.projection);
        constants.materials[i][2]=row.height==OT::DeclaredMissingTexture?-1.0f:row.height==OT::NullTexture?0.0f:1.0f;
        resources[i]=catalog.textures.at(row.diffuse).Get();if(row.height<catalog.textures.size())resources[8+i]=catalog.textures[row.height].Get();}
    resources[16]=knownResource.Get();
    RestoreLightingFieldPipeline restore(cache);
    D3D11_MAPPED_SUBRESOURCE mapped{};Check(cache.context->Map(baker.vertices.Get(),0,D3D11_MAP_WRITE_DISCARD,0,&mapped),"Lighting height shared vertices map");
    std::memcpy(mapped.pData,fieldVertices.data(),fieldVertices.size()*sizeof(OriginalVertex));cache.context->Unmap(baker.vertices.Get(),0);
    cache.context->UpdateSubresource(baker.constants.Get(),0,nullptr,&constants,0,0);
    std::array<ID3D11ShaderResourceView*,45> empty{};cache.context->PSSetShaderResources(0,45,empty.data());cache.context->OMSetRenderTargets(0,nullptr,nullptr);
    cache.context->GSSetShader(nullptr,nullptr,0);cache.context->HSSetShader(nullptr,nullptr,0);cache.context->DSSetShader(nullptr,nullptr,0);
    // The render owner explicitly detaches stream output before every private
    // bake and reestablishes its main/reflection pipeline after preparation.
    cache.context->SOSetTargets(0,nullptr,nullptr);cache.context->SetPredication(nullptr,FALSE);
    cache.context->RSSetState(cache.raster.Get());cache.context->OMSetDepthStencilState(baker.depthDisabled.Get(),0);cache.context->OMSetBlendState(cache.blendState.Get(),nullptr,0xffffffffu);
    const D3D11_VIEWPORT heightViewport{0,0,68,68,0,1};cache.context->RSSetViewports(1,&heightViewport);
    ID3D11RenderTargetView* output=baker.heightView.Get();cache.context->OMSetRenderTargets(1,&output,nullptr);
    cache.context->IASetInputLayout(baker.heightLayout.Get());cache.context->IASetPrimitiveTopology(D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST);
    ID3D11Buffer* vb=baker.vertices.Get();const UINT stride=sizeof(OriginalVertex),offset=0;cache.context->IASetVertexBuffers(0,1,&vb,&stride,&offset);
    cache.context->IASetIndexBuffer(baker.indices.Get(),DXGI_FORMAT_R16_UINT,0);
    cache.context->VSSetShader(baker.heightVs.Get(),nullptr,0);cache.context->PSSetShader(baker.heightPs.Get(),nullptr,0);
    ID3D11Buffer* cb=baker.constants.Get();cache.context->VSSetConstantBuffers(4,1,&cb);cache.context->PSSetConstantBuffers(4,1,&cb);
    ID3D11SamplerState* wrap=baker.wrapSampler.Get();cache.context->PSSetSamplers(0,1,&wrap);cache.context->PSSetShaderResources(0,45,resources.data());
    cache.context->DrawIndexed(68*68*6,0,0);
    cache.context->OMSetRenderTargets(0,nullptr,nullptr);cache.context->PSSetShaderResources(0,45,empty.data());
    const D3D11_VIEWPORT normalViewport{0,0,66,66,0,1};cache.context->RSSetViewports(1,&normalViewport);
    output=normalView.Get();cache.context->OMSetRenderTargets(1,&output,nullptr);
    cache.context->IASetInputLayout(nullptr);cache.context->IASetIndexBuffer(nullptr,DXGI_FORMAT_UNKNOWN,0);
    ID3D11Buffer* noVertices=nullptr;cache.context->IASetVertexBuffers(0,1,&noVertices,&offset,&offset);
    cache.context->VSSetShader(baker.normalVs.Get(),nullptr,0);cache.context->PSSetShader(baker.normalPs.Get(),nullptr,0);
    ID3D11ShaderResourceView* heightInputs[]={baker.heightResource.Get(),knownResource.Get()};cache.context->PSSetShaderResources(0,2,heightInputs);
    cache.context->Draw(3,0);return result;
}
