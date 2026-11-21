#include "../Source/Host/RetailSaveTeam.h"
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <exception>
#include <initializer_list>
#include <iostream>
#include <limits>
#include <map>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

// Independent literal wire writer based on CvTeam.cpp:6987-7097,
// CvTeamTechs::Write (CvTechClasses.cpp:1782-1807), the named legacy array
// helpers, and ImprovementArrayHelpers::WriteYieldArray. No SDK writer,
// private envelope, GameCore, file, database, or process is used as an oracle.
namespace {
using namespace ZeroSisHost;
using Bytes = std::vector<unsigned char>;
using Code = RetailStateErrorCode;
struct Suite {
    std::size_t checks = 0, truncations = 0, mutations = 0, accepted = 0, rejected = 0;
    void Check(bool condition, const std::string& message) {
        ++checks; if (!condition) throw std::runtime_error(message);
    }
};
struct Fixture {
    Bytes bytes;
    std::int32_t id = 0;
    bool rich = false;
    std::size_t end = 0, records = 0, maximumArray = 0;
    std::map<std::string, std::size_t> marks;
    std::vector<std::size_t> versions, bools, signedCounts, unsignedCounts;
};
class Writer {
public:
    Fixture f;
    Writer(bool rich, std::int32_t id) { f.rich = rich; f.id = id; }
    void Mark(const std::string& name) { f.marks[name] = f.bytes.size(); }
    void U8(unsigned char value) { f.bytes.push_back(value); }
    void U32(std::uint32_t value) {
        for (unsigned int i = 0; i < 4; ++i) U8(static_cast<unsigned char>(value >> (8 * i)));
    }
    void I32(std::int32_t value) { U32(static_cast<std::uint32_t>(value)); }
    void Words(std::size_t count, std::uint32_t seed = 0xff000000u) {
        for (std::size_t i = 0; i < count; ++i) U32(seed + static_cast<std::uint32_t>(i));
    }
    void Version(const std::string& name) { Mark(name); f.versions.push_back(f.bytes.size()); U32(1); }
    void Bool(const std::string& name, bool value) {
        Mark(name); f.bools.push_back(f.bytes.size()); U8(value ? 1 : 0);
    }
    void Count(const std::string& name, std::uint32_t value, bool isSigned = false) {
        Mark(name);
        (isSigned ? f.signedCounts : f.unsignedCounts).push_back(f.bytes.size());
        U32(value); f.records += value;
        f.maximumArray = (std::max)(f.maximumArray, static_cast<std::size_t>(value));
    }
    void HashInts(const std::string& name, bool isSigned = false) {
        Count(name, f.rich ? 3u : 0u, isSigned);
        if (f.rich) {
            U32(0); // Generic zero hash has no value.
            U32(0xffffffffu); I32(-1); // Generic -1 hash is still nonzero.
            U32(0x12345678u); U32(0x80000000u);
        }
    }
    void HashBools(const std::string& name) {
        Count(name, f.rich ? 3u : 0u);
        if (f.rich) {
            U32(0); U32(0xffffffffu); Bool(name + ".false", false);
            U32(0x12345678u); Bool(name + ".true", true);
        }
    }
    void ProjectCounts() {
        Count("project_counts", f.rich ? 3u : 0u);
        if (!f.rich) return;
        // Unsorted identities exercise the parser's independent lookup index.
        Mark("project_counts.hash_a"); U32(0x89abcdefu);
        Mark("project_counts.value_a"); I32(3);
        Mark("project_counts.hash_b"); U32(0xffffffffu);
        Mark("project_counts.value_b"); I32(0);
        Mark("project_counts.hash_c"); U32(0x12345678u);
        Mark("project_counts.value_c"); I32(2);
    }
    void ProjectValues(const std::string& name) {
        Count(name, f.rich ? 3u : 0u);
        if (f.rich) {
            U32(0x89abcdefu); I32(-1); U32(0xffffffffu); I32(0); U32(0x12345678u); I32(7);
        }
    }
    void ProjectArt() {
        Count("project_art", f.rich ? 3u : 0u, true);
        if (!f.rich) return;
        // Same source identities as ProjectCounts. Inner lengths are absent:
        // the earlier values 3,0,2 alone determine these five int32 elements.
        Mark("project_art.hash_a"); U32(0x89abcdefu); Words(3, 0x789c0001u);
        Mark("project_art.hash_b"); U32(0xffffffffu);
        Mark("project_art.hash_c"); U32(0x12345678u); Words(2, 0x80000000u);
    }
    void Techs() {
        Version("tech.version"); I32(-1);
        Count("tech.count", f.rich ? 3u : 0u, true);
        if (!f.rich) return;
        Mark("tech.hashes"); U32(0); U32(0xffffffffu); U32(0x12345678u);
        for (unsigned int i = 0; i < 3; ++i) Bool("tech.has" + std::to_string(i), i % 2 == 0);
        for (unsigned int i = 0; i < 3; ++i) Bool("tech.no_trade" + std::to_string(i), i % 2 != 0);
        Mark("tech.progress"); I32(-1); I32(0); U32(0x12345678u);
        Mark("tech.counts"); I32(-1); I32(2); I32(0);
        // Even the zero hash owns a cell in all four following data columns.
    }
    void ImprovementYields(const std::string& name) {
        Count(name, f.rich ? 3u : 0u, true);
        if (f.rich) {
            U32(0);
            U32(0xffffffffu); Words(6, 0x80000000u);
            U32(0x12345678u); Words(6, 0x789c0001u);
        }
    }
    Fixture Finish() {
        Version("team.version"); Words(29);
        for (unsigned int i = 0; i < 8; ++i) Bool("flag" + std::to_string(i), i % 2 != 0);
        Mark("id"); I32(f.id); Words(3);
        Mark("team_arrays"); Words(3u * 64u);
        Mark("domains"); Words(5);
        HashInts("vote_sources");
        Words(2u * 64u);
        for (unsigned int group = 0; group < 10; ++group)
            for (unsigned int team = 0; team < 64; ++team)
                Bool("relations" + std::to_string(group) + "." + std::to_string(team), (team + group) % 3 == 0);
        HashBools("launch"); HashBools("victories"); HashBools("small_awards");
        HashInts("routes"); HashInts("build_times");
        ProjectCounts(); ProjectValues("project_default_art"); ProjectArt(); ProjectValues("project_making");
        HashInts("unit_classes", true); HashInts("building_classes", true); HashInts("obsolete_buildings", true);
        HashInts("terrain_trade"); HashInts("victory_countdown");
        Mark("met"); Words(63); Techs();
        ImprovementYields("yield.all"); ImprovementYields("yield.dry"); ImprovementYields("yield.fresh");
        Count("resources", f.rich ? 4u : 0u);
        if (f.rich) { U32(0); U32(0xffffffffu); U32(0x12345678u); U32(0x789c0001u); }
        f.end = f.bytes.size();
        U32(0xefbeaddeu); // A caller-owned following record, never part of Team.
        return std::move(f);
    }
};
struct Result { std::int32_t id; std::size_t next, records; };
Result Inspect(const unsigned char* bytes, std::size_t size, const RetailSaveStateLimits& limits = {}, std::size_t start = 0) {
    RetailStateDetail::Reader reader(bytes, size, limits);
    reader.Skip(start);
    const auto id = RetailStateDetail::ReadTeam(reader);
    return {id, reader.Pos(), reader.Records()};
}
Result Inspect(const Fixture& f, const RetailSaveStateLimits& limits = {}) { return Inspect(f.bytes.data(), f.bytes.size(), limits); }
void Put32(Bytes& bytes, std::size_t at, std::uint32_t value) {
    if (at > bytes.size() || bytes.size() - at < 4) throw std::logic_error("Invalid team fixture patch position");
    for (unsigned int i = 0; i < 4; ++i) bytes[at + i] = static_cast<unsigned char>(value >> (8 * i));
}
template<class Action>
void Expect(Suite& suite, Code expected, std::size_t size, const std::string& name, Action action) {
    try { action(); }
    catch (const RetailStateError& error) {
        suite.Check(error.Code() == expected, name + ": wrong typed error");
        suite.Check(error.Offset() <= size, name + ": error offset outside input"); return;
    }
    throw std::runtime_error(name + ": expected typed rejection");
}
void Patched(Suite& suite, const Fixture& f, std::size_t at, std::uint32_t value, Code code, const char* name) {
    auto bytes = f.bytes; Put32(bytes, at, value);
    Expect(suite, code, bytes.size(), name, [&] { Inspect(bytes.data(), bytes.size()); });
}
void Golden(Suite& suite, const Fixture& f) {
    const auto immutable = f.bytes;
    const auto r = Inspect(f);
    suite.Check(r.id == f.id && r.next == f.end, "SDK-based literal writer ID/end differs");
    suite.Check(r.records == f.records, "Explicit row-count accounting differs");
    suite.Check(f.marks.at("id") == 128 && f.marks.at("domains") == 912 && f.marks.at("vote_sources") == 932,
        "Literal fixed Team header/64-array/domain5 offsets differ");
    if (f.rich) {
        // Additional payloads: int hashes20, bool hashes42, route/build40,
        // project104, signed hashes60, terrain/victory40, Techs42,
        // improvement yields180 and resource hashes16: total544.
        suite.Check(f.end == 2968 && r.next == 2968 && r.records == 61, "Rich literal size/record oracle differs");
        suite.Check(f.marks.at("tech.progress") - f.marks.at("tech.hashes") == 18 &&
            f.marks.at("tech.counts") - f.marks.at("tech.progress") == 12,
            "Techs five-column layout differs");
    } else {
        // 2336 fixed bytes and 88 version/count bytes, independently summed
        // from the original SDK writer. No sizeof(native object) is involved.
        suite.Check(f.end == 2424 && r.next == 2424 && r.records == 0, "Minimum literal2424 oracle differs");
        suite.Check(f.marks.at("met") == 2144 && f.marks.at("tech.version") == 2396 &&
            f.marks.at("resources") == 2420, "Literal 63-team/Techs/resource offsets differ");
    }
    suite.Check(Inspect(f.bytes.data(), f.end).next == f.end, "Exact Team prefix needs following data");
    auto suffix = f.bytes; Put32(suffix, f.end, 0xffffffffu);
    suite.Check(Inspect(suffix.data(), suffix.size()).next == f.end, "Opaque following record affected Team boundary");
    Bytes wrapped(11, 0xa5); wrapped.insert(wrapped.end(), f.bytes.begin(), f.bytes.end());
    const auto offset = Inspect(wrapped.data(), wrapped.size(), RetailSaveStateLimits{}, 11);
    suite.Check(offset.id == f.id && offset.next == 11 + f.end && offset.records == f.records,
        "Caller-selected Team start was ignored");
    suite.Check(f.bytes == immutable, "Team inspection changed caller input");
}
void Truncations(Suite& suite, const Fixture& f) {
    const auto immutable = f.bytes;
    for (std::size_t cut = 0; cut < f.end; ++cut) {
        Expect(suite, Code::Truncated, cut, "Every Team prefix truncation", [&] { Inspect(f.bytes.data(), cut); });
        ++suite.truncations;
    }
    suite.Check(f.bytes == immutable, "Team truncation inspection changed input");
}

void SparseProjectIndex(Suite& suite) {
    // Isolate the generic zero-hash rule without inventing a whole Team art
    // layout for an absent project whose derived length cannot be resolved.
    Writer w(false, 0);
    w.Count("index", 4); w.U32(0);
    w.U32(0x89abcdefu); w.I32(3); w.U32(0xffffffffu); w.I32(0); w.U32(0x12345678u); w.I32(2);
    const auto immutable = w.f.bytes;
    RetailSaveStateLimits limits;
    RetailStateDetail::Reader reader(w.f.bytes.data(), w.f.bytes.size(), limits);
    const auto index = RetailStateDetail::ReadTeamProjectCounts(reader);
    suite.Check(reader.Pos() == 32 && reader.Records() == 4 && index.size() == 3,
        "Sparse project count index lost a zero row or read its absent value");
    suite.Check(index[0].first == 0x12345678u && index[0].second == 2 &&
        index[1].first == 0x89abcdefu && index[1].second == 3 &&
        index[2].first == 0xffffffffu && index[2].second == 0, "Sorted project index differs from literal identities/counts");
    suite.Check(w.f.bytes == immutable, "Project lookup sorting modified input");
}
void Negative(Suite& suite, const Fixture& empty, const Fixture& rich) {
    const auto immutable = rich.bytes;
    RetailSaveStateLimits limits;
    limits.maxInputBytes = rich.bytes.size();
    suite.Check(Inspect(rich, limits).next == rich.end, "Inclusive Team input budget failed");
    --limits.maxInputBytes;
    Expect(suite, Code::InputLimit, rich.bytes.size(), "Short Team input budget", [&] { Inspect(rich, limits); });
    limits = {}; limits.maxPrefixBytes = rich.end;
    suite.Check(Inspect(rich, limits).next == rich.end, "Inclusive Team prefix budget failed");
    --limits.maxPrefixBytes;
    Expect(suite, Code::PrefixLimit, rich.bytes.size(), "Short Team prefix budget", [&] { Inspect(rich, limits); });
    limits = {}; limits.maxArrayRecords = rich.maximumArray;
    suite.Check(Inspect(rich, limits).records == rich.records, "Inclusive Team row budget failed");
    --limits.maxArrayRecords;
    Expect(suite, Code::ArrayLimit, rich.bytes.size(), "Short Team row budget", [&] { Inspect(rich, limits); });
    limits = {}; limits.maxTotalRecords = rich.records;
    suite.Check(Inspect(rich, limits).records == 61, "Inclusive Team aggregate budget failed");
    --limits.maxTotalRecords;
    Expect(suite, Code::TotalRecordLimit, rich.bytes.size(), "Short Team aggregate budget", [&] { Inspect(rich, limits); });
    limits = {}; limits.maxInputBytes = 0;
    Expect(suite, Code::InputLimit, rich.bytes.size(), "Zero Team input budget", [&] { Inspect(rich, limits); });
    limits = {}; limits.maxPrefixBytes = 0;
    Expect(suite, Code::PrefixLimit, rich.bytes.size(), "Zero Team prefix budget", [&] { Inspect(rich, limits); });
    limits = {}; limits.maxArrayRecords = 0;
    Expect(suite, Code::ArrayLimit, rich.bytes.size(), "Zero Team row budget", [&] { Inspect(rich, limits); });
    limits = {}; limits.maxTotalRecords = 0;
    Expect(suite, Code::TotalRecordLimit, rich.bytes.size(), "Zero Team aggregate budget", [&] { Inspect(rich, limits); });
    limits = {}; limits.maxTotalRecords = 0; limits.maxArrayRecords = 0;
    limits.maxStringBytes = 0; limits.maxEmbeddedDatabaseBytes = 0; limits.maxMapPlots = 0;
    suite.Check(Inspect(empty, limits).records == 0, "Fixed64/63/domain5 arrays were charged as dynamic rows");
    for (const auto version : rich.versions) {
        Patched(suite, rich, version, 0, Code::UnsupportedVersion, "Team/Techs version zero");
        Patched(suite, rich, version, 2, Code::UnsupportedVersion, "Team/Techs future version");
    }
    for (const auto at : rich.bools) {
        auto bytes = rich.bytes; bytes[at] = 2;
        Expect(suite, Code::InvalidValue, bytes.size(), "Malformed Team/Techs boolean", [&] { Inspect(bytes.data(), bytes.size()); });
    }
    for (const auto at : rich.signedCounts)
        Patched(suite, rich, at, 0xffffffffu, Code::InvalidValue, "Negative Team row count");
    for (const auto at : rich.unsignedCounts)
        Patched(suite, rich, at, 0xffffffffu, Code::ArrayLimit, "Unbounded unsigned Team row count");
    Patched(suite, rich, rich.marks.at("project_counts.value_a"), 0xffffffffu,
        Code::InvalidValue, "Negative project count");
    Patched(suite, rich, rich.marks.at("project_counts.hash_b"), 0x89abcdefu,
        Code::InvalidValue, "Duplicate project count hash");
    Patched(suite, rich, rich.marks.at("project_art.hash_c"), 0x89abcdefu,
        Code::InvalidValue, "Duplicate project art hash");
    Patched(suite, rich, rich.marks.at("project_art.hash_a"), 0,
        Code::UnsupportedProfile, "Zero project art hash lacks an inner length");
    Patched(suite, rich, rich.marks.at("project_art.hash_a"), 0x10203040u,
        Code::UnsupportedProfile, "Project art hash has no earlier count");
    Patched(suite, rich, rich.marks.at("project_counts.value_a"), 0x7fffffffu,
        Code::Truncated, "Derived art scalar extent exceeds remaining bytes");
    // Counts charge explicit on-wire rows. The five derived art scalars are
    // skipped in O(1), allocate nothing, and are bounded by input/prefix bytes;
    // they do not add five synthetic rows to maxTotalRecords/maxArrayRecords.
    limits = {}; limits.maxPrefixBytes = rich.marks.at("project_art.hash_a") + 4 + 3 * 4 - 1;
    Expect(suite, Code::PrefixLimit, rich.bytes.size(), "Derived art scalar prefix budget", [&] { Inspect(rich, limits); });
    Expect(suite, Code::NullInput, 1, "Null nonempty Team input", [&] { Inspect(nullptr, 1); });
    Expect(suite, Code::Truncated, 0, "Null empty Team input", [&] { Inspect(nullptr, 0); });
    const unsigned char one = 0;
    Expect(suite, Code::InputLimit, 0, "Oversized Team size without dereference", [&] {
        Inspect(&one, (std::numeric_limits<std::size_t>::max)());
    });
    Expect(suite, Code::Truncated, 1, "Overflowing caller start", [&] {
        Inspect(&one, 1, RetailSaveStateLimits{}, (std::numeric_limits<std::size_t>::max)());
    });
    // The returned ID belongs to the caller's ordinal/profile check. This
    // structural primitive preserves it rather than inventing slot semantics.
    auto idBytes = rich.bytes; Put32(idBytes, rich.marks.at("id"), 17);
    suite.Check(Inspect(idBytes.data(), idBytes.size()).id == 17, "Serialized Team ID was inferred or replaced");
    suite.Check(rich.bytes == immutable, "Team rejection tests modified source input");
}
void SharedBudget(Suite& suite, const Fixture& rich) {
    Bytes bytes(rich.bytes.begin(), rich.bytes.begin() + rich.end);
    bytes.insert(bytes.end(), rich.bytes.begin(), rich.bytes.begin() + rich.end);
    const auto immutable = bytes;
    RetailSaveStateLimits limits; limits.maxTotalRecords = 122;
    RetailStateDetail::Reader reader(bytes.data(), bytes.size(), limits);
    const auto first = RetailStateDetail::ReadTeam(reader), second = RetailStateDetail::ReadTeam(reader);
    suite.Check(first == rich.id && second == rich.id && reader.Pos() == 5936 && reader.Records() == 122,
        "Sequential Team cursor/aggregate row budget reset between records");
    limits.maxTotalRecords = 121;
    Expect(suite, Code::TotalRecordLimit, bytes.size(), "Sequential shared Team aggregate budget", [&] {
        RetailStateDetail::Reader limited(bytes.data(), bytes.size(), limits);
        RetailStateDetail::ReadTeam(limited); RetailStateDetail::ReadTeam(limited);
    });
    suite.Check(bytes == immutable, "Sequential Team input changed");
}
struct Observation {
    bool accepted = false;
    Result value{};
    Code code = Code::Truncated;
    std::size_t offset = 0;
};
Observation Observe(const Bytes& bytes) {
    Observation result;
    RetailSaveStateLimits limits;
    limits.maxInputBytes = 16384; limits.maxPrefixBytes = 16384;
    limits.maxArrayRecords = 2048; limits.maxTotalRecords = 16384;
    try { result.value = Inspect(bytes.data(), bytes.size(), limits); result.accepted = true; }
    catch (const RetailStateError& error) { result.code = error.Code(); result.offset = error.Offset(); }
    return result;
}
bool Same(const Observation& a, const Observation& b) {
    if (a.accepted != b.accepted) return false;
    if (!a.accepted) return a.code == b.code && a.offset == b.offset;
    return a.value.id == b.value.id && a.value.next == b.value.next && a.value.records == b.value.records;
}
void Mutations(Suite& suite, const std::vector<Fixture>& fixtures) {
    std::uint32_t random = 0x712b9ea3u;
    const auto next = [&random]() { random ^= random << 13; random ^= random >> 17; random ^= random << 5; return random; };
    for (std::size_t i = 0; i < 2048; ++i) {
        const auto& seed = fixtures[i % fixtures.size()]; auto bytes = seed.bytes;
        switch (i % 8) {
        case 0: Put32(bytes, 0, 99); break;
        case 1: bytes[seed.end + next() % 4] ^= 0x80; break;
        case 2: Put32(bytes, seed.marks.at("resources"), 0xffffffffu); break;
        case 3: bytes[seed.bools[next() % seed.bools.size()]] = 2; break;
        case 4: bytes.resize(next() % seed.end); break;
        case 5: Put32(bytes, seed.marks.at("id"), next()); break;
        default: bytes[next() % bytes.size()] ^= static_cast<unsigned char>(1u << (next() % 8)); break;
        }
        const auto immutable = bytes;
        const auto first = Observe(bytes), second = Observe(bytes);
        suite.Check(Same(first, second), "Team mutation result was nondeterministic");
        suite.Check(bytes == immutable, "Team mutation inspection changed input");
        if (first.accepted) {
            suite.Check(first.value.next >= 2424 && first.value.next <= bytes.size(), "Accepted Team extent outside input");
            suite.Check(first.value.records <= 16384, "Accepted Team exceeded explicit row budget"); ++suite.accepted;
        } else { suite.Check(first.offset <= bytes.size(), "Team error offset outside input"); ++suite.rejected; }
        ++suite.mutations;
    }
    suite.Check(suite.accepted != 0 && suite.rejected != 0, "Team mutation corpus missed an outcome");
}
std::string Escape(const char* message) {
    std::string text;
    for (const unsigned char* p = reinterpret_cast<const unsigned char*>(message); *p; ++p) {
        if (*p == '"' || *p == '\\') { text += '\\'; text += static_cast<char>(*p); }
        else if (*p >= 0x20 && *p < 0x7f) text += static_cast<char>(*p);
        else text += '?';
    }
    return text;
}
} // namespace

int main() {
    Suite suite;
    try {
        static_assert(sizeof(void*) == 8, "Team component test requires a native 64-bit executable");
        std::vector<Fixture> fixtures;
        for (std::int32_t id : {0, 63}) for (bool rich : {false, true}) fixtures.push_back(Writer(rich, id).Finish());
        for (const auto& f : fixtures) Golden(suite, f);
        Truncations(suite, fixtures[0]); Truncations(suite, fixtures[3]);
        SparseProjectIndex(suite); Negative(suite, fixtures[0], fixtures[3]); SharedBudget(suite, fixtures[3]);
        Mutations(suite, fixtures);
        std::cout << "{\"status\":\"PASS_RETAIL_TEAM_COMPONENT\",\"checks\":" << suite.checks
            << ",\"synthetic_cases\":4,\"truncations\":" << suite.truncations << ",\"mutations\":" << suite.mutations
            << ",\"accepted_mutations\":" << suite.accepted << ",\"rejected_mutations\":" << suite.rejected
            << ",\"mutation_acceptance\":\"STRUCTURAL_INSPECTION_ONLY\",\"input_bytes_unchanged\":true"
            << ",\"gamecore_loaded\":false,\"window_created\":false,\"user_saves_accessed\":false"
            << ",\"complete_save_validated\":false,\"ruleset_compatibility_verified\":false,\"sdk_restore_verified\":false"
            << ",\"retail_outer_order_verified\":false,\"full_engine_goal_complete\":false}\n";
        return 0;
    } catch (const std::exception& error) {
        std::cout << "{\"status\":\"FAIL_RETAIL_TEAM_COMPONENT\",\"checks\":" << suite.checks
            << ",\"error\":\"" << Escape(error.what()) << "\",\"gamecore_loaded\":false,\"window_created\":false"
            << ",\"user_saves_accessed\":false,\"complete_save_validated\":false,\"ruleset_compatibility_verified\":false}\n";
        return 1;
    }
}
