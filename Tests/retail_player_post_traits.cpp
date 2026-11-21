#include "../Source/Host/RetailSavePlayerPostTraits.h"
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

// Independent source-wire fixtures, not SDK serialization or saved games.
// Original CvPlayer.cpp:22604-22633; CvEspionageClasses.cpp:79-93,
// 3713-3791,5554-5604; CvTradeClasses.cpp:3811-3858,4484-4491;
// CvVotingClasses.cpp:7421-7436; CvCultureClasses.cpp:3916-3964;
// CvNotifications.cpp:189-209,289-306; CvTreasury.cpp:1024-1043.
// Tail: CvPlayer.h:1845-1863, CvUnitCycler.cpp:306-317 and
// LinkedList.h:468-496. No production size constants or framing helpers
// construct the fixtures. The unread suffix begins at m_cities, not a
// version signature. All public offsets are reached sequentially.
namespace {
using namespace ZeroSisHost;
using Bytes = std::vector<unsigned char>;
using Code = RetailStateErrorCode;
using Result = decltype(RetailSavePlayerPostTraits::InspectAt(nullptr, std::size_t{}, std::size_t{}));
constexpr std::size_t SpanCount = 9;
struct Suite {
    std::size_t checks = 0, truncations = 0, mutations = 0, accepted = 0, rejected = 0;
    void Check(bool condition, const std::string& why) {
        ++checks;
        if (!condition) throw std::runtime_error(why);
    }
};
struct Fixture {
    Bytes bytes;
    unsigned variant = 0;
    bool notifications = false;
    std::size_t start = 0, end = 0, rows = 0, maxArray = 0, maxString = 0, marker = 0;
    std::array<RetailInflatedSpan, SpanCount> spans{};
    std::map<std::string, std::size_t> marks;
    std::vector<std::size_t> versions, bools, signedCounts, unsignedCounts, strings, fixedCounts;
};
class Writer {
public:
    Fixture f;
    Writer(unsigned variant, std::size_t start) {
        f.variant = variant; f.start = start; f.notifications = variant == 1 || variant == 3;
        f.bytes.assign(start, static_cast<unsigned char>(0x78));
        // Deliberate version/zlib-looking prefix bytes must never be searched.
        if (start >= 4) { f.bytes[0] = 0; f.bytes[1] = 0; f.bytes[2] = 0; f.bytes[3] = 0; }
    }
    bool Rich() const { return f.variant == 3; }
    bool Populated() const { return f.variant >= 2; }
    std::uint32_t N(std::uint32_t sparse, std::uint32_t rich) const {
        return Populated() ? (Rich() ? rich : sparse) : 0u;
    }
    void Mark(const std::string& name) { f.marks[name] = f.bytes.size(); }
    void U8(unsigned char value) { f.bytes.push_back(value); }
    void U32(std::uint32_t value) {
        for (unsigned i = 0; i < 4; ++i) U8(static_cast<unsigned char>(value >> (8u * i)));
    }
    void I32(std::int32_t value) { U32(static_cast<std::uint32_t>(value)); }
    void Words(std::size_t count, std::uint32_t seed = 0x80010000u) {
        for (std::size_t i = 0; i < count; ++i) U32(seed + static_cast<std::uint32_t>(i));
    }
    void Bool(bool value) { f.bools.push_back(f.bytes.size()); U8(value ? 1u : 0u); }
    void Version(const std::string& name, std::uint32_t value) {
        Mark(name); f.versions.push_back(f.bytes.size()); U32(value);
    }
    void Count(const std::string& name, std::uint32_t count, bool signedCount = false, bool fixed = false) {
        Mark(name); (signedCount ? f.signedCounts : f.unsignedCounts).push_back(f.bytes.size());
        if (fixed) f.fixedCounts.push_back(f.bytes.size());
        U32(count); f.rows += count; f.maxArray = (std::max)(f.maxArray, static_cast<std::size_t>(count));
    }
    std::string TextData(unsigned index) const {
        if (!Rich()) return {};
        return (index & 1u) ? std::string("town", 4) : std::string("\xed\x95\x9c\0A", 5);
    }
    void Text(const std::string& name, const std::string& data) {
        Mark(name); f.strings.push_back(f.bytes.size()); U32(static_cast<std::uint32_t>(data.size()));
        f.maxString = (std::max)(f.maxString, data.size());
        f.bytes.insert(f.bytes.end(), data.begin(), data.end());
    }
    template<class F> void Section(std::size_t index, F write) {
        const auto begin = f.bytes.size(); write(); f.spans[index] = {begin, f.bytes.size() - begin};
    }
    void Espionage() {
        Version("esp.version", 0);
        const auto spies = N(1, 2); Count("esp.spies", spies, true);
        for (std::uint32_t i = 0; i < spies; ++i) {
            Version("esp.spy." + std::to_string(i), 1); Words(6); Bool((i & 1u) != 0); Bool(true);
        }
        const auto names = N(1, 9); Count("esp.names", names, true); Words(names); I32(-1);
        const auto civilizations = N(1, 3); Count("esp.tech_civs", civilizations);
        for (std::uint32_t i = 0; i < civilizations; ++i) {
            const auto techs = Rich() ? i : 0u;
            Count("esp.techs." + std::to_string(i), techs); Words(techs);
        }
        const auto steal = N(1, 3); Count("esp.steal", steal); Words(steal);
        Count("esp.maximum_costs", 22, true, true); Words(22);
        Count("esp.heist_civs", 22, true, true);
        for (unsigned i = 0; i < 22; ++i) {
            const auto count = Populated() && i == 21 ? 1u : Rich() && i == 0 ? 2u : 0u;
            Count("esp.heists." + std::to_string(i), count, true); Words(2u * count);
        }
        const auto messages = N(0, 2); Count("esp.notices", messages, true); Words(5u * messages);
        const auto intrigue = N(1, 2); Count("esp.intrigue", intrigue, true);
        for (std::uint32_t i = 0; i < intrigue; ++i) {
            Words(9); Text("esp.spy_name." + std::to_string(i), TextData(i)); Bool((i & 1u) != 0);
        }
    }
    void EspionageAI() {
        Version("esp_ai.version", 0);
        for (unsigned i = 0; i < 7; ++i) {
            const auto count = Rich() ? i % 3u + 1u : Populated() && i == 6 ? 1u : 0u;
            Count("esp_ai.array." + std::to_string(i), count); Words(count);
        }
        Bool(true); I32(-1);
    }
    void Trade() {
        Version("trade.version", 2);
        const auto expired = N(1, 2); Count("trade.expired", expired, true);
        for (std::uint32_t i = 0; i < expired; ++i) { Words(10); Bool(true); Words(4); }
        const auto plundered = N(0, 1); Count("trade.plundered", plundered, true);
        for (std::uint32_t i = 0; i < plundered; ++i) { Words(10); Bool(false); Words(4); }
    }
    void TradeAI() { Version("trade_ai.version", 0); I32(-2147483647); }
    void League() {
        Version("league.version", 2);
        const auto count = N(1, 6); Count("league.votes", count);
        for (std::uint32_t i = 0; i < count; ++i) { Words(4); Bool((i & 1u) != 0); }
    }
    void Culture() {
        Version("culture.version", 6);
        const auto digs = N(1, 2); Count("culture.digs", digs, true); Words(2u * digs); I32(-1);
        Count("culture.influences", 22, true, true); Words(44);
        Mark("culture.reported"); Bool(true); Bool(false);
        Words(3); Text("culture.opinion", TextData(0)); Text("culture.unhappy", TextData(1)); Words(6);
    }
    void Notifications() {
        if (!f.notifications) return;
        Version("notifications.version", 2); Words(4); Mark("notifications.records");
        for (unsigned i = 0; i < 100; ++i) {
            // The hash is raw; zero and 0xffffffff do not omit any payload.
            U32(i % 3u == 0 ? 0u : i % 3u == 1 ? 0xffffffffu : 0x12345678u);
            const bool text = Rich() && (i == 0 || i == 99);
            Text("notifications.message." + std::to_string(i), text ? TextData(0) : std::string{});
            Text("notifications.summary." + std::to_string(i), text ? TextData(1) : std::string{});
            Words(6); Bool((i & 1u) != 0); Mark("notifications.player." + std::to_string(i)); I32(-1);
        }
    }
    void Treasury() {
        Version("treasury.version", 1); Words(9);
        const auto balance = N(1, 3), changes = N(0, 2);
        Count("treasury.balance", balance); Words(balance);
        Count("treasury.changes", changes); Words(changes); I32(-1);
    }
    void PreCity() {
        const auto specialists = N(1, 2), improvements = N(0, 1);
        Count("tail.specialists", specialists); Words(6u * specialists);
        Count("tail.improvements", improvements); Words(6u * improvements);
        const auto cycle = N(1, 3), queue = N(0, 2), names = N(1, 2);
        Count("tail.unit_cycle", cycle, true); Words(cycle);
        Count("tail.research", queue, true); Words(queue);
        Mark("tail.first_bool"); Bool(true); Bool(false); I32(-1); I32(-2147483647);
        Count("tail.city_names", names, true);
        for (std::uint32_t i = 0; i < names; ++i) Text("tail.city_name." + std::to_string(i), TextData(i));
    }
    Fixture Finish() {
        Section(0, [&] { Espionage(); }); Section(1, [&] { EspionageAI(); });
        Section(2, [&] { Trade(); }); Section(3, [&] { TradeAI(); });
        Section(4, [&] { League(); }); Section(5, [&] { Culture(); });
        f.marker = f.bytes.size(); Bool(f.notifications);
        Section(6, [&] { Notifications(); }); Section(7, [&] { Treasury(); });
        Section(8, [&] { PreCity(); }); f.end = f.bytes.size();
        // Deliberately not a city record: the framer must leave this unread.
        U32(0xc17e5eedu); U32(0x789c0001u); return f;
    }
};

std::array<RetailInflatedSpan, SpanCount> Spans(const Result& r) {
    return {r.espionage, r.espionageAI, r.trade, r.tradeAI, r.leagueAI, r.culture,
            r.notifications, r.treasury, r.preCityFields};
}
std::uint32_t Word(const Bytes& data, std::size_t at) {
    if (at > data.size() || data.size() - at < 4) throw std::runtime_error("Fixture word exceeds input");
    return static_cast<std::uint32_t>(data[at]) | (static_cast<std::uint32_t>(data[at + 1]) << 8)
        | (static_cast<std::uint32_t>(data[at + 2]) << 16) | (static_cast<std::uint32_t>(data[at + 3]) << 24);
}
void Put(Bytes& data, std::size_t at, std::uint32_t value) {
    if (at > data.size() || data.size() - at < 4) throw std::runtime_error("Mutation word exceeds input");
    for (unsigned i = 0; i < 4; ++i) data[at + i] = static_cast<unsigned char>(value >> (8u * i));
}
Result Parse(const Fixture& f, const RetailSaveStateLimits& limits = RetailSaveStateLimits{}) {
    return RetailSavePlayerPostTraits::InspectAt(f.bytes.data(), f.bytes.size(), f.start, limits);
}
void Invariants(Suite& s, const Result& r, std::size_t size, std::size_t start) {
    const auto spans = Spans(r); auto cursor = start;
    for (std::size_t i = 0; i < spans.size(); ++i) {
        if (i == 6) { s.Check(cursor < size, "Notification marker exceeds input"); ++cursor; }
        const auto span = spans[i];
        s.Check(span.offset == cursor && span.offset <= size && span.bytes <= size - span.offset,
                "Post-Traits spans or notification-marker gap disagree");
        cursor = span.offset + span.bytes;
    }
    s.Check(cursor == r.nextInflatedOffset && cursor <= size, "Wrong post-Traits next offset");
    s.Check(r.hasNotifications == (r.notifications.bytes != 0), "Optional notifications span disagrees with marker");
    s.Check(!r.completePlayerVerified && !r.completeSaveVerified && !r.rulesetCompatibilityVerified &&
            !r.restoreApproved, "Post-Traits framing granted Player, ruleset or restore approval");
}
template<class F> void Reject(Suite& s, Code expected, const std::string& why, F action) {
    try { action(); }
    catch (const RetailStateError& error) { s.Check(error.Code() == expected, why + ": wrong typed error"); return; }
    s.Check(false, why + ": invalid input was accepted");
}
void Golden(Suite& s, const Fixture& f) {
    const auto before = f.bytes; const auto r = Parse(f); Invariants(s, r, f.bytes.size(), f.start);
    const std::array<std::array<std::size_t, SpanCount>, 4> literal = {{
        {{216, 37, 12, 8, 8, 238, 0, 52, 30}},
        {{216, 37, 12, 8, 8, 238, 4120, 52, 30}},
        {{307, 41, 69, 8, 25, 246, 0, 56, 62}},
        {{503, 89, 183, 8, 110, 263, 4138, 72, 139}}
    }};
    const std::array<std::size_t, 4> totals = {602, 4722, 815, 5506};
    const std::array<std::size_t, 4> rows = {66, 66, 80, 132};
    const std::array<std::size_t, 4> bools = {6, 106, 11, 121};
    const auto spans = Spans(r);
    for (std::size_t i = 0; i < spans.size(); ++i) {
        s.Check(f.spans[i].bytes == literal[f.variant][i], "Independent source writer disagrees with literal section size");
        s.Check(spans[i].offset == f.spans[i].offset && spans[i].bytes == literal[f.variant][i],
                "Incorrect post-Traits section boundary");
    }
    s.Check(f.end - f.start == totals[f.variant], "Wrong literal combined post-Traits size");
    s.Check(f.rows == rows[f.variant] && r.arrayRecords == rows[f.variant], "Wrong explicit-count row total");
    s.Check(f.bools.size() == bools[f.variant], "Wrong literal serialized-bool count");
    s.Check(r.hasNotifications == f.notifications && f.bytes[f.marker] == (f.notifications ? 1 : 0),
            "Wrong notification presence/marker location");
    s.Check(r.notifications.offset == f.marker + 1 && r.treasury.offset == r.notifications.offset + r.notifications.bytes,
            "Presence byte was included in the notifications span");
    const auto base = f.spans[0].offset;
    s.Check(f.marks.at("esp.spies") - base == 4 &&
            f.marks.at("esp.maximum_costs") - base == (f.variant == 3 ? 156u : f.variant == 2 ? 66u : 24u) &&
            f.marks.at("esp.heist_civs") - base == (f.variant == 3 ? 248u : f.variant == 2 ? 158u : 116u),
            "Espionage counted-record/fixed-dimension source checkpoint changed");
    const auto culture = f.spans[5].offset;
    s.Check(f.marks.at("culture.reported") - culture == (f.variant == 3 ? 208u : f.variant == 2 ? 200u : 192u),
            "Culture 22 pairs or following two bool widths changed");
    if (f.notifications) {
        s.Check(f.marks.at("notifications.records") - f.spans[6].offset == 20 &&
                f.marks.at("notifications.player.0") - f.spans[6].offset == (f.variant == 3 ? 66u : 57u),
                "Notifications player was not the last field of its first slot");
    }
    const auto tail = f.spans[8].offset;
    s.Check(f.marks.at("tail.first_bool") - tail == (f.variant == 3 ? 108u : f.variant == 2 ? 44u : 16u),
            "Pre-City matrices or linked-list integer/enum widths changed");
    s.Check(r.nextInflatedOffset == f.end && Word(f.bytes, f.end) == 0xc17e5eedu &&
            Word(f.bytes, f.end + 4) == 0x789c0001u, "Post-Traits parser consumed or searched the unread city suffix");
    const auto exact = RetailSavePlayerPostTraits::InspectAt(f.bytes.data(), f.end, f.start);
    s.Check(exact.nextInflatedOffset == f.end, "Framing improperly required a subsequent city record");
    s.Check(f.bytes == before, "Golden post-Traits framing mutated input");
}
void Cuts(Suite& s, const Fixture& f) {
    const auto before = f.bytes;
    for (std::size_t size = 0; size < f.end; ++size) {
        Reject(s, Code::Truncated, "All-byte post-Traits truncation", [&] {
            RetailSavePlayerPostTraits::InspectAt(f.bytes.data(), size, f.start);
        });
        ++s.truncations;
    }
    s.Check(before == f.bytes, "Truncation inspection mutated fixture bytes");
}
void Negative(Suite& s, const Fixture& empty, const Fixture& rich) {
    for (const auto* fixture : {&empty, &rich}) {
        const auto& f = *fixture;
        for (const auto at : f.versions) {
            for (const auto version : {Word(f.bytes, at) ^ 1u, 0xffffffffu}) {
                auto bad = f; Put(bad.bytes, at, version);
                Reject(s, Code::UnsupportedVersion, "Current nested version only", [&] { Parse(bad); });
            }
        }
        for (const auto at : f.signedCounts) {
            auto bad = f; Put(bad.bytes, at, 0xffffffffu);
            Reject(s, Code::InvalidValue, "Negative signed count", [&] { Parse(bad); });
            Put(bad.bytes, at, 0x7fffffffu);
            Reject(s, Code::ArrayLimit, "Oversized signed count", [&] { Parse(bad); });
        }
        for (const auto at : f.unsignedCounts) {
            auto bad = f; Put(bad.bytes, at, 0xffffffffu);
            Reject(s, Code::ArrayLimit, "Oversized unsigned count", [&] { Parse(bad); });
        }
        for (const auto at : f.fixedCounts) {
            auto bad = f; Put(bad.bytes, at, 21);
            Reject(s, Code::InvalidValue, "Encoded major dimension must be 22", [&] { Parse(bad); });
        }
        for (const auto at : f.strings) {
            auto bad = f; Put(bad.bytes, at, 0xffffffffu);
            Reject(s, Code::StringLimit, "Oversized string byte length", [&] { Parse(bad); });
        }
        auto limits = RetailSaveStateLimits{}; limits.maxInputBytes = f.bytes.size();
        s.Check(Parse(f, limits).nextInflatedOffset == f.end, "Exact input budget rejected");
        --limits.maxInputBytes;
        Reject(s, Code::InputLimit, "Short input budget", [&] { Parse(f, limits); });
        limits = RetailSaveStateLimits{}; limits.maxPrefixBytes = f.end;
        s.Check(Parse(f, limits).nextInflatedOffset == f.end, "Exact prefix budget rejected");
        --limits.maxPrefixBytes;
        Reject(s, Code::PrefixLimit, "Short prefix budget", [&] { Parse(f, limits); });
        limits = RetailSaveStateLimits{}; limits.maxArrayRecords = f.maxArray;
        limits.maxTotalRecords = f.rows; limits.maxStringBytes = f.maxString;
        s.Check(Parse(f, limits).arrayRecords == f.rows, "Exact array, aggregate or string budget rejected");
        --limits.maxArrayRecords;
        Reject(s, Code::ArrayLimit, "Short array-record budget", [&] { Parse(f, limits); });
        ++limits.maxArrayRecords; --limits.maxTotalRecords;
        Reject(s, Code::TotalRecordLimit, "Short aggregate-record budget", [&] { Parse(f, limits); });
        ++limits.maxTotalRecords;
        if (f.maxString) {
            --limits.maxStringBytes;
            Reject(s, Code::StringLimit, "Short string-byte budget", [&] { Parse(f, limits); });
        }
    }
    for (const auto at : rich.bools) {
        auto bad = rich; bad.bytes[at] = 2;
        Reject(s, Code::InvalidValue, "Noncanonical serialized bool", [&] { Parse(bad); });
    }
    Reject(s, Code::NullInput, "Null nonempty input", [&] {
        RetailSavePlayerPostTraits::InspectAt(nullptr, 1, 0);
    });
    Reject(s, Code::Truncated, "Empty input", [&] {
        RetailSavePlayerPostTraits::InspectAt(nullptr, 0, 0);
    });
    Reject(s, Code::Truncated, "Oversized start offset", [&] {
        RetailSavePlayerPostTraits::InspectAt(empty.bytes.data(), empty.bytes.size(),
            (std::numeric_limits<std::size_t>::max)());
    });
    auto zero = RetailSaveStateLimits{}; zero.maxInputBytes = 0;
    Reject(s, Code::InputLimit, "Zero input limit", [&] { Parse(empty, zero); });
    zero = RetailSaveStateLimits{}; zero.maxPrefixBytes = 0;
    Reject(s, Code::PrefixLimit, "Zero prefix limit", [&] { Parse(empty, zero); });
    zero = RetailSaveStateLimits{}; zero.maxArrayRecords = 0;
    Reject(s, Code::ArrayLimit, "Zero array limit", [&] { Parse(empty, zero); });
    zero = RetailSaveStateLimits{}; zero.maxTotalRecords = 0;
    Reject(s, Code::TotalRecordLimit, "Zero aggregate limit", [&] { Parse(empty, zero); });
}
struct Observation { bool accepted = false; Result result; Code code = Code::InvalidValue; std::size_t offset = 0; };
Observation Observe(const Bytes& bytes, std::size_t start) {
    Observation observation;
    try {
        observation.result = RetailSavePlayerPostTraits::InspectAt(bytes.data(), bytes.size(), start);
        observation.accepted = true;
    } catch (const RetailStateError& error) { observation.code = error.Code(); observation.offset = error.Offset(); }
    return observation;
}
bool Same(const Observation& a, const Observation& b) {
    if (a.accepted != b.accepted) return false;
    if (!a.accepted) return a.code == b.code && a.offset == b.offset;
    const auto left = Spans(a.result), right = Spans(b.result);
    for (std::size_t i = 0; i < left.size(); ++i)
        if (left[i].offset != right[i].offset || left[i].bytes != right[i].bytes) return false;
    return a.result.hasNotifications == b.result.hasNotifications && a.result.arrayRecords == b.result.arrayRecords &&
        a.result.nextInflatedOffset == b.result.nextInflatedOffset &&
        a.result.completePlayerVerified == b.result.completePlayerVerified &&
        a.result.completeSaveVerified == b.result.completeSaveVerified &&
        a.result.rulesetCompatibilityVerified == b.result.rulesetCompatibilityVerified &&
        a.result.restoreApproved == b.result.restoreApproved;
}
std::uint32_t Random(std::uint32_t& state) {
    state ^= state << 13; state ^= state >> 17; state ^= state << 5; return state;
}
void Mutations(Suite& s, const std::vector<Fixture>& fixtures) {
    std::uint32_t random = 0x17a9c503u;
    for (std::size_t i = 0; i < 2048; ++i) {
        const auto& f = fixtures[(i / 8) % fixtures.size()]; auto bytes = f.bytes;
        switch (i % 8) {
        case 0: bytes[Random(random) % bytes.size()] ^= static_cast<unsigned char>(1u << (Random(random) % 8)); break;
        case 1: Put(bytes, f.versions[Random(random) % f.versions.size()], 0xffffffffu); break;
        case 2: bytes[f.bools[Random(random) % f.bools.size()]] = 2; break;
        case 3: {
            const auto& counts = (Random(random) & 1u) ? f.signedCounts : f.unsignedCounts;
            Put(bytes, counts[Random(random) % counts.size()], 0xffffffffu); break;
        }
        case 4: bytes.resize(Random(random) % (bytes.size() + 1)); break;
        case 5: bytes.push_back(static_cast<unsigned char>(Random(random))); break;
        case 6: Put(bytes, f.strings[Random(random) % f.strings.size()], Random(random)); break;
        default: Put(bytes, f.fixedCounts[Random(random) % f.fixedCounts.size()], Random(random) % 25u); break;
        }
        const auto before = bytes; const auto a = Observe(bytes, f.start), b = Observe(bytes, f.start);
        s.Check(Same(a, b), "Mutation outcome is nondeterministic");
        s.Check(bytes == before, "Mutation inspection changed input bytes");
        if (a.accepted) { Invariants(s, a.result, bytes.size(), f.start); ++s.accepted; }
        else { s.Check(a.offset <= bytes.size(), "Typed rejection offset exceeds input"); ++s.rejected; }
        ++s.mutations;
    }
    s.Check(s.accepted > 0 && s.rejected > 0, "Mutations missed successful structural reads or typed rejections");
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
    Result framed;
    std::size_t bytes = 0, mapEnd = 0, teamsEnd = 0, prefixEnd = 0, midEnd = 0, lateEnd = 0;
    std::uint32_t plots = 0, nextWord = 0;
};
PublicResult Public(Suite& s) {
    const auto bytes = ReadStdin(); const auto before = bytes;
    s.Check(bytes.size() == 9762327u, "Wrong authenticated public inflated corpus size");
    // The external wrapper authenticates the immutable public input in RAM.
    // These five profile values are explicit hypotheses, not ruleset proof.
    auto remaining = RetailSaveStateLimits{};
    const auto map = RetailSaveMap::InspectGameAndMap(bytes, RetailSaveStateProfile(5), remaining);
    s.Check(map.nextInflatedOffset == 1695150u && map.plotCount == 960u, "Public ordered Map boundary changed");
    s.Check(map.arrayRecords <= remaining.maxTotalRecords, "Map exhausted aggregate budget");
    remaining.maxTotalRecords -= map.arrayRecords;
    RetailStateDetail::Reader teams(bytes.data(), bytes.size(), remaining); teams.Skip(map.nextInflatedOffset);
    for (std::int32_t id = 0; id < 64; ++id)
        s.Check(RetailStateDetail::ReadTeam(teams) == id, "Public Team IDs are not sequential 0..63");
    s.Check(teams.Pos() == 2309550u && teams.Records() <= remaining.maxTotalRecords, "Public ordered Team boundary changed");
    remaining.maxTotalRecords -= teams.Records();
    const auto prefix = RetailSavePlayerPrefix::InspectAt(bytes.data(), bytes.size(), teams.Pos(),
        RetailSavePlayerProfile(4, RetailPlayerCatalogProfile::InitializedBuildings), remaining);
    s.Check(prefix.playerId == 0 && prefix.nextInflatedOffset == 2326136u, "Public Player prefix changed");
    s.Check(prefix.arrayRecords <= remaining.maxTotalRecords, "Player prefix exhausted aggregate budget");
    remaining.maxTotalRecords -= prefix.arrayRecords;
    const auto mid = RetailSavePlayerAiMid::InspectAt(bytes.data(), bytes.size(), prefix.nextInflatedOffset,
        RetailPlayerAiMidCatalogProfile::InitializedTechs, remaining);
    s.Check(mid.nextInflatedOffset == 2403477u && mid.arrayRecords <= remaining.maxTotalRecords,
            "Public Player middle boundary or shared budget changed");
    remaining.maxTotalRecords -= mid.arrayRecords;
    const auto late = RetailSavePlayerAiLate::InspectAt(bytes.data(), bytes.size(), mid.nextInflatedOffset,
        RetailPlayerAiLateProfile::InitializedMinorQuests, remaining);
    s.Check(late.nextInflatedOffset == 2421545u && late.dangerPlotCount == map.plotCount &&
            late.arrayRecords <= remaining.maxTotalRecords, "Public Traits boundary, danger grid or shared budget changed");
    remaining.maxTotalRecords -= late.arrayRecords;
    s.Check(!map.completeSaveVerified && !map.rulesetCompatibilityVerified && !prefix.completeSaveVerified &&
            !prefix.rulesetCompatibilityVerified && !mid.completeSaveVerified && !mid.rulesetCompatibilityVerified &&
            !late.completeSaveVerified && !late.rulesetCompatibilityVerified, "Earlier component granted restore/ruleset approval");
    PublicResult result;
    result.bytes = bytes.size(); result.mapEnd = map.nextInflatedOffset; result.plots = map.plotCount;
    result.teamsEnd = teams.Pos(); result.prefixEnd = prefix.nextInflatedOffset;
    result.midEnd = mid.nextInflatedOffset; result.lateEnd = late.nextInflatedOffset;
    result.framed = RetailSavePlayerPostTraits::InspectAt(bytes.data(), bytes.size(), late.nextInflatedOffset, remaining);
    Invariants(s, result.framed, bytes.size(), late.nextInflatedOffset);
    s.Check(result.framed.arrayRecords <= remaining.maxTotalRecords, "Post-Traits exhausted shared aggregate budget");
    // Observe one word only at the exact source-ordered m_cities boundary.
    // It is not searched for, assigned a version, or accepted as a full city.
    result.nextWord = Word(bytes, result.framed.nextInflatedOffset);
    s.Check(bytes == before, "Public framing changed stdin bytes"); return result;
}
void PublicJson(const PublicResult& p) {
    std::cout << ",\"public\":{\"input_bytes\":" << p.bytes << ",\"map_end\":" << p.mapEnd
        << ",\"map_plot_count\":" << p.plots << ",\"teams_end\":" << p.teamsEnd
        << ",\"player_prefix_end\":" << p.prefixEnd << ",\"player_ai_mid_end\":" << p.midEnd
        << ",\"player_ai_late_end\":" << p.lateEnd << ",\"start_offset\":" << p.lateEnd;
    const std::array<const char*, SpanCount> names = {"espionage", "espionage_ai", "trade", "trade_ai",
        "league_ai", "culture", "notifications", "treasury", "pre_city_fields"};
    const auto spans = Spans(p.framed);
    for (std::size_t i = 0; i < spans.size(); ++i)
        std::cout << ",\"" << names[i] << "_offset\":" << spans[i].offset << ",\"" << names[i] << "_bytes\":" << spans[i].bytes;
    std::cout << ",\"has_notifications\":" << (p.framed.hasNotifications ? "true" : "false")
        << ",\"next_inflated_offset\":" << p.framed.nextInflatedOffset << ",\"array_records\":" << p.framed.arrayRecords
        << ",\"next_word\":" << p.nextWord << ",\"victory_point_awards\":5,\"grand_strategy_count\":4"
        << ",\"building_catalog\":\"initialized\",\"tech_catalog\":\"initialized\",\"minor_quests\":\"initialized\""
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
        if (argc != 1 && !publicMode) throw std::invalid_argument("Usage: retail_player_post_traits [--public]");
        const std::vector<Fixture> fixtures = {Writer(0, 0).Finish(), Writer(1, 7).Finish(),
            Writer(2, 11).Finish(), Writer(3, 13).Finish()};
        for (const auto& fixture : fixtures) Golden(suite, fixture);
        Cuts(suite, fixtures[3]); Negative(suite, fixtures[0], fixtures[3]); Mutations(suite, fixtures);
        PublicResult publicResult; if (publicMode) publicResult = Public(suite);
        std::cout << "{\"status\":\"PASS_RETAIL_PLAYER_POST_TRAITS_COMPONENT\",\"checks\":" << suite.checks
            << ",\"synthetic_cases\":4,\"truncations\":" << suite.truncations << ",\"mutations\":" << suite.mutations
            << ",\"accepted_mutations\":" << suite.accepted << ",\"rejected_mutations\":" << suite.rejected
            << ",\"input_files_unchanged\":true,\"input_bytes_unchanged\":true,\"gamecore_loaded\":false,\"window_created\":false"
            << ",\"game_accessed\":false,\"user_saves_accessed\":false,\"complete_player_validated\":false"
            << ",\"complete_save_validated\":false,\"ruleset_compatibility_verified\":false,\"restore_approved\":false";
        if (publicMode) PublicJson(publicResult);
        std::cout << "}\n"; return 0;
    } catch (const std::exception& error) {
        std::cout << "{\"status\":\"FAIL_RETAIL_PLAYER_POST_TRAITS_COMPONENT\",\"checks\":" << suite.checks
            << ",\"error\":\"" << Escape(error.what()) << "\",\"gamecore_loaded\":false,\"window_created\":false"
            << ",\"user_saves_accessed\":false,\"complete_player_validated\":false,\"complete_save_validated\":false"
            << ",\"ruleset_compatibility_verified\":false,\"restore_approved\":false}\n"; return 1;
    }
}
