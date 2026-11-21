#pragma once

// Portable, allocation-free framing for an already inflated BNW state stream.
// No SDK calls, file access, type-hash resolution or restore approval occurs here.
#include <cstddef>
#include <cstdint>
#include <stdexcept>

namespace ZeroSisHost {

enum class RetailStateErrorCode {
    NullInput, Truncated, InputLimit, PrefixLimit, StringLimit, ArrayLimit,
    TotalRecordLimit, EmbeddedDatabaseLimit, MapPlotLimit, UnsupportedVersion,
    UnsupportedProfile, InvalidValue
};

class RetailStateError final : public std::runtime_error {
public:
    RetailStateError(RetailStateErrorCode code, std::size_t offset, const char* message)
        : std::runtime_error(message), code_(code), offset_(offset) {}
    RetailStateErrorCode Code() const noexcept { return code_; }
    std::size_t Offset() const noexcept { return offset_; }
private:
    RetailStateErrorCode code_;
    std::size_t offset_;
};

// These offsets refer only to the caller's inflated bytes. They are not retail
// file offsets and cannot be combined with RetailSaveWireSpan without decoding.
struct RetailInflatedSpan {
    std::size_t offset = 0;
    std::size_t bytes = 0;
};

enum class RetailBooleanWireProfile {
    CanonicalZeroOne,
    SdkRawByte
};

struct RetailSaveStateLimits {
    std::size_t maxInputBytes = 64u * 1024u * 1024u;
    std::size_t maxPrefixBytes = 64u * 1024u * 1024u;
    std::size_t maxStringBytes = 1024u * 1024u;
    std::size_t maxArrayRecords = 1024u * 1024u;
    std::size_t maxTotalRecords = 1024u * 1024u;
    std::size_t maxEmbeddedDatabaseBytes = 64u * 1024u * 1024u;
    std::size_t maxMapPlots = 1024u * 1024u;
    // The retained Win32 SDK bool codec transfers one raw byte. Opt in
    // explicitly; existing inspectors retain canonical 0/1 validation.
    RetailBooleanWireProfile booleanWireProfile = RetailBooleanWireProfile::CanonicalZeroOne;
};

struct RetailSaveStateProfile {
    // The inner victory array width is NOT on the wire. CvGlobals loads this
    // value from NUM_VICTORY_POINT_AWARDS; five is not a universal mod default.
    explicit RetailSaveStateProfile(std::uint32_t awards) : victoryPointAwards(awards) {}
    std::uint32_t victoryPointAwards;
};

namespace RetailStateDetail {
class Reader {
public:
    Reader(const unsigned char* data, std::size_t size, const RetailSaveStateLimits& limits)
        : data_(data), size_(size), limits_(limits) {
        if (limits_.booleanWireProfile != RetailBooleanWireProfile::CanonicalZeroOne &&
            limits_.booleanWireProfile != RetailBooleanWireProfile::SdkRawByte)
            Fail(RetailStateErrorCode::UnsupportedProfile, "Unsupported BNW boolean wire profile");
        if (!data_ && size_) Fail(RetailStateErrorCode::NullInput, "Null inflated state input");
        if (size_ > limits_.maxInputBytes)
            Fail(RetailStateErrorCode::InputLimit, "Inflated state exceeds input budget");
    }
    std::size_t Pos() const noexcept { return pos_; }
    std::size_t Records() const noexcept { return records_; }
    [[noreturn]] void Fail(RetailStateErrorCode code, const char* message) const {
        throw RetailStateError(code, pos_, message);
    }
    void Skip(std::size_t bytes) { Need(bytes); pos_ += bytes; }
    void Fixed(std::size_t count, std::size_t width) {
        NeedProduct(count, width);
        pos_ += count * width;
    }
    std::uint32_t U32() {
        Need(4);
        const auto* p = data_ + pos_;
        pos_ += 4;
        return static_cast<std::uint32_t>(p[0]) |
            (static_cast<std::uint32_t>(p[1]) << 8) |
            (static_cast<std::uint32_t>(p[2]) << 16) |
            (static_cast<std::uint32_t>(p[3]) << 24);
    }
    std::int32_t I32() {
        const auto value = U32();
        return value <= 0x7fffffffu ? static_cast<std::int32_t>(value)
            : -1 - static_cast<std::int32_t>(~value);
    }
    bool Bool() {
        Need(1);
        const auto value = data_[pos_++];
        if (limits_.booleanWireProfile == RetailBooleanWireProfile::CanonicalZeroOne && value > 1)
            Fail(RetailStateErrorCode::InvalidValue, "Invalid serialized bool");
        return value != 0;
    }
    void Version(std::uint32_t expected) {
        if (U32() != expected)
            Fail(RetailStateErrorCode::UnsupportedVersion, "Unsupported BNW record version");
    }
    std::uint32_t Count(std::size_t minimumRecordBytes) {
        const auto count = U32();
        CheckCount(count, minimumRecordBytes);
        return count;
    }
    std::uint32_t SignedCount(std::size_t minimumRecordBytes) {
        const auto count = I32();
        if (count < 0) Fail(RetailStateErrorCode::InvalidValue, "Negative BNW record count");
        CheckCount(static_cast<std::uint32_t>(count), minimumRecordBytes);
        return static_cast<std::uint32_t>(count);
    }
    RetailInflatedSpan String() {
        const auto length = U32();
        if (length > limits_.maxStringBytes)
            Fail(RetailStateErrorCode::StringLimit, "BNW string exceeds byte budget");
        const auto start = Pos();
        Skip(length);
        return SpanFrom(start);
    }
    void Strings() {
        const auto count = Count(4);
        for (std::uint32_t i = 0; i < count; ++i) String();
    }
    void Hashes(std::size_t valueBytes) {
        const auto count = Count(4);
        for (std::uint32_t i = 0; i < count; ++i)
            if (U32() != 0) Skip(valueBytes);
    }
    RetailInflatedSpan SpanFrom(std::size_t start) const {
        if (start > pos_) Fail(RetailStateErrorCode::InvalidValue, "Invalid inflated span start");
        return {start, pos_ - start};
    }
private:
    void Need(std::size_t bytes) const {
        if (pos_ > size_ || bytes > size_ - pos_)
            Fail(RetailStateErrorCode::Truncated, "Truncated inflated BNW state");
        if (pos_ > limits_.maxPrefixBytes || bytes > limits_.maxPrefixBytes - pos_)
            Fail(RetailStateErrorCode::PrefixLimit, "BNW state prefix exceeds byte budget");
    }
    void NeedProduct(std::size_t count, std::size_t width) const {
        Need(0);
        if (!width) return;
        if (count > (size_ - pos_) / width)
            Fail(RetailStateErrorCode::Truncated, "Truncated inflated BNW array");
        if (count > (limits_.maxPrefixBytes - pos_) / width)
            Fail(RetailStateErrorCode::PrefixLimit, "BNW array exceeds prefix budget");
    }
    void CheckCount(std::uint32_t count, std::size_t minimumRecordBytes) {
        if (count > limits_.maxArrayRecords)
            Fail(RetailStateErrorCode::ArrayLimit, "BNW array exceeds record limit");
        if (records_ > limits_.maxTotalRecords || count > limits_.maxTotalRecords - records_)
            Fail(RetailStateErrorCode::TotalRecordLimit, "BNW state exceeds total record budget");
        NeedProduct(count, minimumRecordBytes);
        records_ += count;
    }
    const unsigned char* data_;
    const std::size_t size_;
    const RetailSaveStateLimits limits_;
    std::size_t pos_ = 0, records_ = 0;
};
} // namespace RetailStateDetail
} // namespace ZeroSisHost
