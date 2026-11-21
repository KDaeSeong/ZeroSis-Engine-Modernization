#include "../Source/Host/RetailSaveState.h"
#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <exception>
#include <iostream>
#include <limits>
#include <map>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>
#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif

// Independent wire writer, grounded in the retained Expansion2 SDK serializers:
// CvGame.cpp:9471-9603; CvStructs.cpp; CvRandom.cpp; CvReplayMessage.cpp;
// FFreeListTrashArray.h:572-631; CvDealClasses.cpp; CvReligionClasses.cpp;
// CvBeliefClasses.cpp; CvCultureClasses.cpp; CvVotingClasses.cpp;
// CvTradeClasses.cpp; and CvMap.cpp:1424-1447. No SDK is linked or called.
// Synthetic records exercise structural framing, not meaningful game rules.
namespace {
using namespace ZeroSisHost;
using Bytes = std::vector<unsigned char>;
using Code = RetailStateErrorCode;

struct Suite {
    std::uint64_t checks = 0, truncations = 0, mutations = 0;
    std::uint64_t accepted = 0, rejected = 0, syntheticCases = 0;
    void Check(bool condition, const std::string& message) {
        ++checks;
        if (!condition) throw std::runtime_error(message);
    }
};

struct Mark { std::string name; std::size_t at; };
struct Fixture {
    Bytes bytes;
    std::uint32_t awards = 0;
    bool rich = false;
    std::size_t gameEnd = 0, databaseStart = 0, databaseBytes = 0;
    std::size_t mapStart = 0, next = 0, records = 0;
    std::size_t maxArray = 0, maxString = 0;
    std::vector<Mark> versions, bools, signedCounts;
    std::map<std::string, std::size_t> marks;
};

class Wire {
public:
    Fixture f;
    Wire(std::uint32_t awards, bool rich) { f.awards = awards; f.rich = rich; }
    std::size_t Pos() const { return f.bytes.size(); }
    void MarkAt(const std::string& name) { f.marks[name] = Pos(); }
    void U8(unsigned char value) { f.bytes.push_back(value); }
    void U16(std::uint16_t value) { U8(static_cast<unsigned char>(value)); U8(static_cast<unsigned char>(value >> 8)); }
    void U32(std::uint32_t value) {
        for (unsigned int shift = 0; shift != 32; shift += 8) U8(static_cast<unsigned char>(value >> shift));
    }
    void I32(std::int32_t value) { U32(static_cast<std::uint32_t>(value)); }
    void Words(std::size_t count, std::uint32_t seed = 0x10203040u) {
        for (std::size_t i = 0; i < count; ++i) U32(seed + static_cast<std::uint32_t>(i));
    }
    void Version(const std::string& name, std::uint32_t value) {
        f.versions.push_back({name, Pos()}); U32(value);
    }
    void Bool(const std::string& name, bool value = false) {
        f.bools.push_back({name, Pos()}); U8(value ? 1 : 0);
    }
    void Count(const std::string& name, std::uint32_t value, bool isSigned = false) {
        MarkAt(name);
        if (isSigned) f.signedCounts.push_back({name, Pos()});
        U32(value); f.records += value; f.maxArray = (std::max)(f.maxArray, static_cast<std::size_t>(value));
    }
    static std::string Text() {
        return std::string("A\0", 2) + u8"한글" + std::string("\x78\x9c", 2) + "SQLite format 3";
    }
    void String(const std::string& name, const std::string& value) {
        MarkAt(name); U32(static_cast<std::uint32_t>(value.size()));
        f.bytes.insert(f.bytes.end(), value.begin(), value.end());
        f.maxString = (std::max)(f.maxString, value.size());
    }
    void Strings(const std::string& name) {
        Count(name, f.rich ? 2u : 0u);
        if (f.rich) { String(name + ".text", Text()); String(name + ".empty", ""); }
    }
    void HashArray(const std::string& name, std::size_t words) {
        Count(name, f.rich ? 3u : 0u);
        if (!f.rich) return;
        U32(0); // NO_TYPE has no value, including for a two-dimensional row.
        U32(0x01020304u); Words(words, 0x01234567u);
        U32(0x789c0001u); Words(words, 0xfedcba98u);
    }
    void FixedName(const std::string& name) {
        MarkAt(name);
        // The SDK streams char[128] as fixed bytes, not a length or NUL scan.
        for (unsigned int i = 0; i < 128; ++i) U8(static_cast<unsigned char>(i == 3 ? 0 : 33 + i % 90));
    }
    void VoteOption(const std::string& name) { Words(4); String(name + ".text", Text()); }
    void VoteRecord(const std::string& name, bool selection, std::int32_t id) {
        Version(name, 1); MarkAt(name + ".id"); I32(id); I32(2);
        if (selection) {
            Count(name + ".options", 2);
            VoteOption(name + ".first"); VoteOption(name + ".second");
        } else VoteOption(name + ".option");
    }
    void FreeList(const std::string& name, bool selection) {
        Count(name + ".slots", f.rich ? 4u : 0u, true);
        MarkAt(name + ".last"); I32(f.rich ? 2 : -1);
        MarkAt(name + ".free_head"); I32(f.rich ? 1 : -1);
        MarkAt(name + ".free_count"); I32(f.rich ? 1 : 0);
        MarkAt(name + ".current_id"); I32(f.rich ? 24576 : 8192);
        if (f.rich) {
            for (unsigned int i = 0; i < 4; ++i) {
                MarkAt(name + ".link" + std::to_string(i)); I32(-1);
            }
        }
        Count(name + ".live", f.rich ? 2u : 0u, true);
        if (f.rich) {
            VoteRecord(name + ".record0", selection, 8192);
            VoteRecord(name + ".record2", selection, 16386);
        }
    }
    void Random(const std::string& name) {
        Version(name, 1); Words(3); MarkAt(name + ".debug"); Bool(name + ".debug");
    }
    void GameFront() {
        Version("game", 1);
        Words(29); // Includes signed years/sentinels; do not constrain meaning.
        for (unsigned int i = 0; i < 10; ++i) Bool("game.flag" + std::to_string(i), (i % 2) != 0);
        Strings("advisors"); // unordered_set<string>, not a scalar word.
        Words(12); String("script", f.rich ? Text() : "");
        Words(7u * 64u); // Four player arrays and three team arrays, without counts.
        for (unsigned int i = 0; i < 8; ++i) HashArray("game.hashes" + std::to_string(i), 1);
        Words(3u * 63u); // Civilization-team vote arrays, without counts.
        Count("special_units", f.rich ? 3u : 0u);
        if (f.rich) { U32(0); U32(0x12345678); Bool("special.true", true); U32(0x87654321); Bool("special.false"); }
        HashArray("victory_rows", f.awards);
        Strings("destroyed_cities"); Strings("great_people");
        FreeList("selections", true); FreeList("triggered", false);
        Random("map_rng"); Random("jon_rng");
        Version("replay", 2); Count("replay.messages", f.rich ? 2u : 0u, true);
        if (f.rich) for (unsigned int i = 0; i < 2; ++i) {
            I32(64); I32(3); Count("replay.plots" + std::to_string(i), 2, true);
            U16(0xffff); U16(4); U16(1); U16(0xfffe);
            I32(0); String("replay.text" + std::to_string(i), Text());
        }
        I32(1); // Session count precedes both plot-extra containers.
        Count("plot_yields", f.rich ? 1u : 0u);
        if (f.rich) { I32(1); I32(2); Count("plot_yields.values", 6); Words(6); }
        Count("plot_costs", f.rich ? 1u : 0u);
        if (f.rich) { I32(2); I32(1); I32(-1); }
        Bool("archaeology", true); I32(-1);
    }
    void TradedItem(const std::string& name) {
        Version(name, 2); Words(6); Bool(name + ".flag", true); I32(0);
        Bool(name + ".from_renewed"); Bool(name + ".to_renewed", true);
    }
    void Deal(const std::string& name) {
        Version(name, 3); Words(5);
        Bool(name + ".considering"); Bool(name + ".checked", true); Bool(name + ".cancelled");
        Words(4); Count(name + ".items", 1, true); TradedItem(name + ".item");
    }
    void Deals() {
        Version("deals", 1);
        for (unsigned int i = 0; i < 3; ++i) {
            const auto name = "deals.group" + std::to_string(i);
            Count(name, f.rich ? 1u : 0u, true);
            if (f.rich) Deal(name + ".deal");
        }
    }
    void Religion() {
        Version("religions", 4); I32(100); Count("religions.entries", f.rich ? 1u : 0u, true);
        if (!f.rich) return;
        Version("religion", 4); Words(5); Bool("religion.pantheon"); Bool("religion.enhanced", true);
        FixedName("religion.custom_name");
        Version("religion.beliefs", 2); Words(26);
        Count("religion.selected_beliefs", 2); U32(0); U32(0x789c0001u);
        Count("religion.buildings", 3, true);
        U32(0); U32(0x12121212u); I32(-1); U32(0x34343434u); I32(3);
    }
    void Culture() {
        Version("culture", 2); Count("culture.works", f.rich ? 1u : 0u, true);
        if (f.rich) { Version("great_work", 3); String("great_work.name", Text()); Words(5); }
        Bool("culture.reported", true);
    }
    void PlayerVote(const std::string& name) { Version(name, 1); Words(3); }
    void Decision(const std::string& name) { Version(name, 1); I32(3); }
    void Voter(const std::string& name) {
        Decision(name + ".base"); Version(name, 1); Count(name + ".votes", 2, true);
        PlayerVote(name + ".first"); PlayerVote(name + ".second");
    }
    void Proposer(const std::string& name) {
        Decision(name + ".base"); Version(name, 1); PlayerVote(name + ".vote");
    }
    void Effects(const std::string& name) {
        Version(name, 9); Bool(name + ".victory"); Bool(name + ".host", true);
        Words(2); Bool(name + ".neutral", true); Words(3);
        Bool(name + ".city_states"); Bool(name + ".player", true); Bool(name + ".happiness");
        Words(4); Bool(name + ".nuclear", true); Words(9);
    }
    void Resolution(const std::string& name) {
        Version(name, 2); Words(3); Effects(name + ".effects");
        Voter(name + ".voter"); Proposer(name + ".proposer");
    }
    void Proposal(const std::string& name) {
        Resolution(name + ".resolution"); Version(name, 1); I32(0);
    }
    void Enact(const std::string& name) { Proposal(name + ".proposal"); Version(name, 1); }
    void Repeal(const std::string& name) {
        Proposal(name + ".proposal"); Version(name, 1); I32(1); Voter(name + ".decision");
    }
    void League() {
        Version("league", 14); I32(0); Bool("league.un", true); Bool("league.in_session"); Words(2);
        Count("league.enact", 1, true); Enact("league.enact.entry");
        Count("league.repeal", 1, true); Repeal("league.repeal.entry");
        Count("league.active", 1, true); Resolution("league.active.resolution");
        Version("league.active.entry", 2); I32(25);
        Count("league.members", 1, true); Words(2); String("league.member.sources", Text());
        Bool("league.member.may_propose", true); Words(3);
        Bool("league.member.ever_host", true); Bool("league.member.always_host");
        I32(0); // Host.
        Count("league.projects", 1, true); I32(2); Count("league.project.contributions", 23, true);
        // FStaticVector<int,22,true> may grow; 22 is not a wire-count limit.
        Words(23); Bool("league.project.complete"); Bool("league.project.warned", true);
        Words(2); FixedName("league.custom_name"); Words(2);
        Count("league.hold_enact", 1, true); Enact("league.hold_enact.entry");
        Count("league.hold_repeal", 1, true); Repeal("league.hold_repeal.entry");
    }
    void Leagues() {
        Version("leagues", 5); I32(12); Count("leagues.entries", f.rich ? 1u : 0u, true);
        if (f.rich) League();
        Words(3);
    }
    void Trade() {
        Version("trade", 3); Count("trade.connections", f.rich ? 1u : 0u, true);
        if (f.rich) {
            I32(1); Words(9); Bool("trade.moving", true); Words(4);
            Count("trade.path", 3, true); Words(6);
            Words(6u * 2u); // Interleaved origin and destination yields.
        }
        Words(22u * 22u); I32(9);
    }
    Fixture Finish() {
        GameFront(); Deals(); Religion(); Culture(); Leagues(); Trade();
        MarkAt("database.length"); U32(f.rich ? 64u : 0u); f.databaseStart = Pos();
        if (f.rich) {
            // Deliberate SQLite/Map/deflate decoys inside an opaque payload.
            const std::array<unsigned char, 16> sqlite{{'S','Q','L','i','t','e',' ','f','o','r','m','a','t',' ','3',0}};
            f.bytes.insert(f.bytes.end(), sqlite.begin(), sqlite.end());
            U32(1); U32(99); U32(77); U8(0x78); U8(0x9c);
            while (Pos() - f.databaseStart < 64) U8(0xa5);
        }
        f.databaseBytes = Pos() - f.databaseStart; f.gameEnd = Pos(); f.mapStart = Pos();
        Version("map", 1); MarkAt("map.width"); I32(4); MarkAt("map.height"); I32(3);
        I32(8); I32(2); I32(1); I32(90); I32(-90);
        Bool("map.wrap_x", true); Bool("map.wrap_y");
        const std::array<unsigned char, 16> guid{{0x78,0x9c,1,0,0,0,99,0,0,0,77,0,0,0,0xff,0xff}};
        f.bytes.insert(f.bytes.end(), guid.begin(), guid.end());
        HashArray("map.resources", 1); HashArray("map.land_resources", 1);
        f.next = Pos();
        for (unsigned int i = 0; i < 64; ++i) U8(static_cast<unsigned char>(0xe0u + i % 16));
        return std::move(f);
    }
};

void PutU32(Bytes& bytes, std::size_t at, std::uint32_t value) {
    if (at > bytes.size() || bytes.size() - at < 4) throw std::logic_error("Invalid test patch position");
    for (unsigned int i = 0; i < 4; ++i) bytes[at + i] = static_cast<unsigned char>(value >> (8 * i));
}

RetailSaveStateInspection Inspect(const Fixture& f, const RetailSaveStateLimits& limits = {}) {
    return RetailSaveState::InspectGameAndMapPrefix(f.bytes, RetailSaveStateProfile(f.awards), limits);
}

void CheckSpan(Suite& suite, RetailInflatedSpan span, std::size_t size, const char* name) {
    suite.Check(span.offset <= size, std::string(name) + " offset outside input");
    suite.Check(span.bytes <= size - span.offset, std::string(name) + " extent outside input");
}
void CheckInspection(Suite& suite, const RetailSaveStateInspection& r, std::size_t size) {
    CheckSpan(suite, r.game, size, "Game"); CheckSpan(suite, r.embeddedDatabase, size, "Database");
    CheckSpan(suite, r.mapHeader, size, "Map");
    suite.Check(r.game.offset == 0, "Game must start at inflated offset zero");
    suite.Check(r.embeddedDatabase.offset >= r.game.offset &&
        r.embeddedDatabase.offset - r.game.offset <= r.game.bytes, "Database starts outside Game");
    suite.Check(r.embeddedDatabase.bytes <= r.game.bytes - (r.embeddedDatabase.offset - r.game.offset), "Database ends outside Game");
    suite.Check(r.mapHeader.offset == r.game.bytes, "Game/Map boundary is not adjacent");
    suite.Check(r.nextInflatedOffset == r.mapHeader.offset + r.mapHeader.bytes, "Wrong next inflated offset");
    suite.Check(!r.completeSaveVerified && !r.rulesetCompatibilityVerified, "Structural inspection must not approve a save");
    suite.Check(r.mapWidth != 0 && r.mapHeight != 0, "Accepted zero map dimensions");
}
void Golden(Suite& suite, const Fixture& f) {
    const auto before = f.bytes;
    const auto r = Inspect(f);
    CheckInspection(suite, r, f.bytes.size());
    suite.Check(r.game.bytes == f.gameEnd && r.embeddedDatabase.offset == f.databaseStart &&
        r.embeddedDatabase.bytes == f.databaseBytes, "Independent SDK writer Game/DB boundary differs");
    suite.Check(r.mapHeader.offset == f.mapStart && r.mapHeader.bytes == f.next - f.mapStart &&
        r.nextInflatedOffset == f.next, "Independent SDK writer Map boundary differs");
    suite.Check(r.mapWidth == 4 && r.mapHeight == 3, "Wrong synthetic map dimensions");
    suite.Check(r.arrayRecords == f.records, "Independent dynamic record accounting differs");
    suite.Check(f.bytes == before, "Input changed during inspection");
    if (!f.rich) {
        // Independently summed wire sizes: Game front 2889, deals 16,
        // religions 12, culture 9, leagues 24, trade 1948, DB length 4;
        // Map v1 scalar/GUID fields 50 plus two empty count words 8.
        suite.Check(f.gameEnd == 4902 && f.databaseStart == 4902 && f.next == 4960,
            "Minimal fixture differs from the fixed SDK wire-size oracle");
        suite.Check(r.game.bytes == 4902 && r.mapHeader.bytes == 58 && r.arrayRecords == 0,
            "Minimal fixed golden differs");
    }
    // Complete prefix is enough for inspection; unknown plot/body bytes remain opaque.
    const auto prefix = RetailSaveState::InspectGameAndMapPrefix(f.bytes.data(), f.next, RetailSaveStateProfile(f.awards));
    suite.Check(prefix.nextInflatedOffset == f.next && !prefix.completeSaveVerified, "Exact prefix needs opaque suffix");
    auto tail = f.bytes;
    std::fill(tail.begin() + f.next, tail.end(), static_cast<unsigned char>(0));
    const auto opaque = RetailSaveState::InspectGameAndMapPrefix(tail, RetailSaveStateProfile(f.awards));
    suite.Check(opaque.nextInflatedOffset == f.next && opaque.game.bytes == r.game.bytes, "Opaque suffix affected framing");
    ++suite.syntheticCases;
}

template<class Operation>
void Expect(Suite& suite, Code code, std::size_t maximumOffset, const std::string& name, Operation operation) {
    try { operation(); }
    catch (const RetailStateError& error) {
        suite.Check(error.Code() == code, name + ": wrong typed rejection");
        suite.Check(error.Offset() <= maximumOffset, name + ": error offset outside input");
        return;
    }
    throw std::runtime_error(name + ": expected typed rejection");
}
void RejectPatched(Suite& suite, const Fixture& f, const std::string& name,
                   std::size_t at, std::uint32_t value, Code code, std::size_t minimumBytes = 0) {
    auto changed = f.bytes;
    if (changed.size() < minimumBytes) changed.resize(minimumBytes);
    PutU32(changed, at, value);
    Expect(suite, code, changed.size(), name, [&] {
        RetailSaveState::InspectGameAndMapPrefix(changed, RetailSaveStateProfile(f.awards));
    });
}

void Truncations(Suite& suite, const Fixture& f) {
    const auto before = f.bytes;
    for (std::size_t cut = 0; cut < f.next; ++cut) {
        Expect(suite, Code::Truncated, cut, "Synthetic prefix truncation", [&] {
            RetailSaveState::InspectGameAndMapPrefix(f.bytes.data(), cut, RetailSaveStateProfile(f.awards));
        });
        ++suite.truncations;
    }
    suite.Check(f.bytes == before, "Truncation testing modified its input");
}

void LimitsAndRejections(Suite& suite, const Fixture& empty, const Fixture& rich) {
    const auto before = rich.bytes;
    RetailSaveStateLimits limits;
    limits.maxInputBytes = rich.bytes.size();
    suite.Check(Inspect(rich, limits).nextInflatedOffset == rich.next, "Inclusive input budget failed");
    --limits.maxInputBytes;
    Expect(suite, Code::InputLimit, rich.bytes.size(), "Short input budget", [&] { Inspect(rich, limits); });
    limits = {}; limits.maxPrefixBytes = rich.next;
    suite.Check(Inspect(rich, limits).nextInflatedOffset == rich.next, "Inclusive prefix budget failed");
    --limits.maxPrefixBytes;
    Expect(suite, Code::PrefixLimit, rich.bytes.size(), "Short prefix budget", [&] { Inspect(rich, limits); });
    limits = {}; limits.maxStringBytes = rich.maxString;
    suite.Check(Inspect(rich, limits).nextInflatedOffset == rich.next, "Inclusive string budget failed");
    --limits.maxStringBytes;
    Expect(suite, Code::StringLimit, rich.bytes.size(), "Short string budget", [&] { Inspect(rich, limits); });
    limits = {}; limits.maxArrayRecords = rich.maxArray;
    suite.Check(Inspect(rich, limits).arrayRecords == rich.records, "Inclusive array budget failed");
    --limits.maxArrayRecords;
    Expect(suite, Code::ArrayLimit, rich.bytes.size(), "Short array budget", [&] { Inspect(rich, limits); });
    limits = {}; limits.maxTotalRecords = rich.records;
    suite.Check(Inspect(rich, limits).arrayRecords == rich.records, "Inclusive total budget failed");
    --limits.maxTotalRecords;
    Expect(suite, Code::TotalRecordLimit, rich.bytes.size(), "Short total budget", [&] { Inspect(rich, limits); });
    limits = {}; limits.maxEmbeddedDatabaseBytes = rich.databaseBytes;
    suite.Check(Inspect(rich, limits).embeddedDatabase.bytes == 64, "Inclusive database budget failed");
    --limits.maxEmbeddedDatabaseBytes;
    Expect(suite, Code::EmbeddedDatabaseLimit, rich.bytes.size(), "Short database budget", [&] { Inspect(rich, limits); });
    limits = {}; limits.maxMapPlots = 12;
    suite.Check(Inspect(rich, limits).mapWidth == 4, "Inclusive plot budget failed");
    limits.maxMapPlots = 11;
    Expect(suite, Code::MapPlotLimit, rich.bytes.size(), "Short plot budget", [&] { Inspect(rich, limits); });
    limits.maxMapPlots = 0;
    Expect(suite, Code::MapPlotLimit, rich.bytes.size(), "Zero plot budget", [&] { Inspect(rich, limits); });
    limits = {}; limits.maxInputBytes = 0;
    Expect(suite, Code::InputLimit, rich.bytes.size(), "Zero input budget", [&] { Inspect(rich, limits); });
    limits = {}; limits.maxPrefixBytes = 0;
    Expect(suite, Code::PrefixLimit, rich.bytes.size(), "Zero prefix budget", [&] { Inspect(rich, limits); });
    limits = {}; limits.maxStringBytes = 0;
    Expect(suite, Code::StringLimit, rich.bytes.size(), "Zero string budget", [&] { Inspect(rich, limits); });
    limits = {}; limits.maxArrayRecords = 0;
    Expect(suite, Code::ArrayLimit, rich.bytes.size(), "Zero array budget", [&] { Inspect(rich, limits); });
    limits = {}; limits.maxTotalRecords = 0;
    Expect(suite, Code::TotalRecordLimit, rich.bytes.size(), "Zero total budget", [&] { Inspect(rich, limits); });
    limits = {}; limits.maxEmbeddedDatabaseBytes = 0;
    Expect(suite, Code::EmbeddedDatabaseLimit, rich.bytes.size(), "Zero database budget", [&] { Inspect(rich, limits); });
    limits = {}; limits.maxStringBytes = 0; limits.maxArrayRecords = 0;
    limits.maxTotalRecords = 0; limits.maxEmbeddedDatabaseBytes = 0;
    suite.Check(Inspect(empty, limits).arrayRecords == 0, "Empty dynamic state needs nonzero budgets");

    Expect(suite, Code::NullInput, 1, "Null nonempty input", [&] {
        RetailSaveState::InspectGameAndMapPrefix(nullptr, 1, RetailSaveStateProfile(5));
    });
    Expect(suite, Code::Truncated, 0, "Null empty input", [&] {
        RetailSaveState::InspectGameAndMapPrefix(nullptr, 0, RetailSaveStateProfile(5));
    });
    const unsigned char one = 0;
    Expect(suite, Code::InputLimit, 0, "Oversized size without dereference", [&] {
        RetailSaveState::InspectGameAndMapPrefix(&one, (std::numeric_limits<std::size_t>::max)(), RetailSaveStateProfile(5));
    });
    Expect(suite, Code::UnsupportedProfile, rich.bytes.size(), "Unbounded profile", [&] {
        RetailSaveState::InspectGameAndMapPrefix(rich.bytes, RetailSaveStateProfile(4097));
    });
    Expect(suite, Code::UnsupportedProfile, rich.bytes.size(), "UINT32_MAX profile", [&] {
        RetailSaveState::InspectGameAndMapPrefix(rich.bytes, RetailSaveStateProfile(0xffffffffu));
    });
    // Width is not inferred. The empty row list carries no information about it.
    const auto explicitMaximum = RetailSaveState::InspectGameAndMapPrefix(empty.bytes, RetailSaveStateProfile(4096));
    suite.Check(explicitMaximum.nextInflatedOffset == empty.next && !explicitMaximum.rulesetCompatibilityVerified,
        "An empty row list incorrectly established profile compatibility");
    for (const auto& version : rich.versions)
        RejectPatched(suite, rich, "Unsupported " + version.name, version.at, 99, Code::UnsupportedVersion);
    for (const auto& boolean : rich.bools) {
        auto changed = rich.bytes; changed[boolean.at] = 2;
        Expect(suite, Code::InvalidValue, changed.size(), "Invalid bool " + boolean.name, [&] {
            RetailSaveState::InspectGameAndMapPrefix(changed, RetailSaveStateProfile(rich.awards));
        });
    }
    for (const auto& count : rich.signedCounts)
        RejectPatched(suite, rich, "Negative count " + count.name, count.at, 0xffffffffu, Code::InvalidValue);
    for (const char* name : {"map_rng.debug", "jon_rng.debug"}) {
        auto changed = rich.bytes; changed[rich.marks.at(name)] = 1;
        Expect(suite, Code::UnsupportedProfile, changed.size(), "Debug random profile", [&] {
            RetailSaveState::InspectGameAndMapPrefix(changed, RetailSaveStateProfile(rich.awards));
        });
    }
    RejectPatched(suite, rich, "Zero map width", rich.marks.at("map.width"), 0, Code::InvalidValue);
    RejectPatched(suite, rich, "Negative map height", rich.marks.at("map.height"), 0xffffffffu, Code::InvalidValue);
    RejectPatched(suite, rich, "Huge map width", rich.marks.at("map.width"), 0x7fffffffu, Code::MapPlotLimit);
    RejectPatched(suite, rich, "Huge string", rich.marks.at("script"), 0xffffffffu, Code::StringLimit);
    RejectPatched(suite, rich, "Huge unsigned count", rich.marks.at("advisors"), 0xffffffffu, Code::ArrayLimit);
    RejectPatched(suite, rich, "Huge embedded database", rich.marks.at("database.length"), 0xffffffffu, Code::EmbeddedDatabaseLimit);
    for (const char* name : {"selections", "triggered"}) {
        const std::string base(name);
        RejectPatched(suite, rich, "Nonpower free capacity", rich.marks.at(base + ".slots"), 3, Code::InvalidValue);
        RejectPatched(suite, rich, "Free capacity over SDK mask", rich.marks.at(base + ".slots"), 16384,
            Code::InvalidValue, rich.bytes.size() + 65536);
        RejectPatched(suite, rich, "Invalid last index", rich.marks.at(base + ".last"), 4, Code::InvalidValue);
        RejectPatched(suite, rich, "Invalid free head", rich.marks.at(base + ".free_head"), 4, Code::InvalidValue);
        RejectPatched(suite, rich, "Invalid free count", rich.marks.at(base + ".free_count"), 4, Code::InvalidValue);
        RejectPatched(suite, rich, "Invalid current ID", rich.marks.at(base + ".current_id"), 24577, Code::InvalidValue);
        RejectPatched(suite, rich, "Cyclic free chain", rich.marks.at(base + ".link1"), 1, Code::InvalidValue);
        RejectPatched(suite, rich, "Inconsistent live count", rich.marks.at(base + ".live"), 1, Code::InvalidValue);
        RejectPatched(suite, rich, "Record occupies free slot", rich.marks.at(base + ".record0.id"), 8193, Code::InvalidValue);
        RejectPatched(suite, rich, "Duplicate live slot", rich.marks.at(base + ".record2.id"), 8192, Code::InvalidValue);
    }
    suite.Check(rich.maxArray == 23 && Inspect(rich).nextInflatedOffset == rich.next,
        "Growable project contribution list of 23 was rejected");
    // A nonempty row actually uses the explicit profile; no hidden default five.
    for (std::uint32_t wrong : {0u, 1u, 7u}) {
        bool rejected = false;
        try {
            const auto r = RetailSaveState::InspectGameAndMapPrefix(rich.bytes, RetailSaveStateProfile(wrong));
            // Structural ambiguity alone may never claim ruleset approval.
            suite.Check(!r.rulesetCompatibilityVerified, "Wrong profile was declared compatible");
            suite.Check(r.nextInflatedOffset != rich.next, "Wrong profile silently reused the correct boundary");
        } catch (const RetailStateError& error) {
            suite.Check(error.Offset() <= rich.bytes.size(), "Wrong-profile error offset outside input"); rejected = true;
        }
        suite.Check(rejected || wrong != rich.awards, "Wrong profile test did not change the profile");
    }
    suite.Check(rich.bytes == before, "Rejection tests modified their input");
}

struct Observation {
    bool accepted = false;
    RetailSaveStateInspection value;
    Code code = Code::Truncated;
    std::size_t errorOffset = 0;
};
Observation Observe(const Bytes& bytes, std::uint32_t awards) {
    Observation result;
    RetailSaveStateLimits limits;
    limits.maxInputBytes = 64u * 1024u;
    limits.maxPrefixBytes = 64u * 1024u;
    limits.maxStringBytes = 4096; limits.maxArrayRecords = 2048;
    limits.maxTotalRecords = 16384; limits.maxEmbeddedDatabaseBytes = 4096;
    try { result.value = RetailSaveState::InspectGameAndMapPrefix(bytes, RetailSaveStateProfile(awards), limits); result.accepted = true; }
    catch (const RetailStateError& error) { result.code = error.Code(); result.errorOffset = error.Offset(); }
    return result;
}
bool Same(const Observation& a, const Observation& b) {
    if (a.accepted != b.accepted) return false;
    if (!a.accepted) return a.code == b.code && a.errorOffset == b.errorOffset;
    const auto& x = a.value; const auto& y = b.value;
    return x.game.offset == y.game.offset && x.game.bytes == y.game.bytes &&
        x.embeddedDatabase.offset == y.embeddedDatabase.offset && x.embeddedDatabase.bytes == y.embeddedDatabase.bytes &&
        x.mapHeader.offset == y.mapHeader.offset && x.mapHeader.bytes == y.mapHeader.bytes &&
        x.nextInflatedOffset == y.nextInflatedOffset && x.mapWidth == y.mapWidth && x.mapHeight == y.mapHeight &&
        x.arrayRecords == y.arrayRecords && x.completeSaveVerified == y.completeSaveVerified &&
        x.rulesetCompatibilityVerified == y.rulesetCompatibilityVerified;
}
void Mutations(Suite& suite, const std::vector<Fixture>& seeds) {
    std::uint32_t random = 0x7fa3b129u;
    const auto next = [&random]() { random ^= random << 13; random ^= random >> 17; random ^= random << 5; return random; };
    for (std::size_t i = 0; i < 2048; ++i) {
        const auto& seed = seeds[i % seeds.size()]; auto bytes = seed.bytes;
        if (i % 8 == 0) PutU32(bytes, 0, 99);
        else if (i % 8 == 1) bytes[seed.next + next() % (bytes.size() - seed.next)] ^= 0x80;
        else if (i % 8 == 2) PutU32(bytes, seed.marks.at("map.width"), next());
        else if (i % 8 == 3) bytes[seed.marks.at("map_rng.debug")] = 1;
        else if (i % 8 == 4) PutU32(bytes, seed.marks.at("advisors"), 0xffffffffu);
        else if (i % 8 == 5) bytes.resize(next() % seed.next);
        else bytes[next() % bytes.size()] ^= static_cast<unsigned char>(1u << (next() % 8));
        const auto immutable = bytes;
        const auto first = Observe(bytes, seed.awards), second = Observe(bytes, seed.awards);
        suite.Check(Same(first, second), "Bounded mutation was nondeterministic");
        suite.Check(bytes == immutable, "Mutation inspection modified input");
        if (first.accepted) { CheckInspection(suite, first.value, bytes.size()); ++suite.accepted; }
        else { suite.Check(first.errorOffset <= bytes.size(), "Mutation error offset outside input"); ++suite.rejected; }
        ++suite.mutations;
    }
    suite.Check(suite.accepted != 0 && suite.rejected != 0, "Mutation corpus did not exercise both outcomes");
}

Bytes ReadStdin() {
#ifdef _WIN32
    if (_setmode(_fileno(stdin), _O_BINARY) == -1) throw std::runtime_error("Cannot set binary stdin");
#endif
    constexpr std::size_t maximum = 64u * 1024u * 1024u;
    Bytes bytes; std::array<char, 65536> chunk{};
    while (std::cin) {
        std::cin.read(chunk.data(), static_cast<std::streamsize>(chunk.size()));
        const auto count = static_cast<std::size_t>(std::cin.gcount());
        if (count > maximum - bytes.size()) throw std::runtime_error("Public stdin exceeds test byte budget");
        bytes.insert(bytes.end(), chunk.begin(), chunk.begin() + count);
    }
    if (!std::cin.eof()) throw std::runtime_error("Public stdin read failed");
    return bytes;
}
std::string Escape(const std::string& text) {
    std::string out;
    for (unsigned char value : text) {
        if (value == '"' || value == '\\') { out += '\\'; out += static_cast<char>(value); }
        else if (value >= 0x20 && value < 0x7f) out += static_cast<char>(value);
        else out += '?';
    }
    return out;
}
void PublicJson(const RetailSaveStateInspection& r, std::size_t input) {
    std::cout << ",\"public\":{\"input_bytes\":" << input << ",\"game_offset\":" << r.game.offset
        << ",\"game_bytes\":" << r.game.bytes << ",\"database_offset\":" << r.embeddedDatabase.offset
        << ",\"database_bytes\":" << r.embeddedDatabase.bytes << ",\"map_offset\":" << r.mapHeader.offset
        << ",\"map_bytes\":" << r.mapHeader.bytes << ",\"next_inflated_offset\":" << r.nextInflatedOffset
        << ",\"map_width\":" << r.mapWidth << ",\"map_height\":" << r.mapHeight
        << ",\"array_records\":" << r.arrayRecords << '}';
}
} // namespace

int main(int argc, char** argv) {
    Suite suite;
    try {
        static_assert(sizeof(void*) == 8, "This component test requires a 64-bit executable");
        const bool publicMode = argc == 2 && std::strcmp(argv[1], "--public") == 0;
        if (argc != 1 && !publicMode) throw std::invalid_argument("Usage: retail_save_state [--public]");
        std::vector<Fixture> fixtures;
        for (std::uint32_t awards : {0u, 1u, 5u, 7u})
            for (bool rich : {false, true}) fixtures.push_back(Wire(awards, rich).Finish());
        for (const auto& fixture : fixtures) Golden(suite, fixture);
        Truncations(suite, fixtures[0]); Truncations(suite, fixtures[5]);
        LimitsAndRejections(suite, fixtures[0], fixtures[5]);
        Mutations(suite, fixtures);
        RetailSaveStateInspection publicResult; std::size_t publicBytes = 0;
        if (publicMode) {
            const auto bytes = ReadStdin(); const auto immutable = bytes;
            suite.Check(bytes.size() == 9762327, "Wrong public inflated corpus length");
            publicResult = RetailSaveState::InspectGameAndMapPrefix(bytes, RetailSaveStateProfile(5));
            CheckInspection(suite, publicResult, bytes.size());
            suite.Check(bytes == immutable, "Public stdin bytes changed"); publicBytes = bytes.size();
        }
        std::cout << "{\"status\":\"PASS_RETAIL_STATE_COMPONENT\",\"checks\":" << suite.checks
            << ",\"synthetic_cases\":" << suite.syntheticCases << ",\"truncations\":" << suite.truncations
            << ",\"mutations\":" << suite.mutations << ",\"accepted_mutations\":" << suite.accepted
            << ",\"rejected_mutations\":" << suite.rejected
            << ",\"input_files_unchanged\":true,\"gamecore_loaded\":false,\"window_created\":false"
            << ",\"game_accessed\":false,\"user_saves_accessed\":false,\"complete_save_validated\":false"
            << ",\"ruleset_compatibility_verified\":false";
        if (publicMode) PublicJson(publicResult, publicBytes);
        std::cout << "}\n"; return 0;
    } catch (const std::exception& error) {
        std::cout << "{\"status\":\"FAIL_RETAIL_STATE_COMPONENT\",\"checks\":" << suite.checks
            << ",\"error\":\"" << Escape(error.what()) << "\",\"gamecore_loaded\":false,\"window_created\":false"
            << ",\"complete_save_validated\":false,\"ruleset_compatibility_verified\":false}\n";
        return 1;
    }
}
