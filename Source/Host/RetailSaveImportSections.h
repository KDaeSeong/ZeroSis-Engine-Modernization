#pragma once

// Prepare owned payloads in the native reader's order without creating a save
// envelope, assigning a bundle identity or entering the SDK. The caller must
// still establish compressed-body provenance, ruleset identity and load safety.
#include "RetailSaveBodyImport.h"
#include "RetailSavePregameImport.h"
#include <array>
#include <cstddef>
#include <cstdint>
#include <limits>

namespace ZeroSisHost {

enum class RetailImportStorage { Pregame, Body };

struct RetailImportSectionSpan {
    // NativeSaveArchive kinds 2..7; Bundle (kind 1) remains deliberately absent.
    unsigned kind = 0, index = 0;
    RetailImportStorage storage = RetailImportStorage::Body;
    RetailInflatedSpan span;
};

struct RetailSaveImportPreparation {
    RetailSavePreparedPregame pregame;
    RetailSavePreparedBody body;
    // Pregame + Game/Map/Supporting + 64 Teams + 64 Players. Adding a verified
    // Bundle later would give the native format's 133 sections, not 132.
    std::array<RetailImportSectionSpan, 132> sections{};
    std::int32_t turn = 0, elapsed = 0, activePlayer = -1;
    std::size_t totalPayloadBytes = 0;
    bool retailHeaderTurnMatches = false;
    bool offlineTransportUnassigned = false;
    bool compressedBodyAssociationVerified = false;
    bool bundleIdentityVerified = false;
    bool rulesetCompatibilityVerified = false;
    bool producerContractVerified = false;
    bool completeSaveVerified = false;
    bool nativeRestoreApproved = false;
};

namespace RetailImportSectionsDetail {

inline std::int32_t ReadElapsed(const unsigned char* data, std::size_t size,
    RetailInflatedSpan game, const RetailSaveStateLimits& limits) {
    RetailStateDetail::Reader validate(data, size, limits);
    if (game.offset > size || game.bytes > size - game.offset || game.bytes < 12u)
        validate.Fail(RetailStateErrorCode::InvalidValue, "Invalid retail Game payload span");
    RetailStateDetail::Reader input(data, game.offset + game.bytes, limits);
    input.Skip(game.offset);
    input.Version(1);
    input.I32(); // m_iEndTurnMessagesSent, not elapsed turns.
    const auto elapsed = input.I32(); // CvGame.cpp Read/Write: Game base +8.
    if (elapsed < 0)
        input.Fail(RetailStateErrorCode::InvalidValue, "Negative elapsed turns in native import candidate");
    return elapsed;
}

inline void RequireOfflinePregame(const RetailSavePreparedPregame& pregame) {
    const auto& wire = pregame.wire;
    if (!pregame.canonicalBooleansChecked || wire.activePlayer < 0 || wire.activePlayer >= 64 ||
        wire.gameTurn < 0 || wire.gameType != 0 ||
        wire.networkIdCount != 64u || wire.maximumOptionNameBytes > 63u || wire.optionNameHasEmbeddedNull)
        throw RetailPregameImportError(RetailPregameImportErrorCode::InvalidLayout, wire.archive.offset,
            "Pregame does not meet offline native candidate metadata requirements");
}

inline bool UnassignedNetworkIds(const unsigned char* raw, std::size_t size,
    const RetailSavePregameImportInspection& wire) {
    // These are original raw-file offsets, not offsets in owned Pregame bytes.
    const auto span = wire.networkIds;
    if (span.offset > size || span.bytes > size - span.offset ||
        wire.networkIdCount != 64u || span.bytes != 64u * 4u)
        throw RetailPregameImportError(RetailPregameImportErrorCode::InvalidLayout, span.offset,
            "Pregame transport-ID payload differs from its checked count");
    bool unassigned = true;
    for (std::size_t i = 0; i < 64u; ++i) {
        const auto* p = raw + span.offset + i * 4u;
        const auto value = static_cast<std::uint32_t>(p[0]) |
            (static_cast<std::uint32_t>(p[1]) << 8) |
            (static_cast<std::uint32_t>(p[2]) << 16) |
            (static_cast<std::uint32_t>(p[3]) << 24);
        if (value != 0xffffffffu) unassigned = false;
    }
    // Existing IDs are preserved. Observing them does not approve importing
    // transport assignments into the offline SDK session.
    return unassigned;
}

inline void Append(RetailSaveImportPreparation& result, std::size_t at,
    unsigned kind, unsigned index, RetailImportStorage storage, RetailInflatedSpan span) {
    const auto& owner = storage == RetailImportStorage::Pregame ? result.pregame.bytes : result.body.bytes;
    if (at >= result.sections.size() || !span.bytes || span.offset > owner.size() ||
        span.bytes > owner.size() - span.offset ||
        span.bytes > static_cast<std::size_t>((std::numeric_limits<std::int32_t>::max)()) ||
        span.bytes > (std::numeric_limits<std::size_t>::max)() - result.totalPayloadBytes)
        throw std::logic_error("Internally prepared native candidate section is invalid");
    result.sections[at] = {kind, index, storage, span};
    result.totalPayloadBytes += span.bytes;
}
} // namespace RetailImportSectionsDetail

class RetailSaveImportSections {
public:
    static RetailSaveImportPreparation Prepare(const unsigned char* raw, std::size_t rawSize,
        const unsigned char* inflated, std::size_t inflatedSize,
        const RetailSaveBodyImportProfile& profile, RetailBodyBooleanImportPolicy booleanPolicy,
        const RetailSaveStateLimits& bodyLimits = RetailSaveStateLimits{},
        const RetailSavePregameLimits& pregameLimits = RetailSavePregameLimits{}) {
        RetailSaveImportPreparation result;
        result.pregame = RetailSavePregameImport::Prepare(raw, rawSize, pregameLimits);
        RetailImportSectionsDetail::RequireOfflinePregame(result.pregame);
        // The SDK consumes Pregame's turn. The retail preview header is observed
        // for diagnostics and is not an additional native restore requirement.
        result.retailHeaderTurnMatches = result.pregame.wire.metadata.currentTurn ==
            static_cast<std::uint32_t>(result.pregame.wire.gameTurn);
        result.offlineTransportUnassigned = RetailImportSectionsDetail::UnassignedNetworkIds(raw, rawSize,
            result.pregame.wire);
        result.body = RetailSaveBodyImport::Prepare(inflated, inflatedSize, profile, booleanPolicy, bodyLimits);
        result.turn = result.pregame.wire.gameTurn;
        result.activePlayer = result.pregame.wire.activePlayer;
        result.elapsed = RetailImportSectionsDetail::ReadElapsed(result.body.bytes.data(), result.body.bytes.size(),
            result.body.wire.game, bodyLimits);

        using Storage = RetailImportStorage;
        std::size_t at = 0;
        auto append = [&](unsigned kind, unsigned index, Storage storage, RetailInflatedSpan span) {
            RetailImportSectionsDetail::Append(result, at++, kind, index, storage, span);
        };
        append(2, 0, Storage::Pregame, {0, result.pregame.bytes.size()});
        append(3, 0, Storage::Body, result.body.wire.game);
        append(4, 0, Storage::Body, result.body.wire.map);
        // Supporting is physically last in this retail body, but the SDK reads
        // it after Map and before Teams. No bytes within a payload are reordered.
        append(5, 0, Storage::Body, result.body.wire.supporting);
        for (unsigned slot = 0; slot < 64u; ++slot)
            append(6, slot, Storage::Body, result.body.wire.teams[slot].whole);
        for (unsigned slot = 0; slot < 64u; ++slot)
            append(7, slot, Storage::Body, result.body.wire.players[slot].whole);
        if (at != result.sections.size() ||
            result.pregame.bytes.size() > (std::numeric_limits<std::size_t>::max)() - result.body.bytes.size() ||
            result.totalPayloadBytes != result.pregame.bytes.size() + result.body.bytes.size())
            throw std::logic_error("Prepared native candidate payloads do not cover their owned buffers");
        // Views describe the owned buffers at return. Later mutation invalidates
        // this evidence. No Bundle section, encoder, file writer or SDK follows.
        return result;
    }
};
} // namespace ZeroSisHost
