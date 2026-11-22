#include "OriginalTerrainTessellationShader.h"
#include <d3d11shader.h>
#include <d3dcompiler.h>
#include <wrl/client.h>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <limits>
#include <stdexcept>

#pragma comment(lib,"d3dcompiler.lib")

namespace T = ZeroSisPresentation::OriginalTerrainTessellation;
using Microsoft::WRL::ComPtr;

namespace {
void Require(bool ok,const char* message){
    if(!ok)throw std::runtime_error(message);
}

// Independent piecewise Mitchell-Netravali kernel for B=3/4 and C=0.
double Kernel(double x){
    x=std::abs(x);
    if(x<1.0)return 0.75+x*x*(0.875*x-1.5);
    if(x>=2.0)return 0.0;
    const double edge=2.0-x;
    return edge*edge*edge/8.0;
}

unsigned CheckSurface(const T::DomainConstants& constants){
    unsigned samples=0;
    for(unsigned i=0;i<16;++i){
        T::Heights impulse{};
        impulse[i]=1.0f;
        for(unsigned y=0;y<=16;++y)for(unsigned x=0;x<=16;++x){
            const float u=x/16.0f,v=y/16.0f;
            const double expected=Kernel(u+1.0-i%4)*Kernel(v+1.0-i/4);
            const float actual=T::Evaluate(impulse,constants.cubicBasis,u,v);
            Require(std::abs(actual-expected)<2e-7,"Unexpected bicubic control order or coefficient");
            ++samples;
        }
    }
    const auto& b=constants.cubicBasis;
    for(unsigned i=0;i<4;++i){
        const float end=b[0][i]+b[1][i]+b[2][i]+b[3][i];
        const float slope=3*b[0][i]+2*b[1][i]+b[2][i];
        Require(end==(i?b[3][i-1]:0.0f) && slope==(i?b[2][i-1]:0.0f),"Adjacent patches do not join smoothly");
    }
    Require(b[3][3]==0 && b[2][3]==0,"Unexpected support at the shared edge");

    T::Heights hidden;
    hidden.fill((std::numeric_limits<float>::quiet_NaN)());
    std::array<std::uint8_t,16> known;
    known.fill(1);
    for(unsigned i=0;i<known.size();++i){
        known[i]=0;
        Require(!T::EvaluateKnown(hidden,known,b,0.5f,0.5f).available,"Unknown control heights were consumed");
        known[i]=1;
    }
    return samples;
}

void CheckBuffer(const char* entry,const char* profile){
    ComPtr<ID3DBlob> code,diagnostic;
    const HRESULT result=D3DCompile(T::ShaderSource,sizeof(T::ShaderSource)-1,"terrain",nullptr,nullptr,entry,profile,
        D3DCOMPILE_ENABLE_STRICTNESS|D3DCOMPILE_WARNINGS_ARE_ERRORS,0,&code,&diagnostic);
    if(FAILED(result) && diagnostic)
        std::fwrite(diagnostic->GetBufferPointer(),1,diagnostic->GetBufferSize(),stderr);
    Require(SUCCEEDED(result),"Terrain shader compile failed");

    ComPtr<ID3D11ShaderReflection> shader;
    Require(SUCCEEDED(D3DReflect(code->GetBufferPointer(),code->GetBufferSize(),IID_PPV_ARGS(&shader))),"Shader reflection failed");
    D3D11_SHADER_INPUT_BIND_DESC binding{};
    Require(SUCCEEDED(shader->GetResourceBindingDescByName("DomainPolicy",&binding)) &&
        binding.Type==D3D_SIT_CBUFFER && binding.BindPoint==7 && binding.BindCount==1,"Unexpected domain buffer binding");
    auto* buffer=shader->GetConstantBufferByName("DomainPolicy");
    D3D11_SHADER_BUFFER_DESC desc{};
    Require(buffer && SUCCEEDED(buffer->GetDesc(&desc)) && desc.Size==sizeof(T::DomainConstants),"Domain buffer size differs");
    const auto field=[&](const char* name,std::size_t offset,std::size_t bytes){
        auto* var=buffer->GetVariableByName(name);
        D3D11_SHADER_VARIABLE_DESC info{};
        Require(var && SUCCEEDED(var->GetDesc(&info)) && info.StartOffset==offset && info.Size==bytes,name);
        return var;
    };
    using C=T::DomainConstants;
    field("domainViewProjection",offsetof(C,domainViewProjection),sizeof(C::domainViewProjection));
    auto* basis=field("cubicBasis",offsetof(C,cubicBasis),sizeof(C::cubicBasis));
    field("patchPlacement",offsetof(C,patchPlacement),sizeof(C::patchPlacement));
    field("domainPolicy",offsetof(C,domainPolicy),sizeof(C::domainPolicy));
    field("patchGrid",offsetof(C,patchGrid),sizeof(C::patchGrid));
    D3D11_SHADER_TYPE_DESC type{};
    Require(SUCCEEDED(basis->GetType()->GetDesc(&type)) && type.Type==D3D_SVT_FLOAT &&
        type.Class==D3D_SVC_VECTOR && type.Elements==4 && type.Columns==4,"Expected four float4 basis rows");
    D3D11_SHADER_VARIABLE_DESC basisInfo{};
    const C upload{};
    Require(SUCCEEDED(basis->GetDesc(&basisInfo)) && basisInfo.DefaultValue &&
        std::memcmp(basisInfo.DefaultValue,upload.cubicBasis.data(),sizeof(upload.cubicBasis))==0,
        "Compiled shader defaults differ from the CPU upload");
    if(std::strcmp(profile,"ds_5_0")==0)
        Require((basisInfo.uFlags&D3D_SVF_USED)!=0,"Domain shader does not read the supplied basis");
}
}

int main(){
    try{
        const unsigned samples=CheckSurface(T::DomainConstants{});
        CheckBuffer("hullMain","hs_5_0");
        CheckBuffer("domainMain","ds_5_0");
        CheckBuffer("worldVertexMain","vs_5_0");
        CheckBuffer("worldDomainMain","ds_5_0");
        std::printf("PASS_RETAIL_TERRAIN_BASIS control_samples=%u reflected_entries=4\n",samples);
        return 0;
    }catch(const std::exception& e){
        std::fprintf(stderr,"FAIL: %s\n",e.what());
        return 1;
    }
}
