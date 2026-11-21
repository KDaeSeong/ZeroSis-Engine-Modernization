#pragma once

// Latest copied BNW Unit nested states. Inflated-byte framing only: no SDK,
// catalog resolution, allocation, file access or approval to restore a Unit.
#include "RetailSaveStateWire.h"
#include <cstddef>
#include <cstdint>

namespace ZeroSisHost {

struct RetailUnitPromotionSummary {
    std::uint32_t catalogSize = 0;
    std::uint32_t enabledCount = 0;
};

namespace RetailStateDetail {

constexpr std::size_t UnitServicesPromotionsMinimumBytes = 12u;
constexpr std::size_t UnitServicesReligionMinimumBytes = 16u;

inline RetailUnitPromotionSummary ReadUnitPromotions(Reader& reader) {
    // CvPromotionClasses.cpp:1774-1803,2015-2089. The first signed size is
    // catalog metadata, read but unused by the SDK. A SECOND signed count
    // controls the sparse rows; there is no bitfield payload or implicit width.
    reader.Version(1);
    const auto catalog = reader.I32();
    if (catalog < 0)
        reader.Fail(RetailStateErrorCode::InvalidValue, "Negative BNW promotion catalog size");
    RetailUnitPromotionSummary result;
    result.catalogSize = static_cast<std::uint32_t>(catalog);
    result.enabledCount = reader.SignedCount(5);
    // Write visits each catalog index once and counts only enabled entries
    // with a nonnull info pointer, so it cannot emit more rows than indices.
    // A positive catalog is only asserted, not required by the wire writer;
    // zero catalog / zero enabled is a supported structural lower bound.
    if (result.enabledCount > result.catalogSize)
        reader.Fail(RetailStateErrorCode::InvalidValue,
            "BNW enabled promotion count exceeds its serialized catalog size");
    for (std::uint32_t i = 0; i < result.enabledCount; ++i) {
        reader.U32();
        // Hash zero, FFFFFFFF, unknown and the special OLIGARCHY hash all
        // retain a bool byte. The generic hash-zero omission rule is WRONG.
        reader.Bool();
    }
    // Only enabledCount declares serialized rows and is charged to Records;
    // catalogSize is scalar metadata and causes no loop or allocation here.
    return result;
}

inline void ReadUnitReligion(Reader& reader) {
    // CvReligionClasses.cpp:4098-4135. Current nested version2 writes a raw
    // ReligionTypes word, religious strength and spreads left, without a hash,
    // count or presence flag. Version1 lacks spreads and is not inferred here.
    reader.Version(2);
    reader.Fixed(3, 4);
}

} // namespace RetailStateDetail
} // namespace ZeroSisHost
