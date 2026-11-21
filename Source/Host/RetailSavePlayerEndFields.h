#pragma once

// Allocation-free framing for CvArmyAI v1 and the fields after CvPlayer's
// polymorphic operations. No SDK, file, native-runtime or restore calls occur.
#include "RetailSaveStateWire.h"
#include <cstddef>
#include <cstdint>

namespace ZeroSisHost {

// This explicit writer profile excludes the old popup queue read at Player
// versions <= 10. The supported original/current Player writer version is 16.
enum class RetailPlayerEndWriterProfile {
    Current16With64Players
};

struct RetailSaveArmyAIInspection {
    std::int32_t id = -1, owner = -1;
    std::uint32_t slotCount = 0;
    RetailInflatedSpan whole;
    std::size_t nextInflatedOffset = 0, arrayRecords = 0;
};

struct RetailSavePlayerEndFieldsInspection {
    RetailInflatedSpan replayNames, replayValues, votes, unitCosts, plots;
    RetailInflatedSpan rushAndImprovements, everConquered, embarkedGraphic, achievements;
    RetailInflatedSpan whole;
    std::uint32_t replayDataSets = 0, replayValueDataSets = 0;
    std::uint32_t voteCount = 0, unitCostCount = 0, plotCount = 0, everCount = 0;
    std::int32_t rushHurryCount = 0, totalImprovementsBuilt = 0;
    std::size_t nextInflatedOffset = 0, arrayRecords = 0;
};

namespace RetailStateDetail {

constexpr std::size_t ArmyAIMinimumBytes = 48u;
constexpr std::size_t ArmyFormationSlotBytes = 12u;
constexpr std::size_t PlayerFieldsAfterOperationsMinimumBytes = 112u;

inline RetailSaveArmyAIInspection ReadArmyAI(Reader& input) {
    // Original CvArmyAI.cpp:99-152, current:100-156. Version 1, ten four-byte
    // scalars, then a signed int32 slot count. Current writes only add checked
    // narrowing of that count; the original wire width and field order remain.
    const auto start = input.Pos();
    const auto records = input.Records();
    RetailSaveArmyAIInspection result;
    input.Version(1);
    result.id = input.I32();
    result.owner = input.I32(); // PlayerTypes uses its four-byte enum codec.
    input.Fixed(8, 4); // Current XY, goal XY, domain, formation, state, operation ID.
    result.slotCount = input.SignedCount(ArmyFormationSlotBytes);
    // CvArmyAI.h:64-66 and .cpp:859-872 (current:863-876): the member named
    // m_bStartedOnOperation is declared int, despite its bool accessors. Each
    // slot is int32 unit ID, int32 checkpoint turn, int32 Started, not a bool.
    input.Fixed(result.slotCount, ArmyFormationSlotBytes);
    result.whole = input.SpanFrom(start);
    result.nextInflatedOffset = input.Pos();
    result.arrayRecords = input.Records() - records;
    return result;
}

inline RetailSavePlayerEndFieldsInspection ReadPlayerFieldsAfterOperations(
    Reader& input, RetailPlayerEndWriterProfile profile) {
    if (profile != RetailPlayerEndWriterProfile::Current16With64Players)
        input.Fail(RetailStateErrorCode::UnsupportedProfile,
            "Unsupported BNW Player end writer profile");

    // Original CvPlayer.cpp:22651-22698, current:22713-22760. The sequence is
    // unchanged. FStlContainerSerialization writes Win32 size_t/size_type counts
    // as uint32; current uses checked unsigned-int narrowing to preserve them.
    // With everConquered count 64, empty variable collections give 112 bytes.
    // A count-zero everConquered structure would be 48 bytes, but is not emitted
    // by this writer profile and is deliberately rejected below.
    const auto start = input.Pos();
    const auto records = input.Records();
    RetailSavePlayerEndFieldsInspection result;

    const auto namesStart = input.Pos();
    result.replayDataSets = input.Count(4);
    for (std::uint32_t i = 0; i < result.replayDataSets; ++i)
        input.String(); // CvString: uint32 byte length, then unpadded bytes.
    result.replayNames = input.SpanFrom(namesStart);

    const auto valuesStart = input.Pos();
    result.replayValueDataSets = input.Count(4);
    for (std::uint32_t i = 0; i < result.replayValueDataSets; ++i) {
        // CvPlayer.h:70,1877-1878: vector<map<unsigned int,int>>. Generic STL
        // pairs are raw uint32 turn and int32 value; no type-hash codec applies.
        const auto turns = input.Count(8);
        input.Fixed(turns, 8);
    }
    result.replayValues = input.SpanFrom(valuesStart);

    const auto votesStart = input.Pos();
    // CvPlayer.h:1874: vector<pair<int,PlayerVoteTypes>>, both four-byte words.
    result.voteCount = input.Count(8);
    input.Fixed(result.voteCount, 8);
    result.votes = input.SpanFrom(votesStart);

    const auto costsStart = input.Pos();
    // CvPlayer.h:1875: vector<pair<UnitClassTypes,int>>, both four-byte words.
    result.unitCostCount = input.Count(8);
    input.Fixed(result.unitCostCount, 8);
    result.unitCosts = input.SpanFrom(costsStart);

    const auto plotsStart = input.Pos();
    // CvPlotsVector elements are int32. This custom signed count retains every
    // entry through the last non--1 plot; the map-sized omitted suffix is -1.
    result.plotCount = input.SignedCount(4);
    input.Fixed(result.plotCount, 4);
    result.plots = input.SpanFrom(plotsStart);

    const auto countersStart = input.Pos();
    // FAutoVariable<int,CvPlayer>::save writes just its underlying int32 value.
    result.rushHurryCount = input.I32();
    result.totalImprovementsBuilt = input.I32();
    result.rushAndImprovements = input.SpanFrom(countersStart);

    const auto conqueredStart = input.Pos();
    // CvPlayer.cpp:22687-22692 writes MAX_PLAYERS, which is 64 in this profile
    // (CvDLLUtilDefines.h:22,28). The in-memory DWORD[4] is not the wire format.
    result.everCount = input.SignedCount(1);
    if (result.everCount != 64u)
        input.Fail(RetailStateErrorCode::InvalidValue,
            "BNW Player end profile requires 64 conquest flags");
    for (std::uint32_t i = 0; i < result.everCount; ++i)
        input.Bool();
    result.everConquered = input.SpanFrom(conqueredStart);

    const auto graphicStart = input.Pos();
    input.String(); // m_strEmbarkedGraphicOverride, CvString byte codec.
    result.embarkedGraphic = input.SpanFrom(graphicStart);

    const auto achievementsStart = input.Pos();
    // CvAchievementUnlocker.cpp:399-413: signed int32 version 1, then two int32
    // progress values. Version(1) checks the same four bytes without conversion.
    input.Version(1);
    input.Fixed(2, 4);
    result.achievements = input.SpanFrom(achievementsStart);

    result.whole = input.SpanFrom(start);
    result.nextInflatedOffset = input.Pos();
    result.arrayRecords = input.Records() - records;
    // These are structural spans only. Owning-player identity, replay-map key
    // semantics, map references, ruleset compatibility and restore approval
    // require independent checks; no complete Player or Save is inferred here.
    return result;
}

} // namespace RetailStateDetail
} // namespace ZeroSisHost
