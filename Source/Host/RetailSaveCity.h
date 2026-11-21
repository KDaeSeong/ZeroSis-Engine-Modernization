#pragma once

// Allocation-free framing of the original BNW City v6 / CityAI v1 wire body.
// This observes bytes only; it does not instantiate cities or resolve rules.
#include "RetailSaveCityServices.h"
#include "RetailSaveCityPopulation.h"
#include <cstddef>
#include <cstdint>

namespace ZeroSisHost {

struct RetailSaveCityProfile {
    RetailSaveCityProfile(std::uint32_t projects, RetailCityProductionCatalogProfile catalogs,
        std::uint32_t yields) : production(projects, catalogs), yieldTypes(yields) {}
    RetailCityServicesProfile production;
    std::uint32_t yieldTypes;
};

struct RetailSaveCityInspection {
    RetailInflatedSpan front, buildings, productionTablesAndRanks;
    RetailInflatedSpan strategy, citizens, religions, emphases, espionage;
    RetailInflatedSpan extraHitPoints, cityAITail, whole;
    std::int32_t cityId = -1;
    std::size_t nextInflatedOffset = 0, arrayRecords = 0;
    bool completePlayerVerified = false;
    bool completeSaveVerified = false;
    bool rulesetCompatibilityVerified = false;
    bool restoreApproved = false;
};

namespace RetailStateDetail {

// These structural minima exclude the required external projectCount * 4.
constexpr std::size_t CityBaseMinimumBytes = 1629u;
constexpr std::size_t CityAIMinimumBytes = 2282u;
constexpr std::size_t CityAITailBytes = 653u;

inline void ValidateCityProfile(Reader& input, const RetailSaveCityProfile& profile) {
    if (profile.yieldTypes != 6u || profile.production.catalogProfile !=
            RetailCityProductionCatalogProfile::InitializedBuildingsAndUnits)
        input.Fail(RetailStateErrorCode::UnsupportedProfile, "Unsupported BNW city wire profile");
}

inline void CityIntVector(Reader& input) {
    const auto count = input.Count(4);
    input.Fixed(count, 4);
}

inline void CityBoolVector(Reader& input) {
    const auto count = input.Count(1);
    for (std::uint32_t i = 0; i < count; ++i) input.Bool();
}

inline RetailSaveCityInspection ReadCityAI(Reader& input, const RetailSaveCityProfile& profile) {
    // NUM_YIELD_TYPES is six in this source profile. The 2D hash-array writer
    // emits no inner dimension; never infer it by searching the input bytes.
    ValidateCityProfile(input, profile);
    RetailSaveCityInspection result;
    const auto start = input.Pos(), records = input.Records();
    input.Version(6);
    result.cityId = input.I32();
    // CvCity.cpp:13774-13839: 66 four-byte fields including ID and the demanded
    // resource hash. Neither a missing hash nor -1 removes a following scalar.
    input.Fixed(65, 4);
    for (unsigned i = 0; i < 10; ++i) input.Bool();
    input.Fixed(4, 4); // Owner, previous owner, original owner, religion owner.
    // FAutoVariable<vector<int>> and vector<int> share the uint32 count codec.
    for (unsigned i = 0; i < 18; ++i) CityIntVector(input);
    CityBoolVector(input); CityBoolVector(input);
    input.String(); input.String(); // Name, script data; opaque byte strings.
    for (unsigned i = 0; i < 3; ++i) input.Hashes(4); // Resource integer tables.
    CityIntVector(input); CityIntVector(input); // Specialist / project production.
    result.front = input.SpanFrom(start);

    auto begin = input.Pos();
    ReadCityBuildings(input);
    result.buildings = input.SpanFrom(begin);
    begin = input.Pos();
    input.Hashes(4); input.Hashes(4); // Unit production and production time.
    for (unsigned i = 0; i < 7; ++i) CityIntVector(input);
    input.Hashes(4); // Free promotion counts.
    // FFastSmallFixedList's capacity estimate 25 is not a serialized maximum.
    // All order cases, including the raw-enum fallback, write 3 words + 2 bools.
    const auto orders = input.Count(14);
    for (std::uint32_t i = 0; i < orders; ++i) {
        input.I32(); input.U32(); input.I32(); input.Bool(); input.Bool();
    }
    // Resource, feature, terrain changes: a count and a hash precede each row.
    // Hash zero omits the entire six-int row; all nonzero hashes retain it.
    for (unsigned i = 0; i < 3; ++i) input.Hashes(24);
    input.I32(); input.Bool(); // Population rank and its validity.
    CityIntVector(input); CityBoolVector(input);
    CityIntVector(input); CityBoolVector(input);
    input.I32(); // Last expansion turn.
    input.I32(); input.I32(); // Base / unmodified building happiness.
    input.Bool(); input.Bool(); // Route to capital last / this turn.
    input.String(); // The writer deliberately saves the city name twice.
    input.Bool(); // Owed culture building.
    result.productionTablesAndRanks = input.SpanFrom(begin);

    begin = input.Pos();
    ReadCityStrategyAI(input, profile.production);
    result.strategy = input.SpanFrom(begin);
    begin = input.Pos(); ReadCityCitizens(input); result.citizens = input.SpanFrom(begin);
    begin = input.Pos(); ReadCityReligions(input); result.religions = input.SpanFrom(begin);
    begin = input.Pos(); ReadCityEmphases(input); result.emphases = input.SpanFrom(begin);
    begin = input.Pos(); ReadCityEspionage(input); result.espionage = input.SpanFrom(begin);
    begin = input.Pos(); input.I32(); result.extraHitPoints = input.SpanFrom(begin);
    // CvCityCulture exists as a member but is NOT separately written here.
    begin = input.Pos();
    // CvCityAI.cpp:238-251 and CvCityAI.h:44-45: these are raw fixed arrays
    // sized REALLY_MAX_PLAYERS (80), without counts; MAX_PLAYERS (64) is wrong.
    input.Version(1); input.Bool(); input.Fixed(2, 4); input.Fixed(160, 4);
    result.cityAITail = input.SpanFrom(begin);
    result.whole = input.SpanFrom(start);
    result.nextInflatedOffset = input.Pos();
    result.arrayRecords = input.Records() - records;
    return result;
}

} // namespace RetailStateDetail

class RetailSaveCity {
public:
    static RetailSaveCityInspection InspectAt(const unsigned char* data, std::size_t size,
        std::size_t start, const RetailSaveCityProfile& profile,
        const RetailSaveStateLimits& limits = RetailSaveStateLimits{}) {
        RetailStateDetail::Reader input(data, size, limits);
        input.Skip(start);
        return RetailStateDetail::ReadCityAI(input, profile);
    }
};

} // namespace ZeroSisHost
