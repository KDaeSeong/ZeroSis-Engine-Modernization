#pragma once

// A caller-declared contiguous BNW player block. The original retail top-level
// writer is unavailable: this explicit profile is not inferred from bytes.
#include "RetailSavePlayer.h"
#include <array>
#include <cstddef>
#include <cstdint>

namespace ZeroSisHost {

enum class RetailPlayerBlockProfile {
    Bnw64InSlotOrder
};

struct RetailSavePlayersProfile {
    RetailSavePlayersProfile(RetailPlayerBlockProfile block, const RetailSavePlayerWireProfile& player)
        : blockProfile(block), playerProfile(player) {}
    RetailPlayerBlockProfile blockProfile;
    RetailSavePlayerWireProfile playerProfile;
};

struct RetailSavePlayerSlotInspection {
    RetailInflatedSpan whole;
    std::int32_t playerId = -1;
    std::uint32_t cityCount = 0, unitCount = 0, armyCount = 0, operationCount = 0;
    std::size_t arrayRecords = 0;
};

struct RetailSavePlayersInspection {
    std::array<RetailSavePlayerSlotInspection, 64> players{};
    RetailInflatedSpan whole;
    std::size_t nextInflatedOffset = 0, arrayRecords = 0;
    std::uint32_t playerCount = 0;
    std::size_t cityCount = 0, unitCount = 0, armyCount = 0, operationCount = 0;
    bool allExpectedPlayersWireFramed = false;
    bool objectReferencesVerified = false;
    bool completeSaveVerified = false;
    bool rulesetCompatibilityVerified = false;
    bool restoreApproved = false;
};

class RetailSavePlayers {
public:
    static RetailSavePlayersInspection InspectAt(const unsigned char* data, std::size_t size,
        std::size_t start, const RetailSavePlayersProfile& profile,
        const RetailSaveStateLimits& limits = RetailSaveStateLimits{}) {
        if (profile.blockProfile != RetailPlayerBlockProfile::Bnw64InSlotOrder)
            throw RetailStateError(RetailStateErrorCode::UnsupportedProfile, start,
                "Unsupported BNW contiguous player-block profile");
        RetailSavePlayersInspection result;
        auto remaining = limits;
        auto cursor = start;
        for (std::uint32_t slot = 0; slot < 64; ++slot) {
            const auto player = RetailSavePlayer::InspectAt(data, size, cursor, profile.playerProfile, remaining);
            if (player.playerId != static_cast<std::int32_t>(slot))
                throw RetailStateError(RetailStateErrorCode::InvalidValue, cursor,
                    "Player ID differs from caller-declared BNW slot order");
            if (player.whole.offset != cursor || player.nextInflatedOffset <= cursor ||
                    player.nextInflatedOffset > size || !player.completePlayerWireFramed)
                throw RetailStateError(RetailStateErrorCode::InvalidValue, cursor,
                    "Noncontiguous BNW player-block boundary");
            if (player.arrayRecords > remaining.maxTotalRecords)
                throw RetailStateError(RetailStateErrorCode::TotalRecordLimit, cursor,
                    "BNW players exceed their shared record budget");
            remaining.maxTotalRecords -= player.arrayRecords;
            result.arrayRecords += player.arrayRecords;
            auto& summary = result.players[slot];
            summary.whole = player.whole;
            summary.playerId = player.playerId;
            summary.cityCount = player.cities.pool.liveCount;
            summary.unitCount = player.units.pool.liveCount;
            summary.armyCount = player.ending.armyPool.liveCount;
            summary.operationCount = player.ending.operations.declaredCount;
            summary.arrayRecords = player.arrayRecords;
            result.cityCount += summary.cityCount;
            result.unitCount += summary.unitCount;
            result.armyCount += summary.armyCount;
            result.operationCount += summary.operationCount;
            cursor = player.nextInflatedOffset;
            ++result.playerCount;
        }
        // Counted nested records share one budget. There is no serialized outer
        // player count to consume or charge again; the explicit profile fixes 64.
        result.whole = {start, cursor - start};
        result.nextInflatedOffset = cursor;
        result.allExpectedPlayersWireFramed = true;
        return result;
    }
};

} // namespace ZeroSisHost
