#pragma once
// Prepared original model geometry only. The game does not load the x86 SDK
// extraction helper. Pose, formation and world scale remain candidate policies.
#include <d3d11.h>
#include <wrl/client.h>
#include <algorithm>
#include <array>
#include <cmath>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>
#include "../Animation/UnitAnimation.h"

namespace ZeroSisPresentation {
struct UnitMeshGeometry {
    unsigned texture=0;
    // position XYZ, normal XYZ, UV. Positions are in candidate tile units.
    std::vector<std::array<float,8>> vertices;
    std::vector<unsigned> indices;
};
struct UnitArtGeometry {std::vector<UnitMeshGeometry> meshes;};
struct UnitAssetCatalog {
    std::map<std::string,UnitArtGeometry> arts;
    std::vector<std::string> artOrder;
    std::vector<Microsoft::WRL::ComPtr<ID3D11ShaderResourceView>> textures;
    std::wstring path;
    std::vector<UnitAnimationFile> animationFiles;
    std::vector<UnitAnimatedMesh> animatedMeshes;
    std::unique_ptr<UnitAnimationRuntime> animationRuntime;

    static UnitAssetCatalog Load(ID3D11Device* device,const std::wstring& source) {
        const auto require=[](bool ok,const char* why){if(!ok)throw std::runtime_error(why);};
        std::ifstream file(std::filesystem::path(source),std::ios::binary|std::ios::ate);
        require(file.good(),"Cannot open unit model package");
        const auto length=file.tellg();
        require(length>=20&&length<=64*1024*1024,"Unit package exceeds its size bound");
        std::vector<unsigned char> data(static_cast<std::size_t>(length));file.seekg(0);
        file.read(reinterpret_cast<char*>(data.data()),length);require(file.good(),"Truncated unit package read");
        std::size_t cursor=0;
        const auto take=[&](std::size_t count){require(count<=data.size()-cursor,"Truncated unit package record");
            const auto* bytes=data.data()+cursor;cursor+=count;return bytes;};
        const auto word=[](const unsigned char* p){return unsigned(p[0])|(unsigned(p[1])<<8)|(unsigned(p[2])<<16)|(unsigned(p[3])<<24);};
        const auto u32=[&](){return word(take(4));};
        const auto f32=[&](){float v;std::memcpy(&v,take(4),4);require(std::isfinite(v),"Nonfinite unit package float");return v;};
        const auto ascii=[&](unsigned maximum){const unsigned n=u32();require(n>0&&n<=maximum,"Invalid unit package string length");const auto* p=take(n);std::string s(reinterpret_cast<const char*>(p),n);for(unsigned char c:s)require(c>=0x20&&c<=0x7e,"Invalid unit package ASCII string");return s;};
        const auto* magic=take(8);const unsigned version=u32();const bool v1=std::memcmp(magic,"ZSUNIT01",8)==0&&version==1;
        const bool v2=std::memcmp(magic,"ZSUNIT02",8)==0&&version==2;
        require(v1||v2,"Unsupported unit package version");
        UnitAssetCatalog result;const unsigned textureCount=u32();
        require(textureCount>0&&textureCount<=64,"Invalid unit texture count");
        for(unsigned i=0;i<textureCount;++i){
            const unsigned count=u32();require(count>=128&&count<=16*1024*1024,"Invalid unit DDS length");
            const auto* dds=take(count);const unsigned w=word(dds+16),h=word(dds+12),mips=word(dds+28),fourcc=word(dds+84);
            require(std::memcmp(dds,"DDS ",4)==0&&word(dds+4)==124&&word(dds+76)==32&&word(dds+80)==4&&word(dds+112)==0&&
                    word(dds+24)==0&&w>0&&h>0&&w<=4096&&h<=4096&&mips>0&&mips<=13,"Invalid unit DDS header");
            unsigned allowedMips=0;for(unsigned size=std::max(w,h);size;size>>=1)++allowedMips;
            require(mips<=allowedMips,"Unit DDS has more mip levels than its dimensions permit");
            const unsigned block=fourcc==0x31545844?8u:16u;
            const DXGI_FORMAT format=fourcc==0x31545844?DXGI_FORMAT_BC1_UNORM_SRGB:
                fourcc==0x33545844?DXGI_FORMAT_BC2_UNORM_SRGB:fourcc==0x35545844?DXGI_FORMAT_BC3_UNORM_SRGB:DXGI_FORMAT_UNKNOWN;
            require(format!=DXGI_FORMAT_UNKNOWN,"Unsupported original unit texture encoding");
            std::vector<D3D11_SUBRESOURCE_DATA> levels;std::size_t offset=128;
            for(unsigned m=0;m<mips;++m){
                const unsigned mw=std::max(1u,w>>m),mh=std::max(1u,h>>m),pitch=((mw+3)/4)*block;
                const unsigned size=pitch*((mh+3)/4);require(size<=count-offset,"Truncated unit DDS mip chain");
                levels.push_back({dds+offset,pitch,size});offset+=size;
            }
            require(offset==count,"Unexpected unit DDS trailing payload");
            D3D11_TEXTURE2D_DESC td{};td.Width=w;td.Height=h;td.MipLevels=mips;td.ArraySize=1;td.Format=format;
            td.SampleDesc.Count=1;td.Usage=D3D11_USAGE_IMMUTABLE;td.BindFlags=D3D11_BIND_SHADER_RESOURCE;
            Microsoft::WRL::ComPtr<ID3D11Texture2D> texture;
            require(SUCCEEDED(device->CreateTexture2D(&td,levels.data(),&texture)),"Unit texture upload failed");
            Microsoft::WRL::ComPtr<ID3D11ShaderResourceView> view;
            require(SUCCEEDED(device->CreateShaderResourceView(texture.Get(),nullptr,&view)),"Unit texture view failed");
            result.textures.push_back(std::move(view));
        }
        const unsigned artCount=u32();require(artCount>0&&artCount<=64,"Invalid unit art count");
        std::size_t totalVertices=0,totalIndices=0;
        for(unsigned a=0;a<artCount;++a){
            const unsigned nameLength=u32();require(nameLength>0&&nameLength<=256,"Invalid unit art name length");
            const auto* bytes=take(nameLength);std::string name(reinterpret_cast<const char*>(bytes),nameLength);
            for(const char c:name)require((c>='A'&&c<='Z')||(c>='0'&&c<='9')||c=='_',"Invalid unit art identity");
            const unsigned meshCount=u32();require(meshCount>0&&meshCount<=128,"Invalid unit mesh count");
            UnitArtGeometry art;
            for(unsigned m=0;m<meshCount;++m){
                UnitMeshGeometry mesh;mesh.texture=u32();const unsigned vc=u32(),ic=u32();
                require(mesh.texture<textureCount&&vc>0&&vc<=200000&&ic>0&&ic<=600000&&ic%3==0,"Invalid unit mesh dimensions");
                totalVertices+=vc;totalIndices+=ic;
                require(totalVertices<=1000000&&totalIndices<=3000000,"Unit geometry exceeds catalog bound");
                mesh.vertices.resize(vc);std::memcpy(mesh.vertices.data(),take(static_cast<std::size_t>(vc)*32),static_cast<std::size_t>(vc)*32);
                for(const auto& v:mesh.vertices){
                    for(float value:v)require(std::isfinite(value)&&std::abs(value)<=10000,"Nonfinite or unbounded unit vertex");
                    require(std::abs(v[0])<=2&&std::abs(v[1])<=2&&std::abs(v[2])<=2,"Unit vertex exceeds tile-space bounds");
                    const float n=v[3]*v[3]+v[4]*v[4]+v[5]*v[5];require(n>=0.5f&&n<=1.5f,"Invalid unit normal");
                }
                mesh.indices.resize(ic);for(auto& index:mesh.indices){index=u32();require(index<vc,"Unit index exceeds vertex bounds");}
                art.meshes.push_back(std::move(mesh));
            }
            require(result.arts.emplace(name,std::move(art)).second,"Duplicate unit art identity");result.artOrder.push_back(name);
        }
        if(v2){
            const unsigned fileCount=u32();require(fileCount>0&&fileCount<=16,"Invalid animation embedded-file count");
            std::map<std::string,unsigned> fileNames;
            for(unsigned i=0;i<fileCount;++i){UnitAnimationFile f;f.name=ascii(128);require(f.name.find_first_of("/\\:")==std::string::npos&&f.name!="."&&f.name!=".."&&f.name.find('.')!=std::string::npos,"Animation filename must be a safe basename");
                require(fileNames.emplace(f.name,i).second,"Duplicate animation filename");const unsigned n=u32();require(n>0&&n<=32*1024*1024,"Invalid embedded animation file size");const auto* b=take(n);f.bytes.assign(b,b+n);result.animationFiles.push_back(std::move(f));}
            const unsigned rigCount=u32();require(rigCount>0&&rigCount<=16,"Invalid animation rig count");
            for(unsigned ri=0;ri<rigCount;++ri){UnitAnimationRig rig;rig.gsdFile=u32();rig.modelFile=u32();rig.animationFile=u32();const unsigned transpose=u32();require(rig.gsdFile<fileCount&&rig.modelFile<fileCount&&rig.animationFile<fileCount&&transpose<=1,"Invalid animation rig file reference");rig.transposeScale=transpose!=0;rig.duration=f32();require(rig.duration>0&&rig.duration<=3600,"Invalid animation duration");const unsigned bones=u32();require(bones>0&&bones<=512,"Invalid animation bone count");std::map<std::string,bool> names;
                for(unsigned bi=0;bi<bones;++bi){UnitAnimationBone bone;bone.name=ascii(128);require(names.emplace(bone.name,true).second,"Duplicate skeleton bone name");bone.parent=static_cast<int32_t>(u32());require(bone.parent>=-1&&bone.parent<static_cast<int>(bones)&&bone.parent!=static_cast<int>(bi),"Invalid skeleton parent");for(float& x:bone.inverse)x=f32();for(float& x:bone.position)x=f32();for(float& x:bone.orientation)x=f32();for(float& x:bone.scaleShear)x=f32();const float q=bone.orientation[0]*bone.orientation[0]+bone.orientation[1]*bone.orientation[1]+bone.orientation[2]*bone.orientation[2]+bone.orientation[3]*bone.orientation[3];require(q>=0.9801f&&q<=1.0201f,"Unnormalized bind orientation");rig.bones.push_back(std::move(bone));}
                UnitAnimationDetail::ValidateHierarchy(rig.bones);std::vector<UnitAnimationDetail::M4> bind;for(const auto& b:rig.bones)bind.push_back(UnitAnimationDetail::Local(b.position.data(),b.orientation.data(),b.scaleShear.data(),rig.transposeScale));(void)UnitAnimationDetail::World(bind,rig.bones);
                result.rigs.push_back(std::move(rig));}
            const unsigned animatedCount=u32();require(animatedCount>0&&animatedCount<=4096,"Invalid animated mesh count");std::map<std::pair<unsigned,unsigned>,bool> mapped;
            for(unsigned mi=0;mi<animatedCount;++mi){UnitAnimatedMesh mesh;mesh.art=u32();mesh.mesh=u32();mesh.rig=u32();mesh.slot=u32();const unsigned vc=u32();require(mesh.art<artCount&&mesh.rig<rigCount&&mesh.slot<12&&vc>0&&vc<=200000,"Invalid animated mesh reference");auto artIt=result.arts.find(result.artOrder[mesh.art]);require(mesh.mesh<artIt->second.meshes.size()&&artIt->second.meshes[mesh.mesh].vertices.size()==vc,"Animated mesh vertex count mismatch");require(mapped.emplace(std::make_pair(mesh.art,mesh.mesh),true).second,"Duplicate animated mesh mapping");const std::size_t byteCount=static_cast<std::size_t>(vc)*52;require(byteCount<=data.size()-cursor,"Truncated animated vertex data");mesh.vertices.resize(vc);
                for(auto& v:mesh.vertices){for(float& x:v.values)x=f32();for(uint32_t& b:v.bones){b=u32();require(b<result.rigs[mesh.rig].bones.size(),"Animated vertex bone index out of range");}unsigned sum=0;for(uint8_t& w:v.weights){w=*take(1);sum+=w;}require(sum==255,"Animated vertex weights must sum to 255");}
                result.animatedMeshes.push_back(std::move(mesh));}
            require(cursor==data.size(),"Trailing animation package records");result.path=source;result.animationRuntime=std::make_unique<UnitAnimationRuntime>(std::filesystem::path(source).parent_path(),result.animationFiles,result.rigs);return result;
        }
        require(cursor==data.size(),"Trailing unit package records");result.path=source;return result;
    }
    bool HasAnimation()const{return static_cast<bool>(animationRuntime);}
    double AnimationDuration(std::size_t rigIndex=0)const{if(rigIndex>=rigs.size())throw std::out_of_range("Animation rig index");return rigs[rigIndex].duration;}
    void Animate(double elapsedSeconds){if(!animationRuntime)return;auto candidates=animationRuntime->Animate(elapsedSeconds,animatedMeshes);if(candidates.size()!=animatedMeshes.size())throw std::runtime_error("Animation candidate count mismatch");
        for(std::size_t i=0;i<candidates.size();++i){const auto& m=animatedMeshes[i];auto it=arts.find(artOrder[m.art]);if(m.mesh>=it->second.meshes.size()||candidates[i].size()!=it->second.meshes[m.mesh].vertices.size())throw std::runtime_error("Animation candidate geometry mismatch");}
        for(std::size_t i=0;i<candidates.size();++i){const auto& m=animatedMeshes[i];auto it=arts.find(artOrder[m.art]);it->second.meshes[m.mesh].vertices.swap(candidates[i]);}}
private:
    std::vector<UnitAnimationRig> rigs;
};
}
