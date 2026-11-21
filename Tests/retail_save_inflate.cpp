// Own headless zlib inspection tests. CNG is used only for independent SHA-256.
// No game, SDK, window, save writer, process launch, or decompressed-body file.
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <bcrypt.h>
#include <fcntl.h>
#include <io.h>
#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <exception>
#include <fstream>
#include <initializer_list>
#include <ios>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include "../Source/Host/RetailSaveInflate.h"

namespace {
using Bytes = std::vector<unsigned char>;
using Digest = std::array<unsigned char, 32>;
using Decoder = ZeroSisHost::RetailSaveInflate;
using Inspection = ZeroSisHost::RetailInflateInspection;
using Limits = ZeroSisHost::RetailInflateLimits;
using Error = ZeroSisHost::RetailInflateError;
using Code = ZeroSisHost::RetailInflateErrorCode;
using Termination = ZeroSisHost::RetailInflateTermination;
constexpr std::size_t InputLimit = 1024u * 1024u;
constexpr std::size_t PublicOutputBytes = 9762327u;
const char* const PublicOutputSha =
    "1fdc3cf2c0d1fa5859f6be202cc7654ff97835ffc67abe91301d1fbceb9a93db";

struct Counters {
    std::size_t checks = 0, fixtures = 0, truncations = 0, mutations = 0;
    std::size_t accepted = 0, rejected = 0;
} counts;
struct PublicObservation {
    bool observed = false, strictRejected = false, finalBlockSeen = false;
    bool unchanged = false;
    std::size_t outputBytes = 0, consumed = 0, blocks = 0, lastBoundaryBit = 0;
    std::string sha, termination = "NOT_OBSERVED";
} publicResult;

void Check(bool condition, const std::string& message) {
    ++counts.checks;
    if (!condition) throw std::runtime_error(message);
}
template<class F> void Reject(Code expected, F operation, const char* label) {
    bool rejected = false;
    try { operation(); }
    catch (const Error& error) {
        Check(error.Code() == expected, std::string(label) + ": wrong typed error");
        rejected = true;
    }
    Check(rejected, std::string(label) + ": input was accepted");
}
Limits Bounded() {
    Limits limits;
    limits.maximumInputBytes = InputLimit;
    limits.maximumOutputBytes = 16u * 1024u * 1024u;
    limits.maximumDecoderMemoryBytes = 1024u * 1024u;
    limits.maximumCalls = 65536;
    return limits;
}

struct AlgorithmHandle {
    BCRYPT_ALG_HANDLE value = nullptr;
    AlgorithmHandle() = default;
    AlgorithmHandle(const AlgorithmHandle&) = delete;
    AlgorithmHandle& operator=(const AlgorithmHandle&) = delete;
    ~AlgorithmHandle() { if (value) BCryptCloseAlgorithmProvider(value, 0); }
};
struct HashHandle {
    BCRYPT_HASH_HANDLE value = nullptr;
    HashHandle() = default;
    HashHandle(const HashHandle&) = delete;
    HashHandle& operator=(const HashHandle&) = delete;
    ~HashHandle() { if (value) BCryptDestroyHash(value); }
};
Digest Sha256(const Bytes& data) {
    AlgorithmHandle algorithm;
    Check(BCryptOpenAlgorithmProvider(&algorithm.value, BCRYPT_SHA256_ALGORITHM, nullptr, 0) >= 0,
          "Cannot open independent CNG SHA-256 provider");
    DWORD objectBytes = 0, returned = 0, hashBytes = 0;
    Check(BCryptGetProperty(algorithm.value, BCRYPT_OBJECT_LENGTH,
              reinterpret_cast<PUCHAR>(&objectBytes), static_cast<ULONG>(sizeof(objectBytes)), &returned, 0) >= 0 &&
              returned == sizeof(objectBytes) && objectBytes > 0 && objectBytes <= InputLimit,
          "Invalid CNG hash-object length");
    Check(BCryptGetProperty(algorithm.value, BCRYPT_HASH_LENGTH,
              reinterpret_cast<PUCHAR>(&hashBytes), static_cast<ULONG>(sizeof(hashBytes)), &returned, 0) >= 0 &&
              returned == sizeof(hashBytes) && hashBytes == 32,
          "Independent CNG hash is not SHA-256");
    Bytes object(static_cast<std::size_t>(objectBytes));
    HashHandle hash; // Destroy the hash before its object buffer and algorithm.
    Check(BCryptCreateHash(algorithm.value, &hash.value, object.data(), objectBytes, nullptr, 0, 0) >= 0,
          "Cannot initialize independent CNG SHA-256 hash");
    constexpr std::size_t chunkLimit = 65536;
    static_assert(chunkLimit <= (std::numeric_limits<ULONG>::max)(), "CNG chunk does not fit ULONG");
    for (std::size_t offset = 0; offset < data.size();) {
        const auto count = (std::min)(chunkLimit, data.size() - offset);
        Check(count <= (std::numeric_limits<ULONG>::max)(), "CNG chunk length overflow");
        Check(BCryptHashData(hash.value, const_cast<PUCHAR>(data.data() + offset),
                            static_cast<ULONG>(count), 0) >= 0, "Independent CNG SHA-256 update failed");
        offset += count;
    }
    Digest result{};
    Check(BCryptFinishHash(hash.value, result.data(), static_cast<ULONG>(result.size()), 0) >= 0,
          "Independent CNG SHA-256 finalization failed");
    return result;
}
std::string Hex(const Digest& value) {
    static const char digits[] = "0123456789abcdef";
    std::string result;
    result.reserve(64);
    for (const auto byte : value) { result += digits[byte >> 4]; result += digits[byte & 15]; }
    return result;
}

Bytes ReadFixture(const char* path) {
    std::ifstream file(path, std::ios::binary | std::ios::ate);
    Check(static_cast<bool>(file), "Cannot open explicit immutable vector fixture");
    const auto end = file.tellg();
    Check(end > std::streampos(0) && end <= std::streampos(InputLimit),
          "Vector fixture must be nonempty and at most 1 MiB");
    Bytes data(static_cast<std::size_t>(end));
    file.seekg(0);
    file.read(reinterpret_cast<char*>(data.data()), static_cast<std::streamsize>(data.size()));
    Check(static_cast<bool>(file) && file.gcount() == static_cast<std::streamsize>(data.size()),
          "Incomplete vector fixture read");
    Check(file.peek() == std::char_traits<char>::eof(), "Vector fixture changed during read");
    return data;
}
Bytes ReadPublicInput() {
    Check(_setmode(_fileno(stdin), _O_BINARY) != -1, "Cannot select binary standard input");
    Bytes result;
    std::array<char, 65536> buffer{};
    while (true) {
        const auto capacity = (std::min)(buffer.size(), InputLimit - result.size() + 1);
        std::cin.read(buffer.data(), static_cast<std::streamsize>(capacity));
        const auto received = std::cin.gcount();
        Check(received >= 0 && static_cast<std::size_t>(received) <= InputLimit - result.size(),
              "Public compressed standard input exceeds 1 MiB");
        for (std::streamsize i = 0; i < received; ++i)
            result.push_back(static_cast<unsigned char>(buffer[static_cast<std::size_t>(i)]));
        Check(!std::cin.bad(), "Failed reading public compressed standard input");
        if (std::cin.eof()) break;
        Check(!std::cin.fail() && received > 0, "Public compressed input made no read progress");
    }
    return result;
}

struct Fixture {
    std::string name;
    std::uint32_t kind = 0, outputBytes = 0;
    Digest outputSha{};
    Bytes compressed;
};
class FixtureReader {
public:
    explicit FixtureReader(const Bytes& bytes) : bytes_(bytes) {}
    std::uint32_t Word() {
        Need(4); const auto p = position_; position_ += 4;
        return static_cast<std::uint32_t>(bytes_[p]) |
            (static_cast<std::uint32_t>(bytes_[p + 1]) << 8) |
            (static_cast<std::uint32_t>(bytes_[p + 2]) << 16) |
            (static_cast<std::uint32_t>(bytes_[p + 3]) << 24);
    }
    Bytes Block(std::size_t count) {
        Need(count);
        Bytes result(bytes_.begin() + static_cast<std::ptrdiff_t>(position_),
                     bytes_.begin() + static_cast<std::ptrdiff_t>(position_ + count));
        position_ += count; return result;
    }
    std::string Name() {
        const auto count = Word();
        Check(count > 0 && count <= 128, "Invalid bounded vector-fixture name");
        const auto bytes = Block(count);
        return std::string(bytes.begin(), bytes.end());
    }
    Digest Hash() {
        Need(32); Digest result{};
        for (auto& byte : result) byte = bytes_[position_++];
        return result;
    }
    bool AtEnd() const { return position_ == bytes_.size(); }
private:
    void Need(std::size_t count) const {
        Check(position_ <= bytes_.size() && count <= bytes_.size() - position_, "Truncated vector fixture");
    }
    const Bytes& bytes_;
    std::size_t position_ = 0;
};
std::vector<Fixture> ParseFixture(const Bytes& bytes) {
    FixtureReader reader(bytes);
    const auto magic = reader.Block(8);
    Check(std::string(magic.begin(), magic.end()) == "ZSINFL01", "Wrong independent fixture format");
    const auto count = reader.Word();
    Check(count > 0 && count <= 64, "Unbounded fixture-vector count");
    std::vector<Fixture> fixtures;
    for (std::uint32_t i = 0; i < count; ++i) {
        Fixture item;
        item.name = reader.Name(); item.kind = reader.Word(); item.outputBytes = reader.Word();
        Check(item.kind <= 4 && item.outputBytes <= Bounded().maximumOutputBytes, "Invalid fixture case descriptor");
        item.outputSha = reader.Hash();
        const auto compressedBytes = reader.Word();
        Check(compressedBytes <= InputLimit, "Oversized fixture input");
        item.compressed = reader.Block(compressedBytes);
        Check(std::none_of(fixtures.begin(), fixtures.end(), [&](const Fixture& old) { return old.name == item.name; }),
              "Duplicate independent fixture name");
        fixtures.push_back(std::move(item));
    }
    Check(reader.AtEnd(), "Trailing bytes in independent vector fixture");
    return fixtures;
}

const char* Name(Termination termination) {
    switch (termination) {
    case Termination::CompleteZlibStream: return "CompleteZlibStream";
    case Termination::NonFinalEmptyStoredBlockBoundary: return "NonFinalEmptyStoredBlockBoundary";
    case Termination::Incomplete: return "Incomplete";
    }
    throw std::runtime_error("Unknown production termination enum");
}
void Invariants(const Inspection& result, std::size_t inputBytes, const Limits& limits) {
    Check(result.bytes.size() <= limits.maximumOutputBytes, "Output escaped its byte budget");
    Check(result.inputConsumed <= inputBytes && result.lastBoundaryBit <= inputBytes * 8,
          "Decoder consumed outside its input");
    Check(result.calls > 0 && result.calls <= limits.maximumCalls, "Decoder escaped its call budget");
    Check(result.decoderPeakBytes > 0 && result.decoderPeakBytes <= limits.maximumDecoderMemoryBytes,
          "Decoder escaped its internal allocation budget");
    if (result.termination == Termination::CompleteZlibStream) {
        Check(result.adlerTrailerVerified && result.finalDeflateBlockSeen && result.inputConsumed == inputBytes,
              "Complete classification lacks final block, trailer or exact input end");
    } else {
        Check(!result.adlerTrailerVerified, "Unfinished inspection claimed a verified trailer");
        if (result.termination == Termination::NonFinalEmptyStoredBlockBoundary)
            Check(!result.finalDeflateBlockSeen && result.inputConsumed == inputBytes &&
                  result.lastBoundaryBit == inputBytes * 8, "Nonfinal boundary classification is inconsistent");
        else Check(result.termination == Termination::Incomplete, "Invalid unfinished termination enum");
    }
}
void StrictIncomplete(const Bytes& input, const Limits& limits) {
    Reject(Code::IncompleteStream, [&] { Decoder::DecodeComplete(input.data(), input.size(), limits); },
           "Strict decoding of an unfinished stream");
}
void FixtureCases(const std::vector<Fixture>& fixtures) {
    std::array<std::size_t, 5> kinds{};
    for (const auto& item : fixtures) {
        ++kinds[item.kind];
        if (item.kind >= 3) {
            const auto code = item.kind == 3 ? Code::DictionaryRequired : Code::InvalidData;
            Reject(code, [&] { Decoder::Inspect(item.compressed, Bounded()); }, item.name.c_str());
            Reject(code, [&] { Decoder::DecodeComplete(item.compressed.data(), item.compressed.size(), Bounded()); },
                   item.name.c_str());
        } else {
            const auto result = Decoder::Inspect(item.compressed, Bounded());
            Invariants(result, item.compressed.size(), Bounded());
            const auto expected = item.kind == 0 ? Termination::CompleteZlibStream :
                item.kind == 1 ? Termination::NonFinalEmptyStoredBlockBoundary : Termination::Incomplete;
            Check(result.termination == expected, item.name + ": independent termination oracle");
            Check(result.bytes.size() == item.outputBytes && Sha256(result.bytes) == item.outputSha,
                  item.name + ": independent plaintext length/SHA-256 oracle");
            if (item.kind == 0) {
                const auto strict = Decoder::DecodeComplete(item.compressed.data(), item.compressed.size(), Bounded());
                Check(strict == result.bytes, item.name + ": strict and inspecting output differ");
                for (std::size_t cut = 0; cut < item.compressed.size(); ++cut) {
                    bool rejected = false;
                    try { Decoder::DecodeComplete(item.compressed.data(), cut, Bounded()); }
                    catch (const Error& error) {
                        Check(error.Code() == Code::IncompleteStream || error.Code() == Code::InvalidData,
                              "A valid stream truncation failed for an unrelated reason");
                        rejected = true;
                    }
                    Check(rejected, "Strict decoding accepted a truncated complete vector");
                    ++counts.truncations;
                }
            } else StrictIncomplete(item.compressed, Bounded());
        }
        ++counts.fixtures;
    }
    for (const auto count : kinds) Check(count > 0, "An independent fixture category is missing");
}

Bytes GoldenComplete() {
    // RFC1951 stored blocks: "A", empty nonfinal, "B", empty nonfinal,
    // empty FINAL. RFC1950 Adler-32("AB") is 0x00c60084, in network order.
    return Bytes{0x78,0x01, 0x00,0x01,0x00,0xfe,0xff,'A',
                 0x00,0x00,0x00,0xff,0xff,
                 0x00,0x01,0x00,0xfe,0xff,'B',
                 0x00,0x00,0x00,0xff,0xff,
                 0x01,0x00,0x00,0xff,0xff, 0x00,0xc6,0x00,0x84};
}
Bytes MagicInsideNonemptyStored() {
    // A legal nonfinal stored block whose DATA merely ends in 00 00 ff ff.
    return Bytes{0x78,0x01,0x00,0x04,0x00,0xfb,0xff,0x00,0x00,0xff,0xff};
}
void GoldenBoundaries(const Bytes& complete) {
    Check(complete.size() == 33, "Independent stored-block golden length");
    const auto whole = Decoder::Inspect(complete, Bounded());
    Check(whole.termination == Termination::CompleteZlibStream && whole.bytes == Bytes{'A','B'},
          "Independent stored-block golden output");
    for (const auto cut : {std::size_t(13), std::size_t(24)}) {
        const Bytes prefix(complete.begin(), complete.begin() + static_cast<std::ptrdiff_t>(cut));
        const auto result = Decoder::Inspect(prefix, Bounded());
        Invariants(result, prefix.size(), Bounded());
        Check(result.termination == Termination::NonFinalEmptyStoredBlockBoundary,
              "Earlier genuine nonfinal empty stored boundary was not recognized");
        Check(result.bytes == (cut == 13 ? Bytes{'A'} : Bytes{'A','B'}), "Earlier boundary output mismatch");
        StrictIncomplete(prefix, Bounded());
    }
    const auto decoy = MagicInsideNonemptyStored();
    const auto result = Decoder::Inspect(decoy, Bounded());
    Check(result.termination == Termination::Incomplete && result.bytes == Bytes({0,0,255,255}),
          "Magic bytes inside nonempty block were misclassified as a flush boundary");
    StrictIncomplete(decoy, Bounded());
}
void LimitAndNegativeCases(const Bytes& complete) {
    const auto baseline = Decoder::Inspect(complete, Bounded());
    Reject(Code::NullInput, [] { Decoder::Inspect(nullptr, 1); }, "Null nonempty compressed input");
    const auto empty = Decoder::Inspect(nullptr, 0, Bounded());
    Check(empty.termination == Termination::Incomplete && empty.bytes.empty(), "Empty inspection semantics");
    Reject(Code::IncompleteStream, [] { Decoder::DecodeComplete(nullptr, 0); }, "Strict empty compressed input");
    auto limits = Bounded(); limits.maximumInputBytes = complete.size();
    Check(Decoder::Inspect(complete, limits).bytes == baseline.bytes, "Exact inclusive input limit");
    limits.maximumInputBytes = complete.size() - 1;
    Reject(Code::InputLimit, [&] { Decoder::Inspect(complete, limits); }, "Input limit one byte too short");
    limits.maximumInputBytes = 0;
    Reject(Code::InputLimit, [&] { Decoder::Inspect(complete, limits); }, "Zero input limit");
    limits = Bounded(); limits.maximumOutputBytes = 2;
    Check(Decoder::Inspect(complete, limits).termination == Termination::CompleteZlibStream,
          "Exact output limit must still permit zero-output trailer processing");
    limits.maximumOutputBytes = 1;
    Reject(Code::OutputLimit, [&] { Decoder::Inspect(complete, limits); }, "Output limit one byte too short");
    limits.maximumOutputBytes = 0;
    Reject(Code::OutputLimit, [&] { Decoder::Inspect(complete, limits); }, "Zero output limit with nonempty output");
    const Bytes emptyComplete{0x78,0x9c,0x03,0x00,0x00,0x00,0x00,0x01};
    Check(Decoder::Inspect(emptyComplete, limits).termination == Termination::CompleteZlibStream,
          "Zero output limit rejected a complete empty stream");
    limits = Bounded(); limits.maximumDecoderMemoryBytes = 0;
    Reject(Code::MemoryLimit, [&] { Decoder::Inspect(complete, limits); }, "Zero decoder-memory limit");
    Check(baseline.decoderPeakBytes > 1, "Expected an actual bounded decoder allocation");
    limits.maximumDecoderMemoryBytes = baseline.decoderPeakBytes;
    Check(Decoder::Inspect(complete, limits).bytes == baseline.bytes, "Exact inclusive decoder-memory limit");
    limits.maximumDecoderMemoryBytes = baseline.decoderPeakBytes - 1;
    Reject(Code::MemoryLimit, [&] { Decoder::Inspect(complete, limits); }, "Insufficient decoder-memory limit");
    limits = Bounded(); limits.maximumCalls = 0;
    Reject(Code::WorkLimit, [&] { Decoder::Inspect(complete, limits); }, "Zero work budget");
    limits.maximumCalls = baseline.calls;
    Check(Decoder::Inspect(complete, limits).termination == Termination::CompleteZlibStream,
          "Exact inclusive work budget");
    Check(baseline.calls > 1, "Stored golden must require multiple block calls");
    limits.maximumCalls = baseline.calls - 1;
    Reject(Code::WorkLimit, [&] { Decoder::Inspect(complete, limits); }, "Insufficient work budget");
    auto bytes = complete; bytes.push_back(0);
    Reject(Code::TrailingInput, [&] { Decoder::Inspect(bytes); }, "Trailing garbage after complete stream");
    Reject(Code::TrailingInput, [&] { Decoder::DecodeComplete(bytes.data(), bytes.size()); }, "Strict trailing garbage");
    bytes = complete; bytes.insert(bytes.end(), emptyComplete.begin(), emptyComplete.end());
    Reject(Code::TrailingInput, [&] { Decoder::Inspect(bytes); }, "Unexpected concatenated zlib streams");
    bytes = complete; bytes.back() ^= 1;
    Reject(Code::InvalidData, [&] { Decoder::Inspect(bytes); }, "Corrupt independent Adler-32 trailer");
    bytes = complete; bytes[5] ^= 1;
    Reject(Code::InvalidData, [&] { Decoder::Inspect(bytes); }, "Stored LEN/NLEN mismatch");
    bytes = complete; bytes[2] = 6;
    Reject(Code::InvalidData, [&] { Decoder::Inspect(bytes); }, "Reserved deflate block type");
}

struct Outcome { bool returned = false; int error = -1; Inspection result; };
bool Known(Code code) {
    switch (code) {
    case Code::NullInput: case Code::InputLimit: case Code::OutputLimit: case Code::MemoryLimit:
    case Code::AllocationFailure: case Code::WorkLimit: case Code::InvalidData: case Code::DictionaryRequired:
    case Code::TrailingInput: case Code::IncompleteStream: return true;
    }
    return false;
}
Outcome Probe(const Bytes& bytes) {
    auto limits = Bounded();
    limits.maximumInputBytes = 4096; limits.maximumOutputBytes = 262144;
    limits.maximumDecoderMemoryBytes = 262144; limits.maximumCalls = 512;
    Outcome outcome;
    try {
        outcome.result = Decoder::Inspect(bytes, limits); outcome.returned = true;
        Invariants(outcome.result, bytes.size(), limits);
    } catch (const Error& error) {
        Check(Known(error.Code()), "Unknown typed mutation error");
        outcome.error = static_cast<int>(error.Code());
    }
    return outcome;
}
std::uint32_t Next(std::uint32_t& state) { state = state * 1664525u + 1013904223u; return state; }
void Mutations(const Bytes& seedBytes, std::uint32_t seed) {
    Check(!seedBytes.empty() && seedBytes.size() <= 4096, "Mutation seed must be a small bounded vector");
    for (std::size_t trial = 0; trial < 512; ++trial) {
        Bytes bytes = seedBytes;
        const auto edits = 1u + Next(seed) % 4u;
        for (std::uint32_t i = 0; i < edits; ++i) {
            const auto offset = static_cast<std::size_t>(Next(seed)) % bytes.size();
            bytes[offset] ^= static_cast<unsigned char>((Next(seed) >> 16) | 1u);
        }
        if (trial % 7 == 0) bytes.resize(static_cast<std::size_t>(Next(seed)) % (bytes.size() + 1));
        const auto first = Probe(bytes), second = Probe(bytes);
        Check(first.returned == second.returned && first.error == second.error, "Nondeterministic mutation outcome");
        if (first.returned) {
            Check(first.result.termination == second.result.termination && first.result.bytes == second.result.bytes &&
                  first.result.inputConsumed == second.result.inputConsumed && first.result.calls == second.result.calls &&
                  first.result.lastBoundaryBit == second.result.lastBoundaryBit &&
                  first.result.finalDeflateBlockSeen == second.result.finalDeflateBlockSeen &&
                  first.result.adlerTrailerVerified == second.result.adlerTrailerVerified,
                  "Nondeterministic mutation inspection");
            ++counts.accepted; // Inspect returning partial bytes is not save acceptance.
        } else ++counts.rejected;
        ++counts.mutations;
    }
}

void PublicCase(const Bytes& compressed) {
    Check(compressed.size() == 407078, "Public compressed stdin size differs from its pinned observation");
    const auto before = Sha256(compressed);
    const auto result = Decoder::Inspect(compressed, Bounded());
    Invariants(result, compressed.size(), Bounded());
    publicResult.observed = true; publicResult.outputBytes = result.bytes.size();
    publicResult.sha = Hex(Sha256(result.bytes)); publicResult.termination = Name(result.termination);
    publicResult.finalBlockSeen = result.finalDeflateBlockSeen; publicResult.consumed = result.inputConsumed;
    publicResult.blocks = result.blocks; publicResult.lastBoundaryBit = result.lastBoundaryBit;
    Check(result.bytes.size() == PublicOutputBytes && publicResult.sha == PublicOutputSha,
          "Public independently observed plaintext size/SHA-256 mismatch");
    Check(result.bytes.size() >= 4 && result.bytes[0] == 1 && result.bytes[1] == 0 &&
          result.bytes[2] == 0 && result.bytes[3] == 0, "Public first SDK word differs from observation");
    // Observe the actual terminal state. The suffix alone does not identify the
    // final block or distinguish nonfinal flush from missing-wrapper-trailer.
    Check(result.termination != Termination::CompleteZlibStream && !result.adlerTrailerVerified,
          "Unfinished public stream was accepted as a complete zlib stream");
    StrictIncomplete(compressed, Bounded()); publicResult.strictRejected = true;
    Check(Sha256(compressed) == before, "Public compressed stdin buffer was modified");
}
std::string Json(const std::string& text) {
    static const char digits[] = "0123456789abcdef";
    std::string result = "\"";
    for (const char c : text) {
        const auto byte = static_cast<unsigned char>(c);
        if (byte == '"' || byte == '\\') { result += '\\'; result += c; }
        else if (byte < 32) { result += "\\u00"; result += digits[byte >> 4]; result += digits[byte & 15]; }
        else result += c;
    }
    return result + '"';
}
void Summary(bool success, const std::string& error = {}) {
    std::cout << "{\"status\":\"" << (success ? "PASS_RETAIL_INFLATE_COMPONENT" : "FAIL_RETAIL_INFLATE_COMPONENT")
              << "\",\"checks\":" << counts.checks << ",\"fixtures\":" << counts.fixtures
              << ",\"truncations\":" << counts.truncations << ",\"mutations\":" << counts.mutations
              << ",\"accepted_mutations\":" << counts.accepted << ",\"rejected_mutations\":" << counts.rejected
              << ",\"mutation_acceptance\":\"INSPECTION_RETURN_ONLY_NOT_SAVE\""
              << ",\"public_output_bytes\":" << publicResult.outputBytes
              << ",\"public_output_sha256\":" << Json(publicResult.sha)
              << ",\"public_termination\":" << Json(publicResult.termination)
              << ",\"public_strict_rejected\":" << (publicResult.strictRejected ? "true" : "false")
              << ",\"public_final_deflate_block_seen\":" << (publicResult.finalBlockSeen ? "true" : "false")
              << ",\"public_last_boundary_bit\":" << publicResult.lastBoundaryBit
              << ",\"public_input_consumed\":" << publicResult.consumed << ",\"public_blocks\":" << publicResult.blocks
              << ",\"input_files_unchanged\":" << (publicResult.unchanged ? "true" : "null")
              << ",\"gamecore_loaded\":false,\"window_created\":false,\"complete_save_validated\":false";
    if (!error.empty()) std::cout << ",\"error\":" << Json(error);
    std::cout << "}\n";
}
} // namespace

int main(int argc, char** argv) {
    static_assert(sizeof(void*) == 8, "This component must execute as x64");
    try {
        Check(argc == 2, "Expected exactly one immutable vector-fixture path and binary public stdin");
        const auto fixtureBytes = ReadFixture(argv[1]);
        const auto fixtures = ParseFixture(fixtureBytes);
        const auto compressed = ReadPublicInput();
        FixtureCases(fixtures);
        const auto golden = GoldenComplete();
        GoldenBoundaries(golden); LimitAndNegativeCases(golden);
        PublicCase(compressed);
        const auto coded = std::find_if(fixtures.begin(), fixtures.end(), [](const Fixture& item) {
            return item.kind == 0 && item.compressed.size() > 32 && item.compressed.size() <= 4096 &&
                   item.outputBytes <= 262144;
        });
        Check(coded != fixtures.end(), "No small independently generated coded mutation vector");
        Mutations(golden, 0x51b7f2abu);
        Mutations(Bytes(golden.begin(), golden.begin() + 13), 0x7a91f30du);
        Mutations(MagicInsideNonemptyStored(), 0x84ef2ca1u);
        Mutations(coded->compressed, 0x403694u);
        Check(counts.mutations == 2048 && counts.accepted + counts.rejected == 2048, "Incomplete mutation coverage");
        Check(ReadFixture(argv[1]) == fixtureBytes, "Immutable vector fixture was modified");
        publicResult.unchanged = true;
        Summary(true); return 0;
    } catch (const std::exception& error) {
        Summary(false, error.what()); return 1;
    } catch (...) {
        Summary(false, "Unexpected nonstandard exception"); return 2;
    }
}
