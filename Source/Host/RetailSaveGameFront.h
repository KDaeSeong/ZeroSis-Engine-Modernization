#pragma once

// BNW Game v1 through plot-extra state, derived from the retained SDK writers.
// This only frames caller-owned inflated bytes; it performs no SDK or file I/O.
#include "RetailSaveStateWire.h"
#include <array>
#include <cstddef>
#include <cstdint>

namespace ZeroSisHost {
namespace RetailStateDetail {

struct GameFrontRandomLayout {
    std::size_t seedOffset = 0, callCountOffset = 0, resetCountOffset = 0;
    std::uint32_t seed = 0, calls = 0, resets = 0;
};

// Optional source-order positions for native restore comparison. These are
// emitted by the same walker used for retail framing, never by marker search.
struct GameFrontReloadLayout {
    std::size_t aiAutoPlayOffset = 0, gameStateOffset = 0;
    std::int32_t aiAutoPlay = 0, gameState = 0;
    RetailInflatedSpan advisorMessages;
    GameFrontRandomLayout mapRandom, jonRandom;
    std::size_t replayCountOffset = 0, sessionOffset = 0;
    std::uint32_t replayMessages = 0;
    RetailInflatedSpan replayRecords;
    std::int32_t sessions = 0;
};

// CvStructs.cpp:61-82,115-132. A vote option has four i32 fields and a string.
inline void ReadGameFrontVoteOption(Reader& reader) {
    reader.Fixed(4, 4);
    reader.String();
}

inline std::int32_t ReadGameFrontVoteRecord(Reader& reader, bool selection) {
    reader.Version(1);
    const auto id = reader.I32();
    reader.I32(); // VoteSourceTypes
    if (selection) {
        const auto options = reader.Count(20);
        for (std::uint32_t i = 0; i < options; ++i)
            ReadGameFrontVoteOption(reader);
    } else {
        ReadGameFrontVoteOption(reader);
    }
    return id;
}

// FFreeListTrashArray.h:21-25,572-630. Slot capacity is at most 1 << 13.
// Preserve the SDK's allocated/free/active accounting and masked record IDs.
inline void ReadGameFrontVotes(Reader& reader, bool selection) {
    constexpr std::uint32_t maxSlots = 1u << 13;
    constexpr std::uint32_t indexMask = maxSlots - 1u;
    constexpr std::int32_t idMask = -static_cast<std::int32_t>(maxSlots);

    const auto slots = reader.SignedCount(4);
    if (slots > maxSlots || (slots != 0 && (slots & (slots - 1u)) != 0))
        reader.Fail(RetailStateErrorCode::InvalidValue, "Invalid BNW free-list capacity");

    const auto lastIndex = reader.I32();
    const auto freeHead = reader.I32();
    const auto freeCount = reader.I32();
    const auto currentId = reader.I32();
    if (lastIndex < -1 || (lastIndex >= 0 &&
            static_cast<std::uint32_t>(lastIndex) >= slots))
        reader.Fail(RetailStateErrorCode::InvalidValue, "Invalid BNW free-list last index");
    const auto allocated = static_cast<std::uint32_t>(lastIndex + 1);
    if (freeCount < 0 || static_cast<std::uint32_t>(freeCount) > allocated ||
            freeHead < -1 || (freeHead >= 0 &&
                static_cast<std::uint32_t>(freeHead) >= allocated))
        reader.Fail(RetailStateErrorCode::InvalidValue, "Invalid BNW free-list metadata");
    const auto currentBits = static_cast<std::uint32_t>(currentId);
    if ((currentBits & indexMask) != 0 || (currentBits & ~indexMask) == 0)
        reader.Fail(RetailStateErrorCode::InvalidValue, "Invalid BNW free-list current ID");

    std::array<std::int32_t, maxSlots> nextFree{};
    std::array<unsigned char, maxSlots> state{};
    for (std::uint32_t i = 0; i < slots; ++i) {
        nextFree[i] = reader.I32();
        if (nextFree[i] < -1 || (nextFree[i] >= 0 &&
                static_cast<std::uint32_t>(nextFree[i]) >= slots))
            reader.Fail(RetailStateErrorCode::InvalidValue, "Invalid BNW free-list link");
    }

    const auto active = reader.SignedCount(selection ? 16u : 32u);
    if (active != allocated - static_cast<std::uint32_t>(freeCount))
        reader.Fail(RetailStateErrorCode::InvalidValue, "Inconsistent BNW free-list counts");

    auto link = freeHead;
    for (std::int32_t i = 0; i < freeCount; ++i) {
        if (link < 0 || static_cast<std::uint32_t>(link) >= allocated || state[link] != 0)
            reader.Fail(RetailStateErrorCode::InvalidValue, "Invalid BNW free-list chain");
        state[link] = 1;
        link = nextFree[link];
    }
    if (link != -1)
        reader.Fail(RetailStateErrorCode::InvalidValue, "Inconsistent BNW free-list head");

    for (std::uint32_t i = 0; i < active; ++i) {
        const auto id = ReadGameFrontVoteRecord(reader, selection);
        const auto slot = static_cast<std::uint32_t>(id) & indexMask;
        if (slot >= allocated || state[slot] != 0 || nextFree[slot] != -1 ||
                (id & idMask) >= currentId)
            reader.Fail(RetailStateErrorCode::InvalidValue, "Invalid BNW free-list record ID");
        state[slot] = 2;
    }
}

// CvRandom.cpp:232-251. Debug streams have additional history containers;
// this release profile must reject that branch rather than lose its boundary.
inline void ReadGameFrontRandom(Reader& reader, GameFrontRandomLayout* layout = nullptr) {
    reader.Version(1);
    GameFrontRandomLayout result;
    result.seedOffset = reader.Pos(); result.seed = reader.U32();
    result.callCountOffset = reader.Pos(); result.calls = reader.U32();
    result.resetCountOffset = reader.Pos(); result.resets = reader.U32();
    if (reader.Bool())
        reader.Fail(RetailStateErrorCode::UnsupportedProfile, "Debug BNW random state is unsupported");
    if (layout) *layout = result;
}

// CvGame.cpp:9571-9578 and CvReplayMessage.cpp:17-19,143-156.
inline void ReadGameFrontReplay(Reader& reader, GameFrontReloadLayout* layout = nullptr) {
    reader.Version(2);
    const auto countOffset = reader.Pos();
    const auto messages = reader.SignedCount(20);
    const auto recordsStart = reader.Pos();
    for (std::uint32_t i = 0; i < messages; ++i) {
        reader.Fixed(2, 4); // turn, ReplayMessageTypes
        const auto plots = reader.SignedCount(4);
        reader.Fixed(plots, 4); // pairs of signed i16 plot coordinates
        reader.I32(); // PlayerTypes
        reader.String();
    }
    if (layout) {
        layout->replayCountOffset = countOffset;
        layout->replayMessages = messages;
        layout->replayRecords = reader.SpanFrom(recordsStart);
    }
}

inline void ReadGameFront(Reader& reader, const RetailSaveStateProfile& profile,
                          GameFrontReloadLayout* layout = nullptr) {
    // CvGame.cpp:9471-9533. Do not impose nonnegative constraints on signed
    // game state or enum fields: years and absent-player/type sentinels differ.
    reader.Version(1);
    reader.Fixed(21, 4);
    const auto autoPlayOffset = reader.Pos();
    const auto autoPlay = reader.I32();
    reader.Fixed(7, 4);
    for (unsigned i = 0; i < 10; ++i) reader.Bool();
    const auto advisorsStart = reader.Pos();
    reader.Strings(); // unordered advisor-message set
    if (layout) layout->advisorMessages = reader.SpanFrom(advisorsStart);
    reader.Fixed(6, 4);
    const auto gameStateOffset = reader.Pos();
    const auto gameState = reader.I32();
    reader.Fixed(5, 4);
    reader.String(); // script data

    // ArrayWrapper writes no count. CvDLLUtilDefines.h:22-29 fixes these
    // Game arrays at MAX_PLAYERS/MAX_TEAMS=64 and MAX_CIV_TEAMS=63.
    reader.Fixed(7u * 64u, 4);
    for (unsigned i = 0; i < 8; ++i) reader.Hashes(4);
    reader.Fixed(3u * 63u, 4);

    const auto specialUnits = reader.Count(4);
    for (std::uint32_t i = 0; i < specialUnits; ++i)
        if (reader.U32() != 0) reader.Bool();

    // CvInfosSerializationHelper.h:623-639 emits only an OUTER row count.
    // The inner width is the caller's explicit NUM_VICTORY_POINT_AWARDS.
    reader.Hashes(static_cast<std::size_t>(profile.victoryPointAwards) * 4u);
    reader.Strings(); // destroyed cities
    reader.Strings(); // great people born
    ReadGameFrontVotes(reader, true);
    ReadGameFrontVotes(reader, false);
    ReadGameFrontRandom(reader, layout ? &layout->mapRandom : nullptr);
    ReadGameFrontRandom(reader, layout ? &layout->jonRandom : nullptr);
    ReadGameFrontReplay(reader, layout);

    // CvGame.cpp:9581-9588; CvStructs.cpp:650-678 and STL vector framing.
    const auto sessionOffset = reader.Pos();
    const auto sessions = reader.I32(); // not a following array length
    const auto yields = reader.Count(12);
    for (std::uint32_t i = 0; i < yields; ++i) {
        reader.Fixed(2, 4);
        const auto values = reader.Count(4);
        reader.Fixed(values, 4);
    }
    const auto costs = reader.Count(12);
    reader.Fixed(costs, 12);
    reader.Bool(); // archaeology triggered
    reader.I32(); // earliest barbarian release turn
    if (layout) {
        layout->aiAutoPlayOffset = autoPlayOffset; layout->aiAutoPlay = autoPlay;
        layout->gameStateOffset = gameStateOffset; layout->gameState = gameState;
        layout->sessionOffset = sessionOffset; layout->sessions = sessions;
    }
}

} // namespace RetailStateDetail
} // namespace ZeroSisHost
