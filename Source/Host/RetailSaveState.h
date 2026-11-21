#pragma once

// Structural inspection of the latest supported BNW Game and Map header.
// This consumes already inflated bytes from a separate decoder. It deliberately
// does not accept a retail container, resolve game types, or modify SDK state.
#include "RetailSaveStateWire.h"
#include "RetailSaveGameFront.h"
#include "RetailSaveGameTail.h"
#include <vector>

namespace ZeroSisHost {
struct RetailSaveStateInspection {
    RetailInflatedSpan game, embeddedDatabase, mapHeader;
    std::size_t nextInflatedOffset = 0;
    std::uint32_t mapWidth = 0, mapHeight = 0;
    std::size_t arrayRecords = 0;
    // Framing alone cannot prove either condition, including for synthetic data.
    bool completeSaveVerified = false;
    bool rulesetCompatibilityVerified = false;
};

class RetailSaveState {
public:
    static RetailSaveStateInspection InspectGameAndMapPrefix(const unsigned char* data,
        std::size_t size, const RetailSaveStateProfile& profile,
        const RetailSaveStateLimits& limits = RetailSaveStateLimits{}) {
        RetailStateDetail::Reader reader(data, size, limits);
        if (profile.victoryPointAwards > 4096)
            reader.Fail(RetailStateErrorCode::UnsupportedProfile, "Victory width exceeds supported profile budget");
        RetailSaveStateInspection result;
        RetailStateDetail::ReadGameFront(reader, profile);
        RetailStateDetail::ReadGameTail(reader);
        const auto databaseBytes = reader.U32();
        if (databaseBytes > limits.maxEmbeddedDatabaseBytes)
            reader.Fail(RetailStateErrorCode::EmbeddedDatabaseLimit, "Embedded database exceeds byte budget");
        const auto databaseStart = reader.Pos();
        reader.Skip(databaseBytes);
        result.embeddedDatabase = reader.SpanFrom(databaseStart);
        result.game = reader.SpanFrom(0);

        // CvMap::Read/Write: version, seven int32 values, two bools, a GUID,
        // then two conditional hashed resource arrays. Plot records follow.
        const auto mapStart = reader.Pos();
        reader.Version(1);
        const auto width = reader.I32(), height = reader.I32();
        if (width <= 0 || height <= 0)
            reader.Fail(RetailStateErrorCode::InvalidValue, "Nonpositive BNW map dimensions");
        result.mapWidth = static_cast<std::uint32_t>(width);
        result.mapHeight = static_cast<std::uint32_t>(height);
        if (result.mapWidth > limits.maxMapPlots / result.mapHeight)
            reader.Fail(RetailStateErrorCode::MapPlotLimit, "BNW map dimensions exceed plot budget");
        reader.Fixed(5, 4); // land, owned, wonders, top latitude, bottom latitude
        reader.Bool(); reader.Bool();
        reader.Skip(16); // GUID scalar fields + Data4[8], no native struct padding
        reader.Hashes(4); reader.Hashes(4);
        result.mapHeader = reader.SpanFrom(mapStart);
        result.nextInflatedOffset = reader.Pos();
        result.arrayRecords = reader.Records();
        return result;
    }
    static RetailSaveStateInspection InspectGameAndMapPrefix(const std::vector<unsigned char>& data,
        const RetailSaveStateProfile& profile, const RetailSaveStateLimits& limits = RetailSaveStateLimits{}) {
        return InspectGameAndMapPrefix(data.data(), data.size(), profile, limits);
    }
};
} // namespace ZeroSisHost
