// Exact retained CvPlayerTraits::Write bodies with actual SDK stream/enum/STL
// codecs. Generated declarations keep real std::vector size_type; only the
// FreeTraitUnits FStaticVector uses an explicitly reported uint-size shim.
// Database type hashing is TestHooks only; no ruleset or restore is validated.
#include "SdkStreamIncludes.h"
#ifdef _WIN64
#include "../Source/Porting/CvCheckedNarrow.h"
#include "../Source/Host/RetailSavePlayerTraits.h"
#endif
#include <hash_map>
#include <CvEnums.h>
#include <CvGameCoreEnums.h>
#include <CvEnumSerialization.h>
#include <FireWorks/FStlContainerSerialization.h>
#include <stdexcept>

namespace TestHooks {
bool WriteHashed(FDataStream& stream, TerrainTypes type) {
    const unsigned int i = static_cast<unsigned int>(type);
    stream << (i == 1u ? 0u : 0xa1000000u | i);
    return i != 1u;
}
bool WriteHashed(FDataStream& stream, ResourceTypes type) {
    const unsigned int i = static_cast<unsigned int>(type);
    stream << (i == 1u ? 0u : 0xb2000000u | i);
    return i != 1u;
}
}

// Supplies exact source declarations/bodies and authenticated preflight lines.
#include "SdkPlayerTraitsWriters.h"

namespace {
typedef std::vector<unsigned char> Bytes;
struct Checks {
    unsigned long count;
    Checks() : count(0) {}
    void Require(bool value, const char* message) {
        ++count;
        if (!value) throw std::runtime_error(message);
    }
};
struct Counts {
    unsigned int maya, noTrain, luxury, resources, terrains, freeUnits, combat;
    unsigned int tables[3];
    explicit Counts(unsigned int kind) {
        maya = noTrain = luxury = resources = terrains = freeUnits = combat = 0;
        tables[0] = tables[1] = tables[2] = 0;
        if (kind == 1) {
            maya = noTrain = luxury = resources = terrains = freeUnits = combat = 1;
            tables[0] = tables[1] = tables[2] = 1;
        } else if (kind == 2) {
            maya = 3; noTrain = 7; luxury = 4; resources = 4; terrains = 3;
            freeUnits = 6; combat = 3;
            tables[0] = 2; tables[1] = 3; tables[2] = 4;
        }
    }
};
struct Offsets {
    std::size_t maya, noTrain, freeUnits, luxury, end;
    Offsets() : maya(0), noTrain(0), freeUnits(0), luxury(0), end(0) {}
};
int Value(unsigned int seed, unsigned int index) {
    const int value = static_cast<int>(0x102000u + seed * 0x100u + index * 17u);
    return index & 1u ? -value : value;
}
bool Flag(unsigned int seed, unsigned int index) {
    return (seed + index * 3u) % 7u < 3u;
}
void Append32(Bytes& out, unsigned int value) {
    for (unsigned int i = 0; i < 4; ++i)
        out.push_back(static_cast<unsigned char>(value >> (8 * i)));
}
void AppendCount(Bytes& out, unsigned int value, unsigned int width) {
    Append32(out, value);
    if (width == 8u) Append32(out, 0u);
}
void AppendFlag(Bytes& out, bool value) { out.push_back(value ? 1u : 0u); }
unsigned int WordAt(const Bytes& data, std::size_t offset) {
    return static_cast<unsigned int>(data[offset]) |
        static_cast<unsigned int>(data[offset + 1]) << 8 |
        static_cast<unsigned int>(data[offset + 2]) << 16 |
        static_cast<unsigned int>(data[offset + 3]) << 24;
}

template<class Traits> void Fill(Traits& obj, const Counts& n, unsigned int seed) {
    unsigned int scalar = 0;
#define SET_INT(Name) obj.Name = Value(seed, scalar++);
    SDK_TRAITS_INT_MEMBERS(SET_INT)
#undef SET_INT
    unsigned int flag = 0;
#define SET_BOOL(Name) obj.Name = Flag(seed, flag++);
    SDK_TRAITS_BOOL_MEMBERS(SET_BOOL)
#undef SET_BOOL
    obj.m_iBaktunPreviousTurn = Value(seed, 65);
    obj.m_eCampGuardType = static_cast<UnitTypes>(Value(seed, 66));
    obj.m_eCombatBonusImprovement = static_cast<ImprovementTypes>(Value(seed, 67));
    obj.m_aMayaBonusChoices.clear();
    for (unsigned int i = 0; i < n.maya; ++i) {
        MayaBonusChoice choice;
        choice.m_eUnitType = static_cast<UnitTypes>(Value(seed, 80u + i));
        choice.m_iBaktunJustFinished = Value(seed, 90u + i);
        obj.m_aMayaBonusChoices.push_back(choice);
    }
    int* yields[7] = { obj.m_iExtraYieldThreshold, obj.m_iFreeCityYield,
        obj.m_iYieldChangeStrategicResources, obj.m_iYieldRateModifier,
        obj.m_iYieldChangeNaturalWonder, obj.m_iYieldChangePerTradePartner,
        obj.m_iYieldChangeIncomingTradeRoute };
    for (unsigned int a = 0; a < 7; ++a)
        for (unsigned int y = 0; y < 6; ++y)
            yields[a][y] = Value(seed, 200u + a * 6u + y);
    for (unsigned int i = 0; i < static_cast<unsigned int>(NUM_TERRAIN_TYPES); ++i)
        obj.m_iStrategicResourceQuantityModifier[i] = Value(seed, 310u + i);
    obj.m_aiResourceQuantityModifier.resize(n.resources);
    for (unsigned int i = 0; i < n.resources; ++i)
        obj.m_aiResourceQuantityModifier[i] = Value(seed, 330u + i);
    obj.m_abNoTrain.clear();
    for (unsigned int i = 0; i < n.noTrain; ++i) obj.m_abNoTrain.push_back(Flag(seed, 40u + i));
    obj.m_aFreeTraitUnits.clear();
    for (unsigned int i = 0; i < n.freeUnits; ++i) {
        FreeTraitUnit unit;
        unit.m_iFreeUnit = static_cast<UnitTypes>(Value(seed, 100u + i));
        unit.m_ePrereqTech = static_cast<TechTypes>(Value(seed, 110u + i));
        obj.m_aFreeTraitUnits.push_back(unit);
    }
    obj.m_paiMovesChangeUnitCombat.resize(n.combat);
    obj.m_paiMaintenanceModifierUnitCombat.resize(n.combat);
    for (unsigned int i = 0; i < n.combat; ++i) {
        obj.m_paiMovesChangeUnitCombat[i] = Value(seed, 350u + i);
        obj.m_paiMaintenanceModifierUnitCombat[i] = Value(seed, 370u + i);
    }
    std::vector< Firaxis::Array<int, NUM_YIELD_TYPES> >* tables[3] = {
        &obj.m_ppaaiImprovementYieldChange, &obj.m_ppaaiSpecialistYieldChange,
        &obj.m_ppaaiUnimprovedFeatureYieldChange };
    for (unsigned int a = 0; a < 3; ++a) {
        tables[a]->resize(n.tables[a]);
        for (unsigned int r = 0; r < n.tables[a]; ++r)
            for (unsigned int y = 0; y < 6; ++y)
                (*tables[a])[r][y] = Value(seed, 400u + a * 60u + r * 6u + y);
    }
    obj.m_aUniqueLuxuryAreas.resize(n.luxury);
    for (unsigned int i = 0; i < n.luxury; ++i)
        obj.m_aUniqueLuxuryAreas[i] = Value(seed, 700u + i);
}

Bytes Oracle(const Counts& n, unsigned int seed, unsigned int directWidth, Offsets& offsets) {
    Bytes out;
    Append32(out, 19u);
    for (unsigned int i = 0; i < 65; ++i) Append32(out, static_cast<unsigned int>(Value(seed, i)));
    for (unsigned int i = 0; i < 14; ++i) AppendFlag(out, Flag(seed, i));
    Append32(out, static_cast<unsigned int>(Value(seed, 65)));
    offsets.maya = out.size();
    AppendCount(out, n.maya, directWidth);
    for (unsigned int i = 0; i < n.maya; ++i) {
        Append32(out, static_cast<unsigned int>(Value(seed, 80u + i)));
        Append32(out, static_cast<unsigned int>(Value(seed, 90u + i)));
    }
    for (unsigned int i = 14; i < 19; ++i) AppendFlag(out, Flag(seed, i));
    Append32(out, static_cast<unsigned int>(Value(seed, 66)));
    Append32(out, static_cast<unsigned int>(Value(seed, 67)));
    for (unsigned int a = 0; a < 7; ++a)
        for (unsigned int y = 0; y < 6; ++y)
            Append32(out, static_cast<unsigned int>(Value(seed, 200u + a * 6u + y)));
    const unsigned int hashes[2] = { n.terrains, n.resources };
    for (unsigned int a = 0; a < 2; ++a) {
        Append32(out, hashes[a]);
        for (unsigned int i = 0; i < hashes[a]; ++i) {
            Append32(out, i == 1u ? 0u : (a == 0 ? 0xa1000000u : 0xb2000000u) | i);
            if (i != 1u) Append32(out, static_cast<unsigned int>(Value(seed, (a == 0 ? 310u : 330u) + i)));
        }
    }
    offsets.noTrain = out.size();
    AppendCount(out, n.noTrain, directWidth);
    for (unsigned int i = 0; i < n.noTrain; ++i) AppendFlag(out, Flag(seed, 40u + i));
    offsets.freeUnits = out.size();
    Append32(out, n.freeUnits);
    for (unsigned int i = 0; i < n.freeUnits; ++i) {
        Append32(out, static_cast<unsigned int>(Value(seed, 100u + i)));
        Append32(out, static_cast<unsigned int>(Value(seed, 110u + i)));
    }
    Append32(out, n.combat);
    for (unsigned int i = 0; i < n.combat; ++i) Append32(out, static_cast<unsigned int>(Value(seed, 350u + i)));
    for (unsigned int i = 0; i < n.combat; ++i) Append32(out, static_cast<unsigned int>(Value(seed, 370u + i)));
    for (unsigned int a = 0; a < 3; ++a) {
        Append32(out, n.tables[a]);
        for (unsigned int r = 0; r < n.tables[a]; ++r)
            for (unsigned int y = 0; y < 6; ++y)
                Append32(out, static_cast<unsigned int>(Value(seed, 400u + a * 60u + r * 6u + y)));
    }
    offsets.luxury = out.size();
    Append32(out, n.luxury);
    for (unsigned int i = 0; i < n.luxury; ++i) Append32(out, static_cast<unsigned int>(Value(seed, 700u + i)));
    offsets.end = out.size();
    return out;
}

void Read32(Checks& c, FDataStream& stream, unsigned int expected) {
    int value = 0; stream >> value;
    c.Require(static_cast<unsigned int>(value) == expected, "Actual SDK int32 reader differs");
}
void ReadBool(Checks& c, FDataStream& stream, bool expected) {
    bool value = !expected; stream >> value;
    c.Require(value == expected, "Actual SDK bool reader differs");
}
void ReadCount(Checks& c, FDataStream& stream, unsigned int expected, unsigned int width) {
    Read32(c, stream, expected);
    if (width == 8u) Read32(c, stream, 0u);
}
void ReadBoundary(Checks& c, FMemoryStream& stream, const Counts& n, unsigned int seed, unsigned int width) {
    stream.Rewind();
    Read32(c, stream, 0x7123ab45u);
    Read32(c, stream, 19u);
    for (unsigned int i = 0; i < 65; ++i) Read32(c, stream, static_cast<unsigned int>(Value(seed, i)));
    for (unsigned int i = 0; i < 14; ++i) ReadBool(c, stream, Flag(seed, i));
    Read32(c, stream, static_cast<unsigned int>(Value(seed, 65)));
    ReadCount(c, stream, n.maya, width);
    for (unsigned int i = 0; i < n.maya; ++i) {
        UnitTypes unit = NO_UNIT; stream >> unit;
        c.Require(static_cast<int>(unit) == Value(seed, 80u + i), "Actual SDK Maya enum codec differs");
        Read32(c, stream, static_cast<unsigned int>(Value(seed, 90u + i)));
    }
    for (unsigned int i = 14; i < 19; ++i) ReadBool(c, stream, Flag(seed, i));
    UnitTypes guard = NO_UNIT; stream >> guard;
    ImprovementTypes improvement = NO_IMPROVEMENT; stream >> improvement;
    c.Require(static_cast<int>(guard) == Value(seed, 66) && static_cast<int>(improvement) == Value(seed, 67),
        "Actual SDK trailing enum codecs differ");
    for (unsigned int a = 0; a < 7; ++a)
        for (unsigned int y = 0; y < 6; ++y) Read32(c, stream, static_cast<unsigned int>(Value(seed, 200u + a * 6u + y)));
    const unsigned int hashes[2] = { n.terrains, n.resources };
    for (unsigned int a = 0; a < 2; ++a) {
        Read32(c, stream, hashes[a]);
        for (unsigned int i = 0; i < hashes[a]; ++i) {
            Read32(c, stream, i == 1u ? 0u : (a == 0 ? 0xa1000000u : 0xb2000000u) | i);
            if (i != 1u) Read32(c, stream, static_cast<unsigned int>(Value(seed, (a == 0 ? 310u : 330u) + i)));
        }
    }
    ReadCount(c, stream, n.noTrain, width);
    for (unsigned int i = 0; i < n.noTrain; ++i) ReadBool(c, stream, Flag(seed, 40u + i));
    Read32(c, stream, n.freeUnits);
    for (unsigned int i = 0; i < n.freeUnits; ++i) {
        UnitTypes unit = NO_UNIT; TechTypes tech = NO_TECH; stream >> unit >> tech;
        c.Require(static_cast<int>(unit) == Value(seed, 100u + i) && static_cast<int>(tech) == Value(seed, 110u + i),
            "Actual SDK free-unit enum codecs differ");
    }
    Read32(c, stream, n.combat);
    for (unsigned int i = 0; i < n.combat; ++i) Read32(c, stream, static_cast<unsigned int>(Value(seed, 350u + i)));
    for (unsigned int i = 0; i < n.combat; ++i) Read32(c, stream, static_cast<unsigned int>(Value(seed, 370u + i)));
    for (unsigned int a = 0; a < 3; ++a) {
        Read32(c, stream, n.tables[a]);
        for (unsigned int r = 0; r < n.tables[a]; ++r)
            for (unsigned int y = 0; y < 6; ++y) Read32(c, stream, static_cast<unsigned int>(Value(seed, 400u + a * 60u + r * 6u + y)));
    }
    Read32(c, stream, n.luxury);
    for (unsigned int i = 0; i < n.luxury; ++i) Read32(c, stream, static_cast<unsigned int>(Value(seed, 700u + i)));
    Read32(c, stream, 0xd3c2b1a0u);
    c.Require(stream.AtEnd() && stream.GetPosition() == stream.GetEOF(), "Full actual SDK reader missed trailing boundary");
}

template<class Traits> std::vector<Bytes> Family(Checks& c, unsigned int width, const char* name) {
    std::vector<Bytes> wires;
    for (unsigned int kind = 0; kind < 3; ++kind) {
        const Counts n(kind); const unsigned int seed = kind + 1u;
        c.Require(n.terrains <= static_cast<unsigned int>(NUM_TERRAIN_TYPES), "Terrain fixture exceeds actual SDK fixed array");
        GC.terrains = static_cast<int>(n.terrains); GC.combat = static_cast<int>(n.combat);
        Traits obj; Fill(obj, n, seed);
        Offsets offsets; const Bytes body = Oracle(n, seed, width, offsets);
        c.Require(offsets.maya == 282u, "Independent Maya count offset changed");
        if (kind == 0) c.Require(body.size() == (width == 4u ? 503u : 511u), "Literal full empty extent changed");
        FMemoryStream stream; stream << 0x7123ab45u;
        obj.Write(stream);
        c.Require(stream.GetEOF() == body.size() + 4u && stream.GetPosition() == stream.GetEOF(), "Full writer extent mismatch");
        Bytes expected; Append32(expected, 0x7123ab45u); expected.insert(expected.end(), body.begin(), body.end());
        stream << 0xd3c2b1a0u; Append32(expected, 0xd3c2b1a0u);
        c.Require(stream.GetEOF() == expected.size() && std::memcmp(stream.GetBuf(), &expected[0], expected.size()) == 0,
            "Full exact SDK writer/count/payload/canary differs from literal oracle");
        ReadBoundary(c, stream, n, seed, width);
        const unsigned char* actual = reinterpret_cast<const unsigned char*>(stream.GetBuf());
        Bytes wire(actual, actual + stream.GetEOF()); wires.push_back(wire);
#ifdef _WIN64
        // Consume only the exact writer body, excluding both independent
        // canaries. This connects actual SDK output to the production reader.
        bool exactProductionBoundary = false;
        try {
            const ZeroSisHost::RetailSaveStateLimits limits;
            ZeroSisHost::RetailStateDetail::Reader input(&wire[4], body.size(), limits);
            ZeroSisHost::RetailStateDetail::ReadPlayerTraits(input);
            exactProductionBoundary = input.Pos() == body.size();
        } catch (const ZeroSisHost::RetailStateError&) {}
        c.Require(width == 4u ? exactProductionBoundary : !exactProductionBoundary,
            "Production Traits reader did not distinguish canonical/legacy full-wire boundaries");
#endif
        char filename[96]; std::sprintf(filename, "%s_case_%u.bin", name, kind);
        FILE* file = std::fopen(filename, "wb"); c.Require(file != NULL, "Cannot save owned wire fixture");
        const std::size_t written = std::fwrite(&wire[0], 1, wire.size(), file);
        c.Require(std::fclose(file) == 0 && written == wire.size(), "Short owned wire fixture output");
        if (width == 8u) {
            Offsets canonicalOffsets; const Bytes canonical = Oracle(n, seed, 4u, canonicalOffsets);
            c.Require(wire.size() == canonical.size() + 16u, "Legacy width expansion is not exactly two words");
            c.Require(WordAt(body, offsets.maya + 4u) == 0u && WordAt(canonical, canonicalOffsets.maya + 4u) != 0u,
                "Maya int32 reader negative control lacks an observable mismatch");
            // Seek by the independently accumulated NoTrain boundary. A signed
            // int reader consumes four bytes, leaving the unwanted upper word.
            if (kind != 0u)
                c.Require(WordAt(body, offsets.noTrain + 4u) == 0u &&
                    WordAt(canonical, canonicalOffsets.noTrain + 4u) != 0u,
                    "NoTrain int32 reader negative control lacks an observable mismatch");
        }
    }
    return wires;
}

#ifdef _WIN64
unsigned int OverflowPreflights(Checks& c) {
    const std::size_t excessive[3] = { static_cast<std::size_t>(INT_MAX) + 1u,
        static_cast<std::size_t>(UINT_MAX), (std::numeric_limits<std::size_t>::max)() };
    unsigned int rejected = 0;
    for (unsigned int which = 0; which < 3; ++which) {
        for (unsigned int value = 0; value < 3; ++value) {
            TraitsPreflightProbe probe;
            probe.m_aMayaBonusChoices.declared = which == 0 ? excessive[value] : 0u;
            probe.m_abNoTrain.declared = which == 1 ? excessive[value] : 0u;
            probe.m_aUniqueLuxuryAreas.declared = which == 2 ? excessive[value] : 0u;
            FMemoryStream stream; stream << 0x192a3b4cu;
            const unsigned int before = stream.GetEOF(); bool threw = false;
            try { probe.Write(stream); } catch (const std::range_error&) { threw = true; }
            c.Require(threw, "Actual extracted int32 preflight accepted an oversized size_t");
            c.Require(stream.GetEOF() == before && stream.GetPosition() == before,
                "Preflight rejection appended or rewound existing output");
            c.Require(std::memcmp(stream.GetBuf(), "\x4c\x3b\x2a\x19", 4) == 0, "Preflight modified existing canary bytes");
            ++rejected;
        }
    }
    TraitsPreflightProbe inclusive;
    inclusive.m_aMayaBonusChoices.declared = inclusive.m_abNoTrain.declared =
        inclusive.m_aUniqueLuxuryAreas.declared = static_cast<std::size_t>(INT_MAX);
    FMemoryStream stream; inclusive.Write(stream);
    c.Require(stream.GetEOF() == 12u, "Inclusive INT_MAX preflight output width differs");
    stream.Rewind(); for (unsigned int i = 0; i < 3; ++i) Read32(c, stream, INT_MAX);
    return rejected;
}
#endif
}

int main(int argc, char** argv) {
    try {
        Checks checks;
        typedef char Int32Required[sizeof(int) == 4 ? 1 : -1]; (void)sizeof(Int32Required);
        typedef char SixYieldsRequired[NUM_YIELD_TYPES == 6 ? 1 : -1]; (void)sizeof(SixYieldsRequired);
#ifdef _WIN64
        checks.Require(argc == 2 && std::strcmp(argv[1], "--x64") == 0, "Expected isolated x64 test mode");
        const std::vector<Bytes> canonical = Family<CandidateWriter::CvPlayerTraits>(checks, 4u, "canonical");
        const std::vector<Bytes> legacy = Family<Legacy64Writer::CvPlayerTraits>(checks, 8u, "legacy64");
        checks.Require(canonical.size() == legacy.size(), "Missing negative-control family");
        for (std::size_t i = 0; i < canonical.size(); ++i) checks.Require(canonical[i] != legacy[i], "Legacy64 unexpectedly matches canonical full wire");
        const unsigned int rejections = OverflowPreflights(checks);
#else
        checks.Require(argc == 2 && std::strcmp(argv[1], "--x86original") == 0, "Expected archived x86 test mode");
        Family<OriginalWriter::CvPlayerTraits>(checks, 4u, "canonical");
        const unsigned int rejections = 0;
#endif
        std::printf("{\"status\":\"PASS_SDK_PLAYER_TRAITS_COUNT\",\"checks\":%lu,\"canonical_direct_count_bytes\":4,"
            "\"legacy64_direct_count_bytes\":%u,\"oversized_preflight_rejections\":%u,\"synthetic_cases\":3,"
            "\"full_writer_body_extracted\":true,\"first_scalar_ints\":65,\"scalar_bools\":19,"
            "\"production_reader_cases\":%u,\"legacy_exact_boundaries_rejected\":%u,"
            "\"hash_resolution_test_hooks_only\":true,\"free_trait_uint_size_shim\":true,"
            "\"gamecore_loaded\":false,\"window_created\":false,\"user_saves_accessed\":false,"
            "\"complete_save_validated\":false,\"ruleset_compatibility_verified\":false,\"restore_approved\":false}\n",
            checks.count,
#ifdef _WIN64
            8u,
#else
            0u,
#endif
            rejections,
#ifdef _WIN64
            3u, 3u
#else
            0u, 0u
#endif
        );
        return 0;
    } catch (const std::exception& error) {
        std::fprintf(stderr, "PlayerTraits component failure: %s\n", error.what());
        return 1;
    }
}
