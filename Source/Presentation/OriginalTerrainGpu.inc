std::unique_ptr<OriginalCatalog> LoadOriginalCatalog(ID3D11Device* device,std::vector<unsigned char> bytes){
    auto package=OT::DecodePackage(std::move(bytes),OT::PackageSha256);
    auto result=std::make_unique<OriginalCatalog>();result->rows=package.rows;
    std::vector<OT::Material> rows;
    for(const auto& row:result->rows)rows.push_back({row.row,row.projection,row.scale});
    result->table=OT::ExpandMaterials(rows);
    for(const auto& source:package.textures){
        D3D11_TEXTURE2D_DESC td{};td.Width=source.width;td.Height=source.height;td.MipLevels=source.mips;td.ArraySize=1;
        td.Format=DXGI_FORMAT_BC3_UNORM;td.SampleDesc.Count=1;td.Usage=D3D11_USAGE_IMMUTABLE;td.BindFlags=D3D11_BIND_SHADER_RESOURCE;
        std::vector<D3D11_SUBRESOURCE_DATA> levels;std::size_t offset=source.offset+128;
        for(unsigned mip=0;mip<source.mips;++mip){
            const unsigned pitch=((std::max(1u,source.width>>mip)+3)/4)*16;
            const unsigned size=pitch*((std::max(1u,source.height>>mip)+3)/4);
            levels.push_back({package.bytes.data()+offset,pitch,size});offset+=size;
        }
        ComPtr<ID3D11Texture2D> texture;Check(device->CreateTexture2D(&td,levels.data(),&texture),"Original terrain texture upload");
        ComPtr<ID3D11ShaderResourceView> view;Check(device->CreateShaderResourceView(texture.Get(),nullptr,&view),"Original terrain raw UNORM view");
        result->textures.push_back(std::move(view));
    }
    std::vector<unsigned char> library(package.bytes.begin()+package.libraryOffset,
        package.bytes.begin()+package.libraryOffset+package.libraryBytes);
    result->library=OT::DecodeLibrary(std::move(library),static_cast<unsigned>(result->rows.size()));
    ComPtr<ID3DBlob> vertex,pixel,diagnostic;
    const auto flags=D3DCOMPILE_ENABLE_STRICTNESS|D3DCOMPILE_WARNINGS_ARE_ERRORS;
    const std::string terrainSource=std::string(OSL::ShaderSource)+OT::ShaderSource;
    Check(D3DCompile(Tess::ShaderSource,sizeof(Tess::ShaderSource)-1,"OriginalTerrainPatch",nullptr,nullptr,"worldVertexMain","vs_5_0",flags,0,&vertex,&diagnostic),"Original terrain world placement shader compile");
    Check(D3DCompile(terrainSource.data(),terrainSource.size(),"OriginalTerrain",nullptr,nullptr,"pixelMain","ps_5_0",flags,0,&pixel,&diagnostic),"Original terrain pixel shader compile");
    Check(device->CreateVertexShader(vertex->GetBufferPointer(),vertex->GetBufferSize(),nullptr,&result->vs),"Original terrain vertex shader");
    Check(device->CreatePixelShader(pixel->GetBufferPointer(),pixel->GetBufferSize(),nullptr,&result->ps),"Original terrain pixel shader");
    const auto patchShader=[&](const char* entry,const char* profile){
        ComPtr<ID3DBlob> shader;
        Check(D3DCompile(Tess::ShaderSource,sizeof(Tess::ShaderSource)-1,"OriginalTerrainPatch",nullptr,nullptr,
            entry,profile,flags,0,&shader,nullptr),entry);
        return shader;
    };
    const auto controls=patchShader("worldControlMain","vs_5_0");
    const auto hull=patchShader("hullMain","hs_5_0"),domain=patchShader("worldDomainMain","ds_5_0");
    Check(device->CreateVertexShader(controls->GetBufferPointer(),controls->GetBufferSize(),nullptr,&result->controlVs),"Terrain control VS");
    Check(device->CreateHullShader(hull->GetBufferPointer(),hull->GetBufferSize(),nullptr,&result->hs),"Terrain hull shader");
    Check(device->CreateDomainShader(domain->GetBufferPointer(),domain->GetBufferSize(),nullptr,&result->ds),"Terrain domain shader");
    const D3D11_INPUT_ELEMENT_DESC elements[]={
        {"POSITION",0,DXGI_FORMAT_R32G32B32_FLOAT,0,0,D3D11_INPUT_PER_VERTEX_DATA,0},
        {"TEXCOORD",0,DXGI_FORMAT_R32G32_FLOAT,0,12,D3D11_INPUT_PER_VERTEX_DATA,0},
        {"TEXCOORD",1,DXGI_FORMAT_R32_FLOAT,0,20,D3D11_INPUT_PER_VERTEX_DATA,0},
        {"TEXCOORD",2,DXGI_FORMAT_R8G8B8A8_UNORM,0,24,D3D11_INPUT_PER_VERTEX_DATA,0},
        {"TEXCOORD",3,DXGI_FORMAT_R8G8B8A8_UNORM,0,28,D3D11_INPUT_PER_VERTEX_DATA,0},
        {"TEXCOORD",5,DXGI_FORMAT_R32G32B32_FLOAT,0,32,D3D11_INPUT_PER_VERTEX_DATA,0}};
    Check(device->CreateInputLayout(elements,static_cast<UINT>(std::size(elements)),vertex->GetBufferPointer(),vertex->GetBufferSize(),&result->layout),"Original terrain vertex layout");
    D3D11_BUFFER_DESC cb{};cb.ByteWidth=sizeof(OriginalConstants);cb.Usage=D3D11_USAGE_DEFAULT;cb.BindFlags=D3D11_BIND_CONSTANT_BUFFER;
    Check(device->CreateBuffer(&cb,nullptr,&result->constants),"Original terrain chunk constants");
    cb.ByteWidth=sizeof(Tess::DomainConstants);
    Check(device->CreateBuffer(&cb,nullptr,&result->patchConstants),"Original terrain patch placement constants");
    const auto indexBuffer=[&](const std::vector<std::uint16_t>& values,ComPtr<ID3D11Buffer>& target){
        D3D11_BUFFER_DESC bd{};bd.ByteWidth=static_cast<UINT>(values.size()*sizeof(std::uint16_t));
        bd.Usage=D3D11_USAGE_IMMUTABLE;bd.BindFlags=D3D11_BIND_INDEX_BUFFER;
        D3D11_SUBRESOURCE_DATA initial{values.data(),0,0};Check(device->CreateBuffer(&bd,&initial,&target),"Original terrain grid indices");
    };
    std::vector<std::uint16_t> indices;indices.reserve(64*64*6);
    std::vector<std::uint16_t> rim,interior;
    rim.reserve(OT::PatchWorld::RimIndices);interior.reserve(OT::PatchWorld::InteriorIndices);
    for(unsigned y=0;y<64;++y)for(unsigned x=0;x<64;++x){
        const auto a=static_cast<std::uint16_t>(y*65+x),b=static_cast<std::uint16_t>(a+1);
        const auto c=static_cast<std::uint16_t>(a+65),d=static_cast<std::uint16_t>(c+1);
        indices.insert(indices.end(),{a,b,c,b,d,c});
        if(x==0 || x==63 || y==0 || y==63)rim.insert(rim.end(),{a,b,c,b,d,c});
        else for(unsigned dy=0;dy<4;++dy)for(unsigned dx=0;dx<4;++dx)
            interior.push_back(static_cast<std::uint16_t>((y-1+dy)*65+x-1+dx));
    }
    indexBuffer(indices,result->indices);indexBuffer({0,1,2,1,3,2},result->quadIndices);
    indexBuffer(rim,result->rimIndices);indexBuffer(interior,result->interiorIndices);
    return result;
}

std::shared_ptr<OriginalSurface> PrepareOriginalSurface(const WorldView& view,OriginalCatalog& catalog){
    auto cells=OT::CaptureTerrainCells(view);
    const auto& old=catalog.surface;
    if(old && old->width==view.gridWidth && old->height==view.gridHeight && old->wrapX==view.wrapX && old->wrapY==view.wrapY &&
       old->seed==view.mapRandomSeed && OT::SameTerrainCells(old->cells,cells))return old;
    auto next=std::make_shared<OriginalSurface>();next->width=view.gridWidth;next->height=view.gridHeight;
    next->wrapX=view.wrapX;next->wrapY=view.wrapY;next->seed=view.mapRandomSeed;next->cells=std::move(cells);
    const auto placements=OT::PlacePieces(next->cells,static_cast<unsigned>(view.gridWidth),static_cast<unsigned>(view.gridHeight),catalog.library,view.mapRandomSeed);
    next->atlas=OT::BuildAtlas(next->cells,static_cast<unsigned>(view.gridWidth),static_cast<unsigned>(view.gridHeight),
        catalog.library,placements.placements,OT::HeightOffsetCandidate,OT::DefaultMaxAtlasTexels,view.wrapX,view.wrapY);
    next->meshes.resize(next->cells.size());return next;
}

std::shared_ptr<OriginalGpuMesh> OriginalMesh(Cache& cache,OriginalSurface& surface,unsigned column,unsigned row){
    const auto index=static_cast<std::size_t>(row)*surface.width+column;
    auto result=surface.meshes.at(index).lock();if(result)return result;
    result=std::make_shared<OriginalGpuMesh>();result->column=column;result->row=row;
    const int startX=static_cast<int>(column*64),startY=static_cast<int>(row*64);
    result->slots=OT::ChunkTop8(surface.atlas,cache.original->table,startX,startY,64,64,OT::HeightWorldScaleCandidate);
    result->dense=result->slots.count!=0;
    result->bicubicInterior=result->dense && OT::HasPatchControls(surface.atlas,column,row);
    const auto vertices=OT::PrepareTerrainVertices<OriginalVertex>(surface.atlas,cache.original->table,result->slots,column,row);
    D3D11_BUFFER_DESC bd{};bd.ByteWidth=static_cast<UINT>(vertices.size()*sizeof(OriginalVertex));
    bd.Usage=D3D11_USAGE_IMMUTABLE;bd.BindFlags=D3D11_BIND_VERTEX_BUFFER;
    D3D11_SUBRESOURCE_DATA initial{vertices.data(),0,0};Check(cache.device->CreateBuffer(&bd,&initial,&result->vertices),"Original global heightfield chunk upload");
    surface.meshes[index]=result;return result;
}

void PrepareOriginalGround(const WorldView& view,Cache& cache,const XMMATRIX& camera,const XMMATRIX& matrix,
    unsigned width,unsigned height,unsigned mapWidth,GroundData& candidate,TerrainFrame& frame){
    candidate.original=std::make_unique<OriginalGroundData>();auto& ground=*candidate.original;
    ground.surface=PrepareOriginalSurface(view,*cache.original);
    const auto patchFrame=OT::PatchFrameForCamera(ground.surface->atlas,view.cameraX,view.cameraY);
    const float centerX=static_cast<float>(view.cameraX)+static_cast<float>(view.cameraY&1)*0.5f;
    const float centerZ=-static_cast<float>(view.cameraY)*OT::RowSpacing;
    std::vector<std::array<std::uint32_t,2>> states(static_cast<std::size_t>(view.gridWidth)*view.gridHeight);
    for(const auto& p:view.plots){
        auto& state=states[static_cast<std::size_t>(p.y)*view.gridWidth+p.x];state[1]=p.revealed?(p.visible?2u:1u):0u;
        if(p.revealed&&p.visible){frame.picking.keys.push_back(WorldViewHitKey::Plot(p.index));state[0]=static_cast<std::uint32_t>(frame.picking.keys.size());}
        if(!state[0])continue;
        int dx=p.x-view.cameraX,dy=p.y-view.cameraY;
        if(view.wrapX){if(dx>view.gridWidth/2)dx-=view.gridWidth;else if(dx<-view.gridWidth/2)dx+=view.gridWidth;}
        if(view.wrapY){if(dy>view.gridHeight/2)dy-=view.gridHeight;else if(dy<-view.gridHeight/2)dy+=view.gridHeight;}
        const float wx=static_cast<float>(dx)+static_cast<float>((p.y&1)-(view.cameraY&1))*0.5f,wz=-static_cast<float>(dy)*OT::RowSpacing;
        float elevation=OT::AtlasWorldHeight(ground.surface->atlas,(p.x+(p.y&1)*0.5)*64.0,p.y*64.0);
        if(!view.waterSurfaceAssetsPath.empty()&&p.water)elevation=std::max(elevation,OriginalWaterSurfaceBinding::WorldPlaneCandidate);
        const auto projected=XMVector4Transform(XMVectorSet(wx,elevation,wz,1),matrix);
        const float pw=XMVectorGetW(projected),pz=XMVectorGetZ(projected);
        if(pw>0 && pz>=0 && pz<=pw){
            const float px=(XMVectorGetX(projected)/pw+1)*0.5f*static_cast<float>(mapWidth),py=(1-XMVectorGetY(projected)/pw)*0.5f*static_cast<float>(height);
            if(px>=0 && px<static_cast<float>(mapWidth) && py>=0 && py<static_cast<float>(height))frame.centers.emplace(p.index,TerrainProjection{px,py});
        }
    }
    D3D11_TEXTURE2D_DESC td{};td.Width=static_cast<UINT>(view.gridWidth);td.Height=static_cast<UINT>(view.gridHeight);
    td.MipLevels=td.ArraySize=1;td.Format=DXGI_FORMAT_R32G32_UINT;td.SampleDesc.Count=1;td.Usage=D3D11_USAGE_IMMUTABLE;td.BindFlags=D3D11_BIND_SHADER_RESOURCE;
    D3D11_SUBRESOURCE_DATA initial{states.data(),static_cast<UINT>(view.gridWidth*8),0};ComPtr<ID3D11Texture2D> texture;
    Check(cache.device->CreateTexture2D(&td,&initial,&texture),"Original independent tile identity texture");
    Check(cache.device->CreateShaderResourceView(texture.Get(),nullptr,&ground.plotState),"Original tile state view");
    std::vector<unsigned char> selectors(states.size(),255);
    if(!view.lightingAssetsPath.empty())selectors=LG::CaptureLightingSelectors(view);
    td.Format=DXGI_FORMAT_R8_UINT;initial={selectors.data(),static_cast<UINT>(view.gridWidth),0};texture.Reset();
    Check(cache.device->CreateTexture2D(&td,&initial,&texture),"Original revealed lighting selector upload");
    Check(cache.device->CreateShaderResourceView(texture.Get(),nullptr,&ground.lightingSelectors),"Original revealed lighting selector view");
    for(int row=view.cameraY-49;row<=view.cameraY+49;++row)for(int column=view.cameraX-49;column<=view.cameraX+49;++column){
        if((!view.wrapX&&(column< -1 || column>=view.gridWidth)) || (!view.wrapY&&(row< -1 || row>=view.gridHeight)))continue;
        const float wx=static_cast<float>(column)+0.5f-centerX,wz=-(static_cast<float>(row)+0.5f)*OT::RowSpacing-centerZ;
        const auto clip=XMVector3TransformCoord(XMVectorSet(wx,0.5f,wz,0),camera);
        const float z=XMVectorGetZ(clip),extent=(z+3)*std::tan(XM_PIDIV4/2);
        const bool outside=z< -3 || z>153 || std::abs(XMVectorGetX(clip))>extent*static_cast<float>(mapWidth)/static_cast<float>(height)+3 || std::abs(XMVectorGetY(clip))>extent+3;
        if(outside){
            if(view.waterSurfaceAssetsPath.empty()&&view.lightingAssetsPath.empty())continue;
            const auto reflected=XMMatrixReflect(XMVectorSet(0,1,0,-OriginalWaterSurfaceBinding::WorldPlaneCandidate))*camera;
            const auto mirrored=XMVector3TransformCoord(XMVectorSet(wx,0.5f,wz,0),reflected);
            const float rz=XMVectorGetZ(mirrored),re=(rz+3)*std::tan(XM_PIDIV4/2);
            if(rz< -3||rz>153||std::abs(XMVectorGetX(mirrored))>re*static_cast<float>(mapWidth)/static_cast<float>(height)+3||std::abs(XMVectorGetY(mirrored))>re+3)continue;
        }
        const auto x=static_cast<unsigned>(OT::WrappedCoordinate(column,view.gridWidth));
        const auto y=static_cast<unsigned>(OT::WrappedCoordinate(row,view.gridHeight));
        auto mesh=OriginalMesh(cache,*ground.surface,x,y);frame.triangles+=mesh->dense?8192u:2u;
        Require(frame.triangles<=24000000,"Original visible heightfield exceeds its controlled mesh bound");
        ground.draws.push_back({std::move(mesh),column,row,OT::PatchWorld::Place(patchFrame,x,y,column,row,0)});
    }
    (void)width;
}

Tess::DomainConstants TerrainDomainForView(const XMMATRIX& viewProjection){
    XMFLOAT4X4 matrix;XMStoreFloat4x4(&matrix,viewProjection);
    std::array<float,16> projection;
    static_assert(sizeof(matrix)==sizeof(projection),"Unexpected terrain view matrix layout");
    std::memcpy(projection.data(),&matrix,sizeof(matrix));
    return Tess::WorldDomainConstants(projection);
}

// Color, integer plot IDs and the terrain shadow caster all submit the same
// world-space vertices. Control heights stay in the existing mesh buffer.
void DrawPlacedTerrainMesh(Cache& cache,const OriginalDraw& draw,Tess::DomainConstants& domain){
    auto& catalog=*cache.original;auto* context=cache.context.Get();const auto& mesh=*draw.mesh;
    ID3D11Buffer* cb=catalog.patchConstants.Get();
    domain.SetPlacement(draw.patch);context->UpdateSubresource(cb,0,nullptr,&domain,0,0);
    context->VSSetConstantBuffers(7,1,&cb);context->VSSetShader(catalog.vs.Get(),nullptr,0);
    context->IASetInputLayout(catalog.layout.Get());context->IASetPrimitiveTopology(D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST);
    ID3D11Buffer* vertices=mesh.vertices.Get();const UINT stride=sizeof(OriginalVertex),offset=0;
    context->IASetVertexBuffers(0,1,&vertices,&stride,&offset);
    if(!mesh.bicubicInterior){
        context->IASetIndexBuffer(mesh.dense?catalog.indices.Get():catalog.quadIndices.Get(),DXGI_FORMAT_R16_UINT,0);
        context->DrawIndexed(mesh.dense?64*64*6:6,0,0);return;
    }
    context->IASetIndexBuffer(catalog.rimIndices.Get(),DXGI_FORMAT_R16_UINT,0);
    context->DrawIndexed(OT::PatchWorld::RimIndices,0,0);
    domain.SetPlacement(OT::PatchWorld::Interior(draw.patch));context->UpdateSubresource(cb,0,nullptr,&domain,0,0);
    context->HSSetConstantBuffers(7,1,&cb);context->DSSetConstantBuffers(7,1,&cb);
    context->VSSetShader(catalog.controlVs.Get(),nullptr,0);context->HSSetShader(catalog.hs.Get(),nullptr,0);
    context->DSSetShader(catalog.ds.Get(),nullptr,0);
    context->IASetIndexBuffer(catalog.interiorIndices.Get(),DXGI_FORMAT_R16_UINT,0);
    context->IASetPrimitiveTopology(D3D11_PRIMITIVE_TOPOLOGY_16_CONTROL_POINT_PATCHLIST);
    context->DrawIndexed(OT::PatchWorld::InteriorIndices,0,0);
    context->HSSetShader(nullptr,nullptr,0);context->DSSetShader(nullptr,nullptr,0);
    context->IASetPrimitiveTopology(D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST);
}

void DrawOriginalGround(const WorldView& view,Cache& cache,const OriginalGroundData& ground,const XMMATRIX& viewProjection,bool fogEnabled,LightingCatalog* lighting=nullptr,
    ID3D11ShaderResourceView* reflection=nullptr,unsigned mapWidth=1,unsigned height=1){
    auto& catalog=*cache.original;
    cache.context->IASetInputLayout(catalog.layout.Get());cache.context->VSSetShader(catalog.vs.Get(),nullptr,0);cache.context->PSSetShader(catalog.ps.Get(),nullptr,0);
    ID3D11Buffer* cb=catalog.constants.Get();cache.context->VSSetConstantBuffers(1,1,&cb);cache.context->PSSetConstantBuffers(1,1,&cb);
    auto domain=TerrainDomainForView(viewProjection);
    if(lighting){
        OriginalLightingConstants parameters{};
        parameters.info[0]=1;parameters.info[2]=1;
        parameters.specularAxis[0]=-0.40824829f;parameters.specularAxis[1]=0.40824829f;parameters.specularAxis[2]=0.81649658f;
        const auto policy=OSL::ResolvePolicy(view.screenLightingPolicy);
        parameters.composition[0]=policy.diffuse?1.0f:0.0f;parameters.composition[1]=policy.specular?1.0f:0.0f;
        cache.context->UpdateSubresource(lighting->constants.Get(),0,nullptr,&parameters,0,0);
        ID3D11Buffer* lightingBuffer=lighting->constants.Get();cache.context->PSSetConstantBuffers(3,1,&lightingBuffer);
        ID3D11SamplerState* lightingSampler=lighting->clampSampler.Get();cache.context->PSSetSamplers(1,1,&lightingSampler);
        if(!cache.screenLighting)cache.screenLighting=std::make_unique<ScreenLightingGpu>(CreateScreenLightingGpu(cache.device.Get()));
        BindScreenLighting(cache.context.Get(),*cache.screenLighting,reflection,mapWidth,height,view.screenLightingPolicy);
    }
    for(const auto& draw:ground.draws){
        const auto& mesh=*draw.mesh;OriginalConstants constants{};std::array<ID3D11ShaderResourceView*,45> resources{};
        for(unsigned i=0;i<mesh.slots.count;++i){
            const auto& material=catalog.table.expanded[mesh.slots.materials[i]];const auto& row=catalog.rows.at(material.row);
            constants.materials[i][0]=material.scale;constants.materials[i][1]=static_cast<float>(material.projection);
            constants.materials[i][2]=row.height==OT::DeclaredMissingTexture?-1.0f:row.height==OT::NullTexture?0.0f:1.0f;
            constants.materials[i][3]=row.specular==OT::NullTexture?0.0f:1.0f;
            resources[i]=catalog.textures.at(row.diffuse).Get();
            if(row.height<catalog.textures.size())resources[8+i]=catalog.textures[row.height].Get();
            if(row.specular<catalog.textures.size())resources[16+i]=catalog.textures[row.specular].Get();
        }
        resources[24]=ground.plotState.Get();
        if(lighting){
            Require(mesh.slots.count==0||(mesh.lightingField&&mesh.lightingField->normal.Get()&&mesh.lightingField->shadow.Get()),"Lighting field was not prepared for this chunk");
            resources[25]=ground.lightingSelectors.Get();
            for(unsigned i=0;i<5;++i){resources[26+i]=lighting->sunlight[i].Get();resources[31+i]=lighting->shadowlight[i].Get();resources[36+i]=lighting->terrainLut[i].Get();}
            if(mesh.lightingField){resources[41]=mesh.lightingField->normal.Get();resources[42]=mesh.lightingField->shadow.Get();}
            const auto policy=OSL::ResolvePolicy(view.screenLightingPolicy);if(policy.specular)resources[44]=reflection;
        }
        const auto origin=OT::PatchWorld::DisplayOrigin(draw.patch);
        constants.placement[0]=origin[0];constants.placement[1]=origin[1];
        constants.placement[2]=static_cast<float>(draw.column);constants.placement[3]=static_cast<float>(draw.row);
        constants.mapInfo[0]=static_cast<float>(view.gridWidth);constants.mapInfo[1]=static_cast<float>(view.gridHeight);
        constants.mapInfo[2]=view.wrapX?1.0f:0.0f;constants.mapInfo[3]=view.wrapY?1.0f:0.0f;
        constants.textureOrigin[0]=static_cast<float>(mesh.column);constants.textureOrigin[1]=static_cast<float>(mesh.row);
        constants.textureOrigin[2]=OT::RetailWorldUnitsPerHexCandidate;constants.textureOrigin[3]=static_cast<float>(mesh.slots.count);
        constants.fogInfo[0]=fogEnabled?1.0f:0.0f;
        constants.fogInfo[1]=lighting?1.0f:0.0f;
        constants.fogInfo[2]=OT::DisplayHeightOriginCandidate();
        constants.fogInfo[3]=OriginalTerrainCacheSampling::SourceMetricYDefault;
        cache.context->UpdateSubresource(catalog.constants.Get(),0,nullptr,&constants,0,0);
        cache.context->PSSetShaderResources(0,static_cast<UINT>(resources.size()),resources.data());
        DrawPlacedTerrainMesh(cache,draw,domain);
    }
    std::array<ID3D11ShaderResourceView*,45> clear{};cache.context->PSSetShaderResources(0,static_cast<UINT>(clear.size()),clear.data());
    if(lighting)UnbindScreenLighting(cache.context.Get());
    ID3D11Buffer* nullBuffer=nullptr;cache.context->VSSetConstantBuffers(1,1,&nullBuffer);cache.context->PSSetConstantBuffers(1,1,&nullBuffer);
    cache.context->VSSetConstantBuffers(7,1,&nullBuffer);
    cache.context->HSSetConstantBuffers(7,1,&nullBuffer);cache.context->DSSetConstantBuffers(7,1,&nullBuffer);
    cache.context->PSSetConstantBuffers(3,1,&nullBuffer);
    cache.context->PSSetConstantBuffers(6,1,&nullBuffer);
    ID3D11SamplerState* nullSampler=nullptr;cache.context->PSSetSamplers(1,1,&nullSampler);
    cache.context->PSSetSamplers(5,1,&nullSampler);
    cache.context->IASetInputLayout(cache.layout.Get());cache.context->VSSetShader(cache.vs.Get(),nullptr,0);cache.context->PSSetShader(cache.ps.Get(),nullptr,0);
}

float GroundHeight(const Cache& cache,const GroundData& ground,const WorldViewPlot& plot){
    if(!ground.original)return Height(cache,plot,0,0,0);
    return OT::AtlasWorldHeight(ground.original->surface->atlas,(plot.x+(plot.y&1)*0.5)*64.0,plot.y*64.0);
}
