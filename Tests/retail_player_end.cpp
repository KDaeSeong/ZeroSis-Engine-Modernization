#include "RetailSavePlayer.h"
#include "RetailSaveMap.h"
#include "RetailSaveTeam.h"
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

// Independent source-wire fixtures, without SDK serializers, save files or
// production framing helpers. CvArmyAI.cpp:99-152; CvAIOperation.cpp:1139-1188
// and each derived Write; CvPlayer.cpp:22651-22698; CvPlayerAI.cpp:685-706.
// The operation suffix table contains literal bytes for all twenty factory
// types. Inherited writers do not manufacture extra versions or padding.
namespace {
using namespace ZeroSisHost;
using Bytes = std::vector<unsigned char>;
using Code = RetailStateErrorCode;
constexpr std::size_t FieldSpanCount = 9;
struct Suite {
    std::size_t checks = 0, truncations = 0, accepted = 0, rejected = 0;
    void Check(bool condition, const char* message) {
        ++checks;
        if (!condition) throw std::runtime_error(message);
    }
};
struct DerivedLayout {
    std::int32_t type;
    Bytes bytes;
    std::vector<std::size_t> versions, bools;
    std::size_t minimumRecordBytes;
};
const std::array<DerivedLayout, 20> Layouts = {{
    {0,  {1,0,0,0},                         {0},   {},  81},
    {1,  {1,0,0,0},                         {0},   {},  81},
    {2,  {1,0,0,0},                         {0},   {},  81},
    {3,  {1,0,0,0,1,255,255,255,255},         {0},   {4}, 86},
    {4,  {1,0,0,0,1,255,255,255,255,2,0,0,0}, {0},   {4}, 90},
    {5,  {1,0,0,0},                         {0},   {},  81},
    {6,  {1,0,0,0},                         {0},   {},  81},
    {7,  {1,0,0,0},                         {0},   {},  81},
    {8,  {1,0,0,0,1,255,255,255,255,2,0,0,0}, {0},   {4}, 90},
    {9,  {1,0,0,0,1,0,0,0},                 {0,4}, {},  85},
    {10, {1,0,0,0,1,0,0,0},                 {0,4}, {},  85},
    {11, {1,0,0,0,255,255,255,255},           {0},   {},  85},
    {12, {1,0,0,0,1,255,255,255,255,2,0,0,0}, {0},   {4}, 90},
    {13, {1,0,0,0,255,255,255,255,1,0,0,0},   {0,8}, {},  89},
    {14, {1,0,0,0,255,255,255,255,1,0,0,0},   {0,8}, {},  89},
    {15, {1,0,0,0},                         {0},   {},  81},
    {16, {1,0,0,0,255,255,255,255,1,0,0,0},   {0,8}, {},  89},
    {17, {1,0,0,0,255,255,255,255},           {0},   {},  85},
    {18, {1,0,0,0,1,0,0,0},                 {0,4}, {},  85},
    {19, {1,0,0,0,1,255,255,255,255,2,0,0,0}, {0},   {4}, 90}
}};
struct ArmyExpected {
    std::int32_t id = -1, owner = -1;
    std::uint32_t slots = 0;
    std::size_t start = 0, end = 0;
};
struct OperationExpected {
    std::int32_t type = -1, key = -1, id = -1;
    std::size_t start = 0, end = 0;
};
struct Fixture {
    Bytes data;
    std::map<std::string, std::size_t> marks;
    std::vector<std::size_t> bools, versions, unsignedCounts, signedCounts;
    std::vector<ArmyExpected> armies;
    std::vector<OperationExpected> operations;
    std::array<RetailInflatedSpan, FieldSpanCount> fields{};
    std::size_t start = 0, armyBody = 0, armyEnd = 0, operationEnd = 0, fieldEnd = 0, end = 0;
    std::size_t records = 0, armyRecords = 0, operationRecords = 0, fieldRecords = 0;
    std::size_t maxCount = 0, maxString = 0;
    std::uint32_t capacity = 0, mismatches = 0;
    std::int32_t last = -1, head = -2, free = 0;
    bool rich = false;
};
class Wire {
public:
    explicit Wire(Fixture& value) : f(value) {}
    void Mark(const std::string& name) { f.marks[name] = f.data.size(); }
    void U32(const std::string& name, std::uint32_t value) {
        Mark(name);
        for (unsigned i = 0; i < 4; ++i)
            f.data.push_back(static_cast<unsigned char>(value >> (8u * i)));
    }
    void I32(const std::string& name, std::int32_t value) { U32(name, static_cast<std::uint32_t>(value)); }
    void Version(const std::string& name) { f.versions.push_back(f.data.size()); U32(name, 1); }
    void Bool(const std::string& name, bool value) {
        Mark(name); f.bools.push_back(f.data.size()); f.data.push_back(static_cast<unsigned char>(value ? 1u : 0u));
    }
    void Words(const std::string& name, std::size_t count) {
        for (std::size_t i = 0; i < count; ++i)
            I32(name + "." + std::to_string(i), i % 2u ? -11 : static_cast<std::int32_t>(i + 3u));
    }
    void Count(const std::string& name, std::uint32_t count, bool isSigned = false) {
        (isSigned ? f.signedCounts : f.unsignedCounts).push_back(f.data.size());
        U32(name, count); f.records += count;
        f.maxCount = std::max(f.maxCount, static_cast<std::size_t>(count));
    }
    void Text(const std::string& name, const std::string& value) {
        U32(name + ".length", static_cast<std::uint32_t>(value.size())); Mark(name + ".payload");
        f.maxString = std::max(f.maxString, value.size());
        f.data.insert(f.data.end(), value.begin(), value.end());
    }
    void Derived(const std::string& name, const DerivedLayout& layout) {
        const auto start = f.data.size(); Mark(name);
        f.data.insert(f.data.end(), layout.bytes.begin(), layout.bytes.end());
        for (std::size_t i = 0; i < layout.versions.size(); ++i) {
            const auto at = start + layout.versions[i]; f.versions.push_back(at);
            f.marks[name + ".version." + std::to_string(i)] = at;
        }
        for (auto offset : layout.bools) {
            f.bools.push_back(start + offset);
            f.data[start + offset] = static_cast<unsigned char>(f.rich ? 1u : 0u);
        }
    }
    void Begin(std::size_t index) { f.fields[index].offset = f.data.size(); }
    void End(std::size_t index) { f.fields[index].bytes = f.data.size() - f.fields[index].offset; }
private:
    Fixture& f;
};
RetailSavePlayerEndProfile EndProfile() {
    return {RetailPlayerOperationsProfile::BnwCurrentFactory20, RetailPlayerEndWriterProfile::Current16With64Players};
}
RetailSavePlayerWireProfile PlayerProfile() {
    return {RetailSavePlayerProfile(4, RetailPlayerCatalogProfile::InitializedBuildings),
        RetailPlayerAiMidCatalogProfile::InitializedTechs, RetailPlayerAiLateProfile::InitializedMinorQuests,
        RetailSaveCityProfile(0, RetailCityProductionCatalogProfile::InitializedBuildingsAndUnits, 6),
        RetailUnitWriterProfile::Bnw9CompleteGreatWorkHashWord, EndProfile()};
}
std::vector<std::int32_t> AllTypes() {
    std::vector<std::int32_t> types;
    for (std::int32_t i = 0; i < 20; ++i) types.push_back(i);
    return types;
}
Fixture Make(bool rich, bool prefix, bool occupied, const std::vector<std::int32_t>& types,
        std::uint32_t emptyCapacity = 0) {
    Fixture f; f.rich = rich;
    if (prefix) f.data = {0x78u, 0x9cu, 0xffu, 0u, 0x55u};
    f.start = f.data.size(); Wire w(f);
    f.capacity = occupied ? 8u : emptyCapacity; f.last = occupied ? 4 : -1;
    f.head = occupied ? 1 : (emptyCapacity ? -1 : -2); f.free = occupied ? 2 : 0;
    w.Count("pool.capacity", f.capacity, true); w.I32("pool.last", f.last); w.I32("pool.head", f.head);
    w.I32("pool.free", f.free); w.I32("pool.current_id", 8192);
    for (std::uint32_t i = 0; i < f.capacity; ++i)
        w.I32("pool.link." + std::to_string(i), occupied && i == 1u ? 3 : (i == 3u ? -1 : 777));
    w.Count("pool.live", occupied ? 3u : 0u, true); f.armyBody = f.data.size();
    if (occupied) {
        const std::array<std::int32_t, 3> ids = {8192, 16386, 24580};
        const std::array<std::uint32_t, 3> slots = rich ? std::array<std::uint32_t, 3>{2,3,1}
            : std::array<std::uint32_t, 3>{0,1,0};
        for (std::size_t i = 0; i < ids.size(); ++i) {
            ArmyExpected a; a.id = ids[i]; a.owner = i == 1u ? -1 : 0; a.slots = slots[i]; a.start = f.data.size();
            const auto name = "army." + std::to_string(i);
            w.Version(name + ".version"); w.I32(name + ".id", a.id); w.I32(name + ".owner", a.owner);
            w.Words(name + ".xy_goal_domain_formation_state_operation", 8); w.Count(name + ".slots", a.slots, true);
            for (std::uint32_t slot = 0; slot < a.slots; ++slot) {
                const auto label = name + ".slot." + std::to_string(slot);
                w.I32(label + ".unit", slot % 2u ? -1 : 8192); w.I32(label + ".checkpoint", -7);
                w.I32(label + ".started", slot % 2u ? 0x12345678 : -9); // int32, not bool.
            }
            a.end = f.data.size(); f.armies.push_back(a);
        }
    }
    f.armyEnd = f.data.size(); f.armyRecords = f.records;
    const auto operationRecordsStart = f.records;
    w.Count("operations.count", static_cast<std::uint32_t>(types.size()));
    for (std::size_t i = 0; i < types.size(); ++i) {
        const auto type = types[i];
        if (type < 0 || type >= 20) throw std::runtime_error("Invalid independent operation fixture type");
        OperationExpected op; op.type = type; op.key = 100 + type; op.id = op.key + (type % 2 ? 10000 : 0);
        if (op.id != op.key) ++f.mismatches;
        op.start = f.data.size(); const auto name = "operation." + std::to_string(i);
        w.I32(name + ".key", op.key); w.I32(name + ".type", type); w.Version(name + ".base_version");
        w.I32(name + ".id", op.id); w.Words(name + ".owner_enemy_state_area", 4);
        w.Bool(name + ".replace_losses", rich); w.Words(name + ".move_target_muster_city_turn", 8);
        w.Count(name + ".armies.count", rich ? 2u : 0u); if (rich) w.Words(name + ".armies.item", 2);
        w.Count(name + ".needed.count", rich ? 2u : 0u); if (rich) w.Words(name + ".needed.item", 6);
        w.Count(name + ".committed.count", rich ? 3u : 0u); if (rich) w.Words(name + ".committed.item", 9);
        w.Derived(name + ".derived", Layouts[static_cast<std::size_t>(type)]);
        op.end = f.data.size(); f.operations.push_back(op);
    }
    f.operationEnd = f.data.size(); f.operationRecords = f.records - operationRecordsStart;
    const auto fieldRecordsStart = f.records;
    w.Begin(0); w.Count("tail.names.count", rich ? 3u : 0u);
    if (rich) {
        w.Text("tail.name.0", "food"); w.Text("tail.name.1", std::string("a\0\xED\x95\x9C", 5));
        w.Text("tail.name.2", "production");
    }
    w.End(0);
    w.Begin(1); w.Count("tail.values.count", rich ? 2u : 0u);
    if (rich) for (std::uint32_t i = 0; i < 2u; ++i) {
        const auto name = "tail.values." + std::to_string(i);
        w.Count(name + ".count", i + 2u);
        for (std::uint32_t turn = 0; turn < i + 2u; ++turn) {
            w.U32(name + ".turn." + std::to_string(turn), turn == 0u ? 0xffffffffu : turn);
            w.I32(name + ".value." + std::to_string(turn), -31);
        }
    }
    w.End(1);
    w.Begin(2); w.Count("tail.votes.count", rich ? 2u : 0u); if (rich) w.Words("tail.votes.item", 4); w.End(2);
    w.Begin(3); w.Count("tail.costs.count", rich ? 3u : 0u); if (rich) w.Words("tail.costs.item", 6); w.End(3);
    w.Begin(4); w.Count("tail.plots.count", rich ? 4u : 0u, true); if (rich) w.Words("tail.plots.item", 4); w.End(4);
    w.Begin(5); w.I32("tail.rush", rich ? -17 : 0); w.I32("tail.improvements", rich ? 91 : 0); w.End(5);
    w.Begin(6); w.Count("tail.ever.count", 64, true);
    for (unsigned i = 0; i < 64; ++i) w.Bool("tail.ever." + std::to_string(i), rich && i % 3u == 1u);
    w.End(6);
    w.Begin(7); w.Text("tail.graphic", rich ? std::string("art\0\x78\x9c\0\0\xff\xff", 10) : std::string{}); w.End(7);
    w.Begin(8); w.Version("tail.achievement_version"); w.I32("tail.achievement.0", -4); w.I32("tail.achievement.1", 11); w.End(8);
    f.fieldEnd = f.data.size(); f.fieldRecords = f.records - fieldRecordsStart;
    w.Version("player_ai.version"); f.end = f.data.size(); w.U32("suffix", 0x9c78beefu); return f;
}
std::uint32_t Word(const Bytes& data, std::size_t offset) {
    if (offset > data.size() || data.size() - offset < 4u) throw std::runtime_error("Fixture word outside input");
    return static_cast<std::uint32_t>(data[offset]) | (static_cast<std::uint32_t>(data[offset + 1u]) << 8) |
        (static_cast<std::uint32_t>(data[offset + 2u]) << 16) | (static_cast<std::uint32_t>(data[offset + 3u]) << 24);
}
void Put(Bytes& data, std::size_t offset, std::uint32_t value) {
    if (offset > data.size() || data.size() - offset < 4u) throw std::runtime_error("Fixture patch outside input");
    for (unsigned i = 0; i < 4; ++i) data[offset + i] = static_cast<unsigned char>(value >> (8u * i));
}
RetailSavePlayerEndInspection Parse(const Fixture& f, const RetailSaveStateLimits& limits = {}) {
    return RetailSavePlayerEnd::InspectAt(f.data.data(), f.data.size(), f.start, EndProfile(), limits);
}
template<class Function> void Reject(Suite& s, Function&& function, Code expected) {
    try { function(); }
    catch (const RetailStateError& error) { s.Check(error.Code() == expected, "Wrong typed Player-end error"); return; }
    s.Check(false, "Invalid Player-end input was accepted");
}
bool SameSpan(const RetailInflatedSpan& a, const RetailInflatedSpan& b) {
    return a.offset == b.offset && a.bytes == b.bytes;
}
std::array<RetailInflatedSpan, FieldSpanCount> FieldSpans(const RetailSavePlayerEndFieldsInspection& r) {
    return {r.replayNames, r.replayValues, r.votes, r.unitCosts, r.plots, r.rushAndImprovements,
        r.everConquered, r.embarkedGraphic, r.achievements};
}
void Invariants(Suite& s, const RetailSavePlayerEndInspection& r, std::size_t size, std::size_t start) {
    auto bounded = [size](const RetailInflatedSpan& span) {
        return span.offset <= size && span.bytes <= size - span.offset;
    };
    s.Check(bounded(r.whole) && r.whole.offset == start && r.nextInflatedOffset >= start &&
        r.nextInflatedOffset <= size && r.whole.bytes == r.nextInflatedOffset - start, "Player-end whole span escaped input");
    s.Check(bounded(r.armyPool.headerSpan) && bounded(r.armyObjects) && bounded(r.armyWhole) &&
        r.armyPool.headerSpan.offset == start && r.armyObjects.offset == r.armyPool.nextInflatedOffset &&
        r.armyPool.nextInflatedOffset == start + r.armyPool.headerSpan.bytes && r.armyWhole.offset == start &&
        r.armyWhole.bytes == r.armyPool.headerSpan.bytes + r.armyObjects.bytes,
        "Army header and actual objects are not adjacent");
    const auto& op = r.operations;
    s.Check(bounded(op.whole) && bounded(op.operations) && op.whole.offset == start + r.armyWhole.bytes &&
        op.operations.offset == op.whole.offset + 4u && op.nextInflatedOffset == op.whole.offset + op.whole.bytes &&
        op.operations.bytes + 4u == op.whole.bytes && r.fields.whole.offset == op.nextInflatedOffset,
        "Operation map boundaries are not contiguous");
    auto next = r.fields.whole.offset;
    for (const auto& span : FieldSpans(r.fields)) {
        s.Check(bounded(span) && span.offset == next, "A Player tail field is not contiguous and bounded");
        next = span.offset + span.bytes;
    }
    s.Check(bounded(r.fields.whole) && next == r.fields.nextInflatedOffset &&
        r.fields.whole.bytes == next - r.fields.whole.offset && r.playerAITrailer.offset == next &&
        r.playerAITrailer.bytes == 4u && bounded(r.playerAITrailer) && next + 4u == r.nextInflatedOffset,
        "Achievement/PlayerAI trailer did not finish the suffix");
    s.Check(!op.objectReferencesVerified && !op.completePlayerVerified && !op.completeSaveVerified &&
        !op.rulesetCompatibilityVerified && !op.restoreApproved && !r.completePlayerVerified &&
        !r.completeSaveVerified && !r.rulesetCompatibilityVerified && !r.restoreApproved,
        "Wire framing granted semantic or restore approval");
}
void Golden(Suite& s, const Fixture& f) {
    const auto before = f.data; const auto r = Parse(f); Invariants(s, r, f.data.size(), f.start);
    s.Check(r.armyPool.slots == f.capacity && r.armyPool.lastIndex == f.last && r.armyPool.freeHead == f.head &&
        r.armyPool.freeCount == f.free && r.armyPool.liveCount == f.armies.size() && r.armyPool.currentId == 8192 &&
        r.armyPool.headerSpan.bytes == 24u + 4u * f.capacity && r.armyPool.nextInflatedOffset == f.armyBody &&
        r.armyObjects.bytes == f.armyEnd - f.armyBody && r.armyWhole.bytes == f.armyEnd - f.start,
        "Army pool metadata or actual object boundary differs");
    RetailStateDetail::Reader armies(f.data.data(), f.data.size(), {}); armies.Skip(f.armyBody);
    for (const auto& expected : f.armies) {
        const auto a = RetailStateDetail::ReadArmyAI(armies);
        s.Check(a.id == expected.id && a.owner == expected.owner && a.slotCount == expected.slots &&
            a.whole.offset == expected.start && a.whole.bytes == 48u + 12u * expected.slots &&
            a.nextInflatedOffset == expected.end && a.arrayRecords == expected.slots,
            "Literal Army v1/48-byte header/12-byte slots differ");
        s.Check(Word(f.data, expected.start) == 1u && Word(f.data, expected.start + 44u) == expected.slots,
            "Army metadata or signed slot count moved");
        if (expected.slots) s.Check(Word(f.data, expected.start + 56u) == 0xfffffff7u,
            "Started-on-operation was not an unrestricted four-byte int");
    }
    s.Check(armies.Pos() == f.armyEnd && armies.Records() + f.capacity + f.armies.size() == f.armyRecords,
        "Army slots or live objects were double-charged");
    if (!f.armies.empty()) s.Check(r.firstArmy.id == f.armies.front().id && r.lastArmy.id == f.armies.back().id &&
        r.firstArmy.whole.offset == f.armies.front().start && r.lastArmy.nextInflatedOffset == f.armies.back().end,
        "First/last Army summaries differ from actual serialized objects");
    const auto& op = r.operations;
    s.Check(op.declaredCount == f.operations.size() && op.keyBodyIdMismatchCount == f.mismatches &&
        op.whole.offset == f.armyEnd && op.nextInflatedOffset == f.operationEnd && op.arrayRecords == f.operationRecords,
        "Operation count, allowed key/ID mismatch aggregation or boundary differs");
    if (!f.operations.empty()) {
        const auto& first = f.operations.front(); const auto& last = f.operations.back();
        s.Check(op.firstMapKey == first.key && op.firstType == first.type && op.firstBodyId == first.id &&
            op.firstOperation.offset == first.start && op.firstOperation.bytes == first.end - first.start &&
            op.lastMapKey == last.key && op.lastType == last.type && op.lastBodyId == last.id &&
            op.lastOperation.offset == last.start && op.lastOperation.bytes == last.end - last.start,
            "First/last operation bodies differ from independent factory fixtures");
    }
    for (const auto& expected : f.operations) {
        const auto& layout = Layouts[static_cast<std::size_t>(expected.type)];
        s.Check(layout.type == expected.type && expected.end - expected.start == layout.minimumRecordBytes + (f.rich ? 68u : 0u),
            "A literal operation factory size differs");
    }
    const auto spans = FieldSpans(r.fields);
    for (std::size_t i = 0; i < spans.size(); ++i)
        s.Check(SameSpan(spans[i], f.fields[i]), "A source-wire tail field boundary differs");
    s.Check(r.fields.replayDataSets == (f.rich ? 3u : 0u) && r.fields.replayValueDataSets == (f.rich ? 2u : 0u) &&
        r.fields.voteCount == (f.rich ? 2u : 0u) && r.fields.unitCostCount == (f.rich ? 3u : 0u) &&
        r.fields.plotCount == (f.rich ? 4u : 0u) && r.fields.everCount == 64u &&
        r.fields.rushHurryCount == (f.rich ? -17 : 0) && r.fields.totalImprovementsBuilt == (f.rich ? 91 : 0) &&
        r.fields.arrayRecords == f.fieldRecords && r.fields.nextInflatedOffset == f.fieldEnd &&
        r.playerAITrailer.offset == f.fieldEnd && r.nextInflatedOffset == f.end && r.arrayRecords == f.records &&
        f.records == f.armyRecords + f.operationRecords + f.fieldRecords,
        "Player tail counters, shared record ownership or AI trailer boundary differs");
    if (!f.rich) {
        const std::array<std::size_t, FieldSpanCount> minimum = {4,4,4,4,4,8,68,4,12};
        for (std::size_t i = 0; i < minimum.size(); ++i)
            s.Check(spans[i].bytes == minimum[i], "Literal 112-byte current-v16 tail differs");
    }
    if (!f.rich && f.capacity == 0u && f.operations.empty())
        s.Check(f.end - f.start == 144u && r.arrayRecords == 64u, "Independent 144-byte suffix minimum differs");
    s.Check(Word(f.data, f.end) == 0x9c78beefu && f.data == before,
        "Player-end parser consumed the sentinel or changed caller bytes");
}
void Negative(Suite& s, const Fixture& minimum, const Fixture& rich) {
    for (auto at : rich.versions) {
        auto f = rich; Put(f.data, at, 127); Reject(s, [&] { Parse(f); }, Code::UnsupportedVersion);
    }
    for (auto at : rich.bools) {
        auto f = rich; f.data[at] = 2; Reject(s, [&] { Parse(f); }, Code::InvalidValue);
    }
    for (auto at : rich.unsignedCounts) {
        auto f = rich; Put(f.data, at, 0xffffffffu); Reject(s, [&] { Parse(f); }, Code::ArrayLimit);
    }
    for (auto at : rich.signedCounts) {
        auto f = rich; Put(f.data, at, 0xffffffffu); Reject(s, [&] { Parse(f); }, Code::InvalidValue);
    }
    for (auto type : {0xffffffffu, 20u, 0x7fffffffu, 0x80000000u}) {
        auto f = rich; Put(f.data, f.marks.at("operation.0.type"), type);
        Reject(s, [&] { Parse(f); }, Code::UnsupportedProfile);
    }
    for (auto count : {0u, 1u, 63u, 65u}) {
        auto f = rich; Put(f.data, f.marks.at("tail.ever.count"), count);
        Reject(s, [&] { Parse(f); }, Code::InvalidValue);
    }
    auto f = rich; Put(f.data, f.marks.at("pool.capacity"), 3);
    Reject(s, [&] { Parse(f); }, Code::InvalidValue);
    f = rich; Put(f.data, f.marks.at("pool.last"), f.capacity);
    Reject(s, [&] { Parse(f); }, Code::InvalidValue);
    f = rich; Put(f.data, f.marks.at("pool.free"), 0xffffffffu);
    Reject(s, [&] { Parse(f); }, Code::InvalidValue);
    f = rich; Put(f.data, f.marks.at("pool.current_id"), 8193);
    Reject(s, [&] { Parse(f); }, Code::InvalidValue);
    f = rich; Put(f.data, f.marks.at("pool.live"), 4);
    Reject(s, [&] { Parse(f); }, Code::InvalidValue);
    f = rich; Put(f.data, f.marks.at("pool.link.1"), 1);
    Reject(s, [&] { Parse(f); }, Code::InvalidValue);
    f = rich; Put(f.data, f.marks.at("pool.current_id"), 0);
    s.Check(Parse(f).nextInflatedOffset == f.end, "Opaque zero Army generation was overconstrained");
    Put(f.data, f.marks.at("pool.current_id"), 0xffffe000u);
    s.Check(Parse(f).nextInflatedOffset == f.end, "Opaque signed Army generation was overconstrained");
    f = rich; Put(f.data, f.marks.at("operation.0.key"), 0xffffffffu);
    s.Check(Parse(f).operations.keyBodyIdMismatchCount == f.mismatches + 1u,
        "Original reader's discarded map key became an invented wire constraint");
    auto profile = EndProfile(); profile.operationProfile = static_cast<RetailPlayerOperationsProfile>(99);
    Reject(s, [&] { RetailSavePlayerEnd::InspectAt(minimum.data.data(), minimum.data.size(), minimum.start, profile); }, Code::UnsupportedProfile);
    profile = EndProfile(); profile.fieldProfile = static_cast<RetailPlayerEndWriterProfile>(99);
    Reject(s, [&] { RetailSavePlayerEnd::InspectAt(minimum.data.data(), minimum.data.size(), minimum.start, profile); }, Code::UnsupportedProfile);
    Reject(s, [&] { RetailSavePlayerEnd::InspectAt(nullptr, 1, 0, EndProfile()); }, Code::NullInput);
    Reject(s, [&] { RetailSavePlayerEnd::InspectAt(nullptr, 0, 0, EndProfile()); }, Code::Truncated);
    Reject(s, [&] { RetailSavePlayerEnd::InspectAt(minimum.data.data(), minimum.data.size(), minimum.data.size() + 1u, EndProfile()); }, Code::Truncated);
    Reject(s, [&] { RetailSavePlayerEnd::InspectAt(minimum.data.data(), minimum.data.size(), (std::numeric_limits<std::size_t>::max)(), EndProfile()); }, Code::Truncated);
    auto limits = RetailSaveStateLimits{}; limits.maxInputBytes = rich.data.size();
    s.Check(Parse(rich, limits).nextInflatedOffset == rich.end, "Exact suffix input budget rejected");
    --limits.maxInputBytes; Reject(s, [&] { Parse(rich, limits); }, Code::InputLimit);
    limits = {}; limits.maxPrefixBytes = rich.end;
    s.Check(Parse(rich, limits).nextInflatedOffset == rich.end, "Exact absolute suffix byte budget rejected");
    --limits.maxPrefixBytes; Reject(s, [&] { Parse(rich, limits); }, Code::PrefixLimit);
    limits = {}; limits.maxStringBytes = rich.maxString;
    s.Check(Parse(rich, limits).nextInflatedOffset == rich.end, "Exact suffix string budget rejected");
    --limits.maxStringBytes; Reject(s, [&] { Parse(rich, limits); }, Code::StringLimit);
    limits = {}; limits.maxArrayRecords = rich.maxCount;
    s.Check(Parse(rich, limits).fields.everCount == 64u, "Exact array budget rejected fixed 64 flags");
    --limits.maxArrayRecords; Reject(s, [&] { Parse(rich, limits); }, Code::ArrayLimit);
    limits = {}; limits.maxTotalRecords = rich.records;
    s.Check(Parse(rich, limits).arrayRecords == rich.records, "Exact aggregate Army/operations/tail budget rejected");
    --limits.maxTotalRecords; Reject(s, [&] { Parse(rich, limits); }, Code::TotalRecordLimit);
    limits = {}; limits.maxTotalRecords = std::max({rich.armyRecords, rich.operationRecords, rich.fieldRecords});
    s.Check(limits.maxTotalRecords < rich.records, "Rich fixture lost its cross-component shared budget test");
    Reject(s, [&] { Parse(rich, limits); }, Code::TotalRecordLimit);
    limits = {}; limits.maxTotalRecords = 64u; limits.maxArrayRecords = 64u; limits.maxStringBytes = 0;
    s.Check(Parse(minimum, limits).arrayRecords == 64u, "Empty suffix charged rows absent from the wire");
    --limits.maxTotalRecords; Reject(s, [&] { Parse(minimum, limits); }, Code::TotalRecordLimit);
    // Raised caller budgets must not turn multiplication or huge counts into
    // wraparound, allocation, signature search or acceptance of a short body.
    limits = {}; limits.maxArrayRecords = (std::numeric_limits<std::size_t>::max)();
    limits.maxTotalRecords = (std::numeric_limits<std::size_t>::max)();
    for (const auto* name : {"operations.count", "operation.0.armies.count", "operation.0.needed.count",
            "operation.0.committed.count", "tail.names.count", "tail.values.count", "tail.values.0.count", "tail.votes.count", "tail.costs.count"}) {
        f = rich; Put(f.data, f.marks.at(name), 0xffffffffu);
        Reject(s, [&] { Parse(f, limits); }, Code::Truncated);
    }
    f = rich; Put(f.data, f.marks.at("army.0.slots"), 0x7fffffffu);
    Reject(s, [&] { Parse(f, limits); }, Code::Truncated);
    f = rich; Put(f.data, f.marks.at("tail.plots.count"), 0x7fffffffu);
    Reject(s, [&] { Parse(f, limits); }, Code::Truncated);
    f = minimum; f.data.resize(f.fieldEnd);
    Reject(s, [&] { Parse(f); }, Code::Truncated); // Mandatory CvPlayerAI v1 word.
}
void Cuts(Suite& s, const Fixture& f) {
    for (std::size_t cut = 0; cut < f.end; ++cut) {
        Reject(s, [&] { RetailSavePlayerEnd::InspectAt(f.data.data(), cut, f.start, EndProfile()); }, Code::Truncated);
        ++s.truncations;
    }
}
struct Observation {
    RetailSavePlayerEndInspection result;
    bool accepted = false;
    Code error = Code::InvalidValue;
    std::size_t errorOffset = 0;
};
Observation Observe(const Fixture& f) {
    Observation r;
    try { r.result = Parse(f); r.accepted = true; }
    catch (const RetailStateError& error) { r.error = error.Code(); r.errorOffset = error.Offset(); }
    return r;
}
std::uint32_t Random(std::uint32_t& value) {
    value ^= value << 13; value ^= value >> 17; value ^= value << 5; return value;
}
void Mutations(Suite& s, const std::vector<Fixture>& fixtures) {
    std::uint32_t state = 0x49a19d37u;
    for (unsigned i = 0; i < 2048u; ++i) {
        auto f = fixtures[Random(state) % fixtures.size()];
        switch (i % 8u) {
        case 0: f.data[Random(state) % f.data.size()] ^= static_cast<unsigned char>(1u << (Random(state) % 8u)); break;
        case 1: f.data.resize(Random(state) % f.data.size()); break;
        case 2: Put(f.data, f.versions[Random(state) % f.versions.size()], Random(state)); break;
        case 3: f.data[f.bools[Random(state) % f.bools.size()]] = 2; break;
        case 4: Put(f.data, f.marks.at(f.operations.empty() ? "pool.current_id" : "operation.0.key"), Random(state)); break;
        case 5: Put(f.data, f.unsignedCounts[Random(state) % f.unsignedCounts.size()], Random(state)); break;
        case 6: Put(f.data, f.marks.at(f.operations.empty() ? "tail.ever.count" : "operation.0.type"), Random(state)); break;
        default: Put(f.data, f.end, Random(state)); break;
        }
        const auto before = f.data; const auto a = Observe(f), b = Observe(f);
        s.Check(a.accepted == b.accepted && a.error == b.error && a.errorOffset == b.errorOffset &&
            a.result.nextInflatedOffset == b.result.nextInflatedOffset && a.result.arrayRecords == b.result.arrayRecords &&
            a.result.operations.keyBodyIdMismatchCount == b.result.operations.keyBodyIdMismatchCount &&
            a.result.armyPool.liveCount == b.result.armyPool.liveCount && a.result.fields.everCount == b.result.fields.everCount,
            "Player-end mutation framing is nondeterministic");
        s.Check(f.data == before, "Mutation parsing modified caller bytes");
        if (a.accepted) { Invariants(s, a.result, f.data.size(), f.start); ++s.accepted; }
        else { s.Check(a.errorOffset <= f.data.size(), "Mutation error escaped the input"); ++s.rejected; }
    }
}
Bytes ReadStdin() {
#if defined(_WIN32)
    if (_setmode(_fileno(stdin), _O_BINARY) == -1) throw std::runtime_error("Cannot select binary stdin");
#endif
    Bytes data; std::array<char, 16384> block{};
    while (std::cin.read(block.data(), static_cast<std::streamsize>(block.size())) || std::cin.gcount() > 0) {
        const auto count = std::cin.gcount();
        if (count < 0 || static_cast<std::size_t>(count) > 64u * 1024u * 1024u - data.size())
            throw std::runtime_error("Public stdin exceeded its budget");
        data.insert(data.end(), block.data(), block.data() + count);
    }
    if (!std::cin.eof()) throw std::runtime_error("Public stdin read failed");
    return data;
}
struct PublicResult {
    RetailSavePlayerInspection player;
    RetailSavePlayerEndInspection direct;
    RetailSavePlayerPrefixInspection nextPrefix;
    std::size_t bytes = 0;
    std::uint32_t nextVersion = 0;
};
void SameEnd(Suite& s, const RetailSavePlayerEndInspection& a, const RetailSavePlayerEndInspection& b) {
    s.Check(SameSpan(a.whole, b.whole) && SameSpan(a.armyPool.headerSpan, b.armyPool.headerSpan) &&
        SameSpan(a.armyObjects, b.armyObjects) && SameSpan(a.armyWhole, b.armyWhole) &&
        SameSpan(a.operations.whole, b.operations.whole) && SameSpan(a.fields.whole, b.fields.whole) &&
        SameSpan(a.playerAITrailer, b.playerAITrailer) && a.nextInflatedOffset == b.nextInflatedOffset &&
        a.arrayRecords == b.arrayRecords && a.armyPool.slots == b.armyPool.slots &&
        a.armyPool.liveCount == b.armyPool.liveCount && a.operations.arrayRecords == b.operations.arrayRecords &&
        a.operations.declaredCount == b.operations.declaredCount && a.fields.arrayRecords == b.fields.arrayRecords &&
        a.fields.everCount == b.fields.everCount, "Direct suffix and assembled Player disagree");
    const auto aa = FieldSpans(a.fields), bb = FieldSpans(b.fields);
    for (std::size_t i = 0; i < aa.size(); ++i)
        s.Check(SameSpan(aa[i], bb[i]), "Direct/assembled Player tail field differs");
}
PublicResult Public(Suite& s) {
    const auto bytes = ReadStdin(), before = bytes;
    // The root runner authenticates the public RAM input before forwarding it.
    // This process has no path argument and neither opens nor rewrites files.
    s.Check(bytes.size() == 9762327u, "Wrong externally authenticated public plaintext size");
    auto remaining = RetailSaveStateLimits{};
    const auto map = RetailSaveMap::InspectGameAndMap(bytes, RetailSaveStateProfile(5), remaining);
    s.Check(map.nextInflatedOffset == 1695150u && map.plotCount == 960u && map.arrayRecords <= remaining.maxTotalRecords,
        "Source-ordered public Map boundary or budget differs");
    remaining.maxTotalRecords -= map.arrayRecords;
    RetailStateDetail::Reader teams(bytes.data(), bytes.size(), remaining); teams.Skip(map.nextInflatedOffset);
    for (std::int32_t id = 0; id < 64; ++id)
        s.Check(RetailStateDetail::ReadTeam(teams) == id, "Source-ordered public Team ID differs");
    s.Check(teams.Pos() == 2309550u && teams.Records() <= remaining.maxTotalRecords,
        "Source-ordered 64-Team boundary differs");
    remaining.maxTotalRecords -= teams.Records();
    PublicResult result; result.bytes = bytes.size();
    const auto profile = PlayerProfile();
    result.player = RetailSavePlayer::InspectAt(bytes.data(), bytes.size(), teams.Pos(), profile, remaining);
    const auto& p = result.player;
    s.Check(p.playerId == 0 && p.prefix.playerId == 0 && p.whole.offset == 2309550u &&
        p.prefix.nextInflatedOffset == 2326136u && p.middle.nextInflatedOffset == 2403477u &&
        p.late.nextInflatedOffset == 2421545u && p.late.dangerPlotCount == map.plotCount &&
        p.postTraits.nextInflatedOffset == 2427999u && p.cities.nextInflatedOffset == 2428055u &&
        p.cities.pool.liveCount == 0u && p.units.nextInflatedOffset == 2444247u && p.units.pool.liveCount == 9u,
        "Complete Player assembly differs from independently retained stage boundaries");
    const auto precedingRecords = p.prefix.arrayRecords + p.middle.arrayRecords + p.late.arrayRecords +
        p.postTraits.arrayRecords + p.cities.arrayRecords + p.units.arrayRecords;
    s.Check(precedingRecords <= remaining.maxTotalRecords && p.arrayRecords == precedingRecords + p.ending.arrayRecords,
        "Assembled Player did not share all stage record budgets exactly once");
    auto suffixLimits = remaining; suffixLimits.maxTotalRecords -= precedingRecords;
    result.direct = RetailSavePlayerEnd::InspectAt(bytes.data(), bytes.size(), 2444247u, EndProfile(), suffixLimits);
    const auto& r = result.direct; Invariants(s, r, bytes.size(), 2444247u); SameEnd(s, p.ending, r);
    s.Check(r.armyPool.slots == 8u && r.armyPool.liveCount == 0u && r.armyPool.headerSpan.offset == 2444247u &&
        r.armyPool.headerSpan.bytes == 56u && r.armyPool.nextInflatedOffset == 2444303u && r.armyObjects.bytes == 0u &&
        r.nextInflatedOffset > 2444247u && r.fields.everCount == 64u &&
        Word(bytes, r.playerAITrailer.offset) == 1u, "Public Army header or mandatory tail/trailer differs");
    s.Check(p.nextInflatedOffset == r.nextInflatedOffset && p.whole.bytes == p.nextInflatedOffset - p.whole.offset &&
        p.completePlayerWireFramed && !p.completePlayerVerified && !p.completeSaveVerified &&
        !p.rulesetCompatibilityVerified && !p.restoreApproved && !p.units.unitObjectIdsVerified &&
        !p.units.restoreApproved && !p.cities.restoreApproved && !map.completeSaveVerified,
        "Complete Player wire frame granted semantic, save or restore approval");
    // This is the exact returned next offset. No version, ID or magic search
    // selects the next Player or changes the caller's declared profiles.
    s.Check(p.arrayRecords <= remaining.maxTotalRecords, "Player exhausted the source-ordered public budget");
    auto after = remaining; after.maxTotalRecords -= p.arrayRecords;
    result.nextVersion = Word(bytes, p.nextInflatedOffset);
    result.nextPrefix = RetailSavePlayerPrefix::InspectAt(bytes.data(), bytes.size(), p.nextInflatedOffset,
        profile.prefixProfile, after);
    s.Check(result.nextVersion == 16u && result.nextPrefix.playerId == 1 &&
        result.nextPrefix.front.offset == p.nextInflatedOffset && result.nextPrefix.nextInflatedOffset > p.nextInflatedOffset,
        "Exact next offset did not begin the expected Player-1 v16 prefix");
    auto exact = remaining; exact.maxTotalRecords = p.arrayRecords;
    s.Check(RetailSavePlayer::InspectAt(bytes.data(), bytes.size(), p.whole.offset, profile, exact).arrayRecords == p.arrayRecords,
        "Exact complete Player shared budget rejected");
    --exact.maxTotalRecords;
    Reject(s, [&] { RetailSavePlayer::InspectAt(bytes.data(), bytes.size(), p.whole.offset, profile, exact); }, Code::TotalRecordLimit);
    exact = suffixLimits; exact.maxTotalRecords = r.arrayRecords;
    s.Check(RetailSavePlayerEnd::InspectAt(bytes.data(), bytes.size(), 2444247u, EndProfile(), exact).arrayRecords == r.arrayRecords,
        "Exact public suffix record budget rejected");
    --exact.maxTotalRecords;
    Reject(s, [&] { RetailSavePlayerEnd::InspectAt(bytes.data(), bytes.size(), 2444247u, EndProfile(), exact); }, Code::TotalRecordLimit);
    s.Check(bytes == before, "Public full Player parsing modified plaintext input"); return result;
}
void PublicJson(const PublicResult& value) {
    const auto& p = value.player; const auto& r = value.direct; const auto& f = r.fields;
    std::cout << ",\"public\":{\"input_bytes\":" << value.bytes << ",\"start_offset\":2444247"
        << ",\"next_inflated_offset\":" << r.nextInflatedOffset << ",\"army_capacity\":" << r.armyPool.slots
        << ",\"army_count\":" << r.armyPool.liveCount << ",\"army_header_end\":" << r.armyPool.nextInflatedOffset
        << ",\"army_objects_bytes\":" << r.armyObjects.bytes << ",\"operation_count\":" << r.operations.declaredCount
        << ",\"operation_key_id_mismatches\":" << r.operations.keyBodyIdMismatchCount
        << ",\"operation_bytes\":" << r.operations.whole.bytes << ",\"replay_name_count\":" << f.replayDataSets
        << ",\"replay_value_dataset_count\":" << f.replayValueDataSets << ",\"vote_count\":" << f.voteCount
        << ",\"unit_cost_count\":" << f.unitCostCount << ",\"plot_count\":" << f.plotCount << ",\"ever_count\":" << f.everCount
        << ",\"rush_hurry_count\":" << f.rushHurryCount << ",\"improvements_built\":" << f.totalImprovementsBuilt
        << ",\"tail_offset\":" << f.whole.offset << ",\"tail_bytes\":" << f.whole.bytes
        << ",\"player_ai_trailer_offset\":" << r.playerAITrailer.offset << ",\"player_ai_trailer_bytes\":" << r.playerAITrailer.bytes
        << ",\"array_records\":" << r.arrayRecords << ",\"player_start_offset\":" << p.whole.offset
        << ",\"player_bytes\":" << p.whole.bytes << ",\"player_array_records\":" << p.arrayRecords
        << ",\"complete_player_wire_framed\":true,\"first_player_id\":" << p.playerId
        << ",\"next_player_prefix_id\":" << value.nextPrefix.playerId << ",\"next_player_prefix_version\":" << value.nextVersion
        << ",\"next_player_prefix_end\":" << value.nextPrefix.nextInflatedOffset
        << ",\"direct_end_matches_player\":true,\"source_ordered\":true,\"pattern_search_used\":false"
        << ",\"complete_player_validated\":false,\"complete_save_validated\":false"
        << ",\"ruleset_compatibility_verified\":false,\"restore_approved\":false}";
}
std::string Escape(const char* raw) {
    std::string value;
    for (const unsigned char* p = reinterpret_cast<const unsigned char*>(raw); *p; ++p) {
        if (*p == '"' || *p == '\\') value += '\\';
        value += *p < 32 ? '?' : static_cast<char>(*p);
    }
    return value;
}
} // namespace

int main(int argc, char** argv) {
    try {
        static_assert(sizeof(void*) == 8, "Player-end component verification requires x64");
        const bool publicMode = argc == 2 && std::string(argv[1]) == "--public";
        if (argc != 1 && !publicMode) throw std::runtime_error("Expected no arguments or --public");
        Suite s;
        std::vector<Fixture> fixtures = {Make(false, false, false, {}), Make(false, true, false, {}, 8),
            Make(false, false, false, AllTypes()), Make(true, true, true, AllTypes()),
            Make(false, true, true, {19,0,11,13})};
        // Each factory type is also tested alone, with zero and nonzero inner
        // collections. This makes every literal suffix both first and last.
        for (std::int32_t type = 0; type < 20; ++type) {
            fixtures.push_back(Make(false, type % 2 != 0, false, {type}));
            fixtures.push_back(Make(true, type % 2 == 0, false, {type}));
        }
        for (const auto& f : fixtures) Golden(s, f);
        Negative(s, fixtures[0], fixtures[3]); Cuts(s, fixtures[0]); Cuts(s, fixtures[3]); Mutations(s, fixtures);
        PublicResult publicResult; if (publicMode) publicResult = Public(s);
        s.Check(s.truncations >= 144u && s.checks > 1000u && s.accepted + s.rejected == 2048u,
            "Player-end verification accounting differs");
        std::cout << "{\"status\":\"PASS_RETAIL_PLAYER_END_COMPONENT\",\"checks\":" << s.checks
            << ",\"synthetic_cases\":" << fixtures.size() << ",\"operation_types\":20,\"operation_minimum_cases\":20"
            << ",\"operation_rich_cases\":20,\"actual_army_pool_cases\":2,\"minimum_bytes\":144"
            << ",\"truncations\":" << s.truncations << ",\"mutations\":2048,\"accepted_mutations\":" << s.accepted
            << ",\"rejected_mutations\":" << s.rejected << ",\"input_files_unchanged\":true,\"input_bytes_unchanged\":true"
            << ",\"gamecore_loaded\":false,\"window_created\":false,\"game_accessed\":false,\"user_saves_accessed\":false"
            << ",\"complete_player_validated\":false,\"complete_save_validated\":false"
            << ",\"ruleset_compatibility_verified\":false,\"restore_approved\":false";
        if (publicMode) PublicJson(publicResult);
        std::cout << "}\n"; return 0;
    } catch (const RetailStateError& error) {
        std::cout << "{\"status\":\"FAIL_RETAIL_PLAYER_END_COMPONENT\",\"error\":\"" << Escape(error.what())
            << "\",\"error_code\":" << static_cast<int>(error.Code()) << ",\"error_offset\":" << error.Offset()
            << ",\"gamecore_loaded\":false,\"window_created\":false,\"game_accessed\":false"
            << ",\"user_saves_accessed\":false,\"complete_player_validated\":false,\"complete_save_validated\":false"
            << ",\"ruleset_compatibility_verified\":false,\"restore_approved\":false}\n"; return 1;
    } catch (const std::exception& error) {
        std::cout << "{\"status\":\"FAIL_RETAIL_PLAYER_END_COMPONENT\",\"error\":\"" << Escape(error.what())
            << "\",\"gamecore_loaded\":false,\"window_created\":false,\"game_accessed\":false"
            << ",\"user_saves_accessed\":false,\"complete_player_validated\":false,\"complete_save_validated\":false"
            << ",\"ruleset_compatibility_verified\":false,\"restore_approved\":false}\n"; return 1;
    }
}
