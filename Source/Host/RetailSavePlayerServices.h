#pragma once

// Latest copied BNW Player services after TradeAI, before the yield arrays.
// These functions frame inflated bytes only: no SDK state, lookup, allocation,
// file access or restore approval. References use SDK_BNW_Original.
#include "RetailSaveStateWire.h"
#include <cstddef>
#include <cstdint>

namespace ZeroSisHost {
namespace RetailStateDetail {

constexpr std::size_t PlayerServicesLeagueMinimumBytes = 8u;
constexpr std::size_t PlayerServicesCultureMinimumBytes = 238u;
constexpr std::size_t PlayerServicesNotificationsMinimumBytes = 4120u;
constexpr std::size_t PlayerServicesTreasuryMinimumBytes = 52u;

inline void ReadPlayerLeagueAI(Reader& reader) {
    // CvVotingClasses.cpp:7394-7435, latest Write version2. The unsigned
    // FStaticVector size is an explicit count; its estimate4 is not a wire cap.
    // Each row is PlayerTypes(int32), three int32 values and one bool byte.
    reader.Version(2);
    const auto commitments = reader.Count(17);
    for (std::uint32_t i = 0; i < commitments; ++i) {
        reader.Fixed(4, 4);
        reader.Bool();
    }
}

inline void ReadPlayerCulture(Reader& reader) {
    // CvCultureClasses.cpp:3820-3962. Latest version6 is supported here; older
    // reader branches1-5 have different extents and are not inferred from data.
    reader.Version(6);
    const auto digPlots = reader.SignedCount(8);
    reader.Fixed(digPlots, 8); // Signed X/Y, not pointers or map lookups.
    reader.I32(); // Last-turn lifetime culture.

    // The current writer explicitly emits MAX_MAJOR_CIVS=22 followed by two
    // interleaved int32 columns. Unlike a ruleset catalog width, this size is
    // on the wire. Other counts are outside this latest BNW writer profile;
    // the SDK reader's unchecked indexing does not authorize larger arrays.
    const auto influences = reader.SignedCount(8);
    if (influences != 22u)
        reader.Fail(RetailStateErrorCode::InvalidValue,
            "BNW Culture influence count differs from the current 22-player writer");
    reader.Fixed(influences, 8);
    reader.Bool(); // Reported two civilizations away.
    reader.Bool(); // Reported one civilization away.
    reader.Fixed(3, 4); // Opinion enum, preferred ideology enum, unhappiness.
    reader.String(); // Opinion tooltip; counted bytes preserve NUL and UTF-8.
    reader.String(); // Unhappiness tooltip (version5 and later).
    reader.Fixed(2, 4); // Biggest-influence PlayerTypes and ideology-switch turn.
    reader.Fixed(4, 4); // Swappable writing/art/artifact/music indexes.
}

inline void ReadPlayerNotifications(Reader& reader) {
    // CvPlayer.cpp:22611-22619 writes an OUTER presence bool. The caller owns
    // that byte and calls this function only when true. It is not part of the
    // Notifications span. CvNotifications.cpp:20 fixes MAX_NOTIFICATIONS=100.
    // Read/Write:264-305 always process all100 slots, including inactive ones;
    // begin/end indexes are not an array count and cannot shorten the stream.
    reader.Version(2);
    reader.Fixed(4, 4); // PlayerTypes, current lookup index, begin index, end index.
    for (unsigned slot = 0; slot < 100; ++slot) {
        // CvNotifications.cpp:169-207. No per-slot version, padding or count.
        // NotificationTypes is a raw32-bit hash enum, including0/FFFFFFFF;
        // it is not a type-array hash with conditional payload omission.
        reader.U32();
        reader.String(); // Message.
        reader.String(); // Summary.
        reader.Fixed(6, 4); // X/Y, game data, extra game data, turn, lookup index.
        reader.Bool(); // Dismissed.
        reader.U32(); // PlayerTypes is LAST on the wire, unlike member order.
        // NeedsBroadcast and WaitExtraTurn are explicitly not serialized.
    }
    // The100 slots are a fixed source layout, not a declared dynamic record
    // count. Their bytes/prefix and200 strings are bounded by Reader limits;
    // they do not add an invented count to Reader::Records().
}

inline void ReadPlayerTreasury(Reader& reader) {
    // CvTreasury.cpp:1002-1045. Nine int32 scalars precede two generic
    // std::vector<int> streams; lifetime gross gold follows both vectors.
    // FStlContainerSerialization.h:65-97,197-201,224-234 uses a native size_type
    // on the copied32-bit SDK; the existing x64 port fixes that count to uint32.
    // Neither vector has a record version or a nullable-catalog branch.
    reader.Version(1);
    reader.Fixed(9, 4);
    const auto balances = reader.Count(4);
    reader.Fixed(balances, 4);
    const auto changes = reader.Count(4);
    reader.Fixed(changes, 4);
    reader.I32(); // Lifetime gross gold income.
}

} // namespace RetailStateDetail
} // namespace ZeroSisHost
