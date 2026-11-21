#pragma once
#include <cmath>

namespace ZeroSisPresentation {

// Normalize a real pointer position against the live horizontal track. Drag
// capture may clamp at either endpoint; a fresh click must be inside the track.
inline bool NormalizeHorizontalSlider(double x,double y,double width,double height,
                                      double pointerX,double pointerY,bool captured,
                                      double& normalized) noexcept {
    if(!std::isfinite(x) || !std::isfinite(y) || !std::isfinite(width) ||
       !std::isfinite(height) || !std::isfinite(pointerX) || !std::isfinite(pointerY) ||
       width<=0 || height<=0 || width>1920 || height>1080 ||
       x<0 || y<0 || x+width>1920 || y+height>1080)return false;
    if(!captured && (pointerX<x || pointerX>x+width || pointerY<y || pointerY>y+height))return false;
    const double value=(pointerX-x)/width;
    normalized=value<0?0:value>1?1:value;
    return true;
}

} // namespace ZeroSisPresentation
