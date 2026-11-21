#pragma once

// CvPlayer::m_cities is a free-list followed by actual CityAI objects.
// The next field is m_units; this component never scans or skips unit bodies.
#include "RetailSaveCity.h"
#include "RetailSaveFreeList.h"
#include <cstddef>

namespace ZeroSisHost {

struct RetailSavePlayerCitiesInspection {
    RetailStateDetail::RetailFreeListHeader pool;
    RetailInflatedSpan cityObjects, whole;
    RetailSaveCityInspection firstCity, lastCity;
    std::size_t nextInflatedOffset = 0, arrayRecords = 0;
    bool cityObjectIdsVerified = false;
    bool completePlayerVerified = false;
    bool completeSaveVerified = false;
    bool rulesetCompatibilityVerified = false;
    bool restoreApproved = false;
};

class RetailSavePlayerCities {
public:
    static RetailSavePlayerCitiesInspection InspectAt(const unsigned char* data, std::size_t size,
        std::size_t start, const RetailSaveCityProfile& profile,
        const RetailSaveStateLimits& limits = RetailSaveStateLimits{}) {
        RetailStateDetail::Reader input(data, size, limits);
        input.Skip(start);
        RetailStateDetail::ValidateCityProfile(input, profile);
        RetailSavePlayerCitiesInspection result;
        result.pool = RetailStateDetail::ReadFreeListHeader(input);
        const auto objectsStart = input.Pos();
        for (std::uint32_t i = 0; i < result.pool.liveCount; ++i) {
            const auto city = RetailStateDetail::ReadCityAI(input, profile);
            if (i == 0) result.firstCity = city;
            result.lastCity = city;
        }
        result.cityObjects = input.SpanFrom(objectsStart);
        result.whole = input.SpanFrom(start);
        result.nextInflatedOffset = input.Pos();
        result.arrayRecords = input.Records();
        // Parsing the wire body does not check object placement, unique IDs,
        // coordinates, owning Player or cross-object/ruleset references.
        return result;
    }
};

} // namespace ZeroSisHost
