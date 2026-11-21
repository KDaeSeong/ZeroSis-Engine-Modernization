#pragma once

// Original BNW CvPlayer::Write v16 through the two final bool vectors,
// immediately before m_pPlayerPolicies->Write (original CvPlayer.cpp:22585).
// This is only a Player prefix, not full Player, CvPlayerAI or retail-save
// support. It frames caller-owned inflated bytes without SDK or file I/O.
#include "RetailSaveStateWire.h"
#include <cstddef>
#include <cstdint>

namespace ZeroSisHost {
namespace RetailStateDetail {

// Original CvPlayer.cpp:22297-22529: the first vector starts at +872 and
// the serialized PlayerTypes ID starts at +864. The rest contains 26 int
// vectors, nine hash/int arrays, two bool vectors and two narrow strings.
// Their empty count/length words add 156 bytes to the fixed prefix.
constexpr std::size_t PlayerFrontMinimumBytes = 1028u;

inline void ReadPlayerFrontIntVector(Reader& input) {
    // FAutoVariable::save writes only its value. Generic STL sequence counts
    // are u32 in original Win32 and in the existing checked x64 port.
    const auto count = input.Count(4);
    input.Fixed(count, 4);
}

inline void ReadPlayerFrontBoolVector(Reader& input) {
    // FStlContainerSerialization iterates vector<bool> as scalar bools;
    // these are one canonical byte per value, not packed native bits.
    const auto count = input.Count(1);
    for (std::uint32_t i = 0; i < count; ++i) input.Bool();
}

inline std::int32_t ReadPlayerFront(Reader& input) {
    // Original CvPlayer.cpp:65,22297-22507. There are 209 four-byte scalar
    // values before the first bool: 208 ints and one FaithPurchaseTypes enum.
    // Signed counters and absent starting-coordinate sentinels are preserved.
    input.Version(16);
    input.Fixed(209, 4);

    // Original CvPlayer.cpp:22509-22529. Do not move the four-byte values
    // across these bool groups or serialize the native object layout.
    for (unsigned i = 0; i < 11; ++i) input.Bool();
    input.I32(); // Number of cities founded.
    input.Bool(); // Strike.
    input.Bool(); // Cramped.
    input.Bool(); // Lost capital.
    input.I32(); // Conqueror: PlayerTypes, not a one-byte GameTypes value.
    input.Bool(); // Adopted state religion.
    input.Bool(); // Allied great-person bias applied.
    const auto playerId = input.I32(); // Relative offset +864.
    input.I32(); // Personality: LeaderHeadTypes, also four bytes.

    // Original CvPlayer.cpp:22531-22546. First count is at relative +872.
    ReadPlayerFrontIntVector(input); // City yield change.
    ReadPlayerFrontIntVector(input); // Coastal city yield change.
    ReadPlayerFrontIntVector(input); // Capital yield change.
    ReadPlayerFrontIntVector(input); // Capital yield change per population.
    ReadPlayerFrontIntVector(input); // Sea-plot yield.
    ReadPlayerFrontIntVector(input); // Yield-rate modifier.
    ReadPlayerFrontIntVector(input); // Capital yield-rate modifier.
    ReadPlayerFrontIntVector(input); // Great-work yield change.
    ReadPlayerFrontIntVector(input); // Extra yield threshold.
    ReadPlayerFrontIntVector(input); // Specialist extra yield.
    ReadPlayerFrontIntVector(input); // Proximity to player.
    ReadPlayerFrontIntVector(input); // Research-agreement counter.
    ReadPlayerFrontIntVector(input); // Incoming unit types.
    ReadPlayerFrontIntVector(input); // Incoming unit countdowns.
    ReadPlayerFrontIntVector(input); // Minor friendship anchors.
    ReadPlayerFrontIntVector(input); // Siphoned luxury count.

    // Original CvPlayer.h:1816-1817 and CvString.h:20: both fields are
    // FAutoVariable<CvString>, and CvString derives from std::string.
    // Each uses a four-byte byte length and that many char bytes, without
    // an added NUL, optional-presence bool or native string-object payload.
    input.String(); // Religion key.
    input.String(); // Script data.

    // Original CvPlayer.cpp:22554-22560. The helper writes a u32 row count,
    // then each hash; only zero omits its int32. Unknown nonzero hashes
    // still have values, so no ruleset lookup is needed for this framing.
    input.Hashes(4); // Resource used.
    input.Hashes(4); // Resource total.
    input.Hashes(4); // Resources gifted to minors.
    input.Hashes(4); // Resource exports.
    input.Hashes(4); // Resource imports.
    input.Hashes(4); // Resources from minors.
    input.Hashes(4); // Resources siphoned.

    // Original CvPlayer.cpp:22562-22576. Improvement count here is a plain
    // int vector, unlike the hashed ImprovementArrayHelpers used elsewhere.
    ReadPlayerFrontIntVector(input); // Improvement count.
    input.Hashes(4); // Free-building count.
    input.Hashes(4); // Free-promotion count.
    ReadPlayerFrontIntVector(input); // Unit-combat production modifiers.
    ReadPlayerFrontIntVector(input); // Unit-combat free experience.
    ReadPlayerFrontIntVector(input); // Unit-class count.
    ReadPlayerFrontIntVector(input); // Unit-class making.
    ReadPlayerFrontIntVector(input); // Building-class count.
    ReadPlayerFrontIntVector(input); // Building-class making.
    ReadPlayerFrontIntVector(input); // Project making.
    ReadPlayerFrontIntVector(input); // Hurry count.
    ReadPlayerFrontIntVector(input); // Hurry modifier.

    // Original CvPlayer.cpp:22581-22583. The next unread bytes belong to
    // PlayerPolicies; its nested version is deliberately not consumed here.
    ReadPlayerFrontBoolVector(input); // Loyal member.
    ReadPlayerFrontBoolVector(input); // Gets science from player.
    return playerId;
}

} // namespace RetailStateDetail
} // namespace ZeroSisHost
