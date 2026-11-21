#include "../Source/Host/RetailSavePlayerAiLate.h"
#include "../Source/Host/RetailSavePlayerAiMid.h"
#include "../Source/Host/RetailSavePlayerPrefix.h"
#include "../Source/Host/RetailSaveMap.h"
#include "../Source/Host/RetailSaveTeam.h"
#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <exception>
#include <initializer_list>
#include <iostream>
#include <limits>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>
#if defined(_WIN32)
#include <fcntl.h>
#include <io.h>
#endif

// Independent source-wire writer. Original CvMinorCivAI.cpp:1582-1594,
// 1795-1855; CvDealAI.cpp:63-68; CvBuilderTaskingAI.cpp:139-156;
// CvCityConnections.cpp:111-129; CvDangerPlots.cpp:673-688; and
// CvTraitClasses.cpp:2853-3003. Fixture bytes and literal checkpoints do not
// use production framing functions/constants, SDK objects or private saves.
// The following unread Espionage word is version ZERO, from the original
// CvEspionageClasses.cpp:3713-3716, not a signature to search for.
namespace {
using namespace ZeroSisHost;
using Bytes = std::vector<unsigned char>;
using Code = RetailStateErrorCode;
using Result = decltype(RetailSavePlayerAiLate::InspectAt(nullptr, std::size_t{}, std::size_t{},
    RetailPlayerAiLateProfile::InitializedMinorQuests));
struct Suite {
    std::size_t checks = 0, truncations = 0, mutations = 0, accepted = 0, rejected = 0;
    void Check(bool condition, const std::string& why) {
        ++checks; if (!condition) throw std::runtime_error(why);
    }
};
struct Fixture {
    Bytes bytes;
    bool rich = false;
    std::uint32_t quests = 0, dimension = 0, cities = 0, grid = 0;
    std::size_t start = 0, end = 0, records = 0, maxArray = 0;
    std::array<RetailInflatedSpan, 6> spans{};
    std::map<std::string, std::size_t> marks;
    std::vector<std::size_t> versions, bools, signedCounts, unsignedCounts;
};
class Writer {
public:
    Fixture f;
    Writer(bool rich, std::uint32_t quests, std::uint32_t dimension, std::uint32_t grid, std::size_t start) {
        f.rich = rich; f.quests = quests; f.dimension = dimension; f.grid = grid; f.start = start;
        f.cities = dimension == 0 ? 0u : (rich ? 3u : 1u);
        f.bytes.assign(start, static_cast<unsigned char>(0x78));
        if (start >= 4) { f.bytes[0] = 1; f.bytes[1] = 0; f.bytes[2] = 0; f.bytes[3] = 0; }
    }
    void Mark(const std::string& name) { f.marks[name] = f.bytes.size(); }
    void U8(unsigned char value) { f.bytes.push_back(value); }
    void U32(std::uint32_t value) {
        for (unsigned i = 0; i < 4; ++i) U8(static_cast<unsigned char>(value >> (8 * i)));
    }
    void I32(std::int32_t value) { U32(static_cast<std::uint32_t>(value)); }
    void Words(std::size_t count, std::uint32_t seed = 0x80010000u) {
        for (std::size_t i = 0; i < count; ++i) U32(seed + static_cast<std::uint32_t>(i));
    }
    void RawChars(std::size_t count) {
        const std::array<unsigned char, 4> pattern = {0xff, 0x80, 0x78, 0x9c};
        for (std::size_t i = 0; i < count; ++i) U8(pattern[i % pattern.size()]);
    }
    void Bool(bool value) { f.bools.push_back(f.bytes.size()); U8(value ? 1 : 0); }
    void Bools(std::size_t count) { for (std::size_t i = 0; i < count; ++i) Bool((i & 1u) != 0); }
    void Version(const std::string& name, std::uint32_t version) {
        Mark(name); f.versions.push_back(f.bytes.size()); U32(version);
    }
    void Count(const std::string& name, std::uint32_t count, bool isSigned = false) {
        Mark(name); (isSigned ? f.signedCounts : f.unsignedCounts).push_back(f.bytes.size());
        U32(count); f.records += count;
        f.maxArray = (std::max)(f.maxArray, static_cast<std::size_t>(count));
    }
    std::uint32_t N() const { return f.rich ? 3u : 0u; }
    void HashInts(const std::string& name) {
        Count(name, N());
        if (f.rich) { U32(0); U32(0xffffffffu); I32(-1); U32(0x12345678u); U32(0x80000000u); }
    }
    template<class F> void Section(std::size_t index, F write) {
        const auto start = f.bytes.size(); write(); f.spans[index] = {start, f.bytes.size() - start};
    }
    void Minor() {
        Version("minor.version", 1); Words(8);
        Mark("minor.war_flags"); Bools(22);
        Mark("minor.enemies");
        for (unsigned row = 0; row < 22; ++row) Words(22);
        Mark("minor.routes"); Bools(22);
        Mark("minor.friendship");
        for (unsigned column = 0; column < 12; ++column) Words(22);
        for (unsigned column = 0; column < 4; ++column) Bools(22);
        // The actual permanent-war and wary arrays are REALLY_MAX_TEAMS=80.
        // CvMinorCivAI.h:589-590, not MAX_CIV_PLAYERS=63 or MAX_TEAMS=64.
        Bools(80); Bools(80);
        for (unsigned major = 0; major < 22; ++major) {
            const auto count = major == 0 ? f.quests : 0u;
            Count("minor.quests" + std::to_string(major), count, true);
            for (std::uint32_t quest = 0; quest < count; ++quest) {
                Version("quest.version" + std::to_string(quest), 2);
                Words(4); Bool((quest & 1u) != 0);
            }
        }
        Mark("minor.notifications"); Bool(true);
    }
    void Traits() {
        Version("traits.version", 19);
        Words(65); // Independently counted scalar writes at source:2859-2923.
        Mark("traits.first_bool"); Bools(14);
        Mark("traits.baktun"); I32(-1);
        Count("traits.maya", N(), true);
        Words(2u * N()); // UnitTypes enum and baktun int, no per-row version.
        Mark("traits.extra_bools"); Bools(5);
        Words(2); // Camp-guard UnitTypes and combat-bonus ImprovementTypes.
        Mark("traits.raw_yields");
        for (unsigned column = 0; column < 7; ++column) Words(6);
        HashInts("traits.terrain"); HashInts("traits.resource");
        Count("traits.no_train", N(), true); Bools(N());
        Count("traits.free_units", N(), true); Words(2u * N());
        Count("traits.combat", N(), true); Words(N()); Words(N());
        for (unsigned kind = 0; kind < 3; ++kind) {
            Count("traits.matrix" + std::to_string(kind), N());
            // std::vector outer uint32 count, each Firaxis::Array has SIX
            // uncounted int32 values. There is no nested count or padding.
            for (std::uint32_t row = 0; row < N(); ++row) Words(6, 0xfffffffau);
        }
        Count("traits.luxury", N(), true); Words(N());
    }
    Fixture Finish() {
        Section(0, [&] { Minor(); });
        Section(1, [&] { Version("deal.version", 1); });
        Section(2, [&] {
            Version("builder.version", 2); I32(-1);
            Count("builder.plots", N()); Words(N()); Bool(true); Bool(false);
        });
        Section(3, [&] {
            Version("city.version", 1); Count("city.dimension", f.dimension);
            Mark("city.matrix"); RawChars(2u * f.dimension * f.dimension);
            Count("city.ids", f.cities, true); Words(f.cities);
        });
        Section(4, [&] {
            Version("danger.version", 1); I32(-1);
            Mark("danger.allocated"); Bool(!f.rich); // False still has a populated grid.
            Count("danger.grid", f.grid, true); Words(f.grid, 0xfffffffdu);
        });
        Section(5, [&] { Traits(); });
        f.end = f.bytes.size(); U32(0); U32(0xe5a1c0deu); Words(8, 4u);
        return f;
    }
};
std::array<RetailInflatedSpan, 6> Spans(const Result& r) {
    return {r.minorCivAI, r.dealAI, r.builderTaskingAI, r.cityConnections, r.dangerPlots, r.traits};
}
Result Parse(const Fixture& f, const RetailSaveStateLimits& limits = RetailSaveStateLimits{}) {
    return RetailSavePlayerAiLate::InspectAt(f.bytes.data(), f.bytes.size(), f.start,
        RetailPlayerAiLateProfile::InitializedMinorQuests, limits);
}
std::uint32_t Word(const Bytes& bytes, std::size_t at) {
    if (at > bytes.size() || bytes.size() - at < 4) throw std::runtime_error("Invalid test word offset");
    return static_cast<std::uint32_t>(bytes[at]) | (static_cast<std::uint32_t>(bytes[at + 1]) << 8) |
        (static_cast<std::uint32_t>(bytes[at + 2]) << 16) | (static_cast<std::uint32_t>(bytes[at + 3]) << 24);
}
void Put(Bytes& bytes, std::size_t at, std::uint32_t value) {
    if (at > bytes.size() || bytes.size() - at < 4) throw std::runtime_error("Invalid test patch offset");
    for (unsigned i = 0; i < 4; ++i) bytes[at + i] = static_cast<unsigned char>(value >> (8 * i));
}
void Invariants(Suite& s, const Result& r, std::size_t size, std::size_t start) {
    auto cursor = start;
    for (const auto span : Spans(r)) {
        s.Check(span.offset == cursor, "Late-AI spans are not contiguous");
        s.Check(span.offset <= size && span.bytes <= size - span.offset, "Late-AI span exceeds input");
        cursor = span.offset + span.bytes;
    }
    s.Check(cursor == r.nextInflatedOffset && cursor <= size, "Wrong late-AI next offset");
    s.Check(!r.completeSaveVerified && !r.rulesetCompatibilityVerified, "Late-AI framing granted ruleset or restore approval");
}
template<class F> void Reject(Suite& s, Code expected, const std::string& why, F action) {
    try { action(); } catch (const RetailStateError& error) {
        s.Check(error.Code() == expected, why + ": wrong typed error"); return;
    }
    s.Check(false, why + ": malformed input accepted");
}
void Golden(Suite& s, const Fixture& f) {
    const auto immutable = f.bytes; const auto r = Parse(f); Invariants(s, r, f.bytes.size(), f.start);
    const std::array<std::size_t, 6> literal = {3409u + 21u * f.quests, 4u,
        f.rich ? 26u : 14u, 12u + 2u * f.dimension * f.dimension + 4u * f.cities,
        13u + 4u * f.grid, f.rich ? 846u : 503u};
    const auto spans = Spans(r);
    for (std::size_t i = 0; i < spans.size(); ++i) {
        s.Check(f.spans[i].bytes == literal[i], "Independent fixture disagrees with literal source size");
        s.Check(spans[i].offset == f.spans[i].offset && spans[i].bytes == literal[i], "Wrong late-AI component boundary");
    }
    s.Check(f.end - f.start == 3955u + 21u * f.quests + (f.rich ? 355u : 0u) +
        2u * f.dimension * f.dimension + 4u * f.cities + 4u * f.grid, "Wrong literal combined late-AI bytes");
    s.Check(f.marks.at("minor.war_flags") - f.start == 36 &&
        f.marks.at("minor.enemies") - f.start == 58 &&
        f.marks.at("minor.routes") - f.start == 1994 &&
        f.marks.at("minor.friendship") - f.start == 2016 &&
        f.marks.at("minor.quests0") - f.start == 3320 &&
        f.marks.at("minor.notifications") - f.start == 3408u + 21u * f.quests,
        "Minor fixed arrays or unprefixed outer quest width changed");
    const auto traits = f.spans[5].offset;
    s.Check(f.marks.at("traits.first_bool") - traits == 264 &&
        f.marks.at("traits.baktun") - traits == 278 &&
        f.marks.at("traits.maya") - traits == 282 &&
        f.marks.at("traits.extra_bools") - traits == (f.rich ? 310u : 286u) &&
        f.marks.at("traits.raw_yields") - traits == (f.rich ? 323u : 299u) &&
        f.marks.at("traits.terrain") - traits == (f.rich ? 491u : 467u) &&
        f.marks.at("traits.no_train") - traits == (f.rich ? 539u : 475u) &&
        f.marks.at("traits.matrix0") - traits == (f.rich ? 602u : 487u) &&
        f.marks.at("traits.luxury") - traits == (f.rich ? 830u : 499u), "Trait source checkpoint changed");
    s.Check(f.marks.at("city.matrix") - f.spans[3].offset == 8 &&
        f.marks.at("city.ids") - f.spans[3].offset == 8u + 2u * f.dimension * f.dimension &&
        f.marks.at("danger.allocated") - f.spans[4].offset == 8 &&
        f.marks.at("danger.grid") - f.spans[4].offset == 9, "Infrastructure wire widths changed");
    const auto rows = f.quests + f.dimension + f.cities + f.grid + (f.rich ? 33u : 0u);
    s.Check(f.records == rows && r.arrayRecords == rows, "Wrong explicit-count row accounting");
    s.Check(f.bools.size() == 315u + f.quests + (f.rich ? 3u : 0u), "Wrong literal bool count");
    s.Check(r.dangerPlotCount == f.grid && r.nextInflatedOffset == f.end, "Wrong danger grid count or final offset");
    s.Check(Word(f.bytes, f.end) == 0 && Word(f.bytes, f.end + 4) == 0xe5a1c0deu,
        "Unread Espionage version-zero sentinel changed");
    const auto exact = RetailSavePlayerAiLate::InspectAt(f.bytes.data(), f.end, f.start,
        RetailPlayerAiLateProfile::InitializedMinorQuests);
    s.Check(exact.nextInflatedOffset == f.end, "Late-AI parser required unread Espionage data");
    s.Check(f.bytes == immutable, "Golden late-AI inspection changed input");
}
void Cuts(Suite& s, const Fixture& f) {
    const auto immutable = f.bytes;
    for (std::size_t size = 0; size < f.end; ++size) {
        Reject(s, Code::Truncated, "All-byte late-AI truncation", [&] {
            RetailSavePlayerAiLate::InspectAt(f.bytes.data(), size, f.start,
                RetailPlayerAiLateProfile::InitializedMinorQuests);
        });
        ++s.truncations;
    }
    s.Check(f.bytes == immutable, "All-byte cuts changed fixture bytes");
}
void Negative(Suite& s, const Fixture& empty, const Fixture& rich) {
    for (const auto* fixture : {&empty, &rich}) {
        const auto& f = *fixture;
        for (const auto at : f.versions) {
            for (std::uint32_t version : {0u, 0xffffffffu, Word(f.bytes, at) + 1u}) {
                auto bad = f; Put(bad.bytes, at, version);
                Reject(s, Code::UnsupportedVersion, "Nested late-AI version", [&] { Parse(bad); });
            }
        }
        for (const auto at : f.signedCounts) {
            auto bad = f; Put(bad.bytes, at, 0xffffffffu);
            Reject(s, Code::InvalidValue, "Negative signed late-AI count", [&] { Parse(bad); });
            Put(bad.bytes, at, 0x7fffffffu);
            Reject(s, Code::ArrayLimit, "Huge signed late-AI count", [&] { Parse(bad); });
        }
        for (const auto at : f.unsignedCounts) {
            auto bad = f; Put(bad.bytes, at, 0xffffffffu);
            Reject(s, Code::ArrayLimit, "Huge unsigned late-AI count", [&] { Parse(bad); });
        }
        auto limits = RetailSaveStateLimits{}; limits.maxPrefixBytes = f.end;
        s.Check(Parse(f, limits).nextInflatedOffset == f.end, "Exact late-AI prefix budget rejected");
        --limits.maxPrefixBytes;
        Reject(s, Code::PrefixLimit, "Short late-AI prefix budget", [&] { Parse(f, limits); });
        limits = RetailSaveStateLimits{}; limits.maxInputBytes = f.bytes.size();
        s.Check(Parse(f, limits).nextInflatedOffset == f.end, "Exact late-AI input budget rejected");
        --limits.maxInputBytes;
        Reject(s, Code::InputLimit, "Short late-AI input budget", [&] { Parse(f, limits); });
        limits = RetailSaveStateLimits{}; limits.maxArrayRecords = f.maxArray;
        limits.maxTotalRecords = f.records; limits.maxStringBytes = 0;
        s.Check(Parse(f, limits).arrayRecords == f.records, "Exact count budgets or zero string budget rejected");
        if (f.rich) {
            --limits.maxArrayRecords;
            Reject(s, Code::ArrayLimit, "Short late-AI array budget", [&] { Parse(f, limits); });
            limits.maxArrayRecords = f.maxArray; --limits.maxTotalRecords;
            Reject(s, Code::TotalRecordLimit, "Short late-AI aggregate budget", [&] { Parse(f, limits); });
        }
    }
    for (const auto at : rich.bools) {
        auto bad = rich; bad.bytes[at] = 2;
        Reject(s, Code::InvalidValue, "Noncanonical late-AI bool", [&] { Parse(bad); });
    }
    auto overflow = rich; Put(overflow.bytes, overflow.marks.at("city.dimension"), 65536u);
    Reject(s, Code::InvalidValue, "City dimension square uint32 overflow", [&] { Parse(overflow); });
    auto hugeMatrix = rich; Put(hugeMatrix.bytes, hugeMatrix.marks.at("city.dimension"), 65535u);
    Reject(s, Code::Truncated, "City matrix must be byte-bounded before any traversal", [&] { Parse(hugeMatrix); });
    auto noAllocation = rich; noAllocation.bytes[noAllocation.marks.at("danger.allocated")] = 0;
    s.Check(Parse(noAllocation).dangerPlotCount == rich.grid, "Danger allocation flag incorrectly skipped grid data");
    Reject(s, Code::NullInput, "Null late-AI input", [&] {
        RetailSavePlayerAiLate::InspectAt(nullptr, 1, 0, RetailPlayerAiLateProfile::InitializedMinorQuests);
    });
    Reject(s, Code::Truncated, "Empty late-AI input", [&] {
        RetailSavePlayerAiLate::InspectAt(nullptr, 0, 0, RetailPlayerAiLateProfile::InitializedMinorQuests);
    });
    Reject(s, Code::Truncated, "Late-AI start exceeds input", [&] {
        RetailSavePlayerAiLate::InspectAt(empty.bytes.data(), empty.bytes.size(),
            (std::numeric_limits<std::size_t>::max)(), RetailPlayerAiLateProfile::InitializedMinorQuests);
    });
    Reject(s, Code::UnsupportedProfile, "Unrecognized Minor quest initialization profile", [&] {
        RetailSavePlayerAiLate::InspectAt(empty.bytes.data(), empty.bytes.size(), empty.start,
            static_cast<RetailPlayerAiLateProfile>(-1));
    });
    Reject(s, Code::UnsupportedProfile, "Minor profile must reject before reading bytes", [&] {
        RetailSavePlayerAiLate::InspectAt(nullptr, 0, (std::numeric_limits<std::size_t>::max)(),
            static_cast<RetailPlayerAiLateProfile>(-1));
    });
    auto zero = RetailSaveStateLimits{}; zero.maxInputBytes = 0;
    Reject(s, Code::InputLimit, "Zero late-AI input budget", [&] { Parse(empty, zero); });
    zero = RetailSaveStateLimits{}; zero.maxPrefixBytes = 0;
    Reject(s, Code::PrefixLimit, "Zero late-AI prefix budget", [&] { Parse(empty, zero); });
    zero = RetailSaveStateLimits{}; zero.maxArrayRecords = 0;
    Reject(s, Code::ArrayLimit, "Zero late-AI array budget", [&] { Parse(rich, zero); });
    zero = RetailSaveStateLimits{}; zero.maxTotalRecords = 0;
    Reject(s, Code::TotalRecordLimit, "Zero late-AI aggregate budget", [&] { Parse(rich, zero); });
}
struct Observation { bool accepted = false; Result result; Code code = Code::InvalidValue; std::size_t offset = 0; };
Observation Observe(const Bytes& bytes, std::size_t start, bool validProfile) {
    Observation o;
    try {
        o.result = RetailSavePlayerAiLate::InspectAt(bytes.data(), bytes.size(), start, validProfile
            ? RetailPlayerAiLateProfile::InitializedMinorQuests : static_cast<RetailPlayerAiLateProfile>(-1));
        o.accepted = true;
    } catch (const RetailStateError& error) { o.code = error.Code(); o.offset = error.Offset(); }
    return o;
}
bool Same(const Observation& a, const Observation& b) {
    if (a.accepted != b.accepted) return false;
    if (!a.accepted) return a.code == b.code && a.offset == b.offset;
    const auto left = Spans(a.result), right = Spans(b.result);
    for (std::size_t i = 0; i < left.size(); ++i)
        if (left[i].offset != right[i].offset || left[i].bytes != right[i].bytes) return false;
    return a.result.dangerPlotCount == b.result.dangerPlotCount && a.result.nextInflatedOffset == b.result.nextInflatedOffset &&
        a.result.arrayRecords == b.result.arrayRecords && a.result.completeSaveVerified == b.result.completeSaveVerified &&
        a.result.rulesetCompatibilityVerified == b.result.rulesetCompatibilityVerified;
}
std::uint32_t Random(std::uint32_t& state) {
    state ^= state << 13; state ^= state >> 17; state ^= state << 5; return state;
}
void Mutations(Suite& s, const std::vector<Fixture>& fixtures) {
    std::uint32_t random = 0xc5a17e42u;
    for (std::size_t i = 0; i < 2048; ++i) {
        const auto& f = fixtures[(i / 8) % fixtures.size()]; auto bytes = f.bytes; bool validProfile = true;
        switch (i % 8) {
        case 0: bytes[Random(random) % bytes.size()] ^= static_cast<unsigned char>(1u << (Random(random) % 8)); break;
        case 1: Put(bytes, f.versions[Random(random) % f.versions.size()], Random(random)); break;
        case 2: bytes[f.bools[Random(random) % f.bools.size()]] = 2; break;
        case 3: {
            const auto& counts = (Random(random) & 1u) ? f.signedCounts : f.unsignedCounts;
            Put(bytes, counts[Random(random) % counts.size()], 0xffffffffu); break;
        }
        case 4: bytes.resize(Random(random) % (bytes.size() + 1)); break;
        case 5: validProfile = false; break;
        case 6: bytes.push_back(static_cast<unsigned char>(Random(random))); break;
        default: Put(bytes, Random(random) % (bytes.size() - 3), Random(random)); break;
        }
        const auto immutable = bytes;
        const auto first = Observe(bytes, f.start, validProfile), second = Observe(bytes, f.start, validProfile);
        s.Check(Same(first, second), "Late-AI mutation outcome was nondeterministic");
        s.Check(bytes == immutable, "Late-AI mutation framing changed input bytes");
        if (first.accepted) { Invariants(s, first.result, bytes.size(), f.start); ++s.accepted; }
        else { s.Check(first.offset <= bytes.size(), "Late-AI error offset exceeds input"); ++s.rejected; }
        ++s.mutations;
    }
    s.Check(s.accepted != 0 && s.rejected != 0, "Late-AI mutations missed accepted or rejected outcomes");
}
Bytes ReadStdin() {
#if defined(_WIN32)
    if (_setmode(_fileno(stdin), _O_BINARY) == -1) throw std::runtime_error("Cannot set binary stdin mode");
#endif
    constexpr std::size_t maximum = 64u * 1024u * 1024u;
    Bytes bytes; std::array<char, 65536> chunk{};
    for (;;) {
        std::cin.read(chunk.data(), static_cast<std::streamsize>(chunk.size()));
        const auto read = std::cin.gcount();
        if (read < 0) throw std::runtime_error("Negative stdin byte count");
        const auto count = static_cast<std::size_t>(read);
        if (count > maximum - bytes.size()) throw std::runtime_error("Public stdin exceeds byte budget");
        const auto* begin = reinterpret_cast<const unsigned char*>(chunk.data());
        bytes.insert(bytes.end(), begin, begin + count); if (count < chunk.size()) break;
    }
    if (std::cin.bad() || (!std::cin.eof() && std::cin.fail())) throw std::runtime_error("Public stdin read failed");
    return bytes;
}
struct PublicResult {
    Result late;
    std::size_t bytes = 0, mapEnd = 0, teamsEnd = 0, prefixEnd = 0, midEnd = 0;
    std::uint32_t mapPlots = 0, espionageVersion = 0;
};
PublicResult Public(Suite& s) {
    const auto bytes = ReadStdin(); const auto immutable = bytes;
    s.Check(bytes.size() == 9762327u, "Wrong public inflated corpus size");
    // All external profiles are explicit structural hypotheses. Root separately
    // authenticates the public input SHA256 in RAM, without retaining the body.
    auto remaining = RetailSaveStateLimits{};
    const auto map = RetailSaveMap::InspectGameAndMap(bytes, RetailSaveStateProfile(5), remaining);
    s.Check(map.nextInflatedOffset == 1695150u && map.plotCount == 960u, "Public ordered Map boundary changed");
    s.Check(map.arrayRecords <= remaining.maxTotalRecords, "Map exceeded shared record budget");
    remaining.maxTotalRecords -= map.arrayRecords;
    RetailStateDetail::Reader teams(bytes.data(), bytes.size(), remaining); teams.Skip(map.nextInflatedOffset);
    for (std::int32_t id = 0; id < 64; ++id)
        s.Check(RetailStateDetail::ReadTeam(teams) == id, "Public Team IDs are not sequential 0..63");
    s.Check(teams.Pos() == 2309550u && teams.Records() <= remaining.maxTotalRecords, "Public ordered Team boundary changed");
    remaining.maxTotalRecords -= teams.Records();
    const auto prefix = RetailSavePlayerPrefix::InspectAt(bytes.data(), bytes.size(), teams.Pos(),
        RetailSavePlayerProfile(4, RetailPlayerCatalogProfile::InitializedBuildings), remaining);
    s.Check(prefix.playerId == 0 && prefix.nextInflatedOffset == 2326136u, "Public Player prefix boundary changed");
    s.Check(prefix.arrayRecords <= remaining.maxTotalRecords, "Player prefix exceeded shared record budget");
    remaining.maxTotalRecords -= prefix.arrayRecords;
    const auto mid = RetailSavePlayerAiMid::InspectAt(bytes.data(), bytes.size(), prefix.nextInflatedOffset,
        RetailPlayerAiMidCatalogProfile::InitializedTechs, remaining);
    s.Check(mid.nextInflatedOffset == 2403477u, "Public ordered AI-middle boundary changed");
    s.Check(mid.arrayRecords <= remaining.maxTotalRecords, "Player middle exceeded shared record budget");
    remaining.maxTotalRecords -= mid.arrayRecords;
    s.Check(!map.completeSaveVerified && !map.rulesetCompatibilityVerified && !prefix.completeSaveVerified &&
        !prefix.rulesetCompatibilityVerified && !mid.completeSaveVerified && !mid.rulesetCompatibilityVerified,
        "Earlier public component granted ruleset or restore approval");
    PublicResult result;
    result.bytes = bytes.size(); result.mapEnd = map.nextInflatedOffset; result.mapPlots = map.plotCount;
    result.teamsEnd = teams.Pos(); result.prefixEnd = prefix.nextInflatedOffset; result.midEnd = mid.nextInflatedOffset;
    result.late = RetailSavePlayerAiLate::InspectAt(bytes.data(), bytes.size(), mid.nextInflatedOffset,
        RetailPlayerAiLateProfile::InitializedMinorQuests, remaining);
    Invariants(s, result.late, bytes.size(), mid.nextInflatedOffset);
    s.Check(result.late.dangerPlotCount == map.plotCount, "Public danger grid disagrees with actual framed Map plots");
    RetailStateDetail::Reader following(bytes.data(), bytes.size(), RetailSaveStateLimits{});
    following.Skip(result.late.nextInflatedOffset); result.espionageVersion = following.U32();
    s.Check(result.espionageVersion == 0, "Following unread CvPlayerEspionage version is not source version zero");
    s.Check(bytes == immutable, "Public late-AI framing changed stdin bytes"); return result;
}
void PublicJson(const PublicResult& p) {
    std::cout << ",\"public\":{\"input_bytes\":" << p.bytes << ",\"map_end\":" << p.mapEnd
        << ",\"map_plot_count\":" << p.mapPlots << ",\"teams_end\":" << p.teamsEnd
        << ",\"player_prefix_end\":" << p.prefixEnd << ",\"player_ai_mid_end\":" << p.midEnd
        << ",\"start_offset\":" << p.midEnd;
    const std::array<const char*, 6> names = {"minor_civ_ai", "deal_ai", "builder_tasking_ai",
        "city_connections", "danger_plots", "traits"};
    const auto spans = Spans(p.late);
    for (std::size_t i = 0; i < names.size(); ++i)
        std::cout << ",\"" << names[i] << "_offset\":" << spans[i].offset << ",\"" << names[i] << "_bytes\":" << spans[i].bytes;
    std::cout << ",\"next_inflated_offset\":" << p.late.nextInflatedOffset << ",\"array_records\":" << p.late.arrayRecords
        << ",\"danger_plot_count\":" << p.late.dangerPlotCount << ",\"espionage_version\":" << p.espionageVersion
        << ",\"victory_point_awards\":5,\"grand_strategy_count\":4,\"building_catalog\":\"initialized\""
        << ",\"tech_catalog\":\"initialized\",\"minor_quests\":\"initialized\",\"profile_ruleset_verified\":false}";
}
std::string Escape(const char* raw) {
    std::string result;
    for (const char character : std::string(raw)) {
        const auto c = static_cast<unsigned char>(character);
        if (c == '"' || c == '\\') { result += '\\'; result += character; }
        else result += c >= 32 && c < 127 ? character : '?';
    }
    return result;
}
} // namespace

int main(int argc, char** argv) {
    Suite suite;
    try {
        static_assert(sizeof(void*) == 8, "This component test requires x64");
        const bool publicMode = argc == 2 && std::strcmp(argv[1], "--public") == 0;
        if (argc != 1 && !publicMode) throw std::invalid_argument("Usage: retail_player_ai_late [--public]");
        const std::vector<Fixture> fixtures = {Writer(false, 0, 0, 0, 0).Finish(),
            Writer(false, 1, 1, 1, 7).Finish(), Writer(true, 7, 3, 5, 13).Finish()};
        for (const auto& fixture : fixtures) Golden(suite, fixture);
        Cuts(suite, fixtures[2]); Negative(suite, fixtures[0], fixtures[2]); Mutations(suite, fixtures);
        PublicResult publicResult; if (publicMode) publicResult = Public(suite);
        std::cout << "{\"status\":\"PASS_RETAIL_PLAYER_AI_LATE_COMPONENT\",\"checks\":" << suite.checks
            << ",\"synthetic_cases\":3,\"truncations\":" << suite.truncations << ",\"mutations\":" << suite.mutations
            << ",\"accepted_mutations\":" << suite.accepted << ",\"rejected_mutations\":" << suite.rejected
            << ",\"input_files_unchanged\":true,\"input_bytes_unchanged\":true,\"gamecore_loaded\":false,\"window_created\":false"
            << ",\"game_accessed\":false,\"user_saves_accessed\":false,\"complete_player_validated\":false"
            << ",\"complete_save_validated\":false,\"ruleset_compatibility_verified\":false,\"restore_approved\":false";
        if (publicMode) PublicJson(publicResult);
        std::cout << "}\n"; return 0;
    } catch (const std::exception& error) {
        std::cout << "{\"status\":\"FAIL_RETAIL_PLAYER_AI_LATE_COMPONENT\",\"checks\":" << suite.checks
            << ",\"error\":\"" << Escape(error.what()) << "\",\"gamecore_loaded\":false,\"window_created\":false"
            << ",\"user_saves_accessed\":false,\"complete_player_validated\":false,\"complete_save_validated\":false"
            << ",\"ruleset_compatibility_verified\":false,\"restore_approved\":false}\n"; return 1;
    }
}
