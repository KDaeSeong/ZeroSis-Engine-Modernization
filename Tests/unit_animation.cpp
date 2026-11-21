#include "../Source/Presentation/WorldUnitAssets.h"
#include <Windows.h>
#include <d3d11.h>
#include <cmath>
#include <atomic>
#include <iostream>
#include <stdexcept>
#include <thread>

using namespace ZeroSisPresentation;
static void Require(bool ok,const char* why){if(!ok)throw std::runtime_error(why);}
static float Difference(const UnitAssetCatalog& a,const UnitAssetCatalog& b){float d=0;Require(a.artOrder==b.artOrder,"Art ordering differs");for(const auto& name:a.artOrder){const auto& x=a.arts.at(name);const auto& y=b.arts.at(name);Require(x.meshes.size()==y.meshes.size(),"Mesh counts differ");for(std::size_t m=0;m<x.meshes.size();++m){Require(x.meshes[m].vertices.size()==y.meshes[m].vertices.size(),"Vertex counts differ");for(std::size_t v=0;v<x.meshes[m].vertices.size();++v)for(unsigned k=0;k<8;++k)d=std::max(d,std::abs(x.meshes[m].vertices[v][k]-y.meshes[m].vertices[v][k]));}}return d;}
int wmain(int argc,wchar_t** argv){
    try{
        Require(argc==3,"Usage: unit_animation.exe <v1-package> <v2-package>");
        D3D_FEATURE_LEVEL level{};Microsoft::WRL::ComPtr<ID3D11Device> device;
        const HRESULT hr=D3D11CreateDevice(nullptr,D3D_DRIVER_TYPE_WARP,nullptr,0,nullptr,0,D3D11_SDK_VERSION,&device,&level,nullptr);
        Require(SUCCEEDED(hr),"Could not create WARP D3D11 device");
        auto v1=UnitAssetCatalog::Load(device.Get(),argv[1]);auto v2=UnitAssetCatalog::Load(device.Get(),argv[2]);
        Require(!v1.HasAnimation(),"v1 unexpectedly has animation");v1.Animate(0.25);Require(v2.HasAnimation(),"v2 did not initialize the Granny bridge");
        Require(!v2.animatedMeshes.empty(),"v2 has no animated geometry");
        v2.Animate(0);const float t0=Difference(v1,v2);Require(t0<=1e-5f,"Animated t0 differs from v1 static geometry");
        std::vector<std::vector<std::array<float,8>>> before;for(const auto& mesh:v2.animatedMeshes){auto it=v2.arts.find(v2.artOrder.at(mesh.art));before.push_back(it->second.meshes.at(mesh.mesh).vertices);}
        v2.Animate(0.25);bool changed=false;std::size_t index=0;for(const auto& mesh:v2.animatedMeshes){const auto& now=v2.arts.at(v2.artOrder.at(mesh.art)).meshes.at(mesh.mesh).vertices;for(std::size_t i=0;i<now.size();++i)for(unsigned k=0;k<6;++k)if(std::abs(now[i][k]-before[index][i][k])>1e-5f)changed=true;++index;}Require(changed,"Intermediate time did not change any animated position or normal");
        const double duration=v2.AnimationDuration();v2.Animate(duration);Require(Difference(v1,v2)<=1e-5f,"Duration wrap does not reproduce t0");
        const auto snapshot=Difference(v1,v2);bool badTime=false;try{v2.Animate(-1);}catch(const std::exception&){badTime=true;}Require(badTime&&Difference(v1,v2)==snapshot,"Invalid time did not preserve the existing pose");
        std::atomic<bool> workerFailed{false};std::thread worker([&](){try{v2.Animate(0.1);}catch(const std::exception&){workerFailed.store(true);}});worker.join();Require(workerFailed.load(),"Foreign-thread Animate was accepted");
        std::vector<UnitAnimationBone> cycle(2);cycle[0].parent=1;cycle[1].parent=0;bool cycleRejected=false;try{std::vector<UnitAnimationDetail::M4> local={UnitAnimationDetail::Identity(),UnitAnimationDetail::Identity()};(void)UnitAnimationDetail::World(local,cycle);}catch(const std::exception&){cycleRejected=true;}Require(cycleRejected,"Skeleton parent cycle was accepted");
        std::vector<UnitAnimationBone> badParent(1);badParent[0].parent=1;bool parentBoundsRejected=false;try{UnitAnimationDetail::ValidateHierarchy(badParent);}catch(const std::exception&){parentBoundsRejected=true;}Require(parentBoundsRejected,"Out-of-range skeleton parent was accepted");
        std::cout<<"PASS_UNIT_ANIMATION_V2_T0_INTERMEDIATE_WRAP_INVALID_TIME_THREAD_CYCLE\n";return 0;
    }catch(const std::exception& e){std::cerr<<"FAIL_UNIT_ANIMATION: "<<e.what()<<"\n";return 1;}
}
