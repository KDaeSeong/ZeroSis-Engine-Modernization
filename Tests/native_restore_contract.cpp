#include "NativeRestoreContract.h"
#include <algorithm>
#include <array>
#include <climits>
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

// Portable production-contract tests: no SDK object or platform restore runs.
// The test-only SHA callback is reused from native_save_envelope.cpp and does
// not replace the production Windows CNG implementation. Known-answer sources:
// https://www.nist.gov/itl/ai/ai-standards-and-guidelines-group/nsrl-test-data
// https://www.rfc-editor.org/rfc/rfc8760.txt
namespace {
using namespace ZeroSisHost;
using Envelope = NativeSaveEnvelope;
using Bytes = std::vector<unsigned char>;
using Hash = std::array<unsigned char, 32>;
using Contract = NativeRestoreContract;
constexpr std::size_t MaximumInputBytes = 32u * 1024u * 1024u;
constexpr std::size_t GameBytes = 4902u;
constexpr std::size_t ReplayCount = 2868u;
constexpr std::size_t ReplayRecords = 2872u;
constexpr std::size_t AiAutoPlay = 88u;
constexpr std::size_t GameState = 158u;
constexpr std::size_t MapRandom = 2830u;
constexpr std::size_t JonRandom = 2847u;
struct Suite {
    std::size_t checks = 0, truncations = 0, corruptions = 0, atomicFailures = 0;
    std::size_t literalCases = 0, validCases = 0, shaVectors = 0;
    void Check(bool value, const char* message) {
        ++checks;
        if (!value) throw std::runtime_error(message);
    }
};
constexpr std::array<std::uint32_t, 64> RoundConstants = {{
    0x428a2f98u,0x71374491u,0xb5c0fbcfu,0xe9b5dba5u,0x3956c25bu,0x59f111f1u,0x923f82a4u,0xab1c5ed5u,
    0xd807aa98u,0x12835b01u,0x243185beu,0x550c7dc3u,0x72be5d74u,0x80deb1feu,0x9bdc06a7u,0xc19bf174u,
    0xe49b69c1u,0xefbe4786u,0x0fc19dc6u,0x240ca1ccu,0x2de92c6fu,0x4a7484aau,0x5cb0a9dcu,0x76f988dau,
    0x983e5152u,0xa831c66du,0xb00327c8u,0xbf597fc7u,0xc6e00bf3u,0xd5a79147u,0x06ca6351u,0x14292967u,
    0x27b70a85u,0x2e1b2138u,0x4d2c6dfcu,0x53380d13u,0x650a7354u,0x766a0abbu,0x81c2c92eu,0x92722c85u,
    0xa2bfe8a1u,0xa81a664bu,0xc24b8b70u,0xc76c51a3u,0xd192e819u,0xd6990624u,0xf40e3585u,0x106aa070u,
    0x19a4c116u,0x1e376c08u,0x2748774cu,0x34b0bcb5u,0x391c0cb3u,0x4ed8aa4au,0x5b9cca4fu,0x682e6ff3u,
    0x748f82eeu,0x78a5636fu,0x84c87814u,0x8cc70208u,0x90befffau,0xa4506cebu,0xbef9a3f7u,0xc67178f2u
}};
class TestSha256 final {
public:
    void Update(const unsigned char* data, std::size_t size) {
        if ((!data && size) || size > (std::numeric_limits<std::uint64_t>::max)() - total_)
            throw std::invalid_argument("Invalid test SHA input");
        total_ += static_cast<std::uint64_t>(size);
        while (size) {
            const auto count = (std::min)(size, block_.size() - used_);
            std::copy(data, data + count, block_.begin() + static_cast<std::ptrdiff_t>(used_));
            data += count; size -= count; used_ += count;
            if (used_ == block_.size()) { Transform(); used_ = 0; }
        }
    }
    Hash Finish() {
        if (total_ > (std::numeric_limits<std::uint64_t>::max)() / 8u)
            throw std::invalid_argument("Test SHA bit length exceeds its wire field");
        const auto bits = total_ * 8u;
        block_[used_++] = 128;
        if (used_ > 56u) {
            std::fill(block_.begin() + static_cast<std::ptrdiff_t>(used_), block_.end(), static_cast<unsigned char>(0));
            Transform(); used_ = 0;
        }
        std::fill(block_.begin() + static_cast<std::ptrdiff_t>(used_), block_.begin() + 56, static_cast<unsigned char>(0));
        for (unsigned i = 0; i < 8u; ++i) block_[63u - i] = static_cast<unsigned char>(bits >> (8u * i));
        Transform();
        Hash result{};
        for (std::size_t i = 0; i < state_.size(); ++i)
            for (unsigned j = 0; j < 4u; ++j) result[4u * i + j] = static_cast<unsigned char>(state_[i] >> (24u - 8u * j));
        return result;
    }
private:
    static std::uint32_t Rotate(std::uint32_t value, unsigned amount) {
        return (value >> amount) | (value << (32u - amount));
    }
    void Transform() {
        std::array<std::uint32_t, 64> words{};
        for (std::size_t i = 0; i < 16u; ++i) {
            const auto* p = block_.data() + 4u * i;
            words[i] = (static_cast<std::uint32_t>(p[0]) << 24) | (static_cast<std::uint32_t>(p[1]) << 16) |
                (static_cast<std::uint32_t>(p[2]) << 8) | static_cast<std::uint32_t>(p[3]);
        }
        for (std::size_t i = 16; i < words.size(); ++i) {
            const auto a = words[i - 15u], b = words[i - 2u];
            words[i] = words[i - 16u] + (Rotate(a,7) ^ Rotate(a,18) ^ (a >> 3)) + words[i - 7u] +
                (Rotate(b,17) ^ Rotate(b,19) ^ (b >> 10));
        }
        auto a = state_[0], b = state_[1], c = state_[2], d = state_[3];
        auto e = state_[4], f = state_[5], g = state_[6], h = state_[7];
        for (std::size_t i = 0; i < words.size(); ++i) {
            const auto first = h + (Rotate(e,6) ^ Rotate(e,11) ^ Rotate(e,25)) + ((e & f) ^ (~e & g)) +
                RoundConstants[i] + words[i];
            const auto second = (Rotate(a,2) ^ Rotate(a,13) ^ Rotate(a,22)) + ((a & b) ^ (a & c) ^ (b & c));
            h = g; g = f; f = e; e = d + first; d = c; c = b; b = a; a = first + second;
        }
        state_[0] += a; state_[1] += b; state_[2] += c; state_[3] += d;
        state_[4] += e; state_[5] += f; state_[6] += g; state_[7] += h;
    }
    std::array<std::uint32_t, 8> state_ = {{
        0x6a09e667u,0xbb67ae85u,0x3c6ef372u,0xa54ff53au,0x510e527fu,0x9b05688cu,0x1f83d9abu,0x5be0cd19u}};
    std::array<unsigned char, 64> block_{};
    std::size_t used_ = 0;
    std::uint64_t total_ = 0;
};
Hash Digest(const unsigned char* data, std::size_t size) {
    TestSha256 hash; hash.Update(data, size); return hash.Finish();
}
std::string Hex(const Hash& hash) {
    constexpr char Digits[] = "0123456789abcdef";
    std::string result; result.reserve(64);
    for (const auto byte : hash) { result.push_back(Digits[byte >> 4]); result.push_back(Digits[byte & 15u]); }
    return result;
}

void Put32(Bytes& bytes, std::size_t at, std::uint32_t value) {
    if (at > bytes.size() || bytes.size() - at < 4u)
        throw std::logic_error("Test patch exceeds its literal input");
    for (unsigned shift = 0; shift < 32u; shift += 8u)
        bytes[at + shift / 8u] = static_cast<unsigned char>(value >> shift);
}
void Append32(Bytes& bytes, std::uint32_t value) {
    const auto at = bytes.size(); bytes.resize(at + 4u); Put32(bytes, at, value);
}
void Append16(Bytes& bytes, std::int16_t value) {
    const auto bits = static_cast<std::uint16_t>(value);
    bytes.push_back(static_cast<unsigned char>(bits));
    bytes.push_back(static_cast<unsigned char>(bits >> 8));
}
Bytes Record(std::int32_t turn, std::int32_t kind,
    const std::vector<std::pair<std::int16_t, std::int16_t>>& plots,
    std::int32_t player, const std::string& text) {
    Bytes bytes;
    Append32(bytes, static_cast<std::uint32_t>(turn));
    Append32(bytes, static_cast<std::uint32_t>(kind));
    Append32(bytes, static_cast<std::uint32_t>(plots.size()));
    for (const auto& plot : plots) { Append16(bytes, plot.first); Append16(bytes, plot.second); }
    Append32(bytes, static_cast<std::uint32_t>(player));
    Append32(bytes, static_cast<std::uint32_t>(text.size()));
    bytes.insert(bytes.end(), text.begin(), text.end());
    return bytes;
}
Bytes Reload(std::int32_t turn, std::int32_t player, const std::string& text) {
    return Record(turn, 0, {{std::int16_t{-1},std::int16_t{-1}}}, player, text);
}
struct Fixture {
    Bytes bytes;
    std::size_t countOffset = ReplayCount, recordOffset = ReplayRecords, recordBytes = 0;
    std::size_t sessionOffset = ReplayRecords;
    std::size_t mapRandom = MapRandom, jonRandom = JonRandom;
    std::size_t gameStateOffset = GameState, advisorBytes = 4;
};
Fixture Game(const std::vector<Bytes>& messages, std::int32_t sessions,
    const Bytes& script = {}, const Bytes& database = {},
    const std::vector<std::string>& advisors = {}) {
    // Independently summed literal layout, not a production writer:
    // Game front 2889, Deals16, Religions12, Culture9, Leagues24,
    // Trade1948, embedded-database length4 = 4902 bytes with empty containers.
    // Fixed arrays are zero-filled at their source-defined widths. Empty vote
    // free lists retain literal last=-1/head=-1/currentID=8192 metadata.
    Fixture f; f.bytes.assign(GameBytes, 0);
    Put32(f.bytes, 0, 1); Put32(f.bytes, 8, 3); f.bytes[122] = 1;
    Put32(f.bytes, 2786, 0xffffffffu); Put32(f.bytes, 2790, 0xffffffffu);
    Put32(f.bytes, 2798, 8192);
    Put32(f.bytes, 2810, 0xffffffffu); Put32(f.bytes, 2814, 0xffffffffu);
    Put32(f.bytes, 2822, 8192);
    Put32(f.bytes, MapRandom, 1); Put32(f.bytes, MapRandom + 4u, 0x10203040u);
    Put32(f.bytes, MapRandom + 8u, 7); Put32(f.bytes, MapRandom + 12u, 11);
    Put32(f.bytes, JonRandom, 1); Put32(f.bytes, JonRandom + 4u, 0x89abcdefu);
    Put32(f.bytes, JonRandom + 8u, 13); Put32(f.bytes, JonRandom + 12u, 17);
    Put32(f.bytes, 2864, 2); Put32(f.bytes, ReplayCount, static_cast<std::uint32_t>(messages.size()));
    Put32(f.bytes, ReplayRecords, static_cast<std::uint32_t>(sessions));
    Put32(f.bytes, 2889, 1); Put32(f.bytes, 2905, 4); Put32(f.bytes, 2909, 100);
    Put32(f.bytes, 2917, 2); Put32(f.bytes, 2926, 5); Put32(f.bytes, 2950, 3);
    Put32(f.bytes, 4898, static_cast<std::uint32_t>(database.size()));
    f.bytes.insert(f.bytes.end(), database.begin(), database.end());
    Bytes records;
    for (const auto& message : messages) records.insert(records.end(), message.begin(), message.end());
    f.bytes.insert(f.bytes.begin() + static_cast<std::ptrdiff_t>(ReplayRecords), records.begin(), records.end());
    f.recordBytes = records.size(); f.sessionOffset += records.size();
    Put32(f.bytes, 182, static_cast<std::uint32_t>(script.size()));
    f.bytes.insert(f.bytes.begin() + 186, script.begin(), script.end());
    f.countOffset += script.size(); f.recordOffset += script.size(); f.sessionOffset += script.size();
    f.mapRandom += script.size(); f.jonRandom += script.size();
    Bytes advisorData;
    for (const auto& message : advisors) {
        Append32(advisorData, static_cast<std::uint32_t>(message.size()));
        advisorData.insert(advisorData.end(), message.begin(), message.end());
    }
    Put32(f.bytes, 130, static_cast<std::uint32_t>(advisors.size()));
    f.bytes.insert(f.bytes.begin() + 134, advisorData.begin(), advisorData.end());
    f.countOffset += advisorData.size(); f.recordOffset += advisorData.size(); f.sessionOffset += advisorData.size();
    f.mapRandom += advisorData.size(); f.jonRandom += advisorData.size(); f.gameStateOffset += advisorData.size();
    f.advisorBytes += advisorData.size();
    return f;
}
Envelope Archive(const Fixture& game, unsigned flags = 0) {
    Envelope value; value.flags = flags; value.turn = 23; value.elapsed = 3; value.activePlayer = 7;
    for (unsigned i = 0; i < 133u; ++i) {
        NativeSaveSection section;
        section.kind = i < 5u ? i + 1u : (i < 69u ? 6u : 7u);
        section.index = i < 5u ? 0u : (i < 69u ? i - 5u : i - 69u);
        section.bytes = {0, static_cast<unsigned char>(i), 255, 128,
            static_cast<unsigned char>(i ^ 165u), 1};
        if (i == 2u) section.bytes = game.bytes;
        value.sections.push_back(std::move(section));
    }
    return value;
}
bool Same(const Envelope& a, const Envelope& b) {
    if (a.flags != b.flags || a.turn != b.turn || a.elapsed != b.elapsed ||
        a.activePlayer != b.activePlayer || a.sections.size() != b.sections.size()) return false;
    for (std::size_t i = 0; i < a.sections.size(); ++i) {
        if (a.sections[i].kind != b.sections[i].kind || a.sections[i].index != b.sections[i].index ||
            a.sections[i].bytes != b.sections[i].bytes) return false;
    }
    return true;
}
void KnownAnswers(Suite& suite) {
    struct Vector { const char* text; const char* hash; };
    const Vector vectors[] = {
        {"", "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"},
        {"abc", "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"},
        {"abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq",
         "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1"}
    };
    for (const auto& vector : vectors) {
        suite.Check(Hex(Digest(reinterpret_cast<const unsigned char*>(vector.text),
            std::strlen(vector.text))) == vector.hash, "Test-only SHA known-answer mismatch");
        ++suite.shaVectors;
    }
}
Bytes LiteralReload() {
    // Independent exact version-2 record: turn23, major event0, plot(-1,-1),
    // player7, 16 UTF-8 bytes. No production serializer builds this oracle.
    const unsigned char literal[] = {
        23,0,0,0, 0,0,0,0, 1,0,0,0, 255,255,255,255,
        7,0,0,0, 16,0,0,0, 'S','e','s','s','i','o','n',' ','2',' ','s','t','a','r','t','s'
    };
    return Bytes(literal, literal + sizeof(literal));
}
bool SameLayout(const NativeRestoreGameLayout& a, const NativeRestoreGameLayout& b) {
    return a.replayMessages == b.replayMessages && a.sessions == b.sessions &&
        a.replayCountOffset == b.replayCountOffset && a.replayRecords.offset == b.replayRecords.offset &&
        a.replayRecords.bytes == b.replayRecords.bytes && a.sessionOffset == b.sessionOffset &&
        a.aiAutoPlayOffset == b.aiAutoPlayOffset && a.gameStateOffset == b.gameStateOffset &&
        a.aiAutoPlay == b.aiAutoPlay && a.gameState == b.gameState &&
        a.advisorMessages.offset == b.advisorMessages.offset && a.advisorMessages.bytes == b.advisorMessages.bytes &&
        a.mapRandom.seedOffset == b.mapRandom.seedOffset && a.mapRandom.callCountOffset == b.mapRandom.callCountOffset &&
        a.mapRandom.resetCountOffset == b.mapRandom.resetCountOffset && a.mapRandom.seed == b.mapRandom.seed &&
        a.mapRandom.calls == b.mapRandom.calls && a.mapRandom.resets == b.mapRandom.resets &&
        a.jonRandom.seedOffset == b.jonRandom.seedOffset && a.jonRandom.callCountOffset == b.jonRandom.callCountOffset &&
        a.jonRandom.resetCountOffset == b.jonRandom.resetCountOffset && a.jonRandom.seed == b.jonRandom.seed &&
        a.jonRandom.calls == b.jonRandom.calls && a.jonRandom.resets == b.jonRandom.resets;
}
NativeRestoreGameLayout Inspect(Suite& suite, const Fixture& fixture,
    std::uint32_t count, std::int32_t sessions, const RetailSaveStateLimits& limits = {}) {
    const auto input = fixture.bytes;
    const auto value = Contract::InspectGame(fixture.bytes, RetailSaveStateProfile(5), limits);
    suite.Check(fixture.bytes == input, "InspectGame mutated its input");
    suite.Check(value.replayMessages == count && value.sessions == sessions, "Literal replay/session values differ");
    suite.Check(value.replayCountOffset == fixture.countOffset && value.replayRecords.offset == fixture.recordOffset &&
        value.replayRecords.bytes == fixture.recordBytes && value.sessionOffset == fixture.sessionOffset,
        "Source-order replay boundary differs from independent offsets");
    suite.Check(value.aiAutoPlayOffset == AiAutoPlay && value.gameStateOffset == fixture.gameStateOffset,
        "Source-order scalar offsets differ from their literal positions");
    suite.Check(value.advisorMessages.offset == 130u && value.advisorMessages.bytes == fixture.advisorBytes,
        "Source-order advisor span differs from its independent count/string layout");
    suite.Check(value.mapRandom.seedOffset == fixture.mapRandom + 4u &&
        value.mapRandom.callCountOffset == fixture.mapRandom + 8u &&
        value.mapRandom.resetCountOffset == fixture.mapRandom + 12u &&
        value.jonRandom.seedOffset == fixture.jonRandom + 4u &&
        value.jonRandom.callCountOffset == fixture.jonRandom + 8u &&
        value.jonRandom.resetCountOffset == fixture.jonRandom + 12u, "Literal RNG offsets differ");
    return value;
}
void Accept(Suite& suite, const Envelope& before, const Envelope& after,
    bool newSeed = false, const std::string& text = "Session 2 starts", const RetailSaveStateLimits& limits = {}) {
    const auto a = before, b = after;
    suite.Check(Contract::Verify(before, after, RetailSaveStateProfile(5), newSeed, text, limits) == 132u,
        "Verify did not report exactly 132 preserved non-game sections");
    suite.Check(Same(before, a) && Same(after, b), "Successful comparison mutated a source envelope");
    ++suite.validCases;
}
void Reject(Suite& suite, const Envelope& before, const Envelope& after,
    bool newSeed = false, const std::string& text = "Session 2 starts", const RetailSaveStateLimits& limits = {}) {
    const auto a = before, b = after;
    unsigned output = 0x5a5aa5a5u;
    bool rejected = false;
    try { output = Contract::Verify(before, after, RetailSaveStateProfile(5), newSeed, text, limits); }
    catch (const std::exception&) { rejected = true; }
    suite.Check(rejected, "An unauthorized restore delta was accepted");
    suite.Check(output == 0x5a5aa5a5u, "Failure published a partial comparison result");
    suite.Check(Same(before, a) && Same(after, b), "Failed comparison mutated an input envelope");
    ++suite.corruptions; ++suite.atomicFailures;
}
void RejectInspect(Suite& suite, const Bytes& input, const RetailSaveStateLimits& limits = {},
    bool exact = false, RetailStateErrorCode code = RetailStateErrorCode::Truncated, std::size_t offset = 0) {
    const auto before = input;
    NativeRestoreGameLayout sentinel;
    sentinel.sessions = -717; sentinel.replayMessages = 79; sentinel.replayCountOffset = 991;
    auto output = sentinel;
    bool rejected = false, exactMatched = false;
    try { output = Contract::InspectGame(input, RetailSaveStateProfile(5), limits); }
    catch (const RetailStateError& error) {
        rejected = true; exactMatched = error.Code() == code && error.Offset() == offset;
    }
    catch (const std::exception&) { rejected = true; }
    suite.Check(rejected, "Malformed or unbounded Game section was accepted");
    suite.Check(!exact || exactMatched, "Game error code/offset differs from the wire contract");
    suite.Check(SameLayout(output, sentinel) && input == before, "Inspection failure changed its output or input");
    ++suite.atomicFailures;
}
void LiteralAndCounts(Suite& suite) {
    const auto before = Game({}, 1);
    suite.Check(before.bytes.size() == 4902u && before.sessionOffset == 2872u,
        "Minimal complete Game wire-size oracle differs");
    const auto layout = Inspect(suite, before, 0, 1);
    suite.Check(layout.mapRandom.seed == 0x10203040u && layout.mapRandom.calls == 7u && layout.mapRandom.resets == 11u &&
        layout.jonRandom.seed == 0x89abcdefu && layout.jonRandom.calls == 13u && layout.jonRandom.resets == 17u,
        "Independent RNG values differ");
    const auto preflight = Contract::PreflightGame(before.bytes, RetailSaveStateProfile(5));
    suite.Check(SameLayout(layout, preflight), "Preflight changed a valid structural layout");
    const auto event = LiteralReload();
    suite.Check(event == Reload(23, 7, "Session 2 starts"), "Independent literal reload record differs");
    const auto after = Game({event}, 2);
    Inspect(suite, after, 1, 2);
    Accept(suite, Archive(before), Archive(after));
    ++suite.literalCases;
    for (const auto count : {2u,255u,256u}) {
        std::vector<Bytes> messages;
        for (unsigned i = 0; i < count; ++i)
            messages.push_back(Record(static_cast<std::int32_t>(i), 3,
                {{std::int16_t{-32768},std::int16_t{32767}},{std::int16_t{17},std::int16_t{-29}}},
                63, std::string("old\0", 4) + u8"기록"));
        const auto original = Game(messages, 255);
        messages.push_back(Reload(23, 7, "Session 256 starts"));
        const auto recaptured = Game(messages, 256);
        Inspect(suite, original, count, 255); Inspect(suite, recaptured, count + 1u, 256);
        Accept(suite, Archive(original), Archive(recaptured), false, "Session 256 starts");
        ++suite.literalCases;
    }
    const auto upper = Game({}, INT_MAX - 1);
    const std::string text = "Session 2,147,483,647 starts";
    const auto maximum = Game({Reload(23, 7, text)}, INT_MAX);
    Accept(suite, Archive(upper), Archive(maximum), false, text);
    for (const auto sessions : {0,-1,INT_MAX}) {
        const auto fixture = Game({}, sessions);
        const auto input = fixture.bytes;
        bool rejected = false;
        try { (void)Contract::PreflightGame(fixture.bytes, RetailSaveStateProfile(5)); }
        catch (const std::invalid_argument&) { rejected = true; }
        suite.Check(rejected && fixture.bytes == input, "Unsafe session increment passed preflight");
        ++suite.corruptions;
    }
}
void SourceOrderAndFraming(Suite& suite) {
    Bytes script = {2,0,0,0, 0,0,0,0, 1,0,0,0, 0,255,128,0};
    const Bytes database = {0,255,2,0,0,0,0,0,0,0,1,0,0,0,128,17};
    const auto before = Game({}, 1, script, database);
    const auto after = Game({LiteralReload()}, 2, script, database);
    Inspect(suite, before, 0, 1); Inspect(suite, after, 1, 2);
    Accept(suite, Archive(before), Archive(after));
    ++suite.literalCases;

    // An actual first-difference false island in the fixed player-int array.
    // A heuristic parser sees version2/count0/session1 at 186/190/194 and an
    // appended record in its counterpart. The real source-order Game framing
    // must reject that counterpart, rather than bless the fake inner island.
    auto island = Game({}, 1);
    Put32(island.bytes, 186, 2); Put32(island.bytes, 190, 0); Put32(island.bytes, 194, 1);
    Inspect(suite, island, 0, 1);
    auto falseTarget = island;
    const auto event = LiteralReload();
    falseTarget.bytes.insert(falseTarget.bytes.begin() + 194, event.begin(), event.end());
    Put32(falseTarget.bytes, 190, 1); Put32(falseTarget.bytes, 194u + event.size(), 2);
    Reject(suite, Archive(island), Archive(falseTarget));
    RejectInspect(suite, falseTarget.bytes);
    ++suite.literalCases;

    const auto plain = Game({}, 1);
    std::vector<std::size_t> cuts = {0,1,2,3,4,7,8,119,120,129,130,133,134,181,182,185,186,
        1977,1978,2009,2010,2765,2766,2781,2782,2805,2806,2829,2830,2846,2847,2863,2864,
        2867,2868,2871,2872,2875,2876,2888,2889,2904,2905,2916,2917,2925,2926,2949,2950,
        2957,2958,4893,4894,4897,4898,4899,4900,4901};
    for (const auto cut : cuts) {
        const Bytes truncated(plain.bytes.begin(), plain.bytes.begin() + static_cast<std::ptrdiff_t>(cut));
        RejectInspect(suite, truncated); ++suite.truncations;
    }
    for (std::size_t cut = before.recordOffset; cut < after.sessionOffset + 4u; ++cut) {
        const Bytes truncated(after.bytes.begin(), after.bytes.begin() + static_cast<std::ptrdiff_t>(cut));
        RejectInspect(suite, truncated); ++suite.truncations;
    }
    auto malformed = plain.bytes; Put32(malformed, 0, 2);
    RejectInspect(suite, malformed, {}, true, RetailStateErrorCode::UnsupportedVersion, 4);
    malformed = plain.bytes; malformed[120] = 2;
    RejectInspect(suite, malformed, {}, true, RetailStateErrorCode::InvalidValue, 121);
    malformed = plain.bytes; Put32(malformed, ReplayCount, 0xffffffffu);
    RejectInspect(suite, malformed, {}, true, RetailStateErrorCode::InvalidValue, ReplayCount + 4u);
    malformed = plain.bytes; malformed.push_back(0);
    RejectInspect(suite, malformed, {}, true, RetailStateErrorCode::InvalidValue, plain.bytes.size());
    malformed = plain.bytes; Put32(malformed, 4898, 1);
    RejectInspect(suite, malformed, {}, true, RetailStateErrorCode::Truncated, 4902);
    malformed = plain.bytes; malformed[MapRandom + 16u] = 1;
    RejectInspect(suite, malformed, {}, true, RetailStateErrorCode::UnsupportedProfile, MapRandom + 17u);
}
void EnvelopeAndPreservation(Suite& suite) {
    const auto original = Archive(Game({}, 1));
    const auto recaptured = Archive(Game({LiteralReload()}, 2));
    for (unsigned flags = 0; flags <= 3u; ++flags) {
        auto source = original; source.flags = flags;
        Accept(suite, source, recaptured);
    }
    for (unsigned flags = 1; flags <= 4u; ++flags) {
        auto target = recaptured; target.flags = flags;
        Reject(suite, original, target);
    }
    auto source = original; source.flags = 4;
    Reject(suite, source, recaptured);
    for (unsigned field = 0; field < 3u; ++field) {
        auto target = recaptured;
        if (field == 0) ++target.turn;
        else if (field == 1) ++target.elapsed;
        else ++target.activePlayer;
        Reject(suite, original, target);
    }
    for (std::size_t i = 0; i < original.sections.size(); ++i) {
        if (i == 2u) continue;
        auto target = recaptured; target.sections[i].bytes[0] ^= 1u;
        Reject(suite, original, target);
    }
    for (const auto index : {0u,1u,2u,3u,4u,5u,68u,69u,132u}) {
        auto target = recaptured; ++target.sections[index].index;
        Reject(suite, original, target);
        target = recaptured; ++target.sections[index].kind;
        Reject(suite, original, target);
        target = recaptured; target.sections[index].bytes.clear();
        Reject(suite, original, target);
    }
    auto target = recaptured; target.sections.pop_back();
    Reject(suite, original, target);
    target = recaptured; std::swap(target.sections[5], target.sections[6]);
    Reject(suite, original, target);

    const Bytes script = {'o','p','a','q','u','e',0,255};
    const Bytes database = {0,255,128,17,2,0,0,0};
    const auto a = Game({}, 1, script, database);
    const auto b = Game({LiteralReload()}, 2, script, database);
    for (const auto position : {std::size_t(8),std::size_t(16),std::size_t(120),std::size_t(186),
                               b.sessionOffset + 12u,b.sessionOffset + 13u,b.bytes.size() - 1u}) {
        auto changed = b; changed.bytes[position] ^= 1u;
        Reject(suite, Archive(a), Archive(changed));
    }
    auto extended = b; extended.bytes.push_back(0);
    Reject(suite, Archive(a), Archive(extended));
}
void ReplayAndText(Suite& suite) {
    const auto source = Archive(Game({}, 1));
    const std::string expected = "Session 2 starts";
    const std::vector<Bytes> invalid = {
        Reload(24, 7, expected), Record(23, 1, {{std::int16_t{-1},std::int16_t{-1}}}, 7, expected),
        Record(23, 0, {}, 7, expected), Record(23, 0, {{std::int16_t{0},std::int16_t{-1}}}, 7, expected),
        Record(23, 0, {{std::int16_t{-1},std::int16_t{-1}},{std::int16_t{-1},std::int16_t{-1}}},
            7, expected), Reload(23, 8, expected),
        Reload(23, 7, "Session 3 starts"), Reload(23, 7, std::string("\xff", 1))
    };
    for (const auto& event : invalid) Reject(suite, source, Archive(Game({event}, 2)));
    for (const auto sessions : {0,1,3,-1,INT_MAX})
        Reject(suite, source, Archive(Game({LiteralReload()}, sessions)));
    Reject(suite, source, Archive(Game({}, 2)));
    Reject(suite, source, Archive(Game({LiteralReload(),LiteralReload()}, 2)));
    const auto old = Record(3, 3,
        {{std::int16_t{-32768},std::int16_t{32767}},{std::int16_t{17},std::int16_t{-29}}},
        4, std::string("A\0B", 3));
    const auto initial = Archive(Game({old}, 1));
    auto preserved = Game({old,LiteralReload()}, 2);
    Accept(suite, initial, Archive(preserved));
    for (const auto delta : {0u,4u,12u,16u,20u,24u,28u}) {
        auto changed = preserved;
        changed.bytes[changed.recordOffset + delta] ^= 1u;
        Reject(suite, initial, Archive(changed));
    }
    const std::string validTexts[] = {
        "", "ASCII", u8"세션 2가 시작됐습니다.", std::string("\xc2\x80", 2),
        std::string("\xe0\xa0\x80", 3), std::string("\xed\x9f\xbf", 3),
        std::string("\xf0\x90\x80\x80", 4), std::string("\xf4\x8f\xbf\xbf", 4)
    };
    for (const auto& text : validTexts)
        Accept(suite, source, Archive(Game({Reload(23, 7, text)}, 2)), false, text);
    const std::string invalidTexts[] = {
        std::string("A\0B", 3), std::string("\x80", 1), std::string("\xc0\xaf", 2),
        std::string("\xc2", 1), std::string("\xe0\x80\x80", 3), std::string("\xed\xa0\x80", 3),
        std::string("\xf0\x80\x80\x80", 4), std::string("\xf4\x90\x80\x80", 4),
        std::string("\xf5\x80\x80\x80", 4), std::string("\xc2" "A", 2)
    };
    for (const auto& text : invalidTexts) {
        // Matching invalid bytes must still fail the real helper's UTF-8 gate.
        Reject(suite, source, Archive(Game({Reload(23, 7, text)}, 2)), false, text);
    }
}
void NormalizationsAndRandom(Suite& suite) {
    for (const auto autoPlay : {0,1,29,-1}) {
        auto a = Game({}, 1); auto b = Game({LiteralReload()}, 2);
        Put32(a.bytes, AiAutoPlay, static_cast<std::uint32_t>(autoPlay));
        Put32(b.bytes, AiAutoPlay, static_cast<std::uint32_t>(autoPlay > 0 ? 1 : autoPlay));
        Accept(suite, Archive(a), Archive(b));
        Put32(b.bytes, AiAutoPlay, autoPlay > 0 ? 2u : 1u);
        Reject(suite, Archive(a), Archive(b));
    }
    for (const auto state : {0u,1u,2u}) {
        auto a = Game({}, 1); auto b = Game({LiteralReload()}, 2);
        Put32(a.bytes, GameState, state); Put32(b.bytes, GameState, state == 1u ? 2u : state);
        Accept(suite, Archive(a), Archive(b));
        Put32(b.bytes, GameState, state == 1u ? 1u : (state == 0u ? 2u : 0u));
        Reject(suite, Archive(a), Archive(b));
    }
    for (const auto resets : {17u,0xffffffffu}) {
        for (const auto seed : {0u,0x89abcdefu,0xffffffffu}) {
            auto a = Game({}, 1); auto b = Game({LiteralReload()}, 2);
            Put32(a.bytes, JonRandom + 12u, resets);
            Put32(b.bytes, JonRandom + 4u, seed);
            Put32(b.bytes, JonRandom + 12u, static_cast<std::uint32_t>(resets + 1u));
            Accept(suite, Archive(a), Archive(b), true);
            Reject(suite, Archive(a), Archive(b), false);
        }
    }
    const auto original = Game({}, 1);
    auto reseeded = Game({LiteralReload()}, 2);
    Put32(reseeded.bytes, JonRandom + 4u, 3); Put32(reseeded.bytes, JonRandom + 12u, 18);
    for (const auto position : {MapRandom + 4u,MapRandom + 8u,MapRandom + 12u,JonRandom + 8u}) {
        auto changed = reseeded; changed.bytes[position] ^= 1u;
        Reject(suite, Archive(original), Archive(changed), true);
    }
    auto changed = reseeded; Put32(changed.bytes, JonRandom + 8u, 0);
    Reject(suite, Archive(original), Archive(changed), true);
    for (const auto reset : {17u,19u}) {
        changed = reseeded; Put32(changed.bytes, JonRandom + 12u, reset);
        Reject(suite, Archive(original), Archive(changed), true);
    }
    auto a = Game({}, 1); auto b = reseeded;
    Put32(a.bytes, AiAutoPlay, 9); Put32(b.bytes, AiAutoPlay, 1);
    Put32(a.bytes, GameState, 1); Put32(b.bytes, GameState, 2);
    Accept(suite, Archive(a, 1), Archive(b), true);
}
void LimitsAndProfiles(Suite& suite) {
    const auto empty = Game({}, 1);
    RetailSaveStateLimits limits;
    limits.maxInputBytes = empty.bytes.size(); limits.maxPrefixBytes = empty.bytes.size();
    limits.maxTotalRecords = 0; limits.maxArrayRecords = 0; limits.maxStringBytes = 0;
    Inspect(suite, empty, 0, 1, limits);
    limits.maxInputBytes -= 1u;
    RejectInspect(suite, empty.bytes, limits, true, RetailStateErrorCode::InputLimit, 0);
    limits = {}; limits.maxPrefixBytes = empty.bytes.size() - 1u;
    RejectInspect(suite, empty.bytes, limits, true, RetailStateErrorCode::PrefixLimit, 4898);
    limits = {}; limits.booleanWireProfile = static_cast<RetailBooleanWireProfile>(77);
    RejectInspect(suite, empty.bytes, limits, true, RetailStateErrorCode::UnsupportedProfile, 0);
    for (const auto awards : {0u,4096u}) {
        const auto layout = Contract::InspectGame(empty.bytes, RetailSaveStateProfile(awards));
        suite.Check(layout.replayCountOffset == ReplayCount, "Explicit empty-catalog width changed the layout");
    }
    bool rejected = false;
    try { (void)Contract::InspectGame(empty.bytes, RetailSaveStateProfile(4097)); }
    catch (const RetailStateError& error) {
        rejected = error.Code() == RetailStateErrorCode::UnsupportedProfile && error.Offset() == 0;
    }
    suite.Check(rejected, "An unsupported explicit catalog profile was accepted");
    const auto old = Record(1, 3,
        {{std::int16_t{-1},std::int16_t{2}},{std::int16_t{3},std::int16_t{-4}}}, 2, "old");
    const auto a = Archive(Game({old,old}, 1));
    const auto b = Archive(Game({old,old,LiteralReload()}, 2));
    limits = {}; limits.maxArrayRecords = 3; limits.maxTotalRecords = 8; limits.maxStringBytes = 16;
    Accept(suite, a, b, false, "Session 2 starts", limits);
    limits.maxTotalRecords = 7; Reject(suite, a, b, false, "Session 2 starts", limits);
    limits.maxTotalRecords = 8; limits.maxArrayRecords = 2;
    Reject(suite, a, b, false, "Session 2 starts", limits);
    limits.maxArrayRecords = 3; limits.maxStringBytes = 15;
    Reject(suite, a, b, false, "Session 2 starts", limits);
    const Bytes database = {0,255,128,17};
    const auto withDatabase = Game({}, 1, {}, database);
    limits = {}; limits.maxEmbeddedDatabaseBytes = 4;
    Inspect(suite, withDatabase, 0, 1, limits);
    limits.maxEmbeddedDatabaseBytes = 3;
    RejectInspect(suite, withDatabase.bytes, limits, true, RetailStateErrorCode::EmbeddedDatabaseLimit, 4902);
}
void AdvisorSet(Suite& suite) {
    const std::vector<std::string> names = {"alpha", "beta"};
    const auto a = Game({}, 1, {}, {}, names);
    const auto b = Game({LiteralReload()}, 2, {}, {}, {"beta", "alpha"});
    suite.Check(a.advisorBytes == 21u && a.countOffset == ReplayCount + 17u &&
        a.gameStateOffset == GameState + 17u, "Independent two-advisor fixed offsets differ");
    Inspect(suite, a, 0, 1); Inspect(suite, b, 1, 2);
    Accept(suite, Archive(a), Archive(b));
    ++suite.literalCases;
    for (const auto& targetNames : std::vector<std::vector<std::string>>{
        {"alpha"}, {"alpha","alpha"}, {"alpha","zeta"}, {"alpha","beta","other"}})
        Reject(suite, Archive(a), Archive(Game({LiteralReload()}, 2, {}, {}, targetNames)));
    const auto duplicate = Game({}, 1, {}, {}, {"alpha","alpha"});
    Reject(suite, Archive(duplicate), Archive(Game({LiteralReload()}, 2, {}, {}, {"alpha","alpha"})));
    const unsigned char islandBytes[] = {2,0,0,0, 0,0,0,0, 1,0,0,0, 0,255,17};
    const std::string island(reinterpret_cast<const char*>(islandBytes), sizeof(islandBytes));
    const auto islandSource = Game({}, 1, {}, {}, {island,"visible"});
    const auto islandTarget = Game({LiteralReload()}, 2, {}, {}, {"visible",island});
    Inspect(suite, islandSource, 0, 1); Inspect(suite, islandTarget, 1, 2);
    Accept(suite, Archive(islandSource), Archive(islandTarget));
    auto changedIsland = island; changedIsland[4] = 1;
    Reject(suite, Archive(islandSource),
        Archive(Game({LiteralReload()}, 2, {}, {}, {"visible",changedIsland})));
    ++suite.literalCases;
}
void SelfTest(Suite& suite) {
    KnownAnswers(suite); LiteralAndCounts(suite); SourceOrderAndFraming(suite);
    EnvelopeAndPreservation(suite); ReplayAndText(suite); NormalizationsAndRandom(suite);
    LimitsAndProfiles(suite); AdvisorSet(suite);
}
std::size_t Decimal(const char* text, std::size_t maximum, bool positive) {
    if (!text || !*text) throw std::invalid_argument("Empty decimal argument");
    std::size_t value = 0;
    for (const char* at = text; *at; ++at) {
        if (*at < '0' || *at > '9') throw std::invalid_argument("Argument must contain decimal digits only");
        const auto digit = static_cast<std::size_t>(*at - '0');
        if (digit > maximum || value > (maximum - digit) / 10u)
            throw std::invalid_argument("Decimal argument exceeds its bound");
        value = value * 10u + digit;
    }
    if (positive && value == 0) throw std::invalid_argument("Input byte count must be positive");
    return value;
}
Bytes ReadInput(std::size_t size) {
#ifdef _WIN32
    if (_setmode(_fileno(stdin), _O_BINARY) == -1) throw std::runtime_error("Cannot select binary stdin");
#endif
    Bytes bytes(size);
    std::cin.read(reinterpret_cast<char*>(bytes.data()), static_cast<std::streamsize>(size));
    if (std::cin.gcount() != static_cast<std::streamsize>(size)) throw std::runtime_error("Truncated stdin input");
    if (std::cin.get() != std::char_traits<char>::eof()) throw std::runtime_error("Unexpected bytes after stdin input");
    if (!std::cin.eof()) throw std::runtime_error("Input did not end normally");
    return bytes;
}
std::uint32_t Get32(const Bytes& bytes, std::size_t at) {
    if (at > bytes.size() || bytes.size() - at < 4u) throw std::invalid_argument("Native descriptor is truncated");
    return static_cast<std::uint32_t>(bytes[at]) | (static_cast<std::uint32_t>(bytes[at + 1u]) << 8) |
        (static_cast<std::uint32_t>(bytes[at + 2u]) << 16) | (static_cast<std::uint32_t>(bytes[at + 3u]) << 24);
}
struct Observation {
    bool present = false, native = false;
    std::size_t inputBytes = 0, sectionCount = 0, gameOffset = 0, gameBytes = 0;
    unsigned flags = 0;
    int turn = 0, elapsed = 0, activePlayer = 0;
    std::string wireHash, gameHash;
    NativeRestoreGameLayout game;
};
Observation InputInspection(Suite& suite, const Bytes& bytes, std::uint32_t awards, bool native) {
    const auto original = Digest(bytes.data(), bytes.size());
    Bytes game;
    Observation result; result.inputBytes = bytes.size(); result.native = native;
    result.wireHash = Hex(original);
    if (native) {
        // The callback computes SHA-256 over the codec-supplied prefix. It does
        // not return the trailer or bypass the production checksum comparison.
        const auto archive = Envelope::Decode(bytes, Digest);
        suite.Check(archive.sections.size() == 133u, "Decoded native archive does not have 133 sections");
        result.sectionCount = archive.sections.size(); result.flags = archive.flags;
        result.turn = archive.turn; result.elapsed = archive.elapsed; result.activePlayer = archive.activePlayer;
        std::size_t cursor = 48;
        for (std::size_t i = 0; i < archive.sections.size(); ++i) {
            const auto kind = Get32(bytes, cursor), index = Get32(bytes, cursor + 4u);
            const auto count = static_cast<std::size_t>(Get32(bytes, cursor + 8u));
            cursor += 12u;
            suite.Check(cursor <= bytes.size() - 32u && count <= bytes.size() - 32u - cursor,
                "Decoded section exceeds the original checked payload");
            const auto& section = archive.sections[i];
            suite.Check(section.kind == kind && section.index == index && section.bytes.size() == count &&
                std::equal(section.bytes.begin(), section.bytes.end(), bytes.begin() + static_cast<std::ptrdiff_t>(cursor)),
                "Decoded owned section bytes differ from the source envelope");
            if (kind == 3u) { result.gameOffset = cursor; game = section.bytes; }
            cursor += count;
        }
        suite.Check(cursor == bytes.size() - 32u && !game.empty(), "Native descriptor inventory does not reach its checksum");
    } else game = bytes;
    result.gameBytes = game.size(); result.gameHash = Hex(Digest(game.data(), game.size()));
    result.game = Contract::InspectGame(game, RetailSaveStateProfile(awards));
    const auto preflight = Contract::PreflightGame(game, RetailSaveStateProfile(awards));
    suite.Check(SameLayout(result.game, preflight), "Actual input preflight and structural layout differ");
    suite.Check(Digest(bytes.data(), bytes.size()) == original, "Actual stdin input was mutated");
    result.present = true;
    return result;
}
void Quote(const std::string& text) {
    std::cout << '"';
    constexpr char digits[] = "0123456789abcdef";
    for (const auto ch : text) {
        const auto byte = static_cast<unsigned char>(ch);
        if (byte == '"' || byte == '\\') std::cout << '\\' << ch;
        else if (byte < 32u) std::cout << "\\u00" << digits[byte >> 4] << digits[byte & 15u];
        else std::cout << ch;
    }
    std::cout << '"';
}
void PrintObservation(const Observation& value) {
    if (!value.present) { std::cout << "null"; return; }
    std::cout << "{\"input_bytes\":" << value.inputBytes << ",\"wire_sha256\":";
    Quote(value.wireHash);
    if (value.native) {
        std::cout << ",\"section_count\":" << value.sectionCount << ",\"flags\":" << value.flags
            << ",\"turn\":" << value.turn << ",\"elapsed\":" << value.elapsed
            << ",\"active_player\":" << value.activePlayer;
    }
    std::cout << ",\"game_offset\":" << value.gameOffset << ",\"game_bytes\":" << value.gameBytes
        << ",\"game_sha256\":";
    Quote(value.gameHash);
    std::cout << ",\"replay_messages\":" << value.game.replayMessages << ",\"sessions\":" << value.game.sessions
        << ",\"replay_count_offset\":" << value.game.replayCountOffset
        << ",\"replay_records_offset\":" << value.game.replayRecords.offset
        << ",\"replay_records_bytes\":" << value.game.replayRecords.bytes
        << ",\"session_offset\":" << value.game.sessionOffset
        << ",\"structural_game_inspection_verified\":true,\"sdk_restore_verified\":false}";
}
void Json(const Suite& suite, bool passed, const std::string& mode, const char* phase,
    bool stdinComplete, std::uint32_t awards, const Observation& observation,
    const std::string& error, const char* domain, int code, std::size_t offset, bool hasOffset) {
    std::cout << "{\"schema\":\"zerosis.native_restore.contract_test.v1\",\"status\":";
    Quote(passed ? "PASS_NATIVE_RESTORE_CONTRACT_COMPONENT" : "FAIL_NATIVE_RESTORE_CONTRACT_COMPONENT");
    std::cout << ",\"mode\":"; Quote(mode);
    std::cout << ",\"phase\":"; Quote(phase);
    std::cout << ",\"checks\":" << suite.checks << ",\"truncations\":" << suite.truncations
        << ",\"directed_corruptions\":" << suite.corruptions << ",\"atomic_failure_cases\":" << suite.atomicFailures
        << ",\"literal_cases\":" << suite.literalCases << ",\"valid_cases\":" << suite.validCases
        << ",\"sha256_vectors\":" << suite.shaVectors << ",\"stdin_read_complete\":" << (stdinComplete ? "true" : "false")
        << ",\"profiles\":{\"awards\":" << awards << "},\"input_bytes_unchanged\":" << (passed ? "true" : "false")
        << ",\"input_files_unchanged\":true,\"all_failure_outputs_unchanged\":" << (passed ? "true" : "false")
        << ",\"test_only_sha256\":true,\"production_cng_executed\":false,\"sdk_executed\":false"
        << ",\"gamecore_loaded\":false,\"window_created\":false,\"game_accessed\":false,\"user_saves_accessed\":false"
        << ",\"complete_player_validated\":false,\"complete_save_validated\":false,\"ruleset_compatibility_verified\":false"
        << ",\"restore_approved\":false,\"native_restore_approved\":false,\"full_engine_goal_complete\":false"
        << ",\"native_input\":";
    if (mode == "stdin-native") PrintObservation(observation); else std::cout << "null";
    std::cout << ",\"game_input\":";
    if (mode == "stdin-game") PrintObservation(observation); else std::cout << "null";
    std::cout << ",\"error\":";
    if (error.empty()) std::cout << "null";
    else {
        std::cout << "{\"domain\":"; Quote(domain); std::cout << ",\"code\":";
        if (code >= 0) std::cout << code; else std::cout << "null";
        std::cout << ",\"offset\":";
        if (hasOffset) std::cout << offset; else std::cout << "null";
        std::cout << ",\"message\":"; Quote(error.substr(0, 256)); std::cout << '}';
    }
    std::cout << "}\n";
}
} // namespace

int main(int argc, char** argv) {
    static_assert(sizeof(std::uint32_t) == 4 && sizeof(std::int16_t) == 2 && sizeof(std::size_t) == 8,
        "This headless contract test requires x64 and fixed wire integer widths");
    Suite suite;
    std::string mode = "invalid";
    const char* phase = "arguments";
    bool stdinComplete = false;
    std::uint32_t awards = 5;
    Observation observation;
    try {
        if (argc == 2 && std::strcmp(argv[1], "--self-test") == 0) {
            mode = "self-test"; phase = "self-test"; SelfTest(suite);
        } else if (argc == 4 && (std::strcmp(argv[1], "--stdin-native") == 0 ||
                               std::strcmp(argv[1], "--stdin-game") == 0)) {
            const bool native = std::strcmp(argv[1], "--stdin-native") == 0;
            mode = native ? "stdin-native" : "stdin-game";
            const auto size = Decimal(argv[2], MaximumInputBytes, true);
            awards = static_cast<std::uint32_t>(Decimal(argv[3], 4096, false));
            phase = "read_stdin";
            const auto bytes = ReadInput(size); stdinComplete = true;
            phase = native ? "decode_native_and_inspect_game" : "inspect_game";
            observation = InputInspection(suite, bytes, awards, native);
        } else throw std::invalid_argument("Use --self-test or --stdin-native|--stdin-game BYTES AWARDS");
        Json(suite, true, mode, "complete", stdinComplete, awards, observation, "", "", -1, 0, false);
        return 0;
    } catch (const RetailStateError& error) {
        Json(suite, false, mode, phase, stdinComplete, awards, observation, error.what(), "retail_state",
            static_cast<int>(error.Code()), error.Offset(), true);
    } catch (const std::exception& error) {
        Json(suite, false, mode, phase, stdinComplete, awards, observation, error.what(), "contract", -1, 0, false);
    }
    return 1;
}
