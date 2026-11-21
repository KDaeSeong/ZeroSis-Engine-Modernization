#include "RetailSavePlayerCities.h"
#include "RetailSaveMap.h"
#include "RetailSaveTeam.h"
#include "RetailSavePlayerPrefix.h"
#include "RetailSavePlayerAiMid.h"
#include "RetailSavePlayerAiLate.h"
#include "RetailSavePlayerPostTraits.h"
#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <exception>
#include <iostream>
#include <limits>
#include <map>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>
#if defined(_WIN32)
#include <fcntl.h>
#include <io.h>
#endif

// Independent literal wire writers follow SDK_BNW_Original:
// CvCity.cpp:13770-13980; CvCityAI.cpp:238-251; CvBuildingClasses.cpp:2171-2207;
// CvCityStrategyAI.cpp:347-370; CvCityCitizens.cpp:161-188;
// CvReligionClasses.cpp:253-267,4058-4077; CvEmphasisClasses.cpp:255-267;
// CvEspionageClasses.cpp:3985-4054; the four *ProductionAI::Write functions;
// FFreeListTrashArray.h:572-630. Production helpers/constants do not build bytes.
// Public data reaches an EMPTY city pool sequentially, not a public City body.
namespace {
using namespace ZeroSisHost;
using Bytes = std::vector<unsigned char>;
using Code = RetailStateErrorCode;
constexpr std::size_t SpanCount = 10;
constexpr auto Catalog = RetailCityProductionCatalogProfile::InitializedBuildingsAndUnits;
struct Suite {
    std::size_t checks = 0, truncations = 0, accepted = 0, rejected = 0;
    void Check(bool condition, const char* message) {
        ++checks;
        if (!condition) throw std::runtime_error(message);
    }
};
struct CityFixture {
    Bytes data;
    std::map<std::string, std::size_t> marks;
    std::vector<std::size_t> versions, bools, signedCounts;
    std::array<RetailInflatedSpan, SpanCount> spans{};
    std::uint32_t projects = 0;
    std::int32_t id = 0;
    std::size_t start = 0, end = 0, records = 0, maxCount = 0, maxString = 0;
    bool rich = false;
};

class Wire {
public:
    explicit Wire(CityFixture& fixture) : f(fixture) {}
    void Mark(const std::string& name) { f.marks[name] = f.data.size(); }
    void U32(const std::string& name, std::uint32_t value) {
        Mark(name);
        for (unsigned i = 0; i < 4; ++i)
            f.data.push_back(static_cast<unsigned char>(value >> (8u * i)));
    }
    void I32(const std::string& name, std::int32_t value) { U32(name, static_cast<std::uint32_t>(value)); }
    void Version(const std::string& name, std::uint32_t value) {
        f.versions.push_back(f.data.size()); U32(name, value);
    }
    void Bool(const std::string& name, bool value) {
        Mark(name); f.bools.push_back(f.data.size()); f.data.push_back(static_cast<unsigned char>(value ? 1u : 0u));
    }
    void Words(const std::string& name, std::size_t count) {
        for (std::size_t i = 0; i < count; ++i)
            U32(name + "." + std::to_string(i), f.rich ? (i % 2 ? 0xffffffffu : 0x12345678u) : 0u);
    }
    void Count(const std::string& name, std::uint32_t value, bool signedCount = false) {
        if (signedCount) f.signedCounts.push_back(f.data.size());
        f.records += value; f.maxCount = std::max(f.maxCount, static_cast<std::size_t>(value));
        U32(name, value);
    }
    void Text(const std::string& name, const std::string& value) {
        U32(name + ".length", static_cast<std::uint32_t>(value.size()));
        Mark(name + ".bytes"); f.maxString = std::max(f.maxString, value.size());
        f.data.insert(f.data.end(), value.begin(), value.end());
    }
    void Ints(const std::string& name) {
        const std::uint32_t count = f.rich ? 3u : 0u;
        Count(name + ".count", count); Words(name + ".item", count);
    }
    void Bools(const std::string& name) {
        const std::uint32_t count = f.rich ? 3u : 0u;
        Count(name + ".count", count);
        for (std::uint32_t i = 0; i < count; ++i) Bool(name + ".item." + std::to_string(i), i % 2 != 0);
    }
    void HashInts(const std::string& name, bool signedCount = false, std::size_t width = 1) {
        const std::uint32_t count = f.rich ? 3u : 0u;
        Count(name + ".count", count, signedCount);
        const std::array<std::uint32_t, 3> hashes = {0u, 0xffffffffu, 0x719a7531u};
        for (std::uint32_t i = 0; i < count; ++i) {
            U32(name + ".hash." + std::to_string(i), hashes[i]);
            if (hashes[i] != 0) Words(name + ".value." + std::to_string(i), width);
        }
    }
    void HashBools(const std::string& name) {
        const std::uint32_t count = f.rich ? 3u : 0u;
        Count(name + ".count", count);
        const std::array<std::uint32_t, 3> hashes = {0u, 0xffffffffu, 0x29a51c3bu};
        for (std::uint32_t i = 0; i < count; ++i) {
            U32(name + ".hash." + std::to_string(i), hashes[i]);
            if (hashes[i] != 0) Bool(name + ".value." + std::to_string(i), i == 2);
        }
    }
    void Begin(std::size_t index) { f.spans[index].offset = f.data.size(); }
    void End(std::size_t index) { f.spans[index].bytes = f.data.size() - f.spans[index].offset; }
private:
    CityFixture& f;
};

CityFixture MakeCity(std::uint32_t projects, bool rich, std::int32_t id, bool prefix = false) {
    CityFixture f; f.projects = projects; f.rich = rich; f.id = id;
    if (prefix) f.data = {0x78u, 0x9cu, 0u, 0xffu, 0x53u};
    f.start = f.data.size(); Wire w(f);
    const std::string name = rich ? std::string("C\0\xED\x95\x9C\x78\x9c", 7) : std::string{};
    const std::string script = rich ? std::string("script\0\x78\x9c\0\0\xff\xff", 13) : std::string{};

    // Version, sixty-six scalar words (including ID and demanded-resource hash),
    // ten bools, four owner/religion words, eighteen vectors and two bool vectors.
    w.Begin(0); w.Version("city.version", 6); w.I32("city.id", id); w.Words("front.scalar", 65);
    for (unsigned i = 0; i < 10; ++i) w.Bool("front.flag." + std::to_string(i), i % 2 != 0);
    w.Words("front.owners", 4);
    for (unsigned i = 0; i < 18; ++i) w.Ints("front.ints." + std::to_string(i));
    w.Bools("front.ever_owned"); w.Bools("front.revealed");
    w.Text("front.name", name); w.Text("front.script", script);
    for (unsigned i = 0; i < 3; ++i) w.HashInts("front.resource." + std::to_string(i));
    w.Ints("front.specialist_production"); w.Ints("front.project_production"); w.End(0);

    w.Begin(1); w.Version("buildings.version", 1); w.Words("buildings.scalar", 7);
    w.Bool("buildings.sold", rich);
    for (unsigned i = 0; i < 6; ++i) w.HashInts("buildings.table." + std::to_string(i), true);
    for (unsigned table = 0; table < 2; ++table) {
        const auto label = "buildings.records." + std::to_string(table);
        w.Count(label + ".count", rich ? 2u : 0u);
        if (rich) { w.Words(label + ".zero_raw", 3); w.Words(label + ".other_raw", 3); }
    }
    w.End(1);

    w.Begin(2); w.HashInts("production.units"); w.HashInts("production.unit_time");
    for (unsigned i = 0; i < 7; ++i) w.Ints("production.ints." + std::to_string(i));
    w.HashInts("production.promotions");
    // Twenty-six entries exceed the container's estimate25. Unknown order77
    // uses two raw words; known orders still retain data2 after a zero hash.
    const std::uint32_t orders = rich ? 26u : 0u;
    w.Count("production.orders.count", orders);
    for (std::uint32_t i = 0; i < orders; ++i) {
        const auto label = "production.order." + std::to_string(i);
        w.I32(label + ".type", i % 6 == 5 ? 77 : static_cast<std::int32_t>(i % 6));
        w.U32(label + ".data1", i % 3 == 0 ? 0u : i % 3 == 1 ? 0xffffffffu : 0x2a3b4c5du);
        w.I32(label + ".data2", -10 - static_cast<std::int32_t>(i));
        w.Bool(label + ".save", i % 2 != 0); w.Bool(label + ".rush", i % 3 == 0);
    }
    for (unsigned i = 0; i < 3; ++i) w.HashInts("production.yield." + std::to_string(i), false, 6);
    w.I32("rank.population", -1); w.Bool("rank.population_valid", rich);
    w.Ints("rank.base_yield"); w.Bools("rank.base_valid");
    w.Ints("rank.yield"); w.Bools("rank.valid");
    w.I32("rank.last_expansion", -2); w.Words("rank.happiness", 2);
    w.Bool("rank.route_last", rich); w.Bool("rank.route_current", !rich);
    w.Text("rank.repeated_name", name); w.Bool("rank.owed_culture", rich); w.End(2);

    w.Begin(3); w.Version("strategy.version", 1);
    w.Count("strategy.flavors.count", rich ? 3u : 0u, true);
    if (rich) w.Words("strategy.flavor", 3);
    w.HashBools("strategy.active"); w.HashInts("strategy.adopted"); w.Words("strategy.specializations", 2);
    w.Version("strategy.building.version", 1); w.HashInts("strategy.building", true);
    w.Version("strategy.unit.version", 1); w.HashInts("strategy.unit", true);
    w.Version("strategy.project.version", 1); w.Words("strategy.project_weight", projects);
    w.Version("strategy.process.version", 1); w.Count("strategy.process.count", rich ? 3u : 0u, true);
    if (rich) {
        const std::array<std::uint32_t, 3> hashes = {0u, 0xffffffffu, 0x1248ace0u};
        for (std::size_t i = 0; i < hashes.size(); ++i) {
            w.U32("strategy.process.hash." + std::to_string(i), hashes[i]);
            w.I32("strategy.process.weight." + std::to_string(i), -127 - static_cast<std::int32_t>(i));
        }
    }
    w.End(3);

    w.Begin(4); w.Version("citizens.version", 1);
    w.Bool("citizens.automated", rich); w.Bool("citizens.no_auto", !rich);
    w.Words("citizens.counts", 3); w.I32("citizens.focus", -1); w.Bool("citizens.avoid_growth", rich);
    for (unsigned table = 0; table < 2; ++table)
        for (unsigned i = 0; i < 37; ++i)
            w.Bool("citizens.working." + std::to_string(table) + "." + std::to_string(i), i % 3 == 0);
    w.Words("citizens.defaults", 2);
    w.HashInts("citizens.specialists"); w.HashInts("citizens.progress");
    w.HashInts("citizens.buildings", true); w.HashInts("citizens.forced_buildings", true);
    w.HashInts("citizens.rates"); w.End(4);

    w.Begin(5); w.Version("religions.version", 3); w.Bool("religions.paid", rich);
    w.I32("religions.pressure", -17); w.Count("religions.count", rich ? 9u : 0u, true);
    // Nine rows exceed FStaticVector's estimate8; each nested version2 has
    // religion, founded byte and exactly three ints, without m_iTemp.
    for (unsigned i = 0; i < (rich ? 9u : 0u); ++i) {
        const auto label = "religions.row." + std::to_string(i);
        w.Version(label + ".version", 2); w.I32(label + ".religion", static_cast<std::int32_t>(i) - 1);
        w.Bool(label + ".founded", i % 2 != 0); w.Words(label + ".counts", 3);
    }
    w.End(5);
    w.Begin(6); w.Version("emphases.version", 1); w.Words("emphases.counts", 2);
    w.Words("emphases.raw_yields", 6); w.HashBools("emphases.flags"); w.End(6);

    w.Begin(7); w.Version("espionage.version", 0);
    for (unsigned column = 0; column < 9; ++column) {
        w.Count("espionage.count." + std::to_string(column), 22, column >= 4);
        for (unsigned i = 0; i < 22; ++i)
            w.I32("espionage.value." + std::to_string(column) + "." + std::to_string(i),
                  i % 2 ? -1 : static_cast<std::int32_t>(column + 2));
    }
    w.End(7); w.Begin(8); w.I32("extra_hit_points", -7); w.End(8);
    w.Begin(9); w.Version("city_ai.version", 1); w.Bool("city_ai.dirty", rich);
    w.Words("city_ai.cache", 2);
    for (unsigned table = 0; table < 2; ++table)
        for (unsigned player = 0; player < 80; ++player)
            w.I32("city_ai.raw." + std::to_string(table) + "." + std::to_string(player),
                  static_cast<std::int32_t>(1000 + table * 100 + player));
    w.End(9); f.end = f.data.size(); w.U32("suffix", 0x9c78beefu);
    return f;
}

std::array<RetailInflatedSpan, SpanCount> Spans(const RetailSaveCityInspection& r) {
    return {r.front, r.buildings, r.productionTablesAndRanks, r.strategy, r.citizens,
            r.religions, r.emphases, r.espionage, r.extraHitPoints, r.cityAITail};
}
RetailSaveCityProfile Profile(std::uint32_t projects) { return RetailSaveCityProfile(projects, Catalog, 6); }
RetailSaveCityInspection ParseCity(const CityFixture& f, const RetailSaveStateLimits& limits = {}) {
    return RetailSaveCity::InspectAt(f.data.data(), f.data.size(), f.start, Profile(f.projects), limits);
}
std::uint32_t Word(const Bytes& data, std::size_t at) {
    if (at > data.size() || data.size() - at < 4) throw std::runtime_error("Test word outside fixture");
    return static_cast<std::uint32_t>(data[at]) | (static_cast<std::uint32_t>(data[at + 1]) << 8) |
        (static_cast<std::uint32_t>(data[at + 2]) << 16) | (static_cast<std::uint32_t>(data[at + 3]) << 24);
}
void Put(Bytes& data, std::size_t at, std::uint32_t value) {
    if (at > data.size() || data.size() - at < 4) throw std::runtime_error("Test patch outside fixture");
    for (unsigned i = 0; i < 4; ++i) data[at + i] = static_cast<unsigned char>(value >> (8u * i));
}
template<class Function> void Reject(Suite& s, Function&& function, Code expected) {
    try { function(); } catch (const RetailStateError& error) {
        s.Check(error.Code() == expected, "Wrong typed city/free-list error"); return;
    }
    s.Check(false, "Invalid city/free-list input was accepted");
}
void CityInvariants(Suite& s, const RetailSaveCityInspection& r, std::size_t size, std::size_t start) {
    bool valid = r.whole.offset == start && r.nextInflatedOffset <= size &&
        r.nextInflatedOffset >= start && r.whole.bytes == r.nextInflatedOffset - start;
    auto next = start;
    for (const auto& span : Spans(r)) {
        valid = valid && span.offset == next && span.offset <= size && span.bytes <= size - span.offset;
        next = span.offset + span.bytes;
    }
    s.Check(valid && next == r.nextInflatedOffset, "City spans are not contiguous and bounded");
    s.Check(!r.completePlayerVerified && !r.completeSaveVerified && !r.rulesetCompatibilityVerified &&
            !r.restoreApproved, "City framing granted semantic or restore approval");
}
void GoldenCity(Suite& s, const CityFixture& f) {
    const auto before = f.data; const auto r = ParseCity(f); CityInvariants(s, r, f.data.size(), f.start);
    s.Check(r.cityId == f.id && r.nextInflatedOffset == f.end && r.arrayRecords == f.records,
            "City ID, boundary or declared record accounting differs from source fixture");
    const auto spans = Spans(r);
    for (std::size_t i = 0; i < spans.size(); ++i)
        s.Check(spans[i].offset == f.spans[i].offset && spans[i].bytes == f.spans[i].bytes,
                "A City nested source boundary differs");
    if (!f.rich) {
        const std::array<std::size_t, SpanCount> literal = {402, 65, 96, 52, 125, 13, 40, 832, 4, 653};
        for (std::size_t i = 0; i < literal.size(); ++i)
            s.Check(spans[i].bytes == literal[i] + (i == 3 ? 4u * f.projects : 0u), "Literal CityAI minimum mismatch");
        s.Check(f.end - f.start == 2282u + 4u * f.projects && r.arrayRecords == 198u,
                "Independent 2282+4P or nine22-column minimum differs");
    } else {
        s.Check(Word(f.data, f.marks.at("production.orders.count")) == 26u &&
                Word(f.data, f.marks.at("production.order.5.type")) == 77u &&
                Word(f.data, f.marks.at("strategy.process.weight.0")) == static_cast<std::uint32_t>(-127),
                "Rich source oracle lost over-estimate orders, fallback or zero-hash process weight");
    }
    s.Check(Word(f.data, f.end) == 0x9c78beefu && f.data == before, "City parser consumed sentinel or changed caller bytes");
}

struct PoolFixture {
    Bytes data;
    std::vector<CityFixture> cities;
    std::uint32_t projects = 0, slots = 0;
    std::int32_t last = -1, head = -1, free = 0, currentId = 8192;
    std::size_t start = 0, end = 0, body = 0, records = 0;
};
void AppendWord(Bytes& data, std::int32_t value) {
    const auto raw = static_cast<std::uint32_t>(value);
    for (unsigned i = 0; i < 4; ++i) data.push_back(static_cast<unsigned char>(raw >> (8u * i)));
}
PoolFixture MakePool(std::uint32_t slots, std::int32_t last, std::int32_t head, std::int32_t free,
                     const std::vector<std::int32_t>& links, std::vector<CityFixture> cities,
                     std::uint32_t projects, bool prefix = false) {
    PoolFixture f; f.projects = projects; f.slots = slots; f.last = last; f.head = head; f.free = free;
    f.cities = std::move(cities); if (prefix) f.data = {0x91u, 0u, 0x78u, 0x9cu, 0xffu};
    f.start = f.data.size();
    if (links.size() != slots) throw std::runtime_error("Wrong independent free-list link fixture");
    AppendWord(f.data, static_cast<std::int32_t>(slots)); AppendWord(f.data, last); AppendWord(f.data, head);
    AppendWord(f.data, free); AppendWord(f.data, 8192);
    for (auto link : links) AppendWord(f.data, link);
    AppendWord(f.data, static_cast<std::int32_t>(f.cities.size())); f.body = f.data.size();
    f.records = slots + f.cities.size();
    for (const auto& city : f.cities) {
        if (city.projects != projects) throw std::runtime_error("Mismatched fixture-only project profile");
        f.data.insert(f.data.end(), city.data.begin() + static_cast<std::ptrdiff_t>(city.start),
                      city.data.begin() + static_cast<std::ptrdiff_t>(city.end));
        f.records += city.records;
    }
    f.end = f.data.size(); AppendWord(f.data, 0x12345678); return f;
}
RetailSavePlayerCitiesInspection ParsePool(const PoolFixture& f, const RetailSaveStateLimits& limits = {}) {
    return RetailSavePlayerCities::InspectAt(f.data.data(), f.data.size(), f.start, Profile(f.projects), limits);
}
void GoldenPool(Suite& s, const PoolFixture& f) {
    const auto before = f.data; const auto r = ParsePool(f);
    s.Check(r.pool.slots == f.slots && r.pool.lastIndex == f.last && r.pool.freeHead == f.head &&
            r.pool.freeCount == f.free && r.pool.currentId == f.currentId && r.pool.liveCount == f.cities.size(),
            "Free-list metadata differs from its literal source fixture");
    s.Check(r.pool.headerSpan.offset == f.start && r.pool.headerSpan.bytes == 24u + 4u * f.slots &&
            r.pool.nextInflatedOffset == f.body && r.cityObjects.offset == f.body &&
            r.cityObjects.bytes == f.end - f.body && r.nextInflatedOffset == f.end &&
            r.whole.offset == f.start && r.whole.bytes == f.end - f.start && r.arrayRecords == f.records,
            "Free-list header/body boundary or explicit record ownership differs");
    s.Check(!r.cityObjectIdsVerified && !r.completePlayerVerified && !r.completeSaveVerified &&
            !r.rulesetCompatibilityVerified && !r.restoreApproved, "City pool granted semantic or restore approval");
    if (!f.cities.empty()) {
        s.Check(r.firstCity.cityId == f.cities.front().id && r.lastCity.cityId == f.cities.back().id,
                "Occupied source city objects were skipped or reordered");
        CityInvariants(s, r.firstCity, f.data.size(), f.body);
        const auto lastStart = f.end - (f.cities.back().end - f.cities.back().start);
        CityInvariants(s, r.lastCity, f.data.size(), lastStart);
    }
    s.Check(Word(f.data, f.end) == 0x12345678u && f.data == before, "Pool consumed sentinel or changed input");
}

void Truncations(Suite& s, const CityFixture& rich, const PoolFixture& occupied) {
    for (std::size_t cut = 0; cut < rich.end; ++cut) {
        Reject(s, [&] { RetailSaveCity::InspectAt(rich.data.data(), cut, rich.start, Profile(rich.projects)); }, Code::Truncated);
        ++s.truncations;
    }
    for (std::size_t cut = 0; cut < occupied.end; ++cut) {
        Reject(s, [&] { RetailSavePlayerCities::InspectAt(occupied.data.data(), cut, occupied.start,
                                                        Profile(occupied.projects)); }, Code::Truncated);
        ++s.truncations;
    }
}
void CityNegative(Suite& s, const CityFixture& empty, const CityFixture& rich) {
    for (auto at : rich.versions) {
        auto f = rich; Put(f.data, at, 0x3456789au);
        Reject(s, [&] { ParseCity(f); }, Code::UnsupportedVersion);
    }
    for (auto at : rich.bools) {
        auto f = rich; f.data[at] = 2;
        Reject(s, [&] { ParseCity(f); }, Code::InvalidValue);
    }
    for (auto at : rich.signedCounts) {
        auto f = rich; Put(f.data, at, 0xffffffffu);
        Reject(s, [&] { ParseCity(f); }, Code::InvalidValue);
    }
    for (unsigned column = 0; column < 9; ++column) {
        auto f = rich; Put(f.data, f.marks.at("espionage.count." + std::to_string(column)), 21);
        Reject(s, [&] { ParseCity(f); }, Code::InvalidValue);
    }
    auto bad = Profile(empty.projects); bad.yieldTypes = 5;
    Reject(s, [&] { RetailSaveCity::InspectAt(empty.data.data(), empty.data.size(), empty.start, bad); }, Code::UnsupportedProfile);
    bad = Profile(empty.projects); bad.production.catalogProfile = static_cast<RetailCityProductionCatalogProfile>(99);
    Reject(s, [&] { RetailSaveCity::InspectAt(empty.data.data(), empty.data.size(), empty.start, bad); }, Code::UnsupportedProfile);
    bad = Profile(0xffffffffu);
    Reject(s, [&] { RetailSaveCity::InspectAt(empty.data.data(), empty.data.size(), empty.start, bad); }, Code::Truncated);
    Reject(s, [&] { RetailSaveCity::InspectAt(nullptr, 1, 0, Profile(0)); }, Code::NullInput);
    Reject(s, [&] { RetailSaveCity::InspectAt(nullptr, 0, 0, Profile(0)); }, Code::Truncated);
    Reject(s, [&] { RetailSaveCity::InspectAt(empty.data.data(), empty.data.size(), empty.data.size() + 1,
                                            Profile(empty.projects)); }, Code::Truncated);
    auto limits = RetailSaveStateLimits{}; limits.maxInputBytes = rich.data.size();
    s.Check(ParseCity(rich, limits).nextInflatedOffset == rich.end, "Exact input limit rejected valid City");
    --limits.maxInputBytes; Reject(s, [&] { ParseCity(rich, limits); }, Code::InputLimit);
    limits = {}; limits.maxPrefixBytes = rich.end;
    s.Check(ParseCity(rich, limits).nextInflatedOffset == rich.end, "Exact prefix limit rejected City");
    --limits.maxPrefixBytes; Reject(s, [&] { ParseCity(rich, limits); }, Code::PrefixLimit);
    limits = {}; limits.maxStringBytes = rich.maxString;
    s.Check(ParseCity(rich, limits).nextInflatedOffset == rich.end, "Exact string limit rejected City");
    --limits.maxStringBytes; Reject(s, [&] { ParseCity(rich, limits); }, Code::StringLimit);
    limits = {}; limits.maxArrayRecords = rich.maxCount;
    s.Check(ParseCity(rich, limits).nextInflatedOffset == rich.end, "Over-estimate26 orders rejected by exact budget");
    --limits.maxArrayRecords; Reject(s, [&] { ParseCity(rich, limits); }, Code::ArrayLimit);
    limits = {}; limits.maxTotalRecords = rich.records;
    s.Check(ParseCity(rich, limits).arrayRecords == rich.records, "Declared record charge differs from literal writer");
    --limits.maxTotalRecords; Reject(s, [&] { ParseCity(rich, limits); }, Code::TotalRecordLimit);
    auto f = rich; Put(f.data, f.marks.at("front.ints.0.count"), 0x100001u);
    Reject(s, [&] { ParseCity(f); }, Code::ArrayLimit);
    limits = {}; limits.maxArrayRecords = 0;
    Reject(s, [&] { ParseCity(empty, limits); }, Code::ArrayLimit); // Explicit espionage columns still declare22.
    limits = {}; limits.maxTotalRecords = 0;
    Reject(s, [&] { ParseCity(empty, limits); }, Code::TotalRecordLimit);
    limits = {}; limits.maxStringBytes = 0;
    s.Check(ParseCity(empty, limits).nextInflatedOffset == empty.end, "Empty strings incorrectly require a positive budget");
}

void PoolNegative(Suite& s, const PoolFixture& empty, const PoolFixture& holes) {
    for (const auto& change : std::vector<std::pair<std::size_t, std::uint32_t>>{
            {0, 0xffffffffu}, {0, 3u}, {4, 8u}, {4, 0xfffffffeu}, {8, 8u}, {12, 0xffffffffu},
            {12, 9u}, {16, 1u}, {16, 8193u}, {20 + 4u * 8u, 0u}, {20 + 4u, 1u}, {20 + 4u * 3u, 1u}}) {
        auto f = holes; Put(f.data, f.start + change.first, change.second);
        Reject(s, [&] { ParsePool(f); }, Code::InvalidValue);
    }
    auto shortChain = holes; Put(shortChain.data, shortChain.start + 20 + 4, 0xffffffffu);
    Reject(s, [&] { ParsePool(shortChain); }, Code::InvalidValue);
    auto large = empty; large.start = 0; large.data.assign(24u + 4u * 16384u, static_cast<unsigned char>(0));
    Put(large.data, 0, 16384); Reject(s, [&] { ParsePool(large); }, Code::InvalidValue);
    auto bad = Profile(0); bad.production.catalogProfile = static_cast<RetailCityProductionCatalogProfile>(99);
    Reject(s, [&] { RetailSavePlayerCities::InspectAt(empty.data.data(), empty.data.size(), empty.start, bad); }, Code::UnsupportedProfile);
    bad = Profile(0); bad.yieldTypes = 7;
    Reject(s, [&] { RetailSavePlayerCities::InspectAt(empty.data.data(), empty.data.size(), empty.start, bad); }, Code::UnsupportedProfile);
    // Project width is unused in an empty pool; it is not an invented SDK cap.
    s.Check(RetailSavePlayerCities::InspectAt(empty.data.data(), empty.data.size(), empty.start,
                Profile(0xffffffffu)).pool.liveCount == 0, "Unused empty-pool project width was rejected");
    auto limits = RetailSaveStateLimits{}; limits.maxTotalRecords = holes.records;
    s.Check(ParsePool(holes, limits).arrayRecords == holes.records, "Pool double-charged occupied objects");
    --limits.maxTotalRecords; Reject(s, [&] { ParsePool(holes, limits); }, Code::TotalRecordLimit);
    limits = {}; limits.maxPrefixBytes = holes.end;
    s.Check(ParsePool(holes, limits).nextInflatedOffset == holes.end, "Exact occupied-pool prefix rejected");
    --limits.maxPrefixBytes; Reject(s, [&] { ParsePool(holes, limits); }, Code::PrefixLimit);
}

struct Observation {
    bool accepted = false;
    std::size_t next = 0, records = 0, errorOffset = 0;
    std::int32_t id = -1;
    Code error = Code::InvalidValue;
};
Observation Observe(const CityFixture& f) {
    Observation o;
    try { const auto r = ParseCity(f); o.accepted = true; o.next = r.nextInflatedOffset;
          o.records = r.arrayRecords; o.id = r.cityId;
          if (r.restoreApproved || r.completePlayerVerified || r.completeSaveVerified || r.rulesetCompatibilityVerified)
              throw std::runtime_error("Mutated City granted approval");
    } catch (const RetailStateError& error) { o.error = error.Code(); o.errorOffset = error.Offset(); }
    return o;
}
std::uint32_t Random(std::uint32_t& state) { state ^= state << 13; state ^= state >> 17; state ^= state << 5; return state; }
void Mutations(Suite& s, const std::vector<CityFixture>& fixtures) {
    std::uint32_t state = 0x76b391adu;
    for (unsigned iteration = 0; iteration < 2048; ++iteration) {
        auto f = fixtures[Random(state) % fixtures.size()]; const auto choice = iteration % 5;
        if (choice == 0) f.data[Random(state) % f.data.size()] ^= static_cast<unsigned char>(1u << (Random(state) % 8));
        else if (choice == 1) f.data.resize(Random(state) % f.data.size());
        else if (choice == 2) Put(f.data, f.versions[Random(state) % f.versions.size()], Random(state));
        else if (choice == 3) f.data[f.bools[Random(state) % f.bools.size()]] = 2;
        else Put(f.data, f.marks.at("city.id"), Random(state));
        const auto before = f.data; const auto a = Observe(f), b = Observe(f);
        s.Check(a.accepted == b.accepted && a.next == b.next && a.records == b.records && a.id == b.id &&
                a.error == b.error && a.errorOffset == b.errorOffset, "Mutation framing is nondeterministic");
        s.Check(f.data == before, "Mutation parsing modified input bytes");
        s.Check(a.accepted ? a.next >= f.start && a.next <= f.data.size() : a.errorOffset <= f.data.size(),
                "Mutation result/error escaped its immutable input");
        if (a.accepted) ++s.accepted; else ++s.rejected;
    }
}

Bytes ReadStdin() {
#if defined(_WIN32)
    if (_setmode(_fileno(stdin), _O_BINARY) == -1) throw std::runtime_error("Cannot select binary stdin");
#endif
    Bytes data; std::array<char, 16384> block{};
    while (std::cin) {
        std::cin.read(block.data(), static_cast<std::streamsize>(block.size())); const auto count = std::cin.gcount();
        if (count < 0 || static_cast<std::size_t>(count) > 64u * 1024u * 1024u - data.size())
            throw std::runtime_error("Public stdin exceeds bounded input budget");
        data.insert(data.end(), block.data(), block.data() + count);
    }
    if (!std::cin.eof()) throw std::runtime_error("Cannot read public binary stdin");
    return data;
}
struct PublicResult { RetailSavePlayerCitiesInspection cities; std::size_t bytes = 0, start = 0; std::uint32_t nextWord = 0; };
PublicResult Public(Suite& s) {
    const auto bytes = ReadStdin(), before = bytes;
    s.Check(bytes.size() == 9762327u, "Wrong externally authenticated public plaintext size");
    auto remaining = RetailSaveStateLimits{};
    const auto map = RetailSaveMap::InspectGameAndMap(bytes, RetailSaveStateProfile(5), remaining);
    s.Check(map.nextInflatedOffset == 1695150u && map.plotCount == 960u && map.arrayRecords <= remaining.maxTotalRecords,
            "Ordered public Map boundary differs"); remaining.maxTotalRecords -= map.arrayRecords;
    RetailStateDetail::Reader teams(bytes.data(), bytes.size(), remaining); teams.Skip(map.nextInflatedOffset);
    for (std::int32_t id = 0; id < 64; ++id) s.Check(RetailStateDetail::ReadTeam(teams) == id, "Public Team IDs differ");
    s.Check(teams.Pos() == 2309550u && teams.Records() <= remaining.maxTotalRecords, "Ordered Team boundary/budget differs");
    remaining.maxTotalRecords -= teams.Records();
    const auto prefix = RetailSavePlayerPrefix::InspectAt(bytes.data(), bytes.size(), teams.Pos(),
        RetailSavePlayerProfile(4, RetailPlayerCatalogProfile::InitializedBuildings), remaining);
    s.Check(prefix.playerId == 0 && prefix.nextInflatedOffset == 2326136u && prefix.arrayRecords <= remaining.maxTotalRecords,
            "Ordered Player prefix differs"); remaining.maxTotalRecords -= prefix.arrayRecords;
    const auto mid = RetailSavePlayerAiMid::InspectAt(bytes.data(), bytes.size(), prefix.nextInflatedOffset,
        RetailPlayerAiMidCatalogProfile::InitializedTechs, remaining);
    s.Check(mid.nextInflatedOffset == 2403477u && mid.arrayRecords <= remaining.maxTotalRecords,
            "Ordered Player middle AI differs"); remaining.maxTotalRecords -= mid.arrayRecords;
    const auto late = RetailSavePlayerAiLate::InspectAt(bytes.data(), bytes.size(), mid.nextInflatedOffset,
        RetailPlayerAiLateProfile::InitializedMinorQuests, remaining);
    s.Check(late.nextInflatedOffset == 2421545u && late.dangerPlotCount == map.plotCount &&
            late.arrayRecords <= remaining.maxTotalRecords, "Ordered Player late AI differs");
    remaining.maxTotalRecords -= late.arrayRecords;
    const auto post = RetailSavePlayerPostTraits::InspectAt(bytes.data(), bytes.size(), late.nextInflatedOffset, remaining);
    s.Check(post.nextInflatedOffset == 2427999u && post.arrayRecords <= remaining.maxTotalRecords,
            "Ordered post-Traits city-list boundary differs"); remaining.maxTotalRecords -= post.arrayRecords;
    PublicResult result; result.bytes = bytes.size(); result.start = post.nextInflatedOffset;
    result.cities = RetailSavePlayerCities::InspectAt(bytes.data(), bytes.size(), result.start, Profile(0), remaining);
    const auto& c = result.cities;
    s.Check(c.pool.slots == 8 && c.pool.lastIndex == -1 && c.pool.freeHead == -1 && c.pool.freeCount == 0 &&
            c.pool.currentId == 8192 && c.pool.liveCount == 0 && c.pool.headerSpan.bytes == 56 &&
            c.nextInflatedOffset == 2428055u && c.cityObjects.bytes == 0 && c.arrayRecords == 8,
            "Public empty pool differs from independent RAM walk");
    for (unsigned i = 0; i < 8; ++i)
        s.Check(Word(bytes, result.start + 20 + 4u * i) == 0xffffffffu, "Public dormant free links differ");
    s.Check(!c.cityObjectIdsVerified && !c.completePlayerVerified && !c.completeSaveVerified &&
            !c.rulesetCompatibilityVerified && !c.restoreApproved && !post.completeSaveVerified &&
            !map.completeSaveVerified && !prefix.completeSaveVerified && !mid.completeSaveVerified && !late.completeSaveVerified &&
            !map.rulesetCompatibilityVerified && !prefix.rulesetCompatibilityVerified && !mid.rulesetCompatibilityVerified &&
            !late.rulesetCompatibilityVerified && !post.rulesetCompatibilityVerified,
            "Public partial components granted restore approval");
    result.nextWord = Word(bytes, c.nextInflatedOffset); s.Check(result.nextWord == 16u, "Unparsed unit capacity word changed");
    s.Check(bytes == before, "Public framing changed stdin bytes"); return result;
}
std::string Escape(const char* raw) {
    std::string out;
    for (const unsigned char* p = reinterpret_cast<const unsigned char*>(raw); *p; ++p) {
        if (*p == '"' || *p == '\\') out += '\\';
        out += *p < 32 ? '?' : static_cast<char>(*p);
    }
    return out;
}
} // namespace

int main(int argc, char** argv) {
    try {
        static_assert(sizeof(void*) == 8, "This component verification requires x64");
        const bool publicMode = argc == 2 && std::string(argv[1]) == "--public";
        if (argc != 1 && !publicMode) throw std::runtime_error("Expected no arguments or --public");
        Suite s;
        const std::vector<CityFixture> cities = {MakeCity(0, false, 8192), MakeCity(3, false, 8193),
            MakeCity(10, false, 8194), MakeCity(3, true, 8195, true), MakeCity(10, true, 8196)};
        for (const auto& city : cities) GoldenCity(s, city);
        std::vector<std::int32_t> emptyLinks(8, -1), holesLinks(8, 1234);
        holesLinks[1] = 3; holesLinks[3] = -1;
        const std::vector<PoolFixture> pools = {
            MakePool(0, -1, -2, 0, {}, {}, 0), MakePool(0, -1, -1, 0, {}, {}, 0),
            MakePool(8, -1, -1, 0, emptyLinks, {}, 0, true),
            MakePool(8, 4, 1, 2, holesLinks, {MakeCity(3, true, 8192), MakeCity(3, false, 8194),
                     MakeCity(3, false, 8196)}, 3, true),
            MakePool(4, 1, -1, 0, std::vector<std::int32_t>(4, 2345),
                     {MakeCity(10, false, 8192), MakeCity(10, true, 8193)}, 10),
            MakePool(8, 0, -1, 0, emptyLinks, {MakeCity(0, false, 8192)}, 0)};
        for (const auto& pool : pools) GoldenPool(s, pool);
        // Generation bits are opaque: aligned zero, positive and negative
        // values are framed without pretending to prove runtime wrap behavior.
        auto zeroGeneration = pools[2]; zeroGeneration.currentId = 0;
        Put(zeroGeneration.data, zeroGeneration.start + 16, 0); GoldenPool(s, zeroGeneration);
        auto negativeGeneration = pools[2]; negativeGeneration.currentId = std::numeric_limits<std::int32_t>::min();
        Put(negativeGeneration.data, negativeGeneration.start + 16, 0x80000000u); GoldenPool(s, negativeGeneration);
        Truncations(s, cities[3], pools[5]); CityNegative(s, cities[0], cities[3]); PoolNegative(s, pools[2], pools[3]);
        Mutations(s, cities); PublicResult publicResult; if (publicMode) publicResult = Public(s);
        s.Check(s.accepted + s.rejected == 2048u, "Mutation accounting mismatch");
        std::cout << "{\"status\":\"PASS_RETAIL_PLAYER_CITIES_COMPONENT\",\"checks\":" << s.checks
            << ",\"synthetic_cases\":" << cities.size() << ",\"pool_cases\":" << pools.size() + 2u
            << ",\"truncations\":" << s.truncations << ",\"mutations\":2048,\"accepted_mutations\":" << s.accepted
            << ",\"rejected_mutations\":" << s.rejected << ",\"input_files_unchanged\":true,\"input_bytes_unchanged\":true"
            << ",\"gamecore_loaded\":false,\"window_created\":false,\"game_accessed\":false,\"user_saves_accessed\":false"
            << ",\"complete_player_framed\":false,\"complete_player_validated\":false,\"complete_save_validated\":false"
            << ",\"ruleset_compatibility_verified\":false,\"sdk_restore_verified\":false"
            << ",\"restore_approved\":false,\"full_engine_goal_complete\":false,\"public_city_object_verified\":false";
        if (publicMode) std::cout << ",\"public\":{\"input_bytes\":" << publicResult.bytes
            << ",\"start_offset\":" << publicResult.start << ",\"next_inflated_offset\":" << publicResult.cities.nextInflatedOffset
            << ",\"city_count\":" << publicResult.cities.pool.liveCount << ",\"pool_capacity\":" << publicResult.cities.pool.slots
            << ",\"array_records\":" << publicResult.cities.arrayRecords << ",\"next_word\":" << publicResult.nextWord
            << ",\"project_count\":0,\"project_profile_used\":false,\"yield_types\":6"
            << ",\"production_catalog\":\"initialized_buildings_and_units\",\"victory_point_awards\":5"
            << ",\"grand_strategy_count\":4,\"profile_ruleset_verified\":false,\"actual_city_body_verified\":false,\"occupied_city_publicly_verified\":false"
            << ",\"unit_body_parsed\":false}";
        std::cout << "}\n"; return 0;
    } catch (const std::exception& error) {
        std::cout << "{\"status\":\"FAIL_RETAIL_PLAYER_CITIES_COMPONENT\",\"error\":\"" << Escape(error.what())
            << "\",\"gamecore_loaded\":false,\"window_created\":false,\"restore_approved\":false}\n"; return 1;
    }
}
