#pragma once

// Original CvDiplomacyAI.cpp:1527-1747, current Write version 4 only.
// The corresponding port Write and both log-record Write bodies are identical.
// This frames one nested state, without validating enum IDs or restoring it.
#include "RetailSaveStateWire.h"
#include <cstddef>

namespace ZeroSisHost {
namespace RetailStateDetail {

constexpr std::size_t PlayerDiplomacyAIMinimumBytes = 71856u;

inline void ReadPlayerDiplomacyBoolArray(Reader& reader, std::size_t count) {
    for (std::size_t i = 0; i < count; ++i) reader.Bool();
}

inline void ReadPlayerDiplomacyAI(Reader& reader) {
    // CvDLLUtilDefines.h:22-28: serialized widths are 22 major, 41 minor,
    // and 63 civilization players, even where backing storage permits 80.
    // FDataStream.h:500-510 writes ArrayWrapper elements without a count.
    constexpr std::size_t major = 22u;
    constexpr std::size_t minor = 41u;
    constexpr std::size_t civ = 63u;
    constexpr std::size_t logEntries = 60u; // CvDiplomacyAI.h:39.
    reader.Version(4);

    reader.Fixed(major, 1); // 1535: major opinions are raw char, not bool.
    for (std::size_t row = 0; row < major; ++row) {
        // 1539-1543: retain each row's char/bool/short/char/short order.
        reader.Fixed(major, 1);
        ReadPlayerDiplomacyBoolArray(reader, major);
        reader.Fixed(major, 2);
        reader.Fixed(major, 1);
        reader.Fixed(major, 2);
    }
    reader.Fixed(major, 1); // 1546: major approach.
    reader.Fixed(minor, 1); // 1547: minor approach.
    reader.Fixed(major * 2u, 1); // 1548-1549: approach guesses/counters.
    reader.Fixed(civ, 2); // 1551: wonders beaten to.
    ReadPlayerDiplomacyBoolArray(reader, civ); // 1552: mustering attack.
    ReadPlayerDiplomacyBoolArray(reader, major); // 1554: research agreement.
    ReadPlayerDiplomacyBoolArray(reader, minor); // 1555: minor route.
    reader.Fixed(civ, 2); // 1557: want-peace counters.
    reader.Fixed(major * 2u, 1); // 1558-1559: peace offer/accept raw chars.
    reader.Fixed(civ * 5u, 1); // 1561-1565: war face/state/projections/goal.
    reader.Fixed(civ * 2u, 2); // 1566-1567: turns at war and wars fought.
    reader.Fixed(civ * 8u, 1); // 1569-1577: strengths, target, five disputes.

    for (std::size_t row = 0; row < civ; ++row) {
        // 1581-1587: three char rows, an int row, then a char row.
        reader.Fixed(civ * 3u, 1);
        reader.Fixed(civ, 4);
        reader.Fixed(civ, 1);
    }
    for (std::size_t row = 0; row < civ; ++row) {
        // 1593-1594: per-row lost value followed by strict bool flags.
        reader.Fixed(civ, 4);
        ReadPlayerDiplomacyBoolArray(reader, civ);
    }
    reader.Fixed(civ, 1); // 1597: war damage.
    reader.Fixed(civ, 4); // 1598: war value lost.
    reader.Fixed(civ * 6u, 1); // 1600-1607: four postures, two threats.

    ReadPlayerDiplomacyBoolArray(reader, major); // 1609: no-settle accepted.
    reader.Fixed(major, 2); // 1610: no-settle counters.
    ReadPlayerDiplomacyBoolArray(reader, major); // 1612: stop-spying accepted.
    reader.Fixed(major, 2); // 1613: stop-spying counters.
    reader.Fixed(major * 2u, 2); // 1615-1616: demand counters.
    ReadPlayerDiplomacyBoolArray(reader, major); // 1618: friendship accepted.
    reader.Fixed(major, 2); // 1619: friendship counters.
    ReadPlayerDiplomacyBoolArray(reader, major * 2u); // 1621-1622: denunciations.
    reader.Fixed(major, 2); // 1623: denunciation counters.
    ReadPlayerDiplomacyBoolArray(reader, major); // 1624: friend's war declaration.
    // 1626-1648: eighteen consecutive short[22] histories/values, including
    // landmarks (v4) and archaeology (v2); older layouts are not accepted.
    reader.Fixed(major * 18u, 2);

    ReadPlayerDiplomacyBoolArray(reader, major * 3u); // 1650-1652: military promises.
    reader.Fixed(major, 2); // 1653: military-promise counter.
    reader.Fixed(major, 2); // 1655: expansion-promise turn.
    ReadPlayerDiplomacyBoolArray(reader, major * 2u); // 1656-1657: broken/ignored.
    reader.Fixed(major, 1); // 1658: expansion-promise raw char data.
    reader.Fixed(major, 2); // 1660: border-promise turn.
    ReadPlayerDiplomacyBoolArray(reader, major * 2u); // 1661-1662: broken/ignored.
    reader.Fixed(major, 1); // 1663: border-promise raw char data.
    // 1665-1691: 21 consecutive bool[22] arrays: attack/bully/spy promises
    // (3 each), forgiveness (1), conversion/digging (5 each), coop-war (1).
    ReadPlayerDiplomacyBoolArray(reader, major * 21u);

    reader.Skip(1); // 1693; CvDiplomacyAI.h:1342 declares demand target as char.
    reader.Bool(); // 1694: demand ready.
    reader.Fixed(13u, 4); // 1696-1708: personality int fields, h:1488-1500.
    // 1710-1711; CvDiplomacyAIEnums.h:28-53 defines seven/five approaches.
    reader.Fixed(7u, 1);
    reader.Fixed(5u, 1);

    reader.Fixed(major, 2); // 1713: attacked-protected-minor turns.
    reader.Fixed(major * 2u, 1); // 1714-1715: attacked minor/count raw chars.
    reader.Fixed(major, 2); // 1717: killed-protected-minor turns.
    reader.Fixed(major * 2u, 1); // 1718-1719: killed minor/count raw chars.
    reader.Fixed(major, 1); // 1721: protected minors bullied.
    reader.Fixed(major, 2); // 1723: sided-with-minor turns.
    reader.Fixed(major * 4u, 1); // 1725-1728: attacked/conquered minors/majors.
    reader.Fixed(major, 4); // 1730: warmonger amounts.
    reader.Fixed(major * 6u, 2); // 1732-1738: five proposal histories, liberation.

    // 1740-1742 and 26192-26196: 22 rows of 60 records, each a signed
    // 32-bit DiploStatementTypes (Enums.h:280-283) followed by an int turn.
    reader.Fixed(major * logEntries, 8);
    // 1745 and 26206-26214: public-declaration enum, data1, data2, PlayerTypes,
    // bool active, int turn: 21 wire bytes, with no C++ structure padding.
    // PublicDeclarationTypes is explicitly int32 (Enums.h:330-333).
    // PlayerTypes uses the original SDK's 4-byte enum codec, confirmed by
    // evidence/serialization/candidate/conformance.json and SdkEnumTypes.inc;
    // that codec's one-byte exception is GameTypes, absent from this state.
    for (std::size_t i = 0; i < logEntries; ++i) {
        reader.Fixed(4u, 4);
        reader.Bool();
        reader.I32();
    }
    reader.I32(); // 1746: StateAllWars, explicit int32 (Enums.h:235-238).
}

} // namespace RetailStateDetail
} // namespace ZeroSisHost
