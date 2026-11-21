#pragma once
#include <array>
#include <cmath>
#include <cstdint>
#include <stdexcept>

namespace ZeroSisHost {
struct MenuReplayPointerGuideLine final {
    double startX=0,startY=0,endX=0,endY=0,width=1;
    std::array<std::uint8_t,4> rgba{{0,0,0,0}};
};
struct MenuReplayPointerGuides final {
    bool visible=false;
    // Original XML order: vertical crosshair, horizontal crosshair, vertical
    // axis guide, horizontal axis guide. Coordinates are GraphDisplay-local.
    std::array<MenuReplayPointerGuideLine,4> lines{};
};
namespace MenuReplayPointerGuideDetail {
inline void ValidateAxis(double origin,double length){
    constexpr double limit=10000000,extension=8;
    const double end=origin+length,guideEnd=end+extension;
    if(!std::isfinite(origin) || !std::isfinite(length) || std::abs(origin)>limit ||
       length<=0 || length+extension>limit || !std::isfinite(end) || end<=origin ||
       !std::isfinite(guideEnd) || guideEnd<=end || std::abs(guideEnd)>limit)
        throw std::invalid_argument("Replay pointer guide geometry is outside its finite representable bounds");
}
}

// Exact CreateUpdateHandler relative-coordinate/strict-inner-bounds policy.
// Hidden results emit no lines; their coordinates do not preserve a previously
// hidden native control's state. Panel/data/modal/capture decisions remain with
// the owner: the original callback checks only GraphsPanel:IsHidden().
inline MenuReplayPointerGuides BuildMenuReplayPointerGuides(double originX,double originY,
    double width,double height,double pointerX,double pointerY,bool graphsVisible,bool pointerAvailable=true){
    MenuReplayPointerGuideDetail::ValidateAxis(originX,width);
    MenuReplayPointerGuideDetail::ValidateAxis(originY,height);
    MenuReplayPointerGuides result;
    const std::array<std::uint8_t,4> crosshair{{90,90,90,90}},guide{{255,0,0,255}};
    result.lines[0].rgba=result.lines[1].rgba=crosshair;
    result.lines[2].rgba=result.lines[3].rgba=guide;
    if(!graphsVisible || !pointerAvailable || !std::isfinite(pointerX) || !std::isfinite(pointerY))return result;
    const double x=pointerX-originX,y=pointerY-originY;
    if(!(x>0 && x<width && y>0 && y<height))return result;
    result.visible=true;
    result.lines[0]={x,0,x,height,1,crosshair};
    result.lines[1]={0,y,width,y,1,crosshair};
    result.lines[2]={x,height,x,height+8,1,guide};
    result.lines[3]={width,y,width+8,y,1,guide};
    return result;
}
}
