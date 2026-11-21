#pragma once

// Latest retained BNW Player's seven nested states after GrandStrategyAI.
// Stops before MinorCivAI. This is neither complete Player framing nor restore.
#include "RetailSavePlayerDiplomacy.h"
#include "RetailSavePlayerReligionTech.h"
#include "RetailSavePlayerTactical.h"
#include <cstddef>
#include <cstdint>

namespace ZeroSisHost {

enum class RetailPlayerAiMidCatalogProfile {
    InitializedTechs
};

struct RetailSavePlayerAiMidInspection {
    RetailInflatedSpan diplomacyAI, playerReligions, religionAI, playerTechs;
    RetailInflatedSpan flavorManager, tacticalAI, homelandAI;
    std::size_t nextInflatedOffset = 0, arrayRecords = 0;
    bool completeSaveVerified = false;
    bool rulesetCompatibilityVerified = false;
};

class RetailSavePlayerAiMid {
public:
    static RetailSavePlayerAiMidInspection InspectAt(const unsigned char* data,
        std::size_t size, std::size_t start, RetailPlayerAiMidCatalogProfile catalog,
        const RetailSaveStateLimits& limits = RetailSaveStateLimits{}) {
        RetailStateDetail::Reader input(data, size, limits);
        // A null tech catalog omits seven arrays without a presence word.
        // Require the supported branch explicitly, before reading any bytes.
        if (catalog != RetailPlayerAiMidCatalogProfile::InitializedTechs)
            input.Fail(RetailStateErrorCode::UnsupportedProfile,
                "Unsupported BNW Player AI middle catalog profile");
        input.Skip(start);
        RetailSavePlayerAiMidInspection result;
        auto begin = input.Pos();
        RetailStateDetail::ReadPlayerDiplomacyAI(input);
        result.diplomacyAI = input.SpanFrom(begin);
        begin = input.Pos();
        RetailStateDetail::ReadPlayerReligions(input);
        result.playerReligions = input.SpanFrom(begin);
        begin = input.Pos();
        RetailStateDetail::ReadPlayerReligionAI(input);
        result.religionAI = input.SpanFrom(begin);
        begin = input.Pos();
        RetailStateDetail::ReadPlayerTechs(input);
        result.playerTechs = input.SpanFrom(begin);
        begin = input.Pos();
        RetailStateDetail::ReadPlayerFlavorManager(input);
        result.flavorManager = input.SpanFrom(begin);
        begin = input.Pos();
        RetailStateDetail::ReadPlayerTacticalAI(input);
        result.tacticalAI = input.SpanFrom(begin);
        begin = input.Pos();
        RetailStateDetail::ReadPlayerHomelandAI(input);
        result.homelandAI = input.SpanFrom(begin);
        result.nextInflatedOffset = input.Pos();
        result.arrayRecords = input.Records();
        return result;
    }
};

} // namespace ZeroSisHost
