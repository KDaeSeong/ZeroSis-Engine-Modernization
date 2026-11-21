#include "RetailSaveImportSections.h"
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

// Independent Pregame byte transcripts and stdin-only public integration.
// No SDK serialization, NativeSaveArchive include, file or runtime is used.
namespace {
using namespace ZeroSisHost;
using Bytes = std::vector<unsigned char>;
constexpr std::size_t MaximumRawBytes = 8u * 1024u * 1024u;
constexpr std::size_t MaximumBodyBytes = 64u * 1024u * 1024u;
constexpr std::size_t Absent = (std::numeric_limits<std::size_t>::max)();
struct Suite {
    std::size_t checks = 0, syntheticCases = 0, truncations = 0, corruptions = 0;
    std::size_t atomicFailures = 0, elapsedCases = 0, optionsCases = 0;
    void Check(bool value, const char* message) {
        ++checks; if (!value) throw std::runtime_error(message);
    }
};
enum class Mode { Unselected, SelfTest, Public };
struct Options {
    Mode mode = Mode::Unselected;
    std::size_t rawSize = 0, bodySize = 0, recordBudget = 1024u * 1024u;
    std::uint32_t awards = 0, grand = 0, projects = 0;
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
    Options value;
    if (argc == 2 && std::strcmp(argv[1], "--self-test") == 0) { value.mode = Mode::SelfTest; return value; }
    if (argc != 8 || std::strcmp(argv[1], "--public") != 0)
        throw std::invalid_argument("Require --self-test or --public rawSize bodySize awards grand projects recordBudget");
    value.mode = Mode::Public;
    value.rawSize = Number(argv[2], static_cast<std::uint32_t>(MaximumRawBytes));
    value.bodySize = Number(argv[3], static_cast<std::uint32_t>(MaximumBodyBytes));
    value.awards = Number(argv[4], 4096u); value.grand = Number(argv[5], 4096u); value.projects = Number(argv[6], 4096u);
    value.recordBudget = Number(argv[7], static_cast<std::uint32_t>(MaximumBodyBytes));
    if (!value.rawSize || !value.bodySize || !value.recordBudget) throw std::invalid_argument("Sizes and record budget must be positive");
    return value;
}
RetailSaveBodyImportProfile BodyProfile(const Options& options) {
    const RetailSavePlayerWireProfile player{
        RetailSavePlayerProfile(options.grand, RetailPlayerCatalogProfile::InitializedBuildings),
        RetailPlayerAiMidCatalogProfile::InitializedTechs, RetailPlayerAiLateProfile::InitializedMinorQuests,
        RetailSaveCityProfile(options.projects, RetailCityProductionCatalogProfile::InitializedBuildingsAndUnits, 6u),
        RetailUnitWriterProfile::Bnw9CompleteGreatWorkHashWord,
        RetailSavePlayerEndProfile(RetailPlayerOperationsProfile::BnwCurrentFactory20,
            RetailPlayerEndWriterProfile::Current16With64Players)};
    return {RetailBodyLayout::Bnw64GameMapTeamsPlayersSupporting, RetailSaveStateProfile(options.awards), player};
}
constexpr std::array<std::size_t, 17> ScalarOffsets = {{
    181,369,391,392,405,410,411,439,730,731,732,737,738,739,791,816,873
}};
constexpr std::array<const char*, 17> ScalarNames = {{
    "s_autorun","s_gameStarted","s_isEarthMap","s_isInternetGame","s_mapNoPlayers",
    "s_loadWBScenario","s_overrideScenarioHandicap","s_dummyvalue","s_privateGame",
    "s_quickCombat","s_quickCombatDefault","s_quickstart","s_randomWorldSize","s_randomMapScript",
    "s_dummyvalue2","s_transferredMap","s_bCityScreenBlocked"
}};
constexpr std::array<const char*, 9> ArrayNames = {{
    "s_DEPRECATEDforceControls","s_minorNationCivs","s_multiplayerOptions","s_playableCivs","s_readyPlayers",
    "s_victories","s_whiteFlags","s_turnNotifySteamInvite","s_turnNotifyEmail"
}};
struct Fixture {
    Bytes raw;
    std::array<std::size_t, 9> arrays{};
    std::size_t wholeEnd = 0, world = 0, gameName = 0, mapName = 0, maximumName = 0;
    std::size_t gameLength = 0, mapLength = 0;
    std::uint32_t worldVersion = 0;
    bool embeddedNull = false;
};
Fixture Literal(std::uint32_t worldVersion, const std::string& gameOption = "A", const std::string& mapOption = "B") {
    if ((worldVersion != 1u && worldVersion != 2u) || gameOption.size() > 64u || mapOption.size() > 64u)
        throw std::runtime_error("Invalid literal fixture request");
    // Fixed on-disk locations are independent constants, not production writer
    // output or an implementation of the parser's sequence of read operations.
    Fixture fixture; fixture.worldVersion = worldVersion; fixture.world = 888;
    const std::size_t extraWorldWord = worldVersion == 2u ? 4u : 0u;
    const auto names = gameOption.size() + mapOption.size();
    fixture.wholeEnd = 1050u + names + extraWorldWord;
    fixture.raw.assign(fixture.wholeEnd + 8u, 0);
    auto& raw = fixture.raw;
    raw[0] = 'C'; raw[1] = 'I'; raw[2] = 'V'; raw[3] = '5'; raw[4] = 8;
    raw[16] = 42; // Header turn; nine metadata strings and both record lists empty.
    raw[69] = 68; // Opaque player-info byte, deliberately not a boolean.
    raw[109] = 3; raw[157] = 6; // Slot hints and Pregame archive versions.
    raw[169] = 68; raw[182] = 68; // Two genuine int32 words retain byte 0x44.
    for (std::size_t i = 0; i < ScalarOffsets.size(); ++i)
        raw[ScalarOffsets[i]] = static_cast<unsigned char>(i % 2u);
    raw[370] = 42; // Pregame turn, after game speed and game-started byte.
    raw[447] = 64; // Network-ID vector: count plus 64 int32 -1 values.
    std::fill(raw.begin() + 451, raw.begin() + 707, static_cast<unsigned char>(255));
    raw[888] = static_cast<unsigned char>(worldVersion);
    fixture.arrays = {{354,436,444,723,744,878,885,
        1036u + names + extraWorldWord, 1043u + names + extraWorldWord}};
    for (const auto payload : fixture.arrays) { raw[payload - 4u] = 3; raw[payload + 1u] = 1; }
    raw[1004u + extraWorldWord] = 1;
    raw[1008u + extraWorldWord] = static_cast<unsigned char>(gameOption.size());
    fixture.gameName = 1012u + extraWorldWord;
    std::copy(gameOption.begin(), gameOption.end(), raw.begin() + static_cast<std::ptrdiff_t>(fixture.gameName));
    raw[fixture.gameName + gameOption.size()] = 68;
    raw[1016u + gameOption.size() + extraWorldWord] = 1;
    raw[1020u + gameOption.size() + extraWorldWord] = static_cast<unsigned char>(mapOption.size());
    fixture.mapName = 1024u + gameOption.size() + extraWorldWord;
    std::copy(mapOption.begin(), mapOption.end(), raw.begin() + static_cast<std::ptrdiff_t>(fixture.mapName));
    raw[fixture.mapName + mapOption.size()] = 68;
    fixture.gameLength = gameOption.size(); fixture.mapLength = mapOption.size();
    fixture.maximumName = (std::max)(gameOption.size(), mapOption.size());
    fixture.embeddedNull = gameOption.find('\0') != std::string::npos || mapOption.find('\0') != std::string::npos;
    raw[fixture.wholeEnd] = 2; raw[fixture.wholeEnd + 6u] = 1; // Format word, then literal 65536.
    return fixture;
}
void Put(Bytes& data, std::size_t offset, std::uint32_t value) {
    if (offset > data.size() || data.size() - offset < 4u) throw std::runtime_error("Test word outside input");
    for (unsigned shift = 0; shift < 32u; shift += 8u) data[offset + shift / 8u] = static_cast<unsigned char>(value >> shift);
}

enum class Domain { None, Metadata, Pregame, Typed, State };
struct Failure { Domain domain = Domain::None; int code = -1; std::size_t offset = Absent; };
template<class Function>
Failure FailureOf(Function function) {
    Failure failure;
    try { function(); }
    catch (const RetailSaveHeaderError& error) { failure = {Domain::Metadata, static_cast<int>(error.Code()), Absent}; }
    catch (const RetailSavePregameError& error) { failure = {Domain::Pregame, static_cast<int>(error.Code()), Absent}; }
    catch (const RetailPregameImportError& error) { failure = {Domain::Typed, static_cast<int>(error.Code()), error.RawOffset()}; }
    catch (const RetailStateError& error) { failure = {Domain::State, static_cast<int>(error.Code()), error.Offset()}; }
    return failure;
}
RetailSavePreparedPregame PregameSentinel() {
    RetailSavePreparedPregame value; value.bytes = {0xa5,68,0,255};
    value.wire.whole = {17,19}; value.wire.activePlayer = -77; value.wire.gameTurn = -91;
    value.wire.scalarBooleans[0].rawOffset = 777;
    return value;
}
bool IsPregameSentinel(const RetailSavePreparedPregame& value) {
    return value.bytes == Bytes{0xa5,68,0,255} && value.wire.whole.offset == 17u && value.wire.whole.bytes == 19u &&
        value.wire.activePlayer == -77 && value.wire.gameTurn == -91 && value.wire.scalarBooleans[0].rawOffset == 777u &&
        !value.canonicalBooleansChecked && !value.rulesetCompatibilityVerified && !value.restoreApproved;
}
RetailSaveImportPreparation SectionSentinel() {
    RetailSaveImportPreparation value; value.pregame = PregameSentinel();
    value.body.bytes = {0x55,68}; value.body.edits = {{1,68,1,3,5}};
    value.turn = 701; value.elapsed = 702; value.activePlayer = 37; value.totalPayloadBytes = 999;
    value.sections[0] = {99,13,RetailImportStorage::Body,{9,17}};
    return value;
}
bool IsSectionSentinel(const RetailSaveImportPreparation& value) {
    if (!IsPregameSentinel(value.pregame) || value.body.bytes != Bytes{0x55,68} || value.body.edits.size() != 1u ||
        value.body.edits[0].offset != 1u || value.body.edits[0].before != 68u || value.body.edits[0].after != 1u ||
        value.body.edits[0].playerSlot != 3u || value.body.edits[0].operationIndex != 5u ||
        value.turn != 701 || value.elapsed != 702 || value.activePlayer != 37 || value.totalPayloadBytes != 999u ||
        value.retailHeaderTurnMatches || value.offlineTransportUnassigned || value.compressedBodyAssociationVerified || value.bundleIdentityVerified ||
        value.rulesetCompatibilityVerified || value.producerContractVerified || value.completeSaveVerified ||
        value.nativeRestoreApproved || value.body.canonicalWireFramed || value.body.restoreApproved) return false;
    for (std::size_t i = 0; i < value.sections.size(); ++i) {
        const auto& section = value.sections[i];
        if (i == 0u) {
            if (section.kind != 99u || section.index != 13u || section.storage != RetailImportStorage::Body ||
                section.span.offset != 9u || section.span.bytes != 17u) return false;
        } else if (section.kind || section.index || section.storage != RetailImportStorage::Body ||
            section.span.offset || section.span.bytes) return false;
    }
    return true;
}
template<class Value, class Function, class Unchanged>
void Reject(Suite& suite, Value sentinel, Function function, Unchanged unchanged, Domain domain, int code,
    std::size_t offset = Absent) {
    auto output = sentinel;
    const auto failure = FailureOf([&] { output = function(); });
    suite.Check(failure.domain == domain && failure.code == code, "Wrong typed import failure domain or code");
    suite.Check(offset == Absent || failure.offset == offset, "Wrong exact raw/state failure offset");
    suite.Check(unchanged(output), "Failure replaced the last output sentinel with a partial result");
    ++suite.atomicFailures;
}
template<class Function>
void RejectPregame(Suite& suite, Function function, Domain domain, int code, std::size_t offset = Absent) {
    Reject(suite, PregameSentinel(), function, IsPregameSentinel, domain, code, offset);
}
template<class Function>
void RejectSections(Suite& suite, Function function, Domain domain, int code, std::size_t offset = Absent) {
    Reject(suite, SectionSentinel(), function, IsSectionSentinel, domain, code, offset);
}
template<class A, class B> bool SpanEqual(const A& a, const B& b) {
    return a.offset == b.offset && a.bytes == b.bytes;
}
template<class Span> bool Inside(const Span& span, std::size_t size) {
    return span.offset <= size && span.bytes <= size - span.offset;
}
RetailSavePreparedPregame Golden(Suite& suite, const Fixture& fixture) {
    const auto before = fixture.raw;
    auto value = RetailSavePregameImport::Prepare(fixture.raw.data(), fixture.raw.size());
    const auto& wire = value.wire;
    suite.Check(wire.metadata.consumedPrefixBytes == 57u && wire.playerInfo.offset == 57u && wire.playerInfo.bytes == 52u &&
        wire.slotHints.offset == 109u && wire.slotHints.bytes == 48u && wire.archive.offset == 157u &&
        wire.archive.bytes == fixture.wholeEnd - 157u && wire.whole.offset == 109u && wire.whole.bytes == fixture.wholeEnd - 109u,
        "Independent raw Pregame transcript boundaries differ");
    const Bytes expected(fixture.raw.begin() + 109, fixture.raw.begin() + static_cast<std::ptrdiff_t>(fixture.wholeEnd));
    suite.Check(value.bytes == expected && fixture.raw == before && value.canonicalBooleansChecked &&
        !value.rulesetCompatibilityVerified && !value.restoreApproved,
        "Pregame ownership, exact bytes, immutable source or false approvals differ");
    suite.Check(wire.slotHintsVersion == 3u && wire.archiveVersion == 6u && wire.worldInfoVersion == fixture.worldVersion &&
        wire.metadata.currentTurn == 42u && wire.activePlayer == 0 && wire.gameTurn == 42 && wire.gameType == 0 &&
        wire.arrayRecords == 93u && wire.booleanBytesChecked == 44u && wire.networkIdCount == 64u &&
        wire.networkIds.offset == 451u && wire.networkIds.bytes == 256u &&
        wire.maximumOptionNameBytes == fixture.maximumName && wire.optionNameHasEmbeddedNull == fixture.embeddedNull,
        "Typed identity, signed enum, shared records, boolean count or option observations differ");
    for (std::size_t i = 0; i < ScalarOffsets.size(); ++i) {
        const auto& site = wire.scalarBooleans[i];
        suite.Check(site.field && std::strcmp(site.field, ScalarNames[i]) == 0 && site.rawOffset == ScalarOffsets[i] &&
            site.value == (fixture.raw[ScalarOffsets[i]] == 1u), "Scalar bool name, fixed raw offset or value differs");
    }
    for (std::size_t i = 0; i < fixture.arrays.size(); ++i) {
        const auto& site = wire.booleanArrays[i];
        const auto at = fixture.arrays[i];
        const auto trueCount = static_cast<std::size_t>(fixture.raw[at]) + fixture.raw[at + 1u] + fixture.raw[at + 2u];
        suite.Check(site.field && std::strcmp(site.field, ArrayNames[i]) == 0 && site.payload.offset == at &&
            site.payload.bytes == 3u && site.count == 3u && site.trueCount == trueCount,
            "Bool-vector name, payload excluding count, count or true count differs");
    }
    suite.Check(value.bytes[60] == 68u && value.bytes[73] == 68u &&
        value.bytes[fixture.gameName + fixture.gameLength - 109u] == 68u &&
        value.bytes[fixture.mapName + fixture.mapLength - 109u] == 68u,
        "A known int32 byte was treated as a boolean or changed");
    ++suite.syntheticCases;
    return value;
}
void LiteralCases(Suite& suite) {
    for (const std::uint32_t world : {1u,2u}) {
        const auto fixture = Literal(world);
        const auto value = Golden(suite, fixture);
        suite.Check(fixture.raw.size() == (world == 1u ? 1060u : 1064u) &&
            value.bytes.size() == (world == 1u ? 943u : 947u), "Independent world-v1/v2 literal sizes differ");
        for (std::size_t cut = 0; cut < fixture.wholeEnd; ++cut) {
            if (cut < 57u) RejectPregame(suite, [&] {
                return RetailSavePregameImport::Prepare(fixture.raw.data(), cut);
            }, Domain::Metadata, static_cast<int>(RetailSaveHeaderErrorCode::Truncated));
            else RejectPregame(suite, [&] {
                return RetailSavePregameImport::Prepare(fixture.raw.data(), cut);
            }, Domain::Pregame, static_cast<int>(RetailSavePregameErrorCode::Truncated));
            ++suite.truncations;
        }
        for (std::size_t cut = fixture.wholeEnd; cut <= fixture.raw.size(); ++cut) {
            const auto shortValue = RetailSavePregameImport::Prepare(fixture.raw.data(), cut);
            suite.Check(shortValue.bytes == value.bytes && SpanEqual(shortValue.wire.whole, value.wire.whole),
                "Pregame incorrectly required a compression descriptor or lost its archive-end boundary");
        }
        auto descriptor = fixture.raw; descriptor[fixture.wholeEnd] = 255; descriptor.back() = 255;
        suite.Check(RetailSavePregameImport::Prepare(descriptor.data(), descriptor.size()).bytes == value.bytes,
            "Typed Pregame inspected unrelated compression bytes");
    }
    for (const unsigned char flag : {static_cast<unsigned char>(0),static_cast<unsigned char>(1)}) {
        auto fixture = Literal(1);
        for (const auto at : ScalarOffsets) fixture.raw[at] = flag;
        for (const auto at : fixture.arrays) std::fill(fixture.raw.begin() + static_cast<std::ptrdiff_t>(at),
            fixture.raw.begin() + static_cast<std::ptrdiff_t>(at + 3u), flag);
        Golden(suite, fixture);
    }
    auto mutableSource = Literal(2).raw;
    const auto owned = RetailSavePregameImport::Prepare(mutableSource.data(), mutableSource.size());
    const auto ownedBefore = owned.bytes;
    std::fill(mutableSource.begin(), mutableSource.end(), static_cast<unsigned char>(0xcc));
    suite.Check(owned.bytes == ownedBefore && owned.bytes.size() == 947u,
        "Prepared Pregame borrowed caller storage instead of owning its payload");
}

void BadPregame(Suite& suite, const Bytes& input, Domain domain, int code,
    std::size_t offset = Absent, const RetailSavePregameLimits& limits = RetailSavePregameLimits{}) {
    const auto before = input;
    RejectPregame(suite, [&] { return RetailSavePregameImport::Prepare(input.data(), input.size(), limits); },
        domain, code, offset);
    suite.Check(input == before, "Failed Pregame preparation changed its source bytes");
    ++suite.corruptions;
}
void DirectedPregame(Suite& suite) {
    using PG = RetailSavePregameErrorCode;
    using Header = RetailSaveHeaderErrorCode;
    const auto fixture = Literal(1);
    for (const auto at : ScalarOffsets) {
        for (const unsigned char flag : {static_cast<unsigned char>(2),static_cast<unsigned char>(255)}) {
            auto bad = fixture.raw; bad[at] = flag;
            BadPregame(suite, bad, Domain::Typed, static_cast<int>(RetailPregameImportErrorCode::InvalidBoolean), at);
        }
    }
    for (const auto at : fixture.arrays) {
        for (std::size_t i = 0; i < 3u; ++i) {
            auto bad = fixture.raw; bad[at + i] = 2;
            BadPregame(suite, bad, Domain::Typed, static_cast<int>(RetailPregameImportErrorCode::InvalidBoolean), at + i);
        }
    }
    struct VersionCase { std::size_t at; std::uint32_t value; Domain domain; int code; };
    const std::array<VersionCase, 7> versions = {{
        {4,9,Domain::Metadata,static_cast<int>(Header::UnsupportedVersion)},
        {109,2,Domain::Pregame,static_cast<int>(PG::UnsupportedSlotHintsVersion)},
        {109,4,Domain::Pregame,static_cast<int>(PG::UnsupportedSlotHintsVersion)},
        {157,5,Domain::Pregame,static_cast<int>(PG::UnsupportedPregameVersion)},
        {157,7,Domain::Pregame,static_cast<int>(PG::UnsupportedPregameVersion)},
        {888,0,Domain::Pregame,static_cast<int>(PG::UnsupportedWorldInfoVersion)},
        {888,3,Domain::Pregame,static_cast<int>(PG::UnsupportedWorldInfoVersion)}
    }};
    for (const auto& item : versions) {
        auto bad = fixture.raw; Put(bad, item.at, item.value);
        BadPregame(suite, bad, item.domain, item.code);
    }
    for (const std::size_t countAt : {350u,447u}) {
        auto bad = fixture.raw; Put(bad, countAt, 0xffffffffu);
        BadPregame(suite, bad, Domain::Pregame, static_cast<int>(PG::RecordLimit));
    }
    auto exact = RetailSavePregameLimits{};
    exact.metadata.maximumHeaderBytes = 57; exact.maximumPrefixBytes = fixture.wholeEnd;
    exact.maximumStringBytes = 1; exact.maximumArrayRecords = 64; exact.maximumTotalArrayRecords = 93;
    suite.Check(RetailSavePregameImport::Prepare(fixture.raw.data(), fixture.raw.size(), exact).bytes.size() == 943u,
        "Exact independent Pregame byte, string and record budgets failed");
    auto limited = exact; --limited.maximumPrefixBytes;
    BadPregame(suite, fixture.raw, Domain::Pregame, static_cast<int>(PG::PrefixLimit), Absent, limited);
    limited = exact; limited.maximumStringBytes = 0;
    BadPregame(suite, fixture.raw, Domain::Pregame, static_cast<int>(PG::StringLimit), Absent, limited);
    limited = exact; limited.maximumArrayRecords = 63;
    BadPregame(suite, fixture.raw, Domain::Pregame, static_cast<int>(PG::RecordLimit), Absent, limited);
    limited = exact; limited.maximumTotalArrayRecords = 92;
    BadPregame(suite, fixture.raw, Domain::Pregame, static_cast<int>(PG::RecordLimit), Absent, limited);
    limited = exact; limited.metadata.maximumHeaderBytes = 56;
    BadPregame(suite, fixture.raw, Domain::Metadata, static_cast<int>(Header::HeaderLimit), Absent, limited);
    RejectPregame(suite, [&] { return RetailSavePregameImport::Prepare(nullptr, 1); },
        Domain::Metadata, static_cast<int>(Header::NullInput));

    const std::array<unsigned char, 4> enumBytes = {{0,127,128,255}};
    const std::array<std::int32_t, 4> enumValues = {{0,127,-128,-1}};
    for (std::size_t i = 0; i < enumBytes.size(); ++i) {
        auto raw = fixture.raw; raw[374] = enumBytes[i]; const auto before = raw;
        const auto value = RetailSavePregameImport::Prepare(raw.data(), raw.size());
        suite.Check(value.wire.gameType == enumValues[i] && value.bytes[265] == enumBytes[i] && raw == before,
            "GameTypes is not the original signed one-byte enum or was rewritten");
        ++suite.syntheticCases;
    }
}
void OfflineGates(Suite& suite) {
    const auto fixture = Literal(1);
    Options options; const auto profile = BodyProfile(options);
    constexpr auto InvalidLayout = static_cast<int>(RetailPregameImportErrorCode::InvalidLayout);
    auto reject = [&](const Bytes& raw) {
        const auto before = raw;
        const auto typed = RetailSavePregameImport::Prepare(raw.data(), raw.size());
        suite.Check(typed.canonicalBooleansChecked && raw == before,
            "A candidate gate was incorrectly conflated with typed framing");
        RejectSections(suite, [&] { return RetailSaveImportSections::Prepare(raw.data(), raw.size(), nullptr, 0,
            profile, RetailBodyBooleanImportPolicy::RequireCanonical); }, Domain::Typed, InvalidLayout, 157);
        suite.Check(raw == before, "Candidate rejection changed raw bytes");
        ++suite.corruptions;
    };
    for (const auto active : {0xffffffffu,64u}) {
        auto raw = fixture.raw; Put(raw, 161, active); reject(raw);
    }
    { auto raw = fixture.raw; Put(raw, 370, 0xffffffffu); reject(raw); }
    {
        auto raw = fixture.raw; Put(raw, 16, 43); const auto before = raw;
        const auto typed = RetailSavePregameImport::Prepare(raw.data(), raw.size());
        RetailImportSectionsDetail::RequireOfflinePregame(typed);
        suite.Check(typed.wire.metadata.currentTurn == 43u && typed.wire.gameTurn == 42,
            "The retail preview turn displaced the source-authoritative Pregame turn");
        RejectSections(suite, [&] { return RetailSaveImportSections::Prepare(raw.data(), raw.size(), nullptr, 0,
            profile, RetailBodyBooleanImportPolicy::RequireCanonical); }, Domain::State,
            static_cast<int>(RetailStateErrorCode::Truncated), 0);
        suite.Check(raw == before, "Preview-turn mismatch control changed its raw input"); ++suite.corruptions;
    }
    for (const unsigned char type : {static_cast<unsigned char>(1),static_cast<unsigned char>(255)}) {
        auto raw = fixture.raw; raw[374] = type; reject(raw);
    }
    {
        auto raw = fixture.raw;
        raw.erase(raw.begin() + 703, raw.begin() + 707); Put(raw, 447, 63);
        const auto typed = RetailSavePregameImport::Prepare(raw.data(), raw.size());
        suite.Check(typed.wire.networkIdCount == 63u && typed.wire.networkIds.bytes == 252u,
            "Independent 63-element network-ID transcript did not remain typed-framed");
        reject(raw);
    }
    for (const auto active : {0u,63u}) {
        auto raw = fixture.raw; Put(raw, 161, active);
        const auto typed = RetailSavePregameImport::Prepare(raw.data(), raw.size());
        RetailImportSectionsDetail::RequireOfflinePregame(typed);
        suite.Check(typed.wire.activePlayer == static_cast<std::int32_t>(active), "Valid active-player endpoint changed");
    }
    {
        auto raw = fixture.raw; Put(raw, 451u + 7u * 4u, 68);
        const auto before = raw;
        const auto typed = RetailSavePregameImport::Prepare(raw.data(), raw.size());
        RetailImportSectionsDetail::RequireOfflinePregame(typed);
        suite.Check(!RetailImportSectionsDetail::UnassignedNetworkIds(raw.data(), raw.size(), typed.wire) && raw == before &&
            typed.bytes[370] == 68u, "Existing transport IDs were assumed unassigned or rewritten");
    }
    const auto valid = RetailSavePregameImport::Prepare(fixture.raw.data(), fixture.raw.size());
    suite.Check(RetailImportSectionsDetail::UnassignedNetworkIds(fixture.raw.data(), fixture.raw.size(), valid.wire),
        "Independent 64 int32 -1 transport-ID observation differs");
    {
        auto observation = valid; observation.canonicalBooleansChecked = false;
        const auto failure = FailureOf([&] { RetailImportSectionsDetail::RequireOfflinePregame(observation); });
        suite.Check(failure.domain == Domain::Typed && failure.code == InvalidLayout && failure.offset == 157u,
            "Unverified typed booleans were admitted by the candidate gate");
    }
    auto badLayout = profile; badLayout.layout = static_cast<RetailBodyLayout>(99);
    RejectSections(suite, [&] { return RetailSaveImportSections::Prepare(fixture.raw.data(), fixture.raw.size(), nullptr, 0,
        badLayout, RetailBodyBooleanImportPolicy::RequireCanonical); }, Domain::State,
        static_cast<int>(RetailStateErrorCode::UnsupportedProfile), 0);
    RejectSections(suite, [&] { return RetailSaveImportSections::Prepare(fixture.raw.data(), fixture.raw.size(), nullptr, 0,
        profile, static_cast<RetailBodyBooleanImportPolicy>(99)); }, Domain::State,
        static_cast<int>(RetailStateErrorCode::UnsupportedProfile), 0);
    auto rawOutput = RetailSaveStateLimits{}; rawOutput.booleanWireProfile = RetailBooleanWireProfile::SdkRawByte;
    RejectSections(suite, [&] { return RetailSaveImportSections::Prepare(fixture.raw.data(), fixture.raw.size(), nullptr, 0,
        profile, RetailBodyBooleanImportPolicy::RequireCanonical, rawOutput); }, Domain::State,
        static_cast<int>(RetailStateErrorCode::UnsupportedProfile), 0);
}
void OptionCases(Suite& suite) {
    const std::array<std::string, 3> names = {{std::string(63, 'X'),std::string(64, 'X'),std::string("A\0B",3)}};
    Options options; const auto profile = BodyProfile(options);
    for (unsigned position = 0; position < 2u; ++position) {
        for (std::size_t i = 0; i < names.size(); ++i) {
            const auto fixture = position == 0u ? Literal(1, names[i], "B") : Literal(2, "A", names[i]);
            const auto typed = Golden(suite, fixture);
            if (i == 0u) {
                RetailImportSectionsDetail::RequireOfflinePregame(typed);
                suite.Check(typed.wire.maximumOptionNameBytes == 63u && !typed.wire.optionNameHasEmbeddedNull,
                    "A 63-byte native-representable option name was rejected");
            } else {
                RejectSections(suite, [&] { return RetailSaveImportSections::Prepare(fixture.raw.data(), fixture.raw.size(),
                    nullptr, 0, profile, RetailBodyBooleanImportPolicy::RequireCanonical); }, Domain::Typed,
                    static_cast<int>(RetailPregameImportErrorCode::InvalidLayout), 157);
                ++suite.corruptions;
            }
            ++suite.optionsCases;
        }
    }
}
void ElapsedCases(Suite& suite) {
    // Nonzero start; +4 is 68 and +8 is 123. Suffix is outside the Game view.
    const Bytes literal = {166,255,0, 1,0,0,0, 68,0,0,0, 123,0,0,0, 68,255,0};
    const auto before = literal;
    RetailSaveStateLimits limits;
    limits.maxInputBytes = literal.size(); limits.maxPrefixBytes = 15; limits.maxTotalRecords = 0;
    suite.Check(RetailImportSectionsDetail::ReadElapsed(literal.data(), literal.size(), {3,12}, limits) == 123 &&
        literal == before, "Elapsed was read from Game+4, outside its span, or changed bytes");
    ++suite.elapsedCases;
    for (const auto value : {0u,0x7fffffffu}) {
        auto raw = literal; Put(raw, 11, value);
        suite.Check(RetailImportSectionsDetail::ReadElapsed(raw.data(), raw.size(), {3,12}, limits) ==
            static_cast<std::int32_t>(value), "Elapsed nonnegative endpoint was not preserved");
        ++suite.elapsedCases;
    }
    auto reject = [&](const Bytes& raw, std::size_t size, RetailInflatedSpan span,
        RetailStateErrorCode code, std::size_t offset, const RetailSaveStateLimits& bounds) {
        const auto inputBefore = raw;
        Reject(suite, std::int32_t(-701), [&] { return RetailImportSectionsDetail::ReadElapsed(raw.data(), size, span, bounds); },
            [](std::int32_t value) { return value == -701; }, Domain::State, static_cast<int>(code), offset);
        suite.Check(raw == inputBefore, "Failed elapsed read changed its source"); ++suite.elapsedCases;
    };
    { auto raw = literal; Put(raw, 11, 0xffffffffu); reject(raw, raw.size(), {3,12}, RetailStateErrorCode::InvalidValue, 15, limits); }
    for (const auto version : {0u,2u}) {
        auto raw = literal; Put(raw, 3, version);
        reject(raw, raw.size(), {3,12}, RetailStateErrorCode::UnsupportedVersion, 7, limits);
    }
    for (std::size_t bytes = 0; bytes < 12u; ++bytes) {
        reject(literal, 3u + bytes, {3,bytes}, RetailStateErrorCode::InvalidValue, 0, limits);
        ++suite.truncations;
    }
    reject(literal, literal.size(), {19,12}, RetailStateErrorCode::InvalidValue, 0, limits);
    reject(literal, literal.size(), {3,Absent}, RetailStateErrorCode::InvalidValue, 0, limits);
    auto narrow = limits; --narrow.maxInputBytes;
    reject(literal, literal.size(), {3,12}, RetailStateErrorCode::InputLimit, 0, narrow);
    narrow = limits; narrow.maxPrefixBytes = 14;
    reject(literal, literal.size(), {3,12}, RetailStateErrorCode::PrefixLimit, 11, narrow);
    narrow = limits; narrow.booleanWireProfile = static_cast<RetailBooleanWireProfile>(99);
    reject(literal, literal.size(), {3,12}, RetailStateErrorCode::UnsupportedProfile, 0, narrow);
}
void SelfTest(Suite& suite) {
    LiteralCases(suite); DirectedPregame(suite); OfflineGates(suite); OptionCases(suite); ElapsedCases(suite);
}

void ReadExact(Bytes& bytes) {
    std::cin.read(reinterpret_cast<char*>(bytes.data()), static_cast<std::streamsize>(bytes.size()));
    if (std::cin.gcount() != static_cast<std::streamsize>(bytes.size()))
        throw std::runtime_error("Stdin ended before its declared raw/body boundary");
}
bool Eligible(const RetailSavePreparedPregame& pregame) {
    const auto& wire = pregame.wire;
    return pregame.canonicalBooleansChecked && wire.activePlayer >= 0 && wire.activePlayer < 64 &&
        wire.gameTurn >= 0 && wire.gameType == 0 && wire.networkIdCount == 64u &&
        wire.maximumOptionNameBytes <= 63u && !wire.optionNameHasEmbeddedNull;
}
void PublicPregame(Suite& suite, const Bytes& raw, const RetailSavePreparedPregame& prepared) {
    const auto& wire = prepared.wire;
    suite.Check(Inside(wire.whole, raw.size()) && wire.whole.bytes &&
        wire.whole.offset == wire.slotHints.offset && Inside(wire.archive, raw.size()) &&
        wire.whole.offset + wire.whole.bytes == wire.archive.offset + wire.archive.bytes &&
        prepared.bytes.size() == wire.whole.bytes &&
        std::equal(prepared.bytes.begin(), prepared.bytes.end(), raw.begin() + static_cast<std::ptrdiff_t>(wire.whole.offset)),
        "Public Pregame is not an exact owned slot-hints-through-archive payload");
    suite.Check(prepared.canonicalBooleansChecked && !prepared.rulesetCompatibilityVerified && !prepared.restoreApproved &&
        wire.slotHintsVersion == 3u && wire.archiveVersion == 6u &&
        (wire.worldInfoVersion == 1u || wire.worldInfoVersion == 2u),
        "Public typed Pregame framing or false approvals differ");
    std::size_t booleanBytes = 17;
    for (std::size_t i = 0; i < wire.scalarBooleans.size(); ++i) {
        const auto& site = wire.scalarBooleans[i];
        suite.Check(site.field && std::strcmp(site.field, ScalarNames[i]) == 0 && site.rawOffset < raw.size() &&
            raw[site.rawOffset] <= 1u && site.value == (raw[site.rawOffset] == 1u),
            "Public scalar bool observation does not match its original raw byte");
    }
    for (std::size_t i = 0; i < wire.booleanArrays.size(); ++i) {
        const auto& array = wire.booleanArrays[i];
        suite.Check(array.field && std::strcmp(array.field, ArrayNames[i]) == 0 && Inside(array.payload, raw.size()) &&
            array.payload.bytes == array.count, "Public bool-vector owner, field or payload width differs");
        std::size_t trueCount = 0;
        for (std::size_t j = 0; j < array.count; ++j) {
            const auto value = raw[array.payload.offset + j];
            if (value > 1u) throw std::runtime_error("Typed public bool vector contains a noncanonical byte");
            trueCount += value;
        }
        suite.Check(trueCount == array.trueCount, "Public bool-vector true count differs from original payload");
        booleanBytes += array.count;
    }
    suite.Check(booleanBytes == wire.booleanBytesChecked && Inside(wire.networkIds, raw.size()) &&
        wire.networkIds.bytes == static_cast<std::size_t>(wire.networkIdCount) * 4u &&
        wire.gameType >= -128 && wire.gameType <= 127,
        "Public boolean-byte total, transport width or signed enum observation differs");
}
void PublicBody(Suite& suite, const Bytes& original, const RetailSavePreparedBody& body) {
    suite.Check(body.bytes.size() == original.size() && body.canonicalWireFramed &&
        body.wire.nextInflatedOffset == original.size() && !body.producerContractVerified &&
        !body.rulesetCompatibilityVerified && !body.completeSaveVerified && !body.restoreApproved,
        "Public body did not produce a complete owned wire frame with false approvals");
    std::size_t editIndex = 0; bool exact = true;
    for (std::size_t i = 0; i < original.size(); ++i) {
        auto expected = original[i];
        if (editIndex < body.edits.size() && body.edits[editIndex].offset == i) {
            const auto& edit = body.edits[editIndex++];
            if (edit.before != original[i] || edit.before <= 1u || edit.after != 1u || edit.playerSlot >= 64u ||
                edit.operationIndex >= body.wire.players[edit.playerSlot].operationCount) exact = false;
            expected = edit.after;
        }
        if (body.bytes[i] != expected) exact = false;
    }
    suite.Check(exact && editIndex == body.edits.size(),
        "Public candidate changed a byte outside its exact ordered permitted edit list");
}
void SectionShape(Suite& suite, const RetailSaveImportPreparation& prepared) {
    using Storage = RetailImportStorage;
    suite.Check(prepared.sections.size() == 132u && !prepared.compressedBodyAssociationVerified &&
        !prepared.bundleIdentityVerified && !prepared.rulesetCompatibilityVerified && !prepared.producerContractVerified &&
        !prepared.completeSaveVerified && !prepared.nativeRestoreApproved,
        "Section preparation approved an unverified association, bundle, ruleset or restore");
    std::vector<RetailInflatedSpan> bodySpans;
    std::size_t total = 0;
    for (std::size_t i = 0; i < prepared.sections.size(); ++i) {
        const auto& section = prepared.sections[i];
        const unsigned kind = i < 4u ? static_cast<unsigned>(i + 2u) : i < 68u ? 6u : 7u;
        const unsigned index = i < 4u ? 0u : static_cast<unsigned>(i < 68u ? i - 4u : i - 68u);
        const auto storage = i == 0u ? Storage::Pregame : Storage::Body;
        const auto& owner = storage == Storage::Pregame ? prepared.pregame.bytes : prepared.body.bytes;
        suite.Check(section.kind == kind && section.index == index && section.storage == storage &&
            Inside(section.span, owner.size()) && section.span.bytes > 0u &&
            section.span.bytes <= static_cast<std::size_t>((std::numeric_limits<std::int32_t>::max)()),
            "A native candidate section has the wrong order, index, storage, nonempty size or bounds");
        RetailInflatedSpan expected;
        if (i == 0u) expected = {0,prepared.pregame.bytes.size()};
        else if (i == 1u) expected = prepared.body.wire.game;
        else if (i == 2u) expected = prepared.body.wire.map;
        else if (i == 3u) expected = prepared.body.wire.supporting;
        else if (i < 68u) expected = prepared.body.wire.teams[index].whole;
        else expected = prepared.body.wire.players[index].whole;
        suite.Check(SpanEqual(section.span, expected), "A section view differs from internally prepared source-order metadata");
        total += section.span.bytes;
        if (i) bodySpans.push_back(section.span);
    }
    std::sort(bodySpans.begin(), bodySpans.end(), [](RetailInflatedSpan a, RetailInflatedSpan b) { return a.offset < b.offset; });
    std::size_t cursor = 0;
    for (const auto& span : bodySpans) {
        suite.Check(span.offset == cursor, "Body section views overlap or leave an uncovered source byte");
        cursor += span.bytes;
    }
    suite.Check(cursor == prepared.body.bytes.size() && total == prepared.totalPayloadBytes &&
        total == prepared.pregame.bytes.size() + prepared.body.bytes.size(),
        "All 132 candidate payloads do not cover their two owned buffers exactly once");
    suite.Check(prepared.sections[3].span.offset > prepared.sections[4].span.offset &&
        prepared.sections[3].span.offset + prepared.sections[3].span.bytes == prepared.body.bytes.size(),
        "Physically last Supporting was not presented before Teams in candidate section order");
}
struct PublicObservation {
    bool readComplete = false, observed = false, eligible = false, accepted = false;
    bool rejectionAtomicity = false, syntheticControlVerified = false;
    std::size_t rawBytes = 0, bodyBytes = 0;
    Failure rejection;
    std::string rejectionMessage;
    RetailSaveImportPreparation result;
};
void PublicTest(Suite& suite, const Options& options, PublicObservation& observation, const char*& phase) {
    phase = "public_stdin";
#ifdef _WIN32
    if (_setmode(_fileno(stdin), _O_BINARY) == -1) throw std::runtime_error("Cannot select binary stdin");
#endif
    const Bytes raw = [&] { Bytes bytes(options.rawSize); ReadExact(bytes); return bytes; }();
    const Bytes body = [&] { Bytes bytes(options.bodySize); ReadExact(bytes); return bytes; }();
    if (std::cin.peek() != std::char_traits<char>::eof() || std::cin.bad())
        throw std::runtime_error("Stdin extends beyond its two declared input sizes or failed");
    observation.readComplete = true; observation.rawBytes = raw.size(); observation.bodyBytes = body.size();
    const auto rawBefore = raw; const auto bodyBefore = body;
    const auto profile = BodyProfile(options);
    auto limits = RetailSaveStateLimits{};
    limits.maxInputBytes = body.size(); limits.maxTotalRecords = options.recordBudget;
    constexpr auto Policy = RetailBodyBooleanImportPolicy::OperationReinforcementNonzeroTruth;
    phase = "public_typed_pregame";
    auto pregame = RetailSavePregameImport::Prepare(raw.data(), raw.size());
    PublicPregame(suite, raw, pregame);
    const bool eligible = Eligible(pregame);
    phase = "public_owned_body";
    auto preparedBody = RetailSaveBodyImport::Prepare(body.data(), body.size(), profile, Policy, limits);
    PublicBody(suite, body, preparedBody);
    const auto elapsed = RetailImportSectionsDetail::ReadElapsed(preparedBody.bytes.data(), preparedBody.bytes.size(),
        preparedBody.wire.game, limits);
    bool unassigned = pregame.wire.networkIdCount == 64u;
    for (std::size_t i = 0; i < pregame.wire.networkIds.bytes; ++i)
        if (raw[pregame.wire.networkIds.offset + i] != 255u) unassigned = false;
    phase = "public_candidate_gate";
    RetailSaveImportPreparation candidate = SectionSentinel();
    Failure rejection; std::string rejectionMessage;
    try { candidate = RetailSaveImportSections::Prepare(raw.data(), raw.size(), body.data(), body.size(), profile, Policy, limits); }
    catch (const RetailPregameImportError& error) {
        rejection = {Domain::Typed,static_cast<int>(error.Code()),error.RawOffset()}; rejectionMessage = error.what();
    }
    if (eligible) {
        suite.Check(rejection.domain == Domain::None, "A source-eligible public input was rejected as a candidate");
        SectionShape(suite, candidate);
        suite.Check(candidate.turn == pregame.wire.gameTurn && candidate.turn >= 0 &&
            candidate.retailHeaderTurnMatches == (pregame.wire.gameTurn >= 0 &&
                pregame.wire.metadata.currentTurn == static_cast<std::uint32_t>(pregame.wire.gameTurn)) &&
            candidate.activePlayer == pregame.wire.activePlayer && candidate.elapsed == elapsed &&
            candidate.offlineTransportUnassigned == unassigned && candidate.pregame.bytes == pregame.bytes &&
            candidate.body.bytes == preparedBody.bytes && RetailBodyImportDetail::SameWire(candidate.body.wire, preparedBody.wire),
            "Actual full section preparation differs from independently prepared metadata or owned payloads");
    } else {
        suite.Check(rejection.domain == Domain::Typed && rejection.code ==
            static_cast<int>(RetailPregameImportErrorCode::InvalidLayout) && rejection.offset == pregame.wire.archive.offset &&
            !rejectionMessage.empty() && IsSectionSentinel(candidate),
            "Ineligible public input did not reject with exact metadata failure and untouched last output");
        ++suite.atomicFailures;
        candidate = RetailSaveImportPreparation{};
        candidate.turn = pregame.wire.gameTurn; candidate.activePlayer = pregame.wire.activePlayer; candidate.elapsed = elapsed;
        candidate.retailHeaderTurnMatches = pregame.wire.gameTurn >= 0 &&
            pregame.wire.metadata.currentTurn == static_cast<std::uint32_t>(pregame.wire.gameTurn);
        candidate.offlineTransportUnassigned = unassigned;
        candidate.pregame = std::move(pregame); candidate.body = std::move(preparedBody);
    }
    phase = "public_failure_atomicity";
    {
        auto bad = raw; const auto at = candidate.pregame.wire.scalarBooleans[0].rawOffset; bad[at] = 2;
        const auto before = bad;
        RejectSections(suite, [&] { return RetailSaveImportSections::Prepare(bad.data(), bad.size(), body.data(), body.size(),
            profile, Policy, limits); }, Domain::Typed, static_cast<int>(RetailPregameImportErrorCode::InvalidBoolean), at);
        suite.Check(bad == before, "A failed public scalar-bool gate changed the raw input"); ++suite.corruptions;
    }
    {
        auto bad = raw; Put(bad, candidate.pregame.wire.archive.offset + 4u, 64);
        const auto before = bad;
        RejectSections(suite, [&] { return RetailSaveImportSections::Prepare(bad.data(), bad.size(), body.data(), body.size(),
            profile, Policy, limits); }, Domain::Typed, static_cast<int>(RetailPregameImportErrorCode::InvalidLayout),
            candidate.pregame.wire.archive.offset);
        suite.Check(bad == before, "A failed public active-player gate changed its source"); ++suite.corruptions;
    }
    if (eligible) {
        RejectSections(suite, [&] { return RetailSaveImportSections::Prepare(raw.data(), raw.size(), body.data(), body.size() - 1u,
            profile, Policy, limits); }, Domain::State, static_cast<int>(RetailStateErrorCode::Truncated));
        ++suite.truncations;
    }
    phase = "synthetic_pregame_public_body_control";
    {
        // Intentionally unpaired synthetic Pregame plus the actual body. This
        // exercises all 132 descriptors even if the real metadata is ineligible.
        // It establishes neither compressed-body association nor save identity.
        const auto fixture = Literal(1); const auto before = fixture.raw;
        const auto control = RetailSaveImportSections::Prepare(fixture.raw.data(), fixture.raw.size(), body.data(), body.size(),
            profile, Policy, limits);
        SectionShape(suite, control);
        const Bytes expectedPregame(fixture.raw.begin() + 109,
            fixture.raw.begin() + static_cast<std::ptrdiff_t>(fixture.wholeEnd));
        suite.Check(fixture.raw == before && control.pregame.bytes == expectedPregame &&
            control.body.bytes == candidate.body.bytes && RetailBodyImportDetail::SameWire(control.body.wire, candidate.body.wire) &&
            control.turn == 42 && control.activePlayer == 0 && control.elapsed == elapsed &&
            control.retailHeaderTurnMatches && control.offlineTransportUnassigned && control.pregame.canonicalBooleansChecked &&
            !control.pregame.rulesetCompatibilityVerified && !control.pregame.restoreApproved &&
            !control.body.restoreApproved && !control.body.rulesetCompatibilityVerified && !control.body.completeSaveVerified,
            "The explicitly unpaired synthetic Pregame/public-body control changed ownership, metadata or approvals");
        observation.syntheticControlVerified = true; ++suite.syntheticCases;
    }
    suite.Check(raw == rawBefore && body == bodyBefore, "Public candidate preparation or failure controls changed either original");
    observation.eligible = eligible; observation.accepted = eligible; observation.rejection = rejection;
    observation.rejectionMessage = std::move(rejectionMessage); observation.rejectionAtomicity = true;
    observation.result = std::move(candidate); observation.observed = true;
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
const char* DomainName(Domain domain) {
    switch (domain) {
    case Domain::Metadata: return "metadata";
    case Domain::Pregame: return "pregame";
    case Domain::Typed: return "pregame_import";
    case Domain::State: return "state";
    default: return "none";
    }
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
    bool passed, const char* phase, const std::string& error, Failure failure) {
    const char* mode = options.mode == Mode::SelfTest ? "self-test" : options.mode == Mode::Public ? "public" : "unselected";
    std::cout << "{\"schema\":\"zerosis.retail.import_sections_test.v1\",\"status\":\""
        << (passed ? "PASS_RETAIL_IMPORT_SECTIONS_COMPONENT" : "FAIL_RETAIL_IMPORT_SECTIONS_COMPONENT")
        << "\",\"mode\":\"" << mode << "\",\"phase\":\"" << phase << "\",\"checks\":" << suite.checks
        << ",\"synthetic_pregame_cases\":" << suite.syntheticCases << ",\"truncations\":" << suite.truncations
        << ",\"directed_corruptions\":" << suite.corruptions << ",\"atomic_failure_cases\":" << suite.atomicFailures
        << ",\"elapsed_cases\":" << suite.elapsedCases << ",\"options_cases\":" << suite.optionsCases
        << ",\"all_failure_outputs_unchanged\":" << Boolean(passed)
        << ",\"input_bytes_unchanged\":" << Boolean(passed) << ",\"input_files_unchanged\":true"
        << ",\"stdin_read_complete\":" << Boolean(observation.readComplete)
        << ",\"gamecore_loaded\":false,\"window_created\":false,\"game_accessed\":false,\"user_saves_accessed\":false"
        << ",\"complete_player_validated\":false,\"complete_save_validated\":false,\"complete_save_verified\":false"
        << ",\"ruleset_compatibility_verified\":false,\"restore_approved\":false,\"sdk_executed\":false"
        << ",\"producer_contract_verified\":false,\"full_engine_goal_complete\":false,\"native_restore_approved\":false"
        << ",\"compressed_body_association_verified\":false,\"bundle_identity_verified\":false,\"public\":";
    if (observation.observed) {
        const auto& result = observation.result; const auto& pregame = result.pregame; const auto& wire = pregame.wire;
        std::cout << "{\"raw_bytes\":" << observation.rawBytes << ",\"body_bytes\":" << observation.bodyBytes
            << ",\"awards\":" << options.awards << ",\"grand\":" << options.grand << ",\"projects\":" << options.projects
            << ",\"maximum_total_records\":" << options.recordBudget
            << ",\"eligible\":" << Boolean(observation.eligible) << ",\"accepted\":" << Boolean(observation.accepted)
            << ",\"rejection_atomicity_verified\":" << Boolean(observation.rejectionAtomicity)
            << ",\"section_count\":" << (observation.accepted ? result.sections.size() : 0u)
            << ",\"total_payload_bytes\":" << (observation.accepted ? result.totalPayloadBytes : 0u)
            << ",\"turn\":" << result.turn << ",\"header_turn\":" << wire.metadata.currentTurn
            << ",\"retail_header_turn_matches\":" << Boolean(result.retailHeaderTurnMatches)
            << ",\"elapsed\":" << result.elapsed << ",\"active_player\":" << result.activePlayer
            << ",\"game_type\":" << wire.gameType << ",\"outer_game_mode\":" << static_cast<unsigned>(wire.metadata.gameMode)
            << ",\"offline_transport_unassigned\":" << Boolean(result.offlineTransportUnassigned)
            << ",\"synthetic_pregame_public_body_control\":{\"verified\":" << Boolean(observation.syntheticControlVerified)
            << ",\"section_count\":132,\"actual_body_reused\":true,\"raw_bytes_unchanged\":true,\"intentionally_unpaired\":true"
            << ",\"compressed_body_association_verified\":false,\"native_restore_approved\":false,\"restore_approved\":false}"
            << ",\"pregame\":{\"raw_offset\":" << wire.whole.offset << ",\"bytes\":" << wire.whole.bytes
            << ",\"raw_end\":" << wire.whole.offset + wire.whole.bytes << ",\"archive_raw_offset\":" << wire.archive.offset
            << ",\"scalar_boolean_count\":" << wire.scalarBooleans.size() << ",\"boolean_array_count\":" << wire.booleanArrays.size()
            << ",\"boolean_bytes_checked\":" << wire.booleanBytesChecked << ",\"network_id_count\":" << wire.networkIdCount
            << ",\"maximum_option_name_bytes\":" << wire.maximumOptionNameBytes
            << ",\"option_name_has_embedded_null\":" << Boolean(wire.optionNameHasEmbeddedNull)
            << ",\"canonical_booleans_checked\":" << Boolean(pregame.canonicalBooleansChecked)
            << "},\"rejection\":";
        if (observation.accepted) std::cout << "null";
        else {
            std::cout << "{\"domain\":\"" << DomainName(observation.rejection.domain) << "\",\"code\":"
                << observation.rejection.code << ",\"raw_offset\":" << observation.rejection.offset << ",\"message\":";
            Text(observation.rejectionMessage); std::cout << '}';
        }
        std::cout << ",\"sections\":[";
        if (observation.accepted) for (std::size_t i = 0; i < result.sections.size(); ++i) {
            const auto& section = result.sections[i]; if (i) std::cout << ',';
            std::cout << "{\"kind\":" << section.kind << ",\"index\":" << section.index << ",\"storage\":\""
                << (section.storage == RetailImportStorage::Pregame ? "pregame" : "body")
                << "\",\"offset\":" << section.span.offset << ",\"bytes\":" << section.span.bytes << '}';
        }
        std::cout << "],\"wire\":"; PrintWire(result.body.wire, observation.bodyBytes); std::cout << '}';
    } else std::cout << "null";
    std::cout << ",\"error_domain\":\"" << DomainName(failure.domain) << "\",\"error_code\":";
    if (failure.code >= 0) std::cout << failure.code; else std::cout << "null";
    std::cout << ",\"error_offset\":";
    if (failure.offset != Absent) std::cout << failure.offset; else std::cout << "null";
    std::cout << ",\"error\":"; Text(error); std::cout << "}\n";
}
} // namespace

int main(int argc, char** argv) {
    static_assert(sizeof(void*) == 8, "Import-section tests require x64");
    static_assert(sizeof(std::uint32_t) == 4 && sizeof(std::int32_t) == 4 &&
        std::numeric_limits<unsigned char>::digits == 8, "Literal tests require 32-bit words and 8-bit bytes");
    Suite suite; Options options; PublicObservation observation;
    const char* phase = "arguments"; bool passed = false;
    std::string error; Failure failure;
    try {
        options = Arguments(argc, argv);
        if (options.mode == Mode::SelfTest) { phase = "self-test"; SelfTest(suite); phase = "complete"; }
        else PublicTest(suite, options, observation, phase);
        passed = true;
    } catch (const RetailSaveHeaderError& caught) {
        failure = {Domain::Metadata,static_cast<int>(caught.Code()),Absent}; error = caught.what();
    } catch (const RetailSavePregameError& caught) {
        failure = {Domain::Pregame,static_cast<int>(caught.Code()),Absent}; error = caught.what();
    } catch (const RetailPregameImportError& caught) {
        failure = {Domain::Typed,static_cast<int>(caught.Code()),caught.RawOffset()}; error = caught.what();
    } catch (const RetailStateError& caught) {
        failure = {Domain::State,static_cast<int>(caught.Code()),caught.Offset()}; error = caught.what();
    } catch (const std::exception& caught) { error = caught.what(); }
    catch (...) { error = "Unexpected non-standard import-section test exception"; }
    Print(suite, options, observation, passed, phase, error, failure);
    return passed ? 0 : 1;
}
