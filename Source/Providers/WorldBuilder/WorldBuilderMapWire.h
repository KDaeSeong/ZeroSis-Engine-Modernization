#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include <vector>

namespace ZeroSisWorldBuilder {
using MapBytes = std::vector<unsigned char>;
// Named, owned file sections. No native C++ struct layout or pointer is serialized.
// Versions 6,7,9,10,11,12 have original-library and installed-file evidence.
struct MapDocument {
    unsigned char version=12,playable=0;
    bool hasScenario=false;
    std::uint32_t width=0,height=0,flags=17;
    // terrain, feature, natural wonder, resource, improvement, unit, technology,
    // policy, building, promotion, in the original file order within each group.
    std::array<MapBytes,10> types;
    MapBytes modData,name,description,worldType,plots;
    std::array<unsigned char,64> speed{};
    std::uint32_t startingTurn=0,maxTurns=0,targetScore=0,startYearBits=0xfffff060u;
    unsigned char playerCount=0,cityStateCount=0,teamCount=0,scenarioPadding=0;
    MapBytes units,unitNames,cities,victories,options;
    std::array<MapBytes,5> relationships;
    MapBytes influence,visibility,teams,players,cityStates,plotScenario;
    // Diagnostic only, never serialized: bit 0 units, bit 1 custom names,
    // bit 2 cities. Set only by the explicit legacy-recovery read policy.
    unsigned recoveredAllocators=0;
};

enum class MapReadPolicy { Strict, RebuildInvalidFreeLists };
// Recovery preserves every plot-reachable record and rebuilds ONLY malformed
// free lists from plot/unit ownership. Unreachable slots in an affected pool
// become reusable. Valid pools, including unreferenced allocated names, stay intact.
// Callers must record recoveredAllocators and save a separate output, never silently
// overwrite the source. SDK-class publication and old-version conversion are separate.
MapDocument ReadMapDocument(const void* bytes,std::size_t size,bool requireScenario=false,MapReadPolicy policy=MapReadPolicy::Strict);
MapBytes WriteMapDocument(const MapDocument& document);
void ValidateMapDocument(const MapDocument& document);
std::size_t MapUnitStride(unsigned version);
std::size_t MapCityStride(unsigned version);
std::size_t MapPlayerStride(unsigned version);
}
