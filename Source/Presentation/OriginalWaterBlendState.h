#pragma once
#include "OriginalWaterBlendModel.h"
#include <d3d11.h>

namespace ZeroSisPresentation { namespace OriginalWaterBlend {
inline D3D11_BLEND_DESC MakeMrtDescription(bool writePick=true){
    D3D11_BLEND_DESC result{};
    // The retail target0 operation is exact. Independent MRT handling protects
    // this renderer's integer pick and fragment-class outputs, absent in retail.
    result.AlphaToCoverageEnable=FALSE;result.IndependentBlendEnable=TRUE;
    for(auto& target:result.RenderTarget){
        target.BlendEnable=FALSE;target.SrcBlend=D3D11_BLEND_ONE;target.DestBlend=D3D11_BLEND_ZERO;
        target.BlendOp=D3D11_BLEND_OP_ADD;target.SrcBlendAlpha=D3D11_BLEND_ONE;
        target.DestBlendAlpha=D3D11_BLEND_ZERO;target.BlendOpAlpha=D3D11_BLEND_OP_ADD;
        target.RenderTargetWriteMask=D3D11_COLOR_WRITE_ENABLE_ALL;
    }
    auto& colour=result.RenderTarget[0];colour.BlendEnable=TRUE;
    colour.SrcBlend=static_cast<D3D11_BLEND>(RetailState.sourceRgb);
    colour.DestBlend=static_cast<D3D11_BLEND>(RetailState.destinationRgb);
    colour.BlendOp=static_cast<D3D11_BLEND_OP>(RetailState.rgbOperation);
    colour.SrcBlendAlpha=static_cast<D3D11_BLEND>(RetailState.sourceAlpha);
    colour.DestBlendAlpha=static_cast<D3D11_BLEND>(RetailState.destinationAlpha);
    colour.BlendOpAlpha=static_cast<D3D11_BLEND_OP>(RetailState.alphaOperation);
    colour.RenderTargetWriteMask=static_cast<UINT8>(RetailState.writeMask);
    if(!writePick)result.RenderTarget[1].RenderTargetWriteMask=0;
    return result;
}
}}
