#pragma once

// Four nested states called by original CvPlayer.cpp:22592-22595, after
// DiplomacyAI and before TacticalAI. Corresponding port Write bodies are
// identical. This is not complete Player framing, ruleset validation or restore.
#include "RetailSaveStateWire.h"
#include <cstddef>
#include <cstdint>

namespace ZeroSisHost {
namespace RetailStateDetail {

// Structural lower bounds admit empty tables, not a verified game ruleset.
// PlayerTechs requires the initialized-tech-catalog branch described below.
constexpr std::size_t PlayerReligionsMinimumBytes = 12u;
constexpr std::size_t PlayerReligionAIMinimumBytes = 4u;
constexpr std::size_t PlayerTechAIMinimumBytes = 8u;
constexpr std::size_t PlayerTechsMinimumBytes = 44u;
constexpr std::size_t PlayerFlavorManagerMinimumBytes = 8u;

inline void ReadPlayerReligions(Reader& reader) {
    // CvReligionClasses.cpp:2248-2255. Despite its name, m_bFoundingReligion
    // is an int (CvReligionClasses.h:310-311), not a one-byte bool.
    reader.Version(1);
    reader.I32(); // Number of prophets spawned; a scalar, not an array count.
    reader.I32(); // Founding religion. Do not apply bool canonicality here.
    // No religion collection, beliefs, strings or nested versions are written.
}

inline void ReadPlayerReligionAI(Reader& reader) {
    // CvReligionClasses.cpp:4182-4187. The only field is the version word;
    // neither the belief catalog nor the owning Player pointer is serialized.
    reader.Version(1);
}

inline void ReadPlayerTechAI(Reader& reader) {
    // CvTechAI.cpp:78-96. uiCount is explicitly uint, even though Read:65-66
    // uses an int local. Every row ALWAYS contains a type hash and an int32
    // weight, including zero/unknown hashes; generic Hashes(4) would be wrong.
    reader.Version(1);
    const auto weights = reader.Count(8);
    reader.Fixed(weights, 8);
}

// Requires CvPlayer's initialized-tech-catalog branch: CvPlayer.cpp:1124
// passes GC.GetGameTechs() to Init; CvTechClasses.cpp:606-613 retains it.
// Write:831-842 omits ALL SEVEN array count words when m_pTechs is null.
// There is no presence flag. This function supports the initialized branch
// only; its caller must explicitly select that profile, without a default or
// byte-based inference. It cannot authenticate a ruleset or a catalog match.
inline void ReadPlayerTechs(Reader& reader) {
    // CvTechClasses.cpp:823-849 and CvInfosSerializationHelper.h:554-565.
    // Each pointer-array writer has its own uint32 count and emits its value
    // only when WriteHashed succeeds. Zero hashes omit the value; all nonzero
    // hashes (including 0xffffffff) retain it, even if the type is unknown.
    reader.Version(1);
    const auto researching = reader.Count(4);
    for (std::uint32_t i = 0; i < researching; ++i)
        if (reader.U32() != 0) reader.Bool();
    reader.Hashes(4); // Civilization tech priority, int32.
    reader.Hashes(4); // Locale tech priority, int32.
    reader.Hashes(4); // Locale resource, ResourceTypes enum.
    reader.Hashes(4); // Civilization unique unit, UnitTypes enum.
    reader.Hashes(4); // Civilization unique building, BuildingTypes enum.
    reader.Hashes(4); // Civilization unique improvement, ImprovementTypes enum.
    // These enum values have four-byte stream codecs, not GameTypes' special
    // one-byte codec. They are raw enum values, not additional type hashes.
    ReadPlayerTechAI(reader);

    // CvTechClasses.cpp:847-849. A signed flavor count precedes the raw int32
    // array. ArrayWrapper::operator<< (FDataStream.h:500-511) adds no count.
    const auto flavors = reader.SignedCount(4);
    reader.Fixed(flavors, 4);
    // All technology/flavor widths above are recorded. No external NUM_TECH
    // or NUM_FLAVOR assumption, base FlavorRecipient header or padding is used.
}

inline void ReadPlayerFlavorManager(Reader& reader) {
    // CvFlavorManager.cpp:264-274. One signed int count owns TWO consecutive
    // int32 columns. Both ArrayWrappers are uncounted, with no base version.
    reader.Version(1);
    const auto flavors = reader.SignedCount(8);
    reader.Fixed(flavors, 4); // Personality flavors.
    reader.Fixed(flavors, 4); // Active flavors.
}

} // namespace RetailStateDetail
} // namespace ZeroSisHost
