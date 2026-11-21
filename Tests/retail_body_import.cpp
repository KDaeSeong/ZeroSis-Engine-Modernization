#include "RetailSaveBodyImport.h"
#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <exception>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>
#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif

// Operation literals test only the internal edit planner. Whole-body tests use
// caller-supplied public stdin and are not independent synthetic save fixtures.
namespace {
using namespace ZeroSisHost;
using Bytes = std::vector<unsigned char>;
using Edits = std::vector<RetailBodyBooleanEdit>;
using Code = RetailStateErrorCode;
using Policy = RetailBodyBooleanImportPolicy;
constexpr std::size_t MaximumInput = 64u * 1024u * 1024u;
constexpr std::size_t Absent = (std::numeric_limits<std::size_t>::max)();
constexpr auto OperationsProfile = RetailPlayerOperationsProfile::BnwCurrentFactory20;

struct Suite {
    std::size_t checks = 0, syntheticOperations = 0, rawBooleans = 0;
    std::size_t truncations = 0, corruptions = 0, atomicFailures = 0, playerGroups = 0;
    void Check(bool value, const char* message) {
        ++checks;
        if (!value) throw std::runtime_error(message);
    }
};
enum class Mode { Unselected, SelfTest, Public };
struct Options {
    Mode mode = Mode::Unselected;
    std::uint32_t awards = 0, grand = 0, projects = 0;
    std::size_t maximumInput = MaximumInput, recordBudget = 1024u * 1024u;
};
std::uint32_t Number(const char* text, std::uint32_t maximum) {
    if (!text || !*text) throw std::invalid_argument("Missing decimal argument");
    std::uint32_t value = 0;
    for (const char* p = text; *p; ++p) {
        if (*p < '0' || *p > '9') throw std::invalid_argument("Arguments require decimal digits only");
        const auto digit = static_cast<std::uint32_t>(*p - '0');
        if (digit > maximum || value > (maximum - digit) / 10u)
            throw std::invalid_argument("Decimal argument exceeds its bound");
        value = value * 10u + digit;
    }
    return value;
}
Options Arguments(int argc, char** argv) {
    Options options;
    if (argc == 2 && std::strcmp(argv[1], "--self-test") == 0) {
        options.mode = Mode::SelfTest; return options;
    }
    if (argc != 7 || std::strcmp(argv[1], "--public") != 0)
        throw std::invalid_argument("Require --self-test or --public awards grand projects maxInput recordBudget");
    options.mode = Mode::Public;
    options.awards = Number(argv[2], 4096u); options.grand = Number(argv[3], 4096u);
    options.projects = Number(argv[4], 4096u);
    options.maximumInput = Number(argv[5], static_cast<std::uint32_t>(MaximumInput));
    options.recordBudget = Number(argv[6], static_cast<std::uint32_t>(MaximumInput));
    if (!options.maximumInput || !options.recordBudget) throw std::invalid_argument("Budgets must be positive");
    return options;
}
RetailSaveBodyImportProfile Profile(const Options& options) {
    const RetailSavePlayerWireProfile player{
        RetailSavePlayerProfile(options.grand, RetailPlayerCatalogProfile::InitializedBuildings),
        RetailPlayerAiMidCatalogProfile::InitializedTechs, RetailPlayerAiLateProfile::InitializedMinorQuests,
        RetailSaveCityProfile(options.projects, RetailCityProductionCatalogProfile::InitializedBuildingsAndUnits, 6u),
        RetailUnitWriterProfile::Bnw9CompleteGreatWorkHashWord,
        RetailSavePlayerEndProfile(OperationsProfile, RetailPlayerEndWriterProfile::Current16With64Players)};
    return {RetailBodyLayout::Bnw64GameMapTeamsPlayersSupporting, RetailSaveStateProfile(options.awards), player};
}

// Version + five int32 words, then the independently positioned raw byte at 24;
// eight unrestricted words and three zero vector counts follow. Integer byte 68
// is intentional and must not be changed by boolean conversion.
constexpr std::array<unsigned char, 69> Base = {{
    1,0,0,0, 7,0,0,0, 0,0,0,0, 255,255,255,255, 2,0,0,0, 255,255,255,255,
    0,
    255,255,255,255, 68,0,0,0, 3,0,0,0, 255,255,255,255,
    4,0,0,0, 255,255,255,255, 255,255,255,255, 10,0,0,0,
    0,0,0,0, 0,0,0,0, 0,0,0,0
}};
constexpr std::array<unsigned char, 40> NonemptyVectors = {{
    1,0,0,0, 68,0,0,0,
    1,0,0,0, 7,0,0,0, 8,0,0,0, 9,0,0,0,
    1,0,0,0, 7,0,0,0, 8,0,0,0, 10,0,0,0
}};
struct Layout {
    std::int32_t type;
    Bytes derived;
    std::vector<std::size_t> versions;
    std::size_t derivedBool;
};
const std::array<Layout, 20> Layouts = {{
    {0,{1,0,0,0},{0},Absent}, {1,{1,0,0,0},{0},Absent}, {2,{1,0,0,0},{0},Absent},
    {3,{1,0,0,0,1,255,255,255,255},{0},4},
    {4,{1,0,0,0,1,255,255,255,255,2,0,0,0},{0},4},
    {5,{1,0,0,0},{0},Absent}, {6,{1,0,0,0},{0},Absent}, {7,{1,0,0,0},{0},Absent},
    {8,{1,0,0,0,1,255,255,255,255,2,0,0,0},{0},4},
    {9,{1,0,0,0,1,0,0,0},{0,4},Absent}, {10,{1,0,0,0,1,0,0,0},{0,4},Absent},
    {11,{1,0,0,0,255,255,255,255},{0},Absent},
    {12,{1,0,0,0,1,255,255,255,255,2,0,0,0},{0},4},
    {13,{1,0,0,0,255,255,255,255,1,0,0,0},{0,8},Absent},
    {14,{1,0,0,0,255,255,255,255,1,0,0,0},{0,8},Absent},
    {15,{1,0,0,0},{0},Absent},
    {16,{1,0,0,0,255,255,255,255,1,0,0,0},{0,8},Absent},
    {17,{1,0,0,0,255,255,255,255},{0},Absent},
    {18,{1,0,0,0,1,0,0,0},{0,4},Absent},
    {19,{1,0,0,0,1,255,255,255,255,2,0,0,0},{0},4}
}};
constexpr std::array<std::size_t, 20> AllTypeOffsets = {{
    39,120,201,282,368,458,539,620,701,791,876,961,1046,1136,1225,1314,1395,1484,1569,1654
}};
struct Record {
    std::size_t start = 0, base = 0, derived = 0;
    std::int32_t type = -1;
};
struct OperationFixture {
    Bytes data;
    RetailInflatedSpan whole;
    std::vector<Record> records;
    std::size_t arrayRecords = 0;
};
OperationFixture MakeOperations(const std::vector<std::int32_t>& types,
    const Bytes& values, bool richFirst = false) {
    if (types.size() > 20u || types.size() != values.size()) throw std::runtime_error("Invalid test fixture request");
    OperationFixture fixture;
    fixture.data = {0xa6,0,68}; fixture.whole.offset = 3;
    fixture.data.insert(fixture.data.end(), {static_cast<unsigned char>(types.size()),0,0,0});
    fixture.arrayRecords = types.size();
    for (std::size_t i = 0; i < types.size(); ++i) {
        const auto type = types[i];
        if (type < 0 || type >= 20) throw std::runtime_error("Unsupported test literal type");
        Record record; record.start = fixture.data.size(); record.type = type;
        fixture.data.insert(fixture.data.end(), {85,0,0,0,static_cast<unsigned char>(type),0,0,0});
        record.base = fixture.data.size();
        if (richFirst && i == 0u) {
            fixture.data.insert(fixture.data.end(), Base.begin(), Base.begin() + 57);
            fixture.data.insert(fixture.data.end(), NonemptyVectors.begin(), NonemptyVectors.end());
            fixture.arrayRecords += 3;
        } else fixture.data.insert(fixture.data.end(), Base.begin(), Base.end());
        fixture.data[record.base + 24u] = values[i];
        record.derived = fixture.data.size();
        const auto& layout = Layouts[static_cast<std::size_t>(type)];
        fixture.data.insert(fixture.data.end(), layout.derived.begin(), layout.derived.end());
        fixture.records.push_back(record);
    }
    fixture.whole.bytes = fixture.data.size() - fixture.whole.offset;
    fixture.data.insert(fixture.data.end(), {68,255,2});
    return fixture;
}
Edits Plan(const OperationFixture& fixture, std::uint32_t player = 0,
    const RetailSaveStateLimits& limits = {}) {
    return RetailBodyImportDetail::CollectOperationEdits(fixture.data.data(), fixture.data.size(),
        fixture.whole, player, OperationsProfile, limits);
}
bool SameEdits(const Edits& a, const Edits& b) {
    if (a.size() != b.size()) return false;
    for (std::size_t i = 0; i < a.size(); ++i)
        if (a[i].offset != b[i].offset || a[i].before != b[i].before || a[i].after != b[i].after ||
            a[i].playerSlot != b[i].playerSlot || a[i].operationIndex != b[i].operationIndex) return false;
    return true;
}
void PutWord(Bytes& bytes, std::size_t offset, std::uint32_t value) {
    if (offset > bytes.size() || bytes.size() - offset < 4u) throw std::runtime_error("Test corruption out of range");
    for (unsigned shift = 0; shift < 32u; shift += 8u) bytes[offset + shift / 8u] = static_cast<unsigned char>(value >> shift);
}

bool SpanEqual(const RetailInflatedSpan& a, const RetailInflatedSpan& b) {
    return a.offset == b.offset && a.bytes == b.bytes;
}
Bytes Apply(const Bytes& input, const Edits& edits) {
    Bytes result = input;
    for (const auto& edit : edits) {
        if (edit.offset >= result.size() || result[edit.offset] != edit.before || edit.before <= 1u || edit.after != 1u)
            throw std::runtime_error("Unexpected test edit plan");
        result[edit.offset] = edit.after;
    }
    return result;
}
template<class Function>
void RejectPlan(Suite& suite, const Bytes& input, Function function, Code expected,
    std::size_t offset = Absent) {
    const auto before = input;
    const Edits sentinel = {{1,68,1,63,31}};
    Edits output = sentinel;
    bool caught = false;
    try { output = function(); }
    catch (const RetailStateError& error) {
        caught = true;
        suite.Check(error.Code() == expected, "Planner failure has the wrong typed code");
        suite.Check(offset == Absent ? error.Offset() <= input.size() : error.Offset() == offset,
            "Planner failure has the wrong offset");
    }
    suite.Check(caught, "Invalid operation plan was returned");
    suite.Check(SameEdits(output, sentinel) && input == before, "Failed plan replaced its output or changed its input");
    ++suite.atomicFailures;
}
template<class Function>
void RejectStrict(Suite& suite, Function function, Code code, std::size_t offset) {
    bool caught = false;
    try { function(); }
    catch (const RetailStateError& error) {
        caught = true;
        suite.Check(error.Code() == code && error.Offset() == offset, "Strict parser rejection code or offset differs");
    }
    suite.Check(caught, "Strict default accepted a noncanonical or malformed operation");
}
void StrictOperationShape(Suite& suite, const OperationFixture& fixture, const Bytes& canonical) {
    const auto parsed = RetailSavePlayerOperations::InspectAt(canonical.data(), canonical.size(), fixture.whole.offset,
        OperationsProfile);
    suite.Check(parsed.declaredCount == fixture.records.size() && parsed.arrayRecords == fixture.arrayRecords &&
        parsed.keyBodyIdMismatchCount == fixture.records.size() && SpanEqual(parsed.whole, fixture.whole) &&
        parsed.nextInflatedOffset == fixture.whole.offset + fixture.whole.bytes,
        "Canonical operation parsing changed boundaries, counts or allowed map-key mismatch");
    suite.Check(!parsed.restoreApproved && !parsed.completePlayerVerified && !parsed.completeSaveVerified &&
        !parsed.rulesetCompatibilityVerified && !parsed.objectReferencesVerified,
        "Operation-only framing claimed semantic approval");
}
void RawValuesAndTypes(Suite& suite) {
    std::vector<std::int32_t> types;
    for (std::int32_t type = 0; type < 20; ++type) types.push_back(type);
    for (unsigned value = 0; value < 256u; ++value) {
        const auto raw = static_cast<unsigned char>(value);
        const auto fixture = MakeOperations(types, Bytes(20, raw));
        const auto before = fixture.data;
        const auto edits = Plan(fixture, 11);
        suite.Check(fixture.whole.offset == 3u && fixture.whole.bytes == 1709u && fixture.data.size() == 1715u,
            "Independent twenty-type literal lengths changed");
        suite.Check(edits.size() == (value > 1u ? 20u : 0u), "Raw 0/1 was edited or nonzero raw booleans were missed");
        Bytes expected = before;
        for (std::size_t i = 0; i < AllTypeOffsets.size(); ++i) {
            suite.Check(fixture.records[i].base + 24u == AllTypeOffsets[i] &&
                fixture.records[i].start + 32u == AllTypeOffsets[i] && before[AllTypeOffsets[i]] == raw,
                "Literal bool offset differs from both base+24 and map-record+32");
            expected[AllTypeOffsets[i]] = static_cast<unsigned char>(value == 0u ? 0u : 1u);
            if (value > 1u) {
                const auto& edit = edits[i];
                suite.Check(edit.offset == AllTypeOffsets[i] && edit.before == raw && edit.after == 1u &&
                    edit.playerSlot == 11u && edit.operationIndex == i,
                    "Edit offset, value or owning player/operation differs from independent constants");
            }
        }
        const auto converted = Apply(fixture.data, edits);
        suite.Check(converted == expected && fixture.data == before,
            "Conversion changed unrelated integers, derived fields, prefix/suffix or original bytes");
        if (value <= 1u) suite.Check(converted == before, "Canonical input was changed");
        else RejectStrict(suite, [&] {
            RetailSavePlayerOperations::InspectAt(fixture.data.data(), fixture.data.size(), 3, OperationsProfile);
        }, Code::InvalidValue, 40);
        StrictOperationShape(suite, fixture, converted);
        ++suite.rawBooleans;
    }
    suite.syntheticOperations = 20;
}
void MultipleOperationsAndPlayers(Suite& suite) {
    const auto first = MakeOperations({0}, {68});
    const auto second = MakeOperations({0,3}, {2,255}, true);
    const auto firstBefore = first.data;
    const auto secondBefore = second.data;
    const auto richPlan = Plan(second, 63);
    suite.Check(second.whole.bytes == 199u && second.arrayRecords == 5u && richPlan.size() == 2u &&
        richPlan[0].offset == 39u && richPlan[1].offset == 148u && richPlan[1].operationIndex == 1u,
        "Nonempty vectors or unequal derived records shifted literal edit positions incorrectly");
    StrictOperationShape(suite, second, Apply(second.data, richPlan));
    Bytes combined = first.data;
    const auto shift = combined.size();
    combined.insert(combined.end(), second.data.begin(), second.data.end());
    const auto combinedBefore = combined;
    const RetailInflatedSpan shifted = {shift + second.whole.offset, second.whole.bytes};
    const auto left = RetailBodyImportDetail::CollectOperationEdits(combined.data(), combined.size(), first.whole,
        0, OperationsProfile, {});
    const auto right = RetailBodyImportDetail::CollectOperationEdits(combined.data(), combined.size(), shifted,
        63, OperationsProfile, {});
    suite.Check(left.size() == 1u && right.size() == 2u && left[0].offset == 39u && left[0].playerSlot == 0u &&
        right[0].offset == shift + 39u && right[1].offset == shift + 148u && right[0].playerSlot == 63u &&
        right[1].playerSlot == 63u && right[1].operationIndex == 1u,
        "Separate synthetic player-slot groups lost their operation ownership or absolute offsets");
    suite.Check(combined == combinedBefore && first.data == firstBefore && second.data == secondBefore,
        "Read-only multi-group planning changed input");
    suite.playerGroups = 2;
    // These are two operation maps with logical slot labels, not two complete
    // synthetic Players or a synthetic 64-Player body.
}
void DerivedBooleanScope(Suite& suite) {
    for (const std::int32_t type : {3,4}) {
        auto fixture = MakeOperations({type}, {68});
        const auto derivedBool = fixture.records[0].derived + 4u;
        fixture.data[derivedBool] = 2;
        const auto before = fixture.data;
        const auto edits = Plan(fixture, 1);
        suite.Check(edits.size() == 1u && edits[0].offset == 39u && edits[0].before == 68u,
            "Internal planner promoted an unrelated derived boolean to an eligible edit");
        const auto converted = Apply(fixture.data, edits);
        suite.Check(converted[39] == 1u && converted[derivedBool] == 2u && fixture.data == before,
            "Base-member import altered a different raw boolean");
        RejectStrict(suite, [&] {
            RetailSavePlayerOperations::InspectAt(converted.data(), converted.size(), fixture.whole.offset, OperationsProfile);
        }, Code::InvalidValue, derivedBool + 1u);
        ++suite.corruptions;
    }
}

void PlannerFailures(Suite& suite) {
    const auto fixture = MakeOperations({0,3}, {68,255}, true);
    auto corruptWord = [&](std::size_t at, std::uint32_t value, Code code, std::size_t failureAt) {
        auto bad = fixture; PutWord(bad.data, at, value);
        RejectPlan(suite, bad.data, [&] { return Plan(bad); }, code, failureAt); ++suite.corruptions;
    };
    const auto& last = fixture.records[1];
    corruptWord(last.start + 4u, 20, Code::UnsupportedProfile, last.start + 8u);
    corruptWord(last.start + 4u, 0xffffffffu, Code::UnsupportedProfile, last.start + 8u);
    corruptWord(last.base, 0, Code::UnsupportedVersion, last.base + 4u);
    corruptWord(last.base, 2, Code::UnsupportedVersion, last.base + 4u);
    corruptWord(last.derived, 2, Code::UnsupportedVersion, last.derived + 4u);
    corruptWord(last.base + 57u, 0xffffffffu, Code::ArrayLimit, last.base + 61u);
    corruptWord(fixture.whole.offset, 0xffffffffu, Code::ArrayLimit, fixture.whole.offset + 4u);
    std::vector<std::int32_t> types;
    for (std::int32_t type = 0; type < 20; ++type) types.push_back(type);
    const auto all = MakeOperations(types, Bytes(20, 68));
    for (std::size_t i = 0; i < all.records.size(); ++i) {
        for (const auto version : Layouts[i].versions) {
            auto badVersion = all; const auto at = all.records[i].derived + version;
            PutWord(badVersion.data, at, 2);
            RejectPlan(suite, badVersion.data, [&] { return Plan(badVersion); }, Code::UnsupportedVersion, at + 4u);
            ++suite.corruptions;
        }
    }
    for (const auto& truncated : {MakeOperations({0}, {68}), fixture}) {
        for (std::size_t count = 0; count < truncated.whole.bytes; ++count) {
            const RetailInflatedSpan span = {truncated.whole.offset, count};
            RejectPlan(suite, truncated.data, [&] {
                return RetailBodyImportDetail::CollectOperationEdits(truncated.data.data(), span.offset + span.bytes,
                    span, 1, OperationsProfile, {});
            }, Code::Truncated);
            ++suite.truncations;
        }
    }
    auto limits = RetailSaveStateLimits{};
    limits.maxInputBytes = fixture.data.size(); limits.maxPrefixBytes = fixture.whole.offset + fixture.whole.bytes;
    limits.maxArrayRecords = 2; limits.maxTotalRecords = 5;
    suite.Check(Plan(fixture, 0, limits).size() == 2u, "Exact operation byte/count/record budgets were rejected");
    auto insufficient = limits; --insufficient.maxInputBytes;
    RejectPlan(suite, fixture.data, [&] { return Plan(fixture, 0, insufficient); }, Code::InputLimit, 0);
    insufficient = limits; --insufficient.maxPrefixBytes;
    RejectPlan(suite, fixture.data, [&] { return Plan(fixture, 0, insufficient); }, Code::PrefixLimit);
    insufficient = limits; --insufficient.maxArrayRecords;
    RejectPlan(suite, fixture.data, [&] { return Plan(fixture, 0, insufficient); }, Code::ArrayLimit, 7);
    insufficient = limits; --insufficient.maxTotalRecords;
    RejectPlan(suite, fixture.data, [&] { return Plan(fixture, 0, insufficient); }, Code::TotalRecordLimit);
    insufficient = {}; insufficient.maxInputBytes = 0;
    RejectPlan(suite, fixture.data, [&] { return Plan(fixture, 0, insufficient); }, Code::InputLimit, 0);
    insufficient = {}; insufficient.maxPrefixBytes = 0;
    RejectPlan(suite, fixture.data, [&] { return Plan(fixture, 0, insufficient); }, Code::PrefixLimit, 0);
    insufficient = {}; insufficient.maxArrayRecords = 0;
    RejectPlan(suite, fixture.data, [&] { return Plan(fixture, 0, insufficient); }, Code::ArrayLimit, 7);
    insufficient = {}; insufficient.maxTotalRecords = 0;
    RejectPlan(suite, fixture.data, [&] { return Plan(fixture, 0, insufficient); }, Code::TotalRecordLimit, 7);
    auto bad = fixture; PutWord(bad.data, bad.whole.offset, 0xffffffffu);
    auto wide = RetailSaveStateLimits{};
    wide.maxArrayRecords = wide.maxTotalRecords = (std::numeric_limits<std::size_t>::max)();
    RejectPlan(suite, bad.data, [&] { return Plan(bad, 0, wide); }, Code::Truncated, 7);
    auto span = fixture.whole; ++span.bytes;
    RejectPlan(suite, fixture.data, [&] {
        return RetailBodyImportDetail::CollectOperationEdits(fixture.data.data(), fixture.data.size(), span,
            0, OperationsProfile, {});
    }, Code::InvalidValue, fixture.whole.offset + fixture.whole.bytes);
    span = {3, Absent};
    RejectPlan(suite, fixture.data, [&] {
        return RetailBodyImportDetail::CollectOperationEdits(fixture.data.data(), fixture.data.size(), span,
            0, OperationsProfile, {});
    }, Code::InvalidValue, 0);
    span = {Absent, 1};
    RejectPlan(suite, fixture.data, [&] {
        return RetailBodyImportDetail::CollectOperationEdits(fixture.data.data(), fixture.data.size(), span,
            0, OperationsProfile, {});
    }, Code::InvalidValue, 0);
    RejectPlan(suite, fixture.data, [&] { return Plan(fixture, 64); }, Code::InvalidValue, 0);
    RejectPlan(suite, fixture.data, [&] {
        return RetailBodyImportDetail::CollectOperationEdits(fixture.data.data(), fixture.data.size(), fixture.whole,
            0, static_cast<RetailPlayerOperationsProfile>(99), {});
    }, Code::UnsupportedProfile, 3);
    insufficient = {}; insufficient.booleanWireProfile = static_cast<RetailBooleanWireProfile>(99);
    RejectPlan(suite, fixture.data, [&] { return Plan(fixture, 0, insufficient); }, Code::UnsupportedProfile, 0);
    const auto empty = MakeOperations({}, {});
    auto zero = RetailSaveStateLimits{}; zero.maxArrayRecords = zero.maxTotalRecords = 0;
    suite.Check(Plan(empty, 0, zero).empty(), "A real zero-operation map required invented records");
    StrictOperationShape(suite, empty, empty.data);
}
bool WireEqual(const RetailSaveBodyInspection& a, const RetailSaveBodyInspection& b) {
    if (!SpanEqual(a.game, b.game) || !SpanEqual(a.map, b.map) || !SpanEqual(a.supporting, b.supporting) ||
        a.arrayRecords != b.arrayRecords || a.nextInflatedOffset != b.nextInflatedOffset ||
        a.cityCount != b.cityCount || a.unitCount != b.unitCount || a.armyCount != b.armyCount ||
        a.operationCount != b.operationCount || a.gameMap.arrayRecords != b.gameMap.arrayRecords ||
        a.gameMap.nextInflatedOffset != b.gameMap.nextInflatedOffset ||
        a.gameMap.prefix.nextInflatedOffset != b.gameMap.prefix.nextInflatedOffset ||
        a.gameMap.prefix.mapWidth != b.gameMap.prefix.mapWidth || a.gameMap.prefix.mapHeight != b.gameMap.prefix.mapHeight ||
        a.gameMap.plotCount != b.gameMap.plotCount || a.gameMap.areaCount != b.gameMap.areaCount ||
        a.gameMap.landmassCount != b.gameMap.landmassCount ||
        !SpanEqual(a.gameMap.prefix.embeddedDatabase, b.gameMap.prefix.embeddedDatabase) ||
        !SpanEqual(a.gameMap.plots, b.gameMap.plots) || !SpanEqual(a.gameMap.areas, b.gameMap.areas) ||
        !SpanEqual(a.gameMap.landmasses, b.gameMap.landmasses)) return false;
    for (std::size_t slot = 0; slot < 64u; ++slot) {
        const auto& x = a.teams[slot]; const auto& y = b.teams[slot];
        if (!SpanEqual(x.whole, y.whole) || x.id != y.id || x.arrayRecords != y.arrayRecords) return false;
        const auto& p = a.players[slot]; const auto& q = b.players[slot];
        if (!SpanEqual(p.whole, q.whole) || !SpanEqual(p.operations, q.operations) || p.id != q.id ||
            p.arrayRecords != q.arrayRecords || p.cityCount != q.cityCount || p.unitCount != q.unitCount ||
            p.armyCount != q.armyCount || p.operationCount != q.operationCount) return false;
    }
    return true;
}
RetailSavePreparedBody Sentinel() {
    RetailSavePreparedBody value;
    value.bytes = {0xa5,68,0,255}; value.edits = {{1,68,1,63,31}};
    value.wire.arrayRecords = 913; value.wire.nextInflatedOffset = 917;
    value.wire.players[3].id = 37; value.wire.players[3].whole = {13,17};
    return value;
}
bool PreparedEqual(const RetailSavePreparedBody& a, const RetailSavePreparedBody& b) {
    return a.bytes == b.bytes && SameEdits(a.edits, b.edits) && WireEqual(a.wire, b.wire) &&
        a.canonicalWireFramed == b.canonicalWireFramed && a.producerContractVerified == b.producerContractVerified &&
        a.rulesetCompatibilityVerified == b.rulesetCompatibilityVerified &&
        a.completeSaveVerified == b.completeSaveVerified && a.restoreApproved == b.restoreApproved;
}
template<class Function>
void RejectBody(Suite& suite, Function function, Code expected, std::size_t maximumOffset,
    std::size_t exactOffset = Absent) {
    const auto sentinel = Sentinel(); auto output = sentinel;
    bool caught = false;
    try { output = function(); }
    catch (const RetailStateError& error) {
        caught = true;
        suite.Check(error.Code() == expected, "Body import failure has the wrong typed code");
        suite.Check(exactOffset == Absent ? error.Offset() <= maximumOffset : error.Offset() == exactOffset,
            "Body import failure escaped its input or has the wrong exact offset");
    }
    suite.Check(caught, "Invalid body import returned a partial result");
    suite.Check(PreparedEqual(output, sentinel), "Failed Prepare replaced the last output sentinel");
    ++suite.atomicFailures;
}
void PolicyGates(Suite& suite) {
    const Options options; const auto profile = Profile(options);
    const Bytes input = {0}; const auto before = input;
    RejectBody(suite, [&] { return RetailSaveBodyImport::Prepare(input.data(), 0, profile, Policy::RequireCanonical); },
        Code::Truncated, 0, 0);
    RejectBody(suite, [&] { return RetailSaveBodyImport::Prepare(input.data(), input.size(), profile, static_cast<Policy>(99)); },
        Code::UnsupportedProfile, input.size(), 0);
    auto layout = profile; layout.layout = static_cast<RetailBodyLayout>(99);
    RejectBody(suite, [&] { return RetailSaveBodyImport::Prepare(input.data(), input.size(), layout,
        Policy::OperationReinforcementNonzeroTruth); }, Code::UnsupportedProfile, input.size(), 0);
    auto limits = RetailSaveStateLimits{}; limits.booleanWireProfile = RetailBooleanWireProfile::SdkRawByte;
    RejectBody(suite, [&] { return RetailSaveBodyImport::Prepare(input.data(), input.size(), profile,
        Policy::OperationReinforcementNonzeroTruth, limits); }, Code::UnsupportedProfile, input.size(), 0);
    limits.booleanWireProfile = static_cast<RetailBooleanWireProfile>(99);
    RejectBody(suite, [&] { return RetailSaveBodyImport::Prepare(input.data(), input.size(), profile,
        Policy::RequireCanonical, limits); }, Code::UnsupportedProfile, input.size(), 0);
    RejectBody(suite, [&] { return RetailSaveBodyImport::Prepare(nullptr, 1, profile,
        Policy::RequireCanonical); }, Code::NullInput, 1, 0);
    suite.Check(input == before && RetailSaveStateLimits{}.booleanWireProfile == RetailBooleanWireProfile::CanonicalZeroOne,
        "Explicit import changed the original bytes or the Reader's strict default");
}
void SelfTest(Suite& suite) {
    RawValuesAndTypes(suite); MultipleOperationsAndPlayers(suite); DerivedBooleanScope(suite);
    PlannerFailures(suite); PolicyGates(suite);
    suite.Check(suite.syntheticOperations == 20u && suite.rawBooleans == 256u && suite.playerGroups == 2u &&
        suite.truncations == 284u && suite.corruptions == 35u, "Focused synthetic fixture accounting differs");
}

bool Inside(const RetailInflatedSpan& span, std::size_t size) {
    return span.offset <= size && span.bytes <= size - span.offset;
}
void BodyShape(Suite& suite, const RetailSaveBodyInspection& wire, std::size_t size) {
    suite.Check(Inside(wire.game, size) && Inside(wire.map, size) && wire.game.offset == 0u &&
        wire.game.bytes > 0u && wire.map.offset == wire.game.bytes && wire.map.bytes > 0u &&
        wire.map.offset + wire.map.bytes == wire.gameMap.nextInflatedOffset,
        "Game/Map body spans are not contiguous or bounded");
    std::size_t cursor = wire.gameMap.nextInflatedOffset, records = wire.gameMap.arrayRecords;
    std::size_t cities = 0, units = 0, armies = 0, operations = 0;
    for (std::size_t slot = 0; slot < 64u; ++slot) {
        const auto& team = wire.teams[slot];
        suite.Check(Inside(team.whole, size) && team.whole.offset == cursor && team.whole.bytes > 0u &&
            team.id == static_cast<std::int32_t>(slot), "Team body spans or IDs differ from explicit slot order");
        cursor = team.whole.offset + team.whole.bytes; records += team.arrayRecords;
    }
    for (std::size_t slot = 0; slot < 64u; ++slot) {
        const auto& player = wire.players[slot];
        suite.Check(Inside(player.whole, size) && player.whole.offset == cursor && player.whole.bytes > 0u &&
            player.id == static_cast<std::int32_t>(slot) && player.operations.offset >= player.whole.offset &&
            player.operations.offset <= player.whole.offset + player.whole.bytes &&
            player.operations.bytes <= player.whole.offset + player.whole.bytes - player.operations.offset,
            "Player IDs, body spans or owning operation span differ");
        cursor = player.whole.offset + player.whole.bytes; records += player.arrayRecords;
        cities += player.cityCount; units += player.unitCount; armies += player.armyCount; operations += player.operationCount;
    }
    suite.Check(Inside(wire.supporting, size) && wire.supporting.offset == cursor &&
        wire.supporting.bytes == 276u + 4u * wire.gameMap.plotCount &&
        wire.supporting.offset + wire.supporting.bytes == size && wire.nextInflatedOffset == size &&
        records == wire.arrayRecords && cities == wire.cityCount && units == wire.unitCount &&
        armies == wire.armyCount && operations == wire.operationCount,
        "Supporting endpoint, shared records or aggregate object counts differ");
}
void ApprovalFlags(Suite& suite, const RetailSavePreparedBody& prepared) {
    suite.Check(prepared.canonicalWireFramed && !prepared.producerContractVerified &&
        !prepared.rulesetCompatibilityVerified && !prepared.completeSaveVerified && !prepared.restoreApproved,
        "Prepared bytes lack canonical framing or claim semantic/producer/restore approval");
}
void ExactEdits(Suite& suite, const Bytes& original, const RetailSavePreparedBody& prepared) {
    suite.Check(prepared.bytes.size() == original.size(), "Import changed the body length");
    std::size_t last = 0;
    for (std::size_t i = 0; i < prepared.edits.size(); ++i) {
        const auto& edit = prepared.edits[i];
        suite.Check(edit.offset < original.size() && (i == 0u || edit.offset > last) &&
            edit.playerSlot < 64u && edit.operationIndex < prepared.wire.players[edit.playerSlot].operationCount &&
            edit.before == original[edit.offset] && edit.before > 1u && edit.after == 1u,
            "Reported boolean edit is duplicated, out of bounds or has invalid ownership/values");
        const auto& operations = prepared.wire.players[edit.playerSlot].operations;
        suite.Check(edit.offset >= operations.offset && edit.offset - operations.offset < operations.bytes,
            "Reported boolean edit lies outside its internally framed operation map");
        last = edit.offset;
    }
    std::size_t nextEdit = 0;
    bool exact = true;
    for (std::size_t at = 0; at < original.size(); ++at) {
        unsigned char expected = original[at];
        if (nextEdit < prepared.edits.size() && prepared.edits[nextEdit].offset == at) {
            expected = 1; ++nextEdit;
        }
        if (prepared.bytes[at] != expected) exact = false;
    }
    suite.Check(exact && nextEdit == prepared.edits.size(), "Output changed a byte outside the complete reported edit list");
}
Bytes ReadInput(std::size_t maximum) {
#ifdef _WIN32
    if (_setmode(_fileno(stdin), _O_BINARY) == -1) throw std::runtime_error("Cannot select binary stdin");
#endif
    Bytes input;
    std::array<char, 65536> block{};
    while (std::cin.read(block.data(), static_cast<std::streamsize>(block.size())) || std::cin.gcount() > 0) {
        const auto count = static_cast<std::size_t>(std::cin.gcount());
        if (count > maximum - input.size()) throw std::runtime_error("Stdin exceeds the explicit byte budget");
        for (std::size_t i = 0; i < count; ++i) input.push_back(static_cast<unsigned char>(block[i]));
    }
    if (!std::cin.eof() || std::cin.bad()) throw std::runtime_error("Cannot finish stdin body read");
    return input;
}
struct PublicObservation {
    bool readComplete = false, observed = false, originalCanonical = false;
    std::size_t inputBytes = 0;
    RetailSavePreparedBody result;
};
void PublicTest(Suite& suite, const Options& options, PublicObservation& observation, const char*& phase) {
    phase = "public_stdin";
    const auto input = ReadInput(options.maximumInput);
    observation.readComplete = true; observation.inputBytes = input.size();
    const auto before = input;
    const auto profile = Profile(options);
    auto limits = RetailSaveStateLimits{};
    limits.maxInputBytes = options.maximumInput; limits.maxTotalRecords = options.recordBudget;
    auto raw = limits; raw.booleanWireProfile = RetailBooleanWireProfile::SdkRawByte;
    phase = "public_original_wire";
    const auto originalWire = RetailBodyImportDetail::InspectBody(input.data(), input.size(), profile, raw);
    phase = "public_prepare";
    auto prepared = RetailSaveBodyImport::Prepare(input.data(), input.size(), profile,
        Policy::OperationReinforcementNonzeroTruth, limits);
    ApprovalFlags(suite, prepared); BodyShape(suite, prepared.wire, input.size()); ExactEdits(suite, input, prepared);
    suite.Check(WireEqual(originalWire, prepared.wire), "Import changed original Game/Map/Team/Player/supporting metadata");
    suite.Check(input == before, "Actual full Prepare changed its caller's original body");
    phase = "public_canonical_output";
    const auto strictWire = RetailBodyImportDetail::InspectBody(prepared.bytes.data(), prepared.bytes.size(), profile, limits);
    suite.Check(WireEqual(strictWire, prepared.wire), "Strict canonical output inspection differs from Prepare metadata");
    phase = "public_exact_record_budget";
    auto exact = limits; exact.maxTotalRecords = originalWire.arrayRecords;
    {
        const auto tight = RetailSaveBodyImport::Prepare(input.data(), input.size(), profile,
            Policy::OperationReinforcementNonzeroTruth, exact);
        suite.Check(PreparedEqual(tight, prepared), "Exact shared budget changed output or was charged once per validation pass");
    }
    phase = "public_require_canonical";
    if (prepared.edits.empty()) {
        const auto strict = RetailSaveBodyImport::Prepare(input.data(), input.size(), profile, Policy::RequireCanonical, limits);
        suite.Check(strict.edits.empty() && strict.bytes == input && WireEqual(strict.wire, prepared.wire),
            "RequireCanonical changed canonical original bytes or metadata");
        ApprovalFlags(suite, strict); observation.originalCanonical = true;
    } else {
        RejectBody(suite, [&] { return RetailSaveBodyImport::Prepare(input.data(), input.size(), profile,
            Policy::RequireCanonical, limits); }, Code::InvalidValue, input.size(), prepared.edits.front().offset + 1u);
    }
    phase = "public_failure_atomicity";
    suite.Check(originalWire.arrayRecords > 0u && !input.empty(), "Public body lacks meaningful byte/record budget boundaries");
    --exact.maxTotalRecords;
    RejectBody(suite, [&] { return RetailSaveBodyImport::Prepare(input.data(), input.size(), profile,
        Policy::OperationReinforcementNonzeroTruth, exact); }, Code::TotalRecordLimit, input.size());
    auto insufficient = limits; insufficient.maxInputBytes = input.size() - 1u;
    RejectBody(suite, [&] { return RetailSaveBodyImport::Prepare(input.data(), input.size(), profile,
        Policy::OperationReinforcementNonzeroTruth, insufficient); }, Code::InputLimit, input.size(), 0);
    RejectBody(suite, [&] { return RetailSaveBodyImport::Prepare(input.data(), input.size() - 1u, profile,
        Policy::OperationReinforcementNonzeroTruth, limits); }, Code::Truncated, input.size() - 1u);
    ++suite.truncations;
    RejectBody(suite, [&] { return RetailSaveBodyImport::Prepare(input.data(), input.size(), profile,
        static_cast<Policy>(99), limits); }, Code::UnsupportedProfile, input.size(), 0);
    auto badLayout = profile; badLayout.layout = static_cast<RetailBodyLayout>(99);
    RejectBody(suite, [&] { return RetailSaveBodyImport::Prepare(input.data(), input.size(), badLayout,
        Policy::OperationReinforcementNonzeroTruth, limits); }, Code::UnsupportedProfile, input.size(), 0);
    phase = "public_non_target_boolean";
    const auto player = RetailSavePlayer::InspectAt(prepared.bytes.data(), prepared.bytes.size(),
        prepared.wire.players[0].whole.offset, profile.playerProfile, limits);
    const auto conquest = player.ending.fields.everConquered;
    suite.Check(Inside(conquest, prepared.bytes.size()) && conquest.bytes == 68u,
        "Current-v16 public Player does not frame its fixed 64 conquest flags");
    {
        auto bad = input; const auto at = conquest.offset + 4u; bad[at] = 2;
        const auto badBefore = bad;
        RejectBody(suite, [&] { return RetailSaveBodyImport::Prepare(bad.data(), bad.size(), profile,
            Policy::OperationReinforcementNonzeroTruth, limits); }, Code::InvalidValue, bad.size(), at + 1u);
        suite.Check(bad == badBefore, "Failed final strict validation changed a public-derived corrupted input");
        ++suite.corruptions;
    }
    phase = "public_trailing_byte";
    if (input.size() < MaximumInput) {
        auto extra = input; extra.push_back(68);
        auto suffixLimits = limits; suffixLimits.maxInputBytes = (std::max)(suffixLimits.maxInputBytes, extra.size());
        RejectBody(suite, [&] { return RetailSaveBodyImport::Prepare(extra.data(), extra.size(), profile,
            Policy::OperationReinforcementNonzeroTruth, suffixLimits); }, Code::InvalidValue, extra.size(), input.size());
        ++suite.corruptions;
    }
    suite.Check(input == before, "Public failure controls changed the immutable original input");
    // Publish observations only after every positive and negative check succeeds.
    observation.result = std::move(prepared); observation.observed = true;
    phase = "complete";
}

const char* Boolean(bool value) { return value ? "true" : "false"; }
void Text(const std::string& value) {
    constexpr char Hex[] = "0123456789abcdef";
    std::cout << '"';
    for (const char raw : value) {
        const auto byte = static_cast<unsigned char>(raw);
        if (byte == '"' || byte == '\\') std::cout << '\\' << static_cast<char>(byte);
        else if (byte < 32u || byte >= 127u) std::cout << "\\u00" << Hex[byte >> 4] << Hex[byte & 15u];
        else std::cout << static_cast<char>(byte);
    }
    std::cout << '"';
}
void PrintWire(const RetailSaveBodyInspection& wire, std::size_t inputBytes) {
    const auto& map = wire.gameMap;
    std::cout << "{\"game_map\":{\"game_end_offset\":" << map.prefix.game.offset + map.prefix.game.bytes
        << ",\"map_header_end_offset\":" << map.prefix.nextInflatedOffset << ",\"map_end_offset\":" << map.nextInflatedOffset
        << ",\"width\":" << map.prefix.mapWidth << ",\"height\":" << map.prefix.mapHeight << ",\"plots\":" << map.plotCount
        << ",\"areas\":" << map.areaCount << ",\"landmasses\":" << map.landmassCount
        << ",\"embedded_database_bytes\":" << map.prefix.embeddedDatabase.bytes << ",\"array_records\":" << map.arrayRecords
        << "},\"teams\":[";
    for (std::size_t slot = 0; slot < wire.teams.size(); ++slot) {
        const auto& row = wire.teams[slot]; if (slot) std::cout << ',';
        std::cout << "{\"slot\":" << slot << ",\"id\":" << row.id << ",\"start\":" << row.whole.offset
            << ",\"end\":" << row.whole.offset + row.whole.bytes << ",\"records\":" << row.arrayRecords << '}';
    }
    std::cout << "],\"players\":[";
    for (std::size_t slot = 0; slot < wire.players.size(); ++slot) {
        const auto& row = wire.players[slot]; if (slot) std::cout << ',';
        std::cout << "{\"slot\":" << slot << ",\"id\":" << row.id << ",\"start\":" << row.whole.offset
            << ",\"end\":" << row.whole.offset + row.whole.bytes << ",\"records\":" << row.arrayRecords
            << ",\"cities\":" << row.cityCount << ",\"units\":" << row.unitCount << ",\"armies\":" << row.armyCount
            << ",\"operations\":" << row.operationCount << '}';
    }
    std::cout << "],\"supporting\":{\"start\":" << wire.supporting.offset << ",\"bytes\":" << wire.supporting.bytes
        << ",\"end\":" << wire.supporting.offset + wire.supporting.bytes
        << "},\"object_counts_completed\":{\"cities\":" << wire.cityCount << ",\"units\":" << wire.unitCount
        << ",\"armies\":" << wire.armyCount << ",\"operations\":" << wire.operationCount
        << "},\"array_records_completed\":" << wire.arrayRecords << ",\"last_completed_offset\":" << wire.nextInflatedOffset
        << ",\"declared_sequence_has_zero_remainder\":" << Boolean(wire.nextInflatedOffset == inputBytes) << '}';
}
void Print(const Suite& suite, const Options& options, const PublicObservation& observation,
    bool passed, const char* phase, const std::string& error, int code, std::size_t offset) {
    const char* mode = options.mode == Mode::SelfTest ? "self-test" : options.mode == Mode::Public ? "public" : "unselected";
    std::cout << "{\"schema\":\"zerosis.retail.body_import_test.v1\",\"status\":\""
        << (passed ? "PASS_RETAIL_BODY_IMPORT_COMPONENT" : "FAIL_RETAIL_BODY_IMPORT_COMPONENT")
        << "\",\"mode\":\"" << mode << "\",\"phase\":\"" << phase << "\",\"checks\":" << suite.checks
        << ",\"synthetic_operation_cases\":" << suite.syntheticOperations << ",\"raw_boolean_cases\":" << suite.rawBooleans
        << ",\"raw_boolean_operation_cases\":" << suite.rawBooleans * suite.syntheticOperations
        << ",\"synthetic_player_slot_groups\":" << suite.playerGroups << ",\"truncations\":" << suite.truncations
        << ",\"directed_corruptions\":" << suite.corruptions << ",\"atomic_failure_cases\":" << suite.atomicFailures
        << ",\"all_failure_outputs_unchanged\":" << Boolean(passed)
        << ",\"input_bytes_unchanged\":" << Boolean(passed) << ",\"input_files_unchanged\":true"
        << ",\"gamecore_loaded\":false,\"window_created\":false,\"game_accessed\":false,\"user_saves_accessed\":false"
        << ",\"complete_player_validated\":false,\"complete_save_validated\":false,\"complete_save_verified\":false"
        << ",\"ruleset_compatibility_verified\":false,\"restore_approved\":false,\"sdk_executed\":false"
        << ",\"producer_contract_verified\":false,\"full_engine_goal_complete\":false,\"public\":";
    if (observation.observed) {
        const auto& prepared = observation.result;
        std::cout << "{\"input_bytes\":" << observation.inputBytes << ",\"awards\":" << options.awards
            << ",\"grand\":" << options.grand << ",\"projects\":" << options.projects
            << ",\"maximum_input_bytes\":" << options.maximumInput << ",\"maximum_total_records\":" << options.recordBudget
            << ",\"array_records\":" << prepared.wire.arrayRecords << ",\"next_inflated_offset\":" << prepared.wire.nextInflatedOffset
            << ",\"following_bytes\":" << observation.inputBytes - prepared.wire.nextInflatedOffset
            << ",\"team_count\":64,\"player_count\":64,\"edit_count\":" << prepared.edits.size()
            << ",\"canonical_body_wire_framed\":" << Boolean(prepared.canonicalWireFramed)
            << ",\"original_require_canonical_accepted\":" << Boolean(observation.originalCanonical) << ",\"edits\":[";
        for (std::size_t i = 0; i < prepared.edits.size(); ++i) {
            const auto& edit = prepared.edits[i]; if (i) std::cout << ',';
            std::cout << "{\"offset\":" << edit.offset << ",\"before\":" << static_cast<unsigned>(edit.before)
                << ",\"after\":" << static_cast<unsigned>(edit.after) << ",\"player_slot\":" << edit.playerSlot
                << ",\"operation_index\":" << edit.operationIndex << '}';
        }
        std::cout << "],\"wire\":"; PrintWire(prepared.wire, observation.inputBytes); std::cout << '}';
    } else std::cout << "null";
    std::cout << ",\"error_code\":";
    if (code >= 0) std::cout << code; else std::cout << "null";
    std::cout << ",\"error_offset\":";
    if (code >= 0) std::cout << offset; else std::cout << "null";
    std::cout << ",\"error\":"; Text(error); std::cout << "}\n";
}
} // namespace

int main(int argc, char** argv) {
    static_assert(sizeof(void*) == 8, "Body-import component tests require x64");
    static_assert(sizeof(std::uint32_t) == 4 && std::numeric_limits<unsigned char>::digits == 8,
        "Literal body-import tests require 32-bit words and 8-bit bytes");
    Suite suite; Options options; PublicObservation observation;
    const char* phase = "arguments"; bool passed = false;
    std::string error; int code = -1; std::size_t offset = 0;
    try {
        options = Arguments(argc, argv);
        if (options.mode == Mode::SelfTest) { phase = "self-test"; SelfTest(suite); phase = "complete"; }
        else PublicTest(suite, options, observation, phase);
        passed = true;
    } catch (const RetailStateError& failure) {
        error = failure.what(); code = static_cast<int>(failure.Code()); offset = failure.Offset();
    } catch (const std::exception& failure) { error = failure.what(); }
    catch (...) { error = "Unexpected non-standard body-import test exception"; }
    Print(suite, options, observation, passed, phase, error, code, offset);
    return passed ? 0 : 1;
}
