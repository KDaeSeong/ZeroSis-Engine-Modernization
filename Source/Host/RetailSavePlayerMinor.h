#pragma once

// Latest retained BNW MinorCivAI and nested quest framing, not Player restore.
// References use SDK_BNW_Original. The port's corresponding Write bodies,
// member declarations and three Minor enum codecs have the same wire layout.
#include "RetailSaveStateWire.h"
#include <cstddef>
#include <cstdint>

namespace ZeroSisHost {
namespace RetailStateDetail {

constexpr std::size_t PlayerMinorCivAIMinimumBytes = 3409u;
constexpr std::size_t PlayerMinorCivQuestBytes = 21u;

inline void ReadPlayerMinorBoolArray(Reader& reader, std::size_t count) {
    for (std::size_t i = 0; i < count; ++i) reader.Bool();
}

inline void ReadPlayerMinorCivQuest(Reader& reader) {
    // CvMinorCivAI.cpp:1582-1594. The quest enum is explicitly int32 at
    // 10059-10063, followed by three int32 fields and the strict handled bool.
    // The minor/assigned Player IDs are absent; Read assigns them externally
    // at 1783-1784. There is no native structure padding or additional header.
    reader.Version(2);
    reader.Fixed(4u, 4);
    reader.Bool();
}

inline void ReadPlayerMinorCivAI(Reader& reader) {
    // Required caller profile: RetailPlayerAiLateProfile::InitializedMinorQuests.
    // ResetQuestList creates 22 lists (CvMinorCivAI.cpp:1693-1708). Write
    // asserts that size but emits no outer count (1840-1852); Read also fixes
    // the list count at 22 (1768-1774). Do not infer another initialization
    // state or list count from subsequent version words.
    constexpr std::size_t major = 22u;
    constexpr std::size_t teams = 80u; // REALLY_MAX_TEAMS, not MAX_TEAMS=64.
    reader.Version(1); // CvMinorCivAI.cpp:1795-1799.

    // 1801-1812: personality/status/unique unit, threat turn, global quest
    // countdown, ally, allied turn, buyout player: eight four-byte scalars.
    // Minor personality/status codecs explicitly cast to int (10033-10056).
    // UnitTypes/PlayerTypes use the verified original SDK int32 enum codecs.
    reader.Fixed(8u, 4);

    // CvMinorCivAI.h:564-590 declares actual C arrays, not generic vectors.
    // FDataStream.h:221-229 serializes them recursively with no count words.
    ReadPlayerMinorBoolArray(reader, major); // 1814: war quests.
    reader.Fixed(major * major, 4); // 1816: int[22][22] enemy-unit counts.
    ReadPlayerMinorBoolArray(reader, major); // 1818: established routes.
    reader.Fixed(major * 12u, 4); // 1820-1831: twelve int[22] arrays.
    ReadPlayerMinorBoolArray(reader, major * 4u); // 1832-1835: four bool[22].
    ReadPlayerMinorBoolArray(reader, teams * 2u); // 1836-1837: two bool[80].

    // 1845-1850 writes one signed int count followed by that many quests in
    // each of the 22 lists. FStaticVector's capacity estimate of five (h:19,
    // 150) is not a count limit, and its generic stream codec is not called.
    // Charge only declared quest rows, not the unprefixed 22 outer lists or
    // fixed C-array elements, to the Reader's array/aggregate record budgets.
    for (std::size_t player = 0; player < major; ++player) {
        const auto quests = reader.SignedCount(PlayerMinorCivQuestBytes);
        for (std::uint32_t i = 0; i < quests; ++i)
            ReadPlayerMinorCivQuest(reader);
    }
    reader.Bool(); // 1854: disable notifications.
}

} // namespace RetailStateDetail
} // namespace ZeroSisHost
