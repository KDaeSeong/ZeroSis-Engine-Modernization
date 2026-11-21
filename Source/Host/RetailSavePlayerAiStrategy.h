#pragma once

// Original BNW CvPlayer.cpp:22589-22590 calls these two AI writers in
// order. This header only frames those records in caller-owned inflated
// bytes. DiplomacyAI and all following Player state are outside its scope;
// it does not establish retail outer ordering or approve SDK restoration.
#include "RetailSaveStateWire.h"
#include <cstddef>
#include <cstdint>

namespace ZeroSisHost {
namespace RetailStateDetail {

// Original CvMilitaryAI.cpp:398-415. The zero-strategy lower bound is
// 4-byte version + three int32s + signed count + four arrays of 63 int32s.
// Each declared strategy adds one bool byte and one int32, in two columns.
constexpr std::size_t PlayerMilitaryAIMinimumBytes = 1028u;
constexpr std::size_t PlayerMilitaryAICivilizationPlayers = 63u;

inline void ReadPlayerMilitaryAI(Reader& input) {
    input.Version(1);
    input.I32(); // Total threat weight.
    input.I32(); // ArmyType is explicitly cast to int in the original writer.
    input.I32(); // Number of times operation builds were skipped.
    const auto strategies = input.SignedCount(5);
    // FDataStream.h:501-510 ArrayWrapper writes elements only, without an
    // extra count. The bool and adoption-turn arrays share the explicit count.
    for (std::uint32_t i = 0; i < strategies; ++i) input.Bool();
    input.Fixed(strategies, 4);

    // CvDLLUtilDefines.h:19-28 distinguishes MAX_CIV_PLAYERS=63 from
    // MAX_PLAYERS=64 and REALLY_MAX_PLAYERS=80. Each of these four writers
    // uses exactly 63 values; storage capacity does not change the wire.
    input.Fixed(PlayerMilitaryAICivilizationPlayers, 4); // Last war state.
    input.Fixed(PlayerMilitaryAICivilizationPlayers, 4); // Last military threat.
    input.Fixed(PlayerMilitaryAICivilizationPlayers, 4); // Last military strength.
    input.Fixed(PlayerMilitaryAICivilizationPlayers, 4); // Last target value.
    // CvMilitaryTarget, CvArmyAI, temporary flavors and strings are not
    // written by this function; do not append their unrelated object layouts.
}

// Original CvGrandStrategyAI.cpp:220-233. The priority array has NO count
// prefix: its width comes from GetNumAIGrandStrategies(), not the save bytes.
// The zero-width lower bound is version + two int32s + two arrays of 22 ints.
constexpr std::size_t PlayerGrandStrategyAIMinimumBytes = 188u;
constexpr std::size_t PlayerGrandStrategyAIMajorPlayers = 22u;
constexpr std::uint32_t PlayerGrandStrategyAIProfileLimit = 4096u;

inline void ReadPlayerGrandStrategyAI(Reader& input, std::uint32_t grandStrategyCount) {
    // 4096 is this inspector's supported profile budget, not an SDK constant.
    // Zero is structurally allowed. No overload/default may silently assume
    // the base game's count, infer it from following bytes or verify a ruleset.
    if (grandStrategyCount > PlayerGrandStrategyAIProfileLimit)
        input.Fail(RetailStateErrorCode::UnsupportedProfile,
            "BNW grand-strategy width exceeds supported profile budget");
    input.Version(1);
    input.I32(); // Turns since the active strategy was set.
    input.I32(); // AIGrandStrategyTypes uses the int32 scalar stream overload.
    input.Fixed(grandStrategyCount, 4); // Priorities, no length on the wire.
    input.Fixed(PlayerGrandStrategyAIMajorPlayers, 4); // Other players' strategy guesses.
    input.Fixed(PlayerGrandStrategyAIMajorPlayers, 4); // Guess confidence values.
    // Profile/fixed columns are bounded by input and prefix bytes, without
    // charging nonexistent count fields as dynamic on-wire record rows.
}

} // namespace RetailStateDetail
} // namespace ZeroSisHost
