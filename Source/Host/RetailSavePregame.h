#pragma once

// Retail prefix framing references: active BNW CvPreGame/CvInfos serializers,
// and samuelyuan/Civ5MapImage 4ecadf1b4ac656cc113ee2d8da64ce8c85db9d29.
// Reference notice: RetailSavePregame.LICENSE.txt.
// This locates a supported uncompressed prefix. It does not validate, inflate,
// restore or write the compressed state, and must not be used as a load approval.
#include "RetailSaveHeader.h"
#include <algorithm>

namespace ZeroSisHost {

enum class RetailSavePregameErrorCode {
    Truncated, PrefixLimit, StringLimit, RecordLimit,
    UnsupportedSlotHintsVersion, UnsupportedPregameVersion,
    UnsupportedWorldInfoVersion, UnsupportedCompressionFormat, UnsupportedChunkSize
};

class RetailSavePregameError final : public std::invalid_argument {
public:
    RetailSavePregameError(RetailSavePregameErrorCode code, const char* message)
        : std::invalid_argument(message), code_(code) {}
    RetailSavePregameErrorCode Code() const noexcept { return code_; }
private:
    RetailSavePregameErrorCode code_;
};

struct RetailSavePregameLimits {
    RetailSaveHeaderLimits metadata;
    std::size_t maximumPrefixBytes = 16u * 1024u * 1024u;
    std::size_t maximumStringBytes = 1024u * 1024u;
    std::size_t maximumArrayRecords = 16384;
    std::size_t maximumTotalArrayRecords = 262144;
};

// Offsets into the caller's original input; no borrowed pointer or copied body.
struct RetailSaveWireSpan {
    std::size_t offset = 0;
    std::size_t bytes = 0;
};

struct RetailSavePregame {
    RetailSaveHeader metadata;
    RetailSaveWireSpan playerInfo, slotHints, archive, compressionHeader;
    std::uint32_t slotHintsVersion = 0, archiveVersion = 0, worldInfoVersion = 0;
    std::uint32_t compressionFormatId = 0, compressionChunkSize = 0;
    std::size_t compressedDataOffset = 0;
    std::size_t arrayRecords = 0;

    // Metadata parse errors retain their RetailSaveHeaderError type.
    static RetailSavePregame ParsePrefix(const unsigned char* bytes, std::size_t size,
                                         const RetailSavePregameLimits& limits);
    static RetailSavePregame ParsePrefix(const unsigned char* bytes, std::size_t size) {
        return ParsePrefix(bytes, size, RetailSavePregameLimits{});
    }
    static RetailSavePregame ParsePrefix(const std::vector<unsigned char>& bytes,
                                         const RetailSavePregameLimits& limits = RetailSavePregameLimits{}) {
        return ParsePrefix(bytes.data(), bytes.size(), limits);
    }
};

namespace RetailSavePregameDetail {
class Reader {
public:
    Reader(const unsigned char* bytes, std::size_t size, std::size_t offset,
           const RetailSavePregameLimits& limits)
        : data_(bytes), size_(size), at_(offset), limits_(limits) { Need(0); }
    void Skip(std::size_t bytes) { Need(bytes); at_ += bytes; }
    std::uint32_t U32() {
        Need(4);
        const auto* p = data_ + at_;
        at_ += 4;
        return static_cast<std::uint32_t>(p[0]) |
            (static_cast<std::uint32_t>(p[1]) << 8) |
            (static_cast<std::uint32_t>(p[2]) << 16) |
            (static_cast<std::uint32_t>(p[3]) << 24);
    }
    void String() {
        const auto length = U32();
        if (length > limits_.maximumStringBytes)
            Fail(RetailSavePregameErrorCode::StringLimit, "Retail Pregame string exceeds its limit");
        Skip(length);
    }
    void Strings(std::size_t count) { for (std::size_t i = 0; i < count; ++i) String(); }
    void ScalarArray(std::size_t width) {
        const auto count = Count(width);
        // Count checked the product against both remaining byte budgets.
        Skip(static_cast<std::size_t>(count) * width);
    }
    void StringArray() {
        const auto count = Count(4);
        Strings(count);
    }
    void Options() {
        const auto count = Count(8);
        for (std::uint32_t i = 0; i < count; ++i) { String(); Skip(4); }
    }
    void BaseInfo() { Skip(4); Strings(8); }
    std::size_t Position() const noexcept { return at_; }
    std::size_t Records() const noexcept { return records_; }
private:
    [[noreturn]] static void Fail(RetailSavePregameErrorCode code, const char* message) {
        throw RetailSavePregameError(code, message);
    }
    void Need(std::size_t bytes) const {
        if (at_ > size_ || bytes > size_ - at_)
            Fail(RetailSavePregameErrorCode::Truncated, "Truncated retail Pregame prefix");
        if (at_ > limits_.maximumPrefixBytes || bytes > limits_.maximumPrefixBytes - at_)
            Fail(RetailSavePregameErrorCode::PrefixLimit, "Retail Pregame prefix exceeds its byte budget");
    }
    std::uint32_t Count(std::size_t width) {
        const auto count = U32();
        if (count > limits_.maximumArrayRecords ||
            count > limits_.maximumTotalArrayRecords - records_)
            Fail(RetailSavePregameErrorCode::RecordLimit, "Retail Pregame array exceeds its record budget");
        if (count > (size_ - at_) / width)
            Fail(RetailSavePregameErrorCode::Truncated, "Truncated retail Pregame array");
        if (count > (limits_.maximumPrefixBytes - at_) / width)
            Fail(RetailSavePregameErrorCode::PrefixLimit, "Retail Pregame array exceeds the prefix budget");
        records_ += count;
        return count;
    }
    const unsigned char* data_;
    const std::size_t size_;
    std::size_t at_, records_ = 0;
    const RetailSavePregameLimits& limits_;
};
}

inline RetailSavePregame RetailSavePregame::ParsePrefix(const unsigned char* bytes, std::size_t size,
                                                       const RetailSavePregameLimits& limits) {
    auto metadataLimits = limits.metadata;
    metadataLimits.maximumHeaderBytes = (std::min)(metadataLimits.maximumHeaderBytes, limits.maximumPrefixBytes);
    metadataLimits.maximumStringBytes = (std::min)(metadataLimits.maximumStringBytes, limits.maximumStringBytes);
    RetailSavePregame result;
    result.metadata = RetailSaveHeader::ParsePrefix(bytes, size, metadataLimits);
    RetailSavePregameDetail::Reader r(bytes, size, result.metadata.consumedPrefixBytes, limits);

    result.playerInfo.offset = r.Position();
    r.Strings(3);                         // civilization name, leader name, color key
    r.Skip(16); r.String(); r.Skip(20);   // opaque IDs, version string, opaque word
    result.playerInfo.bytes = r.Position() - result.playerInfo.offset;

    result.slotHints.offset = r.Position();
    result.slotHintsVersion = r.U32();
    if (result.slotHintsVersion != 3)
        throw RetailSavePregameError(RetailSavePregameErrorCode::UnsupportedSlotHintsVersion,
                                     "Unsupported retail slot-hints layout");
    r.Skip(8); r.String();                // speed, size, map script
    r.ScalarArray(4); r.StringArray();    // civilizations, nicknames
    for (unsigned int i = 0; i < 4; ++i) r.ScalarArray(4); // status, claims, teams, handicaps
    r.StringArray(); r.StringArray();     // civilization and leader keys
    result.slotHints.bytes = r.Position() - result.slotHints.offset;

    result.archive.offset = r.Position();
    result.archiveVersion = r.U32();
    if (result.archiveVersion != 6)
        throw RetailSavePregameError(RetailSavePregameErrorCode::UnsupportedPregameVersion,
                                     "Unsupported retail Pregame archive layout");
    r.Skip(4); r.String(); r.Skip(4); r.String(); // active player, admin password, start points, alias
    r.ScalarArray(4);                     // art styles
    r.Skip(1 + 4 + 4 + 4 + 4);           // autorun, delay, limit, bandwidth, calendar
    r.BaseInfo();                        // calendar info (all strings are length-prefixed)
    for (unsigned int i = 0; i < 4; ++i) r.StringArray(); // civilization identity/passwords
    r.Skip(4); r.BaseInfo(); r.Skip(11 * 4); // climate and eleven int/float words
    r.Skip(4); r.StringArray(); r.Skip(4); r.StringArray(); // era, emails, timer, decals
    r.ScalarArray(1); r.Skip(4); r.String(); // deprecated controls, game mode/name
    // The original utility-library conformance uses a one-byte GameTypes and
    // four-byte GameMapTypes. C++ enum declarations alone do not prove width.
    r.Skip(4 + 1 + 4 + 1 + 4 + 4);      // speed, started, turn, game/map type, update time
    r.ScalarArray(4); r.ScalarArray(4);   // handicaps, last human handicaps
    r.Skip(2); r.StringArray();          // Earth/Internet flags, leader names
    r.Strings(2); r.Skip(1 + 4 + 1 + 1); r.String(); // scenario and map setup
    r.Skip(12); r.StringArray();         // max city elimination, max turns, minors, minor keys
    r.ScalarArray(1); r.Skip(1); r.ScalarArray(1); // minor nation, dummy, multiplayer options
    r.ScalarArray(4); r.StringArray(); r.Skip(8); // net IDs, nicknames, victories, pitboss timer
    r.ScalarArray(1); r.StringArray();    // playable flags and player color keys
    r.Skip(3 + 4 + 3); r.ScalarArray(1); // quick/private/random flags, handicap, ready flags
    r.Skip(4); r.BaseInfo(); r.Skip(4 + 1); // sea level, info, change, dummy
    r.ScalarArray(4); r.ScalarArray(4);   // slot claims/status
    r.String(); r.Skip(8); r.ScalarArray(4); r.Skip(1); // SMTP, random seed, score, teams, transferred
    r.BaseInfo(); r.Skip(4 * 4 + 4 + 1); // timer info, timer enum, city-screen flag
    r.ScalarArray(1); r.ScalarArray(1);   // victory and white flags
    result.worldInfoVersion = r.U32();
    if (result.worldInfoVersion != 1 && result.worldInfoVersion != 2)
        throw RetailSavePregameError(RetailSavePregameErrorCode::UnsupportedWorldInfoVersion,
                                     "Unsupported retail world-info layout");
    r.BaseInfo();
    r.Skip((result.worldInfoVersion == 2 ? 19u : 18u) * 4); // CvWorldInfo scalar fields
    r.Skip(4); r.Options(); r.Options(); r.String(); // world size, game/map options, version
    r.ScalarArray(1); r.ScalarArray(1); r.StringArray(); // turn notifications
    result.archive.bytes = r.Position() - result.archive.offset;

    result.compressionHeader.offset = r.Position();
    result.compressionFormatId = r.U32();
    result.compressionChunkSize = r.U32();
    if (result.compressionFormatId != 1 && result.compressionFormatId != 2)
        throw RetailSavePregameError(RetailSavePregameErrorCode::UnsupportedCompressionFormat,
                                     "Unsupported retail compression format descriptor");
    if (result.compressionChunkSize != 65536)
        throw RetailSavePregameError(RetailSavePregameErrorCode::UnsupportedChunkSize,
                                     "Unsupported retail compression chunk-size descriptor");
    result.compressionHeader.bytes = r.Position() - result.compressionHeader.offset;
    result.compressedDataOffset = r.Position();
    result.arrayRecords = r.Records();
    return result;
}

} // namespace ZeroSisHost
