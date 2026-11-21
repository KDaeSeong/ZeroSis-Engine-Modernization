#pragma once

// Strict preparation of the uncompressed SDK Pregame section only. Every span
// and error offset is relative to the original raw input, not the owned copy.
// No compression descriptor, frame, database lookup or restore is performed.
#include "RetailSavePregame.h"
#include <array>
#include <cstddef>
#include <cstdint>
#include <vector>

namespace ZeroSisHost {

enum class RetailPregameImportErrorCode { InvalidBoolean, InvalidLayout };

class RetailPregameImportError final : public std::invalid_argument {
public:
    RetailPregameImportError(RetailPregameImportErrorCode code, std::size_t offset, const char* message)
        : std::invalid_argument(message), code_(code), offset_(offset) {}
    RetailPregameImportErrorCode Code() const noexcept { return code_; }
    std::size_t RawOffset() const noexcept { return offset_; }
private:
    RetailPregameImportErrorCode code_;
    std::size_t offset_;
};

struct RetailPregameBooleanSite {
    const char* field = nullptr;
    std::size_t rawOffset = 0;
    bool value = false;
};

struct RetailPregameBooleanArray {
    const char* field = nullptr;
    RetailSaveWireSpan payload; // Excludes the uint32 count word.
    std::uint32_t count = 0;
    std::size_t trueCount = 0;
};

struct RetailSavePregameImportInspection {
    RetailSaveHeader metadata;
    RetailSaveWireSpan playerInfo, slotHints, archive, whole;
    std::uint32_t slotHintsVersion = 0, archiveVersion = 0, worldInfoVersion = 0;
    std::int32_t activePlayer = -1, gameTurn = -1, gameType = -1;
    RetailSaveWireSpan networkIds; // Int32 payload only; excludes the uint32 count.
    std::uint32_t networkIdCount = 0;
    std::array<RetailPregameBooleanSite, 17> scalarBooleans{};
    std::array<RetailPregameBooleanArray, 9> booleanArrays{};
    std::size_t arrayRecords = 0, booleanBytesChecked = 0, maximumOptionNameBytes = 0;
    bool optionNameHasEmbeddedNull = false;
};

struct RetailSavePreparedPregame {
    std::vector<unsigned char> bytes; // Exactly wire.whole, without rewriting.
    RetailSavePregameImportInspection wire;
    bool canonicalBooleansChecked = false;
    bool rulesetCompatibilityVerified = false;
    bool restoreApproved = false;
};

namespace RetailPregameImportDetail {

class TypedFields final {
public:
    TypedFields(RetailSavePregameDetail::Reader& reader, const unsigned char* data,
        std::size_t size, RetailSavePregameImportInspection& inspection)
        : reader_(reader), data_(data), size_(size), result_(inspection) {}

    std::int32_t I32() {
        const auto value = reader_.U32();
        return value <= 0x7fffffffu ? static_cast<std::int32_t>(value)
            : -1 - static_cast<std::int32_t>(~value);
    }
    std::int32_t I8() {
        const auto offset = reader_.Position();
        reader_.Skip(1);
        const auto value = data_[offset];
        return value < 128u ? static_cast<std::int32_t>(value)
            : static_cast<std::int32_t>(value) - 256;
    }
    void Bool(const char* field) {
        const auto offset = reader_.Position();
        if (scalarIndex_ >= result_.scalarBooleans.size()) Layout(offset);
        reader_.Skip(1); // Reuse the existing input and prefix bounds checks.
        const auto value = Canonical(offset);
        result_.scalarBooleans[scalarIndex_++] = {field, offset, value};
        ChargeBooleans(1);
    }
    void BoolArray(const char* field) {
        const auto start = reader_.Position();
        if (arrayIndex_ >= result_.booleanArrays.size()) Layout(start);
        reader_.ScalarArray(1); // Charges the existing shared array budget once.
        const auto end = reader_.Position();
        const auto count = BoundedU32(start, end);
        const auto payload = start + 4u;
        if (static_cast<std::size_t>(count) != end - payload) Layout(start);
        std::size_t trueCount = 0;
        for (std::uint32_t i = 0; i < count; ++i)
            if (Canonical(payload + i)) ++trueCount;
        result_.booleanArrays[arrayIndex_++] = {field, {payload, count}, count, trueCount};
        ChargeBooleans(count);
    }
    void NetworkIds() {
        const auto start = reader_.Position();
        reader_.ScalarArray(4);
        const auto end = reader_.Position();
        const auto count = BoundedU32(start, end);
        const auto bytes = end - start;
        if (bytes < 4u || (bytes - 4u) / 4u != count || (bytes - 4u) % 4u) Layout(start);
        result_.networkIds = {start + 4u, bytes - 4u};
        result_.networkIdCount = count;
    }
    void Options() {
        const auto start = reader_.Position();
        reader_.Options(); // Validates every string and charges the option count.
        const auto end = reader_.Position();
        const auto count = BoundedU32(start, end);
        auto cursor = start + 4u;
        for (std::uint32_t i = 0; i < count; ++i) {
            const auto length = BoundedU32(cursor, end);
            cursor += 4u;
            Range(cursor, length, end);
            if (length > result_.maximumOptionNameBytes) result_.maximumOptionNameBytes = length;
            for (std::uint32_t j = 0; j < length; ++j)
                if (data_[cursor + j] == 0) result_.optionNameHasEmbeddedNull = true;
            cursor += length;
            Range(cursor, 4u, end); // CustomOption value is int32, not bool.
            cursor += 4u;
        }
        if (cursor != end) Layout(cursor);
    }
    void Finish() const {
        if (scalarIndex_ != result_.scalarBooleans.size() || arrayIndex_ != result_.booleanArrays.size())
            Layout(reader_.Position());
    }
private:
    [[noreturn]] static void Layout(std::size_t offset) {
        throw RetailPregameImportError(RetailPregameImportErrorCode::InvalidLayout, offset,
            "Invalid typed retail Pregame layout");
    }
    void Range(std::size_t offset, std::size_t bytes, std::size_t end) const {
        if (end > size_ || offset > end || bytes > end - offset) Layout(offset);
    }
    std::uint32_t BoundedU32(std::size_t offset, std::size_t end) const {
        Range(offset, 4u, end);
        const auto* p = data_ + offset;
        return static_cast<std::uint32_t>(p[0]) | (static_cast<std::uint32_t>(p[1]) << 8) |
            (static_cast<std::uint32_t>(p[2]) << 16) | (static_cast<std::uint32_t>(p[3]) << 24);
    }
    bool Canonical(std::size_t offset) const {
        const auto value = data_[offset];
        if (value > 1)
            throw RetailPregameImportError(RetailPregameImportErrorCode::InvalidBoolean, offset,
                "Noncanonical retail Pregame boolean");
        return value != 0;
    }
    void ChargeBooleans(std::size_t count) {
        if (result_.booleanBytesChecked > size_ || count > size_ - result_.booleanBytesChecked)
            Layout(reader_.Position());
        result_.booleanBytesChecked += count;
    }
    RetailSavePregameDetail::Reader& reader_;
    const unsigned char* data_;
    const std::size_t size_;
    RetailSavePregameImportInspection& result_;
    std::size_t scalarIndex_ = 0, arrayIndex_ = 0;
};

inline RetailSavePregameImportInspection Inspect(const unsigned char* data, std::size_t size,
    const RetailSavePregameLimits& limits) {
    auto metadataLimits = limits.metadata;
    metadataLimits.maximumHeaderBytes = (std::min)(metadataLimits.maximumHeaderBytes, limits.maximumPrefixBytes);
    metadataLimits.maximumStringBytes = (std::min)(metadataLimits.maximumStringBytes, limits.maximumStringBytes);
    RetailSavePregameImportInspection result;
    result.metadata = RetailSaveHeader::ParsePrefix(data, size, metadataLimits);
    RetailSavePregameDetail::Reader r(data, size, result.metadata.consumedPrefixBytes, limits);
    TypedFields typed(r, data, size, result);

    result.playerInfo.offset = r.Position();
    r.Strings(3); r.Skip(16); r.String(); r.Skip(20);
    result.playerInfo.bytes = r.Position() - result.playerInfo.offset;
    result.slotHints.offset = r.Position();
    result.slotHintsVersion = r.U32();
    if (result.slotHintsVersion != 3)
        throw RetailSavePregameError(RetailSavePregameErrorCode::UnsupportedSlotHintsVersion,
            "Unsupported retail slot-hints layout");
    r.Skip(8); r.String(); r.ScalarArray(4); r.StringArray();
    for (unsigned i = 0; i < 4; ++i) r.ScalarArray(4);
    r.StringArray(); r.StringArray();
    result.slotHints.bytes = r.Position() - result.slotHints.offset;

    // CvPreGame::writeArchive v6, in its exact serializer order.
    result.archive.offset = r.Position();
    result.archiveVersion = r.U32();
    if (result.archiveVersion != 6)
        throw RetailSavePregameError(RetailSavePregameErrorCode::UnsupportedPregameVersion,
            "Unsupported retail Pregame archive layout");
    result.activePlayer = typed.I32(); r.String(); r.Skip(4); r.String(); r.ScalarArray(4);
    typed.Bool("s_autorun"); r.Skip(4 * 4); r.BaseInfo();
    for (unsigned i = 0; i < 4; ++i) r.StringArray();
    r.Skip(4); r.BaseInfo(); r.Skip(11 * 4);
    r.Skip(4); r.StringArray(); r.Skip(4); r.StringArray();
    typed.BoolArray("s_DEPRECATEDforceControls"); r.Skip(4); r.String();
    r.Skip(4); typed.Bool("s_gameStarted"); result.gameTurn = typed.I32();
    result.gameType = typed.I8(); r.Skip(8); // GameMapTypes and game update time.
    r.ScalarArray(4); r.ScalarArray(4);
    typed.Bool("s_isEarthMap"); typed.Bool("s_isInternetGame"); r.StringArray();
    r.Strings(2); typed.Bool("s_mapNoPlayers"); r.Skip(4);
    typed.Bool("s_loadWBScenario"); typed.Bool("s_overrideScenarioHandicap"); r.String();
    r.Skip(12); r.StringArray(); // Minor-civilization keys, not numeric enums.
    typed.BoolArray("s_minorNationCivs"); typed.Bool("s_dummyvalue");
    typed.BoolArray("s_multiplayerOptions"); typed.NetworkIds(); r.StringArray(); r.Skip(8);
    typed.BoolArray("s_playableCivs"); r.StringArray(); // Player-color keys.
    typed.Bool("s_privateGame"); typed.Bool("s_quickCombat"); typed.Bool("s_quickCombatDefault"); r.Skip(4);
    typed.Bool("s_quickstart"); typed.Bool("s_randomWorldSize"); typed.Bool("s_randomMapScript");
    typed.BoolArray("s_readyPlayers"); r.Skip(4); r.BaseInfo(); r.Skip(4);
    typed.Bool("s_dummyvalue2"); r.ScalarArray(4); r.ScalarArray(4);
    r.String(); r.Skip(8); r.ScalarArray(4); typed.Bool("s_transferredMap");
    r.BaseInfo(); r.Skip(4 * 4 + 4); typed.Bool("s_bCityScreenBlocked");
    typed.BoolArray("s_victories"); typed.BoolArray("s_whiteFlags");
    result.worldInfoVersion = r.U32();
    if (result.worldInfoVersion != 1 && result.worldInfoVersion != 2)
        throw RetailSavePregameError(RetailSavePregameErrorCode::UnsupportedWorldInfoVersion,
            "Unsupported retail world-info layout");
    r.BaseInfo(); r.Skip((result.worldInfoVersion == 2 ? 19u : 18u) * 4u);
    r.Skip(4); typed.Options(); typed.Options(); r.String();
    typed.BoolArray("s_turnNotifySteamInvite"); typed.BoolArray("s_turnNotifyEmail"); r.StringArray();
    typed.Finish();
    result.archive.bytes = r.Position() - result.archive.offset;
    result.whole = {result.slotHints.offset, r.Position() - result.slotHints.offset};
    result.arrayRecords = r.Records();
    return result; // Compression format and first frame length remain unread.
}
} // namespace RetailPregameImportDetail

class RetailSavePregameImport {
public:
    static RetailSavePreparedPregame Prepare(const unsigned char* data, std::size_t size,
        const RetailSavePregameLimits& limits = RetailSavePregameLimits{}) {
        RetailSavePreparedPregame result;
        result.wire = RetailPregameImportDetail::Inspect(data, size, limits);
        const auto& whole = result.wire.whole;
        if (whole.offset > size || !whole.bytes || whole.bytes > size - whole.offset)
            throw RetailPregameImportError(RetailPregameImportErrorCode::InvalidLayout, whole.offset,
                "Invalid prepared retail Pregame span");
        // No caller-owned output is mutated if validation or allocation fails.
        result.bytes.assign(data + whole.offset, data + whole.offset + whole.bytes);
        result.canonicalBooleansChecked = true;
        return result;
    }
};
} // namespace ZeroSisHost
