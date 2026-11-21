#pragma once

// Frames the latest SDK supporting state at a caller-supplied offset.
// No retail placement, including immediately after Map, is inferred here.
#include "RetailSaveStateWire.h"
#include <cstddef>

namespace ZeroSisHost {
namespace RetailStateDetail {

inline void ReadSupporting(Reader& reader, std::size_t plotCount) {
    // CvGame.cpp:9605-9612; nested writers are CvBarbarians.cpp:245-253
    // and CvGoodyHuts.cpp:122-131. ArrayWrapper writes no length words.
    reader.Version(1); // Supporting class data.
    reader.Version(1); // Barbarians.
    reader.Fixed(plotCount, 2); // Signed short camp spawn counters.
    reader.Fixed(plotCount, 2); // Signed short spawned-unit counters.
    reader.Version(1); // Goody huts.
    reader.Fixed(22u * 3u, 4); // Signed int results; negative values are valid.
}

} // namespace RetailStateDetail

class RetailSaveSupporting {
public:
    static RetailInflatedSpan InspectAt(const unsigned char* data, std::size_t size,
        std::size_t start, std::size_t plotCount,
        const RetailSaveStateLimits& limits = RetailSaveStateLimits{}) {
        RetailStateDetail::Reader reader(data, size, limits);
        if (plotCount > limits.maxMapPlots)
            reader.Fail(RetailStateErrorCode::MapPlotLimit, "Supporting plot count exceeds budget");
        reader.Skip(start);
        RetailStateDetail::ReadSupporting(reader, plotCount);
        return reader.SpanFrom(start);
    }
};
} // namespace ZeroSisHost
