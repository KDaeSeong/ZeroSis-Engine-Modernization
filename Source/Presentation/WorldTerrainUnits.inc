std::map<unsigned,Group> PrepareTerrainUnits(const WorldView& view,Cache& cache,const GroundData& groundData,TerrainFrame& result){
    std::map<unsigned,Group> groups;if(view.unitAssetsPath.empty())return groups;
    std::map<std::pair<int,int>,const WorldViewPlot*> visible;
    for(const auto& plot:view.plots)if(plot.revealed&&plot.visible)visible.emplace(std::make_pair(plot.x,plot.y),&plot);
    Require(view.units.size()<=500000,"Unit snapshot exceeds its bound");
    for(const auto& unit:view.units){
        const auto selected=SelectWorldUnitArt({unit.type,unit.unitArtInfoTag,unit.unitArtInfoCulturalVariation,
            unit.unitArtInfoEraVariation,unit.embarked,unit.artStylePrefix,unit.artStyleSuffix,unit.eraArtPrefix});
        if(!selected)continue;const auto art=cache.units->arts.find(*selected);const auto plot=visible.find({unit.x,unit.y});
        if(art==cache.units->arts.end()||plot==visible.end())continue;
        Require(unit.facingDirection>=-1&&unit.facingDirection<6,"Invalid unit facing direction");
        int dx=unit.x-view.cameraX,dy=unit.y-view.cameraY;
        if(view.wrapX){if(dx>view.gridWidth/2)dx-=view.gridWidth;else if(dx<-view.gridWidth/2)dx+=view.gridWidth;}
        if(view.wrapY){if(dy>view.gridHeight/2)dy-=view.gridHeight;else if(dy<-view.gridHeight/2)dy+=view.gridHeight;}
        if(std::abs(dx)>48||std::abs(dy)>48)continue;
        const float wx=static_cast<float>(dx)+static_cast<float>((unit.y&1)-(view.cameraY&1))*0.5f;
        const float wz=-static_cast<float>(dy)*0.866025404f;
        float ground=GroundHeight(cache,groundData,*plot->second);
        if(!view.waterSurfaceAssetsPath.empty()&&plot->second->water)ground=std::max(ground,OriginalWaterSurfaceBinding::WorldPlaneCandidate);
        const float yaw=static_cast<float>(std::max(0,unit.facingDirection))*XM_PI/3,cs=std::cos(yaw),sn=std::sin(yaw);
        for(const auto& mesh:art->second.meshes){
            Require(result.unitTriangles+mesh.indices.size()/3<=2000000,"Unit frame exceeds its triangle bound");
            auto& vertices=groups[mesh.texture].vertices;
            for(const unsigned index:mesh.indices){const auto& v=mesh.vertices[index];
                const float nx=v[3]*cs-v[5]*sn,nz=v[3]*sn+v[5]*cs;
                const float light=0.55f+0.45f*std::abs(-nx*0.40824829f+v[4]*0.81649658f-nz*0.40824829f);
                vertices.push_back({wx+v[0]*cs-v[2]*sn,ground+v[1],wz+v[0]*sn+v[2]*cs,v[6],v[7],light,1,0,0});
            }
            result.unitTriangles+=mesh.indices.size()/3;
        }
        ++result.modelUnits;
    }
    return groups;
}
void UploadTerrainUnits(Cache& cache,const std::map<unsigned,Group>& groups){
    for(auto it=cache.unitBuffers.begin();it!=cache.unitBuffers.end();){
        if(!groups.count(it->first))it=cache.unitBuffers.erase(it);else ++it;
    }
    for(const auto& entry:groups){const auto& vertices=entry.second.vertices;if(vertices.empty())continue;
        Require(vertices.size()*sizeof(Vertex)<=UINT_MAX,"Unit frame vertex buffer exceeds D3D11 bound");
        const UINT bytes=static_cast<UINT>(vertices.size()*sizeof(Vertex));auto& retained=cache.unitBuffers[entry.first];
        if(!retained.buffer||retained.capacity!=bytes){
            D3D11_BUFFER_DESC bd{};bd.ByteWidth=bytes;bd.Usage=D3D11_USAGE_DYNAMIC;bd.BindFlags=D3D11_BIND_VERTEX_BUFFER;bd.CPUAccessFlags=D3D11_CPU_ACCESS_WRITE;
            ComPtr<ID3D11Buffer> next;Check(cache.device->CreateBuffer(&bd,nullptr,&next),"Original unit mesh buffer");retained.buffer=std::move(next);retained.capacity=bytes;
        }
        D3D11_MAPPED_SUBRESOURCE mapped{};Check(cache.context->Map(retained.buffer.Get(),0,D3D11_MAP_WRITE_DISCARD,0,&mapped),"Original unit mesh update");
        std::memcpy(mapped.pData,vertices.data(),bytes);cache.context->Unmap(retained.buffer.Get(),0);
    }
}
void DrawTerrainUnits(Cache& cache,const std::map<unsigned,Group>& groups){
    for(const auto& entry:groups){if(entry.second.vertices.empty())continue;
        const auto& retained=cache.unitBuffers.at(entry.first);ID3D11Buffer* vb=retained.buffer.Get();const UINT stride=sizeof(Vertex),offset=0;
        cache.context->IASetVertexBuffers(0,1,&vb,&stride,&offset);
        ID3D11ShaderResourceView* texture=cache.units->textures.at(entry.first).Get();cache.context->PSSetShaderResources(0,1,&texture);
        cache.context->Draw(static_cast<UINT>(entry.second.vertices.size()),0);
    }
}
