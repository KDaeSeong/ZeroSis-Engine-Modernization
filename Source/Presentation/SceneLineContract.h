#pragma once
#include "BitmapRenderer.h"
#include <cmath>
#include <cstddef>

namespace ZeroSisPresentation {
inline bool SceneLineFailure(std::wstring* error,const wchar_t* message){
    if(error)*error=message;return false;
}

// Shares the existing sprite coordinate bound. A separate line count and
// width budget bounds work without expanding lines into per-pixel sprites.
inline bool ValidateSceneLines(const Scene& scene,std::wstring* error){
    if(scene.lines.size()>kMaxSceneLines)return SceneLineFailure(error,L"Scene line count exceeds its budget");
    std::uint32_t previous=0;bool first=true;
    for(const auto& line:scene.lines){
        if(line.beforeSprite>scene.sprites.size() || (!first && line.beforeSprite<previous))
            return SceneLineFailure(error,L"Scene line anchors are out of range or unordered");
        previous=line.beforeSprite;first=false;
        for(const auto* point:{line.start,line.end})for(unsigned axis=0;axis<2;++axis)
            if(!std::isfinite(point[axis]) || std::fabs(point[axis])>10000000.0f)
                return SceneLineFailure(error,L"Scene line endpoint exceeds coordinate limits");
        if(!std::isfinite(line.width) || line.width<=0 || line.width>256.0f)
            return SceneLineFailure(error,L"Scene line width exceeds its budget");
        for(float value:line.tintRGBA)if(!std::isfinite(value) || value<0 || value>1)
            return SceneLineFailure(error,L"Scene line color is outside [0,1]");
        for(float value:line.clipRect)if(!std::isfinite(value) || std::fabs(value)>10000000.0f)
            return SceneLineFailure(error,L"Scene line clip exceeds coordinate limits");
        if(!(line.clipRect[2]>line.clipRect[0] && line.clipRect[3]>line.clipRect[1]))
            return SceneLineFailure(error,L"Scene line clip is empty or inverted");
    }
    return true;
}

inline bool IsSceneEmpty(const Scene& scene) noexcept{
    return scene.textures.empty() && scene.sprites.empty() && scene.hits.empty() && scene.scrolls.empty() &&
        scene.pixelHits.indices.empty() && scene.pixelHits.keys.empty() && scene.lines.empty();
}

// Both native composition paths and the file/CPU fixture use this same order.
// Validation precedes every callback, including when an invalid anchor would
// otherwise leave a trailing stroke silently undispatched.
template<class PaintSprite,class PaintLine>
bool DispatchScenePaint(const Scene& scene,PaintSprite sprite,PaintLine line,std::wstring* error){
    if(!ValidateSceneLines(scene,error))return false;
    std::size_t nextLine=0;
    for(std::size_t nextSprite=0;nextSprite<=scene.sprites.size();++nextSprite){
        while(nextLine<scene.lines.size() && scene.lines[nextLine].beforeSprite==nextSprite)
            if(!line(scene.lines[nextLine++]))return false;
        if(nextSprite<scene.sprites.size() && !sprite(scene.sprites[nextSprite]))return false;
    }
    return true;
}
} // namespace ZeroSisPresentation
