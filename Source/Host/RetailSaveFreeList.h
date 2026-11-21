#pragma once

// The FFreeListTrashArray outer wire header, before any serialized objects.
// No object length, version, or complete-list boundary is inferred here.
#include "RetailSaveStateWire.h"
#include <array>
#include <cstddef>
#include <cstdint>

namespace ZeroSisHost {
namespace RetailStateDetail {

struct RetailFreeListHeader {
    std::uint32_t slots = 0, liveCount = 0;
    std::int32_t lastIndex = -1, freeHead = -1, freeCount = 0, currentId = 0;
    RetailInflatedSpan headerSpan;
    // The first actual object, or the next field when liveCount is zero.
    // The caller must parse liveCount real objects to find the list's end.
    std::size_t nextInflatedOffset = 0;
};

constexpr std::size_t FreeListHeaderMinimumBytes = 24u;
constexpr std::uint32_t FreeListMaximumSlots = 1u << 13;

inline RetailFreeListHeader ReadFreeListHeader(Reader& reader) {
    // Original/current FFreeListTrashArray.h:572-630, GetCount in
    // FFreeListArrayBase.h:74. Five int32 metadata words, slots int32 links,
    // then one int32 live count. There is no pool version or object length.
    const auto start = reader.Pos();
    RetailFreeListHeader result;
    result.slots = reader.SignedCount(4);
    if (result.slots > FreeListMaximumSlots ||
            (result.slots && (result.slots & (result.slots - 1u))))
        reader.Fail(RetailStateErrorCode::InvalidValue, "Invalid BNW free-list capacity");
    result.lastIndex = reader.I32();
    result.freeHead = reader.I32();
    result.freeCount = reader.I32();
    result.currentId = reader.I32();
    if (result.lastIndex < -1 || (result.lastIndex >= 0 &&
            static_cast<std::uint32_t>(result.lastIndex) >= result.slots))
        reader.Fail(RetailStateErrorCode::InvalidValue, "Invalid BNW free-list last index");
    const auto allocated = static_cast<std::uint32_t>(result.lastIndex + 1);
    if (result.freeCount < 0 || static_cast<std::uint32_t>(result.freeCount) > allocated)
        reader.Fail(RetailStateErrorCode::InvalidValue, "Invalid BNW free-list free count");
    const auto currentBits = static_cast<std::uint32_t>(result.currentId);
    constexpr std::uint32_t indexMask = FreeListMaximumSlots - 1u;
    if (currentBits & indexMask)
        reader.Fail(RetailStateErrorCode::InvalidValue, "Invalid BNW free-list ID generation");
    // The generation bits are opaque here, including zero. The writer records
    // the current int verbatim and Add has no explicit wrap-avoidance path.
    // A nonzero-generation SDK assertion is not a safe framing requirement.

    std::array<std::int32_t, FreeListMaximumSlots> links{};
    for (std::uint32_t i = 0; i < result.slots; ++i) links[i] = reader.I32();
    // Charge only the two explicitly serialized counts: capacity rows and live
    // objects. The caller must not charge these live objects a second time.
    result.liveCount = reader.SignedCount(0);
    if (result.liveCount != allocated - static_cast<std::uint32_t>(result.freeCount))
        reader.Fail(RetailStateErrorCode::InvalidValue, "Inconsistent BNW free-list live count");

    if (result.freeCount == 0) {
        // Base construction starts an unallocated empty pool with head -2;
        // Init/RemoveAll use -1. Both are explicit SDK states, not guesses.
        const bool constructedEmpty = result.slots == 0 && result.lastIndex == -1 && result.freeHead == -2;
        if (result.freeHead != -1 && !constructedEmpty)
            reader.Fail(RetailStateErrorCode::InvalidValue, "Invalid empty BNW free-list head");
    } else {
        std::array<unsigned char, FreeListMaximumSlots> visited{};
        auto link = result.freeHead;
        for (std::int32_t i = 0; i < result.freeCount; ++i) {
            if (link < 0 || static_cast<std::uint32_t>(link) >= allocated || visited[link])
                reader.Fail(RetailStateErrorCode::InvalidValue, "Invalid BNW free-list chain");
            visited[link] = 1;
            link = links[link];
        }
        if (link != -1)
            reader.Fail(RetailStateErrorCode::InvalidValue, "Unterminated BNW free-list chain");
    }
    // Unvisited nextFree values are not validated: they are not traversed by
    // the active free chain and can contain dormant/retired values. Object ID
    // placement and complete object bodies require the caller's real parser.
    result.headerSpan = reader.SpanFrom(start);
    result.nextInflatedOffset = reader.Pos();
    return result;
}

} // namespace RetailStateDetail
} // namespace ZeroSisHost
