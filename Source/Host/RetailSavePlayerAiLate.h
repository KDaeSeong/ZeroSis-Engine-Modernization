#pragma once

// Latest retained BNW Player states after HomelandAI, before Espionage.
// Partial Player framing only; no live state is changed or restored.
#include "RetailSavePlayerMinor.h"
#include "RetailSavePlayerInfrastructure.h"
#include "RetailSavePlayerTraits.h"
#include <cstddef>
#include <cstdint>

namespace ZeroSisHost {

enum class RetailPlayerAiLateProfile {
    InitializedMinorQuests
};

struct RetailSavePlayerAiLateInspection {
    RetailInflatedSpan minorCivAI, dealAI, builderTaskingAI;
    RetailInflatedSpan cityConnections, dangerPlots, traits;
    std::uint32_t dangerPlotCount = 0;
    std::size_t nextInflatedOffset = 0, arrayRecords = 0;
    bool completeSaveVerified = false;
    bool rulesetCompatibilityVerified = false;
};

class RetailSavePlayerAiLate {
public:
    static RetailSavePlayerAiLateInspection InspectAt(const unsigned char* data,
        std::size_t size, std::size_t start, RetailPlayerAiLateProfile profile,
        const RetailSaveStateLimits& limits = RetailSaveStateLimits{}) {
        RetailStateDetail::Reader input(data, size, limits);
        // The outer quest-list count is absent. Original ResetQuestList and
        // Read require exactly 22 initialized lists; Write only asserts it.
        // Require this branch explicitly before consuming any input bytes.
        if (profile != RetailPlayerAiLateProfile::InitializedMinorQuests)
            input.Fail(RetailStateErrorCode::UnsupportedProfile,
                "Unsupported BNW Player late AI profile");
        input.Skip(start);
        RetailSavePlayerAiLateInspection result;
        auto begin = input.Pos();
        RetailStateDetail::ReadPlayerMinorCivAI(input);
        result.minorCivAI = input.SpanFrom(begin);
        begin = input.Pos();
        RetailStateDetail::ReadPlayerDealAI(input);
        result.dealAI = input.SpanFrom(begin);
        begin = input.Pos();
        RetailStateDetail::ReadPlayerBuilderTaskingAI(input);
        result.builderTaskingAI = input.SpanFrom(begin);
        begin = input.Pos();
        RetailStateDetail::ReadPlayerCityConnections(input);
        result.cityConnections = input.SpanFrom(begin);
        begin = input.Pos();
        result.dangerPlotCount = RetailStateDetail::ReadPlayerDangerPlots(input);
        result.dangerPlots = input.SpanFrom(begin);
        begin = input.Pos();
        RetailStateDetail::ReadPlayerTraits(input);
        result.traits = input.SpanFrom(begin);
        result.nextInflatedOffset = input.Pos();
        result.arrayRecords = input.Records();
        return result;
    }
};

} // namespace ZeroSisHost
