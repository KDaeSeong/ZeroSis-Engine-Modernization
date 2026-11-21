#pragma once
#include <cmath>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace ZeroSisHost {
struct MenuReplayGraphColor final {
    std::string type;
    double r=0,g=0,b=0,a=1;
};

// The catalog order is the original GameInfo.Colors() iterator order. Roster
// order is recorded replay order, before any map-specific minor-color swaps.
// Keep the original double channels until selection: float rounding can cross
// the original strict black threshold or inclusive color-difference boundary.
inline std::vector<MenuReplayGraphColor> SelectMenuReplayGraphColors(
    const std::vector<MenuReplayGraphColor>& orderedColorCatalog,
    const std::vector<std::pair<std::string,std::string>>& recordedRoster) {
    const auto require=[](bool valid,const char* reason){
        if(!valid)throw std::runtime_error(reason);
    };
    require(!orderedColorCatalog.empty() && orderedColorCatalog.size()<=4096,
        "Unsupported replay graph color catalog size");
    require(recordedRoster.size()<=64,"Unsupported replay graph color roster size");
    std::map<std::string,const MenuReplayGraphColor*> byType;
    for(const auto& color:orderedColorCatalog){
        require(!color.type.empty() && color.type.size()<=1024 && color.type.find('\0')==std::string::npos,
            "Unsupported replay graph color Type");
        for(double value:{color.r,color.g,color.b,color.a})
            require(std::isfinite(value) && value>=0 && value<=1,
                "Unsupported replay graph color channel");
        require(byType.emplace(color.type,&color).second,"Unsupported duplicate replay graph color Type");
    }
    for(const auto& player:recordedRoster)
        require(byType.count(player.first)==1 && byType.count(player.second)==1,
            "Unsupported missing recorded replay player color");

    // Match the original Type-keyed directed cache, including the assumed zero
    // self-distance. The virtual black color deliberately uses COLOR_BLACK.
    std::map<std::string,std::map<std::string,double>> distances;
    const auto distance=[&](const MenuReplayGraphColor& left,const MenuReplayGraphColor& right){
        auto found=distances.find(left.type);
        if(found==distances.end())
            found=distances.emplace(left.type,std::map<std::string,double>{{left.type,0}}).first;
        auto& row=found->second;
        const auto cached=row.find(right.type);
        if(cached!=row.end())return cached->second;
        const double red=std::pow((left.r-right.r)*255.0,2.0);
        const double green=std::pow((left.g-right.g)*255.0,2.0);
        const double blue=std::pow((left.b-right.b)*255.0,2.0);
        const double value=red+green+blue;
        row.emplace(right.type,value);
        return value;
    };
    const MenuReplayGraphColor black{"COLOR_BLACK",0,0,0,1};
    std::set<std::string> rejected;
    std::vector<MenuReplayGraphColor> selected;
    selected.reserve(recordedRoster.size());
    const auto unique=[&](const MenuReplayGraphColor& color){
        if(rejected.count(color.type))return false;
        if(distance(color,black)>5000.0){
            for(const auto& previous:selected)
                if(distance(color,previous)<3000.0){
                    rejected.insert(color.type);
                    return false;
                }
            return true;
        }
        rejected.insert(color.type);
        return false;
    };
    for(const auto& player:recordedRoster){
        const auto* primary=byType.at(player.first);
        const auto* secondary=byType.at(player.second);
        const MenuReplayGraphColor* chosen=nullptr;
        if(unique(*primary))chosen=primary;
        else if(unique(*secondary))chosen=secondary;
        else for(const auto& color:orderedColorCatalog)
            if(unique(color)){chosen=&color;break;}
        // Original DetermineGraphColor returns primary when all candidates are
        // exhausted, including an already-rejected or black primary.
        selected.push_back(chosen?*chosen:*primary);
    }
    return selected;
}
}
