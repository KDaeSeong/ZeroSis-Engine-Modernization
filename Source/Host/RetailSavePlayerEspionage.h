#pragma once

// Source-exact latest BNW Player espionage framing. This reads inflated bytes
// only; it does not resolve rules, allocate spies, or restore SDK state.
#include "RetailSaveStateWire.h"
#include <cstddef>
#include <cstdint>

namespace ZeroSisHost {
namespace RetailStateDetail {

constexpr std::size_t PlayerEspionageSpyMinimumBytes = 30u;
constexpr std::size_t PlayerEspionageMinimumBytes = 216u;
constexpr std::size_t PlayerEspionageAIMinimumBytes = 37u;

inline void ReadPlayerEspionageSpy(Reader& reader) {
    // Original CvEspionageClasses.cpp:46-93. Latest Spy v1 writes six int32
    // fields, including explicitly int-cast rank/state, then two bools.
    // Spy v0 omits IsDiplomat and is intentionally not a supported branch.
    reader.Version(1);
    reader.Fixed(6, 4);
    reader.Bool(); // Is diplomat.
    reader.Bool(); // Evaluate reassignment, saved even though Read forces true.
}

inline void ReadPlayerEspionage(Reader& reader) {
    // Original CvEspionageClasses.cpp:3600-3791 and header:88-120. The latest
    // enclosing version is zero; it is independent of the nested Spy v1.
    reader.Version(0);
    const auto spies = reader.SignedCount(PlayerEspionageSpyMinimumBytes);
    for (std::uint32_t i = 0; i < spies; ++i) ReadPlayerEspionageSpy(reader);

    // FStaticVector::size() is uint32, but these two original reader counts
    // are int32. The vector's inline capacity eight is not a wire maximum.
    const auto names = reader.SignedCount(4);
    reader.Fixed(names, 4); // Spy name indexes, not strings.
    reader.I32(); // Current spy-name-order index.

    const auto civilizations = reader.Count(4);
    for (std::uint32_t i = 0; i < civilizations; ++i) {
        const auto techs = reader.Count(4);
        reader.Fixed(techs, 4); // Direct TechTypes int32 values, not hashes.
    }
    const auto stealCounts = reader.Count(4);
    reader.Fixed(stealCounts, 4);

    // Both dimension words are explicitly emitted as MAX_MAJOR_CIVS (22)
    // by the original writer. No catalog size or external profile is inferred.
    const auto maximumCosts = reader.SignedCount(4);
    if (maximumCosts != 22)
        reader.Fail(RetailStateErrorCode::InvalidValue,
            "BNW espionage maximum-cost dimension must be 22");
    reader.Fixed(maximumCosts, 4);
    const auto heistCivilizations = reader.SignedCount(4);
    if (heistCivilizations != 22)
        reader.Fail(RetailStateErrorCode::InvalidValue,
            "BNW espionage heist dimension must be 22");
    for (std::uint32_t i = 0; i < heistCivilizations; ++i) {
        const auto heists = reader.SignedCount(8);
        reader.Fixed(heists, 8); // Two int32 coordinates per HeistLocation.
    }

    const auto spyMessages = reader.SignedCount(20);
    reader.Fixed(spyMessages, 20); // X, Y, PlayerTypes, spy result, TechTypes.
    const auto intrigueMessages = reader.SignedCount(41);
    for (std::uint32_t i = 0; i < intrigueMessages; ++i) {
        // Discoverer/source/target, BuildingTypes, int-cast ProjectTypes,
        // intrigue type, turn and city X/Y. All nine are four-byte fields.
        reader.Fixed(9, 4);
        reader.String();
        reader.Bool(); // Shared.
    }
}

inline void ReadPlayerEspionageAI(Reader& reader) {
    // Original CvEspionageClasses.cpp:5491-5604. Seven independently counted
    // FStaticVector<int> arrays; their inline capacities add no wire bytes.
    reader.Version(0);
    for (unsigned array = 0; array < 7; ++array) {
        const auto count = reader.Count(4);
        reader.Fixed(count, 4);
    }
    reader.Bool(); // UN countdown started.
    reader.I32(); // Turn espionage started.
}

} // namespace RetailStateDetail
} // namespace ZeroSisHost
