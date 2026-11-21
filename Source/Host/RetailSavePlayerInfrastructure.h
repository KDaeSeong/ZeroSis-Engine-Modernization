#pragma once

// Four nested states written by original CvPlayer.cpp:22599-22602. This frames
// only their original x86 wire format, not a complete Player or a restore.
#include "RetailSaveStateWire.h"
#include <cstddef>
#include <cstdint>
#include <limits>

namespace ZeroSisHost {
namespace RetailStateDetail {

// Empty arrays give structural lower bounds, not valid game/ruleset profiles.
constexpr std::size_t PlayerDealAIMinimumBytes = 4u;
constexpr std::size_t PlayerBuilderTaskingAIMinimumBytes = 14u;
constexpr std::size_t PlayerCityConnectionsMinimumBytes = 12u;
constexpr std::size_t PlayerDangerPlotsMinimumBytes = 13u;

inline void ReadPlayerDealAI(Reader& reader) {
    // CvDealAI.cpp:63-68. The cached peace value and owning Player are not saved.
    reader.Version(1);
}

inline void ReadPlayerBuilderTaskingAI(Reader& reader) {
    // CvBuilderTaskingAI.cpp:139-156, header:110,126,138-139. The plot list is
    // FStaticVector<int>, whose size() is uint32 in both original and port;
    // this direct size() insertion is not a native-size_t vector count.
    reader.Version(2);
    reader.I32(); // Repair BuildTypes enum, four-byte codec.
    const auto plots = reader.Count(4);
    reader.Fixed(plots, 4); // Non-territory plot IDs, int32.
    reader.Bool(); // Keep marshes.
    reader.Bool(); // Keep jungle, present in the supported v2 only.
}

inline void ReadPlayerCityConnections(Reader& reader) {
    // CvCityConnections.cpp:111-129 and header:59-78. One uint32 dimension,
    // then D*D RouteInfo entries, each pass-eval char followed by route-state
    // char. Neither raw char is a bool and neither has native struct padding.
    reader.Version(1);
    const auto dimension = reader.Count(0);
    // The explicit dimension is charged as D declared rows against both count
    // budgets. Its derived D*D cells have no count word and are byte-budgeted,
    // not charged again as synthetic array records.
    if (dimension != 0 && dimension > (std::numeric_limits<std::uint32_t>::max)() / dimension)
        reader.Fail(RetailStateErrorCode::InvalidValue,
            "City route dimension square overflows the original uint32 cell count");
    // Skip the entire interleaved matrix in two equal byte spans. Fixed checks
    // products by division before multiplication, in O(1), including D=0;
    // no unchecked D*D*2 or dimension-sized allocation/loop is performed.
    reader.Fixed(dimension, dimension);
    reader.Fixed(dimension, dimension);

    // m_aiCityPlotIDs is FStaticVector<int>, with a four-byte unsigned size()
    // writer. Read:99-106 interprets that word as signed int; reject negatives.
    // Its capacity estimate is not a serialized maximum or an extra count.
    const auto cities = reader.SignedCount(4);
    reader.Fixed(cities, 4);
}

inline std::uint32_t ReadPlayerDangerPlots(Reader& reader) {
    // CvDangerPlots.cpp:673-688; header:62-77. PlayerTypes is four-byte, bool
    // one-byte, and each FFastVector<uint> value is uint32. GameTypes' special
    // one-byte enum codec does not apply to the saved PlayerTypes value.
    reader.Version(1);
    reader.I32(); // Owning PlayerTypes; semantic identity is not verified here.
    reader.Bool(); // Array allocated. This flag does not gate the saved grid.
    const auto plots = reader.SignedCount(4); // Explicit map grid size, int32.
    reader.Fixed(plots, 4);
    // The caller can compare this recorded size with an independently framed
    // Map. No map dimension, player identity or ruleset is inferred here.
    // m_bDirty and the relationship-modifier doubles are not serialized.
    return plots;
}

} // namespace RetailStateDetail
} // namespace ZeroSisHost
