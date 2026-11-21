// Own headless component test: no engine, SDK, operating-system UI, or save writes.
// Independent public expectations: bmaupin/js-civ5save commit
// 858ce8532725f634e64fa8acaf355aa8e50829bf,
// src/__tests__/Civ5Save.test.js:82-212,1081-1093.
#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <exception>
#include <fstream>
#include <initializer_list>
#include <ios>
#include <iostream>
#include <iterator>
#include <limits>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include "../Source/Host/RetailSaveHeader.h"

namespace {
using Bytes = std::vector<unsigned char>;
using Header = ZeroSisHost::RetailSaveHeader;
using Limits = ZeroSisHost::RetailSaveHeaderLimits;
using Error = ZeroSisHost::RetailSaveHeaderError;
using Code = ZeroSisHost::RetailSaveHeaderErrorCode;
constexpr std::size_t FixtureLimit = 16u * 1024u;

struct Counters {
    std::size_t checks = 0, fixtures = 0, truncations = 0;
    std::size_t mutations = 0, acceptedMutations = 0, rejectedMutations = 0;
} counts;

void Check(bool condition, const std::string& message) {
    ++counts.checks;
    if (!condition) throw std::runtime_error(message);
}

template<class F> void Reject(Code expected, F&& operation, const std::string& message) {
    bool rejected = false;
    try {
        operation();
    } catch (const Error& error) {
        Check(error.Code() == expected, message + ": wrong typed error");
        rejected = true;
    }
    Check(rejected, message + ": input was accepted");
}

Limits BoundedLimits() {
    Limits limits;
    limits.maximumHeaderBytes = FixtureLimit;
    limits.maximumStringBytes = FixtureLimit;
    limits.maximumDlcRecords = 64;
    limits.maximumModRecords = 64;
    return limits;
}

Bytes ReadFixture(const char* path) {
    // Only the two explicit caller-owned immutable public prefix files are read.
    std::ifstream file(path, std::ios::binary | std::ios::ate);
    Check(static_cast<bool>(file), "Cannot open explicit public prefix file");
    const auto end = file.tellg();
    Check(end > std::streampos(0) && end <= std::streampos(FixtureLimit),
          "Public fixture must be a nonempty prefix of at most 16 KiB");
    const auto size = static_cast<std::size_t>(end);
    Bytes data(size);
    file.seekg(0, std::ios::beg);
    file.read(reinterpret_cast<char*>(data.data()), static_cast<std::streamsize>(size));
    Check(static_cast<bool>(file) && file.gcount() == static_cast<std::streamsize>(size),
          "Incomplete public prefix read");
    Check(file.peek() == std::char_traits<char>::eof(), "Public prefix changed during read");
    return data;
}

std::uint32_t WireU32(const Bytes& data, std::size_t offset) {
    Check(offset <= data.size() && data.size() - offset >= 4,
          "Independent scalar oracle exceeded public prefix");
    return static_cast<std::uint32_t>(data[offset]) |
        (static_cast<std::uint32_t>(data[offset + 1]) << 8) |
        (static_cast<std::uint32_t>(data[offset + 2]) << 16) |
        (static_cast<std::uint32_t>(data[offset + 3]) << 24);
}

std::string RawBuildOracle(const Bytes& data) {
    // Inspect the first two wire strings independently. The upstream JS getter
    // normalizes raw build 180925 to 403694; this reader must preserve raw bytes.
    const auto versionLength = WireU32(data, 8);
    Check(versionLength <= FixtureLimit - 12, "Invalid public version-string span");
    const std::size_t buildOffset = 12 + static_cast<std::size_t>(versionLength);
    const auto buildLength = WireU32(data, buildOffset);
    const auto start = buildOffset + 4;
    Check(start <= data.size() && buildLength <= data.size() - start,
          "Invalid public raw-build span");
    return std::string(reinterpret_cast<const char*>(data.data() + start), buildLength);
}

void EqualHeader(const Header& actual, const Header& expected, const std::string& label) {
    Check(actual.saveGameVersion == expected.saveGameVersion, label + ": save version");
    Check(actual.gameVersion == expected.gameVersion, label + ": game version");
    Check(actual.gameBuild == expected.gameBuild, label + ": raw game build");
    Check(actual.currentTurn == expected.currentTurn, label + ": current turn");
    Check(actual.gameMode == expected.gameMode, label + ": game mode");
    Check(actual.playerCivilization == expected.playerCivilization, label + ": civilization");
    Check(actual.difficulty == expected.difficulty, label + ": difficulty");
    Check(actual.startingEra == expected.startingEra, label + ": starting era");
    Check(actual.currentEra == expected.currentEra, label + ": current era");
    Check(actual.gamePace == expected.gamePace, label + ": pace");
    Check(actual.mapSize == expected.mapSize, label + ": map size");
    Check(actual.mapFile == expected.mapFile, label + ": map file");
    Check(actual.consumedPrefixBytes == expected.consumedPrefixBytes, label + ": prefix boundary");
    Check(actual.enabledDlc.size() == expected.enabledDlc.size(), label + ": DLC count");
    Check(actual.enabledMods.size() == expected.enabledMods.size(), label + ": mod count");
    for (std::size_t i = 0; i < expected.enabledDlc.size(); ++i) {
        Check(actual.enabledDlc[i].identifier == expected.enabledDlc[i].identifier, label + ": opaque DLC GUID bytes");
        Check(actual.enabledDlc[i].auxiliary == expected.enabledDlc[i].auxiliary, label + ": opaque DLC auxiliary bytes");
        Check(actual.enabledDlc[i].name == expected.enabledDlc[i].name, label + ": DLC name bytes");
    }
    for (std::size_t i = 0; i < expected.enabledMods.size(); ++i) {
        Check(actual.enabledMods[i].identifier == expected.enabledMods[i].identifier, label + ": opaque mod ID bytes");
        Check(actual.enabledMods[i].auxiliary == expected.enabledMods[i].auxiliary, label + ": opaque mod auxiliary bytes");
        Check(actual.enabledMods[i].name == expected.enabledMods[i].name, label + ": mod name bytes");
    }
}

void AllTruncations(const Bytes& bytes, const std::string& label) {
    const auto limits = BoundedLimits();
    for (std::size_t end = 0; end < bytes.size(); ++end) {
        Reject(Code::Truncated, [&] { Header::ParsePrefix(bytes.data(), end, limits); },
               label + ": truncation at byte " + std::to_string(end));
        ++counts.truncations;
    }
}

void SuffixBoundary(const Bytes& prefix, const Header& original) {
    Bytes bytes = prefix;
    const unsigned char suffix[] = {0x78, 0x9c, 0xff, 0x00, 'C', 'I', 'V', '5'};
    bytes.insert(bytes.end(), std::begin(suffix), std::end(suffix));
    auto limits = BoundedLimits();
    limits.maximumHeaderBytes = prefix.size();
    EqualHeader(Header::ParsePrefix(bytes, limits), original, "Opaque suffix must be untouched");
}

void Public279(const Bytes& bytes) {
    const auto header = Header::ParsePrefix(bytes, BoundedLimits());
    // Full upstream blob 186fb9a84f4e47192e11b8cd98b436a48ccbee16;
    // only its independently delimited 718-byte metadata prefix is retained.
    Check(bytes.size() == 718, "Public .279 independently delimited prefix length");
    Check(header.saveGameVersion == 8, "Public .279 independently observed metadata version");
    Check(header.gameVersion == "1.0.3.279(130961)", "Public .279 upstream game-version oracle");
    Check(header.gameBuild == RawBuildOracle(bytes), "Public .279 raw build must not be normalized");
    Check(header.gameBuild == "403694", "Public .279 independently observed raw build");
    Check(header.currentTurn == 264, "Public .279 upstream turn oracle");
    Check(header.gameMode == 1, "Public .279 upstream multiplayer oracle");
    Check(header.playerCivilization == "CIVILIZATION_DENMARK", "Public .279 independent civilization oracle");
    Check(header.difficulty == "HANDICAP_SETTLER", "Public .279 upstream difficulty oracle");
    Check(header.startingEra == "ERA_FUTURE" && header.currentEra == "ERA_FUTURE", "Public .279 upstream era oracle");
    Check(header.gamePace == "GAMESPEED_QUICK", "Public .279 upstream pace oracle");
    Check(header.mapSize == "WORLDSIZE_DUEL", "Public .279 upstream size oracle");
    Check(header.mapFile == "Assets\\Maps\\Earth_Duel.Civ5Map", "Public .279 independent raw map path oracle");
    const std::array<const char*, 14> dlcNames{{
        "Mongolia", "Spain and Inca", "Polynesia", "Denmark", "Korea", "Ancient Wonders",
        "Civilization 5 Complete", "Babylon", "DLC_SP_Maps", "DLC_SP_Maps_2", "DLC_SP_Maps_3",
        "Expansion - Gods and Kings", "Expansion - Brave New World", "Upgrade 1"
    }};
    Check(header.enabledDlc.size() == dlcNames.size(), "Public .279 upstream DLC count oracle");
    for (std::size_t i = 0; i < dlcNames.size(); ++i)
        Check(header.enabledDlc[i].name == dlcNames[i], "Public .279 upstream DLC order/name oracle");
    Check(header.enabledMods.empty(), "Public .279 upstream empty mods oracle");
    Check(header.consumedPrefixBytes == bytes.size(), "Public .279 fixture must end at metadata boundary");
    SuffixBoundary(bytes, header);
    AllTruncations(bytes, "Public .279");
    ++counts.fixtures;
}

void PublicIssue8(const Bytes& bytes) {
    const auto header = Header::ParsePrefix(bytes, BoundedLimits());
    // Full upstream blob c34d0d8a66f35d3b4721550626697b5e0838e7d4;
    // only its independently delimited 1100-byte metadata prefix is retained.
    Check(bytes.size() == 1100, "Public issue8 independently delimited prefix length");
    Check(header.saveGameVersion == 8, "Public issue8 independently observed metadata version");
    Check(header.gameVersion == "1.0.3.279 (403694)", "Public issue8 independent game-version oracle");
    Check(header.gameBuild == "403694", "Public issue8 independently observed raw build");
    Check(header.currentTurn == 50 && header.gameMode == 0, "Public issue8 independent turn/mode oracle");
    Check(header.playerCivilization == "CIVILIZATION_VENICE", "Public issue8 independent civilization oracle");
    Check(header.difficulty == "HANDICAP_DEITY", "Public issue8 independent difficulty oracle");
    Check(header.startingEra == "ERA_ANCIENT" && header.currentEra == "ERA_ANCIENT", "Public issue8 independent era oracle");
    Check(header.gamePace == "GAMESPEED_STANDARD", "Public issue8 independent pace oracle");
    Check(header.mapSize == "WORLDSIZE_STANDARD", "Public issue8 independent map-size oracle");
    Check(header.mapFile == "Assets\\Maps\\Archipelago.lua", "Public issue8 independent raw map path oracle");
    Check(header.enabledDlc.size() == 14, "Public issue8 independent DLC count oracle");
    const std::array<const char*, 5> modNames{{
        "(1) Community Patch", "(2) Community Balance Overhaul", "(3) City-State Diplomacy Mod for CBP",
        "(4) C4DF - CBP", "(5) More Luxuries - CBO Edition (5-14b)"
    }};
    const std::array<const char*, 5> modIdentifiers{{
        "d1b6328c-ff44-4b0d-aad7-c657f83610cd", "8411a7a8-dad3-4622-a18e-fcc18324c799",
        "eead0050-1e3f-4178-a91f-26cf1881ac39", "c7bf7064-d1b1-4708-9e93-7a1560868582",
        "be2d13ee-d18d-410e-8f04-7cd19cd99a98"
    }};
    const std::array<unsigned char, 5> auxiliaryFirstBytes{{0x59, 0x0d, 0x1b, 0x0b, 0x9b}};
    Check(header.enabledMods.size() == modNames.size(), "Public issue8 upstream mod-count oracle");
    for (std::size_t i = 0; i < modNames.size(); ++i) {
        Check(header.enabledMods[i].name == modNames[i], "Public issue8 upstream exact mod-name/order oracle");
        Check(header.enabledMods[i].identifier == modIdentifiers[i], "Public issue8 independently observed mod ID bytes");
        const std::array<unsigned char, 4> auxiliary{{auxiliaryFirstBytes[i], 0, 0, 0}};
        Check(header.enabledMods[i].auxiliary == auxiliary, "Public issue8 independently observed four auxiliary bytes");
    }
    Check(header.gameBuild == RawBuildOracle(bytes), "Public issue8 raw build must not be normalized");
    Check(header.consumedPrefixBytes == bytes.size(), "Public issue8 fixture must end at metadata boundary");
    SuffixBoundary(bytes, header);
    AllTruncations(bytes, "Public issue8");
    ++counts.fixtures;
}

void PutU32(Bytes& bytes, std::uint32_t value) {
    for (unsigned int i = 0; i < 4; ++i)
        bytes.push_back(static_cast<unsigned char>((value >> (8u * i)) & 0xffu));
}

void PatchU32(Bytes& bytes, std::size_t offset, std::uint32_t value) {
    Check(offset <= bytes.size() && bytes.size() - offset >= 4, "Synthetic patch escaped its bytes");
    for (unsigned int i = 0; i < 4; ++i)
        bytes[offset + i] = static_cast<unsigned char>((value >> (8u * i)) & 0xffu);
}

struct Synthetic {
    Bytes bytes;
    Header expected;
    std::vector<std::size_t> stringOffsets;
    std::size_t dlcCountOffset = 0, modCountOffset = 0;
};

void PutString(Synthetic& fixture, const std::string& value) {
    fixture.stringOffsets.push_back(fixture.bytes.size());
    PutU32(fixture.bytes, static_cast<std::uint32_t>(value.size()));
    for (const char byte : value) fixture.bytes.push_back(static_cast<unsigned char>(byte));
}

Synthetic Rich(std::uint32_t version) {
    Synthetic fixture;
    auto& expected = fixture.expected;
    const std::string utf8("\xed\x95\x9c\xea\xb8\x80", 6);
    expected.saveGameVersion = version;
    expected.gameVersion = std::string("RAW\0VERSION", 11);
    expected.gameBuild = "180925"; // Preserve it; do not apply the upstream JS getter workaround.
    expected.currentTurn = 0xffffffffu;
    expected.gameMode = 2;
    expected.playerCivilization = "CIVILIZATION_TEST";
    expected.difficulty = std::string("A\0B", 3);
    expected.startingEra = "ERA_ANCIENT";
    expected.currentEra = "ERA_FUTURE";
    expected.gamePace = utf8;
    expected.mapSize = "WORLDSIZE_DUEL";
    expected.mapFile = std::string("map\0", 4) + utf8;
    ZeroSisHost::RetailSaveDlcRecord dlc;
    for (std::size_t i = 0; i < dlc.identifier.size(); ++i)
        dlc.identifier[i] = static_cast<unsigned char>(i * 13u);
    dlc.auxiliary = {{0x00, 0xff, 0x80, 0x7f}};
    dlc.name = std::string("D\0", 2) + utf8;
    expected.enabledDlc.push_back(dlc);
    std::reverse(dlc.identifier.begin(), dlc.identifier.end());
    dlc.auxiliary = {{0x99, 0x00, 0x01, 0xfe}};
    dlc.name.clear();
    expected.enabledDlc.push_back(dlc);
    ZeroSisHost::RetailSaveModRecord mod;
    mod.identifier = std::string("m\0id", 4) + utf8;
    mod.auxiliary = {{0x04, 0x03, 0x02, 0x81}};
    mod.name = utf8 + std::string("\0M", 2);
    expected.enabledMods.push_back(mod);
    mod.identifier.clear();
    mod.auxiliary = {{0xff, 0xff, 0x00, 0x00}};
    mod.name = std::string("\0\0", 2);
    expected.enabledMods.push_back(mod);
    fixture.bytes = {'C', 'I', 'V', '5'};
    PutU32(fixture.bytes, version);
    PutString(fixture, expected.gameVersion);
    PutString(fixture, expected.gameBuild);
    PutU32(fixture.bytes, expected.currentTurn);
    fixture.bytes.push_back(expected.gameMode);
    for (const auto* value : {&expected.playerCivilization, &expected.difficulty, &expected.startingEra,
                             &expected.currentEra, &expected.gamePace, &expected.mapSize, &expected.mapFile})
        PutString(fixture, *value);
    fixture.dlcCountOffset = fixture.bytes.size();
    PutU32(fixture.bytes, 2);
    for (const auto& record : expected.enabledDlc) {
        fixture.bytes.insert(fixture.bytes.end(), record.identifier.begin(), record.identifier.end());
        fixture.bytes.insert(fixture.bytes.end(), record.auxiliary.begin(), record.auxiliary.end());
        PutString(fixture, record.name);
    }
    fixture.modCountOffset = fixture.bytes.size();
    PutU32(fixture.bytes, 2);
    for (const auto& record : expected.enabledMods) {
        PutString(fixture, record.identifier);
        fixture.bytes.insert(fixture.bytes.end(), record.auxiliary.begin(), record.auxiliary.end());
        PutString(fixture, record.name);
    }
    expected.consumedPrefixBytes = fixture.bytes.size();
    return fixture;
}

Bytes GoldenEmpty(std::uint32_t version) {
    // Manually specified wire bytes, independent of both the production reader
    // and the rich-fixture encoder. Turn is 0x78563412 and all nine strings empty.
    Bytes bytes{
        'C','I','V','5', 7,0,0,0,
        0,0,0,0, 0,0,0,0, 0x12,0x34,0x56,0x78, 2,
        0,0,0,0, 0,0,0,0, 0,0,0,0, 0,0,0,0,
        0,0,0,0, 0,0,0,0, 0,0,0,0,
        0,0,0,0, 0,0,0,0
    };
    Check(bytes.size() == 57, "Independent golden wire length");
    PatchU32(bytes, 4, version);
    return bytes;
}

void SyntheticCases(const Synthetic& rich7, const Synthetic& rich8) {
    for (const auto* fixture : {&rich7, &rich8}) {
        EqualHeader(Header::ParsePrefix(fixture->bytes), fixture->expected, "Rich opaque-byte fixture");
        AllTruncations(fixture->bytes, "Rich opaque-byte fixture");
        SuffixBoundary(fixture->bytes, fixture->expected);
    }
    for (const std::uint32_t version : {7u, 8u}) {
        const auto bytes = GoldenEmpty(version);
        Header expected;
        expected.saveGameVersion = version;
        expected.currentTurn = 0x78563412u;
        expected.gameMode = 2;
        expected.consumedPrefixBytes = 57;
        Limits limits;
        limits.maximumStringBytes = limits.maximumDlcRecords = limits.maximumModRecords = 0;
        limits.maximumHeaderBytes = bytes.size();
        EqualHeader(Header::ParsePrefix(bytes, limits), expected, "Independent zero-list golden fixture");
        for (std::size_t budget = 0; budget < bytes.size(); ++budget) {
            limits.maximumHeaderBytes = budget;
            Reject(Code::HeaderLimit, [&] { Header::ParsePrefix(bytes, limits); }, "Every short header budget");
        }
    }
}

void RejectionCases(const Synthetic& rich) {
    auto limits = BoundedLimits();
    const auto empty = GoldenEmpty(8);
    Reject(Code::NullInput, [&] { Header::ParsePrefix(nullptr, 1, limits); }, "Null nonempty input");
    Reject(Code::Truncated, [&] { Header::ParsePrefix(nullptr, 0, limits); }, "Null empty input");
    Reject(Code::Truncated, [&] { Header::ParsePrefix(Bytes{}); }, "Empty vector input");
    for (std::size_t i = 0; i < 4; ++i) {
        auto bytes = empty;
        bytes[i] ^= 0x80;
        Reject(Code::Signature, [&] { Header::ParsePrefix(bytes); }, "Every signature byte");
    }
    for (const std::uint32_t version : {0u, 6u, 9u, 0xffffffffu}) {
        auto bytes = empty;
        PatchU32(bytes, 4, version);
        Reject(Code::UnsupportedVersion, [&] { Header::ParsePrefix(bytes); }, "Unsupported metadata version");
    }
    for (const auto offset : rich.stringOffsets) {
        auto bytes = rich.bytes;
        PatchU32(bytes, offset, 0xffffffffu);
        Reject(Code::StringLimit, [&] { Header::ParsePrefix(bytes, limits); }, "Every oversized string length");
    }
    for (const auto offset : {rich.dlcCountOffset, rich.modCountOffset}) {
        auto bytes = rich.bytes;
        PatchU32(bytes, offset, 0xffffffffu);
        Reject(Code::RecordLimit, [&] { Header::ParsePrefix(bytes, limits); }, "Oversized record count");
    }
    for (const auto offset : {std::size_t(49), std::size_t(53)}) {
        auto bytes = empty;
        PatchU32(bytes, offset, 1);
        Reject(Code::Truncated, [&] { Header::ParsePrefix(bytes, limits); }, "Impossible minimum record span");
    }
    limits.maximumDlcRecords = limits.maximumModRecords = 2;
    EqualHeader(Header::ParsePrefix(rich.bytes, limits), rich.expected, "Exact list count limits");
    limits.maximumDlcRecords = 1;
    Reject(Code::RecordLimit, [&] { Header::ParsePrefix(rich.bytes, limits); }, "DLC count budget");
    limits.maximumDlcRecords = 2;
    limits.maximumModRecords = 1;
    Reject(Code::RecordLimit, [&] { Header::ParsePrefix(rich.bytes, limits); }, "Mod count budget");
    limits = BoundedLimits();
    std::size_t longestString = 0;
    for (const auto offset : rich.stringOffsets)
        longestString = std::max(longestString, static_cast<std::size_t>(WireU32(rich.bytes, offset)));
    Check(longestString > 0, "Rich fixture must exercise nonempty string boundaries");
    limits.maximumStringBytes = longestString;
    EqualHeader(Header::ParsePrefix(rich.bytes, limits), rich.expected, "Exact maximum string length");
    limits.maximumStringBytes = longestString - 1;
    Reject(Code::StringLimit, [&] { Header::ParsePrefix(rich.bytes, limits); }, "String budget one byte below requirement");
    limits.maximumStringBytes = 0;
    Reject(Code::StringLimit, [&] { Header::ParsePrefix(rich.bytes, limits); }, "Nonempty string under zero budget");
    for (const auto offset : {rich.stringOffsets.front(), rich.dlcCountOffset, rich.modCountOffset}) {
        auto bytes = rich.bytes;
        PatchU32(bytes, offset, 0xffffffffu);
        limits.maximumHeaderBytes = limits.maximumStringBytes = std::numeric_limits<std::size_t>::max();
        limits.maximumDlcRecords = limits.maximumModRecords = std::numeric_limits<std::size_t>::max();
        Reject(Code::Truncated, [&] { Header::ParsePrefix(bytes, limits); }, "Hostile lengths before allocation even with permissive limits");
    }
    for (const bool dlc : {true, false}) {
        auto bytes = empty;
        if (dlc) {
            bytes.resize(53);
            PatchU32(bytes, 49, 1);
            bytes.insert(bytes.end(), 24, 0);
            PutU32(bytes, 0);
        } else {
            PatchU32(bytes, 53, 1);
            bytes.insert(bytes.end(), 12, 0);
        }
        limits = BoundedLimits();
        limits.maximumHeaderBytes = dlc ? 53 : 57;
        Reject(Code::HeaderLimit, [&] { Header::ParsePrefix(bytes, limits); }, "Record reserve header-budget preflight");
    }
}

bool KnownCode(Code code) {
    switch (code) {
    case Code::NullInput: case Code::Truncated: case Code::HeaderLimit: case Code::StringLimit:
    case Code::RecordLimit: case Code::Signature: case Code::UnsupportedVersion: return true;
    }
    return false;
}

struct Outcome { bool accepted = false; Code code = Code::Truncated; Header value; };

Outcome Probe(const Bytes& bytes, const Limits& limits) {
    Outcome result;
    try {
        result.value = Header::ParsePrefix(bytes, limits);
        result.accepted = true;
        Check(result.value.consumedPrefixBytes <= bytes.size() &&
              result.value.consumedPrefixBytes <= limits.maximumHeaderBytes, "Mutation parser exceeded its prefix");
        Check(result.value.enabledDlc.size() <= limits.maximumDlcRecords &&
              result.value.enabledMods.size() <= limits.maximumModRecords, "Mutation parser exceeded record limits");
    } catch (const Error& error) {
        result.code = error.Code();
        Check(KnownCode(result.code), "Mutation returned an unknown error code");
    }
    return result;
}

std::uint32_t Next(std::uint32_t& state) { state = state * 1664525u + 1013904223u; return state; }

void Mutations(const Bytes& original, std::uint32_t seed) {
    auto limits = BoundedLimits();
    limits.maximumStringBytes = 4096;
    for (std::size_t trial = 0; trial < 512; ++trial) {
        Bytes bytes = original;
        const auto edits = 1u + Next(seed) % 4u;
        for (std::uint32_t j = 0; j < edits; ++j) {
            const auto offset = static_cast<std::size_t>(Next(seed)) % bytes.size();
            bytes[offset] ^= static_cast<unsigned char>((Next(seed) >> 16) | 1u);
        }
        if (trial % 7 == 0) bytes.resize(static_cast<std::size_t>(Next(seed)) % (bytes.size() + 1));
        const auto first = Probe(bytes, limits);
        const auto second = Probe(bytes, limits);
        Check(first.accepted == second.accepted, "Mutation acceptance was not deterministic");
        if (first.accepted) {
            EqualHeader(first.value, second.value, "Repeated bounded mutation");
            ++counts.acceptedMutations;
        } else {
            Check(first.code == second.code, "Mutation error was not deterministic");
            ++counts.rejectedMutations;
        }
        ++counts.mutations;
    }
}

std::string JsonString(const std::string& value) {
    static const char hex[] = "0123456789abcdef";
    std::string result = "\"";
    for (const char sourceByte : value) {
        const auto byte = static_cast<unsigned char>(sourceByte);
        if (byte == '"' || byte == '\\') { result += '\\'; result += static_cast<char>(byte); }
        else if (byte < 0x20) { result += "\\u00"; result += hex[byte >> 4]; result += hex[byte & 15]; }
        else result += static_cast<char>(byte);
    }
    return result + '"';
}

void Summary(bool success, const std::string& error = {}) {
    std::cout << "{\"status\":\"" << (success ? "PASS_PUBLIC_PREFIX_COMPONENT" : "FAIL_PUBLIC_PREFIX_COMPONENT")
              << "\",\"checks\":" << counts.checks << ",\"fixtures\":" << counts.fixtures
              << ",\"truncations\":" << counts.truncations << ",\"mutations\":" << counts.mutations
              << ",\"accepted_mutations\":" << counts.acceptedMutations
              << ",\"rejected_mutations\":" << counts.rejectedMutations
              << ",\"input_files_unchanged\":" << (success ? "true" : "null")
              << ",\"gamecore_loaded\":false,\"window_created\":false";
    if (!error.empty()) std::cout << ",\"error\":" << JsonString(error);
    std::cout << "}\n";
}
} // namespace

int main(int argc, char** argv) {
    static_assert(sizeof(void*) == 8, "This component must be built for x64");
    try {
        Check(argc == 3, "Expected exactly two explicit immutable public prefix paths");
        const auto public279 = ReadFixture(argv[1]);
        const auto issue8 = ReadFixture(argv[2]);
        Public279(public279);
        PublicIssue8(issue8);
        const auto rich7 = Rich(7), rich8 = Rich(8);
        SyntheticCases(rich7, rich8);
        RejectionCases(rich8);
        Mutations(public279, 0x0b9a1c75u);
        Mutations(issue8, 0x63015e2du);
        Mutations(rich7.bytes, 0x70a5ce1bu);
        Mutations(rich8.bytes, 0x80a5ce1bu);
        Check(ReadFixture(argv[1]) == public279 && ReadFixture(argv[2]) == issue8,
              "Explicit public prefix files changed during the test");
        Check(counts.fixtures == 2 && counts.mutations == 2048, "Incomplete public or mutation coverage");
        Summary(true);
        return 0;
    } catch (const std::exception& error) {
        Summary(false, error.what());
        return 1;
    } catch (...) {
        Summary(false, "Unexpected nonstandard exception");
        return 2;
    }
}
