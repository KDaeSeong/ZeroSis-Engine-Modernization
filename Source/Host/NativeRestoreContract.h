#pragma once

// Exact single-player CvGame::Read effects, with the current release writer.
// This is an in-memory contract, not an SDK loader or retail-save converter.
#include "NativeSaveEnvelope.h"
#include "RetailSaveGameFront.h"
#include "RetailSaveGameTail.h"
#include <algorithm>
#include <cstdint>
#include <string>

namespace ZeroSisHost {

using NativeRestoreGameLayout = RetailStateDetail::GameFrontReloadLayout;

class NativeRestoreContract final {
public:
    static NativeRestoreGameLayout InspectGame(const std::vector<unsigned char>& bytes,
        const RetailSaveStateProfile& profile, const RetailSaveStateLimits& limits = RetailSaveStateLimits{}) {
        RetailStateDetail::Reader reader(bytes.data(), bytes.size(), limits);
        if (profile.victoryPointAwards > 4096)
            reader.Fail(RetailStateErrorCode::UnsupportedProfile, "Native restore victory width exceeds its budget");
        NativeRestoreGameLayout result;
        RetailStateDetail::ReadGameFront(reader, profile, &result);
        RetailStateDetail::ReadGameTail(reader);
        const auto databaseBytes = reader.U32();
        if (databaseBytes > limits.maxEmbeddedDatabaseBytes)
            reader.Fail(RetailStateErrorCode::EmbeddedDatabaseLimit, "Native embedded database exceeds its budget");
        reader.Skip(databaseBytes);
        if (reader.Pos() != bytes.size())
            reader.Fail(RetailStateErrorCode::InvalidValue, "Native Game section has trailing bytes");
        return result;
    }

    static NativeRestoreGameLayout PreflightGame(const std::vector<unsigned char>& bytes,
        const RetailSaveStateProfile& profile, const RetailSaveStateLimits& limits = RetailSaveStateLimits{}) {
        const auto result = InspectGame(bytes, profile, limits);
        // CvGame::Read increments this signed field. Reject overflow before any
        // SDK read, not after a corrupted recapture has already been produced.
        Require(result.sessions >= 1 && result.sessions < INT_MAX,
                "Native restore session count cannot be incremented safely");
        Require(result.replayMessages < static_cast<std::uint32_t>(INT_MAX),
                "Native restore replay count cannot be incremented safely");
        AdvisorValues(bytes, result.advisorMessages, limits);
        return result;
    }

    static unsigned Verify(const NativeSaveEnvelope& before, const NativeSaveEnvelope& after,
        const RetailSaveStateProfile& profile, bool newRandomSeed, const std::string& expectedReloadText,
        const RetailSaveStateLimits& limits = RetailSaveStateLimits{}) {
        before.Validate(); after.Validate();
        Require(ValidUtf8(expectedReloadText), "Native restore reload text is not valid UTF-8");
        Require(after.flags == 0 && before.turn == after.turn && before.elapsed == after.elapsed &&
                before.activePlayer == after.activePlayer, "Native restore changed the archive identity");
        for (std::size_t i = 0; i < before.sections.size(); ++i) {
            const auto& old = before.sections[i]; const auto& current = after.sections[i];
            Require(old.kind == current.kind && old.index == current.index,
                    "Native restore changed a section identity");
            if (old.kind != NativeSaveEnvelope::Game)
                Require(old.bytes == current.bytes, "Native restore changed a non-game section");
        }
        const auto& old = before.sections[2].bytes;
        const auto& current = after.sections[2].bytes;
        const auto source = PreflightGame(old, profile, limits);
        const auto target = InspectGame(current, profile, limits);
        Require(source.replayCountOffset == target.replayCountOffset &&
                source.replayRecords.offset == target.replayRecords.offset &&
                target.replayMessages == source.replayMessages + 1u &&
                target.sessions == source.sessions + 1,
                "Native restore did not add exactly one replay entry and session");
        Require(source.aiAutoPlayOffset == target.aiAutoPlayOffset && source.gameStateOffset == target.gameStateOffset &&
                source.advisorMessages.offset == target.advisorMessages.offset &&
                source.advisorMessages.bytes == target.advisorMessages.bytes &&
                source.jonRandom.seedOffset == target.jonRandom.seedOffset &&
                source.jonRandom.resetCountOffset == target.jonRandom.resetCountOffset &&
                target.aiAutoPlay == (source.aiAutoPlay > 0 ? 1 : source.aiAutoPlay) &&
                target.gameState == (source.gameState == 1 ? 2 : source.gameState),
                "Native restore game-state normalization differs from CvGame::Read");
        const auto oldAdvisors = AdvisorValues(old, source.advisorMessages, limits);
        const auto newAdvisors = AdvisorValues(current, target.advisorMessages, limits);
        Require(oldAdvisors.size() == newAdvisors.size(), "Native restore changed the advisor message set");
        for (std::size_t i = 0; i < oldAdvisors.size(); ++i)
            Require(oldAdvisors[i].bytes == newAdvisors[i].bytes &&
                    Equal(old, oldAdvisors[i].offset, oldAdvisors[i].bytes, current, newAdvisors[i].offset),
                    "Native restore changed an advisor message");
        if (newRandomSeed) {
            // CvRandom::reseed changes only seed/reset count in the release
            // stream. Call count is preserved; unsigned reset count wraps.
            Require(target.jonRandom.calls == source.jonRandom.calls &&
                    target.jonRandom.resets == static_cast<std::uint32_t>(source.jonRandom.resets + 1u),
                    "Native restore RNG reseed counters differ");
        }
        for (std::size_t i = 0; i < source.replayCountOffset; ++i) {
            const bool normalized = Inside(i, source.aiAutoPlayOffset, 4) || Inside(i, source.gameStateOffset, 4) ||
                                    Inside(i, source.advisorMessages.offset, source.advisorMessages.bytes);
            const bool reseeded = newRandomSeed && (Inside(i, source.jonRandom.seedOffset, 4) ||
                                                   Inside(i, source.jonRandom.resetCountOffset, 4));
            Require(normalized || reseeded || old[i] == current[i],
                    "Native restore changed bytes before its replay count");
        }
        Require(Equal(old, source.replayRecords.offset, source.replayRecords.bytes,
                      current, target.replayRecords.offset), "Native restore changed an existing replay entry");
        const auto appended = target.replayRecords.offset + source.replayRecords.bytes;
        Require(appended <= target.sessionOffset && source.replayRecords.offset + source.replayRecords.bytes ==
                source.sessionOffset, "Native restore replay boundaries differ");
        RetailStateDetail::Reader message(current.data(), current.size(), limits);
        message.Skip(appended);
        Require(message.I32() == before.turn && message.I32() == 0,
                "Native restore replay event has the wrong turn or type");
        Require(message.SignedCount(4) == 1 && message.U32() == 0xffffffffu &&
                message.I32() == before.activePlayer, "Native restore replay event has the wrong plot or player");
        const auto text = message.String();
        Require(text.bytes == expectedReloadText.size() &&
                std::equal(expectedReloadText.begin(), expectedReloadText.end(), current.begin() + text.offset,
                    [](char a, unsigned char b) { return static_cast<unsigned char>(a) == b; }) &&
                message.Pos() == target.sessionOffset, "Native restore replay text or size differs");
        const auto oldSuffix = source.sessionOffset + 4u, newSuffix = target.sessionOffset + 4u;
        Require(old.size() - oldSuffix == current.size() - newSuffix &&
                Equal(old, oldSuffix, old.size() - oldSuffix, current, newSuffix),
                "Native restore changed bytes after its session counter");
        return NativeSaveEnvelope::SectionCount() - 1u;
    }

private:
    static std::vector<RetailInflatedSpan> AdvisorValues(const std::vector<unsigned char>& bytes,
        RetailInflatedSpan span, const RetailSaveStateLimits& limits) {
        RetailStateDetail::Reader reader(bytes.data(), bytes.size(), limits);
        reader.Skip(span.offset);
        const auto count = reader.Count(4);
        std::vector<RetailInflatedSpan> values;
        values.reserve(count);
        for (std::uint32_t i = 0; i < count; ++i) values.push_back(reader.String());
        Require(reader.Pos() - span.offset == span.bytes, "Native advisor message set boundary differs");
        const auto less = [&bytes](RetailInflatedSpan a, RetailInflatedSpan b) {
            return std::lexicographical_compare(bytes.begin() + a.offset, bytes.begin() + a.offset + a.bytes,
                                               bytes.begin() + b.offset, bytes.begin() + b.offset + b.bytes);
        };
        std::sort(values.begin(), values.end(), less);
        for (std::size_t i = 1; i < values.size(); ++i)
            Require(values[i - 1].bytes != values[i].bytes ||
                    !Equal(bytes, values[i - 1].offset, values[i - 1].bytes, bytes, values[i].offset),
                    "Native advisor message set contains a duplicate");
        return values;
    }
    static bool ValidUtf8(const std::string& text) noexcept {
        std::size_t cursor = 0;
        while (cursor < text.size()) {
            const auto first = static_cast<unsigned char>(text[cursor++]);
            if (first < 0x80) {
                if (first == 0) return false; // The SDK supplies a C string.
                continue;
            }
            unsigned trailing = 0;
            std::uint32_t value = 0, minimum = 0;
            if (first >= 0xc2 && first <= 0xdf) { trailing = 1; value = first & 0x1fu; minimum = 0x80; }
            else if (first >= 0xe0 && first <= 0xef) { trailing = 2; value = first & 0x0fu; minimum = 0x800; }
            else if (first >= 0xf0 && first <= 0xf4) { trailing = 3; value = first & 0x07u; minimum = 0x10000; }
            else return false;
            if (trailing > text.size() - cursor) return false;
            for (unsigned i = 0; i < trailing; ++i) {
                const auto next = static_cast<unsigned char>(text[cursor++]);
                if ((next & 0xc0u) != 0x80u) return false;
                value = (value << 6) | (next & 0x3fu);
            }
            if (value < minimum || value > 0x10ffffu || (value >= 0xd800 && value <= 0xdfff)) return false;
        }
        return true;
    }
    static void Require(bool condition, const char* message) {
        if (!condition) throw std::invalid_argument(message);
    }
    static bool Inside(std::size_t position, std::size_t offset, std::size_t bytes) noexcept {
        return position >= offset && position - offset < bytes;
    }
    static bool Equal(const std::vector<unsigned char>& left, std::size_t offset, std::size_t size,
                      const std::vector<unsigned char>& right, std::size_t target) {
        return offset <= left.size() && size <= left.size() - offset && target <= right.size() &&
            size <= right.size() - target && std::equal(left.begin() + offset, left.begin() + offset + size,
                                                       right.begin() + target);
    }
};
} // namespace ZeroSisHost
