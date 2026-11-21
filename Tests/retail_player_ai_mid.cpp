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

// Independent source-wire writer, not an SDK/private-envelope serializer:
// CvDiplomacyAI.cpp:1527-1747,26192-26215; CvReligionClasses.cpp:2248-2255,
// 4182-4187; CvTechClasses.cpp:823-849; CvTechAI.cpp:78-98;
// CvFlavorManager.cpp:264-274; CvTacticalAI.cpp:191-201,342-350;
// CvHomelandAI.cpp:87-94. All references are SDK_BNW_Original.
// No game, SDK state, database, user-save or file-path input is accessed.
namespace {
using namespace ZeroSisHost;
using Bytes = std::vector<unsigned char>;
using Code = RetailStateErrorCode;
using Result = decltype(RetailSavePlayerAiMid::InspectAt(nullptr, std::size_t{}, std::size_t{},
    RetailPlayerAiMidCatalogProfile::InitializedTechs));
struct Suite {
    std::size_t checks = 0, truncations = 0, mutations = 0, accepted = 0, rejected = 0;
    void Check(bool value, const std::string& reason) {
        ++checks; if (!value) throw std::runtime_error(reason);
    }
};
struct Fixture {
    Bytes bytes;
    bool rich = false;
    std::uint32_t zones = 0, flavors = 0;
    std::size_t start = 0, end = 0, records = 0, maxArray = 0;
    std::array<RetailInflatedSpan, 7> spans{};
    std::vector<std::size_t> versions, bools, signedCounts, unsignedCounts, navalInts;
    std::map<std::string, std::size_t> marks;
};
class Writer {
public:
    Fixture f;
    Writer(bool rich, std::uint32_t zones, std::uint32_t flavors, std::size_t start) {
        f.rich = rich; f.zones = zones; f.flavors = flavors; f.start = start;
        f.bytes.assign(start, static_cast<unsigned char>(0x78));
        if (start >= 4) { f.bytes[0] = 4; f.bytes[1] = 0; f.bytes[2] = 0; f.bytes[3] = 0; }
    }
    void Mark(const std::string& name) { f.marks[name] = f.bytes.size(); }
    void U8(unsigned char value) { f.bytes.push_back(value); }
    void U16(std::uint16_t value) { U8(static_cast<unsigned char>(value)); U8(static_cast<unsigned char>(value >> 8)); }
    void U32(std::uint32_t value) {
        for (unsigned i = 0; i < 4; ++i) U8(static_cast<unsigned char>(value >> (8 * i)));
    }
    void I32(std::int32_t value) { U32(static_cast<std::uint32_t>(value)); }
    void Words(std::size_t count, std::uint32_t seed = 0x80010000u) {
        for (std::size_t i = 0; i < count; ++i) U32(seed + static_cast<std::uint32_t>(i));
    }
    void Chars(std::size_t count) {
        const std::array<unsigned char, 4> raw = {0xff, 0x80, 0x78, 0x9c};
        for (std::size_t i = 0; i < count; ++i) U8(raw[i % raw.size()]);
    }
    void Shorts(std::size_t count) {
        const std::array<std::uint16_t, 4> raw = {0xffff, 0x8000, 0x7fff, 0};
        for (std::size_t i = 0; i < count; ++i) U16(raw[i % raw.size()]);
    }
    void Bool(bool value) { f.bools.push_back(f.bytes.size()); U8(value ? 1 : 0); }
    void Bools(std::size_t count) { for (std::size_t i = 0; i < count; ++i) Bool((i & 1u) != 0); }
    void Version(const std::string& name, std::uint32_t value) {
        Mark(name); f.versions.push_back(f.bytes.size()); U32(value);
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
    template<class F> void Section(std::size_t at, F write) {
        const auto start = f.bytes.size(); write(); f.spans[at] = {start, f.bytes.size() - start};
    }
    void Diplomacy() {
        Version("diplomacy.version", 4); Chars(22);
        Mark("diplomacy.major_matrix");
        // Each of 22 rows owns char/bool/short/char/short arrays of 22.
        for (unsigned row = 0; row < 22; ++row) { Chars(22); Bools(22); Shorts(22); Chars(22); Shorts(22); }
        Chars(22); Chars(41); Chars(22); Chars(22);
        Shorts(63); Bools(63); Bools(22); Bools(41);
        Shorts(63); Chars(22); Chars(22);
        for (unsigned column = 0; column < 5; ++column) Chars(63);
        Shorts(63); Shorts(63);
        for (unsigned column = 0; column < 3; ++column) Chars(63);
        for (unsigned column = 0; column < 5; ++column) Chars(63);
        Mark("diplomacy.other_matrix");
        // Source loops are 63x63, not MAX_PLAYERS=64 or native storage80.
        for (unsigned row = 0; row < 63; ++row) {
            Chars(63); Chars(63); Chars(63); Words(63); Chars(63);
        }
        Mark("diplomacy.lost_matrix");
        for (unsigned row = 0; row < 63; ++row) { Words(63); Bools(63); }
        Chars(63); Words(63);
        for (unsigned column = 0; column < 6; ++column) Chars(63);

        // No-settle, stop-spying, demand, friendship and denouncement fields.
        Bools(22); Shorts(22); Bools(22); Shorts(22); Shorts(22); Shorts(22);
        Bools(22); Shorts(22); Bools(22); Bools(22); Shorts(22); Bools(22);
        // Requests, civilians, landmarks, resurrection, culture, religion,
        // archaeology, nukes, robbery, intrigue and eight relationship values.
        for (unsigned column = 0; column < 18; ++column) Shorts(22);

        Bools(22); Bools(22); Bools(22); Shorts(22); // Military promises.
        Shorts(22); Bools(22); Bools(22); Chars(22); // Expansion promise.
        Shorts(22); Bools(22); Bools(22); Chars(22); // Border promise.
        for (unsigned column = 0; column < 3; ++column) Bools(22); // Attack a city-state.
        for (unsigned column = 0; column < 3; ++column) Bools(22); // Bully a city-state.
        for (unsigned column = 0; column < 3; ++column) Bools(22); // Spying.
        Bools(22); // Forgave spying.
        for (unsigned column = 0; column < 5; ++column) Bools(22); // Religion promises.
        for (unsigned column = 0; column < 5; ++column) Bools(22); // Archaeology promises.
        Bools(22); // Broken cooperative-war promise.
        // CvDiplomacyAI.h:1342 stores this Player-like field as char, not
        // PlayerTypes. Its direct stream insertion therefore owns ONE byte.
        Mark("diplomacy.demand_target"); U8(0xff);
        Mark("diplomacy.demand_ready"); Bool(true);
        Mark("diplomacy.personality"); Words(13);
        Mark("diplomacy.approaches");
        Chars(7); Chars(5); // Enum counts in CvDiplomacyAIEnums.h:28-54.
        Shorts(22); Chars(22); Chars(22); // Protected minor attacked.
        Shorts(22); Chars(22); Chars(22); // Protected minor killed.
        Chars(22); Shorts(22);
        for (unsigned column = 0; column < 4; ++column) Chars(22);
        Words(22);
        for (unsigned column = 0; column < 6; ++column) Shorts(22);
        Mark("diplomacy.logs");
        for (unsigned player = 0; player < 22; ++player)
            for (unsigned entry = 0; entry < 60; ++entry) { I32(-1); U32(0x80000000u + entry); }
        Mark("diplomacy.declarations");
        for (unsigned entry = 0; entry < 60; ++entry) { Words(4); Bool((entry & 1u) != 0); I32(-1); }
        Mark("diplomacy.all_wars"); I32(-1); // Enum, no additional padding or count.
    }
    Fixture Finish() {
        Section(0, [&] { Diplomacy(); });
        Section(1, [&] {
            Version("religions.version", 1); I32(-1);
            Mark("religions.founding_int"); I32(f.rich ? -1 : 2);
        });
        Section(2, [&] { Version("religion_ai.version", 1); });
        Section(3, [&] {
            Version("techs.version", 1); Count("techs.researching", N());
            if (f.rich) { U32(0); U32(0xffffffffu); Bool(false); U32(0x12345678u); Bool(true); }
            for (unsigned column = 0; column < 6; ++column) HashInts("techs.column" + std::to_string(column));
            Version("tech_ai.version", 1); Count("tech_ai.weights", N());
            if (f.rich) {
                U32(0); Mark("tech_ai.zero_weight"); U32(0x80000000u);
                U32(0xffffffffu); I32(-1); U32(0x87654321u); I32(12345);
            }
            Count("techs.flavors", f.rich ? 3u : 0u, true); Words(f.rich ? 3u : 0u);
        });
        Section(4, [&] {
            Version("flavors.version", 1); Count("flavors.count", f.flavors, true);
            Words(f.flavors, 0x80000000u); Words(f.flavors, 0xffffffffu - f.flavors);
        });
        Section(5, [&] {
            Version("tactical.version", 1); I32(0); Count("tactical.zones", f.zones);
            for (std::uint32_t zone = 0; zone < f.zones; ++zone) {
                Version("zone.version" + std::to_string(zone), 1); Words(4);
                f.navalInts.push_back(f.bytes.size()); I32((zone & 1u) != 0 ? 1 : 0);
            }
        });
        Section(6, [&] { Version("homeland.version", 1); U32(0x80000000u); });
        f.end = f.bytes.size(); U32(1); U32(0xc5a1c0deu); Words(8, 4u);
        return f;
    }
};
std::array<RetailInflatedSpan, 7> Spans(const Result& r) {
    return {r.diplomacyAI, r.playerReligions, r.religionAI, r.playerTechs, r.flavorManager, r.tacticalAI, r.homelandAI};
}
Result Parse(const Fixture& f, const RetailSaveStateLimits& limits = RetailSaveStateLimits{}) {
    return RetailSavePlayerAiMid::InspectAt(f.bytes.data(), f.bytes.size(), f.start,
        RetailPlayerAiMidCatalogProfile::InitializedTechs, limits);
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
        s.Check(span.offset == cursor, "Mid-AI spans are not contiguous");
        s.Check(span.offset <= size && span.bytes <= size - span.offset, "Mid-AI span exceeds input");
        cursor = span.offset + span.bytes;
    }
    s.Check(cursor == r.nextInflatedOffset && cursor <= size, "Wrong mid-AI next offset");
    s.Check(!r.completeSaveVerified && !r.rulesetCompatibilityVerified, "Mid-AI inspector granted restore or ruleset approval");
}
template<class F> void Reject(Suite& s, Code code, const std::string& reason, F action) {
    try { action(); } catch (const RetailStateError& e) { s.Check(e.Code() == code, reason + ": wrong error"); return; }
    s.Check(false, reason + ": malformed input accepted");
}
void Golden(Suite& s, const Fixture& f) {
    const auto immutable = f.bytes; const auto r = Parse(f); Invariants(s, r, f.bytes.size(), f.start);
    const std::array<std::size_t, 7> literal = {71856, 12, 4, f.rich ? 214u : 44u,
        8u + 8u * f.flavors, 12u + 24u * f.zones, 8};
    const auto actual = Spans(r);
    for (std::size_t i = 0; i < actual.size(); ++i) {
        s.Check(f.spans[i].bytes == literal[i], "Independent fixture disagrees with literal source byte count");
        s.Check(actual[i].offset == f.spans[i].offset && actual[i].bytes == literal[i], "Wrong mid-AI component boundary");
    }
    s.Check(f.end - f.start == 71944u + (f.rich ? 170u : 0u) + 8u * f.flavors + 24u * f.zones,
        "Wrong literal combined mid-AI bytes");
    s.Check(f.marks.at("diplomacy.major_matrix") - f.start == 26 &&
        f.marks.at("diplomacy.other_matrix") - f.start == 5014 &&
        f.marks.at("diplomacy.lost_matrix") - f.start == 36766 &&
        f.marks.at("diplomacy.demand_target") - f.start == 59284 &&
        f.marks.at("diplomacy.demand_ready") - f.start == 59285 &&
        f.marks.at("diplomacy.personality") - f.start == 59286 &&
        f.marks.at("diplomacy.approaches") - f.start == 59338 &&
        f.marks.at("diplomacy.logs") - f.start == 60032 &&
        f.marks.at("diplomacy.declarations") - f.start == 70592 &&
        f.marks.at("diplomacy.all_wars") - f.start == 71852, "Literal Diplomacy checkpoints changed");
    s.Check(f.bools.size() == (f.rich ? 5390u : 5388u), "Wrong source bool count or native-padding assumption");
    const auto literalRows = (f.rich ? 27u : 0u) + f.flavors + f.zones;
    s.Check(f.records == literalRows && r.arrayRecords == literalRows, "Wrong declared mid-AI record count");
    s.Check(r.nextInflatedOffset == f.end && Word(f.bytes, f.end) == 1 &&
        Word(f.bytes, f.end + 4) == 0xc5a1c0deu, "Inspector consumed the unread MinorCivAI marker");
    if (f.rich) s.Check(Word(f.bytes, f.marks.at("tech_ai.zero_weight")) == 0x80000000u,
        "Zero TechAI hash lost mandatory weight");
    const auto exact = RetailSavePlayerAiMid::InspectAt(f.bytes.data(), f.end, f.start,
        RetailPlayerAiMidCatalogProfile::InitializedTechs);
    s.Check(exact.nextInflatedOffset == f.end, "Mid-AI framing required unread following data");
    s.Check(f.bytes == immutable, "Golden mid-AI framing modified input");
}
void Cuts(Suite& s, const Fixture& f) {
    const auto immutable = f.bytes;
    // Every byte of one populated complete prefix is cut, including all fixed
    // Diplomacy bytes and every nested record. Other fixtures avoid repeating
    // the identical 71,856-byte fixed Diplomacy traversal unnecessarily.
    for (std::size_t size = 0; size < f.end; ++size) {
        Reject(s, Code::Truncated, "Mid-AI prefix truncation", [&] {
            RetailSavePlayerAiMid::InspectAt(f.bytes.data(), size, f.start, RetailPlayerAiMidCatalogProfile::InitializedTechs);
        });
        ++s.truncations;
    }
    s.Check(f.bytes == immutable, "Mid-AI truncation test modified input");
}
void Negative(Suite& s, const Fixture& empty, const Fixture& rich) {
    for (const auto* fixture : {&empty, &rich}) {
        const auto& f = *fixture;
        for (const auto at : f.versions) {
            for (std::uint32_t version : {0u, 0xffffffffu, Word(f.bytes, at) + 1u}) {
                auto bad = f; Put(bad.bytes, at, version);
                Reject(s, Code::UnsupportedVersion, "Mid-AI nested version", [&] { Parse(bad); });
            }
        }
        for (const auto at : f.signedCounts) {
            auto bad = f; Put(bad.bytes, at, 0xffffffffu);
            Reject(s, Code::InvalidValue, "Negative mid-AI signed count", [&] { Parse(bad); });
            Put(bad.bytes, at, 0x7fffffffu);
            Reject(s, Code::ArrayLimit, "Huge mid-AI signed count", [&] { Parse(bad); });
        }
        for (const auto at : f.unsignedCounts) {
            auto bad = f; Put(bad.bytes, at, 0xffffffffu);
            Reject(s, Code::ArrayLimit, "Huge mid-AI unsigned count", [&] { Parse(bad); });
        }
        auto limits = RetailSaveStateLimits{}; limits.maxPrefixBytes = f.end;
        s.Check(Parse(f, limits).nextInflatedOffset == f.end, "Exact mid-AI prefix budget rejected");
        --limits.maxPrefixBytes;
        Reject(s, Code::PrefixLimit, "Short mid-AI prefix budget", [&] { Parse(f, limits); });
        limits = RetailSaveStateLimits{}; limits.maxInputBytes = f.bytes.size();
        s.Check(Parse(f, limits).nextInflatedOffset == f.end, "Exact mid-AI input budget rejected");
        --limits.maxInputBytes;
        Reject(s, Code::InputLimit, "Short mid-AI input budget", [&] { Parse(f, limits); });
        limits = RetailSaveStateLimits{}; limits.maxArrayRecords = f.maxArray; limits.maxTotalRecords = f.records;
        limits.maxStringBytes = 0;
        s.Check(Parse(f, limits).arrayRecords == f.records, "Exact mid-AI count budgets or zero string budget rejected");
        if (f.rich) {
            --limits.maxArrayRecords;
            Reject(s, Code::ArrayLimit, "Short mid-AI array budget", [&] { Parse(f, limits); });
            limits.maxArrayRecords = f.maxArray; --limits.maxTotalRecords;
            Reject(s, Code::TotalRecordLimit, "Short mid-AI aggregate budget", [&] { Parse(f, limits); });
        }
    }
    for (const auto at : rich.bools) {
        auto bytes = rich.bytes; bytes[at] = 2;
        Reject(s, Code::InvalidValue, "Noncanonical mid-AI bool byte", [&] {
            RetailSavePlayerAiMid::InspectAt(bytes.data(), bytes.size(), rich.start, RetailPlayerAiMidCatalogProfile::InitializedTechs);
        });
    }
    for (std::uint32_t scalar : {2u, 0xffffffffu, 0x80000000u}) {
        auto changed = rich; Put(changed.bytes, changed.marks.at("religions.founding_int"), scalar);
        for (const auto at : changed.navalInts) Put(changed.bytes, at, scalar);
        s.Check(Parse(changed).nextInflatedOffset == rich.end,
            "PlayerReligions or naval int was incorrectly treated as a bool byte");
    }
    Reject(s, Code::NullInput, "Null mid-AI input", [&] {
        RetailSavePlayerAiMid::InspectAt(nullptr, 1, 0, RetailPlayerAiMidCatalogProfile::InitializedTechs);
    });
    Reject(s, Code::Truncated, "Empty mid-AI input", [&] {
        RetailSavePlayerAiMid::InspectAt(nullptr, 0, 0, RetailPlayerAiMidCatalogProfile::InitializedTechs);
    });
    Reject(s, Code::Truncated, "Mid-AI start beyond input", [&] {
        RetailSavePlayerAiMid::InspectAt(empty.bytes.data(), empty.bytes.size(),
            (std::numeric_limits<std::size_t>::max)(), RetailPlayerAiMidCatalogProfile::InitializedTechs);
    });
    Reject(s, Code::UnsupportedProfile, "Unrecognized initialized-tech profile", [&] {
        RetailSavePlayerAiMid::InspectAt(empty.bytes.data(), empty.bytes.size(), empty.start,
            static_cast<RetailPlayerAiMidCatalogProfile>(-1));
    });
    Reject(s, Code::UnsupportedProfile, "Tech profile must reject before reading bytes", [&] {
        RetailSavePlayerAiMid::InspectAt(nullptr, 0, (std::numeric_limits<std::size_t>::max)(),
            static_cast<RetailPlayerAiMidCatalogProfile>(-1));
    });
    auto limits = RetailSaveStateLimits{}; limits.maxInputBytes = 0;
    Reject(s, Code::InputLimit, "Zero mid-AI input budget", [&] { Parse(empty, limits); });
    limits = RetailSaveStateLimits{}; limits.maxPrefixBytes = 0;
    Reject(s, Code::PrefixLimit, "Zero mid-AI prefix budget", [&] { Parse(empty, limits); });
    limits = RetailSaveStateLimits{}; limits.maxArrayRecords = 0;
    Reject(s, Code::ArrayLimit, "Zero mid-AI array budget", [&] { Parse(rich, limits); });
    limits = RetailSaveStateLimits{}; limits.maxTotalRecords = 0;
    Reject(s, Code::TotalRecordLimit, "Zero mid-AI aggregate budget", [&] { Parse(rich, limits); });
}
struct Observation { bool accepted = false; Result result; Code code = Code::InvalidValue; std::size_t offset = 0; };
Observation Observe(const Bytes& bytes, std::size_t start, bool validProfile) {
    Observation o;
    try {
        o.result = RetailSavePlayerAiMid::InspectAt(bytes.data(), bytes.size(), start, validProfile
            ? RetailPlayerAiMidCatalogProfile::InitializedTechs : static_cast<RetailPlayerAiMidCatalogProfile>(-1));
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
    return a.result.nextInflatedOffset == b.result.nextInflatedOffset && a.result.arrayRecords == b.result.arrayRecords &&
        a.result.completeSaveVerified == b.result.completeSaveVerified &&
        a.result.rulesetCompatibilityVerified == b.result.rulesetCompatibilityVerified;
}
std::uint32_t Random(std::uint32_t& value) {
    value ^= value << 13; value ^= value >> 17; value ^= value << 5; return value;
}
void Mutations(Suite& s, const std::vector<Fixture>& fixtures) {
    std::uint32_t random = 0xc5d1047bu;
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
        const auto immutable = bytes; const auto first = Observe(bytes, f.start, validProfile), second = Observe(bytes, f.start, validProfile);
        s.Check(Same(first, second), "Mid-AI mutation result was nondeterministic");
        s.Check(bytes == immutable, "Mid-AI mutation changed caller bytes");
        if (first.accepted) { Invariants(s, first.result, bytes.size(), f.start); ++s.accepted; }
        else { s.Check(first.offset <= bytes.size(), "Mid-AI error offset exceeds input"); ++s.rejected; }
        ++s.mutations;
    }
    s.Check(s.accepted != 0 && s.rejected != 0, "Mid-AI mutations missed accepted or rejected outcomes");
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
struct PublicResult { Result mid; std::size_t bytes = 0, teamsEnd = 0, prefixEnd = 0; std::uint32_t minorVersion = 0; };
PublicResult Public(Suite& s) {
    const auto bytes = ReadStdin(); const auto immutable = bytes;
    s.Check(bytes.size() == 9762327u, "Wrong public inflated corpus size");
    // External profiles Game=5, GrandStrategy=4, initialized catalogs are
    // structural hypotheses only. Root authenticates the public SHA in RAM.
    auto remaining = RetailSaveStateLimits{};
    const auto map = RetailSaveMap::InspectGameAndMap(bytes, RetailSaveStateProfile(5), remaining);
    s.Check(map.nextInflatedOffset == 1695150u && map.plotCount == 960u, "Public ordered Map boundary changed");
    s.Check(map.arrayRecords <= remaining.maxTotalRecords, "Map exceeded shared row budget");
    remaining.maxTotalRecords -= map.arrayRecords;
    RetailStateDetail::Reader teams(bytes.data(), bytes.size(), remaining); teams.Skip(map.nextInflatedOffset);
    for (std::int32_t id = 0; id < 64; ++id)
        s.Check(RetailStateDetail::ReadTeam(teams) == id, "Public team IDs are not sequential 0..63");
    s.Check(teams.Pos() == 2309550u && teams.Records() <= remaining.maxTotalRecords, "Public ordered Team boundary changed");
    remaining.maxTotalRecords -= teams.Records();
    const auto prefix = RetailSavePlayerPrefix::InspectAt(bytes.data(), bytes.size(), teams.Pos(),
        RetailSavePlayerProfile(4, RetailPlayerCatalogProfile::InitializedBuildings), remaining);
    s.Check(prefix.playerId == 0 && prefix.nextInflatedOffset == 2326136u, "Public Player prefix boundary changed");
    s.Check(!map.completeSaveVerified && !map.rulesetCompatibilityVerified && !prefix.completeSaveVerified &&
        !prefix.rulesetCompatibilityVerified, "Earlier public component granted compatibility approval");
    s.Check(prefix.arrayRecords <= remaining.maxTotalRecords, "Player prefix exceeded shared row budget");
    remaining.maxTotalRecords -= prefix.arrayRecords;
    PublicResult result; result.bytes = bytes.size(); result.teamsEnd = teams.Pos(); result.prefixEnd = prefix.nextInflatedOffset;
    result.mid = RetailSavePlayerAiMid::InspectAt(bytes.data(), bytes.size(), prefix.nextInflatedOffset,
        RetailPlayerAiMidCatalogProfile::InitializedTechs, remaining);
    Invariants(s, result.mid, bytes.size(), prefix.nextInflatedOffset);
    RetailStateDetail::Reader following(bytes.data(), bytes.size(), RetailSaveStateLimits{});
    following.Skip(result.mid.nextInflatedOffset); result.minorVersion = following.U32();
    s.Check(result.minorVersion == 1, "Following unread MinorCivAI source version is not one");
    s.Check(bytes == immutable, "Public mid-AI inspection changed stdin bytes"); return result;
}
void PublicJson(const PublicResult& p) {
    std::cout << ",\"public\":{\"input_bytes\":" << p.bytes << ",\"teams_end\":" << p.teamsEnd
        << ",\"player_prefix_end\":" << p.prefixEnd << ",\"start_offset\":" << p.prefixEnd;
    const std::array<const char*, 7> names = {"diplomacy_ai", "player_religions", "religion_ai", "player_techs",
        "flavor_manager", "tactical_ai", "homeland_ai"};
    const auto spans = Spans(p.mid);
    for (std::size_t i = 0; i < names.size(); ++i)
        std::cout << ",\"" << names[i] << "_offset\":" << spans[i].offset << ",\"" << names[i] << "_bytes\":" << spans[i].bytes;
    std::cout << ",\"next_inflated_offset\":" << p.mid.nextInflatedOffset << ",\"array_records\":" << p.mid.arrayRecords
        << ",\"minor_civ_ai_version\":" << p.minorVersion
        << ",\"victory_point_awards\":5,\"grand_strategy_count\":4,\"building_catalog\":\"initialized\",\"tech_catalog\":\"initialized\""
        << ",\"profile_ruleset_verified\":false}";
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
        if (argc != 1 && !publicMode) throw std::invalid_argument("Usage: retail_player_ai_mid [--public]");
        const std::vector<Fixture> fixtures = {Writer(false, 0, 0, 0).Finish(), Writer(false, 1, 1, 7).Finish(),
            Writer(true, 13, 3, 13).Finish()};
        for (const auto& fixture : fixtures) Golden(suite, fixture);
        Cuts(suite, fixtures[2]); Negative(suite, fixtures[0], fixtures[2]); Mutations(suite, fixtures);
        PublicResult publicResult; if (publicMode) publicResult = Public(suite);
        std::cout << "{\"status\":\"PASS_RETAIL_PLAYER_AI_MID_COMPONENT\",\"checks\":" << suite.checks
            << ",\"synthetic_cases\":3,\"truncations\":" << suite.truncations << ",\"mutations\":" << suite.mutations
            << ",\"accepted_mutations\":" << suite.accepted << ",\"rejected_mutations\":" << suite.rejected
            << ",\"input_files_unchanged\":true,\"input_bytes_unchanged\":true,\"gamecore_loaded\":false,\"window_created\":false"
            << ",\"game_accessed\":false,\"user_saves_accessed\":false,\"complete_player_validated\":false"
            << ",\"complete_save_validated\":false,\"ruleset_compatibility_verified\":false,\"restore_approved\":false";
        if (publicMode) PublicJson(publicResult);
        std::cout << "}\n"; return 0;
    } catch (const std::exception& error) {
        std::cout << "{\"status\":\"FAIL_RETAIL_PLAYER_AI_MID_COMPONENT\",\"checks\":" << suite.checks
            << ",\"error\":\"" << Escape(error.what()) << "\",\"gamecore_loaded\":false,\"window_created\":false"
            << ",\"user_saves_accessed\":false,\"complete_player_validated\":false,\"complete_save_validated\":false"
            << ",\"ruleset_compatibility_verified\":false,\"restore_approved\":false}\n"; return 1;
    }
}
