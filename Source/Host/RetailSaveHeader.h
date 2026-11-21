#pragma once

// Wire-layout reference: bmaupin/js-civ5save at
// 858ce8532725f634e64fa8acaf355aa8e50829bf, first-section property definitions.
// Reference license: RetailSaveHeader.LICENSE.txt.
// This reads a metadata prefix, not the Pregame or compressed SDK state.
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace ZeroSisHost {

enum class RetailSaveHeaderErrorCode {
    NullInput, Truncated, HeaderLimit, StringLimit, RecordLimit,
    Signature, UnsupportedVersion
};

class RetailSaveHeaderError final : public std::invalid_argument {
public:
    RetailSaveHeaderError(RetailSaveHeaderErrorCode code, const char* message)
        : std::invalid_argument(message), code_(code) {}
    RetailSaveHeaderErrorCode Code() const noexcept { return code_; }
private:
    RetailSaveHeaderErrorCode code_;
};

struct RetailSaveHeaderLimits {
    std::size_t maximumHeaderBytes = 16u * 1024u * 1024u;
    std::size_t maximumStringBytes = 1024u * 1024u;
    std::size_t maximumDlcRecords = 4096;
    std::size_t maximumModRecords = 16384;
};

struct RetailSaveDlcRecord {
    // Keep on-disk GUID ordering and the uninterpreted auxiliary word intact.
    std::array<unsigned char, 16> identifier{};
    std::array<unsigned char, 4> auxiliary{};
    std::string name;
};

struct RetailSaveModRecord {
    std::string identifier;
    std::array<unsigned char, 4> auxiliary{};
    std::string name;
};

struct RetailSaveHeader {
    std::uint32_t saveGameVersion = 0;
    std::string gameVersion, gameBuild;
    std::uint32_t currentTurn = 0;
    unsigned char gameMode = 0;
    std::string playerCivilization, difficulty, startingEra, currentEra;
    std::string gamePace, mapSize, mapFile;
    std::vector<RetailSaveDlcRecord> enabledDlc;
    std::vector<RetailSaveModRecord> enabledMods;
    // Only the first metadata section ends here. No compression offset is implied.
    std::size_t consumedPrefixBytes = 0;

    static RetailSaveHeader ParsePrefix(const unsigned char* bytes, std::size_t size,
                                        const RetailSaveHeaderLimits& limits);
    static RetailSaveHeader ParsePrefix(const unsigned char* bytes, std::size_t size) {
        return ParsePrefix(bytes, size, RetailSaveHeaderLimits{});
    }
    static RetailSaveHeader ParsePrefix(const std::vector<unsigned char>& bytes,
                                        const RetailSaveHeaderLimits& limits = RetailSaveHeaderLimits{}) {
        return ParsePrefix(bytes.data(), bytes.size(), limits);
    }
};

namespace RetailSaveHeaderDetail {
class Reader final {
public:
    Reader(const unsigned char* data, std::size_t size, const RetailSaveHeaderLimits& limits)
        : data_(data), size_(size), limits_(limits) {
        if (!data && size)
            Fail(RetailSaveHeaderErrorCode::NullInput, "Null retail save input");
    }
    void Signature() {
        Need(4);
        if (std::memcmp(data_ + position_, "CIV5", 4) != 0)
            Fail(RetailSaveHeaderErrorCode::Signature, "Invalid retail save signature");
        position_ += 4;
    }
    std::uint32_t U32() {
        Need(4);
        const auto* p = data_ + position_;
        const std::uint32_t value = static_cast<std::uint32_t>(p[0]) |
            (static_cast<std::uint32_t>(p[1]) << 8) |
            (static_cast<std::uint32_t>(p[2]) << 16) |
            (static_cast<std::uint32_t>(p[3]) << 24);
        position_ += 4;
        return value;
    }
    unsigned char U8() { Need(1); return data_[position_++]; }
    std::string String() {
        const auto length = U32();
        if (length > limits_.maximumStringBytes)
            Fail(RetailSaveHeaderErrorCode::StringLimit, "Retail save string exceeds its limit");
        Need(length);
        // Preserve raw UTF-8 bytes, including embedded NULs; never scan for terminators.
        const auto* begin = reinterpret_cast<const char*>(data_ + position_);
        std::string result(begin, length);
        position_ += length;
        return result;
    }
    template<std::size_t N> std::array<unsigned char, N> Fixed() {
        Need(N);
        std::array<unsigned char, N> result{};
        std::memcpy(result.data(), data_ + position_, N);
        position_ += N;
        return result;
    }
    std::uint32_t Count(std::size_t limit, std::size_t minimumRecordBytes) {
        const auto count = U32();
        if (count > limit)
            Fail(RetailSaveHeaderErrorCode::RecordLimit, "Retail save list exceeds its limit");
        // Validate before reserve(), without multiplying attacker-controlled lengths.
        if (count > (size_ - position_) / minimumRecordBytes)
            Fail(RetailSaveHeaderErrorCode::Truncated, "Truncated retail save list");
        if (count > (limits_.maximumHeaderBytes - position_) / minimumRecordBytes)
            Fail(RetailSaveHeaderErrorCode::HeaderLimit, "Retail save list exceeds the header budget");
        return count;
    }
    std::size_t Position() const noexcept { return position_; }
private:
    [[noreturn]] static void Fail(RetailSaveHeaderErrorCode code, const char* message) {
        throw RetailSaveHeaderError(code, message);
    }
    void Need(std::size_t count) const {
        if (position_ > size_ || count > size_ - position_)
            Fail(RetailSaveHeaderErrorCode::Truncated, "Truncated retail save header");
        if (position_ > limits_.maximumHeaderBytes || count > limits_.maximumHeaderBytes - position_)
            Fail(RetailSaveHeaderErrorCode::HeaderLimit, "Retail save header exceeds its byte budget");
    }
    const unsigned char* data_;
    const std::size_t size_;
    const RetailSaveHeaderLimits& limits_;
    std::size_t position_ = 0;
};
}

inline RetailSaveHeader RetailSaveHeader::ParsePrefix(const unsigned char* bytes, std::size_t size,
                                                      const RetailSaveHeaderLimits& limits) {
    RetailSaveHeaderDetail::Reader input(bytes, size, limits);
    input.Signature();
    RetailSaveHeader result;
    result.saveGameVersion = input.U32();
    if (result.saveGameVersion != 7 && result.saveGameVersion != 8)
        throw RetailSaveHeaderError(RetailSaveHeaderErrorCode::UnsupportedVersion,
                                   "Unsupported retail save metadata version");
    result.gameVersion = input.String();
    result.gameBuild = input.String();
    result.currentTurn = input.U32();
    result.gameMode = input.U8();
    result.playerCivilization = input.String();
    result.difficulty = input.String();
    result.startingEra = input.String();
    result.currentEra = input.String();
    result.gamePace = input.String();
    result.mapSize = input.String();
    result.mapFile = input.String();
    const auto dlcCount = input.Count(limits.maximumDlcRecords, 24);
    result.enabledDlc.reserve(dlcCount);
    for (std::uint32_t i = 0; i < dlcCount; ++i) {
        RetailSaveDlcRecord record;
        record.identifier = input.Fixed<16>();
        record.auxiliary = input.Fixed<4>();
        record.name = input.String();
        result.enabledDlc.push_back(std::move(record));
    }
    const auto modCount = input.Count(limits.maximumModRecords, 12);
    result.enabledMods.reserve(modCount);
    for (std::uint32_t i = 0; i < modCount; ++i) {
        RetailSaveModRecord record;
        record.identifier = input.String();
        record.auxiliary = input.Fixed<4>();
        record.name = input.String();
        result.enabledMods.push_back(std::move(record));
    }
    result.consumedPrefixBytes = input.Position();
    return result;
}

} // namespace ZeroSisHost
