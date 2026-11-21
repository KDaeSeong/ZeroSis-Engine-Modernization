#pragma once

// Latest BNW PlayerTrade and TradeAI wire framing, not game trade restoration.
#include "RetailSaveStateWire.h"
#include <cstddef>
#include <cstdint>

namespace ZeroSisHost {
namespace RetailStateDetail {

constexpr std::size_t PlayerTradeRecordMinimumBytes = 57u;
constexpr std::size_t PlayerTradeMinimumBytes = 12u;
constexpr std::size_t PlayerTradeAIMinimumBytes = 8u;

inline void ReadPlayerTrade(Reader& reader) {
    // Original CvTradeClasses.cpp:3727-3858, header:25-44,142-148. Supported
    // v2 includes both lists. The v0 obsolete word and v1 single-list layout
    // are rejected; no version search or guessed padding is used.
    reader.Version(2);
    const auto expired = reader.SignedCount(PlayerTradeRecordMinimumBytes);
    for (std::uint32_t i = 0; i < expired; ++i) {
        // ID, origin X/Y, destination X/Y, two PlayerTypes, int-cast domain
        // and connection type, and location index precede the moving bool.
        reader.Fixed(10, 4);
        reader.Bool();
        reader.Fixed(4, 4); // Unit ID, completed/required circuits, end turn.
    }
    const auto plundered = reader.SignedCount(PlayerTradeRecordMinimumBytes);
    for (std::uint32_t i = 0; i < plundered; ++i) {
        // Plunder turn replaces the expired-list ID in the first ten words;
        // this is the writer's selected fields, not a full TradeConnection.
        reader.Fixed(10, 4);
        reader.Bool();
        reader.Fixed(4, 4);
    }
    // Neither m_aPlotList nor the two yield arrays are serialized in these
    // lists. They belong to other trade structures, not this Player boundary.
}

inline void ReadPlayerTradeAI(Reader& reader) {
    // Original CvTradeClasses.cpp:4473-4491. Owning Player is not serialized.
    reader.Version(0);
    reader.I32(); // Removable value.
}

} // namespace RetailStateDetail
} // namespace ZeroSisHost
