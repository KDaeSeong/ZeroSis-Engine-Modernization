// Reuse the independent SDK Game-prefix fixture writer without copying its
// source or running the preceding component's main/test suite.
#define main RetailSaveStateFixtureMain
#include "retail_save_state.cpp"
#undef main
#include "../Source/Host/RetailSaveMap.h"

namespace {
// Authority: CvPlot::write/read, CvArea::write, CvLandmass::write,
// BuildArrayHelpers::Write, ImprovementArrayHelpers::Write, and the fixed-array
// FDataStream operators in the retained Expansion2 SDK. The auxiliary Go parser
// stops after MapHeader and is not an oracle for this component.
struct MapFixture {
    Fixture wire;
    std::size_t prefixEnd = 0, mapStart = 0, plotStart = 0, plotBytes = 0;
    std::size_t areaStart = 0, areaBytes = 0, landStart = 0, landBytes = 0, next = 0;
    std::uint32_t plots = 0, areas = 0, landmasses = 0;
};

class MapWire {
public:
    Wire w;
    MapFixture result;
    explicit MapWire(std::uint32_t awards, bool rich) : w(awards, rich) {
        // Game is deliberately the independent minimal profile. Map fixtures
        // then replace its unknown suffix, preserving the original Game bytes.
        w.f = Wire(awards, false).Finish();
        w.f.rich = rich;
        w.f.bytes.resize(w.f.next);
        result.prefixEnd = w.Pos(); result.mapStart = w.f.mapStart;
        result.plots = rich ? 2u : 1u;
        PutU32(w.f.bytes, w.f.marks.at("map.width"), result.plots);
        PutU32(w.f.bytes, w.f.marks.at("map.height"), 1);
    }
    void Shorts(std::size_t count, std::uint16_t seed = 0x8001) {
        for (std::size_t i = 0; i < count; ++i) w.U16(static_cast<std::uint16_t>(seed + i));
    }
    void Plot(unsigned int index) {
        const auto name = "plot" + std::to_string(index);
        const bool auxiliary = w.f.rich && index == 0;
        w.MarkAt(name + ".start"); w.Version(name, 7);
        w.U16(static_cast<std::uint16_t>(index)); w.U16(0); // x/y are short.
        w.I32(w.f.rich ? 8192 : -1); w.U8(0xff); // Area and feature variety.
        Shorts(4); // Ownership, improvement, upgrade and culture are short.
        for (unsigned int i = 0; i < 5; ++i) w.U8(static_cast<unsigned char>(0x80u + i));
        w.U8(0xff); Shorts(2); w.I32(-1); // Builder player/turn/value/RouteTypes.
        w.I32(w.f.rich ? 8192 : -1); w.U32(0x789cffff); // Landmass and route flags.
        for (unsigned int i = 0; i < 12; ++i) w.Bool(name + ".flag" + std::to_string(i), i % 2 != 0);
        w.U8(0xff); w.U8(2); w.U8(0xff); // Raw char owner/plot/terrain.
        w.Words(4, 0); // Feature/resource/improvement/construction hashes: always four bytes each.
        for (unsigned int i = 0; i < 10; ++i) w.U8(static_cast<unsigned char>(0xf0u + i));
        w.Words(10); // Five city IDInfo records have int32 owner + ID.
        Shorts(6); w.Words(80); // Yield shorts and all eighty found values.
        for (unsigned int i = 0; i < 80; ++i) w.U8(static_cast<unsigned char>(0x80u + i));
        Shorts(80); // Signed visibility shorts, including values the SDK clamps after reading.
        for (unsigned int i = 0; i < 80; ++i) w.U8(static_cast<unsigned char>(0xffu - i));
        w.U8(0xa5); w.Words(4, 0x80ffff00); // River byte + four raw DWORD bitset words.
        for (unsigned int i = 0; i < 80; ++i) w.Bool(name + ".reveal" + std::to_string(i), i % 3 == 0);
        for (unsigned int i = 0; i < 80; ++i) w.U32(i % 3 == 0 ? 0u : (i % 3 == 1 ? 0xffffffffu : 0x12345678u));
        Shorts(80); // Revealed route values are short, rather than RouteTypes operators.
        for (unsigned int i = 0; i < 22; ++i) w.Bool(name + ".no_settle" + std::to_string(i), i % 2 != 0);
        w.MarkAt(name + ".has_script");
        w.Bool(name + ".has_script", auxiliary);
        if (auxiliary) {
            // Embedded NUL and plausible next-record words cannot terminate a string.
            w.String(name + ".script", Wire::Text() + std::string("\x01\0\0\0\x02\0\0\0\x01\0\0\0", 12));
        }
        // This outer count is a presence/allocation field, not the inner list
        // length. Distinct positive values must not be forced equal.
        w.Count(name + ".build_outer", auxiliary ? 2u : 0u, true);
        if (auxiliary) {
            w.Count(name + ".build_inner", 3, true);
            w.U32(0); // No short follows a zero hash.
            w.U32(0xffffffffu); w.U16(0x8001); // A nonzero Build hash still has a short.
            w.U32(0x12345678u); w.U16(0x7ffe);
        }
        Shorts(80); // Fixed short[80][1], without row/column count words.
        w.Count(name + ".units", auxiliary ? 3u : 0u);
        if (auxiliary) { w.I32(0); w.I32(13); w.I32(1); w.I32(14); w.I32(-1); w.I32(-1); }
        w.U8(0xfe); // Raw continent char, not a bool.
        w.Version(name + ".archaeology", 2); w.Words(5);
        w.MarkAt(name + ".end");
    }
    void Area(const std::string& name, std::int32_t id) {
        w.Version(name, 1); w.MarkAt(name + ".id"); w.I32(id); w.Words(9); w.Words(4);
        w.Bool(name + ".water"); w.Bool(name + ".mountains", true);
        w.Words(5u * 80u); // Five arrays use REALLY_MAX_{PLAYERS,TEAMS}=80.
        w.Words(64u * 2u); // Target-city loop writes only MAX_PLAYERS=64 pairs.
        w.Words(64u * 6u); // Yield loop writes 64 rows, not the allocated 80.
        w.HashArray(name + ".resources", 1);
        w.Count(name + ".improvements", 4, true);
        w.U32(0); w.U32(0xffffffffu); // Both omit their value in this particular helper.
        w.U32(0x12345678u); w.I32(-1); w.U32(0x789c0001u); w.I32(7);
    }
    void Landmass(const std::string& name, std::int32_t id) {
        w.Version(name, 1); w.MarkAt(name + ".id"); w.I32(id); w.Words(3);
        w.Bool(name + ".water", true); w.U8(0x80); // Continent is a raw char.
    }
    void FreeList(const std::string& name, bool area) {
        w.Count(name + ".slots", w.f.rich ? 4u : 0u, true);
        w.MarkAt(name + ".last"); w.I32(w.f.rich ? 2 : -1);
        w.MarkAt(name + ".free_head"); w.I32(w.f.rich ? 1 : -1);
        w.MarkAt(name + ".free_count"); w.I32(w.f.rich ? 1 : 0);
        w.MarkAt(name + ".current_id"); w.I32(w.f.rich ? 24576 : 8192);
        if (w.f.rich) for (unsigned int i = 0; i < 4; ++i) {
            w.MarkAt(name + ".link" + std::to_string(i)); w.I32(-1);
        }
        w.Count(name + ".live", w.f.rich ? 2u : 0u, true);
        if (w.f.rich) {
            if (area) { Area(name + ".record0", 8192); Area(name + ".record2", 16386); }
            else { Landmass(name + ".record0", 8192); Landmass(name + ".record2", 16386); }
        }
    }
    MapFixture Finish() {
        result.plotStart = w.Pos();
        for (unsigned int i = 0; i < result.plots; ++i) Plot(i);
        result.plotBytes = w.Pos() - result.plotStart;
        result.areaStart = w.Pos(); FreeList("areas", true); result.areaBytes = w.Pos() - result.areaStart;
        result.landStart = w.Pos(); FreeList("landmasses", false); result.landBytes = w.Pos() - result.landStart;
        w.MarkAt("map.ai_hints"); w.I32(-1);
        result.next = w.Pos(); result.areas = w.f.rich ? 2u : 0u; result.landmasses = result.areas;
        w.f.next = result.next;
        for (unsigned int i = 0; i < 64; ++i) w.U8(static_cast<unsigned char>(0xd0u + i % 16));
        result.wire = std::move(w.f);
        return std::move(result);
    }
};

RetailSaveMapInspection MapInspect(const MapFixture& f, const RetailSaveStateLimits& limits = {}) {
    return RetailSaveMap::InspectGameAndMap(f.wire.bytes, RetailSaveStateProfile(f.wire.awards), limits);
}
void MapInvariants(Suite& suite, const RetailSaveMapInspection& r, std::size_t size) {
    CheckInspection(suite, r.prefix, size);
    CheckSpan(suite, r.map, size, "Full Map"); CheckSpan(suite, r.plots, size, "Plots");
    CheckSpan(suite, r.areas, size, "Areas"); CheckSpan(suite, r.landmasses, size, "Landmasses");
    suite.Check(r.map.offset == r.prefix.mapHeader.offset && r.plots.offset == r.prefix.nextInflatedOffset,
        "Map/header/plot positions disagree");
    suite.Check(r.plots.offset + r.plots.bytes == r.areas.offset &&
        r.areas.offset + r.areas.bytes == r.landmasses.offset, "Map sections are not adjacent");
    suite.Check(r.landmasses.offset + r.landmasses.bytes + 4 == r.nextInflatedOffset,
        "Missing or misplaced final AI map hints");
    suite.Check(r.map.offset + r.map.bytes == r.nextInflatedOffset, "Wrong full Map end");
    suite.Check(r.plotCount == static_cast<std::uint64_t>(r.prefix.mapWidth) * r.prefix.mapHeight,
        "Map plot count does not match grid");
    suite.Check(r.arrayRecords >= r.prefix.arrayRecords, "Map lost prefix record accounting");
    suite.Check(!r.completeSaveVerified && !r.rulesetCompatibilityVerified, "Full Map framing approved an entire save");
}
void MapGolden(Suite& suite, const MapFixture& f) {
    const auto before = f.wire.bytes;
    const auto r = MapInspect(f); MapInvariants(suite, r, before.size());
    suite.Check(r.map.offset == f.mapStart && r.map.bytes == f.next - f.mapStart &&
        r.nextInflatedOffset == f.next, "Independent full Map boundary differs");
    suite.Check(r.plots.offset == f.plotStart && r.plots.bytes == f.plotBytes &&
        r.areas.offset == f.areaStart && r.areas.bytes == f.areaBytes &&
        r.landmasses.offset == f.landStart && r.landmasses.bytes == f.landBytes, "Independent Map subspan differs");
    suite.Check(r.plotCount == f.plots && r.areaCount == f.areas && r.landmassCount == f.landmasses,
        "Map record cardinality differs");
    suite.Check(r.arrayRecords == f.wire.records, "Independent full Map count accounting differs");
    if (!f.wire.rich) {
        // Fixed independent oracle: Map58 + Plot1569 + two empty free lists24
        // each + AI hints4. No variable payload contributes to these sizes.
        suite.Check(f.plotBytes == 1569 && f.areaBytes == 24 && f.landBytes == 24 &&
            r.map.bytes == 1679 && r.nextInflatedOffset == 6581, "Minimal fixed Map wire-size oracle differs");
    } else {
        // Each Area is 3718 fixed bytes + 20 resource + 24 improvement bytes;
        // free metadata is 24+4*4. Landmass has 22 fixed bytes per record.
        suite.Check(f.areaBytes == 7564 && f.landBytes == 84, "Rich fixed tail wire-size oracle differs");
        suite.Check(f.wire.marks.at("plot1.end") - f.wire.marks.at("plot1.start") == 1569,
            "Second plot has unexpected optional data or fixed widths");
    }
    const auto exact = RetailSaveMap::InspectGameAndMap(f.wire.bytes.data(), f.next, RetailSaveStateProfile(f.wire.awards));
    suite.Check(exact.nextInflatedOffset == f.next, "Exact Map prefix required an unparsed suffix");
    auto changed = before;
    std::fill(changed.begin() + f.next, changed.end(), static_cast<unsigned char>(0));
    suite.Check(RetailSaveMap::InspectGameAndMap(changed, RetailSaveStateProfile(f.wire.awards)).nextInflatedOffset == f.next,
        "Opaque following state affected Map framing");
    suite.Check(f.wire.bytes == before, "Map inspection modified input"); ++suite.syntheticCases;
}
void MapCuts(Suite& suite, const MapFixture& f) {
    const auto immutable = f.wire.bytes;
    // Previous state tests cover every Game-prefix truncation. This checks every
    // byte boundary from the first Map byte through its final AI-hints word.
    for (std::size_t cut = f.mapStart; cut < f.next; ++cut) {
        Expect(suite, Code::Truncated, cut, "Map prefix truncation", [&] {
            RetailSaveMap::InspectGameAndMap(f.wire.bytes.data(), cut, RetailSaveStateProfile(f.wire.awards));
        }); ++suite.truncations;
    }
    suite.Check(f.wire.bytes == immutable, "Map truncation testing modified input");
}
void MapRejectPatch(Suite& suite, const MapFixture& f, const std::string& name,
                    std::size_t at, std::uint32_t value, Code code, std::size_t minimumBytes = 0) {
    auto bytes = f.wire.bytes;
    if (bytes.size() < minimumBytes) bytes.resize(minimumBytes);
    PutU32(bytes, at, value);
    Expect(suite, code, bytes.size(), name, [&] {
        RetailSaveMap::InspectGameAndMap(bytes, RetailSaveStateProfile(f.wire.awards));
    });
}
void MapNegative(Suite& suite, const MapFixture& empty, const MapFixture& rich) {
    RetailSaveStateLimits limits;
    limits.maxInputBytes = rich.wire.bytes.size();
    suite.Check(MapInspect(rich, limits).nextInflatedOffset == rich.next, "Inclusive Map input budget failed");
    --limits.maxInputBytes;
    Expect(suite, Code::InputLimit, rich.wire.bytes.size(), "Short Map input budget", [&] { MapInspect(rich, limits); });
    limits = {}; limits.maxPrefixBytes = rich.next;
    suite.Check(MapInspect(rich, limits).nextInflatedOffset == rich.next, "Inclusive Map prefix budget failed");
    --limits.maxPrefixBytes;
    Expect(suite, Code::PrefixLimit, rich.wire.bytes.size(), "Short full Map prefix budget", [&] { MapInspect(rich, limits); });
    limits = {}; limits.maxStringBytes = rich.wire.maxString;
    suite.Check(MapInspect(rich, limits).nextInflatedOffset == rich.next, "Inclusive Plot script budget failed");
    --limits.maxStringBytes;
    Expect(suite, Code::StringLimit, rich.wire.bytes.size(), "Short Plot script budget", [&] { MapInspect(rich, limits); });
    limits = {}; limits.maxArrayRecords = rich.wire.maxArray;
    suite.Check(MapInspect(rich, limits).arrayRecords == rich.wire.records, "Inclusive Map array budget failed");
    --limits.maxArrayRecords;
    Expect(suite, Code::ArrayLimit, rich.wire.bytes.size(), "Short Map array budget", [&] { MapInspect(rich, limits); });
    limits = {}; limits.maxTotalRecords = rich.wire.records;
    suite.Check(MapInspect(rich, limits).arrayRecords == rich.wire.records, "Inclusive Map aggregate budget failed");
    --limits.maxTotalRecords;
    Expect(suite, Code::TotalRecordLimit, rich.wire.bytes.size(), "Short Map aggregate budget", [&] { MapInspect(rich, limits); });
    limits = {}; limits.maxMapPlots = rich.plots;
    suite.Check(MapInspect(rich, limits).plotCount == rich.plots, "Inclusive full Map plot budget failed");
    --limits.maxMapPlots;
    Expect(suite, Code::MapPlotLimit, rich.wire.bytes.size(), "Short full Map plot budget", [&] { MapInspect(rich, limits); });
    limits = {}; limits.maxStringBytes = 0; limits.maxArrayRecords = 0; limits.maxTotalRecords = 0;
    limits.maxEmbeddedDatabaseBytes = 0;
    suite.Check(MapInspect(empty, limits).arrayRecords == 0, "Fixed Map arrays were charged as dynamic records");
    limits = {}; limits.maxTotalRecords = 0;
    Expect(suite, Code::TotalRecordLimit, rich.wire.bytes.size(), "Zero Map record budget", [&] { MapInspect(rich, limits); });
    limits = {}; limits.maxStringBytes = 0;
    Expect(suite, Code::StringLimit, rich.wire.bytes.size(), "Zero Plot script budget", [&] { MapInspect(rich, limits); });
    limits = {}; limits.maxArrayRecords = 0;
    Expect(suite, Code::ArrayLimit, rich.wire.bytes.size(), "Zero Map array budget", [&] { MapInspect(rich, limits); });
    Expect(suite, Code::NullInput, 1, "Map null input", [&] {
        RetailSaveMap::InspectGameAndMap(nullptr, 1, RetailSaveStateProfile(5));
    });
    Expect(suite, Code::Truncated, 0, "Map empty input", [&] {
        RetailSaveMap::InspectGameAndMap(nullptr, 0, RetailSaveStateProfile(5));
    });
    Expect(suite, Code::UnsupportedProfile, rich.wire.bytes.size(), "Map unknown profile", [&] {
        RetailSaveMap::InspectGameAndMap(rich.wire.bytes, RetailSaveStateProfile(4097));
    });
    auto hugeGrid = rich.wire.bytes;
    PutU32(hugeGrid, rich.wire.marks.at("map.width"), 0x7fffffffu);
    PutU32(hugeGrid, rich.wire.marks.at("map.height"), 2);
    limits = {}; limits.maxMapPlots = (std::numeric_limits<std::size_t>::max)();
    Expect(suite, Code::MapPlotLimit, hugeGrid.size(), "SDK signed grid overflow", [&] {
        RetailSaveMap::InspectGameAndMap(hugeGrid, RetailSaveStateProfile(5), limits);
    });
    for (const auto& mark : rich.wire.versions) if (mark.at >= rich.plotStart)
        MapRejectPatch(suite, rich, "Unsupported " + mark.name, mark.at, 99, Code::UnsupportedVersion);
    for (const auto& mark : rich.wire.bools) if (mark.at >= rich.plotStart) {
        auto bytes = rich.wire.bytes; bytes[mark.at] = 2;
        Expect(suite, Code::InvalidValue, bytes.size(), "Malformed Map bool " + mark.name, [&] {
            RetailSaveMap::InspectGameAndMap(bytes, RetailSaveStateProfile(rich.wire.awards));
        });
    }
    for (const auto& mark : rich.wire.signedCounts) if (mark.at >= rich.plotStart)
        MapRejectPatch(suite, rich, "Negative Map count " + mark.name, mark.at, 0xffffffffu, Code::InvalidValue);
    MapRejectPatch(suite, rich, "Oversized Plot string", rich.wire.marks.at("plot0.script"), 0xffffffffu, Code::StringLimit);
    MapRejectPatch(suite, rich, "Oversized unit list", rich.wire.marks.at("plot0.units"), 0xffffffffu, Code::ArrayLimit);
    MapRejectPatch(suite, rich, "Oversized build presence count", rich.wire.marks.at("plot0.build_outer"), 0x7fffffffu, Code::ArrayLimit);
    MapRejectPatch(suite, rich, "Oversized build inner count", rich.wire.marks.at("plot0.build_inner"), 0x7fffffffu, Code::ArrayLimit);
    for (const char* name : {"areas", "landmasses"}) {
        const std::string base(name);
        MapRejectPatch(suite, rich, "Bad Map free capacity", rich.wire.marks.at(base + ".slots"), 3, Code::InvalidValue);
        MapRejectPatch(suite, rich, "Map capacity exceeds SDK mask", rich.wire.marks.at(base + ".slots"), 16384,
            Code::InvalidValue, rich.wire.bytes.size() + 65536);
        MapRejectPatch(suite, rich, "Bad Map last index", rich.wire.marks.at(base + ".last"), 4, Code::InvalidValue);
        MapRejectPatch(suite, rich, "Bad Map free head", rich.wire.marks.at(base + ".free_head"), 4, Code::InvalidValue);
        MapRejectPatch(suite, rich, "Bad Map free count", rich.wire.marks.at(base + ".free_count"), 4, Code::InvalidValue);
        MapRejectPatch(suite, rich, "Bad Map current ID", rich.wire.marks.at(base + ".current_id"), 24577, Code::InvalidValue);
        MapRejectPatch(suite, rich, "Cyclic Map free chain", rich.wire.marks.at(base + ".link1"), 1, Code::InvalidValue);
        MapRejectPatch(suite, rich, "Inconsistent Map live count", rich.wire.marks.at(base + ".live"), 1, Code::InvalidValue);
        MapRejectPatch(suite, rich, "Map record in a free slot", rich.wire.marks.at(base + ".record0.id"), 8193, Code::InvalidValue);
        MapRejectPatch(suite, rich, "Duplicate Map record", rich.wire.marks.at(base + ".record2.id"), 8192, Code::InvalidValue);
    }
}

struct MapObservation {
    bool accepted = false;
    RetailSaveMapInspection value;
    Code code = Code::Truncated;
    std::size_t errorOffset = 0;
};
MapObservation MapObserve(const Bytes& bytes, std::uint32_t awards) {
    MapObservation result;
    RetailSaveStateLimits limits;
    limits.maxInputBytes = 128u * 1024u; limits.maxPrefixBytes = 128u * 1024u;
    limits.maxStringBytes = 4096; limits.maxArrayRecords = 2048;
    limits.maxTotalRecords = 16384; limits.maxMapPlots = 8; limits.maxEmbeddedDatabaseBytes = 4096;
    try { result.value = RetailSaveMap::InspectGameAndMap(bytes, RetailSaveStateProfile(awards), limits); result.accepted = true; }
    catch (const RetailStateError& error) { result.code = error.Code(); result.errorOffset = error.Offset(); }
    return result;
}
bool MapSame(const MapObservation& a, const MapObservation& b) {
    if (a.accepted != b.accepted) return false;
    if (!a.accepted) return a.code == b.code && a.errorOffset == b.errorOffset;
    const auto& x = a.value; const auto& y = b.value;
    return x.map.offset == y.map.offset && x.map.bytes == y.map.bytes &&
        x.plots.offset == y.plots.offset && x.plots.bytes == y.plots.bytes &&
        x.areas.offset == y.areas.offset && x.areas.bytes == y.areas.bytes &&
        x.landmasses.offset == y.landmasses.offset && x.landmasses.bytes == y.landmasses.bytes &&
        x.nextInflatedOffset == y.nextInflatedOffset && x.arrayRecords == y.arrayRecords &&
        x.plotCount == y.plotCount && x.areaCount == y.areaCount && x.landmassCount == y.landmassCount &&
        x.completeSaveVerified == y.completeSaveVerified && x.rulesetCompatibilityVerified == y.rulesetCompatibilityVerified;
}
void MapMutations(Suite& suite, const std::vector<MapFixture>& seeds) {
    std::uint32_t random = 0x7bc91df3u;
    const auto next = [&random]() { random ^= random << 13; random ^= random >> 17; random ^= random << 5; return random; };
    for (std::size_t i = 0; i < 2048; ++i) {
        const auto& seed = seeds[i % seeds.size()]; auto bytes = seed.wire.bytes;
        switch (i % 8) {
        case 0: PutU32(bytes, seed.plotStart, 99); break;
        case 1: bytes[seed.next + next() % (bytes.size() - seed.next)] ^= 0x80; break;
        case 2: PutU32(bytes, seed.wire.marks.at("areas.slots"), 0xffffffffu); break;
        case 3: bytes[seed.wire.marks.at("plot0.has_script")] = 2; break;
        case 4: PutU32(bytes, seed.wire.marks.at("plot0.units"), 0xffffffffu); break;
        case 5: bytes.resize(seed.mapStart + next() % (seed.next - seed.mapStart)); break;
        default: bytes[seed.mapStart + next() % (bytes.size() - seed.mapStart)] ^=
            static_cast<unsigned char>(1u << (next() % 8)); break;
        }
        const auto immutable = bytes;
        const auto first = MapObserve(bytes, seed.wire.awards), second = MapObserve(bytes, seed.wire.awards);
        suite.Check(MapSame(first, second), "Map mutation was nondeterministic");
        suite.Check(bytes == immutable, "Map mutation inspection modified input");
        if (first.accepted) { MapInvariants(suite, first.value, bytes.size()); ++suite.accepted; }
        else { suite.Check(first.errorOffset <= bytes.size(), "Map mutation error offset outside input"); ++suite.rejected; }
        ++suite.mutations;
    }
    suite.Check(suite.accepted != 0 && suite.rejected != 0, "Map mutations did not exercise both outcomes");
}
void MapPublicJson(const RetailSaveMapInspection& r, std::size_t size) {
    std::cout << ",\"public\":{\"input_bytes\":" << size << ",\"map_offset\":" << r.map.offset
        << ",\"map_bytes\":" << r.map.bytes << ",\"plot_offset\":" << r.plots.offset << ",\"plot_bytes\":" << r.plots.bytes
        << ",\"areas_offset\":" << r.areas.offset << ",\"areas_bytes\":" << r.areas.bytes
        << ",\"landmasses_offset\":" << r.landmasses.offset << ",\"landmasses_bytes\":" << r.landmasses.bytes
        << ",\"next_inflated_offset\":" << r.nextInflatedOffset << ",\"plot_count\":" << r.plotCount
        << ",\"area_count\":" << r.areaCount << ",\"landmass_count\":" << r.landmassCount
        << ",\"array_records\":" << r.arrayRecords << '}';
}
} // namespace

int main(int argc, char** argv) {
    Suite suite;
    try {
        static_assert(sizeof(void*) == 8, "This component test requires a 64-bit executable");
        const bool publicMode = argc == 2 && std::strcmp(argv[1], "--public") == 0;
        if (argc != 1 && !publicMode) throw std::invalid_argument("Usage: retail_save_map [--public]");
        std::vector<MapFixture> fixtures;
        for (std::uint32_t awards : {0u, 5u})
            for (bool rich : {false, true}) fixtures.push_back(MapWire(awards, rich).Finish());
        for (const auto& fixture : fixtures) MapGolden(suite, fixture);
        MapCuts(suite, fixtures[2]); MapCuts(suite, fixtures[3]);
        MapNegative(suite, fixtures[2], fixtures[3]);
        MapMutations(suite, fixtures);
        RetailSaveMapInspection publicResult; std::size_t publicBytes = 0;
        if (publicMode) {
            const auto bytes = ReadStdin(); const auto immutable = bytes;
            suite.Check(bytes.size() == 9762327, "Wrong public inflated Map corpus length");
            publicResult = RetailSaveMap::InspectGameAndMap(bytes, RetailSaveStateProfile(5));
            MapInvariants(suite, publicResult, bytes.size());
            suite.Check(publicResult.prefix.nextInflatedOffset == 11984 && publicResult.prefix.mapWidth == 40 &&
                publicResult.prefix.mapHeight == 24, "Previously verified public Map prefix changed");
            suite.Check(publicResult.plotCount == 960, "Public full Map did not contain its declared plot count");
            suite.Check(bytes == immutable, "Public Map inspection modified stdin input"); publicBytes = bytes.size();
        }
        std::cout << "{\"status\":\"PASS_RETAIL_MAP_COMPONENT\",\"checks\":" << suite.checks
            << ",\"synthetic_cases\":" << suite.syntheticCases << ",\"truncations\":" << suite.truncations
            << ",\"mutations\":" << suite.mutations << ",\"accepted_mutations\":" << suite.accepted
            << ",\"rejected_mutations\":" << suite.rejected
            << ",\"input_files_unchanged\":true,\"gamecore_loaded\":false,\"window_created\":false"
            << ",\"game_accessed\":false,\"user_saves_accessed\":false,\"complete_save_validated\":false"
            << ",\"ruleset_compatibility_verified\":false";
        if (publicMode) MapPublicJson(publicResult, publicBytes);
        std::cout << "}\n"; return 0;
    } catch (const std::exception& error) {
        std::cout << "{\"status\":\"FAIL_RETAIL_MAP_COMPONENT\",\"checks\":" << suite.checks
            << ",\"error\":\"" << Escape(error.what()) << "\",\"gamecore_loaded\":false,\"window_created\":false"
            << ",\"user_saves_accessed\":false,\"complete_save_validated\":false,\"ruleset_compatibility_verified\":false}\n";
        return 1;
    }
}
