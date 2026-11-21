#include "RetailSavePlayerUnits.h"
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
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>
#if defined(_WIN32)
#include <fcntl.h>
#include <io.h>
#endif

// Independent source-wire fixtures, without SDK serializer calls or save files.
// Archive order: original CvUnit.h:1258-1448, NOT the initializer-list order.
// Outer: CvUnit.cpp:17872-17995; promotions: CvPromotionClasses.cpp:1774-1803,
// 2015-2089; religion: CvReligionClasses.cpp:4098-4135. Generic vector codec:
// original x86 FStlContainerSerialization.h:65-97,197-201,224-234.
// No production size constant or framing helper constructs these bytes.
namespace {
using namespace ZeroSisHost;
using Bytes = std::vector<unsigned char>;
using Code = RetailStateErrorCode;
constexpr auto Profile = RetailUnitWriterProfile::Bnw9CompleteGreatWorkHashWord;
constexpr std::size_t SpanCount = 8;
struct Suite {
    std::size_t checks = 0, truncations = 0, accepted = 0, rejected = 0;
    void Check(bool condition, const char* message) {
        ++checks; if (!condition) throw std::runtime_error(message);
    }
};
struct Fixture {
    Bytes data;
    std::map<std::string, std::size_t> marks;
    std::vector<std::size_t> bools, versions;
    std::array<RetailInflatedSpan, SpanCount> spans{};
    std::int32_t owner = 0, originalOwner = 1, type = 7, x = 3, y = 4, id = 8192, mapLayer = 0;
    std::uint32_t catalog = 0, enabled = 0, missions = 0, typeHash = 0, greatWorkHash = 0;
    std::size_t start = 0, end = 0, records = 0, archiveRecords = 0, maxCount = 0, maxString = 0;
    bool rich = false;
};
class Wire {
public:
    explicit Wire(Fixture& value) : f(value) {}
    void Mark(const std::string& name) { f.marks[name] = f.data.size(); }
    void U32(const std::string& name, std::uint32_t value) {
        Mark(name);
        for (unsigned i = 0; i < 4; ++i) f.data.push_back(static_cast<unsigned char>(value >> (8u * i)));
    }
    void I32(const std::string& name, std::int32_t value) { U32(name, static_cast<std::uint32_t>(value)); }
    void Bool(const std::string& name, bool value) {
        Mark(name); f.bools.push_back(f.data.size()); f.data.push_back(static_cast<unsigned char>(value ? 1u : 0u));
    }
    void Version(const std::string& name, std::uint32_t value) { f.versions.push_back(f.data.size()); U32(name, value); }
    void Words(const std::string& name, std::size_t count) {
        for (std::size_t i = 0; i < count; ++i)
            I32(name + "." + std::to_string(i), f.rich ? (i % 2 ? -2 : static_cast<std::int32_t>(i + 2)) : 0);
    }
    void Count(const std::string& name, std::uint32_t value) {
        U32(name, value); f.records += value; f.maxCount = std::max(f.maxCount, static_cast<std::size_t>(value));
    }
    void Text(const std::string& name, const std::string& value) {
        U32(name + ".length", static_cast<std::uint32_t>(value.size())); Mark(name + ".payload");
        f.maxString = std::max(f.maxString, value.size()); f.data.insert(f.data.end(), value.begin(), value.end());
    }
    void Begin(std::size_t i) { f.spans[i].offset = f.data.size(); }
    void End(std::size_t i) { f.spans[i].bytes = f.data.size() - f.spans[i].offset; }
private:
    Fixture& f;
};

Fixture MakeUnit(bool rich, std::int32_t id, bool prefix = false, bool unusualMetadata = false) {
    Fixture f; f.rich = rich; f.id = id;
    f.catalog = rich ? 7u : 0u; f.enabled = rich ? 3u : 0u; f.missions = rich ? 13u : 0u;
    f.typeHash = rich ? 0xffffffffu : 0u; f.greatWorkHash = rich ? 0x391a7b53u : 0u; f.mapLayer = rich ? 2 : 0;
    if (unusualMetadata) { f.owner = -1; f.originalOwner = -1; f.type = -1; f.x = -17; f.y = -23; f.mapLayer = -1; }
    if (prefix) f.data = {0x78u, 0x9cu, 0xffu, 0u, 9u};
    f.start = f.data.size(); Wire w(f);
    w.Begin(0); w.Version("unit.version", 9); w.End(0);
    w.Begin(1);
    // Six metadata values begin the declaration-ordered full archive. Unit ID
    // is the SIXTH word, even though its constructor initializer is listed first.
    w.I32("archive.owner", f.owner); w.I32("archive.original_owner", f.originalOwner);
    w.I32("archive.type", f.type); w.I32("archive.x", f.x); w.I32("archive.y", f.y); w.I32("archive.id", f.id);
    w.Words("archive.hotkey_through_moves", 8); w.Bool("archive.immobile", rich);
    w.Words("archive.experience_through_fortify", 10); w.Bool("archive.fortified", !rich);
    // 88 declared FAutoVariable raw32 members, m_iBlitzCount through
    // m_iMadeInterceptionCount. Integer ability counters remain four bytes.
    w.Words("archive.blitz_through_interception", 88);
    for (unsigned i = 0; i < 9; ++i) w.Bool("archive.state_bool." + std::to_string(i), i % 2 != 0);
    w.Words("archive.tactical_through_directive", 6);
    w.Text("archive.obsolete_name", rich ? std::string("old\0\xED\x95\x9C", 7) : std::string{});
    w.Text("archive.script", rich ? std::string("script\0\x78\x9c\0\0\xff\xff", 13) : std::string{});
    for (unsigned i = 0; i < 10; ++i) {
        const auto label = "archive.vector." + std::to_string(i);
        const auto count = rich ? 1u + i % 3u : 0u;
        w.Count(label + ".count", count); w.Words(label + ".item", count);
    }
    w.Words("archive.mission_xy_through_unit_ai", 6); w.End(1); f.archiveRecords = f.records;
    w.Begin(2); w.U32("type_hash", f.typeHash); w.I32("last_move", -11); w.End(2);
    w.Begin(3); w.Version("promotions.version", 1);
    w.U32("promotions.catalog", f.catalog); // Metadata, not a serialized row count.
    w.Count("promotions.enabled", f.enabled);
    const std::array<std::uint32_t, 3> hashes = {0u, 0xffffffffu, 0x719a7531u};
    for (std::uint32_t i = 0; i < f.enabled; ++i) {
        w.U32("promotions.hash." + std::to_string(i), hashes[i]);
        w.Bool("promotions.value." + std::to_string(i), true); // Sparse writer saves enabled bits only.
    }
    w.End(3);
    w.Begin(4); w.Words("explicit.three_id_infos", 6);
    // The source uses vector<int>; a count of seven catches an invented fixed
    // five-domain width. No extra count surrounds this generic vector.
    w.Count("explicit.domains.count", rich ? 7u : 0u); if (rich) w.Words("explicit.domains.item", 7);
    w.I32("explicit.ever_selected", -1); w.I32("explicit.map_layer", f.mapLayer); w.I32("explicit.goody_huts", 2);
    w.Bool("explicit.ignore_danger", rich);
    w.Words("explicit.embarked_through_admiral", 28);
    w.Text("explicit.current_name", rich ? std::string("new\0\xEC\x9D\xB4", 7) : std::string{});
    w.I32("explicit.scenario", -3); w.End(4);
    w.Begin(5); w.Version("religion.version", 2); w.I32("religion.type", -1);
    w.I32("religion.strength", -5); w.I32("religion.spreads", 2); w.End(5);
    w.Begin(6); w.U32("great_work_hash", f.greatWorkHash); w.I32("tourism", -7); w.End(6);
    w.Begin(7); w.Count("missions.count", f.missions);
    for (std::uint32_t i = 0; i < f.missions; ++i) {
        const auto label = "missions.row." + std::to_string(i);
        w.I32(label + ".type", i % 2 ? -1 : static_cast<std::int32_t>(i));
        w.Words(label + ".data_flags_turn", 4);
    }
    w.End(7); f.end = f.data.size(); w.U32("suffix", 0x9c78beefu); return f;
}

std::array<RetailInflatedSpan, SpanCount> Spans(const RetailSaveUnitInspection& r) {
    return {r.version, r.archive.whole, r.typeAndLastMove, r.promotions, r.explicitState,
            r.religion, r.greatWorkAndTourism, r.missions};
}
std::uint32_t Word(const Bytes& data, std::size_t offset) {
    if (offset > data.size() || data.size() - offset < 4) throw std::runtime_error("Fixture word outside input");
    return static_cast<std::uint32_t>(data[offset]) | (static_cast<std::uint32_t>(data[offset + 1]) << 8) |
        (static_cast<std::uint32_t>(data[offset + 2]) << 16) | (static_cast<std::uint32_t>(data[offset + 3]) << 24);
}
std::int32_t SignedWord(const Bytes& data, std::size_t offset) {
    const auto value = Word(data, offset);
    return value <= 0x7fffffffu ? static_cast<std::int32_t>(value) : -1 - static_cast<std::int32_t>(~value);
}
void Put(Bytes& data, std::size_t offset, std::uint32_t value) {
    if (offset > data.size() || data.size() - offset < 4) throw std::runtime_error("Fixture patch outside input");
    for (unsigned i = 0; i < 4; ++i) data[offset + i] = static_cast<unsigned char>(value >> (8u * i));
}
RetailSaveUnitInspection Parse(const Fixture& f, const RetailSaveStateLimits& limits = {}) {
    return RetailSaveUnit::InspectAt(f.data.data(), f.data.size(), f.start, Profile, limits);
}
template<class Function> void Reject(Suite& s, Function&& function, Code expected) {
    try { function(); } catch (const RetailStateError& error) {
        s.Check(error.Code() == expected, "Wrong typed Unit error"); return;
    }
    s.Check(false, "Invalid Unit input was accepted");
}
void Invariants(Suite& s, const RetailSaveUnitInspection& r, std::size_t size, std::size_t start) {
    bool valid = r.whole.offset == start && r.nextInflatedOffset <= size && r.nextInflatedOffset >= start &&
        r.whole.bytes == r.nextInflatedOffset - start;
    auto next = start;
    for (const auto& span : Spans(r)) {
        valid = valid && span.offset == next && span.offset <= size && span.bytes <= size - span.offset;
        next = span.offset + span.bytes;
    }
    s.Check(valid && next == r.nextInflatedOffset && r.archive.nextInflatedOffset ==
            r.archive.whole.offset + r.archive.whole.bytes, "Unit spans are not contiguous and bounded");
    s.Check(!r.objectReferencesVerified && !r.completePlayerVerified && !r.completeSaveVerified &&
            !r.rulesetCompatibilityVerified && !r.restoreApproved, "Unit framing granted semantic/restore approval");
}
void Golden(Suite& s, const Fixture& f) {
    const auto before = f.data; const auto r = Parse(f); Invariants(s, r, f.data.size(), f.start);
    s.Check(r.archive.owner == f.owner && r.archive.originalOwner == f.originalOwner && r.archive.unitType == f.type &&
            r.archive.x == f.x && r.archive.y == f.y && r.archive.unitId == f.id && r.mapLayer == f.mapLayer,
            "Declaration-ordered Unit metadata differs from source fixture");
    s.Check(r.unitTypeHash == f.typeHash && r.greatWorkHash == f.greatWorkHash && r.missionCount == f.missions &&
            r.promotionSummary.catalogSize == f.catalog && r.promotionSummary.enabledCount == f.enabled &&
            r.arrayRecords == f.records && r.archive.arrayRecords == f.archiveRecords && r.nextInflatedOffset == f.end,
            "Unit nested metadata, count ownership or boundary differs");
    const auto spans = Spans(r);
    for (std::size_t i = 0; i < spans.size(); ++i)
        s.Check(spans[i].offset == f.spans[i].offset && spans[i].bytes == f.spans[i].bytes,
                "A Unit source-wire nested boundary differs");
    if (!f.rich) {
        const std::array<std::size_t, SpanCount> literal = {4, 555, 8, 12, 161, 16, 8, 4};
        for (std::size_t i = 0; i < literal.size(); ++i) s.Check(spans[i].bytes == literal[i], "Literal Unit minimum differs");
        s.Check(f.end - f.start == 768u && r.arrayRecords == 0u, "Independent 768-byte Unit minimum differs");
        s.Check(f.marks.at("archive.id") == f.start + 24u && f.marks.at("archive.immobile") == f.start + 60u &&
                f.marks.at("archive.fortified") == f.start + 101u, "Literal archive ID/bool offsets differ");
    } else {
        s.Check(f.enabled == 3 && f.missions == 13 && Word(f.data, f.marks.at("explicit.domains.count")) == 7 &&
                f.marks.at("promotions.value.0") == f.marks.at("promotions.hash.0") + 4,
                "Rich oracle lost zero-hash bool or over-estimate vector/mission rows");
    }
    s.Check(Word(f.data, f.end) == 0x9c78beefu && f.data == before, "Unit parser consumed suffix or changed input");
}

struct PoolFixture {
    Bytes data;
    std::vector<Fixture> units;
    std::size_t start = 0, body = 0, end = 0, records = 0;
    std::uint32_t slots = 0;
    std::int32_t last = -1, head = -1, free = 0;
};
void AppendWord(Bytes& data, std::int32_t value) {
    const auto raw = static_cast<std::uint32_t>(value);
    for (unsigned i = 0; i < 4; ++i) data.push_back(static_cast<unsigned char>(raw >> (8u * i)));
}
PoolFixture MakePool(std::uint32_t slots, std::int32_t last, std::int32_t head, std::int32_t free,
                     const std::vector<std::int32_t>& links, std::vector<Fixture> units, bool prefix = false) {
    PoolFixture f; f.slots = slots; f.last = last; f.head = head; f.free = free; f.units = std::move(units);
    if (prefix) f.data = {0x78u, 0x9cu, 0u, 0xffu, 1u}; f.start = f.data.size();
    if (links.size() != slots) throw std::runtime_error("Bad fixture link count");
    AppendWord(f.data, static_cast<std::int32_t>(slots)); AppendWord(f.data, last); AppendWord(f.data, head);
    AppendWord(f.data, free); AppendWord(f.data, 8192);
    for (auto link : links) AppendWord(f.data, link);
    AppendWord(f.data, static_cast<std::int32_t>(f.units.size())); f.body = f.data.size();
    f.records = slots + f.units.size();
    for (const auto& unit : f.units) {
        f.data.insert(f.data.end(), unit.data.begin() + static_cast<std::ptrdiff_t>(unit.start),
                      unit.data.begin() + static_cast<std::ptrdiff_t>(unit.end)); f.records += unit.records;
    }
    f.end = f.data.size(); AppendWord(f.data, 0x12345678); return f;
}
RetailSavePlayerUnitsInspection ParsePool(const PoolFixture& f, const RetailSaveStateLimits& limits = {}) {
    return RetailSavePlayerUnits::InspectAt(f.data.data(), f.data.size(), f.start, Profile, limits);
}
void GoldenPool(Suite& s, const PoolFixture& f) {
    const auto before = f.data; const auto r = ParsePool(f);
    s.Check(r.pool.slots == f.slots && r.pool.lastIndex == f.last && r.pool.freeHead == f.head && r.pool.freeCount == f.free &&
            r.pool.liveCount == f.units.size() && r.pool.headerSpan.offset == f.start &&
            r.pool.headerSpan.bytes == 24u + 4u * f.slots && r.pool.nextInflatedOffset == f.body,
            "Unit pool outer metadata or header boundary differs");
    s.Check(r.whole.offset == f.start && r.whole.bytes == f.end - f.start && r.unitObjects.offset == f.body &&
            r.unitObjects.bytes == f.end - f.body && r.nextInflatedOffset == f.end && r.arrayRecords == f.records,
            "Actual Unit bodies were skipped or double-charged");
    if (!f.units.empty()) {
        s.Check(r.firstUnit.archive.unitId == f.units.front().id && r.lastUnit.archive.unitId == f.units.back().id,
                "Occupied Unit pool first/last objects differ");
        Invariants(s, r.firstUnit, f.data.size(), f.body);
        Invariants(s, r.lastUnit, f.data.size(), f.end - (f.units.back().end - f.units.back().start));
    }
    s.Check(!r.unitObjectIdsVerified && !r.completePlayerVerified && !r.completeSaveVerified &&
            !r.rulesetCompatibilityVerified && !r.restoreApproved, "Unit pool granted semantic/restore approval");
    s.Check(Word(f.data, f.end) == 0x12345678u && f.data == before, "Unit pool changed caller bytes or consumed suffix");
}

void Negative(Suite& s, const Fixture& empty, const Fixture& rich, const PoolFixture& emptyPool) {
    for (auto at : rich.versions) {
        auto f = rich; Put(f.data, at, 127);
        Reject(s, [&] { Parse(f); }, Code::UnsupportedVersion);
    }
    for (auto at : rich.bools) {
        auto f = rich; f.data[at] = 2;
        Reject(s, [&] { Parse(f); }, Code::InvalidValue);
    }
    for (const auto* name : {"promotions.catalog", "promotions.enabled", "missions.count"}) {
        auto f = rich; Put(f.data, f.marks.at(name), 0xffffffffu);
        Reject(s, [&] { Parse(f); }, Code::InvalidValue);
    }
    auto f = rich; Put(f.data, f.marks.at("promotions.catalog"), 2);
    Reject(s, [&] { Parse(f); }, Code::InvalidValue);
    f = rich; Put(f.data, f.marks.at("archive.vector.0.count"), 0xffffffffu);
    Reject(s, [&] { Parse(f); }, Code::ArrayLimit);
    f = rich; Put(f.data, f.marks.at("explicit.domains.count"), 0xffffffffu);
    Reject(s, [&] { Parse(f); }, Code::ArrayLimit);
    Reject(s, [&] { RetailSaveUnit::InspectAt(empty.data.data(), empty.data.size(), empty.start,
                                             static_cast<RetailUnitWriterProfile>(99)); }, Code::UnsupportedProfile);
    Reject(s, [&] { RetailSavePlayerUnits::InspectAt(emptyPool.data.data(), emptyPool.data.size(), emptyPool.start,
                                                    static_cast<RetailUnitWriterProfile>(99)); }, Code::UnsupportedProfile);
    Reject(s, [&] { RetailSaveUnit::InspectAt(nullptr, 1, 0, Profile); }, Code::NullInput);
    Reject(s, [&] { RetailSaveUnit::InspectAt(nullptr, 0, 0, Profile); }, Code::Truncated);
    Reject(s, [&] { RetailSaveUnit::InspectAt(empty.data.data(), empty.data.size(), empty.data.size() + 1, Profile); }, Code::Truncated);
    auto limits = RetailSaveStateLimits{}; limits.maxInputBytes = rich.data.size();
    s.Check(Parse(rich, limits).nextInflatedOffset == rich.end, "Exact Unit input limit rejected");
    --limits.maxInputBytes; Reject(s, [&] { Parse(rich, limits); }, Code::InputLimit);
    limits = {}; limits.maxPrefixBytes = rich.end;
    s.Check(Parse(rich, limits).nextInflatedOffset == rich.end, "Exact Unit prefix limit rejected");
    --limits.maxPrefixBytes; Reject(s, [&] { Parse(rich, limits); }, Code::PrefixLimit);
    limits = {}; limits.maxStringBytes = rich.maxString;
    s.Check(Parse(rich, limits).nextInflatedOffset == rich.end, "Exact Unit string budget rejected");
    --limits.maxStringBytes; Reject(s, [&] { Parse(rich, limits); }, Code::StringLimit);
    limits = {}; limits.maxArrayRecords = rich.maxCount;
    s.Check(Parse(rich, limits).missionCount == 13, "Thirteen mission rows rejected at exact budget");
    --limits.maxArrayRecords; Reject(s, [&] { Parse(rich, limits); }, Code::ArrayLimit);
    limits = {}; limits.maxTotalRecords = rich.records;
    s.Check(Parse(rich, limits).arrayRecords == rich.records, "Unit record accounting differs from independent wire");
    --limits.maxTotalRecords; Reject(s, [&] { Parse(rich, limits); }, Code::TotalRecordLimit);
    // Large catalog metadata does not manufacture rows or require a caller
    // catalog. Semantic resolution is deliberately not approved by the parser.
    f = empty; Put(f.data, f.marks.at("promotions.catalog"), 1000000);
    limits = {}; limits.maxArrayRecords = 0; limits.maxTotalRecords = 0; limits.maxStringBytes = 0;
    s.Check(Parse(f, limits).promotionSummary.catalogSize == 1000000u && Parse(f, limits).arrayRecords == 0,
            "Promotion catalog metadata was charged as absent wire rows");
    limits = {}; limits.maxTotalRecords = 0;
    Reject(s, [&] { Parse(rich, limits); }, Code::TotalRecordLimit);
    // Omitting a promotion bool, or the mandatory GreatWork word, truncates a
    // complete fixture; no alternate layout or following magic is searched.
    f = rich; f.data.erase(f.data.begin() + static_cast<std::ptrdiff_t>(f.marks.at("promotions.value.0")));
    f.data.resize(f.end - 1);
    try { Parse(f); s.Check(false, "Missing promotion bool accepted as an alternate layout"); }
    catch (const RetailStateError&) { s.Check(true, "Missing promotion bool rejected"); }
    f = empty; f.data.erase(f.data.begin() + static_cast<std::ptrdiff_t>(f.marks.at("great_work_hash")),
                            f.data.begin() + static_cast<std::ptrdiff_t>(f.marks.at("great_work_hash") + 4));
    f.data.resize(f.end - 4); Reject(s, [&] { Parse(f); }, Code::Truncated);
}
void Cuts(Suite& s, const Fixture& rich, const PoolFixture& pool) {
    for (std::size_t cut = 0; cut < rich.end; ++cut) {
        Reject(s, [&] { RetailSaveUnit::InspectAt(rich.data.data(), cut, rich.start, Profile); }, Code::Truncated); ++s.truncations;
    }
    for (std::size_t cut = 0; cut < pool.end; ++cut) {
        Reject(s, [&] { RetailSavePlayerUnits::InspectAt(pool.data.data(), cut, pool.start, Profile); }, Code::Truncated); ++s.truncations;
    }
}
void PoolNegative(Suite& s, const PoolFixture& occupied, const PoolFixture& holes) {
    auto f = occupied; Put(f.data, f.start, 3);
    Reject(s, [&] { ParsePool(f); }, Code::InvalidValue);
    f = occupied; Put(f.data, f.start + 4, f.slots);
    Reject(s, [&] { ParsePool(f); }, Code::InvalidValue);
    f = occupied; Put(f.data, f.start + 12, 0xffffffffu);
    Reject(s, [&] { ParsePool(f); }, Code::InvalidValue);
    f = occupied; Put(f.data, f.start + 16, 8193);
    Reject(s, [&] { ParsePool(f); }, Code::InvalidValue);
    f = occupied; Put(f.data, f.body - 4, static_cast<std::uint32_t>(f.units.size() + 1));
    Reject(s, [&] { ParsePool(f); }, Code::InvalidValue);
    f = holes; Put(f.data, f.start + 20 + 4, 1); // Active free slot links to itself.
    Reject(s, [&] { ParsePool(f); }, Code::InvalidValue);
    // The generation high bits are opaque, including zero and a set sign bit.
    f = occupied; Put(f.data, f.start + 16, 0);
    s.Check(ParsePool(f).nextInflatedOffset == f.end, "Zero-generation pool metadata was overconstrained");
    Put(f.data, f.start + 16, 0xffffe000u);
    s.Check(ParsePool(f).nextInflatedOffset == f.end, "Signed pool generation bits were overconstrained");
    auto limits = RetailSaveStateLimits{}; limits.maxTotalRecords = occupied.records;
    s.Check(ParsePool(occupied, limits).arrayRecords == occupied.records, "Exact pool aggregate row budget differs");
    --limits.maxTotalRecords; Reject(s, [&] { ParsePool(occupied, limits); }, Code::TotalRecordLimit);
    limits = {}; limits.maxPrefixBytes = occupied.end;
    s.Check(ParsePool(occupied, limits).nextInflatedOffset == occupied.end, "Exact occupied pool prefix budget rejected");
    --limits.maxPrefixBytes; Reject(s, [&] { ParsePool(occupied, limits); }, Code::PrefixLimit);
}
struct Observation {
    bool accepted = false;
    std::size_t next = 0, records = 0, errorOffset = 0;
    std::int32_t id = -1;
    Code error = Code::InvalidValue;
};
Observation Observe(const Fixture& f) {
    Observation result;
    try {
        const auto r = Parse(f); result.accepted = true; result.next = r.nextInflatedOffset;
        result.records = r.arrayRecords; result.id = r.archive.unitId;
        if (r.objectReferencesVerified || r.completePlayerVerified || r.completeSaveVerified || r.restoreApproved || r.rulesetCompatibilityVerified)
            throw std::runtime_error("Mutated Unit granted approval");
    } catch (const RetailStateError& error) { result.error = error.Code(); result.errorOffset = error.Offset(); }
    return result;
}
std::uint32_t Random(std::uint32_t& value) { value ^= value << 13; value ^= value >> 17; value ^= value << 5; return value; }
void Mutations(Suite& s, const std::vector<Fixture>& fixtures) {
    std::uint32_t state = 0xd751c3a9u;
    for (unsigned i = 0; i < 2048; ++i) {
        auto f = fixtures[Random(state) % fixtures.size()];
        switch (i % 6) {
        case 0: f.data[Random(state) % f.data.size()] ^= static_cast<unsigned char>(1u << (Random(state) % 8)); break;
        case 1: f.data.resize(Random(state) % f.data.size()); break;
        case 2: Put(f.data, f.versions[Random(state) % f.versions.size()], Random(state)); break;
        case 3: f.data[f.bools[Random(state) % f.bools.size()]] = 2; break;
        case 4: Put(f.data, f.marks.at("archive.id"), Random(state)); break;
        default: Put(f.data, f.marks.at("promotions.enabled"), Random(state)); break;
        }
        const auto before = f.data; const auto a = Observe(f), b = Observe(f);
        s.Check(a.accepted == b.accepted && a.next == b.next && a.records == b.records && a.id == b.id &&
                a.error == b.error && a.errorOffset == b.errorOffset, "Unit mutation framing is nondeterministic");
        s.Check(f.data == before, "Unit mutation parser modified input");
        s.Check(a.accepted ? a.next >= f.start && a.next <= f.data.size() : a.errorOffset <= f.data.size(),
                "Unit mutation result/error escaped its input");
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
            throw std::runtime_error("Public stdin exceeded its budget");
        data.insert(data.end(), block.data(), block.data() + count);
    }
    if (!std::cin.eof()) throw std::runtime_error("Public stdin read failed"); return data;
}
struct PublicResult {
    RetailSavePlayerUnitsInspection units;
    RetailStateDetail::RetailFreeListHeader army;
    std::size_t bytes = 0, start = 0;
    std::vector<std::int32_t> unitIds;
};
PublicResult Public(Suite& s) {
    const auto bytes = ReadStdin(), before = bytes;
    s.Check(bytes.size() == 9762327u, "Wrong externally authenticated public plaintext size");
    auto remaining = RetailSaveStateLimits{};
    const auto map = RetailSaveMap::InspectGameAndMap(bytes, RetailSaveStateProfile(5), remaining);
    s.Check(map.nextInflatedOffset == 1695150u && map.plotCount == 960u && map.arrayRecords <= remaining.maxTotalRecords,
            "Ordered public Map boundary/budget differs"); remaining.maxTotalRecords -= map.arrayRecords;
    RetailStateDetail::Reader teams(bytes.data(), bytes.size(), remaining); teams.Skip(map.nextInflatedOffset);
    for (std::int32_t id = 0; id < 64; ++id) s.Check(RetailStateDetail::ReadTeam(teams) == id, "Public Team ID differs");
    s.Check(teams.Pos() == 2309550u && teams.Records() <= remaining.maxTotalRecords, "Ordered Teams boundary differs");
    remaining.maxTotalRecords -= teams.Records();
    const auto prefix = RetailSavePlayerPrefix::InspectAt(bytes.data(), bytes.size(), teams.Pos(),
        RetailSavePlayerProfile(4, RetailPlayerCatalogProfile::InitializedBuildings), remaining);
    s.Check(prefix.playerId == 0 && prefix.nextInflatedOffset == 2326136u && prefix.arrayRecords <= remaining.maxTotalRecords,
            "Ordered Player prefix differs"); remaining.maxTotalRecords -= prefix.arrayRecords;
    const auto mid = RetailSavePlayerAiMid::InspectAt(bytes.data(), bytes.size(), prefix.nextInflatedOffset,
        RetailPlayerAiMidCatalogProfile::InitializedTechs, remaining);
    s.Check(mid.nextInflatedOffset == 2403477u && mid.arrayRecords <= remaining.maxTotalRecords,
            "Ordered middle AI differs"); remaining.maxTotalRecords -= mid.arrayRecords;
    const auto late = RetailSavePlayerAiLate::InspectAt(bytes.data(), bytes.size(), mid.nextInflatedOffset,
        RetailPlayerAiLateProfile::InitializedMinorQuests, remaining);
    s.Check(late.nextInflatedOffset == 2421545u && late.dangerPlotCount == map.plotCount && late.arrayRecords <= remaining.maxTotalRecords,
            "Ordered late AI differs"); remaining.maxTotalRecords -= late.arrayRecords;
    const auto post = RetailSavePlayerPostTraits::InspectAt(bytes.data(), bytes.size(), late.nextInflatedOffset, remaining);
    s.Check(post.nextInflatedOffset == 2427999u && post.arrayRecords <= remaining.maxTotalRecords,
            "Ordered post-Traits differs"); remaining.maxTotalRecords -= post.arrayRecords;
    const auto cities = RetailSavePlayerCities::InspectAt(bytes.data(), bytes.size(), post.nextInflatedOffset,
        RetailSaveCityProfile(0, RetailCityProductionCatalogProfile::InitializedBuildingsAndUnits, 6), remaining);
    s.Check(cities.pool.liveCount == 0 && cities.nextInflatedOffset == 2428055u && cities.arrayRecords <= remaining.maxTotalRecords,
            "Ordered empty-city boundary differs"); remaining.maxTotalRecords -= cities.arrayRecords;
    PublicResult result; result.bytes = bytes.size(); result.start = cities.nextInflatedOffset;
    result.units = RetailSavePlayerUnits::InspectAt(bytes.data(), bytes.size(), result.start, Profile, remaining);
    const auto& pool = result.units.pool;
    // Independent root-side raw-word observations, not values obtained by
    // this parser or a pattern search. Generation increases per allocation;
    // later objects are checked by slot mask, not by sharing this generation.
    s.Check(result.start == 2428055u && pool.slots == 16u && pool.lastIndex == 8 && pool.freeHead == -1 &&
            pool.freeCount == 0 && pool.currentId == 81920 && pool.liveCount == 9u &&
            pool.headerSpan.bytes == 88u && pool.nextInflatedOffset == 2428143u,
            "Public Unit free-list differs from independently unpacked metadata");
    const auto& first = result.units.firstUnit;
    s.Check(first.whole.offset == 2428143u && Word(bytes, first.version.offset) == 9u &&
            first.archive.owner == 0 && first.archive.originalOwner == 0 && first.archive.unitType == 0 &&
            first.archive.x == 32 && first.archive.y == 15 && first.archive.unitId == 8192,
            "Public first Unit differs from independent version/archive observations");
    s.Check(pool.liveCount > 0 && result.units.nextInflatedOffset > result.start &&
            result.units.arrayRecords <= remaining.maxTotalRecords, "Public Unit pool is not an occupied bounded source frame");
    // Independently walk the free-chain metadata and ascending occupied slot
    // order. This checks observed IDs/owners/coordinates, without resolving any
    // type hash, loading a Unit or approving arbitrary saved-state references.
    std::vector<bool> freeSlots(pool.slots, false); auto link = pool.freeHead;
    for (std::int32_t i = 0; i < pool.freeCount; ++i) {
        s.Check(link >= 0 && static_cast<std::uint32_t>(link) < pool.slots && !freeSlots[static_cast<std::size_t>(link)],
                "Public free-chain metadata is not independently bounded");
        freeSlots[static_cast<std::size_t>(link)] = true;
        link = SignedWord(bytes, result.start + 20 + 4u * static_cast<std::uint32_t>(link));
    }
    RetailStateDetail::Reader objects(bytes.data(), bytes.size(), remaining); objects.Skip(pool.nextInflatedOffset);
    std::set<std::int32_t> ids; std::uint32_t objectsSeen = 0;
    for (std::int32_t slot = 0; slot <= pool.lastIndex; ++slot) if (!freeSlots[static_cast<std::size_t>(slot)]) {
        const auto begin = objects.Pos(); const auto unit = RetailStateDetail::ReadUnit(objects, Profile);
        Invariants(s, unit, bytes.size(), begin);
        s.Check((static_cast<std::uint32_t>(unit.archive.unitId) & 8191u) == static_cast<std::uint32_t>(slot) &&
                ids.insert(unit.archive.unitId).second && unit.archive.owner == prefix.playerId &&
                unit.archive.originalOwner >= -1 && unit.archive.originalOwner < 64 && unit.archive.unitType >= 0 &&
                unit.archive.x >= 0 && static_cast<std::uint32_t>(unit.archive.x) < map.prefix.mapWidth &&
                unit.archive.y >= 0 && static_cast<std::uint32_t>(unit.archive.y) < map.prefix.mapHeight,
                "Observed public Unit ID/owner/type/coordinates failed cross-check");
        result.unitIds.push_back(unit.archive.unitId); ++objectsSeen;
    }
    s.Check(objectsSeen == pool.liveCount && objects.Pos() == result.units.nextInflatedOffset &&
            objects.Records() + pool.slots + pool.liveCount == result.units.arrayRecords,
            "Public occupied Unit traversal differs from aggregate boundary/accounting");
    remaining.maxTotalRecords -= result.units.arrayRecords;
    RetailStateDetail::Reader army(bytes.data(), bytes.size(), remaining); army.Skip(result.units.nextInflatedOffset);
    result.army = RetailStateDetail::ReadFreeListHeader(army); // Next source field is m_armyAIs, not a searched signature.
    s.Check(result.army.headerSpan.offset == result.units.nextInflatedOffset && result.army.nextInflatedOffset <= bytes.size(),
            "Following Army free-list header is not adjacent and bounded");
    s.Check(!result.units.unitObjectIdsVerified && !result.units.completePlayerVerified && !result.units.completeSaveVerified &&
            !result.units.rulesetCompatibilityVerified && !result.units.restoreApproved && !cities.restoreApproved &&
            !map.completeSaveVerified && !prefix.completeSaveVerified && !mid.completeSaveVerified && !late.completeSaveVerified &&
            !post.completeSaveVerified, "Public partial parsing granted restore approval");
    s.Check(bytes == before, "Public ordered parsing modified plaintext input"); return result;
}
void UnitJson(const char* name, const RetailSaveUnitInspection& unit) {
    std::cout << ",\"" << name << "\":{\"offset\":" << unit.whole.offset << ",\"bytes\":" << unit.whole.bytes
        << ",\"owner\":" << unit.archive.owner << ",\"original_owner\":" << unit.archive.originalOwner
        << ",\"unit_type\":" << unit.archive.unitType << ",\"x\":" << unit.archive.x << ",\"y\":" << unit.archive.y
        << ",\"unit_id\":" << unit.archive.unitId << ",\"map_layer\":" << unit.mapLayer
        << ",\"unit_type_hash\":" << unit.unitTypeHash << ",\"great_work_hash\":" << unit.greatWorkHash
        << ",\"promotion_catalog_size\":" << unit.promotionSummary.catalogSize
        << ",\"enabled_promotion_count\":" << unit.promotionSummary.enabledCount << ",\"mission_count\":" << unit.missionCount;
    const std::array<const char*, SpanCount> names = {"version", "archive", "type_and_last_move", "promotions",
        "explicit_state", "religion", "great_work_and_tourism", "missions"}; const auto spans = Spans(unit);
    for (std::size_t i = 0; i < names.size(); ++i)
        std::cout << ",\"" << names[i] << "_offset\":" << spans[i].offset << ",\"" << names[i] << "_bytes\":" << spans[i].bytes;
    std::cout << ",\"array_records\":" << unit.arrayRecords << ",\"restore_approved\":false}";
}
std::string Escape(const char* raw) {
    std::string value;
    for (const unsigned char* p = reinterpret_cast<const unsigned char*>(raw); *p; ++p) {
        if (*p == '"' || *p == '\\') value += '\\'; value += *p < 32 ? '?' : static_cast<char>(*p);
    }
    return value;
}
} // namespace

int main(int argc, char** argv) {
    try {
        static_assert(sizeof(void*) == 8, "Unit component verification requires x64");
        const bool publicMode = argc == 2 && std::string(argv[1]) == "--public";
        if (argc != 1 && !publicMode) throw std::runtime_error("Expected no arguments or --public");
        Suite s;
        auto catalogOnly = MakeUnit(false, 16385, true); catalogOnly.catalog = 7;
        Put(catalogOnly.data, catalogOnly.marks.at("promotions.catalog"), 7);
        const std::vector<Fixture> fixtures = {MakeUnit(false, 8192), catalogOnly, MakeUnit(true, 24578, true),
            MakeUnit(true, 32771), MakeUnit(false, -1, false, true)};
        for (const auto& f : fixtures) Golden(s, f);
        std::vector<std::int32_t> links(8, 777); links[1] = 3; links[3] = -1;
        const std::vector<PoolFixture> pools = {
            MakePool(0, -1, -2, 0, {}, {}), MakePool(8, -1, -1, 0, std::vector<std::int32_t>(8, -1), {}, true),
            MakePool(8, 4, 1, 2, links, {MakeUnit(false, 8192), MakeUnit(true, 16386), MakeUnit(false, 24580)}, true),
            MakePool(4, 1, -1, 0, std::vector<std::int32_t>(4, 999), {MakeUnit(true, 8192), MakeUnit(false, 16385)})};
        for (const auto& pool : pools) GoldenPool(s, pool);
        Negative(s, fixtures[0], fixtures[2], pools[1]); PoolNegative(s, pools[3], pools[2]);
        Cuts(s, fixtures[2], pools[3]); Mutations(s, fixtures);
        PublicResult publicResult; if (publicMode) publicResult = Public(s);
        s.Check(s.accepted + s.rejected == 2048u, "Unit mutation accounting differs");
        std::cout << "{\"status\":\"PASS_RETAIL_PLAYER_UNITS_COMPONENT\",\"checks\":" << s.checks
            << ",\"synthetic_cases\":" << fixtures.size() << ",\"pool_cases\":" << pools.size()
            << ",\"truncations\":" << s.truncations << ",\"mutations\":2048,\"accepted_mutations\":" << s.accepted
            << ",\"rejected_mutations\":" << s.rejected << ",\"input_files_unchanged\":true,\"input_bytes_unchanged\":true"
            << ",\"gamecore_loaded\":false,\"window_created\":false,\"game_accessed\":false,\"user_saves_accessed\":false"
            << ",\"complete_player_validated\":false,\"complete_save_validated\":false"
            << ",\"ruleset_compatibility_verified\":false,\"restore_approved\":false";
        if (publicMode) {
            const auto& r = publicResult.units;
            std::cout << ",\"public\":{\"input_bytes\":" << publicResult.bytes << ",\"start_offset\":" << publicResult.start
                << ",\"next_inflated_offset\":" << r.nextInflatedOffset << ",\"unit_count\":" << r.pool.liveCount
                << ",\"pool_capacity\":" << r.pool.slots << ",\"last_index\":" << r.pool.lastIndex
                << ",\"free_head\":" << r.pool.freeHead << ",\"free_count\":" << r.pool.freeCount
                << ",\"current_id\":" << r.pool.currentId << ",\"pool_header_bytes\":" << r.pool.headerSpan.bytes
                << ",\"unit_objects_offset\":" << r.unitObjects.offset
                << ",\"unit_objects_bytes\":" << r.unitObjects.bytes << ",\"array_records\":" << r.arrayRecords;
            UnitJson("first_unit", r.firstUnit); UnitJson("last_unit", r.lastUnit);
            std::cout << ",\"observed_unit_ids\":[";
            for (std::size_t i = 0; i < publicResult.unitIds.size(); ++i) {
                if (i) std::cout << ','; std::cout << publicResult.unitIds[i];
            }
            std::cout << "],\"army_header\":{\"offset\":" << publicResult.army.headerSpan.offset
                << ",\"bytes\":" << publicResult.army.headerSpan.bytes << ",\"capacity\":" << publicResult.army.slots
                << ",\"live_count\":" << publicResult.army.liveCount << ",\"next_offset\":" << publicResult.army.nextInflatedOffset
                << "},\"army_bodies_parsed\":false,\"victory_point_awards\":5,\"grand_strategy_count\":4"
                << ",\"city_project_count_unused\":0,\"profile_ruleset_verified\":false,\"restore_approved\":false}";
        }
        std::cout << "}\n"; return 0;
    } catch (const std::exception& error) {
        std::cout << "{\"status\":\"FAIL_RETAIL_PLAYER_UNITS_COMPONENT\",\"error\":\"" << Escape(error.what())
            << "\",\"gamecore_loaded\":false,\"window_created\":false,\"restore_approved\":false}\n"; return 1;
    }
}
