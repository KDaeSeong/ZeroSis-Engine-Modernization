#pragma once

// Four nested states called by original CvPlayer.cpp:22585-22588.
// References below use SDK_BNW_Original; the corresponding port Write bodies
// are identical. This does not frame an entire Player or verify its ruleset.
#include "RetailSaveStateWire.h"
#include <cstddef>
#include <cstdint>

namespace ZeroSisHost {
namespace RetailStateDetail {

// Zero-length tables give structural lower bounds, not valid game profiles.
constexpr std::size_t PlayerAiEarlyPoliciesMinimumBytes = 60u;
constexpr std::size_t PlayerAiEarlyEconomicMinimumBytes = 65u;
constexpr std::size_t PlayerAiEarlyCitySpecializationMinimumBytes = 26u;
// This bound requires the initialized-building-catalog profile described below.
constexpr std::size_t PlayerAiEarlyWonderMinimumBytes = 12u;

inline void ReadPlayerPolicies(Reader& reader) {
    // CvPolicyClasses.cpp:2179-2214. Six unsigned-count hashed bool tables:
    // zero hashes omit their bool; all nonzero hashes retain one strict bool.
    reader.Version(2);
    for (unsigned table = 0; table < 6; ++table) {
        const auto entries = reader.Count(4);
        for (std::uint32_t i = 0; i < entries; ++i)
            if (reader.U32() != 0) reader.Bool();
    }
    const auto chosenBranches = reader.Count(4);
    reader.Fixed(chosenBranches, 4); // Hashes only, including zero hashes.
    reader.I32(); // Extra policy branches; not a following array length.
    reader.Fixed(3, 4); // Three standalone branch-picked hashes.

    // CvPolicyAI.cpp:87-104. This writer ALWAYS emits hash + int32 weight,
    // including a weight after a zero hash; it is not a generic hashed array.
    reader.Version(1);
    const auto policyWeights = reader.Count(8);
    reader.Fixed(policyWeights, 8);

    // FlavorRecipient has no separate serialized base header here. Its data
    // is just a signed int count and that many raw int32 flavor values.
    const auto flavors = reader.SignedCount(4);
    reader.Fixed(flavors, 4);
}

inline void ReadPlayerEconomicAI(Reader& reader) {
    // CvEconomicAI.cpp:439-479. One signed count owns two uncounted columns.
    reader.Version(1);
    const auto strategies = reader.SignedCount(5);
    for (std::uint32_t i = 0; i < strategies; ++i) reader.Bool();
    reader.Fixed(strategies, 4); // Turn strategy adopted, signed int32.
    reader.Fixed(6, 4); // NUM_YIELD_TYPES=6 raw uint32 yields.
    reader.Bool(); // Exploration plots dirty.

    // FFastVector::size() is unsigned int in both ABIs (FFastVector.h:165),
    // unlike std::vector::size(). The reader's storage clamp still consumes
    // every declared row; it is not an on-wire maximum or another count.
    const auto exploration = reader.Count(8);
    reader.Fixed(exploration, 8); // Plot ID and rating, two int32s.
    const auto goodyHuts = reader.Count(8);
    reader.Fixed(goodyHuts, 8); // Plot ID and assigned unit ID only.
    reader.Fixed(5, 4); // Recon enums, disbands, last-worker turn, visible sites.

    // Explicit signed size, then CvPurchaseRequest's three int32 fields
    // (CvEconomicAI.cpp:2695-2700). No version or native structure padding.
    const auto requests = reader.SignedCount(12);
    reader.Fixed(requests, 12);
}

inline void ReadPlayerCitySpecializationAI(Reader& reader) {
    // CvCitySpecializationAI.cpp:287-299. Latest version adds last-turn int32.
    reader.Version(2);
    reader.Bool(); // Specializations dirty.
    reader.Bool(); // Interrupt wonders.
    reader.Fixed(5, 4); // Specialization/building enums, city ID, weight, turn.
}

// Requires CvPlayer's initialized-building-catalog profile: CvPlayer.cpp:1119
// passes GC.GetGameBuildings() to Init; CvWonderProductionAI.cpp:50 requires
// that catalog. Write:134-154 emits its count only when m_pBuildings is nonnull.
// There is NO presence flag for the null branch. This API supports the
// initialized catalog form only and never infers a null branch from bytes.
inline void ReadPlayerWonderProductionAI(Reader& reader) {
    // CvWonderProductionAI.cpp:124-154. No extra FlavorRecipient base version.
    reader.Version(1);
    const auto flavors = reader.SignedCount(4);
    reader.Fixed(flavors, 4);
    const auto buildings = reader.SignedCount(4);
    for (std::uint32_t i = 0; i < buildings; ++i)
        if (reader.U32() != 0) reader.I32(); // Zero omits weight; other hashes do not.
}

} // namespace RetailStateDetail
} // namespace ZeroSisHost
