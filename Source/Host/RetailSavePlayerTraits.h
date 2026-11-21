#pragma once

// Latest retained BNW PlayerTraits v19 wire framing, not a ruleset validator
// or SDK restore. All counts are recorded; fixed NUM_YIELD_TYPES is six.
#include "RetailSaveStateWire.h"
#include <cstddef>

namespace ZeroSisHost {
namespace RetailStateDetail {

constexpr std::size_t PlayerTraitsMinimumBytes = 503u;

inline void ReadPlayerTraits(Reader& reader) {
    // CvTraitClasses.cpp:2853-3004. Names and host size_t widths cannot
    // replace the original int/uint32 stream codecs.
    reader.Version(19);
    reader.Fixed(65, 4); // Rate/modifier ints through trade-building modifier.
    for (unsigned i = 0; i < 14; ++i) reader.Bool();
    reader.I32(); // Previous baktun.
    const auto mayaChoices = reader.SignedCount(8);
    reader.Fixed(mayaChoices, 8); // UnitTypes enum and finished baktun int.
    for (unsigned i = 0; i < 5; ++i) reader.Bool();
    reader.Fixed(2, 4); // Camp-guard UnitTypes and combat-bonus ImprovementTypes.
    reader.Fixed(7 * 6, 4); // Seven unprefixed int[NUM_YIELD_TYPES] arrays.
    reader.Hashes(4); // TerrainTypes strategic-resource modifiers.
    reader.Hashes(4); // ResourceTypes quantity modifiers.
    const auto noTrain = reader.SignedCount(1);
    for (std::uint32_t i = 0; i < noTrain; ++i) reader.Bool();
    const auto freeUnits = reader.SignedCount(8);
    reader.Fixed(freeUnits, 8); // Free unit int and prerequisite TechTypes enum.
    const auto unitCombatClasses = reader.SignedCount(8);
    reader.Fixed(unitCombatClasses, 4); // Move changes.
    reader.Fixed(unitCombatClasses, 4); // Maintenance modifiers.
    // The generic vector codec prefixes each outer row count once. Each
    // Firaxis::Array<int,6> then writes six ints without an inner count.
    for (unsigned matrix = 0; matrix < 3; ++matrix) {
        const auto rows = reader.Count(6 * 4);
        reader.Fixed(rows, 6 * 4);
    }
    const auto uniqueLuxuryAreas = reader.SignedCount(4);
    reader.Fixed(uniqueLuxuryAreas, 4);
}

} // namespace RetailStateDetail
} // namespace ZeroSisHost
