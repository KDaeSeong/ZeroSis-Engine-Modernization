#include "RetailSaveChunkFrames.h"
#include <array>
#include <cstddef>
#include <cstdint>
#include <exception>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

// Pure framing tests. Payloads are opaque synthetic bytes, never compressed
// saves. No SDK serializer, CLI, stdin, file, process or network is used.
namespace {
using namespace ZeroSisHost;
using Code = RetailSaveChunkFramesErrorCode;
using Bytes = std::vector<unsigned char>;
constexpr auto Profile = RetailSaveChunkFramingProfile::U32LengthPayloadsToEnd;
struct Suite {
    std::size_t checks = 0, rejected = 0, truncations = 0, completeBoundaryTruncations = 0;
    std::size_t smallLiteralCases = 0, largeLiteralCases = 0, observedArithmeticCases = 0;
    void Check(bool value, const char* message) {
        ++checks;
        if (!value) throw std::runtime_error(message);
    }
};
struct ExpectedFrame { std::size_t header, payload, bytes; };
constexpr std::array<unsigned char, 5> One = {1,0,0,0,0xff};
constexpr std::array<unsigned char, 11> Two = {1,0,0,0,0, 2,0,0,0,0xff,0};
constexpr std::array<unsigned char, 18> Three = {1,0,0,0,0xff, 2,0,0,0,0,0xff, 3,0,0,0,0xff,0,0x7e};
constexpr std::array<unsigned char, 21> Prefixed = {0xa7,0,0xff, 1,0,0,0,0xff, 2,0,0,0,0,0xff, 3,0,0,0,0xff,0,0x7e};
constexpr std::array<ExpectedFrame, 1> ExpectedOne = {{{0,4,1}}};
constexpr std::array<ExpectedFrame, 2> ExpectedTwo = {{{0,4,1},{5,9,2}}};
constexpr std::array<ExpectedFrame, 3> ExpectedThree = {{{0,4,1},{5,9,2},{11,15,3}}};
constexpr std::array<ExpectedFrame, 3> ExpectedPrefixed = {{{3,7,1},{8,12,2},{14,18,3}}};
bool Inside(const RetailSaveWireSpan& span, std::size_t size) {
    return span.offset <= size && span.bytes <= size - span.offset;
}
template<std::size_t Count>
void Shape(Suite& suite, const RetailSaveChunkFramesInspection& result, std::size_t size, std::size_t start,
        const std::array<ExpectedFrame, Count>& expected, std::size_t expectedPayload) {
    suite.Check(result.frames.size() == Count && result.totalPayloadBytes == expectedPayload &&
        result.containerSpan.offset == start && result.containerSpan.bytes == size - start && Inside(result.containerSpan, size),
        "Chunk count, container bounds or independent payload total differs");
    std::size_t next = start, total = 0;
    for (std::size_t index = 0; index < Count; ++index) {
        const auto& frame = result.frames[index]; const auto& literal = expected[index];
        suite.Check(Inside(frame.header, size) && Inside(frame.payload, size) && frame.header.offset == next &&
            frame.header.offset == literal.header && frame.header.bytes == 4u && frame.payload.offset == literal.payload &&
            frame.payload.offset == frame.header.offset + frame.header.bytes && frame.payload.bytes == literal.bytes,
            "Literal frame spans overlap, leave gaps, exceed input or differ from four-byte headers");
        next = frame.payload.offset + frame.payload.bytes; total += frame.payload.bytes;
    }
    suite.Check(next == size && total == expectedPayload, "Frame payload sum or exact input-end boundary differs");
}
template<class Function>
void Reject(Suite& suite, Function&& function, Code code, std::size_t offset) {
    try { function(); }
    catch (const RetailSaveChunkFramesError& error) {
        suite.Check(error.Code() == code, "Wrong typed chunk-framing error code");
        suite.Check(error.Offset() == offset, "Wrong rejected chunk header offset"); ++suite.rejected; return;
    }
    catch (...) { suite.Check(false, "Chunk framing raised the wrong exception type"); }
    suite.Check(false, "Malformed or over-budget chunk input was accepted");
}
template<std::size_t Size>
void AllTruncations(Suite& suite, const std::array<unsigned char, Size>& literal) {
    static_assert(Size == 5u || Size == 11u || Size == 18u, "Use only the independently specified small literals");
    const auto before = literal;
    for (std::size_t cut = 0; cut < literal.size(); ++cut) {
        if (cut == 5u) {
            Shape(suite, RetailSaveChunkFrames::Inspect(literal.data(), cut, 0, Profile), cut, 0, ExpectedOne, 1);
            ++suite.completeBoundaryTruncations;
        } else if (cut == 11u) {
            Shape(suite, RetailSaveChunkFrames::Inspect(literal.data(), cut, 0, Profile), cut, 0, ExpectedTwo, 3);
            ++suite.completeBoundaryTruncations;
        } else {
            const std::size_t header = cut < 5u ? 0u : (cut < 11u ? 5u : 11u);
            const auto code = cut == 0u ? Code::EmptyContainer :
                (cut - header < 4u ? Code::TruncatedLength : Code::TruncatedPayload);
            Reject(suite, [&] { RetailSaveChunkFrames::Inspect(literal.data(), cut, 0, Profile); }, code, header);
        }
        ++suite.truncations;
    }
    // A complete-frame prefix has no missing word or sentinel. Framing alone
    // cannot distinguish an intentionally shorter sequence from lost frames.
    suite.Check(literal == before, "Truncation inspection changed literal input bytes");
}
void SmallLiterals(Suite& suite) {
    const auto beforeOne = One;
    const auto beforeTwo = Two;
    const auto beforeThree = Three;
    const auto beforePrefixed = Prefixed;
    Shape(suite, RetailSaveChunkFrames::Inspect(One.data(), One.size(), 0, Profile), 5, 0, ExpectedOne, 1);
    Shape(suite, RetailSaveChunkFrames::Inspect(Two.data(), Two.size(), 0, Profile), 11, 0, ExpectedTwo, 3);
    Shape(suite, RetailSaveChunkFrames::Inspect(Three.data(), Three.size(), 0, Profile), 18, 0, ExpectedThree, 6);
    Shape(suite, RetailSaveChunkFrames::Inspect(Prefixed.data(), Prefixed.size(), 3, Profile), 21, 3, ExpectedPrefixed, 6);
    suite.smallLiteralCases += 4;
    AllTruncations(suite, One); AllTruncations(suite, Two); AllTruncations(suite, Three);
    suite.Check(One == beforeOne && Two == beforeTwo && Three == beforeThree && Prefixed == beforePrefixed,
        "Framing modified opaque 0/255 payload or prefix bytes");
}
void InvalidInputs(Suite& suite) {
    Reject(suite, [&] { RetailSaveChunkFrames::Inspect(nullptr, 1, 0, Profile); }, Code::NullInput, 0);
    Reject(suite, [&] { RetailSaveChunkFrames::Inspect(nullptr, 0, 0, Profile); }, Code::EmptyContainer, 0);
    Reject(suite, [&] { RetailSaveChunkFrames::Inspect(One.data(), 0, 0, Profile); }, Code::EmptyContainer, 0);
    Reject(suite, [&] { RetailSaveChunkFrames::Inspect(Prefixed.data(), 3, 3, Profile); }, Code::EmptyContainer, 3);
    Reject(suite, [&] { RetailSaveChunkFrames::Inspect(One.data(), One.size(), 6, Profile); }, Code::InvalidOffset, 6);
    const auto maximum = (std::numeric_limits<std::size_t>::max)();
    Reject(suite, [&] { RetailSaveChunkFrames::Inspect(One.data(), One.size(), maximum, Profile); }, Code::InvalidOffset, maximum);
    const auto unknown = static_cast<RetailSaveChunkFramingProfile>(99);
    Reject(suite, [&] { RetailSaveChunkFrames::Inspect(Prefixed.data(), Prefixed.size(), 3, unknown); }, Code::UnsupportedProfile, 3);
    const std::array<unsigned char, 4> zero = {0,0,0,0}, oversized = {1,0,1,0}, length257 = {1,1,0,0};
    const std::array<unsigned char, 9> laterZero = {1,0,0,0,0xff, 0,0,0,0};
    const std::array<unsigned char, 5> reverseEndian = {0,0,0,1,0xff};
    Reject(suite, [&] { RetailSaveChunkFrames::Inspect(zero.data(), zero.size(), 0, Profile); }, Code::ZeroLength, 0);
    Reject(suite, [&] { RetailSaveChunkFrames::Inspect(laterZero.data(), laterZero.size(), 0, Profile); }, Code::ZeroLength, 5);
    Reject(suite, [&] { RetailSaveChunkFrames::Inspect(oversized.data(), oversized.size(), 0, Profile); }, Code::FrameSizeLimit, 0);
    Reject(suite, [&] { RetailSaveChunkFrames::Inspect(reverseEndian.data(), reverseEndian.size(), 0, Profile); }, Code::FrameSizeLimit, 0);
    Reject(suite, [&] { RetailSaveChunkFrames::Inspect(length257.data(), length257.size(), 0, Profile); }, Code::TruncatedPayload, 0);
    const std::array<unsigned char, 4> maximumWord = {0xff,0xff,0xff,0xff};
    auto wide = RetailSaveChunkFramesLimits{}; wide.maximumFrameBytes = wide.maximumTotalPayloadBytes = maximum;
    Reject(suite, [&] { RetailSaveChunkFrames::Inspect(maximumWord.data(), maximumWord.size(), 0, Profile, wide); },
        Code::TruncatedPayload, 0);
    suite.Check(zero == std::array<unsigned char, 4>{0,0,0,0} && laterZero == std::array<unsigned char, 9>{1,0,0,0,0xff,0,0,0,0} &&
        maximumWord == std::array<unsigned char, 4>{0xff,0xff,0xff,0xff}, "Rejected literal framing changed input");
}
void Limits(Suite& suite) {
    auto limits = RetailSaveChunkFramesLimits{}; limits.maximumInputBytes = 21;
    Shape(suite, RetailSaveChunkFrames::Inspect(Prefixed.data(), Prefixed.size(), 3, Profile, limits), 21, 3, ExpectedPrefixed, 6);
    limits.maximumInputBytes = 20;
    Reject(suite, [&] { RetailSaveChunkFrames::Inspect(Prefixed.data(), Prefixed.size(), 3, Profile, limits); }, Code::InputLimit, 0);
    limits.maximumInputBytes = 0;
    Reject(suite, [&] { RetailSaveChunkFrames::Inspect(One.data(), One.size(), 0, Profile, limits); }, Code::InputLimit, 0);
    limits = {}; limits.maximumFrames = 3;
    Shape(suite, RetailSaveChunkFrames::Inspect(Three.data(), Three.size(), 0, Profile, limits), 18, 0, ExpectedThree, 6);
    limits.maximumFrames = 2;
    Reject(suite, [&] { RetailSaveChunkFrames::Inspect(Three.data(), Three.size(), 0, Profile, limits); }, Code::FrameLimit, 11);
    limits.maximumFrames = 0;
    Reject(suite, [&] { RetailSaveChunkFrames::Inspect(One.data(), One.size(), 0, Profile, limits); }, Code::FrameLimit, 0);
    limits = {}; limits.maximumFrameBytes = 3;
    Shape(suite, RetailSaveChunkFrames::Inspect(Three.data(), Three.size(), 0, Profile, limits), 18, 0, ExpectedThree, 6);
    limits.maximumFrameBytes = 2;
    Reject(suite, [&] { RetailSaveChunkFrames::Inspect(Three.data(), Three.size(), 0, Profile, limits); }, Code::FrameSizeLimit, 11);
    limits.maximumFrameBytes = 0;
    Reject(suite, [&] { RetailSaveChunkFrames::Inspect(One.data(), One.size(), 0, Profile, limits); }, Code::FrameSizeLimit, 0);
    limits = {}; limits.maximumTotalPayloadBytes = 6;
    Shape(suite, RetailSaveChunkFrames::Inspect(Three.data(), Three.size(), 0, Profile, limits), 18, 0, ExpectedThree, 6);
    limits.maximumTotalPayloadBytes = 5;
    Reject(suite, [&] { RetailSaveChunkFrames::Inspect(Three.data(), Three.size(), 0, Profile, limits); }, Code::TotalPayloadLimit, 11);
    limits.maximumTotalPayloadBytes = 0;
    Reject(suite, [&] { RetailSaveChunkFrames::Inspect(One.data(), One.size(), 0, Profile, limits); }, Code::TotalPayloadLimit, 0);
}
void LargeLengths(Suite& suite) {
    // Literal little-endian length 65536; payload contents are opaque zeros.
    const std::array<unsigned char, 65540> maximum = {0,0,1,0}; const auto beforeMaximum = maximum;
    const std::array<ExpectedFrame, 1> maximumExpected = {{{0,4,65536}}};
    Shape(suite, RetailSaveChunkFrames::Inspect(maximum.data(), maximum.size(), 0, Profile), 65540, 0, maximumExpected, 65536);
    // Unequal payload lengths 1,65536. A full-sized last frame still ends
    // normally at supplied EOF; no invented short final chunk is required.
    const std::array<unsigned char, 65545> unequal = {1,0,0,0,0xff, 0,0,1,0}; const auto beforeUnequal = unequal;
    const std::array<ExpectedFrame, 2> unequalExpected = {{{0,4,1},{5,9,65536}}};
    Shape(suite, RetailSaveChunkFrames::Inspect(unequal.data(), unequal.size(), 0, Profile), 65545, 0, unequalExpected, 65537);
    suite.Check(maximum == beforeMaximum && unequal == beforeUnequal, "Large literal payload input changed"); suite.largeLiteralCases += 2;
}
void ObservedArithmetic(Suite& suite) {
    // Only length arithmetic comes from input_chunk_comparison.json SHA256
    // 04972c76cb6818e21e178363be4bc7ff7da74768f0c62b6d69f5ff3f8504b390.
    // These synthetic 0xa5 payloads contain no public compressed/save bytes.
    const std::array<std::size_t, 11> headers = {0,65540,131080,196620,262160,327700,393240,458780,524320,589860,655400};
    const std::array<unsigned char, 4> fullLengthWord = {0,0,1,0};
    struct Spec { std::size_t wire, payload, last; std::array<unsigned char, 4> finalWord; };
    const std::array<Spec, 2> specs = {{
        {707760,707716,52356,{0x84,0xcc,0,0}},
        {679801,679757,24397,{0x4d,0x5f,0,0}}
    }};
    for (const auto& spec : specs) {
        Bytes synthetic(spec.wire, 0xa5);
        // Copy literal four-byte blocks at independent fixed offsets. There
        // is no integer-to-wire serializer or production writer in this test.
        for (std::size_t frame = 0; frame < 10u; ++frame)
            for (std::size_t byte = 0; byte < 4u; ++byte) synthetic[headers[frame] + byte] = fullLengthWord[byte];
        for (std::size_t byte = 0; byte < 4u; ++byte) synthetic[655400u + byte] = spec.finalWord[byte];
        const auto before = synthetic;
        const std::array<ExpectedFrame, 11> expected = {{{0,4,65536},{65540,65544,65536},{131080,131084,65536},
            {196620,196624,65536},{262160,262164,65536},{327700,327704,65536},{393240,393244,65536},
            {458780,458784,65536},{524320,524324,65536},{589860,589864,65536},{655400,655404,spec.last}}};
        Shape(suite, RetailSaveChunkFrames::Inspect(synthetic.data(), synthetic.size(), 0, Profile), spec.wire, 0, expected, spec.payload);
        suite.Check(synthetic == before, "Observed-length synthetic framing changed its opaque input"); ++suite.observedArithmeticCases;
    }
}
void Run(Suite& suite) {
    SmallLiterals(suite); InvalidInputs(suite); Limits(suite); LargeLengths(suite); ObservedArithmetic(suite);
    suite.Check(suite.smallLiteralCases == 4u && suite.largeLiteralCases == 2u && suite.observedArithmeticCases == 2u &&
        suite.truncations == 34u && suite.completeBoundaryTruncations == 3u, "Focused chunk framing case accounting differs");
}
void Text(const std::string& value) {
    std::cout << '"';
    for (const char raw : value) {
        const auto ch = static_cast<unsigned char>(raw);
        if (ch == '"' || ch == '\\') std::cout << '\\';
        std::cout << (ch < 32u ? '?' : static_cast<char>(ch));
    }
    std::cout << '"';
}
void Print(const Suite& suite, bool passed, const std::string& error, int code, std::size_t offset) {
    std::cout << "{\"status\":\"" << (passed ? "PASS_RETAIL_CHUNK_FRAMES_COMPONENT" : "FAIL_RETAIL_CHUNK_FRAMES_COMPONENT")
        << "\",\"checks\":" << suite.checks << ",\"rejected_cases\":" << suite.rejected
        << ",\"truncations\":" << suite.truncations
        << ",\"complete_frame_boundary_truncations_accepted\":" << suite.completeBoundaryTruncations
        << ",\"independent_small_literal_cases\":" << suite.smallLiteralCases
        << ",\"independent_large_length_literal_cases\":" << suite.largeLiteralCases
        << ",\"public_length_arithmetic_synthetic_cases\":" << suite.observedArithmeticCases
        << ",\"input_bytes_unchanged\":" << (passed ? "true" : "false")
        << ",\"sdk_executed\":false,\"gamecore_loaded\":false,\"window_created\":false"
        << ",\"game_accessed\":false,\"user_saves_accessed\":false,\"native_inflate_performed\":false"
        << ",\"producer_contract_verified\":false,\"compressed_stream_completeness_proved\":false"
        << ",\"complete_player_validated\":false,\"complete_save_validated\":false,\"complete_save_verified\":false"
        << ",\"ruleset_compatibility_verified\":false,\"restore_approved\":false,\"full_engine_goal_complete\":false"
        << ",\"error_code\":";
    if (code >= 0) std::cout << code; else std::cout << "null";
    std::cout << ",\"error_offset\":";
    if (code >= 0) std::cout << offset; else std::cout << "null";
    std::cout << ",\"error\":"; Text(error); std::cout << "}\n";
}
} // namespace

int main() {
    static_assert(sizeof(void*) == 8, "Chunk framing component tests require x64");
    static_assert(sizeof(std::uint32_t) == 4, "Chunk length words must have four bytes");
    Suite suite; bool passed = false; std::string error; int code = -1; std::size_t offset = 0;
    try { Run(suite); passed = true; }
    catch (const RetailSaveChunkFramesError& failure) {
        error = failure.what(); code = static_cast<int>(failure.Code()); offset = failure.Offset();
    }
    catch (const std::exception& failure) { error = failure.what(); }
    catch (...) { error = "Unexpected non-standard framing test exception"; }
    Print(suite, passed, error, code, offset); return passed ? 0 : 1;
}
