#pragma once

// One complete CvPlayerAI wire object assembled from the bounded Player stages.
// Profiles are caller-supplied hypotheses; no catalog or restore is approved.
#include "RetailSavePlayerPrefix.h"
#include "RetailSavePlayerAiMid.h"
#include "RetailSavePlayerAiLate.h"
#include "RetailSavePlayerPostTraits.h"
#include "RetailSavePlayerCities.h"
#include "RetailSavePlayerUnits.h"
#include "RetailSavePlayerEnd.h"
#include <cstddef>

namespace ZeroSisHost {

struct RetailSavePlayerWireProfile {
    RetailSavePlayerWireProfile(const RetailSavePlayerProfile& front,
        RetailPlayerAiMidCatalogProfile mid, RetailPlayerAiLateProfile late,
        const RetailSaveCityProfile& city, RetailUnitWriterProfile unit,
        const RetailSavePlayerEndProfile& end)
        : prefixProfile(front), middleProfile(mid), lateProfile(late), cityProfile(city),
          unitProfile(unit), endProfile(end) {}
    RetailSavePlayerProfile prefixProfile;
    RetailPlayerAiMidCatalogProfile middleProfile;
    RetailPlayerAiLateProfile lateProfile;
    RetailSaveCityProfile cityProfile;
    RetailUnitWriterProfile unitProfile;
    RetailSavePlayerEndProfile endProfile;
};

struct RetailSavePlayerInspection {
    RetailSavePlayerPrefixInspection prefix;
    RetailSavePlayerAiMidInspection middle;
    RetailSavePlayerAiLateInspection late;
    RetailSavePlayerPostTraitsInspection postTraits;
    RetailSavePlayerCitiesInspection cities;
    RetailSavePlayerUnitsInspection units;
    RetailSavePlayerEndInspection ending;
    RetailInflatedSpan whole;
    std::int32_t playerId = -1;
    std::size_t nextInflatedOffset = 0, arrayRecords = 0;
    bool completePlayerWireFramed = false;
    bool completePlayerVerified = false;
    bool completeSaveVerified = false;
    bool rulesetCompatibilityVerified = false;
    bool restoreApproved = false;
};

class RetailSavePlayer {
public:
    static RetailSavePlayerInspection InspectAt(const unsigned char* data, std::size_t size,
        std::size_t start, const RetailSavePlayerWireProfile& profile,
        const RetailSaveStateLimits& limits = RetailSaveStateLimits{}) {
        auto remaining = limits;
        auto cursor = start;
        RetailSavePlayerInspection result;
        // Each stage owns its explicit record counts. Deduct them exactly once
        // from the caller's shared budget rather than resetting it per stage.
        auto advance = [&](std::size_t next, std::size_t records) {
            if (next < cursor || next > size)
                throw RetailStateError(RetailStateErrorCode::InvalidValue, cursor,
                    "Noncontiguous BNW Player stage boundary");
            if (records > remaining.maxTotalRecords)
                throw RetailStateError(RetailStateErrorCode::TotalRecordLimit, cursor,
                    "BNW Player exceeds shared record budget");
            remaining.maxTotalRecords -= records;
            result.arrayRecords += records; // The initial budget bounds this sum.
            cursor = next;
        };
        result.prefix = RetailSavePlayerPrefix::InspectAt(data, size, cursor, profile.prefixProfile, remaining);
        advance(result.prefix.nextInflatedOffset, result.prefix.arrayRecords);
        result.playerId = result.prefix.playerId;
        result.middle = RetailSavePlayerAiMid::InspectAt(data, size, cursor, profile.middleProfile, remaining);
        advance(result.middle.nextInflatedOffset, result.middle.arrayRecords);
        result.late = RetailSavePlayerAiLate::InspectAt(data, size, cursor, profile.lateProfile, remaining);
        advance(result.late.nextInflatedOffset, result.late.arrayRecords);
        result.postTraits = RetailSavePlayerPostTraits::InspectAt(data, size, cursor, remaining);
        advance(result.postTraits.nextInflatedOffset, result.postTraits.arrayRecords);
        result.cities = RetailSavePlayerCities::InspectAt(data, size, cursor, profile.cityProfile, remaining);
        advance(result.cities.nextInflatedOffset, result.cities.arrayRecords);
        result.units = RetailSavePlayerUnits::InspectAt(data, size, cursor, profile.unitProfile, remaining);
        advance(result.units.nextInflatedOffset, result.units.arrayRecords);
        result.ending = RetailSavePlayerEnd::InspectAt(data, size, cursor, profile.endProfile, remaining);
        advance(result.ending.nextInflatedOffset, result.ending.arrayRecords);
        result.whole = {start, cursor - start};
        result.nextInflatedOffset = cursor;
        result.completePlayerWireFramed = true;
        // This proves a contiguous declared wire shape only. It does not prove
        // ruleset identity, object references, full container finish or gameplay.
        return result;
    }
};

} // namespace ZeroSisHost
