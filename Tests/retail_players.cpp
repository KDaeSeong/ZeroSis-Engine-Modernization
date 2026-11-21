#include "RetailSavePlayers.h"
#include "RetailSaveMap.h"
#include "RetailSaveTeam.h"
#include "RetailSaveSupporting.h"
#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <exception>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>
#if defined(_WIN32)
#include <fcntl.h>
#include <io.h>
#endif

// Public-derived integration tests for a caller-authenticated inflated stream.
// This fixture is not an independent literal or a synthetic serializer oracle.
// The input arrives in RAM through stdin; no game, save or input path is opened.
namespace {
using namespace ZeroSisHost;
using Bytes = std::vector<unsigned char>;
using Code = RetailStateErrorCode;
constexpr std::size_t ExpectedPlayers = 64;
struct Suite {
    std::size_t checks = 0, truncations = 0, directedCorruptions = 0;
    void Check(bool value, const char* message) {
        ++checks;
        if (!value) throw std::runtime_error(message);
    }
};
struct Context {
    const char* phase = "arguments";
    std::int32_t currentSlot = -1;
    std::size_t slotStart = 0, completed = 0, inputBytes = 0, lastPlayerEnd = 0;
    std::size_t supportingBytes = 0, supportingEnd = 0, followingBytes = 0;
} Current;
struct SlotTrace {
    RetailInflatedSpan whole;
    std::int32_t playerId = -1;
    std::uint32_t cities = 0, units = 0, armies = 0, operations = 0;
    std::size_t records = 0, prefixEnd = 0;
};
struct DirectTrace {
    std::array<SlotTrace, ExpectedPlayers> players{};
    std::size_t start = 0, end = 0, records = 0, cities = 0, units = 0, armies = 0, operations = 0;
};
struct PublicResult {
    DirectTrace trace;
    RetailSavePlayersInspection aggregate;
    RetailInflatedSpan supporting;
    std::size_t bytes = 0, followingBytes = 0;
    bool plaintextFramed = false;
};
struct DiagnosticStage {
    const char* name = "";
    std::size_t start = 0, next = 0, records = 0, recordBudget = 0;
    std::size_t poolHeaderEnd = 0, poolHeaderRecords = 0, errorOffset = 0;
    std::uint32_t poolCapacity = 0, poolLiveCount = 0, plotCount = 0, operationCount = 0;
    std::int32_t playerId = -1;
    int errorCode = -1;
    bool completed = false, poolObserved = false, typedError = false;
};
struct PrefixDiagnostic {
    std::array<DiagnosticStage, 7> stages{};
    std::size_t stageCount = 0;
    std::uint32_t rawVersion = 0;
    std::int32_t rawPlayerId = -1;
    bool attempted = false, rawVersionObserved = false, rawPlayerIdObserved = false;
    bool sameFailureReproduced = false, internalFailure = false;
};
struct PlayerDiagnostic {
    std::array<DiagnosticStage, 7> stages{};
    PrefixDiagnostic prefix;
    std::size_t start = 0, stageCount = 0, initialRecordBudget = 0;
    std::int32_t slot = -1;
    bool attempted = false, sameFailureReproduced = false, internalFailure = false;
} FailedPlayer;
RetailSavePlayerWireProfile PlayerProfile() {
    return {RetailSavePlayerProfile(4, RetailPlayerCatalogProfile::InitializedBuildings),
        RetailPlayerAiMidCatalogProfile::InitializedTechs, RetailPlayerAiLateProfile::InitializedMinorQuests,
        RetailSaveCityProfile(0, RetailCityProductionCatalogProfile::InitializedBuildingsAndUnits, 6),
        RetailUnitWriterProfile::Bnw9CompleteGreatWorkHashWord,
        RetailSavePlayerEndProfile(RetailPlayerOperationsProfile::BnwCurrentFactory20,
            RetailPlayerEndWriterProfile::Current16With64Players)};
}
RetailSavePlayersProfile PlayersProfile() {
    return {RetailPlayerBlockProfile::Bnw64InSlotOrder, PlayerProfile()};
}
std::uint32_t Word(const Bytes& data, std::size_t offset) {
    if (offset > data.size() || data.size() - offset < 4u) throw std::runtime_error("Wire word outside input");
    return static_cast<std::uint32_t>(data[offset]) | (static_cast<std::uint32_t>(data[offset + 1u]) << 8) |
        (static_cast<std::uint32_t>(data[offset + 2u]) << 16) | (static_cast<std::uint32_t>(data[offset + 3u]) << 24);
}
void Put(Bytes& data, std::size_t offset, std::uint32_t value) {
    if (offset > data.size() || data.size() - offset < 4u) throw std::runtime_error("Wire patch outside input");
    for (unsigned i = 0; i < 4; ++i) data[offset + i] = static_cast<unsigned char>(value >> (8u * i));
}
void Append32(Bytes& data, std::uint32_t value) {
    for (unsigned i = 0; i < 4; ++i) data.push_back(static_cast<unsigned char>(value >> (8u * i)));
}
template<class Function> void Reject(Suite& s, Function&& function, Code expected, std::size_t inputSize) {
    try { function(); }
    catch (const RetailStateError& error) {
        s.Check(error.Code() == expected, "Wrong typed players/supporting error");
        s.Check(error.Offset() <= inputSize, "Typed error escaped its input"); return;
    }
    s.Check(false, "Invalid players/supporting input was accepted");
}
struct SupportingFixture {
    Bytes data;
    std::array<std::size_t, 3> versions{};
    std::size_t start = 0, end = 0, plots = 0;
};
SupportingFixture MakeSupporting(std::size_t plots, bool prefix) {
    SupportingFixture f; f.plots = plots;
    if (prefix) f.data = {0x16u, 0u, 0x7fu};
    f.start = f.data.size();
    f.versions[0] = f.data.size(); Append32(f.data, 1);
    f.versions[1] = f.data.size(); Append32(f.data, 1);
    const std::array<std::uint16_t, 3> signedShortPatterns = {0xffffu, 0x8000u, 0x1234u};
    for (std::size_t array = 0; array < 2u; ++array) for (std::size_t i = 0; i < plots; ++i) {
        const auto value = signedShortPatterns[(i + array) % signedShortPatterns.size()];
        f.data.push_back(static_cast<unsigned char>(value));
        f.data.push_back(static_cast<unsigned char>(value >> 8));
    }
    f.versions[2] = f.data.size(); Append32(f.data, 1);
    // Independent literal: three version words and 66 signed int32 values.
    // The two signed-int16 arrays have caller-supplied widths and no counts.
    const std::array<std::uint32_t, 3> signedIntPatterns = {0xffffffffu, 0x80000000u, 0x12345678u};
    for (std::size_t i = 0; i < 66u; ++i) Append32(f.data, signedIntPatterns[i % signedIntPatterns.size()]);
    f.end = f.data.size(); Append32(f.data, 0x13579bdfu); return f;
}
void SupportingTests(Suite& s) {
    Current.phase = "independent_supporting_fixtures";
    const std::array<SupportingFixture, 3> fixtures = {MakeSupporting(0, false), MakeSupporting(1, true), MakeSupporting(3, true)};
    for (const auto& f : fixtures) {
        const auto before = f.data;
        const auto span = RetailSaveSupporting::InspectAt(f.data.data(), f.data.size(), f.start, f.plots);
        s.Check(span.offset == f.start && span.bytes == 276u + 4u * f.plots && span.offset + span.bytes == f.end,
            "Literal supporting versions, signed arrays or 276+4P boundary differs");
        s.Check(Word(f.data, f.end) == 0x13579bdfu && f.data == before, "Supporting parse changed input or consumed suffix");
        RetailStateDetail::Reader reader(f.data.data(), f.data.size(), {}); reader.Skip(f.start);
        RetailStateDetail::ReadSupporting(reader, f.plots);
        s.Check(reader.Pos() == f.end && reader.Records() == 0u, "Implicit supporting arrays were charged as counted rows");
        for (auto at : f.versions) {
            auto corrupted = f.data; Put(corrupted, at, 127);
            Reject(s, [&] { RetailSaveSupporting::InspectAt(corrupted.data(), corrupted.size(), f.start, f.plots); },
                Code::UnsupportedVersion, corrupted.size());
        }
        for (std::size_t cut = 0; cut < f.end; ++cut) {
            Reject(s, [&] { RetailSaveSupporting::InspectAt(f.data.data(), cut, f.start, f.plots); }, Code::Truncated, cut);
            ++s.truncations;
        }
        auto limits = RetailSaveStateLimits{}; limits.maxInputBytes = f.data.size();
        s.Check(RetailSaveSupporting::InspectAt(f.data.data(), f.data.size(), f.start, f.plots, limits).bytes == span.bytes,
            "Exact supporting input budget rejected");
        --limits.maxInputBytes;
        Reject(s, [&] { RetailSaveSupporting::InspectAt(f.data.data(), f.data.size(), f.start, f.plots, limits); }, Code::InputLimit, f.data.size());
        limits = {}; limits.maxPrefixBytes = f.end;
        s.Check(RetailSaveSupporting::InspectAt(f.data.data(), f.data.size(), f.start, f.plots, limits).bytes == span.bytes,
            "Exact supporting prefix budget rejected");
        --limits.maxPrefixBytes;
        Reject(s, [&] { RetailSaveSupporting::InspectAt(f.data.data(), f.data.size(), f.start, f.plots, limits); }, Code::PrefixLimit, f.data.size());
        limits = {}; limits.maxMapPlots = f.plots; limits.maxTotalRecords = 0; limits.maxArrayRecords = 0;
        s.Check(RetailSaveSupporting::InspectAt(f.data.data(), f.data.size(), f.start, f.plots, limits).bytes == span.bytes,
            "Supporting fixed arrays incorrectly required counted-record budget");
        if (f.plots) {
            --limits.maxMapPlots;
            Reject(s, [&] { RetailSaveSupporting::InspectAt(f.data.data(), f.data.size(), f.start, f.plots, limits); }, Code::MapPlotLimit, f.data.size());
        }
    }
    const auto& f = fixtures[0];
    auto limits = RetailSaveStateLimits{}; limits.maxMapPlots = (std::numeric_limits<std::size_t>::max)();
    Reject(s, [&] { RetailSaveSupporting::InspectAt(f.data.data(), f.data.size(), 0,
        (std::numeric_limits<std::size_t>::max)(), limits); }, Code::Truncated, f.data.size());
    Reject(s, [&] { RetailSaveSupporting::InspectAt(nullptr, 1, 0, 0); }, Code::NullInput, 1);
    Reject(s, [&] { RetailSaveSupporting::InspectAt(nullptr, 0, 0, 0); }, Code::Truncated, 0);
    Reject(s, [&] { RetailSaveSupporting::InspectAt(f.data.data(), f.data.size(), f.data.size() + 1u, 0); }, Code::Truncated, f.data.size());
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
void DiagnosePrefixFailure(const Bytes& bytes, std::size_t start,
        const RetailSavePlayerProfile& profile, const RetailSaveStateLimits& limits,
        const RetailStateError& original) noexcept {
    auto& result = FailedPlayer.prefix; result.attempted = true;
    try {
        // These are fixed source-declared positions, never searched candidates.
        if (start <= bytes.size() && bytes.size() - start >= 4u) {
            result.rawVersion = Word(bytes, start); result.rawVersionObserved = true;
        }
        if (start <= bytes.size() && bytes.size() - start >= 868u) {
            const auto rawId = Word(bytes, start + 864u);
            result.rawPlayerId = rawId <= 0x7fffffffu ? static_cast<std::int32_t>(rawId)
                : -1 - static_cast<std::int32_t>(~rawId);
            result.rawPlayerIdObserved = true;
        }
        // A single Reader carries its position and counted-row budget through
        // precisely the seven calls used by RetailSavePlayerPrefix::InspectAt.
        RetailStateDetail::Reader input(bytes.data(), bytes.size(), limits);
        if (profile.grandStrategyCount > RetailStateDetail::PlayerGrandStrategyAIProfileLimit ||
                profile.catalogProfile != RetailPlayerCatalogProfile::InitializedBuildings)
            input.Fail(Code::UnsupportedProfile, "Unsupported diagnostic Player prefix profile");
        input.Skip(start);
        auto run = [&](const char* name, auto&& function) {
            auto& step = result.stages[result.stageCount++]; step.name = name; step.start = input.Pos();
            const auto before = input.Records(); step.recordBudget = limits.maxTotalRecords - before;
            try {
                function(step); step.next = input.Pos(); step.records = input.Records() - before;
                step.completed = true; return true;
            } catch (const RetailStateError& error) {
                step.next = input.Pos(); step.records = input.Records() - before; step.typedError = true;
                step.errorCode = static_cast<int>(error.Code()); step.errorOffset = error.Offset();
                result.sameFailureReproduced = error.Code() == original.Code() && error.Offset() == original.Offset();
                return false;
            } catch (...) { result.internalFailure = true; return false; }
        };
        if (!run("front", [&](DiagnosticStage& step) { step.playerId = RetailStateDetail::ReadPlayerFront(input); })) return;
        if (!run("policies", [&](DiagnosticStage&) { RetailStateDetail::ReadPlayerPolicies(input); })) return;
        if (!run("economic_ai", [&](DiagnosticStage&) { RetailStateDetail::ReadPlayerEconomicAI(input); })) return;
        if (!run("city_specialization_ai", [&](DiagnosticStage&) { RetailStateDetail::ReadPlayerCitySpecializationAI(input); })) return;
        if (!run("wonder_production_ai", [&](DiagnosticStage&) { RetailStateDetail::ReadPlayerWonderProductionAI(input); })) return;
        if (!run("military_ai", [&](DiagnosticStage&) { RetailStateDetail::ReadPlayerMilitaryAI(input); })) return;
        run("grand_strategy_ai", [&](DiagnosticStage&) { RetailStateDetail::ReadPlayerGrandStrategyAI(input, profile.grandStrategyCount); });
    } catch (...) { result.internalFailure = true; }
}
void DiagnosePlayerFailure(const Bytes& bytes, std::size_t start, std::size_t slot,
        const RetailSavePlayerWireProfile& profile, const RetailSaveStateLimits& limits,
        const RetailStateError& original) noexcept {
    // Diagnostic-only replay of one failed Player, with the same declared
    // profiles, source order and remaining budget. No alternate layout is tried.
    // A pool-header observation supplies its explicit live count even when a
    // real object fails later; those observational rows are not charged twice.
    try {
        FailedPlayer = {}; FailedPlayer.attempted = true; FailedPlayer.start = start;
        FailedPlayer.slot = static_cast<std::int32_t>(slot); FailedPlayer.initialRecordBudget = limits.maxTotalRecords;
        auto remaining = limits; auto cursor = start;
        auto run = [&](const char* name, auto&& function) {
            auto& step = FailedPlayer.stages[FailedPlayer.stageCount++];
            step.name = name; step.start = cursor; step.recordBudget = remaining.maxTotalRecords;
            try {
                function(step);
                if (step.next < cursor || step.next > bytes.size())
                    throw RetailStateError(Code::InvalidValue, cursor, "Diagnostic Player stage boundary escaped input");
                if (step.records > remaining.maxTotalRecords)
                    throw RetailStateError(Code::TotalRecordLimit, cursor, "Diagnostic Player stage exceeded shared budget");
                remaining.maxTotalRecords -= step.records; cursor = step.next; step.completed = true; return true;
            } catch (const RetailStateError& error) {
                step.typedError = true; step.errorCode = static_cast<int>(error.Code()); step.errorOffset = error.Offset();
                FailedPlayer.sameFailureReproduced = error.Code() == original.Code() && error.Offset() == original.Offset();
                return false;
            } catch (...) { FailedPlayer.internalFailure = true; return false; }
        };
        auto observePool = [&](DiagnosticStage& step) {
            RetailStateDetail::Reader header(bytes.data(), bytes.size(), remaining); header.Skip(cursor);
            const auto pool = RetailStateDetail::ReadFreeListHeader(header);
            step.poolObserved = true; step.poolCapacity = pool.slots; step.poolLiveCount = pool.liveCount;
            step.poolHeaderEnd = pool.nextInflatedOffset; step.poolHeaderRecords = header.Records();
        };
        if (!run("prefix", [&](DiagnosticStage& step) {
            const auto value = RetailSavePlayerPrefix::InspectAt(bytes.data(), bytes.size(), cursor, profile.prefixProfile, remaining);
            step.next = value.nextInflatedOffset; step.records = value.arrayRecords; step.playerId = value.playerId;
        })) {
            DiagnosePrefixFailure(bytes, cursor, profile.prefixProfile, remaining, original); return;
        }
        if (!run("middle_ai", [&](DiagnosticStage& step) {
            const auto value = RetailSavePlayerAiMid::InspectAt(bytes.data(), bytes.size(), cursor, profile.middleProfile, remaining);
            step.next = value.nextInflatedOffset; step.records = value.arrayRecords;
        })) return;
        if (!run("late_ai", [&](DiagnosticStage& step) {
            const auto value = RetailSavePlayerAiLate::InspectAt(bytes.data(), bytes.size(), cursor, profile.lateProfile, remaining);
            step.next = value.nextInflatedOffset; step.records = value.arrayRecords; step.plotCount = value.dangerPlotCount;
        })) return;
        if (!run("post_traits", [&](DiagnosticStage& step) {
            const auto value = RetailSavePlayerPostTraits::InspectAt(bytes.data(), bytes.size(), cursor, remaining);
            step.next = value.nextInflatedOffset; step.records = value.arrayRecords;
        })) return;
        if (!run("cities", [&](DiagnosticStage& step) {
            observePool(step);
            const auto value = RetailSavePlayerCities::InspectAt(bytes.data(), bytes.size(), cursor, profile.cityProfile, remaining);
            step.next = value.nextInflatedOffset; step.records = value.arrayRecords;
        })) return;
        if (!run("units", [&](DiagnosticStage& step) {
            observePool(step);
            const auto value = RetailSavePlayerUnits::InspectAt(bytes.data(), bytes.size(), cursor, profile.unitProfile, remaining);
            step.next = value.nextInflatedOffset; step.records = value.arrayRecords;
        })) return;
        run("ending", [&](DiagnosticStage& step) {
            observePool(step);
            const auto value = RetailSavePlayerEnd::InspectAt(bytes.data(), bytes.size(), cursor, profile.endProfile, remaining);
            step.next = value.nextInflatedOffset; step.records = value.arrayRecords; step.operationCount = value.operations.declaredCount;
        });
    } catch (...) { FailedPlayer.internalFailure = true; }
}
DirectTrace TracePlayers(Suite& s, const Bytes& bytes, std::size_t start, const RetailSaveStateLimits& limits) {
    DirectTrace trace; trace.start = start; auto cursor = start; auto remaining = limits;
    const auto profile = PlayerProfile();
    for (std::size_t slot = 0; slot < ExpectedPlayers; ++slot) {
        Current.phase = "source_ordered_direct_player"; Current.currentSlot = static_cast<std::int32_t>(slot);
        Current.slotStart = cursor;
        RetailSavePlayerInspection player;
        try { player = RetailSavePlayer::InspectAt(bytes.data(), bytes.size(), cursor, profile, remaining); }
        catch (const RetailStateError& error) {
            DiagnosePlayerFailure(bytes, cursor, slot, profile, remaining, error); throw;
        }
        s.Check(player.playerId == static_cast<std::int32_t>(slot) && player.prefix.playerId == player.playerId &&
            Word(bytes, cursor) == 16u && Word(bytes, cursor + 864u) == static_cast<std::uint32_t>(slot),
            "Source-ordered direct Player ID/version differs from literal front offsets");
        s.Check(player.whole.offset == cursor && player.whole.bytes > 0u && player.nextInflatedOffset > cursor &&
            player.nextInflatedOffset <= bytes.size() && player.whole.bytes == player.nextInflatedOffset - cursor &&
            player.prefix.front.offset == cursor && player.arrayRecords <= remaining.maxTotalRecords,
            "Source-ordered direct Player span or shared budget escaped input");
        s.Check(player.completePlayerWireFramed && !player.completePlayerVerified && !player.completeSaveVerified &&
            !player.rulesetCompatibilityVerified && !player.restoreApproved && !player.cities.cityObjectIdsVerified &&
            !player.cities.restoreApproved && !player.units.unitObjectIdsVerified && !player.units.restoreApproved &&
            !player.ending.operations.objectReferencesVerified && !player.ending.restoreApproved,
            "Direct Player framing granted semantic or restore approval");
        if (slot == 0u) s.Check(player.nextInflatedOffset == 2444461u && player.prefix.nextInflatedOffset == 2326136u,
            "Retained first Player boundary differs");
        if (slot == 1u) s.Check(player.prefix.nextInflatedOffset == 2460895u,
            "Retained exact Player-1 prefix boundary differs");
        auto& summary = trace.players[slot];
        summary.whole = player.whole; summary.playerId = player.playerId; summary.records = player.arrayRecords;
        summary.prefixEnd = player.prefix.nextInflatedOffset;
        summary.cities = player.cities.pool.liveCount; summary.units = player.units.pool.liveCount;
        summary.armies = player.ending.armyPool.liveCount; summary.operations = player.ending.operations.declaredCount;
        trace.records += summary.records; trace.cities += summary.cities; trace.units += summary.units;
        trace.armies += summary.armies; trace.operations += summary.operations;
        remaining.maxTotalRecords -= player.arrayRecords; cursor = player.nextInflatedOffset;
        Current.completed = slot + 1u; Current.lastPlayerEnd = cursor;
    }
    trace.end = cursor; return trace;
}
void CompareAggregate(Suite& s, const RetailSavePlayersInspection& actual, const DirectTrace& expected,
        std::size_t parseStart, std::size_t inputSize) {
    s.Check(actual.playerCount == ExpectedPlayers && actual.whole.offset == parseStart &&
        actual.nextInflatedOffset >= parseStart && actual.nextInflatedOffset <= inputSize &&
        actual.whole.bytes == expected.end - expected.start && actual.nextInflatedOffset == parseStart + actual.whole.bytes &&
        actual.arrayRecords == expected.records && actual.cityCount == expected.cities && actual.unitCount == expected.units &&
        actual.armyCount == expected.armies && actual.operationCount == expected.operations,
        "Aggregate Player block differs from direct trace boundaries, records or object totals");
    auto cursor = parseStart; std::size_t records = 0;
    for (std::size_t slot = 0; slot < ExpectedPlayers; ++slot) {
        const auto& a = actual.players[slot]; const auto& e = expected.players[slot];
        s.Check(a.playerId == static_cast<std::int32_t>(slot) && a.playerId == e.playerId && a.whole.offset == cursor &&
            a.whole.offset == parseStart + (e.whole.offset - expected.start) && a.whole.bytes == e.whole.bytes &&
            a.arrayRecords == e.records && a.cityCount == e.cities && a.unitCount == e.units &&
            a.armyCount == e.armies && a.operationCount == e.operations,
            "Aggregate per-slot summary differs from the source-ordered direct trace");
        s.Check(a.whole.offset <= inputSize && a.whole.bytes <= inputSize - a.whole.offset,
            "Aggregate slot escaped its input");
        cursor += a.whole.bytes; records += a.arrayRecords;
    }
    s.Check(cursor == actual.nextInflatedOffset && records == actual.arrayRecords,
        "Aggregate charged a nonexistent outer player count or omitted slot rows");
    s.Check(actual.allExpectedPlayersWireFramed && !actual.objectReferencesVerified && !actual.completeSaveVerified &&
        !actual.rulesetCompatibilityVerified && !actual.restoreApproved,
        "Aggregate framing granted object, save, ruleset or restore approval");
}
template<class Function> void RejectAt(Suite& s, Function&& function, Code expected,
        std::size_t inputSize, std::size_t expectedOffset) {
    try { function(); }
    catch (const RetailStateError& error) {
        s.Check(error.Code() == expected, "Directed prefix corruption produced the wrong typed error");
        s.Check(error.Offset() == expectedOffset && error.Offset() <= inputSize,
            "Directed prefix corruption escaped its exact expected slot offset"); return;
    }
    s.Check(false, "Directed Player prefix corruption was accepted");
}
void PublicDerivedTests(Suite& s, const Bytes& bytes, const DirectTrace& trace) {
    // This exact byte range is derived from the authenticated public stream.
    // Its independent direct trace supplies boundaries, not a new serializer.
    Bytes block(bytes.begin() + static_cast<std::ptrdiff_t>(trace.start),
        bytes.begin() + static_cast<std::ptrdiff_t>(trace.end));
    const auto baseline = block;
    const auto profile = PlayersProfile(); auto exact = RetailSaveStateLimits{};
    exact.maxTotalRecords = trace.records;
    Current.phase = "public_derived_exact_block"; Current.currentSlot = -1;
    CompareAggregate(s, RetailSavePlayers::InspectAt(block.data(), block.size(), 0, profile, exact), trace, 0, block.size());
    for (std::size_t slot = 0; slot < ExpectedPlayers; ++slot) {
        const auto start = trace.players[slot].whole.offset - trace.start;
        const auto end = start + trace.players[slot].whole.bytes;
        Current.currentSlot = static_cast<std::int32_t>(slot); Current.slotStart = start;
        Current.phase = "public_derived_prefix_version_corruption";
        Put(block, start, 17);
        RejectAt(s, [&] { RetailSavePlayers::InspectAt(block.data(), block.size(), 0, profile, exact); },
            Code::UnsupportedVersion, block.size(), start + 4u);
        s.Check(Word(block, start) == 17u, "Parser rewrote a rejected public-derived version word");
        Put(block, start, 16); s.Check(block == baseline, "Rejected version parse changed other input bytes");
        ++s.directedCorruptions;
        Current.phase = "public_derived_prefix_id_corruption";
        const auto wrongId = static_cast<std::uint32_t>((slot + 1u) % ExpectedPlayers);
        Put(block, start + 864u, wrongId);
        RejectAt(s, [&] { RetailSavePlayers::InspectAt(block.data(), block.size(), 0, profile, exact); },
            Code::InvalidValue, block.size(), start);
        s.Check(Word(block, start + 864u) == wrongId, "Parser rewrote a rejected public-derived Player ID");
        Put(block, start + 864u, static_cast<std::uint32_t>(slot));
        s.Check(block == baseline, "Rejected ID parse changed other input bytes"); ++s.directedCorruptions;
        Current.phase = "public_derived_slot_boundary_truncation";
        Reject(s, [&] { RetailSavePlayers::InspectAt(block.data(), start, 0, profile, exact); }, Code::Truncated, start);
        ++s.truncations;
        Reject(s, [&] { RetailSavePlayers::InspectAt(block.data(), end - 1u, 0, profile, exact); }, Code::Truncated, end - 1u);
        ++s.truncations;
    }
    Current.phase = "public_derived_profile_rejections"; Current.currentSlot = -1;
    auto rejectProfile = [&](const RetailSavePlayersProfile& bad) {
        Reject(s, [&] { RetailSavePlayers::InspectAt(block.data(), block.size(), 0, bad, exact); },
            Code::UnsupportedProfile, block.size());
    };
    auto bad = profile; bad.blockProfile = static_cast<RetailPlayerBlockProfile>(99); rejectProfile(bad);
    bad = profile; bad.playerProfile.prefixProfile.grandStrategyCount = 0xffffffffu; rejectProfile(bad);
    bad = profile; bad.playerProfile.prefixProfile.catalogProfile = static_cast<RetailPlayerCatalogProfile>(99); rejectProfile(bad);
    bad = profile; bad.playerProfile.middleProfile = static_cast<RetailPlayerAiMidCatalogProfile>(99); rejectProfile(bad);
    bad = profile; bad.playerProfile.lateProfile = static_cast<RetailPlayerAiLateProfile>(99); rejectProfile(bad);
    bad = profile; bad.playerProfile.cityProfile.yieldTypes = 5; rejectProfile(bad);
    bad = profile; bad.playerProfile.cityProfile.production.catalogProfile = static_cast<RetailCityProductionCatalogProfile>(99); rejectProfile(bad);
    bad = profile; bad.playerProfile.unitProfile = static_cast<RetailUnitWriterProfile>(99); rejectProfile(bad);
    bad = profile; bad.playerProfile.endProfile.operationProfile = static_cast<RetailPlayerOperationsProfile>(99); rejectProfile(bad);
    bad = profile; bad.playerProfile.endProfile.fieldProfile = static_cast<RetailPlayerEndWriterProfile>(99); rejectProfile(bad);
    Current.phase = "public_derived_budget_boundaries";
    auto limits = exact; --limits.maxTotalRecords;
    Reject(s, [&] { RetailSavePlayers::InspectAt(block.data(), block.size(), 0, profile, limits); }, Code::TotalRecordLimit, block.size());
    std::size_t largestSlot = 0;
    for (const auto& slot : trace.players) largestSlot = std::max(largestSlot, slot.records);
    s.Check(largestSlot < trace.records, "Public-derived block lost its multi-slot record-budget test");
    limits = exact; limits.maxTotalRecords = largestSlot;
    Reject(s, [&] { RetailSavePlayers::InspectAt(block.data(), block.size(), 0, profile, limits); }, Code::TotalRecordLimit, block.size());
    limits = exact; limits.maxTotalRecords = 0;
    Reject(s, [&] { RetailSavePlayers::InspectAt(block.data(), block.size(), 0, profile, limits); }, Code::TotalRecordLimit, block.size());
    limits = exact; limits.maxArrayRecords = 0;
    Reject(s, [&] { RetailSavePlayers::InspectAt(block.data(), block.size(), 0, profile, limits); }, Code::ArrayLimit, block.size());
    limits = exact; limits.maxInputBytes = block.size();
    s.Check(RetailSavePlayers::InspectAt(block.data(), block.size(), 0, profile, limits).arrayRecords == trace.records,
        "Exact public-derived block input budget rejected");
    --limits.maxInputBytes;
    Reject(s, [&] { RetailSavePlayers::InspectAt(block.data(), block.size(), 0, profile, limits); }, Code::InputLimit, block.size());
    limits = exact; limits.maxPrefixBytes = block.size();
    s.Check(RetailSavePlayers::InspectAt(block.data(), block.size(), 0, profile, limits).nextInflatedOffset == block.size(),
        "Exact public-derived block prefix budget rejected");
    --limits.maxPrefixBytes;
    Reject(s, [&] { RetailSavePlayers::InspectAt(block.data(), block.size(), 0, profile, limits); }, Code::PrefixLimit, block.size());
    Reject(s, [&] { RetailSavePlayers::InspectAt(nullptr, 1, 0, profile); }, Code::NullInput, 1);
    Reject(s, [&] { RetailSavePlayers::InspectAt(nullptr, 0, 0, profile); }, Code::Truncated, 0);
    Reject(s, [&] { RetailSavePlayers::InspectAt(block.data(), block.size(), block.size() + 1u, profile); }, Code::Truncated, block.size());
    Reject(s, [&] { RetailSavePlayers::InspectAt(block.data(), block.size(), (std::numeric_limits<std::size_t>::max)(), profile); }, Code::Truncated, block.size());
    s.Check(block == baseline, "Public-derived aggregate tests changed the baseline block");
    Current.phase = "public_derived_prefix_and_suffix";
    Bytes padded = {0x16u,0u,0u,0u,0xffu,0u,0xa5u}; const auto start = padded.size();
    padded.insert(padded.end(), block.begin(), block.end()); const auto end = padded.size();
    const std::array<unsigned char, 12> suffix = {16,0,0,0,0,0,0,0,0x78,0x9c,0xff,0};
    padded.insert(padded.end(), suffix.begin(), suffix.end()); const auto before = padded;
    const auto framed = RetailSavePlayers::InspectAt(padded.data(), padded.size(), start, profile, exact);
    CompareAggregate(s, framed, trace, start, padded.size());
    s.Check(framed.nextInflatedOffset == end && Word(padded, end) == 16u && padded == before,
        "Aggregate consumed a Player-like suffix, searched padding or modified caller bytes");
}
PublicResult Public(Suite& s) {
    Current.phase = "public_stdin"; const auto bytes = ReadStdin(), before = bytes;
    Current.inputBytes = bytes.size();
    s.Check(bytes.size() == 9762327u, "Wrong externally authenticated public plaintext size");
    auto remaining = RetailSaveStateLimits{}; Current.phase = "source_ordered_map";
    const auto map = RetailSaveMap::InspectGameAndMap(bytes, RetailSaveStateProfile(5), remaining);
    s.Check(map.nextInflatedOffset == 1695150u && map.plotCount == 960u && map.arrayRecords <= remaining.maxTotalRecords,
        "Source-ordered public Map boundary or record budget differs");
    remaining.maxTotalRecords -= map.arrayRecords; Current.phase = "source_ordered_teams";
    RetailStateDetail::Reader teams(bytes.data(), bytes.size(), remaining); teams.Skip(map.nextInflatedOffset);
    for (std::int32_t id = 0; id < 64; ++id)
        s.Check(RetailStateDetail::ReadTeam(teams) == id, "Source-ordered public Team ID differs");
    s.Check(teams.Pos() == 2309550u && teams.Records() <= remaining.maxTotalRecords,
        "Source-ordered 64-Team boundary or record budget differs");
    remaining.maxTotalRecords -= teams.Records(); PublicResult result; result.bytes = bytes.size();
    result.trace = TracePlayers(s, bytes, teams.Pos(), remaining);
    Current.phase = "source_ordered_player_aggregate"; Current.currentSlot = -1;
    try {
        result.aggregate = RetailSavePlayers::InspectAt(bytes.data(), bytes.size(), teams.Pos(), PlayersProfile(), remaining);
    } catch (const RetailStateError& error) {
        // Locate a diagnostic slot in the already completed direct trace.
        // This compares returned spans, not byte patterns or candidate layouts.
        auto location = error.Offset();
        if (error.Code() == Code::UnsupportedVersion && location > result.trace.start) --location;
        for (std::size_t slot = 0; slot < ExpectedPlayers; ++slot) {
            const auto& span = result.trace.players[slot].whole;
            if (location >= span.offset && location - span.offset < span.bytes) {
                Current.currentSlot = static_cast<std::int32_t>(slot); Current.slotStart = span.offset; break;
            }
        }
        throw;
    }
    CompareAggregate(s, result.aggregate, result.trace, teams.Pos(), bytes.size());
    s.Check(result.aggregate.arrayRecords <= remaining.maxTotalRecords,
        "Aggregate exceeded the Map/Teams/Players shared record budget");
    auto supportingLimits = remaining; supportingLimits.maxTotalRecords -= result.aggregate.arrayRecords;
    Current.phase = "source_ordered_supporting"; Current.currentSlot = -1;
    result.supporting = RetailSaveSupporting::InspectAt(bytes.data(), bytes.size(), result.aggregate.nextInflatedOffset,
        map.plotCount, supportingLimits);
    Current.supportingBytes = result.supporting.bytes;
    Current.supportingEnd = result.supporting.offset + result.supporting.bytes;
    s.Check(result.supporting.offset == result.aggregate.nextInflatedOffset && result.supporting.bytes == 4116u &&
        result.supporting.bytes == 276u + 4u * map.plotCount && Current.supportingEnd <= bytes.size(),
        "Supporting state is not adjacent to all 64 Players with the explicit Map plot width");
    result.followingBytes = bytes.size() - Current.supportingEnd; Current.followingBytes = result.followingBytes;
    result.plaintextFramed = result.followingBytes == 0u;
    s.Check(result.plaintextFramed, "Supporting endpoint leaves unexpected trailing plaintext bytes");
    s.Check(bytes == before, "Source-ordered Map/Teams/Players/Supporting parsing modified public input");
    PublicDerivedTests(s, bytes, result.trace);
    s.Check(bytes == before, "Public-derived tests modified the authenticated input"); return result;
}
void PublicJson(const PublicResult& value) {
    const auto& r = value.aggregate;
    std::cout << ",\"public\":{\"input_bytes\":" << value.bytes << ",\"start_offset\":" << r.whole.offset
        << ",\"next_inflated_offset\":" << r.nextInflatedOffset << ",\"player_count\":" << r.playerCount
        << ",\"players_bytes\":" << r.whole.bytes << ",\"array_records\":" << r.arrayRecords
        << ",\"city_count\":" << r.cityCount << ",\"unit_count\":" << r.unitCount << ",\"army_count\":" << r.armyCount
        << ",\"operation_count\":" << r.operationCount << ",\"all_expected_players_wire_framed\":true"
        << ",\"direct_trace_matches_aggregate\":true,\"source_ordered\":true,\"pattern_search_used\":false"
        << ",\"first_player_end\":" << value.trace.players[0].whole.offset + value.trace.players[0].whole.bytes
        << ",\"second_player_prefix_end\":" << value.trace.players[1].prefixEnd
        << ",\"following_bytes\":" << value.bytes - r.nextInflatedOffset
        << ",\"supporting_offset\":" << value.supporting.offset << ",\"supporting_bytes\":" << value.supporting.bytes
        << ",\"supporting_next_offset\":" << value.supporting.offset + value.supporting.bytes
        << ",\"supporting_array_records\":0,\"plaintext_following_bytes\":" << value.followingBytes
        << ",\"public_plaintext_framed\":" << (value.plaintextFramed ? "true" : "false") << ",\"per_slot\":[";
    for (std::size_t slot = 0; slot < ExpectedPlayers; ++slot) {
        const auto& p = r.players[slot]; if (slot) std::cout << ',';
        std::cout << "{\"slot\":" << slot << ",\"player_id\":" << p.playerId << ",\"start_offset\":" << p.whole.offset
            << ",\"next_offset\":" << p.whole.offset + p.whole.bytes << ",\"bytes\":" << p.whole.bytes
            << ",\"prefix_end\":" << value.trace.players[slot].prefixEnd << ",\"array_records\":" << p.arrayRecords
            << ",\"city_count\":" << p.cityCount << ",\"unit_count\":" << p.unitCount
            << ",\"army_count\":" << p.armyCount << ",\"operation_count\":" << p.operationCount << '}';
    }
    std::cout << "],\"object_references_verified\":false,\"complete_player_validated\":false,\"complete_save_validated\":false"
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
void DiagnosticJson() {
    std::cout << ",\"failed_player_replay\":{\"attempted\":" << (FailedPlayer.attempted ? "true" : "false");
    if (FailedPlayer.attempted) {
        std::cout << ",\"slot\":" << FailedPlayer.slot << ",\"start_offset\":" << FailedPlayer.start
            << ",\"initial_record_budget\":" << FailedPlayer.initialRecordBudget
            << ",\"same_declared_profile\":true,\"budget_raised\":false,\"alternate_layouts_tried\":false"
            << ",\"same_failure_reproduced\":" << (FailedPlayer.sameFailureReproduced ? "true" : "false")
            << ",\"internal_failure\":" << (FailedPlayer.internalFailure ? "true" : "false") << ",\"stages\":[";
        for (std::size_t index = 0; index < FailedPlayer.stageCount; ++index) {
            const auto& step = FailedPlayer.stages[index]; if (index) std::cout << ',';
            std::cout << "{\"name\":\"" << Escape(step.name) << "\",\"start_offset\":" << step.start
                << ",\"completed\":" << (step.completed ? "true" : "false") << ",\"next_offset\":" << step.next
                << ",\"array_records\":" << step.records << ",\"record_budget\":" << step.recordBudget;
            if (step.playerId != -1) std::cout << ",\"player_id\":" << step.playerId;
            if (step.plotCount) std::cout << ",\"danger_plot_count\":" << step.plotCount;
            if (step.poolObserved) std::cout << ",\"pool_capacity\":" << step.poolCapacity
                << ",\"pool_live_count\":" << step.poolLiveCount << ",\"pool_header_end\":" << step.poolHeaderEnd
                << ",\"pool_header_records\":" << step.poolHeaderRecords;
            if (step.operationCount) std::cout << ",\"operation_count\":" << step.operationCount;
            if (step.typedError) std::cout << ",\"error_code\":" << step.errorCode << ",\"error_offset\":" << step.errorOffset;
            std::cout << '}';
        }
        std::cout << ']';
        const auto& prefix = FailedPlayer.prefix;
        if (prefix.attempted) {
            std::cout << ",\"prefix_replay_attempted\":true,\"prefix_single_reader\":true"
                << ",\"prefix_same_failure_reproduced\":" << (prefix.sameFailureReproduced ? "true" : "false")
                << ",\"prefix_internal_failure\":" << (prefix.internalFailure ? "true" : "false");
            if (prefix.rawVersionObserved) std::cout << ",\"raw_player_version_offset\":" << FailedPlayer.start
                << ",\"raw_player_version\":" << prefix.rawVersion;
            if (prefix.rawPlayerIdObserved) std::cout << ",\"raw_player_id_offset\":" << FailedPlayer.start + 864u
                << ",\"raw_player_id\":" << prefix.rawPlayerId;
            std::cout << ",\"prefix_nested_stages\":[";
            for (std::size_t index = 0; index < prefix.stageCount; ++index) {
                const auto& step = prefix.stages[index]; if (index) std::cout << ',';
                std::cout << "{\"name\":\"" << Escape(step.name) << "\",\"start_offset\":" << step.start
                    << ",\"next_offset\":" << step.next << ",\"array_records\":" << step.records
                    << ",\"record_budget\":" << step.recordBudget << ",\"completed\":" << (step.completed ? "true" : "false");
                if (step.playerId != -1) std::cout << ",\"player_id\":" << step.playerId;
                if (step.typedError) std::cout << ",\"error_code\":" << step.errorCode << ",\"error_offset\":" << step.errorOffset;
                std::cout << '}';
            }
            std::cout << ']';
        }
    }
    std::cout << '}';
}
int Failure(const std::exception& error, int code, std::size_t offset, bool offsetKnown) {
    std::cout << "{\"status\":\"FAIL_RETAIL_PLAYERS_COMPONENT\",\"error\":\"" << Escape(error.what())
        << "\",\"error_code\":" << code << ",\"error_offset\":" << offset
        << ",\"error_offset_known\":" << (offsetKnown ? "true" : "false") << ",\"phase\":\"" << Escape(Current.phase)
        << "\",\"current_slot\":" << Current.currentSlot << ",\"slot_start_offset\":" << Current.slotStart
        << ",\"direct_players_completed\":" << Current.completed << ",\"observed_input_bytes\":" << Current.inputBytes
        << ",\"last_player_end\":" << Current.lastPlayerEnd << ",\"observed_supporting_bytes\":" << Current.supportingBytes
        << ",\"observed_supporting_next_offset\":" << Current.supportingEnd
        << ",\"observed_plaintext_following_bytes\":" << Current.followingBytes;
    DiagnosticJson();
    std::cout << ",\"gamecore_loaded\":false,\"window_created\":false,\"game_accessed\":false,\"user_saves_accessed\":false"
        << ",\"complete_player_validated\":false,\"complete_save_validated\":false"
        << ",\"ruleset_compatibility_verified\":false,\"restore_approved\":false}\n";
    return 1;
}
} // namespace

int main(int argc, char** argv) {
    try {
        static_assert(sizeof(void*) == 8, "Players component verification requires x64");
        if (argc != 2 || std::string(argv[1]) != "--public")
            throw std::runtime_error("Expected --public and caller-authenticated plaintext on stdin");
        Suite s; SupportingTests(s); const auto result = Public(s);
        Current.phase = "result_accounting"; Current.currentSlot = -1;
        s.Check(s.checks >= 256u && s.truncations >= 128u && s.directedCorruptions >= 128u,
            "Players component verification accounting differs");
        std::cout << "{\"status\":\"PASS_RETAIL_PLAYERS_COMPONENT\",\"checks\":" << s.checks
            << ",\"synthetic_supporting_cases\":3,\"synthetic_player_block_cases\":0,\"public_derived_block_cases\":1"
            << ",\"public_derived_prefix_version_cases\":64,\"public_derived_prefix_id_cases\":64"
            << ",\"truncations\":" << s.truncations << ",\"directed_corruptions\":" << s.directedCorruptions
            << ",\"input_files_unchanged\":true,\"input_bytes_unchanged\":true"
            << ",\"gamecore_loaded\":false,\"window_created\":false,\"game_accessed\":false,\"user_saves_accessed\":false"
            << ",\"complete_player_validated\":false,\"complete_save_validated\":false"
            << ",\"ruleset_compatibility_verified\":false,\"restore_approved\":false";
        PublicJson(result); std::cout << "}\n"; return 0;
    } catch (const RetailStateError& error) {
        return Failure(error, static_cast<int>(error.Code()), error.Offset(), true);
    } catch (const std::exception& error) {
        return Failure(error, -1, 0, false);
    }
}
