#pragma once

// Latest retained BNW TacticalAI and HomelandAI framing only. The enclosing
// Player, catalogs, subsequent state and restore are not validated here.
#include "RetailSaveStateWire.h"
#include <cstddef>
#include <cstdint>

namespace ZeroSisHost {
namespace RetailStateDetail {

constexpr std::size_t PlayerTacticalAIMinimumBytes = 12u;
constexpr std::size_t PlayerHomelandAIMinimumBytes = 8u;
constexpr std::size_t PlayerTemporaryZoneBytes = 24u;

inline void ReadPlayerTacticalAI(Reader& reader) {
    // CvTacticalAI.cpp:342-350. FStaticVector's stream codec writes a uint32
    // size and each element, regardless of its POD/capacity template arguments.
    // Its capacity estimate is not an on-wire count limit.
    reader.Version(1);
    reader.I32(); // Phony field retained by the original serializer.
    const auto zones = reader.Count(PlayerTemporaryZoneBytes);
    for (std::uint32_t i = 0; i < zones; ++i) {
        // CvTemporaryZone operator<<, CvTacticalAI.cpp:191-201. Target enum,
        // last turn, x, y, and naval-invasion flag all use four-byte int codecs.
        // The last field is NOT a serialized bool. Read accepts any nonzero int.
        reader.Version(1);
        reader.Fixed(5, 4);
    }
}

inline void ReadPlayerHomelandAI(Reader& reader) {
    // CvHomelandAI.cpp:87-95. No additional collection or base-class header.
    reader.Version(1);
    reader.I32(); // Move-priority turn.
}

} // namespace RetailStateDetail
} // namespace ZeroSisHost
