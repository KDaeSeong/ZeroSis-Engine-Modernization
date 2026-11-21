#pragma once

// Latest retained BNW Map tail, immediately after the last serialized plot.
// This only frames caller-owned inflated bytes; it performs no SDK or file I/O.
#include "RetailSaveStateWire.h"
#include <array>
#include <cstddef>
#include <cstdint>

namespace ZeroSisHost {
namespace RetailStateDetail {

struct MapTailInspection {
    RetailInflatedSpan areas, landmasses;
    std::uint32_t areaCount = 0, landmassCount = 0;
};

// CvDLLUtilDefines.h:19-29 and CvGameCoreEnums.h:11-22. The first five
// CvArea arrays use REALLY_MAX_PLAYERS/TEAMS, but the following two loops
// serialize only MAX_PLAYERS rows. None of these fixed arrays has a count.
constexpr std::size_t MapTailReallyMaxPlayers = 80;
constexpr std::size_t MapTailPlayers = 64;
constexpr std::size_t MapTailYieldTypes = 6;

// CvArea.cpp:763-808. Version, ten scalar fields, four boundary fields,
// two bools, five 80-element int arrays, 64 city-ID pairs, 64 yield rows,
// and the two empty hashed-array count words: 3,718 bytes before entries.
constexpr std::size_t MapTailAreaMinimum =
    4u + 10u * 4u + 4u * 4u + 2u +
    5u * MapTailReallyMaxPlayers * 4u + MapTailPlayers * 8u +
    MapTailPlayers * MapTailYieldTypes * 4u + 2u * 4u;

// CvMap.cpp:179-194. Version, ID, tile count, two centroid integers,
// water bool and a raw continent-type char. There is no structure padding.
constexpr std::size_t MapTailLandmassMinimum = 4u + 4u * 4u + 2u;

// FFreeListTrashArray.h:21-25,79-87,384-399,572-630. Both Map containers
// use the same wire metadata and ID masks as the Game vote free lists.
// The callback consumes one complete record and returns its serialized ID.
template<typename ReadRecord>
inline std::uint32_t ReadMapTailFreeList(Reader& input,
    std::size_t minimumRecordBytes, ReadRecord readRecord) {
    constexpr std::uint32_t maxSlots = 1u << 13;
    constexpr std::uint32_t indexMask = maxSlots - 1u;
    constexpr std::int32_t idMask = -static_cast<std::int32_t>(maxSlots);

    const auto slots = input.SignedCount(4);
    if (slots > maxSlots || (slots != 0 && (slots & (slots - 1u)) != 0))
        input.Fail(RetailStateErrorCode::InvalidValue, "Invalid BNW map free-list capacity");

    const auto lastIndex = input.I32();
    const auto freeHead = input.I32();
    const auto freeCount = input.I32();
    const auto currentId = input.I32();
    if (lastIndex < -1 || (lastIndex >= 0 &&
            static_cast<std::uint32_t>(lastIndex) >= slots))
        input.Fail(RetailStateErrorCode::InvalidValue, "Invalid BNW map free-list last index");
    const auto allocated = static_cast<std::uint32_t>(lastIndex + 1);
    if (freeCount < 0 || static_cast<std::uint32_t>(freeCount) > allocated ||
            freeHead < -1 || (freeHead >= 0 &&
                static_cast<std::uint32_t>(freeHead) >= allocated))
        input.Fail(RetailStateErrorCode::InvalidValue, "Invalid BNW map free-list metadata");
    const auto currentBits = static_cast<std::uint32_t>(currentId);
    if ((currentBits & indexMask) != 0 || (currentBits & ~indexMask) == 0)
        input.Fail(RetailStateErrorCode::InvalidValue, "Invalid BNW map free-list current ID");

    std::array<std::int32_t, maxSlots> nextFree{};
    std::array<unsigned char, maxSlots> state{};
    for (std::uint32_t i = 0; i < slots; ++i) {
        nextFree[i] = input.I32();
        if (nextFree[i] < -1 || (nextFree[i] >= 0 &&
                static_cast<std::uint32_t>(nextFree[i]) >= slots))
            input.Fail(RetailStateErrorCode::InvalidValue, "Invalid BNW map free-list link");
    }

    const auto active = input.SignedCount(minimumRecordBytes);
    if (active != allocated - static_cast<std::uint32_t>(freeCount))
        input.Fail(RetailStateErrorCode::InvalidValue, "Inconsistent BNW map free-list counts");

    auto link = freeHead;
    for (std::int32_t i = 0; i < freeCount; ++i) {
        if (link < 0 || static_cast<std::uint32_t>(link) >= allocated || state[link] != 0)
            input.Fail(RetailStateErrorCode::InvalidValue, "Invalid BNW map free-list chain");
        state[link] = 1;
        link = nextFree[link];
    }
    if (link != -1)
        input.Fail(RetailStateErrorCode::InvalidValue, "Inconsistent BNW map free-list head");

    for (std::uint32_t i = 0; i < active; ++i) {
        const auto id = readRecord(input);
        const auto slot = static_cast<std::uint32_t>(id) & indexMask;
        if (slot >= allocated || state[slot] != 0 || nextFree[slot] != -1 ||
                (id & idMask) >= currentId)
            input.Fail(RetailStateErrorCode::InvalidValue, "Invalid BNW map free-list record ID");
        state[slot] = 2;
    }
    return active;
}

inline std::int32_t ReadMapTailArea(Reader& input) {
    // CvArea.cpp:763-805 and CvArea.h:133-159. Latest Area record version.
    input.Version(1);
    const auto id = input.I32();
    input.Fixed(9, 4); // Remaining counters, including unsigned total found value.
    input.Fixed(4, 4); // North, south, east and west boundaries.
    input.Bool(); // Water.
    input.Bool(); // Mountains.

    // Units, cities, population, free specialists and revealed tiles.
    input.Fixed(5u * MapTailReallyMaxPlayers, 4);
    input.Fixed(MapTailPlayers, 8); // Target-city owner and ID pairs.
    input.Fixed(MapTailPlayers * MapTailYieldTypes, 4);

    // Resources use an unsigned count and omit values only for zero hashes.
    // Unknown nonzero hashes still have a value, even without type resolution.
    input.Hashes(4);

    // ImprovementArrayHelpers::Read/Write, CvImprovementClasses.cpp:1104-1153.
    // Unlike resource arrays, this count is signed and NO_IMPROVEMENT (-1)
    // is also a hash-only sentinel. Other hashes are followed by one int32.
    const auto improvements = input.SignedCount(4);
    for (std::uint32_t i = 0; i < improvements; ++i) {
        const auto hash = input.U32();
        if (hash != 0 && hash != 0xffffffffu) input.I32();
    }
    return id;
}

inline std::int32_t ReadMapTailLandmass(Reader& input) {
    // CvMap.cpp:179-194. Latest Landmass record version.
    input.Version(1);
    const auto id = input.I32();
    input.Fixed(3, 4); // Tile count and two centroid accumulators.
    input.Bool(); // Water.
    input.Skip(1); // Continent type is a raw char, not a serialized bool.
    return id;
}

inline MapTailInspection ReadMapTail(Reader& input) {
    // CvMap.cpp:1455-1460. No additional outer version or vector count
    // surrounds these two free-list containers.
    MapTailInspection result;
    const auto areaStart = input.Pos();
    result.areaCount = ReadMapTailFreeList(input, MapTailAreaMinimum, ReadMapTailArea);
    result.areas = input.SpanFrom(areaStart);

    const auto landmassStart = input.Pos();
    result.landmassCount = ReadMapTailFreeList(input, MapTailLandmassMinimum, ReadMapTailLandmass);
    result.landmasses = input.SpanFrom(landmassStart);

    input.I32(); // AIMapHints bitmask; the retained SDK imposes no enum bound.
    return result;
}

} // namespace RetailStateDetail
} // namespace ZeroSisHost
