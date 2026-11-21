#pragma once

// Portable current BNW Unit v9 framing. No SDK state, files or graphics access.
#include "RetailSaveUnitArchive.h"
#include "RetailSaveUnitServices.h"
#include <cstddef>
#include <cstdint>

namespace ZeroSisHost {

enum class RetailUnitWriterProfile {
    // v9 Read always consumes a GreatWork hash word. A successful writer emits
    // either that hash or zero. Its failed database-lookup branch omits the word
    // and is not a supported, inferred, or recoverable alternative layout here.
    Bnw9CompleteGreatWorkHashWord
};

struct RetailSaveUnitInspection {
    RetailInflatedSpan version, typeAndLastMove, promotions, explicitState;
    RetailInflatedSpan religion, greatWorkAndTourism, missions, whole;
    RetailSaveUnitArchiveInspection archive;
    RetailUnitPromotionSummary promotionSummary;
    std::uint32_t unitTypeHash = 0, greatWorkHash = 0, missionCount = 0;
    std::int32_t mapLayer = 0;
    std::size_t nextInflatedOffset = 0, arrayRecords = 0;
    bool objectReferencesVerified = false;
    bool completePlayerVerified = false;
    bool completeSaveVerified = false;
    bool rulesetCompatibilityVerified = false;
    bool restoreApproved = false;
};

namespace RetailStateDetail {

constexpr std::size_t UnitMinimumBytes = 768u;

inline void ValidateUnitProfile(Reader& input, RetailUnitWriterProfile profile) {
    if (profile != RetailUnitWriterProfile::Bnw9CompleteGreatWorkHashWord)
        input.Fail(RetailStateErrorCode::UnsupportedProfile, "Unsupported BNW Unit wire profile");
}

inline RetailSaveUnitInspection ReadUnit(Reader& input, RetailUnitWriterProfile profile) {
    ValidateUnitProfile(input, profile);
    RetailSaveUnitInspection result;
    const auto start = input.Pos(), records = input.Records();
    input.Version(9);
    result.version = input.SpanFrom(start);
    result.archive = ReadUnitArchive(input);
    auto begin = input.Pos();
    result.unitTypeHash = input.U32(); // A scalar hash, not an optional record.
    input.I32(); // Last move turn.
    result.typeAndLastMove = input.SpanFrom(begin);
    begin = input.Pos();
    result.promotionSummary = ReadUnitPromotions(input);
    result.promotions = input.SpanFrom(begin);
    begin = input.Pos();
    // Combat, transport and mission-AI IDInfo: PlayerTypes + int32, no padding.
    input.Fixed(6, 4);
    const auto domains = input.Count(4); // std::vector<int>, not a fixed domain array.
    input.Fixed(domains, 4);
    input.I32(); // Ever selected count.
    result.mapLayer = input.I32();
    input.I32(); // Goody huts popped, present in latest v9.
    input.Bool(); // Ignore danger wakeup; not an automatic archive member.
    // CvUnit.cpp:17903-17932. All 28 are int32, including CanHeavyCharge,
    // IgnoreGreatGeneralBenefit and IgnoreZOC; their meanings do not change width.
    input.Fixed(28, 4);
    input.String(); // Current display name, additional to two archive strings.
    input.I32(); // Scenario data.
    result.explicitState = input.SpanFrom(begin);
    begin = input.Pos(); ReadUnitReligion(input); result.religion = input.SpanFrom(begin);
    begin = input.Pos();
    result.greatWorkHash = input.U32();
    input.I32(); // Tourism blast strength.
    result.greatWorkAndTourism = input.SpanFrom(begin);
    begin = input.Pos();
    // MissionQueue::getLength() returns int, while Read uses UINT. A negative
    // signed writer count is invalid. The capacity estimate 12 is not a limit.
    // Each row is MissionTypes, data1, data2, flags, push turn: five raw words.
    result.missionCount = input.SignedCount(20);
    input.Fixed(result.missionCount, 20);
    result.missions = input.SpanFrom(begin);
    result.whole = input.SpanFrom(start);
    result.nextInflatedOffset = input.Pos();
    result.arrayRecords = input.Records() - records;
    return result;
}

} // namespace RetailStateDetail

class RetailSaveUnit {
public:
    static RetailSaveUnitInspection InspectAt(const unsigned char* data, std::size_t size,
        std::size_t start, RetailUnitWriterProfile profile,
        const RetailSaveStateLimits& limits = RetailSaveStateLimits{}) {
        RetailStateDetail::Reader input(data, size, limits);
        input.Skip(start);
        return RetailStateDetail::ReadUnit(input, profile);
    }
};

} // namespace ZeroSisHost
