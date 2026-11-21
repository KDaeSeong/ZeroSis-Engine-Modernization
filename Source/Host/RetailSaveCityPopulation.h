#pragma once

// Latest copied BNW City states between CityStrategyAI and extra hit points.
// Inflated-byte framing only: no SDK, catalogs, allocation, I/O or restore.
#include "RetailSaveCityServices.h"
#include <cstddef>
#include <cstdint>

namespace ZeroSisHost {
namespace RetailStateDetail {

constexpr std::size_t CityPopulationCitizensMinimumBytes = 125u;
constexpr std::size_t CityPopulationReligionsMinimumBytes = 13u;
constexpr std::size_t CityPopulationReligionRowMinimumBytes = 21u;
constexpr std::size_t CityPopulationEmphasesMinimumBytes = 40u;
constexpr std::size_t CityPopulationEspionageMinimumBytes = 832u;

inline void ReadCityCitizens(Reader& reader) {
    // CvCityCitizens.cpp:129-188, Write version1. NUM_CITY_PLOTS=37 is fixed
    // in CvDefines.h:13; both raw bool arrays omit an on-wire count.
    reader.Version(1);
    reader.Bool(); // Automated.
    reader.Bool(); // No automatic specialist assignment.
    reader.Fixed(3, 4); // Unassigned citizens, working plots, forced plots.
    reader.U32(); // CityAIFocusTypes.
    reader.Bool(); // Forced avoid growth.
    for (unsigned table = 0; table < 2; ++table)
        for (unsigned plot = 0; plot < 37; ++plot) reader.Bool();
    reader.Fixed(2, 4); // Default and forced-default specialist counts.

    // CvInfosSerializationHelper.h:247-273,554-567. Each unsigned-count
    // specialist table has a hash and, only for nonzero hashes, an int32.
    // Catalog sizes are serialized, not implicit widths or type resolutions.
    reader.Hashes(4); // Specialist counts.
    reader.Hashes(4); // Specialist great-person progress times100.

    // BuildingArrayHelpers has a SIGNED count, unlike the specialist tables.
    // The shared helper preserves the zero-hash omission and consumes an
    // int32 after every nonzero hash, including FFFFFFFF and unknown hashes.
    ReadCityBuildingIntArray(reader); // Specialists in buildings.
    ReadCityBuildingIntArray(reader); // Forced specialists in buildings.
    reader.Hashes(4); // Building great-person rate changes by specialist.
}

inline void ReadCityReligionInCity(Reader& reader) {
    // CvReligionClasses.cpp:230-267. Latest nested version2; no padding.
    // The member m_iTemp is NOT serialized. Version1 lacks the trade int32
    // and is outside this latest-writer profile; later versions are unknown.
    reader.Version(2);
    reader.U32(); // ReligionTypes, not a hash with optional following bytes.
    reader.Bool(); // Founded here.
    reader.Fixed(3, 4); // Followers, pressure, trade routes applying pressure.
}

inline void ReadCityReligions(Reader& reader) {
    // CvReligionClasses.cpp:4015-4077. Latest outer version3 adds pressure.
    reader.Version(3);
    reader.Bool(); // Paid adoption bonus.
    reader.I32(); // Religious pressure modifier.
    // Write uses FStaticVector's unsigned32 size; Read consumes signed int32.
    // Reject its negative domain; the static estimate8 is not a wire cap.
    const auto religions = reader.SignedCount(CityPopulationReligionRowMinimumBytes);
    for (std::uint32_t i = 0; i < religions; ++i) ReadCityReligionInCity(reader);
}

inline void ReadCityEmphases(Reader& reader) {
    // CvEmphasisClasses.cpp:240-267. Both named "Count" fields are int32,
    // followed by NUM_YIELD_TYPES=6 raw int32 values without an array count.
    reader.Version(1);
    reader.Fixed(2, 4); // Avoid-growth and great-people emphasis counts.
    reader.Fixed(6, 4); // Emphasized-yield counts.
    const auto emphases = reader.Count(4);
    for (std::uint32_t i = 0; i < emphases; ++i)
        if (reader.U32() != 0) reader.Bool();
}

inline void ReadCityEspionage(Reader& reader) {
    // CvEspionageClasses.cpp:3906-4054. Latest version0 writes nine distinct
    // counts, each MAX_MAJOR_CIVS=22 (CvDLLUtilDefines.h:25), then raw int32
    // values. Firaxis::Array does not add a second count around these loops.
    reader.Version(0);
    for (unsigned column = 0; column < 9; ++column) {
        // Read's first four count locals are uint; its remaining five are int.
        const auto entries = column < 4 ? reader.Count(4) : reader.SignedCount(4);
        if (entries != 22u)
            reader.Fail(RetailStateErrorCode::InvalidValue,
                "BNW City espionage count differs from the current 22-player writer");
        reader.Fixed(entries, 4);
    }
    // Columns: spy assignment, amount, rate, goal, last progress, last
    // potential, last base potential, result, number of times robbed.
    // These 198 int32 values are not bool bytes or per-player subrecords.
}

} // namespace RetailStateDetail
} // namespace ZeroSisHost
