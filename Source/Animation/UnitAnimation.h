#pragma once
// Native-only animation data and skinning. Granny access crosses the stable C ABI.
#include "GrannyAnimationBridge.h"
#include <Windows.h>
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <limits>
#include <map>
#include <memory>
#include <stdexcept>
#include <string>
#include <thread>
#include <unordered_map>
#include <utility>
#include <vector>

namespace ZeroSisPresentation {
struct UnitAnimationFile {std::string name;std::vector<unsigned char> bytes;};
struct UnitAnimationBone {
    std::string name;int parent=-1;std::array<float,16> inverse{};std::array<float,3> position{};
    std::array<float,4> orientation{};std::array<float,9> scaleShear{};
};
struct UnitAnimationRig {
    unsigned gsdFile=0,modelFile=0,animationFile=0;bool transposeScale=false;float duration=0;
    std::vector<UnitAnimationBone> bones;
};
struct UnitAnimationVertex {
    std::array<float,8> values{};std::array<uint32_t,4> bones{};std::array<uint8_t,4> weights{};
};
struct UnitAnimatedMesh {
    unsigned art=0,mesh=0,rig=0,slot=0;std::vector<UnitAnimationVertex> vertices;
};

namespace UnitAnimationDetail {
using M4=std::array<float,16>;
inline M4 Identity(){return M4{1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1};}
inline M4 Multiply(const M4& a,const M4& b){M4 c{};for(int col=0;col<4;++col)for(int row=0;row<4;++row)for(int k=0;k<4;++k)c[row+4*col]+=a[row+4*k]*b[k+4*col];return c;}
inline M4 Local(const float* p,const float* q,const float* s,bool transpose){
    const float n=std::sqrt(q[0]*q[0]+q[1]*q[1]+q[2]*q[2]+q[3]*q[3]);
    if(!std::isfinite(n)||n<0.99f||n>1.01f)throw std::runtime_error("Animation quaternion is not normalized");
    const float x=q[0]/n,y=q[1]/n,z=q[2]/n,w=q[3]/n;
    M4 r={1-2*y*y-2*z*z,2*x*y+2*w*z,2*x*z-2*w*y,0,
          2*x*y-2*w*z,1-2*x*x-2*z*z,2*y*z+2*w*x,0,
          2*x*z+2*w*y,2*y*z-2*w*x,1-2*x*x-2*y*y,0,0,0,0,1};
    M4 h=Identity();for(int row=0;row<3;++row)for(int col=0;col<3;++col)h[row+4*col]=s[transpose?col+3*row:row+3*col];
    M4 out=Multiply(r,h);out[12]=p[0];out[13]=p[1];out[14]=p[2];return out;
}
inline std::vector<M4> World(const std::vector<M4>& local,const std::vector<UnitAnimationBone>& bones){
    std::vector<M4> result(local.size());std::vector<uint8_t> state(local.size());
    auto visit=[&](auto&& self,std::size_t i)->void{if(state[i]==1)throw std::runtime_error("Animation skeleton cycle");if(state[i]==2)return;
        state[i]=1;int p=bones[i].parent;if(p<0)result[i]=local[i];else{self(self,static_cast<std::size_t>(p));result[i]=Multiply(result[static_cast<std::size_t>(p)],local[i]);}state[i]=2;};
    for(std::size_t i=0;i<local.size();++i)visit(visit,i);return result;
}
inline void ValidateHierarchy(const std::vector<UnitAnimationBone>& bones){
    for(std::size_t i=0;i<bones.size();++i){const int parent=bones[i].parent;if(parent< -1||parent>=static_cast<int>(bones.size())||parent==static_cast<int>(i))throw std::runtime_error("Animation skeleton parent is out of range");}
    std::vector<M4> identity(bones.size(),Identity());(void)World(identity,bones);
}
inline bool Finite(const float* p,std::size_t n){for(std::size_t i=0;i<n;++i)if(!std::isfinite(p[i]))return false;return true;}
}

class UnitAnimationRuntime {
    struct Api {
        HMODULE module=nullptr;decltype(&ZSGrannyBridge_GetAbiVersion) version=nullptr;
        decltype(&ZSGrannyBridge_Open) open=nullptr;decltype(&ZSGrannyBridge_GetInfo) info=nullptr;
        decltype(&ZSGrannyBridge_GetTrackName) name=nullptr;decltype(&ZSGrannyBridge_Sample) sample=nullptr;
        decltype(&ZSGrannyBridge_Close) close=nullptr;std::size_t live=0;
        explicit Api(const std::filesystem::path& directory){
            std::vector<wchar_t> path(32768);DWORD n=GetModuleFileNameW(nullptr,path.data(),static_cast<DWORD>(path.size()));
            if(!n||n>=path.size())throw std::runtime_error("Cannot locate Host directory for Granny bridge");
            std::filesystem::path dll=std::filesystem::path(std::wstring(path.data(),n)).parent_path()/L"ZeroSisGrannyAnimationBridge.dll";
            module=LoadLibraryExW(dll.c_str(),nullptr,LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR|LOAD_LIBRARY_SEARCH_DEFAULT_DIRS);
            if(!module)throw std::runtime_error("Cannot securely load sibling Granny animation bridge");
            version=reinterpret_cast<decltype(version)>(GetProcAddress(module,"ZSGrannyBridge_GetAbiVersion"));
            open=reinterpret_cast<decltype(open)>(GetProcAddress(module,"ZSGrannyBridge_Open"));
            info=reinterpret_cast<decltype(info)>(GetProcAddress(module,"ZSGrannyBridge_GetInfo"));
            name=reinterpret_cast<decltype(name)>(GetProcAddress(module,"ZSGrannyBridge_GetTrackName"));
            sample=reinterpret_cast<decltype(sample)>(GetProcAddress(module,"ZSGrannyBridge_Sample"));
            close=reinterpret_cast<decltype(close)>(GetProcAddress(module,"ZSGrannyBridge_Close"));
            if(!version||!open||!info||!name||!sample||!close||version()!=ZS_GRANNY_BRIDGE_ABI_VERSION){FreeLibrary(module);module=nullptr;throw std::runtime_error("Granny bridge ABI mismatch");}
            (void)directory;
        }
        ~Api(){if(module){if(live==0)FreeLibrary(module);module=nullptr;}}
    };
    struct Clip {
        std::shared_ptr<Api> api;ZSGrannyBridge* handle=nullptr;float duration=0;std::vector<int> boneTrack;std::thread::id owner;
        Clip()=default;Clip(const Clip&)=delete;Clip& operator=(const Clip&)=delete;
        Clip(Clip&& x)noexcept:api(std::move(x.api)),handle(x.handle),duration(x.duration),boneTrack(std::move(x.boneTrack)),owner(x.owner){x.handle=nullptr;}
        Clip& operator=(Clip&& x)noexcept{if(this!=&x){Reset();api=std::move(x.api);handle=x.handle;duration=x.duration;boneTrack=std::move(x.boneTrack);owner=x.owner;x.handle=nullptr;}return *this;}
        ~Clip(){Reset();}
        void Reset()noexcept{if(!handle||!api)return;if(owner==std::this_thread::get_id()&&api->close(&handle)==ZS_GRANNY_OK){if(api->live)--api->live;}else{ // Keep the bridge mapped if its owner-thread contract was violated.
                api->live=std::max<std::size_t>(api->live,1);handle=nullptr;
            }}
    };
    std::shared_ptr<Api> api_;std::vector<Clip> clips_;std::vector<UnitAnimationRig> rigs_;
    std::filesystem::path packageDirectory_;std::thread::id owner_;

    static std::wstring WideAscii(const std::string& value){std::wstring out;out.reserve(value.size());for(unsigned char c:value){if(c>0x7f)throw std::runtime_error("Non-ASCII embedded unit filename");out.push_back(static_cast<wchar_t>(c));}return out;}
    static void VerifySibling(const std::filesystem::path& directory,const UnitAnimationFile& file){
        const auto path=directory/WideAscii(file.name);std::ifstream stream(path,std::ios::binary|std::ios::ate);
        if(!stream||stream.tellg()<0||static_cast<std::size_t>(stream.tellg())!=file.bytes.size())throw std::runtime_error("Animation sibling file length differs from package");
        std::vector<unsigned char> bytes(file.bytes.size());stream.seekg(0);if(!bytes.empty())stream.read(reinterpret_cast<char*>(bytes.data()),static_cast<std::streamsize>(bytes.size()));
        if(!stream.good()||bytes!=file.bytes)throw std::runtime_error("Animation sibling bytes differ from package");
    }
    static void Check(int32_t status,const char* action){if(status!=ZS_GRANNY_OK)throw std::runtime_error(std::string("Granny bridge ")+action+" failed, status="+std::to_string(status));}
public:
    UnitAnimationRuntime(std::filesystem::path packageDirectory,const std::vector<UnitAnimationFile>& files,
                         const std::vector<UnitAnimationRig>& rigs):rigs_(rigs),packageDirectory_(std::move(packageDirectory)),owner_(std::this_thread::get_id()){
        for(const auto& f:files)VerifySibling(packageDirectory_,f);
        api_=std::make_shared<Api>(packageDirectory_);clips_.reserve(rigs_.size());
        for(const auto& rig:rigs_){
            if(rig.gsdFile>=files.size()||rig.modelFile>=files.size()||rig.animationFile>=files.size())throw std::runtime_error("Animation rig file reference is out of range");
            Clip clip;clip.api=api_;clip.owner=owner_;
            auto g=WideAscii(files[rig.gsdFile].name),m=WideAscii(files[rig.modelFile].name),a=WideAscii(files[rig.animationFile].name);
            Check(api_->open((packageDirectory_/g).c_str(),(packageDirectory_/m).c_str(),(packageDirectory_/a).c_str(),&clip.handle),"Open");++api_->live;
            uint32_t trackCount=0;float duration=0;Check(api_->info(clip.handle,&trackCount,&duration),"GetInfo");
            if(trackCount>512||!std::isfinite(duration)||duration<=0||std::abs(duration-rig.duration)>std::max(1e-4f,rig.duration*1e-5f))throw std::runtime_error("Serialized and bridge animation duration differ");
            clip.duration=duration;std::unordered_map<std::wstring,int> tracks;
            for(uint32_t i=0;i<trackCount;++i){uint32_t required=0;int32_t status=api_->name(clip.handle,i,nullptr,0,&required);if(status!=ZS_GRANNY_BAD_VERSION_OR_SIZE||required<2||required>512)throw std::runtime_error("Invalid Granny track name length");
                std::vector<wchar_t> name(required);Check(api_->name(clip.handle,i,name.data(),required,&required),"GetTrackName");if(!tracks.emplace(std::wstring(name.data()),static_cast<int>(i)).second)throw std::runtime_error("Duplicate Granny track name");}
            clip.boneTrack.assign(rig.bones.size(),-1);
            for(std::size_t i=0;i<rig.bones.size();++i){auto it=tracks.find(WideAscii(rig.bones[i].name));if(it!=tracks.end())clip.boneTrack[i]=it->second;}
            clips_.push_back(std::move(clip));
        }
    }
    UnitAnimationRuntime(const UnitAnimationRuntime&)=delete;UnitAnimationRuntime& operator=(const UnitAnimationRuntime&)=delete;
    bool IsOwnerThread()const{return owner_==std::this_thread::get_id();}
    std::vector<std::vector<std::array<float,8>>> Animate(double elapsed,const std::vector<UnitAnimatedMesh>& meshes)const{
        if(!IsOwnerThread())throw std::runtime_error("Unit animation called from a non-owner thread");
        if(!std::isfinite(elapsed)||elapsed<0)throw std::runtime_error("Unit animation time must be finite and nonnegative");
        std::vector<std::vector<UnitAnimationDetail::M4>> worlds(rigs_.size());
        for(std::size_t r=0;r<rigs_.size();++r){const auto& rig=rigs_[r];const auto& clip=clips_[r];double wrapped=std::fmod(elapsed,static_cast<double>(clip.duration));if(wrapped<0)wrapped+=clip.duration;float time=static_cast<float>(wrapped);
            std::vector<UnitAnimationDetail::M4> local;local.reserve(rig.bones.size());
            for(std::size_t b=0;b<rig.bones.size();++b){const auto& bone=rig.bones[b];float p[3],q[4],s[9];std::copy(bone.position.begin(),bone.position.end(),p);std::copy(bone.orientation.begin(),bone.orientation.end(),q);std::copy(bone.scaleShear.begin(),bone.scaleShear.end(),s);
                if(clip.boneTrack[b]>=0){ZSGrannySample sample{};Check(api_->sample(clip.handle,static_cast<uint32_t>(clip.boneTrack[b]),time,clip.duration,ZS_GRANNY_SAMPLE_VERSION,sizeof(sample),&sample),"Sample");
                    std::copy(sample.position,sample.position+3,p);std::copy(sample.orientation,sample.orientation+4,q);std::copy(sample.scale_shear,sample.scale_shear+9,s);}
                if(!UnitAnimationDetail::Finite(p,3)||!UnitAnimationDetail::Finite(q,4)||!UnitAnimationDetail::Finite(s,9))throw std::runtime_error("Nonfinite animated local transform");
                local.push_back(UnitAnimationDetail::Local(p,q,s,rig.transposeScale));}
            worlds[r]=UnitAnimationDetail::World(local,rig.bones);
        }
        std::vector<std::vector<UnitAnimationDetail::M4>> skinPalette(rigs_.size());
        for(std::size_t r=0;r<rigs_.size();++r){skinPalette[r].reserve(rigs_[r].bones.size());for(std::size_t b=0;b<rigs_[r].bones.size();++b)skinPalette[r].push_back(UnitAnimationDetail::Multiply(worlds[r][b],rigs_[r].bones[b].inverse));}
        std::vector<std::vector<std::array<float,8>>> result;result.reserve(meshes.size());constexpr float scale=0.14f/80.0f;
        for(const auto& mesh:meshes){if(mesh.rig>=rigs_.size()||mesh.slot>=12)throw std::runtime_error("Animated mesh rig or formation slot is invalid");const auto& rig=rigs_[mesh.rig];std::vector<std::array<float,8>> vertices;vertices.reserve(mesh.vertices.size());
            for(const auto& vertex:mesh.vertices){float pos[4]{},normal[3]{};unsigned sum=0;
                for(unsigned lane=0;lane<4;++lane){const unsigned w=vertex.weights[lane];sum+=w;if(!w)continue;const unsigned bi=vertex.bones[lane];if(bi>=rig.bones.size())throw std::runtime_error("Animated vertex bone index is invalid");
                    const auto& skin=skinPalette[mesh.rig][bi];const float v[4]={vertex.values[0],vertex.values[1],vertex.values[2],1};float p[4]{};
                    for(int row=0;row<4;++row)for(int col=0;col<4;++col)p[row]+=skin[row+4*col]*v[col];const float f=static_cast<float>(w)/255.0f;for(int a=0;a<4;++a)pos[a]+=p[a]*f;
                    for(int row=0;row<3;++row)for(int col=0;col<3;++col)normal[row]+=skin[row+4*col]*vertex.values[3+col]*f;
                }
                if(sum!=255||!std::isfinite(pos[3])||std::abs(pos[3])<1e-8f)throw std::runtime_error("Animated vertex weights or homogeneous position invalid");
                const float nn=std::sqrt(normal[0]*normal[0]+normal[1]*normal[1]+normal[2]*normal[2]);if(!std::isfinite(nn)||nn<1e-8f)throw std::runtime_error("Animated normal is invalid");
                const float x=pos[0]/pos[3],y=pos[1]/pos[3],z=pos[2]/pos[3];const unsigned col=mesh.slot%4,row=mesh.slot/4;
                const float offsetX=(static_cast<float>(col)-1.5f)*13.0f/80.0f,offsetZ=(static_cast<float>(row)-1.0f)*13.0f/80.0f;
                std::array<float,8> out={(x*scale)+offsetX,z*scale,(-y*scale)+offsetZ,normal[0]/nn,normal[2]/nn,-normal[1]/nn,vertex.values[6],vertex.values[7]};
                for(float n:out)if(!std::isfinite(n))throw std::runtime_error("Animated vertex output is nonfinite");
                if(std::abs(out[0])>2||std::abs(out[1])>2||std::abs(out[2])>2)throw std::runtime_error("Animated vertex exceeds tile-space bounds");vertices.push_back(out);
            }result.push_back(std::move(vertices));
        }return result;
    }
};
}
