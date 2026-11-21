#include "NativeSaveEnvelope.h"
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
#include <memory>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>
#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif

// Pure portable V1 envelope tests. The SHA-256 below is TEST-ONLY and is
// injected through the real production codec; Windows CNG is not used here.
// Known-answer values: NIST NSRL Test Data (abc, 56-byte message, million a)
// https://www.nist.gov/itl/ai/ai-standards-and-guidelines-group/nsrl-test-data
// Empty message: IETF RFC 8760, section 2.6, item 7.
// https://www.rfc-editor.org/rfc/rfc8760.txt
namespace {
using Envelope = ZeroSisHost::NativeSaveEnvelope;
using Section = ZeroSisHost::NativeSaveSection;
using Bytes = std::vector<unsigned char>;
using Hash = std::array<unsigned char, 32>;
struct Suite {
    std::size_t checks = 0, shaVectors = 0, literalCases = 0, roundTrips = 0;
    std::size_t truncations = 0, corruptions = 0, atomicFailures = 0, digestCases = 0;
    void Check(bool value, const char* message) {
        ++checks; if (!value) throw std::runtime_error(message);
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
void KnownAnswers(Suite& suite) {
    struct Vector { const char* text; const char* expected; };
    const std::array<Vector, 3> vectors = {{
        {"","e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"},
        {"abc","ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"},
        {"abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq","248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1"}
    }};
    for (const auto& value : vectors) {
        const auto size = std::strlen(value.text);
        suite.Check(Hex(Digest(reinterpret_cast<const unsigned char*>(value.text), size)) == value.expected,
            "Test-only SHA-256 differs from its official known-answer vector");
        TestSha256 incremental;
        for (std::size_t i = 0; i < size; ++i)
            incremental.Update(reinterpret_cast<const unsigned char*>(value.text) + i, 1);
        suite.Check(Hex(incremental.Finish()) == value.expected, "Test SHA incremental byte updates differ");
        ++suite.shaVectors;
    }
    const Bytes million(1000000u, static_cast<unsigned char>('a'));
    const auto before = million;
    suite.Check(Hex(Digest(million.data(), million.size())) ==
        "cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0" && million == before,
        "Test SHA million-a vector or immutable input differs");
    TestSha256 incremental;
    for (std::size_t at = 0; at < million.size();) {
        const auto count = (std::min)(std::size_t(137), million.size() - at);
        incremental.Update(million.data() + at, count); at += count;
    }
    suite.Check(Hex(incremental.Finish()) == "cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0",
        "Test SHA uneven multi-block updates differ from million-a expected hash");
    ++suite.shaVectors;
}

struct Identity { unsigned kind, index; };
// Independent fixed section identities. This table is not emitted by Encode.
constexpr std::array<Identity, 133> Identities = {{
    {1,0},{2,0},{3,0},{4,0},{5,0},
    {6,0},{6,1},{6,2},{6,3},{6,4},{6,5},{6,6},{6,7},
    {6,8},{6,9},{6,10},{6,11},{6,12},{6,13},{6,14},{6,15},
    {6,16},{6,17},{6,18},{6,19},{6,20},{6,21},{6,22},{6,23},
    {6,24},{6,25},{6,26},{6,27},{6,28},{6,29},{6,30},{6,31},
    {6,32},{6,33},{6,34},{6,35},{6,36},{6,37},{6,38},{6,39},
    {6,40},{6,41},{6,42},{6,43},{6,44},{6,45},{6,46},{6,47},
    {6,48},{6,49},{6,50},{6,51},{6,52},{6,53},{6,54},{6,55},
    {6,56},{6,57},{6,58},{6,59},{6,60},{6,61},{6,62},{6,63},
    {7,0},{7,1},{7,2},{7,3},{7,4},{7,5},{7,6},{7,7},
    {7,8},{7,9},{7,10},{7,11},{7,12},{7,13},{7,14},{7,15},
    {7,16},{7,17},{7,18},{7,19},{7,20},{7,21},{7,22},{7,23},
    {7,24},{7,25},{7,26},{7,27},{7,28},{7,29},{7,30},{7,31},
    {7,32},{7,33},{7,34},{7,35},{7,36},{7,37},{7,38},{7,39},
    {7,40},{7,41},{7,42},{7,43},{7,44},{7,45},{7,46},{7,47},
    {7,48},{7,49},{7,50},{7,51},{7,52},{7,53},{7,54},{7,55},
    {7,56},{7,57},{7,58},{7,59},{7,60},{7,61},{7,62},{7,63}
}};
constexpr std::array<unsigned char, 48> LiteralHeader = {{
    'Z','E','R','O','S','I','S','_','S','A','V','E','_','V','1',0,
    1,0,0,0, 3,0,0,0, 123,0,0,0, 234,0,0,0, 63,0,0,0,
    64,0,0,0, 64,0,0,0, 133,0,0,0
}};
Bytes Payload(std::size_t index) {
    return {0,static_cast<unsigned char>(index),255,128,static_cast<unsigned char>(index ^ 165u),1,0,
        static_cast<unsigned char>((17u * index) & 255u)};
}
Envelope Model() {
    Envelope value; value.flags = 3; value.turn = 123; value.elapsed = 234; value.activePlayer = 63;
    for (std::size_t i = 0; i < Identities.size(); ++i) {
        Section section; section.kind = Identities[i].kind; section.index = Identities[i].index; section.bytes = Payload(i);
        value.sections.push_back(std::move(section));
    }
    return value;
}
Bytes GoldenPayload() {
    // Direct fixed offsets in a known 2708-byte transcript, not the codec's
    // append/get routines. Each record occupies 12 literal header + 8 payload.
    Bytes bytes(2708, 0);
    std::copy(LiteralHeader.begin(), LiteralHeader.end(), bytes.begin());
    for (std::size_t i = 0; i < Identities.size(); ++i) {
        const auto at = 48u + 20u * i;
        bytes[at] = static_cast<unsigned char>(Identities[i].kind);
        bytes[at + 4u] = static_cast<unsigned char>(Identities[i].index);
        bytes[at + 8u] = 8;
        // Deliberately repeat the independent byte recipe at fixed positions;
        // a model payload helper cannot make a shared mismatch pass this test.
        bytes[at + 12u] = 0; bytes[at + 13u] = static_cast<unsigned char>(i);
        bytes[at + 14u] = 255; bytes[at + 15u] = 128;
        bytes[at + 16u] = static_cast<unsigned char>(i ^ 165u);
        bytes[at + 17u] = 1; bytes[at + 18u] = 0;
        bytes[at + 19u] = static_cast<unsigned char>((17u * i) & 255u);
    }
    return bytes;
}
Bytes Seal(const Bytes& payload) {
    auto bytes = payload; const auto hash = Digest(payload.data(), payload.size());
    bytes.insert(bytes.end(), hash.begin(), hash.end()); return bytes;
}
void Put32(Bytes& bytes, std::size_t at, std::uint32_t value) {
    if (at > bytes.size() || bytes.size() - at < 4u) throw std::runtime_error("Test corruption outside its byte vector");
    for (unsigned shift = 0; shift < 32u; shift += 8u) bytes[at + shift / 8u] = static_cast<unsigned char>(value >> shift);
}
bool Same(const Envelope& left, const Envelope& right) {
    if (left.flags != right.flags || left.turn != right.turn || left.elapsed != right.elapsed ||
        left.activePlayer != right.activePlayer || left.sections.size() != right.sections.size()) return false;
    for (std::size_t i = 0; i < left.sections.size(); ++i) {
        const auto& a = left.sections[i]; const auto& b = right.sections[i];
        if (a.kind != b.kind || a.index != b.index || a.bytes != b.bytes) return false;
    }
    return true;
}
Envelope Sentinel() {
    Envelope value; value.flags = 1; value.turn = 701; value.elapsed = 702; value.activePlayer = 37;
    Section section; section.kind = 99; section.index = 17; section.bytes = {165,68,0,255};
    value.sections.push_back(section); return value;
}
struct DigestTrace {
    std::size_t calls = 0, size = 0;
    const unsigned char* pointer = nullptr;
    Bytes observed;
};
struct RecordingDigest {
    DigestTrace* trace;
    Hash operator()(const unsigned char* data, std::size_t size) const {
        ++trace->calls; trace->pointer = data; trace->size = size;
        trace->observed.assign(data, data + size);
        return Digest(data, size);
    }
};
void RejectedDecode(Suite& suite, const Bytes& input, const char* message,
    const std::string& exactMessage = std::string()) {
    const auto before = input;
    const auto sentinel = Sentinel(); auto output = sentinel;
    DigestTrace trace; bool caught = false;
    try { output = Envelope::Decode(input, RecordingDigest{&trace}); }
    catch (const std::invalid_argument& error) {
        caught = true;
        suite.Check(exactMessage.empty() || exactMessage == error.what(), "Wrong native envelope rejection reason");
    }
    suite.Check(caught, message);
    suite.Check(Same(output, sentinel) && input == before, "Decode failure changed caller input or last output sentinel");
    const bool headerValid = input.size() >= 80u &&
        std::equal(LiteralHeader.begin(), LiteralHeader.begin() + 16, input.begin());
    suite.Check(trace.calls == (headerValid ? 1u : 0u), "Decode digest callback occurred at the wrong validation stage");
    if (headerValid) {
        suite.Check(trace.pointer == input.data() && trace.size == input.size() - 32u &&
            trace.observed == Bytes(input.begin(), input.end() - 32),
            "Failed Decode digested something other than its original payload excluding the 32-byte trailer");
    }
    ++suite.atomicFailures; ++suite.digestCases;
}
void RejectedEncode(Suite& suite, const Envelope& input) {
    const auto before = input;
    const Bytes sentinel = {165,68,0,255}; auto output = sentinel;
    DigestTrace trace; bool caught = false;
    try { output = input.Encode(RecordingDigest{&trace}); }
    catch (const std::invalid_argument&) { caught = true; }
    suite.Check(caught && trace.calls == 0u, "Invalid model was encoded or invoked its digest before Validate");
    suite.Check(output == sentinel && Same(input, before), "Encode failure changed its model or previous byte output");
    ++suite.atomicFailures; ++suite.digestCases;
}

Bytes RoundTrip(Suite& suite, const Envelope& model, const Bytes* expected = nullptr) {
    const auto before = model;
    DigestTrace encodeTrace;
    const auto encoded = model.Encode(RecordingDigest{&encodeTrace});
    suite.Check(encoded.size() >= 80u && Same(model,before), "Encode changed its caller model or returned an incomplete header");
    suite.Check(encodeTrace.calls == 1u && encodeTrace.size == encoded.size() - 32u &&
        encodeTrace.observed == Bytes(encoded.begin(), encoded.end() - 32),
        "Encode callback did not receive the exact finished payload excluding its future checksum trailer");
    const auto checksum = Digest(encoded.data(), encoded.size() - 32u);
    suite.Check(std::equal(checksum.begin(), checksum.end(), encoded.end() - 32), "Encoded SHA trailer differs from the payload");
    if (expected) suite.Check(encoded == *expected, "Production encoder differs from the independent fixed V1 wire transcript");
    const auto encodedBefore = encoded;
    DigestTrace decodeTrace;
    const auto decoded = Envelope::Decode(encoded, RecordingDigest{&decodeTrace});
    suite.Check(Same(decoded, model) && encoded == encodedBefore, "Roundtrip metadata, every section byte or source input differs");
    suite.Check(decodeTrace.calls == 1u && decodeTrace.pointer == encoded.data() &&
        decodeTrace.size == encoded.size() - 32u && decodeTrace.observed == encodeTrace.observed,
        "Decode callback did not receive exactly its caller's original payload excluding the 32-byte trailer");
    suite.Check(decoded.sections.size() == 133u && decoded.sections[0].kind == 1u &&
        decoded.sections[4].kind == 5u && decoded.sections[5].kind == 6u && decoded.sections[5].index == 0u &&
        decoded.sections[68].kind == 6u && decoded.sections[68].index == 63u &&
        decoded.sections[69].kind == 7u && decoded.sections[69].index == 0u &&
        decoded.sections[132].kind == 7u && decoded.sections[132].index == 63u,
        "Fixed sections or first/last Team/Player slots differ");
    auto mutableInput = encoded;
    const auto owned = Envelope::Decode(mutableInput, Digest);
    std::fill(mutableInput.begin(), mutableInput.end(), static_cast<unsigned char>(204));
    suite.Check(Same(owned, model) && encoded == encodedBefore, "Decoded envelope retained a borrowed reference to caller wire bytes");
    suite.digestCases += 2; ++suite.roundTrips;
    return encoded;
}
struct Sample {
    bool verified = false;
    std::string payloadSha, wireSha, checksum;
};
Bytes Positives(Suite& suite, Sample& sample) {
    suite.Check(Envelope::TeamSlots == 64u && Envelope::PlayerSlots == 64u && Envelope::SectionCount() == 133u &&
        Envelope::Bundle == 1u && Envelope::Pregame == 2u && Envelope::Game == 3u && Envelope::Map == 4u &&
        Envelope::Supporting == 5u && Envelope::Team == 6u && Envelope::Player == 7u,
        "Portable production constants differ from the literal V1 contract");
    const auto payload = GoldenPayload(); const auto expected = Seal(payload);
    suite.Check(payload.size() == 2708u && expected.size() == 2740u &&
        std::equal(LiteralHeader.begin(),LiteralHeader.end(),payload.begin()), "Independent golden header or fixed size differs");
    const auto model = Model(); model.Validate();
    for (std::size_t i = 0; i < model.sections.size(); ++i) {
        suite.Check(model.sections[i].bytes.size() == 8u && model.sections[i].bytes[1] == static_cast<unsigned char>(i) &&
            model.sections[i].bytes[0] == 0u && model.sections[i].bytes[2] == 255u && model.sections[i].bytes[3] == 128u,
            "A positive synthetic section lost its distinct binary payload identity");
    }
    const auto encoded = RoundTrip(suite, model, &expected); ++suite.literalCases;
    sample.payloadSha = Hex(Digest(payload.data(),payload.size()));
    sample.wireSha = Hex(Digest(encoded.data(),encoded.size()));
    Hash trailer{}; std::copy(encoded.end() - 32,encoded.end(),trailer.begin()); sample.checksum = Hex(trailer);
    sample.verified = true;
    for (unsigned flag = 0; flag <= 3u; ++flag) {
        auto endpoint = model; endpoint.flags = flag;
        endpoint.turn = (flag & 1u) ? INT_MAX : 0;
        endpoint.elapsed = (flag & 2u) ? INT_MAX : 0;
        endpoint.activePlayer = (flag & 1u) ? 63 : 0;
        // Vary lengths including one-byte sections; first byte uniquely tags
        // every section. These are opaque bytes, not SDK serialization mocks.
        for (std::size_t i = 0; i < endpoint.sections.size(); ++i) {
            auto& bytes = endpoint.sections[i].bytes;
            bytes.assign(1u + i % 9u, static_cast<unsigned char>((i & 1u) ? 255 : 0));
            bytes[0] = static_cast<unsigned char>(i);
        }
        const auto wire = RoundTrip(suite, endpoint);
        const auto decoded = Envelope::Decode(wire, Digest);
        suite.Check(decoded.flags == flag && decoded.turn == endpoint.turn && decoded.elapsed == endpoint.elapsed &&
            decoded.activePlayer == endpoint.activePlayer, "A legal flag or counter/slot endpoint was narrowed or changed");
    }
    return encoded;
}
void InvalidModels(Suite& suite) {
    const auto model = Model();
    for (const auto flag : {4u,0xffffffffu}) { auto bad = model; bad.flags = flag; RejectedEncode(suite,bad); ++suite.corruptions; }
    for (const auto negative : {-1,INT_MIN}) {
        auto bad = model; bad.turn = negative; RejectedEncode(suite,bad); ++suite.corruptions;
        bad = model; bad.elapsed = negative; RejectedEncode(suite,bad); ++suite.corruptions;
    }
    for (const auto active : {-1,64,INT_MAX}) { auto bad = model; bad.activePlayer = active; RejectedEncode(suite,bad); ++suite.corruptions; }
    { auto bad = model; bad.sections.pop_back(); RejectedEncode(suite,bad); ++suite.corruptions; }
    { auto bad = model; bad.sections.push_back(bad.sections.back()); RejectedEncode(suite,bad); ++suite.corruptions; }
    for (const std::size_t i : {0u,1u,4u,5u,68u,69u,132u}) {
        auto bad = model; bad.sections[i].kind = 99; RejectedEncode(suite,bad); ++suite.corruptions;
        bad = model; ++bad.sections[i].index; RejectedEncode(suite,bad); ++suite.corruptions;
        bad = model; bad.sections[i].bytes.clear(); RejectedEncode(suite,bad); ++suite.corruptions;
    }
    { auto bad = model; std::swap(bad.sections[5],bad.sections[6]); RejectedEncode(suite,bad); ++suite.corruptions; }
    { auto bad = model; bad.sections[69] = bad.sections[70]; RejectedEncode(suite,bad); ++suite.corruptions; }
}
void InvalidWire(Suite& suite, const Bytes& encoded) {
    const auto payload = GoldenPayload();
    for (std::size_t i = 0; i < 16u; ++i) {
        auto bad = encoded; bad[i] ^= 128;
        RejectedDecode(suite,bad,"Corrupted literal magic was accepted","Invalid native save header"); ++suite.corruptions;
    }
    for (std::size_t i = 0; i < 32u; ++i) {
        auto bad = encoded; bad[bad.size() - 32u + i] ^= 1;
        RejectedDecode(suite,bad,"A checksum trailer bit was ignored","Native save checksum differs"); ++suite.corruptions;
    }
    { auto bad = encoded; bad[60] ^= 64;
        RejectedDecode(suite,bad,"A payload byte change bypassed SHA verification","Native save checksum differs"); ++suite.corruptions; }
    struct WordCase { std::size_t at; std::uint32_t value; const char* message; };
    const std::array<WordCase, 19> words = {{
        {16,0,"Unsupported native save version"},{16,2,"Unsupported native save version"},
        {20,4,"Invalid native save metadata or section count"},{20,0xffffffffu,"Invalid native save metadata or section count"},
        {24,0x80000000u,"Native save counters exceed their SDK fields"},{24,0xffffffffu,"Native save counters exceed their SDK fields"},
        {28,0x80000000u,"Native save counters exceed their SDK fields"},{28,0xffffffffu,"Native save counters exceed their SDK fields"},
        {32,64,"Native save counters exceed their SDK fields"},{32,0xffffffffu,"Native save counters exceed their SDK fields"},
        {36,63,"Native save slot configuration differs"},{36,65,"Native save slot configuration differs"},
        {36,0xffffffffu,"Native save slot configuration differs"},{40,0,"Native save slot configuration differs"},
        {40,63,"Native save slot configuration differs"},{40,65,"Native save slot configuration differs"},
        {44,132,"Native save slot configuration differs"},{44,134,"Native save slot configuration differs"},
        {44,0xffffffffu,"Native save slot configuration differs"}
    }};
    for (const auto& word : words) {
        auto bad = payload; Put32(bad,word.at,word.value);
        RejectedDecode(suite,Seal(bad),"A checksum-valid malformed metadata field was accepted",word.message); ++suite.corruptions;
    }
    for (const std::size_t i : {0u,1u,4u,5u,68u,69u,132u}) {
        const auto at = 48u + i * 20u;
        auto bad = payload; Put32(bad,at,99);
        RejectedDecode(suite,Seal(bad),"A malformed fixed/Team/Player kind was accepted","Invalid native save section layout"); ++suite.corruptions;
        bad = payload; Put32(bad,at + 4u,Identities[i].index + 1u);
        RejectedDecode(suite,Seal(bad),"A malformed fixed/Team/Player index was accepted","Invalid native save section layout"); ++suite.corruptions;
        for (const auto size : {0u,0x7fffffffu,0x80000000u,0xffffffffu}) {
            bad = payload; Put32(bad,at + 8u,size);
            RejectedDecode(suite,Seal(bad),"An empty, missing or excessive section payload was accepted",
                "Native save section extends beyond its payload"); ++suite.corruptions;
        }
    }
    { auto bad = payload; Put32(bad,48u + 20u,1);
        RejectedDecode(suite,Seal(bad),"A duplicated fixed section was accepted","Invalid native save section layout"); ++suite.corruptions; }
    { auto bad = payload; bad.push_back(165);
        RejectedDecode(suite,Seal(bad),"Trailing checksum-valid payload data was accepted","Native save has trailing section data"); ++suite.corruptions; }
    { auto bad = payload; bad.insert(bad.end(),payload.begin() + 48,payload.begin() + 68);
        RejectedDecode(suite,Seal(bad),"An undeclared extra section was accepted","Native save has trailing section data"); ++suite.corruptions; }
    { auto bad = encoded; bad.push_back(165);
        RejectedDecode(suite,bad,"Trailing bytes outside the original trailer were accepted","Native save checksum differs"); ++suite.corruptions; }
}
void Truncations(Suite& suite, const Bytes& encoded) {
    for (std::size_t cut = 0; cut < encoded.size(); ++cut) {
        const Bytes shortened(encoded.begin(), encoded.begin() + static_cast<std::ptrdiff_t>(cut));
        RejectedDecode(suite,shortened,"A truncated complete-envelope prefix was accepted"); ++suite.truncations;
    }
    const auto payload = GoldenPayload();
    for (std::size_t cut = 0; cut < 48u; ++cut) {
        const Bytes prefix(payload.begin(),payload.begin() + static_cast<std::ptrdiff_t>(cut));
        RejectedDecode(suite,Seal(prefix),"A checksum-valid incomplete fixed header was accepted","Invalid native save header"); ++suite.truncations;
    }
    for (std::size_t i = 0; i < Identities.size(); ++i) {
        for (const std::size_t part : {0u,4u,8u,12u,19u}) {
            const auto cut = 48u + 20u * i + part;
            const Bytes prefix(payload.begin(),payload.begin() + static_cast<std::ptrdiff_t>(cut));
            RejectedDecode(suite,Seal(prefix),"A checksum-valid partial record was accepted",
                part < 12u ? "Truncated native save field" : "Native save section extends beyond its payload");
            ++suite.truncations;
        }
    }
}

struct InjectedDigestFailure final : std::runtime_error {
    explicit InjectedDigestFailure(std::shared_ptr<const unsigned> value)
        : std::runtime_error("Injected test digest failure"), token(std::move(value)) {}
    std::shared_ptr<const unsigned> token;
};
struct ThrowingDigest {
    const volatile bool* requested;
    std::size_t* calls;
    std::shared_ptr<const unsigned> token;
    Hash operator()(const unsigned char* data, std::size_t size) const {
        ++*calls;
        // Keep a genuine return path: this tests runtime exception propagation,
        // without an always-throw template causing MSVC /W4 unreachable warnings.
        if (*requested) throw InjectedDigestFailure(token);
        return Digest(data,size);
    }
};
void DigestFailures(Suite& suite, const Bytes& encoded) {
    const auto model = Model(); const auto modelBefore = model; const auto encodedBefore = encoded;
    const auto token = std::make_shared<const unsigned>(0x54455354u);
    volatile bool requested = true;
    const Bytes sentinelBytes = {165,68,0,255}; auto bytesOutput = sentinelBytes;
    const auto sentinel = Sentinel(); auto modelOutput = sentinel;
    std::size_t calls = 0; bool caught = false;
    try { bytesOutput = model.Encode(ThrowingDigest{&requested,&calls,token}); }
    catch (const InjectedDigestFailure& error) {
        caught = true;
        suite.Check(error.token == token && *error.token == 0x54455354u &&
            std::strcmp(error.what(),"Injected test digest failure") == 0,
            "Encode replaced the injected digest exception type, shared identity or message");
    }
    suite.Check(caught && calls == 1u && bytesOutput == sentinelBytes && Same(model,modelBefore),
        "Digest failure published partial Encode output or changed its input");
    ++suite.atomicFailures; ++suite.digestCases;
    caught = false; calls = 0;
    try { modelOutput = Envelope::Decode(encoded,ThrowingDigest{&requested,&calls,token}); }
    catch (const InjectedDigestFailure& error) {
        caught = true;
        suite.Check(error.token == token && *error.token == 0x54455354u &&
            std::strcmp(error.what(),"Injected test digest failure") == 0,
            "Decode replaced the injected digest exception type, shared identity or message");
    }
    suite.Check(caught && calls == 1u && Same(modelOutput,sentinel) && encoded == encodedBefore,
        "Digest failure published partial Decode output or changed the source bytes");
    ++suite.atomicFailures; ++suite.digestCases;
    requested = false; calls = 0;
    const auto returned = Envelope::Decode(encoded,ThrowingDigest{&requested,&calls,token});
    suite.Check(calls == 1u && Same(returned,model), "Runtime digest callback's nonthrowing path changed a valid result");
    ++suite.digestCases;
}
struct NativeSectionSpan {
    unsigned kind = 0, index = 0;
    std::size_t offset = 0, bytes = 0;
};
struct NativeObservation {
    bool readComplete = false, verified = false;
    std::size_t inputBytes = 0, payloadBytes = 0, bundleBytes = 0;
    unsigned flags = 0;
    int turn = 0, elapsed = 0, activePlayer = -1;
    std::string payloadSha, wireSha, checksum, bundleSha;
    std::vector<NativeSectionSpan> sections;
};
constexpr std::size_t MaximumNativeBytes = 32u * 1024u * 1024u;
std::size_t NativeSize(const char* text) {
    if (!text || !*text) throw std::invalid_argument("Missing native stdin byte count");
    std::size_t value = 0;
    for (const char* p = text; *p; ++p) {
        if (*p < '0' || *p > '9') throw std::invalid_argument("Native stdin count requires decimal digits only");
        const auto digit = static_cast<std::size_t>(*p - '0');
        if (value > (MaximumNativeBytes - digit) / 10u)
            throw std::invalid_argument("Native stdin exceeds its 32 MiB bound");
        value = value * 10u + digit;
    }
    if (!value) throw std::invalid_argument("Native stdin byte count must be positive");
    return value;
}
std::uint32_t Word(const Bytes& bytes, std::size_t at) {
    if (at > bytes.size() || bytes.size() - at < 4u) throw std::runtime_error("Native field is outside the inspected input");
    return static_cast<std::uint32_t>(bytes[at]) | (static_cast<std::uint32_t>(bytes[at + 1u]) << 8) |
        (static_cast<std::uint32_t>(bytes[at + 2u]) << 16) | (static_cast<std::uint32_t>(bytes[at + 3u]) << 24);
}
struct BoundedDigestTrace {
    std::size_t calls = 0, size = 0;
    const unsigned char* pointer = nullptr;
    Hash hash{};
};
struct SummarizingDigest {
    BoundedDigestTrace* trace;
    Hash operator()(const unsigned char* data, std::size_t size) const {
        ++trace->calls; trace->size = size; trace->pointer = data; trace->hash = Digest(data,size);
        return trace->hash;
    }
};
void NativeStdin(Suite& suite, std::size_t declaredBytes, NativeObservation& observation, const char*& phase) {
    phase = "native_stdin_read";
#ifdef _WIN32
    if (_setmode(_fileno(stdin),_O_BINARY) == -1) throw std::runtime_error("Cannot select binary native stdin");
#endif
    Bytes incoming(declaredBytes);
    std::cin.read(reinterpret_cast<char*>(incoming.data()),static_cast<std::streamsize>(incoming.size()));
    if (std::cin.gcount() != static_cast<std::streamsize>(incoming.size()) ||
        std::cin.peek() != std::char_traits<char>::eof() || std::cin.bad())
        throw std::runtime_error("Native stdin does not match its exact declared size");
    const Bytes input = std::move(incoming); const auto before = input;
    observation.readComplete = true; observation.inputBytes = input.size();
    phase = "native_shared_decode";
    BoundedDigestTrace decodedHash;
    const auto decoded = Envelope::Decode(input,SummarizingDigest{&decodedHash});
    suite.Check(decodedHash.calls == 1u && decodedHash.pointer == input.data() && decodedHash.size == input.size() - 32u,
        "Actual native Decode did not digest its exact original payload excluding the trailer");
    suite.Check(input.size() >= 80u && std::equal(LiteralHeader.begin(),LiteralHeader.begin() + 16,input.begin()) &&
        Word(input,16) == 1u && Word(input,20) == decoded.flags && Word(input,24) == static_cast<unsigned>(decoded.turn) &&
        Word(input,28) == static_cast<unsigned>(decoded.elapsed) && Word(input,32) == static_cast<unsigned>(decoded.activePlayer) &&
        Word(input,36) == 64u && Word(input,40) == 64u && Word(input,44) == 133u && decoded.sections.size() == 133u,
        "Actual native fixed V1 header or metadata differs from its shared decoded fields");
    suite.Check(decoded.flags <= 3u && decoded.turn >= 0 && decoded.elapsed >= 0 &&
        decoded.activePlayer >= 0 && decoded.activePlayer < 64, "Actual native metadata exceeds V1 field bounds");
    phase = "native_section_bytes";
    std::size_t at = 48; const auto end = input.size() - 32u;
    std::vector<NativeSectionSpan> spans;
    for (std::size_t i = 0; i < Identities.size(); ++i) {
        const auto& section = decoded.sections[i];
        suite.Check(at <= end && end - at >= 12u && section.kind == Identities[i].kind &&
            section.index == Identities[i].index && Word(input,at) == Identities[i].kind &&
            Word(input,at + 4u) == Identities[i].index && Word(input,at + 8u) == section.bytes.size() &&
            !section.bytes.empty() && section.bytes.size() <= end - at - 12u,
            "Actual native descriptor order, slot, nonempty size or payload bounds differ");
        at += 12u;
        suite.Check(std::equal(section.bytes.begin(),section.bytes.end(),input.begin() + static_cast<std::ptrdiff_t>(at)),
            "Actual decoded section did not preserve every original opaque payload byte");
        spans.push_back({section.kind,section.index,at,section.bytes.size()}); at += section.bytes.size();
    }
    suite.Check(at == end && std::equal(decodedHash.hash.begin(),decodedHash.hash.end(),input.end() - 32),
        "Actual native sections do not end at the original checked SHA trailer");
    phase = "native_exact_reencode";
    BoundedDigestTrace encodedHash;
    const auto encoded = decoded.Encode(SummarizingDigest{&encodedHash});
    suite.Check(encoded == input && encodedHash.calls == 1u && encodedHash.size == end && encodedHash.hash == decodedHash.hash,
        "Actual native Decode/Encode changed a wire byte, metadata field, section or checksum");
    phase = "native_owned_storage";
    {
        // Mutate only a separate test-local copy after Decode; the original
        // stdin input and the observed archive are preserved throughout.
        auto temporary = input; const auto detached = Envelope::Decode(temporary,Digest);
        std::fill(temporary.begin(),temporary.end(),static_cast<unsigned char>(204));
        suite.Check(Same(detached,decoded), "Actual decoded archive borrowed storage from caller wire bytes");
    }
    suite.Check(input == before, "Actual native inspection changed its original stdin bytes");
    observation.payloadBytes = end; observation.flags = decoded.flags; observation.turn = decoded.turn;
    observation.elapsed = decoded.elapsed; observation.activePlayer = decoded.activePlayer;
    observation.payloadSha = Hex(decodedHash.hash); observation.checksum = Hex(decodedHash.hash);
    observation.wireSha = Hex(Digest(input.data(),input.size()));
    observation.bundleBytes = decoded.sections[0].bytes.size();
    observation.bundleSha = Hex(Digest(decoded.sections[0].bytes.data(),decoded.sections[0].bytes.size()));
    observation.sections = std::move(spans); observation.verified = true;
    suite.digestCases += 3; ++suite.roundTrips;
}
const char* Boolean(bool value) { return value ? "true" : "false"; }
void Text(const std::string& value) {
    constexpr char Digits[] = "0123456789abcdef";
    std::cout << '"';
    for (const char raw : value) {
        const auto byte = static_cast<unsigned char>(raw);
        if (byte == '"' || byte == '\\') std::cout << '\\' << static_cast<char>(byte);
        else if (byte < 32u || byte >= 127u) std::cout << "\\u00" << Digits[byte >> 4] << Digits[byte & 15u];
        else std::cout << static_cast<char>(byte);
    }
    std::cout << '"';
}
void Print(const Suite& suite, const Sample& sample, const NativeObservation& native, const char* mode,
    bool passed, const char* phase, const std::string& error) {
    std::cout << "{\"schema\":\"zerosis.native_save.envelope_test.v1\",\"status\":\""
        << (passed ? "PASS_NATIVE_SAVE_ENVELOPE_COMPONENT" : "FAIL_NATIVE_SAVE_ENVELOPE_COMPONENT")
        << "\",\"mode\":\"" << mode << "\",\"phase\":\"" << phase << "\",\"checks\":" << suite.checks
        << ",\"sha256_vectors\":" << suite.shaVectors << ",\"literal_wire_cases\":" << suite.literalCases
        << ",\"roundtrip_cases\":" << suite.roundTrips << ",\"truncations\":" << suite.truncations
        << ",\"directed_corruptions\":" << suite.corruptions << ",\"atomic_failure_cases\":" << suite.atomicFailures
        << ",\"digest_callback_cases\":" << suite.digestCases
        << ",\"input_bytes_unchanged\":" << Boolean(passed) << ",\"input_files_unchanged\":true"
        << ",\"all_failure_outputs_unchanged\":" << Boolean(passed)
        << ",\"stdin_read_complete\":" << Boolean(native.readComplete)
        << ",\"digest_implementation\":\"test_only_portable_sha256\",\"test_only_sha256\":true"
        << ",\"production_cng_executed\":false,\"payload_semantics_verified\":false,\"sdk_executed\":false"
        << ",\"gamecore_loaded\":false,\"window_created\":false,\"game_accessed\":false,\"user_saves_accessed\":false"
        << ",\"complete_player_validated\":false,\"complete_save_validated\":false,\"complete_save_verified\":false"
        << ",\"ruleset_compatibility_verified\":false,\"restore_approved\":false,\"native_restore_approved\":false"
        << ",\"bundle_identity_verified\":false,\"producer_contract_verified\":false,\"full_engine_goal_complete\":false"
        << ",\"known_answer_sources\":[\"https://www.nist.gov/itl/ai/ai-standards-and-guidelines-group/nsrl-test-data\","
        << "\"https://www.rfc-editor.org/rfc/rfc8760.txt\"],\"sample\":";
    if (sample.verified) {
        std::cout << "{\"recipe\":\"fixed133_binary8_v1\",\"flags\":3,\"turn\":123,\"elapsed\":234,\"active_player\":63"
            << ",\"section_count\":133,\"payload_bytes\":2708,\"wire_bytes\":2740,\"payload_sha256\":";
        Text(sample.payloadSha); std::cout << ",\"wire_sha256\":"; Text(sample.wireSha);
        std::cout << ",\"checksum_hex\":"; Text(sample.checksum); std::cout << '}';
    } else std::cout << "null";
    std::cout << ",\"native_input\":";
    if (native.verified) {
        std::cout << "{\"input_bytes\":" << native.inputBytes << ",\"payload_bytes\":" << native.payloadBytes
            << ",\"wire_bytes\":" << native.inputBytes << ",\"section_count\":" << native.sections.size()
            << ",\"flags\":" << native.flags << ",\"turn\":" << native.turn << ",\"elapsed\":" << native.elapsed
            << ",\"active_player\":" << native.activePlayer << ",\"payload_sha256\":";
        Text(native.payloadSha); std::cout << ",\"wire_sha256\":"; Text(native.wireSha);
        std::cout << ",\"checksum_hex\":"; Text(native.checksum);
        std::cout << ",\"bundle_bytes\":" << native.bundleBytes << ",\"bundle_sha256\":"; Text(native.bundleSha);
        std::cout << ",\"roundtrip_exact\":true,\"all_sections_nonempty\":true,\"ordered_section_layout\":true"
            << ",\"source_bytes_unchanged\":true,\"decoded_storage_owned\":true,\"sections\":[";
        for (std::size_t i = 0; i < native.sections.size(); ++i) {
            const auto& row = native.sections[i]; if (i) std::cout << ',';
            std::cout << "{\"kind\":" << row.kind << ",\"index\":" << row.index << ",\"offset\":" << row.offset
                << ",\"bytes\":" << row.bytes << '}';
        }
        std::cout << "]}";
    } else std::cout << "null";
    std::cout << ",\"error\":"; Text(error); std::cout << "}\n";
}
} // namespace

int main(int argc, char** argv) {
    static_assert(sizeof(void*) == 8 && CHAR_BIT == 8 && sizeof(unsigned) == 4 && sizeof(int) == 4 &&
        sizeof(std::uint32_t) == 4, "Portable native-envelope tests require the reviewed x64 V1 integer widths");
    Suite suite; Sample sample; NativeObservation native;
    const char* mode = "unselected"; const char* phase = "arguments"; bool passed = false; std::string error;
    try {
        if (argc == 2 && std::strcmp(argv[1],"--self-test") == 0) {
            mode = "self-test";
            phase = "test_only_sha256_known_answers"; KnownAnswers(suite);
            phase = "independent_literal_and_roundtrip"; const auto encoded = Positives(suite,sample);
            phase = "invalid_models"; InvalidModels(suite);
            phase = "checksum_valid_and_invalid_corruptions"; InvalidWire(suite,encoded);
            phase = "raw_and_resealed_structural_truncations"; Truncations(suite,encoded);
            phase = "digest_exception_atomicity"; DigestFailures(suite,encoded);
        } else if (argc == 3 && std::strcmp(argv[1],"--stdin-native") == 0) {
            mode = "stdin-native"; NativeStdin(suite,NativeSize(argv[2]),native,phase);
        } else throw std::invalid_argument("Require --self-test or --stdin-native bytes; no file paths are accepted");
        phase = "complete"; passed = true;
    } catch (const std::exception& caught) { error = caught.what(); }
    catch (...) { error = "Unexpected non-standard native-envelope test exception"; }
    Print(suite,sample,native,mode,passed,phase,error);
    return passed ? 0 : 1;
}
