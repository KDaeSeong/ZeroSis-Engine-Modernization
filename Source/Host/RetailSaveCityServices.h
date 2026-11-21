#pragma once

// Latest copied BNW CityBuildings and CityStrategyAI wire framing only.
// No SDK, allocation, I/O, catalog resolution or restore approval occurs here.
#include "RetailSaveStateWire.h"
#include <cstddef>
#include <cstdint>

namespace ZeroSisHost {

enum class RetailCityProductionCatalogProfile {
    InitializedBuildingsAndUnits
};

struct RetailCityServicesProfile {
    // ProjectProductionAI has no on-wire count. The caller must supply its
    // catalog width; this does not verify that any type hash resolves to it.
    explicit RetailCityServicesProfile(std::uint32_t projects,
        RetailCityProductionCatalogProfile catalog)
        : projectCount(projects), catalogProfile(catalog) {}
    std::uint32_t projectCount;
    RetailCityProductionCatalogProfile catalogProfile;
};

namespace RetailStateDetail {

constexpr std::size_t CityServicesBuildingsMinimumBytes = 65u;
// The strategy minimum excludes the external projectCount * 4 payload.
constexpr std::size_t CityServicesStrategyMinimumBytes = 52u;
constexpr std::size_t CityServicesBuildingProductionMinimumBytes = 8u;
constexpr std::size_t CityServicesUnitProductionMinimumBytes = 8u;
constexpr std::size_t CityServicesProjectProductionMinimumBytes = 4u;
constexpr std::size_t CityServicesProcessProductionMinimumBytes = 8u;

inline void ReadCityBuildingIntArray(Reader& reader) {
    // SDK_BNW_Original/CvGameCoreDLL_Expansion2/CvBuildingClasses.cpp:
    // 3616-3664, BuildingArrayHelpers. The count is SIGNED, unlike generic
    // hashed arrays. Only hash zero omits the int32. Unknown nonzero hashes,
    // including FFFFFFFF, still carry a value which the SDK may discard.
    const auto entries = reader.SignedCount(4);
    for (std::uint32_t i = 0; i < entries; ++i)
        if (reader.U32() != 0) reader.I32();
}

inline void ReadCityBuildings(Reader& reader) {
    // CvBuildingClasses.cpp:2142-2207, latest version1. The SDK requires its
    // buildings catalog to be initialized, but writes all six array counts.
    // Framing neither initializes nor checks that catalog or its type hashes.
    reader.Version(1);
    reader.Fixed(7, 4); // Buildings, production, defense/mod, missionary, tourism x2.
    reader.Bool(); // Sold a building this turn.
    for (unsigned table = 0; table < 6; ++table) ReadCityBuildingIntArray(reader);

    // CvStructs.cpp:135-164. Generic vector counts are unsigned32; each
    // record has exactly three raw32 fields and no nested count or version.
    // The enum fields are raw values, NOT hashes with optional payloads.
    const auto yieldChanges = reader.Count(12);
    reader.Fixed(yieldChanges, 12); // BuildingClassTypes, YieldTypes, int change.
    const auto greatWorks = reader.Count(12);
    reader.Fixed(greatWorks, 12); // BuildingClassTypes, int slot, int work index.
}

inline void RequireCityProductionCatalog(Reader& reader,
    RetailCityProductionCatalogProfile catalog) {
    if (catalog != RetailCityProductionCatalogProfile::InitializedBuildingsAndUnits)
        reader.Fail(RetailStateErrorCode::UnsupportedProfile,
            "BNW City production requires initialized building and unit catalogs");
}

inline void ReadCityBuildingProductionAI(Reader& reader,
    RetailCityProductionCatalogProfile catalog) {
    // CvBuildingProductionAI.cpp:46-126. A null catalog writes only the
    // version, without even a count; that branch is not inferred from bytes.
    RequireCityProductionCatalog(reader, catalog);
    reader.Version(1);
    ReadCityBuildingIntArray(reader); // Same signed hash/int framing as Buildings.
}

inline void ReadCityUnitProductionAI(Reader& reader,
    RetailCityProductionCatalogProfile catalog) {
    // CvUnitProductionAI.cpp:47-131. The initialized branch has a signed
    // count and the same zero-hash omission as BuildingProductionAI.
    RequireCityProductionCatalog(reader, catalog);
    reader.Version(1);
    const auto entries = reader.SignedCount(4);
    for (std::uint32_t i = 0; i < entries; ++i)
        if (reader.U32() != 0) reader.I32();
}

inline void ReadCityProjectProductionAI(Reader& reader, std::uint32_t projectCount) {
    // CvProjectProductionAI.cpp:38-68. The writer emits version1 followed
    // by GC.GetGameProjects()->GetNumProjects() raw int32 weights, with NO
    // count or hashes. Fixed checks the supplied width against byte budgets
    // without an overflowing product; no invented wire count is charged.
    reader.Version(1);
    reader.Fixed(projectCount, 4);
}

inline void ReadCityProcessProductionAI(Reader& reader) {
    // CvProcessProductionAI.cpp:39-78. The signed count is followed by a
    // hash AND int32 weight for EVERY entry, including hash zero/FFFFFFFF.
    // It must not use Hashes or the BuildingArrayHelpers omission rule.
    reader.Version(1);
    const auto entries = reader.SignedCount(8);
    reader.Fixed(entries, 8);
}

inline void ReadCityStrategyAI(Reader& reader, const RetailCityServicesProfile& profile) {
    RequireCityProductionCatalog(reader, profile.catalogProfile);
    // CvCityStrategyAI.cpp:321-370, latest version1. The signed flavor
    // count is serialized, so no external flavor-width assumption is needed.
    reader.Version(1);
    const auto flavors = reader.SignedCount(4);
    reader.Fixed(flavors, 4); // ArrayWrapper<int> adds no second count.

    // CvInfosSerializationHelper.h:247-269,554-565. These two counts are
    // unsigned32 and hash zero alone omits the following bool/int32. Read
    // each bool explicitly so a noncanonical byte cannot pass as padding.
    const auto strategies = reader.Count(4);
    for (std::uint32_t i = 0; i < strategies; ++i)
        if (reader.U32() != 0) reader.Bool();
    reader.Hashes(4); // Turn each strategy was adopted.
    reader.Fixed(2, 4); // Raw specialization and default-specialization enums.

    ReadCityBuildingProductionAI(reader, profile.catalogProfile);
    ReadCityUnitProductionAI(reader, profile.catalogProfile);
    ReadCityProjectProductionAI(reader, profile.projectCount);
    ReadCityProcessProductionAI(reader);
    // m_eFocusYield is reset by Read but is NOT serialized. These bytes do
    // not establish a complete City, complete Player or compatible ruleset.
}

} // namespace RetailStateDetail
} // namespace ZeroSisHost
