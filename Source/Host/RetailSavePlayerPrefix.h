#pragma once

// Latest retained BNW Player prefix through GrandStrategyAI. DiplomacyAI and
// all subsequent Player/CvPlayerAI state remain unread; no restore is approved.
#include "RetailSavePlayerFront.h"
#include "RetailSavePlayerAiEarly.h"
#include "RetailSavePlayerAiStrategy.h"
#include <cstddef>
#include <cstdint>

namespace ZeroSisHost {

enum class RetailPlayerCatalogProfile {
    InitializedBuildings
};

struct RetailSavePlayerProfile {
    // Grand-strategy array width and the initialized-building-catalog branch
    // are absent from the wire. Require both explicitly; never search for a
    // plausible following version or infer a width from the remaining bytes.
    explicit RetailSavePlayerProfile(std::uint32_t strategies, RetailPlayerCatalogProfile catalog)
        : grandStrategyCount(strategies), catalogProfile(catalog) {}
    std::uint32_t grandStrategyCount;
    RetailPlayerCatalogProfile catalogProfile;
};

struct RetailSavePlayerPrefixInspection {
    RetailInflatedSpan front, policies, economicAI, citySpecializationAI;
    RetailInflatedSpan wonderProductionAI, militaryAI, grandStrategyAI;
    std::int32_t playerId = 0;
    std::size_t nextInflatedOffset = 0, arrayRecords = 0;
    bool completeSaveVerified = false;
    bool rulesetCompatibilityVerified = false;
};

class RetailSavePlayerPrefix {
public:
    static RetailSavePlayerPrefixInspection InspectAt(const unsigned char* data, std::size_t size,
        std::size_t start, const RetailSavePlayerProfile& profile,
        const RetailSaveStateLimits& limits = RetailSaveStateLimits{}) {
        RetailStateDetail::Reader input(data, size, limits);
        if (profile.grandStrategyCount > RetailStateDetail::PlayerGrandStrategyAIProfileLimit ||
            profile.catalogProfile != RetailPlayerCatalogProfile::InitializedBuildings)
            input.Fail(RetailStateErrorCode::UnsupportedProfile, "Unsupported BNW Player inspection profile");
        input.Skip(start);
        RetailSavePlayerPrefixInspection result;
        auto begin = input.Pos();
        result.playerId = RetailStateDetail::ReadPlayerFront(input);
        result.front = input.SpanFrom(begin);
        begin = input.Pos();
        RetailStateDetail::ReadPlayerPolicies(input);
        result.policies = input.SpanFrom(begin);
        begin = input.Pos();
        RetailStateDetail::ReadPlayerEconomicAI(input);
        result.economicAI = input.SpanFrom(begin);
        begin = input.Pos();
        RetailStateDetail::ReadPlayerCitySpecializationAI(input);
        result.citySpecializationAI = input.SpanFrom(begin);
        begin = input.Pos();
        RetailStateDetail::ReadPlayerWonderProductionAI(input);
        result.wonderProductionAI = input.SpanFrom(begin);
        begin = input.Pos();
        RetailStateDetail::ReadPlayerMilitaryAI(input);
        result.militaryAI = input.SpanFrom(begin);
        begin = input.Pos();
        RetailStateDetail::ReadPlayerGrandStrategyAI(input, profile.grandStrategyCount);
        result.grandStrategyAI = input.SpanFrom(begin);
        result.nextInflatedOffset = input.Pos();
        result.arrayRecords = input.Records();
        return result;
    }
};

} // namespace ZeroSisHost
