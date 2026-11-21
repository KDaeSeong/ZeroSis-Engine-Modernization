#pragma once

// Allocation-free framing of CvUnit's registered full automatic archive.
// The caller owns the outer Unit version and all fields following this archive.
// No SDK, I/O, type-hash resolution or restore approval occurs here.
#include "RetailSaveStateWire.h"
#include <cstddef>
#include <cstdint>

namespace ZeroSisHost {

struct RetailSaveUnitArchiveInspection {
    RetailInflatedSpan whole;
    std::int32_t owner = -1, originalOwner = -1, unitType = -1;
    std::int32_t x = -1, y = -1, unitId = -1;
    std::size_t nextInflatedOffset = 0, arrayRecords = 0;
};

namespace RetailStateDetail {

constexpr std::size_t UnitArchiveMinimumBytes = 555u;

inline RetailSaveUnitArchiveInspection ReadUnitArchive(Reader& reader) {
    // SDK_BNW_Original/CvGameCoreDLL_Expansion2/CvUnit.h:1258-1448:
    // 147 registered members = 124 raw32 values, 11 bools, two CvStrings,
    // and ten vector<int> values. C++ DECLARATION order determines their
    // construction/registration order, not CvUnit.cpp:122-315's initializer
    // list order (which misleadingly starts with m_iID).
    //
    // FAutoVariable.h:278-288 and FAutoVector.h:251-265 serialize the value
    // alone. The current provider SdkAutoArchive.cpp:41-46,59-64 appends and
    // traverses registrations. Full save has NO archive count or version;
    // the count/index format of saveDelta is a separate, unused operation.
    const auto start = reader.Pos(), records = reader.Records();
    RetailSaveUnitArchiveInspection result;

    // CvUnit.h:1258-1274, registered members 1-14. Enum values here are
    // raw32 (including UnitTypes), not hashes with optional payloads. The
    // special one-byte GameTypes codec is not used by any archive member.
    result.owner = reader.I32();
    result.originalOwner = reader.I32();
    result.unitType = reader.I32();
    result.x = reader.I32();
    result.y = reader.I32();
    result.unitId = reader.I32();
    reader.Fixed(8, 4); // Hotkey, deploy, recon x/y/count, created, damage, moves.
    reader.Bool(); // Member15, m_bImmobile (CvUnit.h:1275).

    // CvUnit.h:1276-1285, members16-25: experience, level, cargo/capacity,
    // attack x/y, combat timer/first strikes/damage, fortify turns.
    reader.Fixed(10, 4);
    reader.Bool(); // Member26, m_bFortifiedThisTurn (CvUnit.h:1286).

    // CvUnit.h:1287-1391, members27-114: all 88 values are raw32, from
    // m_iBlitzCount through m_iMadeInterceptionCount. This includes the
    // DirectionTypes facing enum and integer ability counters whose names
    // describe boolean effects; none becomes a one-byte bool on the wire.
    reader.Fixed(88, 4);

    // CvUnit.h:1397-1405, members115-123: promotion ready, death delay,
    // combat focus, info bar dirty, not converting, air combat, ranged
    // setup, embarked, AI turn processed. Constructor tracking arguments
    // do not add bytes or alter these eleven total bool widths.
    for (unsigned i = 0; i < 9; ++i) reader.Bool();

    // CvUnit.h:1407-1413, members124-129: TacticalAIMoveTypes, capturing
    // PlayerTypes, leader UnitTypes, InvisibleTypes x2, great-person directive.
    reader.Fixed(6, 4);

    // CvUnit.h:1424-1425, members130-131. Both CvStrings remain on the
    // wire, including the obsolete name member. Each has a uint32 byte
    // length followed by opaque bytes; there is no NUL terminator or hash.
    reader.String();
    reader.String();

    // CvUnit.h:1431-1440, members132-141, in declaration order: terrain/
    // feature double-move, terrain/feature impassable, terrain attack/defense,
    // feature attack/defense, unit-combat modifier, unit-class modifier.
    // FAutoVector serializes its vector value, without delta commands. The
    // original x86 generic count is uint32; the current port's checked-u32
    // generic codec preserves that width (FStlContainerSerialization.h:71).
    for (unsigned table = 0; table < 10; ++table) {
        const auto entries = reader.Count(4);
        reader.Fixed(entries, 4);
    }

    // CvUnit.h:1442-1448, members142-147: mission-AI x/y, MissionAITypes,
    // ActivityTypes, AutomateTypes, UnitAITypes. Raw members between these
    // declarations (mission timer/IDInfo) are outside the automatic archive.
    reader.Fixed(6, 4);
    result.whole = reader.SpanFrom(start);
    result.nextInflatedOffset = reader.Pos();
    result.arrayRecords = reader.Records() - records;
    return result;
}

} // namespace RetailStateDetail
} // namespace ZeroSisHost
