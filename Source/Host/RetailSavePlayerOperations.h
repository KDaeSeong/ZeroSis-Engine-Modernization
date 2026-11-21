#pragma once

// Portable framing for CvPlayer::m_AIOperations and its 20 BNW factory types.
// No SDK objects, heap allocation, file access or restore approval occurs here.
#include "RetailSaveStateWire.h"
#include <cstddef>
#include <cstdint>

namespace ZeroSisHost {

enum class RetailPlayerOperationsProfile {
    // Original x86 size_type counts and current checked uint32 counts have the
    // same wire width. Every base and derived writer emits version 1.
    BnwCurrentFactory20
};

struct RetailSavePlayerOperationsInspection {
    RetailInflatedSpan operations, firstOperation, lastOperation, whole;
    std::uint32_t declaredCount = 0, keyBodyIdMismatchCount = 0;
    std::int32_t firstMapKey = -1, firstType = -1, firstBodyId = -1;
    std::int32_t lastMapKey = -1, lastType = -1, lastBodyId = -1;
    std::size_t nextInflatedOffset = 0, arrayRecords = 0;
    bool objectReferencesVerified = false;
    bool completePlayerVerified = false;
    bool completeSaveVerified = false;
    bool rulesetCompatibilityVerified = false;
    bool restoreApproved = false;
};

namespace RetailStateDetail {

// Base version + 13 int32 fields + bool + three uint32 vector counts.
// Each real operation adds at least one derived version word. The Player map
// also writes its int32 key and int32 factory type before the virtual body.
constexpr std::size_t PlayerOperationBaseMinimumBytes = 69u;
constexpr std::size_t PlayerOperationMinimumBodyBytes = 73u;
constexpr std::size_t PlayerOperationMinimumRecordBytes = 81u;

inline void ValidatePlayerOperationsProfile(Reader& input,
        RetailPlayerOperationsProfile profile) {
    if (profile != RetailPlayerOperationsProfile::BnwCurrentFactory20)
        input.Fail(RetailStateErrorCode::UnsupportedProfile,
            "Unsupported BNW Player operations profile");
}

inline std::int32_t ReadPlayerOperationBase(Reader& input) {
    // Original/current CvAIOperation.cpp:1139-1188. Abort reason is not written.
    input.Version(1);
    const auto bodyId = input.I32();
    input.Fixed(4, 4); // Owner, enemy, state, default area.
    input.Bool(); // Replace losses with reinforcements.
    // Move type, target X/Y, muster X/Y, start-city X/Y, last turn moved.
    input.Fixed(8, 4);
    const auto armies = input.Count(4);
    input.Fixed(armies, 4);
    // OperationSlot writes operation ID, army ID and slot ID individually:
    // three int32 words, without a version word or object padding.
    const auto needed = input.Count(12);
    input.Fixed(needed, 12);
    const auto committed = input.Count(12);
    input.Fixed(committed, 12);
    return bodyId;
}

inline void ReadPlayerOperationDerived(Reader& input, std::int32_t type) {
    // CvAIOperation.h:21-45; CreateOperation in CvAIOperation.cpp:274-327.
    // EnemyTerritory has no serializer. Inherited serializers do not acquire
    // an extra version merely because another concrete class derives from them.
    switch (type) {
    case 0: // CityCloseDefense:4762-4780.
    case 1: // RapidResponse:4876-4894.
    case 2: // BasicCityAttack:2141-2159.
    case 5: // PillageEnemy:2582-2600.
    case 6: // SneakCityAttack and conditional QuickSneak inherit Basic.
    case 7: // SmallCityAttack inherits Basic.
    case 15: // CityStateAttack inherits Basic.
        input.Version(1);
        return;
    case 3: // DestroyBarbarianCamp:2314-2337.
        input.Version(1);
        input.Bool(); // Civilian rescue.
        input.I32(); // Unit to rescue.
        return;
    case 4: // FoundCity inherits Escorted.
    case 8: // MerchantDelegation inherits Escorted.
    case 12: // QuickColonize inherits FoundCity/Escorted.
    case 19: // ConcertTour inherits Escorted.
        // CvAIEscortedOperation:2867-2895.
        input.Version(1);
        input.Bool(); // Escorted.
        input.I32(); // UnitAITypes civilian type.
        input.I32(); // Target area.
        return;
    case 9: // NavalBombardment:3980-3998.
    case 10: // NavalSuperiority:4220-4238.
    case 18: // PureNavalCityAttack:4593-4611.
        input.Version(1); // NavalOperation:3751-3769.
        input.Version(1); // Concrete derived class.
        return;
    case 11: // Colonize is NavalEscortedOperation itself:5156-5178.
        input.Version(1);
        input.I32(); // UnitAITypes civilian type; initial area is not written.
        return;
    case 13: // NavalAttack:5382-5400.
    case 14: // NavalSneakAttack inherits NavalAttack.
    case 16: // NavalCityStateAttack inherits NavalAttack.
        input.Version(1); // NavalEscortedOperation:5156-5178.
        input.I32(); // UnitAITypes civilian type.
        input.Version(1); // NavalAttack.
        return;
    case 17: // NukeAttack:5549-5571.
        input.Version(1);
        input.I32(); // Best unit ID.
        return;
    default:
        input.Fail(RetailStateErrorCode::UnsupportedProfile,
            "Unsupported BNW AI operation type");
    }
}

inline RetailSavePlayerOperationsInspection ReadPlayerOperations(Reader& input,
        RetailPlayerOperationsProfile profile) {
    ValidatePlayerOperationsProfile(input, profile);
    const auto start = input.Pos(), records = input.Records();
    RetailSavePlayerOperationsInspection result;
    // CvPlayer.cpp:22204-22218/22638-22649 (current:22266-22280/22700-22711).
    result.declaredCount = input.Count(PlayerOperationMinimumRecordBytes);
    const auto operationsStart = input.Pos();
    for (std::uint32_t i = 0; i < result.declaredCount; ++i) {
        const auto recordStart = input.Pos();
        const auto mapKey = input.I32(), type = input.I32();
        if (type < 0 || type >= 20)
            input.Fail(RetailStateErrorCode::UnsupportedProfile,
                "Unsupported BNW AI operation type");
        const auto bodyId = ReadPlayerOperationBase(input);
        ReadPlayerOperationDerived(input, type);
        const auto span = input.SpanFrom(recordStart);
        if (i == 0) {
            result.firstMapKey = mapKey;
            result.firstType = type;
            result.firstBodyId = bodyId;
            result.firstOperation = span;
        }
        result.lastMapKey = mapKey;
        result.lastType = type;
        result.lastBodyId = bodyId;
        result.lastOperation = span;
        // The original Read discards the outer key and inserts by body ID.
        // Keep this difference observable without imposing an extra wire rule.
        if (mapKey != bodyId) ++result.keyBodyIdMismatchCount;
    }
    result.operations = input.SpanFrom(operationsStart);
    result.whole = input.SpanFrom(start);
    result.nextInflatedOffset = input.Pos();
    result.arrayRecords = input.Records() - records;
    return result;
}

} // namespace RetailStateDetail

class RetailSavePlayerOperations {
public:
    static RetailSavePlayerOperationsInspection InspectAt(const unsigned char* data,
            std::size_t size, std::size_t start, RetailPlayerOperationsProfile profile,
            const RetailSaveStateLimits& limits = RetailSaveStateLimits{}) {
        RetailStateDetail::Reader input(data, size, limits);
        input.Skip(start);
        return RetailStateDetail::ReadPlayerOperations(input, profile);
    }
};

} // namespace ZeroSisHost
