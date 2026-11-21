#pragma once
#include "WorldViewRenderer.h"
#include <cstdint>
#include <stdexcept>
#include <vector>

namespace ZeroSisPresentation { namespace OriginalLighting {
// Selection metadata is intentionally separate from both colour and picking.
// Unknown plots do not expose continent, water, material or feature fields.
inline std::vector<unsigned char> CaptureLightingSelectors(const WorldView& view){
    if(view.gridWidth<=0||view.gridHeight<=0||
       std::uint64_t(view.gridWidth)*std::uint64_t(view.gridHeight)>500000||view.plots.size()>500000)
        throw std::invalid_argument("Invalid detached lighting grid");
    const auto count=static_cast<std::size_t>(view.gridWidth)*static_cast<std::size_t>(view.gridHeight);
    std::vector<unsigned char> selectors(count,255),seen(count,0);
    for(const auto& plot:view.plots){
        if(plot.x<0||plot.y<0||plot.x>=view.gridWidth||plot.y>=view.gridHeight)
            throw std::invalid_argument("Detached lighting plot is outside its grid");
        const auto at=static_cast<std::size_t>(plot.y)*view.gridWidth+plot.x;
        if(seen[at])throw std::invalid_argument("Duplicate detached lighting plot");
        seen[at]=1;
        if(!plot.revealed)continue;
        if(plot.water){selectors[at]=0;continue;}
        if(plot.continent<0||plot.continent>4)
            throw std::invalid_argument("Invalid detached lighting continent");
        selectors[at]=static_cast<unsigned char>(plot.continent);
    }
    return selectors;
}
}}
