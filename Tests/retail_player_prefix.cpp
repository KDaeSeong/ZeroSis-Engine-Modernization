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

// Independent wire writer: original CvPlayer.cpp:22297-22590,
// CvPolicyClasses.cpp:2179-2214, CvPolicyAI.cpp:87-104,
// CvEconomicAI.cpp:439-479,2695-2700, CvCitySpecializationAI.cpp:287-299,
// CvWonderProductionAI.cpp:124-154, CvMilitaryAI.cpp:398-415 and
// CvGrandStrategyAI.cpp:220-234. Literal byte/row oracles below are derived
// from these writers, not private-envelope output or parser constants.
// No SDK, database, file-path input, process, GameCore or window is used.
namespace {
using namespace ZeroSisHost;
using Bytes = std::vector<unsigned char>;
using Code = RetailStateErrorCode;
using Result = RetailSavePlayerPrefixInspection;
struct Suite {
    std::size_t checks = 0, truncations = 0, mutations = 0, accepted = 0, rejected = 0;
    void Check(bool condition, const std::string& why) {
        ++checks; if (!condition) throw std::runtime_error(why);
    }
};
struct Fixture {
    Bytes bytes;
    bool rich = false;
    std::uint32_t grand = 0;
    std::int32_t id = 0;
    std::size_t start = 0, end = 0, records = 0, maximumArray = 0;
    std::array<RetailInflatedSpan, 7> spans{};
    std::map<std::string, std::size_t> marks;
    std::vector<std::size_t> versions, bools, signedCounts, unsignedCounts;
};
class Writer {
public:
    Fixture f;
    Writer(bool rich, std::uint32_t grand, std::size_t start, std::int32_t id) {
        f.rich = rich; f.grand = grand; f.start = start; f.id = id;
        f.bytes.assign(start, static_cast<unsigned char>(0xce));
        if (start >= 4) { f.bytes[0] = 16; f.bytes[1] = 0; f.bytes[2] = 0; f.bytes[3] = 0; }
    }
    void Mark(const std::string& key) { f.marks[key] = f.bytes.size(); }
    void U8(unsigned char value) { f.bytes.push_back(value); }
    void U32(std::uint32_t value) {
        for (unsigned i = 0; i < 4; ++i) U8(static_cast<unsigned char>(value >> (8 * i)));
    }
    void I32(std::int32_t value) { U32(static_cast<std::uint32_t>(value)); }
    void Words(std::size_t count, std::uint32_t seed = 0x80010000u) {
        for (std::size_t i = 0; i < count; ++i) U32(seed + static_cast<std::uint32_t>(i));
    }
    void Version(const std::string& key, std::uint32_t value) {
        Mark(key); f.versions.push_back(f.bytes.size()); U32(value);
    }
    void Bool(const std::string& key, bool value) {
        Mark(key); f.bools.push_back(f.bytes.size()); U8(value ? 1 : 0);
    }
    void Count(const std::string& key, std::uint32_t count, bool isSigned = false) {
        Mark(key); (isSigned ? f.signedCounts : f.unsignedCounts).push_back(f.bytes.size());
        U32(count); f.records += count;
        f.maximumArray = (std::max)(f.maximumArray, static_cast<std::size_t>(count));
    }
    std::uint32_t N() const { return f.rich ? 3u : 0u; }
    void IntVector(const std::string& key) { Count(key, N()); Words(N()); }
    void BoolVector(const std::string& key) {
        Count(key, N());
        for (std::uint32_t i = 0; i < N(); ++i) Bool(key + ".b" + std::to_string(i), (i & 1u) != 0);
    }
    void HashInts(const std::string& key, bool isSigned = false) {
        Count(key, N(), isSigned);
        if (f.rich) { U32(0); U32(0xffffffffu); I32(-1); U32(0xa1b2c3d4u); U32(0x80000000u); }
    }
    void HashBools(const std::string& key) {
        Count(key, N());
        if (f.rich) {
            U32(0); U32(0xffffffffu); Bool(key + ".false", false);
            U32(0x01234567u); Bool(key + ".true", true);
        }
    }
    void String(const std::string& key, const Bytes& value) {
        Mark(key); U32(static_cast<std::uint32_t>(value.size()));
        f.bytes.insert(f.bytes.end(), value.begin(), value.end());
    }
    template<class F> void Section(std::size_t index, F write) {
        const auto start = f.bytes.size(); write(); f.spans[index] = {start, f.bytes.size() - start};
    }
    Fixture Finish() {
        Section(0, [&] {
            Version("front.version", 16); Words(209);
            for (unsigned i = 0; i < 11; ++i) Bool("front.b" + std::to_string(i), (i & 1u) != 0);
            I32(-17);
            Bool("front.strike", true); Bool("front.cramped", false); Bool("front.lost", true);
            I32(-1); Bool("front.religion", false); Bool("front.bias", true);
            Mark("front.id"); I32(f.id); I32(-1);
            for (unsigned i = 0; i < 16; ++i) IntVector("front.first_vector" + std::to_string(i));
            String("front.religion_length", f.rich ? Bytes{'R', 0, 'x', 0xea, 0xb0, 0x80, 0x78, 0x9c} : Bytes{});
            String("front.script_length", f.rich ? Bytes{'S', 0, 0xed, 0x95, 0x9c, ';', 0x78, 0x9c, 'E', 'N', 'D'} : Bytes{});
            for (unsigned i = 0; i < 7; ++i) HashInts("front.resource" + std::to_string(i));
            IntVector("front.improvements"); HashInts("front.free_buildings"); HashInts("front.free_promotions");
            for (unsigned i = 0; i < 9; ++i) IntVector("front.last_vector" + std::to_string(i));
            BoolVector("front.loyal"); BoolVector("front.science");
        });
        Section(1, [&] {
            Version("policies.version", 2);
            for (unsigned i = 0; i < 6; ++i) HashBools("policies.table" + std::to_string(i));
            Count("policies.chosen", N()); Words(N(), 0u);
            I32(-1); U32(0); U32(0xffffffffu); U32(0x11223344u);
            Version("policy_ai.version", 1); Count("policy_ai.weights", N());
            if (f.rich) {
                U32(0); Mark("policy_ai.zero_hash_weight"); U32(0x80000000u);
                U32(0xffffffffu); I32(-1); U32(0x87654321u); I32(12345);
            }
            Count("policies.flavors", N(), true); Words(N());
        });
        Section(2, [&] {
            Version("economic.version", 1); Count("economic.strategies", N(), true);
            for (std::uint32_t i = 0; i < N(); ++i) Bool("economic.strategy" + std::to_string(i), (i & 1u) != 0);
            Words(N()); Words(6, 0xf0000000u); Bool("economic.dirty", true);
            Count("economic.exploration", N()); Words(2u * N());
            Count("economic.goody", N()); Words(2u * N());
            Words(5); Count("economic.savings", N(), true); Words(3u * N());
        });
        Section(3, [&] {
            Version("city.version", 2); Bool("city.dirty", false); Bool("city.interrupt", true); Words(5);
        });
        Section(4, [&] {
            Version("wonder.version", 1); Count("wonder.flavors", N(), true); Words(N());
            HashInts("wonder.buildings", true);
        });
        Section(5, [&] {
            Version("military.version", 1); I32(-1); I32(-1); I32(-1);
            Count("military.strategies", N(), true);
            for (std::uint32_t i = 0; i < N(); ++i) Bool("military.strategy" + std::to_string(i), (i & 1u) != 0);
            Words(N());
            // Exactly MAX_CIV_PLAYERS=63, not MAX_PLAYERS=64 or storage80.
            for (unsigned column = 0; column < 4; ++column) Words(63, 0xff000000u + 256u * column);
        });
        Section(6, [&] {
            Version("grand.version", 1); I32(-1); I32(-1);
            Mark("grand.priorities"); Words(f.grand, 0xc0000000u);
            Words(22, 0xd0000000u); Words(22, 0xe0000000u);
        });
        f.end = f.bytes.size(); U32(4); U32(0xdac0ffeeu); Words(8, 1u);
        return f;
    }
};
std::array<RetailInflatedSpan, 7> Spans(const Result& r) {
    return {r.front, r.policies, r.economicAI, r.citySpecializationAI,
        r.wonderProductionAI, r.militaryAI, r.grandStrategyAI};
}
RetailSavePlayerProfile Profile(std::uint32_t grand) {
    return RetailSavePlayerProfile(grand, RetailPlayerCatalogProfile::InitializedBuildings);
}
Result Parse(const Fixture& f, const RetailSaveStateLimits& limits = RetailSaveStateLimits{}) {
    return RetailSavePlayerPrefix::InspectAt(f.bytes.data(), f.bytes.size(), f.start, Profile(f.grand), limits);
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
    const auto spans = Spans(r); std::size_t cursor = start;
    for (const auto span : spans) {
        s.Check(span.offset == cursor, "Player spans are not contiguous");
        s.Check(span.offset <= size && span.bytes <= size - span.offset, "Player span exceeds input");
        cursor = span.offset + span.bytes;
    }
    s.Check(cursor == r.nextInflatedOffset && cursor <= size, "Wrong Player next offset");
    s.Check(!r.completeSaveVerified && !r.rulesetCompatibilityVerified, "Player prefix granted restore/ruleset approval");
}
template<class F> void Reject(Suite& s, Code expected, const std::string& why, F action) {
    try { action(); } catch (const RetailStateError& error) {
        s.Check(error.Code() == expected, why + ": wrong typed error"); return;
    }
    s.Check(false, why + ": accepted malformed input");
}
void Golden(Suite& s, const Fixture& f) {
    const auto immutable = f.bytes; const auto r = Parse(f); Invariants(s, r, f.bytes.size(), f.start);
    const std::array<std::size_t, 7> literal = f.rich
        ? std::array<std::size_t, 7>{1545, 192, 164, 26, 44, 1043, 188u + 4u * f.grand}
        : std::array<std::size_t, 7>{1028, 60, 65, 26, 12, 1028, 188u + 4u * f.grand};
    const auto spans = Spans(r);
    for (std::size_t i = 0; i < spans.size(); ++i) {
        s.Check(f.spans[i].bytes == literal[i], "Independent writer disagrees with literal component size");
        s.Check(spans[i].offset == f.spans[i].offset && spans[i].bytes == literal[i], "Wrong Player component boundary");
    }
    s.Check(f.end - f.start == (f.rich ? 3202u : 2407u) + 4u * f.grand, "Wrong literal combined Player size");
    s.Check(r.nextInflatedOffset == f.end && r.playerId == f.id, "Wrong Player ID or final offset");
    s.Check(f.marks.at("front.id") - f.start == 864 &&
        f.marks.at("front.first_vector0") - f.start == 872, "Front literal scalar/bool layout changed");
    s.Check(Word(f.bytes, f.start) == 16 && Word(f.bytes, f.end) == 4 &&
        Word(f.bytes, f.end + 4) == 0xdac0ffeeu, "Literal version or opaque-tail sentinel changed");
    s.Check(f.records == (f.rich ? 159u : 0u) && r.arrayRecords == f.records,
        "Wrong declared row accounting; profile and fixed arrays are not count fields");
    if (f.rich) s.Check(Word(f.bytes, f.marks.at("policy_ai.zero_hash_weight")) == 0x80000000u,
        "Zero PolicyAI hash lost its mandatory weight");
    const auto exact = RetailSavePlayerPrefix::InspectAt(f.bytes.data(), f.end, f.start, Profile(f.grand));
    s.Check(exact.nextInflatedOffset == f.end, "Prefix required unread DiplomacyAI or trailing bytes");
    s.Check(f.bytes == immutable, "Golden inspection changed caller bytes");
}
void Cuts(Suite& s, const Fixture& f) {
    const auto immutable = f.bytes;
    for (std::size_t size = 0; size < f.end; ++size) {
        Reject(s, Code::Truncated, "Player prefix truncation", [&] {
            RetailSavePlayerPrefix::InspectAt(f.bytes.data(), size, f.start, Profile(f.grand));
        });
        ++s.truncations;
    }
    s.Check(f.bytes == immutable, "Truncation inspection modified input");
}
void Negative(Suite& s, const Fixture& empty, const Fixture& rich) {
    for (const auto* fixture : {&empty, &rich}) {
        const auto& f = *fixture;
        for (const auto at : f.versions) {
            for (std::uint32_t version : {0u, 0xffffffffu, Word(f.bytes, at) + 1u}) {
                auto bad = f; Put(bad.bytes, at, version);
                Reject(s, Code::UnsupportedVersion, "Nested Player version", [&] { Parse(bad); });
            }
        }
        for (const auto at : f.bools) {
            auto bad = f; bad.bytes[at] = 2;
            Reject(s, Code::InvalidValue, "Noncanonical Player bool", [&] { Parse(bad); });
        }
        for (const auto at : f.signedCounts) {
            auto bad = f; Put(bad.bytes, at, 0xffffffffu);
            Reject(s, Code::InvalidValue, "Negative Player count", [&] { Parse(bad); });
            Put(bad.bytes, at, 0x7fffffffu);
            Reject(s, Code::ArrayLimit, "Huge signed Player count", [&] { Parse(bad); });
        }
        for (const auto at : f.unsignedCounts) {
            auto bad = f; Put(bad.bytes, at, 0xffffffffu);
            Reject(s, Code::ArrayLimit, "Huge unsigned Player count", [&] { Parse(bad); });
        }
        auto limits = RetailSaveStateLimits{}; limits.maxPrefixBytes = f.end;
        s.Check(Parse(f, limits).nextInflatedOffset == f.end, "Exact Player prefix budget rejected");
        --limits.maxPrefixBytes;
        Reject(s, Code::PrefixLimit, "Short Player prefix budget", [&] { Parse(f, limits); });
        limits = RetailSaveStateLimits{}; limits.maxInputBytes = f.bytes.size();
        s.Check(Parse(f, limits).nextInflatedOffset == f.end, "Exact Player input budget rejected");
        --limits.maxInputBytes;
        Reject(s, Code::InputLimit, "Short Player input budget", [&] { Parse(f, limits); });
        limits = RetailSaveStateLimits{}; limits.maxArrayRecords = f.maximumArray; limits.maxTotalRecords = f.records;
        limits.maxStringBytes = f.rich ? 11u : 0u;
        s.Check(Parse(f, limits).arrayRecords == f.records, "Exact Player count/string budgets rejected");
        if (f.rich) {
            --limits.maxArrayRecords;
            Reject(s, Code::ArrayLimit, "Short Player array budget", [&] { Parse(f, limits); });
            limits.maxArrayRecords = f.maximumArray; --limits.maxTotalRecords;
            Reject(s, Code::TotalRecordLimit, "Short Player aggregate budget", [&] { Parse(f, limits); });
            limits.maxTotalRecords = f.records; limits.maxStringBytes = 10;
            Reject(s, Code::StringLimit, "Short Player narrow-string budget", [&] { Parse(f, limits); });
        }
    }
    for (const auto key : {"front.religion_length", "front.script_length"}) {
        auto bad = rich; Put(bad.bytes, bad.marks.at(key), 0xffffffffu);
        Reject(s, Code::StringLimit, "Oversized Player string", [&] { Parse(bad); });
    }
    Reject(s, Code::NullInput, "Null Player input", [&] {
        RetailSavePlayerPrefix::InspectAt(nullptr, 1, 0, Profile(0));
    });
    Reject(s, Code::Truncated, "Empty Player input", [&] {
        RetailSavePlayerPrefix::InspectAt(nullptr, 0, 0, Profile(0));
    });
    Reject(s, Code::Truncated, "Player start beyond input", [&] {
        RetailSavePlayerPrefix::InspectAt(empty.bytes.data(), empty.bytes.size(),
            (std::numeric_limits<std::size_t>::max)(), Profile(0));
    });
    Reject(s, Code::UnsupportedProfile, "Unbounded grand-strategy profile", [&] {
        RetailSavePlayerPrefix::InspectAt(empty.bytes.data(), empty.bytes.size(), empty.start, Profile(4097));
    });
    Reject(s, Code::UnsupportedProfile, "Unrecognized building-catalog branch", [&] {
        RetailSavePlayerPrefix::InspectAt(empty.bytes.data(), empty.bytes.size(), empty.start,
            RetailSavePlayerProfile(0, static_cast<RetailPlayerCatalogProfile>(-1)));
    });
    auto zero = RetailSaveStateLimits{}; zero.maxInputBytes = 0;
    Reject(s, Code::InputLimit, "Zero Player input budget", [&] { Parse(empty, zero); });
    zero = RetailSaveStateLimits{}; zero.maxPrefixBytes = 0;
    Reject(s, Code::PrefixLimit, "Zero Player prefix budget", [&] { Parse(empty, zero); });
    zero = RetailSaveStateLimits{}; zero.maxArrayRecords = 0;
    Reject(s, Code::ArrayLimit, "Zero Player array budget", [&] { Parse(rich, zero); });
    zero = RetailSaveStateLimits{}; zero.maxTotalRecords = 0;
    Reject(s, Code::TotalRecordLimit, "Zero Player aggregate budget", [&] { Parse(rich, zero); });
    auto maximum = empty.bytes;
    maximum.insert(maximum.begin() + static_cast<std::ptrdiff_t>(empty.marks.at("grand.priorities")),
        4096u * 4u, static_cast<unsigned char>(0xab));
    const auto immutableMaximum = maximum;
    const auto upper = RetailSavePlayerPrefix::InspectAt(maximum.data(), maximum.size(), empty.start, Profile(4096));
    s.Check(upper.nextInflatedOffset == empty.end + 16384u, "Exact supported grand-strategy width rejected");
    s.Check(!upper.rulesetCompatibilityVerified && maximum == immutableMaximum, "Profile limit check changed input or approved ruleset");
    // A wrong but supported explicit width changes framing. There is no magic
    // scan or inferred width, and neither outcome proves ruleset compatibility.
    const auto explicitWidth = RetailSavePlayerPrefix::InspectAt(rich.bytes.data(), rich.bytes.size(),
        rich.start, Profile(rich.grand + 1));
    s.Check(explicitWidth.nextInflatedOffset == rich.end + 4 && !explicitWidth.rulesetCompatibilityVerified,
        "Inspector inferred a grand-strategy width from following bytes");
}
struct Observation {
    bool accepted = false;
    Result result;
    Code code = Code::InvalidValue;
    std::size_t offset = 0;
};
Observation Observe(const Bytes& bytes, std::size_t start, std::uint32_t grand) {
    Observation o;
    try {
        o.result = RetailSavePlayerPrefix::InspectAt(bytes.data(), bytes.size(), start, Profile(grand));
        o.accepted = true;
    } catch (const RetailStateError& e) { o.code = e.Code(); o.offset = e.Offset(); }
    return o;
}
bool Same(const Observation& a, const Observation& b) {
    if (a.accepted != b.accepted) return false;
    if (!a.accepted) return a.code == b.code && a.offset == b.offset;
    const auto left = Spans(a.result), right = Spans(b.result);
    for (std::size_t i = 0; i < left.size(); ++i)
        if (left[i].offset != right[i].offset || left[i].bytes != right[i].bytes) return false;
    return a.result.playerId == b.result.playerId && a.result.nextInflatedOffset == b.result.nextInflatedOffset &&
        a.result.arrayRecords == b.result.arrayRecords && a.result.completeSaveVerified == b.result.completeSaveVerified &&
        a.result.rulesetCompatibilityVerified == b.result.rulesetCompatibilityVerified;
}
std::uint32_t Random(std::uint32_t& state) {
    state ^= state << 13; state ^= state >> 17; state ^= state << 5; return state;
}
void Mutations(Suite& s, const std::vector<Fixture>& fixtures) {
    std::uint32_t random = 0x24c5a17bu;
    for (std::size_t i = 0; i < 2048; ++i) {
        const auto& f = fixtures[(i / 8) % fixtures.size()]; auto bytes = f.bytes; auto grand = f.grand;
        switch (i % 8) {
        case 0: bytes[Random(random) % bytes.size()] ^= static_cast<unsigned char>(1u << (Random(random) % 8)); break;
        case 1: Put(bytes, f.versions[Random(random) % f.versions.size()], Random(random)); break;
        case 2: bytes[f.bools[Random(random) % f.bools.size()]] = 2; break;
        case 3: {
            const auto& counts = (Random(random) & 1u) ? f.signedCounts : f.unsignedCounts;
            Put(bytes, counts[Random(random) % counts.size()], 0xffffffffu); break;
        }
        case 4: bytes.resize(Random(random) % (bytes.size() + 1)); break;
        case 5: grand = (Random(random) & 1u) ? 4097u : Random(random) % 8u; break;
        case 6: bytes.push_back(static_cast<unsigned char>(Random(random))); break;
        default: Put(bytes, Random(random) % (bytes.size() - 3), Random(random)); break;
        }
        const auto immutable = bytes;
        const auto first = Observe(bytes, f.start, grand), second = Observe(bytes, f.start, grand);
        s.Check(Same(first, second), "Player mutation outcome was nondeterministic");
        s.Check(bytes == immutable, "Player mutation inspection modified input");
        if (first.accepted) { Invariants(s, first.result, bytes.size(), f.start); ++s.accepted; }
        else { s.Check(first.offset <= bytes.size(), "Player error offset exceeds input"); ++s.rejected; }
        ++s.mutations;
    }
    s.Check(s.accepted != 0 && s.rejected != 0, "Player mutations did not exercise both outcomes");
}
Bytes ReadStdin() {
#if defined(_WIN32)
    if (_setmode(_fileno(stdin), _O_BINARY) == -1) throw std::runtime_error("Cannot set stdin binary mode");
#endif
    constexpr std::size_t maximum = 64u * 1024u * 1024u;
    Bytes bytes; std::array<char, 65536> chunk{};
    for (;;) {
        std::cin.read(chunk.data(), static_cast<std::streamsize>(chunk.size()));
        const auto read = std::cin.gcount();
        if (read < 0) throw std::runtime_error("Negative stdin byte count");
        const auto count = static_cast<std::size_t>(read);
        if (count > maximum - bytes.size()) throw std::runtime_error("Public stdin exceeds input budget");
        const auto* begin = reinterpret_cast<const unsigned char*>(chunk.data());
        bytes.insert(bytes.end(), begin, begin + count);
        if (count < chunk.size()) break;
    }
    if (std::cin.bad() || (!std::cin.eof() && std::cin.fail())) throw std::runtime_error("Failed to read public stdin");
    return bytes;
}
struct PublicResult { Result player; std::size_t bytes = 0, mapEnd = 0, teamsEnd = 0; std::uint32_t diplomacyVersion = 0; };
PublicResult Public(Suite& s) {
    const auto bytes = ReadStdin(); const auto immutable = bytes;
    s.Check(bytes.size() == 9762327u, "Wrong public inflated corpus length");
    // Profile five and explicit G=4 are structural hypotheses, not verified
    // ruleset compatibility. The root harness separately authenticates SHA256.
    auto limits = RetailSaveStateLimits{};
    const auto map = RetailSaveMap::InspectGameAndMap(bytes, RetailSaveStateProfile(5), limits);
    s.Check(map.nextInflatedOffset == 1695150u && map.plotCount == 960u, "Public ordered Map boundary changed");
    s.Check(!map.completeSaveVerified && !map.rulesetCompatibilityVerified, "Public Map granted approval");
    s.Check(map.arrayRecords <= limits.maxTotalRecords, "Public Map exceeded record budget");
    limits.maxTotalRecords -= map.arrayRecords;
    RetailStateDetail::Reader teams(bytes.data(), bytes.size(), limits); teams.Skip(map.nextInflatedOffset);
    for (std::int32_t id = 0; id < 64; ++id)
        s.Check(RetailStateDetail::ReadTeam(teams) == id, "Public Team IDs are not sequential 0..63");
    s.Check(teams.Pos() == 2309550u, "Public Player start changed after 64 ordered Teams");
    s.Check(teams.Records() <= limits.maxTotalRecords, "Public Teams exceeded shared record budget");
    limits.maxTotalRecords -= teams.Records();
    PublicResult result; result.bytes = bytes.size(); result.mapEnd = map.nextInflatedOffset; result.teamsEnd = teams.Pos();
    result.player = RetailSavePlayerPrefix::InspectAt(bytes.data(), bytes.size(), teams.Pos(), Profile(4), limits);
    Invariants(s, result.player, bytes.size(), teams.Pos());
    s.Check(result.player.playerId == 0, "Public first Player ID is not zero");
    RetailStateDetail::Reader following(bytes.data(), bytes.size(), RetailSaveStateLimits{});
    following.Skip(result.player.nextInflatedOffset); result.diplomacyVersion = following.U32();
    s.Check(result.diplomacyVersion == 4, "Following unread public DiplomacyAI version is not four");
    s.Check(bytes == immutable, "Public Player inspection modified stdin bytes"); return result;
}
void PublicJson(const PublicResult& p) {
    std::cout << ",\"public\":{\"input_bytes\":" << p.bytes << ",\"map_end\":" << p.mapEnd
        << ",\"teams_start\":" << p.mapEnd << ",\"teams_end\":" << p.teamsEnd << ",\"team_count\":64"
        << ",\"player_start\":" << p.player.front.offset << ",\"player_id\":" << p.player.playerId;
    const std::array<const char*, 7> names = {"front", "policies", "economic_ai", "city_specialization_ai",
        "wonder_production_ai", "military_ai", "grand_strategy_ai"};
    const auto spans = Spans(p.player);
    for (std::size_t i = 0; i < names.size(); ++i)
        std::cout << ",\"" << names[i] << "_offset\":" << spans[i].offset << ",\"" << names[i] << "_bytes\":" << spans[i].bytes;
    std::cout << ",\"next_inflated_offset\":" << p.player.nextInflatedOffset << ",\"array_records\":" << p.player.arrayRecords
        << ",\"diplomacy_version\":" << p.diplomacyVersion << ",\"grand_strategy_count\":4,\"profile_ruleset_verified\":false}";
}
std::string Escape(const char* raw) {
    std::string result;
    for (const unsigned char c : std::string(raw)) {
        if (c == '"' || c == '\\') { result += '\\'; result += static_cast<char>(c); }
        else if (c >= 32 && c < 127) result += static_cast<char>(c);
        else result += '?';
    }
    return result;
}
} // namespace

int main(int argc, char** argv) {
    Suite suite;
    try {
        static_assert(sizeof(void*) == 8, "This component test requires x64");
        const bool publicMode = argc == 2 && std::strcmp(argv[1], "--public") == 0;
        if (argc != 1 && !publicMode) throw std::invalid_argument("Usage: retail_player_prefix [--public]");
        const std::vector<Fixture> fixtures = {Writer(false, 0, 0, 0).Finish(), Writer(true, 1, 13, 63).Finish(),
            Writer(false, 4, 7, 0).Finish(), Writer(true, 7, 19, 17).Finish()};
        for (const auto& f : fixtures) { Golden(suite, f); Cuts(suite, f); }
        Negative(suite, fixtures[0], fixtures[1]); Mutations(suite, fixtures);
        PublicResult publicResult; if (publicMode) publicResult = Public(suite);
        std::cout << "{\"status\":\"PASS_RETAIL_PLAYER_PREFIX_COMPONENT\",\"checks\":" << suite.checks
            << ",\"synthetic_cases\":4,\"truncations\":" << suite.truncations << ",\"mutations\":" << suite.mutations
            << ",\"accepted_mutations\":" << suite.accepted << ",\"rejected_mutations\":" << suite.rejected
            << ",\"input_files_unchanged\":true,\"input_bytes_unchanged\":true,\"gamecore_loaded\":false,\"window_created\":false"
            << ",\"game_accessed\":false,\"user_saves_accessed\":false,\"complete_player_validated\":false"
            << ",\"complete_save_validated\":false,\"ruleset_compatibility_verified\":false,\"restore_approved\":false";
        if (publicMode) PublicJson(publicResult);
        std::cout << "}\n"; return 0;
    } catch (const std::exception& error) {
        std::cout << "{\"status\":\"FAIL_RETAIL_PLAYER_PREFIX_COMPONENT\",\"checks\":" << suite.checks
            << ",\"error\":\"" << Escape(error.what()) << "\",\"gamecore_loaded\":false,\"window_created\":false"
            << ",\"user_saves_accessed\":false,\"complete_player_validated\":false,\"complete_save_validated\":false"
            << ",\"ruleset_compatibility_verified\":false,\"restore_approved\":false}\n"; return 1;
    }
}
