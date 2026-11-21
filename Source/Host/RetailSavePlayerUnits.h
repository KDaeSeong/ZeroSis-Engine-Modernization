#pragma once

// CvPlayer::m_units: free-list header and real Unit v9 bodies, ending at m_armyAIs.
#include "RetailSaveUnit.h"
#include "RetailSaveFreeList.h"
#include <cstddef>

namespace ZeroSisHost {

struct RetailSavePlayerUnitsInspection {
    RetailStateDetail::RetailFreeListHeader pool;
    RetailInflatedSpan unitObjects, whole;
    RetailSaveUnitInspection firstUnit, lastUnit;
    std::size_t nextInflatedOffset = 0, arrayRecords = 0;
    bool unitObjectIdsVerified = false;
    bool completePlayerVerified = false;
    bool completeSaveVerified = false;
    bool rulesetCompatibilityVerified = false;
    bool restoreApproved = false;
};

class RetailSavePlayerUnits {
public:
    static RetailSavePlayerUnitsInspection InspectAt(const unsigned char* data, std::size_t size,
        std::size_t start, RetailUnitWriterProfile profile,
        const RetailSaveStateLimits& limits = RetailSaveStateLimits{}) {
        RetailStateDetail::Reader input(data, size, limits);
        input.Skip(start);
        RetailStateDetail::ValidateUnitProfile(input, profile);
        RetailSavePlayerUnitsInspection result;
        result.pool = RetailStateDetail::ReadFreeListHeader(input);
        const auto objectsStart = input.Pos();
        for (std::uint32_t i = 0; i < result.pool.liveCount; ++i) {
            const auto unit = RetailStateDetail::ReadUnit(input, profile);
            if (i == 0) result.firstUnit = unit;
            result.lastUnit = unit;
        }
        result.unitObjects = input.SpanFrom(objectsStart);
        result.whole = input.SpanFrom(start);
        result.nextInflatedOffset = input.Pos();
        result.arrayRecords = input.Records();
        // Placement, owning Player, map references and catalog hashes are not
        // authenticated by structural parsing, even when public IDs cross-check.
        return result;
    }
};

} // namespace ZeroSisHost
