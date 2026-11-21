#pragma once

// Current Player v16 suffix from m_armyAIs through the CvPlayerAI v1 trailer.
// This observes bytes only and does not create SDK objects or approve restore.
#include "RetailSaveFreeList.h"
#include "RetailSavePlayerOperations.h"
#include "RetailSavePlayerEndFields.h"
#include <cstddef>

namespace ZeroSisHost {

struct RetailSavePlayerEndProfile {
    RetailSavePlayerEndProfile(RetailPlayerOperationsProfile operations,
        RetailPlayerEndWriterProfile fields) : operationProfile(operations), fieldProfile(fields) {}
    RetailPlayerOperationsProfile operationProfile;
    RetailPlayerEndWriterProfile fieldProfile;
};

struct RetailSavePlayerEndInspection {
    RetailStateDetail::RetailFreeListHeader armyPool;
    RetailInflatedSpan armyObjects, armyWhole, playerAITrailer, whole;
    RetailSaveArmyAIInspection firstArmy, lastArmy;
    RetailSavePlayerOperationsInspection operations;
    RetailSavePlayerEndFieldsInspection fields;
    std::size_t nextInflatedOffset = 0, arrayRecords = 0;
    bool completePlayerVerified = false;
    bool completeSaveVerified = false;
    bool rulesetCompatibilityVerified = false;
    bool restoreApproved = false;
};

namespace RetailStateDetail {
constexpr std::size_t PlayerEndMinimumBytes = 144u;

inline RetailSavePlayerEndInspection ReadPlayerEnd(Reader& input,
    const RetailSavePlayerEndProfile& profile) {
    if (profile.operationProfile != RetailPlayerOperationsProfile::BnwCurrentFactory20 ||
            profile.fieldProfile != RetailPlayerEndWriterProfile::Current16With64Players)
        input.Fail(RetailStateErrorCode::UnsupportedProfile, "Unsupported BNW Player suffix profile");
    RetailSavePlayerEndInspection result;
    const auto start = input.Pos(), records = input.Records();
    result.armyPool = ReadFreeListHeader(input);
    const auto objectsStart = input.Pos();
    for (std::uint32_t i = 0; i < result.armyPool.liveCount; ++i) {
        const auto army = ReadArmyAI(input);
        if (i == 0) result.firstArmy = army;
        result.lastArmy = army;
    }
    result.armyObjects = input.SpanFrom(objectsStart);
    result.armyWhole = input.SpanFrom(start);
    result.operations = ReadPlayerOperations(input, profile.operationProfile);
    // The obsolete popup-count word exists only for base Player versions <=10.
    // The mandatory current-v16 profile neither guesses nor consumes it.
    result.fields = ReadPlayerFieldsAfterOperations(input, profile.fieldProfile);
    const auto trailer = input.Pos();
    // CvPlayerAI.cpp:685-706 delegates to base Read/Write, then one uint32 v1.
    // Ending at achievements would leave this real serialized word unread.
    input.Version(1);
    result.playerAITrailer = input.SpanFrom(trailer);
    result.whole = input.SpanFrom(start);
    result.nextInflatedOffset = input.Pos();
    result.arrayRecords = input.Records() - records;
    return result;
}
} // namespace RetailStateDetail

class RetailSavePlayerEnd {
public:
    static RetailSavePlayerEndInspection InspectAt(const unsigned char* data, std::size_t size,
        std::size_t start, const RetailSavePlayerEndProfile& profile,
        const RetailSaveStateLimits& limits = RetailSaveStateLimits{}) {
        RetailStateDetail::Reader input(data, size, limits);
        input.Skip(start);
        return RetailStateDetail::ReadPlayerEnd(input, profile);
    }
};

} // namespace ZeroSisHost
