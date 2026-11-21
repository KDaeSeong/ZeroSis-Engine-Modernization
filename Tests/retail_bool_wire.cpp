#include "RetailSaveStateWire.h"
#include <array>
#include <cstddef>
#include <cstdint>
#include <exception>
#include <iostream>
#include <initializer_list>
#include <stdexcept>
#include <string>

// Independent literal byte tests for the explicit portable bool policies.
// No SDK serializer, file, save, process or window is opened.
namespace {
using namespace ZeroSisHost;
using Code = RetailStateErrorCode;
struct Suite {
    std::size_t checks = 0, strictAccepted = 0, strictRejected = 0, rawAccepted = 0, truncations = 0;
    void Check(bool value, const char* message) {
        ++checks;
        if (!value) throw std::runtime_error(message);
    }
};
template<class Function> void Reject(Suite& s, Function&& function, Code expected, std::size_t offset) {
    try { function(); }
    catch (const RetailStateError& error) {
        s.Check(error.Code() == expected, "Wrong typed boolean wire error");
        s.Check(error.Offset() == offset, "Wrong exact boolean wire error offset"); return;
    }
    s.Check(false, "Invalid boolean wire input was accepted");
}
RetailSaveStateLimits Limits(RetailBooleanWireProfile profile) {
    auto result = RetailSaveStateLimits{}; result.booleanWireProfile = profile; return result;
}
void AllBytes(Suite& s) {
    const auto strict = RetailSaveStateLimits{};
    s.Check(strict.booleanWireProfile == RetailBooleanWireProfile::CanonicalZeroOne, "Default boolean policy changed");
    const auto raw = Limits(RetailBooleanWireProfile::SdkRawByte);
    for (unsigned value = 0; value < 256u; ++value) {
        const std::array<unsigned char, 5> literal = {static_cast<unsigned char>(value), 0x78,0x56,0x34,0x12};
        const auto before = literal;
        RetailStateDetail::Reader canonical(literal.data(), literal.size(), strict);
        if (value <= 1u) {
            s.Check(canonical.Bool() == (value != 0u), "Canonical literal truth value differs"); ++s.strictAccepted;
        } else {
            Reject(s, [&] { canonical.Bool(); }, Code::InvalidValue, 1); ++s.strictRejected;
        }
        s.Check(canonical.Pos() == 1u && canonical.Records() == 0u, "Canonical bool did not advance exactly one byte");
        s.Check(canonical.U32() == 0x12345678u && canonical.Pos() == 5u, "Canonical bool moved the following integer");
        RetailStateDetail::Reader sdk(literal.data(), literal.size(), raw);
        s.Check(sdk.Bool() == (value != 0u), "SDK raw byte truth value differs"); ++s.rawAccepted;
        s.Check(sdk.Pos() == 1u && sdk.Records() == 0u, "SDK bool did not advance exactly one byte");
        s.Check(sdk.U32() == 0x12345678u && sdk.Pos() == 5u, "SDK bool moved the following integer");
        s.Check(literal == before, "Boolean reads modified the independent literal input");
    }
}
struct Branch {
    RetailInflatedSpan text;
    std::uint32_t following = 0;
    std::size_t next = 0, records = 0;
    bool present = false;
};
Branch ReadBranch(const unsigned char* data, std::size_t size, const RetailSaveStateLimits& limits) {
    RetailStateDetail::Reader reader(data, size, limits); Branch result;
    result.present = reader.Bool();
    if (result.present) result.text = reader.String();
    result.following = reader.U32(); result.next = reader.Pos(); result.records = reader.Records(); return result;
}
void Branches(Suite& s) {
    // Presence=255, u32 length=3, unpadded A/NUL/Z, then an independent u32.
    const std::array<unsigned char, 12> rawLiteral = {255,3,0,0,0,'A',0,'Z',0x78,0x56,0x34,0x12};
    const std::array<unsigned char, 12> canonicalLiteral = {1,3,0,0,0,'A',0,'Z',0x78,0x56,0x34,0x12};
    const std::array<unsigned char, 5> absentLiteral = {0,0x78,0x56,0x34,0x12};
    const auto beforeRaw = rawLiteral, beforeCanonical = canonicalLiteral;
    const auto beforeAbsent = absentLiteral;
    auto raw = Limits(RetailBooleanWireProfile::SdkRawByte);
    const auto strict = Limits(RetailBooleanWireProfile::CanonicalZeroOne);
    for (const auto profile : {RetailBooleanWireProfile::CanonicalZeroOne, RetailBooleanWireProfile::SdkRawByte}) {
        const auto limits = Limits(profile);
        const auto& bytes = profile == RetailBooleanWireProfile::SdkRawByte ? rawLiteral : canonicalLiteral;
        const auto result = ReadBranch(bytes.data(), bytes.size(), limits);
        s.Check(result.present && result.text.offset == 5u && result.text.bytes == 3u && result.following == 0x12345678u &&
            result.next == 12u && result.records == 0u, "Literal presence/string/int branch differs");
        const auto absent = ReadBranch(absentLiteral.data(), absentLiteral.size(), limits);
        s.Check(!absent.present && absent.next == 5u && absent.following == 0x12345678u && absent.records == 0u,
            "False presence byte consumed a string length");
        for (std::size_t cut = 0; cut < bytes.size(); ++cut) {
            const auto offset = cut == 0u ? 0u : (cut < 5u ? 1u : (cut < 8u ? 5u : 8u));
            Reject(s, [&] { ReadBranch(bytes.data(), cut, limits); }, Code::Truncated, offset); ++s.truncations;
        }
    }
    Reject(s, [&] { ReadBranch(rawLiteral.data(), rawLiteral.size(), strict); }, Code::InvalidValue, 1);
    raw.maxInputBytes = rawLiteral.size();
    s.Check(ReadBranch(rawLiteral.data(), rawLiteral.size(), raw).next == 12u, "Exact raw-branch input budget rejected");
    --raw.maxInputBytes;
    Reject(s, [&] { ReadBranch(rawLiteral.data(), rawLiteral.size(), raw); }, Code::InputLimit, 0);
    raw = Limits(RetailBooleanWireProfile::SdkRawByte); raw.maxPrefixBytes = 12;
    s.Check(ReadBranch(rawLiteral.data(), rawLiteral.size(), raw).next == 12u, "Exact branch prefix budget rejected");
    --raw.maxPrefixBytes;
    Reject(s, [&] { ReadBranch(rawLiteral.data(), rawLiteral.size(), raw); }, Code::PrefixLimit, 8);
    raw = Limits(RetailBooleanWireProfile::SdkRawByte); raw.maxPrefixBytes = 0;
    Reject(s, [&] { ReadBranch(rawLiteral.data(), rawLiteral.size(), raw); }, Code::PrefixLimit, 0);
    raw = Limits(RetailBooleanWireProfile::SdkRawByte); raw.maxStringBytes = 3;
    s.Check(ReadBranch(rawLiteral.data(), rawLiteral.size(), raw).text.bytes == 3u, "Exact presence string budget rejected");
    --raw.maxStringBytes;
    Reject(s, [&] { ReadBranch(rawLiteral.data(), rawLiteral.size(), raw); }, Code::StringLimit, 5);
    raw = Limits(RetailBooleanWireProfile::SdkRawByte); raw.maxStringBytes = 0;
    s.Check(ReadBranch(absentLiteral.data(), absentLiteral.size(), raw).next == 5u, "Absent branch charged nonexistent string bytes");
    Reject(s, [&] { ReadBranch(rawLiteral.data(), rawLiteral.size(), raw); }, Code::StringLimit, 5);
    raw = Limits(RetailBooleanWireProfile::SdkRawByte); raw.maxTotalRecords = 0; raw.maxArrayRecords = 0;
    s.Check(ReadBranch(rawLiteral.data(), rawLiteral.size(), raw).records == 0u, "Bool/string fixed bytes were charged as array records");
    s.Check(rawLiteral == beforeRaw && canonicalLiteral == beforeCanonical && absentLiteral == beforeAbsent,
        "Branch or rejected reads changed literal input");
}
void Boundaries(Suite& s) {
    const std::array<unsigned char, 8> literal = {0xaa,0xbb,0xcc,255,0x78,0x56,0x34,0x12};
    const auto before = literal;
    const auto strict = Limits(RetailBooleanWireProfile::CanonicalZeroOne);
    const auto raw = Limits(RetailBooleanWireProfile::SdkRawByte);
    RetailStateDetail::Reader canonical(literal.data(), literal.size(), strict); canonical.Skip(3);
    Reject(s, [&] { canonical.Bool(); }, Code::InvalidValue, 4);
    s.Check(canonical.Pos() == 4u && canonical.U32() == 0x12345678u && canonical.Pos() == 8u,
        "Nonzero-offset canonical bool lost one-byte advancement");
    RetailStateDetail::Reader sdk(literal.data(), literal.size(), raw); sdk.Skip(3);
    s.Check(sdk.Bool() && sdk.Pos() == 4u && sdk.U32() == 0x12345678u && sdk.Pos() == 8u,
        "Nonzero-offset SDK bool lost one-byte advancement");
    for (const auto profile : {RetailBooleanWireProfile::CanonicalZeroOne, RetailBooleanWireProfile::SdkRawByte}) {
        const auto limits = Limits(profile);
        Reject(s, [&] { RetailStateDetail::Reader reader(nullptr, 1, limits); reader.Bool(); }, Code::NullInput, 0);
        Reject(s, [&] { RetailStateDetail::Reader reader(nullptr, 0, limits); reader.Bool(); }, Code::Truncated, 0);
        Reject(s, [&] { RetailStateDetail::Reader reader(literal.data(), 0, limits); reader.Bool(); }, Code::Truncated, 0);
        ++s.truncations;
        auto one = limits; one.maxPrefixBytes = 1;
        const std::array<unsigned char, 5> oneByte = {1,0x78,0x56,0x34,0x12};
        RetailStateDetail::Reader reader(oneByte.data(), oneByte.size(), one);
        s.Check(reader.Bool() && reader.Pos() == 1u, "One-byte prefix budget rejected the bool itself");
        Reject(s, [&] { reader.U32(); }, Code::PrefixLimit, 1);
    }
    for (const auto value : {2, 99, -1}) {
        auto invalid = strict; invalid.booleanWireProfile = static_cast<RetailBooleanWireProfile>(value);
        Reject(s, [&] { RetailStateDetail::Reader reader(literal.data(), literal.size(), invalid); reader.Bool(); }, Code::UnsupportedProfile, 0);
    }
    s.Check(literal == before, "Nonzero-offset or invalid-profile reads changed input");
}
std::string Escape(const char* text) {
    std::string result;
    for (const unsigned char* at = reinterpret_cast<const unsigned char*>(text); *at; ++at) {
        if (*at == '"' || *at == '\\') result += '\\';
        result += *at < 32 ? '?' : static_cast<char>(*at);
    }
    return result;
}
} // namespace

int main(int argc, char** argv) {
    static_assert(sizeof(void*) == 8, "Boolean wire verification requires x64");
    (void)argv;
    try {
        if (argc != 1) throw std::invalid_argument("Boolean component accepts no arguments or paths");
        Suite suite; AllBytes(suite); Branches(suite); Boundaries(suite);
        suite.Check(suite.strictAccepted == 2u && suite.strictRejected == 254u && suite.rawAccepted == 256u,
            "Exhaustive boolean policy case accounting differs");
        std::cout << "{\"status\":\"PASS_RETAIL_BOOL_WIRE_COMPONENT\",\"checks\":" << suite.checks
            << ",\"literal_byte_values\":256,\"canonical_accepted\":" << suite.strictAccepted
            << ",\"canonical_rejected\":" << suite.strictRejected << ",\"sdk_byte_accepted\":" << suite.rawAccepted
            << ",\"truncations\":" << suite.truncations << ",\"unknown_profile_cases\":3,\"presence_branch_cases\":4"
            << ",\"input_bytes_unchanged\":true,\"input_files_unchanged\":true"
            << ",\"gamecore_loaded\":false,\"window_created\":false,\"game_accessed\":false,\"user_saves_accessed\":false"
            << ",\"complete_player_validated\":false,\"complete_save_validated\":false"
            << ",\"ruleset_compatibility_verified\":false,\"restore_approved\":false,\"full_engine_goal_complete\":false}\n";
        return 0;
    } catch (const RetailStateError& error) {
        std::cout << "{\"status\":\"FAIL_RETAIL_BOOL_WIRE_COMPONENT\",\"error\":\"" << Escape(error.what())
            << "\",\"error_code\":" << static_cast<int>(error.Code()) << ",\"error_offset\":" << error.Offset()
            << ",\"gamecore_loaded\":false,\"window_created\":false,\"restore_approved\":false}\n";
    } catch (const std::exception& error) {
        std::cout << "{\"status\":\"FAIL_RETAIL_BOOL_WIRE_COMPONENT\",\"error\":\"" << Escape(error.what())
            << "\",\"gamecore_loaded\":false,\"window_created\":false,\"restore_approved\":false}\n";
    }
    return 1;
}
