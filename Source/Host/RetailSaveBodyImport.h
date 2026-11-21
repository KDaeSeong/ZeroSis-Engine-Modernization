#pragma once

// Explicit preparation of an already inflated retail body before section packing.
// No SDK, file, compression, bundle identity, Pregame or restore operation occurs.
#include "RetailSaveMap.h"
#include "RetailSavePlayer.h"
#include "RetailSaveSupporting.h"
#include "RetailSaveTeam.h"
#include <array>
#include <cstddef>
#include <cstdint>
#include <vector>

namespace ZeroSisHost {

enum class RetailBodyLayout { Bnw64GameMapTeamsPlayersSupporting };
enum class RetailBodyBooleanImportPolicy {
    RequireCanonical,
    OperationReinforcementNonzeroTruth
};

struct RetailSaveBodyImportProfile {
    RetailSaveBodyImportProfile(RetailBodyLayout layout, const RetailSaveStateProfile& state,
        const RetailSavePlayerWireProfile& player)
        : layout(layout), stateProfile(state), playerProfile(player) {}
    RetailBodyLayout layout;
    RetailSaveStateProfile stateProfile;
    RetailSavePlayerWireProfile playerProfile;
};

struct RetailBodyTeamRow {
    RetailInflatedSpan whole;
    std::int32_t id = -1;
    std::size_t arrayRecords = 0;
};

struct RetailBodyPlayerRow {
    RetailInflatedSpan whole, operations;
    std::int32_t id = -1;
    std::size_t arrayRecords = 0;
    std::uint32_t cityCount = 0, unitCount = 0, armyCount = 0, operationCount = 0;
};

struct RetailSaveBodyInspection {
    RetailSaveMapInspection gameMap;
    RetailInflatedSpan game, map, supporting;
    std::array<RetailBodyTeamRow, 64> teams{};
    std::array<RetailBodyPlayerRow, 64> players{};
    std::size_t arrayRecords = 0, nextInflatedOffset = 0;
    std::size_t cityCount = 0, unitCount = 0, armyCount = 0, operationCount = 0;
};

struct RetailBodyBooleanEdit {
    std::size_t offset = 0;
    unsigned char before = 0, after = 1;
    std::uint32_t playerSlot = 0, operationIndex = 0;
};

struct RetailSavePreparedBody {
    // These spans describe these owned bytes at return. Mutating bytes later
    // invalidates the framing evidence and requires another full validation.
    std::vector<unsigned char> bytes;
    std::vector<RetailBodyBooleanEdit> edits;
    RetailSaveBodyInspection wire;
    bool canonicalWireFramed = false;
    bool producerContractVerified = false;
    bool rulesetCompatibilityVerified = false;
    bool completeSaveVerified = false;
    bool restoreApproved = false;
};

namespace RetailBodyImportDetail {

inline bool SameSpan(const RetailInflatedSpan& a, const RetailInflatedSpan& b) noexcept {
    return a.offset == b.offset && a.bytes == b.bytes;
}

inline void RequireSpan(const RetailInflatedSpan& span, std::size_t start, std::size_t size) {
    if (span.offset != start || start > size || !span.bytes || span.bytes > size - start)
        throw RetailStateError(RetailStateErrorCode::InvalidValue, start,
            "Invalid contiguous retail import span");
}

inline RetailSaveBodyInspection InspectBody(const unsigned char* data, std::size_t size,
    const RetailSaveBodyImportProfile& profile, const RetailSaveStateLimits& limits) {
    if (profile.layout != RetailBodyLayout::Bnw64GameMapTeamsPlayersSupporting)
        throw RetailStateError(RetailStateErrorCode::UnsupportedProfile, 0,
            "Unsupported explicit retail body layout");
    auto remaining = limits;
    RetailSaveBodyInspection result;
    std::size_t cursor = 0;
    auto advance = [&](std::size_t next, std::size_t records) {
        if (next <= cursor || next > size)
            throw RetailStateError(RetailStateErrorCode::InvalidValue, cursor,
                "Invalid retail import stage boundary");
        if (records > remaining.maxTotalRecords)
            throw RetailStateError(RetailStateErrorCode::TotalRecordLimit, cursor,
                "Retail import exceeds shared record budget");
        remaining.maxTotalRecords -= records;
        result.arrayRecords += records;
        cursor = next;
    };
    result.gameMap = RetailSaveMap::InspectGameAndMap(data, size, profile.stateProfile, remaining);
    result.game = result.gameMap.prefix.game;
    result.map = result.gameMap.map;
    RequireSpan(result.game, 0, size);
    RequireSpan(result.map, result.game.bytes, size);
    if (result.map.offset + result.map.bytes != result.gameMap.nextInflatedOffset)
        throw RetailStateError(RetailStateErrorCode::InvalidValue, result.map.offset,
            "Retail Map span differs from framed boundary");
    advance(result.gameMap.nextInflatedOffset, result.gameMap.arrayRecords);

    RetailStateDetail::Reader teams(data, size, remaining);
    teams.Skip(cursor);
    for (std::size_t slot = 0; slot < result.teams.size(); ++slot) {
        const auto start = teams.Pos(), records = teams.Records();
        const auto id = RetailStateDetail::ReadTeam(teams);
        if (id != static_cast<std::int32_t>(slot))
            teams.Fail(RetailStateErrorCode::InvalidValue, "Retail Team ID differs from slot order");
        result.teams[slot] = {teams.SpanFrom(start), id, teams.Records() - records};
    }
    advance(teams.Pos(), teams.Records());

    for (std::size_t slot = 0; slot < result.players.size(); ++slot) {
        const auto player = RetailSavePlayer::InspectAt(data, size, cursor, profile.playerProfile, remaining);
        RequireSpan(player.whole, cursor, size);
        if (player.playerId != static_cast<std::int32_t>(slot) ||
            player.whole.offset + player.whole.bytes != player.nextInflatedOffset ||
            !player.completePlayerWireFramed)
            throw RetailStateError(RetailStateErrorCode::InvalidValue, cursor,
                "Retail Player differs from explicit contiguous slot order");
        const auto operations = player.ending.operations.whole;
        if (operations.offset < cursor || operations.offset > player.nextInflatedOffset ||
            operations.bytes > player.nextInflatedOffset - operations.offset)
            throw RetailStateError(RetailStateErrorCode::InvalidValue, cursor,
                "Retail operations lie outside owning Player");
        auto& row = result.players[slot];
        row.whole = player.whole; row.operations = operations; row.id = player.playerId;
        row.arrayRecords = player.arrayRecords;
        row.cityCount = player.cities.pool.liveCount; row.unitCount = player.units.pool.liveCount;
        row.armyCount = player.ending.armyPool.liveCount;
        row.operationCount = player.ending.operations.declaredCount;
        result.cityCount += row.cityCount; result.unitCount += row.unitCount;
        result.armyCount += row.armyCount; result.operationCount += row.operationCount;
        advance(player.nextInflatedOffset, player.arrayRecords);
    }
    result.supporting = RetailSaveSupporting::InspectAt(data, size, cursor,
        result.gameMap.plotCount, remaining);
    RequireSpan(result.supporting, cursor, size);
    advance(result.supporting.offset + result.supporting.bytes, 0);
    if (cursor != size)
        throw RetailStateError(RetailStateErrorCode::InvalidValue, cursor,
            "Trailing bytes after explicit retail body sequence");
    result.nextInflatedOffset = cursor;
    return result;
}

// Internal only: Prepare supplies spans obtained from its own complete framing.
// A caller-provided offset or this helper alone cannot approve a body or restore.
inline std::vector<RetailBodyBooleanEdit> CollectOperationEdits(const unsigned char* data,
    std::size_t size, RetailInflatedSpan whole, std::uint32_t playerSlot,
    RetailPlayerOperationsProfile profile, const RetailSaveStateLimits& limits) {
    RetailStateDetail::Reader validate(data, size, limits);
    if (playerSlot >= 64 || whole.offset > size || whole.bytes > size - whole.offset)
        validate.Fail(RetailStateErrorCode::InvalidValue, "Invalid retail operation inspection range");
    auto raw = limits;
    raw.booleanWireProfile = RetailBooleanWireProfile::SdkRawByte;
    const auto end = whole.offset + whole.bytes;
    RetailStateDetail::Reader input(data, end, raw);
    input.Skip(whole.offset);
    RetailStateDetail::ValidatePlayerOperationsProfile(input, profile);
    const auto count = input.Count(RetailStateDetail::PlayerOperationMinimumRecordBytes);
    std::vector<RetailBodyBooleanEdit> edits;
    for (std::uint32_t i = 0; i < count; ++i) {
        input.I32(); // Original Read intentionally discards the outer map key.
        const auto type = input.I32();
        if (type < 0 || type >= 20)
            input.Fail(RetailStateErrorCode::UnsupportedProfile, "Unsupported retail operation type");
        const auto base = input.Pos();
        RetailStateDetail::ReadPlayerOperationBase(input);
        RetailStateDetail::ReadPlayerOperationDerived(input, type);
        // Successful base reading proves base+24 is in bounds, even for SIZE_MAX.
        // Only this source-declared member is eligible; derived bools are not.
        const auto offset = base + 24u;
        if (data[offset] > 1) edits.push_back({offset, data[offset], 1, playerSlot, i});
    }
    if (input.Pos() != end)
        input.Fail(RetailStateErrorCode::InvalidValue, "Retail operation inspection did not consume its span");
    return edits;
}

inline bool SameWire(const RetailSaveBodyInspection& a, const RetailSaveBodyInspection& b) noexcept {
    if (!SameSpan(a.game, b.game) || !SameSpan(a.map, b.map) || !SameSpan(a.supporting, b.supporting) ||
        a.arrayRecords != b.arrayRecords || a.nextInflatedOffset != b.nextInflatedOffset ||
        a.cityCount != b.cityCount || a.unitCount != b.unitCount || a.armyCount != b.armyCount ||
        a.operationCount != b.operationCount || a.gameMap.plotCount != b.gameMap.plotCount ||
        a.gameMap.areaCount != b.gameMap.areaCount || a.gameMap.landmassCount != b.gameMap.landmassCount ||
        a.gameMap.prefix.mapWidth != b.gameMap.prefix.mapWidth ||
        a.gameMap.prefix.mapHeight != b.gameMap.prefix.mapHeight ||
        !SameSpan(a.gameMap.prefix.embeddedDatabase, b.gameMap.prefix.embeddedDatabase)) return false;
    for (std::size_t i = 0; i < a.teams.size(); ++i)
        if (!SameSpan(a.teams[i].whole, b.teams[i].whole) || a.teams[i].id != b.teams[i].id ||
            a.teams[i].arrayRecords != b.teams[i].arrayRecords) return false;
    for (std::size_t i = 0; i < a.players.size(); ++i) {
        const auto& x = a.players[i]; const auto& y = b.players[i];
        if (!SameSpan(x.whole, y.whole) || !SameSpan(x.operations, y.operations) || x.id != y.id ||
            x.arrayRecords != y.arrayRecords || x.cityCount != y.cityCount || x.unitCount != y.unitCount ||
            x.armyCount != y.armyCount || x.operationCount != y.operationCount) return false;
    }
    return true;
}
} // namespace RetailBodyImportDetail

class RetailSaveBodyImport {
public:
    static RetailSavePreparedBody Prepare(const unsigned char* data, std::size_t size,
        const RetailSaveBodyImportProfile& profile, RetailBodyBooleanImportPolicy policy,
        const RetailSaveStateLimits& limits = RetailSaveStateLimits{}) {
        if (limits.booleanWireProfile != RetailBooleanWireProfile::CanonicalZeroOne ||
            (policy != RetailBodyBooleanImportPolicy::RequireCanonical &&
             policy != RetailBodyBooleanImportPolicy::OperationReinforcementNonzeroTruth))
            throw RetailStateError(RetailStateErrorCode::UnsupportedProfile, 0,
                "Retail import requires an explicit policy and canonical output validation");
        auto initialLimits = limits;
        if (policy == RetailBodyBooleanImportPolicy::OperationReinforcementNonzeroTruth)
            initialLimits.booleanWireProfile = RetailBooleanWireProfile::SdkRawByte;
        const auto original = RetailBodyImportDetail::InspectBody(data, size, profile, initialLimits);
        RetailSavePreparedBody result;
        // One owned copy; return by value only after every check succeeds.
        result.bytes.assign(data, data + size);
        if (policy == RetailBodyBooleanImportPolicy::OperationReinforcementNonzeroTruth) {
            for (std::uint32_t slot = 0; slot < 64; ++slot) {
                // Reinspection is a consistency check, not new records in the
                // initial/final shared budget. Each full pass starts unchanged.
                const auto edits = RetailBodyImportDetail::CollectOperationEdits(data, size,
                    original.players[slot].operations, slot, profile.playerProfile.endProfile.operationProfile, limits);
                for (const auto& edit : edits) {
                    result.bytes[edit.offset] = edit.after;
                    result.edits.push_back(edit);
                }
            }
            result.wire = RetailBodyImportDetail::InspectBody(result.bytes.data(), result.bytes.size(), profile, limits);
            if (!RetailBodyImportDetail::SameWire(original, result.wire))
                throw RetailStateError(RetailStateErrorCode::InvalidValue, 0,
                    "Boolean import changed retail structural boundaries or counts");
        } else result.wire = original;
        result.canonicalWireFramed = true;
        return result;
    }
};
} // namespace ZeroSisHost
