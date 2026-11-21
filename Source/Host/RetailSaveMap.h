#pragma once

// Latest supported BNW Game + complete Map framing, without SDK mutation.
// A complete Map span is not a complete retail container or a load approval.
#include "RetailSaveState.h"
#include "RetailSavePlot.h"
#include "RetailSaveMapTail.h"
#include <limits>
#include <vector>

namespace ZeroSisHost {
struct RetailSaveMapInspection {
    RetailSaveStateInspection prefix;
    RetailInflatedSpan map, plots, areas, landmasses;
    std::size_t nextInflatedOffset = 0, arrayRecords = 0;
    std::uint32_t plotCount = 0, areaCount = 0, landmassCount = 0;
    bool completeSaveVerified = false;
    bool rulesetCompatibilityVerified = false;
};

class RetailSaveMap {
public:
    static RetailSaveMapInspection InspectGameAndMap(const unsigned char* data, std::size_t size,
        const RetailSaveStateProfile& profile,
        const RetailSaveStateLimits& limits = RetailSaveStateLimits{}) {
        RetailSaveMapInspection result;
        result.prefix = RetailSaveState::InspectGameAndMapPrefix(data, size, profile, limits);
        // CvMap::m_iGridSize is a signed int in the supported SDK. Check before
        // multiplication even when callers raise the configurable plot budget.
        if (result.prefix.mapWidth > static_cast<std::uint32_t>((std::numeric_limits<std::int32_t>::max)()) /
                result.prefix.mapHeight)
            throw RetailStateError(RetailStateErrorCode::MapPlotLimit, result.prefix.mapHeader.offset,
                                   "BNW map exceeds signed SDK grid capacity");
        result.plotCount = result.prefix.mapWidth * result.prefix.mapHeight;

        // The prefix has already charged its dynamic records. A second bounded
        // cursor starts at the first plot and shares the remaining global budget.
        auto remaining = limits;
        remaining.maxTotalRecords -= result.prefix.arrayRecords;
        RetailStateDetail::Reader reader(data, size, remaining);
        reader.Skip(result.prefix.nextInflatedOffset);
        const auto plotStart = reader.Pos();
        for (std::uint32_t i = 0; i < result.plotCount; ++i)
            RetailStateDetail::ReadMapPlot(reader);
        result.plots = reader.SpanFrom(plotStart);
        const auto tail = RetailStateDetail::ReadMapTail(reader);
        result.areas = tail.areas;
        result.landmasses = tail.landmasses;
        result.areaCount = tail.areaCount;
        result.landmassCount = tail.landmassCount;
        result.nextInflatedOffset = reader.Pos();
        result.map = reader.SpanFrom(result.prefix.mapHeader.offset);
        result.arrayRecords = result.prefix.arrayRecords + reader.Records();
        return result;
    }
    static RetailSaveMapInspection InspectGameAndMap(const std::vector<unsigned char>& data,
        const RetailSaveStateProfile& profile,
        const RetailSaveStateLimits& limits = RetailSaveStateLimits{}) {
        return InspectGameAndMap(data.data(), data.size(), profile, limits);
    }
};
} // namespace ZeroSisHost
